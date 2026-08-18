"""
Authentication Security Tests
Medical Imaging Viewer - Comprehensive Authentication Testing Suite

ISO 27001 A.9.2.1 - User registration and de-registration
ISO 27001 A.9.2.2 - User access provisioning
ISO 27001 A.9.2.4 - Management of secret authentication information
ISO 27001 A.9.4.2 - Secure log-on procedures
ISO 27001 A.9.4.3 - Password management system

OWASP ASVS 4.0:
- V2.1: Password Security Requirements
- V2.2: General Authenticator Requirements
- V2.3: Authenticator Lifecycle Requirements
- V3.2: Session Binding Requirements
- V3.3: Session Logout and Timeout Requirements

This module tests:
1. Password hashing with Argon2id (OWASP recommended)
2. JWT token generation and validation
3. Token expiration and refresh mechanisms
4. Account lockout after failed attempts
5. Password strength (policy) validation
6. Property-based testing with Hypothesis
7. Timing attack resistance

@module tests.security.test_authentication
@version 3.0.0 - Realigned to the current auth surface
"""

import time
import uuid
from datetime import timedelta
from typing import Dict

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck

# CAPA-001 PA-2 (re-cut, v3.0.0): this module imported `app.core.security.auth`
# and drove an auth API (str-returning create_access_token, jose.JWTError,
# PasswordManager lockout/validate_password_strength methods) that does not exist
# in the repository. It failed at collection and never executed. The suite has
# been realigned to the ACTUAL production surface, which is PyJWT-based and lives
# under `app.security.*`:
#   - jose.JWTError                         -> jwt.exceptions.InvalidTokenError / ExpiredSignatureError (PyJWT, as used by jwt_manager)
#   - app.core.security.auth.PasswordManager -> app.security.password.PasswordManager
#   - app.core.security.auth (TokenManager)  -> app.security.jwt_manager.TokenManager
#   - TokenManager.create_access_token(data) -> create_access_token(user_id, username, role: UserRole, ...) returning a Token model
#   - decode_token payload keys sub/email    -> user_id/username/role/permissions/exp/iat/jti/type (email via additional_claims)
#   - PasswordManager.validate_password_strength(pw)->bool -> validate_password_policy(pw)->(bool, errors) (min length 12)
#   - PasswordManager lockout methods        -> real lockout control lives in app.security.auth.AuthService.login()
# Every security property the original suite asserted is preserved; see the
# per-test docstrings and TestAccountLockout for the lockout realignment.
from jwt.exceptions import InvalidTokenError, ExpiredSignatureError

from app.security.password import PasswordManager
from app.security.jwt_manager import TokenManager
from app.security.models import UserRole

# A fixed, >=32-char signing key for deterministic token tests. Matches the value
# tests/conftest.py exports into the environment, so it is a legitimate test key
# and never touches production configuration.
TEST_SECRET_KEY = "test-secret-key-minimum-32-characters-required-for-security"

# Text strategy excluding lone surrogates (Unicode category "Cs"), which cannot be
# UTF-8 encoded and would raise inside Argon2 for reasons unrelated to the property
# under test. Everything else — punctuation, symbols, CJK, emoji — stays in scope.
_SAFE_TEXT = st.characters(blacklist_categories=("Cs",))


# =============================================================================
# LOCAL FIXTURE OVERRIDES
# tests/conftest.py defines `password_manager` and `token_manager`, but both are
# wired to the dead `app.core.security.auth` path / a non-existent
# `settings.JWT_SECRET_KEY`. These module-scoped overrides shadow the broken
# conftest fixtures for this file without touching shared test infrastructure.
# =============================================================================


