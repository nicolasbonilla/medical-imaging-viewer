"""Paper 1 addendum, amendment 1 (PREREG-mimics-thickness.md section 15): freeze the reduced analysis sets
BEFORE any tool output exists. Adds to research/paper_1/mimics/analysis_sets.json:

  B1_sample         100 DLBS participants aged 50-89, 25 per decade (50s, 60s, 70s, 80s): within each decade
                    the ids are sorted by participant number and drawn in random order with ONE
                    numpy.random.RandomState(SEED) stream, decades in ascending order (rng.permutation(n)[:25]);
                    reduction (iii) "DLBS 75" = draw ranks 1-19 in the 50s, 60s, 70s and 1-18 in the 80s.
  C1_native_thickness  MSLesSeg native FLAIR slice thickness per scan (dataset CSV
                    info_dataset/patient_scanners_info/patient_scanners_info_FLAIR.csv; Ljubljana 0.8 mm).
  C1_samseg_subset  50 of the 125 FLAMeS-clean C1 scans: all 10 Ljubljana-clean scans + 40 MSLesSeg scans,
                    stratified by native thickness (<= 2.3 mm: 15, 3 mm: 18, 4-5 mm: 5, unknown: 2 =
                    proportional to 43/52/15/5), drawn with RandomState(SEED) per stratum in that order from
                    the sorted ids.
  pilot             the pilot inputs (section 15.6).

    python -I research/paper_1/mimics/freeze_amendment_sets.py --mslesseg-csv <patient_scanners_info_FLAIR.csv>
"""
import argparse
import csv
import hashlib
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SETS = os.path.join(HERE, "analysis_sets.json")
SEED = 20261109
PER_DECADE = 25
DECADES = (50, 60, 70, 80)
REDUCED_RANKS = {50: 19, 60: 19, 70: 19, 80: 18}          # 75 in total
SAMSEG_STRATA = (("<=2.3mm", 15), ("3mm", 18), ("4-5mm", 5), ("unknown", 2))


def num(pid):
    return int(pid.split("-")[1])


def dlbs_sample(dlbs):
    rng = np.random.RandomState(SEED)
    out, rank = [], {}
    for dec in DECADES:
        ids = sorted((s for s, v in dlbs.items() if v["set"] == "B1" and dec <= v["age_mri_w1"] < dec + 10), key=num)
        order = rng.permutation(len(ids))[:PER_DECADE]
        for r, i in enumerate(order, 1):
            out.append(ids[i])
            rank[ids[i]] = {"decade": dec, "draw_rank": r, "decade_pool": len(ids)}
    reduced = [s for s in out if rank[s]["draw_rank"] <= REDUCED_RANKS[rank[s]["decade"]]]
    return sorted(out, key=num), rank, sorted(reduced, key=num)


def case_of(patient, tp):
    n = int(patient[1:])
    return f"mslesseg_{patient}" if n >= 54 else f"mslesseg_{patient}_{tp}"


def native_thickness(csv_path, ms_cases):
    out = {}
    for r in csv.DictReader(open(csv_path, encoding="utf-8-sig"), delimiter=";"):
        v = r["SliceThickness[mm]"].strip()
        out[case_of(r["Patient"], r["Timepoint"])] = None if v.upper() == "NONE" else float(v)
    for c in ms_cases:
        if c.startswith("openms_"):
            out[c] = 0.8                                   # Ljubljana 3D FLAIR 0.47 x 0.47 x 0.8 mm
    missing = [c for c in ms_cases if c not in out]
    if missing:
        raise SystemExit(f"no native thickness for {missing[:5]}")
    return {c: out[c] for c in sorted(ms_cases)}


def stratum(t):
    if t is None:
        return "unknown"
    if t <= 2.3:
        return "<=2.3mm"
    if t == 3.0:
        return "3mm"
    return "4-5mm"


def samseg_subset(ms, nat):
    clean = sorted(c for c, v in ms.items() if not v["flames_contaminated"])
    lj = [c for c in clean if c.startswith("openms_")]
    rng = np.random.RandomState(SEED)
    picked = list(lj)
    for name, k in SAMSEG_STRATA:
        pool = sorted(c for c in clean if c.startswith("mslesseg_") and stratum(nat[c]) == name)
        picked += [pool[i] for i in sorted(rng.permutation(len(pool))[:k])]
    return sorted(picked)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mslesseg-csv", required=True)
    a = ap.parse_args()
    sets = json.load(open(SETS))
    sample, rank, reduced = dlbs_sample(sets["B_dlbs"])
    nat = native_thickness(a.mslesseg_csv, list(sets["C1_ms_iso"]))
    sub = samseg_subset(sets["C1_ms_iso"], nat)
    sets["B1_sample"] = {"rule": f"25 per decade (50-59, 60-69, 70-79, 80-89) from B1; RandomState({SEED}).permutation per "
                                 "decade in ascending order over ids sorted by participant number",
                         "seed": SEED, "ids": sample, "draw": rank,
                         "reduced_75": {"rule": "draw ranks 1-19 (50s, 60s, 70s) and 1-18 (80s)", "ids": reduced}}
    sets["C1_native_thickness"] = {"source": "MSLesSeg info_dataset/patient_scanners_info/patient_scanners_info_FLAIR.csv",
                                   "source_sha256": hashlib.sha256(open(a.mslesseg_csv, "rb").read()).hexdigest(),
                                   "ljubljana": "0.8 mm (3D FLAIR 0.47 x 0.47 x 0.8 mm)", "mm": nat,
                                   "stratum": {c: stratum(t) for c, t in nat.items()}}
    sets["C1_samseg_subset"] = {"rule": "the 10 Ljubljana-clean scans + 40 FLAMeS-clean MSLesSeg scans stratified by native "
                                        f"thickness {dict(SAMSEG_STRATA)}, RandomState({SEED}).permutation per stratum "
                                        "in that order over sorted ids", "seed": SEED, "ids": sub}
    b = {s for s in sample}
    p1 = min((s for s in sample if sets["B_dlbs"][s]["recruitment_cohort"] == 1), key=num)
    sets["pilot"] = {"A_wmh2017": ["wmh_utrecht_1"], "B_dlbs": [p1],
                     "C1_ms": [f"{min(c for c in sub if c.startswith('mslesseg_'))}_th7"], "C2_sibbms": ["sub-001_th7"],
                     "note": "one input per data type, every tool; lowest id of each rule; structural check (G3) only"}
    assert p1 in b and len(sample) == 100 and len(reduced) == 75 and len(sub) == 50
    json.dump(sets, open(SETS, "w", newline="\n"), indent=1)
    dec = {d: sum(1 for s in sample if rank[s]["decade"] == d) for d in DECADES}
    strata = {}
    for c in sub:
        strata[stratum(nat[c])] = strata.get(stratum(nat[c]), 0) + 1
    print(json.dumps({"B1_sample": len(sample), "per_decade": dec, "reduced_75": len(reduced), "samseg_subset": len(sub),
                      "samseg_strata": strata, "pilot": sets["pilot"]}, indent=1))


if __name__ == "__main__":
    main()
