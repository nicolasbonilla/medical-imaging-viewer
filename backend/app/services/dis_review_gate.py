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
   `mask > 0`) and each lesion's region recorded by classify-regions match the current lesions (review of
   PR #68, blocker 1). Adding or removing lesion voxels needs a new classification;
1b. every lesion (18-connected component, the classifier's own connectivity, RC-030) carries exactly ONE
   label, and it is a region 1-4: a lesion split between two regions, or relabelled Active (Gd+) / Black
   hole (T1), has no region the DIS rule may read (second review of PR #68, N1);
1c. a lesion whose region differs from the classifier's is a correction by hand: it is listed, and the
   radiologist acknowledges the corrections in the confirmation (bound to their digest) (N1);
2. an AI draft also has its own review (RC-047) for the current mask;
3. a radiologist's DIS confirmation (`clinician_review`, RC-071) is bound to the SHA-256 of the current
   mask, of the label scheme and of the region corrections (review of PR #68, blocker 1, finding 6, N1).
Otherwise the result is the explicit state "not evaluated: requires clinician review of the segmentation",
with its reason: no met / not met, no region presence, no topography count.

This module decides; it computes nothing about lesions.

@module services.dis_review_gate
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np

from app.services.lesion_analysis_service import MAGNIMS_REGIONS
from app.services.segmentation_service import SegmentationService

EVALUATED = "evaluated"
NOT_EVALUATED = "not_evaluated"

SOURCE_AI_DRAFT = "ai_draft"                  # AI provenance (in-browser FLAMeS draft, RC-047)
SOURCE_AUTOMATIC_TOOL = "automatic_tool"      # server tool output: segmentation_type 'automatic', no provenance
SOURCE_ORIGIN_NOT_RECORDED = "origin_not_recorded"   # drawn here, or a mask uploaded from another program

REASON_REGIONS = "regions_not_classified"
REASON_LESION_LABELS = "lesion_labels_invalid"
REASON_AI_REVIEW = "ai_review_missing"
REASON_NOT_CONFIRMED = "segmentation_not_confirmed"
REASON_OUTDATED = "confirmation_outdated"
REASON_NOT_IDENTIFIED = "segmentation_not_identified"
REASON_FAILED = "assessment_failed"

CRITERIA_VERSION = "McDonald 2024 (Montalban et al., Lancet Neurology 2025)"

# MAGNIMS region ids the DIS rule reads (1-4 must all be defined with these names; 5 and 6 are optional).
MAGNIMS_REQUIRED_IDS = (1, 2, 3, 4)
# The labels a lesion may carry in a mask whose DIS is evaluated: one region each (N1). 5 Active (Gd+) and
# 6 Black Hole (T1) are lesion types, not regions.
DIS_REGION_IDS = frozenset(MAGNIMS_REQUIRED_IDS)
# Lesions listed in a response or a confirmation record (counts and digests always cover every lesion).
LESION_LIST_CAP = 100
# DIS confirmation history kept on the segmentation (every event is also in the server log) (N5).
REVIEW_HISTORY_CAP = 50
# Roles that see who confirmed (names, ids, history); every other role sees the role and the time only (N5).
REVIEWER_IDENTITY_ROLES = frozenset({"radiologist", "admin"})

NOT_EVALUATED_MESSAGE = (
    "Not evaluated: requires clinician review of the segmentation. Dissemination in space is evaluated "
    "only on a segmentation whose lesions went through the MAGNIMS region classification and that a "
    "radiologist has confirmed, lesion by lesion and region by region, for this exact saved mask."
)
REASON_DETAIL = {
    REASON_REGIONS: ("The lesions have not been assigned MAGNIMS regions by the region classification (or "
                     "lesions changed since): run the region classification, check every region, then confirm."),
    REASON_LESION_LABELS: ("A lesion carries no MAGNIMS region or more than one: every connected lesion must carry "
                           "exactly one of periventricular, juxtacortical, infratentorial or deep white matter "
                           "(Active (Gd+) and Black Hole (T1) are not regions). Correct the lesions listed, or run "
                           "the region classification again."),
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


# ──────────────────────────────────────────────────────────── lesions and their regions (second review, N1)
def _lesions(masks_3d) -> List[Dict[str, Any]]:
    """The 18-connected lesions of the footprint (RC-030: the connectivity the region classifier uses), in raster
    order of their first voxel: component id, first flat index, voxel count and the labels the lesion carries."""
    from app.services.lesion_metrics import label_lesions

    mask = np.ascontiguousarray(masks_3d, dtype=np.uint8)
    components, count = label_lesions(mask > 0)
    if count == 0:
        return []
    flat = np.asarray(components).ravel()
    where = np.flatnonzero(flat)
    ids = flat[where]
    order = np.argsort(ids, kind="stable")              # stable: voxels of a lesion stay in raster order
    ids, where, values = ids[order], where[order], mask.ravel()[where][order]
    starts = np.r_[0, np.flatnonzero(np.diff(ids)) + 1]
    stops = np.r_[starts[1:], ids.size]
    low = np.minimum.reduceat(values, starts)
    high = np.maximum.reduceat(values, starts)
    out = []
    for a, b, lo, hi in zip(starts, stops, low, high):
        labels = [int(lo)] if lo == hi else [int(v) for v in np.unique(values[a:b])]
        out.append({"component": int(ids[a]), "first": int(where[a]), "voxels": int(b - a), "labels": labels})
    out.sort(key=lambda les: les["first"])
    return out


def _table_entries(masks_3d, voxel_volume_mm3: float) -> List[Dict[str, Any]]:
    """The lesion table's entries, numbered as the lesion table numbers them (third review of PR #68, m-1).

    Same construction as `lesion_analysis_service.analyze_lesions` (Class C, not modified): the 18-connected
    components of each label, label by label (ids ascending, components in raster order), centroids from the same
    `center_of_mass` call, then sorted largest first (stable) and numbered 1..n. A component below the lesion-size
    floor is left out of the table: here it is kept, unnumbered, as a "small component". `slice` is the slice the
    viewer opens for a table row (`Math.round` of the centroid z rounded to 0.1, 0-based)."""
    from scipy.ndimage import center_of_mass
    from app.services.lesion_metrics import label_lesions, meets_min_volume

    mask = np.ascontiguousarray(masks_3d, dtype=np.uint8)
    entries: List[Dict[str, Any]] = []
    for label in (int(v) for v in np.unique(mask) if v > 0):
        binary = (mask == label).astype(np.uint8)
        components, count = label_lesions(binary)
        if count == 0:
            continue
        ids = list(range(1, count + 1))
        centroids = center_of_mass(binary, components, ids)
        flat = np.asarray(components).ravel()
        voxels = np.bincount(flat, minlength=count + 1)
        where = np.flatnonzero(flat)
        firsts, positions = np.unique(flat[where], return_index=True)
        first_of = dict(zip(firsts.tolist(), where[positions].tolist()))
        for comp, centroid in zip(ids, centroids):
            entries.append({"label": label, "voxels": int(voxels[comp]), "first": int(first_of[comp]),
                            "slice": int(math.floor(round(float(centroid[0]), 1) + 0.5))})
    entries.sort(key=lambda e: -e["voxels"])            # stable, as the table's sort by volume
    number = 0
    for e in entries:
        e["small_component"] = not meets_min_volume(e["voxels"], voxel_volume_mm3)
        if not e["small_component"]:
            number += 1
        e["lesion"] = None if e["small_component"] else number
    return entries


def classification_record(classified_mask, voxel_spacing) -> Dict[str, Any]:
    """What classify-regions records about the lesions it classified (review of PR #68, blocker 1 and N1): the
    lesion footprint, the classified mask and, per lesion, its first voxel, voxel count and region; and the voxel
    volume (third review, m-1), so that lesions are named as the lesion table names them."""
    return {
        "classified_lesion_footprint_sha256": footprint_sha256(classified_mask),
        "classified_mask_sha256": SegmentationService.mask_sha256(classified_mask),
        "classified_lesion_regions": [
            [les["first"], les["voxels"], les["labels"][0] if len(les["labels"]) == 1 else 0]
            for les in _lesions(classified_mask)],
        "lesion_connectivity": 18,
        "voxel_volume_mm3": float(np.prod(voxel_spacing)),
    }


def _first_voxel(first: int, shape) -> List[int]:
    return [int(v) for v in np.unravel_index(first, tuple(shape))]


def _part(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {"lesion": entry["lesion"], "small_component": entry["small_component"], "label": entry["label"],
            "label_name": MAGNIMS_REGIONS.get(entry["label"], f"label {entry['label']}"),
            "voxels": entry["voxels"], "slice": entry["slice"]}


def corrections_sha256(corrections: List[Dict[str, Any]]) -> str:
    """Digest of a set of region corrections (lesion first voxel, classified region, current region)."""
    canonical = json.dumps([[c["first_voxel"], c["classified_region"], c["current_region"]] for c in corrections],
                           separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


NO_CORRECTIONS_SHA256 = corrections_sha256([])


# ─────────────────────────────────────────────────────────────────────────────────────────── the gate
def regions_state(metadata: Any, masks_3d) -> Dict[str, Any]:
    """Are the mask's labels MAGNIMS regions assigned by the region classification to exactly these lesions, one
    region per lesion — and which lesions did a person relabel since (N1)?"""
    labels = getattr(metadata, "labels", None) or []
    magnims = labels_are_magnims(labels)
    allowed = {0, *_label_pairs(labels)}
    in_scheme = magnims and set(int(v) for v in np.unique(masks_3d)) <= allowed
    record = ((getattr(metadata, "analysis_data", None) or {}).get("classification") or {})
    if not isinstance(record, dict):
        record = {}
    out: Dict[str, Any] = {
        "classified": False, "label_scheme": "magnims" if magnims else "other", "method": None,
        "edited_after_classification": None, "lesion_count": None, "lesions_valid": None,
        "invalid_lesions": [], "invalid_lesion_count": 0,
        "corrections": [], "correction_count": 0, "corrections_sha256": None, "listed_limit": LESION_LIST_CAP,
    }
    recorded = record.get("classified_lesion_regions")
    voxel_volume = record.get("voxel_volume_mm3")
    if not (isinstance(voxel_volume, (int, float)) and not isinstance(voxel_volume, bool) and voxel_volume > 0):
        return out                                     # m-1: a record without it cannot name lesions as the table
    if not (in_scheme and isinstance(recorded, list)
            and record.get("classified_lesion_footprint_sha256") == footprint_sha256(masks_3d)):
        return out
    by_first: Dict[int, Tuple[int, int]] = {}
    for item in recorded:
        if isinstance(item, (list, tuple)) and len(item) == 3 and all(isinstance(v, int) for v in item):
            by_first[item[0]] = (item[1], item[2])
    lesions = _lesions(masks_3d)
    if len(by_first) != len(lesions) or any(by_first.get(les["first"], (None,))[0] != les["voxels"]
                                            for les in lesions):
        return out                                     # a record that does not describe these lesions
    shape = np.shape(masks_3d)
    # Third review of PR #68, m-1: every list names a lesion as the lesion table does (number, slice), its parts
    # in table order; a component below the lesion-size floor is a "small component".
    footprint = None
    parts_of: Dict[int, List[Dict[str, Any]]] = {}
    if lesions:
        from app.services.lesion_metrics import label_lesions
        footprint = np.asarray(label_lesions(np.asarray(masks_3d) > 0)[0]).ravel()
        for entry in _table_entries(masks_3d, float(voxel_volume)):
            parts_of.setdefault(int(footprint[entry["first"]]), []).append(entry)
    invalid, corrections = [], []
    for les in lesions:
        classified_region = by_first[les["first"]][1]
        parts = parts_of[les["component"]]
        head = parts[0]                                # its largest part, as the table orders them
        where = {"lesion": head["lesion"], "small_component": head["small_component"], "slice": head["slice"],
                 "first_voxel": _first_voxel(les["first"], shape), "voxels": les["voxels"]}
        if len(les["labels"]) != 1 or les["labels"][0] not in DIS_REGION_IDS:
            invalid.append({**where, "labels": les["labels"],
                            "label_names": [MAGNIMS_REGIONS.get(v, f"label {v}") for v in les["labels"]],
                            "parts": [_part(e) for e in parts]})
        elif les["labels"][0] != classified_region:
            corrections.append({**where, "classified_region": classified_region,
                                "classified_region_name": MAGNIMS_REGIONS.get(classified_region, "none"),
                                "current_region": les["labels"][0],
                                "current_region_name": MAGNIMS_REGIONS[les["labels"][0]]})
    edited = None
    if record.get("classified_mask_sha256"):
        edited = record["classified_mask_sha256"] != SegmentationService.mask_sha256(masks_3d)
    out.update({
        "classified": True, "method": record.get("method"), "edited_after_classification": edited,
        "lesion_count": len(lesions), "lesions_valid": not invalid,
        "invalid_lesions": invalid[:LESION_LIST_CAP], "invalid_lesion_count": len(invalid),
        "corrections": corrections[:LESION_LIST_CAP], "correction_count": len(corrections),
        "corrections_sha256": corrections_sha256(corrections),
    })
    return out


def review_state(metadata: Any, masks_3d) -> Dict[str, Any]:
    """Whether DIS may be evaluated on this mask (RC-070), and why not.

    Order of the reasons: regions not classified → a lesion without exactly one region → an AI draft's own
    review missing → no confirmation → a confirmation given for another mask, label scheme or set of region
    corrections."""
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
    acknowledged = getattr(record, "reviewed_region_corrections_sha256", None) or NO_CORRECTIONS_SHA256
    bound = (has_record and getattr(record, "reviewed_mask_sha256", None) == current
             and getattr(record, "reviewed_labels_sha256", None) == labels_digest
             and acknowledged == regions["corrections_sha256"])
    regions_ok = bool(regions["classified"] and regions["lesions_valid"])
    confirmed = bool(regions_ok and ai_review_ok and bound)
    if confirmed:
        reason = None
    elif not regions["classified"]:
        reason = REASON_REGIONS
    elif not regions["lesions_valid"]:
        reason = REASON_LESION_LABELS
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
        "reviewed_by_role": (getattr(record, "reviewed_by_role", None) or "radiologist") if confirmed else None,
        "reviewed_at": getattr(record, "reviewed_at", None) if confirmed else None,
        "reviewed_mask_sha256": getattr(record, "reviewed_mask_sha256", None) if confirmed else None,
        "current_mask_sha256": current,
        "current_labels_sha256": labels_digest,
    }


def _public(state: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if state is None:
        return None
    return {k: state[k] for k in ("status", "source", "reviewed_by", "reviewed_by_role", "reviewed_at",
                                  "reviewed_mask_sha256", "current_mask_sha256", "current_labels_sha256")}


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


# ─────────────────────────────────────────────── who confirmed: radiologists and administrators only (N5)
def sees_reviewer_identity(user: Any) -> bool:
    """Radiologists and administrators see who confirmed and the history; other roles the role and the time."""
    role = getattr(user, "role", None)
    return str(getattr(role, "value", role) or "").lower() in REVIEWER_IDENTITY_ROLES


def capped_history(events: Iterable[Any]) -> List[Any]:
    """The most recent REVIEW_HISTORY_CAP events (every event is also in the server log)."""
    events = list(events or [])
    return events[-REVIEW_HISTORY_CAP:]


def without_reviewer_identity(block: Any) -> Any:
    """A DIS block whose confirmation names the role and the time, never the person (N5): for roles other than
    radiologist and administrator, for the AI assistant and for the report model."""
    if not isinstance(block, dict) or not isinstance(block.get("segmentation_review"), dict):
        return block
    review = {k: v for k, v in block["segmentation_review"].items() if k not in ("reviewed_by", "reviewed_by_id")}
    if block["segmentation_review"].get("reviewed_by") and not review.get("reviewed_by_role"):
        review["reviewed_by_role"] = "radiologist"
    return {**block, "segmentation_review": {**review, "reviewed_by": None}}


def dis_for_viewer(block: Any, user: Any) -> Any:
    return block if sees_reviewer_identity(user) else without_reviewer_identity(block)


def metadata_for_viewer(metadata: Any, user: Any) -> Tuple[Any, Optional[int]]:
    """(metadata, history count): for a role other than radiologist and administrator, the confirmation without
    the confirmer's name and id, and no history — its length only (N5)."""
    if metadata is None or sees_reviewer_identity(user):
        return metadata, None
    history = list(getattr(metadata, "clinician_review_history", None) or [])
    review = getattr(metadata, "clinician_review", None)
    update: Dict[str, Any] = {"clinician_review_history": []}
    if review is not None:
        update["clinician_review"] = review.model_copy(update={
            "reviewed_by": None, "reviewed_by_id": None,
            "reviewed_by_role": getattr(review, "reviewed_by_role", None) or "radiologist"})
    return metadata.model_copy(update=update), len(history)


# ─────────────────────────────── the report model's text (review of PR #68, finding 4; second review, N3)
# The main controls are the earlier layers: without an evaluated DIS no region reaches the model, the system
# prompt carries the not-evaluated safety rule, and no template asks for a DIS or per-region section. This output
# check is a BACKSTOP for the common wordings in en/es/de; it cannot recognise every paraphrase.
_DIS_TERMS = re.compile("|".join([
    r"\bdissem\w*\s+(?:\w+\s+){0,3}in\s+(?:the\s+)?space\b",
    r"\bspatial(?:ly)?\s+(?:dissem\w*|distribution|distributed|spread|criteri\w*)",
    r"\bd\.?i\.?s\b",
    r"\bmcdonald\b",
    r"\btopograph\w*",
    r"\b(?:typical|characteristic)\s+(?:ms\s+|multiple\s+sclerosis\s+)?(?:regions?|locations?|sites?|areas?)\b",
    r"\bdiseminad?\w*\s+(?:\w+\s+){0,3}(?:en\s+(?:el\s+)?)?espacio\b",
    r"\b(?:diseminacion|distribucion)\s+espacial",
    r"\b(?:regiones|localizaciones|ubicaciones|areas|zonas)\s+(?:tipicas|caracteristicas)",
    r"\b(?:raumlich|ortlich)\w*\s+(?:dissemin\w*|streuung|ausbreitung|verteilung|aussaat)",
    r"\bdissemination\s+im\s+raum",
    r"\b(?:typisch|charakteristisch)\w*\s+(?:ms\s+)?(?:regionen|lokalisationen|bereiche|areale)",
]))
_REGION_COUNT = re.compile(r"\b[1-5]\s*(?:/|of|out\s+of|de(?:\s+(?:las|los))?|von|aus)\s*[2-5]\b")
_REGION_NOUN = re.compile(r"\b(?:regions?|locations?|topograph\w*|sites?|areas?|regiones|localizaciones|"
                          r"ubicaciones|zonas|regionen|lokalisationen|bereiche|areale)\b")
_DIS_REGIONS = {
    "periventricular": re.compile(r"\bperiventri\w*"),
    "juxtacortical": re.compile(r"\b(?:juxta|yuxta|intra)\s?(?:cortic|kortik)\w*"),
    "infratentorial": re.compile(r"\binfratentori\w*"),
    "spinal cord": re.compile(r"\bspinal\s+cord|\bmedula\s+espinal|\bruckenmark\w*"),
}
_PRESENCE = re.compile(r"\d|[✓✔☑✗✘]|\b(?:present|absent|involved|affected|met|fulfilled|presente|ausente|"
                       r"afectad\w*|cumpl\w*|vorhanden|betroffen|erfullt)\b")
_NOT_EVALUATED_ONLY = re.compile(r"^(?:dissemination in space|dis|diseminacion en el espacio|"
                                 r"raumliche dissemination)\s*[:\-]?\s*(?:not evaluated|no evaluada|nicht beurteilt)$")
_LIST_PREFIX = re.compile(r"^(\s*(?:>\s*)*(?:[-*+]\s+|\d+[.)]\s+)?)")
_LIST_ITEM = re.compile(r"^\s*(?:>\s*)*(?:[-*+]|\d+[.)])\s+")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{2,}")
_ABBREVIATIONS = {"e.g", "i.e", "approx", "vs", "dr", "ca", "z.b", "bzw", "etc", "fig", "nr", "p.ej", "aprox",
                  "u.a", "d.h", "ggf", "inkl", "max", "min"}


def _norm(text: str) -> str:
    """Lower case, accents removed, markup removed, hyphens and line breaks as spaces (matching only)."""
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("\u00ad", "").replace("≥", ">=").replace("≤", "<=")
    t = re.sub(r"(\w)-[ \t]*\n\s*(\w)", r"\1\2", t)          # a word hyphenated across a line break
    t = re.sub(r"[*_`~]+", "", t)
    t = re.sub(r"(?<=\w)[\-\u2010\u2011\u2012\u2013\u2014](?=\w)", " ", t)
    return re.sub(r"\s+", " ", t).casefold().strip()


def _regions_named(n: str) -> int:
    return sum(1 for rx in _DIS_REGIONS.values() if rx.search(n))


def _states_dis(n: str) -> bool:
    """A DIS statement, a count of regions, or a claim on the presence of lesions in DIS regions."""
    if _DIS_TERMS.search(n):
        return True
    if _REGION_COUNT.search(n) and _REGION_NOUN.search(n):
        return True
    named = _regions_named(n)
    return named >= 2 or (named == 1 and bool(_PRESENCE.search(n)))


def _is_not_evaluated_statement(n: str) -> bool:
    bare = n.rstrip(" .")
    if _NOT_EVALUATED_ONLY.match(bare):
        return True
    return any(bare == _norm(line).rstrip(" .") for line in NOT_EVALUATED_LINE.values())


def _units(text: str) -> List[Tuple[str, str]]:
    """(unit, following whitespace): sentences, and clauses separated by ';'. A full stop after an initial or an
    abbreviation ("D.I.S.", "e.g.") or before a lower-case word does not end a sentence."""
    out: List[Tuple[str, str]] = []
    pos = 0
    for m in re.finditer(r"([.!?]+|;)(?=\s|$)", text):
        stop = m.end()
        if m.group(1) != ";":
            token = re.split(r"\s", text[pos:m.start()])[-1]
            following = text[stop:].lstrip()
            if re.fullmatch(r"(?:[A-Za-z]\.)*[A-Za-z]", token) or token.lower().strip("(") in _ABBREVIATIONS:
                continue
            if following and not (following[0].isupper() or following[0].isdigit()
                                  or following[0] in "\"'([¿¡*_|#>-"):
                continue
        space = re.match(r"\s*", text[stop:]).group(0)
        out.append((text[pos:stop], space))
        pos = stop + len(space)
    if pos < len(text):
        out.append((text[pos:], ""))
    return out


def _blocks(lines: List[str]) -> List[Tuple[str, List[str]]]:
    """Markdown blocks: ('blank'|'heading'|'table'|'text', lines). A text block is a paragraph or a list item with
    its wrapped continuation lines."""
    blocks: List[Tuple[str, List[str]]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            blocks.append(("blank", [line]))
            i += 1
        elif stripped.startswith("#"):
            blocks.append(("heading", [line]))
            i += 1
        elif stripped.startswith("|"):
            j = i
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            blocks.append(("table", lines[i:j]))
            i = j
        else:
            j = i + 1
            while (j < len(lines) and lines[j].strip() and not lines[j].strip().startswith(("#", "|"))
                   and not _LIST_ITEM.match(lines[j])):
                j += 1
            blocks.append(("text", lines[i:j]))
            i = j
    return blocks


def scrub_unevaluated_dis(content: str, language: str) -> Tuple[str, int]:
    """Replace every statement of a draft that says something on DIS although DIS was not evaluated (backstop).

    Works per sentence (and per ';' clause), across wrapped lines, on text with markup and hyphens normalised. A
    sentence naming dissemination in space (en/es/de), DIS, McDonald, a topography, typical/characteristic MS
    regions, a count of regions, two or more DIS regions, or one DIS region with a presence or a number, is
    replaced by the not-evaluated sentence — also when it says "not evaluated" and claims something else. A table
    with a region or DIS row is removed; a heading naming a DIS region is removed. Returns the new text and the
    number of statements replaced or removed."""
    line = NOT_EVALUATED_LINE.get(language, NOT_EVALUATED_LINE["en"])
    clause = line.rstrip(".")
    out: List[str] = []
    replaced = 0
    for kind, lines in _blocks((content or "").split("\n")):
        if kind == "blank":
            out.extend(lines)
            continue
        if kind == "heading":
            n = _norm(lines[0])
            if _regions_named(n) and not _DIS_TERMS.search(n):
                replaced += 1                         # a per-region section heading of an unconfirmed segmentation
                continue
            out.extend(lines)
            continue
        if kind == "table":
            rows = [r for r in lines if not _TABLE_SEPARATOR.match(r)]
            hits = [r for r in rows if _states_dis(_norm(r)) or _regions_named(_norm(r))]
            if hits:
                replaced += len(hits)
                if not out or out[-1] != line:
                    out.append(line)
                continue
            out.extend(lines)
            continue
        prefix = _LIST_PREFIX.match(lines[0]).group(1)
        body = " ".join([lines[0][len(prefix):].strip(), *(ln.strip() for ln in lines[1:])])
        joined_for_match = "\n".join([lines[0][len(prefix):], *lines[1:]])
        if not _states_dis(_norm(joined_for_match)):
            out.extend(lines)
            continue
        pieces: List[str] = []
        changed = False
        last_is_statement = False
        for unit, space in _units(body):
            n = _norm(unit)
            if _is_not_evaluated_statement(n):
                pieces.append(unit + (" " if space else ""))
                last_is_statement = True
                continue
            if _states_dis(n):
                replaced += 1
                changed = True
                if not last_is_statement:
                    pieces.append((clause + ";" if unit.rstrip().endswith(";") else line) + (" " if space else ""))
                last_is_statement = True
                continue
            pieces.append(unit + (" " if space else ""))
            last_is_statement = False
        if not changed:
            out.extend(lines)
            continue
        text = "".join(pieces).strip()
        if text.endswith(";"):
            text = text[:-1] + "."
        if not prefix and out and out[-1] == line and text == line:
            continue
        out.append(prefix + text)
    return "\n".join(out), replaced
