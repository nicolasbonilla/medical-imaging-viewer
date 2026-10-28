"""PRB-020 (open self-registration) and PRB-024 (new accounts invisible to the administrator) — HAZ-010.

Found in the browser capture of the release candidate (2026-10-28, findings F21 and F17,
`mstool-film/assets/app-captures/CAPTURES.md` §5):

- PRB-020: `POST /api/v1/auth/register` is public. Anyone who can reach the server creates a VIEWER
  account, with no e-mail verification, and the login page offers a "Register" tab. Offering a device
  that is not CE-marked to any clinician who signs up can count as "making available" (EU MDR arts.
  2(27), 6). Wanted: self-registration OFF unless an explicit setting turns it on, never in production;
  accounts created by an administrator (`POST /api/v1/auth/users`); a public status endpoint so the
  login page can hide the tab.
- PRB-024: an account written to the user store after the server started (by the register route, by
  another server instance) is missing from `GET /auth/users` and cannot be changed by the administrator
  (`PATCH` answered 500) until the server restarts: the administrator routes read `AuthService`'s
  in-memory copy, loaded once at start-up.

Every test runs with no cloud credential (PRB-002) and in-memory stores.
Negative controls: scripts/safety/prb020_negative_controls.py.
"""
import itertools

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import get_current_active_user
from app.security.models import UserRole
from app.security.user_storage import get_user_storage
import app.api.routes.auth as auth_routes

from tests.unit.prb020_fakes import FakeUserStorage, make_user, setting

client = TestClient(app)
_ips = itertools.count(1)
PASSWORD = "Str0ng!Passw0rd-2026"


def _ip():
    """A distinct client address per request: the register route is rate-limited per address."""
    return {"X-Forwarded-For": f"198.51.100.{next(_ips) % 250 + 1}"}


def _registration(username="new_clinician"):
    return {"username": username, "email": f"{username}@clinic.example.org", "full_name": "New Clinician",
            "password": PASSWORD, "confirm_password": PASSWORD}


@pytest.fixture
def store(monkeypatch):
    """One persistent user store, seen by the register route and by AuthService (as in production)."""
    s = FakeUserStorage()
    svc = auth_routes.auth_service
    monkeypatch.setattr(svc, "_storage", s)
    monkeypatch.setattr(svc, "_users", {})
    monkeypatch.setattr(svc, "_user_passwords", {})
    monkeypatch.setattr(svc, "_password_history", {})
    saved = dict(app.dependency_overrides)
    app.dependency_overrides[get_user_storage] = lambda: s
    yield s
    app.dependency_overrides.clear()
    app.dependency_overrides.update(saved)


def _act_as(role, uid="u-actor", username="actor"):
    user = make_user(username, role, uid=uid)
    app.dependency_overrides[get_current_active_user] = lambda: user
    return user


# ============================================================================================
# PRB-020 — self-registration off by default, never in production; administrator creates accounts
# ============================================================================================
def test_rc080_prb020_self_registration_setting_is_off_by_default(monkeypatch):
    from app.core.config import Settings
    monkeypatch.delenv("SELF_REGISTRATION_ENABLED", raising=False)
    assert Settings().SELF_REGISTRATION_ENABLED is False


def test_rc080_prb020_register_is_refused_when_self_registration_is_off(store):
    r = client.post("/api/v1/auth/register", json=_registration(), headers=_ip())
    assert r.status_code == 404, r.text
    assert store.users == {}, "no account may be created while self-registration is off"


def test_rc080_prb020_register_works_only_when_the_setting_is_on_outside_production(store):
    with setting("SELF_REGISTRATION_ENABLED", True), setting("ENVIRONMENT", "testing"):
        r = client.post("/api/v1/auth/register", json=_registration("opt_in_user"), headers=_ip())
    assert r.status_code == 201, r.text
    assert r.json()["user"]["role"] == UserRole.VIEWER.value
    assert [u.username for u in store.users.values()] == ["opt_in_user"]


def test_rc080_prb020_production_never_allows_self_registration(store):
    with setting("SELF_REGISTRATION_ENABLED", True), setting("ENVIRONMENT", "production"):
        r = client.post("/api/v1/auth/register", json=_registration("prod_user"), headers=_ip())
    assert r.status_code == 404, r.text
    assert store.users == {}


def test_rc080_prb020_registration_status_is_public_and_states_the_policy():
    app.dependency_overrides.pop(get_current_active_user, None)
    r = client.get("/api/v1/auth/registration")          # no Authorization header
    assert r.status_code == 200, r.text
    assert r.json() == {"self_registration_enabled": False, "account_creation": "administrator"}
    with setting("SELF_REGISTRATION_ENABLED", True), setting("ENVIRONMENT", "testing"):
        assert client.get("/api/v1/auth/registration").json()["self_registration_enabled"] is True
    with setting("SELF_REGISTRATION_ENABLED", True), setting("ENVIRONMENT", "production"):
        assert client.get("/api/v1/auth/registration").json()["self_registration_enabled"] is False


