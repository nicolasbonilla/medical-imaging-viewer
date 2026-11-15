"""Paper 2 runner (PREREG §4 and §8): plan the draft jobs, run the pilot, project the cost, run the full plan.

It reuses v1's providers (Vertex AI Gemini, Anthropic batches), prices and job line. It keeps its own runs directory
and its own caps:
- Gemini: hard cap 30 USD; the full run starts only if the projection is at most 25 USD.
- Anthropic: hard stop 10 USD; the projection must be at most 7 USD.
Spend is counted over this study's ledgers only.

    python -m research.paper_2.runner records --results <paper-1 results dir> --sets <analysis_sets.json> [--geometry <json>]
    python -m research.paper_2.runner pilot   --model gemini
    python -m research.paper_2.runner project --model gemini
    python -m research.paper_2.runner full    --model gemini

Derived records and drafts stay out of the repository: `runs/` and `records*.jsonl` are ignored, because several
sources are non-commercial. They live in the private bucket.
"""
import argparse
import json
import random
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from research.agents_benchmark import config as V1
from research.agents_benchmark.ledger import cost, estimate_request_usd, provider_of
from research.agents_benchmark.runner import job_line
from research.paper_2 import designs as D

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
RECORDS = HERE / "records.jsonl"
SEED = 20261114
CAP = {"gemini": 30.0, "anthropic": 10.0}
PROJECTION_LIMIT = {"gemini": 25.0, "anthropic": 7.0}
SETTING_P = ("dlbs", "wmh2017")

# PREREG §4: which designs each model runs, on which records
PLAN = {
    "gemini": {"designs": ("D1", "D2", "D3", "D4", "D5"), "arms": None, "extra": {"D2i": {"arms": ("flames_ens",),
                                                                                        "sets": SETTING_P + ("ms",)}}},
    "sonnet": {"designs": ("D1", "D2"), "arms": ("flames_ens",), "extra": {}},
    "gemma": {"designs": ("D1",), "arms": ("flames_ens",), "extra": {}},
}
VIEW_OF = {"D1": "base", "D2": "d2", "D2i": "d2", "D3": "base", "D4": "d4", "D5": "d5"}


def load_records(path=RECORDS):
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]


def make_job(rec, design):
    view = rec["views"].get(VIEW_OF[design])
    if view is None:                                  # D5 needs the consensus view (built by consensus_records)
        return None
    return D.DESIGNS[design]({"record_id": view["record_id"], "view": view,
                              "meta": {"scan": rec["scan"], "arm": rec["arm"], "set": rec["set"]}, "a0": None})


def planned(records, alias, pilot_ids=None):
    p = PLAN[alias]
    out = []
    for rec in records:
        key = (rec["scan"], rec["arm"])
        if pilot_ids is not None and key not in pilot_ids:
            continue
        if pilot_ids is None and key in pilot_set(records):
            continue                                  # pilot records are excluded from every analysis (PREREG §8)
        if p["arms"] is None or rec["arm"] in p["arms"]:
            for d in p["designs"]:
                if VIEW_OF[d] in rec["views"]:        # D5 exists only where its consensus view was built
                    out.append((rec, d))
        for d, rule in p["extra"].items():
            if rec["arm"] in rule["arms"] and rec["set"] in rule["sets"]:
                out.append((rec, d))
    return out


def pilot_set(records):
    """10 SibBMS and 10 MS records, seeded; never in any analysis (PREREG §8)."""
    rng = random.Random(SEED)
    out = set()
    for s in ("sibbms", "ms"):
        keys = sorted((r["scan"], r["arm"]) for r in records if r["set"] == s)
        out |= set(rng.sample(keys, min(10, len(keys))))
    return out


def spent(prov):
    tot = 0.0
    for p in RUNS.glob("*/ledger.jsonl"):
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("provider") == prov:
                tot += float(d.get("usd") or 0)
    return tot


def done_keys(path):
    if not path.exists():
        return set()
    out = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if (d.get("result") or {}).get("status") == "ok":
            out.add(d["key"])
    return out


def run_online(provider, model, jobs, out_path, info, workers=None):
    """Each job runs to the end in its own worker. Before every request, spend + its worst case must stay under the cap."""
    prov = provider_of(model)
    state = {"spent": spent(prov), "calls": 0, "done": 0, "stop": None}
    lock = threading.Lock()

    def drive(job):
        n = 0
        while not job.done and state["stop"] is None:
            req = job.next_request()
            if req is None:
                break
            with lock:
                if state["spent"] + estimate_request_usd(model, req, batch=False) > CAP[prov]:
                    state["stop"] = f"{prov}: spent {state['spent']:.4f} USD + next request > cap {CAP[prov]} USD"
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

    with ThreadPoolExecutor(workers or getattr(provider, "workers", 8)) as ex:
        list(ex.map(drive, jobs))
    info.update({"ended": time.time(), "calls": state["calls"], "done": state["done"],
                 "unfinished": len(jobs) - state["done"], "stopped": state["stop"]})
    return info


