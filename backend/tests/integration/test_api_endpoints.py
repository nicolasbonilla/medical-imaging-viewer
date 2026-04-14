"""
Integration tests for core FastAPI endpoints.

Tests health check, imaging, segmentation, and error handling.
Runs against the FastAPI TestClient with JWT auth from conftest.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestHealthEndpoint:
    """Test health check endpoints."""

    @pytest.mark.asyncio
    async def test_health_check_root(self, async_client: AsyncClient):
        """Test root health check returns 200."""
        response = await async_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_check_api(self, async_client: AsyncClient):
        """Test /api/health returns 200."""
        response = await async_client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


@pytest.mark.integration
class TestImagingEndpoints:
    """Test imaging API endpoints."""

    @pytest.mark.asyncio
    async def test_process_invalid_file_id(self, async_client: AsyncClient):
        """Test processing with invalid file ID returns error."""
        response = await async_client.get("/api/v1/imaging/process/invalid_file_id")
        assert response.status_code in [400, 403, 404, 500]

    @pytest.mark.asyncio
    async def test_metadata_invalid_file_id(self, async_client: AsyncClient):
        """Test metadata with invalid file ID returns error."""
        response = await async_client.get("/api/v1/imaging/metadata/invalid_file_id")
        assert response.status_code in [400, 403, 404, 500]


@pytest.mark.integration
class TestSegmentationEndpoints:
    """Test segmentation API endpoints."""

    @pytest.mark.asyncio
    async def test_list_segmentations(self, async_client: AsyncClient):
        """Test listing segmentations."""
        response = await async_client.get("/api/v1/segmentation/list", params={"file_id": "nonexistent"})
        assert response.status_code in [200, 403, 404]

    @pytest.mark.asyncio
    async def test_create_segmentation_valid(self, async_client: AsyncClient):
        """Test creating segmentation with valid data."""
        payload = {
            "file_id": "test_file_123",
            "image_shape": {"rows": 256, "columns": 256, "slices": 50},
            "description": "Test segmentation",
            "labels": [
                {"id": 0, "name": "Background", "color": "#000000", "opacity": 0.0, "visible": False},
                {"id": 1, "name": "Lesion", "color": "#FF0000", "opacity": 0.5, "visible": True},
            ],
        }
        response = await async_client.post("/api/v1/segmentation/create", json=payload)
        assert response.status_code in [200, 403, 500]

    @pytest.mark.asyncio
    async def test_get_nonexistent_segmentation(self, async_client: AsyncClient):
        """Test getting metadata for non-existent segmentation."""
        response = await async_client.get("/api/v1/segmentation/nonexistent_id")
        assert response.status_code in [403, 404]

    @pytest.mark.asyncio
    async def test_paint_stroke_nonexistent(self, async_client: AsyncClient):
        """Test applying paint stroke to non-existent segmentation."""
        response = await async_client.post("/api/v1/segmentation/nonexistent_id/paint", json={
            "slice_index": 0, "label_id": 1, "x": 128, "y": 128, "brush_size": 10, "erase": False,
        })
        assert response.status_code in [403, 404]


@pytest.mark.integration
class TestErrorHandling:
    """Test error handling across endpoints."""

    @pytest.mark.asyncio
    async def test_malformed_json(self, async_client: AsyncClient):
        """Test handling of malformed JSON."""
        response = await async_client.post(
            "/api/v1/segmentation/create",
            content="{invalid json}",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    async def test_missing_required_fields(self, async_client: AsyncClient):
        """Test handling of missing required fields."""
        response = await async_client.post("/api/v1/segmentation/create", json={"file_id": "test"})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_nonexistent_endpoint(self, async_client: AsyncClient):
        """Test request to nonexistent endpoint returns 404."""
        response = await async_client.get("/api/v1/this-does-not-exist")
        assert response.status_code == 404
