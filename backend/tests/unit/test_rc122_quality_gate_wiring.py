"""Single quality gate — wiring into the routes and input derivation (RC-122, RC-123, RC-125, RC-126).

REQ-FUNC-117, REQ-SAFE-052, REQ-SAFE-054; HAZ-025. DRAFT, PENDING owner approval.
The invariants of the rule itself are closed by test_quality_gate_matrix.py; here: the single-study route
(inputs derived on the server, decision through the platform), the longitudinal routes behind
QUALITY_GATE_ENFORCED (off = unchanged; on = the gate decides, fail closed, stricter than RC-062 and never
looser), and the derivation helpers. Real route handlers through FastAPI's TestClient.
"""
import copy
import json
from datetime import datetime
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest
from fastapi.testclient import TestClient

import app.api.routes.clinical_tools as ct
import app.api.routes.segmentation_analysis as sa
from app.agent_platform import registry as R
from app.core.container import get_imaging_service, get_segmentation_service, get_storage_service
from app.main import app
from app.models.schemas import AcquisitionGeometry
from app.security import get_current_active_user
from app.security.models import User, UserRole
from app.services import longitudinal_candidate_safety as lcs
from app.services import quality_gate as qg
from app.services.imaging_service import ImagingService

pytestmark = pytest.mark.unit
REGISTRY = Path(qg.__file__).resolve().parents[1] / "agent_platform" / "agents.json"
PATIENT = "11111111-1111-1111-1111-111111111111"
SHAPE = (12, 24, 24)
ACQ = {"manufacturer": "SIEMENS", "manufacturer_model_name": "Prisma", "magnetic_field_strength_t": 3.0,
       "mr_acquisition_type": "3D", "slice_thickness_mm": 1.0, "repetition_time_ms": 5000.0,
       "echo_time_ms": 393.0, "inversion_time_ms": 1800.0}


def _user():
    now = datetime.utcnow()
    return User(id="id-dr_rev", username="dr_rev", email="dr_rev@example.com", full_name="dr_rev",
                role=UserRole.RADIOLOGIST,
                is_active=True, is_locked=False, email_verified=True, created_at=now, updated_at=now)


def _registry(approved=True, on=True):
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if approved:
        data["agents"]["quality-gate"]["approval"]["status"] = "approved"     # IN MEMORY, for the test only
    return R.AgentRegistry(data, switches=R.InMemoryKillSwitches({"quality-gate": on}), audit=lambda e: None)


# ----------------------------------------------------------------------------- input derivation
@pytest.mark.parametrize("text, ti, expected", [
    ("AX T2 FLAIR", None, "FLAIR"), ("3D FLAIR SPACE", 1800, "FLAIR"), ("T1 FLAIR", None, "other"),
    ("FLAIR", 900, "other"), ("t1_mprage_sag", None, "T1"), ("AX T2 TSE", None, "T2"), ("SWI", None, "other"),
    ("DWI b1000", None, "other"), ("ep2d_diff ADC", None, "other"), ("series 4", None, "unknown"),
    ("", 2500, "unknown"), ("", None, "missing"), (None, None, "missing"), ("   ", None, "missing"),
])
def test_rc122_sequence_is_read_from_the_header_never_guessed(text, ti, expected):
    assert qg.sequence_from_header(text, ti) == expected


def test_rc122_thickness_inputs_come_from_rc054_and_a_stored_record_is_a_lower_bound_at_most():
    geo = AcquisitionGeometry(state="native", effective_mm=3.0, source="dicom_header")
    assert qg.thickness_from_geometry(geo) == {"state": "native", "effective_mm": 3.0}
    assert qg.thickness_from_geometry(None) is None
    assert qg.thickness_from_acquisition_record({**ACQ, "slice_thickness_mm": 5.0}) == {"state": "at_least",
                                                                                          "effective_mm": 5.0}
    assert qg.thickness_from_acquisition_record({**ACQ, "slice_thickness_mm": 3.0,
                                                 "spacing_between_slices_mm": 4.0})["effective_mm"] == 4.0
    for acq in ({**ACQ, "slice_thickness_mm": 1.0}, {**ACQ, "slice_thickness_mm": None},
                {"spacing_between_slices_mm": 5.0}):
        assert qg.thickness_from_acquisition_record(acq)["state"] == "not_determinable"   # never 'native'
    assert qg.thickness_from_acquisition_record(None) is None


def test_rc123_apply_to_comparison_withholds_exactly_what_rc062_withholds():
    result = {k: 1 for k in lcs.ABSTAINED_NULL_FIELDS}
    result.update({"abstained": False, "changes": [{"status": "new"}], "caveat": "x"})
    stopped = qg.apply_to_comparison(result, {"ai_output_allowed": False, "codes": ["scanner_changed"]})
    assert stopped["abstained"] is True and stopped["changes"] == []
    assert all(stopped[k] is None for k in lcs.ABSTAINED_NULL_FIELDS)
    assert "different scanners" in stopped["caveat"]
    allowed = qg.apply_to_comparison(result, {"ai_output_allowed": True, "codes": []})
    assert allowed["changes"] == [{"status": "new"}] and allowed["quality_gate"]["ai_output_allowed"] is True


