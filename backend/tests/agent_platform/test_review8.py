"""Findings of the EIGHTH independent adversarial review of PR #79 (the final fix round) — failing-first tests.

DRAFT, PENDING owner approval. Written against 4ae43d8, where these tests fail; fixes follow.
F1 every refusal by the agent scope writes ONE access-audit row (agent_scope_denied) before raising. F2 report-drafter
is unavailable from 2026-11-30 until the owner approves a successor (D-AGT-1): said loudly, and the daily job alerts.
F3 the card's tool schema is the one the real server advertises (Context hidden). F4 a refused session request is a
clear "no session"; more than 20 studies refused, never truncated. F5 a non-assistant route is "tool not allowed".
F6 a session authorizes each study once. F7 one rule for a storage path. F8 the report route is not compute-only;
no unused description. F9 the session lasts 15 minutes; no report-draft wording. F10 ".." only as a path segment.
"""
import asyncio
import importlib.util
import inspect
import json
from datetime import date
from pathlib import Path

import pytest

from app.agent_platform import cards as C
from tests.agent_platform import _harness as H
from tests.agent_platform.test_review5 import (FILE_IN, FILE_PRIOR, P1, P2, S1, S2, SEG_PRIOR, USER, _Backend,
                                               _scope_module, _scoped_app, scope_key)  # noqa: F401
from tests.agent_platform.test_review6 import _assistant_app, _cap, assistant  # noqa: F401
from tests.agent_platform.test_review7 import Human

BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture
def access_rows(monkeypatch):
    """Every access-audit row (patient_access.audit_access_decision) written during the test."""
    import app.security.patient_access as pa
    rows = []

    class Capture:
        def info(self, msg, extra=None, **kwargs):
            if msg == "Patient access decision":
                rows.append(dict(extra or {}))

        def warning(self, *a, **k):
            pass
    monkeypatch.setattr(pa, "logger", Capture())
    return rows


# ================================================================== F1: scope refusals are audited
def test_rc121_review8_an_out_of_scope_read_writes_exactly_one_denied_audit_row(scope_key, monkeypatch, access_rows):
    from fastapi.testclient import TestClient
    S, CAP = _scope_module(), _cap()
    _Backend().install(monkeypatch)
    client = TestClient(_scoped_app(USER))
    h = {CAP.CAPABILITY_HEADER: S.issue_scope_token(user_id=USER.id, patient_id=P1, study_ids=[S1], run_id="r")}
    for path in (f"/api/v1/segmentation/{SEG_PRIOR}", f"/api/v1/imaging/metadata/{FILE_PRIOR}"):
        access_rows.clear()
        assert client.get(path, headers=h).status_code == 404
        denied = [r for r in access_rows if r.get("access_allowed") is False]
        assert len(denied) == 1 and denied[0]["access_decision"] == "denied:agent_scope_denied", (path, access_rows)


def test_rc121_review8_every_scope_chokepoint_audits_before_raising(scope_key, access_rows):
    from fastapi import HTTPException

    import app.security.patient_access_dependency as pad
    import app.security.resource_access as ra
    S = _scope_module()
    env = _Backend()
    svc = {"patient_service": env.patients, "care_team_service": env.care}
    scope = S.AgentScope(user_id=USER.id, patient_id=P1, study_ids=frozenset({S1}), run_id="r", expires_at=2 ** 40)

    async def one_row(coro):
        access_rows.clear()
        try:
            out = await coro
        except HTTPException:
            out = None
        assert [r["access_decision"] for r in access_rows] == ["denied:agent_scope_denied"], access_rows
        return out

    async def go():
        with S.scope_context(scope):
            await one_row(ra.authorize_resolved_patient(patient_id=P2, resource_label="Patient", user=USER, **svc))
            await one_row(pad.authorize_patient_access(patient_id=P2, user=USER, **svc))
            await one_row(pad.authorize_storage_ref(raw_file_id=FILE_PRIOR, user=USER, **svc))
            assert await one_row(ra.resolve_study_patient_id(S2, env.studies)) is None
            assert await one_row(ra.resolve_segmentation_patient_id(SEG_PRIOR, env.segs)) is None
    asyncio.run(go())


# ================================================================== F2: report-drafter's model retires
def test_rc117_review8_report_drafter_is_loudly_unavailable_after_its_model_retires():
    # Reconciled 2026-11-14 (merge of main, PR #78): the report model is claude-sonnet-5-5, in use by the owner's
    # research-stage decision, with no announced retirement, so the agent is NOT announced unavailable today ...
    assert not any("report-drafter" in a for a in C.availability_alerts(date(2026, 11, 11)))
    note = json.dumps(H.production_data()["agents"]["report-drafter"])
    assert "D-AGT-1" in note and "claude-sonnet-5-5" in note and "2026-11-30" in note
    # ... and the rule still says it loudly when the only in-use model retires.
    data = H.production_data()
    data["models"]["claude-sonnet-5-5"]["retires_on"] = "2026-11-30"
    text = " ".join(C.availability_alerts(date(2026, 11, 11), data))
    assert "report-drafter" in text and "2026-11-30" in text and "D-AGT-1" in text


