"""PRB-021, PRB-023, PRB-025, PRB-026 — patient registry scope, creator access, counts, segmentation author.

Found in the browser capture of the release candidate (2026-10-28, `mstool-film/assets/app-captures/CAPTURES.md`
§5) and while reproducing it on `main` @ 70cc5c7:

- PRB-021 (found while reproducing F21): `GET /api/v1/patients` and `/patients/search` return EVERY patient
  (name, record number, birth date, sex) to any signed-in user with PATIENT_VIEW — a viewer included — with
  no care-team check (REQ-SEC-014). With open self-registration (PRB-020) that is anyone on the internet.
- PRB-023 (F18): a clinician who creates a patient is not put on its care team, so the next request answers
  "Patient not found"; and the access log records `denied:record_unattributed_pending_review` (quarantined)
  although `created_by` was stored: the patient object the check reads (PatientResponse) does not carry
  `created_by`, and "quarantined" was decided on the CALLER's assignments, not the patient's.
- PRB-025 (F07): a deleted study (soft delete = status "cancelled") stays in the patient's study list and in
  every count (studies, images, scans, dashboard); a deleted document (entered-in-error) stays in the document
  count; the study card's "SEGM." is always 0 (no count exists). The delete route says hard delete is
  administrator-only but does not check it.
- PRB-026 (F06, backend part): the creator of a segmentation is never stored, so the viewer shows the
  placeholder "current_user" as its author.

Every test runs with no cloud credential (PRB-002) and in-memory stand-ins (tests/unit/prb020_fakes.py).
Negative controls: scripts/safety/prb020_negative_controls.py.
"""
import uuid
from datetime import datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import get_current_active_user
from app.security.models import UserRole
from app.security.patient_access import AccessDecision
from app.services.patient_service_firestore import PatientServiceFirestore
from app.services.study_service_firestore import StudyServiceFirestore
from app.models.study_schemas import StudySearch, StudyStatus
import app.api.routes.patients as patient_routes
import app.api.routes.studies as study_routes
import app.security.patient_access_dependency as pad
import app.security.resource_access as ra

from tests.unit.prb020_fakes import FakeCareTeam, FakeDb, make_user, patient_doc, study_doc

client = TestClient(app)

P1 = "11111111-1111-4111-8111-111111111111"   # attributed, created by u-other
P2 = "22222222-2222-4222-8222-222222222222"   # attributed, created by u-other
P3 = "33333333-3333-4333-8333-333333333333"   # legacy (no created_by), assigned to u-other
P4 = "44444444-4444-4444-8444-444444444444"   # legacy (no created_by), no assignment at all
S1 = "a1111111-1111-4111-8111-111111111111"
S2 = "a2222222-2222-4222-8222-222222222222"
S3 = "a3333333-3333-4333-8333-333333333333"
ZONE_MAP = "MAGNIMS Zone Map"


class World:
    def __init__(self):
        self.db = FakeDb()
        self.care = FakeCareTeam()
        self.patients = object.__new__(PatientServiceFirestore)
        self.patients.db, self.patients.collection = self.db, "patients"
        self.studies = object.__new__(StudyServiceFirestore)
        self.studies.db, self.studies.storage = self.db, None
        pats = self.db.data.setdefault("patients", {})
        pats[P1] = patient_doc(P1, "Demo", "Patient (public data)", "DEMO-0001", created_by="u-other")
        pats[P2] = patient_doc(P2, "Erika", "Mustermann", "DEMO-0002", created_by="u-other")
        pats[P3] = patient_doc(P3, "Legacy", "Assigned", "LEG-0003")
        pats[P4] = patient_doc(P4, "Legacy", "Orphan", "LEG-0004")
        self.care.assign(patient_id=P3, user_id="u-other", role_in_care="attending", granted_by="u-admin")
        self.audit = []


