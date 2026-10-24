"""
Audit Middleware for FastAPI
ISO 27001 A.12.4.1 - Event logging

CAPA-015 (RC-067, REQ-SEC-024; HAZ-010) — one audit record per API request:

- WHO: the actor is read from the bearer token (signature verified; nothing is enforced here —
  the routes still authenticate and authorize). Role included.
- WHAT: the route TEMPLATE (`/api/v1/segmentation/{segmentation_id}/save`), never the concrete
  path or the query string; the resource identifiers taken from the path parameters (and, for a
  few small JSON routes, from the request body: `tp1`/`tp2`/`masks` ids, `file_id`, report
  template and language); a semantic action for the clinically relevant routes
  (`ROUTE_ACTIONS`: segmentation create/save/modify/delete/confirm, lesion readings,
  longitudinal decisions, AI report generation, AI and clinical-tool runs, DICOM-SEG export,
  care-team changes).
- OUTCOME: from the HTTP status (success / failure / denied) and the status code.
- CORRELATION: the request id (`X-Request-ID`) and the Cloud trace id.

Authentication routes (`/api/v1/auth/*`) record their own, richer events (login success,
failure with a reason code, lock-out, refresh, reuse, logout, password change, admin changes);
for them this middleware adds a record only for a 401/403 nobody else recorded.

Durable (Firestore) policy: every record goes to stdout; Firestore receives every state-changing
request, every clinical action, every 401/403, and reads of patient data once per actor, route
and resource per AUDIT_READ_DEDUP_SECONDS (default 300 s) on each instance — a viewer fetches
hundreds of slices, and one record per slice would make the trail unreadable and costly.
Requests that matched no route are kept on stdout only.

@module core.logging.audit_middleware
"""

import asyncio
import json
import os
import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Dict, Optional, Tuple

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.logging.audit import (
    get_audit_logger,
    AuditEventType,
    AuditSeverity,
    AuditOutcome,
    AuditEvent,
    begin_request_audit,
    end_request_audit,
    client_ip,
    trace_id_of,
    sha256_prefix,
)
from app.core.logging.config import get_logger

logger = get_logger(__name__)

API_PREFIX = "/api/v1"
AUTH_PREFIX = "/api/v1/auth"
EXCLUDED_PREFIXES = ("/api/health", "/api/docs", "/api/redoc", "/api/openapi.json")
READ_METHODS = {"GET", "HEAD"}

