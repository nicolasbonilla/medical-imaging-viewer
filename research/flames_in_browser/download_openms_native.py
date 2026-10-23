"""Download open_ms_data cross_sectional/coregistered volumes (with skull, native FLAIR grid; CC BY 4.0, Lesjak et al. 2018).

python -I research/flames_in_browser/download_openms_native.py OUTDIR PATIENT [PATIENT ...]  -> OUTDIR/patientNN_{FLAIR,T1W,T2W,brainmask}.nii.gz
"""
import os
import sys
import urllib.request

BASE = "https://raw.githubusercontent.com/muschellij2/open_ms_data/master/cross_sectional/coregistered"
out = sys.argv[1]
os.makedirs(out, exist_ok=True)
for p in sys.argv[2:]:
    for name in ("FLAIR", "T1W", "T2W", "brainmask"):
        dst = os.path.join(out, f"{p}_{name}.nii.gz")
        if os.path.exists(dst) and os.path.getsize(dst) > 1000:
            continue
        url = f"{BASE}/{p}/{name}.nii.gz"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (mstool-gate-validation)"})
        with urllib.request.urlopen(req, timeout=300) as r, open(dst, "wb") as f:
            f.write(r.read())
        print(dst, os.path.getsize(dst))
