"""Single quality gate — the agent ``quality-gate`` of the agent platform (code only, no language model).

REQ-FUNC-117, REQ-FUNC-118, REQ-SAFE-052, REQ-SAFE-053, REQ-SAFE-054; HAZ-025; RC-122..RC-127.
DRAFT, PENDING owner approval. Design and survey: docs/iec62304/agent_platform/Quality_Gate_Design.md.

ONE deterministic rule decides, before an AI step runs and again before its output is shown, whether it may
proceed. It consolidates checks that exist elsewhere and CALLS them rather than copying them:

- sequence   from the series description with the gate's token classifier — with the gate on, the ONE sequence
             classifier of the product (G15, restated in the fifth review of PR #81): the RC-049 header evidence of
             the in-browser AI uses it while VITE_ENABLE_QUALITY_GATE is on (its base rules while off, G26); the
             research inventory keeps its own base heuristic; never the file name;
- thickness  from ``acquisition_geometry`` (RC-054): native / at_least / not_determinable;
- scanner    of two visits through ``longitudinal_candidate_safety.compare_acquisitions`` (RC-062);
- skull      the outcome of the skull gates / skull removal of the in-browser AI (RC-101).

ONE implementation (sixth review of PR #81, G27): the rule, the policy and the sequence classifier exist only here.
The browser sends its inputs (the file, the physician's attestation, the skull outcome its worker reports) and shows
this module's answer as it is; the answer names the attestable visits and the action of each code. Unknown never
passes (G3).

DATA RULE (REQ-SAFE-053, RC-124): the thickness check WARNS and never abstains until the v3 evidence asset of
paper 1 (commercial data only) is set in ``policy["thickness"]["evidence_asset"]`` — see ``_thickness_check``.

``evaluate`` is pure. ``run_quality_gate`` consults the platform (approval and both kill switches, read now,
fail closed), records one trace with one child span per check that ran, and one ``agent.run`` audit record.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import io
import json
import math
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services import longitudinal_candidate_safety as lcs

GATE_VERSION = "quality-gate/1"
AGENT_ID = "quality-gate"
POLICY_PATH = Path(__file__).with_name("quality_gate_policy.json")
DECISIONS = ("abstain", "pending", "proceed_with_warnings", "proceed")
STATUSES = ("pass", "warn", "pending", "abstain")
VISIT_LABELS = ("study", "tp1", "tp2")
# Tokeniser of a series description (first review of PR #81, S1/S2): no word-boundary regex — '_' is a word
# character for \b, so 'AX_DWI_B1000' was read as naming no sequence. The SAME steps are in gate.ts.
_CAMEL = re.compile(r"([a-z])([A-Z])")
_PLUS_C = re.compile(r"\+\s*[cC](?![A-Za-z])")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_LETTERS = re.compile(r"[a-z]*")

_POLICY: Optional[Dict[str, Any]] = None


def _policy() -> Dict[str, Any]:
    """The shipped policy, cached and read only (no copy per call; E3)."""
    global _POLICY
    if _POLICY is None:
        _POLICY = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    return _POLICY


def load_policy() -> Dict[str, Any]:
    """A deep copy of the shipped policy, for a caller that changes it (the cached original is never handed out)."""
    return copy.deepcopy(_policy())


# ----------------------------------------------------------------------------- the rule (pure)
def _check(check: str, visit: Optional[str], status: str, code: Optional[str] = None, **params) -> Dict[str, Any]:
    return {"check": check, "visit": visit, "status": status, "code": code, "params": params}


def _number(v) -> Optional[float]:
    """A finite number that is not a boolean, else None (strict: no strings — inputs are normalised)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    v = float(v)
    return v if math.isfinite(v) else None


def _platform_check(platform, policy) -> Dict[str, Any]:
    if isinstance(platform, dict) and platform.get("allowed") is True:
        return _check("platform", None, "pass")
    codes = policy["platform"]["codes"]
    code = platform.get("code") if isinstance(platform, dict) else None
    return _check("platform", None, "abstain", codes.get(code, policy["platform"]["otherwise"])
                  if isinstance(code, str) else policy["platform"]["otherwise"])


def _sequence_check(visit, label, policy, mode) -> Dict[str, Any]:
    rules = policy["sequence"]
    raw = visit.get("sequence")
    seq = "missing" if raw is None else (raw if isinstance(raw, str) and raw in rules["values"] else "unknown")
    if seq in rules["accepted"]:
        return _check("sequence", label, "pass")
    if seq in rules["confirmable_by_physician"]:
        # G13: the attestation lifts only unknown / missing, and only where the product offers it (single study)
        if visit.get("physician_confirmed_flair") is True and mode in rules["confirmation_modes"]:
            return _check("sequence", label, "warn", "sequence_confirmed_by_physician", sequence=seq)
        return _check("sequence", label, "abstain", f"sequence_{seq}")
    return _check("sequence", label, "abstain", "sequence_not_flair", sequence=seq)


def _band(mm: float, policy) -> str:
    for band in policy["thickness"]["bands"]:
        if band["max_mm"] is None or mm <= band["max_mm"]:
            return band["id"]
    return policy["thickness"]["bands"][-1]["id"]


def _evidence_abstain_bands(policy) -> List[str]:
    """V3 EVIDENCE HOOK (REQ-SAFE-053, RC-124). Bands that may abstain: only those of an evidence asset whose
    licence is on the commercial allow-list. None is set in this release, so the thickness check only warns."""
    rules = policy["thickness"]
    asset = rules.get("evidence_asset")
    if not isinstance(asset, dict) or asset.get("licence") not in rules["commercial_licence_allowlist"]:
        return []
    bands = asset.get("abstain_band_ids")
    return [b for b in bands if isinstance(b, str)] if isinstance(bands, list) else []


def _thickness_check(visit, label, policy) -> Dict[str, Any]:
    rules = policy["thickness"]
    t = visit.get("thickness")
    state = t.get("state") if isinstance(t, dict) else None
    mm = _number(t.get("effective_mm")) if isinstance(t, dict) else None
    known = mm is not None and 0.0 < mm <= rules["plausible_max_mm"]
    if state == "native" and known and mm <= rules["thin_limit_mm"]:
        return _check("thickness", label, "pass")
    if state == "native" and known:
        code = "thickness_thick"
    elif state == "at_least" and known and mm > rules["thin_limit_mm"]:
        code = "thickness_at_least"
    else:
        return _check("thickness", label, "warn", "thickness_unknown")
    band = _band(mm, policy)
    if band in _evidence_abstain_bands(policy):
        return _check("thickness", label, "abstain", "thickness_out_of_range", band=band, mm=mm)
    return _check("thickness", label, "warn", code, band=band, mm=mm)


