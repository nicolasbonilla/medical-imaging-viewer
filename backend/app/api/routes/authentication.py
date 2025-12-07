"""
Authentication API Endpoints.

Implements ISO 27001 A.9.4.2 (Secure log-on procedures),
A.9.2.1 (User registration), and A.12.4.1 (Event logging).

Provides registration, login, and CAPTCHA endpoints with
comprehensive security controls.

@module api.routes.authentication
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, status, Request, Depends
from pydantic import BaseModel, EmailStr, Field

from app.core.logging import get_logger
from app.security.auth import AuthService
from app.security.password import PasswordManager
from app.security.jwt_manager import get_token_manager, TokenManager
from app.security.captcha import get_captcha_manager, CAPTCHAManager, CAPTCHADifficulty
from app.security.user_storage import get_user_storage, SecureUserStorage
from app.security.models import (
    User,
    UserCreate,
    UserRole,
    LoginRequest,
    LoginResponse,
    Token,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])


# Request/Response Models
class RegisterRequest(BaseModel):
    """User registration request."""
    username: str = Field(..., min_length=3, max_length=50, pattern="^[a-zA-Z0-9_-]+$")
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=12, max_length=128)
    confirm_password: str = Field(..., min_length=12, max_length=128)

    class Config:
        json_schema_extra = {
            "example": {
                "username": "dr_john_doe",
                "email": "john.doe@hospital.com",
                "full_name": "Dr. John Doe",
                "password": "SecureP@ssw0rd2025!",
                "confirm_password": "SecureP@ssw0rd2025!"
            }
        }


class RegisterResponse(BaseModel):
    """User registration response."""
    user: User
    message: str


class LoginRequestWithCaptcha(BaseModel):
    """Login request with optional CAPTCHA."""
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=1, max_length=128)
    captcha_challenge_id: Optional[str] = None
    captcha_response: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "username": "dr_john_doe",
                "password": "SecureP@ssw0rd2025!",
                "captcha_challenge_id": "abc123...",
                "captcha_response": "123456"
            }
        }


class CAPTCHARequest(BaseModel):
    """CAPTCHA generation request."""
    difficulty: CAPTCHADifficulty = CAPTCHADifficulty.MEDIUM


class CAPTCHAResponse(BaseModel):
    """CAPTCHA generation response."""
    challenge_id: str
    challenge_text: str
    expires_in_seconds: int = 300  # 5 minutes
    message: str = "Enter the numbers shown"


class LoginAttemptTracker:
    """Track failed login attempts to trigger CAPTCHA."""

    def __init__(self):
        # In production, use Redis
        self._attempts: dict[str, int] = {}

    def record_failed_attempt(self, identifier: str) -> int:
        """Record failed login attempt. Returns total attempts."""
        if identifier not in self._attempts:
            self._attempts[identifier] = 0
        self._attempts[identifier] += 1
        return self._attempts[identifier]

    def get_attempts(self, identifier: str) -> int:
        """Get failed attempts count."""
        return self._attempts.get(identifier, 0)

    def reset_attempts(self, identifier: str) -> None:
        """Reset attempts counter."""
        if identifier in self._attempts:
            del self._attempts[identifier]

    def requires_captcha(self, identifier: str, threshold: int = 2) -> bool:
        """Check if CAPTCHA is required (after threshold failed attempts)."""
        return self.get_attempts(identifier) >= threshold


# Global attempt tracker (replace with Redis in production)
attempt_tracker = LoginAttemptTracker()


def get_client_ip(request: Request) -> str:
    """Get client IP address from request."""
    # Check X-Forwarded-For header first (for proxies)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    # Check X-Real-IP header
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fall back to direct client host
    return request.client.host if request.client else "unknown"


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new user",
    description="Register a new user account with password policy validation (ISO 27001 A.9.2.1)"
)
async def register_user(
    request: RegisterRequest,
    http_request: Request,
    user_storage: SecureUserStorage = Depends(get_user_storage),
) -> RegisterResponse:
    """
    Register a new user account.

    ISO 27001 Controls:
    - A.9.2.1: User registration and de-registration
    - A.9.4.3: Password management system
    - A.12.4.1: Event logging

    Security Features:
    - Password policy validation (12+ chars, complexity)
    - Username/email uniqueness check
    - Argon2id password hashing
    - Encrypted storage (AES-256-GCM)
    - Audit logging

    Args:
        request: Registration request data
        http_request: HTTP request context
        user_storage: User storage service

    Returns:
        RegisterResponse with created user

    Raises:
        HTTPException: If validation fails or user exists
    """
    ip_address = get_client_ip(http_request)

    logger.info(
        "Registration attempt",
        extra={
            "username": request.username,
            "email": request.email,
            "ip_address": ip_address,
        }
    )

    # Validate password confirmation
    if request.password != request.confirm_password:
        logger.warning(
            "Registration failed: password mismatch",
            extra={"username": request.username, "ip_address": ip_address}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match"
        )

    # Check if username exists
    if user_storage.username_exists(request.username):
        logger.warning(
            "Registration failed: username exists",
            extra={"username": request.username, "ip_address": ip_address}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )

    # Check if email exists
    if user_storage.email_exists(request.email):
        logger.warning(
            "Registration failed: email exists",
            extra={"email": request.email, "ip_address": ip_address}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already exists"
        )

    # Create password manager and validate policy
    password_manager = PasswordManager()
    is_valid, errors = password_manager.validate_password_policy(request.password)

    if not is_valid:
        logger.warning(
            "Registration failed: password policy violation",
            extra={
                "username": request.username,
                "errors": errors,
                "ip_address": ip_address,
            }
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password policy violation: {', '.join(errors)}"
        )

    # Create user object
    import uuid
    from datetime import datetime

    user_id = str(uuid.uuid4())
    now = datetime.utcnow()

    user = User(
        id=user_id,
        username=request.username,
        email=request.email,
        full_name=request.full_name,
        role=UserRole.VIEWER,  # Default role (least privilege)
        is_active=True,
        is_locked=False,
        email_verified=False,  # Requires email verification
        created_at=now,
        updated_at=now,
        last_password_change=now,
        failed_login_attempts=0,
    )

    # Hash password
    password_hash = password_manager.hash_password(request.password)

    # Save user with encrypted storage
    user_storage.save_user(user, password_hash, password_history=[password_hash])

    logger.info(
        "User registered successfully",
        extra={
            "user_id": user.id,
            "username": user.username,
            "role": user.role.value,
            "ip_address": ip_address,
            "iso27001_control": "A.9.2.1",
        }
    )

    return RegisterResponse(
        user=user,
        message="User registered successfully. Please verify your email to activate your account."
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="User login",
    description="Authenticate user with optional CAPTCHA after failed attempts (ISO 27001 A.9.4.2)"
)
async def login_user(
    request: LoginRequestWithCaptcha,
    http_request: Request,
    user_storage: SecureUserStorage = Depends(get_user_storage),
    token_manager: TokenManager = Depends(get_token_manager),
    captcha_manager: CAPTCHAManager = Depends(get_captcha_manager),
) -> LoginResponse:
    """
    Authenticate user and issue JWT token.

    ISO 27001 Controls:
    - A.9.4.2: Secure log-on procedures
    - A.9.4.4: Use of privileged utility programs (CAPTCHA)
    - A.12.4.1: Event logging

    Security Features:
    - Account lockout after failed attempts
    - CAPTCHA required after 2 failed attempts
    - Argon2id password verification
    - JWT token generation with expiry
    - Failed login tracking
    - IP-based logging

    Args:
        request: Login request with credentials
        http_request: HTTP request context
        user_storage: User storage service
        token_manager: JWT token manager
        captcha_manager: CAPTCHA manager

    Returns:
        LoginResponse with user and access token

    Raises:
        HTTPException: If authentication fails
    """
    ip_address = get_client_ip(http_request)
    user_agent = http_request.headers.get("User-Agent", "unknown")

    logger.info(
        "Login attempt",
        extra={
            "username": request.username,
            "ip_address": ip_address,
            "user_agent": user_agent,
        }
    )

    # Check if CAPTCHA is required
    if attempt_tracker.requires_captcha(request.username):
        if not request.captcha_challenge_id or not request.captcha_response:
            logger.warning(
                "Login failed: CAPTCHA required",
                extra={"username": request.username, "ip_address": ip_address}
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CAPTCHA verification required after multiple failed attempts",
                headers={"X-CAPTCHA-Required": "true"}
            )

        # Validate CAPTCHA
        captcha_valid = captcha_manager.validate_captcha(
            request.captcha_challenge_id,
            request.captcha_response,
            ip_address
        )

        if not captcha_valid:
            logger.warning(
                "Login failed: invalid CAPTCHA",
                extra={"username": request.username, "ip_address": ip_address}
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid CAPTCHA. Please try again."
            )

    # Get user by username or email
    user = user_storage.get_user_by_username(request.username)
    if not user:
        user = user_storage.get_user_by_email(request.username)

    if not user:
        # Record failed attempt
        attempts = attempt_tracker.record_failed_attempt(request.username)
        logger.warning(
            "Login failed: user not found",
            extra={
                "username": request.username,
                "ip_address": ip_address,
                "failed_attempts": attempts,
            }
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if account is locked
    from datetime import datetime
    if user.is_locked:
        if user.locked_until and datetime.utcnow() < user.locked_until:
            logger.warning(
                "Login failed: account locked",
                extra={
                    "user_id": user.id,
                    "username": user.username,
                    "locked_until": user.locked_until.isoformat(),
                    "ip_address": ip_address,
                }
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Account is locked until {user.locked_until.isoformat()}"
            )
        else:
            # Unlock if lockout period expired
            user.is_locked = False
            user.locked_until = None
            user.failed_login_attempts = 0

    # Check if account is active
    if not user.is_active:
        logger.warning(
            "Login failed: account inactive",
            extra={"user_id": user.id, "username": user.username, "ip_address": ip_address}
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )

    # Verify password
    password_manager = PasswordManager()
    password_data = user_storage.get_user_password_data(user.id)

    if not password_data or not password_manager.verify_password(
        request.password,
        password_data['password_hash']
    ):
        # Increment failed attempts
        user.failed_login_attempts += 1
        attempts = attempt_tracker.record_failed_attempt(request.username)

        # Lock account if threshold exceeded (5 attempts)
        if user.failed_login_attempts >= 5:
            from datetime import timedelta
            user.is_locked = True
            user.locked_until = datetime.utcnow() + timedelta(minutes=30)

            logger.warning(
                "Account locked due to excessive failed logins",
                extra={
                    "user_id": user.id,
                    "username": user.username,
                    "failed_attempts": user.failed_login_attempts,
                    "locked_until": user.locked_until.isoformat(),
                    "ip_address": ip_address,
                }
            )

        # Save updated user
        user_storage.save_user(user, password_data['password_hash'], password_data.get('password_history'))

        logger.warning(
            "Login failed: invalid password",
            extra={
                "user_id": user.id,
                "username": user.username,
                "failed_attempts": user.failed_login_attempts,
                "tracker_attempts": attempts,
                "ip_address": ip_address,
            }
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Successful login - reset failed attempts
    user.failed_login_attempts = 0
    user.last_login = datetime.utcnow()
    attempt_tracker.reset_attempts(request.username)

    # Save updated user
    user_storage.save_user(user, password_data['password_hash'], password_data.get('password_history'))

    # Create access token
    token = token_manager.create_access_token(
        user_id=user.id,
        username=user.username,
        role=user.role
    )

    logger.info(
        "Login successful",
        extra={
            "user_id": user.id,
            "username": user.username,
            "role": user.role.value,
            "ip_address": ip_address,
            "iso27001_control": "A.9.4.2",
        }
    )

    return LoginResponse(user=user, token=token)


@router.post(
    "/captcha",
    response_model=CAPTCHAResponse,
    summary="Generate CAPTCHA",
    description="Generate numeric CAPTCHA challenge for enhanced security (ISO 27001 A.9.4.4)"
)
async def generate_captcha(
    request: CAPTCHARequest,
    http_request: Request,
    captcha_manager: CAPTCHAManager = Depends(get_captcha_manager),
) -> CAPTCHAResponse:
    """
    Generate CAPTCHA challenge.

    ISO 27001 Controls:
    - A.9.4.4: Use of privileged utility programs
    - A.14.2.5: Secure system engineering principles
    - A.12.2.1: Protection from malware (bot prevention)

    Args:
        request: CAPTCHA generation request
        http_request: HTTP request context
        captcha_manager: CAPTCHA manager

    Returns:
        CAPTCHA challenge

    Raises:
        HTTPException: If rate limit exceeded
    """
    ip_address = get_client_ip(http_request)

    try:
        challenge_id, challenge_text = captcha_manager.generate_captcha(
            ip_address=ip_address,
            difficulty=request.difficulty
        )

        logger.info(
            "CAPTCHA generated",
            extra={
                "challenge_id": challenge_id,
                "difficulty": request.difficulty.value,
                "ip_address": ip_address,
            }
        )

        return CAPTCHAResponse(
            challenge_id=challenge_id,
            challenge_text=challenge_text,
            expires_in_seconds=300,
            message="Enter the numbers shown"
        )

    except Exception as e:
        logger.error(
            "CAPTCHA generation failed",
            extra={"error": str(e), "ip_address": ip_address},
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e)
        )


@router.get(
    "/me",
    response_model=User,
    summary="Get current user",
    description="Get current authenticated user information"
)
async def get_current_user_info(
    token: str,
    token_manager: TokenManager = Depends(get_token_manager),
    user_storage: SecureUserStorage = Depends(get_user_storage),
) -> User:
    """Get current authenticated user."""
    try:
        token_data = token_manager.decode_token_data(token)
        user = user_storage.get_user_by_id(token_data.user_id)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        return user

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
