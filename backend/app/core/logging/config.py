"""
Logging configuration module.

Provides structured logging with JSON formatting, correlation IDs,
and proper log levels for the Medical Imaging Viewer application.
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional
from pythonjsonlogger import jsonlogger

from app.core.config import get_settings


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """
    Custom JSON formatter that adds additional context to log records.

    Automatically includes:
    - Timestamp
    - Log level
    - Logger name
    - Message
    - Correlation ID (if present)
    - File/line information
    - Exception info (if present)
    """

    def add_fields(self, log_record: dict, record: logging.LogRecord, message_dict: dict):
        """Add custom fields to the log record."""
        super().add_fields(log_record, record, message_dict)

        # Add timestamp
        log_record['timestamp'] = self.formatTime(record, self.datefmt)

        # Add log level
        log_record['level'] = record.levelname

        # Add logger name
        log_record['logger'] = record.name

        # Add file and line information
        log_record['file'] = record.pathname
        log_record['line'] = record.lineno
        log_record['function'] = record.funcName

        # Add correlation ID if present
        if hasattr(record, 'correlation_id'):
            log_record['correlation_id'] = record.correlation_id

        # Add request ID if present
        if hasattr(record, 'request_id'):
            log_record['request_id'] = record.request_id

        # Add user ID if present
        if hasattr(record, 'user_id'):
            log_record['user_id'] = record.user_id


class TextFormatter(logging.Formatter):
    """
    Human-readable text formatter for development.

    Format: [TIMESTAMP] [LEVEL] [MODULE:LINE] - MESSAGE
    """

    def __init__(self):
        super().__init__(
            fmt='[%(asctime)s] [%(levelname)-8s] [%(name)s:%(lineno)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )


def setup_logging(
    log_level: Optional[str] = None,
    log_format: Optional[str] = None,
    log_file: Optional[str] = None
) -> None:
    """
    Configure logging for the application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Format type ("json" or "text")
        log_file: Path to log file

    Example:
        >>> setup_logging(log_level="INFO", log_format="json", log_file="logs/app.log")
    """
    settings = get_settings()

    # Use provided values or fall back to settings
    level = log_level or settings.LOG_LEVEL
    format_type = log_format or settings.LOG_FORMAT
    file_path = log_file or settings.LOG_FILE

    # Convert string level to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Create formatter based on format type
    if format_type.lower() == "json":
        formatter = CustomJsonFormatter(
            '%(timestamp)s %(level)s %(name)s %(message)s'
        )
    else:
        formatter = TextFormatter()

    # Create logs directory if it doesn't exist
    log_path = Path(file_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        filename=file_path,
        maxBytes=settings.LOG_MAX_BYTES,
        backupCount=settings.LOG_BACKUP_COUNT,
        encoding='utf-8'
    )
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("fastapi").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    # Log initialization
    logger = logging.getLogger(__name__)
    logger.info(
        "Logging initialized",
        extra={
            "log_level": level,
            "log_format": format_type,
            "log_file": file_path
        }
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a specific module.

    Args:
        name: Name of the logger (typically __name__)

    Returns:
        Configured logger instance

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("Processing image", extra={"file_id": "abc123"})
    """
    return logging.getLogger(name)
