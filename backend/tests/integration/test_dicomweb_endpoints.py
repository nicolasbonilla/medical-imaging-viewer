"""
Integration tests for DICOMweb PACS integration endpoints.

Tests connection management, QIDO-RS search proxy, and import job tracking.

@module tests.integration.test_dicomweb_endpoints
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestDICOMwebConnections:
    """Test PACS connection management."""

    @pytest.mark.asyncio
    async def test_list_connections_empty(self, async_client: AsyncClient):
        """Test listing connections when none exist."""
        response = await async_client.get("/api/v1/dicomweb/connections")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_create_connection(self, async_client: AsyncClient):
        """Test creating a new PACS connection."""
        response = await async_client.post("/api/v1/dicomweb/connections", json={
            "name": "Test PACS",
            "base_url": "https://pacs.example.com/dicom-web",
            "auth_type": "none",
            "verify_ssl": True,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test PACS"
        assert data["base_url"] == "https://pacs.example.com/dicom-web"
        assert data["password"] == "***"  # Credentials redacted
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_connection_with_basic_auth(self, async_client: AsyncClient):
        """Test creating connection with basic auth (password redacted in response)."""
        response = await async_client.post("/api/v1/dicomweb/connections", json={
            "name": "Auth PACS",
            "base_url": "https://secure-pacs.example.com/dicom-web",
            "auth_type": "basic",
            "username": "dicomuser",
            "password": "secretpassword",
            "verify_ssl": True,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["password"] == "***"
        assert data["auth_type"] == "basic"

    @pytest.mark.asyncio
    async def test_get_nonexistent_connection(self, async_client: AsyncClient):
        """Test getting a connection that doesn't exist."""
        response = await async_client.get("/api/v1/dicomweb/connections/nonexistent-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_connection(self, async_client: AsyncClient):
        """Test deleting a connection."""
        response = await async_client.delete("/api/v1/dicomweb/connections/some-id")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_test_connection_nonexistent(self, async_client: AsyncClient):
        """Test testing a nonexistent connection."""
        response = await async_client.post("/api/v1/dicomweb/connections/nonexistent-id/test")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False


@pytest.mark.integration
class TestDICOMwebSearch:
    """Test QIDO-RS search proxy."""

    @pytest.mark.asyncio
    async def test_search_studies_missing_connection(self, async_client: AsyncClient):
        """Test study search with nonexistent connection returns error."""
        response = await async_client.post("/api/v1/dicomweb/search/studies", json={
            "connection_id": "nonexistent",
            "patient_name": "DOE",
        })
        assert response.status_code in (400, 502)

    @pytest.mark.asyncio
    async def test_search_studies_validation(self, async_client: AsyncClient):
        """Test study search validates input."""
        response = await async_client.post("/api/v1/dicomweb/search/studies", json={})
        assert response.status_code == 422  # Missing required field: connection_id


@pytest.mark.integration
class TestDICOMwebImport:
    """Test WADO-RS import job tracking."""

    @pytest.mark.asyncio
    async def test_import_nonexistent_job(self, async_client: AsyncClient):
        """Test getting status of nonexistent import job."""
        response = await async_client.get("/api/v1/dicomweb/import/nonexistent-job-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_imports_empty(self, async_client: AsyncClient):
        """Test listing imports when none exist."""
        response = await async_client.get("/api/v1/dicomweb/imports")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
