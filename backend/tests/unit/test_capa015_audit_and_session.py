"""CAPA-015 — durable audit trail and secure session continuation
(RC-067, RC-068; REQ-SEC-024, REQ-SEC-025; HAZ-010, HAZ-001).

Why (code reading 2026-10-24, re-checked in the code of main @ 70cc5c7):
- the audit logger appended to `logs/audit.log` on the container's disk and `/auth/audit-logs`
  read an in-memory list; the Firestore collection `audit_logs` was declared but never written.
  On Cloud Run (0-5 instances, scale to zero) disk and memory vanish on every restart or
  scale-in, so "who did what" was lost. The password-login route did not call the audit logger
  at all, and segmentation save/confirm, AI report generation and longitudinal decisions were
  never audited;
- the frontend called `/auth/refresh`, which did not exist; login issued a single 60-minute
  access token, so every user was forced to sign in again every hour;
- a password change was kept in one process's memory only: the login route (which reads the
  user store) kept accepting the OLD password and refusing the new one.

These tests drive the real application (FastAPI TestClient over HTTPS) with an in-memory user
store, an in-memory Firestore stand-in and a controllable clock. No network, no cloud
credentials. They were written before the fix and fail on main @ 70cc5c7 (record:
docs/iec62304/records/risk_verification/CAPA-015_tests_on_base_2026-10-24.json).

Negative controls: scripts/safety/capa015_negative_controls.py.
"""
import hashlib
import importlib
import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.security.models import User, UserRole
from app.security.password import PasswordManager
from app.security.jwt_manager import get_token_manager
from app.security.user_storage import get_user_storage
from app.security.captcha import get_captcha_manager
from app.core.container import get_tool_runner_service

from tests.unit.capa015_fakes import FakeFirestore, FakeUserStorage, fake_transactional

ROOT = Path(__file__).resolve().parents[3]
PASSWORD = "Correct-Horse-Battery-9!"
NEW_PASSWORD = "Another-Long-Passphrase-7?"
SEG = "33333333-3333-4333-8333-333333333333"
SEG2 = "44444444-4444-4444-8444-444444444444"

# Fields an audit record may carry (schema v1). Anything else — description text, query
# strings, request bodies, image data — must never reach the durable trail.
ALLOWED_RECORD_KEYS = {
    "schema_version", "event_id", "event_type", "severity", "outcome", "action", "source",
    "client_timestamp", "server_timestamp", "actor_user_id", "actor_username", "actor_role",
    "attempted_identifier_hmac", "ip_address", "user_agent", "request_id", "trace_id",
    "method", "endpoint", "status_code", "resource_type", "resource_ids", "reason", "details",
    "service_revision", "checksum",
}


def _mod(name):
    return importlib.import_module(name)


def keyed(value):
    """The documented derivation (review m10): AUDIT_HASH_KEY if set, else
    HMAC-SHA-256(JWT secret, "mstool-audit-identifier-hash-v1"); value = HMAC-SHA-256(key, identifier)[:16]."""
    import hmac
    import os
    explicit = os.environ.get("AUDIT_HASH_KEY")
    key = explicit.encode() if explicit else hmac.new(os.environ["JWT_SECRET_KEY"].encode(),
                                                      b"mstool-audit-identifier-hash-v1", hashlib.sha256).digest()
    return hmac.new(key, str(value).encode(), hashlib.sha256).hexdigest()[:16]


def _user(username, role, **kw):
    now = datetime.utcnow()
    return User(id=str(uuid.uuid4()), username=username, email=f"{username}@clinic.example",
                full_name=username, role=role, is_active=kw.pop("is_active", True),
                is_locked=kw.pop("is_locked", False), email_verified=True, created_at=now,
                updated_at=now, last_password_change=now, failed_login_attempts=0, **kw)


class _Captcha:
    """Accepts any answer: lets a test reach the lockout threshold after CAPTCHA is required."""

    def validate_captcha(self, challenge_id, user_input, ip_address=None):
        return bool(challenge_id and user_input)


