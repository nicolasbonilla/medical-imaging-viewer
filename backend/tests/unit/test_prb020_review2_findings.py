"""Re-review of PR #70 (2026-10-28) — failing-first tests for R1-R6.

- R1 the owner backfill accepted any project id except daita-9f4f6 and empty: it must act ONLY on brain-mri-476110,
     checked before the account list is read or any client is built (RC-083, PRB-023).
- R2 an account without `is_active` counted as active (creator and granter): fail closed (RC-083).
- R3 the undo record: each row id is in the backup BEFORE that row is written; a backup is never overwritten by another
     run; the rows of earlier runs are counted by their `basis` (RC-083).
- R4 regression cases for the password leaks closed by the validation handler: sign-in with an over-long password and a
     refused new password on change-password (RC-081, PRB-020/PRB-024).
- R5 the catch-all 500 handler returned the exception message to the client (RC-081, PRB-020 known issues).
- R6 a profile save fell back to this process's password hash when the store gave none (RC-084, PRB-024).

Offline (PRB-002): in-memory stand-ins only. Negative controls: scripts/safety/prb020_negative_controls.py (W*).
"""
import importlib.util
import io
import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import get_current_active_user
from app.security.models import UserRole
from app.security.user_storage import get_user_storage
import app.api.routes.auth as auth_routes
import app.api.routes.patients as patient_routes

from tests.unit.prb020_fakes import FakeCareTeam, FakeDb, FakeUserStorage, make_user, patient_doc

