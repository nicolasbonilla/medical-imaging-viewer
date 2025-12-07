"""
Security data models for authentication and authorization.

Implements ISO 27001 A.9.2.1 (User registration and de-registration)
and A.9.4.3 (Password management system).

@module security.models
"""

from pydantic import BaseModel, Field, field_validator, EmailStr
from typing import Optional, List
from datetime import datetime
from enum import Enum


class UserRole(str, Enum):
    """
    User roles for RBAC (ISO 27001 A.9.2.3).

    Roles are hierarchical:
    - ADMIN: Full system access (privileged)
    - RADIOLOGIST: Can view and analyze all medical images
    - TECHNICIAN: Can upload and process images
    - VIEWER: Read-only access to assigned images
    """
    ADMIN = "admin"
    RADIOLOGIST = "radiologist"
    TECHNICIAN = "technician"
    VIEWER = "viewer"


class Permission(str, Enum):
    """
    Granular permissions for access control (ISO 27001 A.9.4.1).

    Format: <resource>:<action>
    """
    # Image permissions
    IMAGE_VIEW = "image:view"
    IMAGE_UPLOAD = "image:upload"
    IMAGE_DELETE = "image:delete"
    IMAGE_EXPORT = "image:export"

    # Segmentation permissions
    SEGMENTATION_CREATE = "segmentation:create"
    SEGMENTATION_VIEW = "segmentation:view"
    SEGMENTATION_DELETE = "segmentation:delete"

    # User management permissions
    USER_CREATE = "user:create"
    USER_VIEW = "user:view"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"

    # Audit permissions
    AUDIT_VIEW = "audit:view"
    AUDIT_EXPORT = "audit:export"

    # System permissions
    SYSTEM_CONFIG = "system:config"
    SYSTEM_HEALTH = "system:health"


class PasswordPolicy(BaseModel):
    """
    Password policy configuration (ISO 27001 A.9.4.3).

    Implements strong password requirements:
    - Minimum 12 characters
    - Must contain: uppercase, lowercase, digit, special char
    - Maximum age: 90 days
    - Password history: 5 passwords
    - Account lockout: 5 failed attempts
    """
    min_length: int = Field(default=12, ge=8, le=128)
    require_uppercase: bool = True
    require_lowercase: bool = True
    require_digit: bool = True
    require_special: bool = True
    max_age_days: int = Field(default=90, ge=30, le=365)
    password_history_count: int = Field(default=5, ge=3, le=24)
    lockout_threshold: int = Field(default=5, ge=3, le=10)
    lockout_duration_minutes: int = Field(default=30, ge=15, le=1440)

    class Config:
        json_schema_extra = {
            "example": {
                "min_length": 12,
                "require_uppercase": True,
                "require_lowercase": True,
                "require_digit": True,
                "require_special": True,
                "max_age_days": 90,
                "password_history_count": 5,
                "lockout_threshold": 5,
                "lockout_duration_minutes": 30,
            }
        }


class User(BaseModel):
    """
    User model for authentication (ISO 27001 A.9.2.1).

    Attributes:
        id: Unique user identifier
        username: Unique username (3-50 chars)
        email: Valid email address
        full_name: User's full name
        role: User role for RBAC
        is_active: Account active status
        is_locked: Account locked status (after failed login attempts)
        email_verified: Email verification status
        created_at: Account creation timestamp
        updated_at: Last update timestamp
        last_login: Last successful login timestamp
        last_password_change: Last password change timestamp
        failed_login_attempts: Count of consecutive failed logins
        locked_until: Account unlock timestamp
    """
    id: str = Field(..., description="Unique user identifier (UUID)")
    username: str = Field(..., min_length=3, max_length=50, pattern="^[a-zA-Z0-9_-]+$")
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=100)
    role: UserRole
    is_active: bool = True
    is_locked: bool = False
    email_verified: bool = False
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None
    last_password_change: Optional[datetime] = None
    failed_login_attempts: int = 0
    locked_until: Optional[datetime] = None

    # Audit fields (ISO 27001 A.12.4.1)
    created_by: Optional[str] = None
    updated_by: Optional[str] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "username": "john.doe",
                "email": "john.doe@hospital.com",
                "full_name": "Dr. John Doe",
                "role": "radiologist",
                "is_active": True,
                "is_locked": False,
                "email_verified": True,
                "created_at": "2025-11-22T10:00:00Z",
                "updated_at": "2025-11-22T10:00:00Z",
            }
        }