def _skull_check(visit, label) -> Dict[str, Any]:
    skull = visit.get("skull")
    if skull == "stripped":
        return _check("skull", label, "pass")
    if skull == "pending":
        return _check("skull", label, "pending", "skull_pending")
    if skull == "not_stripped":
        return _check("skull", label, "abstain", "skull_present")
    return _check("skull", label, "abstain", "skull_unknown")


def _scanner_record(visit, policy) -> Dict[str, Any]:
    s = visit.get("scanner")
    s = s if isinstance(s, dict) else {}
    out = {}
    for field in policy["scanner"]["fields"]:
        v = s.get(field)
        if field == "magnetic_field_strength_t":
            out[field] = _number(v)
        else:
            out[field] = " ".join(v.split()) or None if isinstance(v, str) else None
    return out


def _scanner_check(visits, policy) -> Dict[str, Any]:
    """RC-123: the scanner of the two visits through RC-062's own comparison (its tolerances, its rules)."""
    fields = policy["scanner"]["fields"]
    result = lcs.compare_acquisitions(_scanner_record(visits[0], policy), _scanner_record(visits[1], policy),
                                      None, None)
    differing = [d["field"] for d in result["differing"] if d["field"] in fields]
    missing = [d["field"] for d in result["missing"] if d["field"] in fields]
    if differing:
        return _check("scanner", None, "abstain", "scanner_changed", fields=[f for f in fields if f in differing])
    # Nothing recorded in EITHER visit (two uploads): a warning, and RC-062 decides — it abstains, as on the base
    # branch. The gate never removes an RC-062 abstention (fourth review of PR #81, R1 / G24).
    unrecorded = all(all(v is None for v in _scanner_record(visit, policy).values()) for visit in visits)
    if missing and unrecorded:
        return _check("scanner", None, policy["codes"]["scanner_not_recorded"], "scanner_not_recorded")
    if missing:
        return _check("scanner", None, "abstain", "scanner_unknown", fields=[f for f in fields if f in missing])
    return _check("scanner", None, "pass")


def _result(checks: List[Dict[str, Any]], policy, mode=None) -> Dict[str, Any]:
    statuses = {c["status"] for c in checks}
    decision = ("abstain" if "abstain" in statuses or not checks else "pending" if "pending" in statuses
                else "proceed_with_warnings" if "warn" in statuses else "proceed")
    return {
        "gate_version": GATE_VERSION,
        "policy_version": policy.get("policy_version"),
        "mode": mode,
        "decision": decision,
        "ai_may_run": decision != "abstain",
        "ai_output_allowed": decision in ("proceed", "proceed_with_warnings"),
        "codes": sorted({c["code"] for c in checks if c["code"]}),
        "checks": checks,
        # Sixth review of PR #81 (G27): the browser holds no policy, so the answer names what it shows — the visits
        # whose FLAIR the physician may attest in this mode, and the i18n action of each code in this mode.
        "attestable_visits": [c["visit"] for c in checks if c["check"] == "sequence"
                              and c["code"] in ("sequence_unknown", "sequence_missing")
                              and mode in policy["sequence"]["confirmation_modes"]],
        "actions": {c["code"]: _action_key(policy, mode, c["code"]) for c in checks if c["code"]},
    }


def _action_key(policy, mode, code) -> str:
    """G14: the i18n action of a code in a mode (policy.mode_actions), else 'action'."""
    table = (policy.get("mode_actions") or {}).get(mode) if isinstance(mode, str) else None
    key = table.get(code) if isinstance(table, dict) else None
    return key if isinstance(key, str) else "action"


def _evaluate(inputs, policy) -> Dict[str, Any]:
    if not isinstance(inputs, dict):
        return _result([_check("input", None, "abstain", "gate_input_invalid")], policy)
    platform = _platform_check(inputs.get("platform"), policy)
    if platform["status"] != "pass":                                   # G6: nothing else runs
        return _result([platform], policy, inputs.get("mode") if isinstance(inputs.get("mode"), str) else None)
    mode, visits = inputs.get("mode"), inputs.get("visits")
    spec = policy["modes"].get(mode) if isinstance(mode, str) else None
    if (spec is None or not isinstance(visits, list) or len(visits) != len(spec["visits"])
            or not all(isinstance(v, dict) for v in visits)):
        return _result([platform, _check("input", None, "abstain", "gate_input_invalid")], policy)
    checks = [platform]
    for label, visit in zip(spec["visits"], visits):
        if visit.get("header") == "unreadable":        # the header could not be read at all (third review)
            checks.append(_check("input", label, policy["codes"]["header_unreadable"], "header_unreadable"))
        checks.append(_sequence_check(visit, label, policy, mode))
        checks.append(_thickness_check(visit, label, policy))
        if "skull" in spec["checks"] and mode in policy["skull"]["required_in_modes"]:
            checks.append(_skull_check(visit, label))
    if "scanner" in spec["checks"]:
        checks.append(_scanner_check(visits, policy))
    return _result(checks, policy, mode)


