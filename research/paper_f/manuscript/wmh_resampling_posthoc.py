"""Paper F - POST HOC sensitivity analysis of the WMH-SynthSeg resampling rule (reviewer issue M5). OFFLINE.

Why: WMH-SynthSeg is the only tool whose output is resampled. Its 1 mm label map is put on the thick FLAMeS grid by
the pre-registered footprint-MAJORITY rule (a thick voxel is lesion only if >= 50% of its footprint is lesion), which
could remove thin lesions. The native 1 mm outputs were not kept; what was kept on the FLAMeS grid is the footprint
MEAN of WMH-SynthSeg's own lesion probability (`{case}_wmhsynthseg_prob.nii.gz`, written by the same run). So the
variants below threshold that footprint-mean probability. They were FIXED IN THIS FILE BEFORE ANY OF THEM WAS
COMPUTED (2026-10-31) and are labelled post hoc everywhere:

  hard_majority      the pre-registered mask ({case}_wmhsynthseg_seg.nii.gz > 0.5)  - must reproduce per_scan.csv
  prob_mean_ge_0.50  footprint-mean probability >= 0.50
  prob_mean_ge_0.25  footprint-mean probability >= 0.25  (proxy for "lesion fraction > 0.25")
  prob_mean_ge_0.10  footprint-mean probability >= 0.10  (a lesion confined to about 1 of 7-8 sub-slices still counts;
                                                         closest available proxy for "footprint-max")

Each variant is scored with the pre-registered metrics (metrics.lesion_metrics: 14.137 mm^3 filter, 26-connectivity,
any-overlap matching) against the expert mask, paired with the FLAMeS per-scan values in results/per_scan.csv.gz,
and summarised with the pre-registered estimator and bootstrap (cohort-weighted, patient clusters within cohort,
10,000 replicates, seed 20261021). Thick band only (179 scans): the footprint rule is not used on 1 mm scans.

    python research/paper_f/manuscript/wmh_resampling_posthoc.py --tool-dir <dir with *_wmhsynthseg_{seg,prob}.nii.gz> \
        --flames-dir <dir with *_gt.nii.gz>
writes research/paper_f/manuscript/data/wmh_resampling_posthoc.json
"""
import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PF = os.path.dirname(HERE)
sys.path.insert(0, PF)
import metrics as M  # noqa: E402

VARIANTS = ("hard_majority", "prob_mean_ge_0.50", "prob_mean_ge_0.25", "prob_mean_ge_0.10")
THRESH = {"prob_mean_ge_0.50": 0.50, "prob_mean_ge_0.25": 0.25, "prob_mean_ge_0.10": 0.10}
KEYS = ("f1", "false_lesions", "recall", "precision", "dice", "vol_pred_ml")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool-dir", required=True)
    ap.add_argument("--flames-dir", required=True)
    a = ap.parse_args()
    import nibabel as nib

    with gzip.open(os.path.join(PF, "results", "per_scan.csv.gz"), "rb") as f:
        rows = [r for r in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8")) if r["variant"] == "primary"]
    fl = {r["case"]: r for r in rows if r["tool"] == "flames" and r["band"] == "thick"}
    wm = {r["case"]: r for r in rows if r["tool"] == "wmhsynthseg" and r["band"] == "thick"}
    cases = sorted(set(fl) & set(wm))
    per = {v: [] for v in VARIANTS}
    hashes = []
    max_dev = 0.0
    for case in cases:
        gimg = nib.load(os.path.join(a.flames_dir, f"{case}_gt.nii.gz"))
        gt = np.asarray(gimg.get_fdata(dtype=np.float32)) > 0.5
        z = gimg.header.get_zooms()[:3]
        sp = os.path.join(a.tool_dir, f"{case}_wmhsynthseg_seg.nii.gz")
        pp = os.path.join(a.tool_dir, f"{case}_wmhsynthseg_prob.nii.gz")
        hashes.append(f"{os.path.basename(pp)} {sha(pp)}")
        seg = np.asarray(nib.load(sp).get_fdata(dtype=np.float32)) > 0.5
        prob = np.asarray(nib.load(pp).get_fdata(dtype=np.float32))
        assert prob.shape == gt.shape and -1e-6 <= prob.min() and prob.max() <= 1 + 1e-6, case
        preds = {"hard_majority": seg}
        preds.update({k: prob >= t for k, t in THRESH.items()})
        for v, pred in preds.items():
            r = M.lesion_metrics(pred, gt, z)
            row = {"case": case, "cohort": fl[case]["cohort"], "patient": fl[case]["patient"],
                   **{k: r[k] for k in KEYS}, "ref_small": r["size_bins"]["14-50"][0], "det_small": r["size_bins"]["14-50"][1]}
            per[v].append(row)
        # sanity: the pre-registered variant must reproduce the stored per-scan values exactly
        for k in ("f1", "false_lesions", "vol_pred_ml"):
            x, y = num(per["hard_majority"][-1][k]), num(wm[case][k])
            if np.isfinite(x) and np.isfinite(y):
                max_dev = max(max_dev, abs(x - y))
    assert max_dev < 1e-9, f"hard_majority does not reproduce per_scan.csv (max deviation {max_dev})"

    out = {"_provenance": {"analysis": "POST HOC (not pre-registered); variants fixed in the script docstring before computing",
                           "n_scans": len(cases), "band": "thick",
                           "prob_files_digest_sha256": hashlib.sha256("\n".join(hashes).encode()).hexdigest(),
                           "hard_majority_reproduces_per_scan_csv": True},
           "variants": {}}
    for v in VARIANTS:
        rs = per[v]
        strata = [r["cohort"] for r in rs]
        clusters = [r["patient"] for r in rs]
        res = {"absolute": {}, "vs_flames": {}}
        for k in KEYS:
            res["absolute"][k] = M.stratified_cluster_bootstrap([num(r[k]) for r in rs], strata, clusters)
        for k, margin in (("f1", M.EQUIV_MARGIN_F1), ("false_lesions", M.EQUIV_MARGIN_FP)):
            d = [num(r[k]) - num(fl[r["case"]][k]) for r in rs]
            res["vs_flames"][k] = M.stratified_cluster_bootstrap(d, strata, clusters, margin=margin)
        nref = sum(r["ref_small"] for r in rs)
        res["small_14_50_detected_pooled"] = {"detected": sum(r["det_small"] for r in rs), "n_ref": nref,
                                             "proportion": sum(r["det_small"] for r in rs) / nref}
        out["variants"][v] = res
    path = os.path.join(HERE, "data", "wmh_resampling_posthoc.json")
    json.dump(out, open(path, "w", encoding="utf-8"), indent=1)
    print("wrote", path)
    for v in VARIANTS:
        r = out["variants"][v]
        f, p = r["vs_flames"]["f1"], r["vs_flames"]["false_lesions"]
        print(f"{v:18s} F1 {r['absolute']['f1']['estimate']:.3f}  dF1 {f['estimate']:+.3f} [{f['ci95'][0]:+.3f},{f['ci95'][1]:+.3f}]"
              f"  dFP {p['estimate']:+.2f} [{p['ci95'][0]:+.2f},{p['ci95'][1]:+.2f}]  recall {r['absolute']['recall']['estimate']:.3f}"
              f"  vol {r['absolute']['vol_pred_ml']['estimate']:.2f}  small {r['small_14_50_detected_pooled']['proportion']:.3f}")


if __name__ == "__main__":
    main()
