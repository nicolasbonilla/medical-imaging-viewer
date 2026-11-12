"""Eighth review of PR #81: truthful reasons from one source (G30), an audit that reflects what the user received and
loses nothing (G31), an attestation only when the end-to-end result would change (G32), an explicit "gate not
enabled" code (U1), one ranged header reader (E1) and shared stored-record reads (E2). DRAFT, PENDING owner approval."""
import asyncio
import inspect
import threading
import time

import pytest
from fastapi.testclient import TestClient

import app.api.routes.segmentation_analysis as sa
from app.agent_platform import registry as R
from app.services import longitudinal_candidate_safety as lcs
from app.services import quality_gate as qg
from tests.unit.test_quality_gate_matrix import PLATFORM_ON, build_cases
from tests.unit.test_rc122_quality_gate_wiring import (  # noqa: F401 — fixtures
    ACQ, FILE, PAIR, URL, _registry, compare, single,
)


def _comparisons(platform=PLATFORM_ON):
    for key, _, inp in build_cases(platform=platform):
        if inp["mode"] == "comparison":
            yield key, {**inp, "visits": [{**v, "physician_confirmed_flair": False} for v in inp["visits"]]}


def _record(visit):
    s = visit.get("scanner")
    return None if not s else {**ACQ, **{k: v for k, v in s.items() if v is not None}}


def _predicted_rc062(inp):
    a, b = (_record(v) for v in inp["visits"])
    return lcs.rc062_withholds(lcs.compare_acquisitions(a, b, (1.0, 1.0, 3.0), (1.0, 1.0, 3.0)), {"status": "ok"})


# ----------------------------------------------------------------------------- G30
def test_rc127_g30_the_stated_causes_are_exactly_the_checks_that_abstained():
    bad = []
    for key, inp in _comparisons():
        gate = qg.evaluate(inp)
        account = qg.explain(gate)
        abstained = [c["code"] for c in gate["checks"] if c["status"] == "abstain"]
        warned = [c["code"] for c in gate["checks"] if c["status"] == "warn"]
        if sorted(set(account["causes"])) != sorted(set(abstained)) or set(account["warnings"]) != set(warned):
            bad.append((key, "account"))
        if gate["ai_output_allowed"] is not True:
            caveat = qg.gate_caveat(gate)
            notice_codes = set(account["causes"])
            if any(qg.reason_sentence(w) in caveat for w in warned if w not in notice_codes):
                bad.append((key, "a warning given as a cause"))
            if "sequence_confirmed_by_physician" in account["causes"]:
                bad.append((key, "an attestation given as a cause"))
    assert not bad, f"G30: {len(bad)} untruthful accounts; first: {bad[:4]}"


def test_rc127_g30_reviewer_case_thickness_thick_is_never_a_cause():
    gate = qg.evaluate({"mode": "comparison", "platform": PLATFORM_ON, "visits": [
        {"sequence": "FLAIR", "physician_confirmed_flair": False, "thickness": {"state": "native", "effective_mm": 5.0},
         "scanner": {"manufacturer": "SIEMENS", "manufacturer_model_name": "Prisma", "magnetic_field_strength_t": 3.0}, "skull": "unknown"},
        {"sequence": "T1", "physician_confirmed_flair": False, "thickness": {"state": "native", "effective_mm": 5.0},
         "scanner": {"manufacturer": "SIEMENS", "manufacturer_model_name": "Prisma", "magnetic_field_strength_t": 3.0}, "skull": "unknown"}]})
    caveat = qg.gate_caveat(gate)
    assert qg.reason_sentence("sequence_not_flair") in caveat
    assert qg.reason_sentence("thickness_thick") not in caveat.split("Warnings:")[0]


