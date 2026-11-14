"""Sixteenth review of PR #81 — failing-first through the REAL lower layers; invariants and matrices before point
fixes; deletion before new mechanism.
R1 authorization precedes ANY answer, audit or gate record of the gate route (flag x agent state x caller, the real
   CAPA-009 check); R2 a decision is bound to its patient (token patient x report patient x pair-file owner x user,
   through the real report route and the stored records); R4 every device-written word of the gate's report text is
   exempt from RC-065 — generated from the reason registry — and no patient named after one of them is refused; R6 an
   unusable vox_offset is an unreadable header at once (one read); R7 the stored records are read once per file
   version; R8 one channel and one rule for the audit confirmation. (R3: BrowserFlamesCard.model.test.tsx, P10. R5:
   test_rc122_flags_off_identity.py.) DRAFT, PENDING owner approval."""
import asyncio
import gzip
import inspect
import json
import struct
from types import SimpleNamespace

import nibabel as nib
import numpy as np
import pytest
from fastapi.testclient import TestClient

import app.api.routes.segmentation_analysis as sa
from app.agent_platform import registry as R
from app.core import container
from app.core.logging import audit as A
from app.core.logging import audit_middleware as M
from app.core.logging import audit_sink as S
from app.main import app
from app.security import get_current_active_user
from app.services import longitudinal_candidate_safety as lcs
from app.services import quality_gate as qg
from tests.unit import test_capa009_object_authorization_everywhere as C9
from tests.unit.test_rc122_quality_gate_wiring import REGISTRY, _Storage
from tests.unit.test_rc122_quality_gate_wiring import single  # noqa: F401 — fixture

pytestmark = pytest.mark.unit
GATE_URL = "/api/v1/clinical/quality-gate"
GATE_EVENTS = {A.AuditEventType.QUALITY_GATE_CONSULTATION, A.AuditEventType.CLINICAL_AI_RUN}


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _platform(state, audit=R.default_audit_sink):
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if state == "unknown":
        del data["agents"]["quality-gate"]
    elif state in ("approved", "killed"):
        data["agents"]["quality-gate"]["approval"]["status"] = "approved"     # IN MEMORY, for the test only
    return R.AgentRegistry(data, switches=R.InMemoryKillSwitches({"quality-gate": state != "killed"}), audit=audit)


# ============================================================================= R1: authorization first, always
CALLERS = {"authorized": [C9.PATIENT], "other_patients_file": [C9.OTHER], "no_access": []}
REFUSAL = {"refused": ["gate_not_approved"], "killed": ["gate_switched_off"]}


@pytest.mark.parametrize("flag", [False, True])
@pytest.mark.parametrize("platform", ["approved", "refused", "killed", "unknown"])
@pytest.mark.parametrize("caller", sorted(CALLERS))
def test_rc126_r1_authorization_precedes_any_answer_or_record_of_the_gate(monkeypatch, flag, platform, caller):
    keys = C9._wire(monkeypatch, entitled=CALLERS[caller])
    img = nib.Nifti1Image(np.zeros((8, 8, 6), np.float32), np.diag([1.0, 1.0, 5.0, 1.0]))
    storage = _Storage(img.to_bytes())
    app.dependency_overrides[container.get_storage_service] = lambda: storage
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", flag)
    monkeypatch.setattr(qg, "_REGISTRY", _platform(platform))
    monkeypatch.setattr(qg, "_LIMITER", None)
    monkeypatch.setenv("QUALITY_GATE_RUN_TOKEN_STORE", "memory")
    monkeypatch.setattr(qg, "_RUN_TOKEN_MEMORY", None)
    monkeypatch.setattr(qg, "_HEADER_CACHE", type(qg._HEADER_CACHE)())
    monkeypatch.setattr(qg, "_RECORDS_CACHE", type(qg._HEADER_CACHE)(), raising=False)   # R7: per test
    monkeypatch.setattr(lcs, "read_source_acquisition", lambda fid, svc=None: None)
    monkeypatch.setattr(qg, "read_source_series_description", lambda fid, svc=None: None)
    events = []
    monkeypatch.setattr(A.AuditLogger, "log_event", lambda self, event, durable=True: events.append(event) or A.AuditWrite(True, None, False))
    try:
        client = TestClient(app, raise_server_exceptions=False)
        r = client.post(GATE_URL, json={"file_id": C9.FILE})
        denial = client.post("/api/v1/clinical/skull-strip", json={"file_id": C9.FILE})   # CAPA-009's own 404
    finally:
        for k in keys + [container.get_storage_service]:
            app.dependency_overrides.pop(k, None)
    gate_records = [e for e in events if e.source == "explicit" and e.event_type in GATE_EVENTS]
    where = (flag, platform, caller, r.status_code, r.text[:200])
    if not flag:                                  # flags off: the base — no gate route, for every caller
        assert r.status_code == 404 and "decision" not in r.text and gate_records == [], where
        return
    if caller != "authorized":                    # the SAME CAPA-009 404 as base, no gate answer, no gate record
        assert r.status_code == 404 and denial.status_code == 404, where
        assert r.json() == denial.json(), where
        assert "decision" not in r.text and gate_records == [], where
        return
    body = r.json()
    assert r.status_code == 200 and body["subject"]["file_id"] == C9.FILE and len(gate_records) == 1, where
    if platform in REFUSAL:
        assert body["codes"] == REFUSAL[platform], where
    if platform != "approved":
        assert body["ai_may_run"] is False and all(c.startswith("gate_") for c in body["codes"]), where


