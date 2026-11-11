"""Findings 1-10 of the THIRD independent adversarial review of PR #79 — failing-first tests.

DRAFT, PENDING owner approval. Written against e125220, where these tests fail; fixes follow. Main theme: the
scope control had become too strict and refused legitimate results.

1-2. Contract tests: the REAL outputs of the app's services (lesion analysis, region classification with
     region_id / zone_id, longitudinal comparison) and realistic imaging outputs pass through every assistant
     tool and validate_tool_result with the study's real ids (UUIDs, a storage path, DICOM UIDs); "id-ness" is
     decided by declared resource keys and resource-id VALUES, not by the shape of a key name; a foreign id
     planted anywhere still refuses the result (RC-114).
3. A refusal before any model call is audited without a model, never as model 'invalid' (RC-110).
4. Agent audit records carry the authenticated actor (or the platform's system actor) and are never dropped
   by the anonymous-source budget: 100 runs, nothing suppressed (RC-110).
5. The retirement check takes an injected date; the wall-clock check is its own scheduled job (RC-117).
6. Oversight and the sign-off span name a reader by the SAME keyed hash (RC-116, RC-120).
7. render_html escapes every value and refuses an invalid record; from_dict validates the author (RC-119).
8. A malformed Verdict fails closed with an audit record (RC-110).
9. validate_tool_result runs the alarm once per string and serialises once; 200 KB within a time bound.
10. The test loader of the MCP servers is the card's own (one server surface).
"""
import ast
import asyncio
import json
import time
from datetime import date
from pathlib import Path

import pytest

from app.agent_platform import cards as C
from app.agent_platform import oversight as O
from app.agent_platform import provenance as P
from app.agent_platform import registry as R
from app.agent_platform import runtime as RT
from app.agent_platform import tracing as T
from app.agent_platform import untrusted as U
from app.agent_platform.registry import AgentRegistry, RefusalCode
from app.agent_platform.untrusted import RunScope
from tests.agent_platform import _contract as K
from tests.agent_platform import _harness as H
from tests.agent_platform import _mcp
from tests.agent_platform._fixtures import FIXED_NOW, make_registry_data

REPO = Path(__file__).resolve().parents[3]
SCOPE = RunScope(K.STUDY, K.STUDY_IDS)


def contract_backend():
    return _mcp.FakeBackend(data={K.SEG_A: {"file": K.FILE_A}, K.SEG_B: {"file": K.FILE_B},
                                  K.SEG_OTHER: {"file": "patients/other/flair.nii.gz"}})


def tool_outputs():
    """The real output of every assistant tool, through the REAL MCP tool functions."""
    backend = contract_backend()
    clinical = _mcp.wire(_mcp.load_mcp_module("ms_clinical_server"), backend)
    imaging = _mcp.wire(_mcp.load_mcp_module("imaging_server"), backend)
    calls = {
        "get_region_classification": lambda: clinical.get_region_classification(K.SEG_A),
        "summarize_dis_items": lambda: clinical.summarize_dis_items(K.SEG_A),
        "analyze_lesions": lambda: clinical.analyze_lesions(K.SEG_A),
        "compare_longitudinal": lambda: clinical.compare_longitudinal(K.SEG_B, K.SEG_A),
        # generate_ms_report removed by the seventh review of PR #79 (R2)
        "get_image_metadata": lambda: imaging.get_image_metadata(K.FILE_A),
        "get_slice_image": lambda: imaging.get_slice_image(K.FILE_A, 8),
        "process_image": lambda: imaging.process_image(K.FILE_A),
        "list_segmentations": lambda: imaging.list_segmentations(K.FILE_A),
        "get_matplotlib_visualization": lambda: imaging.get_matplotlib_visualization(K.FILE_A, 8),
    }
    return {name: asyncio.run(fn()) for name, fn in calls.items()}


PROD = H.production_data()
REGISTRY = AgentRegistry(PROD, switches=R.InMemoryKillSwitches(), audit=lambda e: None, clock=lambda: FIXED_NOW)
OUTPUTS = tool_outputs()
LIMIT = PROD["agents"]["ms-clinical-assistant"]["limits"]["max_tool_result_bytes"]


# ================================================================== 1-2. contract tests on real shapes
@pytest.mark.parametrize("tool", sorted(OUTPUTS))
def test_rc114_review3_real_output_of_every_tool_passes(tool):
    check = U.validate_tool_result(OUTPUTS[tool], tool=REGISTRY.tool(tool), scope=SCOPE, max_bytes=LIMIT)
    assert check.ok, (tool, check.code)