E = AuditEventType
# (method, route template) -> (event type, resource type). A route listed here is a clinical
# or administrative action: always durable, never deduplicated.
ROUTE_ACTIONS: Dict[Tuple[str, str], Tuple[AuditEventType, str]] = {
    ("POST", "/api/v1/segmentation/create"): (E.CLINICAL_SEGMENTATION_CREATE, "segmentation"),
    ("POST", "/api/v1/segmentation/{segmentation_id}/save"): (E.CLINICAL_SEGMENTATION_SAVE, "segmentation"),
    ("PUT", "/api/v1/segmentation/{segmentation_id}/mask/binary"): (E.CLINICAL_SEGMENTATION_SAVE, "segmentation"),
    ("POST", "/api/v1/segmentation/{segmentation_id}/paint"): (E.CLINICAL_SEGMENTATION_MODIFY, "segmentation"),
    ("PUT", "/api/v1/segmentation/{segmentation_id}/labels"): (E.CLINICAL_SEGMENTATION_MODIFY, "segmentation"),
    ("POST", "/api/v1/segmentation/{segmentation_id}/classify-regions"): (E.CLINICAL_SEGMENTATION_MODIFY, "segmentation"),
    ("DELETE", "/api/v1/segmentation/{segmentation_id}"): (E.CLINICAL_SEGMENTATION_DELETE, "segmentation"),
    ("POST", "/api/v1/segmentation/{segmentation_id}/ai-review/confirm"): (E.CLINICAL_SEGMENTATION_CONFIRM, "segmentation"),
    ("POST", "/api/v1/segmentation/{segmentation_id}/lesion-annotations"): (E.CLINICAL_LESION_ANNOTATION, "segmentation"),
    ("POST", "/api/v1/segmentation/longitudinal/review"): (E.CLINICAL_LONGITUDINAL_REVIEW, "segmentation_pair"),
    ("POST", "/api/v1/ai/report/generate"): (E.CLINICAL_AI_REPORT_GENERATE, "report"),
    ("POST", "/api/v1/ai/segment/auto"): (E.CLINICAL_AI_RUN, "image"),
    ("POST", "/api/v1/ai/segment/interactive"): (E.CLINICAL_AI_RUN, "image"),
    ("POST", "/api/v1/ai/anomaly/detect"): (E.CLINICAL_AI_RUN, "image"),
    ("POST", "/api/v1/clinical/flames/segment"): (E.CLINICAL_AI_RUN, "image"),
    ("POST", "/api/v1/clinical/lst-ai/segment"): (E.CLINICAL_AI_RUN, "image"),
    ("POST", "/api/v1/clinical/synthseg/parcellate"): (E.CLINICAL_AI_RUN, "image"),
    ("GET", "/api/v1/segmentation/{segmentation_id}/export/dicom-seg"): (E.DATA_EXPORT, "segmentation"),
    ("POST", "/api/v1/patients/{patient_id}/care-team"): (E.ADMIN_CARE_TEAM_CHANGED, "patient"),
    ("DELETE", "/api/v1/patients/{patient_id}/care-team/{assignment_id}"): (E.ADMIN_CARE_TEAM_CHANGED, "patient"),
}

# Small JSON routes whose BODY names the objects acted on (read only up to 64 KiB, ids only).
BODY_ID_ROUTES = frozenset({
    "/api/v1/segmentation/longitudinal/review",
    "/api/v1/segmentation/longitudinal/compare",
    "/api/v1/segmentation/longitudinal/sel",
    "/api/v1/segmentation/compare",
    "/api/v1/segmentation/agreement-map",
    "/api/v1/segmentation/create",
    "/api/v1/ai/report/generate",
})
_BODY_LIMIT = 64 * 1024

# Path parameters kept as resource identifiers (others — slice index, credential id — are not).
_PATH_ID_KEYS = {
    "patient_id": "patient_id", "study_id": "study_id", "series_id": "series_id",
    "instance_id": "instance_id", "document_id": "document_id", "segmentation_id": "segmentation_id",
    "version_id": "version_id", "task_id": "task_id", "job_id": "job_id",
    "assignment_id": "assignment_id", "connection_id": "connection_id", "history_id": "history_id",
    "user_id": "target_user_id",
}
_HASHED_PATH_KEYS = {"accession_number": "accession_sha256", "mrn": "mrn_sha256"}

_READ_DEDUP_SECONDS = float(os.environ.get("AUDIT_READ_DEDUP_SECONDS", "300"))
_FLUSH_WAIT_S = float(os.environ.get("AUDIT_FLUSH_WAIT_MS", "500")) / 1000.0
_DEDUP_MAX = 20_000
_dedup: "OrderedDict[Tuple, float]" = OrderedDict()
_dedup_lock = threading.Lock()


def reset_read_dedup() -> None:
    """Forget the read-deduplication window (tests)."""
    with _dedup_lock:
        _dedup.clear()


def _seen_recently(key: Tuple) -> bool:
    now = time.monotonic()
    with _dedup_lock:
        t = _dedup.get(key)
        if t is not None and now - t < _READ_DEDUP_SECONDS:
            return True
        _dedup[key] = now
        _dedup.move_to_end(key)
        while len(_dedup) > _DEDUP_MAX:
            _dedup.popitem(last=False)
        return False


