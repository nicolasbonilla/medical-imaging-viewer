"""
Security Audit Logging System
ISO 27001 A.12.4.1 - Event logging
ISO 27001 A.12.4.3 - Administrator and operator logs

Provides comprehensive audit trail for security-critical events including:
- Authentication events (login, logout, failed attempts)
- Authorization events (access granted/denied)
- Data access events (PHI access, file access)
- Configuration changes
- Security incidents
- Administrative actions

CAPA-015 (RC-067, REQ-SEC-024; HAZ-010): every record is (1) written at once as one structured
JSON line on stdout for Cloud Logging and (2) queued for the append-only Firestore collection
`audit_logs` (see audit_sink.py). The local file is kept only outside Cloud Run, where it is a
developer convenience — on Cloud Run the disk is per-instance memory that vanishes on restart.
Records are built by `build_audit_record`: an allow-list of fields — no request body, no query
string, no description text, no image data; identifiers only, file names hashed.

@module core.logging.audit
"""

import ipaddress
import json
import hashlib
import os
import re
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List
from pathlib import Path
from dataclasses import dataclass, asdict, field

from app.core.logging.config import get_logger
from app.core.logging.context import get_request_id

logger = get_logger(__name__)


class AuditEventType(str, Enum):
    """
    Audit event types (ISO 27001 A.12.4.1).

    Categorizes security events for compliance reporting and incident response.
    """
    # Authentication Events (A.9.4.2)
    AUTH_LOGIN_SUCCESS = "auth.login.success"
    AUTH_LOGIN_FAILED = "auth.login.failed"
    AUTH_LOGOUT = "auth.logout"
    AUTH_TOKEN_REFRESH = "auth.token.refresh"
    AUTH_TOKEN_REVOKED = "auth.token.revoked"
    AUTH_PASSWORD_CHANGE = "auth.password.change"
    AUTH_PASSWORD_RESET = "auth.password.reset"
    AUTH_ACCOUNT_LOCKED = "auth.account.locked"
    AUTH_ACCOUNT_UNLOCKED = "auth.account.unlocked"
    AUTH_TOKEN_INVALID = "auth.token.invalid"                # CAPA-015: refused for a missing/expired token
    AUTH_TOKEN_REUSE_DETECTED = "auth.token.reuse_detected"  # CAPA-015: a rotated refresh token was replayed

    # Authorization Events (A.9.4.1)
    AUTHZ_ACCESS_GRANTED = "authz.access.granted"
    AUTHZ_ACCESS_DENIED = "authz.access.denied"
    AUTHZ_PERMISSION_CHANGED = "authz.permission.changed"
    AUTHZ_ROLE_ASSIGNED = "authz.role.assigned"
    AUTHZ_ROLE_REVOKED = "authz.role.revoked"

    # Data Access Events (A.9.4.5, HIPAA)
    DATA_ACCESS_PHI = "data.access.phi"
    DATA_ACCESS_FILE = "data.access.file"
    DATA_ACCESS_METADATA = "data.access.metadata"
    DATA_EXPORT = "data.export"
    DATA_DELETE = "data.delete"
    DATA_MODIFY = "data.modify"
    DATA_ACCESS_READ = "data.access.read"          # CAPA-015: read of patient-scoped data (deduplicated)

    # Clinical Events (CAPA-015, RC-067) — actions that create, change or decide on clinical data
    CLINICAL_SEGMENTATION_CREATE = "clinical.segmentation.create"
    CLINICAL_SEGMENTATION_SAVE = "clinical.segmentation.save"
    CLINICAL_SEGMENTATION_MODIFY = "clinical.segmentation.modify"
    CLINICAL_SEGMENTATION_DELETE = "clinical.segmentation.delete"
    CLINICAL_SEGMENTATION_CONFIRM = "clinical.segmentation.confirm"
    CLINICAL_LESION_ANNOTATION = "clinical.lesion.annotation"
    CLINICAL_LONGITUDINAL_REVIEW = "clinical.longitudinal.review"
    CLINICAL_AI_REPORT_GENERATE = "clinical.ai_report.generate"
    CLINICAL_AI_RUN = "clinical.ai.run"

    # System Events (A.12.4.1)
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_CONFIG_CHANGE = "system.config.change"
    SYSTEM_KEY_ROTATION = "system.key.rotation"
    SYSTEM_BACKUP_CREATED = "system.backup.created"
    SYSTEM_RESTORE_COMPLETED = "system.restore.completed"

    # Security Events (A.16.1.1)
    SECURITY_INTRUSION_DETECTED = "security.intrusion.detected"
    SECURITY_BRUTE_FORCE = "security.brute_force"
    SECURITY_MALWARE_DETECTED = "security.malware.detected"
    SECURITY_POLICY_VIOLATION = "security.policy.violation"
    SECURITY_ENCRYPTION_FAILURE = "security.encryption.failure"
    SECURITY_DATA_INTEGRITY_VIOLATION = "security.data.integrity_violation"
    SECURITY_KEY_COMPROMISED = "security.key.compromised"

    # Administrative Events (A.12.4.3)
    ADMIN_USER_CREATED = "admin.user.created"
    ADMIN_USER_DELETED = "admin.user.deleted"
    ADMIN_USER_MODIFIED = "admin.user.modified"
    ADMIN_ROLE_CREATED = "admin.role.created"
    ADMIN_ROLE_DELETED = "admin.role.deleted"
    ADMIN_PERMISSION_MODIFIED = "admin.permission.modified"
    ADMIN_CARE_TEAM_CHANGED = "admin.care_team.changed"   # CAPA-015

    # Audit trail access (CAPA-015): reading the trail is itself recorded
    AUDIT_LOG_READ = "audit.log.read"

    # Compliance Events (A.18.1.1)
    COMPLIANCE_AUDIT_STARTED = "compliance.audit.started"
    COMPLIANCE_AUDIT_COMPLETED = "compliance.audit.completed"
    COMPLIANCE_VIOLATION_DETECTED = "compliance.violation.detected"
    COMPLIANCE_REPORT_GENERATED = "compliance.report.generated"


