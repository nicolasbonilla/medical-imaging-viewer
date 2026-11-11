"""Study-scoped capability for AI agent runs, enforced by the backend — IEC 62304 Class C.

Risk control RC-121 for HAZ-021 (DRAFT, PENDING owner approval). Fifth independent review of PR #79, the
structural finding: the agent platform enforced a run's study scope by recognising id-shaped strings in tool
results (RC-114); ids of another shape slipped through and harmless strings refused whole results. The scope is
now enforced at the SOURCE, by the object-level authorization that already protects every route (CAPA-009,
RC-026 / RC-028 / RC-036):

1. ISSUE. For a run, the backend issues a capability for ONE patient and the listed studies of that patient,
   bound to the clinician, valid at most ``MAX_TTL_SECONDS``: ``issue_for_studies`` authorizes every study with
   the CAPA-009 resolver (``resource_access.authorize_study_id``, the care-team decision) before signing. The
   token is HMAC-SHA-256 signed with a key that never leaves the backend (``AGENT_SCOPE_KEY``, or derived from
   ``JWT_SECRET_KEY``; neither set -> nothing is issued or accepted: fail closed).
2. CARRY. The agent platform keeps it in ``RunScope.capability``; the assistant's backend client sends it in the
   ``X-MSTool-Agent-Scope`` header with every request (``app.agent_platform.capability``). The model never sees it.
3. ENFORCE. ``AgentScopeMiddleware`` verifies the header (a bad, expired or ambiguous one -> 403; a route that is
   not one of the assistant's object-authorized read routes -> 403) and makes the scope current for the request.
   The CAPA-009 chokepoints then refuse, with the SAME 404 as an object the clinician may not see:
   - any object whose owning patient is not the scope's patient, or a request of another user
     (``resource_access.authorize_resolved_patient``, ``patient_access_dependency.authorize_patient_access``);
   - any study, series, instance, segmentation or imaging file of another study (the study resolvers and the
     storage-path check), even of the same patient;
   - an administrator's archive-wide listing (the ADMIN bypass of the list routes does not apply to an agent).
   So a tool with a bug, or a model that steers it, CANNOT fetch an object outside the run's study, whatever the
   id walk of the platform (now the second layer) recognises.

Without the header nothing changes: the clinician's own authorization applies as before.
"""
from __future__ import annotations

import base64
import contextlib
import contextvars
import hashlib
import hmac
import json
import os
import re
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import FrozenSet, Iterable, Iterator, Optional
from uuid import UUID

from fastapi import HTTPException, status

from app.agent_platform.capability import ASSISTANT_CLIENT, CAPABILITY_HEADER, CLIENT_HEADER
from app.core.logging import get_logger
from app.mcp._backend import AGENT_GET_ROUTES, AGENT_SCOPE_PATH, COMPUTE_ONLY_POST_PATHS, PAID_MODEL_POST_PATHS

logger = get_logger(__name__)

TOKEN_VERSION = 1
DEFAULT_TTL_SECONDS = 900
MAX_TTL_SECONDS = 3600
MAX_STUDIES = 20
MAX_TOKEN_CHARS = 4096
MIN_SECRET_CHARS = 32
_KEY_LABEL = b"mstool-agent-scope-v1"
_B64 = re.compile(r"[A-Za-z0-9_-]+")
_IDENT = re.compile(r"[A-Za-z0-9:_.@-]{1,128}")

# The ONLY routes an agent-scoped request may reach — built from the ONE list of the assistant's client
# (app/mcp/_backend.py; sixth review of PR #79, C3): its read routes and its compute-only POST routes, MINUS the
# routes that call a paid model (S2: they would bypass the agent's cost ledger, RC-112). Each is object-authorized
# by CAPA-009 (tests/unit/test_capa009_*: ROUTE_AUTH).
API_PREFIX = "/api/v1"
AGENT_ROUTES = tuple(("GET", re.compile(re.escape(API_PREFIX) + rx)) for rx in AGENT_GET_ROUTES) + tuple(
    ("POST", re.compile(re.escape(API_PREFIX + p))) for p in sorted(COMPUTE_ONLY_POST_PATHS - PAID_MODEL_POST_PATHS))
# Sixth review (S1): the one route an assistant request may reach WITHOUT a scope — the issuance of its pass.
ISSUE_ROUTE = ("POST", API_PREFIX + AGENT_SCOPE_PATH)


