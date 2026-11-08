#!/usr/bin/env python3
"""Paper 1 gate G2 (PREREG-healthy-controls.md section 7) — INDEPENDENT recount of the false lesions.

Shares no analysis code with evaluate_controls.py / hc_core.py / paper A:
  * decodes every map itself (raw integers x scl_slope + scl_inter, float64) and averages the five FLAMeS
    folds in float64;
  * thresholds at >= 0.5 (probability arms) or > 0 (tool masks);
  * labels with its own breadth-first search over the 18 neighbours (faces + edges);
  * keeps components with voxel count x voxel volume >= 3 mm^3.
Then compares, per control and arm, the number of false lesions and their total volume with
{results}/per_control.csv (exact equality of counts; volumes within 1e-3 mm^3).

    python -I research/paper_1/check_counts.py --results research/paper_1/results --flames-dir D/flames \
        --lstai-dir D/lstai --tool-dir D/toolbench [--out <json>]
"""
import argparse
import csv
import json
import os
import sys
from collections import deque

import nibabel as nib
import numpy as np

NEIGH = [(i, j, k) for i in (-1, 0, 1) for j in (-1, 0, 1) for k in (-1, 0, 1)
         if (i, j, k) != (0, 0, 0) and abs(i) + abs(j) + abs(k) <= 2]
assert len(NEIGH) == 18


def decode(path):
    img = nib.load(path)
    raw = np.asarray(img.dataobj.get_unscaled(), np.float64)
    s, b = img.dataobj.slope, img.dataobj.inter
    s = 1.0 if s is None or not np.isfinite(s) else float(s)
    b = 0.0 if b is None or not np.isfinite(b) else float(b)
    return raw * s + b, img


def bfs_components(fg):
    seen = np.zeros(fg.shape, bool)
    out = []
    X, Y, Z = fg.shape
    for start in map(tuple, np.argwhere(fg)):
        if seen[start]:
            continue
        seen[start] = True
        q, n = deque([start]), 0
        while q:
            x, y, z = q.popleft()
            n += 1
            for i, j, k in NEIGH:
                a, b, c = x + i, y + j, z + k
                if 0 <= a < X and 0 <= b < Y and 0 <= c < Z and fg[a, b, c] and not seen[a, b, c]:
                    seen[a, b, c] = True
                    q.append((a, b, c))
        out.append(n)
    return out


def count(fg, vox):
    sizes = [n for n in bfs_components(fg) if n * vox >= 3.0 - 1e-9]
    return len(sizes), float(sum(sizes) * vox)


def arm_foreground(arm, case, a):
    if arm == "flames_ens":
        maps = [decode(os.path.join(a.flames_dir, f"{case}_f{k}_prob.nii.gz")) for k in range(5)]
        return np.mean([m for m, _ in maps], axis=0) >= 0.5, maps[0][1]
    if arm == "flames_f0":
        m, img = decode(os.path.join(a.flames_dir, f"{case}_f0_prob.nii.gz"))
        return m >= 0.5, img
    if arm == "lstai":
        m, img = decode(os.path.join(a.lstai_dir, f"{case}_lstai_prob.nii.gz"))
        return m >= 0.5, img
    m, img = decode(os.path.join(a.tool_dir, f"{case}_{arm}_seg.nii.gz"))
    return m > 0, img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--flames-dir", required=True)
    ap.add_argument("--lstai-dir", default="")
    ap.add_argument("--tool-dir", default="")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    rows = list(csv.DictReader(open(os.path.join(a.results, "per_control.csv"))))
    res = {"compared": 0, "count_equal": 0, "volume_equal": 0, "mismatches": [], "by_arm": {}}
    for r in rows:
        if r["available"] != "1":
            continue
        fg, img = arm_foreground(r["arm"], r["case"], a)
        vox = float(np.prod([float(z) for z in img.header.get_zooms()[:3]]))
        n, vol = count(fg, vox)
        ok_n = n == int(r["n_false_lesions"])
        ok_v = abs(vol - float(r["false_volume_mm3"])) <= 1e-3
        res["compared"] += 1
        res["count_equal"] += ok_n
        res["volume_equal"] += ok_v
        b = res["by_arm"].setdefault(r["arm"], {"compared": 0, "equal": 0})
        b["compared"] += 1
        b["equal"] += ok_n and ok_v
        if not (ok_n and ok_v):
            res["mismatches"].append({"case": r["case"], "arm": r["arm"], "main": [r["n_false_lesions"], r["false_volume_mm3"]],
                                      "independent": [n, round(vol, 3)]})
    res["passed"] = res["compared"] > 0 and res["count_equal"] == res["volume_equal"] == res["compared"]
    print(json.dumps({k: v for k, v in res.items() if k != "mismatches"}), "mismatches:", len(res["mismatches"]), flush=True)
    out = a.out or os.path.join(a.results, "independent_check.json")
    json.dump(res, open(out, "w"), indent=1)
    sys.exit(0 if res["passed"] else 1)


if __name__ == "__main__":
    main()
