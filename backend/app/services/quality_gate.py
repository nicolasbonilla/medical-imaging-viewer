"""Single quality gate — the agent ``quality-gate`` of the agent platform (code only, no language model).

REQ-FUNC-117, REQ-FUNC-118, REQ-SAFE-052, REQ-SAFE-053, REQ-SAFE-054; HAZ-025; RC-122..RC-127.
DRAFT, PENDING owner approval. Design and survey: docs/iec62304/agent_platform/Quality_Gate_Design.md.

ONE deterministic rule decides, before an AI step runs and again before its output is shown, whether it may
proceed. It consolidates checks that exist elsewhere and CALLS them rather than copying them:

- sequence   from the series description with ``dataset_inventory.detect_sequence`` (never the file name);
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
             or any([a, b] in vocab["flair_pairs"] for a, b in zip(tokens, tokens[1:])))
    t1 = (any(_weighted(t, vocab["t1_prefix"]) or t in vocab["t1_words"] for t in tokens)
          or any(flair_word in t and vocab["t1_prefix"] in t.replace(flair_word, "") for t in tokens))
    t2 = any(_weighted(t, vocab["t2_prefix"]) for t in tokens)
    if is_other or (flair and t1):          # a non-FLAIR name, or a T1-weighted FLAIR: ALWAYS abstains
        return "other"
    if flair:
        return "FLAIR"
    return "T1" if t1 else "T2" if t2 else "unknown"


def sequence_from_header(series_description: Any, inversion_time_ms: Any = None,
                         policy: Optional[Dict[str, Any]] = None) -> str:
    """Sequence of an image from its header text (series description) and inversion time — never the file name.

    FLAIR (only an unambiguous FLAIR, T2-FLAIR or dark-fluid name) / T1 / T2 / other (any token naming a
    non-FLAIR sequence, a T1 weighting with FLAIR, a localizer, a derived or contrast image, an inversion time
    too short for a FLAIR) / unknown (names no sequence, or only a FLAIR-compatible inversion time) / missing."""
    rules = (policy if policy is not None else _policy())["sequence"]
    tokens = sequence_tokens(series_description) if isinstance(series_description, str) else []
    ti = _number(inversion_time_ms)
    ti = ti if ti is not None and ti > 0 else None
    if not tokens and ti is None:
        return "missing"
    if ti is not None and ti < rules["min_flair_inversion_time_ms"]:
        return "other"
    return _classify_tokens(tokens, rules["vocabulary"]) if tokens else "unknown"


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
    return nib.Nifti1Image.from_file_map({"header": holder, "image": holder})


def read_header_fields(data: bytes, name: str, imaging_service) -> Dict[str, Any]:
    """Header only (E1): pydicom with stop_before_pixels, a lazy NIfTI header — no voxel is decoded, normalised
    or summarised. Series description and inversion time (DICOM), RC-054 thickness (both)."""
    from app.services.acquisition_geometry import derive_from_dicom_dataset, derive_from_nifti_image
    fmt = getattr(imaging_service.detect_format(data, name), "value", None)
    if fmt == "dicom":
        import pydicom
        ds = pydicom.dcmread(io.BytesIO(data), stop_before_pixels=True)
        return {"series_description": str(ds.get("SeriesDescription", "") or "") or None,
                "inversion_time_ms": lcs._number(getattr(ds, "InversionTime", None)),
                "thickness": thickness_from_geometry(derive_from_dicom_dataset(ds))}
    if fmt == "nifti":
        return {**_NO_HEADER, "thickness": thickness_from_geometry(derive_from_nifti_image(_nifti_header_image(data)))}
    return dict(_NO_HEADER)


async def _file_version(storage_service, bucket: str, file_path: str) -> Optional[tuple]:
    try:
        meta = await storage_service.get_file_metadata(bucket, file_path)
    except Exception:  # noqa: BLE001 — no version known: no cache
        return None
    version = (getattr(meta, "size", None), getattr(meta, "checksum_sha256", None), getattr(meta, "created_at", None))
    return (file_path, *version) if meta is not None and version[0] is not None and any(version[1:]) else None


async def single_study_inputs(file_path: str, storage_service, imaging_service, *, bucket: str,
                              physician_confirmed_flair: bool = False) -> Dict[str, Any]:
    """Gate inputs of a study opened for AI analysis, derived ON THE SERVER from the stored file: its header's
    series description and inversion time (else the stored series and acquisition records), the RC-054
    geometry. Header only, parsed off the event loop, cached per file version (E1). The skull is 'pending': the
    browser's skull gates and the app's removal decide it before the output (RC-125). Anything unreadable stays
    unknown, so the gate warns or abstains; it never raises."""
    key = await _file_version(storage_service, bucket, file_path)
    fields = _HEADER_CACHE.get(key) if key else None
    if fields is None:
        try:
            data = await storage_service.download_file(bucket, file_path)
            fields = await asyncio.to_thread(read_header_fields, data, file_path.rsplit("/", 1)[-1], imaging_service)
        except Exception:  # noqa: BLE001 — unknown header: sequence missing, thickness unknown (not cached)
            fields = dict(_NO_HEADER)
        else:
            if key:
                _HEADER_CACHE[key] = fields
                while len(_HEADER_CACHE) > HEADER_CACHE_MAX:
                    _HEADER_CACHE.popitem(last=False)
    else:
        _HEADER_CACHE.move_to_end(key)
    acq, stored = await asyncio.to_thread(
        lambda: (lcs.read_source_acquisition(file_path), read_source_series_description(file_path)))
    description = fields["series_description"] or stored
    ti = fields["inversion_time_ms"] if fields["inversion_time_ms"] is not None else (acq or {}).get("inversion_time_ms")
    return {"mode": "single", "visits": [{
        "sequence": sequence_from_header(description, ti),
        "physician_confirmed_flair": physician_confirmed_flair is True,
        "thickness": copy.deepcopy(fields["thickness"]),
        "scanner": None,
        "skull": "pending",
    }]}


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


def run_quality_gate(inputs, *, registry=None, tracer=None, study_key: str = "", actor=None,
                     trace_id: Optional[str] = None) -> Dict[str, Any]:
    """The gate as the registered agent ``quality-gate`` (RC-126): the platform's approval and kill switches are
    read now (fail closed); one trace (one child span per check that ran) and one ``agent.run`` audit record.
    The caller's ``platform`` field, if any, is ignored: only the registry decides it."""
    from app.agent_platform import registry as R
    from app.agent_platform import tracing as T

    reg = registry if registry is not None else default_registry()
    tr = tracer if tracer is not None else T.Tracer()
    policy = load_policy()
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
            attested = any(c["code"] == "sequence_confirmed_by_physician" for c in result["checks"])
            reg.audit("success", f"quality_gate.{result['decision']}" + (".physician_attested" if attested else ""),
                      event="agent.run", agent_id=AGENT_ID, study_key=study_key or None, trace_id=state["trace_id"])
    return result


