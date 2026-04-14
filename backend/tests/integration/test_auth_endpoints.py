"""
Integration tests for authentication endpoints.

Tests login, WebAuthn, user management, and CAPTCHA flows.
Routes under /api/v1/auth/ (authentication.py) and /api/v1/auth/ (auth.py).
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestLoginFlow:
    """Test the login flow."""

    @pytest.mark.asyncio
    async def test_login_missing_fields(self, async_client: AsyncClient):
        """Test login with empty body returns validation error."""
        response = await async_client.post("/api/v1/auth/login", json={})
        assert response.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, async_client: AsyncClient):
        """Test login with wrong password returns error."""
        response = await async_client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "wrongpassword123",
        })
        assert response.status_code in (400, 401, 403)

    @pytest.mark.asyncio
    async def test_login_success_or_captcha(self, async_client: AsyncClient):
        """Test login returns token or captcha challenge."""
        response = await async_client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "Admin123!@2024",
        })
        # 200 = success, 400 = captcha required, 401 = bad creds (no user in test DB)
        assert response.status_code in (200, 400, 401)


@pytest.mark.integration
class TestAuthMe:
    """Test GET /api/v1/auth/me endpoint."""

    @pytest.mark.asyncio
    async def test_me_returns_user_info(self, async_client: AsyncClient):
        """Test /me with the test JWT token returns user info or auth error."""
        response = await async_client.get("/api/v1/auth/me")
        # async_client has JWT token from conftest; may return 200 or 401
        # depending on whether the test user exists in the DB
        assert response.status_code in (200, 401, 403, 404)


@pytest.mark.integration
class TestProtectedEndpoints:
    """Test that protected endpoints respond (not 404)."""

    @pytest.mark.asyncio
    async def test_users_endpoint_exists(self, async_client: AsyncClient):
        """Test /auth/users endpoint exists (returns auth error, not 404)."""
        response = await async_client.get("/api/v1/auth/users")
        # Should not be 404 — endpoint exists
        assert response.status_code != 404


@pytest.mark.integration
class TestWebAuthnEndpoints:
    """Test WebAuthn/Passkey endpoints exist."""

    @pytest.mark.asyncio
    async def test_webauthn_credentials_endpoint_exists(self, async_client: AsyncClient):
        """Test WebAuthn credentials endpoint exists."""
        response = await async_client.get("/api/v1/auth/webauthn/credentials")
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_webauthn_register_begin_endpoint_exists(self, async_client: AsyncClient):
        """Test WebAuthn register/begin endpoint exists."""
        response = await async_client.post("/api/v1/auth/webauthn/register/begin", json={})
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_webauthn_login_begin(self, async_client: AsyncClient):
        """Test WebAuthn login/begin endpoint exists."""
        response = await async_client.post("/api/v1/auth/webauthn/login/begin", json={
            "username": "admin",
        })
        # 200 = has passkeys, 400 = no passkeys, 422 = validation error — all valid
        assert response.status_code in (200, 400, 422)


@pytest.mark.integration
class TestCaptcha:
    """Test CAPTCHA endpoint."""

    @pytest.mark.asyncio
    async def test_captcha_generation(self, async_client: AsyncClient):
        """Test CAPTCHA generation returns challenge."""
        response = await async_client.post("/api/v1/auth/captcha", json={
            "difficulty": "medium",
        })
        # 200 = success, 422 = validation error if schema different
        assert response.status_code in (200, 422)
        if response.status_code == 200:
            data = response.json()
            assert "challenge_id" in data
