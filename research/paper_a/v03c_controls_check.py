#!/usr/bin/env python3
"""Paper A v0.3 controls addendum §7 — INDEPENDENT re-implementation of the primary count.

Shares no analysis code with v03_candidates / v03_analysis / v03_metrics / v03c_controls:
  * decodes the uint8 maps itself (raw * scl_slope + scl_inter, float64) and averages the 5 folds
    in float64;
  * labels {p >= 0.5} with its own breadth-first search over the 18-neighbourhood;
  * keeps components with voxel count x voxel volume >= 3 mm^3; score = float64 mean;
  * re-derives the 1-mm-site false-candidate null from the patient cache with its own selection
    (cohort in {mslesseg, openms}, FLAMeS-clean, lenient label 0) and checks its SHA-256 against
    the frozen calibration record;
  * computes conformal p-values by direct counting and BH by its own step-up;
  * P2 uses the frozen threshold of the calibration record (s >= threshold).
Then compares, per control and per primary cell, with the main record.

    python -I research/paper_a/v03c_controls_check.py <data dir> <out json>
"""
import hashlib
import json
import os
import pickle
import sys
from collections import deque

import nibabel as nib
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REC = os.path.join(HERE, "..", "..", "docs", "research", "records")
OFFS = [(a, b, c) for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1)
        if (a, b, c) != (0, 0, 0) and abs(a) + abs(b) + abs(c) <= 2]          # 18 neighbours
assert len(OFFS) == 18


def decode(path):
    img = nib.load(path)
    raw = np.asarray(img.dataobj.get_unscaled(), np.float64)
    s, i = img.dataobj.slope, img.dataobj.inter
    return raw * (1.0 if s is None else float(s)) + (0.0 if i is None else float(i)), img


def components(fg):
    """BFS 18-connected components of a boolean volume -> list of (N, 3) index arrays."""
    seen = np.zeros(fg.shape, bool)
    shp = fg.shape
    out = []
    for start in map(tuple, np.argwhere(fg)):
        if seen[start]:
            continue
        seen[start] = True
        q = deque([start])
        comp = []
        while q:
            v = q.popleft()
            comp.append(v)
            for o in OFFS:
                w = (v[0] + o[0], v[1] + o[1], v[2] + o[2])
                if 0 <= w[0] < shp[0] and 0 <= w[1] < shp[1] and 0 <= w[2] < shp[2] and fg[w] and not seen[w]:
                    seen[w] = True
                    q.append(w)
        out.append(np.array(comp))
    return out


def cands(prob, vox):
    res = []
    for c in components(prob >= 0.5):
        if len(c) * vox >= 3.0 - 1e-9:
            res.append(float(prob[c[:, 0], c[:, 1], c[:, 2]].mean()))
    return np.array(sorted(res))


def pvals(scores, null):
    return np.array([(1.0 + np.sum(null >= s)) / (null.size + 1.0) for s in scores])


def bh_count(p, alpha):
    m = p.size
    if m == 0:
        return 0
    ps = np.sort(p)
    ok = [k for k in range(1, m + 1) if ps[k - 1] <= alpha * k / m]
    if not ok:
        return 0
    cut = ps[max(ok) - 1]
    return int(np.sum(p <= cut))


