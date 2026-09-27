#!/usr/bin/env python3
"""CALM-MS research — per-candidate MAGNIMS region labels for CERTIFIED dissemination in space.

Builds `.region_cache.npz`: for every scan of the MNI-space cohorts (openms, MSLesSeg, healthy
controls), each lesion candidate gets
  * its score (mean lesion probability; same extraction as the multi-site study),
  * its one-to-one Hungarian match to a ground-truth lesion (lenient IoU>0 and strict IoU>=0.10),
  * its MAGNIMS region: 1 = periventricular, 2 = juxtacortical, 3 = infratentorial,
    4 = deep white matter, 0 = no labelled zone,
and every valid ground-truth lesion (>= 3 mm^3) gets its region too (for ground-truth DIS).

Regions come from the APP'S OWN code, unmodified: `generate_zone_map_atlas` (LST-AI MSMask atlas,
Wiltgen et al. 2024) for the zone map, and the app's per-lesion cascade (any overlap, priority
IT > PV > JC, else DWM — `longitudinal_tracking_service._classify_region`). Research code only
reads these; no Class C module is modified.

The zone map depends only on the image grid + affine, so it is computed once per distinct grid.

    python scripts/calm-ms/region_cache.py
"""
import glob
import importlib.util
import os
import re
import sys

import numpy as np
import nibabel as nib

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(_HERE, "..", "..", "backend")
for p in (_BACKEND, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from app.services.calm_ms_inference import extract_lesion_candidates          # noqa: E402
from app.services.lesion_metrics import label_lesions, meets_min_volume        # noqa: E402
from app.services.ms_region_classifier import generate_zone_map_atlas         # noqa: E402
from app.services.longitudinal_tracking_service import _classify_region       # noqa: E402
from cohort_registry import BUILTIN, subject_of                                # noqa: E402

_spec = importlib.util.spec_from_file_location("_adv", os.path.join(_HERE, "multisite_conformal_advanced.py"))
_adv = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_adv)
_hungarian = _adv._hungarian

THRESHOLD, MIN_VOL, SCORE, SPACING = 0.5, 3.0, "mean", (1.0, 1.0, 1.0)
SITES = ["openms", "mslesseg", "sibbms"]          # the MNI-space cohorts (ISBI is not MNI)
CACHE = os.path.join(_HERE, ".region_cache.npz")
REGION_NAMES = {0: "none", 1: "PV", 2: "JC", 3: "IT", 4: "DWM"}


def _zone_for(img, cache):
    key = (img.shape[:3], tuple(np.round(img.affine, 4).ravel()))
    if key not in cache:
        cache[key] = generate_zone_map_atlas(img, (1.0, 1.0, 1.0))["zone_mask"]
    return cache[key]


def _region(zone, labeled, lab):
    idx = np.argwhere(labeled == lab)
    rid, _ = _classify_region(zone, idx)
    return int(rid) if rid is not None else 0


def build():
    zcache, cases = {}, []
    for site in SITES:
        meta = BUILTIN[site]
        for prob_path in sorted(glob.glob(os.path.join("data", "cohorts", meta["sub"], "*_prob.nii.gz"))):
            case = os.path.basename(prob_path)[:-len("_prob.nii.gz")]
            gt_path = prob_path[:-len("_prob.nii.gz")] + "_gt.nii.gz"
            if not os.path.exists(gt_path):
                continue
            img = nib.load(prob_path)
            prob = np.asarray(img.get_fdata(), dtype=np.float32)
            gt = (np.asarray(nib.load(gt_path).get_fdata()) > 0).astype(np.uint8)
            zone = _zone_for(img, zcache)
            gt_lab, n_raw = label_lesions(gt)
            gt_counts = np.bincount(gt_lab.ravel())
            valid = sorted(g for g in range(1, n_raw + 1)
                           if g < len(gt_counts) and meets_min_volume(int(gt_counts[g]), 1.0))
            gt_regions = {g: _region(zone, gt_lab, g) for g in valid}
            labeled, cands = extract_lesion_candidates(prob, THRESHOLD, SPACING,
                                                       min_volume_mm3=MIN_VOL, score=SCORE)
            m0 = _hungarian(labeled, cands, gt_lab, gt_counts, set(valid), 0.0) if cands else {}
            m1 = _hungarian(labeled, cands, gt_lab, gt_counts, set(valid), 0.10) if cands else {}
            cases.append({
                "site": site, "case": case, "subject": subject_of(site, case, meta),
                "scores": np.array([c.score for c in cands], float),
                "region": np.array([_region(zone, labeled, c.label) for c in cands], int),
                "mg0": np.array([m0[c.label][0] for c in cands], int),
                "mg1": np.array([m1[c.label][0] for c in cands], int),
                "gt_ids": np.array(valid, int),
                "gt_region": np.array([gt_regions[g] for g in valid], int),
            })
            print(f"  [{site}] {case}: {len(cands)} cand, {len(valid)} gt", end="\r")
    print()
    np.savez_compressed(CACHE, cases=np.array(cases, dtype=object))
    return cases


def summarize(cases):
    for site in SITES:
        cs = [c for c in cases if c["site"] == site]
        reg = np.concatenate([c["region"] for c in cs]) if cs else np.array([])
        gtr = np.concatenate([c["gt_region"] for c in cs]) if cs else np.array([])
        cand = {REGION_NAMES[r]: int((reg == r).sum()) for r in range(5)}
        gtd = {REGION_NAMES[r]: int((gtr == r).sum()) for r in range(5)}
        # ground-truth DIS (brain-only McDonald areas PV, JC, IT): >=1 GT lesion in >=2 areas
        dis = [sum(int(np.any(c["gt_region"] == r)) for r in (1, 2, 3)) >= 2 for c in cs]
        print(f"{site:9s} scans={len(cs):3d} | candidates by region {cand} | GT by region {gtd} | "
              f"GT-DIS scans {sum(dis)}/{len(cs)}")


if __name__ == "__main__":
    cs = build()
    summarize(cs)
