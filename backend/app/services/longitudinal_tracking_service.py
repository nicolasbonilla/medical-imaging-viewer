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


def _extract_components(mask_3d: np.ndarray, voxel_spacing: tuple[float, float, float]):
    """
    Extract connected components from a binary mask.
    Returns list of dicts with centroid, volume, and component mask indices.
    """
    try:
        from scipy.ndimage import label as cc_label, center_of_mass
    except ImportError:
        logger.error("scipy required for longitudinal tracking")
        return []

    binary = (mask_3d > 0).astype(np.uint8)
    labeled, num = cc_label(binary)
    if num == 0:
        return []

    voxel_vol = float(np.prod(voxel_spacing))
    components = []
    comp_ids = list(range(1, num + 1))
    centroids = center_of_mass(binary, labeled, comp_ids)

    for comp_id, centroid in zip(comp_ids, centroids):
        comp_mask = labeled == comp_id
        voxel_count = int(comp_mask.sum())
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
    Match lesions between two timepoints by overlap (IoU).
    Returns: matched pairs, unmatched_a (resolved), unmatched_b (new).
    """
    # Precompute voxel sets once (O(N+M) instead of O(N*M))
    sets_a = [set(map(tuple, ca["mask_indices"])) for ca in comps_a]
    sets_b = [set(map(tuple, cb["mask_indices"])) for cb in comps_b]

    matched = []
    used_b = set()

    for a_idx, ca in enumerate(comps_a):
        best_iou = 0.0
        best_b_idx = -1

        for b_idx, cb in enumerate(comps_b):
            if b_idx in used_b:
                continue

            intersection = len(sets_a[a_idx] & sets_b[b_idx])
            union = len(sets_a[a_idx] | sets_b[b_idx])

            if union == 0:
                continue

            iou = intersection / union
            if iou > best_iou:
                best_iou = iou
                best_b_idx = b_idx

        if best_iou >= iou_threshold and best_b_idx >= 0:
            matched.append((ca, comps_b[best_b_idx], best_iou))
            used_b.add(best_b_idx)

    unmatched_a = [ca for ca in comps_a if not any(m[0]["id"] == ca["id"] for m in matched)]
    unmatched_b = [comps_b[i] for i in range(len(comps_b)) if i not in used_b]

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
    }
