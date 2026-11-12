"""Single quality gate — the agent ``quality-gate`` of the agent platform (code only, no language model).

REQ-FUNC-117, REQ-FUNC-118, REQ-SAFE-052, REQ-SAFE-053, REQ-SAFE-054; HAZ-025; RC-122..RC-127.
DRAFT, PENDING owner approval. Design and survey: docs/iec62304/agent_platform/Quality_Gate_Design.md.

ONE deterministic rule decides, before an AI step runs and again before its output is shown, whether it may
proceed. It consolidates checks that exist elsewhere and CALLS them rather than copying them:

- sequence   from the series description with the gate's token classifier — the ONE sequence classifier of the
             product (second review of PR #81, G15): ``dataset_inventory.detect_sequence`` and the RC-049 header
             evidence of the in-browser AI route to it; never the file name;
- thickness  from ``acquisition_geometry`` (RC-054): native / at_least / not_determinable;
- scanner    of two visits through ``longitudinal_candidate_safety.compare_acquisitions`` (RC-062);
- skull      the outcome of the skull gates / skull removal of the in-browser AI (RC-101).

The same rule is implemented in ``frontend/src/services/qualityGate/gate.ts`` from the same policy file; the
shared fixture ``frontend/src/config/qualityGate.cases.v1.json`` pins both (G4). Unknown never passes (G3).

DATA RULE (REQ-SAFE-053, RC-124): the thickness check WARNS and never abstains until the v3 evidence asset of
paper 1 (commercial data only) is set in ``policy["thickness"]["evidence_asset"]`` — see ``_thickness_check``.

``evaluate`` is pure. ``run_quality_gate`` consults the platform (approval and both kill switches, read now,
fail closed), records one trace with one child span per check that ran, and one ``agent.run`` audit record.
"""
from __future__ import annotations

import asyncio
import copy
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
    }


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


def _classify_tokens(tokens: List[str], vocab: Dict[str, Any]) -> str:
    other = set(vocab["other_words"])
    flair_word = vocab["flair_substring"]
    is_other = any({t, t.rstrip("0123456789")} & other for t in tokens)
    flair = (any(flair_word in t for t in tokens) or any(t in vocab["flair_compounds"] for t in tokens)
             or any(t in vocab["flair_words"] for t in tokens)
             or any([a, b] in vocab["flair_pairs"] for a, b in zip(tokens, tokens[1:])))
    t1 = (any(_weighted(t, vocab["t1_prefix"]) or t in vocab["t1_words"] for t in tokens)
          or any(flair_word in t and vocab["t1_prefix"] in t.replace(flair_word, "") for t in tokens))
    t2 = any(_weighted(t, vocab["t2_prefix"]) for t in tokens)
    if is_other or (flair and t1):          # a non-FLAIR name, or a T1-weighted FLAIR: ALWAYS abstains
        return "other"
    if flair:
        return "FLAIR"
    return "T1" if t1 else "T2" if t2 else "unknown"


_TI_PATTERNS: Dict[str, Any] = {}


def text_inversion_time_ms(text: Any, policy: Optional[Dict[str, Any]] = None) -> Optional[float]:
    """An inversion time written in the text ('TI=2500', 'TI: 2.5' — seconds below ti_seconds_below), or None."""
    vocab = (policy if policy is not None else _policy())["sequence"]["vocabulary"]
    if not isinstance(text, str):
        return None
    pattern = _TI_PATTERNS.get(vocab["ti_text_pattern"])
    if pattern is None:
        pattern = _TI_PATTERNS[vocab["ti_text_pattern"]] = re.compile(vocab["ti_text_pattern"], re.IGNORECASE)
    m = pattern.search(text)
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
    return "other" if tokens & set(vocab["image_type_other"]) else "unknown"


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
    classes = [_classify_tokens(tk, vocab) for tk in tokens_per_text if tk]
    classes += [c for c in (_sequence_name_class(fields.get("sequence_name"), vocab),
                            _image_type_class(fields.get("image_type"), vocab)) if c]
    tokens = [t for tk in tokens_per_text for t in tk]
    flair_word = vocab["flair_substring"]
    t1 = (any(_weighted(t, vocab["t1_prefix"]) or t in vocab["t1_words"] for t in tokens)
          or any(flair_word in t and vocab["t1_prefix"] in t.replace(flair_word, "") for t in tokens))
    weighting = "T1" if t1 else "T2" if any(_weighted(t, vocab["t2_prefix"]) for t in tokens) else None
    family = ("SWI" if set(tokens) & set(vocab["swi_family"]) else "PD" if set(tokens) & set(vocab["pd_family"])
              else None)
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


