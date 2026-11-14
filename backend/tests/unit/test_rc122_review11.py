"""Eleventh review of PR #81: the report trusts only the server's record of the gate (I1), the gate's account is type-safe
on any input (I2), the inventory keeps sequence punctuation in file names (I3), the comparison panel and the report
notice give the same warnings (I4, server side), one audit record per consultation (I5), and one place for the voxel
spacing and the visit check. DRAFT, PENDING owner approval."""
import inspect
import json
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

import app.api.routes.segmentation_analysis as sa
from app.agent_platform import registry as R
from app.core.container import get_storage_service
from app.main import app
from app.services import quality_gate as qg
from tests.unit.test_capa014_report_provider_payload import _measurements, _post, route  # noqa: F401 — fixture
from tests.unit.test_rc122_quality_gate_wiring import (  # noqa: F401 — fixtures
    FILE, REGISTRY, URL, _CountingStorage, _registry, single,
)

ROOT = Path(__file__).resolve().parents[3]
SCANNER = {"manufacturer": "SIEMENS", "manufacturer_model_name": "Prisma", "magnetic_field_strength_t": 3.0}
WARNED = {"sequence": "FLAIR", "physician_confirmed_flair": False, "scanner": SCANNER, "skull": "stripped",
          "thickness": {"state": "not_determinable", "effective_mm": None}}          # thickness_unknown: a warning
COUNTS = {"burden_tp1_ml": 1.0, "burden_tp2_ml": 1.5, "total_lesions_tp1": 3, "total_lesions_tp2": 4,
          "status_counts": {"new": 1, "enlarged": 0, "resolved": 0, "shrunk": 0, "stable": 3}}


TEST_PATIENT = "11111111-1111-1111-1111-111111111111"
# R2 (sixteenth review): a pair's source files are its patient's (the decision is bound to that patient)
TEST_PAIR = {"tp1": {"id": "s1", "source": f"patients/{TEST_PATIENT}/studies/st-1/series/se-1/1.nii.gz", "version": None},
             "tp2": {"id": "s2", "source": f"patients/{TEST_PATIENT}/studies/st-2/series/se-1/2.nii.gz", "version": None}}
TEST_USER = "reader-14"            # the clinician who compared AND requests the report (M3: the decision is bound to them)
TEST_SUBJECT = {"patient": TEST_PATIENT, "owners": [TEST_PATIENT, TEST_PATIENT]}   # R2: the stored records agree


def account(lng, user=TEST_USER):
    """The report route's ONE account of the gate (R2, sixteenth review): for this clinician and the test patient, whose
    stored records own the pair."""
    return qg.report_account(lng, user, TEST_SUBJECT)


def record_for(lng, language="en", user=TEST_USER):
    """The verified report's measurement record of this longitudinal block (PR #78; PR #81 integrated): the service's
    own steps — the rendered request, the RC-064 projection with the route's one account (R2), the record."""
    from app.services import verified_report as vr
    from app.services.report_payload_guard import project_measurements
    findings, volumetry, _ = vr.rendered_request({"longitudinal": lng}, None)
    payload = project_measurements(findings, volumetry, gate_account=account(lng, user))
    return vr.build_view(payload.findings, payload.volumetry, vr.language_of(language))


def prompt_for(lng, language="en", user=TEST_USER):
    """What the model receives first: the record and the code-written report (verified_report.first_user_message)."""
    from app.services import verified_report as vr
    return vr.first_user_message(record_for(lng, language, user), vr.language_of(language))


def notice_for(lng, language, user=TEST_USER):
    """The draft's code-written change notice, as the report service writes it from its record and the route's one
    account (R2, G30)."""
    from app.services import verified_report as vr
    from app.services.brain_report_service import report_change_notice
    return report_change_notice(record_for(lng, language, user), vr.language_of(language), account(lng, user))


def projected(lng, user=TEST_USER):
    """The RC-064 projection of the longitudinal block, from the route's one account (R2)."""
    from app.services.report_payload_guard import _Projector
    return _Projector(gate_account=account(lng, user)).longitudinal(lng)


def served(gate, monkeypatch):
    """A gate decision as the SERVER returned it (I1; twelfth review K1/K2): the gate enforced, the decision with its
    SIGNED token for the test pair — what every report test feeds the report path with; the report trusts nothing
    else. The longitudinal block names the same pair (paired)."""
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", True)
    return {**gate, "token": qg.decision_token(gate, TEST_PAIR, TEST_USER)}


def paired(lng):
    """The longitudinal block as the comparison returned it: with the pair its signed decision is bound to (K2)."""
    return {**lng, "pair": TEST_PAIR}


def _decision(visit, monkeypatch):
    """A comparison decision the SERVER made and returned (with its signed token)."""
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    return served(qg.run_quality_gate({"mode": "comparison", "visits": [dict(visit), dict(visit)], "rc062_withholds": False},
                                      study_key="s", releases_output=False), monkeypatch)