def test_rc126_r1_a_refusal_still_downloads_and_reads_nothing_after_authorizing(monkeypatch):
    """What stays of the second review's finding 1: after authorizing the caller, a refusal downloads no image and
    reads no stored record."""
    keys = C9._wire(monkeypatch, entitled=[C9.PATIENT])
    from tests.unit.test_rc122_quality_gate_wiring import _CountingStorage
    storage = _CountingStorage(b"x")
    app.dependency_overrides[container.get_storage_service] = lambda: storage
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", True)
    monkeypatch.setattr(qg, "_REGISTRY", _platform("refused", audit=lambda e: None))
    monkeypatch.setattr(qg, "_LIMITER", None)
    reads = []
    monkeypatch.setattr(lcs, "read_source_acquisition", lambda fid, svc=None: reads.append(fid))
    try:
        body = TestClient(app, raise_server_exceptions=False).post(GATE_URL, json={"file_id": C9.FILE}).json()
    finally:
        for k in keys + [container.get_storage_service]:
            app.dependency_overrides.pop(k, None)
    assert body["codes"] == ["gate_not_approved"] and storage.downloads == 0 and reads == []


# ============================================================================= R2: a decision bound to its patient
PA, PB = C9.PATIENT, C9.OTHER
DR, COLLEAGUE = "id-dr_rev", "id-colleague"
WARNED = {"sequence": "FLAIR", "physician_confirmed_flair": False, "skull": "stripped",
          "scanner": {"manufacturer": "SIEMENS", "manufacturer_model_name": "Prisma", "magnetic_field_strength_t": 3.0},
          "thickness": {"state": "not_determinable", "effective_mm": None}}            # thickness_unknown: a warning
COUNTS = {"burden_tp1_ml": 1.0, "burden_tp2_ml": 1.5, "total_lesions_tp1": 3, "total_lesions_tp2": 4,
          "status_counts": {"new": 1, "enlarged": 0, "resolved": 0, "shrunk": 0, "stable": 3},
          "change_candidates": {"new": 1, "enlarging": 0, "total": 1}}   # the reviewable ones (PR #78)


def _file(patient, study, name):
    return f"patients/{patient}/studies/{study}/series/se-1/{name}.nii.gz"


def _pair(patient):
    return {"tp1": {"id": "seg-1", "source": _file(patient, "st-1", "a"), "version": "10:v1:2026-11-12"},
            "tp2": {"id": "seg-2", "source": _file(patient, "st-2", "b"), "version": "11:v1:2026-11-12"}}


class _Segs:
    def __init__(self, files):
        self.files = files

    async def get_metadata(self, sid):
        return SimpleNamespace(file_id=self.files[sid]) if sid in self.files else None


class _Patients:
    async def get_patient(self, pid, **kw):
        return SimpleNamespace(id=pid, mrn="MRN-2025-0042", given_name="Quenby", middle_name=None,
                               family_name="Zarathustra", birth_date="1978-03-15", created_by="someone-else")


class _CareTeam:
    def list_entitlements_for_user(self, uid):
        from app.security.patient_access import CareTeamAssignment
        return [CareTeamAssignment(patient_id=p, user_id=uid, role_in_care="attending", revoked_at=None) for p in (PA, PB)]


