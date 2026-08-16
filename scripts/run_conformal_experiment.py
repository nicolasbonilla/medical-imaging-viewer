#!/usr/bin/env python3
"""Run the CALM-MS headline experiment on real cases.

Feeds a cohort of (probability map, expert mask) NIfTI pairs through the
leave-one-case-out conformal FDR-coverage engine and prints the plot-that-is-the-
paper: target alpha vs realized FDR (95% CI) vs sensitivity, against the
uncontrolled baseline.

Get the probability maps by running a probabilistic segmenter (e.g. LST-AI) on
the cohort's T1w+FLAIR; the expert masks are the `Expert Rater` ground truth.

Inputs (either):
  --manifest cases.csv     columns: case,prob_path,gt_path
  --data-dir DIR           expects {case}_prob.nii.gz + {case}_gt.nii.gz per case

    python scripts/run_conformal_experiment.py --data-dir ./cohort \
        --alphas 0.05,0.1,0.2,0.3 --threshold 0.5 --out experiment.json
"""
import argparse
import csv
import glob
import json
import os
import sys

import numpy as np
import nibabel as nib

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(_HERE, "..", "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.services.conformal_experiment import run_loo_fdr_experiment  # noqa: E402


def _load(path):
    img = nib.load(path)
    return np.asarray(img.get_fdata()), img.header.get_zooms()[:3]


def _cases_from_manifest(path):
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            yield row["case"], row["prob_path"], row["gt_path"]


def _cases_from_dir(d):
    for prob in sorted(glob.glob(os.path.join(d, "*_prob.nii*"))):
        case = os.path.basename(prob).split("_prob.nii")[0]
        gt = glob.glob(os.path.join(d, case + "_gt.nii*"))
        if gt:
            yield case, prob, gt[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest")
    ap.add_argument("--data-dir")
    ap.add_argument("--alphas", default="0.05,0.1,0.2,0.3")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--min-volume-mm3", type=float, default=3.0)
    ap.add_argument("--score", default="mean", choices=["mean", "max"])
    ap.add_argument("--out", default="conformal_experiment.json")
    args = ap.parse_args()

    if args.manifest:
        specs = list(_cases_from_manifest(args.manifest))
    elif args.data_dir:
        specs = list(_cases_from_dir(args.data_dir))
    else:
        sys.exit("provide --manifest or --data-dir")
    if len(specs) < 2:
        sys.exit(f"need >= 2 cases, found {len(specs)}")

    print("Loading %d cases..." % len(specs), flush=True)
    cases, spacing = [], None
    for case, prob_path, gt_path in specs:
        prob, sp = _load(prob_path)
        gt, _ = _load(gt_path)
        if prob.shape != gt.shape:
            sys.exit(f"[{case}] shape mismatch prob {prob.shape} vs gt {gt.shape}")
        spacing = spacing or tuple(float(x) for x in sp)
        cases.append((prob.astype(float), (gt > 0).astype(np.uint8)))
        print("  %-20s prob%s" % (case, prob.shape), flush=True)

    alphas = [float(a) for a in args.alphas.split(",")]
    print("\nRunning leave-one-case-out conformal FDR experiment...", flush=True)
    res = run_loo_fdr_experiment(
        cases, alphas, args.threshold, spacing,
        min_volume_mm3=args.min_volume_mm3, score=args.score)

    b = res["baseline"]
    print("\n" + "=" * 72)
    print("CALM-MS FDR-COVERAGE  (%d cases, threshold=%.2f)" % (res["n_cases"], args.threshold))
    print("=" * 72)
    print("baseline (no control):   FDR=%.3f   sensitivity=%.3f   lesions/case=%.1f"
          % (b["fdr_mean"], b["sensitivity_mean"], b["n_selected_mean"]))
    print("-" * 72)
    print("  target α   realized FDR      95%% CI          sensitivity   lesions/case")
    for r in res["curve"]:
        lo, hi = r["realized_fdr_ci95"]
        ci = "[%.3f, %.3f]" % (lo, hi) if lo is not None else "     n/a     "
        print("   %5.2f      %6.3f       %s       %6.3f        %5.1f"
              % (r["alpha"], r["realized_fdr_mean"], ci, r["sensitivity_mean"], r["n_selected_mean"]))

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"threshold": args.threshold, "spacing": spacing, "result": res}, f, indent=2)
    print("\nWritten: %s" % os.path.abspath(args.out))


if __name__ == "__main__":
    main()
