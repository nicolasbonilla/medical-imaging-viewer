"""
Logging adapter module.

Provides a custom LoggerAdapter that automatically includes
correlation IDs and other context in log records.
"""

import logging
from typing import Any, Dict, Optional

from app.core.logging.context import (
    get_correlation_id,
    get_request_id,
    get_user_id
)


class ContextLoggerAdapter(logging.LoggerAdapter):
    """
    Logger adapter that automatically includes context variables.

    Automatically adds:
    - correlation_id
    - request_id
    - user_id

    Example:
        >>> from app.core.logging import get_logger
        >>> logger = get_logger(__name__)
        >>> logger.info("Processing request", extra={"file_id": "abc123"})
        # Logs will include correlation_id, request_id, user_id automatically
    """

    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        """
        Process the log message and inject context variables.

        Args:
            msg: Log message
            kwargs: Keyword arguments (includes 'extra')

        Returns:
            Tuple of (message, kwargs) with context injected
        """
        # Get context variables
        correlation_id = get_correlation_id()
        request_id = get_request_id()
        user_id = get_user_id()

        # Create or update extra dict
        extra = kwargs.get('extra', {})

        # Add context variables if present
        if correlation_id:
            extra['correlation_id'] = correlation_id
        if request_id:
            extra['request_id'] = request_id
        if user_id:
            extra['user_id'] = user_id

        # Update kwargs
        kwargs['extra'] = extra

        return msg, kwargs


def get_context_logger(name: str) -> ContextLoggerAdapter:
    """
    Get a context-aware logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        ContextLoggerAdapter instance

    Example:
        >>> logger = get_context_logger(__name__)
        >>> logger.info("User action", extra={"action": "upload"})
    """
    base_logger = logging.getLogger(name)
    return ContextLoggerAdapter(base_logger, {})
