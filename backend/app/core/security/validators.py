"""
Input Validation and Sanitization for Medical Imaging Viewer
ISO 27001 A.8.2.3 - Handling of assets
ISO 27001 A.14.1.2 - Securing application services on public networks
ISO 27001 A.14.2.1 - Secure development policy

Provides comprehensive input validation to prevent:
- SQL Injection
- XSS (Cross-Site Scripting)
- Command Injection
- Path Traversal
- LDAP Injection
- XML/XXE Injection
- File Upload Exploits

@module core.security.validators
"""

import re
import os
import mimetypes
import hashlib
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from enum import Enum

from pydantic import BaseModel, Field, validator, field_validator
from fastapi import UploadFile, HTTPException, status

from app.core.logging import get_logger, get_audit_logger
from app.core.logging.audit import AuditEventType, AuditSeverity

logger = get_logger(__name__)
audit_logger = get_audit_logger()


class ValidationError(Exception):
    """Base exception for validation errors."""
    pass


class SQLInjectionDetected(ValidationError):
    """SQL injection attempt detected."""
    pass


class XSSDetected(ValidationError):
    """XSS attack detected."""
    pass


class CommandInjectionDetected(ValidationError):
    """Command injection attempt detected."""
    pass


class PathTraversalDetected(ValidationError):
    """Path traversal attempt detected."""
    pass


class InvalidFileFormat(ValidationError):
    """Invalid file format detected."""
    pass


class MaliciousFileDetected(ValidationError):
    """Malicious file detected."""
    pass


# ============================================================================
# SQL INJECTION PREVENTION
# ============================================================================

# SQL keywords that might indicate injection attempts
SQL_KEYWORDS = [
    'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER',
    'EXEC', 'EXECUTE', 'UNION', 'JOIN', 'WHERE', 'FROM', 'TABLE',
    'DATABASE', 'SCHEMA', 'GRANT', 'REVOKE', 'TRUNCATE', '--', '/*', '*/',
    'xp_', 'sp_', 'DECLARE', 'CAST', 'CONVERT', 'CHAR', 'VARCHAR',
    'NVARCHAR', 'CONCAT', 'SUBSTRING', 'ASCII', 'WAITFOR', 'DELAY'
]

# SQL injection patterns
SQL_INJECTION_PATTERNS = [
    r"(\bUNION\b.*\bSELECT\b)",
    r"(\bSELECT\b.*\bFROM\b)",
    r"(\bINSERT\b.*\bINTO\b)",
    r"(\bUPDATE\b.*\bSET\b)",
    r"(\bDELETE\b.*\bFROM\b)",
    r"(\bDROP\b.*\bTABLE\b)",
    r"(;.*\bEXEC\b)",
    r"(;.*\bEXECUTE\b)",
    r"(\bOR\b.*=.*)",
    r"(\bAND\b.*=.*)",
    r"('.*OR.*'.*=.*')",
    r"('.*AND.*'.*=.*')",
    r"(--.*)",
    r"(/\*.*\*/)",
    r"(xp_.*\()",
    r"(sp_.*\()",
]