def _report(monkeypatch, *, token_patient, report_patient, owner, user):
    """The REAL report route with the stored records of the report's segmentation and of the pair's segmentations
    (the segmentation store), the real CAPA-009 / RC-029 authorization; the model provider faked."""
    import app.api.routes.ai_report as ai_report
    import app.security.resource_access as ra
    from app.services.brain_report_service import BrainReportService
    from tests.unit.test_capa014_report_provider_payload import _Provider
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", True)
    monkeypatch.setattr(qg, "_REGISTRY", _platform("approved", audit=lambda e: None))
    gate = qg.run_quality_gate({"mode": "comparison", "visits": [dict(WARNED), dict(WARNED)], "rc062_withholds": False},
                               study_key="s", releases_output=False)
    pair = _pair(token_patient)
    lng = {**COUNTS, "pair": pair, "quality_gate": {**gate, "token": qg.decision_token(gate, pair, DR)}}
    segs = _Segs({"seg-report": _file(report_patient, "st-9", "r"),
                  "seg-1": _file(owner, "st-1", "a"), "seg-2": _file(owner, "st-2", "b")})
    monkeypatch.setattr(ra, "_segmentation_service", lambda: segs)
    monkeypatch.setattr(ra, "_patient_service", lambda: _Patients())
    monkeypatch.setattr(ra, "_care_team_service", lambda: _CareTeam())
    monkeypatch.setattr(ai_report, "_patient_service", lambda: _Patients())
    provider = _Provider()
    # verified report (PR #78): a lesion analysis too, so a draft always has something for the model to comment on;
    # the server's lesion table and DIS state of the report's segmentation, stubbed (the segmentation store is not
    # reached, PRB-002) — the report's patient and the pair's owners stay the stored records' (R2)
    from tests.unit.test_capa014_report_provider_payload import _measurements
    table = _measurements()["lesion_analysis"]

    async def _table(segmentation_id):
        return json.loads(json.dumps(table))

    async def _dis(segmentation_id, user):
        from app.services import dis_review_gate as gate
        return gate.not_evaluated(segmentation_id, None, reason=gate.REASON_NOT_CONFIRMED)
    monkeypatch.setattr(ai_report, "server_lesion_table", _table)
    monkeypatch.setattr(ai_report, "server_dis_assessment", _dis)
    monkeypatch.setattr(BrainReportService, "_get_client", lambda self: provider)
    app.dependency_overrides[get_current_active_user] = lambda: C9._user(uid=user)
    app.dependency_overrides[container.get_segmentation_service] = lambda: segs
    try:
        r = TestClient(app, raise_server_exceptions=False).post("/api/v1/ai/report/generate", json={
            "segmentation_id": "seg-report", "language": "en", "findings": {"lesion_analysis": table, "longitudinal": lng}})
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)
        app.dependency_overrides.pop(container.get_segmentation_service, None)
    assert r.status_code == 200, r.text[:400]
    return r.json()["content"], provider.prompt()


@pytest.mark.parametrize("user", [DR, COLLEAGUE])
@pytest.mark.parametrize("moved", [False, True])
@pytest.mark.parametrize("report_patient", [PA, PB])
@pytest.mark.parametrize("token_patient", [PA, PB])
def test_rc127_r2_a_decision_is_established_only_in_a_report_of_its_own_patient(monkeypatch, token_patient,
                                                                                report_patient, moved, user):
    owner = (PB if token_patient == PA else PA) if moved else token_patient
    content, prompt = _report(monkeypatch, token_patient=token_patient, report_patient=report_patient, owner=owner,
                              user=user)
    established = token_patient == report_patient and owner == token_patient and user == DR
    not_established = qg.reason_sentence("gate_not_established", "en")
    warned = qg.reason_sentence("thickness_unknown", "en")
    where = (token_patient[:4], report_patient[:4], owner[:4], user)
    if established:
        assert warned in content and not_established not in content, where
        # the model's record (verified report, PR #78): the gate's warning, code-written, and the change candidates
        assert warned in prompt and '"candidates":' in prompt, where
    else:   # "comparability not established by the gate", no change result (D-QG-19)
        assert not_established in content and warned not in content, where
        from app.services import verified_report as vr
        assert not_established in prompt and vr.GATE_STOPPED in prompt, where
        assert '"candidates":' not in prompt and '"visit_1":' not in prompt, where


# ============================================================================= R4: the gate's words are the device's
_GUARDED = {**COUNTS, "burden_delta_percent": 50.0}


def _gate_states():
    """Every shape of the longitudinal block the RC-064 projector gives the prompt with the gate on, for every reason
    code of the registry (one at a time and all together): stopped by the gate, withheld by RC-062 with the gate's
    warnings, let through with warnings."""
    codes = sorted(qg.CAVEAT_REASONS)
    states = [{"abstained": True, "abstained_by": "quality_gate", "causes": []}]
    for group in [[c] for c in codes] + [codes]:
        states += [{"abstained": True, "abstained_by": "quality_gate", "causes": group},
                   {"abstained": True, "quality_gate_warnings": group},
                   {**_GUARDED, "quality_gate_warnings": group}]
    return states


