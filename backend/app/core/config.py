"""
Application configuration with secure environment variable management.

Implements ISO 27001 A.9.2.4 (Management of secret authentication information)
and A.10.1.2 (Key management).

@module core.config
"""

import os
import secrets
import warnings
from typing import List, Union
from functools import lru_cache
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SecuritySettings(BaseSettings):
    """Security-specific settings (ISO 27001 A.9.4.2, A.9.4.3, A.10.1.1)."""

    # JWT Configuration (ISO 27001 A.9.4.2)
    JWT_SECRET_KEY: str = Field(default="", description="JWT signing secret key")
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, ge=5, le=1440)
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, ge=1, le=30)

    # Password Policy (ISO 27001 A.9.4.3)
    PASSWORD_MIN_LENGTH: int = Field(default=12, ge=8, le=128)
    PASSWORD_REQUIRE_UPPERCASE: bool = True
    PASSWORD_REQUIRE_LOWERCASE: bool = True
    PASSWORD_REQUIRE_DIGIT: bool = True
    PASSWORD_REQUIRE_SPECIAL: bool = True
    PASSWORD_MAX_AGE_DAYS: int = Field(default=90, ge=30, le=365)
    PASSWORD_HISTORY_COUNT: int = Field(default=5, ge=3, le=24)

    # Account Lockout Policy (ISO 27001 A.9.4.2)
    ACCOUNT_LOCKOUT_THRESHOLD: int = Field(default=5, ge=3, le=10)
    ACCOUNT_LOCKOUT_DURATION_MINUTES: int = Field(default=30, ge=15, le=1440)

    # Encryption Configuration (ISO 27001 A.10.1.1, A.10.1.2)
    ENCRYPTION_MASTER_KEY: str = Field(default="", description="Master encryption key")
    KDF_ITERATIONS: int = Field(default=100_000, ge=100_000, le=1_000_000)
    KDF_ALGORITHM: str = Field(default="SHA256")
    KEY_ROTATION_DAYS: int = Field(default=90, ge=30, le=365)

    @field_validator('JWT_SECRET_KEY')
    @classmethod
    def validate_jwt_secret_key(cls, v: str) -> str:
        """Validate JWT secret key strength (ISO 27001 A.9.2.4)."""
        if not v:
            if os.getenv("ENVIRONMENT") == "production":
                raise ValueError("JWT_SECRET_KEY must be set in production environment")
            warnings.warn("JWT_SECRET_KEY not set, using temporary key. NEVER use in production!")
            return secrets.token_urlsafe(64)
        if len(v) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters long")
        return v

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Application Configuration
    APP_NAME: str = Field(default="Medical Imaging Viewer")
    APP_VERSION: str = Field(default="1.0.0")
    DEBUG: bool = Field(default=False)
    ENVIRONMENT: str = Field(default="production")
    API_V1_STR: str = Field(default="/api/v1")

    # Server Configuration
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000, ge=1, le=65535)

    # CORS Configuration
    # Note: Annotated with Union[str, List[str]] to prevent Pydantic from JSON-decoding string values
    CORS_ORIGINS: Union[str, List[str]] = Field(default=["http://localhost:5173", "http://localhost:3000"])

    @field_validator('CORS_ORIGINS', mode='before')
    @classmethod
    def parse_cors_origins(cls, v) -> List[str]:
        if isinstance(v, str):
            # Parse comma-separated string
            return [origin.strip() for origin in v.split(',')]
        return v

    # Legacy properties for backward compatibility
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Google Drive
    GOOGLE_DRIVE_CREDENTIALS_FILE: str = Field(default="credentials.json")
    GOOGLE_DRIVE_TOKEN_FILE: str = Field(default="token.json")
    GOOGLE_DRIVE_SCOPES: str = Field(default="https://www.googleapis.com/auth/drive.readonly")

    # Upload Configuration
    MAX_UPLOAD_SIZE: int = Field(default=524_288_000, ge=1_000_000, le=1_073_741_824)
    ALLOWED_EXTENSIONS: List[str] = Field(default=[".dcm", ".nii", ".nii.gz", ".img", ".hdr"])

    @field_validator('ALLOWED_EXTENSIONS', mode='before')
    @classmethod
    def parse_allowed_extensions(cls, v):
        if isinstance(v, str):
            return [ext.strip() for ext in v.split(',')]
        return v

    # Redis Configuration
    REDIS_HOST: str = Field(default="localhost")
    REDIS_PORT: int = Field(default=6379, ge=1, le=65535)
    REDIS_DB: int = Field(default=0, ge=0, le=15)
    REDIS_PASSWORD: str = Field(default="")
    REDIS_MAX_CONNECTIONS: int = Field(default=50, ge=1, le=1000)

    # Cache TTL
    CACHE_DRIVE_FILES_TTL: int = Field(default=300, ge=60, le=3600)
    CACHE_IMAGES_TTL: int = Field(default=1800, ge=300, le=7200)
    CACHE_METADATA_TTL: int = Field(default=600, ge=60, le=3600)
    CACHE_DEFAULT_TTL: int = Field(default=3600, ge=300, le=86400)

    # Logging (ISO 27001 A.12.4.1)
    LOG_LEVEL: str = Field(default="INFO")
    LOG_FORMAT: str = Field(default="json")
    LOG_FILE: str = Field(default="logs/app.log")
    LOG_MAX_BYTES: int = Field(default=10_485_760, ge=1_000_000)
    LOG_BACKUP_COUNT: int = Field(default=10, ge=1, le=100)

    @field_validator('LOG_LEVEL')
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of: {', '.join(valid_levels)}")
        return v_upper

    # Performance Optimization Flags
    ENABLE_BINARY_PROTOCOL: bool = Field(default=False)
    ENABLE_WEBSOCKET: bool = Field(default=False)
    WEBSOCKET_MAX_CONNECTIONS: int = Field(default=100, ge=10, le=10000)
    WEBSOCKET_HEARTBEAT_INTERVAL: int = Field(default=30, ge=10, le=300)

    ENABLE_PREFETCHING: bool = Field(default=True)
    PREFETCH_SLICES: int = Field(default=3, ge=1, le=10)
    PREFETCH_PRIORITY: str = Field(default="normal")

    USE_REDIS_SCAN: bool = Field(default=True)
    REDIS_SCAN_COUNT: int = Field(default=100, ge=10, le=1000)

    ENABLE_CACHE_WARMING: bool = Field(default=False)
    CACHE_WARMING_ON_STARTUP: bool = Field(default=False)

    # Security Middleware Configuration (ISO 27001 A.14.2.1)
    RATE_LIMIT_ENABLED: bool = Field(default=True)
    INPUT_VALIDATION_ENABLED: bool = Field(default=True)
    INPUT_VALIDATION_STRICT: bool = Field(default=True)

    # TLS/SSL Configuration (ISO 27001 A.13.1.1, A.13.2.1)
    TLS_ENABLED: bool = Field(default=False)
    TLS_CERT_FILE: str = Field(default="/path/to/cert.pem")
    TLS_KEY_FILE: str = Field(default="/path/to/key.pem")
    TLS_MIN_VERSION: str = Field(default="1.3")
    TLS_ENFORCE_HTTPS: bool = Field(default=True)
    TLS_REDIRECT_TO_HTTPS: bool = Field(default=False)

    # HSTS Configuration
    HSTS_ENABLED: bool = Field(default=False)
    HSTS_MAX_AGE: int = Field(default=31536000, ge=86400)  # 1 year minimum
    HSTS_INCLUDE_SUBDOMAINS: bool = Field(default=True)
    HSTS_PRELOAD: bool = Field(default=False)

    # Security Headers Configuration
    SECURITY_HEADER_LEVEL: str = Field(default="STANDARD")
    CUSTOM_CSP: str = Field(default="")
    CSP_REPORT_URI: str = Field(default="")

    # Allowed Hosts (Host header validation)
    ALLOWED_HOSTS: List[str] = Field(default=[])

    @field_validator('ALLOWED_HOSTS', mode='before')
    @classmethod
    def parse_allowed_hosts(cls, v):
        if isinstance(v, str):
            return [host.strip() for host in v.split(',') if host.strip()]
        return v

    @field_validator('TLS_MIN_VERSION')
    @classmethod
    def validate_tls_version(cls, v: str) -> str:
        valid_versions = ["1.2", "1.3"]
        if v not in valid_versions:
            raise ValueError(f"TLS_MIN_VERSION must be one of: {', '.join(valid_versions)}")
        return v

    @field_validator('SECURITY_HEADER_LEVEL')
    @classmethod
    def validate_security_header_level(cls, v: str) -> str:
        valid_levels = ["MINIMAL", "STANDARD", "STRICT", "PARANOID"]
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"SECURITY_HEADER_LEVEL must be one of: {', '.join(valid_levels)}")
        return v_upper

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    def model_post_init(self, __context) -> None:
        """Post-initialization: Load security settings and validate."""
        # Load security settings
        security = SecuritySettings()
        
        # Update legacy fields
        self.SECRET_KEY = security.JWT_SECRET_KEY
        self.ALGORITHM = security.JWT_ALGORITHM
        self.ACCESS_TOKEN_EXPIRE_MINUTES = security.JWT_ACCESS_TOKEN_EXPIRE_MINUTES

        # Security warnings for production
        if self.ENVIRONMENT == "production":
            if self.DEBUG:
                warnings.warn("DEBUG mode enabled in production. This is a security risk.")


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
