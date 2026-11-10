"""Findings 1-10 of the SECOND independent adversarial review of PR #79 — failing-first tests.

DRAFT, PENDING owner approval. Written against the code at 8475800, where every test below fails; the fixes
follow in later commits. Negative controls: scripts/safety/agent_platform_negative_controls.py (mutations W*).

1. Activity flags computed from unconfirmed candidates never reach a model on the platform path either:
   one shared rule with the MCP client (CAPA-013, RC-060; RC-113).
2. The provenance splitter keeps list markers on their item and does not split after a defined
   abbreviation list (RC-119).
3. The result scope also refuses foreign ids used as dict KEYS, numeric ids not declared as lesion
   numbers, *_path / *_uri / *_url values and storage locations (gs://, s3://, ...) (RC-114).
4. A malformed provider response is a non-delivery with a fixed, audited code (RC-110).
5. A cancelled run settles its reservation and leaves an audit record before re-raising (RC-112, RC-110).
6. In ``arun`` sync tools and the verifier run off the event loop (robustness).
7. An edited model sentence keeps a distinct AI marker in the signed text (RC-119).
8. Empty model output is a non-delivery with a fixed, audited code (RC-110).
9. The assistant card hashes the full tool definition (name, description, parameters, signature) (RC-117).
10. Negative controls run in a throwaway copy; CI fails if a mutation is left in the tracked sources (RC-118).
"""
import asyncio
import importlib.util
import inspect
import json
import time
from pathlib import Path

import pytest

from app.agent_platform import cards as C
from app.agent_platform import provenance as P
from app.agent_platform import registry as R
from app.agent_platform import runtime as RT
from app.agent_platform import tracing as T
from app.agent_platform import untrusted as U
from app.agent_platform.registry import AgentRegistry, InMemoryCostLedger, RefusalCode
from app.agent_platform.untrusted import RunScope
from tests.agent_platform import _harness as H
from tests.agent_platform._fixtures import FIXED_NOW, make_registry_data

SCOPE = RunScope("study-1", frozenset({"seg-1", "seg-0", "file-1"}))
REPO = Path(__file__).resolve().parents[3]
NC_SCRIPT = REPO / "scripts" / "safety" / "agent_platform_negative_controls.py"


class Scripted:
    provider = "anthropic"

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        return self.responses.pop(0)


def resp(text="x", stop="end_turn", calls=(), model="model-current"):
    return RT.ModelResponse(model_id=model, text=text, tool_calls=tuple(calls), input_tokens=10, output_tokens=10,
                            stop_reason=stop)


def run_events(audit_events):
    return [e for e in audit_events if e.get("event") == "agent.run"]


# ================================================================== 1. unconfirmed activity flags
READ = R.ToolEntry(name="read_measurements", access="read", arguments=(("segmentation_id", "resource_id"),))


def test_rc113_review2_unconfirmed_activity_flags_never_reach_the_model():
    result = {"segmentation_id": "seg-1", "activity_candidate": True, "dit_candidate": True, "enlarging_count": 3,
              "new_clinically_significant_count": 2, "nested": {"activity_candidate": True},
              "reader_confirmed_activity": {"confirmed": 1}}
    check = U.validate_tool_result(result, tool=READ, scope=SCOPE, max_bytes=10_000)
    assert check.ok
    for key in ("activity_candidate", "dit_candidate", "enlarging_count", "new_clinically_significant_count"):
        assert key not in json.dumps(check.cleaned) and key not in check.for_model
    assert "reader_confirmed_activity" in check.for_model


def test_rc113_review2_one_shared_rule_with_the_mcp_client():
    from app.mcp import _backend
    assert U.assistant_view is _backend.assistant_view
    src = inspect.getsource(_backend)
    assert src.count("assistant_view(response.json())") == 2, "api_get and api_post_compute use the shared rule"


# ================================================================== 2. provenance splitter
def test_rc119_review2_list_markers_stay_on_their_item():
    text = "1. Seven lesions were marked.\n2. MAGNIMS 2021 counting was used.\n10) The largest lesion is 1.5 mL."
    units = [u[1] for u in P.split_units(text)]
    assert units == ["1. Seven lesions were marked.", "2. MAGNIMS 2021 counting was used.",
                     "10) The largest lesion is 1.5 mL."]
    rendered = P.render_text(P.mark_model_text(text, agent_id="a", model_id="m", trace_id=None, verifier=None))
    assert rendered.splitlines()[0] == "1. [AI] Seven lesions were marked."


