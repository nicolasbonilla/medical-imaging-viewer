"""Findings 1-10 of the FOURTH independent adversarial review of PR #79 — failing-first tests.

DRAFT, PENDING owner approval. Written against 44d0737, where these tests fail; fixes follow. Two scope BYPASSES
were verified by hand by the reviewer (findings 1 and 2).

1. BYPASS: any syntactically valid DICOM UID (PS3.5 §9.1 grammar) of any vendor root is recognised in free text
   and as a dict key and must be in scope (RC-114).
2. BYPASS: the actor exemption covers only an actor-id STRING; dicts and lists under actor keys are walked, and
   resource-like *_by keys (superseded_by, replaced_by) are resources (RC-114).
3. mcp is pinned exactly in requirements.txt and the card follows it (RC-117).
4. Any exception at the run boundary becomes an audited RunResult; inputs are validated up front (RC-110).
5. A model segment must name its model; the legend follows authorship (RC-119).
6. Tool arguments named fn or blocking reach the tool (robustness).
7. One audit record per run, with documented event types (RC-110).
8. The file exporter writes from one handle in a writer thread, with a bounded flush (RC-116, availability).
9. The oversight edit size is computed on sentences and words, bounded in time (RC-120).
10. cards.py reuses the registry's retirement rule and iterates the agents with cards (RC-117).
"""
import ast
import asyncio
import builtins
import inspect
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
from app.agent_platform.registry import AgentRegistry, InMemoryKillSwitches, RefusalCode
from app.agent_platform.untrusted import RunScope
from tests.agent_platform import _contract as K
from tests.agent_platform import _harness as H
from tests.agent_platform._fixtures import FIXED_NOW, make_registry_data

BACKEND = Path(__file__).resolve().parents[2]
SCOPE = RunScope(K.STUDY, K.STUDY_IDS)
TOOL = R.ToolEntry(name="analyze_lesions", access="read", arguments=(("segmentation_id", "resource_id"),))
VENDOR_UIDS = ["1.3.12.2.1107.5.2.43.66094.30000020061707373834300000017",       # Siemens
               "1.3.46.670589.11.42151.5.0.6524.2020061716142632055",            # Philips
               "1.3.6.1.4.1.14519.5.2.1.7695.2311.123456789",                    # an enterprise root (TCIA)
               "1.2.840.113619.2.55.3.604688119.868.1599000000.1",               # GE
               "2.25.329800735698586629295641978511506172918"]                   # UUID-derived


def check(value, scope=SCOPE):
    return U.validate_tool_result(value, tool=TOOL, scope=scope, max_bytes=100_000)


# ================================================================== 1. DICOM UIDs of any root
@pytest.mark.parametrize("uid", VENDOR_UIDS)
@pytest.mark.parametrize("where", ["text", "key", "value"])
def test_rc114_review4_foreign_dicom_uid_of_any_root_is_refused(uid, where):
    value = {"text": {"note": f"compared with the prior study {uid} last year"},
             "key": {uid: {"lesions": 3}}, "value": {"source": uid}}[where]
    res = check(value)
    assert not res.ok and res.code == RefusalCode.OUT_OF_SCOPE_RESOURCE, (uid, where)
    assert check(value, RunScope(K.STUDY, K.STUDY_IDS | {uid})).ok, "the same UID passes when it is the study's"


@pytest.mark.parametrize("uid,ok", [("1.2.840.10008.1.2", True), ("1.3.12.2.1107.5.2", True), ("0.1", True),
                                    ("1.02.3", False), ("1..2", False), (".1.2", False), ("1.2.", False),
                                    ("1", False), ("1.2.a", False), ("1." + "2" * 63, False)])
def test_rc114_review4_dicom_uid_grammar_of_ps3_5(uid, ok):
    assert U.is_dicom_uid(uid) is ok, uid


@pytest.mark.parametrize("text", ["total volume 3.1 mL", "1.5", "0.027 mL", "11.11.2026", "version 1.2.3",
                                  "MAGNIMS 2021 and McDonald 2024", "spacing 0.9375 x 0.9375 x 3.0 mm"])
def test_rc114_review4_decimals_dates_and_versions_are_not_uids(text):
    assert check({"note": text, "segmentation_id": K.SEG_A}).ok, text


# ================================================================== 2. actor exemption: the value only
@pytest.mark.parametrize("bad", [
    {"reviewed_by": {"segmentation_id": K.SEG_OTHER}},
    {"created_by": [K.USER, {"file_id": "patients/other/x.nii.gz"}]},
    {"superseded_by": K.SEG_OTHER},
    {"replaced_by": "seg-OTHER"},
    {"superseded_by": 12345},
    {"report_id": {"segmentation_id": K.SEG_OTHER}},       # an exempt key's nested content is still walked
])
def test_rc114_review4_actor_and_exempt_keys_do_not_hide_a_subtree(bad):
    tool = R.ToolEntry(name="generate_ms_report", access="compute", arguments=(("segmentation_id", "resource_id"),),
                       result_exempt_keys=("report_id",))
    res = U.validate_tool_result(bad, tool=tool, scope=SCOPE, max_bytes=100_000)
    assert not res.ok and res.code == RefusalCode.OUT_OF_SCOPE_RESOURCE, bad


