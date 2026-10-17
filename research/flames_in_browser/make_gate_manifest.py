"""Build the case list for the input-gate validation harness (gateValidation.flames.test.ts).

    python -I research/flames_in_browser/make_gate_manifest.py <data/external> <open_ms native dir> <out cases.json>

<data/external> must contain `mslesseg/MSLesSeg Dataset/{train,test}` and
`open_ms_data/cross_sectional/MNI/patientNN`. <open_ms native dir> holds patientNN_{FLAIR,T1W,T2W,brainmask}.nii.gz
downloaded from open_ms_data `cross_sectional/coregistered` (CC BY 4.0); zero-background variants of the with-skull
FLAIRs are written to <open_ms native dir>/zerobg/ (largest head component above 10 % of the 99th percentile,
holes filled — the reviewer's "skull but zero background" case). Only public data; nothing is uploaded.
"""
import glob
import json
import os
import sys

import nibabel as nib
import numpy as np
from scipy import ndimage as ndi

ext, native, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
ms = os.path.join(ext, "mslesseg", "MSLesSeg Dataset")
om = os.path.join(ext, "open_ms_data", "cross_sectional", "MNI")
cases = []
for f in sorted(glob.glob(os.path.join(ms, "**", "*.nii.gz"), recursive=True)):
    b = os.path.basename(f)
    for c in ("FLAIR", "T1", "T2"):
        if b.endswith(f"_{c}.nii.gz"):
            split = "test" if os.sep + "test" + os.sep in f else "train"
            cases.append({"id": b.replace(".nii.gz", ""), "dataset": f"mslesseg-{split}", "contrast": c, "variant": "stripped", "file": f})
for d in sorted(glob.glob(os.path.join(om, "patient*"))):
    pid = os.path.basename(d)
    for f in sorted(glob.glob(os.path.join(d, "*.nii.gz"))):
        b = os.path.basename(f)
        for c in ("FLAIR", "T1POST", "T1", "T2"):
            if b.startswith(c + "_"):
                cases.append({"id": f"openms-mni-{pid}-{c}", "dataset": "openms-mni", "contrast": c, "variant": "stripped", "file": f})
                break
os.makedirs(os.path.join(native, "zerobg"), exist_ok=True)
for f in sorted(glob.glob(os.path.join(native, "*_FLAIR.nii.gz"))):
    pid = os.path.basename(f).split("_")[0]
    mask = os.path.join(native, f"{pid}_brainmask.nii.gz")
    for c, suf in (("FLAIR", "FLAIR"), ("T1", "T1W"), ("T2", "T2W")):
        cases.append({"id": f"openms-native-{pid}-{c}", "dataset": "openms-native", "contrast": c, "variant": "stripped",
                      "file": os.path.join(native, f"{pid}_{suf}.nii.gz"), "mask": mask})
    cases.append({"id": f"openms-native-{pid}-FLAIR-skull", "dataset": "openms-native", "contrast": "FLAIR", "variant": "skull-raw", "file": f})
    zb = os.path.join(native, "zerobg", f"{pid}_FLAIR_skull_zerobg.nii.gz")
    if not os.path.exists(zb):
        im = nib.load(f)
        a = np.asanyarray(im.dataobj)
        thr = 0.1 * np.percentile(a[a > 0], 99)
        lab, n = ndi.label(a > thr)
        sizes = ndi.sum(np.ones_like(lab), lab, range(1, n + 1))
        head = ndi.binary_fill_holes(lab == (int(np.argmax(sizes)) + 1))
        nib.save(nib.Nifti1Image((a * head).astype(a.dtype), im.affine, im.header), zb)
    cases.append({"id": f"openms-native-{pid}-FLAIR-skull-zerobg", "dataset": "openms-native", "contrast": "FLAIR",
                  "variant": "skull-zero-background", "file": zb})
with open(out_path, "w") as fh:
    json.dump(cases, fh, indent=1)
print(len(cases), "cases")
