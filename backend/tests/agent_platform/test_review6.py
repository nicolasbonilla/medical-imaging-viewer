"""Findings of the SIXTH independent adversarial review of PR #79 — failing-first tests.

DRAFT, PENDING owner approval. Written against c05e7ac, where these tests fail; fixes follow.

S1 (safety): RC-121 never applied on the real path — the MCP servers (STDIO, Claude Desktop / Code) never set a
   capability, and the backend let their unscoped requests through. Now the assistant fails closed: it is refused
   LOCALLY without a study session, the backend ALSO refuses any assistant request without a valid scope (the
   client marks every request it sends), and the legitimate way in is a session tool that obtains the pass from
   /agent-scope with the clinician's token (the pass never reaches the model).
S2 (safety): the paid report route was reachable under an agent scope, outside the agent's cost ledger (RC-112).
C1 a scope 404 inside a broad `except Exception` became a 500, audited as a tool failure instead of a denial;
C2 the issuance route re-implemented issue_for_studies; C3 two hand-written route lists disagreed; C4 the same
patient in two spellings counted as two; E1 serial, undeduplicated authorization; E2 the bracket table was
computed on first use (blocking a cold event loop); E3 assistant_view applied twice; E4 _expire scanned everything.
"""
import ast
import asyncio
import importlib
import inspect
import time
import unicodedata
from pathlib import Path

import httpx
import pytest

from app.agent_platform import oversight as O
from app.agent_platform import registry as R
from app.agent_platform import runtime as RT
from app.agent_platform import tracing as T
from app.agent_platform import untrusted as U
from app.agent_platform.registry import AgentRegistry, InMemoryKillSwitches
from app.agent_platform.untrusted import RunScope
from tests.agent_platform import _harness as H
from tests.agent_platform._fixtures import FIXED_NOW, make_registry_data
from tests.agent_platform.test_review5 import (FILE_PRIOR, P1, S1, S2, SEG_IN, SEG_OTHER, SEG_PRIOR, USER, _Backend,
                                               _bracket_like, _scope_module, _scoped_app, scope_key)  # noqa: F401

BACKEND = Path(__file__).resolve().parents[2]


def _cap():
    return importlib.import_module("app.agent_platform.capability")


class _Physician:
    """Amended for the seventh review of PR #79 (R1): a session is opened by the PHYSICIAN through the client
    (elicitation): they type the study id, then confirm the server's description."""

    def __init__(self, study_id):
        self.answers = [("accept", study_id), ("accept", None)]

    async def elicit(self, message, response_type=None, **kwargs):
        action, data = self.answers.pop(0)
        return type("Answer", (), {"action": action, "data": data})()


def _assistant_app():
    """The scoped test backend, plus the lesion-analysis route, a paid model route and the REAL issuance route."""
    from fastapi import Depends

    import app.security.resource_access as ra
    from app.api.routes import agent_scope as issuance
    app = _scoped_app(USER)
    paid = []

    @app.get("/api/v1/segmentation/{segmentation_id}/lesion-analysis",
             dependencies=[Depends(ra.require_segmentation_access)])
    async def lesions(segmentation_id: str):
        return {"lesion_count": 7}

    @app.post("/api/v1/ai/report/generate")
    async def report():
        paid.append(1)
        return {"content": "AI draft"}
    app.include_router(issuance.router, prefix="/api/v1")
    return app, paid


@pytest.fixture
def assistant(scope_key, monkeypatch):
    """The REAL ms-clinical MCP server module (as run over STDIO), talking to the test backend in-process."""
    from app.mcp import _backend
    from tests.agent_platform._mcp import load_mcp_module
    _Backend().install(monkeypatch)
    app, paid = _assistant_app()
    monkeypatch.setattr(_backend, "_TRANSPORT", httpx.ASGITransport(app=app), raising=False)
    monkeypatch.setattr(_backend, "_SESSION", {}, raising=False)
    monkeypatch.setenv("API_BASE_URL", "http://testserver")
    return load_mcp_module("ms_clinical_server"), _backend, app, paid


