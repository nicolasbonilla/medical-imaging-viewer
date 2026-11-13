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
- skull      the outcome of the skull gates / skull removal as the in-browser pipeline REPORTS it (client-reported:
             the server cannot verify it; RC-043 / RC-049 in the browser are the real controls; twelfth review, K4).

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
import base64
import copy
import hashlib
import hmac
import io
import json
import logging
import math
import os
import re
import secrets
import threading
import time
from collections import OrderedDict
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, StrictBool

from app.services import longitudinal_candidate_safety as lcs
from app.services import nifti_header

logger = logging.getLogger(__name__)

GATE_VERSION = "quality-gate/1"
AGENT_ID = "quality-gate"
POLICY_PATH = Path(__file__).with_name("quality_gate_policy.json")
DECISIONS = ("abstain", "pending", "proceed_with_warnings", "proceed")
STATUSES = ("pass", "warn", "pending", "abstain")
VISIT_LABELS = ("study", "tp1", "tp2")
# Tokeniser of a series description (first review of PR #81, S1/S2): no word-boundary regex — '_' is a word
# character for \b, so 'AX_DWI_B1000' was read as naming no sequence.
_CAMEL = re.compile(r"([a-z])([A-Z])")
_PLUS_C = re.compile(r"\+\s*[cC](?![A-Za-z])")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_LETTERS = re.compile(r"[a-z]*")

_POLICY: Optional[Dict[str, Any]] = None


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


def _policy() -> Dict[str, Any]:
    """The shipped policy, cached and read only (no copy per call; E3). Twelfth review (O4): its vocabulary is
    IMMUTABLE, so the word sets built from it can never go stale."""
    global _POLICY
    if _POLICY is None:
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        policy["sequence"]["vocabulary"] = _freeze(policy["sequence"]["vocabulary"])
        _POLICY = policy
    return _POLICY


def load_policy() -> Dict[str, Any]:
    """A fresh, changeable copy of the shipped policy, for a caller that changes it (the cached one is never handed
    out)."""
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------- the rule (pure)
def _check(check: str, visit: Optional[str], status: str, code: Optional[str] = None, **params) -> Dict[str, Any]:
    return {"check": check, "visit": visit, "status": status, "code": code, "params": params}


def _number(v) -> Optional[float]:
    """A positive finite number, through the ONE number parser (lcs._number), strict on types: the gate's inputs are
    normalised, so a text or a boolean is never a number here (seventh review of PR #81, cleanup)."""
    return lcs._number(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


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


def _result(checks: List[Dict[str, Any]], policy, mode=None, rc062_withholds: Any = None) -> Dict[str, Any]:
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
        "attestable_visits": _attestable_visits(checks, policy, mode, rc062_withholds),
        "actions": {c["code"]: _action_key(policy, mode, c["code"]) for c in checks if c["code"]},
    }


def _attestable_visits(checks: List[Dict[str, Any]], policy, mode, rc062_withholds: Any = None) -> List[str]:
    """G28 (seventh review of PR #81): the visits whose FLAIR the physician may attest — offered ONLY when the
    attestation changes the decision: every abstaining check is a sequence check that the attestation lifts
    (unknown / missing, in a mode where it is offered). Anything else that abstains (an unreadable header, a scanner
    change, a skull, the platform) makes an attestation futile, so none is offered and no useless record is written."""
    if mode == "comparison" and (rc062_withholds is not False
                                 or any(c["code"] == "scanner_not_recorded" for c in checks)):
        return []      # G32 (eighth review): RC-062 will withhold the pair anyway, or its verdict is not predicted
    abstaining = [c for c in checks if c["status"] == "abstain"]
    liftable = [c for c in abstaining if c["check"] == "sequence" and c["code"] in ("sequence_unknown", "sequence_missing")
                and mode in policy["sequence"]["confirmation_modes"]]
    return [c["visit"] for c in liftable] if abstaining and len(liftable) == len(abstaining) else []


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
    rc062 = inputs.get("rc062_withholds")
    mode, visits = inputs.get("mode"), inputs.get("visits")
    spec = policy["modes"].get(mode) if isinstance(mode, str) else None
    if (spec is None or not isinstance(visits, list) or len(visits) != len(spec["visits"])
            or not all(isinstance(v, dict) for v in visits)):
        return _result([platform, _check("input", None, "abstain", "gate_input_invalid")], policy)
    checks = [platform]
    for label, visit in zip(spec["visits"], visits):
        if visit.get("header") == "no_source":         # G35 (ninth review): the TRUE reason, and nothing else
            checks.append(_check("input", label, policy["codes"]["source_image_missing"], "source_image_missing"))
            continue
        if visit.get("header") == "unreadable":        # the header could not be read at all (third review)
            checks.append(_check("input", label, policy["codes"]["header_unreadable"], "header_unreadable"))
        checks.append(_sequence_check(visit, label, policy, mode))
        checks.append(_thickness_check(visit, label, policy))
        if "skull" in spec["checks"] and mode in policy["skull"]["required_in_modes"]:
            checks.append(_skull_check(visit, label))
    if "scanner" in spec["checks"]:
        checks.append(_scanner_check(visits, policy))
    if mode == "single" and inputs.get("version_established") is False:
        # K3 (fourteenth review): no stored-file version, no run permission — a stop with its reason, never a dead end
        checks.append(_check("version", "study", policy["codes"]["version_not_established"], "version_not_established"))
    if mode == "single" and inputs.get("run_confirmed") is False:
        # thirteenth review (M1, P2): a final consultation that presents no valid run token of THIS run releases nothing
        checks.append(_check("run", "study", policy["codes"]["run_not_confirmed"], "run_not_confirmed"))
    return _result(checks, policy, mode, rc062_withholds=rc062)


