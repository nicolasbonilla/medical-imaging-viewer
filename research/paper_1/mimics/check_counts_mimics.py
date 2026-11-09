#!/usr/bin/env python3
"""Paper 1 addendum, gate G2 (PREREG-mimics-thickness.md section 8) — INDEPENDENT recount.

Shares no code with evaluate_mimics.py / hc_core.py / paper F: it reuses only the healthy arm's independent
checker (research/paper_1/check_counts.py: own NIfTI decoding in float64, own breadth-first search over the 18
neighbours, own >= 3 mm^3 filter) and adds its own re-implementation of the thick-section simulation.
  1. counts: for every evaluated unit and arm, the number of lesions on the native grid (map >= 0.5 for the
     probability arms, > 0 for the tool masks) must equal `n_native` in the evaluation records exactly;
  2. simulation: for 5 seeded C1 scans of the SAMSEG subset (their 1-mm input is stored byte-identical as
     {case}_th1_FLAIR) and every simulated thickness, a slab average (box, no gap, phase 0) followed
     by np.interp between slab centres, with the 1-mm background kept at 0, must match the stored simulated input
     within 1e-4 of the intensity range.

    python -I research/paper_1/mimics/check_counts_mimics.py --records W/records.json --pf D/pf --mimics D/mimics \
        --c1-sources D/c1src --out research/paper_1/mimics/results/independent_check.json
"""
import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import check_counts as CC  # noqa: E402  (healthy-arm independent checker)

SEED = 20261109


def foreground(arm, iid, src):
    if arm == "flames_ens":
        maps = [CC.decode(os.path.join(src, "flames", f"{iid}_f{k}_prob.nii.gz")) for k in range(5)]
        return np.mean([m for m, _ in maps], axis=0) >= 0.5, maps[0][1]
    if arm == "flames_f0":
        m, img = CC.decode(os.path.join(src, "flames", f"{iid}_f0_prob.nii.gz"))
        return m >= 0.5, img
    if arm == "lstai":
        m, img = CC.decode(os.path.join(src, "lstai", f"{iid}_lstai_prob.nii.gz"))
        return m >= 0.5, img
    m, img = CC.decode(os.path.join(src, "toolbench", f"{iid}_{arm}_seg.nii.gz"))
    return m > 0, img


def simulate_independent(x, t):
    """Box slab of t mm (1-mm voxels, no gap, first slab centred on voxel 0), then linear interpolation."""
    n = x.shape[2]
    centres = np.arange(0, n - 1 + t / 2.0 + 1e-9, t)
    half = t / 2.0
    slabs = []
    for c in centres:
        w = np.clip(np.minimum(np.arange(n) + 0.5, c + half) - np.maximum(np.arange(n) - 0.5, c - half), 0, None)
        slabs.append(np.tensordot(x, w / w.sum(), axes=([2], [0])))
    slabs = np.stack(slabs, axis=-1)
    out = np.empty_like(x, dtype=np.float64)
    z = np.arange(n, dtype=float)
    for i in range(x.shape[0]):
        for j in range(x.shape[1]):
            out[i, j] = np.interp(z, centres, slabs[i, j])
    out[x == 0] = 0.0
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", required=True)
    ap.add_argument("--pf", required=True)
    ap.add_argument("--mimics", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    recs = json.load(open(a.records))
    res = {"counts": {"compared": 0, "equal": 0, "mismatches": []}, "simulation": []}
    for r in recs:
        for arm, x in r["arms"].items():
            if not x.get("available"):
                continue
            src = a.pf if (r["block"] in ("C1", "C2") and r["T"] == 1.0 and not (arm == "samseg" and r["block"] == "C1")) else a.mimics
            iid = f"{r['base']}_th1" if (arm == "samseg" and r["block"] == "C1" and r["T"] == 1.0) else r["id"]
            fg, img = foreground(arm, iid, src)
            vox = float(np.prod(img.header.get_zooms()[:3]))
            n, _ = CC.count(fg, vox)
            res["counts"]["compared"] += 1
            if n == x["n_native"]:
                res["counts"]["equal"] += 1
            else:
                res["counts"]["mismatches"].append({"id": r["id"], "arm": arm, "independent": n, "main": x["n_native"]})
    c1 = sorted({r["base"] for r in recs if r["block"] == "C1" and "samseg" in r["arms"]})
    pick = [c1[i] for i in sorted(np.random.RandomState(SEED).permutation(len(c1))[:5])]
    thick = sorted({r["T"] for r in recs if r["block"] == "C1" and r["T"] > 1})
    for c in pick:
        x, _ = CC.decode(os.path.join(a.mimics, "inputs", f"{c}_th1_FLAIR.nii.gz"))
        for t in thick:
            stored, _ = CC.decode(os.path.join(a.mimics, "inputs", f"{c}_th{int(t)}_FLAIR.nii.gz"))
            mine = simulate_independent(x, t)
            rng = float(x.max() - x.min()) or 1.0
            diff = float(np.abs(mine - stored).max())
            res["simulation"].append({"case": c, "T": t, "max_abs_diff_over_range": round(diff / rng, 8),
                                      "pass": diff / rng <= 1e-4})
    res["passed"] = (res["counts"]["equal"] == res["counts"]["compared"] and all(s["pass"] for s in res["simulation"]))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(res, open(a.out, "w"), indent=1)
    print(f"G2 counts: {res['counts']['equal']}/{res['counts']['compared']} equal; simulation: "
          f"{sum(s['pass'] for s in res['simulation'])}/{len(res['simulation'])} within 1e-4; "
          f"{'PASS' if res['passed'] else 'FAIL'}", flush=True)
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
