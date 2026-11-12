"""Longitudinal change candidates — how they may be presented (CAPA-013; HAZ-007).

Why. Paper C pilot (PR #60; RMF-001 §3.5, RMF-OBS-001): against expert change masks, the
device's new/enlarging rule (`longitudinal_tracking_service.compare_timepoints`) proposed at
least one FALSE new or enlarging candidate in 20 of 20 patients — 8.9 per patient, 5.4 after
the device's own FLAIR-subtraction check. A comparison therefore says "look here", never "the
disease is active". This module is the single place where the comparison result is turned into
what the view, the report generator and the AI assistant receive. It does not change the
segmentation, the matching or the counting rule.

Risk controls (REQ-SAFE-037):
- RC-060 (a)-(c): the candidates are "unconfirmed change candidates". The legacy flags
  `activity_candidate` / `dit_candidate` (and the "clinically significant" count names) are
  removed from every response. Each new (>= 3 mm) or enlarging candidate gets a stable key; a
  radiologist confirms or rejects it (route `/segmentation/longitudinal/review`), and the
  decision is stored with the authenticated reader, the time and the SHA-256 of both masks it
  was given for. `reader_confirmed_activity` — the only field that carries the word — exists
  only when at least one candidate is confirmed for the masks being compared, and applies the
  MAGNIMS-CMSC-NAIMS 2021 rule (>= 1 new or enlarging T2 lesion) to the CONFIRMED candidates
  only.
- RC-061 (d): the measured false-candidate rate comes from a versioned asset
  (`assets/longitudinal_false_candidate_evidence.json`) bound to the rule it was measured on; if
  the rule in force differs, or the asset is unreadable or incomplete, no rate is served.
- RC-062 (e): the comparison abstains — no candidate, count, burden change or region breakdown —
  when the acquisition of the two visits differs or cannot be established (see
  `compare_acquisitions` for the metadata used and what happens when it is missing).
"""
from __future__ import annotations

import hashlib
import inspect
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from app.core.logging import get_logger

logger = get_logger(__name__)

EVIDENCE_ASSET = Path(__file__).resolve().parent / "assets" / "longitudinal_false_candidate_evidence.json"

# MAGNIMS-CMSC-NAIMS 2021 (Wattjes et al., Lancet Neurol 2021): one new or enlarging T2 lesion
# is enough. Applied ONLY to candidates a radiologist confirmed (REQ-SAFE-037 (c)).
MAGNIMS_2021_MIN_NEW_OR_ENLARGING = 1

REVIEW_DECISIONS = ("confirmed", "rejected")
CANDIDATE_KEY_RE = re.compile(r"^c_[0-9a-f]{16}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# Fields of the comparison that must never reach the view, a report or the assistant (RC-060).
LEGACY_FLAG_KEYS = ("activity_candidate", "dit_candidate", "new_clinically_significant_count", "enlarging_count")


# =============================================================================
# RC-061 — the measured false-candidate rate (versioned asset)
# =============================================================================

def current_rule_parameters() -> Dict[str, Optional[float]]:
    """The parameters of the new/enlarging rule in force, read from the code that applies it."""
    from app.services import longitudinal_tracking_service as lts
    from app.services import longitudinal_subtraction as sub

    params = inspect.signature(lts.compare_timepoints).parameters
    iou = params["iou_threshold"].default
    try:  # the registered path passes its own default; both must agree
        from app.services.registration_service import registered_change_candidates
        reg_iou = inspect.signature(registered_change_candidates).parameters["iou_threshold"].default
    except Exception:  # noqa: BLE001 — registration unavailable: the index-aligned default applies
        reg_iou = iou
    return {
        "new_lesion_min_diameter_mm": float(lts.NEW_LESION_MIN_DIAMETER_MM),
        "enlarged_change_threshold": float(params["change_threshold"].default),
        "match_iou_threshold": float(iou) if iou == reg_iou else None,
        "subtraction_signal_sd": float(sub.DEFAULT_MIN_SIGNAL_SD),
    }


def _pair(v) -> Optional[List[float]]:
    if isinstance(v, (list, tuple)) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v):
        return [float(v[0]), float(v[1])]
    return None


