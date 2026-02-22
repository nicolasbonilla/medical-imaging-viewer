"""
Lesion Analysis Service.

Connected component analysis for segmentation masks:
- Per-lesion statistics (volume, centroid, bounding box, label)
- Aggregate statistics (count per region, total burden, size distribution)
- McDonald 2024 DIS (Dissemination in Space) assessment

@module services.lesion_analysis_service
"""

import numpy as np
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)

# MAGNIMS label IDs (must match frontend MAGNIMS_LESION_LABELS)
MAGNIMS_REGIONS = {
    1: "Periventricular",
    2: "Juxtacortical",
    3: "Infratentorial",
    4: "Deep White Matter",
    5: "Active (Gd+)",
    6: "Black Hole (T1)",
}

# McDonald 2024 DIS requires lesions in ≥2 of these 4 regions
DIS_REGIONS = {1, 2, 3, 4}  # PV, JC, IT, DWM


def analyze_lesions(
    mask_3d: np.ndarray,
    voxel_spacing: tuple[float, float, float] = (1.0, 1.0, 1.0),
    labels: Optional[dict[int, str]] = None,
) -> dict:
    """
    Analyze lesions in a 3D segmentation mask using connected components.

    Args:
        mask_3d: 3D numpy array (D, H, W) with label IDs (0=background).
        voxel_spacing: (dz, dy, dx) in mm.
        labels: Mapping of label_id -> label_name. Uses MAGNIMS defaults if None.

    Returns:
        Dict with lesions list, region summary, total burden, and size distribution.
    """
    try:
        from scipy.ndimage import label as cc_label, center_of_mass
    except ImportError:
        logger.error("scipy not available for connected component analysis")
        return {"error": "scipy not available", "lesions": [], "regions": {}}

    if labels is None:
        labels = MAGNIMS_REGIONS

    voxel_vol_mm3 = float(np.prod(voxel_spacing))
    lesions = []
    region_summary: dict[str, dict] = {}

    unique_labels = [lid for lid in np.unique(mask_3d) if lid > 0]

    for label_id in unique_labels:
        label_id = int(label_id)
        label_name = labels.get(label_id, f"Label {label_id}")

        # Binary mask for this label
        binary = (mask_3d == label_id).astype(np.uint8)

        # Connected components
        labeled_array, num_features = cc_label(binary)

        if num_features == 0:
            continue

        # Compute centroids for all components at once
        component_ids = list(range(1, num_features + 1))
        centroids = center_of_mass(binary, labeled_array, component_ids)

        for comp_idx, centroid in zip(component_ids, centroids):
            comp_mask = labeled_array == comp_idx
            voxel_count = int(comp_mask.sum())
            volume_mm3 = voxel_count * voxel_vol_mm3

            # Bounding box
            coords = np.argwhere(comp_mask)
            z_min, y_min, x_min = coords.min(axis=0).tolist()
            z_max, y_max, x_max = coords.max(axis=0).tolist()

            # Size category
            if volume_mm3 < 100:
                size_cat = "small"
            elif volume_mm3 < 1000:
                size_cat = "medium"
            else:
                size_cat = "large"

            lesion_info = {
                "id": len(lesions) + 1,
                "label_id": label_id,
                "region": label_name,
                "voxel_count": voxel_count,
                "volume_mm3": round(volume_mm3, 2),
                "volume_ml": round(volume_mm3 / 1000, 4),
                "size_category": size_cat,
                "centroid": {
                    "z": round(float(centroid[0]), 1),
                    "y": round(float(centroid[1]), 1),
                    "x": round(float(centroid[2]), 1),
                },
                "bounding_box": {
                    "z_min": z_min, "z_max": z_max,
                    "y_min": y_min, "y_max": y_max,
                    "x_min": x_min, "x_max": x_max,
                },
            }
            lesions.append(lesion_info)

        # Region summary
        total_region_voxels = int(binary.sum())
        region_summary[label_name] = {
            "label_id": label_id,
            "lesion_count": num_features,
            "total_voxels": total_region_voxels,
            "total_volume_mm3": round(total_region_voxels * voxel_vol_mm3, 2),
            "total_volume_ml": round(total_region_voxels * voxel_vol_mm3 / 1000, 4),
        }

    # Total burden
    total_annotated = int((mask_3d > 0).sum())
    total_burden_mm3 = total_annotated * voxel_vol_mm3

    # Size distribution
    size_dist = {"small": 0, "medium": 0, "large": 0}
    for les in lesions:
        size_dist[les["size_category"]] += 1

    # Sort lesions by volume (largest first)
    lesions.sort(key=lambda l: l["volume_mm3"], reverse=True)
    # Re-number
    for i, les in enumerate(lesions):
        les["id"] = i + 1

    return {
        "lesions": lesions,
        "total_count": len(lesions),
        "total_burden_mm3": round(total_burden_mm3, 2),
        "total_burden_ml": round(total_burden_mm3 / 1000, 4),
        "regions": region_summary,
        "size_distribution": size_dist,
        "unique_labels": [int(l) for l in unique_labels],
    }


def compute_dis_criteria(
    mask_3d: np.ndarray,
    labels: Optional[dict[int, str]] = None,
) -> dict:
    """
    Evaluate McDonald 2024 Dissemination in Space (DIS) criteria.

    DIS requires typical MS lesions in ≥2 of 4 characteristic regions:
    1. Periventricular (label 1)
    2. Juxtacortical/cortical (label 2)
    3. Infratentorial (label 3)
    4. Deep white matter (label 4)

    Returns:
        Dict with DIS assessment, region presence, and criteria met count.
    """
    if labels is None:
        labels = MAGNIMS_REGIONS

    unique_labels = set(int(l) for l in np.unique(mask_3d) if l > 0)

    # Check each DIS region
    region_presence = {}
    for region_id in sorted(DIS_REGIONS):
        region_name = labels.get(region_id, f"Label {region_id}")
        present = region_id in unique_labels
        # Count voxels in this region
        voxel_count = int((mask_3d == region_id).sum()) if present else 0
        region_presence[region_name] = {
            "label_id": region_id,
            "present": present,
            "voxel_count": voxel_count,
        }

    regions_with_lesions = sum(1 for r in region_presence.values() if r["present"])
    dis_met = regions_with_lesions >= 2

    # Additional info: active lesions (Gd+) and black holes
    has_active = 5 in unique_labels
    has_black_holes = 6 in unique_labels

    return {
        "dis_met": dis_met,
        "regions_with_lesions": regions_with_lesions,
        "total_dis_regions": len(DIS_REGIONS),
        "region_details": region_presence,
        "has_active_lesions": has_active,
        "has_black_holes": has_black_holes,
        "active_voxels": int((mask_3d == 5).sum()) if has_active else 0,
        "black_hole_voxels": int((mask_3d == 6).sum()) if has_black_holes else 0,
    }
