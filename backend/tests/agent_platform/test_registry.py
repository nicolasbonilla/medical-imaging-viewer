"""Agent registry — fail-closed authorization (REQ-AGT-001; RC-110, RC-111, RC-112, RC-115; HAZ-020).

DRAFT, PENDING owner approval. Written before app/agent_platform/registry.py existed (failing first).
Negative controls: scripts/safety/agent_platform_negative_controls.py (mutations R*).

What is bound here:
- RC-110: an unknown agent, model or tool, an agent not approved by the owner, a write tool, a model not
  approved for use or past its retirement date is refused, and every refusal is audited with its code;
  a registry that does not validate refuses everything.
- RC-111: the per-agent kill switch is read again at EVERY call, and a switch that cannot be read is off.
- RC-112: a model call is refused when its worst-case cost would pass the agent's cap for the study or
  for the day; an unpriced model is refused (its cost cannot be bounded).
- RC-115: model ids are matched exactly (no alias, prefix, case, whitespace or look-alike character).
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.agent_platform import registry as R
from tests.agent_platform._fixtures import FIXED_NOW, make_registry_data

PRODUCTION_REGISTRY = Path(R.__file__).with_name("agents.json")


def _codes(events):
    return [e.get("code") for e in events]


# ------------------------------------------------------------------ RC-110 identity and approval
def test_rc110_known_approved_agent_with_switch_on_is_allowed(registry):
    d = registry.check_agent("test-agent")
    assert d.allowed and d.code == "ok", d


def test_rc110_unknown_agent_is_refused_and_audited(registry, audit_events):
    d = registry.check_agent("ghost-agent")
    assert not d.allowed and d.code == R.RefusalCode.UNKNOWN_AGENT
    assert audit_events and audit_events[-1]["code"] == R.RefusalCode.UNKNOWN_AGENT
    assert audit_events[-1]["outcome"] == "denied"


def test_rc110_agent_not_approved_by_the_owner_is_refused(registry, audit_events):
    d = registry.check_agent("pending-agent")
    assert not d.allowed and d.code == R.RefusalCode.AGENT_NOT_APPROVED
    assert _codes(audit_events)[-1] == R.RefusalCode.AGENT_NOT_APPROVED


@pytest.mark.parametrize("bad_id", ["", "TEST-AGENT", "test agent", "test-agent\n", "../test-agent",
                                    "test‐agent", "x" * 65, None, 7])
def test_rc110_malformed_agent_id_is_refused_and_not_echoed(registry, audit_events, bad_id):
    d = registry.check_agent(bad_id)
    assert not d.allowed and d.code == R.RefusalCode.UNKNOWN_AGENT
    assert audit_events[-1]["agent_id"] == "invalid"        # the raw value is never written to the audit log


def test_rc110_unknown_tool_and_write_tool_are_refused(registry, audit_events):
    assert registry.check_tool("test-agent", "read_measurements").allowed
    d = registry.check_tool("test-agent", "delete_everything")
    assert not d.allowed and d.code == R.RefusalCode.UNKNOWN_TOOL
    d = registry.check_tool("test-agent", "write_annotation")
    assert not d.allowed and d.code == R.RefusalCode.WRITE_TOOL_REFUSED
    assert _codes(audit_events)[-2:] == [R.RefusalCode.UNKNOWN_TOOL, R.RefusalCode.WRITE_TOOL_REFUSED]


def test_rc110_tool_of_another_agent_is_refused(registry):
    assert registry.check_tool("test-agent", "compare_visits").allowed
    d = registry.check_tool("other-agent", "compare_visits")
    assert not d.allowed and d.code == R.RefusalCode.TOOL_NOT_ALLOWED


def test_rc110_registry_that_lists_a_write_tool_for_an_agent_refuses_everything(switches, ledger, audit_events):
    data = make_registry_data()
    data["agents"]["test-agent"]["allowed_tools"].append("write_annotation")
    reg = R.AgentRegistry(data, switches=switches, ledger=ledger, audit=audit_events.append,
                          clock=lambda: FIXED_NOW)
    assert not reg.valid
    for d in (reg.check_agent("test-agent"), reg.check_agent("other-agent"),
              reg.check_tool("other-agent", "read_measurements"), reg.check_model("other-agent", "model-current")):
        assert not d.allowed and d.code == R.RefusalCode.REGISTRY_INVALID
    assert R.RefusalCode.REGISTRY_INVALID in _codes(audit_events)


@pytest.mark.parametrize("breakage", [
    lambda d: d["agents"]["test-agent"]["allowed_models"].append("model-nowhere"),
    lambda d: d["agents"]["test-agent"]["allowed_tools"].append("tool-nowhere"),
    lambda d: d["agents"]["test-agent"].pop("cost_cap_usd"),
    lambda d: d["agents"]["test-agent"]["cost_cap_usd"].update(per_study=-1),
    lambda d: d["agents"]["test-agent"]["limits"].update(max_steps=0),
    lambda d: d["models"]["model-current"].update(retires_on="30/11/2026"),
    lambda d: d["agents"]["test-agent"]["approval"].update(status="approved-ish"),
    lambda d: d.pop("agents"),
])
def test_rc110_malformed_registry_fails_closed(switches, ledger, audit_events, breakage):
    data = make_registry_data()
    breakage(data)
    reg = R.AgentRegistry(data, switches=switches, ledger=ledger, audit=audit_events.append,
                          clock=lambda: FIXED_NOW)
    assert not reg.valid
    assert reg.check_agent("other-agent").code == R.RefusalCode.REGISTRY_INVALID


def test_rc110_spec_is_immutable(registry):
    spec = registry.agent("test-agent")
    with pytest.raises(Exception):
        spec.allowed_tools = frozenset({"write_annotation"})
    with pytest.raises(Exception):
        spec.allowed_tools.add("write_annotation")          # frozenset: no in-place change


def test_rc110_production_registry_is_valid_and_every_agent_is_pending_the_owner(switches, ledger, audit_events):
    """The repository registry validates, and NO entry claims the owner's approval (only he records it)."""
    data = json.loads(PRODUCTION_REGISTRY.read_text(encoding="utf-8"))
    reg = R.AgentRegistry(data, switches=switches, ledger=ledger, audit=audit_events.append,
                          clock=lambda: FIXED_NOW)
    assert reg.valid, reg.errors
    assert data["agents"], "the production registry lists no agent"
    for agent_id, spec in data["agents"].items():
        assert spec["approval"]["status"] != "approved", f"{agent_id}: only the owner records an approval"
        assert not reg.check_agent(agent_id).allowed
    for tool, entry in data["tools"].items():
        if entry["access"] == "write":
            assert all(tool not in a["allowed_tools"] for a in data["agents"].values())


