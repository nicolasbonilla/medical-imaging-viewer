"""Dissemination in space only on a segmentation a clinician has confirmed (PRB-003).

RC-070 (REQ-SAFE-038; HAZ-008, HAZ-005, HAZ-003), RC-071 (REQ-SAFE-039), RC-072 (REQ-SAFE-040).

Evidence (paper A v0.3 healthy-control addendum, branch `research/paper-a-v0.3`, record
`docs/research/records/2026-10-24_paper_a_v03c_controls.json`, key `app_dis`): on 100 public healthy
controls (one site, SibBMS, template-normalised, not expert-read, CC BY-NC-SA 3.0), the device's own
brain-DIS code applied to the raw automatic FLAMeS 5-fold segmentation returned "DIS met (brain)" in
19 of 100 (95 % CI 11.8-28.1 %); 85 of 100 got at least one marked spot (2.6 per scan); 165 of the 263
false spots (63 %) were periventricular.

The rule enforced here, on every path that evaluates or shows DIS (the DIS route, the classify-regions
route, the stored metadata, the AI report, the AI assistant):
- DIS is evaluated only when a radiologist's confirmation is bound to the SHA-256 of the CURRENT stored
  mask — the AI-draft review for a segmentation with AI provenance (RC-047, reused), the clinician
  confirmation (`SegmentationMetadata.clinician_review`, RC-071) for any other segmentation. Region
  labels are part of the mask, so a confirmation also covers the region assignment (HAZ-005).
- Otherwise the result is the explicit state "not evaluated: requires clinician review of the
  segmentation": no met / not met, no region presence, no topography count, nothing a reader could
  turn into a DIS decision.

This module decides; it computes nothing about lesions. `lesion_analysis_service.compute_dis_criteria`
(Class C) is unchanged and is called only after this gate has passed.

@module services.dis_review_gate
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.services.segmentation_service import SegmentationService

EVALUATED = "evaluated"
NOT_EVALUATED = "not_evaluated"

SOURCE_AI_DRAFT = "ai_draft"                  # AI provenance (in-browser FLAMeS draft, RC-047)
SOURCE_AUTOMATIC_TOOL = "automatic_tool"      # server tool output: segmentation_type 'automatic', no provenance
SOURCE_ORIGIN_NOT_RECORDED = "origin_not_recorded"   # drawn here, or a mask uploaded from another program
AUTOMATIC_SOURCES = frozenset({SOURCE_AI_DRAFT, SOURCE_AUTOMATIC_TOOL})

REASON_NOT_CONFIRMED = "segmentation_not_confirmed"
REASON_OUTDATED = "confirmation_outdated"
REASON_NOT_IDENTIFIED = "segmentation_not_identified"
REASON_FAILED = "assessment_failed"

CRITERIA_VERSION = "McDonald 2024 (Montalban et al., Lancet Neurology 2025)"

NOT_EVALUATED_MESSAGE = (
    "Not evaluated: requires clinician review of the segmentation. Dissemination in space is evaluated "
    "only on a segmentation that a radiologist has confirmed, lesion by lesion and region by region, for "
    "this exact saved mask."
)
REASON_DETAIL = {
    REASON_NOT_CONFIRMED: "No radiologist has confirmed this segmentation.",
    REASON_OUTDATED: "The segmentation changed after it was confirmed; the confirmation no longer applies.",
    REASON_NOT_IDENTIFIED: "The assessment did not name a stored segmentation, so it could not be checked.",
    REASON_FAILED: "The assessment could not be computed for the confirmed segmentation.",
}

# RC-072: information for safety wherever an automatic segmentation is shown (paper A, wording A of
# `APP-FEATURE-slice-thickness-reliability.md` §5b — without numbers until the SibBMS licence is
# clarified for a commercial product). The frontend holds the same texts (`disReview.automaticMarkingNotice`).
AUTOMATIC_MARKING_NOTICE: Dict[str, str] = {
    "en": ("Automatic marking also marks spots in most healthy brains, mostly next to the ventricles. "
           "A marked spot is not evidence of multiple sclerosis; every spot needs expert review."),
    "es": ("La marcación automática también marca manchas en la mayoría de los cerebros sanos, sobre todo "
           "junto a los ventrículos. Una mancha marcada no es prueba de esclerosis múltiple; cada mancha "
           "requiere la revisión de un experto."),
    "de": ("Die automatische Markierung markiert auch in den meisten gesunden Gehirnen Stellen, vor allem "
           "neben den Ventrikeln. Eine markierte Stelle ist kein Nachweis einer Multiplen Sklerose; jede "
           "Stelle muss fachärztlich geprüft werden."),
}

# What a stored or forwarded DIS block may carry only when it was evaluated on a confirmed segmentation.
CONCLUSION_KEYS = frozenset({
    "dis_met", "dis_met_brain", "dis_met_full", "dit_waiver_supported", "brain_regions_with_lesions",
    "regions_with_lesions", "total_topographies_involved", "region_details",
})


def review_state(metadata: Any, masks_3d) -> Dict[str, Any]:
    """Whether a clinician's confirmation is bound to the current mask (RC-070), and from which record.

    - AI provenance present: only the AI-draft review counts (RC-047) — a clinician record never
      replaces it;
    - otherwise: only the clinician confirmation (RC-071) counts.
    A confirmation counts only if its `reviewed_mask_sha256` equals the SHA-256 of `masks_3d` now.
    """
    current = SegmentationService.mask_sha256(masks_3d)
    provenance = getattr(metadata, "ai_provenance", None)
    if provenance is not None:
        source = SOURCE_AI_DRAFT
        has_record = provenance.review_status == "confirmed"
        record = provenance
    else:
        automatic = str(getattr(metadata, "segmentation_type", None) or "").strip().lower() == "automatic"
        source = SOURCE_AUTOMATIC_TOOL if automatic else SOURCE_ORIGIN_NOT_RECORDED
        record = getattr(metadata, "clinician_review", None)
        has_record = record is not None
    bound = has_record and getattr(record, "reviewed_mask_sha256", None) == current
    return {
        "confirmed": bool(bound),
        "status": "confirmed" if bound else ("outdated" if has_record else "unconfirmed"),
        "source": source,
        # A reviewer is named only for a confirmation that applies to this mask.
        "reviewed_by": getattr(record, "reviewed_by", None) if bound else None,
        "reviewed_at": getattr(record, "reviewed_at", None) if bound else None,
        "reviewed_mask_sha256": getattr(record, "reviewed_mask_sha256", None) if bound else None,
        "current_mask_sha256": current,
    }


def _public(state: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if state is None:
        return None
    return {k: state[k] for k in ("status", "source", "reviewed_by", "reviewed_at", "reviewed_mask_sha256",
                                  "current_mask_sha256")}


def not_evaluated(segmentation_id: Optional[str], state: Optional[Dict[str, Any]],
                  reason: Optional[str] = None) -> Dict[str, Any]:
    """The explicit 'not evaluated' DIS state: no conclusion, no region presence, no topography count."""
    if reason is None:
        reason = REASON_OUTDATED if state and state["status"] == "outdated" else REASON_NOT_CONFIRMED
    out = {
        "segmentation_id": segmentation_id,
        "evaluation_status": NOT_EVALUATED,
        "not_evaluated_reason": reason,
        "message": NOT_EVALUATED_MESSAGE if reason != REASON_FAILED else (
            "Not evaluated: " + REASON_DETAIL[REASON_FAILED]),
        "reason_detail": REASON_DETAIL[reason],
        "segmentation_review": _public(state),
        "dis_criteria_version": CRITERIA_VERSION,
    }
    if state is not None and state["source"] in AUTOMATIC_SOURCES:
        out["information_for_safety"] = AUTOMATIC_MARKING_NOTICE["en"]
    return out


def evaluated(result: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    """A DIS result computed on a confirmed segmentation, marked as such with the confirmation it rests on."""
    return {**result, "evaluation_status": EVALUATED, "segmentation_review": _public(state)}


def is_evaluated(block: Any) -> bool:
    """True only for a block this gate marked as evaluated (anything else is treated as not evaluated)."""
    return isinstance(block, dict) and block.get("evaluation_status") == EVALUATED


def without_stored_dis(metadata: Any) -> Any:
    """A copy of segmentation metadata for an API response, without the stored DIS block (RC-070).

    Before PRB-003 the classify-regions route stored a DIS conclusion for any mask and the viewer showed
    it straight from the metadata. The DIS state is now served only by the gated DIS route; the stored
    record itself is not rewritten by a read."""
    data = getattr(metadata, "analysis_data", None)
    if not isinstance(data, dict) or "dis_assessment" not in data:
        return metadata
    return metadata.model_copy(update={"analysis_data": {k: v for k, v in data.items() if k != "dis_assessment"}})
