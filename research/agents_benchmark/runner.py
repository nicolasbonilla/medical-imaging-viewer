"""Run the arms on the records (PREREG sections 4 and 8).

    python -m research.agents_benchmark.runner pilot   --model gemini|haiku|sonnet
    python -m research.agents_benchmark.runner project --model gemini|haiku|sonnet
    python -m research.agents_benchmark.runner full    --model gemini|haiku|sonnet [--subsets main,injection,multilingual]

Every finished job is appended to RUNS_DIR/<model>-<subset>/results.jsonl (resumable); every response is priced in the
ledger of that run; the budget is checked before every submission (ledger.check_budget).
"""
import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from . import config
from .arms import ARMS
from .ledger import BudgetExceeded, cost
from .records import load_manifest, load_record


def planned_jobs(alias, subset, manifest=None):
    """[(record_id, arm, lang, payload)] for one model and subset (PREREG 2.5, 4)."""
    man = manifest or load_manifest()
    subs = man["subsets"]
    arms = config.PLAN[alias]["arms"]
    pilot = set(subs["pilot"])
    if subset == "pilot":
        return [(r, a, "en", None) for r in subs["pilot"] for a in arms]
    red = reductions()
    if subset == "main":
        ids = [r["record_id"] for r in man["records"] if r["record_id"] not in pilot]
        if alias == "sonnet" and red.get("sonnet_half"):
            ids = sonnet_half(man, ids)
        return [(r, a, "en", None) for r in ids for a in arms]
    if alias == "haiku" and red.get("haiku_a2_main_only"):
        arms = [a for a in arms if a != "A2"]
    if subset == "injection":
        return [(r, a, "en", p) for r, p in sorted(subs["injection"].items()) for a in arms]
    if subset == "multilingual":
        return [(r, a, lang, None) for lang in ("es", "de") for r in subs["multilingual"][lang] for a in arms]
    raise ValueError(subset)


def reductions():
    """Pre-stated budget reductions applied so far (PREREG 8), recorded in runs/reductions.json."""
    p = Path(config.RUNS_DIR) / "reductions.json"
    return json.loads(p.read_text()) if p.exists() else {}


def sonnet_half(man, ids):
    """Reduction (1): a seeded, stratified 50 % half of the analysis set for Sonnet."""
    import numpy as np
    strat = {r["record_id"]: r["stratum"] for r in man["records"]}
    rng = np.random.default_rng(config.SEED + 11)
    keep = []
    for st in sorted({strat[i] for i in ids}):
        pool = sorted(i for i in ids if strat[i] == st)
        k = int(round(len(pool) / 2))
        keep += [pool[j] for j in sorted(rng.choice(len(pool), size=k, replace=False))]
    return sorted(keep)


def run_dir(alias, subset):
    d = Path(config.RUNS_DIR) / f"{alias}-{subset}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def done_keys(path):
    keys = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("result", {}).get("status") == "ok":
                keys.add(d["key"])
    return keys


def run(alias, subset, max_calls=None, provider=None, max_tokens_a0=None):
    model = config.MODELS[alias]
    rd = run_dir(alias, subset)
    out_path = rd / "results.jsonl"
    finished = done_keys(out_path)
    jobs = []
    for rid_, arm, lang, payload in planned_jobs(alias, subset):
        mt = (max_tokens_a0 or config.MAX_TOKENS) if arm == "A0" else config.MAX_TOKENS
        job = ARMS[arm](load_record(rid_), lang=lang, payload=payload, max_tokens=mt)
        if job.key not in finished:
            jobs.append(job)
    if provider is None:
        from .providers import provider_for
        provider = provider_for(model, rd)
    info = {"model": model, "alias": alias, "subset": subset, "started": time.time(), "jobs": len(jobs),
            "already_done": len(finished), "max_calls": max_calls, "code": code_fingerprint()}
    (rd / f"run_info_{int(time.time())}.json").write_text(json.dumps(info, indent=1))
    print(f"[run] {alias}/{subset}: {len(jobs)} jobs to run ({len(finished)} already done)", flush=True)
    if not getattr(provider, "batch", True) and max_calls is None:
        return run_online(provider, model, jobs, out_path, info, rd)
    calls, rnd = 0, 0
    active = list(jobs)
    while active:
        rnd += 1
        items, owners = [], {}
        for job in active:
            if max_calls is not None and calls + len(items) >= max_calls:
                break
            req = job.next_request()
            if req is None:
                continue
            k = f"{job.key}#{rnd}"
            items.append((k, req))
            owners[k] = job
        if not items:
            break
        # online providers: submit in chunks and persist each chunk (a stopped run loses at most one chunk)
        chunk = len(items) if getattr(provider, "batch", True) else 240
        stopped = False
        for c0 in range(0, len(items), chunk):
            part = items[c0:c0 + chunk]
            try:
                resps = provider.submit(model, part)
            except BudgetExceeded as e:
                print(f"[run] STOP (budget): {e}", flush=True)
                info["stopped"] = str(e)
                stopped = True
                break
            calls += len(part)
            with open(out_path, "a", encoding="utf-8") as fh:
                for k, _ in part:
                    job = owners[k]
                    job.consume(resps.get(k) or {"error": "no_response"})
                    if job.done:
                        fh.write(json.dumps(job_line(job, model), ensure_ascii=False) + "\n")
            if chunk < len(items):
                print(f"[run] round {rnd}: {c0 + len(part)}/{len(items)} calls", flush=True)
        if stopped:
            break
        active = [j for j in active if not j.done]
        print(f"[run] round {rnd}: {len(items)} calls, {len(active)} jobs still open, {calls} calls in total", flush=True)
        if max_calls is not None and calls >= max_calls:
            break
    info.update({"ended": time.time(), "calls": calls, "rounds": rnd, "unfinished": len(active)})
    (rd / f"run_info_{int(info['started'])}.json").write_text(json.dumps(info, indent=1))
    return info


