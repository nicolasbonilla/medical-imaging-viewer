"""
Logging context module for correlation IDs and request tracking.

Provides thread-local storage for correlation IDs that persist
across the entire request lifecycle.
"""

import uuid
from contextvars import ContextVar
from typing import Optional

# Context variables for request tracking
correlation_id_var: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)
request_id_var: ContextVar[Optional[str]] = ContextVar('request_id', default=None)
user_id_var: ContextVar[Optional[str]] = ContextVar('user_id', default=None)


def generate_correlation_id() -> str:
    """
    Generate a new correlation ID.

    Returns:
        UUID-based correlation ID

    Example:
        >>> correlation_id = generate_correlation_id()
        >>> print(correlation_id)
        'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
    """
    return str(uuid.uuid4())


def set_correlation_id(correlation_id: str) -> None:
    """
    Set the correlation ID for the current context.

    Args:
        correlation_id: Correlation ID to set

    Example:
        >>> set_correlation_id("request-123")
    """
    correlation_id_var.set(correlation_id)


def get_correlation_id() -> Optional[str]:
    """
    Get the correlation ID for the current context.

    Returns:
        Current correlation ID or None

    Example:
        >>> correlation_id = get_correlation_id()
        >>> if correlation_id:
        ...     print(f"Current request: {correlation_id}")
    """
    return correlation_id_var.get()


def set_request_id(request_id: str) -> None:
    """
    Set the request ID for the current context.

    Args:
        request_id: Request ID to set
    """
    request_id_var.set(request_id)


def get_request_id() -> Optional[str]:
    """Get the request ID for the current context."""
    return request_id_var.get()


def set_user_id(user_id: str) -> None:
    """
    Set the user ID for the current context.

    Args:
        user_id: User ID to set
    """
    user_id_var.set(user_id)


def get_user_id() -> Optional[str]:
    """Get the user ID for the current context."""
    return user_id_var.get()


def clear_context() -> None:
    """
    Clear all context variables.

    Should be called at the end of each request to prevent leakage.
    """
    correlation_id_var.set(None)
    request_id_var.set(None)
    user_id_var.set(None)