class _Tools:
    def list_tools(self):
        return []

    async def check_sidecar_health(self, tool_id):
        return False


class _Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 24, 8, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += timedelta(**kw)


def _try(name):
    """The new modules are imported softly so that, on the code before the fix, every test
    fails on the behaviour it checks (no record, no cookie, no route) rather than on an import."""
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


@pytest.fixture
def env(monkeypatch):
    """Real app; in-memory user store, Firestore stand-in for the audit trail, refresh store
    with a controllable clock. Everything restored afterwards."""
    sink_mod = _try("app.core.logging.audit_sink")
    rt = _try("app.security.refresh_tokens")
    mw = _mod("app.core.logging.audit_middleware")
    authn = _mod("app.api.routes.authentication")

    db = FakeFirestore()
    sink = previous_sink = store = None
    if sink_mod is not None:
        sink = sink_mod.DurableAuditSink(lambda: db, backend="firestore", base_backoff_s=0.01, max_backoff_s=0.05)
        previous_sink = sink_mod.set_durable_audit_sink(sink)
    clock = _Clock()
    if rt is not None:
        store = rt.RefreshTokenStore(repo=rt.MemoryRefreshRepo(), clock=clock)
        app.dependency_overrides[rt.get_refresh_token_store] = lambda: store
    storage = FakeUserStorage()
    pm = PasswordManager()
    hashed = pm.hash_password(PASSWORD)
    rad = storage.add(_user("dr_rad", UserRole.RADIOLOGIST), hashed)
    admin = storage.add(_user("admin_ops", UserRole.ADMIN), hashed)

    app.dependency_overrides[get_user_storage] = lambda: storage
    app.dependency_overrides[get_captcha_manager] = lambda: _Captcha()
    app.dependency_overrides[get_tool_runner_service] = lambda: _Tools()
    authn.attempt_tracker._attempts.clear()
    if hasattr(mw, "reset_read_dedup"):
        mw.reset_read_dedup()
    aud = _mod("app.core.logging.audit")
    if hasattr(aud, "reset_audit_budget"):
        aud.reset_audit_budget()
    client = TestClient(app, base_url="https://testserver", raise_server_exceptions=False)
    tm = get_token_manager()

    def bearer(user):
        return {"Authorization": "Bearer " + tm.create_access_token(user.id, user.username, user.role).access_token}

    def records(event_type=None):
        if sink is not None:
            sink.flush(5.0)
        rows = list(db.docs("audit_logs").values())
        return [r for r in rows if event_type is None or r.get("event_type") == event_type]

    ns = type("Env", (), dict(client=client, db=db, sink=sink, store=store, clock=clock, storage=storage,
                              rad=rad, admin=admin, bearer=staticmethod(bearer), records=staticmethod(records),
                              rt=rt, sink_mod=sink_mod))
    try:
        yield ns
    finally:
        for dep in (get_user_storage, get_captcha_manager, get_tool_runner_service):
            app.dependency_overrides.pop(dep, None)
        if rt is not None:
            app.dependency_overrides.pop(rt.get_refresh_token_store, None)
        authn.attempt_tracker._attempts.clear()
        if sink is not None:
            db.fail_next(0)
            sink.flush(5.0)
            sink_mod.set_durable_audit_sink(previous_sink)
            sink.close()


def _login(env, username="dr_rad", password=PASSWORD, **extra):
    env.client.cookies.clear()
    return env.client.post("/api/v1/auth/login", json={"username": username, "password": password, **extra})


def _cookie(resp):
    m = re.search(r"__session=([^;]*)", resp.headers.get("set-cookie", ""))
    return m.group(1) if m else None


def _refresh(env, token, **headers):
    env.client.cookies.clear()
    h = dict(headers)
    if token is not None:
        h["Cookie"] = f"__session={token}"
    return env.client.post("/api/v1/auth/refresh", headers=h)


