"""Independent review of PR #70 (2026-10-28) — failing-first tests for its findings M1, M2, m1-m4, m8, m9.

- M1  DELETE /studies/series/{id} and /studies/instances/{id} erased storage with only the care-team check (a VIEWER
      on the care team could erase images); now IMAGE_DELETE (administrator) — RC-085, PRB-025.
- M2  the study soft delete (and a status change through PUT) had no role check, and since PRB-025 a cancelled study is
      hidden for everyone; now PATIENT_UPDATE (radiologist, administrator) — RC-085, PRB-025.
- m1  the audit event of an administrator-created account named the new account as actor and /auth/register as route.
- m2  a profile save (administrator PATCH, passkey sign-in) wrote an empty password hash when the password data could not
      be read, and always erased the password history — RC-084, PRB-024.
- m3  deleting an account answered 204 when the user store had not deleted it — RC-084, PRB-024.
- m4  production was recognised by the exact word "production"; any other spelling opened self-registration when the
      setting was on — RC-080, PRB-020.
- m8  test gaps: the segmentation route passes the authenticated user; the administrator route applies the password policy.
- m9  (PRB-027) the PACS patient search and import were open to every role, a VIEWER included.

Offline (PRB-002): in-memory user store, Firestore stand-in, care-team store and storage.
Negative controls: scripts/safety/prb020_negative_controls.py (mutations V1.., added after the review).
"""
import itertools
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import get_current_active_user
from app.security.models import UserRole
from app.security.user_storage import get_user_storage
from app.services.patient_service_firestore import PatientServiceFirestore
from app.services.study_service_firestore import StudyServiceFirestore
import app.api.routes.auth as auth_routes
import app.api.routes.patients as patient_routes
import app.api.routes.studies as study_routes
import app.security.patient_access_dependency as pad
import app.security.resource_access as ra

from tests.unit.prb020_fakes import FakeCareTeam, FakeDb, FakeUserStorage, make_user, patient_doc, setting, study_doc

client = TestClient(app)
PASSWORD = "Str0ng!Passw0rd-2026"
P1 = "11111111-1111-4111-8111-111111111111"
S1 = "a1111111-1111-4111-8111-111111111111"
_ips = itertools.count(1)


def _ip():
    return {"X-Forwarded-For": f"203.0.113.{next(_ips) % 250 + 1}"}


@pytest.fixture(autouse=True)
def _restore_overrides():
    saved = dict(app.dependency_overrides)
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(saved)


def _act_as(role, uid="u-actor", username="actor"):
    user = make_user(username, role, uid=uid)
    app.dependency_overrides[get_current_active_user] = lambda: user
    return user


# ============================================================================================
# M1 / M2 — image deletion and study cancellation need a write permission
# ============================================================================================
class FakeStorage:
    def __init__(self):
        self.deleted = []

    async def delete_file(self, name):
        self.deleted.append(("file", name))

    async def delete_prefix(self, prefix):
        self.deleted.append(("prefix", prefix))


