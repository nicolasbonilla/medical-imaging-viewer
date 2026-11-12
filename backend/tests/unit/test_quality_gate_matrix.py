"""Single quality gate — invariants over the combinatorial matrix (written FIRST, failing).

REQ-FUNC-117, REQ-FUNC-118, REQ-SAFE-052, REQ-SAFE-053, REQ-SAFE-054; HAZ-025; RC-122..RC-127.
DRAFT, PENDING owner approval. Design: docs/iec62304/agent_platform/Quality_Gate_Design.md.

Lesson of PR #78: per-finding fixes did not converge, a combinatorial scenario matrix did. Every invariant
below is checked over EVERY combination of

    sequence {FLAIR, T1, T2, unknown, missing} x physician confirmation {no, yes}
    x thickness {<= 1.5, (1.5, 4.5], (4.5, 6.5], > 6.5 mm, unreadable}
    x scanner {same, other manufacturer, other field strength, unknown}
    x skull {stripped, not stripped, unknown, pending}
    x mode {single study, comparison with tp1 / tp2 / both visits affected}      = 3 200 cases

and the platform states {on, switched off, not approved, unavailable, unknown} over the whole matrix.
Each test reports how many cases fail. Sixth review of PR #81 (G27): the rule has ONE implementation, this
module's subject (quality_gate.py); the browser holds no rule and shows the server's decision, so the former
two-copy parity fixture (G4) is gone.
"""
from __future__ import annotations

import copy
import itertools
import inspect
import json
import re
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:  # pragma: no cover — when run as a script
    sys.path.insert(0, str(BACKEND))

from app.agent_platform import registry as R  # noqa: E402
from app.agent_platform import tracing as T  # noqa: E402
from app.agent_platform.hashing import sha256_text  # noqa: E402
from app.services import longitudinal_candidate_safety as lcs  # noqa: E402
from app.services import quality_gate as QG  # noqa: E402

REPO = BACKEND.parent
BACKEND_POLICY = BACKEND / "app" / "services" / "quality_gate_policy.json"
LOCALES = {lang: REPO / "frontend" / "src" / "i18n" / "locales" / f"{lang}.json" for lang in ("en", "es", "de")}
REGISTRY = BACKEND / "app" / "agent_platform" / "agents.json"

pytestmark = pytest.mark.unit

# ----------------------------------------------------------------------------- the matrix
BASE_SCANNER = {"manufacturer": "SIEMENS", "manufacturer_model_name": "Prisma", "magnetic_field_strength_t": 3.0}
BASE_VISIT = {
    "sequence": "FLAIR",
    "physician_confirmed_flair": False,
    "thickness": {"state": "native", "effective_mm": 1.0},
    "scanner": BASE_SCANNER,
    "skull": "stripped",
}
MATRIX = {
    "base_visit": BASE_VISIT,
    "dimensions": [
        ["sequence", {
            "FLAIR": {"sequence": "FLAIR"}, "T1": {"sequence": "T1"}, "T2": {"sequence": "T2"},
            "unknown": {"sequence": "unknown"}, "missing": {"sequence": "missing"},
        }],
        ["confirmed", {"no": {"physician_confirmed_flair": False}, "yes": {"physician_confirmed_flair": True}}],
        ["thickness", {
            "le1.5": {"thickness": {"state": "native", "effective_mm": 1.0}},
            "1.5-4.5": {"thickness": {"state": "native", "effective_mm": 3.0}},
            "4.5-6.5": {"thickness": {"state": "native", "effective_mm": 5.0}},
            "gt6.5": {"thickness": {"state": "native", "effective_mm": 7.0}},
            "unreadable": {"thickness": {"state": "not_determinable", "effective_mm": None}},
        }],
        ["scanner", {
            "same": {},
            "manufacturer": {"scanner": {**BASE_SCANNER, "manufacturer": "GE MEDICAL SYSTEMS"}},
            "field_strength": {"scanner": {**BASE_SCANNER, "magnetic_field_strength_t": 1.5}},
            "unknown": {"scanner": {**BASE_SCANNER, "manufacturer": None}},
        }],
        ["skull", {
            "stripped": {"skull": "stripped"}, "not_stripped": {"skull": "not_stripped"},
            "unknown": {"skull": "unknown"}, "pending": {"skull": "pending"},
        }],
        ["variant", {
            "single": {"mode": "single", "affected": ["study"]},
            "cmp_tp1": {"mode": "comparison", "affected": ["tp1"]},
            "cmp_tp2": {"mode": "comparison", "affected": ["tp2"]},
            "cmp_both": {"mode": "comparison", "affected": ["tp1", "tp2"]},
        }],
    ],
}
PLATFORM_ON = {"allowed": True, "code": None}
PLATFORM_STATES = {
    "switched_off": {"allowed": False, "code": "agent_switched_off"},
    "not_approved": {"allowed": False, "code": "agent_not_approved"},
    "unavailable": {"allowed": False, "code": "switch_unreadable"},
    "unknown": None,
    "malformed": {"allowed": "true", "code": None},
}
EXPECTED_PLATFORM_CODE = {"switched_off": "gate_switched_off", "not_approved": "gate_not_approved",
                          "unavailable": "gate_unavailable", "unknown": "gate_unavailable",
                          "malformed": "gate_unavailable"}


