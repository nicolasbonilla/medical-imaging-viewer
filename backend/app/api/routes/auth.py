"""
Authentication routes for user management.

Implements ISO 27001 A.9.4.2 (Secure log-on procedures) and
A.9.2.1 (User registration and de-registration).

This module provides REST API endpoints for:
- User registration
- User login/logout
- Password management
- Token management
- User profile operations

All endpoints include audit logging per ISO 27001 A.12.4.1.

@module api.routes.auth
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.security import (
    AuthService,
    TokenManager,
    PasswordManager,
    get_current_user,
    get_current_active_user,
    require_role,
    require_permission,
)
from app.security.models import (
    User,
    UserCreate,
    UserUpdate,
    LoginRequest,
    LoginResponse,
    Token,
    PasswordChange,
    PasswordReset,
    UserRole,
    Permission,
    AuditLog,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

# Router configuration
router = APIRouter(
    prefix="/auth",
    tags=["authentication"],
    responses={
        401: {"description": "Unauthorized"},
        403: {"description": "Forbidden"},
        404: {"description": "Not found"},
    },
)

security = HTTPBearer()


# Initialize services with secure configuration from environment
# ISO 27001 A.9.2.4 (Management of secret authentication information)
from app.security.password import PasswordManager
from app.security.jwt_manager import TokenManager
from app.security.auth import AuthService
from app.security.models import PasswordPolicy
from app.core.config import get_settings

# Load settings from environment
settings = get_settings()

# Initialize password policy from security settings
password_policy = PasswordPolicy(
    min_length=12,  # Will be configurable via environment in future
    require_uppercase=True,
    require_lowercase=True,
    require_digit=True,
    require_special=True,
    max_age_days=90,
    password_history_count=5,
    lockout_threshold=5,
    lockout_duration_minutes=30,
)

# Initialize password manager
password_manager = PasswordManager(policy=password_policy)

# Initialize token manager with secrets from environment
token_manager = TokenManager(
    secret_key=settings.SECRET_KEY,  # Loaded from JWT_SECRET_KEY env var
    algorithm=settings.ALGORITHM,
    access_token_expire_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
)

# Initialize authentication service
auth_service = AuthService(
    password_manager=password_manager,
    token_manager=token_manager,
    password_policy=password_policy,
)


# Helper functions
def _get_client_ip(request: Request) -> str:
    """Extract client IP address from request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _get_user_agent(request: Request) -> str:
    """Extract user agent from request."""
    return request.headers.get("User-Agent", "unknown")


# ============================================================================
# Public Endpoints (No Authentication Required)
# ============================================================================