@pytest.fixture
def world(monkeypatch):
    w = World()
    saved = dict(app.dependency_overrides)
    app.dependency_overrides[patient_routes.get_patient_service] = lambda: w.patients
    app.dependency_overrides[patient_routes.get_care_team_service] = lambda: w.care
    app.dependency_overrides[study_routes.get_study_service] = lambda: w.studies
    monkeypatch.setattr(pad, "_get_patient_service", lambda: w.patients)
    monkeypatch.setattr(pad, "_get_care_team_service", lambda: w.care)
    monkeypatch.setattr(ra, "_patient_service", lambda: w.patients)
    monkeypatch.setattr(ra, "_care_team_service", lambda: w.care)
    monkeypatch.setattr(ra, "_study_service", lambda: w.studies)
    monkeypatch.setattr(pad, "audit_access_decision",
                        lambda *, user_id, patient_id, result: w.audit.append((user_id, patient_id, result.decision)))
    yield w
    app.dependency_overrides.clear()
    app.dependency_overrides.update(saved)


def _act_as(role, uid, username=None):
    user = make_user(username or uid.replace("-", "_"), role, uid=uid)
    app.dependency_overrides[get_current_active_user] = lambda: user
    return user


def _ids(response):
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()["items"]}


# ============================================================================================
# PRB-021 — the patient registry lists only the caller's patients (REQ-SEC-014)
# ============================================================================================
@pytest.mark.parametrize("role", [UserRole.VIEWER, UserRole.TECHNICIAN, UserRole.RADIOLOGIST])
def test_rc082_prb021_user_without_assignment_lists_no_patient(world, role):
    _act_as(role, "u-new")
    r = client.get("/api/v1/patients")
    assert _ids(r) == set()
    assert r.json()["total"] == 0


def test_rc082_prb021_patient_list_shows_only_the_assigned_patients(world):
    _act_as(UserRole.RADIOLOGIST, "u-rad")
    world.care.assign(patient_id=P2, user_id="u-rad", role_in_care="reading", granted_by="u-admin")
    r = client.get("/api/v1/patients")
    assert _ids(r) == {P2}
    assert r.json()["total"] == 1


def test_rc082_prb021_patient_search_is_scoped_too(world):
    _act_as(UserRole.RADIOLOGIST, "u-rad")
    world.care.assign(patient_id=P2, user_id="u-rad", role_in_care="reading", granted_by="u-admin")
    assert _ids(client.get("/api/v1/patients/search", params={"gender": "male"})) == {P2}
    assert _ids(client.get("/api/v1/patients/search", params={"mrn": "DEMO-0001"})) == set()
    assert _ids(client.get("/api/v1/patients/search", params={"family_name": "Muster"})) == {P2}


def test_rc082_prb021_revoked_assignment_no_longer_lists_the_patient(world):
    _act_as(UserRole.RADIOLOGIST, "u-rad")
    rec = world.care.assign(patient_id=P2, user_id="u-rad", role_in_care="reading", granted_by="u-admin")
    world.care.revoke(assignment_id=rec.id, revoked_by="u-admin")
    assert _ids(client.get("/api/v1/patients")) == set()


def test_rc082_prb021_administrator_lists_every_patient(world):
    _act_as(UserRole.ADMIN, "u-admin")
    assert _ids(client.get("/api/v1/patients")) == {P1, P2, P3, P4}


def test_rc082_prb021_scoped_list_pages_and_filters_by_status(world):
    _act_as(UserRole.RADIOLOGIST, "u-rad")
    world.db.data["patients"][P1]["status"] = "inactive"
    for p in (P1, P2, P3):
        world.care.assign(patient_id=p, user_id="u-rad", role_in_care="reading", granted_by="u-admin")
    r = client.get("/api/v1/patients", params={"status": "active", "page_size": 1})
    assert r.json()["total"] == 2 and len(r.json()["items"]) == 1
    page2 = client.get("/api/v1/patients", params={"status": "active", "page_size": 1, "page": 2})
    assert {r.json()["items"][0]["id"], page2.json()["items"][0]["id"]} == {P2, P3}


# ============================================================================================
# PRB-023 — the creator can open the patient it created; the denial reason is the true one
# ============================================================================================
NEW_PATIENT = {"mrn": "NEW-0005", "given_name": "Anna", "family_name": "Beispiel", "birth_date": "1990-05-01",
               "gender": "female", "phone_mobile": "+491701234567", "country": "DEU"}


def test_rc083_prb023_creator_is_put_on_the_care_team_and_can_open_the_patient(world):
    _act_as(UserRole.RADIOLOGIST, "u-rad")
    r = client.post("/api/v1/patients", json=NEW_PATIENT)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert [(a.patient_id, a.user_id, a.role_in_care) for a in world.care.list_for_patient(pid)] == [
        (pid, "u-rad", "attending")]
    assert world.care.list_for_patient(pid)[0].granted_by == "u-rad"
    assert client.get(f"/api/v1/patients/{pid}").status_code == 200
    assert pid in _ids(client.get("/api/v1/patients"))


