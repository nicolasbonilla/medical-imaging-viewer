"""Third independent review of PR #78 (verified AI report), at 44195a8 — written BEFORE the corrections; the tests of
each item fail on the reviewed head. DRAFT, PENDING owner approval.

  T1 (clinical) the volume line needed mL AND mm³ (else "not computed") while {total_volume_ml} needed mL only:
     "- Total lesion volume: not computed." followed by "The total lesion volume is 3.13 mL." ONE availability rule:
     a placeholder is filled only when the code-written line states that value.
  T2 after an attempt, a timeout, provider failure or refusal gave the outcome "not_requested" (response and audit)
     although the AI was asked: it is "withheld", with the real reason and the attempts (RC-104).
  T3 asyncio.wait_for(asyncio.to_thread(client.messages.create)) left the thread and the request running after the
     time budget: the async client is awaited and cancelled at the deadline.
  T5 the retired templates and their prompt builder were dead code in a Class C module.
  T6 a function-level import of the private report_payload_guard._number.
(T4 is the viewer: frontend/src/components/ReportViewerModal.review3.test.tsx.)

Offline: fake providers, in-memory audit sink, no credential, no network.
"""
import ast
import asyncio
import inspect
import time
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.logging.audit_sink import DurableAuditSink, set_durable_audit_sink
from app.services import brain_report_service as BRS
from app.services import report_claim_verifier as V
from app.services import verified_report as VR
from app.services.report_payload_guard import PatientIdentifiers, provider_payload

IDS = PatientIdentifiers.from_record({"mrn": "MRN-TEST-0378", "given_name": "Testgiven", "family_name": "Testfamily",
                                      "birth_date": date(1980, 1, 1)})
GOOD = "[FINDINGS_COMMENT]\nMost lesions are small.\n[IMPRESSION_COMMENT]\nTo be reviewed by a radiologist."
BAD = "[FINDINGS_COMMENT]\nThere are 9 lesions.\n[IMPRESSION_COMMENT]\nTo be reviewed."
REPO = Path(__file__).resolve().parents[3]


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _view(findings, volumetry=None, lang="en"):
    p = provider_payload(findings, volumetry)
    return VR.build_view(p.findings, p.volumetry, lang)


def _service(client):
    svc = BRS.BrainReportService()
    svc._settings = SimpleNamespace(ANTHROPIC_API_KEY="test-not-a-key", CLAUDE_MODEL="claude-sonnet-5-5",
                                    CLAUDE_MAX_TOKENS=4096, REPORT_LLM_ENABLED=True)
    svc._get_client = lambda: client
    return svc


def _generate(svc, findings, volumetry=None):
    return _run(svc.generate_report(template_type="general", findings=findings, volumetry=volumetry, language="en",
                                    identifiers=IDS))


# ═══════════════════════════════════════════════════════════════════════ T1 — one availability rule
def test_rc102_t1_a_volume_in_ml_only_is_written_and_only_then_offered_as_a_placeholder():
    """The reviewer's reproduction: total_burden_ml without mm³."""
    view = _view({"lesion_analysis": {"total_count": 7, "total_burden_ml": 3.132}})
    assembled, fails = VR.check(view, "en", "[FINDINGS_COMMENT]\nThe total lesion volume is {total_volume_ml} mL.\n"
                                            "[IMPRESSION_COMMENT]\nTo be reviewed.")
    assert "Total lesion volume: not computed." not in assembled, assembled
    assert "Total lesion volume: 3.13 mL" in assembled and fails == []
    mm3_only = _view({"lesion_analysis": {"total_count": 7, "total_burden_mm3": 3132.0}})
    assert "total_volume_ml" not in VR.stated_values(mm3_only, "en")
    assert "3132 mm³" in VR.assemble(mm3_only, "en", "", "")


def _line_of(view, lang, placeholder):
    """The code-written line that states the value of a placeholder (None when the report has no such line)."""
    f, comp, _imp, _lim = VR.skeleton(view, lang)
    t = VR.T[lang]
    # (amended with the seventh review of PR #78, I1: no lesion block without a lesion analysis)
    if placeholder == "total_count":
        return f[1] if view["lesions"].get("computed") else None
    if placeholder == "total_volume_ml":
        return f[2] if view["lesions"].get("computed") else None
    if placeholder in ("new_candidates", "enlarging_candidates"):
        return comp[0] if comp else None
    if placeholder == "brain_regions_with_lesions":
        return next((x for x in f if x.startswith(t["dis_ev"].split("{")[0])), None)
    raise AssertionError(placeholder)


def _states_a_value(view, lang, placeholder, line):
    t = VR.T[lang]
    if line is None:
        return False
    if placeholder == "total_count":
        return line != t["count_nc"]
    if placeholder == "total_volume_ml":
        return line != t["volume_nc"] and (" mL" in line or " ml" in line)
    if placeholder in ("new_candidates", "enlarging_candidates"):
        lng = view.get("longitudinal") or {}
        return not lng.get("abstained")
    if placeholder == "brain_regions_with_lesions":
        return "brain_regions_with_lesions" in view["dis"]
    raise AssertionError(placeholder)


