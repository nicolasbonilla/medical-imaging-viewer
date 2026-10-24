"""CAPA-015 — independent adversarial review of PR #65 (2026-10-24): backend findings.

M1  the refresh-session idle limit must outlive the access token (startup refuses otherwise);
    login and refresh tell the client when the refresh session ends; templates emit 15 min.
M3  /api/v1/auth/* requests without an explicit audit event were not recorded (passkey
    registration and deletion, user list/detail reads, any 5xx, logout with an unknown cookie).
m5  a lost refresh response or a two-tab race looked like token theft: a short grace window now
    returns the same successor for the immediately previous token; real reuse still revokes.
m6  a transient user-store error revoked the session family (the lookup returned None on any
    error): now 503 and the token is kept.
m8  store calls of /refresh and /logout ran on the event loop; "revoke every session" touched
    expired and revoked families too.
m9  the client IP (audit record, rate-limit key) trusted the client-controlled first
    X-Forwarded-For hop; a flood of failed/anonymous requests could fill the audit queue; one old
    dropped record kept the administrator banner red forever.
m10 identifiers were hashed with plain SHA-256 (reversible for small spaces such as MRNs);
    the full user agent was stored.

Written before the fixes; they fail on the PR #65 head (2c618ec) — record
docs/iec62304/records/risk_verification/CAPA-015_review1_tests_on_pr65_2026-10-24.json.
"""
import asyncio
import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.unit.capa015_fakes import FakeFirestore, fake_transactional
from tests.unit.test_capa015_audit_and_session import (  # noqa: F401  (env is a fixture)
    env, _login, _cookie, _refresh, _mod, keyed, PASSWORD, SEG,
)

ROOT = Path(__file__).resolve().parents[3]


# =============================================================================== M1
@pytest.mark.unit
def test_rc068_startup_refuses_a_refresh_idle_limit_not_longer_than_the_access_token():
    from pydantic import ValidationError
    from app.core.config import SecuritySettings
    secret = "x" * 40
    ok = SecuritySettings(JWT_SECRET_KEY=secret, JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15, REFRESH_TOKEN_IDLE_MINUTES=30)
    assert ok.REFRESH_TOKEN_IDLE_MINUTES == 30
    for access, idle in ((60, 30), (28, 30), (30, 30)):
        with pytest.raises(ValidationError):
            SecuritySettings(JWT_SECRET_KEY=secret, JWT_ACCESS_TOKEN_EXPIRE_MINUTES=access,
                             REFRESH_TOKEN_IDLE_MINUTES=idle)


@pytest.mark.unit
def test_rc068_login_and_refresh_tell_the_client_when_the_refresh_session_ends(env):
    r = _login(env)
    tok = r.json()["token"]
    assert 0 < tok["refresh_expires_in"] <= 30 * 60, tok
    env.clock.advance(minutes=10)
    r2 = _refresh(env, _cookie(r))
    assert r2.status_code == 200
    assert 0 < r2.json()["token"]["refresh_expires_in"] <= 30 * 60


