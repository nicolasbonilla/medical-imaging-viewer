"""Independent code review of PR #78 (verified AI report), findings 1-10 — written BEFORE the corrections; each test
fails on the reviewed head (d68b222). DRAFT, PENDING owner approval.

  R1  DIS evaluated without a lesion analysis (the route allows it) crashed the record builder (HTTP 500).
  R2  the SDK retry got a fresh full timeout: one draft could wait about twice the 25 s budget (REQ-SAFE-019, 30 s).
  R3  zone statistics, segmentation labels, anomalies and structure volumes were accepted and silently dropped.
  R4  a region count the device did not compute became 0 ("not computed", never 0 — RC-102).
  R5  {total_count} was filled with the exact count from 20 lesions (MAGNIMS 2021 asks for the range).
  R6  the record's "evaluated" rule was stricter than the gate's: a confirmed mask read "not confirmed".
  R7  a request refused by the privacy checks left no audit record of its outcome (RC-104).
  R8  the unlisted-label filter was dead code; now a placeholder in the record stops the request (fail closed).
  R9  the retired-model table was a second allow mechanism next to the allow-list and its retirement date.
  R10 the number reader accepted ±inf (and the count reader raised OverflowError on it).

Offline: fake provider, in-memory audit sink, no credential.
"""
import asyncio
import time
from datetime import date
from types import SimpleNamespace

import pytest

from app.core.logging.audit_sink import DurableAuditSink, set_durable_audit_sink
from app.services import brain_report_service as BRS
from app.services import report_claim_verifier as V
from app.services import verified_report as VR
from app.services.report_payload_guard import PatientIdentifiers, ProviderGuardError, provider_payload

IDS = PatientIdentifiers.from_record({"mrn": "MRN-TEST-0178", "given_name": "Testgiven", "family_name": "Testfamily",
                                      "birth_date": date(1980, 1, 1)})
EVALUATED = {"evaluation_status": "evaluated", "dis_met": True, "regions_with_lesions": 2, "total_dis_regions": 5,
             "region_details": {"Periventricular": {"present": True}, "Juxtacortical": {"present": True},
                                "Infratentorial": {"present": False}}}
GOOD = "[FINDINGS_COMMENT]\nMost lesions are small.\n[IMPRESSION_COMMENT]\nTo be reviewed by a radiologist."


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _view(findings, volumetry=None, lang="en"):
    p = provider_payload(findings, volumetry)
    return VR.build_view(p.findings, p.volumetry, lang)


class _Client:
    def __init__(self, answer=GOOD, delay=0.0):
        self.answer, self.delay, self.calls = answer, delay, []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        if self.delay:
            time.sleep(self.delay)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.answer)], stop_reason="end_turn",
                               model="claude-sonnet-5-5", usage=SimpleNamespace(input_tokens=2, output_tokens=2))


def _service(client):
    svc = BRS.BrainReportService()
    svc._settings = SimpleNamespace(ANTHROPIC_API_KEY="test-not-a-key", CLAUDE_MODEL="claude-sonnet-5-5",
                                    CLAUDE_MAX_TOKENS=4096, REPORT_LLM_ENABLED=True)
    svc._get_client = lambda: client
    return svc


def _generate(svc, findings, volumetry=None, **kw):
    return _run(svc.generate_report(template_type="general", findings=findings, volumetry=volumetry, language="en",
                                    identifiers=IDS, **kw))


# ── R1
def test_rc102_r1_dis_evaluated_without_lesion_analysis_gives_a_report():
    view = _view({"dis_assessment": EVALUATED})
    assert view["dis"]["status"] == "evaluated" and view["lesions"]["computed"] is False
    report = VR.assemble(view, "en", "", "")
    assert "Lesions per MAGNIMS region: not computed." in report and "Lesion count: not computed." in report
    assert not V.verify(report, None, view)["primary"]
    result = _generate(_service(_Client()), {"dis_assessment": EVALUATED})
    assert result["verification"]["outcome"] == "passed_0"
    assert any("lesion_analysis" not in f and isinstance(f.get("dis_assessment"), dict)
               and f["dis_assessment"].get("evaluation_status") == "evaluated" for f, _v, _s in VR.synthetic_payloads())


# ── R2
def test_rc106_r2_one_draft_never_waits_beyond_its_time_budget(monkeypatch):
    monkeypatch.setattr(VR, "LLM_DEADLINE_S", 0.6)
    client = _Client(delay=3.0)
    t0 = time.monotonic()
    result = _generate(_service(client), {"lesion_analysis": {"total_count": 7, "total_burden_mm3": 10.0,
                                                              "total_burden_ml": 0.01}})
    assert time.monotonic() - t0 < 2.0
    assert result["verification"]["reason"] == VR.REASON_TIMEOUT and "Lesions marked: 7" in result["content"]