@pytest.mark.parametrize("tool", sorted(OUTPUTS))
def test_rc114_review3_a_foreign_id_planted_in_a_real_output_still_refuses_it(tool):
    check = U.validate_tool_result(K.with_foreign_id(OUTPUTS[tool]), tool=REGISTRY.tool(tool), scope=SCOPE,
                                   max_bytes=LIMIT)
    assert not check.ok and check.code == RefusalCode.OUT_OF_SCOPE_RESOURCE, tool


@pytest.mark.parametrize("builder", [K.classification, K.geometric_classification])
def test_rc114_review3_real_region_classifications_pass(builder):
    out = {"classification": builder(), "note": "regions are candidates"}
    assert "region_id" in json.dumps(out)
    assert U.validate_tool_result(out, tool=REGISTRY.tool("get_region_classification"), scope=SCOPE,
                                  max_bytes=LIMIT).ok


@pytest.mark.parametrize("key", ["total_burden_mm3", "total_volume_mm3", "T2-FLAIR", "Cortical / Juxtacortical",
                                 "region_id", "zone_id", "volume_tp1_mm3", "burden_delta_percent"])
def test_rc114_review3_ordinary_keys_are_not_resource_ids(key):
    assert U.validate_tool_result({key: 3, "segmentation_id": K.SEG_A}, tool=REGISTRY.tool("analyze_lesions"),
                                  scope=SCOPE, max_bytes=LIMIT).ok, key


@pytest.mark.parametrize("bad", [
    {"lesions": [{"id": 1, "parent": K.SEG_OTHER}]},                      # a UUID under an ordinary key
    {K.SEG_OTHER: {"total_count": 2}},                                    # a UUID as a key
    {"segmentation_id": 12345},                                          # a number under a resource key
    {"notes": ["see patients/other-uuid/" + K.SEG_OTHER + "/mask.nii.gz"]},  # a UUID inside a path in free text
    {"series_instance_uid": "1.2.826.0.1.3680043.8.498.99999999999999999"},  # a foreign DICOM UID
])
def test_rc114_review3_foreign_values_are_refused_by_their_value(bad):
    check = U.validate_tool_result(bad, tool=REGISTRY.tool("analyze_lesions"), scope=SCOPE, max_bytes=LIMIT)
    assert not check.ok and check.code == RefusalCode.OUT_OF_SCOPE_RESOURCE, bad


def test_rc114_review3_unconfirmed_activity_flags_in_a_real_comparison_are_removed():
    check = U.validate_tool_result(OUTPUTS["compare_longitudinal"], tool=REGISTRY.tool("compare_longitudinal"),
                                   scope=SCOPE, max_bytes=LIMIT)
    assert check.ok and "activity_candidate" not in check.for_model and "dit_candidate" not in check.for_model


# ================================================================== 3. no model 'invalid' in the audit
def test_rc110_review3_refusal_before_a_model_call_is_audited_without_a_model(registry, audit_events):
    RT.AgentRuntime(registry, T.Tracer(T.NoopExporter())).run(
        "pending-agent", model_client=H.ScriptedModel([]), scope=SCOPE, system="s", user_content="u")
    assert audit_events and all(e.get("model_id") != "invalid" for e in audit_events), audit_events


# ================================================================== 4. durable agent audit records
class _Durable:
    def __init__(self):
        self.records = []

    def submit(self, record):
        self.records.append(record)
        return None


@pytest.mark.parametrize("with_actor", [True, False])
def test_rc110_review3_100_runs_a_minute_lose_no_audit_record(monkeypatch, with_actor):
    from app.core.logging import audit as A
    from app.core.logging import audit_sink
    sink = _Durable()
    monkeypatch.setattr(audit_sink, "get_durable_audit_sink", lambda: sink)
    A.reset_audit_budget()
    reg = AgentRegistry(make_registry_data(), switches=R.InMemoryKillSwitches({"test-agent": True}),
                        clock=lambda: FIXED_NOW)                        # the DEFAULT sink: the server audit log
    rt = RT.AgentRuntime(reg, T.Tracer(T.NoopExporter()))
    actor = R.AuditActor(user_id=K.USER, username="dr.example", role="radiologist") if with_actor else None
    for _ in range(100):
        kwargs = {"actor": actor} if actor else {}
        rt.run("pending-agent", model_client=H.ScriptedModel([]), scope=SCOPE, system="s", user_content="u", **kwargs)
    agent = [r for r in sink.records if str(r.get("reason", "")).startswith("agent.")]
    # Amended for the fourth review of PR #79, finding 7: exactly ONE agent.run record per run (was a refusal
    # record and a run record per run).
    assert len(agent) == 100 and all(r["reason"] == "agent.run:agent_not_approved" for r in agent), len(agent)
    assert not any((r.get("details") or {}).get("durable_suppressed") for r in sink.records)
    expected = K.USER if with_actor else R.SYSTEM_ACTOR.user_id
    assert all(r.get("actor_user_id") == expected for r in agent)