def test_rc110_production_registry_lists_the_report_model_with_its_retirement_date():
    """claude-sonnet-4-5-20250929 (the report model on main) retires on 2026-11-30 (Anthropic model
    deprecations page, read 2026-11-10); the registry must carry that date so the platform stops using it."""
    data = json.loads(PRODUCTION_REGISTRY.read_text(encoding="utf-8"))
    model = data["models"]["claude-sonnet-4-5-20250929"]
    assert model["retires_on"] == "2026-11-30"


# ------------------------------------------------------------------ RC-111 kill switch
def test_rc111_switch_is_read_at_every_call(registry, switches, audit_events):
    assert registry.check_agent("test-agent").allowed
    switches.set("test-agent", False)
    d = registry.check_agent("test-agent")
    assert not d.allowed and d.code == R.RefusalCode.AGENT_SWITCHED_OFF
    assert not registry.check_tool("test-agent", "read_measurements").allowed
    assert not registry.check_model("test-agent", "model-current").allowed
    switches.set("test-agent", True)
    assert registry.check_tool("test-agent", "read_measurements").allowed
    assert switches.reads >= 4, "the switch must be consulted on every call, not cached"


def test_rc111_switch_is_per_agent(registry, switches):
    switches.set("test-agent", False)
    assert registry.check_agent("other-agent").allowed