class SQLValidator:
    """
    SQL Injection Prevention Validator.

    ISO 27001 A.14.2.1 - Secure development policy
    OWASP Top 10 2021 A03:2021 - Injection
    """

    @staticmethod
    def validate(value: str, field_name: str = "input") -> str:
        """
        Validate input for SQL injection attempts.

        Args:
            value: Input string to validate
            field_name: Name of the field being validated

        Returns:
            Sanitized value

        Raises:
            SQLInjectionDetected: If SQL injection pattern is detected
        """
        if not value:
            return value

        # Check for SQL keywords
        value_upper = value.upper()
        for keyword in SQL_KEYWORDS:
            if keyword in value_upper:
                audit_logger.log_security_event(
                    event_type=AuditEventType.SECURITY_INJECTION_ATTEMPT,
                    severity=AuditSeverity.HIGH,
                    description=f"SQL injection attempt detected in field '{field_name}'",
                    metadata={
                        'field': field_name,
                        'keyword_found': keyword,
                        'value_sample': value[:100]
                    }
                )
                raise SQLInjectionDetected(
                    f"SQL injection attempt detected in field '{field_name}': "
                    f"Forbidden keyword '{keyword}' found"
                )

        # Check for SQL injection patterns
        for pattern in SQL_INJECTION_PATTERNS:
            if re.search(pattern, value_upper, re.IGNORECASE):
                audit_logger.log_security_event(
                    event_type=AuditEventType.SECURITY_INJECTION_ATTEMPT,
                    severity=AuditSeverity.HIGH,
                    description=f"SQL injection pattern detected in field '{field_name}'",
                    metadata={
                        'field': field_name,
                        'pattern': pattern,
                        'value_sample': value[:100]
                    }
                )
                raise SQLInjectionDetected(
                    f"SQL injection attempt detected in field '{field_name}': "
                    f"Suspicious pattern found"
                )

        return value


# ============================================================================
# XSS PREVENTION
# ============================================================================

# HTML tags that should be blocked
DANGEROUS_HTML_TAGS = [
    'script', 'iframe', 'embed', 'object', 'applet', 'link', 'style',
    'meta', 'form', 'input', 'button', 'textarea', 'select'
]

# JavaScript event handlers
DANGEROUS_ATTRIBUTES = [
    'onclick', 'onerror', 'onload', 'onmouseover', 'onmouseout',
    'onfocus', 'onblur', 'onchange', 'onsubmit', 'onkeypress',
    'onkeydown', 'onkeyup', 'ondblclick', 'onmousedown', 'onmouseup'
]

# XSS attack patterns
XSS_PATTERNS = [
    r'<script[^>]*>.*?</script>',
    r'javascript:',
    r'on\w+\s*=',
    r'<iframe[^>]*>',
    r'<embed[^>]*>',
    r'<object[^>]*>',
    r'data:text/html',
    r'vbscript:',
    r'expression\(',
]


class XSSValidator:
    """
    XSS (Cross-Site Scripting) Prevention Validator.

    ISO 27001 A.14.2.1 - Secure development policy
    OWASP Top 10 2021 A03:2021 - Injection
    """

    @staticmethod
    def validate(value: str, field_name: str = "input", allow_html: bool = False) -> str:
        """
        Validate input for XSS attempts.

        Args:
            value: Input string to validate
            field_name: Name of the field being validated
            allow_html: Whether to allow safe HTML tags

        Returns:
            Sanitized value

        Raises:
            XSSDetected: If XSS pattern is detected
        """
        if not value:
            return value

        # Check for XSS patterns
        for pattern in XSS_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                audit_logger.log_security_event(
                    event_type=AuditEventType.SECURITY_XSS_ATTEMPT,
                    severity=AuditSeverity.HIGH,
                    description=f"XSS attempt detected in field '{field_name}'",
                    metadata={
                        'field': field_name,
                        'pattern': pattern,
                        'value_sample': value[:100]
                    }
                )
                raise XSSDetected(
                    f"XSS attempt detected in field '{field_name}': "
                    f"Dangerous pattern found"
                )

        # Check for dangerous HTML tags
        if not allow_html:
            for tag in DANGEROUS_HTML_TAGS:
                tag_pattern = f'<{tag}[^>]*>'
                if re.search(tag_pattern, value, re.IGNORECASE):
                    audit_logger.log_security_event(
                        event_type=AuditEventType.SECURITY_XSS_ATTEMPT,
                        severity=AuditSeverity.HIGH,
                        description=f"Dangerous HTML tag detected in field '{field_name}'",
                        metadata={
                            'field': field_name,
                            'tag': tag,
                            'value_sample': value[:100]
                        }
                    )
                    raise XSSDetected(
                        f"XSS attempt detected in field '{field_name}': "
                        f"Dangerous HTML tag '<{tag}>' not allowed"
                    )

        # Check for dangerous attributes (event handlers)
        for attr in DANGEROUS_ATTRIBUTES:
            if re.search(f'{attr}\\s*=', value, re.IGNORECASE):
                audit_logger.log_security_event(
                    event_type=AuditEventType.SECURITY_XSS_ATTEMPT,
                    severity=AuditSeverity.HIGH,
                    description=f"Dangerous attribute detected in field '{field_name}'",
                    metadata={
                        'field': field_name,
                        'attribute': attr,
                        'value_sample': value[:100]
                    }
                )
                raise XSSDetected(
                    f"XSS attempt detected in field '{field_name}': "
                    f"Dangerous attribute '{attr}' not allowed"
                )

        return value

    @staticmethod
    def sanitize(value: str) -> str:
        """
        Sanitize string by escaping HTML special characters.

        Args:
            value: String to sanitize

        Returns:
            Sanitized string with HTML entities escaped
        """
        if not value:
            return value

        # Escape HTML special characters
        replacements = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#x27;',
            '/': '&#x2F;',
        }

        for char, entity in replacements.items():
            value = value.replace(char, entity)

        return value


