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

@module core.logging.audit
"""

import json
import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List
from pathlib import Path
from dataclasses import dataclass, asdict, field

from app.core.logging import get_logger

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
    SECURITY_KEY_COMPROMISED = "security.key.compromised"

    # Administrative Events (A.12.4.3)
    ADMIN_USER_CREATED = "admin.user.created"
    ADMIN_USER_DELETED = "admin.user.deleted"
    ADMIN_USER_MODIFIED = "admin.user.modified"
    ADMIN_ROLE_CREATED = "admin.role.created"
    ADMIN_ROLE_DELETED = "admin.role.deleted"
    ADMIN_PERMISSION_MODIFIED = "admin.permission.modified"

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

    # Event identification (with defaults)
    event_id: str = field(default_factory=lambda: hashlib.sha256(
        f"{datetime.now(timezone.utc).isoformat()}{id(object())}".encode()
    ).hexdigest()[:16])

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


class AuditLogger:
    """
    Security audit logger with tamper-proof event recording.

    ISO 27001 A.12.4.1 - Event logging
    ISO 27001 A.12.4.2 - Protection of log information
    ISO 27001 A.12.4.3 - Administrator and operator logs
    """

    def __init__(self, audit_log_file: str = "logs/audit.log"):
        """
        Initialize audit logger.

        Args:
            audit_log_file: Path to audit log file
        """
        self.audit_log_file = Path(audit_log_file)
        self.audit_log_file.parent.mkdir(parents=True, exist_ok=True)

        # Application logger for operational events
        self.logger = get_logger(__name__)

        self.logger.info(
            "Audit logger initialized",
            extra={
                "audit_log_file": str(self.audit_log_file),
                "iso27001_control": "A.12.4.1"
            }
        )

    def log_event(self, event: AuditEvent) -> None:
        """
        Log audit event to file and application logger.

        Args:
            event: Audit event to log
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
                return

            # Write to audit log file (append-only)
            with open(self.audit_log_file, 'a', encoding='utf-8') as f:
                f.write(event.to_json() + '\n')

            # Log to application logger based on severity
            log_level = self._severity_to_log_level(event.severity)
            self.logger.log(
                log_level,
                f"Audit Event: {event.event_type.value}",
                extra={
                    "event_id": event.event_id,
                    "event_type": event.event_type.value,
                    "severity": event.severity.value,
                    "outcome": event.outcome.value,
                    "user_id": event.user_id,
                    "ip_address": event.ip_address,
                    "resource_id": event.resource_id,
                    "description": event.description,
                    "iso27001_controls": event.iso27001_controls,
                    "checksum": event.checksum,
                }
            )

            # Alert on critical security events
            if event.severity == AuditSeverity.CRITICAL:
                self._send_security_alert(event)

        except Exception as e:
            self.logger.error(
                f"Failed to log audit event: {e}",
                extra={
                    "event_type": event.event_type.value if event else None,
                    "error": str(e)
                },
                exc_info=True
            )

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
        audit_log_file = getattr(settings, 'AUDIT_LOG_FILE', 'logs/audit.log')
        _audit_logger = AuditLogger(audit_log_file=audit_log_file)
    return _audit_logger
