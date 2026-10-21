"""Paper C — new/enlarging-lesion CANDIDATES from two co-registered timepoints, and their scores.

Two detectors (fixed in PROTOCOL.md §3 before any outcome was computed):

D-sub  model-free FLAIR subtraction (no segmenter, so no training-data contamination).
       z_t = FLAIR_t z-scored within the brain domain (the app's normalize_intensity);
       d = z_b - z_a (the app's subtraction_map, follow-up minus baseline).
       Candidate voxels: d >= 1.5 AND z_b >= 1.0 (bright at follow-up) inside the eroded domain
       (the app's 1-voxel 'interior'); 18-connected components >= 14.14 mm3 (3 mm diameter).
       Score S_sub = mean d over the component.

D-seg  the app's CURRENT rule on two segmentations (FLAMeS 5-fold mean, p >= 0.5):
       app longitudinal_tracking_service.compare_timepoints (18-conn, >= 3 mm3, mutual-best
       IoU >= 0.3) -> 'new' components >= 14.14 mm3 (clinically_significant) and 'enlarged'
       matched components (> 20 % volume) are the candidates. Change region R = whole component
       (new) or component minus the baseline mask (enlarged).
       Scores: S_sub = mean d over R inside the domain (what the app reports as
       subtraction_signal); S_dp = mean (p_b - p_a) over R (segmenter's own change evidence).
       App baselines: activity_candidate (>= 1 significant new or enlarged) and the same with
       new lesions counted only when subtraction-confirmed (S_sub >= 0.5 SD, app default).
"""
import numpy as np
from scipy import ndimage

from common import CLIN_MM3, STRUCT18, app_longitudinal, components

T_SUB = 1.5        # subtraction threshold (SD units) for D-sub candidate voxels
T_FU = 1.0         # follow-up FLAIR brightness (SD units) for D-sub candidate voxels
APP_CONFIRM_SD = 0.5


def subtraction(flair_a, flair_b, domain):
    """(d, z_b, interior) with the app's own normalisation; None if a volume is uninformative."""
    _, lsub = app_longitudinal()
    d = lsub.subtraction_map(flair_a, flair_b, domain)
    zb = lsub.normalize_intensity(flair_b, domain)
    if d is None or zb is None:
        return None
    interior = ndimage.binary_erosion(domain, iterations=1)   # as confirm_new_candidates
    return d.astype(np.float32), zb.astype(np.float32), interior


def label_candidates(cands, truth_region):
    for c in cands:
        c["true"] = bool(truth_region[c["_idx"]].any()) if c["_idx"][0].size else False
    return cands


def dsub_candidates(d, zb, interior, voxvol, t_sub=T_SUB, t_fu=T_FU):
    m = (d >= t_sub) & (zb >= t_fu) & interior
    lab, comps = components(m, voxvol, CLIN_MM3)
    out = []
    for c in comps:
        sl = c["slice"]
        local = lab[sl] == c["id"]
        idx = tuple(a + s.start for a, s in zip(np.nonzero(local), sl))
        out.append({"volume_mm3": c["volume_mm3"], "score": float(d[idx].mean()), "_idx": idx})
    return out


def dseg_candidates(prob_a, prob_b, d, domain, zooms):
    """App rule on the 5-fold-mean FLAMeS masks. Returns (candidates, app_flags)."""
    lts, _ = app_longitudinal()
    mask_a = prob_a >= 0.5
    mask_b = prob_b >= 0.5
    spacing = tuple(float(z) for z in zooms)
    res = lts.compare_timepoints(mask_a, mask_b, spacing)
    comps_a = lts._extract_components(mask_a, spacing)
    comps_b = lts._extract_components(mask_b, spacing)
    matched, _resolved, new = lts._match_components(comps_a, comps_b, 0.3)
    cands = []
    for cb in new:
        if cb["volume_mm3"] < CLIN_MM3:
            continue                                   # not clinically_significant -> not counted
        idx = tuple(cb["mask_indices"].T)
        cands.append({"kind": "new", "volume_mm3": cb["volume_mm3"], "_idx": idx})
    for ca, cb, _iou in matched:
        if ca["volume_mm3"] > 0 and (cb["volume_mm3"] - ca["volume_mm3"]) / ca["volume_mm3"] > 0.20:
            ii = cb["mask_indices"]
            keep = ~mask_a[ii[:, 0], ii[:, 1], ii[:, 2]]
            idx = tuple(ii[keep].T) if keep.any() else tuple(ii.T)
            cands.append({"kind": "enlarged", "volume_mm3": cb["volume_mm3"], "_idx": idx})
    for c in cands:
        idx = c["_idx"]
        inside = domain[idx]
        c["score_sub"] = float(d[idx][inside].mean()) if inside.any() else float("-inf")
        c["score_dp"] = float((prob_b[idx] - prob_a[idx]).mean())
    n_new_conf = sum(1 for c in cands if c["kind"] == "new" and c["score_sub"] >= APP_CONFIRM_SD)
    n_enl = sum(1 for c in cands if c["kind"] == "enlarged")
    flags = {"app_activity": bool(res["activity_candidate"]),
             "app_activity_subconfirmed": bool(n_new_conf + n_enl >= 1),
             "app_new_significant": int(res["new_clinically_significant_count"]),
             "app_enlarging": int(res["enlarging_count"])}
    if flags["app_new_significant"] != sum(1 for c in cands if c["kind"] == "new") or flags["app_enlarging"] != n_enl:
        raise AssertionError("candidate reconstruction disagrees with the app's compare_timepoints")
    return cands, flags


def strip(cands):
    """JSON-safe copy without voxel indices."""
    return [{k: v for k, v in c.items() if not k.startswith("_")} for c in cands]