def build_cases(matrix=MATRIX, platform=PLATFORM_ON):
    """Every combination, in a fixed order: (key, values, input). The SAME rule is in gate.test.ts."""
    names = [d[0] for d in matrix["dimensions"]]
    tables = [list(d[1].items()) for d in matrix["dimensions"]]
    out = []
    for combo in itertools.product(*tables):
        key = "|".join(v for v, _ in combo)
        values = dict(zip(names, (v for v, _ in combo)))
        parts = dict(zip(names, (p for _, p in combo)))
        patch = {**parts["sequence"], **parts["confirmed"], **parts["thickness"], **parts["skull"]}
        variant = parts["variant"]
        base = copy.deepcopy(matrix["base_visit"])
        if variant["mode"] == "single":
            visits = [{**base, **patch, **parts["scanner"]}]
        else:
            tp1 = {**base, **(patch if "tp1" in variant["affected"] else {})}
            tp2 = {**base, **(patch if "tp2" in variant["affected"] else {}), **parts["scanner"]}
            visits = [tp1, tp2]
        out.append((key, values, {"mode": variant["mode"], "visits": copy.deepcopy(visits),
                                  "platform": copy.deepcopy(platform)}))
    return out


CASES = build_cases()
N = len(CASES)


def _evaluate_all(platform=PLATFORM_ON):
    return [(k, v, i, QG.evaluate(i)) for k, v, i in (CASES if platform is PLATFORM_ON else build_cases(platform=platform))]


@pytest.fixture(scope="module")
def results():
    return _evaluate_all()


def _report(name, bad):
    bad = sorted(set(bad))
    return f"{name} failed in {len(bad)} of {N} cases; first: {bad[:4]}"


def _checks(out, check=None, visit=None):
    return [c for c in out.get("checks", []) if (check is None or c.get("check") == check)
            and (visit is None or c.get("visit") == visit)]


def _visit_labels(inp):
    return ["study"] if inp["mode"] == "single" else ["tp1", "tp2"]


def test_rc122_matrix_size_is_the_full_cross_product():
    assert N == 5 * 2 * 5 * 4 * 4 * 4 == 3200


# ----------------------------------------------------------------------------- G1
def test_rc122_g1_the_ai_never_runs_on_a_non_flair_or_unknown_sequence(results):
    bad = []
    for key, _, inp, out in results:
        if out.get("ai_output_allowed") and not out.get("ai_may_run"):
            bad.append(key)
        for visit in inp["visits"]:
            seq, confirmed = visit["sequence"], visit["physician_confirmed_flair"] is True
            if seq in ("T1", "T2", "other") and out.get("ai_may_run") is not False:
                bad.append(key)                  # a header naming another sequence: never, whatever is confirmed
            if seq in ("unknown", "missing") and not confirmed and out.get("ai_may_run") is not False:
                bad.append(key)
            if seq in ("unknown", "missing") and confirmed and out.get("ai_may_run") \
                    and "sequence_confirmed_by_physician" not in out.get("codes", []):
                bad.append(key)                  # a confirmation always leaves a warning
    assert not bad, _report("G1", bad)


# ----------------------------------------------------------------------------- G2
def _policy():
    return json.loads(BACKEND_POLICY.read_text(encoding="utf-8"))


def test_rc127_g2_every_non_pass_check_carries_a_known_code_with_its_status(results):
    codes = _policy()["codes"]
    bad = []
    for key, _, _, out in results:
        if out.get("decision") == "abstain" and not any(c.get("status") == "abstain" for c in out.get("checks", [])):
            bad.append(key)
        for c in out.get("checks", []):
            if c.get("status") == "pass":
                if c.get("code") is not None:
                    bad.append(key)
            elif c.get("code") not in codes or codes[c["code"]] != c.get("status"):
                bad.append(key)
        listed = sorted({c["code"] for c in out.get("checks", []) if c.get("code")})
        if out.get("codes") != listed:
            bad.append(key)
    assert not bad, _report("G2", bad)