def run(alias, phase, records, provider=None, workers=None):
    model = V1.MODELS[alias]
    rd = RUNS / f"{alias}-{phase}"
    rd.mkdir(parents=True, exist_ok=True)
    out = rd / "results.jsonl"
    finished = done_keys(out)
    pairs = planned(records, alias, pilot_set(records) if phase == "pilot" else None)
    jobs = [j for j in (make_job(r, d) for r, d in pairs) if j is not None and j.key not in finished]
    if provider is None:
        from research.agents_benchmark.providers import provider_for
        provider = provider_for(model, rd)
    info = {"model": model, "phase": phase, "jobs": len(jobs), "already_done": len(finished), "started": time.time()}
    print(f"[paper2] {alias}/{phase}: {len(jobs)} jobs ({len(finished)} already done)", flush=True)
    info = run_online(provider, model, jobs, out, info, workers)
    (rd / f"run_info_{int(info['started'])}.json").write_text(json.dumps(info, indent=1))
    print(f"[paper2] done {info['done']}/{info['jobs']}; stopped: {info['stopped']}", flush=True)
    return info


def project(alias, records):
    """Pilot mean cost per job, per design, times the planned full jobs; the full run needs ≤ the projection limit."""
    model = V1.MODELS[alias]
    rows = [json.loads(x) for x in (RUNS / f"{alias}-pilot" / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    per = {}
    for d in set(r["arm"] for r in rows):
        us = [r["usd"] for r in rows if r["arm"] == d]
        per[d] = sum(us) / len(us)
    plan = Counter(d for _, d in planned(records, alias))
    total = sum(plan[d] * per.get(d, max(per.values())) for d in plan)
    prov = provider_of(model)
    return {"model": model, "per_job_usd": per, "planned_jobs": dict(plan), "projected_usd": round(total, 3),
            "already_spent_usd": round(spent(prov), 4), "limit_usd": PROJECTION_LIMIT[prov],
            "fits": spent(prov) + total <= PROJECTION_LIMIT[prov]}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["records", "pilot", "project", "full", "plan"])
    ap.add_argument("--model", default="gemini", choices=sorted(PLAN))
    ap.add_argument("--results")
    ap.add_argument("--sets")
    ap.add_argument("--geometry", default=str(RUNS / "geometry.json"), help="acquisition blocks (geometry.py)")
    ap.add_argument("--consensus", help="consensus_eval.py's output folder (D5 views)")
    a = ap.parse_args(argv)
    if a.cmd == "records" and a.geometry and not Path(a.geometry).exists():
        raise SystemExit(f"{a.geometry} is missing: run research.paper_2.geometry first")
    if a.cmd == "records":
        from research.paper_2 import records as R
        sets = json.load(open(a.sets, encoding="utf-8"))
        units, les = R.load(str(Path(a.results) / "per_unit.csv"), str(Path(a.results) / "lesions.csv"), sets)
        geo = json.loads(Path(a.geometry).read_text(encoding="utf-8")) if a.geometry else {}
        recs = R.build(units, les, (lambda uid: geo.get(uid)) if geo else None)
        d5 = None
        if a.consensus:                               # consensus_eval.py's outputs (design D5)
            cu, cl = R.load_consensus(str(Path(a.consensus) / "consensus_per_unit.csv"),
                                      str(Path(a.consensus) / "consensus_lesions.csv"))
            d5 = R.attach_d5(recs, cu, cl)
        RECORDS.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n", encoding="utf-8")
        g1 = R.gate_g1(recs, units)
        print(json.dumps({"records": len(recs), "by_set": Counter(r["set"] for r in recs),
                          "recount_mismatch": sum(r["meta"]["recount_mismatch"] for r in recs), "G1": g1, "D5": d5},
                         indent=1))
        return 0 if g1["passed"] else 1
    recs = load_records()
    if a.cmd == "plan":
        print(json.dumps({"pilot_records": len(pilot_set(recs)),
                          "pilot_jobs": len(planned(recs, a.model, pilot_set(recs))),
                          "full_jobs": Counter(d for _, d in planned(recs, a.model))}, indent=1))
        return 0
    if a.cmd == "project":
        print(json.dumps(project(a.model, recs), indent=1))
        return 0
    if a.cmd == "full":
        pj = project(a.model, recs)
        if not pj["fits"]:
            print(json.dumps(pj, indent=1))
            raise SystemExit("projection above the limit: apply the registered reductions (PREREG §8) first")
    run(a.model, a.cmd, recs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
