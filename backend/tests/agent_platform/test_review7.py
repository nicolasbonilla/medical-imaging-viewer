"""Findings of the SEVENTH independent adversarial review of PR #79 — failing-first tests.

DRAFT, PENDING owner approval. Written against 677ebe8, where these tests fail; fixes follow.

R1 (safety): the MODEL chose the study ids of the study session, so injected study text could open another patient's
   study. The scope is now chosen by the HUMAN: the session tools take no ids; the server asks the physician
   through the client (MCP elicitation) for the study and then for a confirmation written by the server (patient
   reference, study date, series); a client without elicitation, a decline or a cancel opens nothing; a session for
   another patient needs a fresh confirmation and is audited as a patient switch.
R2 generate_ms_report removed from the server and its instructions. R3/R4/R9 the shared rule applied ONCE at the
source, always; the platform checks the viewed result, no second view; one implementation. R5 the assistant always
needs a scope (no dead option). R6 path traversal in a path parameter. R7 a refused write is a denial. R8 no registry
parse per call. R10 issuance builds the services once and stops at the first refusal.
"""
import asyncio
import importlib
import inspect
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.agent_platform import registry as R
from app.agent_platform import runtime as RT
from app.agent_platform import tracing as T
from app.agent_platform.registry import AgentRegistry, InMemoryKillSwitches, RefusalCode
from app.agent_platform.untrusted import RunScope
from tests.agent_platform import _harness as H
from tests.agent_platform._fixtures import FIXED_NOW, make_registry_data
from tests.agent_platform.test_review5 import (FILE_IN, P1, P2, S1, S3, SEG_IN, USER, _Backend, _scope_module,
                                               scope_key)  # noqa: F401
from tests.agent_platform.test_review6 import _assistant_app, _cap, assistant  # noqa: F401

BACKEND = Path(__file__).resolve().parents[2]


class Human:
    """The physician at the client: answers the server's elicitations (the model never sees them)."""

    def __init__(self, *answers):
        self.answers, self.asked = list(answers), []

    async def elicit(self, message, response_type=None, **kwargs):
        self.asked.append(message)
        action, data = self.answers.pop(0)
        return SimpleNamespace(action=action, data=data)


class NoElicitation:
    async def elicit(self, message, response_type=None, **kwargs):
        raise RuntimeError("Method not found: elicitation/create")          # what a client without it answers


# ================================================================== R1: the human chooses the scope
def test_rc121_review7_the_model_cannot_choose_the_studies(assistant):
    server, backend, _app, _paid = assistant
    for name in ("open_study_session",):
        params = [p for p in inspect.signature(getattr(server, name)).parameters if p != "ctx"]
        assert params == [], f"{name} takes no study id from the model"
    tools = H.production_data()["tools"]
    assert tools["open_study_session"]["arguments"] == {} and tools["open_imaging_session"]["arguments"] == {}


def test_rc121_review7_an_injected_open_without_human_confirmation_grants_nothing(assistant):
    server, backend, _app, _paid = assistant
    CAP = _cap()
    human = Human(("accept", S3), ("decline", None))       # steered to another patient; the physician declines
    with pytest.raises(CAP.ScopeRequired):
        asyncio.run(server.open_study_session(human))
    assert not backend._SESSION.get("token") and len(human.asked) == 2
    assert "patient" in human.asked[1].lower() and P2[:8] in human.asked[1]     # the server names the patient
    with pytest.raises(CAP.ScopeRequired):
        asyncio.run(server.analyze_lesions(SEG_IN))


@pytest.mark.parametrize("ctx", [None, NoElicitation(), Human(("cancel", None))])
def test_rc121_review7_a_client_without_elicitation_or_a_cancel_gets_no_session(assistant, ctx):
    server, backend, _app, _paid = assistant
    with pytest.raises(_cap().ScopeRequired):
        asyncio.run(server.open_study_session(ctx))
    assert not backend._SESSION.get("token")


