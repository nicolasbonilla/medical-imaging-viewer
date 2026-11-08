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
    if subset == "main":
        ids = [r["record_id"] for r in man["records"] if r["record_id"] not in pilot]
        return [(r, a, "en", None) for r in ids for a in arms]
    if subset == "injection":
        return [(r, a, "en", p) for r, p in sorted(subs["injection"].items()) for a in arms]
    if subset == "multilingual":
        return [(r, a, lang, None) for lang in ("es", "de") for r in subs["multilingual"][lang] for a in arms]
    raise ValueError(subset)


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
        try:
            resps = provider.submit(model, items)
        except BudgetExceeded as e:
            print(f"[run] STOP (budget): {e}", flush=True)
            info["stopped"] = str(e)
            break
        calls += len(items)
        with open(out_path, "a", encoding="utf-8") as fh:
            for k, job in owners.items():
                job.consume(resps.get(k) or {"error": "no_response"})
                if job.done:
                    fh.write(json.dumps(job_line(job, model), ensure_ascii=False) + "\n")
        active = [j for j in active if not j.done]
        print(f"[run] round {rnd}: {len(items)} calls, {len(active)} jobs still open, {calls} calls in total", flush=True)
        if max_calls is not None and calls >= max_calls:
            break
    info.update({"ended": time.time(), "calls": calls, "rounds": rnd, "unfinished": len(active)})
    (rd / f"run_info_{int(info['started'])}.json").write_text(json.dumps(info, indent=1))
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
    p = run_dir(alias, subset) / "results.jsonl"
    rows = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return rows


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
    proj = {arm: (sum(v) / len(v) if v else None) for arm, v in per_arm.items()}
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
        other = "sonnet" if args.model == "haiku" else "haiku"
        op = run_dir(other, "pilot") / "projection.json"
        both = proj["projected_usd"] + (json.loads(op.read_text())["projected_usd"] if op.exists() else 0)
        print(f"[run] Anthropic projection (Haiku + Sonnet): {both:.3f} USD; limit {limit}")
        if both > limit and not args.force:
            print("[run] projection exceeds the limit: apply the pre-stated reductions (PREREG 8) first")
            return 3
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