class AuditSeverity(str, Enum):
    """Severity levels for audit events."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AuditOutcome(str, Enum):
    """Outcome of audited action."""
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    DENIED = "denied"


@dataclass
class AuditEvent:
    """
    Immutable audit event record (ISO 27001 A.12.4.1).

    Captures all relevant information about a security event for
    compliance reporting, incident response, and forensic analysis.
    """
    # Required fields (no defaults)
    event_type: AuditEventType
    severity: AuditSeverity
    outcome: AuditOutcome

    # Event identification (with defaults). CAPA-015: a random UUID — it is the record's
    # Firestore document id, so it must never collide (the former time + id() hash could).
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    # Temporal information
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Actor information (who)
    user_id: Optional[str] = None
    username: Optional[str] = None
    user_role: Optional[str] = None
    session_id: Optional[str] = None

    # Source information (from where)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    source_system: Optional[str] = None

    # Target information (what)
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    resource_name: Optional[str] = None

    # Action details (how)
    action: Optional[str] = None
    method: Optional[str] = None
    endpoint: Optional[str] = None

    # Additional context
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Security context
    risk_score: Optional[int] = None  # 0-100
    threat_indicators: List[str] = field(default_factory=list)

    # Compliance tags
    iso27001_controls: List[str] = field(default_factory=list)
    hipaa_requirements: List[str] = field(default_factory=list)

    # Integrity protection
    checksum: Optional[str] = None

    # CAPA-015 (RC-067): request correlation and structured, identifier-only context
    request_id: Optional[str] = None
    trace_id: Optional[str] = None
    status_code: Optional[int] = None
    resource_ids: Dict[str, str] = field(default_factory=dict)
    reason: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    attempted_identifier_sha256: Optional[str] = None
    source: str = "explicit"          # "explicit" (emitted by the code that acted) | "middleware"

    def __post_init__(self):
        """Calculate checksum for tamper detection."""
        if not self.checksum:
            self.checksum = self._calculate_checksum()

    def _calculate_checksum(self) -> str:
        """
        Calculate SHA-256 checksum of event data for integrity verification.

        ISO 27001 A.12.4.2 - Protection of log information
        """
        # Create deterministic string representation
        data = {
            'event_id': self.event_id,
            'event_type': self.event_type.value,
            'timestamp': self.timestamp.isoformat(),
            'user_id': self.user_id,
            'ip_address': self.ip_address,
            'resource_id': self.resource_id,
            'action': self.action,
            'outcome': self.outcome.value,
        }

        data_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()

    def verify_integrity(self) -> bool:
        """
        Verify event integrity using checksum.

        Returns:
            True if checksum is valid, False if tampered
        """
        current_checksum = self.checksum
        self.checksum = None
        calculated = self._calculate_checksum()
        self.checksum = current_checksum
        return calculated == current_checksum

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        # Convert enums to strings
        data['event_type'] = self.event_type.value
        data['severity'] = self.severity.value
        data['outcome'] = self.outcome.value
        # Convert timestamp to ISO format
        data['timestamp'] = self.timestamp.isoformat()
        return data

    def to_json(self) -> str:
        """Serialize to JSON."""
        return json.dumps(self.to_dict(), default=str)


# =============================================================================
# CAPA-015 (RC-067): the audit RECORD — what reaches stdout and Firestore.
# An allow-list: fields not built here never leave the process. No description text, no
# request body, no query string, no image data. Identifiers are kept only when they look like
# identifiers; anything else (a typed login name, a file name) is reduced to a SHA-256 prefix.
# =============================================================================

RECORD_SCHEMA_VERSION = 1

_CLOUD_SEVERITY = {
    AuditSeverity.LOW: "INFO",
    AuditSeverity.MEDIUM: "NOTICE",
    AuditSeverity.HIGH: "WARNING",
    AuditSeverity.CRITICAL: "CRITICAL",
}

_CODE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
_IDENT = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_USERNAME = re.compile(r"^[A-Za-z0-9_.@-]{1,100}$")
_ENDPOINT = re.compile(r"^/[A-Za-z0-9_./{}:-]{0,200}$")
_METHODS = {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}

# Keys of `details`: short codes, counts and flags only — never free text.
DETAIL_KEYS = frozenset({
    "template_type", "language", "decisions", "failed_attempts", "fields_changed", "new_role",
    "revoked_sessions", "rotation_count", "deduplicated_window_s", "role",
})


def sha256_prefix(value: str, length: int = 16) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:length]


def _code(value) -> Optional[str]:
    if value is None:
        return None
    s = value.value if isinstance(value, Enum) else str(value)
    return s if _CODE.match(s) else None


def _ip(value) -> Optional[str]:
    try:
        return str(ipaddress.ip_address(str(value).strip())) if value else None
    except ValueError:
        return None


def _safe_ids(ids: Optional[Dict[str, Any]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k, v in (ids or {}).items():
        if not _CODE.match(str(k)) or v is None:
            continue
        s = str(v)
        out[str(k)] = s if _IDENT.match(s) else "sha256:" + sha256_prefix(s)
    return out


def _safe_details(details: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in (details or {}).items():
        if k not in DETAIL_KEYS:
            continue
        if isinstance(v, bool) or (isinstance(v, (int, float)) and not isinstance(v, bool)):
            out[k] = v
        elif isinstance(v, (list, tuple)):
            vals = [c for c in (_code(x) for x in list(v)[:20]) if c]
            out[k] = vals
        else:
            c = _code(v)
            if c:
                out[k] = c
    return out


def build_audit_record(event: AuditEvent) -> Dict[str, Any]:
    """The allow-listed, identifier-only audit record of an event (schema v1)."""
    role = event.user_role.value if isinstance(event.user_role, Enum) else event.user_role
    endpoint = event.endpoint if event.endpoint and _ENDPOINT.match(event.endpoint) else None
    record = {
        "schema_version": RECORD_SCHEMA_VERSION,
        "event_id": event.event_id,
        "event_type": event.event_type.value,
        "severity": event.severity.value,
        "outcome": event.outcome.value,
        "action": _code(event.action),
        "source": _code(event.source),
        "client_timestamp": event.timestamp.isoformat(),
        "actor_user_id": event.user_id if event.user_id and _IDENT.match(str(event.user_id)) else None,
        "actor_username": event.username if event.username and _USERNAME.match(str(event.username)) else None,
        "actor_role": _code(str(role).lower()) if role else None,
        "attempted_identifier_sha256": _code(event.attempted_identifier_sha256),
        "ip_address": _ip(event.ip_address),
        "user_agent": str(event.user_agent)[:200] if event.user_agent else None,
        "request_id": _code(event.request_id),
        "trace_id": _code(event.trace_id),
        "method": event.method if event.method in _METHODS else None,
        "endpoint": endpoint,
        "status_code": int(event.status_code) if isinstance(event.status_code, int) else None,
        "resource_type": _code(event.resource_type),
        "resource_ids": _safe_ids({**({"resource_id": event.resource_id} if event.resource_id else {}),
                                   **(event.resource_ids or {})}),
        "reason": _code(event.reason),
        "details": _safe_details(event.details),
        "service_revision": _code(os.environ.get("K_REVISION")),
        "checksum": event.checksum,
    }
    return {k: v for k, v in record.items() if v not in (None, {}, [])}


# Per-request audit context (set by AuditMiddleware): the durable writes a request produced
# (so the middleware can wait for them) and whether the code emitted its own explicit event.
class RequestAuditContext:
    __slots__ = ("futures", "explicit")

    def __init__(self):
        self.futures: List[Any] = []
        self.explicit = False


_request_audit: ContextVar[Optional[RequestAuditContext]] = ContextVar("request_audit", default=None)


def begin_request_audit():
    """Start a request's audit context; returns (context, token for reset)."""
    ctx = RequestAuditContext()
    return ctx, _request_audit.set(ctx)