def evaluate(inputs, policy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The gate's decision for normalised inputs (see the design, section 3). Total: never raises."""
    policy = policy if policy is not None else _policy()
    try:
        return _evaluate(inputs, policy)
    except Exception:  # noqa: BLE001 — a fault in the gate is an abstention, never a pass
        return _result([_check("input", None, "abstain", "gate_input_invalid")], policy)


def canonical(result: Dict[str, Any]) -> str:
    """The decision as one line: decision|codes|check@visit:status:code[param];..."""
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


COMPILED_MAX = 8
_COMPILED: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
_FROZEN_KEYS: Dict[int, tuple] = {}


def _vocab_key(vocab) -> str:
    """O4 (twelfth review): the cache key is the vocabulary's CONTENT, so a vocabulary changed in place never reuses
    stale word sets; the immutable shipped vocabulary's digest is computed once (it cannot change)."""
    if isinstance(vocab, MappingProxyType):
        hit = _FROZEN_KEYS.get(id(vocab))
        if hit is not None and hit[0] is vocab:
            return hit[1]
    plain = lambda v: dict(v) if isinstance(v, MappingProxyType) else list(v)  # noqa: E731
    key = hashlib.sha256(json.dumps(vocab, sort_keys=True, default=plain).encode("utf-8")).hexdigest()
    if isinstance(vocab, MappingProxyType):
        _FROZEN_KEYS[id(vocab)] = (vocab, key)
    return key


def _compiled(vocab: Dict[str, Any]) -> Dict[str, Any]:
    """The vocabulary's word sets and its inversion-time regex, built once per vocabulary CONTENT (fifth review,
    cleanup; twelfth review, O4: keyed by a content digest, at most COMPILED_MAX kept)."""
    key = _vocab_key(vocab)
    hit = _COMPILED.get(key)
    if hit is not None:
        _COMPILED.move_to_end(key)
        return hit
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
    _COMPILED[key] = c
    while len(_COMPILED) > COMPILED_MAX:
        _COMPILED.popitem(last=False)
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
    """The ONE sequence classifier of the product, FIELD-AWARE (third review of PR #81, G19): the SERIES-level
    description (``description``: a text or a list — SeriesDescription, NIfTI descrip, the stored series description)
    by its tokens, ``sequence_name`` by the vendor-code table, ``image_type`` by its own list. Any of them naming a
    non-FLAIR sequence decides (other / T1 / T2); else a FLAIR name; else unknown; nothing at all = missing.

    Tenth review (S2, G33 extended): ``protocol_name`` is EXAM-level for some vendors (GE writes the examination's
    protocol there, "BRAIN W WO CONTRAST"), so it never vetoes a series: it may support a FLAIR when the series fields
    are silent, and anything else it says leaves the series unknown (the physician may attest) — never 'other'."""
    policy = policy if policy is not None else _policy()
    rules = policy["sequence"]
    vocab = rules["vocabulary"]
    desc = fields.get("description")
    texts = [t for t in (desc if isinstance(desc, (list, tuple)) else [desc]) if isinstance(t, str)]
    exam = [t for t in (fields.get("protocol_name"),) if isinstance(t, str) and sequence_tokens(t)]
    ti = _number(inversion_time_ms)
    ti = ti if ti is not None and ti > 0 else next(
        (v for v in (text_inversion_time_ms(t, policy) for t in texts) if v is not None), None)
    tokens_per_text = [sequence_tokens(t) for t in texts]
    per_text = [_classify_tokens(tk, vocab) for tk in tokens_per_text if tk]       # one weighting routine
    classes = [cls for cls, _, _ in per_text]
    classes += [c for c in (_sequence_name_class(fields.get("sequence_name"), vocab),
                            _image_type_class(fields.get("image_type"), vocab)) if c]
    if exam and not any(c in ("other", "T1", "T2", "FLAIR") for c in classes):   # the series is silent (S2)
        classes.append("FLAIR" if _classify_tokens(sequence_tokens(exam[0]), vocab)[0] == "FLAIR" else "unknown")
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
    (SWI/PD)."""
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
    """The series description stored for a source image's series (PACS import), or None. Never raises. Ninth review of
    PR #81 (G34): IMAGE-LEVEL only — a description copied from the STUDY (marked series_description_source = "study",
    or equal to the study's study_description) is not the series' own and is ignored."""
    try:
        refs = lcs.source_refs(file_id, study_service)
        if refs is None:
            return None
        study, series = refs
        doc = series.get()
        data = (doc.to_dict() or {}) if getattr(doc, "exists", False) else {}
        value = data.get("series_description")
        if not isinstance(value, str) or not value.strip() or data.get("series_description_source") == "study":
            return None
        study_doc = study.get()
        study_desc = (study_doc.to_dict() or {}).get("study_description") if getattr(study_doc, "exists", False) else None
        same = isinstance(study_desc, str) and " ".join(study_desc.split()).lower() == " ".join(value.split()).lower()
        return None if same else value
    except Exception:  # noqa: BLE001 — unknown description: the sequence is "missing", the gate abstains
        return None


def study_of(file_id) -> Optional[str]:
    """The study id in a source image's storage path (for the pseudonymised study key), or None."""
    m = lcs._FILE_ID_RE.fullmatch(str(file_id or ""))
    return m.group(1) if m else None


_NO_HEADER = {"descriptions": [], "protocol_name": None, "sequence_name": None, "image_type": None,
              "inversion_time_ms": None, "thickness": None, "voxel_spacing_mm": None}
_HEADER_CACHE: "OrderedDict[tuple, Dict[str, Any]]" = OrderedDict()
HEADER_CACHE_MAX = 256


def _nifti_header_image(data: bytes, decoded: Optional[bytes] = None):
    """A NIfTI image whose header is read and whose voxels are NOT (nibabel's lazy array proxy). ``decoded``: the
    prefix already decompressed by the reader (E1, eighth review: one decompression per round)."""
    import nibabel as nib
    raw = decoded if decoded is not None else nifti_header.header_prefix(data)
    holder = nib.FileHolder(fileobj=io.BytesIO(raw))
    klass = nib.Nifti2Image if nifti_header.sizeof_hdr(raw)[0] == 540 else nib.Nifti1Image
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


def read_header_fields(data: bytes, decoded: Optional[bytes] = None) -> Dict[str, Any]:
    """Header only (E1): pydicom with stop_before_pixels, a lazy NIfTI header — no voxel is decoded, normalised
    or summarised. Descriptions, ProtocolName, SequenceName, ImageType and inversion time (DICOM, and NIfTI with
    its text fields and extensions — A1), RC-054 thickness (both)."""
    from app.services.acquisition_geometry import derive_from_dicom_dataset, derive_from_nifti_image
    fmt = sniff_format(data, decoded)                # magic bytes, never the file name (third review, other 1)
    if fmt == "dicom":
        import pydicom
        ds = pydicom.dcmread(io.BytesIO(data), stop_before_pixels=True, force=True)
        # S3 (tenth review): RC-062 loads a source image with the NIfTI loader only, so a DICOM source has no RC-062
        # spacing at run time — none is predicted for it here (RC-062 will withhold the pair)
        return {**_dicom_fields(ds), "thickness": thickness_from_geometry(derive_from_dicom_dataset(ds)),
                "voxel_spacing_mm": None}
    if fmt == "nifti":
        img = _nifti_header_image(data, decoded)
        # S3: the SAME helper, axis order and 3-D check as RC-062 at run time (_load_source_intensity)
        return {**_nifti_fields(img), "thickness": thickness_from_geometry(derive_from_nifti_image(img)),
                "voxel_spacing_mm": lcs.rc062_voxel_spacing(img)}
    return {**_NO_HEADER, "unreadable": True}


HEADER_PREFIX_NIFTI = 4096        # compressed bytes: the 348-byte header (+ extensions) of a NIfTI
HEADER_PREFIX_DICOM = 65536       # a bounded DICOM prefix, read with stop_before_pixels
HEADER_PREFIX_MAX = 4 * 1024 * 1024
_PIXEL_DATA_TAGS = (b"\xe0\x7f\x10\x00", b"\x7f\xe0\x00\x10")


NIFTI_DECOMPRESSED_MAX = nifti_header.DECOMPRESSED_MAX   # O1 (twelfth review): header + extensions, at most 16 MiB


def sniff_format(data: bytes, decoded: Optional[bytes] = None) -> Optional[str]:
    """The format from MAGIC BYTES only (third review, other 1): NIfTI sizeof_hdr 348/540 (raw or gzip), DICOM 'DICM' at
    128 or a preamble-less file starting with an explicit-VR group 0002/0008 element. None = not determinable.
    ``decoded``: the prefix the reader already decompressed (E1, eighth review: never decompressed twice)."""
    if nifti_header.sizeof_hdr(decoded if decoded is not None else nifti_header.header_prefix(data))[0]:
        return "nifti"
    if data[128:132] == b"DICM":
        return "dicom"
    if len(data) >= 8 and data[0:2] in (b"\x02\x00", b"\x08\x00") and data[4:6].isalpha() and data[4:6].isupper():
        return "dicom"
    return None


def _inspect_header_prefix(data: bytes):
    """One round of the ranged reader (E1, eighth review): decompress the prefix ONCE and say whether it holds the
    whole header — DICOM: the pixel data starts inside it; NIfTI: the header plus the extensions up to vox_offset.
    Returns (complete, (prefix, decompressed NIfTI prefix or None)) so the parser never decompresses again."""
    import struct
    raw = nifti_header.header_prefix(data)                        # the ONE decompression of this round
    fmt = sniff_format(data, raw)
    if fmt == "dicom":
        return any(tag in data for tag in _PIXEL_DATA_TAGS), (data, None)
    if fmt != "nifti":
        return False, (data, raw)
    size, endian = nifti_header.sizeof_hdr(raw)
    if size is None or len(raw) < size + 4:
        return False, (data, raw)
    if raw[size] == 0:
        return True, (data, raw)
    vox_offset = (struct.unpack(endian + "f", raw[108:112])[0] if size == 348
                  else struct.unpack(endian + "q", raw[168:176])[0])
    return len(raw) >= vox_offset, (data, raw)


async def _read_header_fields(storage_service, bucket: str, file_path: str) -> Dict[str, Any]:
    """E1 / second review, finding 3 / eighth review: the header only, through the ONE ranged header reader of the
    app (displayed_image_check.read_header_prefix: bounded ranges, retried larger while the header runs longer, one
    full download from a storage without real ranges); each round is decompressed once, in a worker thread, and the
    decompressed bytes are passed down to the parser."""
    from app.services.displayed_image_check import read_header_prefix
    name = file_path.rsplit("/", 1)[-1]
    first = HEADER_PREFIX_NIFTI if name.lower().endswith((".nii", ".nii.gz")) else HEADER_PREFIX_DICOM
    data, decoded = await read_header_prefix(storage_service, bucket, file_path, _inspect_header_prefix,
                                             first=first, largest=HEADER_PREFIX_MAX, in_thread=True)
    return await asyncio.to_thread(read_header_fields, data, decoded)


async def file_version(storage_service, bucket: str, file_path: str) -> Optional[tuple]:
    """(file, size, checksum, created) of the stored file, or None when its version is unknown (nothing is cached)."""
    try:
        meta = await storage_service.get_file_metadata(bucket, file_path)
    except Exception:  # noqa: BLE001 — no version known: no cache
        return None
    version = (getattr(meta, "size", None), getattr(meta, "checksum_sha256", None), getattr(meta, "created_at", None))
    return (file_path, *version) if meta is not None and version[0] is not None and any(version[1:]) else None


_NOT_GIVEN = object()


async def visit_header_fields(storage_service, bucket: str, file_path: str, *,
                              version_key: Any = _NOT_GIVEN) -> Dict[str, Any]:
    """The header fields of one stored image, cached per file version (E1) — the ONE cache of the gate (tenth review,
    S1); an unreadable header is an explicit 'unreadable' (never 'missing'). Used by the single study AND by each visit
    of a comparison (A1)."""
    key = version_key if version_key is not _NOT_GIVEN else await file_version(storage_service, bucket, file_path)
    fields = _HEADER_CACHE.get(key) if key else None
    if fields is not None:
        _HEADER_CACHE.move_to_end(key)
        return fields
    try:
        fields = await _read_header_fields(storage_service, bucket, file_path)
    except Exception:  # noqa: BLE001 — the header could not be read: an explicit code, never 'missing'
        fields = {**_NO_HEADER, "unreadable": True}
    if key and not fields.get("unreadable"):          # S1: a failed or unreadable read is NEVER remembered
        _HEADER_CACHE[key] = fields
        while len(_HEADER_CACHE) > HEADER_CACHE_MAX:
            _HEADER_CACHE.popitem(last=False)
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
    if not isinstance(thickness, dict) or thickness.get("state") == "not_determinable":
        # R2 (seventh review): the record's thickness (a lower bound) when the header cannot tell
        recorded = thickness_from_acquisition_record(acq, policy["thickness"]["thin_limit_mm"])
        thickness = recorded if recorded is not None else thickness
    return {
        **({"header": "no_source"} if fields.get("no_source") else {"header": "unreadable"} if fields.get("unreadable") else {}),
        "sequence": classify_fields(header_classifier_fields(fields, stored_description), ti, policy)["class"],
        "physician_confirmed_flair": physician_confirmed_flair is True,
        "thickness": dict(thickness) if isinstance(thickness, dict) else None,
        "scanner": scanner_from_acquisition_record(acq) if with_scanner else None,
        "skull": skull,
    }


def stored_records(file_path: str, study_service=None):
    """(acquisition record, stored series description) of a source image; never raises (unknown = None). Two
    document reads (E1, seventh review): one instance document by query, and the series document."""
    return (lcs.read_source_acquisition(file_path, study_service),
            read_source_series_description(file_path, study_service))


async def single_study_inputs(file_path: str, storage_service, *, bucket: str,
                              physician_confirmed_flair: bool = False, skull: str = "pending"):
    """Gate inputs of a study opened for AI analysis, derived ON THE SERVER from the stored file (visit_inputs) — except
    the skull outcome, which the in-browser pipeline reports (client-reported, K4):
    its header, else the stored series and acquisition records, and the RC-054 geometry. Header only, parsed off the
    event loop, cached per file version (E1). Anything unreadable stays unknown, so the gate warns or abstains; it
    never raises. Returns (inputs, file version or None). Every consultation is evaluated (tenth review, S1): the
    header (file version, then the header cache or a ranged read) and the stored records are read concurrently.

    ``skull``: 'pending' before the run; at the final consultation the outcome the browser reports ('stripped' /
    'unknown'), so the decision that releases or withholds the output is decided and audited here (G17)."""
    async def header():
        version = await file_version(storage_service, bucket, file_path)
        return version, await visit_header_fields(storage_service, bucket, file_path, version_key=version)

    (key, fields), (acq, stored) = await asyncio.gather(header(), asyncio.to_thread(stored_records, file_path))
    visit = visit_inputs(fields, acq, stored, physician_confirmed_flair=physician_confirmed_flair, skull=skull)
    return {"mode": "single", "visits": [visit]}, version_text(key)


def version_text(key: Optional[tuple]) -> Optional[str]:
    """A stored file's version as text (size:checksum:created), or None when unknown — the subject of an answer and
    the version a signed token binds."""
    return ":".join(str(v) for v in key[1:]) if key else None


def actor_for(user, request=None):
    """The authenticated clinician as the platform's audit actor (never anonymous, CAPA-015)."""
    from app.agent_platform.registry import AuditActor
    role = getattr(user, "role", None)
    return AuditActor(user_id=str(getattr(user, "id", "") or ""), username=getattr(user, "username", None),
                      role=str(getattr(role, "value", role)) if role is not None else None, request=request)


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


# Tenth review of PR #81 (S1): ONE per-user limit, checked before any authorization, storage or Firestore read; there
# is no consultation cache any more, so every consultation is a real evaluation and every one counts
RATE_LIMIT_PER_MINUTE = 60
_LIMITER = None


def new_rate_limiter():
    from app.core.security.rate_limiter import RateLimiter
    return RateLimiter(redis_client=None, default_limit=RATE_LIMIT_PER_MINUTE, default_window=60)


def rate_limit(user_id: str) -> Optional[int]:
    """The ONE rate limit of the gate's consultations, per user, with the platform's rate limiter: None when allowed,
    else the seconds to wait. KNOWN LIMITATION: the limiter is per server instance (in memory), so N instances allow up
    to N times the limit (Quality_Gate_Design.md)."""
    global _LIMITER
    from app.core.security.rate_limiter import RateLimitScope
    if _LIMITER is None:
        _LIMITER = new_rate_limiter()
    allowed, meta = _LIMITER.check_rate_limit(f"quality_gate:{user_id}", limit=RATE_LIMIT_PER_MINUTE, window=60,
                                              scope=RateLimitScope.PER_USER, user_id=user_id)
    if allowed:
        return None
    # S5 (fifteenth review): the limiter's own remaining time, rounded UP in ONE place — the limiter's in-memory window
    # (the gate's only one), where a blocked request always has 1..window seconds left. No second rounding or clamp
    # here: the full negative-control pass showed it could never act (AH11, retired)
    return int(meta["retry_after"])


def rate_limited_response(wait: int, code: str = "gate_rate_limited"):
    """The ONE 429 answer of the gate: the seconds to wait in Retry-After and as data (code gate_rate_limited; K2,
    fourteenth review: gate_run_in_progress while the same final consultation is still being decided)."""
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=429, headers={"Retry-After": str(wait)}, content={"error": {
        "code": "HTTP_429", "message": "Too many quality-gate checks; try again shortly",
        "details": {"code": code, "retry_after_s": wait}}})


