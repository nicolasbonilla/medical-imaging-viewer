"""RC-105 and RC-106 (REQ-SAFE-051; HAZ-017, HAZ-013) — DRAFT, PENDING owner approval.

RC-105: the kill switch. REPORT_LLM_ENABLED=false: no model is called (no client is even created); every report is the
        code-written measurements with the fixed "not requested" note.
RC-106: the model. Only an id of REPORT_MODELS is called, with its fixed parameters (no sampling parameter); the
        retiring claude-sonnet-4-5-20250929 (2026-11-30), any retired, retiring or unlisted id, and an allow-listed id
        past its retirement date are refused (measurements-only, reason stated). A provider failure, a 404 (the model
        no longer served), a timeout or a refusal give the measurements-only report too; the answer is read by block
        type; all calls of one report share a 25 s budget. The last test drives the SDK version the app pins
        (requirements.txt, anthropic 0.44.0) against a local fake transport — no network — and is skipped where that
        SDK is not installed (CI installs it).

No real API is called.
"""
import asyncio
import json
from datetime import date
from types import SimpleNamespace

import pytest

from app.services import brain_report_service as BRS
from app.services import verified_report as VR
from app.services.report_payload_guard import PatientIdentifiers

IDS = PatientIdentifiers.from_record({"mrn": "MRN-TEST-0106", "given_name": "Testgiven", "family_name": "Testfamily",
                                      "birth_date": date(1980, 1, 1)})
FINDINGS = {"lesion_analysis": {"total_count": 7, "total_burden_mm3": 3132.0, "total_burden_ml": 3.132,
                                "size_distribution": {"small": 4, "medium": 2, "large": 1}}}
GOOD = "[FINDINGS_COMMENT]\nMost lesions are small.\n[IMPRESSION_COMMENT]\nAutomatic marking, to be reviewed."


class _Client:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        return self.reply or SimpleNamespace(content=[SimpleNamespace(type="text", text=GOOD)], stop_reason="end_turn",
                                             model="claude-sonnet-5-5",
                                             usage=SimpleNamespace(input_tokens=3, output_tokens=3))


def _service(client=None, model="claude-sonnet-5-5", enabled=True, key="test-not-a-key"):
    svc = BRS.BrainReportService()
    svc._settings = SimpleNamespace(ANTHROPIC_API_KEY=key, CLAUDE_MODEL=model, CLAUDE_MAX_TOKENS=4096,
                                    REPORT_LLM_ENABLED=enabled)
    created = []
    if client is not None:
        svc._get_client = lambda: created.append(1) or client
    svc.created = created
    return svc