def run_online(provider, model, jobs, out_path, info, rd):
    """Online providers: every job runs to completion in its own worker and is saved as soon as it finishes."""
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from .ledger import estimate_request_usd, provider_of, spent
    prov = provider_of(model)
    cap = config.ANTHROPIC_HARD_STOP_USD if prov == "anthropic" else config.GEMINI_CAP_USD
    state = {"spent": spent(prov), "calls": 0, "done": 0, "stop": None}
    lock = threading.Lock()

    def drive(job):
        n = 0
        while not job.done and state["stop"] is None:
            req = job.next_request()
            if req is None:
                break
            with lock:
                if state["spent"] + estimate_request_usd(model, req, batch=False) > cap:
                    state["stop"] = f"{prov}: spent {state['spent']:.4f} USD + next request > cap {cap} USD"
                    break
            n += 1
            resp = provider.one(model, f"{job.key}#{n}", req)
            with lock:
                state["spent"] += cost(model, resp.get("usage") or {}, batch=False)
                state["calls"] += 1
            job.consume(resp)
        if job.done:
            with lock, open(out_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(job_line(job, model), ensure_ascii=False) + "\n")
                state["done"] += 1
                if state["done"] % 100 == 0:
                    print(f"[run] {state['done']}/{len(jobs)} jobs done, {state['calls']} calls, "
                          f"{state['spent']:.3f} USD spent ({prov})", flush=True)

    with ThreadPoolExecutor(provider.workers) as ex:
        list(ex.map(drive, jobs))
    if state["stop"]:
        print(f"[run] STOP (budget): {state['stop']}", flush=True)
        info["stopped"] = state["stop"]
    info.update({"ended": time.time(), "calls": state["calls"], "done": state["done"],
                 "unfinished": len(jobs) - state["done"]})
    (rd / f"run_info_{int(info['started'])}.json").write_text(json.dumps(info, indent=1))
    print(f"[run] finished: {state['done']}/{len(jobs)} jobs, {state['calls']} calls", flush=True)
    return info


def job_line(job, model):
    usd = sum(cost(model, c.get("usage") or {}, batch=model.startswith("claude")) for c in job.calls)
    return {"key": job.key, "record_id": job.rec["record_id"], "arm": job.arm, "lang": job.lang, "payload": job.payload,
            "model": model, "max_tokens": job.max_tokens, "result": job.result, "calls": job.calls,
            "n_calls": len(job.calls), "usd": usd, "ts": time.time()}


