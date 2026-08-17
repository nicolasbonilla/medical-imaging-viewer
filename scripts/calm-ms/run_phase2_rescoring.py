#!/usr/bin/env python3
"""CALM-MS Phase 2: paired split-conformal FDR coverage, raw score vs learned score.

Runs the leave-one-case-out experiment that answers Phase 2's question on real
cases: does a calibrated lesion score (learned from per-lesion features) recover
more sensitivity than the base segmenter's pooled probability, at the SAME
conformal FDR guarantee? Both curves share each fold's calibration set and test
case, so the sensitivity lift at matched FDR is attributable to the score alone.

Inputs (either):
  --manifest cases.csv     columns: case,prob_path,gt_path[,second_path]
  --data-dir DIR           {case}_prob.nii.gz + {case}_gt.nii.gz per case;
                           optional {case}_prob2.nii.gz or {case}_ai_seg.nii.gz
                           is used as the second-model agreement feature.

    python scripts/calm-ms/run_phase2_rescoring.py --data-dir ./cohort \
        --alphas 0.05,0.1,0.2,0.3 --threshold 0.5 --out phase2.json
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
_BACKEND = os.path.join(_HERE, "..", "..", "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.services.phase2_lesion_rescoring import run_loo_rescoring_experiment  # noqa: E402


def _load(path):
    img = nib.load(path)
    return np.asarray(img.get_fdata()), img.header.get_zooms()[:3]


def _cases_from_manifest(path):
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            yield row["case"], row["prob_path"], row["gt_path"], row.get("second_path") or None


def _cases_from_dir(d):
    for prob in sorted(glob.glob(os.path.join(d, "*_prob.nii*"))):
        case = os.path.basename(prob).split("_prob.nii")[0]
        gt = glob.glob(os.path.join(d, case + "_gt.nii*"))
        if not gt:
            continue
        second = (glob.glob(os.path.join(d, case + "_prob2.nii*"))
                  or glob.glob(os.path.join(d, case + "_ai_seg.nii*")))
        yield case, prob, gt[0], (second[0] if second else None)


def _print_curve(title, baseline, curve):
    print("\n" + "=" * 74)
    print(title)
    print("=" * 74)
    print("baseline (no control):   FDR=%.3f   sensitivity=%.3f   lesions/case=%.1f"
          % (baseline["fdr_mean"], baseline["sensitivity_mean"], baseline["n_selected_mean"]))
    print("-" * 74)
    print("  target a   realized FDR      95%% CI          sensitivity   lesions/case")
    for r in curve:
        lo, hi = r["realized_fdr_ci95"]
        ci = "[%.3f, %.3f]" % (lo, hi) if lo is not None else "     n/a     "
        print("   %5.2f      %6.3f       %s       %6.3f        %5.1f"
              % (r["alpha"], r["realized_fdr_mean"], ci, r["sensitivity_mean"], r["n_selected_mean"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest")
    ap.add_argument("--data-dir")
    ap.add_argument("--alphas", default="0.05,0.1,0.2,0.3")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--min-volume-mm3", type=float, default=3.0)
    ap.add_argument("--score", default="mean", choices=["mean", "max"])
    ap.add_argument("--l2", type=float, default=1.0)
    ap.add_argument("--out", default="phase2_rescoring.json")
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
    cases, seconds, spacing = [], [], None
    n_second = 0
    for case, prob_path, gt_path, second_path in specs:
        prob, sp = _load(prob_path)
        gt, _ = _load(gt_path)
        if prob.shape != gt.shape:
            sys.exit(f"[{case}] shape mismatch prob {prob.shape} vs gt {gt.shape}")
        spacing = spacing or tuple(float(x) for x in sp)
        cases.append((prob.astype(float), (gt > 0).astype(np.uint8)))
        sm = None
        if second_path:
            s, _ = _load(second_path)
            if s.shape == prob.shape:
                sm = (s > (0.5 if s.max() <= 1.0 else 0)).astype(np.uint8)
                n_second += 1
        seconds.append(sm)
        print("  %-20s prob%s%s" % (case, prob.shape, "  +2nd" if sm is not None else ""), flush=True)

    alphas = [float(a) for a in args.alphas.split(",")]
    print("\nRunning paired split-conformal re-scoring experiment "
          "(%d/%d cases have a 2nd model)..." % (n_second, len(cases)), flush=True)
    res = run_loo_rescoring_experiment(
        cases, alphas, args.threshold, spacing,
        min_volume_mm3=args.min_volume_mm3, score=args.score,
        second_masks=seconds if n_second else None, l2=args.l2)

    _print_curve("PHASE 1 - raw pooled probability  (%d cases, thr=%.2f)"
                 % (res["n_cases"], args.threshold), res["baseline"], res["curve_raw"])
    _print_curve("PHASE 2 - learned calibrated score  (%d cases, thr=%.2f)"
                 % (res["n_cases"], args.threshold), res["baseline"], res["curve_learned"])

    print("\n" + "-" * 74)
    print("SENSITIVITY LIFT AT MATCHED TARGET (learned - raw):")
    raw = {c["alpha"]: c for c in res["curve_raw"]}
    for r in res["curve_learned"]:
        d = r["sensitivity_mean"] - raw[r["alpha"]]["sensitivity_mean"]
        print("   a=%.2f   d-sensitivity = %+.3f   (raw %.3f -> learned %.3f)"
              % (r["alpha"], d, raw[r["alpha"]]["sensitivity_mean"], r["sensitivity_mean"]))

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"threshold": args.threshold, "spacing": spacing, "result": res}, f, indent=2)
    print("\nWritten: %s" % os.path.abspath(args.out))


if __name__ == "__main__":
    main()