def test_rc106_r2_the_client_makes_no_retry_of_its_own(monkeypatch):
    """Amended for the third review of PR #78 (T3, DRAFT): the service's client is the SDK's async client."""
    import sys
    from unittest.mock import MagicMock
    module = MagicMock()
    monkeypatch.setitem(sys.modules, "anthropic", module)
    svc = BRS.BrainReportService()
    svc._settings = SimpleNamespace(ANTHROPIC_API_KEY="test-not-a-key")
    svc._get_client()
    assert module.AsyncAnthropic.call_args.kwargs["max_retries"] == 0


# ── R3
@pytest.mark.parametrize("lang", VR.LANGUAGES)
def test_rc102_r3_measurements_not_in_the_verified_report_are_listed_never_dropped(lang):
    findings = {"lesion_analysis": {"total_count": 7, "total_burden_mm3": 10.0, "total_burden_ml": 0.01},
                "zone_stats": {"total_brain_voxels": 1000, "zones": {"Periventricular": {"voxel_count": 10,
                                                                                         "percentage": 1.0}}},
                "segmentation_labels": ["Periventricular"],
                "anomalies": [{"type": "Lesion", "confidence": 0.5}]}
    volumetry = {"total_brain_volume_ml": 1100.0, "structures": [{"structure_name": "Brain Stem", "volume_ml": 20.0}]}
    view = _view(findings, volumetry, lang)
    assert view["not_included"] == ["zone_statistics", "segmentation_labels", "anomalies", "structure_volumes"]
    report = VR.assemble(view, lang, "", "")
    line = VR.T[lang]["not_included"].format(items=", ".join(VR.T[lang]["ni_" + k] for k in view["not_included"]))
    assert line in report and not V.verify(report, None, view)["primary"]
    from app.services.dis_review_gate import scrub_unevaluated_dis
    assert scrub_unevaluated_dis(report, lang) == (report, 0)


def test_rc102_r3_the_api_says_which_measurements_are_not_included():
    from app.api.routes.ai_report import ReportGenerateRequest, router
    text = ReportGenerateRequest.model_fields["findings"].description
    assert "not included in the verified" in text
    route = next(r for r in router.routes if getattr(r, "path", "").endswith("/generate"))
    assert "not included in the verified" in route.description


# ── R4
def test_rc102_r4_a_region_count_not_computed_is_never_written_0():
    """Amended for the second review of PR #78 (E, DRAFT): the region not computed is "not computed" on its own; the
    regions that were computed keep their counts (they are never called "not computed")."""
    regions = {"Periventricular": {"lesion_count": "x", "total_volume_mm3": 1.0, "total_volume_ml": 0.001},
               "Juxtacortical": {"lesion_count": 2, "total_volume_mm3": 1.0, "total_volume_ml": 0.001},
               "Infratentorial": {"lesion_count": 1, "total_volume_mm3": 1.0, "total_volume_ml": 0.001},
               "Deep White Matter": {"lesion_count": 3, "total_volume_mm3": 1.0, "total_volume_ml": 0.001}}
    view = _view({"lesion_analysis": {"total_count": 7, "total_burden_mm3": 10.0, "total_burden_ml": 0.01,
                                      "size_distribution": {"small": 4, "medium": 2, "large": 1},
                                      "regions": regions}, "dis_assessment": EVALUATED})
    report = VR.assemble(view, "en", "", "")
    assert "periventricular: 0" not in report and "periventricular: not computed; juxtacortical: 2" in report
    assert 0.0 not in V.Pools(view).counts
    assert not V.verify(report, None, view)["primary"]


# ── R5
def test_rc102_r5_the_total_count_placeholder_follows_magnims_from_20_lesions():
    view = _view({"lesion_analysis": {"total_count": 75, "total_burden_mm3": 10.0, "total_burden_ml": 0.01}})
    assert VR.stated_values(view, "en")["total_count"] == "50-100"
    assembled, fails = VR.check(view, "en", "[FINDINGS_COMMENT]\nMost of the {total_count} lesions are small.\n"
                                            "[IMPRESSION_COMMENT]\nTo be reviewed.")
    assert fails == [] and "Most of the 50-100 lesions are small." in assembled and "75 lesions" not in assembled
    small = _view({"lesion_analysis": {"total_count": 7, "total_burden_mm3": 10.0, "total_burden_ml": 0.01}})
    assert VR.stated_values(small, "en")["total_count"] == "7"


