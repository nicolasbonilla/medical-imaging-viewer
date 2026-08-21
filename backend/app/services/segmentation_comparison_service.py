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


def compute_normalized_dice(
    pred_mask: np.ndarray,
    ref_mask: np.ndarray,
    effective_load: float = 0.001,
) -> float:
    """Normalised Dice (nDSC) — Raina et al. 2023 (arXiv:2302.05432), the load-corrected
    Dice standardised by the Shifts MS white-matter-lesion challenge.

    Plain DSC is biased by lesion LOAD (the fraction of voxels that are lesion): the same
    per-lesion error scores a very different DSC on a heavy-load vs a light-load scan, so
    DSC cannot be fairly compared or aggregated across patients. nDSC removes that bias by
    rescaling the false positives to a fixed REFERENCE load r (=0.001, the average lesion
    voxel fraction), so the score is load-invariant and equals plain DSC exactly when the
    scan's load equals r.

    Directional: `ref_mask` is the reference (ground truth), `pred_mask` the prediction.
    Exact formula from the reference implementation (github.com/NataliiaMolch/nDSC):
        scaling = (1 - r) * P / (r * (N - P))          # P = ref lesion voxels, N = total
        nDSC    = 2*TP / (2*TP + FN + scaling * FP)
    Empty-reference convention matches DSC (scaling=1 → nDSC=DSC; both empty → 1.0).
    """
    pred = pred_mask > 0
    ref = ref_mask > 0
    p = int(ref.sum())                 # reference lesion voxels
    n_total = int(ref.size)
    tp = int(np.count_nonzero(pred & ref))
    fp = int(np.count_nonzero(pred & ~ref))
    fn = int(np.count_nonzero(~pred & ref))

    if p == 0:  # empty reference → reduce to standard DSC (both empty → 1.0)
        denom = 2 * tp + fp + fn
        return 1.0 if denom == 0 else float(2 * tp / denom)

    n_neg = n_total - p
    scaling = 1.0 if n_neg == 0 else (1.0 - effective_load) * p / (effective_load * n_neg)
    denom = 2 * tp + fn + scaling * fp
    return float(2 * tp / denom) if denom > 0 else 1.0


def compute_jaccard(mask_a: np.ndarray, mask_b: np.ndarray) -> float:
    """Jaccard index (IoU) between two binary masks: |A ∩ B| / |A ∪ B|.

    Same empty-mask conventions as Dice: 1.0 if both empty, 0.0 if exactly one.
    """
    a = (mask_a > 0).astype(bool)
    b = (mask_b > 0).astype(bool)
    sum_a, sum_b = a.sum(), b.sum()
    if sum_a == 0 and sum_b == 0:
        return 1.0
    if sum_a == 0 or sum_b == 0:
        return 0.0
    inter = np.logical_and(a, b).sum()
    union = np.logical_or(a, b).sum()
    return float(inter / union)


def compute_avd(
    mask_a: np.ndarray,
    mask_b: np.ndarray,
    voxel_spacing: tuple[float, float, float],
) -> float:
    """Absolute Volume Difference as a fraction of the REFERENCE volume (B).

    AVD = |vol_a - vol_b| / vol_b — the standard benchmark volumetric error
    (MSSEG/ISBI), unsigned and normalized, unlike compute_volume_diff's signed
    percentage. Returns 0.0 if both empty; 1.0 (100%) if only the reference is
    empty but the prediction is not.
    """
    voxel_vol = float(np.prod(voxel_spacing))
    vol_a = float((mask_a > 0).sum()) * voxel_vol
    vol_b = float((mask_b > 0).sum()) * voxel_vol
    if vol_b == 0:
        return 0.0 if vol_a == 0 else 1.0
    return float(abs(vol_a - vol_b) / vol_b)


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


# Lesion size buckets (mm³) for size-stratified detection sensitivity. Small lesions
# are where every MS segmenter fails (e.g. FLAMeS 2025 reports ~35% detection for
# 3–10 mm³ vs ~81% for >10 mm³), so a single LTPR hides the clinically important gap.
# Aligned to the ISBI/MSSEG 3 mm³ noise floor and the FLAMeS size strata.
_SIZE_BUCKETS_MM3 = [
    (0.0, 3.0, "<3mm3 (sub-floor)"),
    (3.0, 10.0, "3-10mm3"),
    (10.0, 30.0, "10-30mm3"),
    (30.0, 100.0, "30-100mm3"),
    (100.0, float("inf"), ">=100mm3"),
]