client = TestClient(app)
SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "owner" / "prb021_backfill_creator_care_team.py"
ASSIGNMENTS = "patient_assignments"
P1 = "11111111-0000-4000-8000-000000000001"
P2 = "22222222-0000-4000-8000-000000000002"


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
# R1-R3 — the owner backfill
# ============================================================================================
def _script():
    spec = importlib.util.spec_from_file_location("prb021_backfill_r2", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


USERS = [
    {"id": "u-admin", "username": "site_admin", "role": "admin", "is_active": True},
    {"id": "u-rad", "username": "dr_rad", "role": "radiologist", "is_active": True},
    {"id": "u-nofield", "username": "dr_nofield", "role": "radiologist"},              # no is_active field
    {"id": "u-admin-nofield", "username": "admin_nofield", "role": "admin"},           # no is_active field
]


def _world(tmp_path, db=None):
    db = db if db is not None else FakeDb()
    pats = db.data.setdefault("patients", {})
    pats[P1] = patient_doc(P1, "Anna", "Beispiel", "MRN-1", created_by="u-rad")
    pats[P2] = patient_doc(P2, "Bert", "NoField", "MRN-2", created_by="u-nofield")
    db.data.setdefault(ASSIGNMENTS, {})
    users = tmp_path / "users.json"
    users.write_text(json.dumps(USERS), encoding="utf-8")
    return {"db": db, "users": str(users), "backups": tmp_path / "backups"}


def _run(w, *extra, answer="ASSIGN", project="brain-mri-476110", granted_by="u-admin", users=None, now=None):
    mod = _script()
    out = io.StringIO()
    argv = ["--project", project, "--users-json", users or w["users"], "--granted-by", granted_by,
            "--backup-dir", str(w["backups"]), *extra]
    rc = mod.main(argv, db=w["db"], input_fn=lambda _p="": answer, out=out, now=now)
    return rc, out.getvalue()


@pytest.mark.parametrize("project", ["mstool-research", "brain-mri-47611", "", "daita-9f4f6", "some-other-project",
                                     "BRAIN-MRI-476110", "brain-mri-476110-copy"])
def test_rc083_prb023_r2_backfill_acts_only_on_the_production_project(tmp_path, project):
    w = _world(tmp_path)
    missing_users = str(tmp_path / "never_read.json")         # the guard comes before the account list is read
    rc, text = _run(w, project=project, users=missing_users)
    assert rc != 0
    assert "REFUSED" in text and "brain-mri-476110" in text and "account list" not in text
    assert w["db"].reads == 0


def test_rc083_prb023_r2_backfill_accepts_the_production_project(tmp_path):
    w = _world(tmp_path)
    rc, text = _run(w)                                        # dry run (no --apply)
    assert rc == 0 and "DRY RUN" in text


def test_rc083_prb023_r2_account_without_is_active_is_not_active(tmp_path):
    w = _world(tmp_path)
    rc, text = _run(w)
    assert rc == 0
    assert f"would assign: patient {P1}" in text and f"would assign: patient {P2}" not in text
    assert "would assign: 1" in text and "inactive account: 1" in text
    rc, text = _run(w, "--apply", granted_by="u-admin-nofield")
    assert rc != 0 and "ACTIVE administrator" in text
    assert w["db"].data[ASSIGNMENTS] == {}


class _CheckingDb(FakeDb):
    """Firestore stand-in whose assignment writes first check that the row id is already in the run's backup."""

    def __init__(self, backups):
        super().__init__()
        self.backups = backups
        self.checked = []

    def collection(self, name):
        q = super().collection(name)
        if name != ASSIGNMENTS:
            return q
        db = self
        real_document = q.document

        def document(doc_id=None):
            ref = real_document(doc_id)
            real_set = ref.set

            def set_(data, merge=False):
                files = sorted(db.backups.glob("prb021_backfill_*.json"))
                assert files, "no backup before the first write"
                saved = json.loads(files[-1].read_text(encoding="utf-8"))
                assert ref.id in saved["attempted_assignment_ids"], "row written before its id was in the backup"
                db.checked.append(ref.id)
                return real_set(data, merge=merge)
            ref.set = set_
            return ref
        q.document = document
        return q


def test_rc083_prb023_r2_each_row_id_is_in_the_backup_before_it_is_written(tmp_path):
    db = _CheckingDb(tmp_path / "backups")
    w = _world(tmp_path, db=db)
    w["db"].data["patients"][P2]["created_by"] = "u-admin"      # one row to write, P1
    rc, text = _run(w, "--apply")
    assert rc == 0, text
    assert len(db.checked) == 1
    saved = json.loads(sorted(w["backups"].glob("prb021_backfill_*.json"))[-1].read_text(encoding="utf-8"))
    assert saved["created_assignment_ids"] == db.checked == saved["attempted_assignment_ids"]


def test_rc083_prb023_r2_a_run_never_overwrites_another_runs_backup(tmp_path):
    import datetime
    w = _world(tmp_path)
    same_second = datetime.datetime(2026, 10, 28, 12, 0, 0, tzinfo=datetime.timezone.utc)
    assert _run(w, "--apply", now=same_second)[0] == 0
    first = sorted(w["backups"].glob("prb021_backfill_*.json"))
    assert len(first) == 1
    first_text = first[0].read_text(encoding="utf-8")
    pid = str(uuid.uuid4())
    w["db"].data["patients"][pid] = patient_doc(pid, "Carl", "Later", "MRN-9", created_by="u-rad")
    assert _run(w, "--apply", now=same_second)[0] == 0
    files = sorted(w["backups"].glob("prb021_backfill_*.json"))
    assert len(files) == 2
    assert first[0].read_text(encoding="utf-8") == first_text


def test_rc083_prb023_r2_earlier_runs_are_counted_and_the_undo_by_basis_documented(tmp_path):
    w = _world(tmp_path)
    assert _run(w, "--apply")[0] == 0
    rc, text = _run(w)
    assert rc == 0 and "rows from earlier backfill runs (basis prb021_backfill_created_by): 1" in text
    doc = _script().__doc__
    assert "basis" in doc and "prb021_backfill_created_by" in doc and "revoke every row" in doc


# ============================================================================================
# R4 — the other password paths through the validation handler
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


def _capture_handler_logs(monkeypatch):
    import app.core.exception_handlers as handlers
    logged = []
    monkeypatch.setattr(handlers.logger, "warning", lambda msg, *a, **k: logged.append((msg, k.get("extra"))))
    monkeypatch.setattr(handlers.logger, "error", lambda msg, *a, **k: logged.append((msg, k.get("extra"))))
    return logged


def test_rc081_prb020_r2_sign_in_with_an_over_long_password_leaks_nothing(store, monkeypatch):
    logged = _capture_handler_logs(monkeypatch)
    secret = "zqxSECRETpwA1!" + "x" * 130
    r = client.post("/api/v1/auth/login", json={"username": "nobody", "password": secret},
                    headers={"X-Forwarded-For": "198.51.100.201"})
    assert r.status_code == 400, r.text
    assert "zqxSECRETpw" not in r.text and "zqxSECRETpw" not in repr(logged)


def test_rc084_prb024_r2_a_refused_new_password_leaks_nothing(store, monkeypatch):
    logged = _capture_handler_logs(monkeypatch)
    _act_as(UserRole.RADIOLOGIST, uid="u-pw", username="pw_user")
    r = client.post("/api/v1/auth/change-password",
                    json={"current_password": "zqxCurrent1!aaaa", "new_password": "zqxSECRETweak"})
    assert r.status_code == 400, r.text
    assert "zqxSECRETweak" not in r.text and "zqxSECRETweak" not in repr(logged)


# ============================================================================================
# R5 — the catch-all 500 handler returns no internal detail
# ============================================================================================
class _BrokenPatients:
    async def create_patient(self, data, created_by=None):
        raise RuntimeError("internal-detail-zqx: connection string user=svc password=hunter2")


def test_rc081_prb020_r2_unexpected_errors_return_no_internal_detail(monkeypatch):
    logged = _capture_handler_logs(monkeypatch)
    app.dependency_overrides[patient_routes.get_patient_service] = lambda: _BrokenPatients()
    app.dependency_overrides[patient_routes.get_care_team_service] = lambda: FakeCareTeam()
    _act_as(UserRole.ADMIN, uid="u-admin", username="site_admin")
    body = {"mrn": "BODY-MRN-ZQX-77", "given_name": "Anna", "family_name": "Beispiel", "birth_date": "1990-05-01",
            "gender": "female", "phone_mobile": "+491701234567", "country": "DEU"}
    r = TestClient(app, raise_server_exceptions=False).post("/api/v1/patients", json=body)
    assert r.status_code == 500
    assert "internal-detail-zqx" not in r.text and "hunter2" not in r.text and "RuntimeError" not in r.text
    assert r.json()["error"]["message"] == "An unexpected error occurred"
    server_side = repr(logged)
    assert "RuntimeError" in server_side                       # the detail stays in the server log
    assert "BODY-MRN-ZQX-77" not in server_side                # the request body is not logged


# ============================================================================================
# R6 — a profile save refuses when the store gives no password, whatever this process remembers
# ============================================================================================
@pytest.mark.parametrize("store_answer", ["error", "nothing"])
def test_rc084_prb024_r2_profile_save_never_uses_the_remembered_hash(store, monkeypatch, store_answer):
    user = make_user("stale_memory", UserRole.VIEWER)
    store.save_user(user, "hash-current", ["hash-current", "hash-old"])
    auth_routes.auth_service._user_passwords[user.id] = "hash-old"        # this instance's stale copy
    auth_routes.auth_service._password_history[user.id] = ["hash-old"]

    def unreadable(_uid):
        if store_answer == "error":
            raise OSError("store unavailable")
        return None
    monkeypatch.setattr(store, "get_user_password_data", unreadable)
    _act_as(UserRole.ADMIN, uid="u-admin", username="site_admin")
    r = client.patch(f"/api/v1/auth/users/{user.id}", json={"role": "radiologist"})
    assert r.status_code == 503, r.text
    assert store.passwords[user.id] == {"password_hash": "hash-current", "password_history": ["hash-current", "hash-old"]}
    assert store.get_user_by_id(user.id).role == UserRole.VIEWER