@pytest.mark.unit
def test_rc068_secret_templates_no_longer_emit_a_60_minute_access_token():
    for rel in ("backend/scripts/generate_secrets.py", "backend/.env.example"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60" not in text, rel
        assert "JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15" in text, rel
        assert "REFRESH_TOKEN_IDLE_MINUTES=30" in text, rel


# =============================================================================== M3
class _WA:
    def __init__(self, fail_begin=False):
        self.fail_begin = fail_begin

    def generate_registration(self, user_id, username, display_name):
        if self.fail_begin:
            raise RuntimeError("authenticator service down")
        return {"challenge": "c"}

    def verify_registration(self, user_id, credential_json, device_name):
        return {"credential_id": "cred-new", "device_name": device_name}

    def get_credentials(self, user_id):
        return [{"credential_id": "a"}, {"credential_id": "b"}]

    def delete_credential(self, user_id, credential_id):
        return True


@pytest.mark.unit
def test_rc067_auth_requests_without_their_own_event_are_still_recorded(env, monkeypatch):
    auth_routes = _mod("app.api.routes.auth")
    monkeypatch.setattr(auth_routes, "_get_webauthn_service", lambda: _WA())
    monkeypatch.setattr(auth_routes.auth_service, "get_user_by_id", lambda uid: env.storage.get_user_by_id(uid))
    monkeypatch.setattr(auth_routes.auth_service, "list_users", lambda: env.storage.list_all_users())
    h_rad, h_admin = env.bearer(env.rad), env.bearer(env.admin)
    assert env.client.post("/api/v1/auth/webauthn/register/complete", headers=h_rad,
                           json={"credential": {}, "device_name": "key"}).status_code == 200
    assert env.client.delete("/api/v1/auth/webauthn/credentials/a", headers=h_rad).status_code == 200
    assert env.client.get("/api/v1/auth/users", headers=h_admin).status_code == 200
    assert env.client.get(f"/api/v1/auth/users/{env.rad.id}", headers=h_admin).status_code == 200
    recs = env.records()
    by_endpoint = {(r.get("method"), r.get("endpoint")): r for r in recs}
    reg = by_endpoint.get(("POST", "/api/v1/auth/webauthn/register/complete"))
    assert reg and reg["event_type"] == "auth.credential.register" and reg["actor_user_id"] == env.rad.id, recs
    dele = by_endpoint.get(("DELETE", "/api/v1/auth/webauthn/credentials/{credential_id}"))
    assert dele and dele["event_type"] == "auth.credential.delete" and dele["actor_user_id"] == env.rad.id
    assert dele["resource_ids"].get("credential_id") == "a"
    lst = by_endpoint.get(("GET", "/api/v1/auth/users"))
    assert lst and lst["actor_user_id"] == env.admin.id
    one = by_endpoint.get(("GET", "/api/v1/auth/users/{user_id}"))
    assert one and one["resource_ids"].get("target_user_id") == env.rad.id


@pytest.mark.unit
def test_rc067_a_server_error_on_an_auth_route_is_recorded(env, monkeypatch):
    auth_routes = _mod("app.api.routes.auth")
    monkeypatch.setattr(auth_routes, "_get_webauthn_service", lambda: _WA(fail_begin=True))
    r = env.client.post("/api/v1/auth/webauthn/register/begin", headers=env.bearer(env.rad), json={})
    assert r.status_code == 500
    rows = [x for x in env.records() if x.get("status_code") == 500]
    assert len(rows) == 1 and rows[0]["endpoint"] == "/api/v1/auth/webauthn/register/begin"
    assert rows[0]["outcome"] == "failure" and rows[0]["actor_user_id"] == env.rad.id


@pytest.mark.unit
def test_rc067_logout_with_an_unknown_cookie_and_no_bearer_is_recorded(env):
    env.client.cookies.clear()
    r = env.client.post("/api/v1/auth/logout", headers={"Cookie": "__session=not-a-known-token"})
    assert r.status_code == 204
    rows = env.records("auth.logout")
    assert len(rows) == 1 and rows[0]["outcome"] == "failure" and rows[0]["reason"] == "unknown_session", env.records()


# =============================================================================== m5
@pytest.mark.unit
def test_rc068_a_replay_within_the_grace_window_returns_the_same_successor(env):
    t1 = _cookie(_login(env))
    r = _refresh(env, t1)
    t2 = _cookie(r)
    assert r.status_code == 200
    env.clock.advance(seconds=10)
    replay = _refresh(env, t1)               # the browser never received t2 (lost response / other tab)
    assert replay.status_code == 200, replay.text
    assert _cookie(replay) == t2, "the same successor must be returned, not a new branch"
    assert not env.records("auth.token.reuse_detected")
    r3 = _refresh(env, t2)
    assert r3.status_code == 200 and _cookie(r3) not in (t1, t2)
    dump = json.dumps(env.store.repo.dump(), default=str)
    assert t2 not in dump, "the successor kept for the grace window must not be stored readable"


@pytest.mark.unit
def test_rc068_real_reuse_is_still_detected_after_the_window_or_after_the_successor_was_used(env):
    t1 = _cookie(_login(env))
    t2 = _cookie(_refresh(env, t1))
    env.clock.advance(seconds=31)
    assert _refresh(env, t1).status_code == 401
    assert _refresh(env, t2).status_code == 401, "reuse after the window must revoke the family"
    assert len(env.records("auth.token.reuse_detected")) == 1

    a1 = _cookie(_login(env))
    a2 = _cookie(_refresh(env, a1))
    a3 = _cookie(_refresh(env, a2))           # successor already used: a replay of a1 is theft
    assert _refresh(env, a1).status_code == 401
    assert _refresh(env, a3).status_code == 401


# =============================================================================== m6
@pytest.mark.unit
def test_rc068_a_transient_user_store_error_does_not_end_the_session(env, monkeypatch):
    token = _cookie(_login(env))
    real = env.storage.lookup_user
    calls = {"n": 0}

    def flaky(uid):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("user store unreachable")
        return real(uid)

    monkeypatch.setattr(env.storage, "lookup_user", flaky)
    first = _refresh(env, token)
    assert first.status_code == 503, first.text
    assert "__session=" not in first.headers.get("set-cookie", ""), "the cookie must be kept"
    second = _refresh(env, token)
    assert second.status_code == 200, "a transient error must not burn or revoke the session"


@pytest.mark.unit
def test_rc068_secure_user_storage_distinguishes_not_found_from_an_error(tmp_path, monkeypatch):
    from app.security.user_storage import SecureUserStorage, UserStoreUnavailable
    store = SecureUserStorage(storage_dir=tmp_path)
    assert store.lookup_user("does-not-exist") is None

    def boom(user_id):
        raise OSError("disk unreadable")

    monkeypatch.setattr(store, "_read_profile_blob", boom)
    with pytest.raises(UserStoreUnavailable):
        store.lookup_user("anyone")


# =============================================================================== m8
@pytest.mark.unit
def test_rc068_refresh_and_logout_store_calls_run_off_the_event_loop(env, monkeypatch):
    seen = []

    def wrap(fn):
        def inner(*a, **k):
            try:
                asyncio.get_running_loop()
                seen.append((fn.__name__, "event-loop"))
            except RuntimeError:
                seen.append((fn.__name__, "thread"))
            return fn(*a, **k)
        inner.__name__ = fn.__name__
        return inner

    token = _cookie(_login(env))
    for name in ("peek_owner", "rotate", "revoke_family"):
        monkeypatch.setattr(env.store, name, wrap(getattr(env.store, name)))
    monkeypatch.setattr(env.storage, "lookup_user", wrap(env.storage.lookup_user))
    new = _cookie(_refresh(env, token))
    env.client.cookies.clear()
    env.client.post("/api/v1/auth/logout", headers={"Cookie": f"__session={new}"})
    assert seen and all(where == "thread" for _, where in seen), seen


@pytest.mark.unit
def test_rc068_revoking_every_session_touches_only_live_families():
    rt = _mod("app.security.refresh_tokens")
    for repo in (rt.MemoryRefreshRepo(), rt.FirestoreRefreshRepo(FakeFirestore(), transactional=fake_transactional)):
        now = {"t": datetime(2026, 10, 24, 8, 0, tzinfo=timezone.utc)}
        store = rt.RefreshTokenStore(repo=repo, clock=lambda: now["t"])
        old = store.issue("u1")
        now["t"] += timedelta(hours=13)          # past the absolute expiry
        revoked = store.issue("u1")
        store.revoke_family(revoked.family_id, "logout")
        live = store.issue("u1")
        assert store.revoke_all_for_user("u1", "password_change") == 1, type(repo).__name__
        fams = repo.dump()["families"] if hasattr(repo, "dump") else repo.db.docs("refresh_token_families")
        assert fams[live.family_id]["revoked"] is True
        assert fams[revoked.family_id]["revoked_reason"] == "logout", "an already revoked family was rewritten"
        assert fams[old.family_id]["revoked"] is False, "an expired family was touched"


# =============================================================================== m9
@pytest.mark.unit
def test_rc067_the_recorded_ip_ignores_client_supplied_forwarded_hops(env):
    env.client.cookies.clear()
    env.client.post("/api/v1/auth/login", json={"username": "dr_rad", "password": PASSWORD},
                    headers={"X-Forwarded-For": "6.6.6.6, 203.0.113.7"})
    rec = env.records("auth.login.success")[-1]
    assert rec.get("ip_address") == "203.0.113.7", rec.get("ip_address")


@pytest.mark.unit
def test_rc067_the_rate_limit_key_ignores_client_supplied_forwarded_hops():
    from starlette.requests import Request
    from app.core.security.rate_limit_middleware import RateLimitMiddleware, IPBlacklistMiddleware

    def req(xff, host=None):
        headers = [(b"x-forwarded-for", xff.encode())]
        if host:
            headers.append((b"x-forwarded-host", host.encode()))
        return Request({"type": "http", "method": "GET", "path": "/", "headers": headers, "client": ("10.0.0.9", 1)})

    for cls in (RateLimitMiddleware, IPBlacklistMiddleware):
        assert cls._get_client_ip(object.__new__(cls), req("6.6.6.6, 203.0.113.7")) == "203.0.113.7"
        # through Firebase Hosting (one more trusted hop, documented assumption)
        assert cls._get_client_ip(object.__new__(cls), req("6.6.6.6, 203.0.113.7, 35.190.0.1",
                                                           "app.mstool-ai.com")) == "203.0.113.7"


@pytest.mark.unit
def test_rc067_a_flood_from_one_source_cannot_fill_the_durable_queue(env, capsys):
    capsys.readouterr()
    for i in range(60):
        env.client.get(f"/api/v1/segmentation/{SEG}/info", headers={"Authorization": f"Bearer forged-{i}",
                                                                     "X-Forwarded-For": "198.51.100.66"})
    durable = [r for r in env.records() if r.get("ip_address") == "198.51.100.66"]
    assert 1 <= len(durable) <= 30, len(durable)
    lines = [x for x in capsys.readouterr().out.splitlines() if x.startswith("{") and "198.51.100.66" in x]
    assert len(lines) >= 60, "every request is still on the server log"


@pytest.mark.unit
def test_rc067_the_banner_recovers_once_drops_are_no_longer_recent():
    sink_mod = _mod("app.core.logging.audit_sink")
    clock = {"t": 1000.0}
    db = FakeFirestore()
    db.fail_next(10_000, ops=("create",))
    sink = sink_mod.DurableAuditSink(lambda: db, backend="firestore", max_queue=1, base_backoff_s=0.01,
                                     max_backoff_s=0.01, max_attempts=1, clock=lambda: clock["t"])
    sink.submit({"event_id": "x1", "event_type": "auth.logout"})
    sink.flush(5.0)
    assert sink.status()["state"] == "failing"
    db.fail_next(0)
    sink.submit({"event_id": "x2", "event_type": "auth.logout"})
    sink.flush(5.0)
    clock["t"] += 16 * 60
    st = sink.status()
    assert st["state"] == "ok" and st["dropped_total"] == 1 and st["dropped_recent"] == 0, st
    sink.close()


# =============================================================================== m10
@pytest.mark.unit
def test_rc067_identifiers_are_hashed_with_a_secret_key(env, monkeypatch):
    acc = "ACC-2026-0042"
    env.client.get(f"/api/v1/studies/accession/{acc}", headers=env.bearer(env.rad))
    rec = [r for r in env.records() if "accession" in (r.get("endpoint") or "")][0]
    assert rec["resource_ids"].get("accession_hmac") == keyed(acc), rec["resource_ids"]
    assert hashlib.sha256(acc.encode()).hexdigest()[:16] not in json.dumps(rec, default=str)
    aud = _mod("app.core.logging.audit")
    monkeypatch.setenv("AUDIT_HASH_KEY", "a-separate-audit-hash-key-for-this-deployment")
    try:
        if hasattr(aud, "reset_audit_hash_key"):
            aud.reset_audit_hash_key()
        assert aud.keyed_hash(acc) == keyed(acc) != hashlib.sha256(acc.encode()).hexdigest()[:16]
    finally:
        monkeypatch.delenv("AUDIT_HASH_KEY")
        if hasattr(aud, "reset_audit_hash_key"):
            aud.reset_audit_hash_key()


@pytest.mark.unit
def test_rc067_the_user_agent_is_reduced_to_a_coarse_class(env):
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/130.0.0.0 Safari/537.36 Workstation-RAD-17")
    env.client.cookies.clear()
    env.client.post("/api/v1/auth/login", json={"username": "dr_rad", "password": PASSWORD},
                    headers={"User-Agent": ua})
    rec = env.records("auth.login.success")[-1]
    assert rec.get("user_agent") == "chrome/windows", rec.get("user_agent")
    assert "Workstation-RAD-17" not in json.dumps(rec, default=str)