@pytest.mark.parametrize("text,n", [
    ("Lesions e.g. periventricular ones are listed. The total is approx. 3.1 mL.", 2),
    ("Seven lesions, i.e. all small. Volume ca. 3 mL vs. 2.9 mL before.", 2),
    ("Lesiones p. ej. periventriculares. Volumen aprox. 3 mL.", 2),
    ("Läsionen z. B. periventrikulär. Volumen ca. 3 ml, vgl. Voruntersuchung.", 2),
    ("Reviewed by Dr. Smith. Fig. 2 shows it.", 2),
    ("Seven lesions. Eight lesions! Nine?", 3),
])
def test_rc119_review2_abbreviations_do_not_split(text, n):
    assert len([u for u in P.split_units(text) if u[1].strip()]) == n
    assert "".join(u[1] + u[2] for u in P.split_units(text)) == text


# ================================================================== 3. result scope: keys, numbers, locations
@pytest.mark.parametrize("result", [
    {"seg-OTHER": {"lesions": 3}},
    {"by_segmentation": {"seg-OTHER": 1}},
    {"segmentation_id": 12345},
    {"lesions": [{"id": "seg-OTHER"}]},                      # amended by the third review: by VALUE, not by key
    {"mask_path": "/data/seg-1.nii.gz"},
    {"note": "stored at gs://bucket/patients/other.nii.gz"},
    {"download_url": "https://storage.googleapis.com/bucket/other.nii.gz"},
    {"items": [{"source": "s3://bucket/other"}]},
])
def test_rc114_review2_foreign_keys_numeric_ids_and_locations_refuse_the_result(result):
    check = U.validate_tool_result(result, tool=READ, scope=SCOPE, max_bytes=10_000)
    assert not check.ok and check.code == RefusalCode.OUT_OF_SCOPE_RESOURCE, result


def test_rc114_review2_declared_lesion_numbers_in_scope_keys_and_labels_pass():
    tool = R.ToolEntry(name="analyze_lesions", access="read", arguments=(("segmentation_id", "resource_id"),))
    ok = U.validate_tool_result({"seg-1": {"lesions": [{"id": 4, "label_id": 1}]}, "Deep White Matter": 2,
                                 "Cortical / Juxtacortical": 1, "image_uri": "seg-1"}, tool=tool, scope=SCOPE,
                                max_bytes=10_000)
    assert ok.ok, ok


def test_rc114_review2_storage_locations_in_arguments_are_refused():
    tool = R.ToolEntry(name="t", access="read", arguments=(("segmentation_id", "resource_id"), ("notes", "array")))
    d = U.check_tool_arguments(tool, {"segmentation_id": "seg-1", "notes": [{"ref": "gs://bucket/x"}]}, SCOPE)
    assert not d.allowed and d.code == RefusalCode.OUT_OF_SCOPE_RESOURCE


def test_rc114_review2_production_registry_declares_the_result_resource_keys_of_the_real_schemas():
    """Amended by the third review (findings 1-2): numbers under lesion, label, region or zone keys are not
    resources at all; what a tool declares instead is which result keys DO hold resource ids (its real schema)."""
    tools = H.production_data()["tools"]
    assert all("result_numeric_keys" not in t for t in tools.values())
    assert tools["compare_longitudinal"]["result_resource_keys"] == ["id"]
    assert tools["list_segmentations"]["result_resource_keys"] == ["id"]


# ================================================================== 4. malformed provider response
@pytest.mark.parametrize("bad", [
    None,
    {"text": "x"},
    RT.ModelResponse(model_id="model-current", text="x", tool_calls={"name": "read_measurements"}),
    RT.ModelResponse(model_id="model-current", text="x", tool_calls=None),
    RT.ModelResponse(model_id="model-current", text=5),
    RT.ModelResponse(model_id="model-current", text="", stop_reason="tool_use",
                     tool_calls=(RT.ToolCall("c1", "read_measurements", ["seg-1"]),)),
    RT.ModelResponse(model_id="model-current", text="", stop_reason="tool_use", tool_calls=("read_measurements",)),
    RT.ModelResponse(model_id=None, text="x"),
])
def test_rc110_review2_malformed_provider_response_is_an_audited_non_delivery(switches, audit_events, bad):
    ledger = InMemoryCostLedger()
    reg = AgentRegistry(make_registry_data(), switches=switches, ledger=ledger, audit=audit_events.append,
                        clock=lambda: FIXED_NOW)
    res = RT.AgentRuntime(reg, T.Tracer(T.NoopExporter())).run(
        "test-agent", model_client=Scripted([bad]), scope=SCOPE, system="s", user_content="u")
    assert res.status == "failed" and res.code == RefusalCode.MODEL_RESPONSE_INVALID and res.text is None
    assert run_events(audit_events)[-1]["outcome"] == "failure"
    assert ledger.open_reservations() == 0


