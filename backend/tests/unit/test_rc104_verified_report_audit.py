"""RC-104 (REQ-SAFE-050; HAZ-003, HAZ-016) — every model attempt of the verified report, and its outcome, are in the
server audit log (CAPA-015 trail: stdout + durable store): prompt SHA-256, model id, verdict, rule ids, latency —
never the prompt, the record, the answer or a typed text. DRAFT, PENDING owner approval.

Offline: the durable store is the in-memory sink; the provider is a fake.
"""
import hashlib
import json
import re
from datetime import date, datetime
from types import SimpleNamespace

import pytest

from app.core.logging.audit_sink import DurableAuditSink, set_durable_audit_sink
from app.security.models import User, UserRole
from app.services import verified_report as VR
from app.services.report_payload_guard import PatientIdentifiers

IDS = PatientIdentifiers.from_record({"mrn": "MRN-TEST-0104", "given_name": "Testgiven", "family_name": "Testfamily",
                                      "birth_date": date(1980, 1, 1)})
NOW = datetime(2026, 11, 10, 9, 0, 0)
USER = User(id="reader-104", username="reader-104", email="reader-104@example.com", full_name="Reader",
            role=UserRole.RADIOLOGIST, is_active=True, is_locked=False, email_verified=True, created_at=NOW,
            updated_at=NOW)
FINDINGS = {"lesion_analysis": {"total_count": 7, "total_burden_mm3": 3132.0, "total_burden_ml": 3.132,
                                "size_distribution": {"small": 4, "medium": 2, "large": 1}},
            "dis_assessment": {"evaluation_status": "not_evaluated"},
            "clinical_indication": "Typed ZQX text, Juan Perez"}
GOOD = "[FINDINGS_COMMENT]\nMost lesions are small ZQXOK.\n[IMPRESSION_COMMENT]\nAutomatic marking, to be reviewed."
BAD = "[FINDINGS_COMMENT]\nThere are 7 lesions ZQXBAD.\n[IMPRESSION_COMMENT]\nConsistent with multiple sclerosis."


class _Client:
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.answers.pop(0))], stop_reason="end_turn",
                               model="claude-sonnet-5-5", usage=SimpleNamespace(input_tokens=11, output_tokens=7))


@pytest.fixture
def sink():
    memory = DurableAuditSink(None, backend="memory")
    previous = set_durable_audit_sink(memory)
    yield memory
    set_durable_audit_sink(previous)


def _service(client, enabled=True):
    from app.services.brain_report_service import BrainReportService
    svc = BrainReportService()
    svc._settings = SimpleNamespace(ANTHROPIC_API_KEY="test-not-a-key", CLAUDE_MODEL="claude-sonnet-5-5",
                                    CLAUDE_MAX_TOKENS=4096, REPORT_LLM_ENABLED=enabled)
    svc._get_client = lambda: client
    return svc


async def _generate(client, enabled=True):
    return await _service(client, enabled).generate_report(template_type="general", findings=FINDINGS, language="en",
                                                           identifiers=IDS, audit_actor=USER, segmentation_id="seg-104")


def _records(sink, report_id, kind):
    return [r for r in sink.memory_records
            if r["event_type"] == kind and r.get("resource_ids", {}).get("report_id") == report_id]


@pytest.mark.asyncio
async def test_rc104_every_attempt_is_audited_with_hash_model_verdict_rules_and_latency(sink):
    client = _Client(BAD, GOOD)
    result = await _generate(client)
    attempts = _records(sink, result["report_id"], "clinical.ai_report.attempt")
    assert [a["details"]["attempt"] for a in attempts] == [1, 2]
    assert [a["details"]["verdict"] for a in attempts] == ["fail", "pass"]
    assert [a["outcome"] for a in attempts] == ["failure", "success"]
    assert {"FMT.digits", "E4.lexicon"} <= set(attempts[0]["details"]["rule_ids"])
    assert attempts[1]["details"].get("rule_ids") in (None, [])
    for a in attempts:
        d = a["details"]
        assert d["model_id"] == "claude-sonnet-5-5" and d["model_answered"] == "claude-sonnet-5-5"
        assert re.fullmatch(r"[0-9a-f]{64}", d["prompt_sha256"])
        assert isinstance(d["latency_ms"], int) and d["latency_ms"] >= 0
        assert (d["input_tokens"], d["output_tokens"]) == (11, 7) and d["flow"] == VR.FLOW_CODE
        assert a["actor_user_id"] == "reader-104" and a["resource_ids"]["segmentation_id"] == "seg-104"
    assert attempts[0]["details"]["prompt_sha256"] != attempts[1]["details"]["prompt_sha256"]