def test_rc114_review4_an_actor_id_value_is_still_exempt():
    assert check({"created_by": K.USER, "reviewed_by_id": K.USER, "segmentation_id": K.SEG_A}).ok


# ================================================================== 3. mcp pinned
def test_rc117_review4_mcp_is_pinned_exactly_and_the_card_follows():
    assert C.requirement_pin("mcp") == "1.12.4"
    card = C.load_card("ms-clinical-assistant")
    assert card["sdk_pins"].get("mcp") == "1.12.4"
    assert card["mcp"]["observed"]["mcp_sdk_version"] == C.requirement_pin("mcp")
    assert "NOT pin" not in card["mcp"]["mcp_sdk_requirement"]


# ================================================================== 4. run boundary
@pytest.mark.parametrize("kwargs", [{"scope": None}, {"scope": "study-1"},
                                    {"untrusted": [("dicom_tag", 5)]}, {"untrusted": ["SeriesDescription"]},
                                    {"untrusted": [(None, "x")]}])
def test_rc110_review4_invalid_run_inputs_are_refused_and_audited(registry, audit_events, kwargs):
    args = {"model_client": H.ScriptedModel([]), "scope": SCOPE, "system": "s", "user_content": "u", **kwargs}
    res = RT.AgentRuntime(registry, T.Tracer(T.NoopExporter())).run("test-agent", **args)
    assert res.status == "refused" and res.code == RefusalCode.RUN_INPUT_INVALID
    assert [e for e in audit_events if e.get("event") == "agent.run"][-1]["code"] == str(RefusalCode.RUN_INPUT_INVALID)