def _prompts():
    """What the model receives (verified report, PR #78): the record and the code-written report of each gate state."""
    from app.services import verified_report as vr
    return [(state, language, vr.first_user_message(vr.build_view({"longitudinal": state}, None, language), language))
            for state in _gate_states() for language in ("en", "es", "de")]


def test_rc125_r4_every_word_the_gate_can_put_in_the_prompt_is_exempt():
    from app.services.brain_report_service import fixed_prompt_pairs, fixed_prompt_words
    from app.services.report_payload_guard import words_of
    exempt, pairs = fixed_prompt_words(), fixed_prompt_pairs()
    missing, missing_pairs = set(), set()
    for _state, _language, prompt in _prompts():
        words = [w for w in words_of(prompt) if w.isalpha()]       # the words a name can be (never a number)
        missing |= {w for w in words if w not in exempt}
        missing_pairs |= {p for p in zip(words, words[1:]) if p not in pairs}
    assert not missing and not missing_pairs, (sorted(missing)[:40], sorted(missing_pairs)[:10])


def _identifiers(given, family):
    from app.services.report_payload_guard import PatientIdentifiers
    return PatientIdentifiers.from_record(SimpleNamespace(mrn="MRN-2025-0042", given_name=given, family_name=family,
                                                          birth_date="1978-03-15"))


def test_rc125_r4_no_patient_named_after_a_word_of_the_gate_is_refused_and_real_names_still_are():
    from app.services.brain_report_service import assert_prompt_carries_no_identifier
    from app.services.report_payload_guard import IdentifierInPrompt, words_of
    refused = []
    for state, language, prompt in _prompts():
        tokens = sorted({w for w in words_of(prompt) if len(w) >= 4 and w.isalpha()})
        for token in tokens:
            for given, family in ((token, "Zarathustra"), ("Quenby", token)):
                try:
                    assert_prompt_carries_no_identifier(prompt, _identifiers(given, family))
                except IdentifierInPrompt:
                    refused.append((token, language, sorted(state)[:3]))
    assert not refused, f"{len(refused)} names refused, e.g. {refused[:8]}"
    # the tripwire still catches the patient's own name (and given + family together) in the same prompts
    prompt = _prompts()[0][2]
    for leak in ("Quenby", "Zarathustra", "Quenby Zarathustra"):
        with pytest.raises(IdentifierInPrompt):
            assert_prompt_carries_no_identifier(prompt + f"\nPatient: {leak}", _identifiers("Quenby", "Zarathustra"))


# ============================================================================= R6: an unusable vox_offset
class _Ranged:
    """A storage with real ranged reads, counting them."""

    def __init__(self, data):
        self.data, self.reads = data, 0

    async def download_file_range(self, bucket, path, start, end):
        self.reads += 1
        return self.data[start:end + 1]

    async def get_file_metadata(self, bucket, path):
        from app.core.interfaces.storage_interface import StorageObject
        return StorageObject(bucket=bucket, name=path, size=len(self.data), content_type="application/gzip",
                             checksum_sha256="v1", created_at="2026-11-12")


def _nifti_with_vox(kind, vox):
    """A gzip NIfTI with an extension (so the reader needs vox_offset) and 1.5 MiB of incompressible voxels (so the
    ranged reader could keep reading), its vox_offset overwritten with ``vox``."""
    arr = np.random.default_rng(16).integers(0, 255, size=(128, 128, 96), dtype=np.uint8)
    img = (nib.Nifti2Image if kind == 2 else nib.Nifti1Image)(arr, np.diag([1.0, 1.0, 3.0, 1.0]))
    img.header.extensions.append(nib.nifti1.Nifti1Extension("comment", b"x" * 3000))
    raw = bytearray(img.to_bytes())
    if vox is not None:
        if kind == 1:
            raw[108:112] = struct.pack("<f", vox)
        else:
            raw[168:176] = struct.pack("<q", int(vox))
    return gzip.compress(bytes(raw), compresslevel=1)


@pytest.mark.parametrize("kind, vox", [(1, float("nan")), (1, float("inf")), (1, float("-inf")), (1, -1.0),
                                       (1, 1e12), (2, -352), (2, 2 ** 62)])
def test_rc122_r6_an_unusable_vox_offset_is_an_unreadable_header_at_once(kind, vox):
    storage = _Ranged(_nifti_with_vox(kind, vox))
    fields = _run(qg.visit_header_fields(storage, "b", "patients/p/studies/s/series/x/v.nii.gz", version_key=None))
    assert fields.get("unreadable") is True, (kind, vox, fields)
    assert storage.reads == 1, f"vox_offset {vox}: {storage.reads} ranged reads (never re-read up to 4 MiB)"
    assert qg.visit_inputs(fields, None, None)["header"] == "unreadable"         # the gate's code: header_unreadable