def _run(coro):
    """A loop of its own (asyncio.run would unset the loop the async tests of the suite share)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _generate(svc, findings=FINDINGS, language="en"):
    return _run(svc.generate_report(template_type="general", findings=findings, language=language, identifiers=IDS))


# ───────────────────────────────────────────────────────────── RC-105: the kill switch
@pytest.mark.parametrize("language", VR.LANGUAGES)
def test_rc105_the_kill_switch_calls_no_model(language):
    client = _Client()
    svc = _service(client, enabled=False)
    result = _generate(svc, language=language)
    assert client.calls == [] and svc.created == []
    assert result["verification"]["reason"] == VR.REASON_OFF and result["verification"]["interpretive_text"] == \
        "not_requested"
    assert result["model"] is None and result["tokens_used"] is None
    assert VR.WITHHELD[language]["off"] in result["content"]
    assert VR.T[language]["count_exact"].format(n=7) in result["content"]          # the measurements are all there


def test_rc105_the_kill_switch_is_an_environment_setting(monkeypatch):
    from app.core.config import Settings
    assert Settings.model_fields["REPORT_LLM_ENABLED"].default is True
    monkeypatch.setenv("REPORT_LLM_ENABLED", "false")
    assert Settings().REPORT_LLM_ENABLED is False


def test_rc105_the_kill_switch_works_without_a_provider_key():
    result = _generate(_service(None, enabled=False, key=""))
    assert result["verification"]["reason"] == VR.REASON_OFF


# ───────────────────────────────────────────────────────────── RC-106: the model
def test_rc106_the_default_model_is_current_and_allowed_never_the_retiring_one():
    from app.core.config import Settings
    default = Settings.model_fields["CLAUDE_MODEL"].default
    assert default == BRS.DEFAULT_REPORT_MODEL == "claude-sonnet-5-5"
    assert BRS.report_model_allowed(default)
    assert default not in BRS.RETIRED_OR_RETIRING_MODELS
    assert not BRS.report_model_allowed("claude-sonnet-4-5-20250929")


@pytest.mark.parametrize("model", ["claude-sonnet-4-5-20250929", "claude-sonnet-4-5", "claude-3-5-sonnet-20241022",
                                   "claude-opus-5-5", "gpt-4o", "", None])
def test_rc106_a_retiring_retired_or_unlisted_model_is_refused(model):
    client = _Client()
    result = _generate(_service(client, model=model))
    assert client.calls == []
    assert result["verification"]["reason"] == VR.REASON_MODEL_NOT_ALLOWED and result["model"] is None
    assert VR.WITHHELD["en"]["model"] in result["content"]


def test_rc106_an_allowed_model_past_its_retirement_date_is_refused(monkeypatch):
    monkeypatch.setitem(BRS.REPORT_MODELS, "claude-sonnet-5-5",
                        {**BRS.REPORT_MODELS["claude-sonnet-5-5"], "retires_on": "2027-01-01"})
    assert BRS.report_model_allowed("claude-sonnet-5-5", today=date(2026, 12, 31))
    assert not BRS.report_model_allowed("claude-sonnet-5-5", today=date(2027, 1, 1))


@pytest.mark.parametrize("model,params", [
    ("claude-sonnet-5-5", {"thinking": {"type": "between_tools"}, "output_config": {"effort": "low"}}),
    ("claude-haiku-5-5", {"thinking": {"type": "disabled"}, "output_config": {"effort": "low"}}),
])
def test_rc106_each_allowed_model_is_called_with_its_fixed_parameters(model, params):
    client = _Client()
    result = _generate(_service(client, model=model))
    (call,) = client.calls
    assert call["model"] == model and call["extra_body"] == params and call["max_tokens"] == 4096
    assert not {"temperature", "top_p", "top_k", "thinking", "output_config", "fallbacks"} & set(call)
    assert 1.0 <= call["timeout"] <= VR.LLM_DEADLINE_S
    assert result["verification"]["outcome"] == "passed_0"


class NotFoundError(Exception):
    status_code = 404


class APITimeoutError(Exception):
    pass


@pytest.mark.parametrize("error,reason", [(NotFoundError("model: claude-x"), VR.REASON_MODEL_UNAVAILABLE),
                                          (APITimeoutError("timed out"), VR.REASON_TIMEOUT),
                                          (RuntimeError("overloaded"), VR.REASON_PROVIDER)])
def test_rc106_a_provider_failure_gives_the_measurements_only(error, reason):
    client = _Client(error=error)
    result = _generate(_service(client))
    assert len(client.calls) == 1 and result["verification"]["reason"] == reason
    assert VR.WITHHELD["en"]["unavailable"] in result["content"] and "Lesions marked: 7" in result["content"]


def test_rc106_a_refusal_gives_the_measurements_only():
    refusal = SimpleNamespace(content=[], stop_reason="refusal", model="claude-sonnet-5-5",
                              usage=SimpleNamespace(input_tokens=3, output_tokens=0))
    client = _Client(reply=refusal)
    result = _generate(_service(client))
    assert len(client.calls) == 1 and result["verification"]["reason"] == VR.REASON_REFUSAL


def test_rc106_without_a_provider_key_nothing_is_sent():
    svc = _service(None, key="")
    result = _generate(svc)
    assert result["verification"]["reason"] == VR.REASON_NOT_CONFIGURED and svc._client is None


def test_rc106_the_answer_is_read_by_block_type():
    message = SimpleNamespace(content=[SimpleNamespace(type="thinking", thinking="", signature="s"),
                                       {"type": "thinking", "thinking": "reasoning"},
                                       SimpleNamespace(type="text", text="[FINDINGS_COMMENT]\nA."),
                                       {"type": "text", "text": "\n[IMPRESSION_COMMENT]\nB."},
                                       SimpleNamespace(text="no type: not read")],
                              stop_reason="end_turn", model="claude-sonnet-5-5",
                              usage=SimpleNamespace(input_tokens=1, output_tokens=2))
    reply = BRS.reply_of(message)
    assert reply.text == "[FINDINGS_COMMENT]\nA.\n[IMPRESSION_COMMENT]\nB."
    assert (reply.stop_reason, reply.model, reply.input_tokens, reply.output_tokens) == \
        ("end_turn", "claude-sonnet-5-5", 1, 2)


def test_rc106_all_calls_of_one_report_share_the_time_budget():
    clock = iter([0.0, 0.0, 30.0, 30.0, 30.0, 30.0])

    async def model(system, messages, timeout_s):
        return VR.ModelReply(text="no format", stop_reason="end_turn")

    records = []
    res = _run(VR.run_flow(VR.build_view(FINDINGS, None, "en"), "en", model,
                           request_meta={"model": "claude-sonnet-5-5"}, tripwire=lambda t: None,
                           on_attempt=records.append, clock=lambda: next(clock)))
    assert res.reason == VR.REASON_TIMEOUT and [r["verdict"] for r in records] == ["fail", "not_sent"]


# ───────────────────────────────────────────────────────────── the pinned SDK, offline (CI installs it)
def test_rc106_the_pinned_sdk_sends_the_fixed_parameters_and_the_reply_is_read_by_type():
    anthropic = pytest.importorskip("anthropic")
    httpx = pytest.importorskip("httpx")
    seen = []

    def handler(request):
        seen.append({"body": json.loads(request.content), "path": request.url.path})
        return httpx.Response(200, json={
            "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5",
            "content": [{"type": "thinking", "thinking": "", "signature": "sig"}, {"type": "text", "text": GOOD}],
            "stop_reason": "end_turn", "stop_sequence": None, "usage": {"input_tokens": 9, "output_tokens": 4}})

    client = anthropic.Anthropic(api_key="test-not-a-key", max_retries=0,
                                 http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    svc = _service(client)
    result = _generate(svc)
    (sent,) = seen
    assert sent["path"].endswith("/v1/messages")
    body = sent["body"]
    assert body["model"] == "claude-sonnet-5-5" and body["max_tokens"] == 4096
    assert body["thinking"] == {"type": "between_tools"} and body["output_config"] == {"effort": "low"}
    assert not {"temperature", "top_p", "top_k"} & set(body)
    assert body["system"] == VR.SYSTEM_PROMPT and body["messages"][0]["role"] == "user"
    assert result["verification"]["outcome"] == "passed_0" and "Most lesions are small." in result["content"]
    assert result["tokens_used"] == {"input": 9, "output": 4}
