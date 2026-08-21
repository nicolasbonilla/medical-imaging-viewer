"""
Longitudinal Tracking Service.

Compares lesion masks between two timepoints to detect:
- NEW lesions (only in TP2)
- RESOLVED lesions (only in TP1)
- ENLARGED lesions (in both, TP2 > TP1 by >20%)
- SHRUNK lesions (in both, TP2 < TP1 by >20%)
- STABLE lesions (in both, change ≤20%)

Also computes a timeline of total burden across multiple timepoints.

@module services.longitudinal_tracking_service
"""

import numpy as np
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)

# MAGNIMS / clinical-trial minimum for a COUNTABLE new T2 lesion: ~3 mm diameter.
# This is distinct from (and larger than) the 3 mm³ MSSEG noise floor — a real but
# sub-3mm speck is not a clinically-actionable new lesion. Candidates below this are
# still reported, flagged clinically_significant=False, and excluded from the
# activity/DIT candidate counts. A 3 mm sphere ≈ 14.14 mm³.
NEW_LESION_MIN_DIAMETER_MM = 3.0


def _sphere_volume_mm3(diameter_mm: float) -> float:
    return (4.0 / 3.0) * np.pi * (diameter_mm / 2.0) ** 3


def _extract_components(mask_3d: np.ndarray, voxel_spacing: tuple[float, float, float]):
    """
    Extract connected components from a binary mask.
    Returns list of dicts with centroid, volume, and component mask indices.
    """
    try:
        from scipy.ndimage import center_of_mass
        from app.services.lesion_metrics import label_lesions, meets_min_volume
    except ImportError:
        logger.error("scipy required for longitudinal tracking")
        return []

    binary = (mask_3d > 0).astype(np.uint8)
    labeled, num = label_lesions(binary)  # RC-030: 18-connectivity (ISBI-2015/MSSEG-2016)
    if num == 0:
        return []

    voxel_vol = float(np.prod(voxel_spacing))
    components = []
    comp_ids = list(range(1, num + 1))
    centroids = center_of_mass(binary, labeled, comp_ids)

    for comp_id, centroid in zip(comp_ids, centroids):
        comp_mask = labeled == comp_id
        voxel_count = int(comp_mask.sum())
        # RC-030: drop sub-noise-floor specks (consistent with analyze_lesions /
        # compute_dis_criteria). This is the MSSEG-2016 evaluation floor, not a
        # validated new/enlarging-lesion threshold.
        if not meets_min_volume(voxel_count, voxel_vol):
            continue
        components.append({
            "id": comp_id,
            "centroid": (float(centroid[0]), float(centroid[1]), float(centroid[2])),
            "voxel_count": voxel_count,
            "volume_mm3": round(voxel_count * voxel_vol, 2),
            "mask_indices": np.argwhere(comp_mask),
        })

    return components


def _match_components(comps_a, comps_b, iou_threshold: float = 0.3):
    """
    Match lesions between two timepoints by overlap (IoU), MUTUAL-BEST.

    A pair (a, b) is matched iff b is a's highest-IoU partner AND a is b's
    highest-IoU partner (and IoU >= threshold). Mutual-best is the rigorous
    convention (it is what the lesion-scale registration QC uses): it prevents a
    large TP2 lesion from greedily "claiming" a small TP1 lesion that actually
    corresponds to a different component, which would hide a real resolved/new
    lesion. Returns: matched pairs, unmatched_a (resolved), unmatched_b (new).
    """
    n, m = len(comps_a), len(comps_b)
    if n == 0 or m == 0:
        return [], list(comps_a), list(comps_b)

    sets_a = [set(map(tuple, ca["mask_indices"])) for ca in comps_a]
    sets_b = [set(map(tuple, cb["mask_indices"])) for cb in comps_b]

    iou = [[0.0] * m for _ in range(n)]
    for i in range(n):
        for j in range(m):
            inter = len(sets_a[i] & sets_b[j])
            if inter == 0:
                continue
            union = len(sets_a[i] | sets_b[j])
            if union:
                iou[i][j] = inter / union

    best_b_for_a = [max(range(m), key=lambda j: iou[i][j]) for i in range(n)]
    best_a_for_b = [max(range(n), key=lambda i: iou[i][j]) for j in range(m)]

    matched = []
    used_b = set()
    for i in range(n):
        j = best_b_for_a[i]
        if iou[i][j] >= iou_threshold and best_a_for_b[j] == i:
            matched.append((comps_a[i], comps_b[j], iou[i][j]))
            used_b.add(j)

    matched_a_ids = {mm[0]["id"] for mm in matched}
    unmatched_a = [ca for ca in comps_a if ca["id"] not in matched_a_ids]
    unmatched_b = [comps_b[j] for j in range(m) if j not in used_b]

    return matched, unmatched_a, unmatched_b


