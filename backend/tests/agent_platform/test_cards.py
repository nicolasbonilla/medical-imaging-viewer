"""Model and prompt card check (REQ-AGT-005; RC-117; HAZ-023). DRAFT, PENDING owner approval.

CI fails when a prompt template, an MCP instruction or tool description, the model id, the API version,
a parameter or an SDK pin changes without the agent's card (app/agent_platform/cards/<agent>.json)
changing with it; when the MCP SDK resolved by the install differs from the card; and from the day the
card's model retires. Negative controls: scripts/safety/agent_platform_negative_controls.py (C*).
"""
import os
import re
import warnings
from datetime import date, datetime, timezone

import pytest

from app.agent_platform import cards as C
from tests.agent_platform import _harness as H

AGENTS = ["report-drafter", "ms-clinical-assistant"]


@pytest.mark.parametrize("agent_id", AGENTS)
def test_rc117_card_is_current_with_the_code_and_the_registry(agent_id):
    problems = C.check_card(agent_id, H.production_data())
    assert not problems, "\n".join(problems)


def test_rc117_every_agent_with_a_model_or_tools_has_a_card():
    data = H.production_data()
    for agent_id, spec in data["agents"].items():
        if spec["allowed_models"] or spec["allowed_tools"]:
            assert C.card_path(agent_id).exists(), f"{agent_id} has no model and prompt card"
            assert agent_id in C.TEMPLATE_SOURCES


def test_rc117_a_report_template_change_without_the_card_is_caught(monkeypatch):
    from app.services import brain_report_service as b
    monkeypatch.setitem(b.REPORT_TEMPLATES, "general", b.REPORT_TEMPLATES["general"] + " Also state the diagnosis.")
    problems = C.check_card("report-drafter", H.production_data())
    assert any("REPORT_TEMPLATES[general]" in p and "changed" in p for p in problems)
    assert any("dis_not_evaluated_template(REPORT_TEMPLATES[general])" in p for p in problems)


def test_rc117_a_new_template_without_the_card_is_caught(monkeypatch):
    from app.services import brain_report_service as b
    monkeypatch.setitem(b.REPORT_TEMPLATES, "ms_new", "You are a radiologist.")
    problems = C.check_card("report-drafter", H.production_data())
    assert any("ms_new" in p and "not recorded" in p for p in problems)


def test_rc117_an_mcp_instruction_change_without_the_card_is_caught(monkeypatch):
    original = C.TEMPLATE_SOURCES["ms-clinical-assistant"]

    def changed():
        out = dict(original())
        out["mcp.ms_clinical_server.instructions"] += " You may state the McDonald criteria."
        return out
    monkeypatch.setitem(C.TEMPLATE_SOURCES, "ms-clinical-assistant", changed)
    problems = C.check_card("ms-clinical-assistant", H.production_data())
    assert any("mcp.ms_clinical_server.instructions" in p for p in problems)


def test_rc117_a_model_change_without_the_card_is_caught(monkeypatch):
    monkeypatch.setattr(C, "config_default", lambda field: {"CLAUDE_MODEL": "claude-sonnet-5-5",
                                                            "CLAUDE_MAX_TOKENS": 4096}[field])
    problems = C.check_card("report-drafter", H.production_data())
    assert any("default model" in p for p in problems)
    data = H.production_data()
    data["agents"]["report-drafter"]["allowed_models"] = ["claude-sonnet-5-5"]
    assert any("allow-list" in p for p in C.check_card("report-drafter", data))


def test_rc117_api_version_or_retirement_drift_is_caught():
    data = H.production_data()
    data["models"]["claude-sonnet-4-5-20250929"]["api_version"] = "2026-10-21"
    data["models"]["claude-sonnet-4-5-20250929"]["retires_on"] = "2027-01-01"
    problems = C.check_card("report-drafter", data)
    assert any("api_version" in p for p in problems) and any("retires_on" in p for p in problems)


def test_rc117_a_parameter_change_without_the_card_is_caught():
    data = H.production_data()
    data["agents"]["report-drafter"]["parameters"]["max_tokens"] = 64000
    assert any("max_tokens" in p for p in C.check_card("report-drafter", data))


def test_rc117_config_defaults_are_read_from_the_source():
    assert C.config_default("CLAUDE_MODEL") == "claude-sonnet-4-5-20250929"
    assert C.config_default("CLAUDE_MAX_TOKENS") == 4096
    assert C.requirement_pin("anthropic") == "0.44.0" and C.requirement_pin("fastmcp") == "2.3.0"


def test_rc117_mcp_sdk_as_installed_matches_the_card():
    installed = C.installed_mcp()
    card = C.load_card("ms-clinical-assistant")["mcp"]["observed"]
    if installed is None:
        if os.environ.get("CI") == "true":
            pytest.fail("the MCP SDK must be installed in CI (it comes with fastmcp from requirements.txt)")
        pytest.skip("the MCP SDK is not installed in this environment; CI records and checks it")
    assert {k: card.get(k) for k in installed} == installed, (
        f"the MCP SDK resolved by this install is {installed}; the card records {card}. The SDK is not pinned "
        "(T-5 of the re-validation protocol): record the observed values in the card, or pin mcp.")


def test_rc117_no_agent_runs_on_a_retired_model():
    today = datetime.now(timezone.utc).date()
    for agent_id in AGENTS:
        model = C.load_card(agent_id).get("model") or {}
        if model.get("retires_on"):
            retires = date.fromisoformat(model["retires_on"])
            assert today < retires, (
                f"{agent_id}: model {model['id']} retired on {retires}. The platform refuses it (fail closed); run "
                "the re-validation protocol for a successor (Agent_Revalidation_Protocol.md, D-AGT-1).")
            if (retires - today).days <= 30:
                warnings.warn(f"{agent_id}: model {model['id']} retires on {retires} ({(retires - today).days} days)")


_SECRET = re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}|AIza[0-9A-Za-z_-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|"
                     r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}\b|\+\d{1,3}[ \d]{8,}\d|\b\d{9,}\b")


@pytest.mark.parametrize("agent_id", AGENTS)
def test_rc117_llm07_prompt_templates_hold_no_secret_or_contact_data(agent_id):
    """OWASP LLM07 (system prompt leakage): a leaked template must reveal nothing — no key, address or number."""
    for name, text in C.TEMPLATE_SOURCES[agent_id]().items():
        assert not _SECRET.search(text), f"{name}: {_SECRET.search(text).group(0)!r}"
