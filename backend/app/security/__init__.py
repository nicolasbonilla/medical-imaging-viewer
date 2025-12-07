"""
Security module for ISO 27001 compliance.

Implements authentication, authorization, and cryptographic controls
according to ISO/IEC 27001:2022 Annex A requirements.

ISO Controls Implemented:
- A.9.1.1: Access control policy
- A.9.2.1: User registration and de-registration
- A.9.2.3: Management of privileged access rights
- A.9.2.4: Management of secret authentication information
- A.9.4.2: Secure log-on procedures
- A.9.4.3: Password management system
- A.10.1.1: Policy on the use of cryptographic controls
- A.10.1.2: Key management

@module security
"""

from .auth import (
    AuthService,
    TokenManager,
    PasswordManager,
    get_current_user,
    get_current_active_user,
    require_role,
    require_permission,
)

from .rbac import (
    RBACManager,
    check_permission,
    get_user_permissions,
)

from .crypto import (
    CryptoService,
    KeyManager,
    EncryptionConfig,
)

from .models import (
    User,
    UserCreate,
    UserUpdate,
    UserRole,
    Permission,
    Token,
    TokenData,
    PasswordPolicy,
    PasswordChange,
    PasswordReset,
    LoginRequest,
    LoginResponse,
    AuditLog,
)

__all__ = [
    # Authentication
    "AuthService",
    "TokenManager",
    "PasswordManager",
    "get_current_user",
    "get_current_active_user",
    "require_role",
    "require_permission",

    # Authorization
    "RBACManager",
    "check_permission",
    "get_user_permissions",

    # Cryptography
    "CryptoService",
    "KeyManager",
    "EncryptionConfig",

    # Models
    "User",
    "UserCreate",
    "UserUpdate",
    "UserRole",
    "Permission",
    "Token",
    "TokenData",
    "PasswordPolicy",
    "PasswordChange",
    "PasswordReset",
    "LoginRequest",
    "LoginResponse",
    "AuditLog",
]