def _locale(lang):
    return json.loads(LOCALES[lang].read_text(encoding="utf-8"))


def test_rc127_g2_every_code_has_a_plain_message_and_an_action_in_en_es_de():
    codes = _policy()["codes"]
    missing = []
    texts = {}
    for lang in LOCALES:
        gate = _locale(lang).get("qualityGate") or {}
        for code in codes:
            entry = (gate.get("codes") or {}).get(code) or {}
            for part in ("message", "action"):
                text = entry.get(part)
                if not isinstance(text, str) or len(text.strip()) < 12:
                    missing.append(f"{lang}:{code}.{part}")
                else:
                    texts[(lang, code, part)] = text
                    # "seconds": F3 (fifth review), only for gate_rate_limited
                    allowed = {"band", "fields", "mm", "sequence"} | ({"seconds"} if code == "gate_rate_limited" else set())
                    if set(re.findall(r"\{\{(\w+)\}\}", text)) - allowed:
                        missing.append(f"{lang}:{code}.{part} has an unknown placeholder")
        for group, names in (("decision", ("abstain", "pending", "proceed", "proceed_with_warnings")),
                             ("check", ("platform", "sequence", "thickness", "scanner", "skull")),
                             ("status", ("pass", "warn", "pending", "abstain"))):
            for name in names:
                if not isinstance((gate.get(group) or {}).get(name), str):
                    missing.append(f"{lang}:{group}.{name}")
    for (lang, code, part), text in texts.items():
        if lang != "en" and texts.get(("en", code, part)) == text:
            missing.append(f"{lang}:{code}.{part} is not translated")
    assert not missing, f"G2: {len(missing)} missing or untranslated texts; first: {missing[:6]}"


# ----------------------------------------------------------------------------- G3
def _thin(visit):
    t = visit.get("thickness") or {}
    mm = t.get("effective_mm")
    return t.get("state") == "native" and isinstance(mm, (int, float)) and 0 < mm <= 1.5


def _scanner_same(inp):
    a, b = (v.get("scanner") or {} for v in inp["visits"])
    fields = ("manufacturer", "manufacturer_model_name", "magnetic_field_strength_t")
    return all(a.get(f) is not None and a.get(f) == b.get(f) for f in fields)


def test_rc122_g3_no_pass_from_an_unknown_value_and_proceed_only_when_everything_is_known_and_good(results):
    bad = []
    for key, _, inp, out in results:
        labels = _visit_labels(inp)
        for label, visit in zip(labels, inp["visits"]):
            for c in _checks(out, "sequence", label):
                if c["status"] == "pass" and visit["sequence"] != "FLAIR":
                    bad.append(key)
            for c in _checks(out, "thickness", label):
                if c["status"] == "pass" and not _thin(visit):
                    bad.append(key)
            for c in _checks(out, "skull", label):
                if c["status"] == "pass" and visit["skull"] != "stripped":
                    bad.append(key)
        for c in _checks(out, "scanner"):
            if c["status"] == "pass" and not _scanner_same(inp):
                bad.append(key)
        if out.get("decision") == "proceed":
            good = all(v["sequence"] == "FLAIR" and _thin(v) for v in inp["visits"])
            good &= (inp["visits"][0]["skull"] == "stripped") if inp["mode"] == "single" else _scanner_same(inp)
            if not good:
                bad.append(key)
        if out.get("decision") not in ("abstain", "pending", "proceed", "proceed_with_warnings"):
            bad.append(key)
    assert not bad, _report("G3", bad)