# ================================================================== 5. retirement check
def test_rc117_review3_retirement_check_takes_an_injected_date():
    assert not C.retirement_problems(today=date(2026, 11, 10))
    problems = C.retirement_problems(today=date(2026, 11, 30))
    assert problems and "claude-sonnet-4-5-20250929" in problems[0]


def test_rc117_review3_no_test_reads_the_wall_clock_for_retirement():
    tree = ast.parse((Path(__file__).with_name("test_cards.py")).read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "now"]
    assert not calls, "test_cards.py must inject the date: a wall-clock check would turn every PR red"


def test_rc117_review3_wall_clock_retirement_runs_in_its_own_scheduled_job():
    wf = (REPO / ".github" / "workflows" / "agent-model-retirement.yml").read_text(encoding="utf-8")
    assert "schedule:" in wf and "cron:" in wf and "python -m app.agent_platform.cards --retirement" in wf


# ================================================================== 6. one reader key
def test_rc120_review3_oversight_and_signoff_name_the_reader_by_the_same_key():
    mem = T.InMemoryExporter()
    T.link_signoff(T.Tracer(mem), run_trace_id="0af7651916cd43dd8448eb211c80319c", run_span_id="b7ad6b7169203331",
                   signoff_record_id="rec-1", content_sha256="ab" * 32, reader_id="dr.example")
    assert mem.spans[-1].attributes["mstool.signoff.reader_key"] == O.reader_key("dr.example")
    assert O.reader_key is R.reader_key


# ================================================================== 7. HTML injection
BAD_AUTHOR = '"><img src=x onerror=alert(1)>'


def test_rc119_review3_from_dict_refuses_an_unknown_author():
    doc = P.mark_model_text("Seven lesions.", agent_id="a", model_id="m", trace_id=None, verifier=None).to_dict()
    doc["segments"][0]["author"] = BAD_AUTHOR
    with pytest.raises(ValueError):
        P.ProvenanceDocument.from_dict(doc)


def test_rc119_review3_render_html_refuses_an_invalid_record_and_escapes_every_value():
    seg = P.Segment(kind="sentence", text="x", trailing="", author=BAD_AUTHOR, sha256=P._sha("x"))
    with pytest.raises(ValueError):
        P.render_html(P.ProvenanceDocument((seg,)))
    doc = P.mark_model_text("Seven lesions.", agent_id='a"><b>', model_id='m"onmouseover="x', trace_id=None,
                            verifier=None)
    html = P.render_html(doc)
    assert "<b>" not in html and 'onmouseover="x' not in html


# ================================================================== 8. malformed verdicts
@pytest.mark.parametrize("verdict", [RT.Verdict("pass", 5), RT.Verdict(None, "x"), RT.Verdict("pass", "x", "2"),
                                     RT.Verdict("pass", "x", 0, None), RT.Verdict("maybe", "x")])
def test_rc110_review3_malformed_verdict_fails_closed_and_is_audited(registry, audit_events, verdict):
    rt = RT.AgentRuntime(registry, T.Tracer(T.NoopExporter()), verifier=lambda d, c: verdict)
    # Amended for the fifth review of PR #79 (finding 1): the answer states its normal end; there is no default.
    res = rt.run("test-agent", model_client=H.ScriptedModel([RT.ModelResponse("model-current", "Seven lesions.",
                                                                              input_tokens=1, output_tokens=1,
                                                                              stop_reason="end_turn")]),
                 scope=SCOPE, system="s", user_content="u")
    assert res.status == "failed" and res.code == RefusalCode.VERIFIER_FAILED and res.text is None
    assert [e for e in audit_events if e.get("event") == "agent.run"][-1]["outcome"] == "failure"


# ================================================================== 9. no duplicated work
def test_review3_alarm_runs_once_per_string_and_200kb_is_bounded(monkeypatch):
    calls = {"n": 0}
    real = U.detect_instructions

    def counting(text):
        calls["n"] += 1
        return real(text)
    monkeypatch.setattr(U, "detect_instructions", counting)
    result = {"items": [{"text": f"lesion note {i}: stable, no change " + "x" * 60} for i in range(2000)]}
    assert len(json.dumps(result)) > 190_000
    start = time.perf_counter()
    check = U.validate_tool_result(result, tool=REGISTRY.tool("analyze_lesions"), scope=SCOPE, max_bytes=400_000)
    elapsed = time.perf_counter() - start
    assert check.ok and calls["n"] == 2000, calls["n"]
    assert elapsed < 2.0, elapsed


# ================================================================== 10. one server surface
def test_review3_test_loader_is_the_cards_loader():
    assert _mcp.StubFastMCP is C.StubFastMCP
    assert "load_with_stub_fastmcp" in Path(_mcp.__file__).read_text(encoding="utf-8")
