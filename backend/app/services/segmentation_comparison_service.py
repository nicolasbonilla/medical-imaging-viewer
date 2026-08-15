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
from app.utils.spacing_utils import SPACING_REQUIRED, require_spacing
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
    voxel_spacing: tuple[float, float, float],
) -> float:
    """
    Compute the 95th-percentile Hausdorff distance (HD95) in mm between the two
    masks' SURFACES — the boundary-distance metric used by the MS challenges
    (MSSEG-2 / Anima animaSegPerfAnalyzer2, ISBI-2015) and reference libraries
    (MONAI, medpy).

    Surface-based is the point: HD95 measures how far the boundaries disagree.
    The previous implementation took distances over EVERY foreground voxel, so
    the many interior voxels (distance 0 wherever the masks overlap) diluted the
    distribution and biased HD95 optimistically LOW versus the standard. Here the
    distance is measured from each SURFACE voxel of one mask to the nearest
    SURFACE voxel of the other, symmetrically.

    Returns mm. 0.0 if both empty; inf if exactly one is empty.
    """
    try:
        import scipy.ndimage  # noqa: F401 — availability check only
    except ImportError:
        logger.warning("scipy not available, returning -1 for Hausdorff")
        return -1.0

    a = (mask_a > 0)
    b = (mask_b > 0)

    if not a.any() and not b.any():
        return 0.0
    if not a.any() or not b.any():
        return float('inf')

    d_a_to_b, d_b_to_a = _surface_distances(a, b, voxel_spacing)

    hd95 = max(
        float(np.percentile(d_a_to_b, 95)) if d_a_to_b.size > 0 else 0.0,
        float(np.percentile(d_b_to_a, 95)) if d_b_to_a.size > 0 else 0.0,
    )

    return float(hd95)


def _surface_distances(a_bool: np.ndarray, b_bool: np.ndarray, voxel_spacing):
    """Directed surface-to-surface distances (mm), both directions.

    Returns (d_a_to_b, d_b_to_a): for every SURFACE voxel of A, its distance to
    the nearest surface voxel of B, and vice versa. Shared by HD95 (percentile)
    and ASSD (mean) so both use one boundary definition.

    Surface (boundary) voxels = foreground minus its erosion; a face-connected
    structuring element makes any foreground voxel touching background a surface
    voxel. border_value=0 treats out-of-bounds as background, so foreground that
    reaches the volume edge IS surface (the MONAI/medpy convention) — the object
    genuinely ends there.
    """
    from scipy.ndimage import distance_transform_edt, binary_erosion, generate_binary_structure

    struct = generate_binary_structure(a_bool.ndim, 1)
    surf_a = a_bool & ~binary_erosion(a_bool, structure=struct, border_value=0)
    surf_b = b_bool & ~binary_erosion(b_bool, structure=struct, border_value=0)

    dist_to_surf_b = distance_transform_edt(~surf_b, sampling=voxel_spacing)
    dist_to_surf_a = distance_transform_edt(~surf_a, sampling=voxel_spacing)

    return dist_to_surf_b[surf_a], dist_to_surf_a[surf_b]


def compute_assd(
    mask_a: np.ndarray,
    mask_b: np.ndarray,
    voxel_spacing: tuple[float, float, float],
) -> float:
    """Average Symmetric Surface Distance (ASSD / MSD) in mm.

    The mean over BOTH masks' surface voxels of the distance to the nearest
    surface voxel of the other mask — the MSSEG-2 / Anima symmetric surface
    metric that complements HD95: HD95 reports the worst-case boundary gap, ASSD
    the average boundary disagreement. Returns 0.0 if both empty, inf if exactly
    one is empty.
    """
    try:
        import scipy.ndimage  # noqa: F401 — availability check only
    except ImportError:
        logger.warning("scipy not available, returning -1 for ASSD")
        return -1.0

    a = (mask_a > 0)
    b = (mask_b > 0)

    if not a.any() and not b.any():
        return 0.0
    if not a.any() or not b.any():
        return float('inf')

    d_a_to_b, d_b_to_a = _surface_distances(a, b, voxel_spacing)
    total = d_a_to_b.size + d_b_to_a.size
    if total == 0:
        return 0.0
    return float((float(d_a_to_b.sum()) + float(d_b_to_a.sum())) / total)


