"""Dissemination in space only on a classified segmentation a radiologist has confirmed (PRB-003).

RC-070 (REQ-SAFE-038; HAZ-008, HAZ-005, HAZ-003), RC-071 (REQ-SAFE-039), RC-072 (REQ-SAFE-040).

Evidence (paper A v0.3 healthy-control addendum, branch `research/paper-a-v0.3`, record
`docs/research/records/2026-10-24_paper_a_v03c_controls.json`, key `app_dis`): on 100 public healthy
controls (one site, SibBMS, template-normalised, not expert-read, CC BY-NC-SA 3.0), the device's own
brain-DIS code applied to the raw automatic FLAMeS 5-fold segmentation returned "DIS met (brain)" in
19 of 100 (95 % CI 11.8-28.1 %); 85 of 100 got at least one marked spot (2.6 per scan); 165 of the 263
false spots (63 %) were periventricular.

`compute_dis_criteria` (Class C) reads label ids 1 / 2 / 3 as periventricular / juxtacortical /
infratentorial. Its result means something only for a mask whose labels ARE those regions. The rule
enforced here, on every path that evaluates or shows DIS (the DIS route, classify-regions, the stored
metadata, the AI report, the AI assistant):
1. the regions are classified: the label scheme is MAGNIMS (ids 1-4 named periventricular, juxtacortical,
   infratentorial, deep white matter; no other id or mask value outside the scheme), and the region
   classification was run on exactly these lesions — the classified lesion footprint (SHA-256 of
   `mask > 0`) recorded by classify-regions equals the current one. A radiologist may correct a region
   label afterwards (the footprint is unchanged and the confirmation covers the correction); adding or
   removing lesion voxels needs a new classification (review of PR #68, blocker 1);
2. an AI draft also has its own review (RC-047) for the current mask;
3. a radiologist's DIS confirmation (`clinician_review`, RC-071) is bound to the SHA-256 of the current
   mask AND of the label scheme (review of PR #68, blocker 1 and finding 6).
Otherwise the result is the explicit state "not evaluated: requires clinician review of the segmentation",
with its reason: no met / not met, no region presence, no topography count.

This module decides; it computes nothing about lesions.

@module services.dis_review_gate
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, Iterable, Optional, Tuple

import numpy as np

from app.services.lesion_analysis_service import MAGNIMS_REGIONS
from app.services.segmentation_service import SegmentationService

EVALUATED = "evaluated"
NOT_EVALUATED = "not_evaluated"

SOURCE_AI_DRAFT = "ai_draft"                  # AI provenance (in-browser FLAMeS draft, RC-047)
SOURCE_AUTOMATIC_TOOL = "automatic_tool"      # server tool output: segmentation_type 'automatic', no provenance
SOURCE_ORIGIN_NOT_RECORDED = "origin_not_recorded"   # drawn here, or a mask uploaded from another program

REASON_REGIONS = "regions_not_classified"
REASON_AI_REVIEW = "ai_review_missing"
REASON_NOT_CONFIRMED = "segmentation_not_confirmed"
REASON_OUTDATED = "confirmation_outdated"
REASON_NOT_IDENTIFIED = "segmentation_not_identified"
REASON_FAILED = "assessment_failed"

CRITERIA_VERSION = "McDonald 2024 (Montalban et al., Lancet Neurology 2025)"

# MAGNIMS region ids the DIS rule reads (1-4 must all be defined with these names; 5 and 6 are optional).
MAGNIMS_REQUIRED_IDS = (1, 2, 3, 4)

NOT_EVALUATED_MESSAGE = (
    "Not evaluated: requires clinician review of the segmentation. Dissemination in space is evaluated "
    "only on a segmentation whose lesions went through the MAGNIMS region classification and that a "
    "radiologist has confirmed, lesion by lesion and region by region, for this exact saved mask."
)
REASON_DETAIL = {
    REASON_REGIONS: ("The lesions have not been assigned MAGNIMS regions by the region classification (or "
                     "lesions changed since): run the region classification, check every region, then confirm."),
    REASON_AI_REVIEW: "This AI draft's own review has not been confirmed for the current mask.",
    REASON_NOT_CONFIRMED: "No radiologist has confirmed the lesions and regions of this segmentation.",
    REASON_OUTDATED: ("The mask or its labels changed after the confirmation; the confirmation no longer "
                      "applies."),
    REASON_NOT_IDENTIFIED: "The request did not name its stored segmentation, so DIS could not be checked.",
    REASON_FAILED: "The assessment could not be computed for the confirmed segmentation.",
}

REGIONS_NOT_CONFIRMED_NOTE = "Regions not confirmed by a radiologist; not a DIS assessment."

# RC-072: information for safety wherever an automatic LESION segmentation is shown (paper A, wording A of
# `APP-FEATURE-slice-thickness-reliability.md` §5b — without numbers until the SibBMS licence is clarified;
# "most" itself rests on that CC BY-NC data: owner decision). Not shown for structure parcellations
# (SynthSeg, mindGlide structures). The frontend holds the same texts (`disReview.automaticMarkingNotice`).
AUTOMATIC_MARKING_NOTICE: Dict[str, str] = {
    "en": ("Automatic lesion marking also marks spots in most healthy brains, mostly next to the ventricles. "
           "A marked spot is not evidence of multiple sclerosis; every spot needs expert review."),
    "es": ("La marcación automática de lesiones también marca manchas en la mayoría de los cerebros sanos, "
           "sobre todo junto a los ventrículos. Una mancha marcada no es prueba de esclerosis múltiple; cada "
           "mancha requiere la revisión de un experto."),
    "de": ("Die automatische Läsionsmarkierung markiert auch in den meisten gesunden Gehirnen Stellen, vor "
           "allem neben den Ventrikeln. Eine markierte Stelle ist kein Nachweis einer Multiplen Sklerose; jede "
           "Stelle muss fachärztlich geprüft werden."),
}

# The sentence that replaces a DIS statement written by the report model while DIS was not evaluated.
NOT_EVALUATED_LINE: Dict[str, str] = {
    "en": "Dissemination in space: not evaluated (requires clinician review of the segmentation).",
    "es": "Diseminación en el espacio: no evaluada (requiere la revisión clínica de la segmentación).",
    "de": "Räumliche Dissemination: nicht beurteilt (erfordert die ärztliche Prüfung der Segmentierung).",
}

# What a stored or forwarded DIS block may carry only when it was evaluated on a confirmed segmentation.
CONCLUSION_KEYS = frozenset({
    "dis_met", "dis_met_brain", "dis_met_full", "dit_waiver_supported", "brain_regions_with_lesions",
    "regions_with_lesions", "total_topographies_involved", "region_details",
})


# ─────────────────────────────────────────────────────────────────────────────────────────── digests
def footprint_sha256(masks_3d) -> str:
    """SHA-256 of the lesion footprint (`mask > 0`, uint8, C order): the lesions, whatever their labels."""
    return SegmentationService.mask_sha256((np.asarray(masks_3d) > 0).astype(np.uint8))


def _label_pairs(labels: Iterable[Any]) -> Dict[int, str]:
    out: Dict[int, str] = {}
    for lbl in labels or []:
        lid = getattr(lbl, "id", None) if not isinstance(lbl, dict) else lbl.get("id")
        name = getattr(lbl, "name", None) if not isinstance(lbl, dict) else lbl.get("name")
        if isinstance(lid, int) and not isinstance(lid, bool) and lid > 0:
            out[lid] = str(name)
    return out


def labels_sha256(labels: Iterable[Any]) -> str:
    """SHA-256 of the label scheme (id -> name, background excluded), independent of colours and order."""
    canonical = json.dumps(sorted(_label_pairs(labels).items()), separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def labels_are_magnims(labels: Iterable[Any]) -> bool:
    """Ids 1-4 named exactly as the MAGNIMS regions the DIS rule reads; every other id a MAGNIMS label too."""
    pairs = _label_pairs(labels)
    if any(pairs.get(i) != MAGNIMS_REGIONS[i] for i in MAGNIMS_REQUIRED_IDS):
        return False
    return all(MAGNIMS_REGIONS.get(i) == name for i, name in pairs.items())


def is_lesion_detection_source(validation_source: Optional[str]) -> bool:
    """FLAMeS (worker or browser), LST-AI and the mindGlide LESION output — not structure parcellations."""
    vs = str(validation_source or "").strip().lower()
    return vs.startswith("flames") or vs.startswith("lst-ai") or vs == "mindglide-v1.0"


# ─────────────────────────────────────────────────────────────────────────────────────────── the gate
def regions_state(metadata: Any, masks_3d) -> Dict[str, Any]:
    """Are the mask's labels MAGNIMS regions assigned by the region classification to exactly these lesions?"""
    labels = getattr(metadata, "labels", None) or []
    magnims = labels_are_magnims(labels)
    allowed = {0, *_label_pairs(labels)}
    in_scheme = magnims and set(int(v) for v in np.unique(masks_3d)) <= allowed
    record = ((getattr(metadata, "analysis_data", None) or {}).get("classification") or {})
    if not isinstance(record, dict):
        record = {}
    classified = bool(in_scheme and record.get("classified_lesion_footprint_sha256") == footprint_sha256(masks_3d))
    edited = None
    if classified and record.get("classified_mask_sha256"):
        edited = record["classified_mask_sha256"] != SegmentationService.mask_sha256(masks_3d)
    return {"classified": classified, "label_scheme": "magnims" if magnims else "other",
            "edited_after_classification": edited, "method": record.get("method") if classified else None}