def in_context(event, write):
    """What the real log_event does with an explicit record's outcome: it joins the request's audit context — the ONE
    channel the middleware reads (R8, sixteenth review)."""
    from app.core.logging import audit as A
    ctx = A._request_audit.get()
    if ctx is not None and event.source == "explicit":
        ctx.explicit_writes.append(write)
    return write


class _StoredPair:
    """The segmentation store as the report reads it (R2, sixteenth review): the pair's segmentations are the test
    patient's (CAPA-007's resolver reads their source files)."""

    async def get_metadata(self, sid):
        return {"s1": type("M", (), {"file_id": TEST_PAIR["tp1"]["source"]})(),
                "s2": type("M", (), {"file_id": TEST_PAIR["tp2"]["source"]})()}.get(sid)


def _report(route, monkeypatch, lng):
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", True)
    # R2 (sixteenth review): the report's segmentation and the pair's are the test patient's, in the stored records
    import app.api.routes.ai_report as ai_report
    import app.security.resource_access as ra

    async def _authorized(segmentation_id, user):
        return TEST_PATIENT
    monkeypatch.setattr(ai_report, "authorize_segmentation_id", _authorized)
    monkeypatch.setattr(ra, "_segmentation_service", lambda: _StoredPair())
    route.provider.calls.clear()
    r = _post(route, {**_measurements(), "longitudinal": paired(lng)})
    assert r.status_code == 200, r.text
    return route.provider.prompt(), r.json()["content"]          # the model's text and the draft with its notice


# ----------------------------------------------------------------------------- I1
def test_rc127_i1_a_tampered_block_cannot_drop_the_server_s_warnings(route, monkeypatch):
    server = _decision(WARNED, monkeypatch)
    warnings = qg.explain(server)["warnings"]
    assert warnings, server["codes"]
    tampered = {**server, "codes": [], "checks": [], "decision": "proceed"}           # the warnings dropped
    prompt, text = _report(route, monkeypatch, {**COUNTS, "quality_gate": tampered})
    for code in warnings:
        assert qg.reason_sentence(code) in prompt and qg.reason_sentence(code) in text, code


def test_rc127_i1_a_flipped_decision_cannot_turn_a_stop_into_a_clean_comparison(route, monkeypatch):
    server = _decision({**WARNED, "sequence": "T1"}, monkeypatch)                     # the server STOPPED the pair
    assert server["ai_output_allowed"] is False
    flipped = {**server, "decision": "proceed", "ai_may_run": True, "ai_output_allowed": True, "codes": [], "checks": []}
    prompt, text = _report(route, monkeypatch, {**COUNTS, "abstained": False, "quality_gate": flipped})
    assert "New-lesion candidates" not in prompt, "I1: a gate stop was reported as a clean comparison"
    assert qg.reason_sentence("sequence_not_flair") in prompt and qg.reason_sentence("sequence_not_flair") in text


@pytest.mark.parametrize("trace", ["qg1.e30.e30", None, "not-a-token", ["x"]])
def test_rc127_i1_an_unknown_forged_or_missing_trace_is_not_a_gate_decision(route, monkeypatch, trace):
    server = _decision(WARNED, monkeypatch)
    forged = {**server, "token": trace, "codes": [], "checks": [], "decision": "proceed", "ai_output_allowed": True}
    prompt, text = _report(route, monkeypatch, {**COUNTS, "quality_gate": forged})
    assert "New-lesion candidates" not in prompt, "I1: an unverified gate block was reported as a clean comparison"
    note = qg.reason_sentence("gate_not_established")
    assert note in prompt and note in text


# ----------------------------------------------------------------------------- I2
@pytest.mark.parametrize("gate", [
    {"checks": [{"code": ["x"]}]},
    {"checks": [{"code": "thickness_unknown", "status": ["warn"], "visit": {"a": 1}}, 1, None, "x", {"code": {"y": 2}}]},
    {"codes": [["x"], {"y": 1}, "thickness_unknown", 3]},
    {"checks": "not a list", "codes": "nor this"},
    ["a", "list"], None, 7,
])
def test_rc127_i2_the_gate_account_is_type_safe(gate):
    out = qg.explain(gate)
    assert all(isinstance(v, str) for key in ("causes", "warnings", "attested_visits") for v in out[key]), out


@pytest.mark.parametrize("enforced", [False, True])
def test_rc127_i2_a_malformed_gate_block_gives_a_draft_never_a_500(route, monkeypatch, enforced):
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", enforced)
    for lng in ({"abstained": True, "quality_gate": {"checks": [{"code": ["x"]}]}},
                {**COUNTS, "quality_gate": {"checks": [{"code": ["x"], "status": "warn", "visit": ["tp1"]}]}}):
        r = _post(route, {**_measurements(), "longitudinal": lng})
        assert r.status_code == 200, r.text