@router.post(
    "/register",
    response_model=User,
    status_code=status.HTTP_201_CREATED,
    summary="Register new user",
    description="""
    Register a new user account.

    ISO 27001: A.9.2.1 (User registration and de-registration)

    Password Requirements:
    - Minimum 12 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character (!@#$%^&*()_+-=[]{}|;:,.<>?)
    - Cannot be a common weak password

    Default role is VIEWER (least privilege principle).
    """,
    responses={
        201: {"description": "User successfully registered"},
        400: {"description": "Invalid request or password policy violation"},
        409: {"description": "Username or email already exists"},
    },
)
async def register_user(
    user_create: UserCreate,
    request: Request,
) -> User:
    """
    Register a new user account.

    Args:
        user_create: User registration data
        request: FastAPI request object

    Returns:
        Created user object (without password)

    Raises:
        HTTPException: 400 if validation fails, 409 if user exists

    Example:
        POST /api/v1/auth/register
        {
            "username": "john.doe",
            "email": "john.doe@hospital.com",
            "full_name": "Dr. John Doe",
            "password": "SecureP@ssw0rd2025!",
            "role": "viewer"
        }
    """
    try:
        logger.info(
            f"User registration attempt: {user_create.username}",
            extra={
                "username": user_create.username,
                "email": user_create.email,
                "role": user_create.role.value,
                "ip_address": _get_client_ip(request),
            }
        )

        user = auth_service.register_user(
            user_create=user_create,
            created_by=None,  # Self-registration
        )

        logger.info(
            f"User registered successfully: {user.username}",
            extra={"user_id": user.id, "username": user.username}
        )

        return user

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"User registration failed: {str(e)}",
            extra={
                "username": user_create.username,
                "error": str(e),
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User registration failed"
        )


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="User login",
    description="""
    Authenticate user and receive JWT access token.

    ISO 27001: A.9.4.2 (Secure log-on procedures)

    Security Features:
    - Account lockout after 5 failed attempts (30 minutes)
    - Password expiration enforcement (90 days)
    - Audit logging of all login attempts
    - JWT token with 60-minute expiration

    The returned token should be included in subsequent requests:
    Authorization: Bearer <token>
    """,
    responses={
        200: {"description": "Login successful, token returned"},
        401: {"description": "Invalid credentials"},
        403: {"description": "Account locked or password expired"},
    },
)
async def login(
    login_request: LoginRequest,
    request: Request,
) -> LoginResponse:
    """
    Authenticate user and return JWT token.

    Args:
        login_request: Login credentials
        request: FastAPI request object

    Returns:
        LoginResponse with user info and access token

    Raises:
        HTTPException: 401 if credentials invalid, 403 if account locked

    Example:
        POST /api/v1/auth/login
        {
            "username": "john.doe",
            "password": "SecureP@ssw0rd2025!"
        }

        Response:
        {
            "user": {...},
            "token": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 3600
            }
        }
    """
    try:
        ip_address = _get_client_ip(request)
        user_agent = _get_user_agent(request)

        logger.info(
            f"Login attempt: {login_request.username}",
            extra={
                "username": login_request.username,
                "ip_address": ip_address,
                "user_agent": user_agent,
            }
        )

        login_response = auth_service.login(
            login_request=login_request,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        logger.info(
            f"Login successful: {login_response.user.username}",
            extra={
                "user_id": login_response.user.id,
                "username": login_response.user.username,
                "role": login_response.user.role.value,
            }
        )

        return login_response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Login failed: {str(e)}",
            extra={
                "username": login_request.username,
                "error": str(e),
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )


# ============================================================================
# Protected Endpoints (Authentication Required)
# ============================================================================

@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="User logout",
    description="""
    Logout user and revoke access token.

    ISO 27001: A.9.4.2 (Secure log-on procedures)

    The token will be added to a revocation list and will no longer
    be valid for authentication.
    """,
    responses={
        204: {"description": "Logout successful, token revoked"},
        401: {"description": "Invalid or expired token"},
    },
)
async def logout(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """
    Logout user and revoke JWT token.

    Args:
        request: FastAPI request object
        credentials: Bearer token credentials
        current_user: Current authenticated user

    Returns:
        None (204 No Content)

    Example:
        POST /api/v1/auth/logout
        Authorization: Bearer <token>
    """
    try:
        token = credentials.credentials

        logger.info(
            f"Logout: {current_user.username}",
            extra={
                "user_id": current_user.id,
                "username": current_user.username,
                "ip_address": _get_client_ip(request),
            }
        )

        auth_service.logout(token)

        logger.info(
            f"Logout successful: {current_user.username}",
            extra={
                "user_id": current_user.id,
                "username": current_user.username,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Logout failed: {str(e)}",
            extra={
                "user_id": current_user.id,
                "error": str(e),
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed"
        )


@router.get(
    "/me",
    response_model=User,
    summary="Get current user",
    description="""
    Get current authenticated user information.

    ISO 27001: A.9.2.4 (Management of secret authentication information)

    Returns user profile without sensitive information (no password hash).
    """,
    responses={
        200: {"description": "Current user information"},
        401: {"description": "Invalid or expired token"},
    },
)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """
    Get current authenticated user.

    Args:
        current_user: Current authenticated user from token

    Returns:
        Current user object

    Example:
        GET /api/v1/auth/me
        Authorization: Bearer <token>

        Response:
        {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "username": "john.doe",
            "email": "john.doe@hospital.com",
            "full_name": "Dr. John Doe",
            "role": "radiologist",
            "is_active": true,
            ...
        }
    """
    return current_user


@router.patch(
    "/me",
    response_model=User,
    summary="Update current user",
    description="""
    Update current user profile information.

    ISO 27001: A.9.2.5 (Review of user access rights)

    Users can update their own email and full name.
    Role changes require admin privileges.
    """,
    responses={
        200: {"description": "User updated successfully"},
        400: {"description": "Invalid request"},
        401: {"description": "Invalid or expired token"},
        403: {"description": "Insufficient permissions"},
    },
)
async def update_current_user(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_active_user),
) -> User:
    """
    Update current user profile.

    Args:
        user_update: User update data
        current_user: Current authenticated user

    Returns:
        Updated user object

    Raises:
        HTTPException: 400 if validation fails, 403 if trying to change role

    Example:
        PATCH /api/v1/auth/me
        Authorization: Bearer <token>
        {
            "full_name": "Dr. John Smith",
            "email": "john.smith@hospital.com"
        }
    """
    try:
        # Users cannot change their own role
        if user_update.role is not None and user_update.role != current_user.role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot change your own role. Contact administrator."
            )

        logger.info(
            f"User update: {current_user.username}",
            extra={
                "user_id": current_user.id,
                "username": current_user.username,
                "update_fields": user_update.model_dump(exclude_none=True),
            }
        )

        updated_user = auth_service.update_user(
            user_id=current_user.id,
            user_update=user_update,
            updated_by=current_user.id,
        )

        logger.info(
            f"User updated successfully: {current_user.username}",
            extra={
                "user_id": current_user.id,
                "username": current_user.username,
            }
        )

        return updated_user

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"User update failed: {str(e)}",
            extra={
                "user_id": current_user.id,
                "error": str(e),
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User update failed"
        )


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change password",
    description="""
    Change current user password.

    ISO 27001: A.9.4.3 (Password management system)

    Security Requirements:
    - Must provide current password
    - New password must meet policy requirements
    - Cannot reuse last 5 passwords
    - Password history is maintained
    """,
    responses={
        204: {"description": "Password changed successfully"},
        400: {"description": "Password policy violation or in history"},
        401: {"description": "Current password incorrect"},
    },
)
async def change_password(
    password_change: PasswordChange,
    request: Request,
    current_user: User = Depends(get_current_active_user),
) -> None:
    """
    Change current user password.

    Args:
        password_change: Current and new password
        request: FastAPI request object
        current_user: Current authenticated user

    Returns:
        None (204 No Content)

    Raises:
        HTTPException: 400 if policy violation, 401 if current password wrong

    Example:
        POST /api/v1/auth/change-password
        Authorization: Bearer <token>
        {
            "current_password": "OldPassword123!",
            "new_password": "NewSecureP@ssw0rd2025!"
        }
    """
    try:
        logger.info(
            f"Password change request: {current_user.username}",
            extra={
                "user_id": current_user.id,
                "username": current_user.username,
                "ip_address": _get_client_ip(request),
            }
        )

        auth_service.change_password(
            user_id=current_user.id,
            password_change=password_change,
        )

        logger.info(
            f"Password changed successfully: {current_user.username}",
            extra={
                "user_id": current_user.id,
                "username": current_user.username,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Password change failed: {str(e)}",
            extra={
                "user_id": current_user.id,
                "error": str(e),
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password change failed"
        )


# ============================================================================
# Admin Endpoints (Admin Role Required)
# ============================================================================

@router.get(
    "/users",
    response_model=List[User],
    summary="List all users",
    description="""
    Get list of all users (admin only).

    ISO 27001: A.9.2.5 (Review of user access rights)

    Requires ADMIN role or USER_VIEW permission.
    """,
    responses={
        200: {"description": "List of users"},
        401: {"description": "Invalid or expired token"},
        403: {"description": "Insufficient permissions (admin required)"},
    },
)
async def list_users(
    current_user: User = Depends(require_permission(Permission.USER_VIEW)),
) -> List[User]:
    """
    Get list of all users.

    Args:
        current_user: Current authenticated admin user

    Returns:
        List of all users

    Example:
        GET /api/v1/auth/users
        Authorization: Bearer <admin-token>
    """
    try:
        logger.info(
            f"List users request by: {current_user.username}",
            extra={
                "user_id": current_user.id,
                "username": current_user.username,
                "role": current_user.role.value,
            }
        )

        users = auth_service.list_users()

        return users

    except Exception as e:
        logger.error(
            f"List users failed: {str(e)}",
            extra={
                "user_id": current_user.id,
                "error": str(e),
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve users"
        )


@router.get(
    "/users/{user_id}",
    response_model=User,
    summary="Get user by ID",
    description="""
    Get specific user by ID (admin only).

    ISO 27001: A.9.2.5 (Review of user access rights)

    Requires ADMIN role or USER_VIEW permission.
    """,
    responses={
        200: {"description": "User found"},
        401: {"description": "Invalid or expired token"},
        403: {"description": "Insufficient permissions"},
        404: {"description": "User not found"},
    },
)
async def get_user(
    user_id: str,
    current_user: User = Depends(require_permission(Permission.USER_VIEW)),
) -> User:
    """
    Get user by ID.

    Args:
        user_id: User ID to retrieve
        current_user: Current authenticated admin user

    Returns:
        User object

    Raises:
        HTTPException: 404 if user not found

    Example:
        GET /api/v1/auth/users/550e8400-e29b-41d4-a716-446655440000
        Authorization: Bearer <admin-token>
    """
    try:
        logger.info(
            f"Get user request by {current_user.username} for user_id: {user_id}",
            extra={
                "admin_user_id": current_user.id,
                "target_user_id": user_id,
            }
        )

        user = auth_service.get_user_by_id(user_id)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )

        return user

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Get user failed: {str(e)}",
            extra={
                "user_id": current_user.id,
                "target_user_id": user_id,
                "error": str(e),
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user"
        )


@router.patch(
    "/users/{user_id}",
    response_model=User,
    summary="Update user",
    description="""
    Update user by ID (admin only).

    ISO 27001: A.9.2.5 (Review of user access rights)

    Admins can update any user including role changes.
    Role changes are validated to prevent privilege escalation.
    """,
    responses={
        200: {"description": "User updated"},
        400: {"description": "Invalid request"},
        401: {"description": "Invalid or expired token"},
        403: {"description": "Insufficient permissions"},
        404: {"description": "User not found"},
    },
)
async def update_user(
    user_id: str,
    user_update: UserUpdate,
    current_user: User = Depends(require_permission(Permission.USER_UPDATE)),
) -> User:
    """
    Update user by ID.

    Args:
        user_id: User ID to update
        user_update: Update data
        current_user: Current authenticated admin user

    Returns:
        Updated user object

    Raises:
        HTTPException: 404 if user not found, 400 if validation fails

    Example:
        PATCH /api/v1/auth/users/550e8400-e29b-41d4-a716-446655440000
        Authorization: Bearer <admin-token>
        {
            "role": "radiologist",
            "is_active": true
        }
    """
    try:
        logger.info(
            f"Update user request by {current_user.username} for user_id: {user_id}",
            extra={
                "admin_user_id": current_user.id,
                "target_user_id": user_id,
                "update_fields": user_update.model_dump(exclude_none=True),
            }
        )

        updated_user = auth_service.update_user(
            user_id=user_id,
            user_update=user_update,
            updated_by=current_user.id,
        )

        logger.info(
            f"User updated successfully by {current_user.username}",
            extra={
                "admin_user_id": current_user.id,
                "target_user_id": user_id,
            }
        )

        return updated_user

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Update user failed: {str(e)}",
            extra={
                "admin_user_id": current_user.id,
                "target_user_id": user_id,
                "error": str(e),
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user"
        )


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete user",
    description="""
    Delete user by ID (admin only).

    ISO 27001: A.9.2.1 (User de-registration)

    Users cannot delete themselves.
    All audit logs for the user are preserved.
    """,
    responses={
        204: {"description": "User deleted"},
        401: {"description": "Invalid or expired token"},
        403: {"description": "Insufficient permissions or self-deletion attempt"},
        404: {"description": "User not found"},
    },
)
async def delete_user(
    user_id: str,
    current_user: User = Depends(require_permission(Permission.USER_DELETE)),
) -> None:
    """
    Delete user by ID.

    Args:
        user_id: User ID to delete
        current_user: Current authenticated admin user

    Returns:
        None (204 No Content)

    Raises:
        HTTPException: 403 if self-deletion, 404 if user not found

    Example:
        DELETE /api/v1/auth/users/550e8400-e29b-41d4-a716-446655440000
        Authorization: Bearer <admin-token>
    """
    try:
        # Prevent self-deletion
        if user_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot delete your own account"
            )

        logger.info(
            f"Delete user request by {current_user.username} for user_id: {user_id}",
            extra={
                "admin_user_id": current_user.id,
                "target_user_id": user_id,
            }
        )

        auth_service.delete_user(user_id, deleted_by=current_user.id)

        logger.info(
            f"User deleted successfully by {current_user.username}",
            extra={
                "admin_user_id": current_user.id,
                "target_user_id": user_id,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Delete user failed: {str(e)}",
            extra={
                "admin_user_id": current_user.id,
                "target_user_id": user_id,
                "error": str(e),
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user"
        )


# ============================================================================
# Audit Endpoints (Privileged Users Only)
# ============================================================================

@router.get(
    "/audit-logs",
    response_model=List[AuditLog],
    summary="Get audit logs",
    description="""
    Get security audit logs (admin/radiologist only).

    ISO 27001: A.12.4.1 (Event logging)

    Returns audit trail of authentication and authorization events.
    Supports filtering by user, action, date range.
    """,
    responses={
        200: {"description": "Audit logs"},
        401: {"description": "Invalid or expired token"},
        403: {"description": "Insufficient permissions"},
    },
)
async def get_audit_logs(
    limit: int = 100,
    offset: int = 0,
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    current_user: User = Depends(require_permission(Permission.AUDIT_VIEW)),
) -> List[AuditLog]:
    """
    Get security audit logs.

    Args:
        limit: Maximum number of logs to return
        offset: Offset for pagination
        user_id: Filter by user ID
        action: Filter by action type
        current_user: Current authenticated user with AUDIT_VIEW permission

    Returns:
        List of audit log entries

    Example:
        GET /api/v1/auth/audit-logs?limit=50&user_id=550e8400-e29b-41d4-a716-446655440000
        Authorization: Bearer <token>
    """
    try:
        logger.info(
            f"Audit logs request by {current_user.username}",
            extra={
                "user_id": current_user.id,
                "limit": limit,
                "offset": offset,
                "filter_user_id": user_id,
                "filter_action": action,
            }
        )

        audit_logs = auth_service.get_audit_logs(
            limit=limit,
            offset=offset,
            user_id=user_id,
            action=action,
        )

        return audit_logs

    except Exception as e:
        logger.error(
            f"Get audit logs failed: {str(e)}",
            extra={
                "user_id": current_user.id,
                "error": str(e),
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve audit logs"
        )