def test_rc083_prb023_administrator_creator_is_not_put_on_a_care_team(world):
    _act_as(UserRole.ADMIN, "u-admin")
    r = client.post("/api/v1/patients", json=NEW_PATIENT)
    assert r.status_code == 201, r.text
    assert world.care.list_for_patient(r.json()["id"]) == []


def test_rc083_prb023_failed_assignment_is_reported_not_hidden(world):
    _act_as(UserRole.TECHNICIAN, "u-tech")
    world.care.fail_assign = True
    r = client.post("/api/v1/patients", json=NEW_PATIENT)
    assert r.status_code == 500, r.text
    detail = r.json().get("detail") or r.json().get("error", {}).get("message", "")
    assert "care team" in str(detail).lower() and "administrator" in str(detail).lower()
    created = [d for d in world.db.data["patients"].values() if d["mrn"] == "NEW-0005"]
    assert len(created) == 1 and created[0]["created_by"] == "u-tech"


async def test_rc083_prb023_provenance_is_read_for_the_decision_but_never_returned(world):
    patient = await world.patients.get_patient(UUID(P1))
    assert getattr(patient, "created_by", None) == "u-other"
    assert "created_by" not in patient.model_dump()
    _act_as(UserRole.ADMIN, "u-admin")
    body = client.get(f"/api/v1/patients/{P1}").json()
    assert body["id"] == P1 and "created_by" not in body


def test_rc083_prb023_unassigned_user_on_an_attributed_patient_is_denied_as_not_assigned(world):
    _act_as(UserRole.RADIOLOGIST, "u-new")                    # no assignment at all
    assert client.get(f"/api/v1/patients/{P1}").status_code == 404
    assert world.audit[-1] == ("u-new", P1, AccessDecision.DENIED_NOT_ASSIGNED)


def test_rc083_prb023_legacy_patient_on_someone_elses_care_team_is_not_called_quarantined(world):
    _act_as(UserRole.RADIOLOGIST, "u-new")                    # no assignment at all
    assert client.get(f"/api/v1/patients/{P3}").status_code == 404
    assert world.audit[-1] == ("u-new", P3, AccessDecision.DENIED_NOT_ASSIGNED)


def test_rc083_prb023_legacy_patient_without_any_assignment_is_quarantined(world):
    _act_as(UserRole.RADIOLOGIST, "u-rad")
    world.care.assign(patient_id=P2, user_id="u-rad", role_in_care="reading", granted_by="u-admin")
    assert client.get(f"/api/v1/patients/{P4}").status_code == 404
    assert world.audit[-1] == ("u-rad", P4, AccessDecision.DENIED_QUARANTINED)


# ============================================================================================
# PRB-025 — deleted studies and documents are neither listed nor counted; SEGM. is a real count
# ============================================================================================
def _three_studies(world):
    st = world.db.data.setdefault("studies", {})
    st[S1] = study_doc(S1, P1, "available", "2026-09-30T00:00:00")
    st[S2] = study_doc(S2, P1, "cancelled", "2026-09-29T00:00:00")
    st[S3] = study_doc(S3, P1, "entered-in-error", "2026-09-28T00:00:00")


async def test_rc085_prb025_deleted_studies_are_not_listed_for_the_patient(world):
    _three_studies(world)
    items, total = await world.studies.list_patient_studies(UUID(P1))
    assert [str(s.id) for s in items] == [S1]
    assert total == 1


async def test_rc085_prb025_deleted_studies_and_documents_are_not_counted(world):
    _three_studies(world)
    docs = world.db.data.setdefault("documents", {})
    docs["d1"] = {"id": "d1", "patient_id": P1, "status": "current"}
    docs["d2"] = {"id": "d2", "patient_id": P1, "status": "entered-in-error"}
    patient = await world.patients.get_patient(UUID(P1), include_stats=True)
    assert (patient.study_count, patient.document_count) == (1, 1)
    summaries, _ = await world.patients.list_patients()
    assert {str(s.id): (s.study_count, s.document_count) for s in summaries}[P1] == (1, 1)
    _act_as(UserRole.ADMIN, "u-admin")
    assert {i["id"]: i["study_count"] for i in client.get("/api/v1/patients").json()["items"]}[P1] == 1


