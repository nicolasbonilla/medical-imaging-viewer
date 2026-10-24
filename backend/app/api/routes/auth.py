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
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.concurrency import run_in_threadpool

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
from app.core.logging.audit import emit_audit, AuditEventType, AuditOutcome, AuditSeverity
from app.security.refresh_tokens import (
    REFRESH_COOKIE_NAME,
    RefreshTokenStore,
    clear_refresh_cookie,
    get_refresh_token_store,
)

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
optional_bearer = HTTPBearer(auto_error=False)


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

# Token manager: the SAME process-wide instance the authentication dependency uses
# (get_current_user -> get_token_manager). CAPA-015: a second instance here meant that a token
# revoked at logout was revoked in a list nobody checked.
from app.security.jwt_manager import get_token_manager
token_manager = get_token_manager()

# Initialize authentication service
auth_service = AuthService(
    password_manager=password_manager,
    token_manager=token_manager,
    password_policy=password_policy,
)




# Helper functions
def _get_client_ip(request: Request) -> str:
    """Client IP: the right-most untrusted X-Forwarded-For hop (CAPA-015 review m9)."""
    from app.core.client_ip import client_ip
    return client_ip(request) or "unknown"


def _get_user_agent(request: Request) -> str:
    """Extract user agent from request."""
    return request.headers.get("User-Agent", "unknown")


# ============================================================================
# NOTE: POST /register, POST /login, and GET /me are defined in
# authentication.py (registered first in main.py). Duplicate endpoints
# have been removed from this file to avoid route collisions.
# ============================================================================

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
    response: Response,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_bearer),
    refresh_store: RefreshTokenStore = Depends(get_refresh_token_store),
) -> None:
    """
    Logout: revoke the access token (if presented and valid), revoke the refresh-token family of
    the session cookie, and clear the cookie (CAPA-015, RC-068).

    The access token is optional so that a user whose access token has already expired can still
    end the session held by the refresh cookie (the cookie is SameSite=Strict: a cross-site page
    cannot send it). Always 204 — logging out twice is not an error.

    Example:
        POST /api/v1/auth/logout
        Authorization: Bearer <token>   (optional)
        Cookie: __session=<refresh token>
    """
    actor = None
    if credentials is not None:
        try:
            actor = token_manager.decode_token_data(credentials.credentials)
            auth_service.logout(credentials.credentials)
        except Exception:  # expired or invalid access token: the cookie may still end the session
            actor = None
    family = owner = None
    store_error = False
    cookie = request.cookies.get(REFRESH_COOKIE_NAME)
    if cookie:
        try:   # store calls off the event loop (review m8)
            owner, family = await run_in_threadpool(refresh_store.peek_owner, cookie)
            if family:
                await run_in_threadpool(refresh_store.revoke_family, family, "logout")
        except Exception as e:  # noqa: BLE001
            store_error = True
            logger.error("REFRESH_STORE_UNAVAILABLE logout could not revoke the session",
                         extra={"error_type": type(e).__name__})
    clear_refresh_cookie(response)
    # Exactly one audit record per logout (review M3: an unknown cookie without a bearer left none).
    user_id = getattr(actor, "user_id", None) or owner
    if actor is not None or owner:
        outcome, reason = AuditOutcome.SUCCESS, (None if actor else "refresh_cookie")
        if store_error:
            outcome, reason = AuditOutcome.PARTIAL, "session_not_revoked"
    else:
        outcome = AuditOutcome.FAILURE
        reason = "store_unavailable" if store_error else ("unknown_session" if cookie else "no_session")
    emit_audit(AuditEventType.AUTH_LOGOUT, outcome, request=request, user_id=user_id,
               username=getattr(actor, "username", None), role=getattr(actor, "role", None), reason=reason)
    logger.info("Logout", extra={"user_id": user_id, "session_revoked": bool(family)})



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
    response: Response,
    current_user: User = Depends(get_current_active_user),
    refresh_store: RefreshTokenStore = Depends(get_refresh_token_store),
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

        # CAPA-015 (RC-068): a new password ends every session of the user, everywhere.
        revoked = 0
        try:
            revoked = await run_in_threadpool(refresh_store.revoke_all_for_user, current_user.id, "password_change")
        except Exception as e:  # noqa: BLE001 — logged and audited; the change itself stands
            logger.error("REFRESH_STORE_UNAVAILABLE sessions not revoked after a password change",
                         extra={"error_type": type(e).__name__, "user_id": current_user.id})
        clear_refresh_cookie(response)
        emit_audit(AuditEventType.AUTH_TOKEN_REVOKED, AuditOutcome.SUCCESS, request=request,
                   user_id=current_user.id, username=current_user.username, role=current_user.role,
                   reason="password_change", details={"revoked_sessions": revoked},
                   severity=AuditSeverity.MEDIUM)

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
    summary="Get audit logs",
    description="""
    Read the durable audit trail (Firestore `audit_logs`), newest first — administrators only.

    ISO 27001: A.12.4.1 (Event logging). CAPA-015 (RC-067, REQ-SEC-024): was an in-memory list
    lost on every restart, readable by radiologists.

    Pagination: pass `next_page_token` from the previous page as `page_token`.
    Filters: `user_id` (actor), `event_type`, `outcome`. Reading the trail is itself recorded.
    The response also carries `sink_status` (is audit writing working on this instance).
    """,
    responses={
        200: {"description": "A page of audit records"},
        400: {"description": "Invalid page token"},
        401: {"description": "Invalid or expired token"},
        403: {"description": "Administrators only"},
        503: {"description": "The durable audit trail is unavailable or not configured"},
    },
)
async def get_audit_logs(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    page_token: Optional[str] = Query(None, max_length=64),
    user_id: Optional[str] = Query(None, max_length=128),
    event_type: Optional[str] = Query(None, max_length=64),
    outcome: Optional[str] = Query(None, max_length=16),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """Read a page of the durable audit trail (CAPA-015, RC-067)."""
    from starlette.concurrency import run_in_threadpool
    from app.core.logging.audit_sink import get_durable_audit_sink, query_audit_records

    sink = get_durable_audit_sink()
    sink_status = sink.status()
    if sink.backend != "firestore":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"The audit trail is not stored durably on this server (backend: {sink.backend}).",
        )
    try:
        client = await run_in_threadpool(sink.client)
        items, next_token = await run_in_threadpool(
            query_audit_records, client, limit=limit, page_token=page_token,
            actor_user_id=user_id, event_type=event_type, outcome=outcome,
        )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid page token")
    except Exception as e:  # noqa: BLE001
        logger.error("Audit trail could not be read", extra={"error_type": type(e).__name__}, exc_info=True)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="The audit trail could not be read. Try again later.")

    emit_audit(AuditEventType.AUDIT_LOG_READ, AuditOutcome.SUCCESS, request=request,
               user_id=current_user.id, username=current_user.username, role=current_user.role,
               resource_ids={"target_user_id": user_id} if user_id else None,
               severity=AuditSeverity.MEDIUM)
    return {"items": items, "next_page_token": next_token, "sink_status": sink_status}


