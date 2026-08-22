"""Bridge from this research package to the repo's CALM-MS conformal layer + metrics.

The whole point of the nnU-Net base segmenter is that it plugs UNDERNEATH the repo's
already-shipped, model-agnostic CALM-MS conformal precision-control layer. That layer is
authoritative and MUST NOT be re-implemented here — we import it. This module:

  1. Locates the repo's `backend/` package (via CALM_MS_BACKEND env override, else the
     repo layout relative to this file) and puts it on sys.path.
  2. Re-exports the CALM-MS bridge functions (candidate extraction, feature matrix,
     conformal selection) so the segmenter's output format is, by construction, the
     format CALM-MS consumes.
  3. Re-exports the repo's lesion metrics (18-connectivity Dice + lesion-wise TPR/PPV/F1)
     when reachable, and otherwise exposes a small, convention-identical vendored fallback
     (18-conn labelling, ISBI/MSSEG any-voxel detection) so the CPU benchmark still runs
     outside a full repo checkout. `USING_REPO_METRICS` records which path was taken.

Nothing here trains or touches app/ code; it is read-only glue.
"""
from __future__ import annotations

import os
import sys

import numpy as np

# ---------------------------------------------------------------------------
# Locate the repo backend and put it on sys.path.
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_BACKEND = os.path.abspath(os.path.join(_HERE, "..", "..", "backend"))
CALM_MS_BACKEND = os.environ.get("CALM_MS_BACKEND", _DEFAULT_BACKEND)

if os.path.isdir(CALM_MS_BACKEND) and CALM_MS_BACKEND not in sys.path:
    sys.path.insert(0, CALM_MS_BACKEND)


class BridgeError(RuntimeError):
    """Raised when the CALM-MS layer cannot be imported from the repo backend."""


# ---------------------------------------------------------------------------
# CALM-MS conformal layer — REQUIRED (this is the layer we plug under).
# ---------------------------------------------------------------------------
try:
    from app.services.calm_ms_inference import (   # noqa: E402
        LesionCandidate,
        extract_lesion_candidates,
        label_candidates_tp,
        build_calibration_nulls,
        select_lesions_conformal,
        ConformalResult,
        SCORE_MEAN,
        SCORE_MAX,
    )
    from app.services.calm_ms_lesion_features import (   # noqa: E402
        candidate_feature_matrix,
        FEATURE_NAMES,
    )
    from app.services.conformal_lesion_fdr import select_by_fdr  # noqa: E402
    from app.services.lesion_metrics import (   # noqa: E402
        MIN_LESION_VOLUME_MM3,
        label_lesions as _repo_label_lesions,
    )
    HAVE_CALM = True
    _CALM_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - exercised only outside a repo checkout
    HAVE_CALM = False
    _CALM_IMPORT_ERROR = exc
    MIN_LESION_VOLUME_MM3 = 3.0
    FEATURE_NAMES = ()


def require_calm() -> None:
    """Fail loudly (not silently) if the CALM-MS layer is unreachable.

    Candidate extraction, feature extraction and conformal selection have NO honest
    fallback — they must be the exact code the shipped conformal guarantee is calibrated
    against — so callers that need them gate on this.
    """
    if not HAVE_CALM:
        raise BridgeError(
            "Could not import the CALM-MS conformal layer from the repo backend at "
            f"'{CALM_MS_BACKEND}'. Set CALM_MS_BACKEND to the repo's backend/ dir. "
            f"Underlying import error: {_CALM_IMPORT_ERROR!r}"
        )


# ---------------------------------------------------------------------------
# Metrics — PREFER the repo's, else a convention-identical vendored fallback.
# ---------------------------------------------------------------------------
try:
    from app.services.segmentation_comparison_service import (   # noqa: E402
        compute_dice as _repo_compute_dice,
        compute_lesion_detection_metrics as _repo_lesion_metrics,
    )
    USING_REPO_METRICS = True
    _METRICS_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - exercised only outside a repo checkout
    USING_REPO_METRICS = False
    _METRICS_IMPORT_ERROR = exc


def _fallback_label_lesions(binary_mask: np.ndarray):
    """18-connected labelling (ISBI-2015 / MSSEG-2016), matching RC-030."""
    from scipy.ndimage import label, generate_binary_structure

    return label(np.asarray(binary_mask) > 0, structure=generate_binary_structure(3, 2))


def label_lesions(binary_mask: np.ndarray):
    """18-connected discrete-lesion labelling (repo convention if reachable, else vendored)."""
    if HAVE_CALM:
        return _repo_label_lesions(binary_mask)
    return _fallback_label_lesions(binary_mask)