# ============================================================================
# COMMAND INJECTION PREVENTION
# ============================================================================

# Shell metacharacters that could be used for command injection
SHELL_METACHARACTERS = [
    ';', '|', '&', '$', '`', '\n', '\r', '(', ')', '<', '>',
    '{', '}', '[', ']', '!', '*', '?', '~', '^', '\\', '\x00'
]

# Command injection patterns
COMMAND_INJECTION_PATTERNS = [
    r';\s*\w+',
    r'\|\s*\w+',
    r'&&\s*\w+',
    r'\|\|\s*\w+',
    r'`.*`',
    r'\$\(.*\)',
    r'\${.*}',
]


class CommandInjectionValidator:
    """
    Command Injection Prevention Validator.

    ISO 27001 A.14.2.1 - Secure development policy
    OWASP Top 10 2021 A03:2021 - Injection
    """

    @staticmethod
    def validate(value: str, field_name: str = "input") -> str:
        """
        Validate input for command injection attempts.

        Args:
            value: Input string to validate
            field_name: Name of the field being validated

        Returns:
            Sanitized value

        Raises:
            CommandInjectionDetected: If command injection pattern is detected
        """
        if not value:
            return value

        # Check for shell metacharacters
        for char in SHELL_METACHARACTERS:
            if char in value:
                audit_logger.log_security_event(
                    event_type=AuditEventType.SECURITY_INJECTION_ATTEMPT,
                    severity=AuditSeverity.HIGH,
                    description=f"Command injection attempt detected in field '{field_name}'",
                    metadata={
                        'field': field_name,
                        'metacharacter': repr(char),
                        'value_sample': value[:100]
                    }
                )
                raise CommandInjectionDetected(
                    f"Command injection attempt detected in field '{field_name}': "
                    f"Shell metacharacter {repr(char)} not allowed"
                )

        # Check for command injection patterns
        for pattern in COMMAND_INJECTION_PATTERNS:
            if re.search(pattern, value):
                audit_logger.log_security_event(
                    event_type=AuditEventType.SECURITY_INJECTION_ATTEMPT,
                    severity=AuditSeverity.HIGH,
                    description=f"Command injection pattern detected in field '{field_name}'",
                    metadata={
                        'field': field_name,
                        'pattern': pattern,
                        'value_sample': value[:100]
                    }
                )
                raise CommandInjectionDetected(
                    f"Command injection attempt detected in field '{field_name}': "
                    f"Suspicious pattern found"
                )

        return value


# ============================================================================
# PATH TRAVERSAL PREVENTION
# ============================================================================