@pytest.mark.parametrize("lang", ["en", "es", "de"])
def test_rc127_g30_reviewer_case_the_report_model_and_the_notice_give_the_same_cause(lang, monkeypatch):
    """A gate stop reaches the report model as the gate's causes — never as 'acquisition not comparable'."""
    from app.api.routes.ai_report import LONGITUDINAL_NOTICE, longitudinal_notice
    from app.services.brain_report_service import BrainReportService
    from app.services.report_payload_guard import _Projector
    gate = qg.evaluate({"mode": "comparison", "platform": PLATFORM_ON, "visits": [
        {"sequence": "FLAIR", "physician_confirmed_flair": False, "thickness": None, "scanner": None, "skull": "unknown"},
        {"sequence": "T1", "physician_confirmed_flair": False, "thickness": None, "scanner": None, "skull": "unknown"}]})
    from tests.unit.test_rc122_review11 import served           # I1 (eleventh review): the server's record
    lng = qg.abstained_comparison(served(gate, monkeypatch))
    guarded = _Projector().longitudinal(lng)
    assert guarded.get("abstained_by") == "quality_gate" and guarded.get("causes") == ["sequence_not_flair"]
    prompt = BrainReportService()._build_findings_prompt({"longitudinal": guarded}, language=lang)
    assert "could not be established as comparable" not in prompt
    assert qg.reason_sentence("sequence_not_flair") in prompt
    notice = longitudinal_notice(lng, lang)
    assert LONGITUDINAL_NOTICE[lang]["abstained"] not in notice
    assert qg.reason_sentence("sequence_not_flair", lang) in notice
    assert qg.reason_sentence("scanner_not_recorded", lang) not in notice.split(qg.reason_lead("warned", lang))[0]


def test_rc127_g30_rc062_s_reason_only_when_rc062_withheld(monkeypatch):
    from app.api.routes.ai_report import LONGITUDINAL_NOTICE, longitudinal_notice
    from tests.unit.test_rc122_review11 import served           # I1 (eleventh review): the server's record
    warned = qg.evaluate({"mode": "comparison", "platform": PLATFORM_ON, "visits": [
        {"sequence": "FLAIR", "physician_confirmed_flair": False, "thickness": None, "scanner": None, "skull": "unknown"},
        {"sequence": "FLAIR", "physician_confirmed_flair": False, "thickness": None, "scanner": None, "skull": "unknown"}]})
    assert warned["ai_output_allowed"] is True
    rc062 = qg.apply_to_comparison(lcs.present_comparison({"changes": []}, acquisition_check={"status": "not_established",
                                   "missing": [], "differing": []}, evidence=None, binding=None, stored_review=None,
                                   visit_check={"status": "ok"}), served(warned, monkeypatch))
    notice = longitudinal_notice(rc062, "en")
    assert LONGITUDINAL_NOTICE["en"]["abstained"] in notice
    assert qg.reason_sentence("scanner_not_recorded") in notice            # a warning, stated as a warning
    stopped = longitudinal_notice(qg.abstained_comparison(served({**warned, "ai_output_allowed": False, "decision": "abstain",
        "codes": ["scanner_changed"], "checks": [{"check": "scanner", "visit": None, "status": "abstain",
                                                  "code": "scanner_changed", "params": {}}]}, monkeypatch)), "en")
    assert LONGITUDINAL_NOTICE["en"]["abstained"] not in stopped


# ----------------------------------------------------------------------------- G31
def test_rc126_g31_a_comparison_rc062_withholds_is_recorded_as_withheld_never_released(compare, monkeypatch):
    client, records, (f1, f2) = compare
    events = []
    reg = _registry()
    reg._audit = events.append
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", True)
    monkeypatch.setattr(qg, "_REGISTRY", reg)
    records["acq"][f2]["mr_acquisition_type"] = "2D"                      # the gate passes; RC-062 withholds
    res = client.post("/api/v1/segmentation/longitudinal/compare", json=PAIR).json()
    assert res["quality_gate"]["ai_output_allowed"] is True and res["abstained"] is True
    assert not [e for e in events if e.get("event") == "agent.run"], events
    assert any((e.get("details") or {}).get("withheld_by") == "rc062" for e in events), events


def test_rc126_g31_the_audit_keeps_every_attested_visit_in_structured_fields():
    events = []
    reg = _registry()
    reg._audit = events.append
    visit = {"header": "unreadable", "sequence": "missing", "physician_confirmed_flair": True, "thickness": None,
             "scanner": None, "skull": "unknown"}
    qg.run_quality_gate({"mode": "comparison", "visits": [visit, dict(visit)]}, registry=reg,
                        study_key="patients/p/studies/a-very-long-study-identifier-0000000000000000")
    details = events[-1].get("details") or {}
    assert details.get("attested_visits") == ["tp1", "tp2"] and details.get("causes") == ["header_unreadable"]
    assert details.get("decision") == "abstain"
    emitted = []
    import app.core.logging.audit as A
    original = A.emit_audit
    try:
        A.emit_audit = lambda event_type, outcome, **k: emitted.append(k.get("details"))
        R.default_audit_sink(events[-1])
    finally:
        A.emit_audit = original
    assert emitted and emitted[0].get("attested_visits") == ["tp1", "tp2"]