# ================================================================== 5. cancellation
def test_rc112_review2_cancelled_model_call_settles_and_is_audited(switches, audit_events):
    ledger = InMemoryCostLedger()
    reg = AgentRegistry(make_registry_data(), switches=switches, ledger=ledger, audit=audit_events.append,
                        clock=lambda: FIXED_NOW)

    class Hanging:
        provider = "anthropic"

        async def acomplete(self, request):
            await asyncio.Event().wait()

    async def main():
        rt = RT.AgentRuntime(reg, T.Tracer(T.NoopExporter()))
        task = asyncio.create_task(rt.arun("test-agent", model_client=Hanging(), scope=SCOPE, system="s",
                                           user_content="u"))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(main())
    assert ledger.open_reservations() == 0
    study, _ = ledger.totals("test-agent", "study-1", FIXED_NOW.date().isoformat())
    assert study > 0, "the worst case of a cancelled call stays charged"
    ev = run_events(audit_events)[-1]
    assert ev["outcome"] == "cancelled" and ev["code"] == str(RefusalCode.RUN_CANCELLED)


def test_rc110_review2_cancelled_tool_call_is_audited(registry, audit_events):
    async def hanging_tool(segmentation_id):
        await asyncio.Event().wait()

    class AsyncModel:
        provider = "anthropic"

        async def acomplete(self, request):
            return resp("", stop="tool_use", calls=[RT.ToolCall("c1", "read_measurements", {"segmentation_id": "seg-1"})])

    async def main():
        rt = RT.AgentRuntime(registry, T.Tracer(T.NoopExporter()), tools={"read_measurements": hanging_tool})
        task = asyncio.create_task(rt.arun("test-agent", model_client=AsyncModel(), scope=SCOPE, system="s",
                                           user_content="u"))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(main())
    assert run_events(audit_events)[-1]["outcome"] == "cancelled"


# ================================================================== 6. sync tools and verifier off the loop
def _ticks_during(coro_factory):
    async def main():
        ticks = {"n": 0}

        async def ticker():
            while True:
                ticks["n"] += 1
                await asyncio.sleep(0.01)
        task = asyncio.create_task(ticker())
        res = await coro_factory()
        task.cancel()
        return res, ticks["n"]
    return asyncio.run(main())


def test_review2_slow_sync_tool_does_not_stall_the_callers_loop(registry):
    def slow_tool(segmentation_id):
        time.sleep(0.3)
        return {"segmentation_id": segmentation_id}

    class AsyncModel:
        provider = "anthropic"

        def __init__(self):
            self.r = [resp("", stop="tool_use", calls=[RT.ToolCall("c1", "read_measurements",
                                                                   {"segmentation_id": "seg-1"})]), resp("Seven.")]

        async def acomplete(self, request):
            return self.r.pop(0)
    rt = RT.AgentRuntime(registry, T.Tracer(T.NoopExporter()), tools={"read_measurements": slow_tool})
    res, ticks = _ticks_during(lambda: rt.arun("test-agent", model_client=AsyncModel(), scope=SCOPE, system="s",
                                               user_content="u"))
    assert res.status == "delivered" and ticks >= 5


def test_review2_slow_sync_verifier_does_not_stall_the_callers_loop(registry):
    def slow_verifier(draft, ctx):
        time.sleep(0.3)
        return RT.Verdict("pass", draft)

    class AsyncModel:
        provider = "anthropic"

        async def acomplete(self, request):
            return resp("Seven lesions.")
    rt = RT.AgentRuntime(registry, T.Tracer(T.NoopExporter()), verifier=slow_verifier)
    res, ticks = _ticks_during(lambda: rt.arun("test-agent", model_client=AsyncModel(), scope=SCOPE, system="s",
                                               user_content="u"))
    assert res.status == "delivered" and ticks >= 5


# ================================================================== 7. edited model sentences keep a marker
def test_rc119_review2_edited_model_sentence_keeps_a_distinct_marker():
    draft = "Seven lesions were marked. Dissemination in space: not evaluated."
    doc = P.mark_model_text(draft, agent_id="a", model_id="m-1", trace_id=None, verifier=None)
    edited = P.reconcile(doc, draft.replace("Seven", "Eight"))
    text = P.render_text(edited)
    assert P.TEXT_MARK_EDITED + " Eight lesions were marked." in text
    assert P.TEXT_MARK + " Dissemination" in text
    assert P.TEXT_MARK_EDITED in text.splitlines()[-1], "the legend explains the edited marker"
    html = P.render_html(edited)
    assert 'class="mstool-ai-edited"' in html and 'data-edited-from-model="true"' in html