# ================================================================== F3: the card's schema is the advertised one
def test_rc117_review8_the_card_hides_the_request_context_like_the_real_server():
    module = C.load_with_stub_fastmcp(BACKEND / "app" / "mcp" / "ms_clinical_server.py", "card_schema_check")
    definition = json.loads(C.tool_definition("open_study_session", module.mcp.tools["open_study_session"]))
    assert definition["parameters"] == [], definition


@pytest.mark.skipif(importlib.util.find_spec("fastmcp") is None, reason="fastmcp is installed in CI")
def test_rc117_review8_card_parameters_equal_the_real_server_schema():
    import importlib.metadata
    import sys
    if importlib.metadata.version("fastmcp") != C.requirement_pin("fastmcp"):
        pytest.skip("another fastmcp than the pinned one is installed here")
    for name, alias in (("ms_clinical_server", "app.mcp.ms_clinical_server"), ("imaging_server", "app.mcp.imaging_server")):
        stub = C.load_with_stub_fastmcp(BACKEND / "app" / "mcp" / f"{name}.py", f"card_{name}")
        sys.modules.pop(alias, None)
        real = importlib.import_module(alias).mcp
        for tool in asyncio.run(real.list_tools()):
            card = json.loads(C.tool_definition(tool.name, stub.mcp.tools[tool.name]))
            assert [p["name"] for p in card["parameters"]] == list(tool.parameters.get("properties", {})), tool.name
        sys.modules.pop(alias, None)


# ================================================================== F4: a refused session request
def test_rc121_review8_a_refused_session_request_is_a_clear_no_session(assistant):
    server, backend, _app, _paid = assistant
    CAP = _cap()
    with pytest.raises(CAP.ScopeRequired) as e:
        asyncio.run(server.open_study_session(Human(("accept", "not-a-study-id"), ("accept", None))))
    assert "no session was opened" in str(e.value).lower()
    many = ",".join([S1] * 21)
    with pytest.raises(CAP.ScopeRequired) as e:
        asyncio.run(server.open_study_session(Human(("accept", many), ("accept", None))))
    assert "20" in str(e.value) and not backend._SESSION.get("token")


# ================================================================== F5: not an assistant route
def test_rc110_review8_a_non_assistant_route_is_tool_not_allowed(assistant):
    server, backend, _app, _paid = assistant
    asyncio.run(server.open_study_session(Human(("accept", S1), ("accept", None))))
    for call in (backend.api_get("/patients/" + P1), backend.api_post_compute("/ai/report/generate", {})):
        with pytest.raises(PermissionError) as e:
            asyncio.run(call)
        assert e.value.code == "tool_not_allowed_for_agent", e.value


# ================================================================== F6: one authorization per study
def test_rc121_review8_a_session_authorizes_each_study_once(assistant, access_rows, monkeypatch):
    server, backend, _app, _paid = assistant
    import app.security.resource_access as ra
    reads = []
    studies = ra._study_service()
    real = studies.get_study

    async def counting(study_id, *a, **k):
        reads.append(str(study_id))
        return await real(study_id, *a, **k)
    monkeypatch.setattr(studies, "get_study", counting)
    asyncio.run(server.open_study_session(Human(("accept", S1), ("accept", None))))
    assert reads == [S1], reads
    assert [r["patient_id"] for r in access_rows if r.get("access_allowed")] == [P1], access_rows


# ================================================================== F7, F8, F9, F10
def test_rc121_review8_one_rule_for_a_storage_path():
    S = _scope_module()
    src = inspect.getsource(S.study_of_storage_path)
    assert "parse_patient_storage_ref" in src and "_canon(" not in src
    assert S.study_of_storage_path(FILE_IN) == S1 and S.study_of_storage_path("patients/x/studies/y") is None


def test_review8_no_report_route_and_no_dead_description():
    from app.mcp import _backend
    assert "/ai/report/generate" not in _backend.COMPUTE_ONLY_POST_PATHS
    assert not hasattr(_backend, "PAID_MODEL_POST_PATHS")
    for server in ("ms_clinical_server.py", "imaging_server.py"):
        assert "SERVER_DESCRIPTION" not in (BACKEND / "app" / "mcp" / server).read_text(encoding="utf-8")


def test_review8_the_texts_say_15_minutes_and_no_report_draft(assistant):
    server, _b, _a, _p = assistant
    doc = inspect.getdoc(server.open_study_session)
    assert "15 minutes" in doc and "hour" not in doc
    assert "drafts from measurements" not in json.dumps(H.production_data())
    assert "draft report" not in (BACKEND / "app" / "mcp" / "__init__.py").read_text(encoding="utf-8").lower()


def test_rc121_review8_dot_dot_only_as_a_segment_and_255_character_names():
    from app.mcp import _backend
    stem = FILE_IN.rsplit("/", 1)[0]
    assert _backend.get_route_allowed(f"/imaging/metadata/{stem}/scan..nii.gz")
    assert _backend.get_route_allowed(f"/imaging/metadata/{stem}/{'a' * 248}.nii.gz")          # 255 characters
    assert not _backend.get_route_allowed(f"/imaging/metadata/{stem}/{'a' * 249}.nii.gz")      # 256
    assert not _backend.get_route_allowed(f"/imaging/metadata/{stem}/../x.nii.gz")