def compare_timepoints(
    mask_tp1: np.ndarray,
    mask_tp2: np.ndarray,
    voxel_spacing: tuple[float, float, float],
    iou_threshold: float = 0.3,
    change_threshold: float = 0.20,
) -> dict:
    """
    Compare lesion masks from two timepoints.

    Args:
        mask_tp1: 3D mask from earlier timepoint (D, H, W).
        mask_tp2: 3D mask from later timepoint (D, H, W).
        voxel_spacing: (dz, dy, dx) in mm.
        iou_threshold: Minimum IoU to consider same lesion.
        change_threshold: Volume change fraction to classify as enlarged/shrunk.

    Returns:
        Dict with lesion changes, summary stats, and delta burden.

    Raises:
        ValueError: If mask shapes don't match.
    """
    if mask_tp1.shape != mask_tp2.shape:
        raise ValueError(f"Mask shapes must match: {mask_tp1.shape} vs {mask_tp2.shape}")

    voxel_vol = float(np.prod(voxel_spacing))

    comps_a = _extract_components(mask_tp1, voxel_spacing)
    comps_b = _extract_components(mask_tp2, voxel_spacing)

    matched, resolved, new_lesions = _match_components(comps_a, comps_b, iou_threshold)

    changes = []

    # Matched lesions: classify as enlarged, shrunk, or stable
    for ca, cb, iou in matched:
        vol_a = ca["volume_mm3"]
        vol_b = cb["volume_mm3"]
        delta = vol_b - vol_a
        pct = (delta / vol_a * 100) if vol_a > 0 else 0.0

        if pct > change_threshold * 100:
            status = "enlarged"
        elif pct < -change_threshold * 100:
            status = "shrunk"
        else:
            status = "stable"

        changes.append({
            "centroid_z": round(cb["centroid"][0], 1),
            "centroid_y": round(cb["centroid"][1], 1),
            "centroid_x": round(cb["centroid"][2], 1),
            "volume_tp1_mm3": vol_a,
            "volume_tp2_mm3": vol_b,
            "volume_tp1_ml": round(vol_a / 1000, 4),
            "volume_tp2_ml": round(vol_b / 1000, 4),
            "change_mm3": round(delta, 2),
            "change_percent": round(pct, 1),
            "status": status,
            "iou": round(iou, 3),
        })

    # New lesions
    new_min_volume = _sphere_volume_mm3(NEW_LESION_MIN_DIAMETER_MM)
    for cb in new_lesions:
        changes.append({
            "centroid_z": round(cb["centroid"][0], 1),
            "centroid_y": round(cb["centroid"][1], 1),
            "centroid_x": round(cb["centroid"][2], 1),
            "volume_tp1_mm3": 0,
            "volume_tp2_mm3": cb["volume_mm3"],
            "volume_tp1_ml": 0,
            "volume_tp2_ml": round(cb["volume_mm3"] / 1000, 4),
            "change_mm3": cb["volume_mm3"],
            "change_percent": 100.0,
            "status": "new",
            "iou": 0,
            # MAGNIMS clinical size gate: only ≥3 mm-diameter new lesions are
            # clinically countable (below = likely non-actionable / subthreshold).
            "clinically_significant": bool(cb["volume_mm3"] >= new_min_volume),
        })

    # Resolved lesions
    for ca in resolved:
        changes.append({
            "centroid_z": round(ca["centroid"][0], 1),
            "centroid_y": round(ca["centroid"][1], 1),
            "centroid_x": round(ca["centroid"][2], 1),
            "volume_tp1_mm3": ca["volume_mm3"],
            "volume_tp2_mm3": 0,
            "volume_tp1_ml": round(ca["volume_mm3"] / 1000, 4),
            "volume_tp2_ml": 0,
            "change_mm3": -ca["volume_mm3"],
            "change_percent": -100.0,
            "status": "resolved",
            "iou": 0,
        })

    # Summary
    burden_tp1 = int((mask_tp1 > 0).sum()) * voxel_vol
    burden_tp2 = int((mask_tp2 > 0).sum()) * voxel_vol
    burden_delta = burden_tp2 - burden_tp1
    burden_pct = (burden_delta / burden_tp1 * 100) if burden_tp1 > 0 else (100.0 if burden_tp2 > 0 else 0.0)

    status_counts = {"new": 0, "resolved": 0, "enlarged": 0, "shrunk": 0, "stable": 0}
    for c in changes:
        status_counts[c["status"]] += 1

    # MAGNIMS activity / DIT CANDIDATE signals (never findings). The clinical
    # thresholds (2021/2024 MAGNIMS-CMSC-NAIMS): ≥1 new lesion supports
    # dissemination-in-time; ≥2 new/enlarging lesions signals active disease. We
    # count only clinically-significant (≥3 mm) new lesions. These are CANDIDATE
    # flags — the route stamps registration_verified=False + adjudication_required,
    # and the report builder is barred from asserting DIT/active disease. They exist
    # to surface "worth a radiologist's attention", not to diagnose.
    new_significant = sum(
        1 for c in changes if c["status"] == "new" and c.get("clinically_significant")
    )
    enlarging = status_counts["enlarged"]

    return {
        "changes": changes,
        "total_lesions_tp1": len(comps_a),
        "total_lesions_tp2": len(comps_b),
        "burden_tp1_mm3": round(burden_tp1, 2),
        "burden_tp2_mm3": round(burden_tp2, 2),
        "burden_tp1_ml": round(burden_tp1 / 1000, 4),
        "burden_tp2_ml": round(burden_tp2 / 1000, 4),
        "burden_delta_mm3": round(burden_delta, 2),
        "burden_delta_percent": round(burden_pct, 1),
        "status_counts": status_counts,
        # Clinical candidate signals (advisory — see above).
        "new_lesion_min_diameter_mm": NEW_LESION_MIN_DIAMETER_MM,
        "new_clinically_significant_count": new_significant,
        "enlarging_count": enlarging,
        "dit_candidate": new_significant >= 1,
        "activity_candidate": (new_significant + enlarging) >= 2,
    }