# =============================================================================== RC-067
# Audit trail: durable (Firestore `audit_logs`), append-only, server time, actor, role, action,
# resource ids, outcome, request id; no image data, no free text; never breaks the request.

@pytest.mark.unit
def test_rc067_login_success_is_written_durably_with_actor_role_and_request_id(env):
    r = _login(env)
    assert r.status_code == 200, r.text
    rows = env.records("auth.login.success")
    assert len(rows) == 1, f"no durable login record in Firestore audit_logs: {env.records()}"
    rec = rows[0]
    assert rec["actor_user_id"] == env.rad.id and rec["actor_role"] == "radiologist"
    assert rec["outcome"] == "success"
    assert rec["request_id"] and rec["request_id"] == r.headers.get("x-request-id")
    assert isinstance(rec["server_timestamp"], datetime), "the time must be the server's commit time"
    assert PASSWORD not in json.dumps(rec, default=str)
    assert set(rec) <= ALLOWED_RECORD_KEYS, set(rec) - ALLOWED_RECORD_KEYS


@pytest.mark.unit
def test_rc067_failed_logins_captcha_and_lockout_are_recorded_without_the_typed_identifier(env):
    typed = "someone-who-does-not-exist@example.org"
    assert _login(env, username=typed, password="x" * 12).status_code == 401
    unknown = [r for r in env.records("auth.login.failed") if r.get("reason") == "user_not_found"]
    assert len(unknown) == 1
    assert typed not in json.dumps(unknown[0], default=str), "the typed identifier must not be stored"
    # keyed hash (review m10): HMAC-SHA-256 with a key derived from the server secret, never a plain hash
    assert unknown[0]["attempted_identifier_hmac"] == keyed(typed)
    assert hashlib.sha256(typed.encode()).hexdigest()[:16] not in json.dumps(unknown[0], default=str)

    for _ in range(2):
        assert _login(env, password="wrong-password-123").status_code == 401
    # existing control kept: after 2 failures a CAPTCHA is required (and that refusal is audited)
    r = _login(env, password="wrong-password-123")
    assert r.status_code == 400 and "captcha" in r.text.lower()
    assert [x for x in env.records("auth.login.failed") if x.get("reason") == "captcha_required"]
    for _ in range(3):
        _login(env, password="wrong-password-123", captcha_challenge_id="c", captcha_response="1")
    # existing control kept: locked after 5 failed passwords
    r = _login(env, password=PASSWORD, captcha_challenge_id="c", captcha_response="1")
    assert r.status_code == 403, r.text
    invalid = [x for x in env.records("auth.login.failed") if x.get("reason") == "invalid_password"]
    assert len(invalid) == 5 and all(x["actor_user_id"] == env.rad.id for x in invalid)
    locked = env.records("auth.account.locked")
    assert len(locked) == 1 and locked[0]["actor_user_id"] == env.rad.id
    assert [x for x in env.records("auth.login.failed") if x.get("reason") == "account_locked"]


def _deny_objects(monkeypatch):
    ra = _mod("app.security.resource_access")
    sa = _mod("app.api.routes.segmentation_analysis")

    async def _not_found(*a, **k):
        raise HTTPException(status_code=404, detail="Segmentation not found")

    monkeypatch.setattr(ra, "_segmentation_service", lambda: None)
    monkeypatch.setattr(ra, "resolve_segmentation_patient_id", _not_found)
    monkeypatch.setattr(sa, "authorize_mask_specs", _not_found)