# ================================================================== S1: the STDIO assistant fails closed
def test_rc121_review6_stdio_assistant_without_a_session_is_refused_locally_and_by_the_backend(assistant, monkeypatch):
    server, backend, _app, _paid = assistant
    CAP = _cap()
    with pytest.raises(CAP.ScopeRequired):
        asyncio.run(server.analyze_lesions(SEG_OTHER))                 # no session: nothing is sent
    monkeypatch.setattr(backend, "_require_pass", lambda capability: None)   # the local check bypassed (a bug) ...
    with pytest.raises(CAP.ScopeRefused) as e:
        asyncio.run(server.analyze_lesions(SEG_OTHER))
    assert e.value.status == 403                                        # ... the backend refuses it anyway


def test_rc121_review6_a_study_session_is_the_way_in_and_its_pass_never_reaches_the_model(assistant):
    server, backend, _app, _paid = assistant
    CAP = _cap()
    info = asyncio.run(server.open_study_session(_Physician(S1)))
    assert "token" not in info and backend._SESSION.get("token") and backend._SESSION["token"] not in str(info)
    assert asyncio.run(server.analyze_lesions(SEG_IN)) == {"lesion_count": 7}
    for foreign in (SEG_OTHER, SEG_PRIOR):                             # another patient; same patient, other study
        with pytest.raises(CAP.ScopeRefused):
            asyncio.run(server.analyze_lesions(foreign))
    backend._SESSION["expires_at"] = 0                                   # the session ended
    with pytest.raises(CAP.ScopeRequired):
        asyncio.run(server.analyze_lesions(SEG_IN))
    agent = H.production_data()["agents"]["ms-clinical-assistant"]
    assert agent["requires_backend_scope"] is True
    assert {"open_study_session", "open_imaging_session"} <= set(agent["allowed_tools"])


# ================================================================== S2: no paid model call under an agent scope
def test_rc112_review6_the_paid_report_route_is_out_of_reach_of_an_agent(assistant):
    from fastapi.testclient import TestClient
    server, backend, app, paid = assistant
    S, CAP = _scope_module(), _cap()
    assert not S.route_allowed("POST", "/api/v1/ai/report/generate")
    token = S.issue_scope_token(user_id=USER.id, patient_id=P1, study_ids=[S1], run_id="r")
    assert TestClient(app).post("/api/v1/ai/report/generate", json={},
                                headers={CAP.CAPABILITY_HEADER: token}).status_code == 403
    asyncio.run(server.open_study_session(_Physician(S1)))
    with pytest.raises(PermissionError):
        asyncio.run(backend.api_post_compute("/ai/report/generate", {}))
    assert paid == [], "no paid model call was made"
    assert "generate_ms_report" not in H.production_data()["agents"]["ms-clinical-assistant"]["allowed_tools"]


# ================================================================== C1: a scope refusal is a denial
_AUTH_CALLS = {"require_imaging_access", "authorize_file_scope", "authorize_mask_specs", "authorize_segmentation_id",
               "authorize_study_id", "authorize_patient_id", "_authorized_inputs", "_authorized_image_request"}


def test_rc121_review6_no_route_turns_an_authorization_refusal_into_a_500():
    bad = []
    for path in (BACKEND / "app" / "api" / "routes").glob("*.py"):
        for t in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(t, ast.Try):
                continue
            calls = {getattr(c.func, "id", getattr(c.func, "attr", "")) for b in t.body for c in ast.walk(b)
                     if isinstance(c, ast.Call)}
            if not calls & _AUTH_CALLS:
                continue
            for h in t.handlers:
                types = h.type.elts if isinstance(h.type, ast.Tuple) else [h.type]
                names = {"<bare>" if x is None else getattr(x, "id", getattr(x, "attr", "")) for x in types}
                if "HTTPException" in names:
                    break
                if names & {"Exception", "<bare>", "BaseException"}:
                    bad.append(f"{path.name}:{t.lineno}")
                    break
    assert not bad, bad