# ----------------------------------------------------------------------------- I3
def test_rc122_i3_sequence_punctuation_in_a_file_name_is_kept():
    from app.services import dataset_inventory as inv
    assert inv.detect_sequence("", "AX_T2*.nii.gz") == "SWI"
    assert inv.descriptive_name("uploads/x/AX_T2*_7a3f9e21-0c4d-4b1e-9a7f-2b6c1d0e8f11.nii.gz").replace("_", " ").split()[:2] \
        == ["AX", "T2*"]
    assert "+" in inv.descriptive_name("T1+C_00012345.nii") and "-" in inv.descriptive_name("t1-mprage.nii.gz")


def test_rc122_g26_i3_file_names_are_the_base_except_the_identifier_tokens():
    import importlib.util
    from app.services import dataset_inventory as inv
    snap = json.loads((ROOT / "frontend/src/config/qualityGate.flags_off_snapshot.v1.json").read_text(encoding="utf-8"))
    spec = importlib.util.spec_from_file_location("gen", ROOT / "scripts/safety/quality_gate_flags_off_snapshot.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    assert snap["filename_corpus"] == gen.generate_filenames()
    markers = {m for c in snap["filename_corpus"] for m in "*+-" if m in c["file"]}
    assert markers == {"*", "+", "-"}
    bad = [(c["text"], c["file"], inv.detect_sequence(c["text"], c["file"]), base)
           for c, base in zip(snap["filename_corpus"], snap["inventory_filenames"])
           if inv.detect_sequence(c["text"], c["file"]) != base]
    assert not bad, f"I3: {len(bad)} of {len(snap['filename_corpus'])} file names differ from the base; first: {bad[:4]}"


# ----------------------------------------------------------------------------- I4 (the server side of the panel)
def test_rc127_i4_the_shared_fixture_names_the_warnings_the_report_notice_gives():
    states = json.loads((ROOT / "frontend/src/config/qualityGate.ui_states.v1.json").read_text(encoding="utf-8"))["states"]
    governed = [s for s in states if s["expect"].get("governed")]
    assert governed
    for s in states:
        gate = s["result"].get("quality_gate")
        expected = qg.explain(gate)["warnings"] if s["expect"].get("governed") else []
        assert s["expect"].get("warnings") == expected, s["name"]


# ----------------------------------------------------------------------------- I5
def _durable_future():
    """A durable write the store confirmed (K1, fourteenth review: a stubbed logger reports a REAL outcome)."""
    from concurrent.futures import Future
    f = Future()
    f.set_result(True)
    return f


def _records(monkeypatch):
    from app.core.logging import audit as A
    seen = []
    monkeypatch.setattr(A.AuditLogger, "log_event",
                        lambda self, event, durable=True: (seen.append(event.event_type if event.outcome == A.AuditOutcome.SUCCESS
                                                                       else (event.event_type, event.outcome)),
                                                           in_context(event, A.AuditWrite(True, _durable_future())))[1])
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    data["agents"]["quality-gate"]["approval"]["status"] = "approved"     # IN MEMORY, for the test only
    monkeypatch.setattr(qg, "_REGISTRY", R.AgentRegistry(data, switches=R.InMemoryKillSwitches({"quality-gate": True}),
                                                         audit=R.default_audit_sink))
    return A, seen


def test_rc126_i5_one_audit_record_per_consultation(single, monkeypatch):
    client, _ = single
    A, seen = _records(monkeypatch)
    img = nib.Nifti1Image(np.zeros((8, 8, 6), np.float32), np.diag([1.0, 1.0, 1.0, 1.0])).to_bytes()
    app.dependency_overrides[get_storage_service] = (lambda st: (lambda: st))(_CountingStorage(img))
    run = client.post(URL, json={"file_id": FILE, "physician_confirmed_flair": True}).json()     # allows the run (K5)
    seen.clear()
    released = client.post(URL, json={"file_id": FILE, "physician_confirmed_flair": True, "skull": "stripped",
                                      "run_token": run["run_token"]}).json()
    assert released["ai_output_allowed"] is True
    assert seen == [A.AuditEventType.CLINICAL_AI_RUN], seen
    seen.clear()
    client.post(URL, json={"file_id": FILE})
    assert seen == [A.AuditEventType.QUALITY_GATE_CONSULTATION], seen
    seen.clear()
    # twelfth review (K3, which supersedes I5's "no record for a 404"): a request the route did not record — here the
    # gate not enabled — leaves the middleware's own record, as for any route: one, and not a successful consultation
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", False)
    assert client.post(URL, json={"file_id": FILE}).status_code == 404
    assert seen == [(A.AuditEventType.QUALITY_GATE_CONSULTATION, A.AuditOutcome.FAILURE)], seen


# ----------------------------------------------------------------------------- one place
def test_rc123_one_voxel_spacing_helper_and_the_visit_check_in_the_same_gather():
    src = inspect.getsource(sa)
    assert src.count("float(zooms[2])") == 0, "the voxel spacing is computed in one helper (lcs)"
    setup = inspect.getsource(sa._gate_setup)
    # K8 (fourteenth review) supersedes O3's single gather: the cheap visit check FIRST, then the reads
    assert "visit_check = await _visit_check(specs[0]" in setup