def test_rc122_g3_values_outside_the_known_set_never_pass():
    odd = [
        {"sequence": "flair"}, {"sequence": None}, {"sequence": 7}, {"physician_confirmed_flair": "yes", "sequence": "unknown"},
        {"thickness": {"state": "native", "effective_mm": float("nan")}}, {"thickness": {"state": "native", "effective_mm": 0}},
        {"thickness": {"state": "native", "effective_mm": -1.0}}, {"thickness": {"state": "native", "effective_mm": 25.0}},
        {"thickness": {"state": "native", "effective_mm": True}}, {"thickness": {"state": "native", "effective_mm": "1.0"}},
        {"thickness": {"state": "at_least", "effective_mm": 1.0}}, {"thickness": None}, {"thickness": "1mm"},
        {"skull": "STRIPPED"}, {"skull": None}, {"skull": True},
    ]
    bad = []
    for patch in odd:
        out = QG.evaluate({"mode": "single", "visits": [{**BASE_VISIT, **patch}], "platform": PLATFORM_ON})
        if out.get("decision") == "proceed" or any(c.get("status") == "pass" and c.get("check") != "platform"
                                                   and c.get("check") in {k.split("_")[0] for k in patch}
                                                   for c in out.get("checks", [])):
            bad.append(repr(patch))
    for broken in ({"mode": "single", "visits": [], "platform": PLATFORM_ON},
                   {"mode": "comparison", "visits": [BASE_VISIT], "platform": PLATFORM_ON},
                   {"mode": "other", "visits": [BASE_VISIT], "platform": PLATFORM_ON},
                   {"mode": "single", "visits": ["x"], "platform": PLATFORM_ON}, None, "x"):
        out = QG.evaluate(broken)
        if out.get("ai_may_run") is not False or "gate_input_invalid" not in out.get("codes", []):
            bad.append(repr(broken)[:60])
    assert not bad, f"G3 (odd values): {len(bad)} inputs passed or ran: {bad[:6]}"


# ----------------------------------------------------------------------------- G27 (replaces G4, sixth review)
def test_rc126_g27_one_policy_on_the_server_bound_to_the_registry_and_to_the_checks_it_reuses():
    """One implementation (G27): the policy exists only on the server; the registry records its SHA-256 (the agent's
    card); its scanner and thickness parameters are those of RC-062 and RC-054."""
    backend = json.loads(BACKEND_POLICY.read_text(encoding="utf-8"))
    assert not (REPO / "frontend" / "src" / "config" / "qualityGatePolicy.v1.json").exists(), "a browser policy copy"
    entry = json.loads(REGISTRY.read_text(encoding="utf-8"))["agents"]["quality-gate"]
    assert entry.get("policy", {}).get("sha256") == sha256_text(backend), "policy changed without the registry"
    assert backend["scanner"]["field_strength_tolerance_t"] == lcs._ABS_TOL["magnetic_field_strength_t"]
    assert backend["scanner"]["fields"] == list(lcs.REQUIRED_ACQUISITION_FIELDS[:3])
    from app.services import acquisition_geometry as AG
    assert backend["thickness"]["thin_limit_mm"] == AG.THIN_LIMIT_MM
    assert backend["thickness"]["plausible_max_mm"] == AG.PLAUSIBLE_MAX_MM


# ----------------------------------------------------------------------------- G5
def _expected_checks(inp):
    labels = _visit_labels(inp)
    out = [("platform", None)]
    for label in labels:
        out += [("sequence", label), ("thickness", label)]
        if inp["mode"] == "single":
            out.append(("skull", label))
    if inp["mode"] == "comparison":
        out.append(("scanner", None))
    return out


def test_rc126_g5_exactly_the_applicable_checks_run_and_are_recorded(results):
    bad = [key for key, _, inp, out in results
           if [(c.get("check"), c.get("visit")) for c in out.get("checks", [])] != _expected_checks(inp)]
    assert not bad, _report("G5", bad)


def _approved_registry(switches=None, audit=None, data=None):
    data = copy.deepcopy(data if data is not None else json.loads(REGISTRY.read_text(encoding="utf-8")))
    data["agents"]["quality-gate"]["approval"]["status"] = "approved"     # IN MEMORY, for the test only
    return R.AgentRegistry(data, switches=switches or R.InMemoryKillSwitches({"quality-gate": True}),
                           audit=audit.append if audit is not None else (lambda e: None))


def test_rc126_g5_the_trace_and_the_audit_record_exactly_the_checks_that_ran(results):
    audit = []
    exporter = T.InMemoryExporter()
    tracer = T.Tracer(exporter)
    reg = _approved_registry(audit=audit)
    bad = []
    for key, _, inp, _ in results:
        before_spans, before_audit = len(exporter.spans), len(audit)
        out = QG.run_quality_gate({k: v for k, v in inp.items() if k != "platform"}, registry=reg, tracer=tracer,
                                  study_key="study-" + str(len(audit)))
        spans = list(exporter.spans)[before_spans:]
        roots = [s for s in spans if s.parent_span_id is None]
        children = [s for s in spans if s.parent_span_id is not None]
        recorded = [(s.attributes.get("mstool.gate.check"), s.attributes.get("mstool.gate.visit"),
                     s.attributes.get("mstool.gate.status"), s.attributes.get("mstool.gate.code")) for s in children]
        expected = [(c["check"], c["visit"] or "none", c["status"], c["code"] or "none") for c in out.get("checks", [])]
        records = audit[before_audit:]
        if (len(roots) != 1 or roots[0].attributes.get("gen_ai.agent.id") != "quality-gate" or recorded != expected
                or not expected or out.get("trace_id") != roots[0].trace_id
                or any("mstool.trace.dropped_attributes" in s.attributes for s in spans)
                or len(records) != 1
                # F4 (fifth review): an AI run only when the decision releases an output, else a consultation
                or records[0].get("event") != ("agent.run" if out.get("ai_output_allowed") is True else "agent.consultation")
                or records[0].get("agent_id") != "quality-gate" or records[0].get("trace_id") != roots[0].trace_id):
            bad.append(key)
    assert not bad, _report("G5 (trace/audit)", bad)