@pytest.fixture
def imaging(monkeypatch):
    db, care, storage = FakeDb(), FakeCareTeam(), FakeStorage()
    patients = object.__new__(PatientServiceFirestore)
    patients.db, patients.collection = db, "patients"
    studies = object.__new__(StudyServiceFirestore)
    studies.db, studies.storage = db, storage
    ser, inst = str(uuid.uuid4()), str(uuid.uuid4())
    db.data["patients"] = {P1: patient_doc(P1, "Anna", "Beispiel", "MRN-1", created_by="u-other")}
    db.data["studies"] = {S1: study_doc(S1, P1)}
    db.data[f"studies/{S1}/series"] = {ser: {
        "id": ser, "study_id": S1, "series_instance_uid": "2.25.1", "series_number": 1, "modality": "MR",
        "status": "available", "created_at": "2026-10-28T10:00:00", "gcs_path": f"patients/{P1}/studies/{S1}/series/{ser}"}}
    db.data[f"studies/{S1}/series/{ser}/instances"] = {inst: {
        "id": inst, "series_id": ser, "study_id": S1, "sop_instance_uid": "2.25.2", "original_filename": "f.nii.gz",
        "file_size_bytes": 1, "content_type": "application/gzip", "checksum_sha256": "0" * 64,
        "created_at": "2026-10-28T10:00:00", "gcs_object_name": f"patients/{P1}/studies/{S1}/series/{ser}/{inst}.nii.gz"}}
    for uid in ("u-viewer", "u-tech", "u-rad"):
        care.assign(patient_id=P1, user_id=uid, role_in_care="consulting", granted_by="u-admin")
    app.dependency_overrides[patient_routes.get_patient_service] = lambda: patients
    app.dependency_overrides[patient_routes.get_care_team_service] = lambda: care
    app.dependency_overrides[study_routes.get_study_service] = lambda: studies
    monkeypatch.setattr(pad, "_get_patient_service", lambda: patients)
    monkeypatch.setattr(pad, "_get_care_team_service", lambda: care)
    monkeypatch.setattr(ra, "_patient_service", lambda: patients)
    monkeypatch.setattr(ra, "_care_team_service", lambda: care)
    monkeypatch.setattr(ra, "_study_service", lambda: studies)
    return {"db": db, "storage": storage, "series": ser, "instance": inst}


@pytest.mark.parametrize("role,uid", [(UserRole.VIEWER, "u-viewer"), (UserRole.TECHNICIAN, "u-tech"),
                                      (UserRole.RADIOLOGIST, "u-rad")])
def test_rc085_prb025_r1_only_an_administrator_erases_a_series_or_an_image(imaging, role, uid):
    _act_as(role, uid=uid)
    assert client.delete(f"/api/v1/studies/instances/{imaging['instance']}").status_code == 403
    assert client.delete(f"/api/v1/studies/series/{imaging['series']}").status_code == 403
    assert imaging["storage"].deleted == []
    assert imaging["instance"] in imaging["db"].data[f"studies/{S1}/series/{imaging['series']}/instances"]
    assert imaging["series"] in imaging["db"].data[f"studies/{S1}/series"]


def test_rc085_prb025_r1_an_administrator_still_erases_a_series_and_an_image(imaging):
    _act_as(UserRole.ADMIN, uid="u-admin")
    assert client.delete(f"/api/v1/studies/instances/{imaging['instance']}").status_code == 200
    assert client.delete(f"/api/v1/studies/series/{imaging['series']}").status_code == 200
    assert [kind for kind, _ in imaging["storage"].deleted] == ["file", "prefix"]


@pytest.mark.parametrize("role,uid", [(UserRole.VIEWER, "u-viewer"), (UserRole.TECHNICIAN, "u-tech")])
def test_rc085_prb025_r1_cancelling_a_study_needs_a_write_permission(imaging, role, uid):
    _act_as(role, uid=uid)
    assert client.delete(f"/api/v1/studies/{S1}").status_code == 403
    assert imaging["db"].data["studies"][S1]["status"] == "available"


def test_rc085_prb025_r1_a_radiologist_cancels_and_restores_a_study(imaging):
    _act_as(UserRole.RADIOLOGIST, uid="u-rad")
    assert client.delete(f"/api/v1/studies/{S1}").status_code == 200
    assert imaging["db"].data["studies"][S1]["status"] == "cancelled"
    r = client.put(f"/api/v1/studies/{S1}", json={"status": "available"})
    assert r.status_code == 200, r.text
    assert imaging["db"].data["studies"][S1]["status"] == "available"


def test_rc085_prb025_r1_a_status_change_through_update_needs_the_same_permission(imaging):
    _act_as(UserRole.VIEWER, uid="u-viewer")
    assert client.put(f"/api/v1/studies/{S1}", json={"status": "cancelled"}).status_code == 403
    assert imaging["db"].data["studies"][S1]["status"] == "available"
    # Editing the description is unchanged by this fix (positive control).
    r = client.put(f"/api/v1/studies/{S1}", json={"study_description": "Brain MRI (follow-up)"})
    assert r.status_code == 200, r.text