def compute_volume_diff(
    mask_a: np.ndarray,
    mask_b: np.ndarray,
    voxel_spacing: tuple[float, float, float],
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


def compute_lesion_detection_metrics(
    pred_mask: np.ndarray,
    ref_mask: np.ndarray,
    min_overlap_ratio: float = 0.0,
) -> dict:
    """Lesion-WISE detection metrics (TPR / PPV / F1) — the challenge standard.

    Dice measures voxel OVERLAP; it says nothing about whether the right DISCRETE
    lesions were found. Two segmentations with equal Dice can disagree sharply on
    lesion detection (one large lesion segmented loosely vs. many small lesions
    missed). MS lesion segmentation is therefore evaluated on BOTH axes, and the
    detection axis is defined lesion-wise in the two reference challenges:

      - ISBI-2015 (Carass et al., NeuroImage 2017; PMC5344762): a reference lesion
        counts as detected (a true positive) when it OVERLAPS the segmentation;
        LTPR = detected reference lesions / reference lesions, and LFPR =
        segmentation lesions not overlapping the reference / segmentation lesions.
      - MSSEG-2016 (Commowick et al., Sci Rep 2018): detection with an
        18-connectivity kernel and an overlap gate.

    Discrete lesions are labelled with the shared 18-connected convention
    (RC-030, lesion_metrics.label_lesions), so this metric is consistent with the
    lesion COUNT reported everywhere else in the app.

    Directionality (documented, not symmetric): `ref_mask` is the reference /
    ground truth, `pred_mask` the prediction under test.
      - sensitivity (LTPR) = TP_ref / n_ref  — fraction of reference lesions hit.
      - precision   (LPPV) = matched_pred / n_pred = 1 - LFPR.
      - lesion_f1          = 2*P*R / (P+R).
    TP_ref (reference lesions detected) and matched_pred (predictions hitting a
    reference) can differ when lesions are confluent — this asymmetry is inherent
    to lesion-wise scoring and matches the challenge definitions.

    `min_overlap_ratio` gates "detected": a reference lesion counts as detected
    only if the predicted foreground covers at least this FRACTION of its voxels.
    Default 0.0 = any-voxel overlap (the ISBI-2015 convention). Raise it to demand
    partial spatial agreement (MSSEG-style).

    Empty-mask conventions (documented): a vacuous rate is 1.0 (nothing to detect
    → "all detected"; nothing predicted → "no false positives"), so two empty
    masks score F1 = 1.0 (they agree there are no lesions), while an empty-vs-
    populated pair scores F1 = 0.0.
    """
    from app.services.lesion_metrics import label_lesions

    pred_labels, n_pred = label_lesions(pred_mask > 0)
    ref_labels, n_ref = label_lesions(ref_mask > 0)

    pred_fg = pred_mask > 0
    ref_fg = ref_mask > 0

    # Reference lesions detected by the prediction (sensitivity numerator).
    detected_ref = 0
    for lesion_id in range(1, n_ref + 1):
        component = ref_labels == lesion_id
        overlap = int(np.count_nonzero(component & pred_fg))
        size = int(np.count_nonzero(component))
        if size > 0 and (overlap / size) > min_overlap_ratio:
            detected_ref += 1

    # Predicted lesions that hit a real lesion (precision numerator); the rest
    # are false positives. Gate symmetrically on the predicted lesion's own size.
    matched_pred = 0
    for lesion_id in range(1, n_pred + 1):
        component = pred_labels == lesion_id
        overlap = int(np.count_nonzero(component & ref_fg))
        size = int(np.count_nonzero(component))
        if size > 0 and (overlap / size) > min_overlap_ratio:
            matched_pred += 1

    false_positives = n_pred - matched_pred
    false_negatives = n_ref - detected_ref

    sensitivity = (detected_ref / n_ref) if n_ref > 0 else 1.0   # LTPR
    precision = (matched_pred / n_pred) if n_pred > 0 else 1.0   # LPPV
    denom = precision + sensitivity
    lesion_f1 = (2 * precision * sensitivity / denom) if denom > 0 else 0.0

    return {
        "ref_lesion_count": n_ref,
        "pred_lesion_count": n_pred,
        "true_positives": detected_ref,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "sensitivity_ltpr": round(sensitivity, 4),
        "precision_lppv": round(precision, 4),
        "lesion_f1": round(lesion_f1, 4),
        "min_overlap_ratio": min_overlap_ratio,
        "connectivity": 18,  # RC-030 shared convention
    }


def compare_two_masks(
    mask_a: np.ndarray,
    mask_b: np.ndarray,
    label_a: str = "Mask A",
    label_b: str = "Mask B",
    # RC-024 (CAPA-001 CA-5): required. The sentinel replaces the old
    # (1.0, 1.0, 1.0) default; omitting it now raises instead of assuming.
    voxel_spacing: tuple[float, float, float] = SPACING_REQUIRED,
) -> dict:
    """
    Full pairwise comparison between two masks.
    Returns Dice (voxel overlap), Hausdorff, volume diff, per-slice Dice, and
    lesion-wise detection metrics (TPR/PPV/F1 — a distinct quality axis from
    Dice). Mask B is treated as the reference for the directional detection
    metrics; see compute_lesion_detection_metrics.
    Raises ValueError if mask shapes don't match.
    """
    voxel_spacing = require_spacing(voxel_spacing, caller="compare_two_masks")
    if mask_a.shape != mask_b.shape:
        raise ValueError(f"Mask shapes must match: {mask_a.shape} vs {mask_b.shape}")

    dice = compute_dice(mask_a, mask_b)
    hausdorff = compute_hausdorff(mask_a, mask_b, voxel_spacing)
    assd = compute_assd(mask_a, mask_b, voxel_spacing)
    volume = compute_volume_diff(mask_a, mask_b, voxel_spacing)
    per_slice = compute_per_slice_dice(mask_a, mask_b)
    # Directional: A = prediction under test, B = reference.
    lesion_detection = compute_lesion_detection_metrics(pred_mask=mask_a, ref_mask=mask_b)

    return {
        "label_a": label_a,
        "label_b": label_b,
        "dice": round(dice, 4),
        "hausdorff_mm": round(hausdorff, 2) if hausdorff != float('inf') else None,
        # ASSD (average symmetric surface distance, mm) — the MSSEG-2/Anima mean
        # boundary metric complementing HD95's worst-case.
        "assd_mm": round(assd, 2) if assd != float('inf') else None,
        "volume": volume,
        "per_slice_dice": [round(d, 4) for d in per_slice],
        "lesion_detection": lesion_detection,
    }