def main():
    data, out = sys.argv[1], sys.argv[2]
    calib = json.load(open(os.path.join(REC, "2026-10-24_paper_a_v03c_calibration.json"), encoding="utf-8"))
    main_rec = json.load(open(os.path.join(REC, "2026-10-24_paper_a_v03c_controls.json"), encoding="utf-8"))
    pc = pickle.load(open(os.path.join(HERE, ".cache", "v03_candidates.pkl"), "rb"))
    res = {"arms": {}}
    for arm, folds in (("ens", range(5)), ("f0", [0])):
        null = []
        for r in pc["cases"]:
            if r["cohort"] in ("mslesseg", "openms") and r["flames_clean"] and arm in r["arms"]:
                a = r["arms"][arm]
                null.extend(np.asarray(a["score"], float)[np.asarray(a["mg0"]) == 0].tolist())
        null = np.array(null, np.float64)
        sha = hashlib.sha256(np.sort(null).tobytes()).hexdigest()
        frozen = calib["arms"][arm]["1-mm sites"]
        p2 = frozen["thresholds"]["P2|0.1"], frozen["thresholds"]["P2|0.2"]
        counts = {"P1|0.1": 0, "P1|0.2": 0, "P2|0.1": 0, "P2|0.2": 0, "raw_any": 0}
        per = {}
        for i in range(1, 101):
            case = f"sub-{i:03d}"
            maps = [decode(os.path.join(data, "cohort", f"{case}_f{k}_prob.nii.gz")) for k in folds]
            prob = np.mean([m[0] for m in maps], axis=0)
            vox = float(np.prod(maps[0][1].header.get_zooms()[:3]))
            sc = cands(prob, vox)
            p = pvals(sc, null)
            n11, n12 = bh_count(p, 0.1), bh_count(p, 0.2)
            q1, q2 = int(np.sum(sc >= p2[0])), int(np.sum(sc >= p2[1]))
            per[case] = {"n": int(sc.size), "P1|0.1": n11, "P1|0.2": n12, "P2|0.1": q1, "P2|0.2": q2,
                         "scores": [round(float(s), 6) for s in sc]}
            counts["raw_any"] += int(sc.size > 0)
            for k, v in (("P1|0.1", n11), ("P1|0.2", n12), ("P2|0.1", q1), ("P2|0.2", q2)):
                counts[k] += int(v > 0)
        res["arms"][arm] = {"null_size": int(null.size), "null_sha256": sha,
                            "null_sha_matches_frozen": sha == frozen["null_sha256"], "counts": counts, "per_control": per}
        print(arm, "null", null.size, "sha ok" if sha == frozen["null_sha256"] else "SHA MISMATCH", counts, flush=True)
    # comparison with the main record
    cmp_ = {}
    for arm in ("ens", "f0"):
        mine = res["arms"][arm]["counts"]
        theirs = {k: main_rec["operating_points"][f"{arm}|1-mm sites|{k.split('|')[0]}|{k.split('|')[1]}|all100"]["scans_with_any"]
                  for k in ("P1|0.1", "P1|0.2", "P2|0.1", "P2|0.2")}
        theirs["raw_any"] = main_rec["raw_candidates"][arm]["scans_with_any_candidate"]
        per_main = {r["case"]: r for r in main_rec["per_control"]}
        n_diff = [c for c, v in res["arms"][arm]["per_control"].items()
                  if v["n"] != per_main[c][f"{arm}_candidates"]]
        sel_diff = []
        if arm == "ens":
            sel_diff = [c for c, v in res["arms"][arm]["per_control"].items()
                        if any(v[k] != per_main[c]["selected_primary"][k] for k in ("P1|0.1", "P1|0.2", "P2|0.1", "P2|0.2"))]
        cmp_[arm] = {"independent": mine, "main": theirs, "counts_equal": mine == theirs,
                     "controls_with_different_candidate_count": n_diff,
                     "controls_with_different_number_selected": sel_diff}
        print(arm, "independent", mine, "main", theirs, "EQUAL" if mine == theirs else "DIFFERENT",
              "| candidate-count diffs:", n_diff, "| selection diffs:", sel_diff, flush=True)
    res["comparison"] = cmp_
    res["all_equal"] = all(v["counts_equal"] and not v["controls_with_different_candidate_count"]
                           and not v["controls_with_different_number_selected"] for v in cmp_.values())
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)
    print("ALL EQUAL" if res["all_equal"] else "MISMATCH - see record", flush=True)


if __name__ == "__main__":
    main()