# ============================================================================================
# m1 .. m4, m8 — accounts
# ============================================================================================
@pytest.fixture
def store(monkeypatch):
    s = FakeUserStorage()
    svc = auth_routes.auth_service
    for name, value in (("_storage", s), ("_users", {}), ("_user_passwords", {}), ("_password_history", {}),
                        ("_audit_logs", [])):
        monkeypatch.setattr(svc, name, value)
    app.dependency_overrides[get_user_storage] = lambda: s
    return s


def _new_account(role="radiologist", username="dr_new"):
    return {"username": username, "email": f"{username}@clinic.example.org", "full_name": "Dr New",
            "password": PASSWORD, "role": role}


def test_rc081_prb020_r1_audit_of_an_admin_created_account_names_the_administrator(store):
    admin = _act_as(UserRole.ADMIN, uid="u-admin", username="site_admin")
    r = client.post("/api/v1/auth/users", json=_new_account("admin", "second_admin"))
    assert r.status_code == 201, r.text
    new_id = r.json()["id"]
    events = [e for e in auth_routes.auth_service._audit_logs if e.action == "register_user"]
    assert len(events) == 1
    ev = events[0]
    assert ev.user_id == admin.id
    assert ev.resource == "/auth/users"
    assert ev.details["target_user_id"] == new_id and ev.details["role"] == "admin"
    privileged = [e for e in auth_routes.auth_service._audit_logs if e.action == "privileged_account_created"]
    assert len(privileged) == 1 and privileged[0].user_id == admin.id
    assert privileged[0].details["target_user_id"] == new_id


@pytest.mark.parametrize("password", ["short1!A", "alllowercase-2026!", "NoDigitsHere!!!x", "NoSpecial2026abc"])
def test_rc081_prb020_r1_administrator_route_applies_the_password_policy(store, password, monkeypatch):
    """A refused password is a 400 with the reason — it was a 500 (the validator's error could not be written as
    JSON) — and the password as typed is neither returned nor logged."""
    import app.core.exception_handlers as handlers
    logged = []
    monkeypatch.setattr(handlers.logger, "warning", lambda msg, *a, **k: logged.append((msg, k.get("extra"))))
    _act_as(UserRole.ADMIN, uid="u-admin", username="site_admin")
    body = {**_new_account(), "password": password}
    r = client.post("/api/v1/auth/users", json=body)
    assert r.status_code == 400, r.text
    assert "password" in r.text and password not in r.text
    assert logged and password not in repr(logged)
    assert store.users == {}


def test_rc084_prb024_r1_role_change_keeps_the_password_and_its_history(store):
    user = make_user("keeps_history", UserRole.VIEWER)
    store.save_user(user, "hash-3", ["hash-3", "hash-2", "hash-1"])
    _act_as(UserRole.ADMIN, uid="u-admin", username="site_admin")
    r = client.patch(f"/api/v1/auth/users/{user.id}", json={"role": "radiologist"})
    assert r.status_code == 200, r.text
    assert store.passwords[user.id] == {"password_hash": "hash-3", "password_history": ["hash-3", "hash-2", "hash-1"]}


def test_rc084_prb024_r1_profile_is_not_saved_without_the_password(store, monkeypatch):
    user = make_user("unreadable_pw", UserRole.VIEWER)
    store.save_user(user, "hash-9", ["hash-9"])
    monkeypatch.setattr(store, "get_user_password_data", lambda _uid: None)   # read error swallowed by the store
    _act_as(UserRole.ADMIN, uid="u-admin", username="site_admin")
    r = client.patch(f"/api/v1/auth/users/{user.id}", json={"role": "radiologist"})
    assert r.status_code == 503, r.text
    assert store.passwords[user.id]["password_hash"] == "hash-9"
    assert store.get_user_by_id(user.id).role == UserRole.VIEWER


class _FakeWebAuthn:
    def verify_authentication(self, user_id, credential_json):
        return True