def compute_lesion_detection_metrics(
    pred_mask: np.ndarray,
    ref_mask: np.ndarray,
    min_overlap_ratio: float = 0.0,
    voxel_spacing: "tuple[float, float, float] | None" = None,
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
    from app.services.lesion_metrics import label_lesions, meets_min_volume

    # Apply the SAME sub-noise-floor filter as the clinical lesion count (RC-030 /
    # MIN_LESION_VOLUME_MM3) so these detection metrics count the same discrete lesions the
    # app reports everywhere else. Without it, sub-3mm3 specks inflate n_pred -> a false LFPR
    # / broken detection F1 (audit finding #5). Spacing None -> voxel-count floor (vol=1).
    _voxel_vol = (float(voxel_spacing[0]) * float(voxel_spacing[1]) * float(voxel_spacing[2])
                  if voxel_spacing is not None else 1.0)

    def _floored_fg(mask: np.ndarray) -> np.ndarray:
        labeled, n = label_lesions(mask > 0)
        out = np.zeros(mask.shape, dtype=bool)
        for lbl in range(1, n + 1):
            comp = labeled == lbl
            if meets_min_volume(int(comp.sum()), _voxel_vol):
                out |= comp
        return out

    pred_fg = _floored_fg(pred_mask)
    ref_fg = _floored_fg(ref_mask)
    pred_labels, n_pred = label_lesions(pred_fg)
    ref_labels, n_ref = label_lesions(ref_fg)

    # Voxel volume for size stratification (mm³). None spacing → count in voxels.
    voxel_volume_mm3 = (
        float(voxel_spacing[0]) * float(voxel_spacing[1]) * float(voxel_spacing[2])
        if voxel_spacing is not None else None
    )

    # Reference lesions detected by the prediction (sensitivity numerator), tracking each
    # reference lesion's (size, detected) so detection can be stratified by lesion size.
    detected_ref = 0
    ref_sizes_detected: list[tuple[float, bool]] = []  # (size_mm3_or_voxels, detected)
    for lesion_id in range(1, n_ref + 1):
        component = ref_labels == lesion_id
        overlap = int(np.count_nonzero(component & pred_fg))
        size = int(np.count_nonzero(component))
        is_detected = size > 0 and (overlap / size) > min_overlap_ratio
        if is_detected:
            detected_ref += 1
        size_metric = size * voxel_volume_mm3 if voxel_volume_mm3 is not None else float(size)
        ref_sizes_detected.append((size_metric, is_detected))

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
    # LFPR = fraction of PREDICTED lesions that are false positives (= 1 - precision);
    # reported explicitly because it is the ISBI/MSSEG axis that penalises over-segmentation
    # (the field's honest failure mode), and 0.0 when nothing was predicted.
    lfpr = round(false_positives / n_pred, 4) if n_pred > 0 else 0.0

    # Size-stratified detection sensitivity — LTPR within each reference-lesion size band.
    # A single LTPR averages over sizes and hides that small lesions are systematically
    # missed; this exposes the clinically important small-lesion gap. mm³ when spacing is
    # known, else voxel counts (labelled accordingly, never silently conflated).
    size_unit = "mm3" if voxel_volume_mm3 is not None else "voxels"
    size_buckets = []
    for lo, hi, label_mm3 in _SIZE_BUCKETS_MM3:
        members = [det for (sz, det) in ref_sizes_detected if lo <= sz < hi]
        n_bucket = len(members)
        det_bucket = sum(1 for det in members if det)
        size_buckets.append({
            "bucket": label_mm3 if size_unit == "mm3" else label_mm3.replace("mm3", "vox"),
            "min": lo,
            "max": None if hi == float("inf") else hi,
            "n_ref": n_bucket,
            "detected": det_bucket,
            "sensitivity_ltpr": round(det_bucket / n_bucket, 4) if n_bucket > 0 else None,
        })

    return {
        "ref_lesion_count": n_ref,
        "pred_lesion_count": n_pred,
        "true_positives": detected_ref,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "sensitivity_ltpr": round(sensitivity, 4),
        "precision_lppv": round(precision, 4),
        "false_positive_rate_lfpr": lfpr,
        "lesion_f1": round(lesion_f1, 4),
        "size_stratified_sensitivity": {"unit": size_unit, "buckets": size_buckets},
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
    # nDSC (load-corrected Dice) — directional: A = prediction, B = reference.
    ndsc = compute_normalized_dice(pred_mask=mask_a, ref_mask=mask_b)
    hausdorff = compute_hausdorff(mask_a, mask_b, voxel_spacing)
    assd = compute_assd(mask_a, mask_b, voxel_spacing)
    # AVD = |vol_a − vol_b| / vol_b — the standard MSSEG/ISBI UNSIGNED, reference-normalised
    # volumetric error (directional: B = reference). Complements the signed diff_percent.
    avd = compute_avd(mask_a, mask_b, voxel_spacing)
    volume = compute_volume_diff(mask_a, mask_b, voxel_spacing)
    per_slice = compute_per_slice_dice(mask_a, mask_b)
    # Directional: A = prediction under test, B = reference.
    # Pass voxel_spacing so detection sensitivity is stratified by lesion size in mm³
    # (the SOTA/FLAMeS convention), not raw voxel counts.
    lesion_detection = compute_lesion_detection_metrics(
        pred_mask=mask_a, ref_mask=mask_b, voxel_spacing=voxel_spacing
    )

    return {
        "label_a": label_a,
        "label_b": label_b,
        "dice": round(dice, 4),
        # nDSC = load-corrected Dice (Shifts standard); comparable across lesion loads,
        # unlike plain Dice. Equals Dice when the scan's lesion load == the reference (0.001).
        "ndsc": round(ndsc, 4),
        "hausdorff_mm": round(hausdorff, 2) if hausdorff != float('inf') else None,
        # ASSD (average symmetric surface distance, mm) — the MSSEG-2/Anima mean
        # boundary metric complementing HD95's worst-case.
        "assd_mm": round(assd, 2) if assd != float('inf') else None,
        # AVD (absolute volume difference, fraction of the reference volume B) — MSSEG/ISBI.
        "avd": round(avd, 4),
        "volume": volume,
        "per_slice_dice": [round(d, 4) for d in per_slice],
        "lesion_detection": lesion_detection,
    }
