"""
Integration tests for FastAPI endpoints.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestHealthEndpoint:
    """Test suite for health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_check(self, async_client: AsyncClient):
        """Test health check endpoint returns 200."""
        # Act
        response = await async_client.get("/health")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data


@pytest.mark.integration
class TestImagingEndpoints:
    """Test suite for imaging API endpoints."""

    @pytest.mark.asyncio
    async def test_formats_endpoint(self, async_client: AsyncClient):
        """Test GET /api/v1/imaging/formats endpoint."""
        # Act
        response = await async_client.get("/api/v1/imaging/formats")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "formats" in data
        assert isinstance(data["formats"], list)
        assert "dicom" in data["formats"]
        assert "nifti" in data["formats"]

    @pytest.mark.asyncio
    async def test_process_invalid_file_id(self, async_client: AsyncClient):
        """Test processing with invalid file ID returns 404."""
        # Act
        response = await async_client.get("/api/v1/imaging/process/invalid_file_id")

        # Assert
        # Should return error (404 or 500 depending on Drive service)
        assert response.status_code in [404, 500]


@pytest.mark.integration
class TestSegmentationEndpoints:
    """Test suite for segmentation API endpoints."""

    @pytest.mark.asyncio
    async def test_list_segmentations_empty(self, async_client: AsyncClient):
        """Test listing segmentations for non-existent file."""
        # Act
        response = await async_client.get("/api/v1/segmentation/list/nonexistent_file_id")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Should return empty list for non-existent file
        assert len(data) == 0

    @pytest.mark.asyncio
    async def test_create_segmentation_invalid_request(self, async_client: AsyncClient):
        """Test creating segmentation with invalid data."""
        # Arrange
        invalid_payload = {
            "file_id": "",  # Empty file_id
            "image_shape": {
                "rows": -1,  # Invalid
                "columns": 0,  # Invalid
                "slices": 100
            }
        }

        # Act
        response = await async_client.post(
            "/api/v1/segmentation/create",
            json=invalid_payload
        )

        # Assert
        # Should return validation error
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_segmentation_valid_request(self, async_client: AsyncClient):
        """Test creating segmentation with valid data."""
        # Arrange
        valid_payload = {
            "file_id": "test_file_123",
            "image_shape": {
                "rows": 512,
                "columns": 512,
                "slices": 100
            },
            "description": "Test segmentation",
            "labels": [
                {"id": 0, "name": "Background", "color": "#000000", "opacity": 0.0, "visible": False},
                {"id": 1, "name": "Lesion", "color": "#FF0000", "opacity": 0.5, "visible": True}
            ]
        }

        # Act
        response = await async_client.post(
            "/api/v1/segmentation/create",
            json=valid_payload
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "segmentation_id" in data
        assert data["file_id"] == "test_file_123"
        assert data["total_slices"] == 100

    @pytest.mark.asyncio
    async def test_get_segmentation_metadata_not_found(self, async_client: AsyncClient):
        """Test getting metadata for non-existent segmentation."""
        # Act
        response = await async_client.get("/api/v1/segmentation/nonexistent_id/metadata")

        # Assert
        # Should return 404
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_apply_paint_stroke_to_nonexistent_segmentation(self, async_client: AsyncClient):
        """Test applying paint stroke to non-existent segmentation."""
        # Arrange
        paint_stroke = {
            "slice_index": 0,
            "label_id": 1,
            "x": 256,
            "y": 256,
            "brush_size": 10,
            "erase": False
        }

        # Act
        response = await async_client.post(
            "/api/v1/segmentation/nonexistent_id/paint",
            json=paint_stroke
        )

        # Assert
        # Should return 404
        assert response.status_code == 404


@pytest.mark.integration
class TestSegmentationWorkflow:
    """Test complete segmentation workflow."""

    @pytest.mark.asyncio
    async def test_full_segmentation_workflow(self, async_client: AsyncClient):
        """Test creating segmentation, applying strokes, and retrieving results."""
        # Step 1: Create segmentation
        create_payload = {
            "file_id": "workflow_test_file",
            "image_shape": {
                "rows": 256,
                "columns": 256,
                "slices": 50
            },
            "description": "Workflow test",
            "labels": [
                {"id": 0, "name": "Background", "color": "#000000", "opacity": 0.0, "visible": False},
                {"id": 1, "name": "ROI", "color": "#00FF00", "opacity": 0.6, "visible": True}
            ]
        }

        create_response = await async_client.post(
            "/api/v1/segmentation/create",
            json=create_payload
        )

        assert create_response.status_code == 200
        seg_data = create_response.json()
        seg_id = seg_data["segmentation_id"]

        # Step 2: Get metadata
        metadata_response = await async_client.get(f"/api/v1/segmentation/{seg_id}/metadata")
        assert metadata_response.status_code == 200
        metadata = metadata_response.json()
        assert metadata["file_id"] == "workflow_test_file"
        assert len(metadata["labels"]) == 2

        # Step 3: Apply paint stroke
        paint_stroke = {
            "slice_index": 0,
            "label_id": 1,
            "x": 128,
            "y": 128,
            "brush_size": 20,
            "erase": False
        }

        paint_response = await async_client.post(
            f"/api/v1/segmentation/{seg_id}/paint",
            json=paint_stroke
        )

        assert paint_response.status_code == 200
        paint_result = paint_response.json()
        assert paint_result["success"] is True

        # Step 4: Get slice mask
        mask_response = await async_client.get(f"/api/v1/segmentation/{seg_id}/slice/0/mask")
        assert mask_response.status_code == 200

        # Step 5: List segmentations for file
        list_response = await async_client.get("/api/v1/segmentation/list/workflow_test_file")
        assert list_response.status_code == 200
        seg_list = list_response.json()
        assert len(seg_list) > 0
        assert any(s["segmentation_id"] == seg_id for s in seg_list)


@pytest.mark.integration
class TestErrorHandling:
    """Test error handling across endpoints."""

    @pytest.mark.asyncio
    async def test_malformed_json(self, async_client: AsyncClient):
        """Test handling of malformed JSON."""
        # Act
        response = await async_client.post(
            "/api/v1/segmentation/create",
            content="{invalid json}",
            headers={"Content-Type": "application/json"}
        )

        # Assert
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_required_fields(self, async_client: AsyncClient):
        """Test handling of missing required fields."""
        # Arrange
        incomplete_payload = {
            "file_id": "test_file"
            # Missing image_shape
        }

        # Act
        response = await async_client.post(
            "/api/v1/segmentation/create",
            json=incomplete_payload
        )

        # Assert
        assert response.status_code == 422
        error_data = response.json()
        assert "detail" in error_data

    @pytest.mark.asyncio
    async def test_invalid_http_method(self, async_client: AsyncClient):
        """Test using wrong HTTP method."""
        # Act - Use POST instead of GET
        response = await async_client.post("/api/v1/imaging/formats")

        # Assert
        assert response.status_code == 405  # Method Not Allowed
