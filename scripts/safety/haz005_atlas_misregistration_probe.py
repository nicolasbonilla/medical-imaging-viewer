"""HAZ-005 / CAPA-006 §4 / RC-032 probe: MSMask-atlas regions on an image that is NOT in MNI space.

The zone map depends only on the image grid + affine. Before RC-032, a native (unregistered) scan
was given the atlas zones by grid resampling alone, so the zones stayed where MNI says while the
anatomy was elsewhere. We emulate that by moving the anatomy (rotation, head size, translation)
inside a real MNI scan while keeping its affine, and measure how often each expert lesion's MAGNIMS
region changes, and how often brain DIS (>=2 of PV/JC/IT) flips.

Data: public MSLesSeg cohort (already MNI-registered) with expert masks, in
data/cohorts/mslesseg-flames/ (git-ignored; fetched by the CALM-MS tooling; no data of this device).
Run: backend/venv/Scripts/python scripts/safety/haz005_atlas_misregistration_probe.py
Recorded output: docs/research/records/haz005_atlas_misregistration_output.txt
"""
import glob, os, sys, logging
from pathlib import Path
import numpy as np, nibabel as nib
from scipy import ndimage as ndi
from scipy.spatial.transform import Rotation

os.chdir(Path(__file__).resolve().parents[2] / "backend")
sys.path.insert(0, ".")
logging.disable(logging.CRITICAL)
from app.services.ms_region_classifier import generate_zone_map_atlas
from app.services.lesion_metrics import label_lesions, meets_min_volume
from app.services.longitudinal_tracking_service import _classify_region

files = sorted(glob.glob("../data/cohorts/mslesseg-flames/mslesseg_P*_T1_gt.nii.gz"))[:30]
rng = np.random.default_rng(20260928)
LEVELS = {"small (3 deg, 3%, 5 mm)": (3, 0.03, 5), "moderate (8 deg, 7%, 10 mm)": (8, 0.07, 10),
          "large (15 deg, 10%, 20 mm)": (15, 0.10, 20)}
zone_cache = {}

def regions(zone, lab, ids):
    # Same rule as the product (classify_from_zone_mask): contact, IT > PV > JC, and a lesion
    # in no zone is DWM by default (the first run of this probe used 0 there — CAPA-006 review).
    return {g: (_classify_region(zone, np.argwhere(lab == g))[0] or 4) for g in ids}

def dis(regs):
    return sum(any(r == a for r in regs.values()) for a in (1, 2, 3)) >= 2

res = {k: {"lesions": 0, "changed": 0, "dis_flip": 0, "scans": 0, "vanished": 0} for k in LEVELS}
for f in files:
    img = nib.load(f)
    key = (img.shape, tuple(np.round(img.affine, 3).ravel()))
    if key not in zone_cache:
        zone_cache[key] = generate_zone_map_atlas(img, (1, 1, 1))["zone_mask"]
    zone = zone_cache[key]
    gt = (np.asarray(img.dataobj) > 0).astype(np.uint8)
    lab, n = label_lesions(gt)
    counts = np.bincount(lab.ravel())
    ids = [g for g in range(1, n + 1) if meets_min_volume(int(counts[g]), 1.0)]
    if not ids:
        continue
    ref = regions(zone, lab, ids)
    ctr = (np.array(img.shape) - 1) / 2.0
    for name, (deg, sc, sh) in LEVELS.items():
        axis = rng.normal(size=3); axis /= np.linalg.norm(axis)
        R = Rotation.from_rotvec(np.deg2rad(rng.uniform(-deg, deg)) * axis).as_matrix()
        s = 1.0 + rng.uniform(-sc, sc)
        t = rng.uniform(-sh, sh, size=3)
        A = R * s                                   # anatomy moved: x' = A (x - c) + c + t
        Ainv = np.linalg.inv(A)
        offset = ctr - Ainv @ (ctr + t)             # output->input mapping for affine_transform
        lab2 = ndi.affine_transform(lab, Ainv, offset=offset, order=0, output_shape=lab.shape)
        moved = regions(zone, lab2, ids)            # same (MNI) zone map, anatomy moved
        r = res[name]; r["scans"] += 1
        for g in ids:
            if not np.any(lab2 == g):
                r["vanished"] += 1; continue
            r["lesions"] += 1; r["changed"] += int(moved[g] != ref[g])
        r["dis_flip"] += int(dis({g: v for g, v in moved.items() if np.any(lab2 == g)}) != dis(ref))
    print(f"  {os.path.basename(f)} done", end="\r")
print()
for name, r in res.items():
    print(f"{name:28s}: lesions whose region changed {r['changed']}/{r['lesions']} "
          f"({100*r['changed']/max(r['lesions'],1):.1f}%) | brain-DIS flipped in {r['dis_flip']}/{r['scans']} scans")