def compute_dice(mask_a: np.ndarray, mask_b: np.ndarray) -> float:
    """Dice; both-empty -> 1.0, one-empty -> 0.0 (repo convention)."""
    if USING_REPO_METRICS:
        return _repo_compute_dice(mask_a, mask_b)
    a = np.asarray(mask_a) > 0
    b = np.asarray(mask_b) > 0
    sa, sb = int(a.sum()), int(b.sum())
    if sa == 0 and sb == 0:
        return 1.0
    if sa == 0 or sb == 0:
        return 0.0
    return float(2.0 * np.logical_and(a, b).sum() / (sa + sb))


def compute_lesion_detection_metrics(
    pred_mask: np.ndarray,
    ref_mask: np.ndarray,
    min_overlap_ratio: float = 0.0,
    voxel_spacing=None,
) -> dict:
    """Lesion-wise TPR/PPV/F1 (18-conn, ISBI/MSSEG any-voxel convention).

    Uses the repo's audited implementation when reachable; otherwise a compact vendored
    equivalent with the same 18-connectivity, the same asymmetric >=3 mm3 prediction-only
    noise floor, and the same empty-mask conventions.
    """
    if USING_REPO_METRICS:
        return _repo_lesion_metrics(pred_mask, ref_mask, min_overlap_ratio, voxel_spacing)

    voxel_vol = (float(np.prod(voxel_spacing)) if voxel_spacing is not None else 1.0)

    def _floored_fg(mask):
        labeled, n = _fallback_label_lesions(mask > 0)
        out = np.zeros(mask.shape, dtype=bool)
        for lbl in range(1, n + 1):
            comp = labeled == lbl
            if int(comp.sum()) * voxel_vol >= MIN_LESION_VOLUME_MM3:
                out |= comp
        return out

    pred_fg = _floored_fg(np.asarray(pred_mask))
    ref_fg = np.asarray(ref_mask) > 0
    pred_labels, n_pred = _fallback_label_lesions(pred_fg)
    ref_labels, n_ref = _fallback_label_lesions(ref_fg)

    detected_ref = 0
    for i in range(1, n_ref + 1):
        comp = ref_labels == i
        size = int(comp.sum())
        overlap = int(np.count_nonzero(comp & pred_fg))
        if size > 0 and (overlap / size) > min_overlap_ratio:
            detected_ref += 1
    matched_pred = 0
    for i in range(1, n_pred + 1):
        comp = pred_labels == i
        size = int(comp.sum())
        overlap = int(np.count_nonzero(comp & ref_fg))
        if size > 0 and (overlap / size) > min_overlap_ratio:
            matched_pred += 1

    sensitivity = (detected_ref / n_ref) if n_ref > 0 else 1.0
    precision = (matched_pred / n_pred) if n_pred > 0 else 1.0
    denom = precision + sensitivity
    f1 = (2 * precision * sensitivity / denom) if denom > 0 else 0.0
    return {
        "ref_lesion_count": n_ref,
        "pred_lesion_count": n_pred,
        "true_positives": detected_ref,
        "false_positives": n_pred - matched_pred,
        "false_negatives": n_ref - detected_ref,
        "sensitivity_ltpr": round(sensitivity, 4),
        "precision_lppv": round(precision, 4),
        "false_positive_rate_lfpr": round((n_pred - matched_pred) / n_pred, 4) if n_pred else 0.0,
        "lesion_f1": round(f1, 4),
        "min_overlap_ratio": min_overlap_ratio,
        "connectivity": 18,
    }


__all__ = [
    # CALM-MS conformal layer (re-exported from the repo backend)
    "LesionCandidate", "extract_lesion_candidates", "label_candidates_tp",
    "build_calibration_nulls", "select_lesions_conformal", "ConformalResult",
    "SCORE_MEAN", "SCORE_MAX", "candidate_feature_matrix", "FEATURE_NAMES",
    "select_by_fdr", "MIN_LESION_VOLUME_MM3",
    # metrics (repo or vendored fallback)
    "label_lesions", "compute_dice", "compute_lesion_detection_metrics",
    # status / guards
    "require_calm", "HAVE_CALM", "USING_REPO_METRICS", "bridge_status", "BridgeError",
    "CALM_MS_BACKEND",
]


def bridge_status() -> dict:
    """Small diagnostic dict for CLIs to print at startup."""
    return {
        "backend": CALM_MS_BACKEND,
        "have_calm": HAVE_CALM,
        "using_repo_metrics": USING_REPO_METRICS,
        "n_features": len(FEATURE_NAMES),
    }
