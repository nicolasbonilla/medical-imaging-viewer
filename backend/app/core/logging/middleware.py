"""
Logging middleware for FastAPI.

Automatically adds correlation IDs to all requests and logs
request/response information.
"""

import time
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.logging import (
    generate_correlation_id,
    set_correlation_id,
    set_request_id,
    clear_context,
    get_logger
)

logger = get_logger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds correlation IDs and logs all requests/responses.

    For each request:
    1. Generates or extracts correlation ID from X-Correlation-ID header
    2. Sets correlation ID in context
    3. Logs request details
    4. Processes request
    5. Logs response details with duration
    6. Clears context

    Example response headers:
        X-Correlation-ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890
        X-Request-ID: req-123456
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process each request with correlation ID tracking.

        Args:
            request: FastAPI Request object
            call_next: Next middleware/endpoint in chain

        Returns:
            Response with correlation ID headers
        """
        # Generate or extract correlation ID
        correlation_id = request.headers.get('X-Correlation-ID') or generate_correlation_id()
        request_id = f"req-{int(time.time() * 1000)}"

        # Set context
        set_correlation_id(correlation_id)
        set_request_id(request_id)

        # Log request
        start_time = time.time()
        logger.info(
            f"Request started: {request.method} {request.url.path}",
            extra={
                "method": request.method,
                "path": request.url.path,
                "query_params": str(request.query_params),
                "client_ip": request.client.host if request.client else None,
                "user_agent": request.headers.get('user-agent'),
            }
        )

        try:
            # Process request
            response = await call_next(request)

            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Log response
            logger.info(
                f"Request completed: {request.method} {request.url.path}",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                }
            )

            # Add correlation ID to response headers
            response.headers['X-Correlation-ID'] = correlation_id
            response.headers['X-Request-ID'] = request_id

            return response

        except Exception as e:
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Log error
            logger.error(
                f"Request failed: {request.method} {request.url.path}",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": round(duration_ms, 2),
                },
                exc_info=True  # Include stack trace in logs
            )

            # Re-raise to let FastAPI handle it
            raise

        finally:
            # Clean up context
            clear_context()