def test_rc110_review4_an_internal_error_becomes_an_audited_failure(registry, audit_events, monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("bug")
    monkeypatch.setattr(registry, "authorize_model_call", broken)
    res = RT.AgentRuntime(registry, T.Tracer(T.NoopExporter())).run(
        "test-agent", model_client=H.ScriptedModel([]), scope=SCOPE, system="s", user_content="u")
    assert res.status == "failed" and res.code == RefusalCode.RUN_INTERNAL_ERROR and res.text is None
    ev = [e for e in audit_events if e.get("event") == "agent.run"][-1]
    assert ev["outcome"] == "failure" and ev["code"] == str(RefusalCode.RUN_INTERNAL_ERROR)


class Abort(BaseException):
    pass


def test_rc110_review4_a_base_exception_is_audited_and_re_raised(registry, audit_events, monkeypatch):
    def aborting(*a, **k):
        raise Abort()
    monkeypatch.setattr(registry, "authorize_model_call", aborting)
    with pytest.raises(Abort):
        RT.AgentRuntime(registry, T.Tracer(T.NoopExporter())).run(
            "test-agent", model_client=H.ScriptedModel([]), scope=SCOPE, system="s", user_content="u")
    assert [e for e in audit_events if e.get("event") == "agent.run"][-1]["outcome"] in ("failure", "cancelled")


# ================================================================== 5. model segments name their model
def test_rc119_review4_a_model_part_without_a_model_id_is_refused():
    with pytest.raises(ValueError):
        P.compose([("model", "Seven lesions.", {"agent_id": "a"})])
    doc = P.mark_model_text("Seven lesions.", agent_id="a", model_id="m-1", trace_id=None, verifier=None).to_dict()
    doc["segments"][0]["model_id"] = None
    with pytest.raises(ValueError):
        P.ProvenanceDocument.from_dict(doc)


def test_rc119_review4_legend_follows_authorship():
    doc = P.mark_model_text("Seven lesions.", agent_id="a", model_id="m-1", trace_id=None, verifier=None)
    text = P.render_text(doc)
    assert P.TEXT_MARK in text and "no part of this text was written by an AI model" not in text


# ================================================================== 6. tool arguments named fn / blocking
def test_review4_tool_arguments_named_fn_and_blocking_reach_the_tool(switches, ledger, audit_events):
    data = make_registry_data()
    data["tools"]["odd_tool"] = {"access": "read", "arguments": {"segmentation_id": "resource_id", "fn": "string",
                                                                  "blocking": "boolean"}}
    data["agents"]["test-agent"]["allowed_tools"].append("odd_tool")
    reg = AgentRegistry(data, switches=switches, ledger=ledger, audit=audit_events.append, clock=lambda: FIXED_NOW)
    got = []

    def odd_tool(segmentation_id, fn, blocking):
        got.append((fn, blocking))
        return {"segmentation_id": segmentation_id}

    def model():
        call = RT.ToolCall("c1", "odd_tool", {"segmentation_id": "seg-1", "fn": "x", "blocking": True})
        return H.ScriptedModel([RT.ModelResponse("model-current", "", (call,), 10, 10, "tool_use"),
                                RT.ModelResponse("model-current", "Seven lesions.", (), 10, 10, "end_turn")])
    scope = RunScope("study-1", frozenset({"seg-1"}))
    rt = RT.AgentRuntime(reg, T.Tracer(T.NoopExporter()), tools={"odd_tool": odd_tool})
    assert rt.run("test-agent", model_client=model(), scope=scope, system="s", user_content="u").status == "delivered"
    res = asyncio.run(rt.arun("test-agent", model_client=model(), scope=scope, system="s", user_content="u"))
    assert res.status == "delivered" and got == [("x", True), ("x", True)]


# ================================================================== 7. one audit record per run
@pytest.mark.parametrize("case", ["refused_agent", "write_tool", "delivered", "model_failure"])
def test_rc110_review4_exactly_one_audit_record_per_run(registry, audit_events, case):
    class Down:
        provider = "anthropic"

        def complete(self, request):
            raise TimeoutError("down")
    write = RT.ToolCall("c1", "write_annotation", {"segmentation_id": "seg-1"})
    agent, model = {
        "refused_agent": ("pending-agent", H.ScriptedModel([])),
        "write_tool": ("test-agent", H.ScriptedModel([RT.ModelResponse("model-current", "", (write,), 1, 1, "tool_use")])),
        "delivered": ("test-agent", H.ScriptedModel([RT.ModelResponse("model-current", "Seven.", (), 1, 1, "end_turn")])),
        "model_failure": ("test-agent", Down()),
    }[case]
    RT.AgentRuntime(registry, T.Tracer(T.NoopExporter())).run(agent, model_client=model,
                                                             scope=RunScope("study-1", frozenset({"seg-1"})),
                                                             system="s", user_content="u")
    assert len(audit_events) == 1 and audit_events[0]["event"] == "agent.run", audit_events
    assert all(e["event"] in R.AUDIT_EVENT_TYPES for e in audit_events)


# ================================================================== 8. file exporter: one handle, writer thread
def test_rc116_review4_file_exporter_uses_one_handle_and_a_bounded_flush(tmp_path, monkeypatch):
    opened = {"n": 0}
    real_open = builtins.open

    def counting_open(*a, **k):
        opened["n"] += 1
        return real_open(*a, **k)
    monkeypatch.setattr(builtins, "open", counting_open)
    exporter = T.OtlpJsonFileExporter(str(tmp_path / "spans.jsonl"))
    tracer = T.Tracer(exporter)
    start = time.perf_counter()
    for _ in range(500):
        with tracer.agent_span("test-agent", provider="anthropic"):
            pass
    elapsed = time.perf_counter() - start
    assert exporter.flush(timeout=5.0)
    exporter.close()
    monkeypatch.setattr(builtins, "open", real_open)
    lines = (tmp_path / "spans.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 500 and opened["n"] <= 1, opened
    assert elapsed < 2.0


# ================================================================== 9. oversight edit size is bounded
def test_rc120_review4_edit_size_of_a_15k_report_is_bounded():
    sentences = [f"Lesion {i} in the periventricular white matter measures {i % 9 + 1}.{i % 7} mL and is stable."
                 for i in range(200)]
    shown = " ".join(sentences)
    assert len(shown) > 15_000
    final = shown.replace("is stable.", "is unchanged.", 40).replace("measures 3", "measures 4", 25)
    start = time.perf_counter()
    chars, ratio = O.edit_size(shown, final)
    elapsed = time.perf_counter() - start
    assert elapsed < 0.5, elapsed
    assert 0 < ratio < 0.2 and chars > 0
    assert O.edit_size("7 lesions", "8 lesions") == (1, 1 / 9)


# ================================================================== 10. one retirement rule
def test_rc117_review4_cards_reuse_the_registry_retirement_rule():
    tree = ast.parse(Path(C.__file__).read_text(encoding="utf-8"))
    assigned = {t.id for n in ast.walk(tree) if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
    assert "RETIREMENT_WARNING_DAYS" not in assigned
    assert C.RETIREMENT_WARNING_DAYS == R.RETIREMENT_WARNING_DAYS
    defaults = [p.default for p in inspect.signature(C.retirement_problems).parameters.values()
                if p.default is not inspect.Parameter.empty]
    assert not any(isinstance(d, tuple) for d in defaults), "the agents come from TEMPLATE_SOURCES, not a tuple"
    assert R.retirement_state(date(2026, 11, 30), date(2026, 11, 30)) == ("retired", 0)
    assert R.retirement_state(date(2026, 11, 30), date(2026, 11, 10)) == ("warning", 20)