# ----------------------------------------------------------------------------- signed decisions (twelfth review)
# K1/K2: every comparison / SEL decision is returned with a compact token signed with HMAC-SHA256, binding the pair
# (both segmentation ids, source files and versions), the clinician, the decision, its causes and warnings, the policy
# version, the issue time and the expiry. The report verifies it — across instances and restarts, nothing is kept in
# memory. K5: the consultation that allows a run returns a single-use run token; only a final consultation presenting
# it (same file, version, clinician and attestation) is recorded as the AI run.
TOKEN_PREFIX = "qg1"
DECISION_TOKEN_TTL_S = 24 * 3600
RUN_TOKEN_TTL_S = 2 * 3600
# M2 (thirteenth review) / K2 (fourteenth) / S1 (fifteenth review): the run-token LEDGER — the idempotency-key
# pattern with ONE document per token (request_digest, state claimed | decided, claimed_at, attempt, decision),
# changed ONLY inside a transaction (Firestore: a transaction on the token's document; memory: under a lock).
# A final consultation CLAIMS the token with a digest of its request; the gate is then evaluated WITHOUT any audit;
# the decision is SETTLED in the document; only then is it audited and answered. The identical request within the
# token's lifetime REPLAYS the stored decision (a lost answer: never re-evaluated, never more permissive, audited as a
# replay); another request is refused (run_not_confirmed); a claim whose evaluation or settlement failed is released
# (retryable at once by the same request); an abandoned claim is taken over INSIDE the transaction after
# RUN_CLAIM_LEASE_S; while a live claim is being decided, the same request is asked to wait (429 gate_run_in_progress).
# Full or unreachable: FAIL CLOSED — no release, logged. Every call is blocking I/O: off the event loop (K5).
RUN_TOKEN_COLLECTION = "quality_gate_run_tokens"
RUN_TOKENS_SPENT_MAX = 100_000
RUN_CLAIM_LEASE_S = 30
_RUN_TOKEN_MEMORY = None


