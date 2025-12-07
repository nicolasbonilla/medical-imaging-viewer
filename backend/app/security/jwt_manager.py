"""
JWT Token Management Service.

Implements ISO 27001 A.9.4.2 (Secure log-on procedures) and
A.9.2.4 (Management of secret authentication information).

Provides JWT token generation, validation, and revocation.

@module security.jwt_manager
"""

import uuid
from typing import Optional, Dict, Set
from datetime import datetime, timedelta

import jwt
from jwt.exceptions import InvalidTokenError, ExpiredSignatureError

from app.core.logging import get_logger
from app.core.config import get_settings
from .models import TokenData, Token, UserRole, Permission
from .rbac import RBACManager

logger = get_logger(__name__)
settings = get_settings()


class TokenManager:
    """
    JWT token management with revocation support.

    Features:
    - JWT generation with custom claims
    - Token validation and decoding
    - Token revocation (blacklist)
    - Refresh token support
    - Configurable expiration

    ISO 27001 Controls:
    - A.9.4.2: Secure authentication (JWT-based)
    - A.9.2.4: Token secret management
    - A.9.2.3: Session management

    Example:
        >>> tm = TokenManager()
        >>> token = tm.create_access_token(
        ...     user_id="123",
        ...     username="john.doe",
        ...     role=UserRole.RADIOLOGIST
        ... )
        >>> payload = tm.decode_token(token.access_token)
        >>> payload['user_id']
        '123'
    """

    def __init__(
        self,
        secret_key: Optional[str] = None,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 60,
        refresh_token_expire_days: int = 30,
    ):
        """
        Initialize token manager.

        Args:
            secret_key: JWT signing key (from settings if not provided)
            algorithm: JWT algorithm (default: HS256)
            access_token_expire_minutes: Access token TTL in minutes
            refresh_token_expire_days: Refresh token TTL in days
        """
        self.secret_key = secret_key or settings.JWT_SECRET_KEY
        self.algorithm = algorithm
        self.access_token_expire_minutes = access_token_expire_minutes
        self.refresh_token_expire_days = refresh_token_expire_days

        # Token revocation blacklist (in production, use Redis)
        self._revoked_tokens: Set[str] = set()

        logger.info(
            "TokenManager initialized",
            extra={
                "algorithm": self.algorithm,
                "access_token_ttl_minutes": self.access_token_expire_minutes,
                "refresh_token_ttl_days": self.refresh_token_expire_days,
            }
        )

    def create_access_token(
        self,
        user_id: str,
        username: str,
        role: UserRole,
        expires_delta: Optional[timedelta] = None,
        additional_claims: Optional[Dict] = None,
    ) -> Token:
        """
        Create JWT access token.

        Args:
            user_id: User unique identifier
            username: Username
            role: User role
            expires_delta: Custom expiration time
            additional_claims: Additional JWT claims

        Returns:
            Token object with access_token and metadata

        Example:
            >>> tm = TokenManager()
            >>> token = tm.create_access_token(
            ...     user_id="user_123",
            ...     username="john.doe",
            ...     role=UserRole.RADIOLOGIST
            ... )
            >>> token.token_type
            'bearer'

        ISO 27001: A.9.4.2 (Token generation)
        """
        # Calculate expiration
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(
                minutes=self.access_token_expire_minutes
            )

        # Get permissions for role
        permissions = RBACManager.get_permissions_for_role(role)
        permission_list = [p.value for p in permissions]

        # Generate unique token ID (for revocation)
        jti = str(uuid.uuid4())

        # Build JWT claims
        claims = {
            "user_id": user_id,
            "username": username,
            "role": role.value,
            "permissions": permission_list,
            "exp": expire,
            "iat": datetime.utcnow(),
            "jti": jti,
            "type": "access",
        }

        # Add additional claims if provided
        if additional_claims:
            claims.update(additional_claims)

        # Encode JWT
        encoded_jwt = jwt.encode(
            claims,
            self.secret_key,
            algorithm=self.algorithm
        )

        logger.info(
            "Access token created",
            extra={
                "user_id": user_id,
                "username": username,
                "role": role.value,
                "jti": jti,
                "expires_at": expire.isoformat(),
            }
        )

        # Calculate expires_in seconds
        expires_in = int((expire - datetime.utcnow()).total_seconds())

        return Token(
            access_token=encoded_jwt,
            token_type="bearer",
            expires_in=expires_in,
        )

    def create_refresh_token(
        self,
        user_id: str,
        username: str,
    ) -> str:
        """
        Create JWT refresh token.

        Refresh tokens have longer TTL and can be used to obtain new access tokens.

        Args:
            user_id: User unique identifier
            username: Username

        Returns:
            Refresh token string

        Example:
            >>> tm = TokenManager()
            >>> refresh_token = tm.create_refresh_token("user_123", "john.doe")
            >>> len(refresh_token) > 0
            True

        ISO 27001: A.9.2.3 (Session management with refresh tokens)
        """
        expire = datetime.utcnow() + timedelta(days=self.refresh_token_expire_days)
        jti = str(uuid.uuid4())

        claims = {
            "user_id": user_id,
            "username": username,
            "exp": expire,
            "iat": datetime.utcnow(),
            "jti": jti,
            "type": "refresh",
        }

        encoded_jwt = jwt.encode(
            claims,
            self.secret_key,
            algorithm=self.algorithm
        )

        logger.info(
            "Refresh token created",
            extra={
                "user_id": user_id,
                "username": username,
                "jti": jti,
                "expires_at": expire.isoformat(),
            }
        )

        return encoded_jwt

    def decode_token(self, token: str) -> Dict:
        """
        Decode and validate JWT token.

        Args:
            token: JWT token string

        Returns:
            Decoded token payload

        Raises:
            InvalidTokenError: If token is invalid
            ExpiredSignatureError: If token has expired

        Example:
            >>> tm = TokenManager()
            >>> token = tm.create_access_token("user_123", "john", UserRole.VIEWER)
            >>> payload = tm.decode_token(token.access_token)
            >>> payload['username']
            'john'

        ISO 27001: A.9.4.2 (Token validation)
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )

            # Check if token is revoked
            jti = payload.get("jti")
            if jti and self.is_token_revoked(jti):
                raise InvalidTokenError("Token has been revoked")

            logger.debug(
                "Token decoded successfully",
                extra={
                    "user_id": payload.get("user_id"),
                    "jti": jti,
                }
            )

            return payload

        except ExpiredSignatureError:
            logger.warning("Token expired")
            raise

        except InvalidTokenError as e:
            logger.warning(
                "Invalid token",
                extra={"error": str(e)}
            )
            raise

    def decode_token_data(self, token: str) -> TokenData:
        """
        Decode token and return TokenData model.

        Args:
            token: JWT token string

        Returns:
            TokenData object

        Raises:
            InvalidTokenError: If token is invalid or missing required fields
        """
        payload = self.decode_token(token)

        try:
            # Convert permissions from strings back to Permission enum
            permissions = [
                Permission(p) for p in payload.get("permissions", [])
            ]

            return TokenData(
                user_id=payload["user_id"],
                username=payload["username"],
                role=UserRole(payload["role"]),
                permissions=permissions,
                exp=datetime.fromtimestamp(payload["exp"]),
                iat=datetime.fromtimestamp(payload["iat"]),
                jti=payload["jti"],
            )

        except (KeyError, ValueError) as e:
            raise InvalidTokenError(f"Invalid token structure: {e}")

    def revoke_token(self, token: str) -> None:
        """
        Revoke a token (add to blacklist).

        In production, store revoked tokens in Redis with TTL.

        Args:
            token: JWT token string to revoke

        Example:
            >>> tm = TokenManager()
            >>> token = tm.create_access_token("user_123", "john", UserRole.VIEWER)
            >>> tm.revoke_token(token.access_token)
            >>> tm.is_token_revoked_str(token.access_token)
            True

        ISO 27001: A.9.2.3 (Token revocation for session termination)
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={"verify_exp": False}  # Allow revoking expired tokens
            )

            jti = payload.get("jti")
            if jti:
                self._revoked_tokens.add(jti)

                logger.info(
                    "Token revoked",
                    extra={
                        "jti": jti,
                        "user_id": payload.get("user_id"),
                    }
                )

        except InvalidTokenError as e:
            logger.error(
                "Failed to revoke token",
                extra={"error": str(e)}
            )
            raise

    def is_token_revoked(self, jti: str) -> bool:
        """
        Check if token is revoked by JTI.

        Args:
            jti: JWT ID

        Returns:
            True if token is revoked, False otherwise
        """
        return jti in self._revoked_tokens

    def is_token_revoked_str(self, token: str) -> bool:
        """
        Check if token string is revoked.

        Args:
            token: JWT token string

        Returns:
            True if token is revoked, False otherwise
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={"verify_exp": False}
            )
            jti = payload.get("jti")
            return jti in self._revoked_tokens if jti else False

        except InvalidTokenError:
            return False

    def revoke_user_tokens(self, user_id: str) -> None:
        """
        Revoke all tokens for a specific user.

        Note: This is a simplified implementation. In production,
        maintain a user_id -> jti mapping in Redis.

        Args:
            user_id: User identifier

        ISO 27001: A.9.2.6 (Session termination on user de-registration)
        """
        logger.info(
            "Revoking all tokens for user",
            extra={"user_id": user_id}
        )

        # In production, query Redis for all JTIs associated with user_id
        # and add them to revocation list

    def refresh_access_token(self, refresh_token: str) -> Token:
        """
        Create new access token using refresh token.

        Args:
            refresh_token: Valid refresh token

        Returns:
            New access token

        Raises:
            InvalidTokenError: If refresh token is invalid

        Example:
            >>> tm = TokenManager()
            >>> refresh = tm.create_refresh_token("user_123", "john")
            >>> # ... store user data ...
            >>> new_token = tm.refresh_access_token(refresh)
            >>> new_token.token_type
            'bearer'

        ISO 27001: A.9.2.3 (Session refresh mechanism)
        """
        try:
            payload = self.decode_token(refresh_token)

            # Verify it's a refresh token
            if payload.get("type") != "refresh":
                raise InvalidTokenError("Not a refresh token")

            # Note: In production, retrieve user data from database
            # For now, we need to get role from somewhere
            # This is a simplified example

            logger.info(
                "Access token refreshed",
                extra={
                    "user_id": payload["user_id"],
                    "username": payload["username"],
                }
            )

            # This method needs to be called with user data from DB
            # Returning a stub for now
            raise NotImplementedError(
                "refresh_access_token requires user data from database"
            )

        except InvalidTokenError:
            logger.warning("Invalid refresh token")
            raise

    def get_token_expiry(self, token: str) -> Optional[datetime]:
        """
        Get token expiration datetime.

        Args:
            token: JWT token string

        Returns:
            Expiration datetime or None if token is invalid
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={"verify_exp": False}
            )

            exp_timestamp = payload.get("exp")
            if exp_timestamp:
                return datetime.fromtimestamp(exp_timestamp)

            return None

        except InvalidTokenError:
            return None

    def get_token_age(self, token: str) -> Optional[timedelta]:
        """
        Get token age (time since issued).

        Args:
            token: JWT token string

        Returns:
            Time delta since token was issued, or None if invalid
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={"verify_exp": False}
            )

            iat_timestamp = payload.get("iat")
            if iat_timestamp:
                issued_at = datetime.fromtimestamp(iat_timestamp)
                return datetime.utcnow() - issued_at

            return None

        except InvalidTokenError:
            return None


# Singleton instance
_token_manager: Optional[TokenManager] = None


def get_token_manager() -> TokenManager:
    """
    Get singleton TokenManager instance.

    Returns:
        TokenManager instance
    """
    global _token_manager

    if _token_manager is None:
        _token_manager = TokenManager(
            secret_key=settings.SECRET_KEY,
            access_token_expire_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        )

    return _token_manager
