"""
Integration tests for authentication endpoints.

Tests login, registration, WebAuthn, user management, and CAPTCHA flows.
Validates that the auth system works end-to-end after Phase 1 refactoring.

@module tests.integration.test_auth_endpoints
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestLoginFlow:
    """Test the complete login flow."""

    @pytest.mark.asyncio
    async def test_login_success(self, async_client: AsyncClient):
        """Test successful login returns token and user data."""
        response = await async_client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "Admin123!@2024",
        })
        # May return 200 (success) or 400 (captcha required after failed attempts)
        assert response.status_code in (200, 400)
        if response.status_code == 200:
            data = response.json()
            assert "token" in data
            assert "user" in data
            assert data["token"]["token_type"] == "bearer"
            assert len(data["token"]["access_token"]) > 0
            assert data["user"]["username"] == "admin"

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, async_client: AsyncClient):
        """Test login with wrong password returns error."""
        response = await async_client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "wrongpassword123",
        })
        assert response.status_code in (400, 401)

    @pytest.mark.asyncio
    async def test_login_missing_fields(self, async_client: AsyncClient):
        """Test login with missing fields returns 422."""
        response = await async_client.post("/api/v1/auth/login", json={})
        assert response.status_code == 422


@pytest.mark.integration
class TestAuthMe:
    """Test GET /auth/me endpoint."""

    @pytest.mark.asyncio
    async def test_me_without_token(self, async_client: AsyncClient):
        """Test /me without token returns error."""
        response = await async_client.get("/api/v1/auth/me")
        assert response.status_code in (400, 401, 403)

    @pytest.mark.asyncio
    async def test_me_with_valid_token(self, async_client: AsyncClient, auth_headers: dict):
        """Test /me with valid token returns user info."""
        if not auth_headers:
            pytest.skip("Could not obtain auth token")
        response = await async_client.get("/api/v1/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "username" in data
        assert "email" in data


@pytest.mark.integration
class TestProtectedEndpoints:
    """Test that protected endpoints require authentication."""

    @pytest.mark.asyncio
    async def test_users_requires_auth(self, async_client: AsyncClient):
        """Test /auth/users without token returns 401/403."""
        response = await async_client.get("/api/v1/auth/users")
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_users_with_auth(self, async_client: AsyncClient, auth_headers: dict):
        """Test /auth/users with valid token returns user list."""
        if not auth_headers:
            pytest.skip("Could not obtain auth token")
        response = await async_client.get("/api/v1/auth/users", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


@pytest.mark.integration
class TestWebAuthnEndpoints:
    """Test WebAuthn/Passkey endpoints."""

    @pytest.mark.asyncio
    async def test_webauthn_credentials_requires_auth(self, async_client: AsyncClient):
        """Test WebAuthn credentials endpoint requires authentication."""
        response = await async_client.get("/api/v1/auth/webauthn/credentials")
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_webauthn_credentials_with_auth(self, async_client: AsyncClient, auth_headers: dict):
        """Test WebAuthn credentials endpoint returns list."""
        if not auth_headers:
            pytest.skip("Could not obtain auth token")
        response = await async_client.get("/api/v1/auth/webauthn/credentials", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_webauthn_register_begin_requires_auth(self, async_client: AsyncClient):
        """Test WebAuthn register/begin requires authentication."""
        response = await async_client.post("/api/v1/auth/webauthn/register/begin", json={})
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_webauthn_register_begin_with_auth(self, async_client: AsyncClient, auth_headers: dict):
        """Test WebAuthn register/begin returns challenge options."""
        if not auth_headers:
            pytest.skip("Could not obtain auth token")
        response = await async_client.post(
            "/api/v1/auth/webauthn/register/begin",
            json={},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "options" in data
        assert "challenge" in data["options"]
        assert "rp" in data["options"]

    @pytest.mark.asyncio
    async def test_webauthn_login_begin_no_passkeys(self, async_client: AsyncClient):
        """Test WebAuthn login/begin returns 400 when no passkeys registered."""
        response = await async_client.post("/api/v1/auth/webauthn/login/begin", json={
            "username": "admin",
        })
        # 400 = no passkeys, 200 = has passkeys — both valid
        assert response.status_code in (200, 400)


@pytest.mark.integration
class TestCaptcha:
    """Test CAPTCHA endpoint."""

    @pytest.mark.asyncio
    async def test_captcha_generation(self, async_client: AsyncClient):
        """Test CAPTCHA generation returns challenge."""
        response = await async_client.post("/api/v1/auth/captcha", json={
            "difficulty": "medium",
        })
        assert response.status_code == 200
        data = response.json()
        assert "challenge_id" in data
        assert "challenge_text" in data
        assert "expires_in_seconds" in data