def review_state(metadata: Any, masks_3d) -> Dict[str, Any]:
    """Whether DIS may be evaluated on this mask (RC-070), and why not.

    Order of the reasons: regions not classified → an AI draft's own review missing → no confirmation →
    a confirmation given for another mask or label scheme."""
    current = SegmentationService.mask_sha256(masks_3d)
    labels_digest = labels_sha256(getattr(metadata, "labels", None) or [])
    regions = regions_state(metadata, masks_3d)
    provenance = getattr(metadata, "ai_provenance", None)
    automatic = str(getattr(metadata, "segmentation_type", None) or "").strip().lower() == "automatic"
    if provenance is not None:
        source = SOURCE_AI_DRAFT
    else:
        source = SOURCE_AUTOMATIC_TOOL if automatic else SOURCE_ORIGIN_NOT_RECORDED
    lesion_detection = source == SOURCE_AI_DRAFT or (
        source == SOURCE_AUTOMATIC_TOOL and is_lesion_detection_source(getattr(metadata, "validation_source", None)))
    ai_review_ok = provenance is None or (
        provenance.review_status == "confirmed" and provenance.reviewed_mask_sha256 == current)
    record = getattr(metadata, "clinician_review", None)
    has_record = record is not None
    bound = (has_record and getattr(record, "reviewed_mask_sha256", None) == current
             and getattr(record, "reviewed_labels_sha256", None) == labels_digest)
    confirmed = bool(regions["classified"] and ai_review_ok and bound)
    if confirmed:
        reason = None
    elif not regions["classified"]:
        reason = REASON_REGIONS
    elif not ai_review_ok:
        reason = REASON_AI_REVIEW
    elif has_record and not bound:
        reason = REASON_OUTDATED
    else:
        reason = REASON_NOT_CONFIRMED
    return {
        "confirmed": confirmed,
        "status": "confirmed" if confirmed else ("outdated" if has_record and not bound else "unconfirmed"),
        "reason": reason,
        "source": source,
        "lesion_detection": lesion_detection,
        "regions": regions,
        # A reviewer is named only for a confirmation that applies to this mask and label scheme.
        "reviewed_by": getattr(record, "reviewed_by", None) if confirmed else None,
        "reviewed_at": getattr(record, "reviewed_at", None) if confirmed else None,
        "reviewed_mask_sha256": getattr(record, "reviewed_mask_sha256", None) if confirmed else None,
        "current_mask_sha256": current,
        "current_labels_sha256": labels_digest,
    }