def _views():
    for findings, volumetry, source in VR.synthetic_payloads():
        for lang in VR.LANGUAGES:
            yield VR.build_view(findings, volumetry, lang, review_source=source), lang
    for la in ({"total_count": 7, "total_burden_ml": 3.132}, {"total_count": 7, "total_burden_mm3": 3132.0},
               {"total_count": 7}, {"total_count": 25, "total_burden_mm3": 3132.0, "total_burden_ml": 3.132}):
        for lang in VR.LANGUAGES:
            yield _view({"lesion_analysis": la}, lang=lang), lang


def test_rc102_t1_property_a_placeholder_is_available_exactly_when_its_line_states_the_value():
    n = 0
    for view, lang in _views():
        vals = VR.stated_values(view, lang)
        for ph in VR.PLACEHOLDERS:
            line = _line_of(view, lang, ph)
            stated = _states_a_value(view, lang, ph, line)
            assert (ph in vals) == stated, (ph, lang, line, vals.get(ph))
            if ph in vals:
                assert vals[ph] in line, (ph, vals[ph], line)
            n += 1
    assert n > 200


# ═══════════════════════════════════════════════════════════════════════ T2 — asked, then not delivered = withheld
def _flow(replies):
    """run_flow with scripted replies: a ModelReply, or an exception to raise."""
    view = _view({"lesion_analysis": {"total_count": 7, "total_burden_mm3": 10.0, "total_burden_ml": 0.01}})
    seq = list(replies)

    async def call(system, messages, remaining):
        r = seq.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    return _run(VR.run_flow(view, "en", call, request_meta={"model": "m"}, tripwire=lambda t: None,
                            on_attempt=lambda r: None))


@pytest.mark.parametrize("replies,reason", [
    ([VR.ModelReply(text=BAD), VR.ProviderFailure(VR.REASON_TIMEOUT, "TimeoutError")], VR.REASON_TIMEOUT),
    ([VR.ModelReply(text=BAD), VR.ProviderFailure(VR.REASON_PROVIDER, "APIError")], VR.REASON_PROVIDER),
    ([VR.ModelReply(text=BAD), VR.ModelReply(text="", stop_reason="refusal")], VR.REASON_REFUSAL),
    ([VR.ProviderFailure(VR.REASON_PROVIDER, "APIError")], VR.REASON_PROVIDER),
    ([VR.ModelReply(text="", stop_reason="refusal")], VR.REASON_REFUSAL),
], ids=["timeout_after_an_attempt", "provider_after_an_attempt", "refusal_after_an_attempt", "provider_first",
        "refusal_first"])
def test_rc104_t2_a_draft_the_ai_was_asked_for_and_did_not_deliver_is_withheld(replies, reason):
    result = _flow(replies)
    assert result.outcome == VR.OUTCOME_WITHHELD and result.interpretive == "withheld", result.summary()
    assert result.reason == reason and len(result.attempts) == len(replies)
    assert result.summary()["outcome"] == "withheld"


def test_rc104_t2_nothing_sent_is_still_not_requested():
    view = _view({"lesion_analysis": {"total_count": 7}})

    async def call(*a):
        raise AssertionError("no call expected")

    result = _run(VR.run_flow(view, "en", call, request_meta={"model": "m"}, tripwire=lambda t: None,
                              on_attempt=lambda r: None, deadline_s=0.0))
    assert result.outcome == VR.NOT_REQUESTED and result.interpretive == "not_requested"


@pytest.fixture
def sink():
    from app.core.logging.audit import reset_audit_budget
    reset_audit_budget()
    memory = DurableAuditSink(None, backend="memory")
    previous = set_durable_audit_sink(memory)
    yield memory
    set_durable_audit_sink(previous)


class _SyncClient:
    def __init__(self, answers):
        self.answers, self.calls = list(answers), []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=a)], stop_reason="end_turn",
                               model="claude-sonnet-5-5", usage=SimpleNamespace(input_tokens=2, output_tokens=2))


def test_rc104_t2_the_audit_and_the_response_say_withheld_with_the_reason(sink):
    client = _SyncClient([BAD, RuntimeError("provider down")])
    result = _run(_service(client).generate_report(
        template_type="general", findings={"lesion_analysis": {"total_count": 7}}, language="en", identifiers=IDS,
        audit_actor=SimpleNamespace(id="reader-t2", username="reader-t2", role="radiologist")))
    assert result["verification"]["outcome"] == "withheld" and result["verification"]["interpretive_text"] == "withheld"
    assert result["verification"]["reason"] == VR.REASON_PROVIDER and result["verification"]["attempts"] == 2
    (outcome,) = [r for r in sink.memory_records if r["event_type"] == "clinical.ai_report.verification"]
    assert outcome["details"]["report_outcome"] == "withheld" and outcome["details"]["interpretive_text"] == "withheld"
    assert outcome["details"]["llm_reason"] == VR.REASON_PROVIDER and outcome["details"]["attempts"] == 2