def load_false_candidate_evidence(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """The measured false-candidate rate to show next to the candidates, or None.

    None when the asset is missing, unreadable or incomplete, or when it was measured on another
    rule than the one in force — the view then says that no measured rate is available.
    """
    path = Path(path) if path is not None else EVIDENCE_ASSET
    try:
        asset = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[RC-061] evidence asset unreadable: {e}")
        return None
    try:
        if asset.get("applies_to_rule") != current_rule_parameters():
            logger.warning("[RC-061] evidence asset measured on another rule; rate withheld")
            return None
        m, src = asset["measurement"], asset["source"]
        out = {
            "asset": str(asset["asset_id"]),
            "version": str(asset["version"]),
            "status": str(asset.get("status", "")),
            "measured_on": str(m["measured_on"]),
            "dataset": str(m["dataset"]),
            "segmenter": str(m["segmenter"]),
            "patients": int(m["patients"]),
            "stable_patients": int(m["stable_patients"]),
            "patients_with_false_candidate": int(m["patients_with_false_candidate"]),
            "false_candidates_per_patient": float(m["false_candidates_per_patient"]),
            "false_candidates_per_patient_ci95": _pair(m["false_candidates_per_patient_ci95"]),
            "patients_with_false_candidate_after_subtraction": int(m["patients_with_false_candidate_after_subtraction"]),
            "after_subtraction_per_patient": float(m["after_subtraction_per_patient"]),
            "after_subtraction_per_patient_ci95": _pair(m["after_subtraction_per_patient_ci95"]),
            "source": str(src["display"]),
            "source_record": str(src["record"]),
            "source_commit": str(src["commit"]),
        }
        n_false, n_all = (int(x) for x in m["false_candidates_of_all_candidates"])
        out.update({"false_candidates": n_false, "all_candidates": n_all,
                    "false_share_of_candidates": n_false / n_all})
    except Exception as e:  # noqa: BLE001 — incomplete asset: no rate rather than a wrong one
        logger.warning(f"[RC-061] evidence asset incomplete: {e}")
        return None
    if out["patients"] <= 0 or out["false_candidates_per_patient_ci95"] is None \
            or not 0 <= out["false_candidates"] <= out["all_candidates"] \
            or out["after_subtraction_per_patient_ci95"] is None \
            or not all(math.isfinite(out[k]) and out[k] >= 0
                       for k in ("false_candidates_per_patient", "after_subtraction_per_patient")):
        logger.warning("[RC-061] evidence asset has invalid figures; rate withheld")
        return None
    return out


def _fmt(x: float) -> str:
    return f"{x:g}"


def false_share_percent(evidence: Dict[str, Any]) -> int:
    """Share of all proposed candidates that were false in the source record, in whole percent."""
    return round(100 * evidence["false_share_of_candidates"])


def evidence_sentence(evidence: Optional[Dict[str, Any]]) -> str:
    """English sentence for API consumers (the view renders its own, localised text).

    States the measured figures as measured (review of PR #63: "most candidates may be false"
    overstated a 46 % share)."""
    if not evidence:
        return ("No measured false-candidate rate is available for this rule: treat every candidate "
                "as unconfirmed. ")
    lo, hi = evidence["false_candidates_per_patient_ci95"]
    return (f"In a public test with expert-marked change ({evidence['patients']} patients, "
            f"{evidence['segmenter']}; {evidence['source']}, {evidence['measured_on']}) this rule proposed on "
            f"average {_fmt(evidence['false_candidates_per_patient'])} false new or enlarging candidates per "
            f"patient (95 % CI {_fmt(lo)}-{_fmt(hi)}), {false_share_percent(evidence)} % of all the candidates "
            f"it proposed ({evidence['false_candidates']} of {evidence['all_candidates']}); "
            f"{_fmt(evidence['after_subtraction_per_patient'])} after the subtraction check. No stable patients "
            f"were studied. ")


def assistant_rate_sentence() -> str:
    """The measured rate for the AI assistant's standing instructions, read from the versioned asset
    (review of PR #63: the instructions hard-coded the figure)."""
    ev = load_false_candidate_evidence()
    if not ev:
        return ("No measured false-candidate rate is available for this rule: treat every candidate as "
                "unconfirmed.")
    return (f"In a public test with expert-marked change ({ev['patients']} patients) this rule proposed on "
            f"average {_fmt(ev['false_candidates_per_patient'])} false candidates per patient, "
            f"{false_share_percent(ev)} % of all the candidates it proposed ({ev['source']}, "
            f"{ev['measured_on']}; the response's `false_candidate_evidence` gives the figures).")


# =============================================================================
# RC-062 — acquisition of the two visits
# =============================================================================

REQUIRED_ACQUISITION_FIELDS = (
    "manufacturer", "manufacturer_model_name", "magnetic_field_strength_t",
    "mr_acquisition_type", "slice_thickness_mm",
)
# Compared when at least one visit records them; recorded for one visit only = not established.
SEQUENCE_FIELDS = ("repetition_time_ms", "echo_time_ms", "inversion_time_ms", "spacing_between_slices_mm")
_TEXT_FIELDS = frozenset({"manufacturer", "manufacturer_model_name", "mr_acquisition_type"})
_ABS_TOL = {"magnetic_field_strength_t": 0.05, "slice_thickness_mm": 0.05, "spacing_between_slices_mm": 0.05}
_REL_TOL = {"repetition_time_ms": 0.05, "echo_time_ms": 0.05, "inversion_time_ms": 0.05}
VOXEL_SPACING_TOL_MM = 0.01
ACQUISITION_SOURCE = (
    "acquisition record of each visit's source image (DICOM header: Manufacturer, "
    "ManufacturerModelName, MagneticFieldStrength, MRAcquisitionType, SliceThickness, "
    "SpacingBetweenSlices, RepetitionTime, EchoTime, InversionTime; written at PACS import) "
    "and the voxel size of each image file"
)

# DICOM keyword per acquisition field (written at PACS import by dicomweb_service).
_DICOM_KEYWORDS = {
    "manufacturer": "Manufacturer",
    "manufacturer_model_name": "ManufacturerModelName",
    "magnetic_field_strength_t": "MagneticFieldStrength",
    "mr_acquisition_type": "MRAcquisitionType",
    "slice_thickness_mm": "SliceThickness",
    "spacing_between_slices_mm": "SpacingBetweenSlices",
    "repetition_time_ms": "RepetitionTime",
    "echo_time_ms": "EchoTime",
    "inversion_time_ms": "InversionTime",
}


def _number(v) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    if not isinstance(v, (str, bytes, int, float)):
        try:
            v = list(v)[0]
        except Exception:  # noqa: BLE001
            return None
    try:
        x = float(v)
    except Exception:  # noqa: BLE001
        return None
    return x if math.isfinite(x) and x > 0 else None


def _text(v) -> Optional[str]:
    if v is None:
        return None
    s = " ".join(str(v).split())
    return s or None


def acquisition_from_dicom(ds) -> Dict[str, Any]:
    """Acquisition record from a DICOM header, as plain JSON values (None when absent). Never raises."""
    out: Dict[str, Any] = {}
    for field, keyword in _DICOM_KEYWORDS.items():
        try:
            raw = getattr(ds, keyword, None)
        except Exception:  # noqa: BLE001
            raw = None
        out[field] = _text(raw) if field in _TEXT_FIELDS else _number(raw)
    return out


def _value(acq: Optional[dict], field: str):
    if not isinstance(acq, dict):
        return None
    raw = acq.get(field)
    if field in _TEXT_FIELDS:
        t = _text(raw)
        return t.upper() if t else None
    return _number(raw)


def _same(field: str, a, b) -> bool:
    if field in _TEXT_FIELDS:
        return a == b
    if field in _ABS_TOL:
        return abs(a - b) <= _ABS_TOL[field]
    return abs(a - b) <= _REL_TOL[field] * max(abs(a), abs(b))


def _spacing(s) -> Optional[List[float]]:
    try:
        vals = [float(x) for x in s]
    except Exception:  # noqa: BLE001
        return None
    return vals if len(vals) == 3 and all(math.isfinite(x) and x > 0 for x in vals) else None


def compare_acquisitions(acq_tp1: Optional[dict], acq_tp2: Optional[dict],
                         spacing_tp1, spacing_tp2) -> Dict[str, Any]:
    """Compare the acquisition of the two visits (RC-062).

    Metadata used: manufacturer, model, field strength, 2D/3D, slice thickness (required: missing
    for either visit = not established); repetition, echo and inversion time and spacing between
    slices (compared when recorded; recorded for one visit only = not established); voxel size of
    the two image files (missing = not established).

    status: "same" (comparable), "differs" (any field differs beyond its tolerance) or
    "not_established" (nothing differs but something is missing). Only "same" lets the comparison
    show candidates.
    """
    differing: List[Dict[str, Any]] = []
    missing: List[Dict[str, Any]] = []
    for field in REQUIRED_ACQUISITION_FIELDS + SEQUENCE_FIELDS:
        v1, v2 = _value(acq_tp1, field), _value(acq_tp2, field)
        if v1 is None or v2 is None:
            if field in SEQUENCE_FIELDS and v1 is None and v2 is None:
                continue
            missing.append({"field": field, "timepoints": [tp for tp, v in (("tp1", v1), ("tp2", v2)) if v is None]})
        elif not _same(field, v1, v2):
            differing.append({"field": field, "tp1": v1, "tp2": v2})
    s1, s2 = _spacing(spacing_tp1), _spacing(spacing_tp2)
    if s1 is None or s2 is None:
        missing.append({"field": "voxel_spacing_mm",
                        "timepoints": [tp for tp, v in (("tp1", s1), ("tp2", s2)) if v is None]})
    elif any(abs(a - b) > VOXEL_SPACING_TOL_MM for a, b in zip(s1, s2)):
        differing.append({"field": "voxel_spacing_mm", "tp1": s1, "tp2": s2})
    status = "differs" if differing else ("not_established" if missing else "same")
    return {
        "status": status,
        "comparable": status == "same",
        "required_fields": list(REQUIRED_ACQUISITION_FIELDS),
        "fields_compared": list(REQUIRED_ACQUISITION_FIELDS) + ["voxel_spacing_mm"] + list(SEQUENCE_FIELDS),
        "differing": differing,
        "missing": missing,
        "tolerances": {**_ABS_TOL, **{k: f"{int(v * 100)} %" for k, v in _REL_TOL.items()},
                       "voxel_spacing_mm": VOXEL_SPACING_TOL_MM},
        "source": ACQUISITION_SOURCE,
    }


_FILE_ID_RE = re.compile(r"patients/[^/]+/studies/([^/]+)/series/([^/]+)/[^/]+")


def _parse_when(v):
    """A study date as a naive datetime, or None (ISO date/datetime, DICOM YYYYMMDD, datetime)."""
    from datetime import datetime as _dt
    if v is None:
        return None
    if isinstance(v, _dt):
        return v.replace(tzinfo=None)
    s_ = str(v).strip()
    for parse in (lambda x: _dt.fromisoformat(x.replace("Z", "+00:00")), lambda x: _dt.strptime(x[:8], "%Y%m%d")):
        try:
            return parse(s_).replace(tzinfo=None)
        except Exception:  # noqa: BLE001
            continue
    return None


def check_visit_order(visit_tp1: Optional[dict], visit_tp2: Optional[dict]) -> Dict[str, Any]:
    """Visit 2 must be a different, later visit than visit 1 (review of PR #63).

    status "ok"; "same_visit" or "wrong_order" (the route refuses the comparison); "unknown" when a
    study or date is missing or the two dates are equal (the comparison abstains)."""
    s1 = (visit_tp1 or {}).get("study_id")
    s2 = (visit_tp2 or {}).get("study_id")
    d1, d2 = _parse_when((visit_tp1 or {}).get("study_date")), _parse_when((visit_tp2 or {}).get("study_date"))
    out = {"tp1_study_date": d1.isoformat() if d1 else None, "tp2_study_date": d2.isoformat() if d2 else None}
    if s1 and s2 and s1 == s2:
        return {**out, "status": "same_visit"}
    if not (s1 and s2 and d1 and d2) or d1 == d2:
        return {**out, "status": "unknown"}
    return {**out, "status": "ok" if d2 > d1 else "wrong_order"}


async def read_source_visit(file_id, study_service=None) -> Optional[Dict[str, Any]]:
    """Study (visit) and study date of a segmentation's source image, or None. Never raises."""
    from uuid import UUID
    m = _FILE_ID_RE.fullmatch(str(file_id or ""))
    if not m:
        return None
    try:
        if study_service is None:
            from app.core.container import get_study_service
            study_service = get_study_service()
        study = await study_service.get_study(UUID(m.group(1)))
        when = getattr(study, "study_date", None)
        return {"study_id": m.group(1), "study_date": when.isoformat() if hasattr(when, "isoformat") else when}
    except Exception as e:  # noqa: BLE001 — unknown visit: the comparison abstains
        logger.warning(f"[RC-062] visit of a source image unreadable: {e}")
        return None


def read_source_acquisition(file_id, study_service=None) -> Optional[Dict[str, Any]]:
    """The acquisition record stored with a source image (instance document), or None. Never raises."""
    m = _FILE_ID_RE.fullmatch(str(file_id or ""))
    if not m:
        return None
    try:
        if study_service is None:
            from app.core.container import get_study_service
            study_service = get_study_service()
        db = getattr(study_service, "db", None)
        if db is None:
            return None
        instances = (db.collection("studies").document(m.group(1))
                     .collection("series").document(m.group(2)).collection("instances"))
        for doc in instances.stream():
            data = doc.to_dict() or {}
            if data.get("gcs_object_name") == file_id:
                acq = data.get("acquisition")
                return acq if isinstance(acq, dict) else None
    except Exception as e:  # noqa: BLE001 — unknown acquisition: the comparison abstains
        logger.warning(f"[RC-062] acquisition record unreadable for a source image: {e}")
    return None


# =============================================================================
# RC-060 — candidates, reader decisions, presentation
# =============================================================================

def mask_sha256(mask) -> str:
    """SHA-256 of the stored mask bytes — same digest as SegmentationService.mask_sha256."""
    return hashlib.sha256(np.ascontiguousarray(mask, dtype=np.uint8).tobytes()).hexdigest()


def mask_binding(tp1_mask, tp2_mask) -> Dict[str, str]:
    return {"tp1_mask_sha256": mask_sha256(tp1_mask), "tp2_mask_sha256": mask_sha256(tp2_mask)}


def is_reviewable(change: dict) -> bool:
    """A candidate the rule counts: new >= 3 mm, or enlarged."""
    return (change.get("status") == "new" and change.get("clinically_significant") is True) \
        or change.get("status") == "enlarged"


def candidate_key(change: dict) -> str:
    """Stable key of a candidate for the masks compared. Any change of position or volume gives
    another key, so a decision never carries over to a different candidate."""
    def f(k, nd):
        try:
            return f"{float(change.get(k, 0) or 0):.{nd}f}"
        except Exception:  # noqa: BLE001
            return "nan"
    basis = "|".join([str(change.get("status")), f("centroid_z", 1), f("centroid_y", 1), f("centroid_x", 1),
                      f("volume_tp1_mm3", 2), f("volume_tp2_mm3", 2)])
    return "c_" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def _registration_sentence(result: dict) -> str:
    if result.get("registration_applied"):
        return ("Timepoints were rigidly co-registered, but registration is advisory and NOT verified at "
                "lesion scale: a residual misalignment can still produce a false new or enlarging candidate. ")
    return ("This comparison did NOT perform spatial registration (source intensities unavailable); equal "
            "array dimensions are not necessarily voxel-aligned. ")


def _abstention_caveat(check: dict, visit_check: Optional[dict] = None) -> str:
    reasons = []
    if (visit_check or {}).get("status") == "unknown":
        reasons.append("the dates of the two visits could not be established, so their order is not known")
    if check["status"] == "differs":
        reasons.append("the acquisition differs between the two visits ("
                       + ", ".join(d["field"] for d in check["differing"]) + ")")
    elif check["status"] == "not_established":
        reasons.append("the acquisition could not be established (" + ", ".join(
            f"{d['field']} missing for {'/'.join(d['timepoints'])}" for d in check["missing"]) + ")")
    return ("No automatic change candidates and no lesion load or count comparison for this pair: "
            + "; ".join(reasons) + ". Automatic results are not reliable across a change of scanner or "
            "protocol, or when it cannot be excluded. Compare the images visually with the overlay.")


# Every quantity withheld when the comparison abstains (RC-062; review of PR #63, blocker 2: the
# lesion load and count of each visit were still shown and passed to the report).
ABSTAINED_NULL_FIELDS = (
    "status_counts", "change_candidates", "burden_delta_mm3", "burden_delta_percent", "region_stratification",
    "region_atlas_note", "subtraction_summary", "review_binding", "burden_tp1_mm3", "burden_tp2_mm3",
    "burden_tp1_ml", "burden_tp2_ml", "total_lesions_tp1", "total_lesions_tp2",
)


def present_comparison(result: dict, *, acquisition_check: dict, evidence: Optional[dict],
                       binding: Optional[Dict[str, str]], stored_review: Optional[dict],
                       visit_check: Optional[dict] = None, review_read_failed: bool = False) -> dict:
    """What the view, the report generator and the assistant receive (RC-060, RC-061, RC-062)."""
    out = {k: v for k, v in result.items() if k not in LEGACY_FLAG_KEYS}
    visit_check = visit_check or {"status": "unknown"}
    out["acquisition_check"] = acquisition_check
    out["visit_check"] = visit_check
    out["false_candidate_evidence"] = evidence

    if acquisition_check.get("status") != "same" or visit_check.get("status") != "ok":   # RC-062
        out.update({"abstained": True, "changes": []})
        out.update({k: None for k in ABSTAINED_NULL_FIELDS})
        out["caveat"] = _abstention_caveat(acquisition_check, visit_check)
        return out

    decisions: Dict[str, dict] = {}
    voided = False
    if review_read_failed:
        binding = None          # decisions unknown: none may be shown, none may be recorded blind
    elif binding and isinstance(stored_review, dict):
        if stored_review.get("tp1_mask_sha256") == binding["tp1_mask_sha256"] \
                and stored_review.get("tp2_mask_sha256") == binding["tp2_mask_sha256"]:
            decisions = stored_review.get("decisions") or {}
        else:
            voided = True       # the masks changed after the decisions: they do not apply

    n_new = n_enl = c_new = c_enl = rejected = 0
    confirmers, times, changes = set(), [], []
    for ch in result.get("changes") or []:
        ch = dict(ch)
        if is_reviewable(ch):
            key = candidate_key(ch)
            ch["candidate_key"] = key
            is_new = ch.get("status") == "new"
            n_new, n_enl = n_new + is_new, n_enl + (not is_new)
            d = decisions.get(key)
            if isinstance(d, dict) and d.get("decision") in REVIEW_DECISIONS:
                ch["reader_review"] = {"decision": d["decision"], "reviewed_by": d.get("reviewed_by"),
                                       "reviewed_at": d.get("reviewed_at")}
                if d["decision"] == "confirmed":
                    c_new, c_enl = c_new + is_new, c_enl + (not is_new)
                    confirmers.add(str(d.get("reviewed_by")))
                    times.append(str(d.get("reviewed_at")))
                else:
                    rejected += 1
        changes.append(ch)

    total, confirmed = n_new + n_enl, c_new + c_enl
    out.update({
        "abstained": False,
        "changes": changes,
        "change_candidates": {
            "new": n_new, "enlarging": n_enl, "total": total, "confirmed": confirmed, "rejected": rejected,
            "awaiting_review": total - confirmed - rejected, "earlier_decisions_voided": voided,
            "decisions_unavailable": review_read_failed,
            "presentation": "unconfirmed change candidates, to be reviewed one by one by a radiologist",
        },
        "review_binding": binding,
    })
    if review_read_failed:   # review of PR #63: a read error must not look like "awaiting review"
        out["change_candidates"].update({"confirmed": None, "rejected": None, "awaiting_review": None})
    if confirmed >= MAGNIMS_2021_MIN_NEW_OR_ENLARGING:
        out["reader_confirmed_activity"] = {
            "rule": "MAGNIMS-CMSC-NAIMS 2021: one new or enlarging T2 lesion indicates MRI activity; "
                    "applied to radiologist-confirmed lesions only",
            "confirmed_new": c_new,
            "confirmed_enlarging": c_enl,
            "confirmed_by": sorted(confirmers),
            "first_confirmed_at": min(times),
            "last_confirmed_at": max(times),
        }
    out["caveat"] = (
        "New/enlarging/resolved results are UNCONFIRMED CHANGE CANDIDATES, to be reviewed one by one: only a "
        "radiologist's confirmation counts. " + evidence_sentence(evidence) + _registration_sentence(result)
        + "The FLAIR subtraction result is a signal, not a confirmation. A reader must adjudicate each "
          "candidate before it informs dissemination in time or any diagnostic conclusion."
        + (" The radiologist decisions recorded for this pair could not be read: do not treat the candidates "
           "as unreviewed; compare again." if review_read_failed else "")
    )
    return out


def validate_decisions(decisions) -> Optional[str]:
    """Error message for an invalid decision list, or None."""
    if not isinstance(decisions, list) or not decisions or len(decisions) > 500:
        return "decisions must be a non-empty list"
    for d in decisions:
        if not isinstance(d, dict):
            return "each decision must be an object"
        if not isinstance(d.get("candidate_key"), str) or not CANDIDATE_KEY_RE.fullmatch(d["candidate_key"]):
            return "each decision needs the candidate_key returned by the comparison"
        if d.get("decision") not in REVIEW_DECISIONS:
            return "decision must be 'confirmed' or 'rejected'"
    return None


def validate_binding(binding) -> Optional[Dict[str, str]]:
    if not isinstance(binding, dict):
        return None
    out = {k: str(binding.get(k, "")).strip().lower() for k in ("tp1_mask_sha256", "tp2_mask_sha256")}
    return out if all(SHA256_RE.fullmatch(v) for v in out.values()) else None