def test_rc121_review6_an_out_of_scope_tool_call_is_audited_as_a_denial(scope_key, monkeypatch):
    from app.mcp import _backend
    S = _scope_module()
    _Backend().install(monkeypatch)
    app, _paid = _assistant_app()
    monkeypatch.setattr(_backend, "_TRANSPORT", httpx.ASGITransport(app=app), raising=False)
    monkeypatch.setenv("API_BASE_URL", "http://testserver")

    async def buggy_read(segmentation_id):
        return await _backend.api_get(f"/segmentation/{SEG_PRIOR}")
    data = make_registry_data()
    data["agents"]["test-agent"]["requires_backend_scope"] = True
    events = []
    reg = AgentRegistry(data, switches=InMemoryKillSwitches({"test-agent": True}), audit=events.append,
                        clock=lambda: FIXED_NOW)
    token = S.issue_scope_token(user_id=USER.id, patient_id=P1, study_ids=[S1], run_id="run-1")
    model = H.ScriptedModel([RT.ModelResponse("model-current", "", (RT.ToolCall("c1", "read_measurements",
                                                                                {"segmentation_id": SEG_IN}),),
                                              10, 10, "tool_use")])
    res = asyncio.run(RT.AgentRuntime(reg, T.Tracer(T.NoopExporter()), tools={"read_measurements": buggy_read}).arun(
        "test-agent", model_client=model, scope=RunScope(S1, frozenset({SEG_IN}), capability=token), system="s",
        user_content="u"))
    assert res.status == "refused" and res.code == R.RefusalCode.OUT_OF_SCOPE_RESOURCE and res.text is None
    assert [e for e in events if e.get("event") == "agent.run"][-1]["outcome"] == "denied"


# ================================================================== C2, C3, C4, E1: one implementation, one list
def test_rc121_review6_the_route_uses_the_one_issuance_and_the_route_lists_are_one():
    from app.api.routes import agent_scope as issuance
    from app.mcp import _backend
    S = _scope_module()
    src = inspect.getsource(issuance.issue_agent_scope)
    assert "issue_for_studies(" in src and "authorize_study_id(" not in src and "sign_for_patient(" not in src
    post = {rx.pattern for m, rx in S.AGENT_ROUTES if m == "POST"}
    allowed_posts = _backend.COMPUTE_ONLY_POST_PATHS    # eighth review (F8): the paid route is not compute-only
    assert all(S.route_allowed("POST", "/api/v1" + p) for p in allowed_posts) and len(post) == len(allowed_posts)
    for module in ("ms_clinical_server.py", "imaging_server.py"):
        tree = ast.parse((BACKEND / "app" / "mcp" / module).read_text(encoding="utf-8"))
        for call in ast.walk(tree):
            if isinstance(call, ast.Call) and getattr(call.func, "id", "") in ("api_get", "api_post_compute"):
                arg = call.args[0]
                # amended (seventh review, R6: strict path parameters): a real storage path in an imaging route's
                # first slot, a digit elsewhere
                parts, first = [], True
                for v in ([arg] if isinstance(arg, ast.Constant) else arg.values):
                    if isinstance(v, ast.Constant):
                        parts.append(v.value)
                    else:
                        parts.append(FILE_PRIOR if first and "".join(parts).startswith("/imaging/") else "7")
                        first = False
                path = "".join(parts)
                method = "GET" if call.func.id == "api_get" else "POST"
                assert S.route_allowed(method, "/api/v1" + path), (module, method, path)


def test_rc121_review6_one_patient_in_two_spellings_is_one_patient(scope_key):
    S = _scope_module()
    token = S.sign_for_patient(USER, {P1, P1.upper()}, [S1], run_id="r")
    assert S.verify_scope_token(token).patient_id == P1


