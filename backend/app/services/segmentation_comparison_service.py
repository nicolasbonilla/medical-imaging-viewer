"""
Segmentation Comparison Service.

Computes similarity metrics between segmentation/expert masks:
- Dice coefficient (spatial overlap)
- Hausdorff distance (surface distance in mm)
- Volume difference (percentage)
- Voxel-wise agreement map

@module services.segmentation_comparison_service
"""

import numpy as np
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


def compute_dice(mask_a: np.ndarray, mask_b: np.ndarray) -> float:
    """
    Compute Dice Similarity Coefficient between two binary masks.
    DSC = 2 * |A ∩ B| / (|A| + |B|)
    Returns 1.0 if both masks are empty, 0.0 if only one is empty.
    """
    a = (mask_a > 0).astype(bool)
    b = (mask_b > 0).astype(bool)

    sum_a = a.sum()
    sum_b = b.sum()

    if sum_a == 0 and sum_b == 0:
        return 1.0  # Both empty = perfect agreement
    if sum_a == 0 or sum_b == 0:
        return 0.0

    intersection = np.logical_and(a, b).sum()
    return float(2.0 * intersection / (sum_a + sum_b))


def compute_hausdorff(
    mask_a: np.ndarray,
    mask_b: np.ndarray,
    voxel_spacing: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> float:
    """
    Compute 95th percentile Hausdorff distance between two binary masks.
    Uses scipy distance transform for efficient computation.
    Returns distance in mm. Returns 0.0 if both masks are empty.
    """
    try:
        from scipy.ndimage import distance_transform_edt
    except ImportError:
        logger.warning("scipy not available, returning -1 for Hausdorff")
        return -1.0

    a = (mask_a > 0).astype(bool)
    b = (mask_b > 0).astype(bool)

    if not a.any() and not b.any():
        return 0.0
    if not a.any() or not b.any():
        return float('inf')

    # Distance transform of the complement
    dist_a = distance_transform_edt(~a, sampling=voxel_spacing)
    dist_b = distance_transform_edt(~b, sampling=voxel_spacing)

    # Surface distances: distance from each surface voxel of A to nearest surface of B
    surface_a_to_b = dist_b[a]
    surface_b_to_a = dist_a[b]

    # 95th percentile Hausdorff (more robust than max)
    hd95 = max(
        np.percentile(surface_a_to_b, 95) if len(surface_a_to_b) > 0 else 0.0,
        np.percentile(surface_b_to_a, 95) if len(surface_b_to_a) > 0 else 0.0,
    )

    return float(hd95)


def compute_volume_diff(
    mask_a: np.ndarray,
    mask_b: np.ndarray,
    voxel_spacing: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> dict:
    """
    Compute volume difference between two masks.
    Returns volumes in mm³ and percentage difference.
    """
    voxel_vol = float(np.prod(voxel_spacing))

    vol_a = float((mask_a > 0).sum()) * voxel_vol
    vol_b = float((mask_b > 0).sum()) * voxel_vol
    diff = vol_b - vol_a
    pct = (diff / vol_a * 100) if vol_a > 0 else (100.0 if vol_b > 0 else 0.0)

    return {
        "volume_a_mm3": round(vol_a, 2),
        "volume_b_mm3": round(vol_b, 2),
        "diff_mm3": round(diff, 2),
        "diff_percent": round(pct, 2),
    }


def compute_agreement_map(masks: list[np.ndarray]) -> np.ndarray:
    """
    Compute voxel-wise agreement across N binary masks.
    Returns array where each voxel value = count of masks that are positive there.
    Value range: 0 to len(masks).
    """
    if not masks:
        return np.zeros((1,), dtype=np.uint8)

    result = np.zeros_like(masks[0], dtype=np.uint8)
    for mask in masks:
        result += (mask > 0).astype(np.uint8)

    return result


def compute_per_slice_dice(
    mask_a: np.ndarray,
    mask_b: np.ndarray,
) -> list[float]:
    """
    Compute Dice coefficient for each axial slice.
    Assumes masks are 3D with shape (D, H, W).
    Returns list of Dice values, one per slice along first axis.
    """
    if mask_a.ndim != 3 or mask_b.ndim != 3:
        return []

    if mask_a.shape != mask_b.shape:
        logger.error("Shape mismatch in per_slice_dice: %s vs %s", mask_a.shape, mask_b.shape)
        return []

    depth = mask_a.shape[0]
    dice_per_slice = []

    for z in range(depth):
        slice_a = mask_a[z]
        slice_b = mask_b[z]
        dice_per_slice.append(compute_dice(slice_a, slice_b))

    return dice_per_slice


def compare_two_masks(
    mask_a: np.ndarray,
    mask_b: np.ndarray,
    label_a: str = "Mask A",
    label_b: str = "Mask B",
    voxel_spacing: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> dict:
    """
    Full pairwise comparison between two masks.
    Returns Dice, Hausdorff, volume diff, and per-slice Dice.
    Raises ValueError if mask shapes don't match.
    """
    if mask_a.shape != mask_b.shape:
        raise ValueError(f"Mask shapes must match: {mask_a.shape} vs {mask_b.shape}")

    dice = compute_dice(mask_a, mask_b)
    hausdorff = compute_hausdorff(mask_a, mask_b, voxel_spacing)
    volume = compute_volume_diff(mask_a, mask_b, voxel_spacing)
    per_slice = compute_per_slice_dice(mask_a, mask_b)

    return {
        "label_a": label_a,
        "label_b": label_b,
        "dice": round(dice, 4),
        "hausdorff_mm": round(hausdorff, 2) if hausdorff != float('inf') else None,
        "volume": volume,
        "per_slice_dice": [round(d, 4) for d in per_slice],
    }