class RunClaim:
    """The ledger's answer to a final consultation's run token. ``status``: invalid | unavailable | fresh | replay |
    in_progress | conflict. (A plain class: this module is also loaded outside sys.modules, as a restart.)"""

    __slots__ = ("status", "key", "digest", "expires_at", "answer", "wait_s", "attempt")

    def __init__(self, status: str, key: Optional[str] = None, digest: Optional[str] = None, expires_at: int = 0,
                 answer: Optional[Dict[str, Any]] = None, wait_s: int = 0, attempt: int = 0):
        self.status, self.key, self.digest, self.expires_at, self.answer, self.wait_s, self.attempt = (
            status, key, digest, expires_at, answer, wait_s, attempt)


def _claim_step(doc, digest: str, expires_at: int, now: float):
    """The claim, on the token's document as read in the transaction: (document to write or None, RunClaim)."""
    if doc is None:
        return ({"request_digest": digest, "state": "claimed", "claimed_at": float(now), "attempt": 1,
                 "decision": None, "expires_at": int(expires_at)}, RunClaim("fresh", attempt=1))
    if doc.get("request_digest") != digest:
        return None, RunClaim("conflict")
    if doc.get("state") == "decided":
        return None, RunClaim("replay", answer=copy.deepcopy(doc.get("decision")))
    elapsed = now - float(doc.get("claimed_at") or 0.0)
    if elapsed >= RUN_CLAIM_LEASE_S:                     # released (claimed_at 0) or abandoned: taken over HERE
        attempt = int(doc.get("attempt") or 0) + 1
        return {**doc, "claimed_at": float(now), "attempt": attempt}, RunClaim("fresh", attempt=attempt)
    return None, RunClaim("in_progress", wait_s=max(1, int(math.ceil(RUN_CLAIM_LEASE_S - elapsed))))


def _settle_step(doc, digest: str, attempt: int, answer: Dict[str, Any]):
    """Settle a fresh claim's decision: the first decision stands; an attempt that no longer holds the claim settles
    nothing (None: the caller fails closed)."""
    if doc is None or doc.get("request_digest") != digest:
        return None, None
    if doc.get("state") == "decided":
        return None, copy.deepcopy(doc.get("decision"))
    if int(doc.get("attempt") or 0) != attempt:
        return None, None
    return {**doc, "state": "decided", "decision": copy.deepcopy(answer)}, copy.deepcopy(answer)


def _release_step(doc, digest: str, attempt: int):
    """A claim whose evaluation or settlement failed: retryable AT ONCE by the same request (claimed_at 0)."""
    if (doc is not None and doc.get("request_digest") == digest and doc.get("state") == "claimed"
            and int(doc.get("attempt") or 0) == attempt):
        return {**doc, "claimed_at": 0.0}, None
    return None, None