def test_rc121_review7_a_patient_switch_needs_a_fresh_confirmation_and_is_audited(assistant, monkeypatch):
    server, backend, _app, _paid = assistant
    import app.core.logging.audit as audit
    emitted = []
    real = audit.emit_audit
    monkeypatch.setattr(audit, "emit_audit", lambda *a, **k: (emitted.append(k.get("reason")), real(*a, **k)))
    first = Human(("accept", S1), ("accept", None))
    asyncio.run(server.open_study_session(first))
    assert backend._SESSION.get("token") and asyncio.run(server.analyze_lesions(SEG_IN)) == {"lesion_count": 7}
    second = Human(("accept", S3), ("accept", None))
    asyncio.run(server.open_study_session(second))
    assert len(second.asked) == 2 and P2[:8] in second.asked[1]
    assert sum(1 for r in emitted if r and "patient_switch" in r) == 1, emitted
    with pytest.raises(_cap().ScopeRefused):
        asyncio.run(server.analyze_lesions(SEG_IN))           # the old patient is out of the new session


# ================================================================== R2: no dead report tool
def test_review7_generate_ms_report_is_gone_from_the_assistant(assistant):
    server, _b, _a, _p = assistant
    assert not hasattr(server, "generate_ms_report")
    instructions = server.mcp.instructions
    assert "generate_ms_report" not in instructions and "verified-report" in instructions


# ================================================================== R3, R4, R9: the shared rule once, at the source
def test_rc113_review7_identifiers_and_activity_flags_are_removed_at_the_source_inside_a_run(scope_key, monkeypatch):
    from fastapi import Depends

    import app.security.patient_access_dependency as pad
    from app.mcp import _backend
    from app.security.auth import get_current_active_user
    S = _scope_module()
    _Backend().install(monkeypatch)
    app, _paid = _assistant_app()

    @app.get("/api/v1/imaging/metadata/{file_id:path}", include_in_schema=False)
    async def metadata_with_identifiers(file_id: str, current_user=Depends(get_current_active_user)):
        await pad.require_imaging_access(file_id, current_user)
        return {"patient_id": "MRN-0042", "PatientName": "Doe^Jane", "StudyDate": "20261109", "shape": [256, 256, 60],
                "activity_candidate": True, "nested": {"dit_candidate": True}}
    app.router.routes.insert(0, app.router.routes.pop())          # this route answers first
    monkeypatch.setattr(_backend, "_TRANSPORT", httpx.ASGITransport(app=app), raising=False)
    monkeypatch.setenv("API_BASE_URL", "http://testserver")
    seen = []

    async def get_image_metadata(file_id):
        out = await _backend.api_get(f"/imaging/metadata/{file_id}")
        seen.append(out)
        return out
    data = make_registry_data()
    data["tools"]["get_image_metadata"] = {"access": "read", "arguments": {"file_id": "resource_id"},
                                           "output": {"type": "object", "resource_fields": [], "actor_fields": [],
                                                      "exempt_fields": []}}
    data["agents"]["test-agent"]["allowed_tools"].append("get_image_metadata")
    reg = AgentRegistry(data, switches=InMemoryKillSwitches({"test-agent": True}), clock=lambda: FIXED_NOW)
    token = S.issue_scope_token(user_id=USER.id, patient_id=P1, study_ids=[S1], run_id="run-1")
    model = H.ScriptedModel([
        RT.ModelResponse("model-current", "", (RT.ToolCall("c1", "get_image_metadata", {"file_id": FILE_IN}),),
                         10, 10, "tool_use"),
        RT.ModelResponse("model-current", "The image has 60 slices.", (), 10, 10, "end_turn")])
    res = asyncio.run(RT.AgentRuntime(reg, T.Tracer(T.NoopExporter()), tools={"get_image_metadata": get_image_metadata}
                                      ).arun("test-agent", model_client=model,
                                             scope=RunScope(S1, frozenset({FILE_IN}), capability=token),
                                             system="s", user_content="u"))
    assert res.status == "delivered", (res.status, res.code)                 # no false out-of-scope rejection
    text = str(seen) + str(model.requests[-1].messages)
    for leaked in ("MRN-0042", "Doe", "20261109", "activity_candidate", "dit_candidate"):
        assert leaked not in text, leaked