@pytest.mark.parametrize("kind", [1, 2])
def test_rc122_r6_a_valid_vox_offset_is_read(kind):
    storage = _Ranged(_nifti_with_vox(kind, None))
    fields = _run(qg.visit_header_fields(storage, "b", "patients/p/studies/s/series/x/v.nii.gz", version_key=None))
    assert not fields.get("unreadable"), fields


def test_rc122_r6_the_gate_reads_vox_offset_through_the_one_reader():
    src = inspect.getsource(qg._inspect_header_prefix)
    assert "struct.unpack" not in src and "nifti_header.vox_offset(" in src


# ============================================================================= R7: stored records once per version
def test_rc122_r7_consultations_of_one_version_read_the_stored_records_once(single, monkeypatch):
    client, _ = single
    monkeypatch.setattr(qg, "_REGISTRY", _platform("approved", audit=lambda e: None))
    reads = []
    monkeypatch.setattr(lcs, "read_source_acquisition", lambda fid, svc=None: reads.append(("acq", fid)) or {
        "manufacturer": "SIEMENS", "slice_thickness_mm": 1.0})
    monkeypatch.setattr(qg, "read_source_series_description", lambda fid, svc=None: reads.append(("desc", fid)) or "AX T2 FLAIR")
    for _ in range(5):
        assert client.post(GATE_URL, json={"file_id": "f"}).status_code == 200
    assert len([r for r in reads if r[0] == "acq"]) == 1 and len([r for r in reads if r[0] == "desc"]) == 1, reads
    img = nib.Nifti1Image(np.zeros((8, 8, 7), np.float32), np.diag([1.0, 1.0, 5.0, 1.0]))   # a new version
    app.dependency_overrides[container.get_storage_service] = lambda: _Storage(img.to_bytes())
    assert client.post(GATE_URL, json={"file_id": "f"}).status_code == 200
    assert len([r for r in reads if r[0] == "acq"]) == 2, "a new version reads its records again"
    now = qg._now()
    monkeypatch.setattr(qg, "_now", lambda: now + qg.RECORDS_CACHE_TTL_S + 1)
    assert client.post(GATE_URL, json={"file_id": "f"}).status_code == 200
    assert len([r for r in reads if r[0] == "acq"]) == 3, "after the TTL the records are read again"


def test_rc122_r7_an_incomplete_answer_is_never_remembered(single, monkeypatch):
    client, _ = single
    monkeypatch.setattr(qg, "_REGISTRY", _platform("approved", audit=lambda e: None))
    reads = []
    monkeypatch.setattr(lcs, "read_source_acquisition", lambda fid, svc=None: reads.append(fid))     # None: unknown
    for _ in range(3):
        assert client.post(GATE_URL, json={"file_id": "f"}).status_code == 200
    assert len(reads) == 3


# ============================================================================= R8: one channel, one rule
def test_rc126_r8_one_channel_and_one_rule_for_the_audit_confirmation():
    assert not hasattr(M, "_durable_backend"), "one rule: AuditWrite.expected"
    assert "audit_writes" not in inspect.getsource(M) and "audit_writes" not in inspect.getsource(R), \
        "one channel: RequestAuditContext.explicit_writes"


def test_rc126_r8_a_rate_limited_consultation_is_still_recorded_by_the_middleware(single, monkeypatch):
    """K3: a request the gate did not record itself (here a 429, whose only explicit record is the limiter's) is
    recorded by the middleware — also with ONE channel."""
    client, _ = single
    monkeypatch.setattr(qg, "_REGISTRY", _platform("approved"))
    monkeypatch.setattr(qg, "RATE_LIMIT_PER_MINUTE", 1)
    monkeypatch.setattr(qg, "_LIMITER", qg.new_rate_limiter())
    sink = S.DurableAuditSink(None, backend="memory")
    previous = S.set_durable_audit_sink(sink)
    A.reset_audit_budget()
    try:
        assert client.post(GATE_URL, json={"file_id": "f"}).status_code == 200
        assert client.post(GATE_URL, json={"file_id": "f"}).status_code == 429
    finally:
        S.set_durable_audit_sink(previous)
    rows = [r for r in sink.memory_records if r.get("endpoint") == GATE_URL]
    limited = [r for r in rows if r.get("status_code") == 429]
    assert [r.get("source") for r in limited] == ["middleware"], rows