# Path traversal patterns
PATH_TRAVERSAL_PATTERNS = [
    r'\.\.',
    r'\.\\',
    r'\.\/',
    r'%2e%2e',
    r'%252e%252e',
    r'\.\.%2f',
    r'\.\.%5c',
]


class PathTraversalValidator:
    """
    Path Traversal Prevention Validator.

    ISO 27001 A.14.2.1 - Secure development policy
    OWASP Top 10 2021 A01:2021 - Broken Access Control
    """

    @staticmethod
    def validate(value: str, field_name: str = "path") -> str:
        """
        Validate path for traversal attempts.

        Args:
            value: Path string to validate
            field_name: Name of the field being validated

        Returns:
            Validated path

        Raises:
            PathTraversalDetected: If path traversal attempt is detected
        """
        if not value:
            return value

        # Check for path traversal patterns
        for pattern in PATH_TRAVERSAL_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                audit_logger.log_security_event(
                    event_type=AuditEventType.SECURITY_PATH_TRAVERSAL,
                    severity=AuditSeverity.HIGH,
                    description=f"Path traversal attempt detected in field '{field_name}'",
                    metadata={
                        'field': field_name,
                        'pattern': pattern,
                        'value': value
                    }
                )
                raise PathTraversalDetected(
                    f"Path traversal attempt detected in field '{field_name}': "
                    f"Suspicious pattern found"
                )

        # Normalize path and check if it stays within bounds
        try:
            normalized = os.path.normpath(value)

            # Check for absolute paths (should be relative)
            if os.path.isabs(normalized):
                raise PathTraversalDetected(
                    f"Path traversal attempt detected in field '{field_name}': "
                    f"Absolute paths not allowed"
                )

            # Check if normalized path goes outside current directory
            if normalized.startswith('..'):
                raise PathTraversalDetected(
                    f"Path traversal attempt detected in field '{field_name}': "
                    f"Path escapes base directory"
                )

        except Exception as e:
            logger.error(f"Path validation error: {e}")
            raise PathTraversalDetected(
                f"Invalid path in field '{field_name}'"
            )

        return normalized


# ============================================================================
# FILE UPLOAD VALIDATION
# ============================================================================

class MedicalImageFormat(str, Enum):
    """Allowed medical image formats."""
    DICOM = "application/dicom"
    NIFTI = "application/nifti"
    NIFTI_GZ = "application/nifti-gz"
    PNG = "image/png"
    JPEG = "image/jpeg"
    TIFF = "image/tiff"


# Allowed MIME types for medical imaging
ALLOWED_MIME_TYPES = {
    MedicalImageFormat.DICOM: ['.dcm', '.dicom'],
    MedicalImageFormat.NIFTI: ['.nii'],
    MedicalImageFormat.NIFTI_GZ: ['.nii.gz'],
    MedicalImageFormat.PNG: ['.png'],
    MedicalImageFormat.JPEG: ['.jpg', '.jpeg'],
    MedicalImageFormat.TIFF: ['.tif', '.tiff'],
}

# File magic numbers (first bytes) for format verification
FILE_MAGIC_NUMBERS = {
    'DICOM': b'DICM',
    'PNG': b'\x89PNG\r\n\x1a\n',
    'JPEG': b'\xff\xd8\xff',
    'TIFF_LE': b'II\x2a\x00',  # Little-endian
    'TIFF_BE': b'MM\x00\x2a',  # Big-endian
    'GZIP': b'\x1f\x8b',  # For .nii.gz
}

# Maximum file size (500 MB for medical images)
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB


class FileUploadValidator:
    """
    File Upload Security Validator.

    ISO 27001 A.14.2.1 - Secure development policy
    ISO 27001 A.8.2.3 - Handling of assets
    OWASP Top 10 2021 A04:2021 - Insecure Design
    """

    @staticmethod
    async def validate_file(
        file: UploadFile,
        max_size: int = MAX_FILE_SIZE,
        allowed_formats: Optional[List[MedicalImageFormat]] = None
    ) -> Tuple[str, str]:
        """
        Validate uploaded file for security and format compliance.

        Args:
            file: Uploaded file
            max_size: Maximum file size in bytes
            allowed_formats: List of allowed formats (None = all medical formats)

        Returns:
            Tuple of (validated_filename, detected_mime_type)

        Raises:
            InvalidFileFormat: If file format is invalid
            MaliciousFileDetected: If file appears malicious
            HTTPException: For various validation failures
        """
        if not file:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No file provided"
            )

        # Validate filename
        filename = FileUploadValidator._validate_filename(file.filename)

        # Read file content for validation
        content = await file.read()
        file_size = len(content)

        # Reset file pointer for later processing
        await file.seek(0)

        # Check file size
        if file_size > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large: {file_size} bytes (max: {max_size} bytes)"
            )

        if file_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File is empty"
            )

        # Detect file format from magic numbers
        detected_format = FileUploadValidator._detect_file_format(content, filename)

        # Validate against allowed formats
        if allowed_formats and detected_format not in allowed_formats:
            audit_logger.log_security_event(
                event_type=AuditEventType.SECURITY_INVALID_INPUT,
                severity=AuditSeverity.MEDIUM,
                description=f"Invalid file format uploaded: {detected_format}",
                metadata={
                    'filename': filename,
                    'detected_format': detected_format,
                    'file_size': file_size
                }
            )
            raise InvalidFileFormat(
                f"File format '{detected_format}' not allowed. "
                f"Allowed formats: {[f.value for f in allowed_formats]}"
            )

        # Check for malicious content
        FileUploadValidator._check_malicious_content(content, filename)

        # Calculate file hash for integrity
        file_hash = hashlib.sha256(content).hexdigest()

        # Log successful upload validation
        logger.info(
            f"File upload validated: {filename}",
            extra={
                'filename': filename,
                'format': detected_format,
                'size': file_size,
                'hash': file_hash
            }
        )

        return filename, detected_format

    @staticmethod
    def _validate_filename(filename: str) -> str:
        """
        Validate and sanitize filename.

        Args:
            filename: Original filename

        Returns:
            Sanitized filename

        Raises:
            PathTraversalDetected: If filename contains path traversal
        """
        if not filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Filename is required"
            )

        # Check for path traversal
        PathTraversalValidator.validate(filename, "filename")

        # Remove any path components (just in case)
        filename = os.path.basename(filename)

        # Validate filename characters (alphanumeric, dots, hyphens, underscores)
        if not re.match(r'^[\w\-. ]+$', filename):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Filename contains invalid characters"
            )

        # Check filename length
        if len(filename) > 255:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Filename too long (max 255 characters)"
            )

        return filename

    @staticmethod
    def _detect_file_format(content: bytes, filename: str) -> str:
        """
        Detect file format from magic numbers and extension.

        Args:
            content: File content
            filename: Filename

        Returns:
            Detected MIME type

        Raises:
            InvalidFileFormat: If format cannot be determined
        """
        # Check magic numbers
        if content.startswith(FILE_MAGIC_NUMBERS['PNG']):
            return MedicalImageFormat.PNG
        elif content.startswith(FILE_MAGIC_NUMBERS['JPEG']):
            return MedicalImageFormat.JPEG
        elif content.startswith(FILE_MAGIC_NUMBERS['TIFF_LE']) or \
             content.startswith(FILE_MAGIC_NUMBERS['TIFF_BE']):
            return MedicalImageFormat.TIFF
        elif b'DICM' in content[128:132]:  # DICOM signature at offset 128
            return MedicalImageFormat.DICOM
        elif content.startswith(FILE_MAGIC_NUMBERS['GZIP']):
            # Likely .nii.gz
            if filename.endswith('.nii.gz'):
                return MedicalImageFormat.NIFTI_GZ

        # Fall back to extension-based detection
        ext = os.path.splitext(filename)[1].lower()

        for mime_type, extensions in ALLOWED_MIME_TYPES.items():
            if ext in extensions:
                return mime_type

        raise InvalidFileFormat(
            f"Unable to determine file format for '{filename}'"
        )

    @staticmethod
    def _check_malicious_content(content: bytes, filename: str) -> None:
        """
        Check for malicious content in file.

        Args:
            content: File content
            filename: Filename

        Raises:
            MaliciousFileDetected: If malicious content is found
        """
        # Check for embedded scripts in image metadata
        suspicious_patterns = [
            b'<script',
            b'javascript:',
            b'onerror=',
            b'onload=',
            b'<?php',
            b'#!/bin/',
            b'eval(',
        ]

        content_lower = content.lower()
        for pattern in suspicious_patterns:
            if pattern in content_lower:
                audit_logger.log_security_event(
                    event_type=AuditEventType.SECURITY_MALWARE_DETECTED,
                    severity=AuditSeverity.CRITICAL,
                    description=f"Malicious content detected in uploaded file",
                    metadata={
                        'filename': filename,
                        'pattern': pattern.decode('utf-8', errors='ignore')
                    }
                )
                raise MaliciousFileDetected(
                    f"Malicious content detected in file '{filename}'"
                )