class MemoryDocs:
    """The token documents in memory (QUALITY_GATE_RUN_TOKEN_STORE=memory: offline tests only): bounded, never forgets
    an unexpired document (full: raises). ``faults`` (tests only) is called at each external call — ("read") and
    ("write", apply) — to inject a failure there."""

    def __init__(self, max_entries: Optional[int] = None, faults=None):
        self._docs: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        self._lock = threading.Lock()
        self._max = max_entries if max_entries is not None else RUN_TOKENS_SPENT_MAX
        self._faults = faults

    def _call(self, kind: str, apply=None):
        if self._faults is not None:
            return self._faults(kind, apply)
        return apply() if apply is not None else None

    def peek(self, key: str) -> Optional[Dict[str, Any]]:
        return copy.deepcopy(self._docs.get(key))

    def transact(self, key: str, step, now: float):
        from app.security.agent_scope import AgentScopeError
        with self._lock:
            while self._docs and next(iter(self._docs.values()))["expires_at"] <= now:
                self._docs.popitem(last=False)                  # same lifetime: the oldest expire first
            self._call("read")
            new, result = step(copy.deepcopy(self._docs.get(key)))
            if new is not None:
                if key not in self._docs and len(self._docs) >= self._max:
                    raise AgentScopeError("run token ledger full")
                self._call("write", lambda: self._docs.__setitem__(key, copy.deepcopy(new)))
            return result


class FirestoreDocs:
    """The token documents in Firestore (`quality_gate_run_tokens`, one per token): read and written in ONE Firestore
    transaction on the token's document; `ttl` (a timestamp) lets a TTL policy delete it after its expiry."""

    COLLECTION = RUN_TOKEN_COLLECTION

    def __init__(self, client=None):
        self._client = client

    def transact(self, key: str, step, now: float):
        from datetime import datetime, timedelta, timezone
        from google.cloud import firestore
        client = self._client
        if client is None:
            from app.core.firebase import get_firestore_client
            client = get_firestore_client()
        ref = client.collection(self.COLLECTION).document(key)

        @firestore.transactional
        def run(tx):
            snap = ref.get(transaction=tx)
            doc = snap.to_dict() if snap.exists else None
            if doc is not None:
                doc.pop("ttl", None)
            new, result = step(doc)
            if new is not None:
                ttl = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=min(int(new["expires_at"]), 253402300799))
                tx.set(ref, {**new, "ttl": ttl})
            return result
        return run(client.transaction())


class RunLedger:
    """The run-token ledger over ONE document per token (S1, fifteenth review)."""

    def __init__(self, docs):
        self.docs = docs

    def claim(self, key: str, digest: str, expires_at: int, now: float) -> RunClaim:
        return self.docs.transact(key, lambda doc: _claim_step(doc, digest, expires_at, now), now)

    def settle(self, claim: "RunClaim", answer: Dict[str, Any], now: float) -> Optional[Dict[str, Any]]:
        return self.docs.transact(claim.key, lambda doc: _settle_step(doc, claim.digest, claim.attempt, answer), now)

    def release(self, claim: "RunClaim", now: float) -> None:
        self.docs.transact(claim.key, lambda doc: _release_step(doc, claim.digest, claim.attempt), now)


def _run_token_store() -> RunLedger:
    global _RUN_TOKEN_MEMORY
    if os.environ.get("QUALITY_GATE_RUN_TOKEN_STORE") == "memory":
        if _RUN_TOKEN_MEMORY is None:
            _RUN_TOKEN_MEMORY = RunLedger(MemoryDocs(max_entries=RUN_TOKENS_SPENT_MAX))
        return _RUN_TOKEN_MEMORY
    return RunLedger(FirestoreDocs())


def _now() -> float:
    return time.time()


def _token_key() -> Optional[bytes]:
    """The HMAC-SHA256 key of the gate's tokens: the DEDICATED secret QUALITY_GATE_TOKEN_SECRET (settings / Secret
    Manager). Without it, a key DERIVED from the server secret for this purpose only (HMAC-SHA256 with a domain label,
    as the audit's identifier hash does) — the JWT signing key itself is never used as this key. None when neither is
    configured: nothing is signed or accepted (every report: not established)."""
    from app.core.config import get_settings
    settings = get_settings()
    dedicated = getattr(settings, "QUALITY_GATE_TOKEN_SECRET", "") or ""
    if dedicated:
        return dedicated.encode("utf-8")
    base = getattr(settings, "SECRET_KEY", "") or ""
    return hmac.new(base.encode("utf-8"), b"mstool-quality-gate-token-v1", hashlib.sha256).digest() if base else None


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _sign(key: bytes, body: str) -> str:
    return _b64(hmac.new(key, f"{TOKEN_PREFIX}.{body}".encode("ascii"), hashlib.sha256).digest())