def file_ref_ids(file_id: str) -> Dict[str, str]:
    """Identifiers of an imaging storage reference: patient/study/series ids from the RC-027
    grammar, and a hash of the file name (file names are free text and may contain a name)."""
    out: Dict[str, str] = {"file_sha256": sha256_prefix(file_id)}
    try:
        from app.security.storage_access import parse_patient_storage_ref
        ref = parse_patient_storage_ref(file_id)
        for attr in ("patient_id", "study_id", "series_id"):
            v = getattr(ref, attr, None)
            if v:
                out[attr] = str(v)
    except Exception:  # not a storage reference — the hash alone identifies it
        pass
    return out


def _body_ids(body: Any) -> Tuple[Dict[str, str], Dict[str, Any]]:
    ids: Dict[str, str] = {}
    details: Dict[str, Any] = {}
    if not isinstance(body, dict):
        return ids, details
    for key in ("tp1", "tp2"):
        spec = body.get(key)
        if isinstance(spec, dict) and spec.get("id"):
            kind = spec.get("type")
            ids[f"{key}_{kind}_id" if kind in ("segmentation", "instance") else f"{key}_id"] = str(spec["id"])
    masks = body.get("masks")
    if isinstance(masks, list):
        for i, spec in enumerate(masks[:4]):
            if isinstance(spec, dict) and spec.get("id"):
                ids[f"mask{i + 1}_id"] = str(spec["id"])
    if isinstance(body.get("file_id"), str):
        ids.update(file_ref_ids(body["file_id"]))
    for key in ("segmentation_id", "patient_id", "study_id"):
        if isinstance(body.get(key), str):
            ids[key] = body[key]
    for key in ("template_type", "language"):
        if isinstance(body.get(key), str):
            details[key] = body[key]
    if isinstance(body.get("decisions"), list):
        details["decisions"] = len(body["decisions"])
    return ids, details


def _path_ids(path_params: Dict[str, Any]) -> Dict[str, str]:
    ids: Dict[str, str] = {}
    for name, value in (path_params or {}).items():
        if value is None:
            continue
        if name == "file_id":
            ids.update(file_ref_ids(str(value)))
        elif name in _PATH_ID_KEYS:
            ids[_PATH_ID_KEYS[name]] = str(value)
        elif name in _HASHED_PATH_KEYS:
            ids[_HASHED_PATH_KEYS[name]] = sha256_prefix(str(value))
    return ids


def _actor(request: Request) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """(user_id, username, role) from a valid bearer token, else (None, None, None)."""
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None, None, None
    try:
        from app.security.jwt_manager import get_token_manager
        data = get_token_manager().decode_token_data(auth[7:].strip())
        return data.user_id, data.username, data.role.value
    except Exception:
        return None, None, None


def _outcome(status: int) -> AuditOutcome:
    if status < 400:
        return AuditOutcome.SUCCESS
    if status in (401, 403):
        return AuditOutcome.DENIED
    return AuditOutcome.FAILURE


def _severity(status: int, clinical: bool) -> AuditSeverity:
    if status >= 500:
        return AuditSeverity.HIGH
    if status >= 400:
        return AuditSeverity.MEDIUM
    return AuditSeverity.MEDIUM if clinical else AuditSeverity.LOW