CLINICAL = [
    ("POST", f"/api/v1/segmentation/{SEG}/save", None, "clinical.segmentation.save"),
    ("PUT", f"/api/v1/segmentation/{SEG}/mask/binary", None, "clinical.segmentation.save"),
    ("POST", f"/api/v1/segmentation/{SEG}/ai-review/confirm", None, "clinical.segmentation.confirm"),
    ("DELETE", f"/api/v1/segmentation/{SEG}", None, "clinical.segmentation.delete"),
    ("POST", "/api/v1/segmentation/longitudinal/review",
     {"tp1": {"type": "segmentation", "id": SEG}, "tp2": {"type": "segmentation", "id": SEG2},
      "review_binding": {}, "decisions": []}, "clinical.longitudinal.review"),
]


@pytest.mark.unit
@pytest.mark.parametrize("method,path,body,event_type", CLINICAL, ids=[c[3] + ":" + c[0] for c in CLINICAL])
def test_rc067_clinical_actions_are_recorded_with_actor_resource_ids_and_outcome(env, monkeypatch, method, path,
                                                                                 body, event_type):
    _deny_objects(monkeypatch)
    r = env.client.request(method, path, json=body, headers=env.bearer(env.rad))
    assert r.status_code == 404
    rows = env.records(event_type)
    assert len(rows) == 1, f"{method} {path}: no durable '{event_type}' record: {env.records()}"
    rec = rows[0]
    assert rec["actor_user_id"] == env.rad.id and rec["actor_role"] == "radiologist"
    assert rec["outcome"] == "failure" and rec["status_code"] == 404
    assert rec["request_id"] == r.headers.get("x-request-id")
    ids = rec["resource_ids"]
    assert SEG in ids.values(), ids
    if body:
        assert SEG2 in ids.values(), ids
    assert set(rec) <= ALLOWED_RECORD_KEYS


@pytest.mark.unit
def test_rc067_ai_report_generation_is_recorded_with_template_and_outcome(env, monkeypatch):
    ai_report = _mod("app.api.routes.ai_report")

    class _Svc:
        async def generate_report(self, **kw):
            return {"report_id": "r1", "content": "draft", "template_type": kw["template_type"],
                    "language": kw["language"], "processing_time_ms": 1}

    monkeypatch.setattr(ai_report, "get_report_service", lambda: _Svc())
    r = env.client.post("/api/v1/ai/report/generate", headers=env.bearer(env.rad), json={
        "template_type": "ms_lesion_burden", "language": "es",
        "findings": {"lesion_analysis": {"total_lesions": 3}, "patient_name": "Erika Mustermann"}})
    assert r.status_code == 200, r.text
    rows = env.records("clinical.ai_report.generate")
    assert len(rows) == 1
    rec = rows[0]
    assert rec["outcome"] == "success" and rec["actor_user_id"] == env.rad.id
    assert rec["details"].get("template_type") == "ms_lesion_burden" and rec["details"].get("language") == "es"
    assert "Mustermann" not in json.dumps(rec, default=str), "no free text from the request body"


@pytest.mark.unit
def test_rc067_data_reads_are_durable_once_per_window_and_always_on_stdout(env, capsys):
    capsys.readouterr()
    for _ in range(2):
        assert env.client.get("/api/v1/clinical/tools", headers=env.bearer(env.rad)).status_code == 200
    rows = env.records("data.access.read")
    assert len(rows) == 1, f"a repeated read within the window is one durable record: {rows}"
    assert rows[0]["actor_user_id"] == env.rad.id and rows[0]["endpoint"] == "/api/v1/clinical/tools"
    lines = [json.loads(x) for x in capsys.readouterr().out.splitlines() if x.startswith("{") and '"audit"' in x]
    reads = [x for x in lines if x["audit"]["event_type"] == "data.access.read"]
    assert len(reads) == 2, "every audited request is written to stdout as structured JSON"
    assert reads[0]["severity"] in {"INFO", "NOTICE", "WARNING", "ERROR", "CRITICAL", "ALERT"}


