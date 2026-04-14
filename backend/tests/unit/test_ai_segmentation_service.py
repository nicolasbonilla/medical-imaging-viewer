"""
Unit tests for AISegmentationService — IEC 62304 Class C.

Tests verify AI segmentation service behavior including graceful
degradation when backends are unavailable (DD-AI-001).
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.core.interfaces.ai_interface import (
    AITaskStatus,
    InteractiveSegmentRequest,
    AutoSegmentRequest,
    AnomalyDetectionRequest,
    ClickPoint3D,
)


@pytest.mark.unit
class TestAISegmentationServiceInit:
    """Tests for AISegmentationService initialization (Class C — DD-AI-001)."""

    def test_service_initializes_without_cache(self):
        """Service initializes without a cache service."""
        from app.services.ai_segmentation_service import AISegmentationService

        service = AISegmentationService()
        assert service.cache_service is None
        assert isinstance(service._tasks, dict)

    def test_service_initializes_with_cache(self):
        """Service accepts an optional cache service."""
        from app.services.ai_segmentation_service import AISegmentationService

        mock_cache = MagicMock()
        service = AISegmentationService(cache_service=mock_cache)
        assert service.cache_service is mock_cache


@pytest.mark.unit
class TestSegmentInteractive:
    """Tests for segment_interactive — graceful degradation (Class C — DD-AI-001)."""

    def setup_method(self):
        from app.services.ai_segmentation_service import AISegmentationService

        self.service = AISegmentationService()

    @pytest.mark.asyncio
    async def test_returns_failed_status(self):
        """Interactive segmentation returns FAILED (not yet available)."""
        request = InteractiveSegmentRequest(
            file_id="test-file-123",
            click_points=[ClickPoint3D(x=50, y=50, z=25, label="positive")],
        )
        result = await self.service.segment_interactive(request)
        assert result.status == AITaskStatus.FAILED
        assert result.task_id  # Must have a task_id
        assert result.error is not None
        assert "not yet available" in result.error.lower()

    @pytest.mark.asyncio
    async def test_returns_unique_task_id(self):
        """Each call returns a unique task_id."""
        request = InteractiveSegmentRequest(
            file_id="test-file-123",
            click_points=[ClickPoint3D(x=10, y=20, z=5, label="positive")],
        )
        result1 = await self.service.segment_interactive(request)
        result2 = await self.service.segment_interactive(request)
        assert result1.task_id != result2.task_id


@pytest.mark.unit
class TestSegmentAuto:
    """Tests for segment_auto — graceful degradation (Class C — DD-AI-001)."""

    def setup_method(self):
        from app.services.ai_segmentation_service import AISegmentationService

        self.service = AISegmentationService()

    @pytest.mark.asyncio
    async def test_no_tool_runner_returns_failed(self):
        """Without ToolRunnerService, returns FAILED with informative error."""
        request = AutoSegmentRequest(file_id="test-file-123")

        with patch(
            "app.core.container.get_tool_runner_service",
            side_effect=ImportError("No tool runner"),
        ):
            result = await self.service.segment_auto(request)

        assert result.status == AITaskStatus.FAILED
        assert result.error is not None
        assert "synthseg" in result.error.lower() or "not configured" in result.error.lower()

    @pytest.mark.asyncio
    async def test_tool_runner_available_delegates(self):
        """When ToolRunnerService is available and SynthSeg configured, delegates."""
        request = AutoSegmentRequest(file_id="test-file-123")

        mock_runner = MagicMock()
        mock_runner.is_synthseg_available.return_value = True
        mock_runner.run_synthseg = AsyncMock(return_value="task-abc")
        mock_task = MagicMock()
        mock_task.task_id = "task-abc"
        mock_task.progress = 10.0
        mock_runner.get_task_status = AsyncMock(return_value=mock_task)

        with patch(
            "app.core.container.get_tool_runner_service",
            return_value=mock_runner,
        ):
            result = await self.service.segment_auto(request)

        assert result.status == AITaskStatus.PROCESSING
        assert result.task_id == "task-abc"
        mock_runner.run_synthseg.assert_awaited_once_with("test-file-123")

    @pytest.mark.asyncio
    async def test_tool_runner_synthseg_not_available(self):
        """When SynthSeg is not available, returns FAILED."""
        request = AutoSegmentRequest(file_id="test-file-123")

        mock_runner = MagicMock()
        mock_runner.is_synthseg_available.return_value = False

        with patch(
            "app.core.container.get_tool_runner_service",
            return_value=mock_runner,
        ):
            result = await self.service.segment_auto(request)

        assert result.status == AITaskStatus.FAILED


@pytest.mark.unit
class TestDetectAnomalies:
    """Tests for detect_anomalies — graceful degradation (Class C — DD-AI-001)."""

    def setup_method(self):
        from app.services.ai_segmentation_service import AISegmentationService

        self.service = AISegmentationService()

    @pytest.mark.asyncio
    async def test_returns_empty_result(self):
        """Anomaly detection returns empty result (not yet available)."""
        request = AnomalyDetectionRequest(file_id="test-file-123", sensitivity="medium")
        result = await self.service.detect_anomalies(request)
        assert result is not None
        assert result.anomalies == []
        assert result.overall_confidence == 0.0
        assert result.processing_time_ms == 0

    @pytest.mark.asyncio
    async def test_all_sensitivity_levels_accepted(self):
        """All valid sensitivity levels are accepted without error."""
        for level in ("low", "medium", "high"):
            request = AnomalyDetectionRequest(file_id="test-file", sensitivity=level)
            result = await self.service.detect_anomalies(request)
            assert result.anomalies == []


@pytest.mark.unit
class TestGetTaskStatus:
    """Tests for get_task_status (Class C — DD-AI-001)."""

    def setup_method(self):
        from app.services.ai_segmentation_service import AISegmentationService

        self.service = AISegmentationService()

    @pytest.mark.asyncio
    async def test_unknown_task_returns_failed(self):
        """Unknown task_id returns FAILED with 'Task not found' error."""
        result = await self.service.get_task_status("nonexistent-task-id")
        assert result.status == AITaskStatus.FAILED
        assert result.error == "Task not found"
        assert result.task_id == "nonexistent-task-id"

    @pytest.mark.asyncio
    async def test_local_task_found(self):
        """Task stored in local _tasks dict is returned."""
        from app.core.interfaces.ai_interface import AITaskResult

        task = AITaskResult(
            task_id="local-task-1",
            status=AITaskStatus.COMPLETED,
            segmentation_id="seg-001",
        )
        self.service._tasks["local-task-1"] = task

        result = await self.service.get_task_status("local-task-1")
        assert result.status == AITaskStatus.COMPLETED
        assert result.segmentation_id == "seg-001"


@pytest.mark.unit
class TestListAvailableModels:
    """Tests for list_available_models (Class C — DD-AI-001)."""

    def setup_method(self):
        from app.services.ai_segmentation_service import AISegmentationService

        self.service = AISegmentationService()

    @pytest.mark.asyncio
    async def test_returns_list_of_models(self):
        """Returns a list with known model entries."""
        result = await self.service.list_available_models()
        assert isinstance(result, list)
        assert len(result) >= 2  # At least synthseg + lst-ai

    @pytest.mark.asyncio
    async def test_each_model_has_required_fields(self):
        """Each model dict has id, name, type, and description."""
        result = await self.service.list_available_models()
        for model in result:
            assert "id" in model
            assert "name" in model
            assert "type" in model
            assert "description" in model

    @pytest.mark.asyncio
    async def test_synthseg_model_present(self):
        """SynthSeg model is always present in the list."""
        result = await self.service.list_available_models()
        ids = [m["id"] for m in result]
        assert "synthseg" in ids

    @pytest.mark.asyncio
    async def test_graceful_when_tool_runner_unavailable(self):
        """Models list still returns when ToolRunnerService is not available."""
        with patch(
            "app.core.container.get_tool_runner_service",
            side_effect=ImportError("not available"),
        ):
            result = await self.service.list_available_models()
        assert isinstance(result, list)
        # All models should show configured=False
        for model in result:
            if "configured" in model:
                assert model["configured"] is False


@pytest.mark.unit
class TestGetSynthSegLabels:
    """Tests for get_synthseg_labels static method (Class C — DD-AI-001)."""

    def test_returns_dict(self):
        """Returns a dict mapping int -> tuple."""
        from app.services.ai_segmentation_service import AISegmentationService

        labels = AISegmentationService.get_synthseg_labels()
        assert isinstance(labels, dict)
        assert len(labels) > 0

    def test_background_label_present(self):
        """Background label (0) is present."""
        from app.services.ai_segmentation_service import AISegmentationService

        labels = AISegmentationService.get_synthseg_labels()
        assert 0 in labels
        name, color = labels[0]
        assert name == "Background"

    def test_label_values_are_name_color_tuples(self):
        """Each label value is a (name, color_hex) tuple."""
        from app.services.ai_segmentation_service import AISegmentationService

        labels = AISegmentationService.get_synthseg_labels()
        for label_id, value in labels.items():
            assert isinstance(label_id, int)
            assert isinstance(value, tuple)
            assert len(value) == 2
            name, color = value
            assert isinstance(name, str)
            assert color.startswith("#")