def code_fingerprint():
    import hashlib
    h = {}
    for p in sorted(config.HERE.glob("*.py")):
        h[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    try:
        import subprocess
        h["git_commit"] = subprocess.run(["git", "-C", str(config.REPO), "rev-parse", "HEAD"], capture_output=True,
                                         text=True).stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    return h


def read_results(alias, subset):
    """One row per job: the last successful result, else the last error (a failed job is re-run on resume)."""
    p = run_dir(alias, subset) / "results.jsonl"
    best = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            prev = best.get(d["key"])
            if prev is None or d["result"].get("status") == "ok" or prev["result"].get("status") != "ok":
                best[d["key"]] = d
    return list(best.values())


def project(alias):
    """Projection from the pilot (PREREG 8) and the A0 truncation contingency (PREREG 4)."""
    rows = read_results(alias, "pilot")
    per_arm = defaultdict(list)
    trunc = Counter()
    for r in rows:
        per_arm[r["arm"]].append(r["usd"])
        if r["arm"] == "A0" and any(c.get("stop_reason") == "max_tokens" for c in r["calls"]):
            trunc["A0"] += 1
    n_a0 = len(per_arm.get("A0", []))
    plan = Counter()
    for subset in config.PLAN[alias]["subsets"]:
        for _, arm, _, _ in planned_jobs(alias, subset):
            plan[arm] += 1
    # cost per CALL from the ledger (finished and unfinished pilot jobs) x expected calls per job: the finished jobs'
    # mean when >= 80 % of the arm's started jobs finished, else the arm's maximum (A2: 9, A3: 3) - conservative
    led = run_dir(alias, "pilot") / "ledger.jsonl"
    call_cost, started = defaultdict(list), defaultdict(set)
    if led.exists():
        for line in led.read_text(encoding="utf-8").splitlines():
            d = json.loads(line)
            k = d["job"].split("#")[0]
            arm = k.split("|")[1]
            call_cost[arm].append(d["usd"])
            started[arm].add(k)
    max_calls = {"A0": 1, "A1": 1, "A2": config.A2_MAX_STEPS + 1, "A3": config.A3_MAX_REGENERATIONS + 1}
    proj = {}
    for arm in plan:
        if not call_cost.get(arm):
            proj[arm] = (sum(per_arm[arm]) / len(per_arm[arm])) if per_arm.get(arm) else None
            continue
        fin = [r for r in rows if r["arm"] == arm]
        mean_calls = (sum(r["n_calls"] for r in fin) / len(fin)) if fin else max_calls[arm]
        if len(fin) < 0.8 * len(started[arm]):
            mean_calls = max_calls[arm]
        proj[arm] = sum(call_cost[arm]) / len(call_cost[arm]) * mean_calls
    total = sum((proj.get(a) or 0) * n for a, n in plan.items())
    out = {"alias": alias, "model": config.MODELS[alias], "pilot_jobs": {a: len(v) for a, v in per_arm.items()},
           "pilot_usd": round(sum(sum(v) for v in per_arm.values()), 5),
           "pilot_calls": sum(r["n_calls"] for r in rows),
           "mean_usd_per_job": {a: (round(v, 6) if v is not None else None) for a, v in proj.items()},
           "planned_jobs": dict(plan), "projected_usd": round(total, 4),
           "a0_truncation_rate": (trunc["A0"] / n_a0) if n_a0 else None,
           "a0_contingency_triggered": bool(n_a0 and trunc["A0"] / n_a0 > 0.20)}
    (run_dir(alias, "pilot") / "projection.json").write_text(json.dumps(out, indent=1))
    return out


JUDGE_RESERVE_USD = 0.6   # Claude judges (PREREG 6): ~100 Sonnet + ~200 Haiku judge calls, worst case


def anthropic_projection():
    tot = JUDGE_RESERVE_USD
    for a_ in ("haiku", "sonnet"):
        p = run_dir(a_, "pilot") / "projection.json"
        if p.exists():
            tot += json.loads(p.read_text())["projected_usd"]
    return tot


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["pilot", "project", "full"])
    ap.add_argument("--model", required=True, choices=sorted(config.MODELS))
    ap.add_argument("--subsets", default=None)
    ap.add_argument("--force", action="store_true", help="run the full plan even if the projection exceeds the limit")
    args = ap.parse_args(argv)
    if args.cmd == "pilot":
        print(json.dumps(run(args.model, "pilot", max_calls=config.PILOT_CALLS_PER_MODEL), indent=1))
        print(json.dumps(project(args.model), indent=1))
        return 0
    if args.cmd == "project":
        print(json.dumps(project(args.model), indent=1))
        return 0
    proj_path = run_dir(args.model, "pilot") / "projection.json"
    if not proj_path.exists():
        print("[run] no pilot projection: run the pilot first")
        return 2
    proj = json.loads(proj_path.read_text())
    limit = (config.ANTHROPIC_PROJECTION_LIMIT_USD if args.model in ("haiku", "sonnet")
             else config.GEMINI_PROJECTION_LIMIT_USD)
    if args.model in ("haiku", "sonnet"):
        both = anthropic_projection()
        print(f"[run] Anthropic projection (Haiku + Sonnet + judges): {both:.3f} USD; limit {limit}")
        steps = [("sonnet_half", "Sonnet on a seeded 50 % stratified half of the analysis set"),
                 ("haiku_a2_main_only", "Haiku A2 limited to the analysis set (no subsets)")]
        for flag, what in steps:
            if both <= limit or args.force:
                break
            red = reductions()
            if not red.get(flag):
                red[flag] = {"applied_at": time.time(), "what": what, "projection_before_usd": both}
                (Path(config.RUNS_DIR) / "reductions.json").write_text(json.dumps(red, indent=1))
                for a_ in ("haiku", "sonnet"):
                    if (run_dir(a_, "pilot") / "results.jsonl").exists():
                        project(a_)
                both = anthropic_projection()
                print(f"[run] pre-stated reduction applied: {what}; projection now {both:.3f} USD", flush=True)
        if both > limit and not args.force:
            print("[run] projection still exceeds the limit after the pre-stated reductions: not started")
            return 3
        proj = json.loads(proj_path.read_text())
    elif proj["projected_usd"] > limit and not args.force:
        print(f"[run] projection {proj['projected_usd']} > {limit} USD: not started")
        return 3
    mt = config.MAX_TOKENS_A0_CONTINGENCY if proj.get("a0_contingency_triggered") else None
    subsets = args.subsets.split(",") if args.subsets else config.PLAN[args.model]["subsets"]
    for s in subsets:
        print(json.dumps(run(args.model, s, max_tokens_a0=mt), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