def end_request_audit(token) -> None:
    try:
        _request_audit.reset(token)
    except ValueError:  # reset from another context — harmless
        pass


def client_ip(request) -> Optional[str]:
    if request is None:
        return None
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if getattr(request, "client", None) else None


def trace_id_of(request) -> Optional[str]:
    header = request.headers.get("X-Cloud-Trace-Context") if request is not None else None
    return header.split("/")[0] if header else None


def emit_audit(
    event_type: "AuditEventType",
    outcome: "AuditOutcome",
    *,
    request=None,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    role=None,
    reason: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_ids: Optional[Dict[str, Any]] = None,
    details: Optional[Dict[str, Any]] = None,
    severity: Optional["AuditSeverity"] = None,
    attempted_identifier: Optional[str] = None,
    ip_address: Optional[str] = None,
):
    """Record an EXPLICIT audit event from the code that acted (authentication, admin changes).

    Never raises. Within a request, the middleware then does not add a generic record for
    the same authentication request."""
    try:
        if severity is None:
            severity = {AuditOutcome.SUCCESS: AuditSeverity.LOW, AuditOutcome.DENIED: AuditSeverity.MEDIUM,
                        AuditOutcome.FAILURE: AuditSeverity.MEDIUM}.get(outcome, AuditSeverity.MEDIUM)
        route = request.scope.get("route") if request is not None else None
        event = AuditEvent(
            event_type=event_type,
            severity=severity,
            outcome=outcome,
            user_id=user_id,
            username=username,
            user_role=role,
            ip_address=ip_address or client_ip(request),
            user_agent=request.headers.get("User-Agent") if request is not None else None,
            method=request.method if request is not None else None,
            endpoint=getattr(route, "path", None) or (request.url.path if request is not None else None),
            action=event_type.value,
            resource_type=resource_type,
            resource_ids=dict(resource_ids or {}),
            reason=reason,
            details=dict(details or {}),
            attempted_identifier_sha256=sha256_prefix(attempted_identifier) if attempted_identifier else None,
            trace_id=trace_id_of(request),
            source="explicit",
        )
        return get_audit_logger().log_event(event)
    except Exception as e:  # noqa: BLE001 — auditing must never break the request
        logger.error(f"Failed to emit audit event: {e}", exc_info=True)
        return None