def test_rc113_review7_one_implementation_of_the_shared_rule():
    from app.mcp import _backend
    from app.agent_platform import untrusted as U
    assert not hasattr(_backend, "drop_direct_identifiers") and not hasattr(_backend, "drop_unconfirmed_activity_flags")
    src = inspect.getsource(U.validate_tool_result)
    assert "assistant_view(" not in src, "the platform checks the viewed result; it does not view it again"


# ================================================================== R5, R8: the assistant always needs a scope
def test_rc121_review7_the_assistant_always_needs_a_scope():
    from app.mcp import _backend
    assert not hasattr(_backend, "_requires_scope"), "no per-call registry read, no dead option"
    data = H.production_data()
    data["agents"]["ms-clinical-assistant"]["requires_backend_scope"] = False
    assert not AgentRegistry(data, switches=InMemoryKillSwitches({}), clock=lambda: FIXED_NOW).valid


# ================================================================== R6: path traversal
@pytest.mark.parametrize("bad", [f"../../patients/{P2}", f"{FILE_IN}/../../../x", "patients%2f..%2fx",
                                 "patients\\x", "%2e%2e/patients"])
def test_rc121_review7_a_traversal_in_a_path_parameter_is_refused_before_sending(assistant, bad):
    server, backend, _app, _paid = assistant
    asyncio.run(server.open_study_session(Human(("accept", S1), ("accept", None))))
    sent = []
    real = backend._TRANSPORT.handle_async_request

    async def spy(request):
        sent.append(str(request.url))
        return await real(request)
    backend._TRANSPORT.handle_async_request = spy
    with pytest.raises(_cap().ScopeRefused):
        asyncio.run(backend.api_get(f"/imaging/metadata/{bad}"))
    assert sent == []
    assert not _scope_module().route_allowed("GET", f"/api/v1/imaging/metadata/{bad}")


# ================================================================== R7: a refused write is a denial
def test_rc110_review7_a_refused_write_is_audited_as_a_denial(registry, audit_events):
    from app.mcp import _backend

    async def writer(segmentation_id):
        return await _backend.api_post_compute(f"/segmentation/{segmentation_id}/save", {})
    model = H.ScriptedModel([RT.ModelResponse("model-current", "", (RT.ToolCall("c1", "read_measurements",
                                                                                {"segmentation_id": "seg-1"}),),
                                              10, 10, "tool_use")])
    res = asyncio.run(RT.AgentRuntime(registry, T.Tracer(T.NoopExporter()), tools={"read_measurements": writer}).arun(
        "test-agent", model_client=model, scope=RunScope("study-1", frozenset({"seg-1"}), capability="pass"),
        system="s", user_content="u"))
    assert res.status == "refused" and res.code == RefusalCode.TOOL_NOT_ALLOWED
    assert [e for e in audit_events if e.get("event") == "agent.run"][-1]["outcome"] == "denied"


# ================================================================== R10: issuance stops at the first refusal
def test_rc121_review7_issuance_builds_services_once_and_stops_at_the_first_refusal(scope_key, monkeypatch):
    import app.security.resource_access as ra
    from fastapi import HTTPException
    S = _scope_module()
    env = _Backend()
    env.install(monkeypatch)
    built = []
    monkeypatch.setattr(ra, "_study_service", lambda: (built.append("studies"), env.studies)[1])
    calls = []
    real = ra.authorize_study_id

    async def counting(study_id, user, **kwargs):
        calls.append(study_id)
        if study_id == S3:
            raise HTTPException(status_code=404, detail="Study not found")
        return await real(study_id, user, **kwargs)
    monkeypatch.setattr(ra, "authorize_study_id", counting)
    ids = sorted([S1, S3, "d4e5f6a7-b8c9-4d0e-9f1a-2b3c4d5e6f70"])
    with pytest.raises(HTTPException):
        asyncio.run(S.issue_for_studies(ids, USER, run_id="r"))
    assert calls == ids[:ids.index(S3) + 1], "no study is authorized after the first refusal"
    assert built.count("studies") <= 1, built
