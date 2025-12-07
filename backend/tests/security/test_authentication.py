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
5. Password strength requirements
6. Property-based testing with Hypothesis
7. Timing attack resistance

@module tests.security.test_authentication
@version 2.0.0 - Enterprise Security Testing
"""

import pytest
import time
from datetime import datetime, timedelta
from typing import Dict
from hypothesis import given, strategies as st, settings, HealthCheck
from jose import jwt, JWTError

from app.core.security.auth import PasswordManager, TokenManager
from app.core.config import get_settings

settings_config = get_settings()


# =============================================================================
# PASSWORD HASHING TESTS (Argon2id)
# ISO 27001 A.9.2.4 - Management of secret authentication information
# =============================================================================

@pytest.mark.security
@pytest.mark.authentication
class TestPasswordHashing:
    """Test password hashing with Argon2id."""

    def test_hash_password_returns_hash(self, password_manager: PasswordManager):
        """Test that password hashing returns a valid hash."""
        password = "SecureP@ssw0rd123!"
        password_hash = password_manager.hash_password(password)

        assert password_hash is not None
        assert isinstance(password_hash, str)
        assert len(password_hash) > 0
        assert password_hash != password  # Hash should not equal plaintext

    def test_hash_password_is_deterministic_different(self, password_manager: PasswordManager):
        """Test that same password produces different hashes (due to salt)."""
        password = "SecureP@ssw0rd123!"
        hash1 = password_manager.hash_password(password)
        hash2 = password_manager.hash_password(password)

        # Argon2id uses random salt, so hashes should differ
        assert hash1 != hash2

    def test_verify_password_correct(self, password_manager: PasswordManager):
        """Test password verification with correct password."""
        password = "SecureP@ssw0rd123!"
        password_hash = password_manager.hash_password(password)

        # Verification should succeed
        assert password_manager.verify_password(password, password_hash) is True

    def test_verify_password_incorrect(self, password_manager: PasswordManager):
        """Test password verification with incorrect password."""
        correct_password = "SecureP@ssw0rd123!"
        wrong_password = "WrongP@ssw0rd456!"
        password_hash = password_manager.hash_password(correct_password)

        # Verification should fail
        assert password_manager.verify_password(wrong_password, password_hash) is False

    def test_verify_password_case_sensitive(self, password_manager: PasswordManager):
        """Test that password verification is case-sensitive."""
        password = "SecureP@ssw0rd123!"
        password_hash = password_manager.hash_password(password)

        # Different case should fail
        assert password_manager.verify_password("securep@ssw0rd123!", password_hash) is False
        assert password_manager.verify_password("SECUREP@SSW0RD123!", password_hash) is False

    def test_hash_empty_password(self, password_manager: PasswordManager):
        """Test hashing empty password."""
        # Should still hash (though application should reject empty passwords)
        password_hash = password_manager.hash_password("")
        assert password_hash is not None
        assert password_manager.verify_password("", password_hash) is True

    def test_hash_very_long_password(self, password_manager: PasswordManager):
        """Test hashing very long password (1000+ characters)."""
        # Argon2id should handle long passwords
        long_password = "a" * 1000
        password_hash = password_manager.hash_password(long_password)

        assert password_hash is not None
        assert password_manager.verify_password(long_password, password_hash) is True

    def test_hash_unicode_password(self, password_manager: PasswordManager):
        """Test hashing password with Unicode characters."""
        unicode_password = "P@ssw0rd™€中文🔒"
        password_hash = password_manager.hash_password(unicode_password)

        assert password_hash is not None
        assert password_manager.verify_password(unicode_password, password_hash) is True

    def test_timing_attack_resistance(self, password_manager: PasswordManager):
        """
        Test timing attack resistance.

        Argon2id should have consistent timing regardless of password correctness.
        Note: This is a basic test; true timing analysis requires statistical methods.
        """
        password = "SecureP@ssw0rd123!"
        password_hash = password_manager.hash_password(password)

        # Measure time for correct password
        start_correct = time.perf_counter()
        password_manager.verify_password(password, password_hash)
        time_correct = time.perf_counter() - start_correct

        # Measure time for incorrect password
        start_incorrect = time.perf_counter()
        password_manager.verify_password("WrongPassword", password_hash)
        time_incorrect = time.perf_counter() - start_incorrect

        # Time difference should be minimal (< 50ms typically for Argon2id)
        # Note: This test may be flaky on heavily loaded systems
        time_diff_ms = abs(time_correct - time_incorrect) * 1000
        assert time_diff_ms < 100, f"Timing difference too large: {time_diff_ms:.2f}ms"


# =============================================================================
# PROPERTY-BASED TESTING WITH HYPOTHESIS
# Advanced testing using random input generation
# =============================================================================

@pytest.mark.security
@pytest.mark.authentication
@pytest.mark.property
class TestPasswordHashingPropertyBased:
    """Property-based tests for password hashing using Hypothesis."""

    @given(password=st.text(min_size=1, max_size=1000))
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=50)
    def test_hash_verify_round_trip(self, password: str, password_manager: PasswordManager):
        """
        Property: Any password should hash and verify correctly.

        Tests that for ANY input password:
        1. Hashing succeeds
        2. Verification with correct password succeeds
        3. Verification with different password fails
        """
        # Hash password
        password_hash = password_manager.hash_password(password)

        # Verify with correct password
        assert password_manager.verify_password(password, password_hash) is True

        # Verify with wrong password (if password is not empty)
        if len(password) > 0:
            wrong_password = password + "WRONG"
            assert password_manager.verify_password(wrong_password, password_hash) is False

    @given(password=st.text(min_size=8, max_size=128))
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=30)
    def test_hash_uniqueness(self, password: str, password_manager: PasswordManager):
        """
        Property: Same password should produce different hashes (salt randomness).

        Tests that Argon2id uses random salts.
        """
        hash1 = password_manager.hash_password(password)
        hash2 = password_manager.hash_password(password)

        # Should be different due to random salt
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
        """Test creating access token with valid data."""
        data = {"sub": "test_user", "role": "viewer"}
        token = token_manager.create_access_token(data)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

        # Token should have 3 parts separated by dots (header.payload.signature)
        parts = token.split(".")
        assert len(parts) == 3

    def test_create_refresh_token(self, token_manager: TokenManager):
        """Test creating refresh token with valid data."""
        data = {"sub": "test_user"}
        token = token_manager.create_refresh_token(data)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_valid_token(self, token_manager: TokenManager):
        """Test decoding valid access token."""
        data = {"sub": "test_user", "role": "admin"}
        token = token_manager.create_access_token(data)

        # Decode token
        decoded = token_manager.decode_token(token)

        assert decoded is not None
        assert decoded["sub"] == "test_user"
        assert decoded["role"] == "admin"
        assert "exp" in decoded  # Expiration should be present
        assert "iat" in decoded  # Issued at should be present

    def test_decode_invalid_token(self, token_manager: TokenManager):
        """Test decoding invalid token."""
        invalid_token = "invalid.token.here"

        with pytest.raises(JWTError):
            token_manager.decode_token(invalid_token)

    def test_decode_tampered_token(self, token_manager: TokenManager):
        """Test decoding tampered token (signature verification)."""
        data = {"sub": "test_user", "role": "viewer"}
        token = token_manager.create_access_token(data)

        # Tamper with token by changing a character
        tampered_token = token[:-5] + "XXXXX"

        with pytest.raises(JWTError):
            token_manager.decode_token(tampered_token)

    def test_token_expiration(self, token_manager: TokenManager):
        """Test token expiration validation."""
        # Create token with very short expiration (1 second)
        short_lived_manager = TokenManager(
            secret_key=settings_config.JWT_SECRET_KEY,
            algorithm="HS256",
            access_token_expire_minutes=1/60  # 1 second
        )

        data = {"sub": "test_user"}
        token = short_lived_manager.create_access_token(data)

        # Token should be valid immediately
        decoded = short_lived_manager.decode_token(token)
        assert decoded["sub"] == "test_user"

        # Wait for token to expire
        time.sleep(2)

        # Token should now be expired
        with pytest.raises(JWTError):
            short_lived_manager.decode_token(token)

    def test_token_contains_required_claims(self, token_manager: TokenManager):
        """Test that token contains all required claims."""
        data = {"sub": "test_user", "role": "radiologist", "email": "test@example.com"}
        token = token_manager.create_access_token(data)

        decoded = token_manager.decode_token(token)

        # Required standard claims
        assert "sub" in decoded
        assert "exp" in decoded
        assert "iat" in decoded

        # Custom claims
        assert decoded["sub"] == "test_user"
        assert decoded["role"] == "radiologist"
        assert decoded["email"] == "test@example.com"

    def test_different_tokens_for_different_users(self, token_manager: TokenManager):
        """Test that different users get different tokens."""
        token1 = token_manager.create_access_token({"sub": "user1"})
        token2 = token_manager.create_access_token({"sub": "user2"})

        assert token1 != token2

    def test_token_secret_key_importance(self):
        """Test that different secret keys produce different tokens."""
        data = {"sub": "test_user"}

        manager1 = TokenManager(secret_key="secret1" + "x" * 25, algorithm="HS256")
        manager2 = TokenManager(secret_key="secret2" + "x" * 25, algorithm="HS256")

        token1 = manager1.create_access_token(data)
        token2 = manager2.create_access_token(data)

        # Tokens should differ due to different secret keys
        assert token1 != token2

        # Manager2 should not be able to decode Manager1's token
        with pytest.raises(JWTError):
            manager2.decode_token(token1)


# =============================================================================
# TOKEN REFRESH MECHANISM TESTS
# ISO 27001 A.9.4.2 - Secure log-on procedures
# =============================================================================

@pytest.mark.security
@pytest.mark.authentication
class TestTokenRefresh:
    """Test token refresh mechanisms."""

    def test_refresh_token_longer_expiration(self):
        """Test that refresh tokens have longer expiration than access tokens."""
        manager = TokenManager(
            secret_key=settings_config.JWT_SECRET_KEY,
            algorithm="HS256",
            access_token_expire_minutes=30,
            refresh_token_expire_days=7
        )

        data = {"sub": "test_user"}
        access_token = manager.create_access_token(data)
        refresh_token = manager.create_refresh_token(data)

        access_decoded = manager.decode_token(access_token)
        refresh_decoded = manager.decode_token(refresh_token)

        # Refresh token should expire later
        assert refresh_decoded["exp"] > access_decoded["exp"]

    def test_refresh_token_independent_validation(self, token_manager: TokenManager):
        """Test that refresh tokens can be validated independently."""
        data = {"sub": "test_user"}
        refresh_token = token_manager.create_refresh_token(data)

        decoded = token_manager.decode_token(refresh_token)
        assert decoded["sub"] == "test_user"


# =============================================================================
# PASSWORD STRENGTH VALIDATION TESTS
# OWASP ASVS 4.0 V2.1 - Password Security Requirements
# =============================================================================

@pytest.mark.security
@pytest.mark.authentication
class TestPasswordStrength:
    """Test password strength validation."""

    def test_validate_strong_password(self, password_manager: PasswordManager):
        """Test validation of strong passwords."""
        strong_passwords = [
            "SecureP@ssw0rd123!",
            "MyC0mplex!Pass",
            "Tr0ub4dor&3",
            "CorrectHorseBatteryStaple123!",  # XKCD style + requirements
        ]

        for password in strong_passwords:
            # Should be accepted (no exception)
            is_strong = password_manager.validate_password_strength(password)
            assert is_strong is True, f"Password should be strong: {password}"

    def test_validate_weak_passwords(self, password_manager: PasswordManager):
        """Test validation rejects weak passwords."""
        weak_passwords = [
            "password",  # Too common
            "12345678",  # Only numbers
            "abcdefgh",  # Only lowercase
            "ABCDEFGH",  # Only uppercase
            "Pass123",   # Too short
            "password123",  # No special chars
            "Password!",  # No numbers
        ]

        for password in weak_passwords:
            is_strong = password_manager.validate_password_strength(password)
            assert is_strong is False, f"Password should be weak: {password}"

    def test_password_minimum_length(self, password_manager: PasswordManager):
        """Test minimum password length requirement (8 characters)."""
        # 7 characters - should fail
        assert password_manager.validate_password_strength("Pass1!@") is False

        # 8 characters - should pass
        assert password_manager.validate_password_strength("Pass12!@") is True

    def test_password_complexity_requirements(self, password_manager: PasswordManager):
        """Test password complexity requirements."""
        # Missing uppercase
        assert password_manager.validate_password_strength("password123!") is False

        # Missing lowercase
        assert password_manager.validate_password_strength("PASSWORD123!") is False

        # Missing digit
        assert password_manager.validate_password_strength("Password!@#") is False

        # Missing special character
        assert password_manager.validate_password_strength("Password123") is False

        # Has all requirements
        assert password_manager.validate_password_strength("Password123!") is True


# =============================================================================
# ACCOUNT LOCKOUT TESTS
# ISO 27001 A.9.4.3 - Password management system
# OWASP ASVS 4.0 V2.2.1 - Anti-automation
# =============================================================================

@pytest.mark.security
@pytest.mark.authentication
class TestAccountLockout:
    """Test account lockout after failed login attempts."""

    def test_account_lockout_after_failed_attempts(self, password_manager: PasswordManager):
        """Test that account locks after 5 failed attempts."""
        username = "test_user"
        max_attempts = 5

        # Simulate failed login attempts
        for i in range(max_attempts):
            is_locked = password_manager.record_failed_attempt(username)
            if i < max_attempts - 1:
                assert is_locked is False, f"Account should not be locked at attempt {i+1}"
            else:
                assert is_locked is True, "Account should be locked after max attempts"

    def test_account_unlock_after_timeout(self, password_manager: PasswordManager):
        """Test that account unlocks after lockout period."""
        username = "test_user_timeout"
        max_attempts = 5

        # Lock the account
        for _ in range(max_attempts):
            password_manager.record_failed_attempt(username)

        # Account should be locked
        assert password_manager.is_account_locked(username) is True

        # Simulate lockout period (typically 15 minutes)
        # In real implementation, would wait or mock time
        password_manager.unlock_account(username)

        # Account should be unlocked
        assert password_manager.is_account_locked(username) is False

    def test_failed_attempts_reset_on_success(self, password_manager: PasswordManager):
        """Test that failed attempt counter resets on successful login."""
        username = "test_user_reset"

        # Record some failed attempts
        for _ in range(3):
            password_manager.record_failed_attempt(username)

        # Successful login should reset counter
        password_manager.reset_failed_attempts(username)

        # Account should not be locked
        assert password_manager.is_account_locked(username) is False

        # Counter should be reset (can do 5 more failed attempts)
        for i in range(5):
            is_locked = password_manager.record_failed_attempt(username)
            if i < 4:
                assert is_locked is False
            else:
                assert is_locked is True


# =============================================================================
# INTEGRATION TESTS
# End-to-end authentication flow testing
# =============================================================================

@pytest.mark.security
@pytest.mark.authentication
@pytest.mark.integration
@pytest.mark.asyncio
class TestAuthenticationIntegration:
    """Integration tests for complete authentication flow."""

    async def test_complete_login_flow(
        self,
        password_manager: PasswordManager,
        token_manager: TokenManager,
        test_user_data: Dict[str, str]
    ):
        """Test complete login flow: password verification + token generation."""
        # 1. User registration (hash password)
        password_hash = password_manager.hash_password(test_user_data["password"])

        # 2. User login (verify password)
        is_valid = password_manager.verify_password(test_user_data["password"], password_hash)
        assert is_valid is True

        # 3. Generate access token
        token_data = {
            "sub": test_user_data["username"],
            "role": test_user_data["role"],
            "email": test_user_data["email"]
        }
        access_token = token_manager.create_access_token(token_data)

        # 4. Verify token can be decoded
        decoded = token_manager.decode_token(access_token)
        assert decoded["sub"] == test_user_data["username"]
        assert decoded["role"] == test_user_data["role"]

    async def test_failed_login_flow(
        self,
        password_manager: PasswordManager,
        test_user_data: Dict[str, str]
    ):
        """Test failed login flow with incorrect password."""
        # 1. User registration
        password_hash = password_manager.hash_password(test_user_data["password"])

        # 2. Attempt login with wrong password
        wrong_password = "WrongPassword123!"
        is_valid = password_manager.verify_password(wrong_password, password_hash)
        assert is_valid is False

        # 3. No token should be generated (handled by application logic)

    async def test_token_based_authorization(
        self,
        token_manager: TokenManager,
        admin_user_data: Dict[str, str]
    ):
        """Test role-based authorization using JWT tokens."""
        # Generate token for admin user
        admin_token = token_manager.create_access_token({
            "sub": admin_user_data["username"],
            "role": admin_user_data["role"]
        })

        # Decode and verify role
        decoded = token_manager.decode_token(admin_token)
        assert decoded["role"] == "admin"

        # Application can now authorize based on role
        # (actual authorization logic tested in test_authorization.py)