# ----------------------------------------------------------------------------- G6
@pytest.mark.parametrize("state", sorted(PLATFORM_STATES))
def test_rc126_g6_platform_not_on_means_no_ai_step_and_the_reason(state):
    bad = []
    for key, _, inp in build_cases(platform=PLATFORM_STATES[state]):
        out = QG.evaluate(inp)
        if (out.get("decision") != "abstain" or out.get("ai_may_run") is not False
                or out.get("ai_output_allowed") is not False
                or out.get("codes") != [EXPECTED_PLATFORM_CODE[state]]
                or [c.get("check") for c in out.get("checks", [])] != ["platform"]):
            bad.append(key)
    assert not bad, _report(f"G6 ({state})", bad)


def test_rc126_g6_the_real_registry_and_switches_fail_closed():
    inp = {"mode": "single", "visits": [BASE_VISIT]}
    tracer = T.Tracer(T.InMemoryExporter())

    class Unreadable:
        def is_on(self, agent_id):
            raise OSError("switch store down")

    production = R.AgentRegistry.load(REGISTRY, switches=R.InMemoryKillSwitches({"quality-gate": True}),
                                      audit=lambda e: None)
    cases = {
        "gate_not_approved": production,                                           # the repository entry: pending
        "gate_switched_off": _approved_registry(switches=R.InMemoryKillSwitches({"quality-gate": False})),
        "gate_unavailable": _approved_registry(switches=Unreadable()),
    }
    bad = []
    for code, reg in cases.items():
        out = QG.run_quality_gate(inp, registry=reg, tracer=tracer, study_key="s")
        if out.get("ai_may_run") is not False or out.get("codes") != [code]:
            bad.append((code, out.get("codes")))
    invalid = R.AgentRegistry({}, switches=R.InMemoryKillSwitches({"quality-gate": True}), audit=lambda e: None)
    out = QG.run_quality_gate(inp, registry=invalid, tracer=tracer, study_key="s")
    if out.get("ai_may_run") is not False or out.get("codes") != ["gate_unavailable"]:
        bad.append(("registry_invalid", out.get("codes")))
    env = R.AgentRegistry.load(REGISTRY, audit=lambda e: None)        # environment switches: absent = off
    out = QG.run_quality_gate(inp, registry=env, tracer=tracer, study_key="s")
    if out.get("ai_may_run") is not False:
        bad.append(("environment", out.get("codes")))
    assert not bad, f"G6 (real platform): {bad}"


def test_rc126_g6_the_registry_entry_is_code_only_and_not_approved():
    entry = json.loads(REGISTRY.read_text(encoding="utf-8"))["agents"]["quality-gate"]
    assert entry["approval"]["status"] == "pending", "registered, awaiting the owner (never 'approved' here)"
    assert entry["model_control"] == "none" and entry["allowed_models"] == [] and entry["allowed_tools"] == []
    assert entry["cost_cap_usd"] == {"per_study": 0.0, "per_day": 0.0}


# ----------------------------------------------------------------------------- G7 (data rule)
def test_rc124_g7_thickness_never_abstains_without_commercial_evidence(results):
    bad = [key for key, _, _, out in results if any(c.get("status") == "abstain" for c in _checks(out, "thickness"))]
    assert not bad, _report("G7", bad)
    policy = _policy()
    assert policy["thickness"]["evidence_asset"] is None
    assert set(policy["thickness"]["commercial_licence_allowlist"]) <= {"CC0-1.0", "CC-BY-4.0"}
    text = BACKEND_POLICY.read_text(encoding="utf-8").lower()
    for word in ("sibbms", "wmh", "ms3seg", "muslim", "detection"):
        assert word not in text, f"the shipped policy mentions {word!r}"


