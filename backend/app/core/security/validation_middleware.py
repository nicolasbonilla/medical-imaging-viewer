"""
Input Validation Middleware for FastAPI
ISO 27001 A.14.2.1 - Secure development policy

Automatically validates and sanitizes all incoming request data to prevent
injection attacks and malicious input.

@module core.security.validation_middleware
"""

import json
from typing import Callable, Dict, Any, Optional
from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.security.validators import (
    InputValidator,
    SQLInjectionDetected,
    XSSDetected,
    CommandInjectionDetected,
    PathTraversalDetected,
    ValidationError
)
from app.core.logging import get_logger, get_audit_logger
from app.core.logging.audit import AuditEventType, AuditSeverity

logger = get_logger(__name__)
audit_logger = get_audit_logger()


class InputValidationMiddleware(BaseHTTPMiddleware):
    """
    Middleware for automatic input validation and sanitization.

    ISO 27001 A.14.2.1 - Secure development policy
    ISO 27001 A.14.1.2 - Securing application services
    """

    def __init__(
        self,
        app: ASGIApp,
        enabled: bool = True,
        strict_mode: bool = True
    ):
        """
        Initialize input validation middleware.

        Args:
            app: ASGI application
            enabled: Whether validation is enabled
            strict_mode: Strict mode blocks requests, lenient mode only logs
        """
        super().__init__(app)
        self.enabled = enabled
        self.strict_mode = strict_mode

        # Paths that should bypass validation
        self.bypass_paths = [
            '/api/health',
            '/api/docs',
            '/api/redoc',
            '/api/openapi.json',
            '/',
        ]

        # Path-specific validation rules
        self.path_rules = self._build_path_rules()

        logger.info(
            "Input validation middleware initialized",
            extra={
                "enabled": self.enabled,
                "strict_mode": self.strict_mode,
                "iso27001_control": "A.14.2.1"
            }
        )

    def _build_path_rules(self) -> Dict[str, Dict[str, bool]]:
        """
        Build path-specific validation rules.

        Returns:
            Dictionary mapping paths to validation rules
        """
        return {
            # Authentication endpoints - strict validation
            '/api/v1/auth': {
                'check_sql': True,
                'check_xss': True,
                'check_command': True,
                'check_path': False,
                'allow_html': False,
            },
            # User management - strict validation
            '/api/v1/users': {
                'check_sql': True,
                'check_xss': True,
                'check_command': True,
                'check_path': False,
                'allow_html': False,
            },
            # File/imaging endpoints - check path traversal
            '/api/v1/imaging': {
                'check_sql': True,
                'check_xss': True,
                'check_command': False,
                'check_path': True,
                'allow_html': False,
            },
            '/api/v1/drive': {
                'check_sql': True,
                'check_xss': True,
                'check_command': False,
                'check_path': True,
                'allow_html': False,
            },
            # Segmentation endpoints
            '/api/v1/segmentation': {
                'check_sql': True,
                'check_xss': True,
                'check_command': False,
                'check_path': True,
                'allow_html': False,
            },
            # Default rules for other endpoints
            'default': {
                'check_sql': True,
                'check_xss': True,
                'check_command': False,
                'check_path': False,
                'allow_html': False,
            }
        }

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """
        Validate and sanitize request input.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware in chain

        Returns:
            HTTP response
        """
        # Skip if disabled
        if not self.enabled:
            return await call_next(request)

        # Skip bypass paths
        if self._should_bypass(request.url.path):
            return await call_next(request)

        # Get validation rules for this path
        rules = self._get_rules_for_path(request.url.path)

        try:
            # Validate query parameters
            await self._validate_query_params(request, rules)

            # Validate path parameters
            await self._validate_path_params(request, rules)

            # Validate request body (for POST/PUT/PATCH)
            if request.method in ['POST', 'PUT', 'PATCH']:
                await self._validate_body(request, rules)

            # Validate headers
            await self._validate_headers(request, rules)

            # Process request
            response = await call_next(request)

            return response

        except ValidationError as e:
            # Handle validation errors
            return self._handle_validation_error(e, request)

        except Exception as e:
            # Log unexpected errors
            logger.error(
                f"Unexpected error in input validation: {e}",
                extra={
                    "path": request.url.path,
                    "method": request.method
                },
                exc_info=True
            )

            if self.strict_mode:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Input validation error"
                )
            else:
                return await call_next(request)

    def _should_bypass(self, path: str) -> bool:
        """Check if path should bypass validation."""
        return any(path.startswith(bypass) for bypass in self.bypass_paths)

    def _get_rules_for_path(self, path: str) -> Dict[str, bool]:
        """Get validation rules for path."""
        # Check for exact or prefix match
        for rule_path, rules in self.path_rules.items():
            if path.startswith(rule_path):
                return rules

        # Return default rules
        return self.path_rules['default']

    async def _validate_query_params(
        self, request: Request, rules: Dict[str, bool]
    ) -> None:
        """
        Validate query parameters.

        Args:
            request: HTTP request
            rules: Validation rules

        Raises:
            ValidationError: If validation fails
        """
        validator = InputValidator()

        for key, value in request.query_params.items():
            if isinstance(value, str):
                validator.validate_all(
                    value,
                    field_name=f"query_param.{key}",
                    **rules
                )

    async def _validate_path_params(
        self, request: Request, rules: Dict[str, bool]
    ) -> None:
        """
        Validate path parameters.

        Args:
            request: HTTP request
            rules: Validation rules

        Raises:
            ValidationError: If validation fails
        """
        validator = InputValidator()

        if hasattr(request, 'path_params'):
            for key, value in request.path_params.items():
                if isinstance(value, str):
                    validator.validate_all(
                        value,
                        field_name=f"path_param.{key}",
                        **rules
                    )

    async def _validate_body(
        self, request: Request, rules: Dict[str, bool]
    ) -> None:
        """
        Validate request body.

        Args:
            request: HTTP request
            rules: Validation rules

        Raises:
            ValidationError: If validation fails
        """
        # Get content type
        content_type = request.headers.get('content-type', '')

        # Only validate JSON bodies
        if 'application/json' not in content_type:
            return

        try:
            # Read body
            body_bytes = await request.body()

            if not body_bytes:
                return

            # Parse JSON
            body = json.loads(body_bytes)

            # Validate all string fields recursively
            self._validate_dict_recursive(body, rules, path="body")

        except json.JSONDecodeError:
            # Invalid JSON will be handled by FastAPI
            pass
        except Exception as e:
            logger.warning(f"Error validating request body: {e}")

    def _validate_dict_recursive(
        self,
        data: Dict[str, Any],
        rules: Dict[str, bool],
        path: str = ""
    ) -> None:
        """
        Recursively validate all string values in dictionary.

        Args:
            data: Dictionary to validate
            rules: Validation rules
            path: Current path in nested structure

        Raises:
            ValidationError: If validation fails
        """
        validator = InputValidator()

        for key, value in data.items():
            field_path = f"{path}.{key}" if path else key

            if isinstance(value, str):
                # Validate string value
                validator.validate_all(
                    value,
                    field_name=field_path,
                    **rules
                )
            elif isinstance(value, dict):
                # Recursively validate nested dict
                self._validate_dict_recursive(value, rules, field_path)
            elif isinstance(value, list):
                # Validate list items
                for i, item in enumerate(value):
                    if isinstance(item, str):
                        validator.validate_all(
                            item,
                            field_name=f"{field_path}[{i}]",
                            **rules
                        )
                    elif isinstance(item, dict):
                        self._validate_dict_recursive(
                            item, rules, f"{field_path}[{i}]"
                        )

    async def _validate_headers(
        self, request: Request, rules: Dict[str, bool]
    ) -> None:
        """
        Validate suspicious headers.

        Args:
            request: HTTP request
            rules: Validation rules

        Raises:
            ValidationError: If validation fails
        """
        validator = InputValidator()

        # Validate potentially dangerous headers
        dangerous_headers = [
            'referer', 'user-agent', 'x-forwarded-for',
            'x-real-ip', 'x-custom-header'
        ]

        for header in dangerous_headers:
            value = request.headers.get(header)
            if value:
                try:
                    # Only check for XSS in headers
                    validator.validate_all(
                        value,
                        field_name=f"header.{header}",
                        check_sql=False,
                        check_xss=True,
                        check_command=False,
                        check_path=False
                    )
                except ValidationError:
                    # Log but don't block (headers may have false positives)
                    logger.warning(
                        f"Suspicious header value detected: {header}",
                        extra={
                            "header": header,
                            "value": value[:100]
                        }
                    )

    def _handle_validation_error(
        self, error: ValidationError, request: Request
    ) -> Response:
        """
        Handle validation error.

        Args:
            error: Validation error
            request: HTTP request

        Returns:
            HTTP response
        """
        # Determine error type and severity
        if isinstance(error, SQLInjectionDetected):
            error_type = "sql_injection"
            severity = AuditSeverity.HIGH
            status_code = status.HTTP_400_BAD_REQUEST
        elif isinstance(error, XSSDetected):
            error_type = "xss_attempt"
            severity = AuditSeverity.HIGH
            status_code = status.HTTP_400_BAD_REQUEST
        elif isinstance(error, CommandInjectionDetected):
            error_type = "command_injection"
            severity = AuditSeverity.HIGH
            status_code = status.HTTP_400_BAD_REQUEST
        elif isinstance(error, PathTraversalDetected):
            error_type = "path_traversal"
            severity = AuditSeverity.HIGH
            status_code = status.HTTP_400_BAD_REQUEST
        else:
            error_type = "validation_error"
            severity = AuditSeverity.MEDIUM
            status_code = status.HTTP_400_BAD_REQUEST

        # Get client info
        client_ip = self._get_client_ip(request)

        # Log security event
        audit_logger.log_security_event(
            event_type=AuditEventType.SECURITY_INVALID_INPUT,
            severity=severity,
            description=f"Input validation failed: {error_type}",
            metadata={
                'error_type': error_type,
                'error_message': str(error),
                'path': request.url.path,
                'method': request.method,
                'client_ip': client_ip,
                'user_agent': request.headers.get('User-Agent')
            }
        )

        # Return appropriate response
        if self.strict_mode:
            # Strict mode: block request
            raise HTTPException(
                status_code=status_code,
                detail={
                    'error': error_type,
                    'message': 'Invalid input detected',
                    'details': str(error)
                }
            )
        else:
            # Lenient mode: log and continue
            logger.warning(
                f"Input validation failed (lenient mode): {error}",
                extra={
                    'path': request.url.path,
                    'error_type': error_type
                }
            )
            # This won't be reached in strict mode, but keeping for clarity
            return Response(
                status_code=status.HTTP_200_OK,
                content="Request processed with validation warnings"
            )

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address from request."""
        forwarded_for = request.headers.get('X-Forwarded-For')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()

        real_ip = request.headers.get('X-Real-IP')
        if real_ip:
            return real_ip

        if request.client:
            return request.client.host

        return 'unknown'