class AuditMiddleware(BaseHTTPMiddleware):
    """
    Middleware for automatic audit logging of HTTP requests.

    ISO 27001 A.12.4.1 - Event logging
    ISO 27001 A.12.4.3 - Administrator and operator logs
    """

    def __init__(self, app: ASGIApp):
        """Initialize audit middleware."""
        super().__init__(app)
        self.audit_logger = get_audit_logger()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if not path.startswith(API_PREFIX) or path.startswith(EXCLUDED_PREFIXES):
            return await call_next(request)

        ctx, token = begin_request_audit()
        start_time = time.time()
        body_ids: Dict[str, str] = {}
        body_details: Dict[str, Any] = {}
        try:
            if request.method == "POST" and path in BODY_ID_ROUTES:
                body_ids, body_details = await self._peek_body(request)
            actor = _actor(request)
            try:
                response = await call_next(request)
                status = response.status_code
            except Exception:
                self._record(request, 500, actor, ctx, body_ids, body_details, start_time)
                raise
            self._record(request, status, actor, ctx, body_ids, body_details, start_time)
            await self._wait_for_durable(ctx)
            response.headers["X-Request-Duration-Ms"] = f"{(time.time() - start_time) * 1000:.2f}"
            return response
        finally:
            end_request_audit(token)

    @staticmethod
    async def _peek_body(request: Request) -> Tuple[Dict[str, str], Dict[str, Any]]:
        try:
            length = int(request.headers.get("content-length") or 0)
            if "json" not in (request.headers.get("content-type") or "") or not 0 < length <= _BODY_LIMIT:
                return {}, {}
            return _body_ids(json.loads(await request.body()))
        except Exception:
            return {}, {}

    @staticmethod
    async def _wait_for_durable(ctx) -> None:
        """Bounded wait for this request's durable writes while the sink is healthy (Cloud Run
        throttles the CPU between requests). Never fails the request."""
        if not ctx.futures or _FLUSH_WAIT_S <= 0:
            return
        try:
            from app.core.logging.audit_sink import get_durable_audit_sink
            if not get_durable_audit_sink().is_healthy():
                return
            waiters = [asyncio.wrap_future(f) for f in ctx.futures]
            await asyncio.wait_for(asyncio.shield(asyncio.gather(*waiters, return_exceptions=True)), _FLUSH_WAIT_S)
        except (asyncio.TimeoutError, Exception):
            return

    def _record(self, request, status, actor, ctx, body_ids, body_details, start_time) -> None:
        try:
            event, durable = self._build(request, status, actor, ctx, body_ids, body_details, start_time)
            if event is not None:
                self.audit_logger.log_event(event, durable=durable)
        except Exception as e:  # noqa: BLE001 — auditing must never break the request
            logger.error(f"Audit middleware failed to record a request: {e}", exc_info=True)

    def _build(self, request, status, actor, ctx, body_ids, body_details, start_time):
        method = request.method
        path = request.url.path
        route = request.scope.get("route")
        template = getattr(route, "path", None)
        user_id, username, role = actor

        if path.startswith(AUTH_PREFIX):
            # authentication routes record their own events; add one only for an unrecorded 401/403
            if ctx.explicit or status not in (401, 403):
                return None, False

        mapped = ROUTE_ACTIONS.get((method, template)) if template else None
        if mapped:
            event_type, resource_type = mapped
        elif status == 401:
            event_type, resource_type = E.AUTH_TOKEN_INVALID, None
        elif status == 403:
            event_type, resource_type = E.AUTHZ_ACCESS_DENIED, None
        elif method in READ_METHODS:
            event_type, resource_type = E.DATA_ACCESS_READ, None
        elif method == "DELETE":
            event_type, resource_type = E.DATA_DELETE, None
        else:
            event_type, resource_type = E.DATA_MODIFY, None

        ids = {**_path_ids(request.scope.get("path_params") or {}), **body_ids}
        durable = True
        if template is None and status not in (401, 403):
            durable = False                     # matched no route: stdout only
        elif event_type == E.DATA_ACCESS_READ:
            key = (user_id or client_ip(request), template, tuple(sorted(ids.items())), status // 100)
            durable = not _seen_recently(key)

        event = AuditEvent(
            event_type=event_type,
            severity=_severity(status, bool(mapped)),
            outcome=_outcome(status),
            user_id=user_id,
            username=username,
            user_role=role,
            ip_address=client_ip(request),
            user_agent=request.headers.get("User-Agent"),
            resource_type=resource_type,
            resource_ids=ids,
            action=event_type.value,
            method=method,
            endpoint=template,
            status_code=status,
            details={**body_details, **({} if durable or event_type != E.DATA_ACCESS_READ
                                        else {"deduplicated_window_s": int(_READ_DEDUP_SECONDS)})},
            trace_id=trace_id_of(request),
            source="middleware",
            iso27001_controls=["A.12.4.1"],
        )
        return event, durable