# ----------------------------------------------------------------------------- G32
def test_rc122_g32_an_attestation_only_when_the_end_to_end_result_would_change():
    bad, offered = [], 0
    for key, inp in _comparisons():
        for variant in ("as is", "no scanner record in either visit"):
            case = inp if variant == "as is" else {**inp, "visits": [{**v, "scanner": None} for v in inp["visits"]]}
            rc062 = _predicted_rc062(case)
            out = qg.evaluate({**case, "rc062_withholds": rc062})
            visits = out["attestable_visits"]
            if not visits:
                continue
            offered += 1
            attested = {**case, "rc062_withholds": rc062, "visits": [
                {**v, "physician_confirmed_flair": True} if label in visits else v for label, v in zip(("tp1", "tp2"), case["visits"])]}
            if rc062 or qg.evaluate(attested)["decision"] == "abstain" or variant != "as is":
                bad.append((key, variant))
    assert not bad, f"G32: a futile attestation offered in {len(bad)} cases; first: {bad[:4]}"
    assert offered > 0


def test_rc122_g32_rc062_s_own_fields_decide_too():
    """RC-062 withholds on fields the gate does not check (2D / 3D, slice thickness, an unknown visit order): the
    scanner check passes, yet no attestation may be offered."""
    scanner = {"manufacturer": "SIEMENS", "manufacturer_model_name": "Prisma", "magnetic_field_strength_t": 3.0}
    visit = {"sequence": "unknown", "physician_confirmed_flair": False, "thickness": None, "scanner": scanner, "skull": "unknown"}
    a, b = {**ACQ}, {**ACQ, "mr_acquisition_type": "2D" if ACQ["mr_acquisition_type"] != "2D" else "3D"}
    rc062 = lcs.rc062_withholds(lcs.compare_acquisitions(a, b, (1.0, 1.0, 3.0), (1.0, 1.0, 3.0)), {"status": "ok"})
    assert rc062 is True
    gate = {"mode": "comparison", "platform": PLATFORM_ON, "visits": [visit, dict(visit)]}
    assert qg.evaluate({**gate, "rc062_withholds": rc062})["attestable_visits"] == []
    assert qg.evaluate({**gate, "rc062_withholds": False})["attestable_visits"] == ["tp1", "tp2"]


# ----------------------------------------------------------------------------- U1
def test_rc126_u1_the_server_says_explicitly_that_the_gate_is_not_enabled(single, monkeypatch):
    client, _ = single
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", False)
    r = client.post(URL, json={"file_id": FILE})
    assert r.status_code == 404 and r.headers.get("X-Quality-Gate-Code") == "gate_not_enabled"
    assert "X-Quality-Gate-Code" in r.headers.get("Access-Control-Expose-Headers", "")


# ----------------------------------------------------------------------------- E1, E2
def test_rc122_e1_one_ranged_header_reader_and_one_decompression_per_round(single, monkeypatch):
    import gzip
    import nibabel as nib
    import numpy as np
    from app.services import displayed_image_check as dic
    assert "read_header_prefix(" in inspect.getsource(qg._read_header_fields)
    assert "read_header_prefix(" in inspect.getsource(dic._header_bytes)
    data = gzip.compress(nib.Nifti1Image(np.zeros((8, 8, 6), np.float32), np.eye(4)).to_bytes())
    calls = []
    original = qg._nifti_prefix
    monkeypatch.setattr(qg, "_nifti_prefix", lambda d: calls.append(1) or original(d))

    class _Ranged:
        async def download_file_range(self, bucket, path, start, end):
            return data[start:end + 1]

        async def download_file(self, bucket, path):
            return data

    fields = asyncio.new_event_loop().run_until_complete(qg._read_header_fields(_Ranged(), "b", "x.nii.gz"))
    assert fields["thickness"] is not None and len(calls) == 1, calls


def test_rc123_e2_the_stored_records_of_both_visits_are_read_concurrently(compare, monkeypatch):
    client, records, _ = compare
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", True)
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    state = {"active": 0, "max": 0, "calls": 0}
    lock = threading.Lock()

    def _slow(fid, svc=None):
        with lock:
            state["active"] += 1
            state["calls"] += 1
            state["max"] = max(state["max"], state["active"])
        time.sleep(0.1)
        with lock:
            state["active"] -= 1
        return records["desc"].get(fid)

    monkeypatch.setattr(qg, "read_source_series_description", _slow)
    assert client.post("/api/v1/segmentation/longitudinal/compare", json=PAIR).status_code == 200
    assert state["max"] == 2 and state["calls"] == 2, state
    assert "records" in inspect.signature(qg.comparison_gate).parameters
