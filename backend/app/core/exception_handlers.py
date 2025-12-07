"""
Global exception handlers for FastAPI application.

This module provides centralized exception handling that:
1. Catches all AppException instances
2. Converts them to structured JSON responses
3. Ensures consistent error response format
4. Integrates with logging middleware
5. Handles unexpected exceptions gracefully

Exception handlers are registered in main.py during app initialization.
"""

from typing import Union
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppException, InternalServerException
from app.core.logging import get_logger

logger = get_logger(__name__)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """
    Handle all custom AppException instances.

    This handler catches all exceptions that inherit from AppException
    and converts them to structured JSON responses.

    Args:
        request: FastAPI Request object
        exc: The AppException instance

    Returns:
        JSONResponse with error details

    Example response:
        {
            "error": {
                "code": "NOT_FOUND",
                "message": "File not found: abc123",
                "details": {
                    "file_id": "abc123"
                }
            }
        }
    """
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict()
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
) -> JSONResponse:
    """
    Handle FastAPI validation errors (Pydantic validation).

    Converts Pydantic validation errors to our standard error format.

    Args:
        request: FastAPI Request object
        exc: RequestValidationError from Pydantic

    Returns:
        JSONResponse with validation error details

    Example response:
        {
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid request parameters",
                "details": {
                    "errors": [
                        {
                            "loc": ["body", "file_id"],
                            "msg": "field required",
                            "type": "value_error.missing"
                        }
                    ]
                }
            }
        }
    """
    # Log validation error
    logger.warning(
        "Request validation failed",
        extra={
            "path": request.url.path,
            "method": request.method,
            "errors": exc.errors()
        }
    )

    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid request parameters",
                "details": {
                    "errors": exc.errors()
                }
            }
        }
    )


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException
) -> JSONResponse:
    """
    Handle Starlette HTTP exceptions.

    Converts standard HTTP exceptions to our error format.

    Args:
        request: FastAPI Request object
        exc: StarletteHTTPException

    Returns:
        JSONResponse with error details

    Example response:
        {
            "error": {
                "code": "HTTP_404",
                "message": "Not found",
                "details": {}
            }
        }
    """
    # Log HTTP exception
    logger.warning(
        f"HTTP exception: {exc.status_code}",
        extra={
            "path": request.url.path,
            "method": request.method,
            "status_code": exc.status_code,
            "detail": exc.detail
        }
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": f"HTTP_{exc.status_code}",
                "message": exc.detail,
                "details": {}
            }
        }
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle all unhandled exceptions.

    This is the catch-all handler for any exception not caught by
    other handlers. It logs the full exception and returns a generic
    500 error to the client (without exposing internal details).

    Args:
        request: FastAPI Request object
        exc: Any unhandled Exception

    Returns:
        JSONResponse with generic error message

    Example response:
        {
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "details": {}
            }
        }
    """
    # Wrap in InternalServerException for consistent logging
    internal_error = InternalServerException(
        message="An unexpected error occurred",
        details={
            "path": request.url.path,
            "method": request.method,
            "exception_type": type(exc).__name__,
            "exception_message": str(exc)
        }
    )

    # Log with full stack trace
    logger.error(
        "Unhandled exception",
        extra={
            "path": request.url.path,
            "method": request.method,
            "exception_type": type(exc).__name__,
            "exception_message": str(exc)
        },
        exc_info=exc
    )

    return JSONResponse(
        status_code=500,
        content=internal_error.to_dict()
    )


def register_exception_handlers(app) -> None:
    """
    Register all exception handlers with the FastAPI app.

    This function should be called during app initialization in main.py.

    Args:
        app: FastAPI application instance

    Example:
        from app.core.exception_handlers import register_exception_handlers

        app = FastAPI()
        register_exception_handlers(app)
    """
    # Custom AppException handler (highest priority for our exceptions)
    app.add_exception_handler(AppException, app_exception_handler)

    # Pydantic validation errors
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    # Starlette HTTP exceptions
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)

    # Catch-all for unhandled exceptions (lowest priority)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    logger.info("Exception handlers registered successfully")