# ----------------------------------------------------------------------------- comparison wiring
def apply_to_comparison(result: Dict[str, Any], gate: Dict[str, Any]) -> Dict[str, Any]:
    """Attach the gate to a longitudinal comparison; when it abstains, withhold exactly what RC-062 withholds."""
    out = dict(result)
    out["quality_gate"] = gate
    if gate.get("ai_output_allowed") is not True:
        out.update({"abstained": True, "changes": []})
        out.update({k: None for k in lcs.ABSTAINED_NULL_FIELDS})
        out["reader_confirmed_activity"] = None
        previous = out.get("caveat")       # C3: RC-062's reasons (visit dates, acquisition fields) are kept
        out["caveat"] = (previous.rstrip() + " " if isinstance(previous, str) and previous.strip() else "") + gate_caveat(gate)
    return out


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
}


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


def comparison_gate(source_tp1, source_tp2, *, acquisitions=None, user=None, request=None) -> Dict[str, Any]:
    """The gate on two visits from their stored records (RC-123), through the platform (RC-126). ``acquisitions``:
    the two records the route already read (E2); read here only when not given."""
    given = list(acquisitions) if acquisitions is not None else [_UNREAD, _UNREAD]
    visits = [visit_from_stored_records(s, acquisition=a) for s, a in zip((source_tp1, source_tp2), given)]
    return run_quality_gate({"mode": "comparison", "visits": visits},
                            study_key=study_of(source_tp2) or study_of(source_tp1) or "",
                            actor=actor_for(user, request) if user is not None else None)