# ═══════════════════════════════════════════════════════════════════════ T3 — the async client, cancelled at the deadline
class _AsyncClient:
    """An async provider whose answer takes longer than the budget; it records whether it was really cancelled."""

    def __init__(self, delay):
        self.delay, self.started, self.cancelled = delay, False, False
        self.messages = self

    async def create(self, **kw):
        self.started = True
        try:
            await asyncio.sleep(self.delay)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=GOOD)], stop_reason="end_turn",
                               model="claude-sonnet-5-5", usage=SimpleNamespace(input_tokens=2, output_tokens=2))


def test_rc106_t3_the_provider_call_is_awaited_and_cancelled_at_the_deadline(monkeypatch):
    monkeypatch.setattr(VR, "LLM_DEADLINE_S", 0.5)
    client = _AsyncClient(delay=5.0)
    t0 = time.monotonic()
    result = _generate(_service(client), {"lesion_analysis": {"total_count": 7}})
    assert time.monotonic() - t0 < 2.0
    assert client.started and client.cancelled
    assert result["verification"]["reason"] == VR.REASON_TIMEOUT and result["verification"]["outcome"] == "withheld"


def test_rc106_t3_the_service_builds_the_async_client_without_retries(monkeypatch):
    import sys
    from unittest.mock import MagicMock
    module = MagicMock()
    monkeypatch.setitem(sys.modules, "anthropic", module)
    svc = BRS.BrainReportService()
    svc._settings = SimpleNamespace(ANTHROPIC_API_KEY="test-not-a-key-t3")   # fifth review, V4: a key of its own

    async def lookup():         # (amended with the seventh review, finding 9: a client only on a running loop)
        return svc._get_client()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(lookup())
    finally:
        loop.close()
    assert module.AsyncAnthropic.call_args.kwargs["max_retries"] == 0
    assert not module.Anthropic.called


def test_rc106_t3_with_the_pinned_sdk_the_http_request_itself_is_cancelled(monkeypatch):
    anthropic = pytest.importorskip("anthropic")
    import httpx
    state = SimpleNamespace(started=False, cancelled=False)

    class _Slow(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            state.started = True
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                state.cancelled = True
                raise
            return httpx.Response(500)

    monkeypatch.setattr(VR, "LLM_DEADLINE_S", 0.5)
    svc = BRS.BrainReportService()
    svc._settings = SimpleNamespace(ANTHROPIC_API_KEY="test-not-a-key", CLAUDE_MODEL="claude-sonnet-5-5",
                                    CLAUDE_MAX_TOKENS=4096, REPORT_LLM_ENABLED=True)
    client = anthropic.AsyncAnthropic(api_key="test-not-a-key", max_retries=0,
                                      http_client=httpx.AsyncClient(transport=_Slow()))
    svc._get_client = lambda: client
    t0 = time.monotonic()
    result = _generate(svc, {"lesion_analysis": {"total_count": 7}})
    assert time.monotonic() - t0 < 2.0
    assert state.started and state.cancelled
    assert result["verification"]["reason"] == VR.REASON_TIMEOUT


# ═══════════════════════════════════════════════════════════════════════ T5 — no retired templates in the shipped module
RETIRED = ("REPORT_TEMPLATES", "_FORMAT_INSTRUCTIONS", "dis_not_evaluated_template", "DIS_NOT_EVALUATED_SYSTEM_RULE",
           "CLINICIAN_TEXT_INSTRUCTION", "_synthetic_payloads")


def test_rc065_t5_the_retired_templates_are_not_in_the_shipped_module():
    for name in RETIRED:
        assert not hasattr(BRS, name), name
    assert not hasattr(BRS.BrainReportService, "_build_findings_prompt")
    assert not hasattr(BRS.BrainReportService, "list_retired_templates")
    archive = REPO / "docs" / "archive" / "retired_report_prompt.py"
    assert archive.exists() and "NOT SHIPPED" in archive.read_text(encoding="utf-8")
    assert not (REPO / "backend" / "archive").exists()      # the whole backend folder is copied into the image


def test_rc065_t5_the_device_vocabulary_comes_from_the_verified_report_only():
    src = inspect.getsource(BRS._fixed_prompt_word_lists)
    assert "verified_report.synthetic_payloads()" in src and "verified_report.first_user_message" in src
    assert "_build_findings_prompt" not in src and "REPORT_TEMPLATES" not in src


# ═══════════════════════════════════════════════════════════════════════ T6 — one public number reader, module level
def test_rc102_t6_the_number_reader_is_public_and_imported_at_module_level():
    from app.services import report_payload_guard as G
    assert callable(getattr(G, "finite_number", None))
    assert VR.finite_number is G.finite_number
    tree = ast.parse(Path(VR.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for inner in ast.walk(node):
                if isinstance(inner, ast.ImportFrom) and inner.module == "app.services.report_payload_guard":
                    raise AssertionError(f"function-level import in {node.name}")
    assert G.finite_number(float("inf")) is None and G.finite_number(True) is None and G.finite_number(2.5) == 2.5