_NO_HEADER = {"series_description": None, "inversion_time_ms": None, "thickness": None}
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


def read_header_fields(data: bytes, name: str, imaging_service) -> Dict[str, Any]:
    """Header only (E1): pydicom with stop_before_pixels, a lazy NIfTI header — no voxel is decoded, normalised
    or summarised. Series description and inversion time (DICOM), RC-054 thickness (both)."""
    from app.services.acquisition_geometry import derive_from_dicom_dataset, derive_from_nifti_image
    fmt = sniff_format(data)                         # magic bytes, never the file name (third review, other 1)
    if fmt == "dicom":
        import pydicom
        ds = pydicom.dcmread(io.BytesIO(data), stop_before_pixels=True, force=True)
        text = lambda k: (str(ds.get(k, "") or "").strip() or None)
        image_type = getattr(ds, "ImageType", None)
        return {"series_description": text("SeriesDescription"), "protocol_name": text("ProtocolName"),
                "sequence_name": text("SequenceName"),
                "image_type": [str(v) for v in image_type] if image_type is not None and not isinstance(image_type, str)
                else image_type,
                "inversion_time_ms": lcs._number(getattr(ds, "InversionTime", None)),
                "thickness": thickness_from_geometry(derive_from_dicom_dataset(ds))}
    if fmt == "nifti":
        return {**_NO_HEADER, "thickness": thickness_from_geometry(derive_from_nifti_image(_nifti_header_image(data)))}
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


async def single_study_inputs(file_path: str, storage_service, imaging_service, *, bucket: str,
                              physician_confirmed_flair: bool = False, skull: str = "pending"):
    """Gate inputs of a study opened for AI analysis, derived ON THE SERVER from the stored file: its header's
    series description and inversion time (else the stored series and acquisition records), the RC-054
    geometry. Header only, parsed off the event loop, cached per file version (E1). The skull is 'pending': the
    browser's skull gates and the app's removal decide it before the output (RC-125). Anything unreadable stays
    unknown, so the gate warns or abstains; it never raises. Returns (inputs, file version or None).

    ``skull``: 'pending' before the run; at the final consultation the outcome the browser reports ('stripped' /
    'unknown'), so the decision that releases or withholds the output is decided and audited here (G17)."""
    key = await _file_version(storage_service, bucket, file_path)
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
    acq, stored = await asyncio.to_thread(
        lambda: (lcs.read_source_acquisition(file_path), read_source_series_description(file_path)))
    description = fields["series_description"] or stored
    ti = fields["inversion_time_ms"] if fields["inversion_time_ms"] is not None else (acq or {}).get("inversion_time_ms")
    sequence = classify_fields({"description": description, "protocol_name": fields.get("protocol_name"),
                                "sequence_name": fields.get("sequence_name"), "image_type": fields.get("image_type")},
                               ti)["class"]
    return {"mode": "single", "visits": [{
        **({"header": "unreadable"} if fields.get("unreadable") else {}),
        "sequence": sequence,
        "physician_confirmed_flair": physician_confirmed_flair is True,
        "thickness": dict(fields["thickness"]) if isinstance(fields["thickness"], dict) else None,
        "scanner": None,
        "skull": skull,
    }]}, (":".join(str(v) for v in key[1:]) if key else None)


def actor_for(user, request=None):
    """The authenticated clinician as the platform's audit actor (never anonymous, CAPA-015)."""
    from app.agent_platform.registry import AuditActor
    role = getattr(user, "role", None)
    return AuditActor(user_id=str(getattr(user, "id", "") or ""), username=getattr(user, "username", None),
                      role=str(getattr(role, "value", role)) if role is not None else None, request=request)


_UNREAD = object()