class AuditLogger:
    """
    Security audit logger with tamper-proof event recording.

    ISO 27001 A.12.4.1 - Event logging
    ISO 27001 A.12.4.2 - Protection of log information
    ISO 27001 A.12.4.3 - Administrator and operator logs
    """

    def __init__(self, audit_log_file: Optional[str] = None, stdout: bool = True):
        """
        Initialize audit logger.

        Args:
            audit_log_file: Optional local file (developer convenience, never relied upon;
                not used on Cloud Run, whose disk is per-instance memory).
            stdout: Write each record as one structured JSON line on stdout (Cloud Logging).
        """
        self.audit_log_file = Path(audit_log_file) if audit_log_file else None
        if self.audit_log_file is not None:
            self.audit_log_file.parent.mkdir(parents=True, exist_ok=True)
        self.stdout = stdout

        # Application logger for operational events
        self.logger = get_logger(__name__)

        self.logger.info(
            "Audit logger initialized",
            extra={
                "audit_log_file": str(self.audit_log_file) if self.audit_log_file else None,
                "audit_durable_store": "firestore:audit_logs",
                "iso27001_control": "A.12.4.1"
            }
        )

    def log_event(self, event: AuditEvent, durable: bool = True):
        """
        Record an audit event: one stdout JSON line at once, then the durable append-only store.

        Never raises and never blocks the caller (CAPA-015, RC-067).

        Args:
            event: Audit event to log
            durable: False only for records deliberately kept out of Firestore (a repeated read
                within the deduplication window, a request that matched no route)

        Returns:
            The Future of the durable write, or None.
        """
        try:
            # Verify event integrity
            if not event.verify_integrity():
                self.logger.error(
                    "Audit event integrity check failed",
                    extra={
                        "event_id": event.event_id,
                        "event_type": event.event_type.value
                    }
                )
                return None

            if event.request_id is None:
                event.request_id = get_request_id()
            record = build_audit_record(event)

            if self.stdout:
                self._write_stdout(record, event)

            if self.audit_log_file is not None:
                with open(self.audit_log_file, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(record, default=str) + '\n')

            future = None
            if durable:
                from app.core.logging.audit_sink import get_durable_audit_sink
                future = get_durable_audit_sink().submit(record)
            ctx = _request_audit.get()
            if ctx is not None:
                if future is not None:
                    ctx.futures.append(future)
                if event.source == "explicit":
                    ctx.explicit = True

            # Alert on critical security events
            if event.severity == AuditSeverity.CRITICAL:
                self._send_security_alert(event)
            return future

        except Exception as e:
            self.logger.error(
                f"Failed to log audit event: {e}",
                extra={
                    "event_type": event.event_type.value if event else None,
                    "error": str(e)
                },
                exc_info=True
            )
            return None

    @staticmethod
    def _write_stdout(record: Dict[str, Any], event: AuditEvent) -> None:
        """One structured JSON line per record — Cloud Run forwards stdout to Cloud Logging."""
        line = {
            "severity": _CLOUD_SEVERITY.get(event.severity, "INFO"),
            "message": f"AUDIT {record.get('event_type')} {record.get('outcome')}",
            "audit": record,
            "logging.googleapis.com/labels": {"audit": "true"},
        }
        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        if record.get("trace_id") and project:
            line["logging.googleapis.com/trace"] = f"projects/{project}/traces/{record['trace_id']}"
        sys.stdout.write(json.dumps(line, default=str) + "\n")
        sys.stdout.flush()

    def _severity_to_log_level(self, severity: AuditSeverity) -> int:
        """Map audit severity to logging level."""
        import logging
        mapping = {
            AuditSeverity.LOW: logging.INFO,
            AuditSeverity.MEDIUM: logging.WARNING,
            AuditSeverity.HIGH: logging.ERROR,
            AuditSeverity.CRITICAL: logging.CRITICAL,
        }
        return mapping.get(severity, logging.INFO)

    def _send_security_alert(self, event: AuditEvent) -> None:
        """
        Send alert for critical security events.

        ISO 27001 A.16.1.2 - Reporting information security events
        """
        self.logger.critical(
            f"SECURITY ALERT: {event.event_type.value}",
            extra={
                "alert_type": "security_critical",
                "event_id": event.event_id,
                "description": event.description,
                "user_id": event.user_id,
                "ip_address": event.ip_address,
                "threat_indicators": event.threat_indicators,
                "iso27001_control": "A.16.1.2"
            }
        )

        # TODO: Integrate with alerting system (email, SMS, SIEM)

    def log_authentication(
        self,
        event_type: AuditEventType,
        username: str,
        ip_address: str,
        success: bool,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log authentication event (ISO 27001 A.9.4.2).

        Args:
            event_type: Type of authentication event
            username: Username attempting authentication
            ip_address: Source IP address
            success: Whether authentication succeeded
            reason: Reason for failure (if applicable)
            metadata: Additional context
        """
        event = AuditEvent(
            event_type=event_type,
            severity=AuditSeverity.MEDIUM if success else AuditSeverity.HIGH,
            outcome=AuditOutcome.SUCCESS if success else AuditOutcome.FAILURE,
            username=username,
            ip_address=ip_address,
            action="authenticate",
            description=reason or ("Authentication successful" if success else "Authentication failed"),
            metadata=metadata or {},
            iso27001_controls=["A.9.4.2"],
        )
        self.log_event(event)

    def log_authorization(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        granted: bool,
        ip_address: Optional[str] = None,
        reason: Optional[str] = None
    ) -> None:
        """
        Log authorization event (ISO 27001 A.9.4.1).

        Args:
            user_id: User attempting access
            resource_type: Type of resource
            resource_id: Resource identifier
            action: Action attempted
            granted: Whether access was granted
            ip_address: Source IP address
            reason: Reason for denial (if applicable)
        """
        event = AuditEvent(
            event_type=AuditEventType.AUTHZ_ACCESS_GRANTED if granted else AuditEventType.AUTHZ_ACCESS_DENIED,
            severity=AuditSeverity.LOW if granted else AuditSeverity.MEDIUM,
            outcome=AuditOutcome.SUCCESS if granted else AuditOutcome.DENIED,
            user_id=user_id,
            ip_address=ip_address,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            description=reason or ("Access granted" if granted else "Access denied"),
            iso27001_controls=["A.9.4.1"],
        )
        self.log_event(event)

    def log_data_access(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        phi_involved: bool = False,
        ip_address: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log data access event (ISO 27001 A.9.4.5, HIPAA).

        Args:
            user_id: User accessing data
            resource_type: Type of data accessed
            resource_id: Data identifier
            action: Action performed (read, write, delete)
            phi_involved: Whether PHI was accessed (HIPAA)
            ip_address: Source IP address
            metadata: Additional context
        """
        event_type = AuditEventType.DATA_ACCESS_PHI if phi_involved else AuditEventType.DATA_ACCESS_FILE

        event = AuditEvent(
            event_type=event_type,
            severity=AuditSeverity.HIGH if phi_involved else AuditSeverity.LOW,
            outcome=AuditOutcome.SUCCESS,
            user_id=user_id,
            ip_address=ip_address,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            description=f"Data {action}: {resource_type}/{resource_id}",
            metadata=metadata or {},
            iso27001_controls=["A.9.4.5"],
            hipaa_requirements=["164.312(b) - Audit Controls"] if phi_involved else [],
        )
        self.log_event(event)

    def log_security_event(
        self,
        event_type: AuditEventType,
        description: str,
        severity: AuditSeverity = AuditSeverity.HIGH,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        threat_indicators: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log security incident (ISO 27001 A.16.1.1).

        Args:
            event_type: Type of security event
            description: Description of incident
            severity: Event severity
            user_id: Associated user (if applicable)
            ip_address: Source IP address
            threat_indicators: List of threat indicators
            metadata: Additional context
        """
        event = AuditEvent(
            event_type=event_type,
            severity=severity,
            outcome=AuditOutcome.FAILURE,
            user_id=user_id,
            ip_address=ip_address,
            description=description,
            threat_indicators=threat_indicators or [],
            metadata=metadata or {},
            iso27001_controls=["A.16.1.1", "A.16.1.2"],
        )
        self.log_event(event)

    def log_admin_action(
        self,
        event_type: AuditEventType,
        admin_user_id: str,
        action: str,
        target_user_id: Optional[str] = None,
        description: Optional[str] = None,
        ip_address: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log administrative action (ISO 27001 A.12.4.3).

        Args:
            event_type: Type of admin event
            admin_user_id: Administrator performing action
            action: Action performed
            target_user_id: Target user (if applicable)
            description: Description of action
            ip_address: Source IP address
            metadata: Additional context
        """
        event = AuditEvent(
            event_type=event_type,
            severity=AuditSeverity.HIGH,
            outcome=AuditOutcome.SUCCESS,
            user_id=admin_user_id,
            ip_address=ip_address,
            resource_id=target_user_id,
            action=action,
            description=description or f"Administrative action: {action}",
            metadata=metadata or {},
            iso27001_controls=["A.12.4.3"],
        )
        self.log_event(event)


# Global audit logger instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get global audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        from app.core.config import get_settings
        settings = get_settings()
        # CAPA-015: on Cloud Run (K_SERVICE set) the disk is per-instance memory that vanishes
        # on restart and grows the instance's memory; the durable store is Firestore.
        audit_log_file = None if os.environ.get("K_SERVICE") else getattr(settings, 'AUDIT_LOG_FILE', 'logs/audit.log')
        _audit_logger = AuditLogger(audit_log_file=audit_log_file)
    return _audit_logger