@pytest.mark.parametrize("readable", [True, False])
def test_rc084_prb024_r1_passkey_sign_in_never_writes_an_empty_password(store, monkeypatch, readable):
    user = make_user("passkey_user", UserRole.RADIOLOGIST)
    store.save_user(user, "hash-pk", ["hash-pk", "hash-old"])
    auth_routes.auth_service._users[user.id] = store.get_user_by_id(user.id)
    monkeypatch.setattr(auth_routes, "_get_webauthn_service", lambda: _FakeWebAuthn())
    if not readable:
        monkeypatch.setattr(store, "get_user_password_data", lambda _uid: None)
    app.dependency_overrides.pop(get_current_active_user, None)
    r = client.post("/api/v1/auth/webauthn/login/complete", json={"username": "passkey_user", "credential": {}})
    assert r.status_code == 200, r.text
    assert store.passwords[user.id] == {"password_hash": "hash-pk", "password_history": ["hash-pk", "hash-old"]}


def test_rc084_prb024_r1_delete_the_store_refused_is_reported(store, monkeypatch):
    user = make_user("hard_to_delete", UserRole.VIEWER)
    store.save_user(user, "hash-d")
    monkeypatch.setattr(store, "delete_user", lambda _uid: False)
    _act_as(UserRole.ADMIN, uid="u-admin", username="site_admin")
    r = client.delete(f"/api/v1/auth/users/{user.id}")
    assert r.status_code == 503, r.text
    assert "hard_to_delete" in [u["username"] for u in client.get("/api/v1/auth/users").json()]


@pytest.mark.parametrize("env", ["prod", "Production ", "staging", "", "live", "PRODUCTION"])
def test_rc080_prb020_r1_an_unknown_environment_counts_as_production(store, env):
    with setting("SELF_REGISTRATION_ENABLED", True), setting("ENVIRONMENT", env):
        body = {"username": "env_user", "email": "env.user@clinic.example.org", "full_name": "Env User",
                "password": PASSWORD, "confirm_password": PASSWORD}
        assert client.post("/api/v1/auth/register", json=body, headers=_ip()).status_code == 404
        assert client.get("/api/v1/auth/registration").json()["self_registration_enabled"] is False
    assert store.users == {}


@pytest.mark.parametrize("env", ["development", "local", "test", "testing"])
def test_rc080_prb020_r1_named_non_production_environments_allow_it_when_set(store, env):
    with setting("SELF_REGISTRATION_ENABLED", True), setting("ENVIRONMENT", env):
        assert client.get("/api/v1/auth/registration").json()["self_registration_enabled"] is True


# ============================================================================================
# m6 — the per-patient count queries of one page run concurrently, with the same results
# ============================================================================================
class _SlowCountDb(FakeDb):
    """Firestore stand-in whose aggregation queries take `delay` seconds each (a network round trip)."""

    def __init__(self, delay):
        super().__init__()
        self.delay = delay

    def collection(self, name):
        q = super().collection(name)
        db = self

        class _Slow(type(q)):
            def _copy(self, **kw):
                c = super()._copy(**kw)
                c.__class__ = _Slow
                return c

            def count(self):
                import time
                time.sleep(db.delay)
                return super().count()
        q.__class__ = _Slow
        return q


async def test_rc085_prb025_r1_page_counts_run_concurrently_with_the_same_results():
    import time
    db = _SlowCountDb(delay=0.05)
    svc = object.__new__(PatientServiceFirestore)
    svc.db, svc.collection = db, "patients"
    pats, studies, docs = db.data.setdefault("patients", {}), db.data.setdefault("studies", {}), db.data.setdefault("documents", {})
    for i in range(20):
        pid = str(uuid.UUID(int=i + 1))
        pats[pid] = patient_doc(pid, f"G{i:02d}", f"F{i:02d}", f"MRN-{i}")
        for j in range(i % 3 + 1):
            sid = str(uuid.uuid4())
            studies[sid] = study_doc(sid, pid, "cancelled" if j == 0 and i % 2 else "available")
        docs[f"d{i}"] = {"id": f"d{i}", "patient_id": pid, "status": "current"}
    t0 = time.perf_counter()
    items, total = await svc.list_patients(page_size=20)
    elapsed = time.perf_counter() - t0
    # 20 patients x 5 aggregation queries x 50 ms = 5 s one after another.
    assert elapsed < 2.5, f"page counts took {elapsed:.2f} s"
    expected = {str(uuid.UUID(int=i + 1)): ((i % 3 + 1) - (1 if i % 2 else 0), 1) for i in range(20)}
    assert {str(s.id): (s.study_count, s.document_count) for s in items} == expected and total == 20