def test_rc124_g7_the_v3_hook_abstains_only_with_a_commercial_licence():
    thick = {"mode": "single", "visits": [{**BASE_VISIT, "thickness": {"state": "native", "effective_mm": 7.0}}],
             "platform": PLATFORM_ON}
    bad = []
    for licence, should_abstain in (("CC-BY-4.0", True), ("CC0-1.0", True), ("CC-BY-NC-4.0", False),
                                    ("CC-BY-NC-SA-4.0", False), (None, False), ("", False)):
        policy = copy.deepcopy(_policy())
        policy["thickness"]["evidence_asset"] = {"asset_id": "thickness-evidence", "version": "3.0.0",
                                                 "sha256": "0" * 64, "licence": licence, "abstain_band_ids": ["B4"]}
        out = QG.evaluate(thick, policy=policy)
        abstained = "thickness_out_of_range" in out.get("codes", []) and out.get("ai_may_run") is False
        if abstained != should_abstain:
            bad.append(licence)
        thin = QG.evaluate({**thick, "visits": [BASE_VISIT]}, policy=policy)
        if thin.get("decision") != "proceed":
            bad.append(f"{licence}: a thin study")
    assert not bad, f"G7 (hook): wrong for licences {bad}"


# ----------------------------------------------------------------------------- G8 -> G24
# The G8 matrix (scanner fields only) is replaced by G24, exhaustive over every RC-062 acquisition fact and the
# visit order, on the comparison OUTPUT: tests/unit/test_rc123_rc062_monotonicity.py (fourth review of PR #81).


# ----------------------------------------------------------------------------- G9
def test_rc122_g9_deterministic_and_independent_of_what_does_not_apply(results):
    bad = []
    groups = {}
    for key, values, inp, out in results:
        if QG.canonical(QG.evaluate(copy.deepcopy(inp))) != QG.canonical(out):
            bad.append(key)
        ignored = "scanner" if values["variant"] == "single" else "skull"
        group = tuple((n, v) for n, v in values.items() if n != ignored)
        groups.setdefault(group, set()).add(QG.canonical(out))
    bad += ["|".join(v for _, v in g) for g, outs in groups.items() if len(outs) != 1]
    assert not bad, _report("G9", bad)


# ----------------------------------------------------------------------------- G10
RANK = {
    "sequence": {"FLAIR": 0, "unknown": 1, "missing": 1, "T1": 2, "T2": 2},
    "confirmed": {"yes": 0, "no": 1},
    "thickness": {"le1.5": 0, "1.5-4.5": 1, "4.5-6.5": 2, "gt6.5": 3, "unreadable": 3},
    "scanner": {"same": 0, "manufacturer": 1, "field_strength": 1, "unknown": 1},
    "skull": {"stripped": 0, "pending": 1, "unknown": 2, "not_stripped": 2},
}


def test_rc122_g10_making_one_input_worse_never_turns_an_abstention_into_a_run(results):
    by_key = {key: out for key, _, _, out in results}
    names = [d[0] for d in MATRIX["dimensions"]]
    bad = []
    for key, values, _, out in results:
        for dim, ranks in RANK.items():
            for worse, rank in ranks.items():
                if rank <= ranks[values[dim]]:
                    continue
                other = by_key["|".join(worse if n == dim else values[n] for n in names)]
                if out.get("ai_may_run") is False and other.get("ai_may_run") is not False:
                    bad.append(key)
                if out.get("ai_output_allowed") is False and other.get("ai_output_allowed") is not False:
                    bad.append(key)
    assert not bad, _report("G10", bad)


# ----------------------------------------------------------------------------- G11
def test_rc125_g11_no_ai_output_while_a_check_is_pending_or_abstains(results):
    bad = [key for key, _, _, out in results
           if out.get("ai_output_allowed") and any(c.get("status") in ("pending", "abstain") for c in out.get("checks", []))]
    bad += [key for key, values, _, out in results
            if values["variant"] == "single" and values["skull"] == "pending"
            and (out.get("ai_output_allowed") is not False or "skull_pending" not in out.get("codes", []))]
    assert not bad, _report("G11", bad)