def test_rc081_prb020_administrator_creates_an_account_with_its_role(store):
    admin = _act_as(UserRole.ADMIN, uid="u-admin", username="site_admin")
    body = {"username": "dr_neuro", "email": "dr.neuro@clinic.example.org", "full_name": "Dr Neuro",
            "password": PASSWORD, "role": "radiologist"}
    r = client.post("/api/v1/auth/users", json=body)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["username"] == "dr_neuro" and out["role"] == "radiologist"
    assert "password" not in out and "password_hash" not in out
    stored = store.get_user_by_username("dr_neuro")
    assert stored is not None and stored.role == UserRole.RADIOLOGIST
    assert stored.created_by == admin.id
    assert store.passwords[stored.id]["password_hash"] != PASSWORD          # hashed, never stored as typed
    # The new account is visible to the administrator at once (PRB-024 too).
    listed = client.get("/api/v1/auth/users").json()
    assert "dr_neuro" in [u["username"] for u in listed]


@pytest.mark.parametrize("role", [UserRole.VIEWER, UserRole.TECHNICIAN, UserRole.RADIOLOGIST])
def test_rc081_prb020_only_an_administrator_creates_accounts(store, role):
    _act_as(role)
    body = {"username": "sneaky_user", "email": "sneaky@clinic.example.org", "full_name": "Sneaky",
            "password": PASSWORD, "role": "admin"}
    r = client.post("/api/v1/auth/users", json=body)
    assert r.status_code == 403, r.text
    assert store.users == {}


def test_rc081_prb020_account_creation_refuses_a_name_already_in_the_store(store):
    # Written by another server instance after this one started.
    store.save_user(make_user("taken_name", UserRole.VIEWER), "argon2-hash")
    _act_as(UserRole.ADMIN, uid="u-admin", username="site_admin")
    body = {"username": "taken_name", "email": "other@clinic.example.org", "full_name": "Other",
            "password": PASSWORD, "role": "technician"}
    r = client.post("/api/v1/auth/users", json=body)
    assert r.status_code == 400, r.text
    assert len(store.users) == 1


# ============================================================================================
# PRB-024 — the administrator sees and manages accounts created after start-up
# ============================================================================================
def test_rc084_prb024_account_registered_after_start_is_listed_for_the_administrator(store):
    with setting("SELF_REGISTRATION_ENABLED", True), setting("ENVIRONMENT", "testing"):
        assert client.post("/api/v1/auth/register", json=_registration("late_user"), headers=_ip()).status_code == 201
    _act_as(UserRole.ADMIN, uid="u-admin", username="site_admin")
    r = client.get("/api/v1/auth/users")
    assert r.status_code == 200, r.text
    assert "late_user" in [u["username"] for u in r.json()]


def test_rc084_prb024_administrator_changes_the_role_of_an_account_created_after_start(store):
    late = make_user("late_radiologist", UserRole.VIEWER)
    store.save_user(late, "argon2-hash")                    # e.g. written by another instance
    _act_as(UserRole.ADMIN, uid="u-admin", username="site_admin")
    r = client.get(f"/api/v1/auth/users/{late.id}")
    assert r.status_code == 200, r.text
    r = client.patch(f"/api/v1/auth/users/{late.id}", json={"role": "radiologist"})
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "radiologist"
    assert store.get_user_by_id(late.id).role == UserRole.RADIOLOGIST
    assert store.passwords[late.id]["password_hash"] == "argon2-hash"   # the password is kept


def test_rc084_prb024_account_the_store_did_not_take_is_not_created(store, monkeypatch):
    def refuse(*_a, **_k):
        raise OSError("store unavailable")
    monkeypatch.setattr(store, "save_user", refuse)
    _act_as(UserRole.ADMIN, uid="u-admin", username="site_admin")
    body = {"username": "phantom", "email": "phantom@clinic.example.org", "full_name": "Phantom",
            "password": PASSWORD, "role": "viewer"}
    r = client.post("/api/v1/auth/users", json=body)
    assert r.status_code == 503, r.text
    assert "phantom" not in [u.username for u in auth_routes.auth_service._users.values()]


def test_rc084_prb024_failed_sign_in_is_stored_and_the_password_kept(store):
    from fastapi import HTTPException
    from app.security.models import LoginRequest, UserCreate
    svc = auth_routes.auth_service
    user = svc.register_user(UserCreate(username="lock_me", email="lock.me@clinic.example.org", full_name="Lock Me",
                                        password=PASSWORD, role=UserRole.VIEWER))
    stored_hash = store.passwords[user.id]["password_hash"]
    with pytest.raises(HTTPException):
        svc.login(LoginRequest(username="lock_me", password="Wr0ng!Password789"))
    assert store.get_user_by_id(user.id).failed_login_attempts == 1      # visible to every instance
    assert store.passwords[user.id]["password_hash"] == stored_hash       # never overwritten
    svc.login(LoginRequest(username="lock_me", password=PASSWORD))
    assert store.get_user_by_id(user.id).failed_login_attempts == 0


def test_rc084_prb024_account_deleted_elsewhere_is_no_longer_listed(store):
    gone = make_user("gone_user", UserRole.VIEWER)
    store.save_user(gone, "argon2-hash")
    _act_as(UserRole.ADMIN, uid="u-admin", username="site_admin")
    assert "gone_user" in [u["username"] for u in client.get("/api/v1/auth/users").json()]
    store.delete_user(gone.id)                               # deleted by another instance
    assert "gone_user" not in [u["username"] for u in client.get("/api/v1/auth/users").json()]
    assert client.get(f"/api/v1/auth/users/{gone.id}").status_code == 404