@pytest.mark.unit
def test_rc067_records_hold_no_query_string_file_name_or_free_text(env, monkeypatch):
    _deny_objects(monkeypatch)
    imaging = _mod("app.api.routes.imaging")
    from app.core.container import get_storage_service, get_imaging_service

    async def _no_image(*a, **k):
        raise HTTPException(status_code=404, detail="Image not found")

    monkeypatch.setattr(imaging, "require_imaging_access", _no_image)
    monkeypatch.setitem(app.dependency_overrides, get_storage_service, lambda: object())
    monkeypatch.setitem(app.dependency_overrides, get_imaging_service, lambda: object())
    secret = "query-secret-token-value"
    r = env.client.get(f"/api/v1/segmentation/{SEG}/info?token={secret}&name=Mustermann",
                       headers=env.bearer(env.rad))
    assert r.status_code == 404
    file_id = ("patients/11111111-1111-4111-8111-111111111111/studies/22222222-2222-4222-8222-222222222222/"
               "series/55555555-5555-4555-8555-555555555555/Mustermann_Erika_FLAIR.nii.gz")
    env.client.get(f"/api/v1/imaging/metadata/{file_id}", headers=env.bearer(env.rad))
    blob = json.dumps(env.records(), default=str)
    assert secret not in blob and "Mustermann" not in blob and "Erika" not in blob
    meta = [x for x in env.records() if "imaging" in (x.get("endpoint") or "")]
    assert meta and meta[0]["endpoint"] == "/api/v1/imaging/metadata/{file_id:path}"
    assert meta[0]["resource_ids"].get("patient_id") == "11111111-1111-4111-8111-111111111111"
    for rec in env.records():
        assert set(rec) <= ALLOWED_RECORD_KEYS, set(rec) - ALLOWED_RECORD_KEYS
        assert "description" not in rec and "metadata" not in rec


@pytest.mark.unit
def test_rc067_firestore_outage_never_breaks_the_request_is_logged_loudly_and_retried(env, caplog):
    env.db.fail_next(3, ops=("create",), collections=("audit_logs",))
    with caplog.at_level(logging.ERROR):
        r = _login(env)
    assert r.status_code == 200, "an audit-store outage must not break the clinical request"
    status = env.sink.status()
    assert status["consecutive_failures"] >= 1 or status["written_total"] >= 1
    assert any("AUDIT_SINK_WRITE_FAILED" in rec.getMessage() for rec in caplog.records), \
        "a failed audit write must be logged loudly"
    rows = env.records("auth.login.success")
    assert len(rows) == 1, "the record is retried until written, exactly once"
    assert env.sink.status()["state"] == "ok"


@pytest.mark.unit
def test_rc067_admin_sees_when_audit_writing_is_failing(env):
    env.db.fail_next(10_000, ops=("create",), collections=("audit_logs",))
    _login(env)
    r = env.client.get("/api/v1/auth/audit-status", headers=env.bearer(env.admin))
    assert r.status_code == 200
    body = r.json()
    assert body["state"] in {"degraded", "failing"}, body
    assert body["queue_depth"] >= 1 and body["last_error"]
    assert env.client.get("/api/v1/auth/audit-status", headers=env.bearer(env.rad)).status_code == 403
    env.db.fail_next(0)


@pytest.mark.unit
def test_rc067_queue_overflow_keeps_the_record_in_the_server_log(caplog):
    sink_mod = _mod("app.core.logging.audit_sink")
    db = FakeFirestore()
    db.fail_next(10_000, ops=("create",))
    sink = sink_mod.DurableAuditSink(lambda: db, backend="firestore", max_queue=1,
                                     base_backoff_s=10, max_backoff_s=10)
    with caplog.at_level(logging.CRITICAL):
        sink.submit({"event_id": "e1", "event_type": "auth.login.success"})
        sink.submit({"event_id": "e2", "event_type": "auth.login.success"})
        sink.submit({"event_id": "e3", "event_type": "auth.login.success"})
    st = sink.status()
    assert st["dropped_total"] >= 1 and st["state"] == "failing"
    assert any("AUDIT_RECORD_DROPPED" in r.getMessage() and '"e3"' in r.getMessage() for r in caplog.records)
    sink.close()