def sign_token(payload: Dict[str, Any]) -> Optional[str]:
    key = _token_key()
    if key is None:
        return None
    body = _b64(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return f"{TOKEN_PREFIX}.{body}.{_sign(key, body)}"


def verify_token(token: Any, kind: str) -> Optional[Dict[str, Any]]:
    """The payload of a token this server signed, of this kind and not expired; None for anything else. Never raises."""
    try:
        key = _token_key()
        if key is None or not isinstance(token, str) or len(token) > 8192:
            return None
        prefix, body, sig = token.split(".")
        if prefix != TOKEN_PREFIX or not hmac.compare_digest(_sign(key, body), sig):
            return None
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        exp = payload.get("exp") if isinstance(payload, dict) else None
        if payload.get("kind") != kind or isinstance(exp, bool) or not isinstance(exp, (int, float)) or exp <= _now():
            return None
        return payload
    except Exception:  # noqa: BLE001 — not a token of this server
        return None


def decision_token(gate: Dict[str, Any], pair: Dict[str, Any], user_id: Any) -> Optional[str]:
    """K1/K2: the signed, pair-bound record of a comparison / SEL decision this server returned."""
    account, now = explain(gate), int(_now())
    return sign_token({"kind": "decision", "pair": pair, "user": str(user_id or ""), "decision": gate.get("decision"),
                       "ai_output_allowed": gate.get("ai_output_allowed") is True, "causes": account["causes"],
                       "warnings": account["warnings"], "policy_version": gate.get("policy_version"),
                       "iat": now, "exp": now + DECISION_TOKEN_TTL_S})


def report_account(longitudinal: Any, user_id: Any) -> Optional[Dict[str, Any]]:
    """I1 / K1 / K2: the gate's account of a report's longitudinal block, from the SIGNED decision only — its
    decision, causes and warnings; the client's copy gives nothing else. None while the gate is not enforced (the base
    report). A missing, forged, expired or tampered token, one signed for another pair than the block's, or (M3,
    thirteenth review) for another clinician than the one requesting the report: the comparability is NOT established
    by the gate — a stop with a plain note (gate_not_established), never a clean comparison. The ONE hook of the report
    path (when PR #78 lands, its notice moves into the verified report)."""
    from app.core.config import get_settings
    if not get_settings().QUALITY_GATE_ENFORCED or not isinstance(longitudinal, dict):
        return None
    block = longitudinal.get("quality_gate")
    payload = verify_token(block.get("token") if isinstance(block, dict) else None, "decision")
    if (payload is None or not isinstance(payload.get("pair"), dict) or payload["pair"] != longitudinal.get("pair")
            or not str(user_id or "") or payload.get("user") != str(user_id or "")):
        return {"established": False, "stopped": True, "causes": ["gate_not_established"], "warnings": []}
    codes = lambda v: [c for c in v if isinstance(c, str)] if isinstance(v, list) else []  # noqa: E731
    stopped = payload.get("ai_output_allowed") is not True
    return {"established": True, "stopped": stopped, "causes": codes(payload.get("causes")) if stopped else [],
            "warnings": codes(payload.get("warnings"))}


def run_token(file_id: str, version: Optional[str], user_id: Any, attested: bool) -> Optional[str]:
    """K5: the single-use token of a consultation that allows a run, for this file version, clinician and attestation."""
    now = int(_now())
    return sign_token({"kind": "run", "file": file_id, "version": version, "user": str(user_id or ""),
                       "attested": attested is True, "nonce": secrets.token_hex(16), "iat": now, "exp": now + RUN_TOKEN_TTL_S})


def _final_digest(*, user_id: Any, file_id: str, version: Optional[str], attested: bool, skull: str) -> str:
    """K2: the digest of a final consultation's request — what makes a retry IDENTICAL."""
    body = {"kind": "final", "user": str(user_id or ""), "file": file_id, "version": version,
            "attested": attested is True, "skull": skull}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def claim_final(token: Any, *, file_id: str, version: Optional[str], user_id: Any, attested: bool,
                skull: str) -> RunClaim:
    """Claim a final consultation's run token in the ledger. ``fresh`` only for a token this server issued for exactly
    this file, version, clinician and attestation, before its expiry, not claimed by another request (or released, or
    abandoned beyond the lease); ``replay`` with the stored decision for the identical request; ``conflict`` for
    another request; ``in_progress`` while a live claim of the same request is being decided; ``invalid`` /
    ``unavailable`` (fail closed, logged) otherwise. Blocking: call it off the event loop."""
    payload = verify_token(token, "run")
    if (payload is None or payload.get("file") != file_id or payload.get("version") != version or not version
            or payload.get("user") != str(user_id or "") or payload.get("attested") is not (attested is True)
            or not isinstance(payload.get("nonce"), str)):
        return RunClaim("invalid")
    key, expires_at = f"run-{payload['nonce']}", int(payload["exp"])
    digest = _final_digest(user_id=user_id, file_id=file_id, version=version, attested=attested, skull=skull)
    try:
        claim = _run_token_store().claim(key, digest, expires_at, _now())
    except Exception as exc:  # noqa: BLE001 — full or unreachable: fail closed, never a release
        logger.warning("Quality gate: the run token store refused a run token (%s); the release is not recorded",
                       type(exc).__name__)
        return RunClaim("unavailable")
    if claim.status == "conflict":
        logger.warning("Quality gate: a run token was presented again for another request; the release is not recorded")
    claim.key, claim.digest, claim.expires_at = key, digest, expires_at
    return claim


def settle_final(claim: RunClaim, answer: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """S1: store the decision of a fresh claim in its document, BEFORE it is audited or answered; returns the decision
    to deliver (the first one stored for the token), or None when it could not be stored (a store failure, or the
    claim taken over meanwhile): the caller then FAILS CLOSED — no release, no AI-run record. Blocking."""
    if claim.status != "fresh" or not claim.key:
        return None
    try:
        return _run_token_store().settle(claim, answer, _now())
    except Exception as exc:  # noqa: BLE001 — not stored: fail closed
        logger.warning("Quality gate: the run token store could not keep a decision (%s); nothing is released",
                       type(exc).__name__)
        return None


def release_final(claim: RunClaim) -> None:
    """S1: a claim whose evaluation or settlement failed is retryable AT ONCE by the same request (best effort: a store
    that fails here leaves it to the lease). Blocking."""
    if claim.status != "fresh" or not claim.key:
        return
    try:
        _run_token_store().release(claim, _now())
    except Exception as exc:  # noqa: BLE001 — the lease frees it later
        logger.warning("Quality gate: a failed run claim could not be released (%s)", type(exc).__name__)


def audit_replay(answer: Dict[str, Any], *, actor=None, study_key: str = "", registry=None) -> None:
    """K2: a stored decision delivered again for the identical request is audited as a REPLAY (a consultation record,
    never a second release)."""
    from app.agent_platform import registry as R
    reg = registry if registry is not None else default_registry()
    details = {**explain(answer), "decision": answer.get("decision"), "mode": answer.get("mode"),
               "released": answer.get("ai_output_allowed") is True}
    with R.audit_actor(actor):
        reg.audit("success", "quality_gate.replayed", event="agent.consultation", agent_id=AGENT_ID,
                  study_key=study_key or None, trace_id=answer.get("trace_id"), details=details)


def unavailable_answer(subject: Dict[str, Any], trace_id: Optional[str] = None) -> Dict[str, Any]:
    """S1: the fail-closed answer of a final consultation whose decision could not be stored: the gate unavailable."""
    from app.agent_platform import registry as R
    policy = _policy()
    result = _result([_check("platform", None, "abstain", policy["platform"]["otherwise"])], policy)
    result["platform"] = {"allowed": False, "code": str(R.RefusalCode.RUN_INTERNAL_ERROR)}
    return {**result, "trace_id": trace_id, "subject": subject}


def audit_unavailable(answer: Dict[str, Any], *, actor=None, study_key: str = "", registry=None) -> None:
    """S1: a decision that could not be stored is recorded as a FAILED consultation (never an AI run)."""
    from app.agent_platform import registry as R
    reg = registry if registry is not None else default_registry()
    with R.audit_actor(actor):
        reg.audit("failure", "quality_gate.store_unavailable", event="agent.consultation", agent_id=AGENT_ID,
                  study_key=study_key or None, trace_id=answer.get("trace_id"),
                  details={"decision": answer.get("decision"), "mode": "single", "released": False})


def run_quality_gate(inputs, *, registry=None, tracer=None, study_key: str = "", actor=None, releases_output: bool = True,
                     trace_id: Optional[str] = None) -> Dict[str, Any]:
    """The gate as the registered agent ``quality-gate`` (RC-126): consulted (consult_quality_gate), then audited
    (audit_quality_gate) — one ``agent.run`` or ``agent.consultation`` record."""
    result, record = consult_quality_gate(inputs, registry=registry, tracer=tracer, study_key=study_key, actor=actor,
                                          trace_id=trace_id)
    audit_quality_gate(result, record, registry=registry, study_key=study_key, actor=actor,
                       releases_output=releases_output)
    return result


def consult_quality_gate(inputs, *, registry=None, tracer=None, study_key: str = "", actor=None,
                         trace_id: Optional[str] = None):
    """S1 (fifteenth review): the gate's decision through the platform — approval and kill switches read now (fail
    closed), one trace with one child span per check — WITHOUT any audit record: returns (result, record), the record
    to write once the decision is final (audit_quality_gate). The caller's ``platform`` field is ignored."""
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
                result["platform"] = payload["platform"]          # shown by the browser with the decision
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
        except Exception:  # noqa: BLE001 — a platform fault: abstain, recorded as a failure
            result = _result([_check("platform", None, "abstain", policy["platform"]["otherwise"])], policy)
            result["platform"] = {"allowed": False, "code": str(R.RefusalCode.RUN_INTERNAL_ERROR)}
            result["trace_id"] = state.get("trace_id")
            return result, {"fault": True}
        result["trace_id"] = state["trace_id"]
        details = {**explain(result), "decision": result.get("decision"), "mode": result.get("mode"),
                   **_skull_report(inputs)}
        return result, {"fault": False, "refusal": state["refusal"], "details": details}


def audit_quality_gate(result: Dict[str, Any], record: Dict[str, Any], *, registry=None, study_key: str = "",
                       actor=None, releases_output: bool) -> None:
    """The ONE audit record of a consultation, written once its decision is final (S1). F4 (fifth review of PR #81): a
    consultation is not an AI run — only a decision that releases an AI output (``releases_output`` and
    ai_output_allowed) is the AI run ("agent.run" -> CLINICAL_AI_RUN); every other one is a consultation. G31 (eighth
    review): a comparison's gate decision releases nothing by itself; structured details keep every cause and visit."""
    from app.agent_platform import registry as R
    reg = registry if registry is not None else default_registry()
    with R.audit_actor(actor):
        if record.get("fault"):
            reg.audit("failure", R.RefusalCode.RUN_INTERNAL_ERROR, event="agent.consultation", agent_id=AGENT_ID,
                      study_key=study_key or None, trace_id=result.get("trace_id"))
            return
        event = "agent.run" if releases_output and result.get("ai_output_allowed") is True else "agent.consultation"
        if record.get("refusal"):
            reg.audit("denied", record["refusal"], event=event, agent_id=AGENT_ID,
                      study_key=study_key or None, trace_id=result.get("trace_id"), details=record.get("details"))
        else:
            # S3: the physician's attestation is recorded with the run's actor (the authenticated clinician)
            reg.audit("success", audit_code(result), event=event, agent_id=AGENT_ID,
                      study_key=study_key or None, trace_id=result.get("trace_id"), details=record.get("details"))


def _skull_report(inputs: Any) -> Dict[str, str]:
    """K4 (twelfth review): the skull outcome of a single study is what the in-browser pipeline REPORTS — the server
    cannot verify it (RC-043 / RC-049 in the browser are the real controls); the audit says so."""
    visits = inputs.get("visits") if isinstance(inputs, dict) and inputs.get("mode") == "single" else None
    skull = visits[0].get("skull") if isinstance(visits, list) and visits and isinstance(visits[0], dict) else None
    return {"skull_report": f"client_reported:{skull}"} if isinstance(skull, str) and skull.isidentifier() else {}


# ----------------------------------------------------------------------------- comparison wiring
def apply_to_comparison(result: Dict[str, Any], gate: Dict[str, Any]) -> Dict[str, Any]:
    """Attach the gate to a longitudinal comparison; when it abstains, withhold exactly what RC-062 withholds."""
    if gate.get("ai_output_allowed") is not True:      # ONE abstention path (second review, finding 5)
        return abstained_comparison(gate)
    out = {**result, "quality_gate": gate}
    reasons = [reason_sentence(c) for c in explain(gate)["warnings"]]
    if reasons:                                       # R4: a warned comparison says so (the assistant reads this)
        previous = out.get("caveat") if isinstance(out.get("caveat"), str) else ""
        out["caveat"] = (previous.rstrip() + " " if previous.strip() else "") + (
            reason_lead("warned") + " " + "; ".join(reasons) + ".")
    return out


def present_gated_comparison(result: Dict[str, Any], *, acquisition_check: Dict[str, Any], evidence, binding,
                             stored_review, visit_check, review_read_failed: bool = False, gate=None) -> Dict[str, Any]:
    """G24 / G25 (fourth review of PR #81): RC-062 EXACTLY as on the base branch
    (longitudinal_candidate_safety.present_comparison, no gate parameter), then the gate, which can only ADD an
    abstention or warnings. The compare route answers through this one function."""
    presented = lcs.present_comparison(result, acquisition_check=acquisition_check, evidence=evidence,
                                       binding=binding, stored_review=stored_review, visit_check=visit_check,
                                       review_read_failed=review_read_failed)
    return apply_to_comparison(presented, gate) if gate is not None else presented


# C3 / A4: plain reasons for the report and the assistant (never a raw code), from ONE table (en/es/de). The UI shows
# the physician-facing texts of the i18n files through QualityGatePanel.
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


CAVEAT_REASONS = {code: row["en"] for code, row in _REASONS["reasons"].items()}


def audit_code(result: Dict[str, Any]) -> str:
    """G17: the decision, plus '.attested' when the physician's attestation was used — shown and withheld outputs leave
    distinguishable records. Tenth review (S4): a SHORT code by construction (at most 43 characters, so the audit
    reason '<event>:<code>' always fits the 64-character code field whole); the causes and the attested visits travel
    as structured details (explain), never packed into this string."""
    attested = any(c.get("code") == "sequence_confirmed_by_physician" for c in result.get("checks", []))
    return f"quality_gate.{result.get('decision')}" + (".attested" if attested else "")


def explain(gate: Any) -> Dict[str, Any]:
    """G30 (eighth review of PR #81): the ONE account of a gate result that every text is built from — CAUSES are
    exactly the checks that stopped it (abstained; for a pending result, the pending checks), WARNINGS the checks that
    only warned (tenth review: the ONE warnings story — the caveat, the notice, the report payload and the model's text
    all take them from here), and the visits the physician attested. A client-supplied result is read defensively: checks of the
    right shape, else codes with their policy status; anything else is ignored."""
    statuses = _policy()["codes"]
    text = lambda v: v if isinstance(v, str) else None  # noqa: E731 — I2 (eleventh review): anything else is ignored
    checks = gate.get("checks") if isinstance(gate, dict) and isinstance(gate.get("checks"), list) else None
    if checks is not None:
        # known codes only (R4): a client-supplied result never brings free text into a report or an audit record
        pairs = [(text(c.get("code")), text(c.get("status")), text(c.get("visit"))) for c in checks
                 if isinstance(c, dict) and text(c.get("code")) in statuses]
    else:
        codes = gate.get("codes") if isinstance(gate, dict) and isinstance(gate.get("codes"), list) else []
        pairs = [(c, statuses[c], None) for c in codes if isinstance(c, str) and c in statuses]
    unique = lambda xs: list(dict.fromkeys(xs))  # noqa: E731
    causes = unique(c for c, st, _ in pairs if st == "abstain")
    if not causes and isinstance(gate, dict) and gate.get("ai_output_allowed") is not True:
        causes = unique(c for c, st, _ in pairs if st == "pending") or ["gate_unavailable"]
    return {"causes": causes,
            "warnings": unique(c for c, st, _ in pairs if st == "warn"),
            "attested_visits": unique(v for c, _, v in pairs if c == "sequence_confirmed_by_physician" and v)}


def gate_caveat(gate: Dict[str, Any]) -> str:
    """The comparison caveat of a pair the gate stopped: its CAUSES only (G30), never a warning."""
    reasons = [CAVEAT_REASONS.get(c, "a quality check did not pass") for c in explain(gate)["causes"]]
    return ("No automatic change candidates and no lesion load or count comparison for this pair: the quality gate "
            "stopped it, because " + "; ".join(reasons) + ". Compare the images visually with the overlay.")


def abstained_sel(gate: Optional[Dict[str, Any]], *, pair: Any = None, reason: Optional[str] = None,
                  **extra: Any) -> Dict[str, Any]:
    """The SEL search's answer when it is withheld — by the gate (its causes) or by RC-062 (its reason, with its own
    checks in ``extra``) — the ONE shape (thirteenth review). Every quantity withheld; the candidate firewall kept."""
    out = {"ok": False, "abstained": True, "reason": reason if reason is not None else gate_caveat(gate), "sels": [],
           "n_existing": 0, "n_sel": 0, **extra, "registration_verified": False, "adjudication_required": True}
    if gate is not None:
        out.update({"quality_gate": gate, "pair": pair})
    return out


class PairAttestation(BaseModel):
    """The physician's per-visit FLAIR attestation of a comparison (F1): strict booleans only, no other key — the ONE
    validator of the compare and SEL routes (thirteenth review), as the single study's StrictBool."""
    model_config = ConfigDict(extra="forbid")
    tp1: StrictBool = False
    tp2: StrictBool = False


def abstained_comparison(gate: Dict[str, Any]) -> Dict[str, Any]:
    """The comparison response when the gate stops it BEFORE anything is loaded (C2): every quantity withheld."""
    out = {"abstained": True, "changes": [], "quality_gate": gate, "registration_verified": False,
           "adjudication_required": True, "reader_confirmed_activity": None, "caveat": gate_caveat(gate)}
    out.update({k: None for k in lcs.ABSTAINED_NULL_FIELDS})
    return out


def comparison_gate(source_tp1, source_tp2, *, headers=None, records=None, attestation=(False, False),
                    visit_ok: Optional[bool] = None, user=None, request=None) -> Dict[str, Any]:
    """The gate on two visits (RC-123), through the platform (RC-126). Each visit is derived exactly as a single study
    (visit_inputs, A1) from its stored image header (``headers``) and its stored records (``records``: the
    (acquisition, series description) pairs the route read concurrently with stored_records — E2, eighth review).
    G32: RC-062's verdict on the pair is PREDICTED here (lcs.rc062_withholds on the stored acquisitions and the visit
    order) so that an attestation is offered only when the end-to-end result could change. The gate's own record is a
    decision (agent.consultation); the route records what the user finally received (audit_comparison_outcome, G31)."""
    given_rec = list(records) if records is not None else [None, None]
    given_hdr = list(headers) if headers is not None else [None, None]
    visits, acqs, spacings = [], [], []
    for s, rec, h, att in zip((source_tp1, source_tp2), given_rec, given_hdr, attestation):
        acq, stored = rec if isinstance(rec, tuple) else (stored_records(s) if s else (None, None))
        fields = h if isinstance(h, dict) else {**_NO_HEADER, "no_source": True} if not s else {**_NO_HEADER, "unreadable": True}
        acqs.append(acq if isinstance(acq, dict) else None)
        spacings.append(fields.get("voxel_spacing_mm"))       # S3: RC-062's own spacing (lcs.rc062_voxel_spacing)
        visits.append(visit_inputs(fields, acq, stored, physician_confirmed_flair=att is True, with_scanner=True))
    rc062 = lcs.rc062_withholds(lcs.compare_acquisitions(acqs[0], acqs[1], spacings[0], spacings[1]),
                                {"status": "ok" if visit_ok is True else "unknown"})
    return run_quality_gate({"mode": "comparison", "visits": visits, "rc062_withholds": rc062},
                            study_key=study_of(source_tp2) or study_of(source_tp1) or "",
                            actor=actor_for(user, request) if user is not None else None, releases_output=False)


# K6 (fourteenth review): what a pair the gate allowed finally gave — every value is a registered audit code (K7)
WITHHELD_BY = frozenset({"rc062", "sel", "unknown", "not_delivered", "error", "http_400", "http_403", "http_404",
                         "http_409", "http_413", "http_422", "http_500", "http_503"})


class OutcomeRecord:
    """K6 (fourteenth review of PR #81): EXACTLY ONE outcome record (G31) per gate-consulting request whose pair the gate
    allowed — released, or withheld:<by> — on EVERY path: the route records it where it knows the outcome; any path
    that ends otherwise (an error, a 4xx after the gate, an early return) is recorded on close as withheld with its
    error code. A pair the gate stopped has its gate record only (audit_comparison_outcome does nothing for it)."""

    def __init__(self, gate: Any = None, *, pair: Optional[Dict[str, Any]] = None, user=None, request=None):
        self.gate, self.user, self.request, self.done = gate, user, request, False
        source = ((pair or {}).get("tp2") or {}).get("source") if isinstance(pair, dict) else None
        self.study_key = (study_of(source) or "") if isinstance(source, str) else ""

    def record(self, *, released: bool, withheld_by: Optional[str] = None, study_key: Optional[str] = None) -> None:
        if self.done:
            return
        self.done = True
        audit_comparison_outcome(self.gate, released=released, withheld_by=withheld_by, user=self.user,
                                 request=self.request, study_key=study_key or self.study_key)

    def close(self, exc: Optional[BaseException]) -> None:
        if self.done:
            return
        status = getattr(exc, "status_code", None) if exc is not None else None
        code = f"http_{status}" if isinstance(status, int) and f"http_{status}" in WITHHELD_BY else (
            "error" if exc is not None else "not_delivered")
        self.record(released=False, withheld_by=code)


def audit_comparison_outcome(gate: Any, *, released: bool, withheld_by: Optional[str] = None, user=None, request=None,
                             study_key: str = "", registry=None) -> None:
    """G31 (eighth review of PR #81): what the user FINALLY received for a pair the gate allowed — released (an AI
    run, CLINICAL_AI_RUN) only when the comparison or SEL output was actually delivered; withheld otherwise, with the
    deciding control (rc062). Structured details, never a packed string."""
    if not isinstance(gate, dict) or gate.get("ai_output_allowed") is not True:
        return                                       # the gate's own record already says it stopped the pair
    from app.agent_platform import registry as R
    reg = registry if registry is not None else default_registry()
    by = withheld_by if withheld_by in WITHHELD_BY else "unknown"
    details = {**explain(gate), "decision": gate.get("decision"), "mode": gate.get("mode"),
               "released": released is True, "withheld_by": None if released else by}
    with R.audit_actor(actor_for(user, request) if user is not None else None):
        reg.audit("success", "quality_gate.released" if released else f"quality_gate.withheld.{details['withheld_by']}",
                  event="agent.run" if released else "agent.consultation", agent_id=AGENT_ID,
                  study_key=study_key or None, trace_id=gate.get("trace_id"), details=details)


def _register_audit_reasons() -> None:
    """K7 (fourteenth review of PR #81): every code the gate writes into an audit reason — its policy codes, its
    decisions, its outcomes — in the closed registry of audit reasons."""
    from app.core.logging.audit import register_reason_codes
    try:
        codes = set(_policy()["codes"])
    except Exception:  # noqa: BLE001 — the policy is read again at every consultation; its codes register then
        codes = set()
    decisions = ("proceed", "proceed_with_warnings", "pending", "abstain")
    codes |= {f"quality_gate.{d}" for d in decisions} | {f"quality_gate.{d}.attested" for d in decisions}
    codes |= {"quality_gate.released", "quality_gate.replayed", "quality_gate.store_unavailable"}
    codes |= {f"quality_gate.withheld.{w}" for w in WITHHELD_BY}
    register_reason_codes(codes)


_register_audit_reasons()