@router.get(
    "/audit-status",
    summary="Audit trail writing status",
    description="Whether this server instance is writing the audit trail durably (state ok / degraded / "
                "failing / not_durable / off), queue depth, failures. Administrators only (CAPA-015, RC-067).",
)
async def get_audit_status(current_user: User = Depends(require_role(UserRole.ADMIN))):
    from app.core.logging.audit_sink import get_durable_audit_sink
    return get_durable_audit_sink().status()


# =============================================================================
# WebAuthn / Passkeys Endpoints
# =============================================================================

def _get_webauthn_service():
    """Lazy-initialize WebAuthn service."""
    if not hasattr(_get_webauthn_service, '_instance'):
        from app.security.webauthn_service import WebAuthnService
        from app.core.config import Settings
        from app.core.firebase import get_firestore_client
        s = Settings()
        try:
            db = get_firestore_client()
        except Exception:
            db = None
        _get_webauthn_service._instance = WebAuthnService(
            rp_id=s.WEBAUTHN_RP_ID,
            rp_name=s.WEBAUTHN_RP_NAME,
            origin=s.WEBAUTHN_ORIGIN,
            db=db,
        )
    return _get_webauthn_service._instance


@router.post("/webauthn/register/begin")
async def webauthn_register_begin(
    request: Request,
    current_user=Depends(get_current_active_user),
):
    """Begin WebAuthn credential registration (requires authentication)."""
    try:
        wa = _get_webauthn_service()
        options = wa.generate_registration(
            user_id=current_user.id,
            username=current_user.username,
            display_name=current_user.full_name,
        )
        return {"options": options}
    except Exception as e:
        logger.error("WebAuthn register begin failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webauthn/register/complete")
async def webauthn_register_complete(
    request: Request,
    current_user=Depends(get_current_active_user),
):
    """Complete WebAuthn credential registration."""
    try:
        body = await request.json()
        wa = _get_webauthn_service()
        credential = wa.verify_registration(
            user_id=current_user.id,
            credential_json=body.get('credential', {}),
            device_name=body.get('device_name', ''),
        )
        return credential
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("WebAuthn register complete failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webauthn/login/begin")
async def webauthn_login_begin(request: Request):
    """Begin WebAuthn authentication (public, no auth required)."""
    try:
        body = await request.json()
        username = body.get('username', '')
        if not username:
            raise HTTPException(status_code=400, detail="Username is required")

        # Find user
        user = auth_service._find_user_by_username_or_email(username)
        if not user:
            raise HTTPException(status_code=400, detail="Invalid credentials")

        wa = _get_webauthn_service()
        options = wa.generate_authentication(user_id=user.id)
        return {"options": options}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("WebAuthn login begin failed", extra={"error": str(e)})
        raise HTTPException(status_code=400, detail="Invalid credentials")


