"""Longitudinal intra-subject registration (REQ-FUNC-LONG-001, INVESTIGATIONAL — SHADOW).

Registers a later timepoint (TP2) to an earlier one (TP1) so the longitudinal overlay is
TRUTHFULLY co-registered instead of index-aligned — which removes misregistration false
positives from the CANDIDATE change counts. It asserts NO new clinical claim:
`registration_verified` is NEVER set true here (increment 1). The endpoint keeps today's
candidate firewall verbatim; the report builder keeps forcing verified=False.

Design shaped by the 2026-08-21 adversarial design+refute (workflow w3p81u3kz), whose two
independent skeptics converged on:

  * RIGID only (Euler3D, 6 DOF). Intra-subject the brain is a near-rigid body; a rigid
    transform cannot absorb lesion change. DEFORMABLE registration IS BANNED — a non-linear
    warp shrinks a new lesion to match TP1's normal tissue, erasing the finding
    (HAZ-LONG-2). Enforced by a static CI test (no deformable-transform symbol in this file).
  * DETERMINISM is a safety property: ITK MI random-sampling is reproducible only
    single-threaded, so threads are pinned to 1 at import (a near-threshold pair must not
    flip PASS/FAIL run-to-run).
  * FAIL-CLOSED: any exception / non-finite / non-convergence / empty-or-degenerate brain
    mask / bad input -> registration_ok=False -> caller keeps the candidate firewall.
  * The QC readout here is ADVISORY ONLY and is explicitly NOT the gate for flipping
    `registration_verified`. Whole-brain overlap Dice SATURATES above the lesion length
    scale — a 3-5 mm residual that can mint a phantom "new" lesion barely moves it — so it
    cannot certify lesion-scale alignment. A lesion-scale QC gate is still to be designed
    AND validated on adjudicated multi-session intensity pairs (NOT available in-hand; see
    docs/longitudinal-registration/REG-VV-DOSSIER.md, gates NOT_MEETABLE on public data).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import SimpleITK as sitk

from app.core.logging import get_logger

logger = get_logger(__name__)

# DETERMINISM (safety): pin ITK to a single thread so MI random-sampling — and therefore
# the recovered transform and every QC readout — are reproducible run-to-run. Without this
# the thread pool sizes to the node's hardware concurrency (independent of the CPU quota)
# and a near-threshold pair could flip nondeterministically.
sitk.ProcessObject.SetGlobalDefaultNumberOfThreads(1)

# A brain mask with fewer than this many voxels is degenerate (empty/low-contrast/prob-map
# masquerading as intensity) -> fail closed rather than register against noise.
_MIN_BRAIN_VOXELS = 1000
_MAX_ITERATIONS = 200


@dataclass
class RegistrationResult:
    """Outcome of a shadow registration. `registration_verified` is ALWAYS False in
    increment 1 — it is present only to make the firewall contract explicit."""
    registration_ok: bool
    registration_verified: bool = False   # HARD FALSE — never flipped in shadow mode
    method: str = "rigid_euler3d"
    reason: str = ""
    advisory_qc: dict = field(default_factory=dict)
    transform_params: dict = field(default_factory=dict)
    resampled_moving_mask: np.ndarray | None = None
    # The moving (TP2) INTENSITY resampled into fixed (TP1) space — LINEAR
    # interpolation (intensities, not labels). Enables an intensity subtraction map
    # (TP2−TP1) for new-lesion confirmation. None when registration failed closed.
    resampled_moving_image: np.ndarray | None = None
    # Valid subtraction domain (fixed space): where BOTH timepoints have brain —
    # fixed brain ∩ resampled-moving brain. Excludes air/background, the resample
    # zero-pad rim, and FOV-clipped regions, so subtraction normalization and
    # boundary rejection avoid confirming misregistration/edge artifacts (A+B
    # adversarial Findings 1/2). None when registration failed closed.
    brain_domain: np.ndarray | None = None

    def as_dict(self) -> dict:
        return {
            "registration_ok": self.registration_ok,
            "registration_verified": False,   # invariant: never true here
            "method": self.method,
            "reason": self.reason,
            # ADVISORY — NOT a safety gate. brain-overlap Dice does not certify lesion-scale
            # alignment (it saturates above the lesion scale).
            "advisory_qc": self.advisory_qc,
            "transform_params": self.transform_params,
        }


def _to_sitk(arr: np.ndarray, spacing) -> sitk.Image:
    img = sitk.GetImageFromArray(np.ascontiguousarray(arr, dtype=np.float32))
    # spacing arrives as (dz, dy, dx) (array order); sitk wants (x, y, z).
    img.SetSpacing((float(spacing[2]), float(spacing[1]), float(spacing[0])))
    return img


def _brain_mask(img: sitk.Image) -> sitk.Image:
    """Otsu brain-ish mask -> largest connected component -> fill holes. NOTE: Otsu is a
    leaky brain extractor on MRI (skull/scalp share the bright class); this mask is used
    only to focus MI sampling and for the ADVISORY overlap readout, never as a safety gate."""
    m = sitk.OtsuThreshold(img, 0, 1)          # foreground (bright) = 1
    m = sitk.BinaryMorphologicalClosing(m, [2, 2, 2])
    cc = sitk.RelabelComponent(sitk.ConnectedComponent(m), sortByObjectSize=True)
    m = sitk.BinaryFillhole(cc == 1)           # keep largest component, fill interior
    return m


def _dice(a: sitk.Image, b: sitk.Image) -> float:
    aa = sitk.GetArrayViewFromImage(a) > 0
    bb = sitk.GetArrayViewFromImage(b) > 0
    denom = int(aa.sum()) + int(bb.sum())
    if denom == 0:
        return 0.0
    return float(2 * np.logical_and(aa, bb).sum() / denom)


def register_rigid(fixed: sitk.Image, moving: sitk.Image,
                   fixed_mask: sitk.Image, moving_mask: sitk.Image):
    """Rigid (Euler3D) Mattes-MI multi-resolution registration of `moving` -> `fixed`.
    Returns (transform, final_metric, stop_condition). Raises on ITK failure (caller
    fail-closes)."""
    initial = sitk.CenteredTransformInitializer(
        fixed, moving, sitk.Euler3DTransform(),
        sitk.CenteredTransformInitializerFilter.MOMENTS)

    R = sitk.ImageRegistrationMethod()
    R.SetMetricAsMattesMutualInformation(numberOfHistogramBins=32)
    R.SetMetricSamplingStrategy(R.RANDOM)
    R.SetMetricSamplingPercentage(0.10, seed=42)     # deterministic (threads pinned to 1)
    R.SetMetricFixedMask(fixed_mask)                 # sample brain only
    R.SetMetricMovingMask(moving_mask)
    R.SetInterpolator(sitk.sitkLinear)
    R.SetOptimizerAsRegularStepGradientDescent(
        learningRate=1.0, minStep=1e-4,
        numberOfIterations=_MAX_ITERATIONS,
        gradientMagnitudeTolerance=1e-6, relaxationFactor=0.5)
    R.SetOptimizerScalesFromPhysicalShift()          # balance rotation vs translation DOF
    R.SetShrinkFactorsPerLevel([4, 2, 1])
    R.SetSmoothingSigmasPerLevel([2, 1, 0])
    R.SmoothingSigmasAreSpecifiedInPhysicalUnitsOn()
    R.SetInitialTransform(initial, inPlace=False)

    tx = R.Execute(fixed, moving)
    return tx, float(R.GetMetricValue()), R.GetOptimizerStopConditionDescription()


def register_timepoints(fixed_img: np.ndarray, moving_img: np.ndarray,
                        moving_mask: np.ndarray, spacing) -> RegistrationResult:
    """Shadow registration of TP2 (`moving_*`) onto TP1 (`fixed_img`), resampling the TP2
    lesion mask into TP1 space (nearest-neighbour, label-preserving).

    FAIL-CLOSED: returns registration_ok=False on any bad input, non-finite data,
    degenerate brain mask, non-convergence, or ITK error. registration_verified is NEVER
    true (increment 1). On success the resampled TP2 mask + an ADVISORY QC readout are
    returned; the caller still applies the candidate firewall."""
    try:
        fixed_img = np.asarray(fixed_img, dtype=np.float32)
        moving_img = np.asarray(moving_img, dtype=np.float32)
        moving_mask = np.asarray(moving_mask)
        if fixed_img.ndim != 3 or moving_img.ndim != 3:
            return RegistrationResult(False, reason="inputs must be 3D")
        if not (np.isfinite(fixed_img).all() and np.isfinite(moving_img).all()):
            return RegistrationResult(False, reason="non-finite intensities")

        f = _to_sitk(fixed_img, spacing)
        m = _to_sitk(moving_img, spacing)
        fmask = _brain_mask(f)
        mmask = _brain_mask(m)
        f_vox = int(sitk.GetArrayViewFromImage(fmask).sum())
        m_vox = int(sitk.GetArrayViewFromImage(mmask).sum())
        if f_vox < _MIN_BRAIN_VOXELS or m_vox < _MIN_BRAIN_VOXELS:
            return RegistrationResult(False, reason="degenerate/empty brain mask")

        tx, metric, stop = register_rigid(f, m, fmask, mmask)
        # Fail closed on non-convergence. For RegularStepGradientDescent, a SUCCESSFUL solve
        # stops with "Step too small" (the step refined below minStep) or a gradient-tolerance
        # message; the ONLY suspect stop is hitting the iteration cap (still moving when it ran
        # out). Treat "maximum number of iterations" as non-convergence, everything else as OK.
        converged = "maximum number of iterations" not in stop.lower()
        if not np.isfinite(metric):
            return RegistrationResult(False, reason="non-finite registration metric")

        # Resample the TP2 mask into TP1 space, nearest-neighbour (label-preserving).
        m_mask_img = _to_sitk(moving_mask.astype(np.float32), spacing)
        resampled = sitk.Resample(m_mask_img, f, tx, sitk.sitkNearestNeighbor, 0.0,
                                  m_mask_img.GetPixelID())
        resampled_arr = (sitk.GetArrayFromImage(resampled) > 0.5).astype(np.uint8)

        # Resample the moving brain mask too, for the ADVISORY overlap readout.
        mmask_resampled = sitk.Resample(mmask, f, tx, sitk.sitkNearestNeighbor, 0.0,
                                       mmask.GetPixelID())

        # Resample the moving INTENSITY into fixed space (LINEAR — intensities, not
        # labels) so a subtraction map (TP2−TP1) can confirm new-lesion candidates.
        moving_img_resampled = sitk.Resample(m, f, tx, sitk.sitkLinear, 0.0, m.GetPixelID())
        resampled_img_arr = sitk.GetArrayFromImage(moving_img_resampled).astype(np.float32)

        # Valid subtraction domain = fixed brain ∩ resampled-moving brain. Only where
        # BOTH timepoints have brain is a subtraction meaningful; this excludes the
        # resample zero-pad rim and FOV-clipped regions where a linear-interpolation
        # edge would otherwise mint a false positive subtraction signal.
        brain_fixed = sitk.GetArrayViewFromImage(fmask) > 0
        brain_moving = sitk.GetArrayViewFromImage(mmask_resampled) > 0
        brain_domain_arr = (brain_fixed & brain_moving).astype(np.uint8)
        params = tx.GetParameters()  # (rx, ry, rz, tx, ty, tz) for Euler3D
        rot_deg = float(np.degrees(np.linalg.norm(params[:3])))
        trans_mm = float(np.linalg.norm(params[3:6]))
        advisory = {
            "brain_overlap_dice": _dice(fmask, mmask_resampled),
            "final_mi_metric": metric,
            "rotation_deg": rot_deg,
            "translation_mm": trans_mm,
            "stop_condition": stop,
            "note": ("ADVISORY ONLY — brain-overlap Dice does NOT certify lesion-scale "
                     "alignment; it is not the gate for registration_verified."),
        }
        if not converged:
            return RegistrationResult(False, reason=f"did not converge: {stop}",
                                      advisory_qc=advisory)

        return RegistrationResult(
            registration_ok=True, reason="rigid registration converged",
            advisory_qc=advisory,
            transform_params={"rotation_deg": rot_deg, "translation_mm": trans_mm},
            resampled_moving_mask=resampled_arr,
            resampled_moving_image=resampled_img_arr,
            brain_domain=brain_domain_arr)
    except Exception as e:  # noqa: BLE001 — any ITK/other failure must fail closed
        logger.warning("[Registration] failed closed", extra={"error": str(e)})
        return RegistrationResult(False, reason=f"registration error: {e}")


def registered_change_candidates(tp1_img, tp2_img, tp1_mask, tp2_mask, spacing,
                                 iou_threshold: float = 0.3) -> dict:
    """SHADOW register-then-compare: register TP2->TP1 (rigid), resample the TP2 lesion mask
    into TP1 space, and run the longitudinal change comparison on the CO-REGISTERED masks —
    so change CANDIDATES are computed on truthfully aligned data (fewer misregistration
    false positives) instead of index-aligned masks.

    registration_verified is NEVER true here (shadow). If registration fails closed, the
    comparison falls back to the UN-registered TP2 mask and `registration_applied=False`,
    preserving today's candidate firewall verbatim. The QC readout is advisory, not a flip
    gate. The caller must still present every count as an unadjudicated candidate.
    """
    from app.services.longitudinal_tracking_service import compare_timepoints
    reg = register_timepoints(tp1_img, tp2_img, tp2_mask, spacing)
    applied = bool(reg.registration_ok and reg.resampled_moving_mask is not None)
    tp2_for_compare = reg.resampled_moving_mask if applied else np.asarray(tp2_mask)
    result = compare_timepoints(np.asarray(tp1_mask), tp2_for_compare, tuple(float(s) for s in spacing),
                                iou_threshold=iou_threshold)
    result["registration_applied"] = applied
    result["registration_verified"] = False        # invariant: never true in shadow
    result["registration_advisory_qc"] = reg.advisory_qc
    result["registration_reason"] = reg.reason

    # FLAIR SUBTRACTION CONFIRMATION (advisory). On the CO-REGISTERED intensities,
    # measure whether each NEW candidate is actually brighter at follow-up — the
    # clinically-validated new-lesion sensitivity/specificity aid. A "new" candidate
    # with no positive subtraction signal is likely a segmentation/registration
    # artifact. NEVER upgrades a candidate to a finding (registration_verified stays
    # False); only annotates. Requires registration to have run (subtraction on
    # un-registered volumes is dominated by pose, not disease).
    result["subtraction_available"] = False
    if applied and reg.resampled_moving_image is not None:
        try:
            from app.services.longitudinal_subtraction import subtraction_map, confirm_new_candidates
            sub = subtraction_map(
                np.asarray(tp1_img, dtype=np.float32), reg.resampled_moving_image,
                brain_mask=reg.brain_domain,
            )
            if sub is not None:
                summary = confirm_new_candidates(
                    result["changes"], tp2_for_compare, sub, brain_domain=reg.brain_domain,
                )
                result["subtraction_available"] = True
                result["subtraction_summary"] = summary
        except Exception as e:  # noqa: BLE001 — advisory; must never break the comparison
            logger.warning("[Subtraction] confirmation skipped", extra={"error": str(e)})
    return result