def _public(state: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if state is None:
        return None
    return {k: state[k] for k in ("status", "source", "reviewed_by", "reviewed_at", "reviewed_mask_sha256",
                                  "current_mask_sha256", "current_labels_sha256")}


def not_evaluated(segmentation_id: Optional[str], state: Optional[Dict[str, Any]],
                  reason: Optional[str] = None) -> Dict[str, Any]:
    """The explicit 'not evaluated' DIS state: no conclusion, no region presence, no topography count."""
    if reason is None:
        reason = (state or {}).get("reason") or REASON_NOT_CONFIRMED
    out = {
        "segmentation_id": segmentation_id,
        "evaluation_status": NOT_EVALUATED,
        "not_evaluated_reason": reason,
        "message": NOT_EVALUATED_MESSAGE if reason != REASON_FAILED else (
            "Not evaluated: " + REASON_DETAIL[REASON_FAILED]),
        "reason_detail": REASON_DETAIL[reason],
        "segmentation_review": _public(state),
        "regions": (state or {}).get("regions"),
        "dis_criteria_version": CRITERIA_VERSION,
    }
    if state is not None and state.get("lesion_detection"):
        out["information_for_safety"] = AUTOMATIC_MARKING_NOTICE["en"]
    return out


def evaluated(result: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    """A DIS result computed on a confirmed segmentation, marked as such with the confirmation it rests on."""
    return {**result, "evaluation_status": EVALUATED, "segmentation_review": _public(state),
            "regions": state["regions"]}


def is_evaluated(block: Any) -> bool:
    """True only for a block this gate marked as evaluated (anything else is treated as not evaluated)."""
    return isinstance(block, dict) and block.get("evaluation_status") == EVALUATED


def region_status(state: Dict[str, Any]) -> Dict[str, Any]:
    """Attached to lesion measurements: whether their regions rest on a confirmed, classified segmentation."""
    if state["confirmed"]:
        return {"confirmed": True, "note": None}
    return {"confirmed": False, "note": REGIONS_NOT_CONFIRMED_NOTE, "reason": state["reason"]}


def without_stored_dis(metadata: Any) -> Any:
    """A copy of segmentation metadata for an API response, without the stored DIS block (RC-070).

    Before PRB-003 the classify-regions route stored a DIS conclusion for any mask and the viewer showed
    it straight from the metadata. The DIS state is now served only by the gated DIS route; the stored
    record itself is not rewritten by a read."""
    data = getattr(metadata, "analysis_data", None)
    if not isinstance(data, dict) or "dis_assessment" not in data:
        return metadata
    return metadata.model_copy(update={"analysis_data": {k: v for k, v in data.items() if k != "dis_assessment"}})


def without_region_breakdown(lesion_analysis: Any) -> Any:
    """Lesion measurements without any region (review of PR #68, finding 3): for a report on a segmentation
    whose regions no radiologist confirmed, counts and volumes are kept, regions are not passed on."""
    if not isinstance(lesion_analysis, dict):
        return lesion_analysis
    out = {k: v for k, v in lesion_analysis.items() if k not in ("regions", "region_summary", "unique_labels")}
    if isinstance(out.get("lesions"), list):
        out["lesions"] = [
            {**{k: v for k, v in les.items() if k not in ("label_name", "label", "label_id")},
             "region": "not confirmed"} if isinstance(les, dict) else les
            for les in out["lesions"]
        ]
    out["region_status"] = {"confirmed": False, "note": REGIONS_NOT_CONFIRMED_NOTE}
    return out


# ───────────────────────────────────────────────── the report model's text (review of PR #68, finding 4)
_DIS_STATEMENT = re.compile(
    r"dissemination\s+in\s+space|typical\s+(?:ms\s+)?regions|diseminaci[oó]n\s+en\s+(?:el\s+)?espacio|"
    r"regiones\s+t[ií]picas|r[äa]umlich\w*\s+dissemination|dissemination\s+im\s+raum|typischen\s+(?:ms-)?regionen",
    re.IGNORECASE)
_DIS_ACRONYM = re.compile(r"\bDIS\b")
_ALLOWED = re.compile(r"not\s+evaluated|no\s+evaluada|nicht\s+beurteilt", re.IGNORECASE)


def scrub_unevaluated_dis(content: str, language: str) -> Tuple[str, int]:
    """Replace every line of a draft that states something on DIS although DIS was not evaluated.

    Line-based and conservative: a line naming dissemination in space, DIS or "typical MS regions" (en/es/de)
    is replaced by the not-evaluated sentence unless it already says "not evaluated"; headings are kept.
    Returns the new text and the number of lines replaced."""
    line = NOT_EVALUATED_LINE.get(language, NOT_EVALUATED_LINE["en"])
    out, replaced = [], 0
    for raw in (content or "").split("\n"):
        stripped = raw.strip()
        states = (_DIS_STATEMENT.search(raw) or _DIS_ACRONYM.search(raw)) and not _ALLOWED.search(raw)
        if states and not stripped.startswith("#"):
            replaced += 1
            if not out or out[-1] != line:
                out.append(line)
            continue
        out.append(raw)
    return "\n".join(out), replaced