@pytest.mark.unit
def test_rc067_records_are_append_only(env):
    env.sink.submit({"event_id": "fixed-id", "event_type": "auth.logout", "outcome": "success"})
    env.sink.flush(5.0)
    env.sink.submit({"event_id": "fixed-id", "event_type": "auth.logout", "outcome": "FORGED"})
    env.sink.flush(5.0)
    assert env.db.docs("audit_logs")["fixed-id"]["outcome"] == "success", "an existing record was overwritten"
    ops = {op for op, coll, _ in env.db.calls if coll == "audit_logs"}
    assert ops == {"create"}, f"audit_logs written with {ops}; only create is append-only"
    rules = (ROOT / "firestore.rules").read_text(encoding="utf-8")
    block = re.search(r"match /audit_logs/\{\w+\}\s*\{([^}]*)\}", rules)
    assert block and "allow write: if false" in block.group(1), "clients must never write the audit trail"


@pytest.mark.unit
def test_rc067_audit_log_endpoint_reads_firestore_paginated_admin_only(env):
    for i in range(5):
        env.sink.submit({"schema_version": 1, "event_id": f"seed{i}", "event_type": "auth.logout",
                         "outcome": "success", "actor_user_id": env.rad.id if i % 2 else "other"})
    env.sink.flush(5.0)
    h = env.bearer(env.admin)
    r = env.client.get("/api/v1/auth/audit-logs?limit=2", headers=h)
    assert r.status_code == 200, r.text
    page1 = r.json()
    assert [x["event_id"] for x in page1["items"]] == ["seed4", "seed3"], "newest first"
    assert page1["next_page_token"]
    page2 = env.client.get(f"/api/v1/auth/audit-logs?limit=2&page_token={page1['next_page_token']}", headers=h).json()
    assert [x["event_id"] for x in page2["items"]] == ["seed2", "seed1"]
    mine = env.client.get(f"/api/v1/auth/audit-logs?limit=50&user_id={env.rad.id}", headers=h).json()
    assert {x["event_id"] for x in mine["items"]} == {"seed1", "seed3"}
    assert "sink_status" in page1
    # admin-only: a radiologist (who holds AUDIT_VIEW in the role map) is refused
    assert env.client.get("/api/v1/auth/audit-logs", headers=env.bearer(env.rad)).status_code == 403
    # reading the trail is itself recorded
    assert env.records("audit.log.read")


@pytest.mark.unit
def test_rc067_auth_service_events_reach_the_durable_trail(env):
    auth_routes = _mod("app.api.routes.auth")
    auth_routes.auth_service._log_audit_event("user_updated", f"user:{env.rad.id}", "success",
                                              user_id=env.admin.id, username="admin_ops")
    rows = env.records("admin.user.modified")
    assert len(rows) == 1 and rows[0]["actor_user_id"] == env.admin.id
    assert not hasattr(auth_routes.auth_service, "_audit_logs") or not auth_routes.auth_service._audit_logs, \
        "audit events must not live in a per-process list"


# =============================================================================== RC-068
# Session: short-lived access token + rotating refresh token (hashed, server-side, idle and
# absolute expiry, reuse revokes the family), HttpOnly Secure SameSite=Strict cookie; revoked on
# logout and password change; inactive or locked users cannot continue.

@pytest.mark.unit
def test_rc068_login_sets_an_httponly_secure_samesite_strict_cookie_and_no_token_in_the_body(env):
    r = _login(env)
    assert r.status_code == 200
    sc = r.headers.get("set-cookie", "")
    token = _cookie(r)
    assert token, f"no refresh cookie: {sc!r}"
    low = sc.lower()
    assert "httponly" in low and "secure" in low and "samesite=strict" in low
    assert "path=/api/v1/auth" in low and "max-age=" in low
    assert token not in r.text, "the refresh token must never be readable by page scripts"
    assert "no-store" in r.headers.get("cache-control", "")


