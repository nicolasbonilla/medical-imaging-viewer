#!/usr/bin/env python3
"""Warp each case's LST-AI MNI probability map into the expert (native) space.

LST-AI emits the lesion probability in its MNI template (193x229x193); the expert
masks live on the 1mm brain template (181x217x181). This reslices the MNI prob
back into the expert grid using the flair->MNI affine LST-AI produced, applied
INVERSE via greedy (run inside the LST-AI container — light, no ML, no OOM).

Per case in --dir it expects: {case}_flair.nii.gz (ref grid), {case}_prob_mni.nii.gz,
{case}_flair2mni.mat  -> writes {case}_prob.nii.gz (181x217x181), which
run_conformal_experiment.py --data-dir consumes alongside {case}_gt.nii.gz.

    python scripts/warp_cohort_probs.py --dir ./cohort --image jqmcginnis/lst-ai:v1.2.0
"""
import argparse
import glob
import os
import subprocess
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="./cohort")
    ap.add_argument("--image", default="jqmcginnis/lst-ai:v1.2.0")
    args = ap.parse_args()
    d = os.path.abspath(args.dir)

    cases = sorted(os.path.basename(p)[:-len("_prob_mni.nii.gz")]
                   for p in glob.glob(os.path.join(d, "*_prob_mni.nii.gz")))
    if not cases:
        sys.exit("no *_prob_mni.nii.gz found in %s" % d)
    print("warping %d cases -> native (expert) space\n" % len(cases), flush=True)

    ok = 0
    for i, case in enumerate(cases, 1):
        ref = "%s_flair.nii.gz" % case
        mov = "%s_prob_mni.nii.gz" % case
        mat = "%s_flair2mni.mat" % case
        out = "%s_prob.nii.gz" % case
        if not all(os.path.exists(os.path.join(d, f)) for f in (ref, mov, mat)):
            print("[%2d] %s  missing inputs — skipped" % (i, case), flush=True)
            continue
        cmd = ["docker", "run", "--rm", "-v", d + ":/work", "--entrypoint", "greedy", args.image,
               "-d", "3", "-rf", "/work/" + ref, "-rm", "/work/" + mov, "/work/" + out,
               "-r", "/work/" + mat + ",-1", "-ri", "LINEAR"]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            ok += 1
            print("[%2d] %s  -> %s" % (i, case, out), flush=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print("[%2d] %s  greedy FAILED: %s" % (i, case, e), flush=True)

    print("\n%d/%d warped. Next:" % (ok, len(cases)))
    print("  python scripts/run_conformal_experiment.py --data-dir %s --out experiment.json" % args.dir)


if __name__ == "__main__":
    main()