async def test_rc085_prb025_explicit_status_filter_still_finds_a_cancelled_study(world):
    _three_studies(world)
    items, total = await world.studies.search_studies(StudySearch(patient_id=UUID(P1), status=StudyStatus.CANCELLED))
    assert [str(s.id) for s in items] == [S2] and total == 1
    items, total = await world.studies.search_studies(StudySearch(patient_id=UUID(P1)))
    assert [str(s.id) for s in items] == [S1] and total == 1


async def test_rc085_prb025_study_summary_counts_its_segmentations(world):
    _three_studies(world)
    segs = world.db.data.setdefault("segmentations", {})
    base = f"patients/{P1}/studies/{S1}/series/{uuid.uuid4()}"
    segs["seg-a"] = {"file_id": f"{base}/{uuid.uuid4()}.nii.gz", "description": "Expert Rater 1"}
    segs["seg-b"] = {"file_id": f"{base}/{uuid.uuid4()}.nii.gz", "description": "FLAMeS automatic"}
    segs["zone"] = {"file_id": f"{base}/{uuid.uuid4()}.nii.gz", "description": ZONE_MAP}
    segs["other"] = {"file_id": f"patients/{P2}/studies/{S2}/series/x/y.nii.gz", "description": "Other"}
    items, _ = await world.studies.list_patient_studies(UUID(P1))
    assert items[0].segmentation_count == 2


def test_rc085_prb025_deleting_a_study_removes_it_from_the_list_and_the_counts(world):
    _three_studies(world)
    _act_as(UserRole.RADIOLOGIST, "u-rad")
    world.care.assign(patient_id=P1, user_id="u-rad", role_in_care="attending", granted_by="u-admin")
    assert client.delete(f"/api/v1/studies/{S1}").status_code == 200
    r = client.get(f"/api/v1/studies/patient/{P1}")
    assert r.status_code == 200, r.text
    assert r.json()["items"] == [] and r.json()["total"] == 0
    assert client.get(f"/api/v1/patients/{P1}").json()["study_count"] == 0
    assert world.db.data["studies"][S1]["status"] == "cancelled"          # kept as a record, not erased


def test_rc085_prb025_permanent_deletion_needs_an_administrator(world):
    _three_studies(world)
    _act_as(UserRole.RADIOLOGIST, "u-rad")
    world.care.assign(patient_id=P1, user_id="u-rad", role_in_care="attending", granted_by="u-admin")
    r = client.delete(f"/api/v1/studies/{S1}", params={"hard_delete": "true"})
    assert r.status_code == 403, r.text
    assert world.db.data["studies"][S1]["status"] == "available"


# ============================================================================================
# PRB-026 — the creator of a segmentation is recorded by the server
# ============================================================================================
def test_rc088_prb026_segmentation_records_its_creator(monkeypatch):
    from app.services.segmentation_service import SegmentationService
    svc = object.__new__(SegmentationService)
    svc.segmentations_cache = {}
    monkeypatch.setattr(svc, "_save_segmentation", lambda *_a, **_k: None, raising=False)
    out = svc.create_segmentation(file_id=f"patients/{P1}/studies/{S1}/series/x/f.nii.gz", image_shape=(4, 5, 3),
                                  created_by="dr_demo")
    assert out.metadata.created_by == "dr_demo"
    assert out.metadata.model_dump()["created_by"] == "dr_demo"          # stored with the metadata


def test_rc087_prb026_patient_list_item_carries_given_and_family_name(world):
    _act_as(UserRole.ADMIN, "u-admin")
    items = {i["id"]: i for i in client.get("/api/v1/patients").json()["items"]}
    assert (items[P1]["given_name"], items[P1]["family_name"]) == ("Demo", "Patient (public data)")


def test_rc088_prb026_creator_is_the_authenticated_user_not_a_client_field():
    from app.models.schemas import CreateSegmentationRequest
    req = CreateSegmentationRequest(file_id="x", image_shape={"rows": 1, "columns": 1, "slices": 1},
                                    created_by="someone_else")
    assert "created_by" not in req.model_dump()