# ----------------------------------------------------------------------------- first review of PR #81 (S1-S3, C1)
CORPUS = BACKEND / "tests" / "fixtures" / "quality_gate" / "sequences.v1.json"   # server test data (G27)
REQUIRED_NAMES = ("DWI", "ADC", "TRACE", "STIR", "DIR", "PSIR", "SWI", "GRE", "T2*", "TOF", "MPRAGE", "SPACE",
                  "CUBE", "VISTA", "FFE", "T1_FLAIR", "FLAIR_T1", "T1W_FLAIR", "FLAIR T1W", "T2_FLAIR", "3D_FLAIR",
                  "FLAIR_3D", "FLAIR_FS", "DARK_FLUID", "DarkFluid", "dark-fluid", "localizer", "Scout", "MPR",
                  "MIP", "Derived")


def _corpus():
    return json.loads(CORPUS.read_text(encoding="utf-8"))["cases"]


def test_rc122_g12_the_corpus_is_broad_enough():
    cases = _corpus()
    texts = " | ".join(str(c["text"]) for c in cases)
    assert len(cases) >= 80
    assert {"Siemens", "GE", "Philips", "Canon"} <= {c["vendor"] for c in cases}
    assert [n for n in REQUIRED_NAMES if n not in texts] == []
    assert {"", None} <= {c["text"] for c in cases}
    assert {c["expected"] for c in cases} == {"FLAIR", "T1", "T2", "other", "unknown", "missing"}


def _fields(c):
    return {"description": c["text"], "sequence_name": c.get("sequence_name"), "image_type": c.get("image_type")}


def _klass(c):
    return QG.classify_fields(_fields(c), c["inversion_time_ms"])["class"]


def test_rc122_g12_every_series_description_gets_its_class():
    bad = [(_fields(c), c["expected"], _klass(c)) for c in _corpus() if _klass(c) != c["expected"]]
    assert not bad, f"G12 failed for {len(bad)} of {len(_corpus())} descriptions; first: {bad[:6]}"


def test_rc122_g12_a_non_flair_name_always_abstains_whatever_is_confirmed():
    bad = []
    for c in _corpus():
        if c["expected"] not in ("other", "T1", "T2"):
            continue
        seq = _klass(c)
        visit = {**BASE_VISIT, "sequence": seq, "physician_confirmed_flair": True}
        if QG.evaluate({"mode": "single", "visits": [visit], "platform": PLATFORM_ON}).get("ai_may_run") is not False:
            bad.append(c["text"])
    assert not bad, f"G12: {len(bad)} non-FLAIR names let the AI run after a confirmation: {bad[:6]}"


def _confirmation_modes():
    # The product offers the physician's attestation only in the single-study card (S3; C1).
    return _policy()["sequence"].get("confirmation_modes", ["single"])


def test_rc122_g13_a_confirmation_lifts_only_unknown_or_missing_and_only_where_it_is_offered(results):
    bad = []
    for key, values, inp, out in results:
        confirmed = [v for v in inp["visits"] if v["physician_confirmed_flair"] is True]
        if not confirmed:
            continue
        lifted = "sequence_confirmed_by_physician" in out.get("codes", [])
        if lifted and inp["mode"] not in _confirmation_modes():
            bad.append(key)
        if any(v["sequence"] in ("T1", "T2", "other") for v in confirmed) and out.get("ai_may_run") is not False:
            bad.append(key)
    for seq in ("other", "T1", "T2"):
        for mode, visits in (("single", [{**BASE_VISIT, "sequence": seq, "physician_confirmed_flair": True}]),
                             ("comparison", [BASE_VISIT, {**BASE_VISIT, "sequence": seq, "physician_confirmed_flair": True}])):
            if QG.evaluate({"mode": mode, "visits": visits, "platform": PLATFORM_ON}).get("ai_may_run") is not False:
                bad.append(f"{mode}:{seq}")
    assert not bad, _report("G13", bad)


def _action_key(policy, mode, code):
    return ((policy.get("mode_actions") or {}).get(mode) or {}).get(code, "action")


def test_rc127_g14_every_suggested_action_is_possible_in_its_mode(results):
    """An action that asks for the physician's attestation is shown only where the product offers it."""
    policy = _policy()
    texts = {lang: (_locale(lang).get("qualityGate") or {}).get("codes") or {} for lang in LOCALES}
    asks = re.compile(r"confirmation box|casilla de confirmación|Bestätigungshäkchen", re.IGNORECASE)
    bad = []
    for key, _, inp, out in results:
        for c in out.get("checks", []):
            if c.get("status") == "pass" or not c.get("code"):
                continue
            action = _action_key(policy, inp["mode"], c["code"])
            for lang in LOCALES:
                text = (texts[lang].get(c["code"]) or {}).get(action)
                if not isinstance(text, str) or len(text.strip()) < 12:
                    bad.append(key)
                elif asks.search(text) and inp["mode"] not in _confirmation_modes():
                    bad.append(key)
    assert not bad, _report("G14", bad)


