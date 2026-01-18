"""
Audit Middleware for FastAPI
ISO 27001 A.12.4.1 - Event logging

Automatically captures and logs security-relevant HTTP requests and responses
including authentication, authorization, and data access events.

@module core.logging.audit_middleware
"""

import time
from typing import Callable, Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.logging.audit import (
    get_audit_logger,
    AuditEventType,
    AuditSeverity,
    AuditOutcome,
    AuditEvent
)
from app.core.logging import get_logger

logger = get_logger(__name__)


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

        # Paths that should be audited
        self.audit_paths = {
            # Authentication endpoints
            '/api/v1/auth/login': AuditEventType.AUTH_LOGIN_SUCCESS,
            '/api/v1/auth/logout': AuditEventType.AUTH_LOGOUT,
            '/api/v1/auth/refresh': AuditEventType.AUTH_TOKEN_REFRESH,
            '/api/v1/auth/change-password': AuditEventType.AUTH_PASSWORD_CHANGE,
            '/api/v1/auth/reset-password': AuditEventType.AUTH_PASSWORD_RESET,

            # User management (admin)
            '/api/v1/users': AuditEventType.ADMIN_USER_CREATED,

            # Data access
            '/api/v1/imaging': AuditEventType.DATA_ACCESS_FILE,
            '/api/v1/storage': AuditEventType.DATA_ACCESS_FILE,
        }

        # Sensitive endpoints that require detailed logging
        self.sensitive_paths = [
            '/api/v1/auth',
            '/api/v1/users',
            '/api/v1/imaging',
            '/api/v1/admin',
        ]

        # Paths to exclude from audit logging
        self.exclude_paths = [
            '/api/health',
            '/api/docs',
            '/api/redoc',
            '/api/openapi.json',
            '/',
        ]

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """
        Process request and log audit events.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware in chain

        Returns:
            HTTP response
        """
        # Check if path should be excluded
        if self._should_exclude(request.url.path):
            return await call_next(request)

        # Record start time for performance tracking
        start_time = time.time()

        # Extract request metadata
        request_metadata = await self._extract_request_metadata(request)

        # Process request
        response = await call_next(request)

        # Calculate request duration
        duration_ms = (time.time() - start_time) * 1000

        # Log audit event if path is sensitive
        if self._is_sensitive(request.url.path):
            await self._log_request_audit(
                request=request,
                response=response,
                duration_ms=duration_ms,
                metadata=request_metadata
            )

        # Log failed authentication attempts
        if response.status_code == 401:
            await self._log_auth_failure(request, request_metadata)

        # Log authorization failures
        if response.status_code == 403:
            await self._log_authz_failure(request, request_metadata)

        # Add audit headers to response
        response.headers["X-Audit-Logged"] = "true"
        response.headers["X-Request-Duration-Ms"] = f"{duration_ms:.2f}"

        return response

    def _should_exclude(self, path: str) -> bool:
        """Check if path should be excluded from auditing."""
        return any(path.startswith(exclude) for exclude in self.exclude_paths)

    def _is_sensitive(self, path: str) -> bool:
        """Check if path is sensitive and requires detailed audit."""
        return any(path.startswith(sensitive) for sensitive in self.sensitive_paths)

    async def _extract_request_metadata(self, request: Request) -> dict:
        """
        Extract metadata from request for auditing.

        Args:
            request: HTTP request

        Returns:
            Dictionary with request metadata
        """
        # Extract client IP (handle proxy headers)
        client_ip = request.client.host if request.client else None
        forwarded_for = request.headers.get('X-Forwarded-For')
        if forwarded_for:
            client_ip = forwarded_for.split(',')[0].strip()

        metadata = {
            'method': request.method,
            'path': request.url.path,
            'query_params': dict(request.query_params),
            'ip_address': client_ip,
            'user_agent': request.headers.get('User-Agent'),
            'referer': request.headers.get('Referer'),
            'content_type': request.headers.get('Content-Type'),
        }

        # Extract user info from request state (set by auth middleware)
        if hasattr(request.state, 'user'):
            user = request.state.user
            metadata['user_id'] = getattr(user, 'id', None)
            metadata['username'] = getattr(user, 'username', None)
            metadata['user_role'] = getattr(user, 'role', None)

        return metadata

    async def _log_request_audit(
        self,
        request: Request,
        response: Response,
        duration_ms: float,
        metadata: dict
    ) -> None:
        """
        Log audit event for request.

        Args:
            request: HTTP request
            response: HTTP response
            duration_ms: Request duration in milliseconds
            metadata: Request metadata
        """
        # Determine event type based on path and method
        event_type = self._determine_event_type(
            path=metadata['path'],
            method=metadata['method'],
            status_code=response.status_code
        )

        # Determine severity based on status code
        severity = self._determine_severity(response.status_code)

        # Determine outcome
        outcome = self._determine_outcome(response.status_code)

        # Create audit event
        event = AuditEvent(
            event_type=event_type,
            severity=severity,
            outcome=outcome,
            user_id=metadata.get('user_id'),
            username=metadata.get('username'),
            user_role=metadata.get('user_role'),
            ip_address=metadata.get('ip_address'),
            user_agent=metadata.get('user_agent'),
            resource_type=self._extract_resource_type(metadata['path']),
            action=metadata['method'],
            method=metadata['method'],
            endpoint=metadata['path'],
            description=f"{metadata['method']} {metadata['path']} - {response.status_code}",
            metadata={
                'query_params': metadata.get('query_params'),
                'referer': metadata.get('referer'),
                'content_type': metadata.get('content_type'),
                'status_code': response.status_code,
                'duration_ms': duration_ms,
            },
            iso27001_controls=["A.12.4.1"],
        )

        # Log the event
        self.audit_logger.log_event(event)

    async def _log_auth_failure(self, request: Request, metadata: dict) -> None:
        """
        Log authentication failure (401).

        ISO 27001 A.9.4.2 - Secure log-on procedures
        """
        self.audit_logger.log_authentication(
            event_type=AuditEventType.AUTH_LOGIN_FAILED,
            username=metadata.get('username', 'unknown'),
            ip_address=metadata.get('ip_address'),
            success=False,
            reason="Invalid credentials or token",
            metadata={
                'path': metadata['path'],
                'user_agent': metadata.get('user_agent'),
            }
        )

    async def _log_authz_failure(self, request: Request, metadata: dict) -> None:
        """
        Log authorization failure (403).

        ISO 27001 A.9.4.1 - Information access restriction
        """
        self.audit_logger.log_authorization(
            user_id=metadata.get('user_id', 'unknown'),
            resource_type=self._extract_resource_type(metadata['path']),
            resource_id=metadata.get('path'),
            action=metadata['method'],
            granted=False,
            ip_address=metadata.get('ip_address'),
            reason="Insufficient permissions"
        )

    def _determine_event_type(
        self, path: str, method: str, status_code: int
    ) -> AuditEventType:
        """Determine audit event type based on request."""
        # Check if specific path has defined event type
        if path in self.audit_paths:
            return self.audit_paths[path]

        # Authentication endpoints
        if '/auth/login' in path:
            return AuditEventType.AUTH_LOGIN_SUCCESS if status_code == 200 else AuditEventType.AUTH_LOGIN_FAILED
        elif '/auth/logout' in path:
            return AuditEventType.AUTH_LOGOUT
        elif '/auth/refresh' in path:
            return AuditEventType.AUTH_TOKEN_REFRESH

        # User management
        elif '/users' in path:
            if method == 'POST':
                return AuditEventType.ADMIN_USER_CREATED
            elif method == 'DELETE':
                return AuditEventType.ADMIN_USER_DELETED
            elif method in ['PUT', 'PATCH']:
                return AuditEventType.ADMIN_USER_MODIFIED

        # Data access
        elif '/imaging' in path or '/storage' in path:
            if method == 'GET':
                return AuditEventType.DATA_ACCESS_FILE
            elif method == 'DELETE':
                return AuditEventType.DATA_DELETE
            elif method in ['PUT', 'PATCH', 'POST']:
                return AuditEventType.DATA_MODIFY

        # Authorization
        elif status_code == 403:
            return AuditEventType.AUTHZ_ACCESS_DENIED

        # Default
        return AuditEventType.AUTHZ_ACCESS_GRANTED

    def _determine_severity(self, status_code: int) -> AuditSeverity:
        """Determine severity based on HTTP status code."""
        if status_code >= 500:
            return AuditSeverity.HIGH
        elif status_code == 403:
            return AuditSeverity.MEDIUM
        elif status_code == 401:
            return AuditSeverity.MEDIUM
        elif status_code >= 400:
            return AuditSeverity.LOW
        else:
            return AuditSeverity.LOW

    def _determine_outcome(self, status_code: int) -> AuditOutcome:
        """Determine outcome based on HTTP status code."""
        if status_code < 300:
            return AuditOutcome.SUCCESS
        elif status_code == 403:
            return AuditOutcome.DENIED
        elif status_code >= 400:
            return AuditOutcome.FAILURE
        else:
            return AuditOutcome.PARTIAL

    def _extract_resource_type(self, path: str) -> str:
        """Extract resource type from path."""
        if '/imaging' in path:
            return 'medical_image'
        elif '/storage' in path:
            return 'storage_file'
        elif '/users' in path:
            return 'user'
        elif '/auth' in path:
            return 'authentication'
        else:
            return 'unknown'
