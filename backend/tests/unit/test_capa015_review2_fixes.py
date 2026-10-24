"""CAPA-015 — re-review of PR #65 at 09e11e8 (2026-10-24): backend findings.

N1  the client-IP fix could be bypassed: the hop count was chosen from `X-Forwarded-Host`, a header
    the client sends. A direct call to run.app with `X-Forwarded-For: 6.6.6.6` and
    `X-Forwarded-Host: app.mstool-ai.com` recorded 6.6.6.6 (and a wrong hop count would put every
    user in one rate-limit bucket). Now: the right-most entry (added by Google's front end) is the
    client, unless it is a published Firebase Hosting / Fastly egress address — then step left,
    and only over such addresses. No client-sent header decides anything.
N4  the per-source budget pushed AUTHENTICATED failures and denials out of the durable trail: 30
    anonymous junk requests from one IP, then a radiologist's failed `ai-review/confirm`, left no
    durable record. Now only anonymous records are budgeted.
N2  a developer `.env` with `JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60` stopped the app from importing (the
    start-up lifetime check): the suite sets the session lifetimes explicitly.
nit `webauthn/register/begin` was recorded as a completed registration.
N1b (coordinator check of the egress list, 2026-10-24) the embedded list lacked two IPv4 ranges and one
    IPv6 range and had one IPv6 range too narrow — written before the list was replaced, fails on 9f4855e.

Written before the fixes; they fail on 09e11e8 — record
docs/iec62304/records/risk_verification/CAPA-015_review2_tests_on_pr65_2026-10-24.json.
"""
import importlib

import pytest
from starlette.requests import Request

from tests.unit.test_capa015_audit_and_session import env, _mod, SEG, _deny_objects  # noqa: F401


def _req(xff, host=None, client="10.0.0.9"):
    headers = [(b"x-forwarded-for", xff.encode())]
    if host:
        headers.append((b"x-forwarded-host", host.encode()))
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers, "client": (client, 1)})


def _client_ip():
    return importlib.import_module("app.core.client_ip").client_ip


# =============================================================================== N1
@pytest.mark.unit
def test_rc067_no_client_header_chooses_the_hop_count():
    client_ip = _client_ip()
    # attacker -> run.app directly; Google's front end appends the real address 198.51.100.200
    assert client_ip(_req("6.6.6.6, 198.51.100.200")) == "198.51.100.200"
    assert client_ip(_req("6.6.6.6, 198.51.100.200", "app.mstool-ai.com")) == "198.51.100.200", \
        "a client-sent X-Forwarded-Host must not make the server trust a client-sent hop"
    assert client_ip(_req("6.6.6.6, 203.0.113.7, 198.51.100.200", "app.mstool-ai.com")) == "198.51.100.200"


@pytest.mark.unit
def test_rc067_steps_left_only_over_published_hosting_egress_addresses():
    client_ip = _client_ip()
    # Hosting (Fastly) appends the client, Google's front end appends Hosting's egress address
    assert client_ip(_req("203.0.113.7, 151.101.1.1")) == "203.0.113.7"
    assert client_ip(_req("6.6.6.6, 203.0.113.7, 151.101.1.1")) == "203.0.113.7"
    # a 3-entry chain through two egress addresses never collapses to a proxy address
    assert client_ip(_req("203.0.113.7, 151.101.64.10, 151.101.1.1")) == "203.0.113.7"
    assert client_ip(_req("203.0.113.7, 2a04:4e42::1")) == "203.0.113.7"
    # an egress-looking address the CLIENT wrote, left of a real address, is not trusted
    assert client_ip(_req("151.101.1.1, 198.51.100.200")) == "198.51.100.200"


@pytest.mark.unit
def test_rc067_the_egress_list_is_sourced_dated_and_replaceable_without_a_rebuild(monkeypatch):
    mod = importlib.import_module("app.core.client_ip")
    assert "fastly" in mod.EGRESS_SOURCE_URL.lower() and mod.EGRESS_LIST_DATE[:4] == "2026"
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "192.0.2.0/24")       # a Cloud Run settings update
    assert mod.client_ip(_req("203.0.113.7, 192.0.2.5")) == "203.0.113.7"
    assert mod.client_ip(_req("203.0.113.7, 151.101.1.1")) == "151.101.1.1", "the override replaces the list"


