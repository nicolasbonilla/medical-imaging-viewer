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

import copy
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services import longitudinal_candidate_safety as lcs
from app.services.dataset_inventory import SEQ_FLAIR, SEQ_T1, SEQ_T2, detect_sequence

GATE_VERSION = "quality-gate/1"
AGENT_ID = "quality-gate"
POLICY_PATH = Path(__file__).with_name("quality_gate_policy.json")
DECISIONS = ("abstain", "pending", "proceed_with_warnings", "proceed")
STATUSES = ("pass", "warn", "pending", "abstain")
VISIT_LABELS = ("study", "tp1", "tp2")
# A FLAIR's inversion time is ~1600-2800 ms; T1 IR / MPRAGE ~400-1200, STIR ~150-250 (as headerEvidence.ts).
MIN_FLAIR_TI_MS = 1400.0
_T1_FLAIR = re.compile(r"t1[ _-]*w?[ _-]*flair|flair[ _-]*t1\b")
# Names of other contrasts that detect_sequence does not know (as headerEvidence.ts): never a FLAIR.
_OTHER = re.compile(r"\b(dwi|dti|adc|trace|stir|dir|psir|mra|tof|locali[sz]er|scout|gd|gado|post[ _-]?(gd|contrast))\b")

_POLICY: Optional[Dict[str, Any]] = None


def load_policy() -> Dict[str, Any]:
    """The shipped policy (a deep copy; the cached original is never handed out)."""
    global _POLICY
    if _POLICY is None:
        _POLICY = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    return copy.deepcopy(_POLICY)


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


def _sequence_check(visit, label, policy) -> Dict[str, Any]:
    rules = policy["sequence"]
    raw = visit.get("sequence")
    seq = "missing" if raw is None else (raw if isinstance(raw, str) and raw in rules["values"] else "unknown")
    if seq in rules["accepted"]:
        return _check("sequence", label, "pass")
    if seq in rules["confirmable_by_physician"]:
        if visit.get("physician_confirmed_flair") is True:
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
        checks.append(_sequence_check(visit, label, policy))
        checks.append(_thickness_check(visit, label, policy))
        if "skull" in spec["checks"] and mode in policy["skull"]["required_in_modes"]:
            checks.append(_skull_check(visit, label))
    if "scanner" in spec["checks"]:
        checks.append(_scanner_check(visits, policy))
    return _result(checks, policy, mode)


def evaluate(inputs, policy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The gate's decision for normalised inputs (see the design, section 3). Total: never raises."""
    policy = policy if policy is not None else load_policy()
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
def sequence_from_header(series_description: Any, inversion_time_ms: Any = None) -> str:
    """Sequence of an image from its header text (series description) and inversion time — never the file name.

    FLAIR / T1 / T2 / other (PD, SWI, a T1-weighted FLAIR, an inversion time too short for a FLAIR) / unknown
    (text that names no sequence, or only a FLAIR-compatible inversion time) / missing (nothing recorded)."""
    text = " ".join(series_description.split()) if isinstance(series_description, str) else ""
    ti = _number(inversion_time_ms)
    ti = ti if ti is not None and ti > 0 else None
    if not text and ti is None:
        return "missing"
    if ti is not None and ti < MIN_FLAIR_TI_MS:
        return "other"
    found = detect_sequence(text) if text else None
    if found == SEQ_FLAIR:
        return "other" if _T1_FLAIR.search(text.lower()) else "FLAIR"
    if found in (SEQ_T1, SEQ_T2):
        return found
    return "other" if found or _OTHER.search(text.lower()) else "unknown"


def thickness_from_geometry(geometry: Any) -> Optional[Dict[str, Any]]:
    """The thickness input from an RC-054 AcquisitionGeometry (model or dict); None when absent."""
    if geometry is None:
        return None
    get = geometry.get if isinstance(geometry, dict) else (lambda k: getattr(geometry, k, None))
    return {"state": get("state"), "effective_mm": get("effective_mm")}


def thickness_from_acquisition_record(acq: Optional[dict]) -> Optional[Dict[str, Any]]:
    """The thickness input from a stored acquisition record (PACS import). The record does not say whether the
    image is ORIGINAL, so it is at most a lower bound (as RC-054 treats a derived image): at_least above 1.5 mm,
    otherwise not determinable."""
    if not isinstance(acq, dict):
        return None
    values = [lcs._number(acq.get(k)) for k in ("slice_thickness_mm", "spacing_between_slices_mm")]
    if values[0] is None:
        return {"state": "not_determinable", "effective_mm": None}
    mm = max(v for v in values if v is not None)
    if mm > load_policy()["thickness"]["thin_limit_mm"]:
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


def visit_from_stored_records(file_id, *, skull: str = "unknown", physician_confirmed_flair: bool = False,
                              study_service=None) -> Dict[str, Any]:
    """Gate inputs of one visit from the records stored with its source image (comparison mode)."""
    acq = lcs.read_source_acquisition(file_id, study_service) if file_id else None
    description = read_source_series_description(file_id, study_service) if file_id else None
    return {
        "sequence": sequence_from_header(description, (acq or {}).get("inversion_time_ms")),
        "physician_confirmed_flair": physician_confirmed_flair is True,
        "thickness": thickness_from_acquisition_record(acq),
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
            result["trace_id"] = state.get("trace_id")
            reg.audit("failure", R.RefusalCode.RUN_INTERNAL_ERROR, event="agent.run", agent_id=AGENT_ID,
                      study_key=study_key or None, trace_id=state.get("trace_id"))
            return result
        result["trace_id"] = state["trace_id"]
        if state["refusal"]:
            reg.audit("denied", state["refusal"], event="agent.run", agent_id=AGENT_ID,
                      study_key=study_key or None, trace_id=state["trace_id"])
        else:
            reg.audit("success", f"quality_gate.{result['decision']}", event="agent.run", agent_id=AGENT_ID,
                      study_key=study_key or None, trace_id=state["trace_id"])
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
    return out
