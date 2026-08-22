"""Slowly-Expanding Lesion (SEL) detection — INVESTIGATIONAL / candidate.

SELs (Elliott et al., Mult Scler J 2019) are the vanguard "smoldering disease" MRI
biomarker: a PRE-EXISTING lesion showing consistent CONCENTRIC (rim) expansion
between timepoints, detected via the Jacobian determinant of a NON-LINEAR
(diffeomorphic-demons) registration. Jacobian > 1 = local tissue expansion.

DELIBERATELY DEFORMABLE — the crucial distinction from the new-lesion path. In
registration_service a warp is BANNED (HAZ-LONG-2: it would shrink a genuinely NEW
lesion to match baseline, erasing the finding). Here the deformation IS the signal;
SELs are computed ONLY on pre-existing lesions, never to detect new ones. The ban is
scoped to registration_service.

Design (hardened after adversarial scientific review):
  1. RIGID pre-registration TP2→TP1 first (reuse registration_service), so demons
     measures LOCAL expansion, not the global head-pose difference, and the
     pre-existing overlap is tested on ALIGNED masks (review F3/F4).
  2. Deformable (diffeomorphic-demons) register the rigidly-aligned TP2 → TP1;
     Jacobian determinant on the TP1 grid. J>1 == expanded TP1→TP2 (sign verified).
  3. EXPANDING FRACTION, not whole-lesion mean: an SEL expands at the RIM while its
     demyelinated CORE is stable (and intensity-uniform cores give demons no signal
     — aperture problem). So per lesion we measure the FRACTION of its voxels that
     are locally expanding (per-voxel J ≥ a floor), which is Elliott's measure, not
     the review-flagged whole-lesion mean (F1).
  4. PER-SUBJECT NULL CALIBRATION (F2): the "expanding" fraction of the subject's own
     NORMAL-APPEARING tissue is the registration-noise floor. A lesion is an SEL
     candidate only if its expanding fraction BOTH clears an absolute minimum AND
     exceeds that per-subject noise floor by a margin — so the threshold is calibrated
     to each scan pair, not a magic constant.

Class C: SINGLE-INTERVAL (2 timepoints) → CANDIDATES only; the validated definition
confirms MONOTONIC expansion over ≥2 intervals (≥3 timepoints). Fail-closed (no SELs,
never false ones); determinism (threads pinned); the caller keeps the candidate
firewall (registration_verified stays False).

@module services.sel_detection_service
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import SimpleITK as sitk

from app.core.logging import get_logger

logger = get_logger(__name__)

# Determinism (safety): a near-threshold SEL must not flip run-to-run.
sitk.ProcessObject.SetGlobalDefaultNumberOfThreads(1)

# A voxel is "locally expanding" when its Jacobian ratio reaches this (~+5% volume).
VOXEL_EXPANSION_FLOOR = 1.05
# A lesion must have at least this FRACTION of voxels expanding to be considered...
MIN_EXPANDING_FRACTION = 0.30
# ...AND exceed the subject's own normal-tissue expanding fraction (registration-noise
# floor) by at least this margin (per-subject calibration, not a magic threshold).
NOISE_FLOOR_MARGIN = 0.15
# Pre-existing lesions below this volume (mm³) are too small for a reliable Jacobian.
DEFAULT_MIN_LESION_MM3 = 50.0
_DEMONS_ITERATIONS = 60
_DEMONS_SMOOTHING = 1.5


@dataclass
class SELResult:
    ok: bool
    reason: str = ""
    sels: list = field(default_factory=list)
    n_existing: int = 0
    n_sel: int = 0
    # Per-subject registration-noise floor (expanding fraction of normal tissue).
    background_expanding_fraction: float = 0.0
    voxel_expansion_floor: float = VOXEL_EXPANSION_FLOOR


def _to_sitk(arr: np.ndarray, spacing) -> sitk.Image:
    img = sitk.GetImageFromArray(np.ascontiguousarray(arr, dtype=np.float32))
    img.SetSpacing((float(spacing[2]), float(spacing[1]), float(spacing[0])))
    return img


def deformable_jacobian(fixed_img: np.ndarray, moving_img: np.ndarray, spacing) -> np.ndarray | None:
    """Diffeomorphic-Demons register moving→fixed and return the Jacobian determinant
    of the displacement field, fixed-space internal order (k,a0,a1). J>1 == the region
    EXPANDED from fixed to moving. Returns None on any failure / non-positive folds."""
    try:
        fixed_img = np.asarray(fixed_img, dtype=np.float32)
        moving_img = np.asarray(moving_img, dtype=np.float32)
        if fixed_img.ndim != 3 or moving_img.ndim != 3 or fixed_img.shape != moving_img.shape:
            return None
        if not (np.isfinite(fixed_img).all() and np.isfinite(moving_img).all()):
            return None

        f = _to_sitk(fixed_img, spacing)
        m = _to_sitk(moving_img, spacing)
        matcher = sitk.HistogramMatchingImageFilter()
        matcher.SetNumberOfHistogramLevels(256)
        matcher.SetNumberOfMatchPoints(16)
        matcher.ThresholdAtMeanIntensityOn()
        m = matcher.Execute(m, f)

        demons = sitk.DiffeomorphicDemonsRegistrationFilter()
        demons.SetNumberOfIterations(_DEMONS_ITERATIONS)
        demons.SetStandardDeviations(_DEMONS_SMOOTHING)
        disp = demons.Execute(f, m)

        jac = sitk.DisplacementFieldJacobianDeterminant(disp)
        jac_arr = sitk.GetArrayFromImage(jac).astype(np.float32)
        if not np.isfinite(jac_arr).all():
            return None
        # Fold guard (review F5): the discrete Jacobian can go ≤0 at large boundary
        # deformations even for a "diffeomorphic" field. A non-positive determinant is
        # not a physiologic volume ratio — a large fold fraction means the field is
        # untrustworthy → fail closed.
        if (jac_arr <= 0).mean() > 0.001:
            logger.warning("[SEL] deformable field has folds (J<=0); failing closed")
            return None
        return jac_arr
    except Exception as e:  # noqa: BLE001 — fail closed (no SELs, never false ones)
        logger.warning("[SEL] deformable Jacobian failed closed", extra={"error": str(e)})
        return None


def detect_sels(
    tp1_img: np.ndarray,
    tp2_img: np.ndarray,
    tp1_mask: np.ndarray,
    tp2_mask: np.ndarray,
    spacing,
    min_lesion_mm3: float = DEFAULT_MIN_LESION_MM3,
) -> SELResult:
    """Detect SEL CANDIDATES among PRE-EXISTING lesions via a rigid→deformable
    pipeline, the per-lesion expanding FRACTION, and a per-subject noise-floor
    calibration. Fail-closed → SELResult(ok=False) with no SELs.
    """
    from app.services.lesion_metrics import label_lesions, meets_min_volume
    from app.services.registration_service import register_timepoints
    from scipy.ndimage import center_of_mass

    tp1_bin = (np.asarray(tp1_mask) > 0)
    tp2_bin = (np.asarray(tp2_mask) > 0)
    if tp1_bin.shape != tp2_bin.shape:
        return SELResult(False, reason="mask shape mismatch")

    spacing = tuple(float(s) for s in spacing)

    # 1) RIGID pre-align TP2→TP1 so demons measures local expansion, not head pose,
    #    and the pre-existing test runs on ALIGNED masks (review F3/F4). Fail-closed.
    reg = register_timepoints(np.asarray(tp1_img, np.float32), np.asarray(tp2_img, np.float32),
                              tp2_bin.astype(np.uint8), spacing)
    if not reg.registration_ok or reg.resampled_moving_image is None or reg.resampled_moving_mask is None:
        return SELResult(False, reason=f"rigid pre-registration failed: {reg.reason}")
    tp2_img_aligned = np.asarray(reg.resampled_moving_image, np.float32)
    tp2_mask_aligned = np.asarray(reg.resampled_moving_mask) > 0
    brain = (np.asarray(reg.brain_domain) > 0) if reg.brain_domain is not None else None

    # 2) Deformable Jacobian on the rigidly-aligned pair.
    jac = deformable_jacobian(np.asarray(tp1_img, np.float32), tp2_img_aligned, spacing)
    if jac is None:
        return SELResult(False, reason="deformable registration failed closed")
    if jac.shape != tp1_bin.shape:
        return SELResult(False, reason="jacobian/mask grid mismatch")

    expanding = jac >= VOXEL_EXPANSION_FLOOR

    # 4) Per-subject noise floor: expanding fraction of NORMAL-APPEARING tissue
    #    (brain minus lesions). This calibrates the SEL bar to THIS scan pair.
    if brain is not None and brain.any():
        nawm = brain & ~(tp1_bin | tp2_mask_aligned)
    else:
        nawm = ~(tp1_bin | tp2_mask_aligned)
    background_frac = float(expanding[nawm].mean()) if nawm.any() else 0.0
    sel_bar = max(MIN_EXPANDING_FRACTION, background_frac + NOISE_FLOOR_MARGIN)

    voxel_vol = float(np.prod(spacing))
    labeled, n = label_lesions(tp1_bin)
    sels = []
    n_existing = 0
    for lid in range(1, n + 1):
        comp = labeled == lid
        count = int(comp.sum())
        if not meets_min_volume(count, voxel_vol) or count * voxel_vol < min_lesion_mm3:
            continue
        # PRE-EXISTING = TP1 lesion still present at TP2 (on the ALIGNED TP2 mask).
        overlap = int((comp & tp2_mask_aligned).sum())
        if overlap == 0 or overlap / count < 0.30:
            continue
        n_existing += 1
        # 3) EXPANDING FRACTION (not whole-lesion mean).
        frac = float(expanding[comp].mean())
        if frac >= sel_bar:
            cz, cy, cx = center_of_mass(comp)
            sels.append({
                "centroid_z": round(float(cz), 1),
                "centroid_y": round(float(cy), 1),
                "centroid_x": round(float(cx), 1),
                "baseline_volume_mm3": round(count * voxel_vol, 2),
                "expanding_fraction": round(frac, 3),
                "mean_jacobian": round(float(jac[comp].mean()), 3),
            })

    return SELResult(
        ok=True,
        reason="ok",
        sels=sels,
        n_existing=n_existing,
        n_sel=len(sels),
        background_expanding_fraction=round(background_frac, 3),
        voxel_expansion_floor=VOXEL_EXPANSION_FLOOR,
    )