class UserCreate(BaseModel):
    """
    User creation request (ISO 27001 A.9.2.1).

    Password must meet policy requirements.
    """
    username: str = Field(..., min_length=3, max_length=50, pattern="^[a-zA-Z0-9_-]+$")
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=12, max_length=128)
    role: UserRole = UserRole.VIEWER  # Default to least privilege

    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """
        Validate password meets policy requirements (ISO 27001 A.9.4.3).

        Raises:
            ValueError: If password doesn't meet requirements
        """
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters long")

        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")

        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")

        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")

        special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
        if not any(c in special_chars for c in v):
            raise ValueError("Password must contain at least one special character")

        # Check for common weak passwords
        weak_passwords = [
            "Password123!", "Admin123!", "Welcome123!",
            "Qwerty123!", "P@ssw0rd123"
        ]
        if v in weak_passwords:
            raise ValueError("Password is too common, please choose a stronger password")

        return v

    class Config:
        json_schema_extra = {
            "example": {
                "username": "jane.smith",
                "email": "jane.smith@hospital.com",
                "full_name": "Dr. Jane Smith",
                "password": "SecureP@ssw0rd2025!",
                "role": "radiologist",
            }
        }


class UserUpdate(BaseModel):
    """
    User update request (ISO 27001 A.9.2.5).

    All fields optional for partial updates.
    """
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(None, min_length=1, max_length=100)
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None

    class Config:
        json_schema_extra = {
            "example": {
                "full_name": "Dr. Jane Smith-Jones",
                "is_active": False,
            }
        }


class PasswordChange(BaseModel):
    """
    Password change request (ISO 27001 A.9.4.3).

    Requires current password for verification.
    """
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=12, max_length=128)

    @field_validator('new_password')
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        """Validate new password meets policy requirements."""
        # Reuse validation from UserCreate
        return UserCreate.validate_password_strength(v)


class PasswordReset(BaseModel):
    """
    Password reset request (ISO 27001 A.9.4.3).

    Used with password reset token.
    """
    token: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=12, max_length=128)

    @field_validator('new_password')
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        """Validate new password meets policy requirements."""
        return UserCreate.validate_password_strength(v)


class Token(BaseModel):
    """
    JWT access token response (ISO 27001 A.9.4.2).

    Attributes:
        access_token: JWT access token
        token_type: Always "bearer"
        expires_in: Token expiration time in seconds
    """
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Token expiration time in seconds")

    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 3600,
            }
        }


class TokenData(BaseModel):
    """
    JWT token payload data (ISO 27001 A.9.2.4).

    Attributes:
        user_id: User identifier
        username: Username
        role: User role
        permissions: List of permissions
        exp: Token expiration timestamp
        iat: Token issued at timestamp
        jti: JWT ID (for revocation)
    """
    user_id: str
    username: str
    role: UserRole
    permissions: List[Permission]
    exp: datetime
    iat: datetime
    jti: str  # JWT ID for token revocation

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                "username": "john.doe",
                "role": "radiologist",
                "permissions": ["image:view", "image:export"],
                "exp": "2025-11-22T11:00:00Z",
                "iat": "2025-11-22T10:00:00Z",
                "jti": "abc123",
            }
        }


class LoginRequest(BaseModel):
    """
    Login request (ISO 27001 A.9.4.2).

    Attributes:
        username: Username or email
        password: User password
    """
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)

    class Config:
        json_schema_extra = {
            "example": {
                "username": "john.doe",
                "password": "SecureP@ssw0rd2025!",
            }
        }


class LoginResponse(BaseModel):
    """
    Login response (ISO 27001 A.9.4.2).

    Attributes:
        user: User information
        token: Access token
    """
    user: User
    token: Token

    class Config:
        json_schema_extra = {
            "example": {
                "user": {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "username": "john.doe",
                    "email": "john.doe@hospital.com",
                    "full_name": "Dr. John Doe",
                    "role": "radiologist",
                },
                "token": {
                    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    "token_type": "bearer",
                    "expires_in": 3600,
                },
            }
        }


class AuditLog(BaseModel):
    """
    Security audit log entry (ISO 27001 A.12.4.1).

    Attributes:
        id: Unique audit log ID
        timestamp: Event timestamp
        user_id: User who performed the action
        username: Username who performed the action
        action: Action performed
        resource: Resource accessed
        result: Success or failure
        ip_address: Client IP address
        user_agent: Client user agent
        details: Additional details (JSON)
    """
    id: str
    timestamp: datetime
    user_id: Optional[str]
    username: Optional[str]
    action: str
    resource: str
    result: str  # "success" | "failure"
    ip_address: Optional[str]
    user_agent: Optional[str]
    details: Optional[dict] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "log_550e8400-e29b-41d4-a716-446655440000",
                "timestamp": "2025-11-22T10:30:00Z",
                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                "username": "john.doe",
                "action": "login",
                "resource": "/api/v1/auth/login",
                "result": "success",
                "ip_address": "192.168.1.100",
                "user_agent": "Mozilla/5.0...",
                "details": {"mfa_used": True},
            }
        }