@pytest.fixture(scope="module", autouse=True)
def _isolate_auth_user_storage(tmp_path_factory):
    """Redirect the process-wide user-storage singleton to an isolated temp dir for
    this module only. TestAccountLockout registers users via AuthService, which
    otherwise writes real records into the shared on-disk ``data/users`` store —
    polluting the developer's data AND leaking users into later tests (this silently
    broke the RC-029 authorization tests in a full run). Restored afterwards; the
    real ``data/users`` and the global encryption key are never touched.
    """
    try:
        import app.security.user_storage as us
    except Exception:  # pragma: no cover - app not importable
        yield
        return
    prev = us._user_storage
    us._user_storage = us.SecureUserStorage(
        storage_dir=tmp_path_factory.mktemp("auth_user_store"))
    try:
        yield
    finally:
        us._user_storage = prev


@pytest.fixture
def password_manager() -> PasswordManager:
    """Password manager backed by the real Argon2id implementation."""
    return PasswordManager()


@pytest.fixture
def token_manager() -> TokenManager:
    """Token manager with an explicit HS256 test key (30-min access TTL)."""
    return TokenManager(
        secret_key=TEST_SECRET_KEY,
        algorithm="HS256",
        access_token_expire_minutes=30,
        refresh_token_expire_days=7,
    )


# =============================================================================
# PASSWORD HASHING TESTS (Argon2id)
# ISO 27001 A.9.2.4 - Management of secret authentication information
# =============================================================================

