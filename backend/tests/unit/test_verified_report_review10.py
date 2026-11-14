"""Tenth independent review of PR #78 — invariants I16-I19 and findings 5, 7, 8, 9 (Class C; REQ-SAFE-048/049/050/051;
RC-064, RC-065, RC-066, RC-102 to RC-106, CAPA-008, CAPA-013). DRAFT, PENDING owner approval.

Written failing first on 0a6b1c4 (before any correction).

I16  every error of the report route carries a machine-readable `error.code` (parameters in `error.details`); the
     report panel maps codes, never message prefixes — one shared fixture (backend/tests/fixtures/report_error_codes.json,
     read here and by frontend/src/components/AIReportPanel.errorCodes.test.tsx).
I17  no record states that a check passed unless that check ran before it was written (comments ON and OFF); a model
     call cancelled in flight still writes the verification record, with that paid call counted (RC-104).
I18  no model request is sent with less than MIN_LLM_BUDGET_S left, retries included; a retry skipped (or cut) for
     lack of time is reported as failed_check / withheld — the AI answered and its text was withheld.
I19  CAPA-008's "nothing to write -> 422 nothing_to_report" is evaluated after the route's own substitutions.
"""
import asyncio
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.api.routes.ai_report as ai_report
from app.services import brain_report_service as BRS
from app.services import report_payload_guard as G
from app.services import verified_report as VR
from tests.unit.test_capa014_report_provider_payload import _Patients, _measurements, _post, route  # noqa: F401
from tests.unit.test_verified_report_scenario_matrix import (GOOD, I7_CASES, IDS, _Client, _generate,  # noqa: F401
                                                              _request, _run, _service, sink)

FIXTURE = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "report_error_codes.json")
                     .read_text(encoding="utf-8"))
CODES = {c["code"]: c for c in FIXTURE["codes"]}
REAL_SERVER_LESION_TABLE = ai_report.server_lesion_table      # (captured before the route fixture stubs it)
LESION_CASE = {"lesion": "computed", "dis": "not_evaluated", "longitudinal": "absent", "volumetry": "absent",
               "source": "automatic", "entry": "none"}
FAILING = GOOD.replace("The marking is automatic.", "There are seven lesions.")   # fails FMT.number_words


def _error(r):
    body = r.json()
    return body.get("error") if isinstance(body.get("error"), dict) else {}


# ══════════════════════════════════════════════════════════════════════════════════════════════ I16
def _raise(exc):
    def f(*a, **k):
        raise exc
    return f


def _araise(exc):
    async def f(*a, **k):
        raise exc
    return f


def _real_lesion_table(monkeypatch, exc):
    import app.api.routes.segmentation_analysis as sa
    monkeypatch.setattr(ai_report, "server_lesion_table", REAL_SERVER_LESION_TABLE)
    monkeypatch.setattr(ai_report, "_dis_services", lambda: (None, None))
    monkeypatch.setattr(sa, "lesion_table", _araise(exc))


def _scenario(code, route, monkeypatch):
    """One request that must end in `code` (the reviewer's cases and one per remaining error of the route)."""
    from app.utils import VoxelSpacingUnavailableError
    f = _measurements()
    if code == "nothing_to_report":
        return _post(route, {})
    if code == "segmentation_required":
        return _post(route, f, seg=None)
    if code == "segmentation_not_found":
        monkeypatch.setattr(ai_report, "authorize_segmentation_id",
                            _araise(HTTPException(status_code=404, detail="Segmentation not found")))
    elif code == "segmentation_conflict":
        f["lesion_analysis"]["segmentation_id"] = "another-segmentation"
    elif code == "request_invalid":
        monkeypatch.setattr(ai_report, "authorize_mask_specs",
                            _araise(HTTPException(status_code=400, detail="Invalid mask reference")))
    elif code == "geometry_unreadable":
        _real_lesion_table(monkeypatch, VoxelSpacingUnavailableError("no voxel spacing in the header"))
    elif code == "lesion_table_failed":
        _real_lesion_table(monkeypatch, RuntimeError("the table could not be computed"))
    elif code == "implausible_measurement":
        f["lesion_analysis"]["total_count"] = 20240304
    elif code == "patient_record_unavailable":
        route.patients = _Patients(error=RuntimeError("the record store is down"))
    elif code == "identifier_in_prompt":
        monkeypatch.setattr(BRS, "assert_prompt_carries_no_identifier",
                            _raise(G.IdentifierInPrompt("identifier check failed (name)")))
    elif code == "label_in_record":
        monkeypatch.setattr(BRS, "assert_prompt_carries_no_identifier",
                            _raise(BRS.LabelInRecord("a label of the request reached the measurement record")))
    elif code == "not_sent":
        monkeypatch.setattr(BRS, "assert_prompt_carries_no_identifier", _raise(G.ProviderGuardError("refused")))
    elif code == "report_failed":
        monkeypatch.setattr(VR, "change_notice", _raise(RuntimeError("internal fault")))
    return _post(route, f)