class AgentScopeError(ValueError):
    """A capability that cannot be issued or accepted."""


@dataclass(frozen=True)
class AgentScope:
    user_id: str
    patient_id: str
    study_ids: FrozenSet[str]
    run_id: str
    expires_at: int


_ACTIVE: "contextvars.ContextVar[Optional[AgentScope]]" = contextvars.ContextVar("mstool_agent_scope", default=None)


def active_scope() -> Optional[AgentScope]:
    return _ACTIVE.get()


def scope_active() -> bool:
    return _ACTIVE.get() is not None


@contextlib.contextmanager
def scope_context(scope: Optional[AgentScope]) -> Iterator[None]:
    token = _ACTIVE.set(scope)
    try:
        yield
    finally:
        _ACTIVE.reset(token)


# ---------------------------------------------------------------------------- token
def _key() -> bytes:
    for name in ("AGENT_SCOPE_KEY", "JWT_SECRET_KEY"):
        secret = os.environ.get(name, "")
        if len(secret) >= MIN_SECRET_CHARS:
            return hmac.new(secret.encode("utf-8"), _KEY_LABEL, hashlib.sha256).digest()
    raise AgentScopeError("no agent-scope key: AGENT_SCOPE_KEY or JWT_SECRET_KEY (32 characters or more) is not set")


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _uuid(value) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        raise AgentScopeError("not a UUID")