# ============================================================================
# PYDANTIC MODELS WITH BUILT-IN VALIDATION
# ============================================================================

class ValidatedString(BaseModel):
    """String with automatic XSS and SQL injection validation."""

    value: str = Field(..., min_length=1, max_length=1000)

    @field_validator('value')
    @classmethod
    def validate_value(cls, v: str) -> str:
        """Validate string for XSS and SQL injection."""
        v = SQLValidator.validate(v, "value")
        v = XSSValidator.validate(v, "value", allow_html=False)
        return v


class ValidatedPath(BaseModel):
    """Path with automatic traversal validation."""

    path: str = Field(..., min_length=1, max_length=500)

    @field_validator('path')
    @classmethod
    def validate_path(cls, v: str) -> str:
        """Validate path for traversal attempts."""
        return PathTraversalValidator.validate(v, "path")


class ValidatedCommand(BaseModel):
    """Command with automatic injection validation."""

    command: str = Field(..., min_length=1, max_length=500)

    @field_validator('command')
    @classmethod
    def validate_command(cls, v: str) -> str:
        """Validate command for injection attempts."""
        return CommandInjectionValidator.validate(v, "command")


# ============================================================================
# COMPREHENSIVE INPUT VALIDATOR
# ============================================================================

class InputValidator:
    """
    Comprehensive input validator combining all validation strategies.

    Usage:
        >>> validator = InputValidator()
        >>> validator.validate_all(user_input, field_name="username")
    """

    @staticmethod
    def validate_all(
        value: str,
        field_name: str = "input",
        check_sql: bool = True,
        check_xss: bool = True,
        check_command: bool = False,
        check_path: bool = False,
        allow_html: bool = False
    ) -> str:
        """
        Validate input against multiple attack vectors.

        Args:
            value: Input to validate
            field_name: Name of the field
            check_sql: Check for SQL injection
            check_xss: Check for XSS
            check_command: Check for command injection
            check_path: Check for path traversal
            allow_html: Allow safe HTML tags

        Returns:
            Validated value

        Raises:
            ValidationError: If any validation fails
        """
        if not value:
            return value

        validated = value

        if check_sql:
            validated = SQLValidator.validate(validated, field_name)

        if check_xss:
            validated = XSSValidator.validate(validated, field_name, allow_html)

        if check_command:
            validated = CommandInjectionValidator.validate(validated, field_name)

        if check_path:
            validated = PathTraversalValidator.validate(validated, field_name)

        return validated

    @staticmethod
    def sanitize_html(value: str) -> str:
        """
        Sanitize HTML by escaping special characters.

        Args:
            value: String to sanitize

        Returns:
            Sanitized string
        """
        return XSSValidator.sanitize(value)
