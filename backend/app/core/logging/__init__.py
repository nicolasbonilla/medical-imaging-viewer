"""
Logging module for Medical Imaging Viewer.

Provides structured logging with JSON formatting, correlation IDs,
and context-aware logging.

Usage:
    >>> from app.core.logging import setup_logging, get_logger
    >>>
    >>> # Initialize logging (call once at app startup)
    >>> setup_logging()
    >>>
    >>> # Get logger in your module
    >>> logger = get_logger(__name__)
    >>>
    >>> # Log with context
    >>> logger.info("Processing image", extra={"file_id": "abc123"})
    >>> logger.error("Failed to load image", extra={"error": str(e)})
"""

from app.core.logging.config import setup_logging, get_logger
from app.core.logging.adapter import get_context_logger
from app.core.logging.context import (
    generate_correlation_id,
    set_correlation_id,
    get_correlation_id,
    set_request_id,
    get_request_id,
    set_user_id,
    get_user_id,
    clear_context
)
from app.core.logging.audit import (
    get_audit_logger,
    AuditLogger,
    AuditEvent,
    AuditEventType,
    AuditSeverity,
    AuditOutcome,
)
from app.core.logging.audit_middleware import AuditMiddleware

__all__ = [
    # Configuration
    "setup_logging",
    "get_logger",
    "get_context_logger",

    # Context management
    "generate_correlation_id",
    "set_correlation_id",
    "get_correlation_id",
    "set_request_id",
    "get_request_id",
    "set_user_id",
    "get_user_id",
    "clear_context",

    # Audit logging (ISO 27001 A.12.4.1)
    "get_audit_logger",
    "AuditLogger",
    "AuditEvent",
    "AuditEventType",
    "AuditSeverity",
    "AuditOutcome",
    "AuditMiddleware",
]