def _canon(value) -> Optional[str]:
    try:
        return str(UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        return None


def issue_scope_token(*, user_id: str, patient_id: str, study_ids: Iterable[str], run_id: str,
                      ttl_seconds: int = DEFAULT_TTL_SECONDS, now: Optional[int] = None) -> str:
    """Sign a capability. Callers authorize first (``issue_for_studies``); this only validates and signs."""
    if not isinstance(user_id, str) or not _IDENT.fullmatch(user_id):
        raise AgentScopeError("user id not well formed")
    if not isinstance(run_id, str) or not _IDENT.fullmatch(run_id):
        raise AgentScopeError("run id not well formed")
    if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or not 0 < ttl_seconds <= MAX_TTL_SECONDS:
        raise AgentScopeError(f"the lifetime must be 1 to {MAX_TTL_SECONDS} seconds")
    studies = sorted({_uuid(s) for s in (study_ids or ())})
    if not 0 < len(studies) <= MAX_STUDIES:
        raise AgentScopeError(f"a scope names 1 to {MAX_STUDIES} studies")
    issued = int(time.time()) if now is None else int(now)
    payload = {"v": TOKEN_VERSION, "uid": user_id, "pid": _uuid(patient_id), "sids": studies, "rid": run_id,
               "exp": issued + ttl_seconds}
    body = _b64(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    sig = _b64(hmac.new(_key(), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_scope_token(token, *, now: Optional[int] = None) -> AgentScope:
    """The scope a token grants, or AgentScopeError (signature, shape, expiry, lifetime)."""
    key = _key()
    if not isinstance(token, str) or not 0 < len(token) <= MAX_TOKEN_CHARS or token.count(".") != 1:
        raise AgentScopeError("not a scope token")
    body, sig = token.split(".")
    if not _B64.fullmatch(body) or not _B64.fullmatch(sig):
        raise AgentScopeError("not a scope token")
    expected = _b64(hmac.new(key, body.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, sig):
        raise AgentScopeError("bad signature")
    try:
        payload = json.loads(_unb64(body))
    except (ValueError, UnicodeDecodeError):
        raise AgentScopeError("bad payload")
    if not isinstance(payload, dict) or set(payload) != {"v", "uid", "pid", "sids", "rid", "exp"} \
            or payload["v"] != TOKEN_VERSION:
        raise AgentScopeError("bad payload")
    uid, pid, sids, rid, exp = payload["uid"], payload["pid"], payload["sids"], payload["rid"], payload["exp"]
    if not (isinstance(uid, str) and _IDENT.fullmatch(uid) and isinstance(rid, str) and _IDENT.fullmatch(rid)
            and isinstance(pid, str) and _canon(pid) == pid and isinstance(sids, list)
            and 0 < len(sids) <= MAX_STUDIES and all(isinstance(s, str) and _canon(s) == s for s in sids)
            and isinstance(exp, int) and not isinstance(exp, bool)):
        raise AgentScopeError("bad payload")
    current = int(time.time()) if now is None else int(now)
    if not current < exp <= current + MAX_TTL_SECONDS:
        raise AgentScopeError("expired")
    return AgentScope(user_id=uid, patient_id=pid, study_ids=frozenset(sids), run_id=rid, expires_at=exp)


# ---------------------------------------------------------------------------- enforcement (CAPA-009 chokepoints)
def allows_patient(patient_id, user) -> bool:
    """No agent scope -> True. Otherwise only the scope's patient, and only for the user it was issued to."""
    scope = _ACTIVE.get()
    if scope is None:
        return True
    return (_canon(patient_id) or str(patient_id)) == scope.patient_id and str(getattr(user, "id", "")) == scope.user_id


def allows_study(study_id) -> bool:
    scope = _ACTIVE.get()
    return scope is None or _canon(study_id) in scope.study_ids


def study_of_storage_path(path) -> Optional[str]:
    """The study of a ``patients/{uuid}/studies/{uuid}/...`` storage path, or None."""
    if not isinstance(path, str):
        return None
    parts = path.split("/")
    if len(parts) < 4 or parts[0] != "patients" or parts[2] != "studies":
        return None
    return _canon(parts[3])


def allows_storage_path(path) -> bool:
    scope = _ACTIVE.get()
    if scope is None:
        return True
    study = study_of_storage_path(path)
    return study is not None and study in scope.study_ids


def route_allowed(method: str, path: str) -> bool:
    return any(method == m and rx.fullmatch(path) for m, rx in AGENT_ROUTES)


# ---------------------------------------------------------------------------- issuance
async def issue_for_studies(study_ids, user, *, run_id: str, ttl_seconds: int = DEFAULT_TTL_SECONDS,
                            now: Optional[int] = None) -> str:
    """Authorize every study for ``user`` with the CAPA-009 resolver (404 when not entitled), require ONE owning
    patient, and sign the capability. An agent-scoped request can never mint one."""
    ids, patients = await _authorize_studies(study_ids, user)
    token = sign_for_patient(user, set(patients), ids, run_id=run_id, ttl_seconds=ttl_seconds, now=now)
    _record_session(user, _canon(patients[0]))
    return token


async def _authorize_studies(study_ids, user):
    """Each study once (deduplicated), with the services built ONCE, one after the other, stopping at the first
    refusal (seventh review of PR #79, R10: no access-audit row is written after a refused study)."""
    from app.security import resource_access
    if scope_active():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="An agent request cannot issue an agent scope")
    canon = [_canon(s) for s in (study_ids or ())]
    ids = sorted(set(canon))
    if not ids or None in canon or len(ids) > MAX_STUDIES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Name 1 to {MAX_STUDIES} study UUIDs")
    services = resource_access.study_services()
    patients = []
    for sid in ids:
        patients.append(await resource_access.authorize_study_id(sid, user, services=services))
    return ids, patients


async def preview_studies(study_ids, user) -> dict:
    """What the physician is asked to confirm (seventh review, R1): the patient reference (the first 8 characters of
    the patient's id, as the web app shows it), and each study's reference, date and number of series. Nothing is
    issued or stored."""
    from app.security import resource_access
    ids, patients = await _authorize_studies(study_ids, user)
    if len({_canon(p) for p in patients}) != 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="An agent scope covers the studies of one patient")
    studies_service = resource_access.study_services()[0]
    studies = []
    for sid in ids:
        try:
            study = await studies_service.get_study(sid, include_stats=True)
        except Exception:  # noqa: BLE001 — details are informative only; the authorization above already passed
            study = None
        date = getattr(study, "study_date", None) or getattr(study, "date", None)
        series = getattr(study, "series_count", None)
        if series is None and isinstance(getattr(study, "series", None), (list, tuple)):
            series = len(study.series)
        studies.append({"study_ref": sid[:8], "date": str(date)[:10] if date else None,
                        "series": series if isinstance(series, int) else None})
    return {"patient_ref": _canon(patients[0])[:8], "studies": studies, "expires_in": DEFAULT_TTL_SECONDS}


# Seventh review (R1): the patient of each clinician's latest assistant session, to audit a PATIENT SWITCH. In
# memory, bounded (like the initiator registry, CAPA-009); a restart only loses the comparison point.
_LAST_PATIENT: "OrderedDict[str, str]" = OrderedDict()
_MAX_SESSIONS = 50_000


def _record_session(user, patient_id: Optional[str]) -> None:
    uid = str(getattr(user, "id", ""))
    previous = _LAST_PATIENT.get(uid)
    _LAST_PATIENT[uid] = patient_id
    _LAST_PATIENT.move_to_end(uid)
    while len(_LAST_PATIENT) > _MAX_SESSIONS:
        _LAST_PATIENT.popitem(last=False)
    if previous and patient_id and previous != patient_id:
        logger.warning("Agent scope: patient switch", extra={"user_id": uid})
        try:
            from app.core.logging.audit import AuditEventType, AuditOutcome, emit_audit
            emit_audit(AuditEventType.CLINICAL_AI_RUN, AuditOutcome.SUCCESS, user_id=uid,
                       username=getattr(user, "username", None), role=getattr(user, "role", None),
                       reason="agent.scope:patient_switch", resource_type="agent_scope",
                       resource_ids={"from_patient": previous, "to_patient": patient_id})
        except Exception:  # noqa: BLE001 — auditing never breaks the issuance
            pass


def sign_for_patient(user, patients, study_ids, *, run_id: str, ttl_seconds: int = DEFAULT_TTL_SECONDS,
                     now: Optional[int] = None) -> str:
    """Sign for studies ALREADY authorized; they must belong to exactly one patient (compared as canonical UUIDs:
    sixth review, C4 — one patient in two spellings is one patient)."""
    canonical = {_canon(p) for p in patients}
    if len(canonical) != 1 or None in canonical:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="An agent scope covers the studies of one patient")
    try:
        token = issue_scope_token(user_id=str(user.id), patient_id=next(iter(canonical)), study_ids=study_ids,
                                  run_id=run_id, ttl_seconds=ttl_seconds, now=now)
    except AgentScopeError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Agent scope not available")
    logger.info("Agent scope issued", extra={"user_id": str(user.id), "studies": len(study_ids), "run_id": run_id})
    return token


# ---------------------------------------------------------------------------- the guard
class AgentScopeMiddleware:
    """Pure ASGI: verify the capability header, keep agent requests on the assistant's routes, and make the scope
    current for the request. A request without the header passes unchanged."""

    _HEADER = CAPABILITY_HEADER.lower().encode("latin-1")
    _CLIENT = CLIENT_HEADER.lower().encode("latin-1")

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        headers = scope.get("headers") or ()
        values = [v for k, v in headers if k.lower() == self._HEADER]
        assistant = any(k.lower() == self._CLIENT and v == ASSISTANT_CLIENT.encode("latin-1") for k, v in headers)
        if not values and not assistant:
            return await self.app(scope, receive, send)            # not an agent request: unchanged
        method, path = str(scope.get("method", "")).upper(), str(scope.get("path", ""))
        try:
            if not values:
                # Sixth review of PR #79 (S1): an ASSISTANT request without a pass reaches only the issuance of
                # its pass; anything else is refused, whatever the client did or did not volunteer.
                if scope["type"] == "http" and (method, path) == ISSUE_ROUTE:
                    return await self.app(scope, receive, send)
                raise AgentScopeError("an assistant request needs a study session")
            if len(values) != 1 or scope["type"] != "http":
                raise AgentScopeError("one header, HTTP only")
            granted = verify_scope_token(values[0].decode("latin-1"))
            if not route_allowed(method, path):
                raise AgentScopeError("not an agent route")
        except (AgentScopeError, UnicodeDecodeError) as exc:
            logger.warning("Agent scope refused", extra={"reason": str(exc)[:80]})
            if scope["type"] == "websocket":
                return await send({"type": "websocket.close", "code": 1008})
            body = b'{"detail":"Agent scope refused"}'
            await send({"type": "http.response.start", "status": 403,
                        "headers": [(b"content-type", b"application/json"),
                                    (b"content-length", str(len(body)).encode("ascii"))]})
            return await send({"type": "http.response.body", "body": body})
        token = _ACTIVE.set(granted)
        try:
            await self.app(scope, receive, send)
        finally:
            _ACTIVE.reset(token)