@pytest.mark.parametrize("code", sorted(CODES))
def test_rc103_i16_every_report_error_carries_its_code(route, monkeypatch, code):
    entry = CODES[code]
    r = _scenario(code, route, monkeypatch)
    err = _error(r)
    assert (r.status_code, err.get("code")) == (entry["status"], code), r.text[:400]
    for k, v in (entry.get("details") or {}).items():
        assert (err.get("details") or {}).get(k) == v, err


def test_rc103_i16_the_route_and_the_fixture_name_the_same_codes():
    assert set(getattr(ai_report, "REPORT_ERROR_CODES", ())) == set(CODES)
    texts = [c["en"] for c in FIXTURE["codes"]]
    assert len(set(texts)) == len(texts), "every code has its own panel message"
    # every error leaves the route through the coded error (no bare HTTPException in the route body)
    assert "raise HTTPException(" not in inspect.getsource(ai_report.generate_report)


@pytest.mark.parametrize("path,value", [("lesion_analysis.total_count", 20240304),
                                        ("lesion_analysis.total_burden_mm3", 19751109),
                                        ("lesion_analysis.regions.Periventricular.lesion_count", -1)])
@pytest.mark.parametrize("comments_on", [True, False])
def test_rc103_i16_an_implausible_measurement_names_it_and_where_it_comes_from(route, monkeypatch, path, value,
                                                                               comments_on):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "REPORT_LLM_ENABLED", comments_on)
    f = _measurements()
    target, keys = f, path.split(".")
    for k in keys[:-1]:
        target = target[k]
    target[keys[-1]] = value
    r = _post(route, f)
    err = _error(r)
    assert r.status_code == 422 and err.get("code") == "implausible_measurement", r.text[:300]
    field = (err.get("details") or {}).get("field")
    assert field == keys[-1] and field in FIXTURE["fields"], err
    message = str(err.get("message", "")).lower()
    assert "segmentation analysis" in message and ("re-run" in message or "check the segmentation" in message)
    assert "correct the input" not in message and str(value) not in r.text
    assert route.provider.calls == []


# ══════════════════════════════════════════════════════════════════════════════════════════════ I17
class _Log:
    def __init__(self, events):
        self.events = events

    def __getattr__(self, level):
        def log(msg, *a, **k):
            self.events.append(("log", level, str(msg), dict(k.get("extra") or {})))
        return log


@pytest.mark.parametrize("enabled", [True, False])
def test_rc066_i17_privacy_passed_is_recorded_only_after_the_checks_ran(monkeypatch, enabled):
    events = []
    real_numbers, real_tripwire = BRS.assert_no_patient_numbers, BRS.assert_prompt_carries_no_identifier

    def numbers(*a, **k):
        events.append(("ran", "patient_numbers"))
        return real_numbers(*a, **k)

    def tripwire(*a, **k):
        events.append(("ran", "identifier_tripwire"))
        return real_tripwire(*a, **k)

    monkeypatch.setattr(BRS, "assert_no_patient_numbers", numbers)
    monkeypatch.setattr(BRS, "assert_prompt_carries_no_identifier", tripwire)
    monkeypatch.setattr(BRS, "logger", _Log(events))
    bad = []
    for c in I7_CASES:
        events.clear()
        client = _Client()
        _generate(_service(client, enabled=enabled), c)
        ran = set()
        for e in events:
            if e[0] == "ran":
                ran.add(e[1])
            elif e[3].get("privacy_check") == "passed" and ran != {"patient_numbers", "identifier_tripwire"}:
                bad.append((c, f"'passed' recorded after {sorted(ran)} ({len(client.calls)} calls)"))
                break
    assert not bad, f"I17 (comments {'on' if enabled else 'off'}): {len(bad)} of {len(I7_CASES)}; first: {bad[:2]}"


def test_rc104_i17_a_model_call_cancelled_in_flight_still_writes_the_verification_record(sink):
    client = _Client()

    def cancelled(**kw):
        client.calls.append(kw)
        raise asyncio.CancelledError()

    client.create = cancelled
    with pytest.raises(asyncio.CancelledError):
        _generate(_service(client, enabled=True), LESION_CASE,
                  audit_actor=SimpleNamespace(id="reader-i17", username="reader-i17", role="radiologist"))
    attempts = [x for x in sink.memory_records if x["event_type"] == "clinical.ai_report.attempt"]
    outcomes = [x for x in sink.memory_records if x["event_type"] == "clinical.ai_report.verification"]
    assert len(client.calls) == 1
    assert len(outcomes) == 1, "a paid call without its verification record"
    assert outcomes[0]["details"]["attempts"] == 1 and len(attempts) == 1, outcomes[0]["details"]