@pytest.mark.unit
def test_rc068_access_tokens_are_short_lived(env):
    from app.core.config import SecuritySettings
    assert SecuritySettings.model_fields["JWT_ACCESS_TOKEN_EXPIRE_MINUTES"].default <= 15
    r = _login(env)
    assert r.json()["token"]["expires_in"] <= 15 * 60


@pytest.mark.unit
def test_rc068_refresh_rotates_and_the_old_token_is_refused(env):
    first = _cookie(_login(env))
    r = _refresh(env, first)
    assert r.status_code == 200, r.text
    second = _cookie(r)
    assert second and second != first
    payload = get_token_manager().decode_token(r.json()["token"]["access_token"])
    assert payload["user_id"] == env.rad.id and payload["type"] == "access"
    env.clock.advance(seconds=31)                    # past the reuse grace window (review m5)
    assert _refresh(env, first).status_code == 401, "a used refresh token must not work twice"
    assert env.records("auth.token.refresh")


@pytest.mark.unit
def test_rc068_reuse_revokes_the_whole_family(env):
    first = _cookie(_login(env))
    second = _cookie(_refresh(env, first))
    env.clock.advance(seconds=31)                             # past the reuse grace window (review m5)
    assert _refresh(env, first).status_code == 401           # replay of a rotated token
    assert _refresh(env, second).status_code == 401, "reuse must revoke every token of the family"
    reuse = env.records("auth.token.reuse_detected")
    assert len(reuse) == 1 and reuse[0]["actor_user_id"] == env.rad.id


@pytest.mark.unit
def test_rc068_refresh_tokens_are_stored_hashed(env):
    token = _cookie(_login(env))
    dump = json.dumps(env.store.repo.dump(), default=str)
    assert token not in dump, "the raw refresh token is stored server-side"
    assert hashlib.sha256(token.encode()).hexdigest() in dump


@pytest.mark.unit
def test_rc068_idle_and_absolute_expiry(env):
    token = _cookie(_login(env))
    env.clock.advance(minutes=31)
    assert _refresh(env, token).status_code == 401, "idle expiry (30 min) not enforced"

    token = _cookie(_login(env))
    start = env.clock.now
    for _ in range(40):                         # active user: rotates every 20 minutes
        env.clock.advance(minutes=20)
        r = _refresh(env, token)
        if r.status_code != 200:
            break
        token = _cookie(r)
    assert r.status_code == 401, "absolute expiry (12 h) not enforced"
    assert timedelta(hours=11, minutes=40) < env.clock.now - start <= timedelta(hours=12),         "the session must end at the absolute limit, not before and not after"


@pytest.mark.unit
def test_rc068_logout_revokes_the_session_and_clears_the_cookie(env):
    login = _login(env)
    token = _cookie(login)
    access = login.json()["token"]["access_token"]
    env.client.cookies.clear()
    r = env.client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {access}",
                                                        "Cookie": f"__session={token}"})
    assert r.status_code == 204
    sc = r.headers.get("set-cookie", "").lower()
    assert "__session=" in sc and ("max-age=0" in sc or "expires=thu, 01 jan 1970" in sc)
    assert _refresh(env, token).status_code == 401
    assert env.records("auth.logout")


