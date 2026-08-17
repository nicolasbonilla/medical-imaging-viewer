#!/usr/bin/env python3
"""Run LST-AI over a cohort to produce the probability maps CALM-MS needs.

LST-AI (CompImg/LST-AI) is a 3x 3D-U-Net ensemble for MS lesion segmentation. Run
with --probability_map it emits the ensemble's per-voxel lesion PROBABILITY — the
missing input for the conformal experiment. This wrapper runs it per case (via
Docker, the cleanest path on Windows) and lays outputs out for
scripts/calm-ms/run_conformal_experiment.py.

DOCKER (recommended — no conda/Python-3.9 needed):
    docker pull jqmcginnis/lst-ai:v1.2.0
    python scripts/calm-ms/run_lstai_cohort.py --manifest ./cohort/cohort.csv \
        --out-dir ./cohort --docker-image jqmcginnis/lst-ai:v1.2.0 --limit 1
    # inspect case001 output, verify, then drop --limit to run all.

NATIVE (Linux / a python 3.8-3.9 env with `pip install -e .` of LST-AI):
    python scripts/calm-ms/run_lstai_cohort.py --manifest ./cohort/cohort.csv --out-dir ./cohort

The T1/FLAIR here are RAW (not skull-stripped / co-registered), so do NOT pass
--stripped — LST-AI runs its full preprocessing. Outputs per case:
{case}_prob.nii.gz + {case}_gt.nii.gz for run_conformal_experiment.py --data-dir.
"""
import argparse
import csv
import glob
import os
import shutil
import subprocess
import sys


def _find_prob_map(*dirs):
    """Locate the probability-map NIfTI LST-AI wrote (name/space varies)."""
    for d in dirs:
        for pat in ("*prob*map*.nii*", "*probability*.nii*", "*prob*.nii*"):
            hits = sorted(glob.glob(os.path.join(d, "**", pat), recursive=True))
            if hits:
                return hits[0]
    return None


def _native_cmd(lst_bin, r, case_out, tmp, device, stripped):
    cmd = [lst_bin, "--t1", r["t1_path"], "--flair", r["flair_path"],
           "--output", case_out, "--temp", tmp,
           "--probability_map", "--device", device]
    if stripped:
        cmd.append("--stripped")
    return cmd


def _docker_cmd(image, out_abs, case, device, stripped):
    cmd = ["docker", "run", "--rm", "-v", out_abs + ":/work", image,
           "--t1", "/work/%s_t1.nii.gz" % case,
           "--flair", "/work/%s_flair.nii.gz" % case,
           "--output", "/work/_lst_%s" % case,
           "--temp", "/work/_tmp_%s" % case,
           "--probability_map", "--device", device]
    if stripped:
        cmd.append("--stripped")
    return cmd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, help="CSV: case,t1_path,flair_path,expert_path")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--docker-image", help="e.g. jqmcginnis/lst-ai:v1.2.0 (uses Docker)")
    ap.add_argument("--device", default="cpu", help="GPU id (e.g. 0) or 'cpu'")
    ap.add_argument("--stripped", action="store_true",
                    help="images ALREADY skull-stripped+registered (NOT our raw pull)")
    ap.add_argument("--lst-bin", default="lst", help="native LST-AI executable")
    ap.add_argument("--limit", type=int, default=0, help="run only the first N cases (0 = all)")
    args = ap.parse_args()

    out_abs = os.path.abspath(args.out_dir)
    os.makedirs(out_abs, exist_ok=True)
    with open(args.manifest, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if args.limit:
        rows = rows[: args.limit]
    mode = "docker(%s)" % args.docker_image if args.docker_image else "native(%s)" % args.lst_bin
    print("Cohort: %d cases  |  mode: %s\n" % (len(rows), mode), flush=True)

    ok = 0
    for i, r in enumerate(rows, 1):
        case = r["case"]
        case_out = os.path.join(out_abs, "_lst_" + case)
        tmp = os.path.join(out_abs, "_tmp_" + case)
        os.makedirs(case_out, exist_ok=True)
        os.makedirs(tmp, exist_ok=True)
        if args.docker_image:
            cmd = _docker_cmd(args.docker_image, out_abs, case, args.device, args.stripped)
        else:
            cmd = _native_cmd(args.lst_bin, r, case_out, tmp, args.device, args.stripped)
        print("[%d/%d] %s" % (i, len(rows), case), flush=True)
        try:
            subprocess.run(cmd, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print("    FAILED: %s" % e, flush=True)
            continue

        prob = _find_prob_map(case_out, tmp)
        if not prob:
            print("    no probability map found (looked in _lst_%s / _tmp_%s)" % (case, case), flush=True)
            continue
        shutil.copyfile(prob, os.path.join(out_abs, case + "_prob.nii.gz"))
        # gt already present from the pull step; copy from manifest if not.
        gt_dst = os.path.join(out_abs, case + "_gt.nii.gz")
        if not os.path.exists(gt_dst) and os.path.exists(r.get("expert_path", "")):
            shutil.copyfile(r["expert_path"], gt_dst)
        ok += 1
        print("    -> %s_prob.nii.gz  (from %s)" % (case, os.path.basename(prob)), flush=True)

    print("\nDone: %d/%d cases with probability maps in %s" % (ok, len(rows), out_abs))
    if ok >= 2:
        print("Next: python scripts/calm-ms/run_conformal_experiment.py --data-dir %s" % args.out_dir)
    elif ok == 1:
        print("1 case done — inspect its *_prob.nii.gz vs *_gt.nii.gz alignment, then drop --limit.")


if __name__ == "__main__":
    main()
