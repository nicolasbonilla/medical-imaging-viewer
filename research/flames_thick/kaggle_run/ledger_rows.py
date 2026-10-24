"""Kaggle session records -> docs/research/compute-ledger/kaggle_runs.csv (+ copies of the records).

Each Kaggle session writes sessions/<session_id>.json into its kernel output (kernel_main.py); later
sessions carry the earlier records forward. This script turns them into one ledger row per session
(platform kaggle, 0 USD, hours charged to the free weekly GPU quota) that research/cloud/build_ledger.py
includes, and copies the records (without the long pip freeze, kept once) to docs/research/flames-thick/kaggle/.

    python research/flames_thick/kaggle_run/ledger_rows.py <dir with sessions/*.json> [...]
"""
import csv
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
CSV = os.path.join(REPO, "docs", "research", "compute-ledger", "kaggle_runs.csv")
RECORDS = os.path.join(REPO, "docs", "research", "flames-thick", "kaggle", "sessions")
COLUMNS = ["run_id", "date_utc", "purpose", "paper_or_feature", "status", "machine_type", "vcpus", "memory_gb",
           "cpu_model", "gpu", "start_utc", "end_utc", "wall_seconds", "gpu_hours", "epochs",
           "median_seconds_per_epoch", "notes"]


def row(rec):
    m = rec.get("machine", {})
    gpus = m.get("gpus", [])
    names = sorted({g.split(",")[1].strip() for g in gpus if g.count(",") >= 3})
    driver = sorted({g.split(",")[3].strip() for g in gpus if g.count(",") >= 3})
    gpu = (f"{len(gpus)} × {' / '.join(names)} (driver {', '.join(driver)})" if gpus else "none (CPU session)")
    runs = rec.get("runs", {})
    ep = " / ".join(f"{rid}: {r.get('epochs_this_session')} ({r.get('epochs_done_at_start')}→{r.get('epochs_done_at_end')})"
                    for rid, r in runs.items())
    med = " / ".join(f"{rid}: {r.get('median_s_per_epoch')}" for rid, r in runs.items())
    states = {r.get("state_at_end") for r in runs.values()}
    ok = not rec.get("errors") and states <= {"paused", "completed"} and states
    acc = (m.get("accelerator_requested") or "CPU")
    return {"run_id": f"kaggle-{rec['session']}", "date_utc": rec["start_utc"][:10], "purpose": rec.get("purpose", ""),
            "paper_or_feature": "FLAMeS-thick (docs/research/flames-thick)", "status": "ok" if ok else "failed",
            "machine_type": f"Kaggle {acc}", "vcpus": m.get("vcpus", ""), "memory_gb": m.get("memory_gb", ""),
            "cpu_model": m.get("cpu_model", ""), "gpu": gpu, "start_utc": rec["start_utc"], "end_utc": rec.get("end_utc", ""),
            "wall_seconds": rec.get("wall_seconds", ""), "gpu_hours": rec.get("gpu_hours", ""), "epochs": ep,
            "median_seconds_per_epoch": med,
            "notes": (f"kernel {rec.get('kernel')}; previous {rec.get('previous_kernel')}; git {str(rec.get('git_commit'))[:10]}; "
                      f"venv Python {rec.get('venv_python')}; torch {rec.get('torch', '').split(' [')[0]}; "
                      f"end states {sorted(s for s in states if s)}; errors {len(rec.get('errors', []))}")}


def main(argv=None):
    dirs = (argv if argv is not None else sys.argv[1:]) or ["."]
    recs = {}
    for d in dirs:
        for p in glob.glob(os.path.join(d, "**", "sessions", "*.json"), recursive=True):
            r = json.load(open(p))
            recs[r["session_id"]] = r
    old = {}
    if os.path.exists(CSV):
        old = {r["run_id"]: r for r in csv.DictReader(open(CSV, encoding="utf-8"))}
    os.makedirs(RECORDS, exist_ok=True)
    for sid, r in sorted(recs.items()):
        old[f"kaggle-{r['session']}"] = row(r)
        slim = {k: v for k, v in r.items() if k != "pip_freeze"}
        slim["pip_freeze_lines"] = len(r.get("pip_freeze", []))
        json.dump(slim, open(os.path.join(RECORDS, f"{sid}.json"), "w"), indent=1)
        freeze = os.path.join(RECORDS, "pip_freeze.txt")
        if r.get("pip_freeze") and not os.path.exists(freeze):
            open(freeze, "w").write("\n".join(r["pip_freeze"]) + "\n")
    with open(CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for k in sorted(old, key=lambda k: old[k]["start_utc"]):
            w.writerow({c: old[k].get(c, "") for c in COLUMNS})
    print(f"{len(recs)} session record(s) -> {CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
