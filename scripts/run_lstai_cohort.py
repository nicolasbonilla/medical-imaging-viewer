#!/usr/bin/env python3
"""Run LST-AI over a cohort to produce the probability maps CALM-MS needs.

LST-AI (CompImg/LST-AI) is a 3x 3D-U-Net ensemble for MS lesion segmentation. Run
with --probability_map it emits the ensemble's per-voxel lesion PROBABILITY — the
missing input for the conformal experiment. This wrapper runs it per case and
lays the outputs out for scripts/run_conformal_experiment.py.

PREREQUISITES (LST-AI needs Python 3.8-3.9, NOT 3.11 — use a separate env):
    conda create -n lstai python=3.9 -y && conda activate lstai
    git clone https://github.com/CompImg/LST-AI && cd LST-AI && pip install -e .

INPUT manifest CSV, columns: case,t1_path,flair_path,expert_path
    (expert_path = the 'Expert Rater' ground-truth mask for that case)

    python scripts/run_lstai_cohort.py --manifest cohort.csv --out-dir ./cohort \
        --device cpu --stripped
    # then:
    python scripts/run_conformal_experiment.py --data-dir ./cohort

Outputs per case in --out-dir: {case}_prob.nii.gz + {case}_gt.nii.gz
(exactly what run_conformal_experiment.py --data-dir expects).
"""
import argparse
import csv
import glob
import os
import shutil
import subprocess
import sys
import tempfile


def _find_prob_map(out_dir):
    """Locate the probability-map NIfTI LST-AI wrote (name varies by version)."""
    for pat in ("*prob*map*.nii*", "*probability*.nii*", "*prob*.nii*"):
        hits = sorted(glob.glob(os.path.join(out_dir, "**", pat), recursive=True))
        if hits:
            return hits[0]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, help="CSV: case,t1_path,flair_path,expert_path")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--device", default="cpu", help="GPU id (e.g. 0) or 'cpu'")
    ap.add_argument("--stripped", action="store_true",
                    help="images are already skull-stripped (ISBI/MNI) -> pass --stripped to lst")
    ap.add_argument("--lst-bin", default="lst", help="LST-AI executable")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    with open(args.manifest, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print("Cohort: %d cases\n" % len(rows), flush=True)

    ok = 0
    for i, r in enumerate(rows, 1):
        case = r["case"]
        case_out = os.path.join(args.out_dir, "_lst_" + case)
        os.makedirs(case_out, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            cmd = [args.lst_bin,
                   "--t1", r["t1_path"], "--flair", r["flair_path"],
                   "--output", case_out, "--temp", tmp,
                   "--probability_map", "--device", args.device]
            if args.stripped:
                cmd.append("--stripped")
            print("[%d/%d] %s" % (i, len(rows), case), flush=True)
            try:
                subprocess.run(cmd, check=True)
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                print("    FAILED: %s" % e, flush=True)
                continue

        prob = _find_prob_map(case_out)
        if not prob:
            print("    no probability map found in %s (check --probability_map output name)" % case_out, flush=True)
            continue
        shutil.copyfile(prob, os.path.join(args.out_dir, case + "_prob.nii.gz"))
        shutil.copyfile(r["expert_path"], os.path.join(args.out_dir, case + "_gt.nii.gz"))
        ok += 1
        print("    -> %s_prob.nii.gz + %s_gt.nii.gz" % (case, case), flush=True)

    print("\nDone: %d/%d cases ready in %s" % (ok, len(rows), os.path.abspath(args.out_dir)))
    if ok >= 2:
        print("Next: python scripts/run_conformal_experiment.py --data-dir %s" % args.out_dir)


if __name__ == "__main__":
    main()