# ============================================================================================
# m8 — the segmentation route records the authenticated user
# ============================================================================================
def test_rc088_prb026_r1_the_route_records_the_authenticated_user(monkeypatch):
    from app.services.segmentation_service import SegmentationService
    import app.api.routes.segmentation as seg_routes
    from app.core.container import get_segmentation_service
    svc = object.__new__(SegmentationService)
    svc.segmentations_cache = {}
    monkeypatch.setattr(svc, "_save_segmentation", lambda *_a, **_k: None, raising=False)

    async def _allowed(*_a, **_k):
        return None
    monkeypatch.setattr(seg_routes, "require_imaging_access", _allowed)
    app.dependency_overrides[get_segmentation_service] = lambda: svc
    _act_as(UserRole.RADIOLOGIST, uid="u-rad", username="dr_route")
    body = {"file_id": f"patients/{P1}/studies/{S1}/series/x/f.nii.gz",
            "image_shape": {"rows": 4, "columns": 5, "slices": 3}, "created_by": "someone_else"}
    r = client.post("/api/v1/segmentation/create", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["metadata"]["created_by"] == "dr_route"


# ============================================================================================
# m9 / PRB-027 — the PACS patient search and import are not open to every role
# ============================================================================================
class _FakePacs:
    def __init__(self):
        self.calls = []

    async def search_studies(self, connection_id, params):
        self.calls.append("search_studies")
        return []

    async def search_series(self, connection_id, study_uid):
        self.calls.append("search_series")
        return []

    async def start_import(self, **_kw):
        self.calls.append("start_import")
        return "job-1"


PACS_CALLS = [
    ("/api/v1/dicomweb/search/studies", {"connection_id": "c1", "patient_name": "Muster*"}),
    ("/api/v1/dicomweb/search/series?connection_id=c1&study_instance_uid=1.2.3", None),
    ("/api/v1/dicomweb/import", {"connection_id": "c1", "study_instance_uid": "1.2.3",
                                 "series_instance_uid": "1.2.3.4", "patient_id": P1}),
]


@pytest.mark.parametrize("path,body", PACS_CALLS)
def test_rc089_prb027_a_viewer_cannot_search_or_import_from_the_pacs(imaging, monkeypatch, path, body):
    import app.api.routes.dicomweb as dicomweb_routes
    pacs = _FakePacs()
    monkeypatch.setattr(dicomweb_routes, "_get_dicomweb_service", lambda: pacs)
    _act_as(UserRole.VIEWER, uid="u-viewer")          # on the patient's care team
    r = client.post(path, json=body) if body is not None else client.post(path)
    assert r.status_code == 403, r.text
    assert pacs.calls == []                           # the PACS was never asked


@pytest.mark.parametrize("path,body", PACS_CALLS)
def test_rc089_prb027_a_technician_still_searches_and_imports(imaging, monkeypatch, path, body):
    import app.api.routes.dicomweb as dicomweb_routes
    pacs = _FakePacs()
    monkeypatch.setattr(dicomweb_routes, "_get_dicomweb_service", lambda: pacs)
    _act_as(UserRole.TECHNICIAN, uid="u-tech")
    r = client.post(path, json=body) if body is not None else client.post(path)
    assert r.status_code == 200, r.text
    assert len(pacs.calls) == 1