@pytest.mark.unit
def test_rc067_the_egress_list_is_the_published_fastly_list(monkeypatch):
    # Coordinator check 2026-10-24 against https://api.fastly.com/public-ip-list: the first transcription
    # lacked 90.98.0.0/17, 90.98.128.0/18 and 2a04:4e44::/32 and had 2a04:4e42::/32 instead of /31.
    monkeypatch.delenv("TRUSTED_PROXY_CIDRS", raising=False)
    monkeypatch.delenv("TRUST_FORWARDED_FOR", raising=False)
    mod = importlib.import_module("app.core.client_ip")
    assert len(mod.EGRESS_CIDRS) == 24 and len(set(mod.EGRESS_CIDRS)) == 24, "21 IPv4 + 3 IPv6 ranges"
    # one address from each previously missing range (90.98.128.0/18 ends at 90.98.191.255)
    for egress in ("90.98.1.1", "90.98.150.1", "2a04:4e43::1", "2a04:4e44::1"):
        assert mod.client_ip(_req(f"203.0.113.7, {egress}")) == "203.0.113.7", egress
    # just outside the published ranges: not an egress address, so it is the client
    for outside in ("90.98.200.1", "2a04:4e45::1"):
        assert mod.client_ip(_req(f"203.0.113.7, {outside}")) == outside, outside


@pytest.mark.unit
def test_rc067_the_rate_limit_key_cannot_be_chosen_by_the_client():
    from app.core.security.rate_limit_middleware import RateLimitMiddleware, IPBlacklistMiddleware
    for cls in (RateLimitMiddleware, IPBlacklistMiddleware):
        inst = object.__new__(cls)
        assert cls._get_client_ip(inst, _req("6.6.6.6, 198.51.100.200", "app.mstool-ai.com")) == "198.51.100.200"
        assert cls._get_client_ip(inst, _req("203.0.113.7, 151.101.1.1")) == "203.0.113.7"


# =============================================================================== N4
@pytest.mark.unit
def test_rc067_anonymous_noise_never_pushes_an_authenticated_failure_out_of_the_trail(env, monkeypatch):
    _deny_objects(monkeypatch)
    ip = "198.51.100.77"
    for i in range(30):   # noise from the same workstation (anonymous, forged tokens)
        env.client.get("/api/v1/clinical/tools", headers={"Authorization": f"Bearer junk-{i}", "X-Forwarded-For": ip})
    r = env.client.post(f"/api/v1/segmentation/{SEG}/ai-review/confirm",
                        headers={**env.bearer(env.rad), "X-Forwarded-For": ip})
    assert r.status_code == 404
    recs = [x for x in env.records("clinical.segmentation.confirm") if x.get("ip_address") == ip]
    assert len(recs) == 1, "an authenticated user's failed clinical action must always be durable"
    assert recs[0]["actor_user_id"] == env.rad.id and recs[0]["outcome"] == "failure"
    anonymous = [x for x in env.records() if x.get("ip_address") == ip and not x.get("actor_user_id")]
    assert len(anonymous) <= 30


# =============================================================================== N2
@pytest.mark.unit
def test_rc068_a_developer_env_file_cannot_break_the_test_suite(tmp_path, monkeypatch):
    from app.core.config import SecuritySettings
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60\nREFRESH_TOKEN_IDLE_MINUTES=30\n")
    s = SecuritySettings()          # the suite's own values take precedence over a developer .env
    assert (s.JWT_ACCESS_TOKEN_EXPIRE_MINUTES, s.REFRESH_TOKEN_IDLE_MINUTES, s.REFRESH_TOKEN_ABSOLUTE_HOURS) == (15, 30, 12)


# =============================================================================== nit
class _WA:
    def generate_registration(self, user_id, username, display_name):
        return {"challenge": "c"}


@pytest.mark.unit
def test_rc067_starting_a_passkey_registration_is_not_recorded_as_a_registration(env, monkeypatch):
    auth_routes = _mod("app.api.routes.auth")
    monkeypatch.setattr(auth_routes, "_get_webauthn_service", lambda: _WA())
    r = env.client.post("/api/v1/auth/webauthn/register/begin", headers=env.bearer(env.rad), json={})
    assert r.status_code == 200
    rec = [x for x in env.records() if x.get("endpoint") == "/api/v1/auth/webauthn/register/begin"]
    assert len(rec) == 1 and rec[0]["event_type"] == "auth.credential.register_begin", rec
    assert not env.records("auth.credential.register")
