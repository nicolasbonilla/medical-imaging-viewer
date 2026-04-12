"""
Lesion Analysis Service.

Connected component analysis for segmentation masks:
- Per-lesion statistics (volume, centroid, bounding box, label)
- Aggregate statistics (count per region, total burden, size distribution)
- McDonald 2024 DIS (Dissemination in Space) assessment
  (Montalban et al., Lancet Neurology 2025; 24(10): 850-865)

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

# McDonald 2024 DIS: 5 regions (PV, JC, IT, spinal cord, optic nerve)
# Brain MRI evaluable regions: PV, JC, IT only
# Spinal cord and optic nerve require separate imaging
DIS_BRAIN_REGIONS = {1, 2, 3}  # PV, JC, IT (brain MRI only)
DIS_TOTAL_REGIONS = 5  # Total McDonald 2024 DIS regions

# Minimum lesion volume (mm3) — consistent with ms_region_classifier.py
MIN_LESION_VOLUME_MM3 = 3.0  # ~3 voxels at 1mm isotropic


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
    # IEC 62304 Class C — Input validation (REQ-SAFE-005)
    if not isinstance(mask_3d, np.ndarray):
        raise ValueError("mask_3d must be a numpy ndarray")
    if mask_3d.ndim != 3:
        raise ValueError(f"mask_3d must be 3D, got {mask_3d.ndim}D")
    if voxel_spacing is not None:
        if not all(isinstance(v, (int, float)) and v > 0 for v in voxel_spacing):
            raise ValueError(f"voxel_spacing values must be positive, got {voxel_spacing}")

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

        filtered_count = 0
        for comp_idx, centroid in zip(component_ids, centroids):
            comp_mask = labeled_array == comp_idx
            voxel_count = int(comp_mask.sum())
            volume_mm3 = voxel_count * voxel_vol_mm3

            # Skip noise components (consistent with ms_region_classifier.py)
            if volume_mm3 < MIN_LESION_VOLUME_MM3:
                continue

            filtered_count += 1

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

        # Region summary (use filtered count)
        total_region_voxels = int(binary.sum())
        region_summary[label_name] = {
            "label_id": label_id,
            "lesion_count": filtered_count,
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
    voxel_spacing: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> dict:
    """
    Evaluate McDonald 2024 Dissemination in Space (DIS) criteria.

    McDonald 2024 (Montalban et al., Lancet Neurology 2025) DIS requires
    typical MS lesions in ≥2 of 5 characteristic regions:
      1. Periventricular (label 1)
      2. Juxtacortical/cortical (label 2)
      3. Infratentorial (label 3)
      4. Spinal cord (requires separate imaging — not assessed here)
      5. Optic nerve (requires separate imaging — not assessed here)

    Note: Deep White Matter (label 4) is NOT a DIS region per McDonald 2024.
    This function evaluates only the 3 brain MRI regions (PV, JC, IT).

    Args:
        mask_3d: 3D numpy array (D, H, W) with MAGNIMS label IDs.
        labels: Mapping of label_id -> label_name.
        voxel_spacing: (dz, dy, dx) in mm — used for minimum volume filter.

    Returns:
        Dict with McDonald 2024 DIS assessment (brain regions only).
    """
    # IEC 62304 Class C — Input validation (REQ-SAFE-005)
    if not isinstance(mask_3d, np.ndarray):
        raise ValueError("mask_3d must be a numpy ndarray")
    if mask_3d.ndim != 3:
        raise ValueError(f"mask_3d must be 3D, got {mask_3d.ndim}D")
    if voxel_spacing is not None:
        if not all(isinstance(v, (int, float)) and v > 0 for v in voxel_spacing):
            raise ValueError(f"voxel_spacing values must be positive, got {voxel_spacing}")

    try:
        from scipy.ndimage import label as cc_label
    except ImportError:
        logger.error("scipy not available for DIS assessment")
        return {"error": "scipy not available"}

    if labels is None:
        labels = MAGNIMS_REGIONS

    voxel_vol_mm3 = float(np.prod(voxel_spacing))

    # Check each DIS brain region (PV, JC, IT) — with volume filter
    region_presence = {}
    for region_id in sorted(DIS_BRAIN_REGIONS):
        region_name = labels.get(region_id, f"Label {region_id}")
        binary = (mask_3d == region_id).astype(np.uint8)
        total_voxels = int(binary.sum())

        # Count lesions meeting minimum volume threshold
        qualifying_lesions = 0
        if total_voxels > 0:
            labeled_array, num_features = cc_label(binary)
            for comp_id in range(1, num_features + 1):
                comp_voxels = int((labeled_array == comp_id).sum())
                if comp_voxels * voxel_vol_mm3 >= MIN_LESION_VOLUME_MM3:
                    qualifying_lesions += 1

        region_presence[region_name] = {
            "label_id": region_id,
            "present": qualifying_lesions > 0,
            "voxel_count": total_voxels,
            "qualifying_lesion_count": qualifying_lesions,
        }

    brain_regions_with_lesions = sum(
        1 for r in region_presence.values() if r["present"]
    )
    dis_met_brain = brain_regions_with_lesions >= 2

    # DWM info (not a DIS region, but clinically relevant)
    dwm_voxels = int((mask_3d == 4).sum())
    dwm_lesion_count = 0
    if dwm_voxels > 0:
        dwm_binary = (mask_3d == 4).astype(np.uint8)
        dwm_labeled, dwm_features = cc_label(dwm_binary)
        for comp_id in range(1, dwm_features + 1):
            comp_voxels = int((dwm_labeled == comp_id).sum())
            if comp_voxels * voxel_vol_mm3 >= MIN_LESION_VOLUME_MM3:
                dwm_lesion_count += 1

    # Additional info: active lesions (Gd+) and black holes
    unique_labels_set = set(int(l) for l in np.unique(mask_3d) if l > 0)
    has_active = 5 in unique_labels_set
    has_black_holes = 6 in unique_labels_set

    return {
        "dis_met_brain": dis_met_brain,
        "dis_criteria_version": "McDonald 2024 (Montalban et al., Lancet Neurology 2025)",
        "brain_regions_with_lesions": brain_regions_with_lesions,
        "total_dis_regions": DIS_TOTAL_REGIONS,
        "brain_regions_evaluated": len(DIS_BRAIN_REGIONS),
        "spinal_cord_evaluated": False,
        "optic_nerve_evaluated": False,
        "note": (
            "Brain MRI assessment only. Full McDonald 2024 DIS requires "
            "5 regions including spinal cord and optic nerve imaging."
        ),
        "region_details": region_presence,
        "dwm_lesion_count": dwm_lesion_count,
        "dwm_voxels": dwm_voxels,
        "has_active_lesions": has_active,
        "has_black_holes": has_black_holes,
        "active_voxels": int((mask_3d == 5).sum()) if has_active else 0,
        "black_hole_voxels": int((mask_3d == 6).sum()) if has_black_holes else 0,
        # Legacy field for backwards compatibility
        "dis_met": dis_met_brain,
        "regions_with_lesions": brain_regions_with_lesions,
        "total_dis_regions_legacy": len(DIS_BRAIN_REGIONS),
    }
