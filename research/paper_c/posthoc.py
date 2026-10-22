#!/usr/bin/env python3
"""Paper C pilot — POST HOC explanatory checks (written AFTER the pre-registered results were seen).

Nothing here changes a pre-registered number. Questions:
  1. Why is S_sub anti-informative on open_ms (candidate AUROC < 0.5)? Score and volume of true vs
     false candidates per arm.
  2. Ceiling of any patient-level threshold: in how many active patients does the best TRUE
     candidate outrank every FALSE candidate of the same patient (necessary for a flag without a
     false call at some threshold)?
  3. How far apart are the calibration quantile (largest false scores across patients) and the
     typical true score — i.e. how much the score would need to improve.

    python research/paper_c/posthoc.py
"""
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import run_pilot as R  # noqa: E402

OUT = os.path.join(C.RECORDS, "2026-10-21_paper_c_posthoc.json")


def q(v, p):
    v = [x for x in v if math.isfinite(x)]
    return float(np.percentile(v, p)) if v else None


def main():
    cache = json.load(open(R.CACHE))
    rec = {"note": "POST HOC (after results)", "arms": {}}
    for arm in ("A1", "A2", "A2b", "A3", "A4", "A4b"):   # A4/A4b added 2026-10-22, after the A4 results (post hoc)
        units = R.units_for(arm, cache)
        raw_key = {"A1": None, "A3": None}.get(arm)
        st = [c["score"] for u in units for c in u["cands"] if c["true"]]
        sf = [c["score"] for u in units for c in u["cands"] if not c["true"]]
        # volumes from the raw cache
        src = cache["open_ms"] if arm in ("A1", "A4", "A4b") else [u for u in cache["mslesseg"] if u["first_pair"]]
        raw = [u["dsub"]["1.5"] if arm in ("A1", "A3") else u["dseg"] for u in src]
        vt = [c["volume_mm3"] for r in raw for c in r if c["true"]]
        vf = [c["volume_mm3"] for r in raw for c in r if not c["true"]]
        ceiling = 0
        for u in units:
            t = [c["score"] for c in u["cands"] if c["true"] and math.isfinite(c["score"])]
            f = [c["score"] for c in u["cands"] if not c["true"] and math.isfinite(c["score"])]
            if t and (not f or max(t) > max(f)):
                ceiling += 1
        mf = sorted(R.K.max_false(u["cands"]) for u in units)
        a = {"score_true_q25_50_75": [q(st, p) for p in (25, 50, 75)],
             "score_false_q25_50_75": [q(sf, p) for p in (25, 50, 75)],
             "volume_true_median_mm3": q(vt, 50), "volume_false_median_mm3": q(vf, 50),
             "patients_best_true_outranks_all_false": ceiling, "patients": len(units),
             "max_false_score_sorted": [round(x, 3) if math.isfinite(x) else None for x in mf],
             "true_scores_above_80pct_of_patient_maxfalse": float(np.mean([s > q(mf, 80) for s in st])) if st else None}
        if raw_key is None and arm in ("A2", "A2b", "A4", "A4b"):
            kinds = {}
            for r in raw:
                for c in r:
                    k = (c["kind"], c["true"])
                    kinds[f"{k[0]}_{'true' if k[1] else 'false'}"] = kinds.get(f"{k[0]}_{'true' if k[1] else 'false'}", 0) + 1
            a["candidate_kinds"] = kinds
        rec["arms"][arm] = a
        print(f"{arm}: score true q50 {a['score_true_q25_50_75'][1]:.2f} vs false q50 {a['score_false_q25_50_75'][1]:.2f}; "
              f"volume true {a['volume_true_median_mm3']:.0f} vs false {a['volume_false_median_mm3']:.0f} mm3; "
              f"best true outranks all false in {ceiling}/{len(units)} patients; "
              f"share of true scores above the 80th pct of patient max-false {a['true_scores_above_80pct_of_patient_maxfalse']:.2f}"
              + (f"; kinds {a.get('candidate_kinds')}" if "candidate_kinds" in a else ""))
    json.dump(rec, open(OUT, "w"), indent=1)
    print("wrote", os.path.relpath(OUT, C.ROOT))


if __name__ == "__main__":
    main()