def test_rc126_a_fault_inside_the_gate_is_an_abstention_audited_as_a_failure(monkeypatch):
    audit = []
    reg = _registry()
    reg._audit = audit.append
    monkeypatch.setattr(qg, "evaluate", lambda *a, **k: 1 / 0)
    out = qg.run_quality_gate({"mode": "single", "visits": []}, registry=reg, study_key="s")
    assert out["ai_may_run"] is False and out["codes"] == ["gate_unavailable"]
    assert [(e["event"], e["outcome"], e["code"]) for e in audit] == [("agent.consultation", "failure", "run_internal_error")]   # F4: releases nothing


# ----------------------------------------------------------------------------- single-study route
FILE = f"patients/{PATIENT}/studies/st-1/series/se-1/flair.nii"


class _Storage:
    def __init__(self, data):
        self.data = data

    async def download_file(self, bucket, path):
        return self.data


@pytest.fixture
def single(monkeypatch):
    img = nib.Nifti1Image(np.zeros((8, 8, 6), np.float32), np.diag([1.0, 1.0, 5.0, 1.0]))
    state = {"paths": []}

    async def _authorized(file_ids, patient_id, study_id, user):        # CAPA-009 verified in test_capa009_*
        state["paths"].append(list(file_ids))
        return [FILE]

    monkeypatch.setattr(ct, "_authorized_inputs", _authorized)
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", True)
    monkeypatch.setattr(qg, "_LIMITER", None)
    monkeypatch.setattr(lcs, "read_source_acquisition", lambda fid, svc=None: None)
    monkeypatch.setattr(qg, "read_source_series_description", lambda fid, svc=None: None)
    app.dependency_overrides[get_current_active_user] = _user
    app.dependency_overrides[get_storage_service] = lambda: _Storage(img.to_bytes())
    app.dependency_overrides[get_imaging_service] = lambda: ImagingService()
    yield TestClient(app), state
    for dep in (get_current_active_user, get_storage_service, get_imaging_service):
        app.dependency_overrides.pop(dep, None)


