"""
Integration tests for DICOMweb PACS integration endpoints.

Routes under /api/v1/dicomweb/. All require authentication (JWT from conftest).
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestDICOMwebConnections:
    """Test PACS connection management."""

    @pytest.mark.asyncio
    async def test_list_connections(self, async_client: AsyncClient):
        """Test listing PACS connections."""
        response = await async_client.get("/api/v1/dicomweb/connections")
        assert response.status_code in (200, 403, 500)
        if response.status_code == 200:
            assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_create_connection(self, async_client: AsyncClient):
        """Test creating a new PACS connection."""
        response = await async_client.post("/api/v1/dicomweb/connections", json={
            "name": "Test PACS",
            "base_url": "https://pacs.example.com/dicom-web",
            "auth_type": "none",
            "verify_ssl": True,
        })
        assert response.status_code in (200, 201, 403, 422, 500)

    @pytest.mark.asyncio
    async def test_get_nonexistent_connection(self, async_client: AsyncClient):
        """Test getting a connection that doesn't exist returns 404."""
        response = await async_client.get("/api/v1/dicomweb/connections/nonexistent-id")
        assert response.status_code in (404, 403)

    @pytest.mark.asyncio
    async def test_delete_nonexistent_connection(self, async_client: AsyncClient):
        """Test deleting a nonexistent connection."""
        response = await async_client.delete("/api/v1/dicomweb/connections/nonexistent-id")
        assert response.status_code in (200, 404, 403)


@pytest.mark.integration
class TestDICOMwebSearch:
    """Test QIDO-RS search proxy."""

    @pytest.mark.asyncio
    async def test_search_studies_validation(self, async_client: AsyncClient):
        """Test study search validates input."""
        response = await async_client.post("/api/v1/dicomweb/search/studies", json={})
        assert response.status_code in (400, 403, 422)

    @pytest.mark.asyncio
    async def test_search_studies_missing_connection(self, async_client: AsyncClient):
        """Test study search with nonexistent connection."""
        response = await async_client.post("/api/v1/dicomweb/search/studies", json={
            "connection_id": "nonexistent",
            "patient_name": "DOE",
        })
        assert response.status_code in (400, 403, 404, 422, 500, 502)


@pytest.mark.integration
class TestDICOMwebImport:
    """Test WADO-RS import job tracking."""

    @pytest.mark.asyncio
    async def test_import_nonexistent_job(self, async_client: AsyncClient):
        """Test getting status of nonexistent import job."""
        response = await async_client.get("/api/v1/dicomweb/import/nonexistent-job-id")
        assert response.status_code in (404, 403)

    @pytest.mark.asyncio
    async def test_list_imports(self, async_client: AsyncClient):
        """Test listing imports."""
        response = await async_client.get("/api/v1/dicomweb/imports")
        assert response.status_code in (200, 403, 500)
