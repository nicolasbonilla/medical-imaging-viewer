"""
Custom exception hierarchy for the Medical Imaging Viewer application.

This module provides a structured exception hierarchy that:
1. Maps to HTTP status codes
2. Includes error codes for client handling
3. Integrates with structured logging
4. Provides user-friendly error messages
5. Supports additional context via details dict

Exception Hierarchy:
    AppException (base)
    ├── ValidationException (400)
    ├── UnauthorizedException (401)
    ├── ForbiddenException (403)
    ├── NotFoundException (404)
    ├── ConflictException (409)
    └── InternalServerException (500)

Usage:
    from app.core.exceptions import NotFoundException
    from app.core.logging import get_logger

    logger = get_logger(__name__)

    def get_file(file_id: str):
        file = database.get(file_id)
        if not file:
            raise NotFoundException(
                message=f"File not found: {file_id}",
                details={"file_id": file_id}
            )
        return file
"""

from typing import Optional, Dict, Any
from app.core.logging import get_logger

logger = get_logger(__name__)


class AppException(Exception):
    """
    Base exception for all application exceptions.

    All custom exceptions should inherit from this class.
    Automatically logs the exception when raised.

    Attributes:
        message: Human-readable error message
        status_code: HTTP status code
        error_code: Machine-readable error code
        details: Additional context information
    """

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: str = "INTERNAL_ERROR",
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the exception.

        Args:
            message: Human-readable error message
            status_code: HTTP status code (default: 500)
            error_code: Machine-readable error code
            details: Additional context information
        """
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}

        # Automatically log the exception
        self._log_exception()

    def _log_exception(self) -> None:
        """Log the exception with appropriate level based on status code."""
        log_data = {
            "error_code": self.error_code,
            "status_code": self.status_code,
            "error_message": self.message,
            **self.details
        }

        # 5xx errors are logged as ERROR, others as WARNING
        if self.status_code >= 500:
            logger.error(
                f"Internal server error: {self.error_code}",
                extra=log_data,
                exc_info=True
            )
        else:
            logger.warning(
                f"Client error: {self.error_code}",
                extra=log_data
            )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert exception to dictionary for JSON response.

        Returns:
            Dictionary with error information
        """
        return {
            "error": {
                "code": self.error_code,
                "message": self.message,
                "details": self.details
            }
        }


class ValidationException(AppException):
    """
    Exception raised when validation fails.

    HTTP Status: 400 Bad Request

    Examples:
        - Invalid input parameters
        - Missing required fields
        - Invalid data format
        - Business rule violations
    """

    def __init__(
        self,
        message: str = "Validation failed",
        error_code: str = "VALIDATION_ERROR",
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            status_code=400,
            error_code=error_code,
            details=details
        )


class UnauthorizedException(AppException):
    """
    Exception raised when authentication fails.

    HTTP Status: 401 Unauthorized

    Examples:
        - Missing authentication token
        - Invalid credentials
        - Expired token
    """

    def __init__(
        self,
        message: str = "Authentication required",
        error_code: str = "UNAUTHORIZED",
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            status_code=401,
            error_code=error_code,
            details=details
        )


class ForbiddenException(AppException):
    """
    Exception raised when user lacks permission.

    HTTP Status: 403 Forbidden

    Examples:
        - User authenticated but not authorized
        - Insufficient permissions for resource
        - Access denied to specific operation
    """

    def __init__(
        self,
        message: str = "Access forbidden",
        error_code: str = "FORBIDDEN",
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            status_code=403,
            error_code=error_code,
            details=details
        )


class NotFoundException(AppException):
    """
    Exception raised when resource is not found.

    HTTP Status: 404 Not Found

    Examples:
        - File not found
        - User not found
        - Segmentation not found
        - Storage file not found
    """

    def __init__(
        self,
        message: str = "Resource not found",
        error_code: str = "NOT_FOUND",
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            status_code=404,
            error_code=error_code,
            details=details
        )


class ConflictException(AppException):
    """
    Exception raised when there's a conflict with current state.

    HTTP Status: 409 Conflict

    Examples:
        - Duplicate resource
        - Concurrent modification
        - State conflict
    """

    def __init__(
        self,
        message: str = "Resource conflict",
        error_code: str = "CONFLICT",
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            status_code=409,
            error_code=error_code,
            details=details
        )


class InternalServerException(AppException):
    """
    Exception raised for internal server errors.

    HTTP Status: 500 Internal Server Error

    Examples:
        - Unexpected errors
        - System failures
        - Unhandled exceptions
    """

    def __init__(
        self,
        message: str = "Internal server error",
        error_code: str = "INTERNAL_ERROR",
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            status_code=500,
            error_code=error_code,
            details=details
        )


# Domain-specific exceptions

class ImageProcessingException(AppException):
    """
    Exception raised during image processing operations.

    HTTP Status: 500 Internal Server Error (default)

    Examples:
        - Failed to load DICOM file
        - Failed to load NIfTI file
        - Invalid image format
        - Matplotlib rendering error
        - Image transformation error
    """

    def __init__(
        self,
        message: str = "Image processing failed",
        error_code: str = "IMAGE_PROCESSING_ERROR",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            status_code=status_code,
            error_code=error_code,
            details=details
        )


class SegmentationException(AppException):
    """
    Exception raised during segmentation operations.

    HTTP Status: 500 Internal Server Error (default)

    Examples:
        - Failed to create segmentation
        - Failed to apply paint stroke
        - Failed to generate overlay
        - Invalid segmentation format
        - Export error
    """

    def __init__(
        self,
        message: str = "Segmentation operation failed",
        error_code: str = "SEGMENTATION_ERROR",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            status_code=status_code,
            error_code=error_code,
            details=details
        )


class CacheException(AppException):
    """
    Exception raised when cache operations fail.

    HTTP Status: 500 Internal Server Error (non-critical - fallback to direct access)

    Examples:
        - Redis connection failed
        - Cache serialization error
        - Cache timeout
        - Invalid cache key
    """

    def __init__(
        self,
        message: str = "Cache operation failed",
        error_code: str = "CACHE_ERROR",
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            status_code=500,
            error_code=error_code,
            details=details
        )


class StorageException(AppException):
    """
    Exception raised during cloud storage operations.

    HTTP Status: Variable (depends on operation)

    Examples:
        - Upload failed
        - Download failed
        - File not found in storage
        - Permission denied
        - Signed URL generation failed
    """

    def __init__(
        self,
        message: str = "Storage operation failed",
        error_code: str = "STORAGE_ERROR",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            status_code=status_code,
            error_code=error_code,
            details=details
        )


class DatabaseException(AppException):
    """
    Exception raised during database operations.

    HTTP Status: 500 Internal Server Error

    Examples:
        - Connection failed
        - Query timeout
        - Integrity constraint violation
        - Transaction rollback
    """

    def __init__(
        self,
        message: str = "Database operation failed",
        error_code: str = "DATABASE_ERROR",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            status_code=status_code,
            error_code=error_code,
            details=details
        )
