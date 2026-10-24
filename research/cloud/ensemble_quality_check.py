"""Quality check of the FLAMeS 5-fold cloud run: per-fold and 5-fold-mean Dice / lesion F1 vs expert masks.

Ljubljana (openms) patients except 16-20 and 26-30 were in FLAMeS training (contamination) -> reported apart.
"""
import glob
import os
import sys

import nibabel as nib
import numpy as np
from scipy import ndimage

D = sys.argv[1]
CLEAN_LJ = {f"openms_patient{i:02d}" for i in list(range(16, 21)) + list(range(26, 31))}


def dice(a, b):
    s = a.sum() + b.sum()
    return 2 * (a & b).sum() / s if s else 1.0


def lesion_f1(pred, gt):
    lp, n_p = ndimage.label(pred, structure=np.ones((3, 3, 3)))
    lg, n_g = ndimage.label(gt, structure=np.ones((3, 3, 3)))
    tp_p = len(set(np.unique(lp[gt])) - {0})          # predicted components touching GT
    tp_g = len(set(np.unique(lg[pred])) - {0})        # GT components touched
    prec = tp_p / n_p if n_p else 1.0
    rec = tp_g / n_g if n_g else 1.0
    return 2 * prec * rec / (prec + rec) if prec + rec else 0.0, n_p - tp_p


rows = []
for gtp in sorted(glob.glob(os.path.join(D, "*_gt.nii.gz"))):
    cid = os.path.basename(gtp)[:-len("_gt.nii.gz")]
    folds = [os.path.join(D, f"{cid}_f{k}_prob.nii.gz") for k in range(5)]
    if not all(os.path.exists(f) for f in folds):
        continue
    gt = nib.load(gtp).get_fdata() > 0.5
    probs = [nib.load(f).get_fdata() for f in folds]
    d_f = [dice(p > 0.5, gt) for p in probs]
    mean = np.mean(probs, axis=0) > 0.5
    f1_ens, fp_ens = lesion_f1(mean, gt)
    f1_f0, fp_f0 = lesion_f1(probs[0] > 0.5, gt)
    group = ("ljubljana_clean" if cid in CLEAN_LJ else "ljubljana_in_training") if cid.startswith("openms") else "mslesseg"
    rows.append((cid, group, d_f, dice(mean, gt), f1_f0, f1_ens, fp_f0, fp_ens))

for g in ("mslesseg", "ljubljana_clean", "ljubljana_in_training"):
    r = [x for x in rows if x[1] == g]
    if not r:
        continue
    f0 = np.array([x[2][0] for x in r]); per = np.array([np.mean(x[2]) for x in r]); ens = np.array([x[3] for x in r])
    print(f"{g:22s} n={len(r):3d}  Dice fold0 {np.median(f0):.3f} | mean single fold {np.median(per):.3f} | "
          f"5-fold ensemble {np.median(ens):.3f}  (median)  ensemble better in {np.mean(ens > f0) * 100:.0f}% of cases")
    print(f"{'':22s}        lesion F1 fold0 {np.median([x[4] for x in r]):.3f} -> ensemble {np.median([x[5] for x in r]):.3f}; "
          f"false-positive lesions per scan fold0 {np.mean([x[6] for x in r]):.1f} -> ensemble {np.mean([x[7] for x in r]):.1f}")
