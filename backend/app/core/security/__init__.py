"""
Security module for Medical Imaging Viewer.

Provides comprehensive security controls including:
- Rate limiting and DoS protection (ISO 27001 A.12.2.1)
- IP blacklisting (ISO 27001 A.13.1.3)
- Input validation and sanitization (ISO 27001 A.14.2.1)

@module core.security
"""

from app.core.security.rate_limiter import (
    RateLimiter,
    RateLimitStrategy,
    RateLimitScope,
    RateLimitExceeded,
    RATE_LIMIT_CONFIGS,
    get_rate_limiter,
)

from app.core.security.rate_limit_middleware import (
    RateLimitMiddleware,
    IPBlacklistMiddleware,
)

from app.core.security.validators import (
    # Validators
    SQLValidator,
    XSSValidator,
    CommandInjectionValidator,
    PathTraversalValidator,
    FileUploadValidator,
    InputValidator,
    # Exceptions
    ValidationError,
    SQLInjectionDetected,
    XSSDetected,
    CommandInjectionDetected,
    PathTraversalDetected,
    InvalidFileFormat,
    MaliciousFileDetected,
    # Pydantic models
    ValidatedString,
    ValidatedPath,
    ValidatedCommand,
    # Enums
    MedicalImageFormat,
)

from app.core.security.validation_middleware import (
    InputValidationMiddleware,
)

from app.core.security.encryption import (
    # Encryption classes
    AESGCMEncryption,
    EncryptionService,
    EncryptedRedisClient,
    KeyDerivation,
    # Enums
    DataClassification,
    # Exceptions
    EncryptionError,
    DecryptionError,
    KeyDerivationError,
    # Factory functions
    create_encryption_service,
    create_encrypted_redis_client,
)

from app.core.security.tls_enforcement import (
    # TLS Enforcement
    TLSEnforcementMiddleware,
    CertificateValidator,
    # Enums
    TLSVersion,
    SecurityHeaderLevel,
    # Functions
    get_security_headers,
    create_ssl_context,
    # Constants
    TLS_1_2_CIPHERS,
    TLS_1_3_CIPHERS,
    BLOCKED_CIPHERS,
)

__all__ = [
    # Rate Limiting (ISO 27001 A.12.2.1)
    "RateLimiter",
    "RateLimitStrategy",
    "RateLimitScope",
    "RateLimitExceeded",
    "RATE_LIMIT_CONFIGS",
    "get_rate_limiter",
    "RateLimitMiddleware",

    # IP Blacklisting (ISO 27001 A.13.1.3)
    "IPBlacklistMiddleware",

    # Input Validation (ISO 27001 A.14.2.1)
    "SQLValidator",
    "XSSValidator",
    "CommandInjectionValidator",
    "PathTraversalValidator",
    "FileUploadValidator",
    "InputValidator",
    "ValidationError",
    "SQLInjectionDetected",
    "XSSDetected",
    "CommandInjectionDetected",
    "PathTraversalDetected",
    "InvalidFileFormat",
    "MaliciousFileDetected",
    "ValidatedString",
    "ValidatedPath",
    "ValidatedCommand",
    "MedicalImageFormat",
    "InputValidationMiddleware",

    # Encryption (ISO 27001 A.10.1.1, A.10.1.2)
    "AESGCMEncryption",
    "EncryptionService",
    "EncryptedRedisClient",
    "KeyDerivation",
    "DataClassification",
    "EncryptionError",
    "DecryptionError",
    "KeyDerivationError",
    "create_encryption_service",
    "create_encrypted_redis_client",

    # TLS/SSL Enforcement (ISO 27001 A.13.1.1, A.13.2.1)
    "TLSEnforcementMiddleware",
    "CertificateValidator",
    "TLSVersion",
    "SecurityHeaderLevel",
    "get_security_headers",
    "create_ssl_context",
    "TLS_1_2_CIPHERS",
    "TLS_1_3_CIPHERS",
    "BLOCKED_CIPHERS",
]
