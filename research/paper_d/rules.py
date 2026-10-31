"""Lesion definition, region-assignment rules and the brain-DIS rule for paper D (research code).

Region codes follow the device (lesion_analysis_service.MAGNIMS_REGIONS): 1 PV, 2 JC, 3 IT, 4 DWM.

Rules (protocol §5.4):
  APP      device rule: contact with the device's MSMask zone map, priority IT > PV > JC > DWM; a
           lesion in no zone is DWM by default (ms_region_classifier.classify_from_zone_mask).
  APP-LV   APP on a zone map whose ventricles are the lateral ventricles only.
  LSTAI    LST-AI v1.2.0 annotate.py verbatim: 26-connected lesions, each dilated by a 3x3x3 cube;
           PV if the dilated lesion touches MSMask label 4, else JC if it touches label 2, else IT if
           it touches label 5, else "subcortical" (= DWM). No minimum size in LST-AI itself.
  LSTAI-LV LSTAI with label 4 restricted to the lateral ventricles.
  APP-3MM  (secondary) APP with the 3 / 4 / 3 mm zone distances the device's IFU stated until CAPA-006.
  APP-MAJ  (secondary) zone holding most lesion voxels (the device's pre-audit majority rule);
           ties broken IT > PV > JC > DWM.

Everything is vectorised over lesions (np.bincount) — the device's per-lesion loops would make the
1,000+-pipeline grid infeasible; tests/test_paper_d.py proves equality with the device functions.
"""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage as ndi

PV, JC, IT, DWM = 1, 2, 3, 4
DIS_REGIONS = (PV, JC, IT)
STRUCT18 = ndi.generate_binary_structure(3, 2)   # device convention (lesion_metrics, RC-030)
STRUCT26 = np.ones((3, 3, 3), dtype=bool)         # LST-AI: skimage label(connectivity=3)
CUBE = np.ones((3, 3, 3), dtype=bool)

SPHERE_3MM_MM3 = 4.0 / 3.0 * math.pi * 1.5 ** 3    # 14.137 mm^3
MIN_SIZE_RULES = ("none", "v3", "v14", "la3")      # protocol §5.3


def label(binary: np.ndarray, connectivity: int):
    st = STRUCT18 if connectivity == 18 else STRUCT26
    return ndi.label(binary, structure=st)


def lesion_features(lab: np.ndarray, n: int, voxel_mm=(1.0, 1.0, 1.0), prob=None) -> dict:
    """Per-lesion volume (mm^3), long axis (largest bounding-box extent, mm) and mean probability."""
    vox_vol = float(np.prod(voxel_mm))
    counts = np.bincount(lab.ravel(), minlength=n + 1)[1:]
    vol = counts * vox_vol
    long_axis = np.zeros(n)
    for i, sl in enumerate(ndi.find_objects(lab, max_label=n)):
        if sl is None:
            continue
        long_axis[i] = max((s.stop - s.start) * v for s, v in zip(sl, voxel_mm))
    out = {"volume_mm3": vol, "long_axis_mm": long_axis}
    if prob is not None:
        sums = np.bincount(lab.ravel(), weights=prob.ravel(), minlength=n + 1)[1:]
        out["mean_prob"] = sums / np.maximum(counts, 1)
    return out


def keep_by_min_size(feat: dict, rule: str) -> np.ndarray:
    vol, la = feat["volume_mm3"], feat["long_axis_mm"]
    if rule == "none":
        return np.ones(vol.shape, dtype=bool)
    if rule == "v3":
        return vol >= 3.0            # device: lesion_metrics.MIN_LESION_VOLUME_MM3 (MSSEG-2016 floor)
    if rule == "v14":
        return vol >= SPHERE_3MM_MM3  # sphere of 3 mm diameter
    if rule == "la3":
        return la >= 3.0             # Filippi 2019 "3 mm in long axis" (bounding-box extent)
    raise ValueError(rule)


def zone_counts(lab: np.ndarray, n: int, zone: np.ndarray) -> np.ndarray:
    """(n, 5) matrix: number of voxels of each lesion in zones 0..4."""
    idx = lab.ravel().astype(np.int64) * 5 + zone.ravel().astype(np.int64)
    c = np.bincount(idx, minlength=(n + 1) * 5).reshape(n + 1, 5)
    return c[1:]


def regions_contact(zc: np.ndarray) -> np.ndarray:
    """Device contact rule on zone counts: IT > PV > JC, else DWM (also when in no zone)."""
    reg = np.full(zc.shape[0], DWM, dtype=np.int8)
    reg[zc[:, 2] > 0] = JC
    reg[zc[:, 1] > 0] = PV
    reg[zc[:, 3] > 0] = IT
    return reg


def regions_majority(zc: np.ndarray) -> np.ndarray:
    """Zone holding most lesion voxels among zones 1-4; ties broken IT > PV > JC > DWM."""
    order = [IT, PV, JC, DWM]
    sub = zc[:, order]
    best = np.argmax(sub, axis=1)             # argmax returns the first max -> priority order
    reg = np.array(order, dtype=np.int8)[best]
    reg[sub.max(axis=1) == 0] = DWM
    return reg


def lstai_touch_masks(labels: np.ndarray) -> dict:
    """Dilated MSMask structures: a 3x3x3-dilated lesion touches label L  <=>  the lesion touches
    the 3x3x3-dilated label L (the cube is symmetric)."""
    from research.paper_d.atlas import dilate_cube
    return {L: dilate_cube(labels == L) for L in (4, 2, 5)}


def regions_lstai(lab26: np.ndarray, n26: int, touch: dict) -> np.ndarray:
    hits = {L: np.bincount(lab26.ravel(), weights=touch[L].ravel().astype(np.float64),
                           minlength=n26 + 1)[1:] > 0 for L in (4, 2, 5)}
    reg = np.full(n26, DWM, dtype=np.int8)
    reg[hits[5]] = IT
    reg[hits[2]] = JC
    reg[hits[4]] = PV            # LST-AI priority: PV > JC > IT > subcortical
    return reg


def region_counts(regions: np.ndarray, keep: np.ndarray) -> np.ndarray:
    """Counts of kept lesions in PV, JC, IT, DWM."""
    r = regions[keep]
    return np.array([(r == k).sum() for k in (PV, JC, IT, DWM)], dtype=np.int32)


def dis_brain(counts, pv_min: int = 1) -> bool:
    """Device brain-DIS rule: >= 1 lesion in >= 2 of PV, JC, IT (spinal cord / optic nerve not
    available). pv_min=3 gives the MAGNIMS 2016 variant (exploratory)."""
    pv = counts[0] >= pv_min
    return int(pv) + int(counts[1] >= 1) + int(counts[2] >= 1) >= 2
