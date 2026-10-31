"""Paper D — reader-study case selection (READER_STUDY_PROTOCOL.md §3), deterministic and outcome-free.

Research code, not the device. Uses only what the automated grid already computed (share of the
1,120 primary pipelines saying "brain DIS met", expert lesion count, patient) — no reader data exist.

Selection (fixed in the protocol before any read):
  * every NON-UNANIMOUS scan of the primary (clean) set (0 < share < 1): 48 scans;
  * 36 UNANIMOUS control scans, one per patient, from patients that have no non-unanimous scan,
    sampled with seed 20261031 stratified by expert-lesion-count tertile (cuts 18 / 30, protocol S3)
    to follow the tertile mix of the non-unanimous set as far as availability allows;
  * 4 TRAINING scans from the 20 FLAMeS-in-sample Ljubljana scans (outside every primary analysis);
  * 12 REPEAT scans (6 non-unanimous, 6 unanimous, seeded) read a second time after the washout;
  * Task 2 (per-lesion region labels): every expert lesion (18-connected, >= 3 mm3, G0 labelling) of
    the non-unanimous scans; at most 10 per unanimous scan (seeded random sample).
Case codes RS-001..RS-084 are assigned in a seeded random order, so a code says nothing about the
stratum. Reading orders are a separate seeded permutation per reader and per session.

    python research/paper_d/select_reader_cases.py --data-root <main checkout>/data \
        --out <main checkout>/data/experiments/paper-d/reader-study
The manifest holds the strata: it is kept by the study coordinator, never given to readers and never
committed (the repository is public). Only its SHA-256 is recorded in READER_STUDY_PROTOCOL.md.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402

from research.paper_d.analyze import REF, DEFAULT, LSTAI_SHIPPED, cell, load, matrix  # noqa: E402
from research.paper_d.common import data_root, experiments_dir  # noqa: E402

SEED = 20261031
N_CONTROLS = 36
N_TRAINING = 4
N_REPEAT_EACH = 6
TASK2_CAP_UNANIMOUS = 10
TERTILE_CUTS = (18, 30)
SEC_PER_LESION = 7          # planning assumptions, re-estimated on the training cases (protocol §8)
MIN_PER_SCAN_TASK1 = 3.0


def tertile(n):
    return 0 if n <= TERTILE_CUTS[0] else (1 if n <= TERTILE_CUTS[1] else 2)


def expert_lesions(out_dir: Path, case: str):
    d = json.load(gzip.open(out_dir / "scans" / f"{case}.json.gz", "rt"))
    return [l for l in d["lesions"]["E"] if l["G"] == "G0" and l["conn"] == 18 and l["volume_mm3"] >= 3.0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    root = data_root(args.data_root)
    out_dir = experiments_dir(root)
    df, _lesions, record = load(out_dir)
    meta = record["scan_meta"]
    done = sorted(set(df.case) & set(record["scans"]))
    clean = [c for c in done if not meta[c]["flames_in_sample"]]
    insample = [c for c in done if meta[c]["flames_in_sample"]]

    D = matrix(df, clean)
    share = D.mean(axis=1).to_numpy()
    ref = cell(df, clean, REF)
    dflt = cell(df, clean, DEFAULT)
    lst = cell(df, clean, LSTAI_SHIPPED)
    ntot = cell(df, clean, REF, "n_total")
    info = {c: {"patient": meta[c]["patient"], "dataset": meta[c]["dataset"], "share_met": float(s),
                "reference_dis": int(r), "device_default_dis": int(dd), "lstai_shipped_dis": int(ls),
                "expert_lesions": int(n), "tertile": tertile(int(n))}
            for c, s, r, dd, ls, n in zip(clean, share, ref, dflt, lst, ntot)}

    rng = np.random.default_rng(SEED)
    nonun = [c for c in clean if 0 < info[c]["share_met"] < 1]
    unan = [c for c in clean if info[c]["share_met"] in (0.0, 1.0)]
    nu_patients = {info[c]["patient"] for c in nonun}
    # one candidate scan per eligible patient (seeded), patients without a non-unanimous scan
    by_patient = {}
    for c in unan:
        p = info[c]["patient"]
        if p in nu_patients:
            continue
        by_patient.setdefault(p, []).append(c)
    pool = []
    for p in sorted(by_patient):
        opts = sorted(by_patient[p])
        pool.append(opts[int(rng.integers(len(opts)))])
    # stratified by tertile to follow the non-unanimous tertile mix
    nu_mix = Counter(info[c]["tertile"] for c in nonun)
    target = {t: int(round(N_CONTROLS * nu_mix.get(t, 0) / len(nonun))) for t in (0, 1, 2)}
    while sum(target.values()) != N_CONTROLS:            # rounding fix, deterministic
        t = max(target, key=lambda x: nu_mix.get(x, 0)) if sum(target.values()) < N_CONTROLS else min(target, key=lambda x: nu_mix.get(x, 0))
        target[t] += 1 if sum(target.values()) < N_CONTROLS else -1
    avail = {t: sorted(c for c in pool if info[c]["tertile"] == t) for t in (0, 1, 2)}
    controls, shortfall = [], 0
    for t in (0, 1, 2):
        take = min(target[t] + shortfall, len(avail[t]))
        shortfall = target[t] + shortfall - take
        controls += list(rng.choice(avail[t], size=take, replace=False)) if take else []
    if shortfall:                                          # fill from the remaining pool, low burden first
        rest = sorted((c for c in pool if c not in controls), key=lambda c: info[c]["expert_lesions"])
        controls += rest[:shortfall]
    controls = sorted(controls)
    assert len(controls) == N_CONTROLS, len(controls)

    training = sorted(rng.choice(sorted(insample), size=N_TRAINING, replace=False).tolist())
    reading = sorted(nonun) + controls
    codes = rng.permutation(len(reading))
    code_of = {c: f"RS-{int(k) + 1:03d}" for c, k in zip(reading, codes)}
    repeat = sorted(rng.choice(sorted(nonun), N_REPEAT_EACH, replace=False).tolist()
                    + rng.choice(controls, N_REPEAT_EACH, replace=False).tolist())

    cases, n_task2 = [], 0
    for c in sorted(reading, key=lambda x: code_of[x]):
        les = expert_lesions(out_dir, c)
        ids = [int(l["id"]) for l in les]
        if c in nonun:
            t2 = ids
        else:
            t2 = sorted(rng.choice(ids, size=min(TASK2_CAP_UNANIMOUS, len(ids)), replace=False).tolist())
        n_task2 += len(t2)
        s = info[c]["share_met"]
        cases.append({"code": code_of[c], "scan": c, **info[c],
                      "stratum": "non-unanimous" if c in nonun else "unanimous",
                      "contested": bool(0.1 <= s <= 0.9),
                      "repeat_read": c in repeat, "task2_lesion_ids_E18_G0": t2,
                      "n_expert_lesions_listed": len(ids)})
    train_cases = [{"code": f"TR-{i + 1}", "scan": c, "patient": meta[c]["patient"],
                    "expert_lesions": len(expert_lesions(out_dir, c))} for i, c in enumerate(training)]

    orders = {}
    for r in ("A", "B", "C"):
        rr = np.random.default_rng(SEED + ord(r))
        codes_sorted = sorted(code_of.values())
        orders[f"reader_{r}"] = {"session1_task1": list(rr.permutation(codes_sorted)),
                                 "session2_task2": list(rr.permutation(codes_sorted)),
                                 "session3_repeat_task1": list(rr.permutation(sorted(code_of[c] for c in repeat)))}

    n_scans = len(reading)
    hours = {"training_and_setup": 0.75,
             "task1_scan_reads": round(n_scans * MIN_PER_SCAN_TASK1 / 60, 1),
             "task2_lesion_labels": round(n_task2 * SEC_PER_LESION / 3600, 1),
             "repeat_reads": round(len(repeat) * MIN_PER_SCAN_TASK1 / 60, 1)}
    hours["total"] = round(sum(hours.values()), 1)
    summary = {"seed": SEED, "primary_set_scans": len(clean), "non_unanimous": len(nonun),
               "contested": sum(1 for c in nonun if 0.1 <= info[c]["share_met"] <= 0.9),
               "unanimous_available": len(unan), "eligible_control_patients": len(pool),
               "controls": len(controls), "reading_scans": n_scans,
               "patients_in_reading_set": len({info[c]["patient"] for c in reading}),
               "reference_not_met_in_reading_set": sum(1 for c in reading if info[c]["reference_dis"] == 0),
               "device_default_differs_from_reference": sum(1 for c in reading if info[c]["device_default_dis"] != info[c]["reference_dis"]),
               "tertile_mix_nonunanimous": {str(k): v for k, v in sorted(nu_mix.items())},
               "tertile_mix_controls": {str(k): v for k, v in sorted(Counter(info[c]["tertile"] for c in controls).items())},
               "expert_lesions_task1_total": sum(info[c]["expert_lesions"] for c in reading),
               "task2_lesions_total": n_task2, "repeat_scans": len(repeat), "training_scans": len(training),
               "planning_hours_per_reader": hours,
               "planning_assumptions": {"minutes_per_scan_task1": MIN_PER_SCAN_TASK1, "seconds_per_lesion_task2": SEC_PER_LESION}}

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"note": "COORDINATOR ONLY - holds the strata. Never give this file to a reader.",
                "script": "research/paper_d/select_reader_cases.py", "summary": summary,
                "cases": cases, "training": train_cases}
    blob = json.dumps(manifest, indent=1)
    (out / "case_manifest.json").write_bytes(blob.encode("utf-8"))      # bytes: same hash on every OS
    (out / "reading_orders.json").write_bytes(json.dumps(orders, indent=1).encode("utf-8"))
    summary["manifest_sha256"] = hashlib.sha256(blob.encode()).hexdigest()
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