@pytest.mark.security
@pytest.mark.authentication
class TestPasswordHashing:
    """Test password hashing with Argon2id."""

    def test_hash_password_returns_hash(self, password_manager: PasswordManager):
        """Test that password hashing returns a valid, non-plaintext hash."""
        password = "SecureP@ssw0rd123!"
        password_hash = password_manager.hash_password(password)

        assert password_hash is not None
        assert isinstance(password_hash, str)
        assert len(password_hash) > 0
        assert password_hash != password  # Hash must not equal plaintext
        assert password_hash.startswith("$argon2id$")  # Argon2id output format

    def test_hash_password_is_salted_non_deterministic(self, password_manager: PasswordManager):
        """Test that the same password produces different hashes (random salt)."""
        password = "SecureP@ssw0rd123!"
        hash1 = password_manager.hash_password(password)
        hash2 = password_manager.hash_password(password)

        # Argon2id uses a random salt, so two hashes of the same input must differ
        assert hash1 != hash2

    def test_verify_password_correct(self, password_manager: PasswordManager):
        """Test password verification with the correct password."""
        password = "SecureP@ssw0rd123!"
        password_hash = password_manager.hash_password(password)

        assert password_manager.verify_password(password, password_hash) is True

    def test_verify_password_incorrect(self, password_manager: PasswordManager):
        """Test password verification with an incorrect password."""
        correct_password = "SecureP@ssw0rd123!"
        wrong_password = "WrongP@ssw0rd456!"
        password_hash = password_manager.hash_password(correct_password)

        assert password_manager.verify_password(wrong_password, password_hash) is False

    def test_verify_password_case_sensitive(self, password_manager: PasswordManager):
        """Test that password verification is case-sensitive."""
        password = "SecureP@ssw0rd123!"
        password_hash = password_manager.hash_password(password)

        assert password_manager.verify_password("securep@ssw0rd123!", password_hash) is False
        assert password_manager.verify_password("SECUREP@SSW0RD123!", password_hash) is False

    def test_hash_empty_password_rejected(self, password_manager: PasswordManager):
        """
        Test that hashing an empty password is rejected.

        The current implementation raises ValueError on an empty password rather
        than silently hashing it — a stronger guarantee than the original test
        (which asserted an empty password could round-trip). We assert the reject.
        """
        with pytest.raises(ValueError):
            password_manager.hash_password("")

    def test_hash_very_long_password(self, password_manager: PasswordManager):
        """Test hashing a very long password (1000+ characters)."""
        long_password = "aB3$" * 250  # 1000 chars, mixed classes
        password_hash = password_manager.hash_password(long_password)

        assert password_hash is not None
        assert password_manager.verify_password(long_password, password_hash) is True

    def test_hash_unicode_password(self, password_manager: PasswordManager):
        """Test hashing a password with Unicode characters."""
        unicode_password = "P@ssw0rd™€中文\U0001f512"
        password_hash = password_manager.hash_password(unicode_password)

        assert password_hash is not None
        assert password_manager.verify_password(unicode_password, password_hash) is True

    def test_timing_attack_resistance(self, password_manager: PasswordManager):
        """
        Test basic timing-attack resistance.

        Argon2id verification runs the full KDF whether or not the password matches
        (no early exit), so correct vs incorrect verification must not differ
        DRAMATICALLY. A wall-clock timing test is inherently noisy under machine load,
        so we compare the MEDIAN of several runs with a RELATIVE bound: a real leak
        (e.g. an early-exit on mismatch) would make one path near-instant and blow the
        ratio up, while scheduling jitter stays well within tolerance. (Rigorous
        constant-time analysis needs dedicated statistical tooling; this is a sanity
        check.)
        """
        password = "SecureP@ssw0rd123!"
        password_hash = password_manager.hash_password(password)

        def _median_verify_seconds(candidate: str, n: int = 5) -> float:
            samples = []
            for _ in range(n):
                t0 = time.perf_counter()
                password_manager.verify_password(candidate, password_hash)
                samples.append(time.perf_counter() - t0)
            samples.sort()
            return samples[len(samples) // 2]

        time_correct = _median_verify_seconds(password)
        time_incorrect = _median_verify_seconds("WrongPassword")

        # Both should be the full-KDF cost. A genuine timing leak (early exit) would
        # make the ratio explode; noise keeps it near 1. 3x is robust to load while
        # still catching a real short-circuit.
        lo = max(min(time_correct, time_incorrect), 1e-6)
        ratio = max(time_correct, time_incorrect) / lo
        assert ratio < 3.0, (
            f"Verify time ratio too large (possible timing leak): {ratio:.2f} "
            f"(correct={time_correct*1000:.1f}ms, incorrect={time_incorrect*1000:.1f}ms)")


# =============================================================================
# PROPERTY-BASED TESTING WITH HYPOTHESIS
# Advanced testing using random input generation
# =============================================================================

@pytest.mark.security
@pytest.mark.authentication
@pytest.mark.property
class TestPasswordHashingPropertyBased:
    """Property-based tests for password hashing using Hypothesis."""

    @given(password=st.text(alphabet=_SAFE_TEXT, min_size=1, max_size=200))
    @settings(
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        max_examples=50,
        # Argon2id is intentionally expensive (64 MB / 2 iterations); a single
        # hash can exceed 200ms. Disable Hypothesis's per-example deadline so the
        # deliberately-slow KDF is not misreported as a failure. The security
        # property under test (round-trip correctness) is unchanged.
        deadline=None,
    )
    def test_hash_verify_round_trip(self, password: str, password_manager: PasswordManager):
        """
        Property: any non-empty password hashes, verifies with the correct value,
        and fails verification with a different value.
        """
        password_hash = password_manager.hash_password(password)

        assert password_manager.verify_password(password, password_hash) is True

        wrong_password = password + "WRONG"
        assert password_manager.verify_password(wrong_password, password_hash) is False

    @given(password=st.text(alphabet=_SAFE_TEXT, min_size=8, max_size=128))
    @settings(
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        max_examples=30,
        # See test_hash_verify_round_trip: Argon2id's cost trips the default
        # 200ms deadline; disabling it does not weaken the salt-uniqueness check.
        deadline=None,
    )
    def test_hash_uniqueness(self, password: str, password_manager: PasswordManager):
        """Property: the same password yields different hashes (salt randomness)."""
        hash1 = password_manager.hash_password(password)
        hash2 = password_manager.hash_password(password)

        assert hash1 != hash2


# =============================================================================
# JWT TOKEN GENERATION TESTS
# ISO 27001 A.9.4.2 - Secure log-on procedures
# =============================================================================

@pytest.mark.security
@pytest.mark.authentication
class TestJWTTokenGeneration:
    """Test JWT token generation and validation."""

    def test_create_access_token(self, token_manager: TokenManager):
        """Test creating an access token returns a well-formed JWT."""
        token_obj = token_manager.create_access_token(
            user_id="user_123", username="test_user", role=UserRole.VIEWER
        )

        assert token_obj.token_type == "bearer"
        access_token = token_obj.access_token
        assert isinstance(access_token, str)
        assert len(access_token) > 0

        # header.payload.signature
        assert len(access_token.split(".")) == 3

    def test_create_refresh_token(self, token_manager: TokenManager):
        """Test creating a refresh token returns a well-formed JWT string."""
        refresh_token = token_manager.create_refresh_token(
            user_id="user_123", username="test_user"
        )

        assert isinstance(refresh_token, str)
        assert len(refresh_token) > 0
        assert len(refresh_token.split(".")) == 3

    def test_decode_valid_token(self, token_manager: TokenManager):
        """Test decoding a valid access token exposes the expected claims."""
        token_obj = token_manager.create_access_token(
            user_id="user_123", username="test_user", role=UserRole.ADMIN
        )

        decoded = token_manager.decode_token(token_obj.access_token)

        assert decoded is not None
        assert decoded["user_id"] == "user_123"
        assert decoded["username"] == "test_user"
        assert decoded["role"] == "admin"
        assert decoded["type"] == "access"
        assert "exp" in decoded   # Expiration present
        assert "iat" in decoded   # Issued-at present
        assert "jti" in decoded   # Unique token id (revocation) present
        # RBAC-derived permissions are embedded in the token
        assert isinstance(decoded["permissions"], list)
        assert len(decoded["permissions"]) > 0

    def test_decode_invalid_token(self, token_manager: TokenManager):
        """Test decoding a structurally invalid token is rejected."""
        with pytest.raises(InvalidTokenError):
            token_manager.decode_token("invalid.token.here")

    def test_decode_tampered_token(self, token_manager: TokenManager):
        """Test that tampering with the payload breaks signature verification."""
        token_obj = token_manager.create_access_token(
            user_id="user_123", username="test_user", role=UserRole.VIEWER
        )

        # Corrupt a byte in the payload segment; the HMAC signature covers
        # header.payload, so any change must fail verification.
        header, payload, signature = token_obj.access_token.split(".")
        idx = 10
        flipped_char = "X" if payload[idx] != "X" else "Y"
        tampered_payload = payload[:idx] + flipped_char + payload[idx + 1:]
        tampered_token = ".".join([header, tampered_payload, signature])
        assert tampered_token != token_obj.access_token

        with pytest.raises(InvalidTokenError):
            token_manager.decode_token(tampered_token)

    def test_token_expiration(self):
        """Test that an expired token is rejected."""
        manager = TokenManager(secret_key=TEST_SECRET_KEY, algorithm="HS256")

        token_obj = manager.create_access_token(
            user_id="user_123",
            username="test_user",
            role=UserRole.VIEWER,
            expires_delta=timedelta(seconds=1),
        )

        # Valid immediately
        decoded = manager.decode_token(token_obj.access_token)
        assert decoded["username"] == "test_user"

        # Wait for the token to expire, then it must be rejected
        time.sleep(2)
        with pytest.raises(ExpiredSignatureError):
            manager.decode_token(token_obj.access_token)

    def test_token_contains_required_claims(self, token_manager: TokenManager):
        """Test that the token carries all required claims, including custom ones."""
        token_obj = token_manager.create_access_token(
            user_id="user_123",
            username="test_user",
            role=UserRole.RADIOLOGIST,
            additional_claims={"email": "test@example.com"},
        )

        decoded = token_manager.decode_token(token_obj.access_token)

        # Required standard claims
        assert "user_id" in decoded
        assert "exp" in decoded
        assert "iat" in decoded
        assert "jti" in decoded

        # Custom / identity claims
        assert decoded["user_id"] == "user_123"
        assert decoded["username"] == "test_user"
        assert decoded["role"] == "radiologist"
        assert decoded["email"] == "test@example.com"

    def test_different_tokens_for_different_users(self, token_manager: TokenManager):
        """Test that different users get distinct, correctly-scoped tokens."""
        token1 = token_manager.create_access_token(
            user_id="user1", username="user1", role=UserRole.VIEWER
        )
        token2 = token_manager.create_access_token(
            user_id="user2", username="user2", role=UserRole.VIEWER
        )

        assert token1.access_token != token2.access_token

        assert token_manager.decode_token(token1.access_token)["user_id"] == "user1"
        assert token_manager.decode_token(token2.access_token)["user_id"] == "user2"

    def test_token_secret_key_importance(self):
        """Test that a token signed with one key is not accepted by another key."""
        manager1 = TokenManager(secret_key="secret1" + "x" * 30, algorithm="HS256")
        manager2 = TokenManager(secret_key="secret2" + "x" * 30, algorithm="HS256")

        token1 = manager1.create_access_token(
            user_id="user_123", username="test_user", role=UserRole.VIEWER
        )
        token2 = manager2.create_access_token(
            user_id="user_123", username="test_user", role=UserRole.VIEWER
        )

        assert token1.access_token != token2.access_token

        # A manager with a different signing key MUST reject the other's token.
        with pytest.raises(InvalidTokenError):
            manager2.decode_token(token1.access_token)


# =============================================================================
# TOKEN REFRESH MECHANISM TESTS
# ISO 27001 A.9.4.2 - Secure log-on procedures
# =============================================================================

@pytest.mark.security
@pytest.mark.authentication
class TestTokenRefresh:
    """Test token refresh mechanisms."""

    def test_refresh_token_longer_expiration(self):
        """Test that refresh tokens expire later than access tokens."""
        manager = TokenManager(
            secret_key=TEST_SECRET_KEY,
            algorithm="HS256",
            access_token_expire_minutes=30,
            refresh_token_expire_days=7,
        )

        access_token = manager.create_access_token(
            user_id="user_123", username="test_user", role=UserRole.VIEWER
        )
        refresh_token = manager.create_refresh_token(
            user_id="user_123", username="test_user"
        )

        access_decoded = manager.decode_token(access_token.access_token)
        refresh_decoded = manager.decode_token(refresh_token)

        assert refresh_decoded["exp"] > access_decoded["exp"]
        assert access_decoded["type"] == "access"
        assert refresh_decoded["type"] == "refresh"

    def test_refresh_token_independent_validation(self, token_manager: TokenManager):
        """Test that a refresh token validates independently and is typed."""
        refresh_token = token_manager.create_refresh_token(
            user_id="user_123", username="test_user"
        )

        decoded = token_manager.decode_token(refresh_token)
        assert decoded["user_id"] == "user_123"
        assert decoded["username"] == "test_user"
        assert decoded["type"] == "refresh"


# =============================================================================
# PASSWORD STRENGTH (POLICY) VALIDATION TESTS
# OWASP ASVS 4.0 V2.1 - Password Security Requirements
#
# The current PasswordManager exposes validate_password_policy(pw) -> (bool, errors)
# with a 12-character minimum (PasswordPolicy default). These tests assert the
# ACTUAL enforced policy (min length 12 + full complexity + common/sequential
# rejection) rather than the weaker 8-char policy the stale suite assumed.
# =============================================================================

@pytest.mark.security
@pytest.mark.authentication
class TestPasswordStrength:
    """Test password strength (policy) validation."""

    def test_validate_strong_password(self, password_manager: PasswordManager):
        """Test that strong passwords pass policy validation."""
        strong_passwords = [
            "SecureP@ssw0rd123!",
            "MyC0mplex!Passphrase",
            "CorrectHorseBatteryStaple135!",
        ]

        for password in strong_passwords:
            is_valid, errors = password_manager.validate_password_policy(password)
            assert is_valid is True, f"Password should be strong: {password} -> {errors}"

    def test_validate_weak_passwords(self, password_manager: PasswordManager):
        """Test that weak passwords are rejected by policy validation."""
        weak_passwords = [
            "password",      # too short, no complexity, common
            "12345678",      # only digits, sequential
            "abcdefgh",      # only lowercase, sequential
            "ABCDEFGH",      # only uppercase, sequential
            "Pass123",       # too short
            "password123",   # no uppercase / special
            "Password!",     # no digit, too short
        ]

        for password in weak_passwords:
            is_valid, _ = password_manager.validate_password_policy(password)
            assert is_valid is False, f"Password should be weak: {password}"

    def test_password_minimum_length(self, password_manager: PasswordManager):
        """Test the minimum password length requirement (12 characters)."""
        # 11 characters - should fail
        assert password_manager.validate_password_policy("Pass12!@wxy")[0] is False

        # 12 characters meeting all complexity - should pass
        assert password_manager.validate_password_policy("Pass12!@wxyz")[0] is True

    def test_password_complexity_requirements(self, password_manager: PasswordManager):
        """Test password complexity requirements (each at >=12 chars)."""
        # Missing uppercase
        assert password_manager.validate_password_policy("password135!")[0] is False

        # Missing lowercase
        assert password_manager.validate_password_policy("PASSWORD135!")[0] is False

        # Missing digit
        assert password_manager.validate_password_policy("Password!@#$")[0] is False

        # Missing special character
        assert password_manager.validate_password_policy("Password1357")[0] is False

        # Has all requirements
        assert password_manager.validate_password_policy("Password135!")[0] is True


# =============================================================================
# ACCOUNT LOCKOUT TESTS
# ISO 27001 A.9.4.3 - Password management system
# OWASP ASVS 4.0 V2.2.1 - Anti-automation
#
# REALIGNED: the stale suite called PasswordManager.record_failed_attempt /
# is_account_locked / unlock_account / reset_failed_attempts — an API that does
# not exist on PasswordManager (nor anywhere else). The real lockout control is
# implemented in app.security.auth.AuthService.login(): after
# password_policy.lockout_threshold consecutive failed logins the account is
# locked (HTTP 403) and even the correct password is refused until the lockout
# window elapses. These tests exercise that real control end to end.
# =============================================================================

@pytest.mark.security
@pytest.mark.authentication
@pytest.mark.integration
class TestAccountLockout:
    """Test account lockout after failed login attempts (via AuthService)."""

    VALID_PASSWORD = "SecureP@ssw0rd2025!"
    WRONG_PASSWORD = "Wr0ng!Password789"

    def _make_service(self, lockout_threshold: int):
        from app.security.auth import AuthService
        from app.security.models import PasswordPolicy

        policy = PasswordPolicy(
            lockout_threshold=lockout_threshold,
            lockout_duration_minutes=30,
        )
        return AuthService(password_policy=policy)

    def _register(self, auth):
        """Register a fresh, uniquely-named user and return it."""
        from app.security.models import UserCreate

        username = f"lock_{uuid.uuid4().hex[:12]}"
        user = auth.register_user(UserCreate(
            username=username,
            email=f"{username}@example.com",
            full_name="Lockout Test User",
            password=self.VALID_PASSWORD,
            role=UserRole.VIEWER,
        ))
        return user, username

    def test_account_lockout_after_failed_attempts(self):
        """Test that an account locks once the failed-attempt threshold is hit."""
        from fastapi import HTTPException
        from app.security.models import LoginRequest

        threshold = 3
        auth = self._make_service(threshold)
        user, username = self._register(auth)

        # Attempts below the threshold: rejected (401) but NOT yet locked.
        for _ in range(threshold - 1):
            with pytest.raises(HTTPException) as exc:
                auth.login(LoginRequest(username=username, password=self.WRONG_PASSWORD))
            assert exc.value.status_code == 401
        assert auth.get_user_by_id(user.id).is_locked is False

        # The threshold-th failure locks the account.
        with pytest.raises(HTTPException):
            auth.login(LoginRequest(username=username, password=self.WRONG_PASSWORD))
        assert auth.get_user_by_id(user.id).is_locked is True

    def test_locked_account_rejects_correct_password(self):
        """Test that a locked account refuses even the correct password."""
        from fastapi import HTTPException
        from app.security.models import LoginRequest

        threshold = 3
        auth = self._make_service(threshold)
        user, username = self._register(auth)

        for _ in range(threshold):
            with pytest.raises(HTTPException):
                auth.login(LoginRequest(username=username, password=self.WRONG_PASSWORD))
        assert auth.get_user_by_id(user.id).is_locked is True

        # Correct credentials must still be refused while locked (403, not a login).
        with pytest.raises(HTTPException) as exc:
            auth.login(LoginRequest(username=username, password=self.VALID_PASSWORD))
        assert exc.value.status_code == 403

    def test_failed_attempts_reset_on_success(self):
        """Test that a successful login resets the failed-attempt counter."""
        from fastapi import HTTPException
        from app.security.models import LoginRequest

        auth = self._make_service(lockout_threshold=5)
        user, username = self._register(auth)

        # Some failures below the threshold.
        for _ in range(3):
            with pytest.raises(HTTPException):
                auth.login(LoginRequest(username=username, password=self.WRONG_PASSWORD))
        assert auth.get_user_by_id(user.id).failed_login_attempts == 3

        # A successful login resets the counter (and the account stays unlocked).
        response = auth.login(LoginRequest(username=username, password=self.VALID_PASSWORD))
        assert response.user.username == username
        assert auth.get_user_by_id(user.id).failed_login_attempts == 0
        assert auth.get_user_by_id(user.id).is_locked is False


# =============================================================================
# INTEGRATION TESTS
# End-to-end authentication flow testing
# =============================================================================

@pytest.mark.security
@pytest.mark.authentication
@pytest.mark.integration
class TestAuthenticationIntegration:
    """Integration tests for the complete authentication flow."""

    def test_complete_login_flow(
        self,
        password_manager: PasswordManager,
        token_manager: TokenManager,
        test_user_data: Dict[str, str],
    ):
        """Test the complete flow: hash -> verify -> issue token -> decode token."""
        # 1. Registration (hash password)
        password_hash = password_manager.hash_password(test_user_data["password"])

        # 2. Login (verify password)
        assert password_manager.verify_password(
            test_user_data["password"], password_hash
        ) is True

        # 3. Issue an access token
        access_token = token_manager.create_access_token(
            user_id="user-001",
            username=test_user_data["username"],
            role=UserRole(test_user_data["role"]),
            additional_claims={"email": test_user_data["email"]},
        )

        # 4. Decode and verify the token content
        decoded = token_manager.decode_token(access_token.access_token)
        assert decoded["username"] == test_user_data["username"]
        assert decoded["role"] == test_user_data["role"]
        assert decoded["email"] == test_user_data["email"]

    def test_failed_login_flow(
        self,
        password_manager: PasswordManager,
        test_user_data: Dict[str, str],
    ):
        """Test the failed login flow: a wrong password never verifies."""
        password_hash = password_manager.hash_password(test_user_data["password"])

        assert password_manager.verify_password(
            "WrongPassword123!", password_hash
        ) is False
        # No token is issued when verification fails (enforced by application logic).

    def test_token_based_authorization(
        self,
        token_manager: TokenManager,
        admin_user_data: Dict[str, str],
    ):
        """Test role/permission-based authorization data carried by the JWT."""
        admin_token = token_manager.create_access_token(
            user_id="admin-001",
            username=admin_user_data["username"],
            role=UserRole(admin_user_data["role"]),
        )

        decoded = token_manager.decode_token(admin_token.access_token)
        assert decoded["role"] == "admin"

        # Admin-only permission must be embedded so downstream RBAC can authorize.
        assert "user:create" in decoded["permissions"]