def visit_from_stored_records(file_id, *, acquisition: Any = _UNREAD, skull: str = "unknown",
                              physician_confirmed_flair: bool = False, study_service=None,
                              policy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Gate inputs of one visit from the records stored with its source image (comparison mode). The caller passes
    the acquisition record it already read (E2); it is read here only when not given."""
    policy = policy if policy is not None else _policy()
    if acquisition is _UNREAD:
        acquisition = lcs.read_source_acquisition(file_id, study_service) if file_id else None
    acq = acquisition if isinstance(acquisition, dict) else None
    description = read_source_series_description(file_id, study_service) if file_id else None
    return {
        "sequence": sequence_from_header(description, (acq or {}).get("inversion_time_ms"), policy),
        "physician_confirmed_flair": physician_confirmed_flair is True,
        "thickness": thickness_from_acquisition_record(acq, policy["thickness"]["thin_limit_mm"]),
        "scanner": scanner_from_acquisition_record(acq),
        "skull": skull,
    }


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


def allow_consultation(user_id: str) -> bool:
    """Per-user bound on consultations (each may read a file header), with the platform's rate limiter."""
    global _LIMITER
    from app.core.security.rate_limiter import RateLimitScope
    if _LIMITER is None:
        _LIMITER = new_rate_limiter()
    allowed, _ = _LIMITER.check_rate_limit(f"quality_gate:{user_id}", limit=RATE_LIMIT_PER_MINUTE, window=60,
                                           scope=RateLimitScope.PER_USER, user_id=user_id)
    return bool(allowed)


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
            reg.audit("failure", R.RefusalCode.RUN_INTERNAL_ERROR, event="agent.run", agent_id=AGENT_ID,
                      study_key=study_key or None, trace_id=state.get("trace_id"))
            return result
        result["trace_id"] = state["trace_id"]
        if state["refusal"]:
            reg.audit("denied", state["refusal"], event="agent.run", agent_id=AGENT_ID,
                      study_key=study_key or None, trace_id=state["trace_id"])
        else:
            # S3: the physician's attestation is recorded with the run's actor (the authenticated clinician)
            reg.audit("success", audit_code(result), event="agent.run", agent_id=AGENT_ID,
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


def comparison_withheld(acquisition_check: Dict[str, Any], visit_check, gate=None) -> Dict[str, bool]:
    """G25: the ONE comparability verdict of a pair, for compare_longitudinal and the SEL search: RC-062's own
    decision (present_comparison, as on the base branch) or the gate's abstention."""
    rc062 = lcs.present_comparison({}, acquisition_check=acquisition_check, evidence=None, binding=None,
                                   stored_review=None, visit_check=visit_check).get("abstained") is True
    stops = gate is not None and gate.get("ai_output_allowed") is not True
    return {"withheld": rc062 or stops, "rc062": rc062, "gate": stops}


# C3: plain reasons for the report and the assistant (never a raw code). The UI shows the en/es/de texts of the
# i18n files through QualityGatePanel; these are the backend's English sentences for text consumers.
CAVEAT_REASONS = {
    "gate_not_approved": "the quality gate is not yet approved for use",
    "gate_switched_off": "the quality gate is switched off",
    "gate_unavailable": "the quality gate could not be completed",
    "gate_input_invalid": "the information needed to check the images is incomplete",
    "sequence_not_flair": "an image is not a FLAIR (its header names another sequence)",
    "sequence_unknown": "an image header does not say which sequence it is",
    "sequence_missing": "an image carries no sequence information",
    "sequence_confirmed_by_physician": "a physician confirmed as FLAIR an image whose header does not say so",
    "thickness_thick": "the slices are thick, so small lesions can be missed",
    "thickness_at_least": "the slices are thicker than 1.5 mm (only a lower bound is known), so small lesions can be missed",
    "thickness_unknown": "the original slice thickness cannot be read",
    "thickness_out_of_range": "the slices are thicker than the range in which the AI has been shown to work",
    "scanner_changed": "the two visits were acquired on different scanners",
    "scanner_unknown": "it cannot be established that the two visits were acquired on the same scanner",
    "skull_present": "an image still has its skull",
    "skull_unknown": "it cannot be confirmed that the skull was removed",
    "skull_pending": "the skull has not been checked yet",
    "scanner_not_recorded": "the scanners of the two visits are not recorded",
    "header_unreadable": "an image header could not be read",
}


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


def comparison_gate(source_tp1, source_tp2, *, acquisitions=None, attestation=(False, False), user=None,
                    request=None) -> Dict[str, Any]:
    """The gate on two visits from their stored records (RC-123), through the platform (RC-126). ``acquisitions``:
    the two records the route already read (E2); read here only when not given."""
    given = list(acquisitions) if acquisitions is not None else [_UNREAD, _UNREAD]
    visits = [visit_from_stored_records(s, acquisition=a, physician_confirmed_flair=att is True)
              for s, a, att in zip((source_tp1, source_tp2), given, attestation)]
    return run_quality_gate({"mode": "comparison", "visits": visits},
                            study_key=study_of(source_tp2) or study_of(source_tp1) or "",
                            actor=actor_for(user, request) if user is not None else None)