def test_rc121_review6_issuance_dedups_and_authorizes_concurrently(scope_key, monkeypatch):
    # Amended for the seventh review of PR #79 (R10): one study after the other (stopping at the first refusal), with
    # the services built once — so at most ONE authorization at a time; still deduplicated.
    _Backend().install(monkeypatch)
    import app.security.resource_access as ra
    S = _scope_module()
    state = {"now": 0, "max": 0, "calls": []}

    async def authorize(study_id, user, **kwargs):
        state["calls"].append(study_id)
        state["now"] += 1
        state["max"] = max(state["max"], state["now"])
        await asyncio.sleep(0.01)
        state["now"] -= 1
        return P1
    monkeypatch.setattr(ra, "authorize_study_id", authorize)
    asyncio.run(S.issue_for_studies([S1, S1.upper(), S2], USER, run_id="r"))
    assert sorted(state["calls"]) == sorted([S1, S2]) and state["max"] == 1


# ================================================================== E2, E3, E4
def test_rc113_review6_the_bracket_table_is_static():
    assert not hasattr(U.bracket_like, "cache_info"), "no first-use computation on the event loop"
    assert isinstance(U.BRACKET_LIKE, frozenset)
    computed = {chr(c) for c in range(0x20000) if not 0xD800 <= c < 0xE000 and _bracket_like(chr(c))}
    assert computed <= U.BRACKET_LIKE


def test_rc113_review6_assistant_view_is_applied_once(scope_key, monkeypatch):
    from app.mcp import _backend
    S = _scope_module()
    _Backend().install(monkeypatch)
    app, _paid = _assistant_app()
    monkeypatch.setattr(_backend, "_TRANSPORT", httpx.ASGITransport(app=app), raising=False)
    monkeypatch.setenv("API_BASE_URL", "http://testserver")
    calls = []
    real = _backend.assistant_view

    def counting(value):
        calls.append(1)
        return real(value)
    monkeypatch.setattr(_backend, "assistant_view", counting)
    monkeypatch.setattr(U, "assistant_view", counting)

    async def read(segmentation_id):
        return await _backend.api_get(f"/segmentation/{segmentation_id}")
    data = make_registry_data()
    reg = AgentRegistry(data, switches=InMemoryKillSwitches({"test-agent": True}), clock=lambda: FIXED_NOW)
    model = H.ScriptedModel([
        RT.ModelResponse("model-current", "", (RT.ToolCall("c1", "read_measurements", {"segmentation_id": SEG_IN}),),
                         10, 10, "tool_use"),
        RT.ModelResponse("model-current", "Seven lesions.", (), 10, 10, "end_turn")])
    token = S.issue_scope_token(user_id=USER.id, patient_id=P1, study_ids=[S1], run_id="run-1")
    res = asyncio.run(RT.AgentRuntime(reg, T.Tracer(T.NoopExporter()), tools={"read_measurements": read}).arun(
        "test-agent", model_client=model, scope=RunScope(S1, frozenset({SEG_IN}), capability=token), system="s",
        user_content="u"))
    assert res.status == "delivered" and len(calls) == 1, len(calls)


def test_rc120_review6_expiry_stops_at_the_first_entry_still_valid():
    from datetime import timedelta
    clock = {"t": FIXED_NOW}
    rec = O.OversightRecorder(clock=lambda: clock["t"], pending_ttl=timedelta(hours=1), max_pending=100)
    reads = []

    class Counting(dict):
        def __getitem__(self, key):
            if key == "shown_at":
                reads.append(1)
            return super().__getitem__(key)
    for i in range(50):
        rec._pending[(f"d{i}", "r")] = Counting(agent_id="a", shown_at=FIXED_NOW + timedelta(minutes=i),
                                                 draft_sha256="x")
    clock["t"] = FIXED_NOW + timedelta(hours=1, minutes=1, seconds=30)       # d0 and d1 have expired
    rec._expire(clock["t"])
    assert len(rec._pending) == 48 and len(reads) == 3, len(reads)