def evaluate(inputs, policy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The gate's decision for normalised inputs (see the design, section 3). Total: never raises."""
    policy = policy if policy is not None else _policy()
    try:
        return _evaluate(inputs, policy)
    except Exception:  # noqa: BLE001 — a fault in the gate is an abstention, never a pass
        return _result([_check("input", None, "abstain", "gate_input_invalid")], policy)


def canonical(result: Dict[str, Any]) -> str:
    """The decision as one line, identical in gate.ts (G4): decision|codes|check@visit:status:code[param];..."""
    parts = []
    for c in result.get("checks", []):
        p = c.get("params") or {}
        param = p.get("band") or ("+".join(p["fields"]) if p.get("fields") else None) or p.get("sequence")
        parts.append(f"{c['check']}@{c.get('visit') or '-'}:{c['status']}:{c.get('code') or '-'}"
                     + (f"[{param}]" if param else ""))
    return f"{result.get('decision')}|{','.join(result.get('codes', []))}|{';'.join(parts)}"


# ----------------------------------------------------------------------------- inputs from stored metadata
def sequence_tokens(text: str) -> List[str]:
    """The tokens of a series description: camelCase split, '*' read as 'star', '+C' as 'postcontrast', lower
    case, split on every non-alphanumeric character (so '_' separates, unlike a regex word boundary)."""
    s = _PLUS_C.sub(" postcontrast ", _CAMEL.sub(r"\1 \2", text).replace("*", " star "))
    return [t for t in _NON_ALNUM.split(s.lower()) if t]


def _weighted(token: str, prefix: str) -> bool:
    return token.startswith(prefix) and _LETTERS.fullmatch(token[len(prefix):]) is not None


_COMPILED: Dict[int, tuple] = {}


def _compiled(vocab: Dict[str, Any]) -> Dict[str, Any]:
    """The vocabulary's word sets and its inversion-time regex, built ONCE per policy (fifth review of PR #81,
    cleanup): the shipped policy's at import, a test's own policy on first use."""
    hit = _COMPILED.get(id(vocab))
    if hit is not None and hit[0] is vocab:
        return hit[1]
    c = {
        "other": frozenset(vocab["other_words"]),
        "weak": frozenset(vocab.get("weak_other_words", ())),
        "flair_word": vocab["flair_substring"],
        "flair_names": frozenset(vocab["flair_words"]) | frozenset(vocab["flair_compounds"]),
        "flair_pairs": frozenset(tuple(p) for p in vocab["flair_pairs"]),
        "t1_prefix": vocab["t1_prefix"], "t2_prefix": vocab["t2_prefix"],
        "t1_words": frozenset(vocab["t1_words"]),
        "swi": frozenset(vocab["swi_family"]), "pd": frozenset(vocab["pd_family"]),
        "image_type_other": frozenset(vocab["image_type_other"]),
        "ti": re.compile(vocab["ti_text_pattern"], re.IGNORECASE),
    }
    _COMPILED[id(vocab)] = (vocab, c)
    return c


_compiled(_policy()["sequence"]["vocabulary"])     # the shipped policy's word sets: built once, at import


def _classify_tokens(tokens: List[str], vocab: Dict[str, Any]) -> tuple:
    """(class, T1-weighted, T2-weighted) of one description's tokens — the ONE weighting routine (fifth review of
    PR #81, cleanup; classify_fields reuses it). D-QG-12: a WEAK word (weak_other_words: cal, loc, dir, mag — also a
    calibration, a location, a phase-encoding direction, a magnitude image) makes the image 'other' only when the
    description names no FLAIR; every other word of other_words does so always."""
    c = _compiled(vocab)
    flair_word = c["flair_word"]
    flair = (any(flair_word in t or t in c["flair_names"] for t in tokens)
             or any((a, b) in c["flair_pairs"] for a, b in zip(tokens, tokens[1:])))
    hits = {w for t in tokens for w in (t, t.rstrip("0123456789")) if w in c["other"]}
    is_other = bool(hits - c["weak"]) or (bool(hits) and not flair)
    t1 = (any(_weighted(t, c["t1_prefix"]) or t in c["t1_words"] for t in tokens)
          or any(flair_word in t and c["t1_prefix"] in t.replace(flair_word, "") for t in tokens))
    t2 = any(_weighted(t, c["t2_prefix"]) for t in tokens)
    if is_other or (flair and t1):          # a non-FLAIR name, or a T1-weighted FLAIR: ALWAYS abstains
        return "other", t1, t2
    if flair:
        return "FLAIR", t1, t2
    return ("T1" if t1 else "T2" if t2 else "unknown"), t1, t2


def classify_text(text: Any, policy: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """The class ONE description names by its words alone — never by an inversion time (fifth review of PR #81,
    F5); None for no words. Same as gate.ts classifyText."""
    tokens = sequence_tokens(text) if isinstance(text, str) else []
    if not tokens:
        return None
    return _classify_tokens(tokens, (policy if policy is not None else _policy())["sequence"]["vocabulary"])[0]


def text_inversion_time_ms(text: Any, policy: Optional[Dict[str, Any]] = None) -> Optional[float]:
    """An inversion time written in the text ('TI=2500', 'TI: 2.5' — seconds below ti_seconds_below), or None."""
    vocab = (policy if policy is not None else _policy())["sequence"]["vocabulary"]
    if not isinstance(text, str):
        return None
    m = _compiled(vocab)["ti"].search(text)
    if not m:
        return None
    v = float(m.group(1))
    if not math.isfinite(v) or v <= 0:
        return None
    return v * 1000.0 if v < vocab["ti_seconds_below"] else v


def _sequence_name_class(value: Any, vocab: Dict[str, Any]) -> Optional[str]:
    """G19: the DICOM SequenceName is a vendor internal code ('*tir2d1rr18', 'fgre', 'TFE'): a leading '*' is a Siemens
    prefix (never 'T2*'); the leading letters are looked up; an unlisted code says nothing (unknown)."""
    if not isinstance(value, str) or not value.strip():
        return None
    code = value.strip().lower().lstrip("*")
    if vocab["flair_substring"] in code:
        return "FLAIR"
    letters = re.match(r"[a-z]*", code).group(0)
    return vocab["sequence_name_codes"].get(letters, "unknown")


def _image_type_class(value: Any, vocab: Dict[str, Any]) -> Optional[str]:
    """G19: the DICOM ImageType: a reformatted, projected, subtracted or parametric image is other (D-QG-7);
    anything else says nothing."""
    values = value if isinstance(value, (list, tuple)) else str(value).split("\\") if isinstance(value, str) else []
    tokens = {t for v in values for t in _NON_ALNUM.split(str(v).lower()) if t}
    if not tokens:
        return None
    return "other" if tokens & _compiled(vocab)["image_type_other"] else "unknown"


def classify_fields(fields: Dict[str, Any], inversion_time_ms: Any = None,
                    policy: Optional[Dict[str, Any]] = None) -> Dict[str, Optional[str]]:
    """The ONE sequence classifier of the product, FIELD-AWARE (third review of PR #81, G19): the description
    (``description``: a text or a list — SeriesDescription, ProtocolName, NIfTI descrip; also ``protocol_name``) by
    its tokens, ``sequence_name`` by the vendor-code table, ``image_type`` by its own list. Any field naming a
    non-FLAIR sequence decides (other / T1 / T2); else a FLAIR name; else unknown; nothing at all = missing."""
    policy = policy if policy is not None else _policy()
    rules = policy["sequence"]
    vocab = rules["vocabulary"]
    desc = fields.get("description")
    texts = [t for t in (desc if isinstance(desc, (list, tuple)) else [desc]) if isinstance(t, str)]
    if isinstance(fields.get("protocol_name"), str):
        texts.append(fields["protocol_name"])
    ti = _number(inversion_time_ms)
    ti = ti if ti is not None and ti > 0 else next(
        (v for v in (text_inversion_time_ms(t, policy) for t in texts) if v is not None), None)
    tokens_per_text = [sequence_tokens(t) for t in texts]
    per_text = [_classify_tokens(tk, vocab) for tk in tokens_per_text if tk]       # one weighting routine
    classes = [cls for cls, _, _ in per_text]
    classes += [c for c in (_sequence_name_class(fields.get("sequence_name"), vocab),
                            _image_type_class(fields.get("image_type"), vocab)) if c]
    words = _compiled(vocab)
    tokens = {t for tk in tokens_per_text for t in tk}
    weighting = "T1" if any(t1 for _, t1, _ in per_text) else "T2" if any(t2 for _, _, t2 in per_text) else None
    family = "SWI" if tokens & words["swi"] else "PD" if tokens & words["pd"] else None
    if not classes and ti is None:
        cls = "missing"
    elif ti is not None and ti < rules["min_flair_inversion_time_ms"]:
        cls = "other"
    else:
        cls = next((c for c in classes if c in ("other", "T1", "T2")), None) or (
            "FLAIR" if "FLAIR" in classes else "unknown")
    return {"class": cls, "weighting": weighting, "family": family}


def classify_sequence(series_description: Any, inversion_time_ms: Any = None,
                      policy: Optional[Dict[str, Any]] = None) -> Dict[str, Optional[str]]:
    """The description field alone through classify_fields (G15): the class, plus the weighting (T1/T2) and family
    (SWI/PD) the dataset inventory reports. Same rules as gate.ts and headerEvidence.ts (both route to it)."""
    return classify_fields({"description": series_description}, inversion_time_ms, policy)


def sequence_from_header(series_description: Any, inversion_time_ms: Any = None,
                         policy: Optional[Dict[str, Any]] = None) -> str:
    """Sequence of an image from its header text (series description) and inversion time — never the file name.

    FLAIR (only an unambiguous FLAIR, T2-FLAIR or dark-fluid name) / T1 / T2 / other (any token naming a
    non-FLAIR sequence, a T1 weighting with FLAIR, a localizer, a derived or contrast image, an inversion time
    too short for a FLAIR) / unknown (names no sequence, or only a FLAIR-compatible inversion time) / missing."""
    return classify_sequence(series_description, inversion_time_ms, policy)["class"]


def thickness_from_geometry(geometry: Any) -> Optional[Dict[str, Any]]:
    """The thickness input from an RC-054 AcquisitionGeometry (model or dict); None when absent."""
    if geometry is None:
        return None
    get = geometry.get if isinstance(geometry, dict) else (lambda k: getattr(geometry, k, None))
    return {"state": get("state"), "effective_mm": get("effective_mm")}


def thickness_from_acquisition_record(acq: Optional[dict], thin_limit_mm: Optional[float] = None
                                      ) -> Optional[Dict[str, Any]]:
    """The thickness input from a stored acquisition record (PACS import). The record does not say whether the
    image is ORIGINAL, so it is at most a lower bound (as RC-054 treats a derived image): at_least above the thin
    limit of the policy being evaluated (E3), otherwise not determinable."""
    if not isinstance(acq, dict):
        return None
    limit = thin_limit_mm if thin_limit_mm is not None else _policy()["thickness"]["thin_limit_mm"]
    values = [lcs._number(acq.get(k)) for k in ("slice_thickness_mm", "spacing_between_slices_mm")]
    if values[0] is None:
        return {"state": "not_determinable", "effective_mm": None}
    mm = max(v for v in values if v is not None)
    if mm > limit:
        return {"state": "at_least", "effective_mm": mm}
    return {"state": "not_determinable", "effective_mm": None}


def scanner_from_acquisition_record(acq: Optional[dict]) -> Optional[Dict[str, Any]]:
    if not isinstance(acq, dict):
        return None
    return {"manufacturer": lcs._text(acq.get("manufacturer")),
            "manufacturer_model_name": lcs._text(acq.get("manufacturer_model_name")),
            "magnetic_field_strength_t": lcs._number(acq.get("magnetic_field_strength_t"))}


def read_source_series_description(file_id, study_service=None) -> Optional[str]:
    """The series description stored for a source image's series (PACS import), or None. Never raises."""
    m = lcs._FILE_ID_RE.fullmatch(str(file_id or ""))
    if not m:
        return None
    try:
        if study_service is None:
            from app.core.container import get_study_service
            study_service = get_study_service()
        db = getattr(study_service, "db", None)
        if db is None:
            return None
        doc = db.collection("studies").document(m.group(1)).collection("series").document(m.group(2)).get()
        value = (doc.to_dict() or {}).get("series_description") if getattr(doc, "exists", False) else None
        return value if isinstance(value, str) and value.strip() else None
    except Exception:  # noqa: BLE001 — unknown description: the sequence is "missing", the gate abstains
        return None


def study_of(file_id) -> Optional[str]:
    """The study id in a source image's storage path (for the pseudonymised study key), or None."""
    m = lcs._FILE_ID_RE.fullmatch(str(file_id or ""))
    return m.group(1) if m else None


_NO_HEADER = {"descriptions": [], "protocol_name": None, "sequence_name": None, "image_type": None,
              "inversion_time_ms": None, "thickness": None}
_HEADER_CACHE: "OrderedDict[tuple, Dict[str, Any]]" = OrderedDict()
HEADER_CACHE_MAX = 256


def _nifti_header_image(data: bytes):
    """A NIfTI image whose header is read and whose voxels are NOT (nibabel's lazy array proxy)."""
    import gzip
    import nibabel as nib
    stream = gzip.GzipFile(fileobj=io.BytesIO(data)) if data[:2] == b"\x1f\x8b" else io.BytesIO(data)
    holder = nib.FileHolder(fileobj=stream)
    klass = nib.Nifti2Image if _nifti_sizeof_hdr(_nifti_prefix(data))[0] == 540 else nib.Nifti1Image
    return klass.from_file_map({"header": holder, "image": holder})


def _dicom_fields(ds) -> Dict[str, Any]:
    text = lambda k: (str(ds.get(k, "") or "").strip() or None)
    image_type = getattr(ds, "ImageType", None)
    return {"descriptions": [t for t in (text("SeriesDescription"),) if t], "protocol_name": text("ProtocolName"),
            "sequence_name": text("SequenceName"),
            "image_type": [str(v) for v in image_type] if image_type is not None and not isinstance(image_type, str)
            else image_type,
            "inversion_time_ms": lcs._number(getattr(ds, "InversionTime", None))}


def _printable_runs(payload: bytes, cap: int = 65536) -> List[str]:
    """Printable ASCII runs of at least 4 characters of an extension payload (as the browser's RC-049 read them)."""
    return [m.group(0).strip() for m in re.finditer(rb"[\x20-\x7e]{4,}", payload[:cap]) if m.group(0).strip()
            and len(m.group(0).strip()) >= 4]


def _nifti_fields(img) -> Dict[str, Any]:
    """A1 (sixth review of PR #81): everything the browser's RC-049 read from a NIfTI — descrip, aux_file,
    intent_name, db_name, the printable text of its extensions, and the DICOM attributes of a DICOM extension
    (SeriesDescription, ProtocolName, SequenceName, InversionTime, ImageType)."""
    hdr = img.header
    texts = []
    for key in ("descrip", "aux_file", "intent_name", "db_name"):
        try:
            value = hdr[key]
        except Exception:  # noqa: BLE001 — a field this header version lacks
            continue
        value = value.item() if hasattr(value, "item") else value
        value = value.decode("latin-1", "replace") if isinstance(value, (bytes, bytearray)) else str(value or "")
        value = "".join(ch if 32 <= ord(ch) < 127 else " " for ch in value.split("\x00", 1)[0]).strip()
        if value:
            texts.append(value)
    out = {**_NO_HEADER, "descriptions": texts}
    for ext in list(getattr(hdr, "extensions", []) or []):
        code = ext.get_code() if hasattr(ext, "get_code") else getattr(ext, "code", None)
        content = ext.get_content() if hasattr(ext, "get_content") else getattr(ext, "_content", b"")
        payload = content if isinstance(content, (bytes, bytearray)) else bytes(getattr(ext, "_raw_content", b"") or b"")
        if code == 2:
            try:
                import pydicom
                ds = content if hasattr(content, "get") and not isinstance(content, (bytes, bytearray)) else \
                    pydicom.dcmread(io.BytesIO(payload), force=True)
                d = _dicom_fields(ds)
                out["descriptions"] = out["descriptions"] + d["descriptions"]
                for key in ("protocol_name", "sequence_name", "image_type", "inversion_time_ms"):
                    out[key] = d[key] if d[key] is not None else out[key]
            except Exception:  # noqa: BLE001 — an unreadable DICOM extension adds nothing
                pass
        else:
            out["descriptions"] = out["descriptions"] + [r.decode("ascii") for r in _printable_runs(bytes(payload))]
    return out


def header_classifier_fields(fields: Dict[str, Any], stored_description: Any = None) -> Dict[str, Any]:
    """The classifier's fields of one image: its header descriptions (and the series description stored for it,
    as the browser's RC-049 also read the app's), ProtocolName, SequenceName and ImageType (field-aware, G19)."""
    texts = list(fields.get("descriptions") or [])
    if isinstance(stored_description, str) and stored_description.strip():
        texts.append(stored_description)
    return {"description": texts, "protocol_name": fields.get("protocol_name"),
            "sequence_name": fields.get("sequence_name"), "image_type": fields.get("image_type")}


def read_header_fields(data: bytes, name: str, imaging_service) -> Dict[str, Any]:
    """Header only (E1): pydicom with stop_before_pixels, a lazy NIfTI header — no voxel is decoded, normalised
    or summarised. Descriptions, ProtocolName, SequenceName, ImageType and inversion time (DICOM, and NIfTI with
    its text fields and extensions — A1), RC-054 thickness (both)."""
    from app.services.acquisition_geometry import derive_from_dicom_dataset, derive_from_nifti_image
    fmt = sniff_format(data)                         # magic bytes, never the file name (third review, other 1)
    if fmt == "dicom":
        import pydicom
        ds = pydicom.dcmread(io.BytesIO(data), stop_before_pixels=True, force=True)
        return {**_dicom_fields(ds), "thickness": thickness_from_geometry(derive_from_dicom_dataset(ds))}
    if fmt == "nifti":
        img = _nifti_header_image(data)
        return {**_nifti_fields(img), "thickness": thickness_from_geometry(derive_from_nifti_image(img))}
    return {**_NO_HEADER, "unreadable": True}


HEADER_PREFIX_NIFTI = 4096        # compressed bytes: the 348-byte header (+ extensions) of a NIfTI
HEADER_PREFIX_DICOM = 65536       # a bounded DICOM prefix, read with stop_before_pixels
HEADER_PREFIX_MAX = 4 * 1024 * 1024
_PIXEL_DATA_TAGS = (b"\xe0\x7f\x10\x00", b"\x7f\xe0\x00\x10")


def _nifti_prefix(data: bytes) -> bytes:
    import zlib
    if data[:2] != b"\x1f\x8b":
        return data
    try:
        return zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(data, 1 << 20)
    except zlib.error:
        return b""


def _nifti_sizeof_hdr(raw: bytes):
    import struct
    if len(raw) < 4:
        return None, None
    for endian in ("<", ">"):
        size = struct.unpack(endian + "i", raw[:4])[0]
        if size in (348, 540):
            return size, endian
    return None, None


def sniff_format(data: bytes) -> Optional[str]:
    """The format from MAGIC BYTES only (third review, other 1): NIfTI sizeof_hdr 348/540 (raw or gzip), DICOM 'DICM' at
    128 or a preamble-less file starting with an explicit-VR group 0002/0008 element. None = not determinable."""
    if _nifti_sizeof_hdr(_nifti_prefix(data))[0]:
        return "nifti"
    if data[128:132] == b"DICM":
        return "dicom"
    if len(data) >= 8 and data[0:2] in (b"\x02\x00", b"\x08\x00") and data[4:6].isalpha() and data[4:6].isupper():
        return "dicom"
    return None


def _header_complete(data: bytes) -> bool:
    """Does this prefix hold the whole header? DICOM: the pixel data starts inside it; NIfTI: the header plus the
    extensions up to vox_offset (after decompressing the prefix). Magic bytes only; run in a worker thread."""
    import struct
    fmt = sniff_format(data)
    if fmt == "dicom":
        return any(tag in data for tag in _PIXEL_DATA_TAGS)
    if fmt != "nifti":
        return False
    raw = _nifti_prefix(data)
    size, endian = _nifti_sizeof_hdr(raw)
    if len(raw) < size + 4:
        return False
    if raw[size] == 0:
        return True
    vox_offset = (struct.unpack(endian + "f", raw[108:112])[0] if size == 348
                  else struct.unpack(endian + "q", raw[168:176])[0])
    return len(raw) >= vox_offset


async def _read_header_fields(storage_service, bucket: str, file_path: str, imaging_service) -> Dict[str, Any]:
    """E1 / second review, finding 3: the header only, through bounded byte ranges (retried larger while the header
    runs longer), parsed in a worker thread. A storage without ranges is read whole (as displayed_image_check)."""
    from app.core.interfaces.storage_interface import IStorageService
    name = file_path.rsplit("/", 1)[-1]
    ranged = getattr(storage_service, "download_file_range", None)
    if ranged is None or getattr(type(storage_service), "download_file_range", None) is IStorageService.download_file_range:
        # no real ranges (the interface default downloads the whole file per call): ONE full download at most
        data = await storage_service.download_file(bucket, file_path)
        return await asyncio.to_thread(read_header_fields, data, name, imaging_service)
    size = HEADER_PREFIX_NIFTI if name.lower().endswith((".nii", ".nii.gz")) else HEADER_PREFIX_DICOM
    while True:
        data = await ranged(bucket, file_path, 0, size - 1)
        if len(data) < size or size >= HEADER_PREFIX_MAX or await asyncio.to_thread(_header_complete, data):
            return await asyncio.to_thread(read_header_fields, data, name, imaging_service)
        size *= 4


async def _file_version(storage_service, bucket: str, file_path: str) -> Optional[tuple]:
    try:
        meta = await storage_service.get_file_metadata(bucket, file_path)
    except Exception:  # noqa: BLE001 — no version known: no cache
        return None
    version = (getattr(meta, "size", None), getattr(meta, "checksum_sha256", None), getattr(meta, "created_at", None))
    return (file_path, *version) if meta is not None and version[0] is not None and any(version[1:]) else None


async def file_version_key(storage_service, bucket: str, file_path: str) -> Optional[tuple]:
    """(file, size, checksum, created) of the stored file, or None when its version is unknown (then nothing is
    cached for it)."""
    return await _file_version(storage_service, bucket, file_path)


_NOT_GIVEN = object()


async def visit_header_fields(storage_service, bucket: str, file_path: str, imaging_service=None, *,
                              version_key: Any = _NOT_GIVEN) -> Dict[str, Any]:
    """The header fields of one stored image, cached per file version (E1); an unreadable header is an explicit
    'unreadable' (never 'missing'). Used by the single study AND by each visit of a comparison (A1)."""
    # the route passes the version it already read for the cache key (F3): one metadata read per consultation
    key = version_key if version_key is not _NOT_GIVEN else await _file_version(storage_service, bucket, file_path)
    fields = _HEADER_CACHE.get(key) if key else None
    if fields is None:
        try:
            fields = await _read_header_fields(storage_service, bucket, file_path, imaging_service)
        except Exception:  # noqa: BLE001 — the header could not be read: an explicit code, never 'missing'
            fields = {**_NO_HEADER, "unreadable": True}
        else:
            if key and not fields.get("unreadable"):
                _HEADER_CACHE[key] = fields
                while len(_HEADER_CACHE) > HEADER_CACHE_MAX:
                    _HEADER_CACHE.popitem(last=False)
    else:
        _HEADER_CACHE.move_to_end(key)
    return fields


def visit_inputs(fields: Dict[str, Any], acquisition: Optional[dict], stored_description: Any, *,
                 physician_confirmed_flair: bool = False, skull: str = "unknown", with_scanner: bool = False,
                 policy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The gate inputs of ONE image, the same way in a single study and in each visit of a comparison (A1, sixth
    review of PR #81): the sequence from its header (and the stored series description), its inversion time from
    the header else the acquisition record; the RC-054 thickness from its header else the acquisition record (a
    lower bound); the scanner from the acquisition record (comparison only)."""
    policy = policy if policy is not None else _policy()
    acq = acquisition if isinstance(acquisition, dict) else None
    ti = fields.get("inversion_time_ms") if fields.get("inversion_time_ms") is not None else (acq or {}).get("inversion_time_ms")
    thickness = fields.get("thickness")
    if not isinstance(thickness, dict):
        thickness = thickness_from_acquisition_record(acq, policy["thickness"]["thin_limit_mm"])
    return {
        **({"header": "unreadable"} if fields.get("unreadable") else {}),
        "sequence": classify_fields(header_classifier_fields(fields, stored_description), ti, policy)["class"],
        "physician_confirmed_flair": physician_confirmed_flair is True,
        "thickness": dict(thickness) if isinstance(thickness, dict) else None,
        "scanner": scanner_from_acquisition_record(acq) if with_scanner else None,
        "skull": skull,
    }


def stored_records(file_path: str):
    """(acquisition record, stored series description) of a source image; never raises (unknown = None)."""
    return lcs.read_source_acquisition(file_path), read_source_series_description(file_path)


async def single_study_inputs(file_path: str, storage_service, imaging_service, *, bucket: str,
                              physician_confirmed_flair: bool = False, skull: str = "pending",
                              version_key: Any = _NOT_GIVEN, records: Any = None):
    """Gate inputs of a study opened for AI analysis, derived ON THE SERVER from the stored file (visit_inputs):
    its header, else the stored series and acquisition records, and the RC-054 geometry. Header only, parsed off the
    event loop, cached per file version (E1). Anything unreadable stays unknown, so the gate warns or abstains; it
    never raises. Returns (inputs, file version or None).

    ``skull``: 'pending' before the run; at the final consultation the outcome the browser reports ('stripped' /
    'unknown'), so the decision that releases or withholds the output is decided and audited here (G17).
    ``records``: the (acquisition, stored description) pair the route already read for the cache key (A3)."""
    key = version_key if version_key is not _NOT_GIVEN else await _file_version(storage_service, bucket, file_path)
    fields = await visit_header_fields(storage_service, bucket, file_path, imaging_service, version_key=key)
    acq, stored = records if records is not None else await asyncio.to_thread(stored_records, file_path)
    visit = visit_inputs(fields, acq, stored, physician_confirmed_flair=physician_confirmed_flair, skull=skull)
    return {"mode": "single", "visits": [visit]}, (":".join(str(v) for v in key[1:]) if key else None)


def actor_for(user, request=None):
    """The authenticated clinician as the platform's audit actor (never anonymous, CAPA-015)."""
    from app.agent_platform.registry import AuditActor
    role = getattr(user, "role", None)
    return AuditActor(user_id=str(getattr(user, "id", "") or ""), username=getattr(user, "username", None),
                      role=str(getattr(role, "value", role)) if role is not None else None, request=request)


_UNREAD = object()


# ----------------------------------------------------------------------------- through the platform
_REGISTRY = None


def default_registry():
    """The repository registry (agents.json) with the environment kill switches, read at every consultation."""
    global _REGISTRY
    if _REGISTRY is None:
        from app.agent_platform.registry import AgentRegistry
        _REGISTRY = AgentRegistry.load()
    return _REGISTRY


def platform_allows(registry=None) -> bool:
    """Approval and both kill switches, read now, WITHOUT an audit record of its own: the route asks it before any
    I/O, and a refusal is then audited once by run_quality_gate (second review of PR #81, finding 1)."""
    from app.agent_platform import registry as R
    reg = registry if registry is not None else default_registry()
    with R.within_run():
        return reg.check_agent(AGENT_ID).allowed is True


RATE_LIMIT_PER_MINUTE = 30
_LIMITER = None


def new_rate_limiter():
    from app.core.security.rate_limiter import RateLimiter
    return RateLimiter(redis_client=None, default_limit=RATE_LIMIT_PER_MINUTE, default_window=60)


def rate_limit_evaluation(user_id: str) -> Optional[int]:
    """Per-user bound on REAL evaluations (each may read a file header and writes an audit record), with the
    platform's rate limiter: None when allowed, else the seconds to wait (fifth review of PR #81, F3). A
    consultation served from the cache is not counted. KNOWN LIMITATION: the limiter and the cache are per server
    instance (in memory), so N instances allow up to N times the limit (Quality_Gate_Design.md)."""
    global _LIMITER
    from app.core.security.rate_limiter import RateLimitScope
    if _LIMITER is None:
        _LIMITER = new_rate_limiter()
    allowed, meta = _LIMITER.check_rate_limit(f"quality_gate:{user_id}", limit=RATE_LIMIT_PER_MINUTE, window=60,
                                              scope=RateLimitScope.PER_USER, user_id=user_id)
    if allowed:
        return None
    wait = _number((meta or {}).get("retry_after")) if isinstance(meta, dict) else None
    return max(1, min(60, int(math.ceil(wait)))) if wait is not None and wait > 0 else 60


# F3: the gate's answers to pre-run consultations, per (file, version, attestation, skull, policy version)
CONSULTATION_CACHE_MAX = 512
_CONSULTATIONS: "OrderedDict[tuple, tuple]" = OrderedDict()


def consultation_key(version_key: Optional[tuple], physician_confirmed_flair: bool, skull: str,
                     records: Any = None, user_id: Optional[str] = None) -> Optional[tuple]:
    """The cache key of a consultation, or None when it must be evaluated: the file's version is unknown, or the
    consultation would release an AI output (a skull outcome other than 'pending' — the final consultation, whose
    decision is always decided and audited again, F4). Sixth review of PR #81: the key names EVERY input the
    decision is made from (A3: the file version, a digest of the stored series and acquisition records, the
    attestation, the skull outcome, the policy version) and, when the physician attests, the clinician (A2: an
    attestation is always evaluated and audited under the clinician who gave it)."""
    if not version_key or skull != "pending":
        return None
    digest = hashlib.sha256(json.dumps(records, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    attested = physician_confirmed_flair is True
    return (*version_key, attested, skull, _policy()["policy_version"], digest, user_id if attested else None)


def cached_consultation(key: Optional[tuple]) -> Optional[tuple]:
    """(answer, file version) of an earlier evaluation of the same consultation, or None."""
    if key is None or key not in _CONSULTATIONS:
        return None
    _CONSULTATIONS.move_to_end(key)
    return _CONSULTATIONS[key]


def store_consultation(key: Optional[tuple], answer: Dict[str, Any], version: Optional[str]) -> None:
    """Only an answer the platform allowed is kept (a refusal or a fault is never served again); the platform is
    read again before every cached answer is served, so a kill switch applies at once."""
    if key is None or (answer.get("platform") or {}).get("allowed") is not True:
        return
    _CONSULTATIONS[key] = (answer, version)
    while len(_CONSULTATIONS) > CONSULTATION_CACHE_MAX:
        _CONSULTATIONS.popitem(last=False)


def run_quality_gate(inputs, *, registry=None, tracer=None, study_key: str = "", actor=None,
                     trace_id: Optional[str] = None) -> Dict[str, Any]:
    """The gate as the registered agent ``quality-gate`` (RC-126): the platform's approval and kill switches are
    read now (fail closed); one trace (one child span per check that ran) and one ``agent.run`` audit record.
    The caller's ``platform`` field, if any, is ignored: only the registry decides it."""
    from app.agent_platform import registry as R
    from app.agent_platform import tracing as T

    reg = registry if registry is not None else default_registry()
    tr = tracer if tracer is not None else T.Tracer()
    policy = _policy()                 # cached, read only (finding 6)
    state: Dict[str, Any] = {}
    with R.audit_actor(actor), R.within_run():
        try:
            with tr.agent_span(AGENT_ID, provider="mstool", trace_id=trace_id, registry_version=reg.version,
                               study_key=R.pseudonymise(study_key) if study_key else None) as span:
                state["trace_id"] = span.trace_id
                decision = reg.check_agent(AGENT_ID, trace_id=span.trace_id)
                state["refusal"] = None if decision.allowed else decision.code
                payload = {k: v for k, v in inputs.items() if k != "platform"} if isinstance(inputs, dict) else {}
                payload["platform"] = {"allowed": decision.allowed is True,
                                       "code": str(decision.code) if decision.code else None}
                if not isinstance(inputs, dict):
                    payload["mode"] = None
                result = evaluate(payload, policy)
                result["platform"] = payload["platform"]          # the browser re-evaluates with it (gate.ts)
                for c in result["checks"]:
                    with tr.span(f"gate_check {c['check']}", "INTERNAL", {
                        "mstool.operation.name": "gate_check", "mstool.gate.check": c["check"],
                        "mstool.gate.visit": c["visit"] or "none", "mstool.gate.status": c["status"],
                        "mstool.gate.code": c["code"] or "none"}):
                        pass
                span.set("mstool.run.status", "refused" if state["refusal"] else
                         "abstained" if result["decision"] == "abstain" else "delivered")
                if state["refusal"]:
                    span.set("mstool.refusal.code", str(state["refusal"]))
        except Exception:  # noqa: BLE001 — a platform fault: abstain, audited as a failure
            result = _result([_check("platform", None, "abstain", policy["platform"]["otherwise"])], policy)
            result["platform"] = {"allowed": False, "code": str(R.RefusalCode.RUN_INTERNAL_ERROR)}
            result["trace_id"] = state.get("trace_id")
            reg.audit("failure", R.RefusalCode.RUN_INTERNAL_ERROR, event="agent.consultation", agent_id=AGENT_ID,
                      study_key=study_key or None, trace_id=state.get("trace_id"))
            return result
        result["trace_id"] = state["trace_id"]
        # F4 (fifth review of PR #81): a consultation is not an AI run. Only a decision that releases an AI output
        # (ai_output_allowed: the final consultation of a single study, or a comparison allowed) is linked to the AI
        # run ("agent.run" -> CLINICAL_AI_RUN); every other one is a consultation ("agent.consultation").
        event = "agent.run" if result.get("ai_output_allowed") is True else "agent.consultation"
        if state["refusal"]:
            reg.audit("denied", state["refusal"], event=event, agent_id=AGENT_ID,
                      study_key=study_key or None, trace_id=state["trace_id"])
        else:
            # S3: the physician's attestation is recorded with the run's actor (the authenticated clinician)
            reg.audit("success", audit_code(result), event=event, agent_id=AGENT_ID,
                      study_key=study_key or None, trace_id=state["trace_id"])
    return result


# ----------------------------------------------------------------------------- comparison wiring
def apply_to_comparison(result: Dict[str, Any], gate: Dict[str, Any]) -> Dict[str, Any]:
    """Attach the gate to a longitudinal comparison; when it abstains, withhold exactly what RC-062 withholds."""
    if gate.get("ai_output_allowed") is not True:      # ONE abstention path (second review, finding 5)
        return abstained_comparison(gate)
    out = {**result, "quality_gate": gate}
    reasons = [CAVEAT_REASONS[c] for c in warning_codes(gate)]
    if reasons:                                       # R4: a warned comparison says so (the assistant reads this)
        previous = out.get("caveat") if isinstance(out.get("caveat"), str) else ""
        out["caveat"] = (previous.rstrip() + " " if previous.strip() else "") + (
            "Quality-gate warnings for this pair: " + "; ".join(reasons) + ".")
    return out


def warning_codes(gate: Any) -> List[str]:
    """The gate's WARNING codes (policy status 'warn'), from a gate result; anything else is ignored (R4)."""
    codes = _policy()["codes"]
    raw = gate.get("codes") if isinstance(gate, dict) else None
    return [c for c in raw if isinstance(c, str) and codes.get(c) == "warn"] if isinstance(raw, list) else []


def present_gated_comparison(result: Dict[str, Any], *, acquisition_check: Dict[str, Any], evidence, binding,
                             stored_review, visit_check, review_read_failed: bool = False, gate=None) -> Dict[str, Any]:
    """G24 / G25 (fourth review of PR #81): RC-062 EXACTLY as on the base branch
    (longitudinal_candidate_safety.present_comparison, no gate parameter), then the gate, which can only ADD an
    abstention or warnings. The compare route answers through this one function."""
    presented = lcs.present_comparison(result, acquisition_check=acquisition_check, evidence=evidence,
                                       binding=binding, stored_review=stored_review, visit_check=visit_check,
                                       review_read_failed=review_read_failed)
    return apply_to_comparison(presented, gate) if gate is not None else presented


# C3: plain reasons for the report and the assistant (never a raw code). The UI shows the en/es/de texts of the
# i18n files through QualityGatePanel; these are the backend's English sentences for text consumers.
REASONS_PATH = Path(__file__).with_name("quality_gate_reasons.json")
_REASONS: Dict[str, Any] = json.loads(REASONS_PATH.read_text(encoding="utf-8"))


def reason_sentence(code: str, lang: str = "en") -> str:
    """A4 (sixth review of PR #81): the ONE table of reason sentences (quality_gate_reasons.json) — the caveat the
    assistant reads (en) and the code-written report notice (en/es/de) take their sentences from it."""
    row = _REASONS["reasons"].get(code) or {"en": "a quality check did not pass", "es": "un control de calidad no se superó",
                                            "de": "eine Qualitätsprüfung wurde nicht bestanden"}
    return row.get(lang) or row["en"]


def reason_lead(name: str, lang: str = "en") -> str:
    row = _REASONS["leads"][name]
    return row.get(lang) or row["en"]


# C3: plain reasons for the report and the assistant (never a raw code), from the one table (A4).
CAVEAT_REASONS = {code: row["en"] for code, row in _REASONS["reasons"].items()}


def audit_code(result: Dict[str, Any]) -> str:
    """G17: the decision and the code that decided it (the first abstaining, else pending, check), plus '.attested'
    when the physician's attestation was used — shown and withheld outputs leave distinguishable records (the
    server log keeps 64 characters: 'agent.run:' + this)."""
    decision = result.get("decision")
    deciding = next((c["code"] for st in ("abstain", "pending") for c in result.get("checks", [])
                     if c.get("status") == st and c.get("code")), None) if decision in ("abstain", "pending") else None
    visits = [c.get("visit") for c in result.get("checks", []) if c.get("code") == "sequence_confirmed_by_physician"]
    attested = "" if not visits else ".attested" if visits == ["study"] else ".attested_" + "_".join(visits)
    return f"quality_gate.{decision}" + (f".{deciding}" if deciding else "") + attested


def gate_caveat(gate: Dict[str, Any]) -> str:
    reasons = [CAVEAT_REASONS.get(c, "a quality check did not pass") for c in (gate.get("codes") or ["gate_unavailable"])]
    return ("No automatic change candidates and no lesion load or count comparison for this pair: the quality gate "
            "stopped it, because " + "; ".join(reasons) + ". Compare the images visually with the overlay.")


def abstained_comparison(gate: Dict[str, Any]) -> Dict[str, Any]:
    """The comparison response when the gate stops it BEFORE anything is loaded (C2): every quantity withheld."""
    out = {"abstained": True, "changes": [], "quality_gate": gate, "registration_verified": False,
           "adjudication_required": True, "reader_confirmed_activity": None, "caveat": gate_caveat(gate)}
    out.update({k: None for k in lcs.ABSTAINED_NULL_FIELDS})
    return out


def comparison_gate(source_tp1, source_tp2, *, headers=None, acquisitions=None, attestation=(False, False),
                    user=None, request=None) -> Dict[str, Any]:
    """The gate on two visits (RC-123), through the platform (RC-126). Sixth review of PR #81 (A1): each visit is
    derived exactly as a single study (visit_inputs) from its stored image header (``headers``, read by the route),
    its stored series description and its acquisition record (``acquisitions``: the records the route already read
    for RC-062, E2). A visit whose header was not read is 'unreadable' and abstains."""
    given_acq = list(acquisitions) if acquisitions is not None else [_UNREAD, _UNREAD]
    given_hdr = list(headers) if headers is not None else [None, None]
    visits = []
    for s, a, h, att in zip((source_tp1, source_tp2), given_acq, given_hdr, attestation):
        acq = (lcs.read_source_acquisition(s) if s else None) if a is _UNREAD else a
        fields = h if isinstance(h, dict) else {**_NO_HEADER, "unreadable": True}
        stored = read_source_series_description(s) if s else None
        visits.append(visit_inputs(fields, acq, stored, physician_confirmed_flair=att is True, with_scanner=True))
    return run_quality_gate({"mode": "comparison", "visits": visits},
                            study_key=study_of(source_tp2) or study_of(source_tp1) or "",
                            actor=actor_for(user, request) if user is not None else None)