# ── R6
def test_rc102_r6_the_report_never_contradicts_the_gate():
    from app.services import dis_review_gate as gate
    block = {**EVALUATED, "regions_with_lesions": "two"}
    assert gate.is_evaluated(block)
    view = _view({"lesion_analysis": {"total_count": 7, "total_burden_mm3": 10.0, "total_burden_ml": 0.01},
                  "dis_assessment": block})
    assert view["segmentation"]["confirmed_by_radiologist"] is True and view["dis"]["status"] == "evaluated"
    report = VR.assemble(view, "en", "", "")
    assert "not confirmed by a radiologist" not in report and VR.T["en"]["src_conf"] in report
    assert VR.T["en"]["dis_ev_nc"].format(met=VR.T["en"]["met"]) in report
    assert not V.verify(report, None, view)["primary"]
    _assembled, fails = VR.check(view, "en", "[FINDINGS_COMMENT]\nLesions are in two of three regions; dissemination "
                                             "in space is met in {brain_regions_with_lesions} regions.\n"
                                             "[IMPRESSION_COMMENT]\nReview.")
    assert "FMT.placeholder" in {f["rule"] for f in fails}


# ── R7
@pytest.fixture
def sink():
    # anonymous records are budgeted per source (CAPA-015 m9); the report route always has an authenticated user,
    # so these tests pass one (USER) and start from a fresh budget
    from app.core.logging.audit import reset_audit_budget
    reset_audit_budget()
    memory = DurableAuditSink(None, backend="memory")
    previous = set_durable_audit_sink(memory)
    yield memory
    set_durable_audit_sink(previous)


USER = SimpleNamespace(id="reader-r7", username="reader-r7", role="radiologist")


def _outcomes(sink):
    return [r for r in sink.memory_records if r["event_type"] == "clinical.ai_report.verification"]


def test_rc104_r7_a_request_refused_by_the_identifier_check_is_audited(sink, monkeypatch):
    original = VR.first_user_message
    monkeypatch.setattr(VR, "first_user_message", lambda view, lang: original(view, lang) + "\nTestgiven Testfamily")
    client = _Client()
    with pytest.raises(ProviderGuardError):
        _generate(_service(client), {"lesion_analysis": {"total_count": 7, "total_burden_mm3": 10.0,
                                                         "total_burden_ml": 0.01}}, segmentation_id="seg-r7",
                  audit_actor=USER)
    assert client.calls == []
    (outcome,) = _outcomes(sink)
    assert outcome["actor_user_id"] == "reader-r7"
    assert outcome["details"]["report_outcome"] == "not_sent" and outcome["outcome"] == "denied"
    assert outcome["details"]["llm_reason"] == "identifier_in_request"
    assert outcome["resource_ids"]["segmentation_id"] == "seg-r7"


def test_rc104_r7_a_request_refused_for_an_implausible_measurement_is_audited(sink):
    with pytest.raises(ProviderGuardError):
        _generate(_service(_Client()), {"lesion_analysis": {"total_count": 20240304}}, audit_actor=USER)
    (outcome,) = _outcomes(sink)
    assert (outcome["details"]["report_outcome"], outcome["details"]["llm_reason"]) == \
        ("not_sent", "implausible_measurement")


# ── R8
def test_rc102_r8_a_placeholder_in_the_record_stops_the_request(monkeypatch):
    original = VR.first_user_message
    monkeypatch.setattr(VR, "first_user_message", lambda view, lang: original(view, lang) + "\n[unlisted label 1]")
    client = _Client()
    findings = {"lesion_analysis": {"total_count": 7, "total_burden_mm3": 10.0, "total_burden_ml": 0.01,
                                    "regions": {"My A": {"lesion_count": 7}}}}
    with pytest.raises(ProviderGuardError):
        _generate(_service(client), findings)
    assert client.calls == []
    monkeypatch.setattr(VR, "first_user_message", original)
    assert _generate(_service(_Client()), findings)["unlisted_labels"] == {}


# ── R9
def test_rc106_r9_the_allow_list_and_its_retirement_date_alone_decide(monkeypatch):
    monkeypatch.setitem(BRS.RETIRED_OR_RETIRING_MODELS, "claude-sonnet-5-5", "2026-11-30")   # a table entry by mistake
    assert BRS.report_model_allowed("claude-sonnet-5-5", today=date(2026, 12, 1))
    monkeypatch.setattr(BRS, "RETIRED_OR_RETIRING_MODELS", {})
    assert not BRS.report_model_allowed("claude-sonnet-4-5-20250929")


# ── R10
def test_rc102_r10_an_infinite_value_is_not_computed():
    view = VR.build_view({"lesion_analysis": {"total_count": float("inf"), "total_burden_mm3": float("inf"),
                                              "total_burden_ml": float("-inf"),
                                              "size_distribution": {"small": float("nan"), "medium": 1, "large": 1}}},
                         {"total_brain_volume_ml": float("inf"), "intracranial_volume_ml": 1400.0}, "en")
    les = view["lesions"]
    assert les["total_count"] is None and les["total_volume_mm3"] is None and les["total_volume_ml"] is None
    assert view["brain_volumetry"]["total_brain_volume_ml"] is None
    report = VR.assemble(view, "en", "", "")
    assert "Lesion count: not computed." in report and "inf" not in report