@pytest.mark.asyncio
async def test_rc104_the_prompt_hash_is_the_sha256_of_the_exact_request(sink):
    client = _Client(GOOD)
    result = await _generate(client)
    (attempt,) = _records(sink, result["report_id"], "clinical.ai_report.attempt")
    sent = client.calls[0]
    request = {"model": sent["model"], "max_tokens": sent["max_tokens"], "params": sent["extra_body"],
               "system": sent["system"], "messages": sent["messages"]}
    expected = hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False,
                                         separators=(",", ":")).encode("utf-8")).hexdigest()
    assert attempt["details"]["prompt_sha256"] == expected


@pytest.mark.asyncio
async def test_rc104_the_outcome_is_audited(sink):
    result = await _generate(_Client(BAD, BAD, BAD))
    (outcome,) = _records(sink, result["report_id"], "clinical.ai_report.verification")
    d = outcome["details"]
    assert (d["report_outcome"], d["interpretive_text"], d["attempts"], d["llm_reason"]) == \
        ("blocked", "withheld", 3, VR.REASON_BLOCKED)
    assert outcome["outcome"] == "partial" and outcome["severity"] == "medium"
    passed = await _generate(_Client(GOOD))
    (ok,) = _records(sink, passed["report_id"], "clinical.ai_report.verification")
    assert (ok["details"]["report_outcome"], ok["details"]["interpretive_text"], ok["outcome"]) == \
        ("passed_0", "delivered", "success")


@pytest.mark.asyncio
async def test_rc104_a_report_without_model_call_is_audited_with_its_reason(sink):
    client = _Client()
    result = await _generate(client, enabled=False)
    assert client.calls == [] and _records(sink, result["report_id"], "clinical.ai_report.attempt") == []
    (outcome,) = _records(sink, result["report_id"], "clinical.ai_report.verification")
    assert outcome["details"]["llm_reason"] == VR.REASON_OFF and outcome["details"]["attempts"] == 0
    assert "model_id" not in outcome["details"]


@pytest.mark.asyncio
async def test_rc104_no_prompt_record_answer_or_typed_text_in_the_audit(sink):
    result = await _generate(_Client(BAD, GOOD))
    mine = [r for r in sink.memory_records if r.get("resource_ids", {}).get("report_id") == result["report_id"]]
    assert len(mine) == 3
    text = json.dumps(mine).casefold()
    for absent in ("zqx", "juan", "perez", "lesions marked", "measurement record", "consistent with",
                   "findings_comment", "write the draft"):
        assert absent not in text, absent
    # (amended with the fifth review of PR #78: the number is looked for as a number — the records carry random
    # hexadecimal ids and hashes, which contained "3132" by chance in a CI run)
    import re
    assert not re.search(r"(?<![0-9a-f-])3132(?![0-9a-f-])", text), "3132"


def test_rc104_the_audit_allow_list_keeps_codes_and_drops_free_text():
    from app.core.logging.audit import AuditEvent, AuditEventType, AuditOutcome, AuditSeverity, build_audit_record
    event = AuditEvent(event_type=AuditEventType.CLINICAL_AI_REPORT_ATTEMPT, severity=AuditSeverity.LOW,
                       outcome=AuditOutcome.FAILURE,
                       details={"model_id": "claude-sonnet-5-5", "verdict": "fail", "latency_ms": 812,
                                "rule_ids": ["E3.technique", "a sentence of the answer", "FMT.digits"],
                                "prompt_sha256": "a" * 64, "comment": "free text is not a detail key",
                                "error": "Some error with spaces"})
    d = build_audit_record(event)["details"]
    assert d["model_id"] == "claude-sonnet-5-5" and d["verdict"] == "fail" and d["latency_ms"] == 812
    assert d["rule_ids"] == ["E3.technique", "FMT.digits"] and d["prompt_sha256"] == "a" * 64
    assert "comment" not in d and "error" not in d