def test_rc111_unreadable_switch_is_off(switches, ledger, audit_events):
    class Broken:
        def is_on(self, agent_id):
            raise OSError("switch store unreachable")

    reg = R.AgentRegistry(make_registry_data(), switches=Broken(), ledger=ledger, audit=audit_events.append,
                          clock=lambda: FIXED_NOW)
    d = reg.check_agent("test-agent")
    assert not d.allowed and d.code == R.RefusalCode.SWITCH_UNREADABLE


def test_rc111_environment_switch_is_off_unless_exactly_on(monkeypatch):
    sw = R.EnvKillSwitches()
    monkeypatch.delenv("MSTOOL_AGENT_SWITCH__TEST_AGENT", raising=False)
    assert not sw.is_on("test-agent")                                   # absent: off
    for value in ("ON", "true", "1", "yes", " on", "on "):
        monkeypatch.setenv("MSTOOL_AGENT_SWITCH__TEST_AGENT", value)
        assert not sw.is_on("test-agent"), value
    monkeypatch.setenv("MSTOOL_AGENT_SWITCH__TEST_AGENT", "on")
    assert sw.is_on("test-agent")
    monkeypatch.setenv("MSTOOL_AGENTS_SWITCH", "off")                    # the master switch wins
    assert not sw.is_on("test-agent")


# ------------------------------------------------------------------ RC-110 / RC-115 models
def test_rc110_model_not_allowed_for_the_agent_is_refused(registry):
    d = registry.check_model("other-agent", "model-retiring")
    assert not d.allowed and d.code == R.RefusalCode.MODEL_NOT_ALLOWED


def test_rc110_model_not_approved_for_use_is_refused(registry):
    d = registry.check_model("test-agent", "model-unapproved")
    assert not d.allowed and d.code == R.RefusalCode.MODEL_NOT_APPROVED


def test_rc110_retired_model_is_refused_on_and_after_its_date(switches, ledger, audit_events):
    def at(day):
        return R.AgentRegistry(make_registry_data(), switches=switches, ledger=ledger, audit=audit_events.append,
                               clock=lambda: datetime(2026, 11, day, 9, 0, tzinfo=timezone.utc))
    assert at(29).check_model("test-agent", "model-retiring").allowed
    d = at(30).check_model("test-agent", "model-retiring")
    assert not d.allowed and d.code == R.RefusalCode.MODEL_RETIRED
    assert at(10).check_model("test-agent", "model-retired").code == R.RefusalCode.MODEL_RETIRED


def test_rc110_model_close_to_retirement_carries_a_warning(registry):
    d = registry.check_model("test-agent", "model-retiring")
    assert d.allowed and any("2026-11-30" in w for w in d.warnings)
    assert not registry.check_model("test-agent", "model-current").warnings


@pytest.mark.parametrize("impersonation", ["Model-Current", "model-current ", " model-current", "model-current​",
                                           "model‐current", "model-currеnt", "model-current-latest",
                                           "model-curren", "model", "", None])
def test_rc115_model_id_must_match_exactly(registry, impersonation):
    d = registry.check_model("test-agent", impersonation)
    assert not d.allowed and d.code == R.RefusalCode.UNKNOWN_MODEL


# ------------------------------------------------------------------ RC-112 cost caps
def test_rc112_estimate_uses_the_worst_case_output(registry):
    # 10 000 input tokens at $3/MTok + 1 000 output tokens at $15/MTok = 0.03 + 0.015
    assert registry.estimate_cost_usd("model-current", 10_000, 1_000) == pytest.approx(0.045)