# ----------------------------------------------------------------------------- second review of PR #81
def test_rc122_g15_with_the_gate_on_one_classifier():
    """G15, restated (fifth review) and made structural (sixth review, G27): ONE sequence classifier, the server's
    (quality_gate.classify_fields); with the gate on the RC-049 header evidence takes the class the server returns
    (vitest), with it off it keeps its base rules (G26); the research inventory always keeps its base heuristic."""
    from app.services import dataset_inventory as inv
    for c in _corpus():
        fields = {"description": c["text"], "sequence_name": c.get("sequence_name"), "image_type": c.get("image_type")}
        assert QG.classify_fields(fields, c["inversion_time_ms"])["class"] == c["expected"], c
        if not c.get("sequence_name") and not c.get("image_type"):
            assert QG.sequence_from_header(c["text"], c["inversion_time_ms"]) == c["expected"], c
    assert hasattr(inv, "_SEQUENCE_PATTERNS"), "the inventory keeps its base patterns (G26)"
    assert "quality_gate" not in inspect.getsource(inv), "the inventory does not route to the gate (G26)"
    assert "dataset_inventory.detect_sequence" not in (QG.__doc__ or ""), "the docstring names a router that is gone"


# ----------------------------------------------------------------------------- third review of PR #81
SNAPSHOT = BACKEND / "tests" / "fixtures" / "quality_gate" / "pre_pr_snapshot.v1.json"


def _corpus_by_key():
    return {json.dumps([c.get("text"), c.get("sequence_name"), c.get("image_type"), c.get("inversion_time_ms")]): c
            for c in _corpus()}


def test_rc122_g19_no_flair_accepted_before_this_pr_is_lost():
    """What the pre-PR RC-049 header evidence and inventory accepted as FLAIR is still FLAIR for the gate and the
    inventory, except the documented changes (D-QG-7, S2, a short inversion time)."""
    from app.services import dataset_inventory as inv
    snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    cases = _corpus_by_key()
    bad = []
    for key in snap["rc049_accepted_as_flair"]:
        c = cases[key]
        if _klass(c) in ("other", "T1", "T2") and key not in snap["exceptions"]:
            bad.append(("gate", key))
    for key in snap["inventory_flair"]:
        if inv.detect_sequence(cases[key]["text"] or "") != "FLAIR" and key not in snap["exceptions"]:
            bad.append(("inventory", key))
    undocumented = [k for k, why in snap["exceptions"].items() if not any(d in why for d in ("D-QG-7", "D-QG-11", "D-QG-12", "S2", "inversion time"))]
    assert not undocumented, f"exceptions without a documented decision: {undocumented}"
    assert not bad, f"G19: {len(bad)} pre-PR FLAIR acceptances lost; first: {bad[:6]}"


def test_rc122_g19_star_is_a_siemens_prefix_in_sequence_name():
    for code in ("*tir2d1rr18", "*spcir_278", "*tse2d1_15"):
        got = QG.classify_fields({"description": "t2_tirm_tra_dark-fluid", "sequence_name": code}, None)["class"]
        assert got == "FLAIR", (code, got)
    assert QG.classify_fields({"description": "Ax T2* GRE"}, None)["class"] == "other"    # in a description, T2*


def test_rc122_g20_identifiers_never_change_the_class():
    """Only descriptive text is classified: random UUID or hex fragments in ids or paths never change the class."""
    import random
    import uuid
    from app.services import dataset_inventory as inv
    rng = random.Random(81)
    bad = []
    for c in _corpus():
        if c.get("sequence_name") or c.get("image_type") or c["inversion_time_ms"] is not None:
            continue
        text = c["text"] or ""
        alone = inv.detect_sequence(text)
        for _ in range(12):
            u = [str(uuid.UUID(int=rng.getrandbits(128))) for _ in range(4)]
            frag = "%08x" % rng.getrandbits(32)
            ids = (f"patients/{u[0]}/studies/{u[1]}/series/{u[2]}/{u[3]}.nii.gz",
                   f"patients/{u[0]}/studies/{u[1]}/series/{u[2]}/{frag}_{u[3][:8]}.nii.gz",
                   f"{u[0]}-{frag[:4]}")
            for fid in ids:
                if inv.detect_sequence(text, fid) != alone:
                    bad.append((text, fid))
    assert not bad, f"G20: identifiers changed the class in {len(bad)} cases; first: {bad[:3]}"