def test_rc126_the_single_study_route_is_refused_while_the_agent_is_not_approved(single, monkeypatch):
    client, state = single
    monkeypatch.setattr(qg, "_REGISTRY", R.AgentRegistry.load(REGISTRY, audit=lambda e: None))
    r = client.post("/api/v1/clinical/quality-gate", json={"file_id": "anything"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert state["paths"] == [], "a refusal authorizes, reads and downloads nothing (second review, finding 1)"
    assert body["decision"] == "abstain" and body["ai_may_run"] is False and body["codes"] == ["gate_not_approved"]
    assert len(body["trace_id"]) == 32


def test_rc122_the_single_study_route_derives_its_inputs_on_the_server(single, monkeypatch):
    client, _ = single
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    body = client.post("/api/v1/clinical/quality-gate", json={"file_id": FILE}).json()
    visit = body["inputs"]["visits"][0]
    assert visit == {"sequence": "missing", "physician_confirmed_flair": False,
                     "thickness": {"state": "at_least", "effective_mm": 5.0}, "scanner": None, "skull": "pending"}
    assert body["decision"] == "abstain" and body["codes"] == ["sequence_missing", "skull_pending", "thickness_at_least"]
    confirmed = client.post("/api/v1/clinical/quality-gate",
                            json={"file_id": FILE, "physician_confirmed_flair": True}).json()
    assert confirmed["decision"] == "pending" and confirmed["ai_may_run"] is True
    assert confirmed["ai_output_allowed"] is False
    assert confirmed["codes"] == ["sequence_confirmed_by_physician", "skull_pending", "thickness_at_least"]
    # the browser re-evaluates the same rule with the skull outcome before the output (gate.ts)
    final = qg.evaluate({**confirmed["inputs"], "visits": [{**confirmed["inputs"]["visits"][0], "skull": "stripped"}],
                         "platform": {"allowed": True, "code": None}})
    assert final["decision"] == "proceed_with_warnings" and final["ai_output_allowed"] is True


def test_rc122_an_unreadable_file_never_passes(single, monkeypatch):
    client, _ = single
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    app.dependency_overrides[get_storage_service] = lambda: _Storage(b"not an image")
    body = client.post("/api/v1/clinical/quality-gate", json={"file_id": FILE, "physician_confirmed_flair": True}).json()
    assert body["inputs"]["visits"][0]["thickness"] is None
    assert body["ai_output_allowed"] is False and "thickness_unknown" in body["codes"]


# ----------------------------------------------------------------------------- longitudinal routes
class _Meta:
    def __init__(self, sid):
        self.file_id = f"patients/{PATIENT}/studies/st-{sid}/series/se-{sid}/{sid}.nii.gz"
        self.analysis_data = {}
        self.modified_at = None


class _SegSvc:
    cache = None

    def __init__(self, masks):
        self.entries = {sid: {"metadata": _Meta(sid), "masks_3d": m} for sid, m in masks.items()}

    def get_mask(self, sid):
        e = self.entries.get(sid)
        return e["masks_3d"] if e else None

    def get_loaded(self, sid):
        return self.entries.get(sid)

    async def get_metadata(self, sid):
        e = self.entries.get(sid)
        return e["metadata"] if e else None

    def persist(self, sid):
        pass


PAIR = {"tp1": {"type": "segmentation", "id": "s1"}, "tp2": {"type": "segmentation", "id": "s2"}}


@pytest.fixture
def compare(monkeypatch):
    tp1 = np.zeros(SHAPE, np.uint8)
    tp1[2:5, 4:7, 4:7] = 1
    tp2 = tp1.copy()
    tp2[7:10, 15:18, 15:18] = 1                                          # one NEW candidate
    seg = _SegSvc({"s1": tp1, "s2": tp2})
    f1, f2 = (seg.entries[s]["metadata"].file_id for s in ("s1", "s2"))
    records = {"acq": {f1: dict(ACQ), f2: dict(ACQ)}, "desc": {f1: "AX FLAIR", f2: "AX FLAIR"}}

    async def _no_object_check(specs, user):
        return None

    async def _source(file_id, storage_service, context):
        return None, (1.0, 1.0, 1.0), None

    monkeypatch.setattr(sa, "authorize_mask_specs", _no_object_check)
    monkeypatch.setattr(sa, "_load_source_intensity", _source)
    monkeypatch.setattr(sa, "_source_acquisition", lambda fid: records["acq"].get(fid), raising=False)
    monkeypatch.setattr(sa, "_source_visit", lambda fid: {f1: {"study_id": "st-s1", "study_date": "2024-01-10"},
                                                          f2: {"study_id": "st-s2", "study_date": "2025-01-12"}}.get(fid),
                        raising=False)
    monkeypatch.setattr(lcs, "read_source_acquisition", lambda fid, svc=None: copy.deepcopy(records["acq"].get(fid)))
    monkeypatch.setattr(qg, "read_source_series_description", lambda fid, svc=None: records["desc"].get(fid))
    app.dependency_overrides[get_current_active_user] = _user
    app.dependency_overrides[get_segmentation_service] = lambda: seg
    app.dependency_overrides[get_storage_service] = lambda: object()
    yield TestClient(app), records, (f1, f2)
    for dep in (get_current_active_user, get_segmentation_service, get_storage_service):
        app.dependency_overrides.pop(dep, None)


def _post(client, path="/api/v1/segmentation/longitudinal/compare"):
    r = client.post(path, json=PAIR)
    assert r.status_code == 200, r.text
    return r.json()


def test_rc123_flag_off_the_comparison_is_unchanged(compare, monkeypatch):
    client, *_ = compare
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", False)
    res = _post(client)
    assert "quality_gate" not in res and res["abstained"] is False and res["change_candidates"]["total"] == 1


def test_rc126_flag_on_and_the_agent_not_approved_means_no_candidates(compare, monkeypatch):
    client, *_ = compare
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", True)
    monkeypatch.setattr(qg, "_REGISTRY", R.AgentRegistry.load(REGISTRY, audit=lambda e: None))
    res = _post(client)
    assert res["quality_gate"]["codes"] == ["gate_not_approved"]
    assert res["abstained"] is True and res["change_candidates"] is None and res["changes"] == []
    sel = _post(client, "/api/v1/segmentation/longitudinal/sel")
    assert sel["abstained"] is True and sel["quality_gate"]["codes"] == ["gate_not_approved"] and sel["sels"] == []


def test_rc123_flag_on_same_scanner_flair_shows_candidates_with_the_gate_attached(compare, monkeypatch):
    client, *_ = compare
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", True)
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    res = _post(client)
    gate = res["quality_gate"]
    assert gate["decision"] == "proceed_with_warnings" and gate["codes"] == ["thickness_unknown"]
    assert res["abstained"] is False and res["change_candidates"]["total"] == 1


def test_rc123_a_scanner_change_stops_the_comparison_in_the_gate_and_in_rc062(compare, monkeypatch):
    client, records, (f1, f2) = compare
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", True)
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    records["acq"][f2]["manufacturer"] = "GE MEDICAL SYSTEMS"
    res = _post(client)
    assert "scanner_changed" in res["quality_gate"]["codes"] and res["abstained"] is True
    assert lcs.compare_acquisitions(records["acq"][f1], records["acq"][f2], None, None)["status"] == "differs"


def test_rc123_the_gate_is_stricter_than_rc062_on_the_sequence(compare, monkeypatch):
    """RC-062 sees the same acquisition record, but visit 2's series is a T1: the gate withholds the candidates."""
    client, records, (f1, f2) = compare
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", True)
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    records["desc"][f2] = "t1_mprage_sag"
    res = _post(client)
    assert lcs.compare_acquisitions(records["acq"][f1], records["acq"][f2], (1.0, 1.0, 1.0), (1.0, 1.0, 1.0))["status"] == "same"
    assert "sequence_not_flair" in res["quality_gate"]["codes"]
    assert res["abstained"] is True and res["change_candidates"] is None and res["burden_tp2_mm3"] is None
    assert "not a FLAIR" in res["caveat"] and "sequence_not_flair" not in res["caveat"]


# ----------------------------------------------------------------------------- first review of PR #81
def test_rc123_c2_the_gate_decides_before_any_mask_or_image_is_loaded(compare, monkeypatch):
    client, *_ = compare
    loads = []

    async def _source(file_id, storage_service, context):
        loads.append(file_id)
        return None, (1.0, 1.0, 1.0), None

    monkeypatch.setattr(sa, "_load_source_intensity", _source)
    seg = app.dependency_overrides[get_segmentation_service]()
    masks = []
    monkeypatch.setattr(seg, "get_mask", lambda sid: masks.append(sid))
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", True)
    monkeypatch.setattr(qg, "_REGISTRY", R.AgentRegistry.load(REGISTRY, audit=lambda e: None))
    res = _post(client)
    assert res["abstained"] is True and res["quality_gate"]["codes"] == ["gate_not_approved"]
    assert loads == [] and masks == [], "nothing is loaded, registered or mapped before the gate allows it"
    sel = _post(client, "/api/v1/segmentation/longitudinal/sel")
    assert sel["abstained"] is True and loads == [] and masks == []


def test_rc123_c3_one_abstention_path_with_plain_reasons():
    result = {"abstained": False, "changes": [{"status": "new"}], "caveat": "x"}
    gate = {"ai_output_allowed": False, "codes": ["scanner_changed", "sequence_unknown"]}
    out = qg.apply_to_comparison(result, gate)
    assert out == qg.abstained_comparison(gate), "one abstention path (second review, finding 5)"
    assert "different scanners" in out["caveat"] and "does not say which sequence" in out["caveat"]
    for code in qg.load_policy()["codes"]:
        text = qg.gate_caveat({"codes": [code]})
        assert text and code not in text and "_" not in text, code


def test_rc123_e2_the_acquisition_records_are_read_once(compare, monkeypatch):
    client, records, _ = compare
    reads, stream = [], []
    monkeypatch.setattr(sa, "_source_acquisition", lambda fid: reads.append(fid) or records["acq"].get(fid),
                        raising=False)
    monkeypatch.setattr(lcs, "read_source_acquisition", lambda fid, svc=None: stream.append(fid))
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", True)
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    res = _post(client)
    assert res["abstained"] is False and len(reads) == 2 and stream == []


def test_rc122_e3_the_thin_limit_is_the_evaluated_policy_s(monkeypatch):
    monkeypatch.setattr(qg, "load_policy", lambda: 1 / 0)
    rec = {**ACQ, "slice_thickness_mm": 1.8}
    assert qg.thickness_from_acquisition_record(rec, thin_limit_mm=2.0)["state"] == "not_determinable"
    assert qg.thickness_from_acquisition_record(rec, thin_limit_mm=1.5) == {"state": "at_least", "effective_mm": 1.8}


class _CountingStorage(_Storage):
    def __init__(self, data):
        super().__init__(data)
        self.downloads = 0

    async def download_file(self, bucket, path):
        self.downloads += 1
        return self.data

    async def get_file_metadata(self, bucket, path):
        from app.core.interfaces.storage_interface import StorageObject
        return StorageObject(bucket=bucket, name=path, size=len(self.data), content_type="application/octet-stream",
                             checksum_sha256="v1", created_at="2026-11-12")


class _NoPixelImaging(ImagingService):
    def load_nifti(self, data):
        raise AssertionError("the gate must not decode the image")

    def load_dicom(self, data):
        raise AssertionError("the gate must not decode the image")


def _dicom_bytes(rows=4, comment_bytes=0):
    import io
    import pydicom
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.4"
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset("x.dcm", {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID, ds.SOPInstanceUID, ds.Modality = meta.MediaStorageSOPClassUID, meta.MediaStorageSOPInstanceUID, "MR"
    ds.SeriesDescription, ds.InversionTime, ds.ImageType = "Ax T2 FLAIR", 2200, ["ORIGINAL", "PRIMARY"]
    ds.SliceThickness, ds.SpacingBetweenSlices, ds.MRAcquisitionType = 3.0, 3.0, "2D"
    ds.Rows = ds.Columns = rows
    if comment_bytes:
        ds.ImageComments = "c" * comment_bytes
    ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation, ds.SamplesPerPixel = 16, 16, 15, 0, 1
    ds.PhotometricInterpretation, ds.PixelData = "MONOCHROME2", b"\0" * (rows * rows * 2)
    buf = io.BytesIO()
    pydicom.dcmwrite(buf, ds, write_like_original=False)
    return buf.getvalue()


def test_rc122_e1_headers_only_off_the_event_loop_and_cached_per_file_version(single, monkeypatch):
    import asyncio
    client, _ = single
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    monkeypatch.setattr(qg, "_HEADER_CACHE", type(qg._HEADER_CACHE)())
    threads = []
    parse = qg.read_header_fields

    def _spy(data, name, imaging_service):
        try:
            asyncio.get_running_loop()
            threads.append("event loop")
        except RuntimeError:
            threads.append("worker")
        return parse(data, name, imaging_service)

    monkeypatch.setattr(qg, "read_header_fields", _spy)
    app.dependency_overrides[get_imaging_service] = lambda: _NoPixelImaging()
    for data, name, expected in ((_dicom_bytes(), "patients/p/studies/s/series/se/x.dcm", ("FLAIR", "native", 3.0)),
                                 (None, FILE, ("missing", "at_least", 5.0))):
        storage = _CountingStorage(data) if data is not None else None
        if storage is None:
            img = nib.Nifti1Image(np.zeros((8, 8, 6), np.float32), np.diag([1.0, 1.0, 5.0, 1.0]))
            storage = _CountingStorage(img.to_bytes())
        app.dependency_overrides[get_storage_service] = (lambda st: (lambda: st))(storage)   # no parameter: FastAPI would copy it
        monkeypatch.setattr(ct, "_authorized_inputs", lambda *a, n=name: _as_coro([n]))
        for _ in range(2):
            body = client.post("/api/v1/clinical/quality-gate", json={"file_id": name}).json()
            visit = body["inputs"]["visits"][0]
            assert (visit["sequence"], visit["thickness"]["state"], visit["thickness"]["effective_mm"]) == expected
        assert storage.downloads == 1, "the second consultation of the same file version is served from the cache"
    assert threads and set(threads) == {"worker"}


async def _as_coro(value):
    return value


def test_rc122_g13_the_attestation_is_a_strict_boolean_and_is_audited_with_the_user(single, monkeypatch):
    client, _ = single
    for value in ("true", 1, "yes"):
        r = client.post("/api/v1/clinical/quality-gate", json={"file_id": FILE, "physician_confirmed_flair": value})
        assert r.status_code in (400, 422), value
    records = []
    reg = _registry()
    reg._audit = lambda e: records.append((e, R.current_actor().user_id))
    monkeypatch.setattr(qg, "_REGISTRY", reg)
    client.post("/api/v1/clinical/quality-gate", json={"file_id": FILE})
    client.post("/api/v1/clinical/quality-gate", json={"file_id": FILE, "physician_confirmed_flair": True})
    (plain, u1), (attested, u2) = records
    assert plain["code"] == "quality_gate.abstain.sequence_missing"
    assert attested["code"] == "quality_gate.pending.skull_pending.attested"
    assert u1 == u2 == "id-dr_rev"


# ----------------------------------------------------------------------------- second review of PR #81
URL = "/api/v1/clinical/quality-gate"


def test_rc126_g17_shown_and_hidden_outputs_leave_distinguishable_audit_records(single, monkeypatch):
    """The decision that releases or withholds the AI output is decided and audited ON THE SERVER, with the skull
    outcome the browser reports; the browser only re-checks it with the same rule."""
    client, _ = single
    records = []
    reg = _registry()
    reg._audit = records.append
    monkeypatch.setattr(qg, "_REGISTRY", reg)
    shown = client.post(URL, json={"file_id": FILE, "physician_confirmed_flair": True, "skull": "stripped"}).json()
    hidden = client.post(URL, json={"file_id": FILE, "physician_confirmed_flair": True, "skull": "unknown"}).json()
    assert shown["ai_output_allowed"] is True and hidden["ai_output_allowed"] is False
    assert [r["code"] for r in records] == ["quality_gate.proceed_with_warnings.attested",
                                            "quality_gate.abstain.skull_unknown.attested"]
    assert shown["subject"]["file_id"] == FILE and "version" in shown["subject"]
    for bad in ("not_stripped", "STRIPPED", 1, None):
        assert client.post(URL, json={"file_id": FILE, "skull": bad}).status_code in (400, 422), bad


def test_rc126_behind_the_flag_and_refused_before_any_io(single, monkeypatch):
    client, state = single
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", False)
    assert client.post(URL, json={"file_id": FILE}).status_code == 404
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", True)
    storage = _CountingStorage(b"x")
    app.dependency_overrides[get_storage_service] = (lambda st: (lambda: st))(storage)
    monkeypatch.setattr(qg, "_REGISTRY", R.AgentRegistry.load(REGISTRY, audit=lambda e: None))      # pending
    state["paths"].clear()
    body = client.post(URL, json={"file_id": FILE}).json()
    assert body["codes"] == ["gate_not_approved"] and body["subject"]["file_id"] == FILE
    assert storage.downloads == 0 and state["paths"] == [], "nothing is authorized, read or downloaded"


def test_rc126_a_per_user_rate_limit_bounds_the_reads(single, monkeypatch):
    client, _ = single
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    monkeypatch.setattr(qg, "RATE_LIMIT_PER_MINUTE", 3)
    monkeypatch.setattr(qg, "_LIMITER", qg.new_rate_limiter())
    codes = [client.post(URL, json={"file_id": FILE}).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]


def test_rc122_the_header_is_read_with_a_bounded_range(single, monkeypatch):
    import gzip
    client, _ = single
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    monkeypatch.setattr(qg, "_HEADER_CACHE", type(qg._HEADER_CACHE)())

    class _Ranged(_CountingStorage):
        def __init__(self, data):
            super().__init__(data)
            self.ranges = []

        async def download_file(self, bucket, path):
            raise AssertionError("the whole file was downloaded")

        async def download_file_range(self, bucket, path, start, end):
            self.ranges.append((start, end))
            return self.data[start:end + 1]

    rng = np.random.default_rng(0)           # incompressible voxels: the gzip file is large too
    img = nib.Nifti1Image(rng.random((64, 64, 40)).astype(np.float32), np.diag([1.0, 1.0, 5.0, 1.0])).to_bytes()
    cases = ((img, FILE, 5.0, 1), (gzip.compress(img), FILE + ".gz", 5.0, 1),
             (_dicom_bytes(rows=512), "patients/p/studies/s/series/se/a.dcm", 3.0, 1),
             (_dicom_bytes(rows=512, comment_bytes=200_000), "patients/p/studies/s/series/se/b.dcm", 3.0, 2))
    for data, name, mm, min_ranges in cases:
        storage = _Ranged(data)
        app.dependency_overrides[get_storage_service] = (lambda st: (lambda: st))(storage)
        monkeypatch.setattr(ct, "_authorized_inputs", lambda *a, n=name: _as_coro([n]))
        visit = client.post(URL, json={"file_id": name}).json()["inputs"]["visits"][0]
        read = sum(e - s + 1 for s, e in storage.ranges)
        assert visit["thickness"]["effective_mm"] == mm, name
        assert len(storage.ranges) >= min_ranges and read < len(data), (name, storage.ranges, len(data))


async def _no_metadata(sid):
    return None


async def _broken_metadata(sid):
    raise RuntimeError("segmentation store unreadable")


def test_rc123_missing_or_unreadable_metadata_abstains_with_a_reason(compare, monkeypatch):
    client, *_ = compare
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", True)
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    seg = app.dependency_overrides[get_segmentation_service]()
    for broken in (_no_metadata, _broken_metadata):
        monkeypatch.setattr(seg, "get_metadata", broken)
        for path, reason in (("/api/v1/segmentation/longitudinal/compare", "caveat"),
                             ("/api/v1/segmentation/longitudinal/sel", "reason")):
            r = client.post(path, json=PAIR)
            assert r.status_code == 200, (broken.__name__, path, r.status_code)
            assert r.json()["abstained"] is True and r.json()[reason], (broken.__name__, path)


def test_rc123_the_metadata_is_read_once_per_visit_and_one_type_check(compare, monkeypatch):
    import inspect
    client, *_ = compare
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", True)
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    seg = app.dependency_overrides[get_segmentation_service]()
    calls, original = [], seg.get_metadata

    async def _counting(sid):
        calls.append(sid)
        return await original(sid)

    monkeypatch.setattr(seg, "get_metadata", _counting)
    _post(client)
    assert sorted(calls) == ["s1", "s2"]
    calls.clear()
    client.post("/api/v1/segmentation/longitudinal/sel", json=PAIR)
    assert sorted(calls) == ["s1", "s2"]
    src = inspect.getsource(sa.detect_slowly_expanding_lesions)
    # one message; checked where the base checked it with the gate off (G26), and before the gate with it on
    assert inspect.getsource(sa).count("SEL detection requires segmentation-type inputs") == 1
    assert src.count("_sel_input_type_error()") == 2 and "settings.QUALITY_GATE_ENFORCED and any(" in src


def test_rc126_no_policy_copy_per_consultation(monkeypatch):
    monkeypatch.setattr(qg, "load_policy", lambda: 1 / 0)
    visit = {"sequence": "FLAIR", "physician_confirmed_flair": False, "skull": "stripped", "scanner": None,
             "thickness": {"state": "native", "effective_mm": 1.0}}
    out = qg.run_quality_gate({"mode": "single", "visits": [visit]}, registry=_registry(), study_key="s")
    assert out["decision"] == "proceed"


# ----------------------------------------------------------------------------- third review of PR #81
def test_rc126_g22_every_clinical_and_analysis_post_route_is_audited():
    """GENERIC: every POST route of the clinical tools and segmentation-analysis routers is registered in the audit
    middleware, so the audit names what it read or recorded (no new route can be missed)."""
    from fastapi.routing import APIRoute
    from app.core.logging import audit_middleware as am
    prefix = "/api/v1"
    paths = {prefix + r.path for router in (ct.router, sa.router) for r in router.routes
             if isinstance(r, APIRoute) and "POST" in r.methods}
    missing = sorted(p for p in paths if p not in am.BODY_ID_ROUTES and ("POST", p) not in am.ROUTE_ACTIONS)
    assert not missing, f"G22: POST routes not registered in the audit middleware: {missing}"
    assert "/api/v1/clinical/quality-gate" in am.BODY_ID_ROUTES


def test_rc126_the_rate_limit_comes_first_and_the_gate_runs_off_the_loop(single, monkeypatch):
    import asyncio
    client, _ = single
    monkeypatch.setattr(qg, "_REGISTRY", R.AgentRegistry.load(REGISTRY, audit=lambda e: None))    # refused
    monkeypatch.setattr(qg, "RATE_LIMIT_PER_MINUTE", 2)
    monkeypatch.setattr(qg, "_LIMITER", qg.new_rate_limiter())
    assert [client.post(URL, json={"file_id": FILE}).status_code for _ in range(4)] == [200, 200, 429, 429]
    where = []
    original = qg.run_quality_gate

    def _spy(*a, **k):
        try:
            asyncio.get_running_loop()
            where.append("event loop")
        except RuntimeError:
            where.append("worker")
        return original(*a, **k)

    monkeypatch.setattr(qg, "run_quality_gate", _spy)
    monkeypatch.setattr(qg, "_LIMITER", None)
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    client.post(URL, json={"file_id": FILE})
    assert where == ["worker"]


def test_rc122_the_header_format_comes_from_magic_bytes_off_the_loop(single, monkeypatch):
    import asyncio
    client, _ = single
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    monkeypatch.setattr(qg, "_HEADER_CACHE", type(qg._HEADER_CACHE)())

    class _NoDetect(ImagingService):
        def detect_format(self, data, name):
            raise AssertionError("the gate must detect the format from magic bytes")

    app.dependency_overrides[get_imaging_service] = lambda: _NoDetect()
    threads = []
    complete = qg._header_complete

    def _spy(*a, **k):
        try:
            asyncio.get_running_loop()
            threads.append("event loop")
        except RuntimeError:
            threads.append("worker")
        return complete(*a, **k)

    monkeypatch.setattr(qg, "_header_complete", _spy)

    class _Ranged(_CountingStorage):
        async def download_file_range(self, bucket, path, start, end):
            return self.data[start:end + 1]

    img = nib.Nifti1Image(np.zeros((8, 8, 6), np.float32), np.diag([1.0, 1.0, 5.0, 1.0])).to_bytes()
    for data, name, expect in ((img, "patients/p/studies/s/series/se/scan.img", ("at_least", None)),
                               (_dicom_bytes(rows=512), "patients/p/studies/s/series/se/IM0001", ("native", None)),
                               (b"\x00" * 4096, "patients/p/studies/s/series/se/blob.bin", (None, "header_unreadable"))):
        storage = _Ranged(data)
        app.dependency_overrides[get_storage_service] = (lambda st: (lambda: st))(storage)
        monkeypatch.setattr(ct, "_authorized_inputs", lambda *a, n=name: _as_coro([n]))
        body = client.post(URL, json={"file_id": name, "physician_confirmed_flair": True}).json()
        visit = body["inputs"]["visits"][0]
        state, code = expect
        if state:
            assert visit["thickness"]["state"] == state, (name, visit)
        else:
            assert code in body["codes"] and body["ai_may_run"] is False, (name, body["codes"])
    assert threads and set(threads) == {"worker"}


def test_rc122_a_storage_without_real_ranges_is_read_once():
    import asyncio
    from app.core.interfaces.storage_interface import IStorageService

    class _DefaultRanges:
        download_file_range = IStorageService.download_file_range       # the interface default: whole file, sliced

        def __init__(self, data):
            self.data, self.downloads = data, 0

        async def download_file(self, bucket, path):
            self.downloads += 1
            return self.data

    storage = _DefaultRanges(_dicom_bytes(rows=512, comment_bytes=200_000))
    loop = asyncio.new_event_loop()          # own loop: asyncio.run would leave the next test without one
    try:
        fields = loop.run_until_complete(qg._read_header_fields(storage, "b", "patients/p/studies/s/series/se/b.dcm", ImagingService()))
    finally:
        loop.close()
    assert storage.downloads == 1 and fields["thickness"]["effective_mm"] == 3.0


def test_rc123_f1_two_uploaded_niftis_can_be_compared_with_a_per_visit_attestation(compare, monkeypatch):
    """F1 as corrected by the fourth review (R1): two uploads, no acquisition record and no description. Without the
    attestation the gate abstains per visit; with it (per visit, strict booleans, audited with the user) the gate
    passes with warnings and RC-062 then ABSTAINS exactly as on the base branch — the gate never relaxes it."""
    client, records, (f1, f2) = compare
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", True)
    audit = []
    reg = _registry()
    reg._audit = audit.append
    monkeypatch.setattr(qg, "_REGISTRY", reg)
    records["acq"].clear()
    records["desc"].clear()
    res = _post(client)
    assert res["abstained"] is True and {"sequence_missing"} <= set(res["quality_gate"]["codes"])
    body = {**PAIR, "quality_gate_attestation": {"tp1": True, "tp2": True}}
    res = client.post("/api/v1/segmentation/longitudinal/compare", json=body).json()
    gate = res["quality_gate"]
    assert gate["ai_output_allowed"] is True and "scanner_not_recorded" in gate["codes"], gate["codes"]
    assert res["abstained"] is True and res["change_candidates"] is None and "acquisition_unrecorded" not in res
    assert res["acquisition_check"]["status"] == "not_established"
    assert audit[-1]["code"].endswith(".attested_tp1_tp2")
    for bad in ({"tp1": "true", "tp2": True}, {"tp1": 1}, ["tp1"], {"tp3": True}):
        r = client.post("/api/v1/segmentation/longitudinal/compare", json={**PAIR, "quality_gate_attestation": bad})
        assert r.status_code in (400, 422), bad


def test_rc123_f1_an_attestation_never_lifts_another_sequence_in_a_comparison(compare, monkeypatch):
    client, records, (f1, f2) = compare
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", True)
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    records["desc"][f2] = "Ax DWI B1000"
    res = client.post("/api/v1/segmentation/longitudinal/compare",
                      json={**PAIR, "quality_gate_attestation": {"tp1": True, "tp2": True}}).json()
    assert res["abstained"] is True and "sequence_not_flair" in res["quality_gate"]["codes"]


# ----------------------------------------------------------------------------- fifth review of PR #81: F3, F4
def _spy_runs(monkeypatch):
    runs = []
    original = qg.run_quality_gate

    def _spy(*a, **k):
        runs.append(a[0])
        return original(*a, **k)

    monkeypatch.setattr(qg, "run_quality_gate", _spy)
    return runs


def test_rc126_f3_repeated_consultations_come_from_the_cache_and_are_not_counted(single, monkeypatch):
    """Per (file, version, attestation, skull, policy version): a repeated pre-run consultation is served from the
    server's cache and does not count against the limit; only real evaluations count."""
    client, _ = single
    app.dependency_overrides[get_storage_service] = (lambda st: (lambda: st))(_CountingStorage(
        nib.Nifti1Image(np.zeros((8, 8, 6), np.float32), np.diag([1.0, 1.0, 5.0, 1.0])).to_bytes()))
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    monkeypatch.setattr(qg, "RATE_LIMIT_PER_MINUTE", 2)
    monkeypatch.setattr(qg, "_LIMITER", qg.new_rate_limiter())
    monkeypatch.setattr(qg, "_CONSULTATIONS", type(qg._CONSULTATIONS)())
    runs = _spy_runs(monkeypatch)
    first = [client.post(URL, json={"file_id": FILE}) for _ in range(6)]
    assert [r.status_code for r in first] == [200] * 6 and len(runs) == 1
    assert all(r.json() == first[0].json() for r in first)
    assert client.post(URL, json={"file_id": FILE, "physician_confirmed_flair": True}).status_code == 200
    assert len(runs) == 2                                     # another attestation: a real evaluation, counted
    limited = client.post(URL, json={"file_id": FILE, "skull": "stripped"})
    assert limited.status_code == 429 and len(runs) == 2      # the third real evaluation is over the limit
    details = limited.json()["error"]["details"]
    assert details["code"] == "gate_rate_limited" and isinstance(details["retry_after_s"], int)
    assert 0 < details["retry_after_s"] <= 60 and limited.headers["Retry-After"] == str(details["retry_after_s"])
    assert client.post(URL, json={"file_id": FILE}).status_code == 200   # still served from the cache


def test_rc126_f3_a_releasing_consultation_is_never_served_from_the_cache(single, monkeypatch):
    client, _ = single
    app.dependency_overrides[get_storage_service] = (lambda st: (lambda: st))(_CountingStorage(
        nib.Nifti1Image(np.zeros((8, 8, 6), np.float32), np.diag([1.0, 1.0, 5.0, 1.0])).to_bytes()))
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    monkeypatch.setattr(qg, "_LIMITER", None)
    monkeypatch.setattr(qg, "_CONSULTATIONS", type(qg._CONSULTATIONS)())
    runs = _spy_runs(monkeypatch)
    for _ in range(3):
        assert client.post(URL, json={"file_id": FILE, "skull": "stripped"}).status_code == 200
    assert len(runs) == 3, "each final consultation is decided and audited again"


def test_rc126_f3_the_kill_switch_applies_to_a_cached_answer(single, monkeypatch):
    client, _ = single
    app.dependency_overrides[get_storage_service] = (lambda st: (lambda: st))(_CountingStorage(
        nib.Nifti1Image(np.zeros((8, 8, 6), np.float32), np.diag([1.0, 1.0, 5.0, 1.0])).to_bytes()))
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    monkeypatch.setattr(qg, "_LIMITER", None)
    monkeypatch.setattr(qg, "_CONSULTATIONS", type(qg._CONSULTATIONS)())
    assert client.post(URL, json={"file_id": FILE}).json()["platform"]["allowed"] is True
    monkeypatch.setattr(qg, "_REGISTRY", _registry(on=False))
    assert client.post(URL, json={"file_id": FILE}).json()["codes"] == ["gate_switched_off"]


def test_rc126_f4_opening_ten_images_records_no_ai_run(single, monkeypatch):
    """A consultation is not an AI run: ten images opened (ten pre-run consultations) record ten consultations and
    no CLINICAL_AI_RUN; only a decision that releases an AI output is linked to the AI run."""
    from app.core.logging import audit as A
    client, _ = single
    monkeypatch.setattr(qg, "_REGISTRY", None)
    monkeypatch.setattr(R.AgentRegistry, "load", classmethod(lambda cls, *a, **k: _registry_with_sink()))
    monkeypatch.setattr(qg, "_LIMITER", None)
    seen = []
    monkeypatch.setattr(A.AuditLogger, "log_event", lambda self, event, durable=True: seen.append(event.event_type))
    for i in range(10):
        monkeypatch.setattr(qg, "_CONSULTATIONS", type(qg._CONSULTATIONS)())
        assert client.post(URL, json={"file_id": f"{FILE}-{i}"}).status_code == 200
    assert A.AuditEventType.CLINICAL_AI_RUN not in seen, seen
    assert seen.count(A.AuditEventType.QUALITY_GATE_CONSULTATION) >= 10


def _registry_with_sink():
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    data["agents"]["quality-gate"]["approval"]["status"] = "approved"     # IN MEMORY, for the test only
    return R.AgentRegistry(data, switches=R.InMemoryKillSwitches({"quality-gate": True}), audit=R.default_audit_sink)


def test_rc126_f4_only_a_releasing_decision_is_an_ai_run():
    from app.core.logging import audit as A
    events = []
    reg = _registry()
    reg._audit = events.append
    flair = {"sequence": "FLAIR", "physician_confirmed_flair": False, "scanner": None,
             "thickness": {"state": "native", "effective_mm": 1.0}}
    qg.run_quality_gate({"mode": "single", "visits": [{**flair, "skull": "pending"}]}, registry=reg)
    qg.run_quality_gate({"mode": "single", "visits": [{**flair, "skull": "stripped"}]}, registry=reg)
    qg.run_quality_gate({"mode": "single", "visits": [{**flair, "skull": "unknown"}]}, registry=reg)
    assert [e["event"] for e in events] == ["agent.consultation", "agent.run", "agent.consultation"]
    assert all(e["event"] in R.AUDIT_EVENT_TYPES for e in events)
    emitted = []
    import app.core.logging.audit as audit_module
    original = audit_module.emit_audit
    try:
        audit_module.emit_audit = lambda event_type, outcome, **k: emitted.append(event_type)
        for e in events:
            R.default_audit_sink(e)
    finally:
        audit_module.emit_audit = original
    assert emitted == [A.AuditEventType.QUALITY_GATE_CONSULTATION, A.AuditEventType.CLINICAL_AI_RUN,
                       A.AuditEventType.QUALITY_GATE_CONSULTATION]


def test_rc126_f4_the_route_is_audited_as_a_consultation():
    import app.core.logging.audit_middleware as am
    from app.core.logging.audit import AuditEventType
    assert am.ROUTE_ACTIONS[("POST", URL)][0] == AuditEventType.QUALITY_GATE_CONSULTATION