@pytest.mark.unit
def test_rc068_password_change_takes_effect_and_revokes_every_session(env, monkeypatch):
    auth_routes = _mod("app.api.routes.auth")
    monkeypatch.setattr(auth_routes.auth_service, "_storage", env.storage)
    a = _login(env)
    b_token = _cookie(_login(env))
    r = env.client.post("/api/v1/auth/change-password", headers=env.bearer(env.rad),
                        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert r.status_code == 204, r.text
    assert _refresh(env, _cookie(a)).status_code == 401 and _refresh(env, b_token).status_code == 401
    assert _login(env, password=NEW_PASSWORD).status_code == 200, "the new password must work at login"
    env.client.cookies.clear()
    from app.api.routes import authentication as authn
    authn.attempt_tracker._attempts.clear()
    assert _login(env, password=PASSWORD).status_code == 401, "the old password must stop working"
    assert [x for x in env.records("auth.password.change") if x["outcome"] == "success"]


@pytest.mark.unit
def test_rc068_inactive_or_locked_users_cannot_refresh(env):
    token = _cookie(_login(env))
    env.rad.is_active = False
    assert _refresh(env, token).status_code == 401
    env.rad.is_active = True
    assert _refresh(env, token).status_code == 401, "the family must be revoked, not just refused once"
    token = _cookie(_login(env))
    env.rad.is_locked, env.rad.locked_until = True, datetime.utcnow() + timedelta(minutes=30)
    assert _refresh(env, token).status_code == 401


@pytest.mark.unit
def test_rc068_refreshed_access_token_carries_the_current_role(env):
    token = _cookie(_login(env))
    env.rad.role = UserRole.VIEWER
    r = _refresh(env, token)
    assert r.status_code == 200
    assert get_token_manager().decode_token(r.json()["token"]["access_token"])["role"] == "viewer"


@pytest.mark.unit
def test_rc068_refresh_refuses_a_foreign_origin_and_a_missing_cookie(env):
    token = _cookie(_login(env))
    assert _refresh(env, token, Origin="https://evil.example").status_code == 403
    assert _refresh(env, None).status_code == 401
    assert _refresh(env, token, Origin="http://localhost:5173").status_code == 200


@pytest.mark.unit
def test_rc068_passkey_login_also_starts_a_rotating_session_and_keeps_lock_checks(env, monkeypatch):
    auth_routes = _mod("app.api.routes.auth")

    class _WA:
        def verify_authentication(self, user_id, credential_json):
            return True

    monkeypatch.setattr(auth_routes, "_get_webauthn_service", lambda: _WA())
    monkeypatch.setattr(auth_routes.auth_service, "_find_user_by_username_or_email",
                        lambda name: env.storage.get_user_by_username(name))
    monkeypatch.setattr(auth_routes.auth_service, "_storage", env.storage)
    env.client.cookies.clear()
    r = env.client.post("/api/v1/auth/webauthn/login/complete", json={"username": "dr_rad", "credential": {}})
    assert r.status_code == 200, r.text
    assert _cookie(r) and _refresh(env, _cookie(r)).status_code == 200
    env.rad.is_locked = True
    env.client.cookies.clear()
    assert env.client.post("/api/v1/auth/webauthn/login/complete",
                           json={"username": "dr_rad", "credential": {}}).status_code == 403


@pytest.mark.unit
def test_rc068_firestore_repository_stores_hashes_and_rotates_in_one_transaction():
    rt = _mod("app.security.refresh_tokens")
    db = FakeFirestore()
    clock = _Clock()
    store = rt.RefreshTokenStore(repo=rt.FirestoreRefreshRepo(db, transactional=fake_transactional), clock=clock)
    issued = store.issue("user-1")
    tokens = db.docs("refresh_tokens")
    assert list(tokens) == [hashlib.sha256(issued.token.encode()).hexdigest()]
    assert issued.token not in json.dumps({**tokens, **db.docs("refresh_token_families")}, default=str)
    nxt = store.rotate(issued.token)
    assert len(db.transactions) >= 1 and db.transactions[-1].writes, "rotation must run in a transaction"
    clock.advance(seconds=31)                  # past the reuse grace window (review m5)
    with pytest.raises(rt.RefreshError) as e:
        store.rotate(issued.token)
    assert e.value.reuse is True
    fam = db.docs("refresh_token_families")[nxt.family_id]
    assert fam["revoked"] is True and fam["revoked_reason"] == "reuse_detected"
    with pytest.raises(rt.RefreshError):
        store.rotate(nxt.token)