def test_rc112_unpriced_model_is_refused(registry):
    d = registry.authorize_model_call("test-agent", "model-unpriced", study_key="s1", input_tokens=10, max_output_tokens=10)
    assert not d.allowed and d.code == R.RefusalCode.COST_UNKNOWN


def test_rc112_study_cap_refuses_the_call_that_would_pass_it(registry, audit_events):
    # cap 0.50 per study; each call's worst case is 0.045
    for _ in range(11):
        d = registry.authorize_model_call("test-agent", "model-current", study_key="s1",
                                          input_tokens=10_000, max_output_tokens=1_000)
        assert d.allowed, d
        registry.record_cost("test-agent", "s1", 0.045)
    d = registry.authorize_model_call("test-agent", "model-current", study_key="s1",
                                      input_tokens=10_000, max_output_tokens=1_000)
    assert not d.allowed and d.code == R.RefusalCode.STUDY_COST_CAP
    assert _codes(audit_events)[-1] == R.RefusalCode.STUDY_COST_CAP
    # another study is not affected
    assert registry.authorize_model_call("test-agent", "model-current", study_key="s2",
                                         input_tokens=10_000, max_output_tokens=1_000).allowed


def test_rc112_day_cap_spans_studies_and_resets_the_next_day(switches, ledger, audit_events):
    now = {"t": FIXED_NOW}
    reg = R.AgentRegistry(make_registry_data(), switches=switches, ledger=ledger, audit=audit_events.append,
                          clock=lambda: now["t"])
    for i in range(4):                     # 4 studies x 0.49 = 1.96 of the 2.00 daily cap
        reg.record_cost("test-agent", f"s{i}", 0.49)
    d = reg.authorize_model_call("test-agent", "model-current", study_key="s9", input_tokens=10_000,
                                 max_output_tokens=1_000)
    assert not d.allowed and d.code == R.RefusalCode.DAY_COST_CAP
    now["t"] = FIXED_NOW + timedelta(days=1)
    assert reg.authorize_model_call("test-agent", "model-current", study_key="s9", input_tokens=10_000,
                                    max_output_tokens=1_000).allowed


def test_rc112_costs_are_per_agent(registry):
    registry.record_cost("test-agent", "s1", 0.49)
    assert registry.authorize_model_call("other-agent", "model-current", study_key="s1",
                                         input_tokens=10_000, max_output_tokens=1_000).allowed


@pytest.mark.parametrize("tokens", [(-1, 10), (10, -1), (10**9, 10), (10, 10**9), ("10", 10), (None, 10)])
def test_rc112_impossible_token_counts_are_refused(registry, tokens):
    d = registry.authorize_model_call("test-agent", "model-current", study_key="s1",
                                      input_tokens=tokens[0], max_output_tokens=tokens[1])
    assert not d.allowed and d.code in (R.RefusalCode.LIMIT_EXCEEDED, R.RefusalCode.COST_UNKNOWN)


def test_rc112_negative_or_unbounded_recorded_cost_is_rejected(registry):
    with pytest.raises(ValueError):
        registry.record_cost("test-agent", "s1", -0.01)
    with pytest.raises(ValueError):
        registry.record_cost("test-agent", "s1", float("nan"))


# ------------------------------------------------------------------ audit content
def test_rc110_audit_events_carry_codes_and_identifiers_only(registry, audit_events):
    registry.check_agent("ghost-agent")
    registry.check_tool("test-agent", "write_annotation")
    registry.authorize_model_call("test-agent", "model-unpriced", study_key="patient-name-Jane-Doe",
                                  input_tokens=1, max_output_tokens=1)
    allowed_keys = {"event", "outcome", "agent_id", "code", "model_id", "tool", "study_key", "trace_id",
                    "registry_version", "reason"}
    for e in audit_events:
        assert set(e) <= allowed_keys, set(e) - allowed_keys
        assert "Jane" not in json.dumps(e), "a study key is pseudonymised before it is audited"