@router.post("/webauthn/login/complete")
async def webauthn_login_complete(
    request: Request,
    response: Response,
    refresh_store: RefreshTokenStore = Depends(get_refresh_token_store),
):
    """Complete WebAuthn authentication and issue JWT token (and, CAPA-015, a refresh session)."""
    from app.api.routes.authentication import start_session

    def audit_failure(reason, user=None, username=None):
        emit_audit(AuditEventType.AUTH_LOGIN_FAILED, AuditOutcome.FAILURE, request=request,
                   user_id=getattr(user, "id", None), username=getattr(user, "username", None),
                   role=getattr(user, "role", None), reason=reason,
                   attempted_identifier=username if user is None else None)

    user = None
    username = ""
    try:
        body = await request.json()
        username = body.get('username', '')
        credential = body.get('credential', {})

        user = auth_service._find_user_by_username_or_email(username)
        if not user:
            audit_failure("passkey_user_not_found", username=username)
            raise HTTPException(status_code=401, detail="Invalid credentials")

        if not user.is_active:
            audit_failure("account_inactive", user)
            raise HTTPException(status_code=403, detail="Account is disabled")
        if user.is_locked:
            audit_failure("account_locked", user)
            raise HTTPException(status_code=403, detail="Account is locked")

        wa = _get_webauthn_service()
        wa.verify_authentication(user_id=user.id, credential_json=credential)

        # Issue JWT (same as password login)
        from app.security.models import UserRole
        token_obj = token_manager.create_access_token(
            user_id=user.id,
            username=user.username,
            role=UserRole(user.role) if isinstance(user.role, str) else user.role,
        )

        # Update last login
        from datetime import datetime as dt
        user.last_login = dt.utcnow()
        user.failed_login_attempts = 0
        try:
            pwd_data = auth_service._storage.get_user_password_data(user.id)
            pwd_hash = pwd_data.get('password_hash', '') if pwd_data else ''
            auth_service._storage.save_user(user, pwd_hash)
        except Exception as e:
            logger.warning("Could not update last_login after WebAuthn", extra={"error": str(e)})

        logger.info("WebAuthn login successful", extra={
            "user_id": user.id,
            "username": user.username,
            "ip": _get_client_ip(request),
        })
        refresh_expires_in = await run_in_threadpool(start_session, response, user, refresh_store)   # CAPA-015 RC-068
        emit_audit(AuditEventType.AUTH_LOGIN_SUCCESS, AuditOutcome.SUCCESS, request=request,
                   user_id=user.id, username=user.username, role=user.role, reason="passkey")

        return {
            "token": {
                "access_token": token_obj.access_token,
                "token_type": "bearer",
                "expires_in": token_obj.expires_in,
                "refresh_expires_in": refresh_expires_in,
            },
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "is_active": user.is_active,
                "is_locked": user.is_locked,
                "failed_login_attempts": user.failed_login_attempts,
                "last_login": user.last_login.isoformat() if user.last_login else None,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "updated_at": user.updated_at.isoformat() if user.updated_at else None,
            },
        }
    except HTTPException:
        raise
    except ValueError as e:
        audit_failure("passkey_invalid", user, username)
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error("WebAuthn login complete failed", extra={"error": str(e)})
        audit_failure("passkey_error", user, username)
        raise HTTPException(status_code=401, detail="Authentication failed")


@router.get("/webauthn/credentials")
async def webauthn_list_credentials(current_user=Depends(get_current_active_user)):
    """List registered WebAuthn credentials for the current user."""
    wa = _get_webauthn_service()
    creds = wa.get_credentials(current_user.id)
    # Strip private key data before returning
    return [
        {
            "credential_id": c.get('credential_id', ''),
            "device_name": c.get('device_name', ''),
            "created_at": c.get('created_at', ''),
            "last_used": c.get('last_used'),
        }
        for c in creds
    ]


@router.delete("/webauthn/credentials/{credential_id}")
async def webauthn_delete_credential(
    credential_id: str,
    current_user=Depends(get_current_active_user),
):
    """Delete a WebAuthn credential."""
    wa = _get_webauthn_service()
    creds = wa.get_credentials(current_user.id)
    if len(creds) <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the last passkey")
    if not wa.delete_credential(current_user.id, credential_id):
        raise HTTPException(status_code=404, detail="Credential not found")
    return {"status": "deleted"}