# ================================================================== 8. empty output
@pytest.mark.parametrize("text", ["", "   \n ", None])
@pytest.mark.parametrize("with_verifier", [False, True])
def test_rc110_review2_empty_output_is_an_audited_non_delivery(registry, audit_events, text, with_verifier):
    verifier = (lambda d, c: RT.Verdict("pass", d or "")) if with_verifier else None
    rt = RT.AgentRuntime(registry, T.Tracer(T.NoopExporter()), verifier=verifier)
    res = rt.run("test-agent", model_client=Scripted([resp(text)]), scope=SCOPE, system="s", user_content="u")
    assert res.status == "failed" and res.code == RefusalCode.MODEL_OUTPUT_EMPTY and res.text is None
    assert run_events(audit_events)[-1]["outcome"] == "failure"


# ================================================================== 9. full tool definitions in the card
def test_rc117_review2_card_hashes_the_full_tool_definition():
    names = C.TEMPLATE_SOURCES["ms-clinical-assistant"]()
    assert "mcp.ms_clinical_server.tool[analyze_lesions].definition" in names
    definition = json.loads(names["mcp.ms_clinical_server.tool[analyze_lesions].definition"])
    assert definition["name"] == "analyze_lesions" and "signature" in definition
    assert [p["name"] for p in definition["parameters"]] == ["segmentation_id"]


@pytest.mark.parametrize("change", ["add_parameter", "change_default"])
def test_rc117_review2_a_tool_signature_change_fails_the_card_check(monkeypatch, change):
    real = C.load_with_stub_fastmcp

    def patched(path, alias):
        module = real(path, alias)
        if path.name == "ms_clinical_server.py":
            original = module.mcp.tools["generate_ms_report"]
            if change == "add_parameter":
                async def generate_ms_report(segmentation_id: str, language: str = "en",
                                             include_longitudinal: bool = False, longitudinal_baseline_id: str = "",
                                             write_to_record: bool = True) -> dict:
                    return {}
            else:
                async def generate_ms_report(segmentation_id: str, language: str = "de",
                                             include_longitudinal: bool = False,
                                             longitudinal_baseline_id: str = "") -> dict:
                    return {}
            generate_ms_report.__doc__ = original.__doc__
            module.mcp.tools["generate_ms_report"] = generate_ms_report
        return module
    monkeypatch.setattr(C, "load_with_stub_fastmcp", patched)
    problems = C.check_card("ms-clinical-assistant", H.production_data())
    assert any("tool[generate_ms_report]" in p for p in problems), problems


# ================================================================== 10. negative controls never touch the checkout
def _nc():
    spec = importlib.util.spec_from_file_location("agent_nc_under_test", NC_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rc118_review2_loading_the_script_changes_nothing():
    import os
    cwd = os.getcwd()
    nc = _nc()
    assert os.getcwd() == cwd, "importing the script must not change the working directory"
    assert nc.M


def test_rc118_review2_no_mutation_is_left_in_the_tracked_sources():
    """The CI guard: every mutation's original code (its anchor) is present exactly once, and where a mutation
    INSERTS text around its anchor, the inserted text is absent — so no mutation can be left in a commit."""
    nc = _nc()
    for name, (path, anchor, replacement, _c, _w) in nc.M.items():
        text = (REPO / path).read_text(encoding="utf-8").replace("\r\n", "\n")
        assert text.count(anchor) == 1, f"{name}: the original code is missing from {path} — a mutation was left in it"
        if anchor in replacement:
            inserted = [part for part in replacement.split(anchor) if part.strip()]
            assert not any(part in text for part in inserted), f"{name}: its inserted code is present in {path}"


def test_rc118_review2_mutations_are_applied_in_a_throwaway_copy():
    nc = _nc()
    name = "R1_write_tools_allowed"
    path = nc.M[name][0]
    before = (REPO / path).read_bytes()
    with nc.work_copy() as work:
        assert REPO not in Path(work).resolve().parents and Path(work).resolve() != REPO
        nc.apply_mutation(work, name)
        assert (REPO / path).read_bytes() == before, "the real checkout was touched"
        assert (Path(work) / path).read_bytes() != before
    assert not Path(work).exists(), "the throwaway copy is removed"