# ══════════════════════════════════════════════════════════════════════════════════════════════ I18
def _timed_client(clock, seconds, text=FAILING, fail_on=None):
    client = _Client()

    def create(**kw):
        client.calls.append(kw)
        clock.t += seconds
        if fail_on is not None and len(client.calls) == fail_on:
            raise type("APITimeoutError", (Exception,), {})("request timed out")
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn",
                               model="claude-sonnet-5-5", usage=SimpleNamespace(input_tokens=2, output_tokens=2))

    client.create = create
    return client


@pytest.mark.parametrize("seconds", [0.5, 5.0, 10.0, 15.0, 19.9, 20.5, 22.0, 24.0])
def test_rc106_i18_no_request_with_less_than_the_minimum_budget_retries_included(monkeypatch, seconds):
    clock = SimpleNamespace(t=1000.0)
    monkeypatch.setattr(VR, "now", lambda: clock.t)
    client = _timed_client(clock, seconds)
    findings, volumetry = _request(LESION_CASE)
    result = _run(_service(client, enabled=True).generate_report(
        template_type="general", findings=findings, volumetry=volumetry, language="en", identifiers=IDS,
        request_started=clock.t))
    timeouts = [round(call["timeout"], 3) for call in client.calls]
    assert client.calls and all(t >= VR.MIN_LLM_BUDGET_S - 1e-6 for t in timeouts), timeouts
    v = result["verification"]
    assert (v["reason"], v["interpretive_text"]) == (VR.REASON_BLOCKED, "withheld"), (v, timeouts)


def test_rc106_i18_a_retry_cut_by_the_time_budget_is_a_failed_check_not_a_timeout(monkeypatch):
    clock = SimpleNamespace(t=1000.0)
    monkeypatch.setattr(VR, "now", lambda: clock.t)
    client = _timed_client(clock, 1.0, fail_on=2)
    findings, volumetry = _request(LESION_CASE)
    result = _run(_service(client, enabled=True).generate_report(
        template_type="general", findings=findings, volumetry=volumetry, language="en", identifiers=IDS,
        request_started=clock.t))
    v = result["verification"]
    assert len(client.calls) == 2 and (v["reason"], v["interpretive_text"]) == (VR.REASON_BLOCKED, "withheld"), v


# ══════════════════════════════════════════════════════════════════════════════════════════════ I19
def test_capa008_i19_nothing_to_report_is_decided_after_the_routes_substitutions(route):
    r = _post(route, {"longitudinal": {"reader_confirmed_activity": True}})
    assert (r.status_code, _error(r).get("code")) == (422, "nothing_to_report"), r.text[:300]
    assert route.provider.calls == []


# ══════════════════════════════════════════════════════════════════════════════════════════════ findings
def test_rc065_finding5_a_measurement_equal_to_a_patient_number_gives_a_measurements_only_draft():
    """A projected number equal to one of the patient's numbers (here 198011, a form of the birth date 1980-01-01):
    nothing is sent and the clinician still gets the measurements, with the privacy reason — never a 503."""
    client = _Client()
    findings = {"lesion_analysis": {"total_count": 7, "total_burden_mm3": 198011.0, "total_burden_ml": 198.011,
                                    "size_distribution": {"small": 4, "medium": 2, "large": 1}},
                "dis_assessment": {"evaluation_status": "not_evaluated"}}
    result = _run(_service(client, enabled=True).generate_report(
        template_type="general", findings=findings, volumetry=None, language="en", identifiers=IDS))
    v = result["verification"]
    assert client.calls == [] and v["reason"] == "identifier_check" and v["interpretive_text"] == "not_requested", v
    assert "Lesions marked: 7" in result["content"]


def test_rc061_finding7_a_transient_read_error_does_not_retire_the_rate(monkeypatch):
    from app.services import longitudinal_candidate_safety as lcs
    for f in (getattr(lcs, "_read_evidence_asset", None), lcs.load_false_candidate_evidence):
        getattr(f, "cache_clear", lambda: None)()
    real, calls = lcs.json.loads, []

    def flaky(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("transient read error")
        return real(*a, **k)

    monkeypatch.setattr(lcs.json, "loads", flaky)
    assert lcs.load_false_candidate_evidence() is None
    assert lcs.load_false_candidate_evidence() is not None, "a failed read was cached until restart"


def test_rc106_finding8_the_budget_is_computed_once():
    src = inspect.getsource(BRS.BrainReportService.generate_report)
    assert src.count("verified_report.now() - started") == 1, "the time left is computed more than once"


def test_rc065_finding9_one_patient_number_rule():
    src = inspect.getsource(G)
    assert src.count("str(abs(int(") == 1, "the patient-number rule is written more than once"
    assert "is_patient_number(" in inspect.getsource(G._Projector.number)
    assert "is_patient_number(" in inspect.getsource(G.assert_no_patient_numbers)
