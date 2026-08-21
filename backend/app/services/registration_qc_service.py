"""Lesion-scale registration QC gate (REQ-FUNC-LONG-011, gate_2 of the registration V&V
dossier). INVESTIGATIONAL — necessary-not-sufficient; a PASS here is NOT authorization to
flip registration_verified (gates 4-7 stay blocked; the flag stays hard-false).

WHY THIS EXISTS: the whole-brain-overlap Dice QC was ruled UNSAFE (it saturates above the
lesion length-scale and rubber-stamps the registrar's own MI). This measures the residual
misalignment LEFT AFTER registration at LESION scale, in millimetres, on a channel the MI
optimizer never referenced (lesion centroids).

Design shaped + hardened by two adversarial rounds (workflows wj2aubap5 / wf_bf51d924-57d):

  * PRIMARY, MI-orthogonal signal: `R_disp` = worst-case centroid displacement (mm) of
    matched STABLE lesion fiducials between the TP1 mask and the resampled TP2 mask. Report
    in the hazard's own units (mm), not an overlap ratio.
  * MUTUAL-BEST matching (not the tracker's greedy best-IoU): a residual that slides a
    lesion onto a NEIGHBOUR's footprint would give a small centroid delta under greedy
    matching -> silent PASS. Require reciprocal best + reject ambiguous seconds.
  * COVERAGE GUARD (closes the rotational lever-arm blind spot): centroid displacement under
    a residual rotation is theta*r (r = distance from axis). Large MS fiducials are
    periventricular = central = small r, so a central-only fiducial set UNDER-reports
    rotation exactly where it is largest. If the fiducials are centrally clustered (do not
    span the brain), we CANNOT observe the periphery -> REJECT (fail-closed), never certify.
  * FAIL-CLOSED: <3 fiducials / ambiguous match / no coverage / non-finite / undefined ->
    qc_pass=False. The cut is max(1.0 mm, measured jitter floor + margin) — the floor is a
    MEASURED input (biological + inter-session segmentation jitter), not an assumption.
  * The local-intensity NCC arm is ADVISORY only (it lives on MI's high-gradient leverage
    region, and there is no intensity in the staged cohort) — never a PASS conjunct.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.services.longitudinal_tracking_service import _extract_components

# Fiducial must be large enough that a hazard-scale (3-5 mm) shift cannot break its own
# match (equiv-sphere diameter ~7.8 mm) — see circularity handling in the dossier.
_V_FID_MM3 = 250.0
_VOL_STABLE_FRAC = 0.10        # |dV|/V1 <= 10% -> near-static (centroid moves ~= residual)
_MIN_FIDUCIALS = 3
_IOU_MATCH = 0.3
_AMBIGUITY_MARGIN = 0.1        # reject a fiducial whose 2nd-best IoU is within this margin
_COVERAGE_MIN_MM = 50.0        # fiducial centroids must span >= this (else central-clustered)
_R_DISP_CUT_MM = 1.0           # <=1 mm residual cannot unseat a >=4 mm lesion below IoU 0.3
_MARGIN_MM = 0.25


@dataclass
class LesionScaleQC:
    qc_pass: bool
    r_disp_mm: float | None = None
    n_fiducials: int = 0
    coverage_span_mm: float | None = None
    cut_mm: float = _R_DISP_CUT_MM
    reason: str = ""
    per_fiducial: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "qc_pass": bool(self.qc_pass),
            "r_disp_mm": self.r_disp_mm,
            "n_fiducials": self.n_fiducials,
            "coverage_span_mm": self.coverage_span_mm,
            "cut_mm": self.cut_mm,
            "reason": self.reason,
            "is_flip_authorization": False,   # gate_2 is necessary-not-sufficient
        }


def _iou_matrix(comps1, comps2) -> np.ndarray:
    sets1 = [set(map(tuple, c["mask_indices"])) for c in comps1]
    sets2 = [set(map(tuple, c["mask_indices"])) for c in comps2]
    iou = np.zeros((len(comps1), len(comps2)), dtype=float)
    for i, s1 in enumerate(sets1):
        for j, s2 in enumerate(sets2):
            u = len(s1 | s2)
            iou[i, j] = (len(s1 & s2) / u) if u else 0.0
    return iou


def _mutual_best_fiducials(comps1, comps2):
    """Reciprocal best-IoU matches with ambiguity rejection. A fiducial is kept only if it
    is each other's unique best match with no close second — so a shift onto a neighbour
    (greedy false match) cannot pass silently."""
    if not comps1 or not comps2:
        return []
    iou = _iou_matrix(comps1, comps2)
    fids = []
    for i in range(len(comps1)):
        row = iou[i]
        j = int(np.argmax(row))
        if row[j] < _IOU_MATCH:
            continue
        if int(np.argmax(iou[:, j])) != i:      # not reciprocal best -> drop
            continue
        srt = np.sort(row)[::-1]
        if srt.size > 1 and srt[1] >= _IOU_MATCH and (srt[0] - srt[1]) < _AMBIGUITY_MARGIN:
            continue                             # ambiguous second -> drop (fail-closed)
        fids.append((comps1[i], comps2[j]))
    return fids


def lesion_scale_qc(mask_tp1: np.ndarray, mask_tp2_resampled: np.ndarray, spacing,
                    jitter_floor_mm: float | None = None) -> LesionScaleQC:
    """Lesion-scale registration QC on the TP1 mask vs the RESAMPLED TP2 mask (already in
    TP1 space). Fail-closed: any undefined/degenerate case -> qc_pass=False. A PASS is
    necessary-not-sufficient and NEVER flips registration_verified."""
    try:
        spacing = tuple(float(s) for s in spacing)
        if len(spacing) != 3 or any(s <= 0 for s in spacing):
            return LesionScaleQC(False, reason="invalid spacing")
        m1 = np.asarray(mask_tp1)
        m2r = np.asarray(mask_tp2_resampled)
        if m1.shape != m2r.shape or m1.ndim != 3:
            return LesionScaleQC(False, reason="mask shape mismatch / not 3D")

        comps1 = _extract_components(m1, spacing)
        comps2 = _extract_components(m2r, spacing)
        if len(comps1) == 0 or len(comps2) == 0:
            return LesionScaleQC(False, reason="no lesions in one timepoint -> cannot certify")

        # Stable, large, unambiguously-matched fiducials only.
        fids = []
        for c1, c2 in _mutual_best_fiducials(comps1, comps2):
            if c1["volume_mm3"] < _V_FID_MM3 or c2["volume_mm3"] < _V_FID_MM3:
                continue
            if abs(c2["volume_mm3"] - c1["volume_mm3"]) / max(c1["volume_mm3"], 1e-6) > _VOL_STABLE_FRAC:
                continue
            fids.append((c1, c2))

        if len(fids) < _MIN_FIDUCIALS:
            return LesionScaleQC(False, n_fiducials=len(fids),
                                 reason=f"only {len(fids)} stable fiducials (<{_MIN_FIDUCIALS}) -> cannot certify")

        sp = np.array(spacing, dtype=float)
        cents1 = np.array([c1["centroid"] for c1, _ in fids]) * sp   # mm
        cents2 = np.array([c2["centroid"] for _, c2 in fids]) * sp
        disps = np.linalg.norm(cents1 - cents2, axis=1)
        if not np.isfinite(disps).all():
            return LesionScaleQC(False, n_fiducials=len(fids), reason="non-finite displacement")
        r_disp = float(np.max(disps))

        # Coverage guard: fiducials must span the brain, else the rotational lever arm is
        # unobserved (central-clustered fiducials under-report rotation) -> cannot certify.
        pd = np.linalg.norm(cents1[:, None, :] - cents1[None, :, :], axis=2)
        span = float(pd.max())
        if span < _COVERAGE_MIN_MM:
            return LesionScaleQC(False, r_disp_mm=r_disp, n_fiducials=len(fids),
                                 coverage_span_mm=span,
                                 reason=f"fiducials centrally clustered (span {span:.1f}<{_COVERAGE_MIN_MM}mm) "
                                        "-> rotation lever arm unobserved; cannot certify")

        cut = _R_DISP_CUT_MM if jitter_floor_mm is None else max(_R_DISP_CUT_MM, jitter_floor_mm + _MARGIN_MM)
        per = [{"vol_tp1_mm3": c1["volume_mm3"], "disp_mm": round(float(d), 3)}
               for (c1, _), d in zip(fids, disps)]
        if r_disp > cut:
            return LesionScaleQC(False, r_disp_mm=r_disp, n_fiducials=len(fids),
                                 coverage_span_mm=span, cut_mm=cut, per_fiducial=per,
                                 reason=f"residual {r_disp:.2f}mm > cut {cut:.2f}mm")
        return LesionScaleQC(True, r_disp_mm=r_disp, n_fiducials=len(fids),
                             coverage_span_mm=span, cut_mm=cut, per_fiducial=per,
                             reason="lesion-scale residual within cut (necessary-not-sufficient)")
    except Exception as e:  # noqa: BLE001 — any failure fails closed
        return LesionScaleQC(False, reason=f"qc error: {e}")
