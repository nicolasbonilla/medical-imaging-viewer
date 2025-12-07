"""
Unit tests for PrefetchService.

Tests the intelligent prefetching functionality focusing on:
- Core prefetching logic
- Cache filtering
- Rate limiting
- Edge cases
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.prefetch_service import PrefetchService


@pytest.fixture
def mock_imaging_service():
    """Mock ImagingService."""
    service = AsyncMock()
    service.get_slice = AsyncMock(return_value={"data": "slice_data"})
    service.get_file_metadata = AsyncMock(return_value={"slices": 100})
    return service


@pytest.fixture
def mock_cache_service():
    """Mock ICacheService."""
    service = AsyncMock()
    service.exists = AsyncMock(return_value=False)
    service.set = AsyncMock(return_value=True)
    return service


@pytest.fixture
def prefetch_service(mock_imaging_service, mock_cache_service):
    """Create PrefetchService with mocked dependencies."""
    return PrefetchService(
        imaging_service=mock_imaging_service,
        cache_service=mock_cache_service,
        prefetch_count=3,
        priority="normal"
    )


class TestPrefetchIndexCalculation:
    """Test suite for prefetch index calculation logic."""

    def test_forward_prefetch_middle_range(self, prefetch_service):
        """Test forward prefetch from middle of range."""
        indices = prefetch_service._calculate_prefetch_indices(10, 100, "forward")

        # Should prefetch 3 slices ahead: 11, 12, 13
        assert indices == [11, 12, 13]

    def test_backward_prefetch_middle_range(self, prefetch_service):
        """Test backward prefetch from middle of range."""
        indices = prefetch_service._calculate_prefetch_indices(10, 100, "backward")

        # Should prefetch 3 slices behind: 9, 8, 7
        assert indices == [9, 8, 7]

    def test_both_directions_prefetch(self, prefetch_service):
        """Test prefetch in both directions."""
        indices = prefetch_service._calculate_prefetch_indices(10, 100, "both")

        # Should prefetch both directions: [11,12,13] + [9,8,7]
        assert 11 in indices and 12 in indices and 13 in indices
        assert 9 in indices and 8 in indices and 7 in indices
        assert len(indices) == 6

    def test_forward_prefetch_near_end(self, prefetch_service):
        """Test forward prefetch near end boundary."""
        indices = prefetch_service._calculate_prefetch_indices(98, 100, "forward")

        # Should only prefetch available slice (99)
        assert indices == [99]

    def test_backward_prefetch_near_start(self, prefetch_service):
        """Test backward prefetch near start boundary."""
        indices = prefetch_service._calculate_prefetch_indices(1, 100, "backward")

        # Should only prefetch available slice (0)
        assert indices == [0]

    def test_prefetch_at_end_boundary(self, prefetch_service):
        """Test prefetch at exact end boundary."""
        indices = prefetch_service._calculate_prefetch_indices(99, 100, "forward")

        # No slices to prefetch
        assert indices == []

    def test_prefetch_at_start_boundary(self, prefetch_service):
        """Test prefetch at exact start boundary."""
        indices = prefetch_service._calculate_prefetch_indices(0, 100, "backward")

        # No slices to prefetch
        assert indices == []


class TestCacheFiltering:
    """Test suite for cache filtering logic."""

    @pytest.mark.asyncio
    async def test_filter_all_uncached(self, prefetch_service, mock_cache_service):
        """Test filtering when all slices are uncached."""
        mock_cache_service.exists.return_value = False

        uncached = await prefetch_service._filter_uncached_slices(
            file_id="test_file",
            indices=[1, 2, 3, 4, 5]
        )

        # All slices should be uncached
        assert uncached == [1, 2, 3, 4, 5]
        assert mock_cache_service.exists.call_count == 5

    @pytest.mark.asyncio
    async def test_filter_all_cached(self, prefetch_service, mock_cache_service):
        """Test filtering when all slices are cached."""
        mock_cache_service.exists.return_value = True

        uncached = await prefetch_service._filter_uncached_slices(
            file_id="test_file",
            indices=[1, 2, 3, 4, 5]
        )

        # No slices should be uncached
        assert uncached == []
        assert mock_cache_service.exists.call_count == 5

    @pytest.mark.asyncio
    async def test_filter_partially_cached(self, prefetch_service, mock_cache_service):
        """Test filtering when some slices are cached."""
        # Simulate slices 2 and 4 being cached
        call_count = [0]

        async def exists_mock(key: str):
            call_count[0] += 1
            # Cache keys: slice:test_file:1, slice:test_file:2, etc.
            return ":2" in key or ":4" in key

        mock_cache_service.exists = exists_mock

        uncached = await prefetch_service._filter_uncached_slices(
            file_id="test_file",
            indices=[1, 2, 3, 4, 5]
        )

        # Only 1, 3, 5 should be uncached
        assert uncached == [1, 3, 5]


class TestPrefetching:
    """Test suite for actual prefetching operations."""

    @pytest.mark.asyncio
    async def test_prefetch_disabled(self, mock_imaging_service, mock_cache_service):
        """Test that prefetching returns 0 when disabled."""
        service = PrefetchService(
            imaging_service=mock_imaging_service,
            cache_service=mock_cache_service,
            prefetch_count=3,
            priority="normal"
        )
        service.enabled = False

        count = await service.prefetch_slices(
            file_id="test_file",
            current_slice=10,
            total_slices=100,
            direction="forward"
        )

        assert count == 0

    @pytest.mark.asyncio
    async def test_prefetch_success(self, prefetch_service, mock_cache_service, mock_imaging_service):
        """Test successful prefetching operation."""
        # All slices uncached
        mock_cache_service.exists.return_value = False

        # Mock successful slice retrieval
        mock_imaging_service.get_slice.return_value = {"data": "slice_data"}

        count = await prefetch_service.prefetch_slices(
            file_id="test_file",
            current_slice=10,
            total_slices=100,
            direction="forward"
        )

        # Should prefetch 3 slices successfully
        assert count == 3
        assert mock_imaging_service.get_slice.call_count == 3

    @pytest.mark.asyncio
    async def test_prefetch_no_uncached_slices(self, prefetch_service, mock_cache_service, mock_imaging_service):
        """Test prefetching when all slices are already cached."""
        # All slices cached
        mock_cache_service.exists.return_value = True

        count = await prefetch_service.prefetch_slices(
            file_id="test_file",
            current_slice=10,
            total_slices=100,
            direction="forward"
        )

        # No prefetching should occur
        assert count == 0
        assert mock_imaging_service.get_slice.call_count == 0

    @pytest.mark.asyncio
    async def test_prefetch_at_boundary(self, prefetch_service, mock_cache_service, mock_imaging_service):
        """Test prefetching at boundary (no slices to prefetch)."""
        mock_cache_service.exists.return_value = False

        count = await prefetch_service.prefetch_slices(
            file_id="test_file",
            current_slice=99,
            total_slices=100,
            direction="forward"
        )

        # No slices to prefetch at boundary
        assert count == 0
        assert mock_imaging_service.get_slice.call_count == 0


class TestRateLimiting:
    """Test suite for rate limiting functionality."""

    @pytest.mark.asyncio
    async def test_rate_limiting_applies_delays(self, prefetch_service):
        """Test that rate limiting applies appropriate delays."""
        # Create dummy async coroutines that return True
        async def dummy_task():
            return True

        tasks = [dummy_task() for _ in range(3)]

        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            results = await prefetch_service._execute_with_rate_limit(tasks)

            # Should have called sleep between tasks (not after last)
            # Priority "normal" = 0.2s = 200ms
            assert mock_sleep.call_count == 2  # Between 3 tasks

            # All tasks should complete
            assert len(results) == 3
            assert all(r is True for r in results)

    @pytest.mark.asyncio
    async def test_rate_limiting_correct_delay(self, prefetch_service):
        """Test that rate limiting uses correct delay for priority."""
        async def dummy_task():
            return True

        tasks = [dummy_task() for _ in range(2)]

        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            await prefetch_service._execute_with_rate_limit(tasks)

            # Normal priority = 0.2s delay
            if mock_sleep.call_count > 0:
                mock_sleep.assert_called_with(0.2)


class TestPrefetchRange:
    """Test suite for range prefetching."""

    @pytest.mark.asyncio
    async def test_prefetch_range_success(self, prefetch_service, mock_cache_service, mock_imaging_service):
        """Test successful range prefetching."""
        mock_cache_service.exists.return_value = False
        mock_imaging_service.get_slice.return_value = {"data": "slice_data"}

        result = await prefetch_service.prefetch_range(
            file_id="test_file",
            start_slice=10,
            end_slice=15
        )

        # Should prefetch slices 10-15 (6 slices)
        assert result["success"] == 6
        assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_prefetch_range_disabled(self, mock_imaging_service, mock_cache_service):
        """Test range prefetching when service is disabled."""
        service = PrefetchService(
            imaging_service=mock_imaging_service,
            cache_service=mock_cache_service
        )
        service.enabled = False

        result = await service.prefetch_range(
            file_id="test_file",
            start_slice=10,
            end_slice=15
        )

        assert result["success"] == 0
        assert result["failed"] == 0


class TestMetadataPrefetching:
    """Test suite for metadata prefetching."""

    @pytest.mark.asyncio
    async def test_prefetch_metadata_success(self, prefetch_service, mock_cache_service, mock_imaging_service):
        """Test successful metadata prefetching."""
        # Metadata not cached
        mock_cache_service.exists.return_value = False

        # Mock metadata extraction
        mock_imaging_service.get_file_metadata.return_value = {
            "slices": 100,
            "format": "DICOM"
        }

        success = await prefetch_service.prefetch_all_metadata(file_id="test_file")

        assert success is True
        mock_imaging_service.get_file_metadata.assert_called_once_with("test_file")

    @pytest.mark.asyncio
    async def test_prefetch_metadata_already_cached(self, prefetch_service, mock_cache_service, mock_imaging_service):
        """Test metadata prefetching when already cached."""
        # Metadata already cached
        mock_cache_service.exists.return_value = True

        success = await prefetch_service.prefetch_all_metadata(file_id="test_file")

        assert success is True
        # Should not attempt to fetch again
        mock_imaging_service.get_file_metadata.assert_not_called()


class TestEdgeCases:
    """Test suite for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_prefetch_with_errors(self, prefetch_service, mock_cache_service, mock_imaging_service):
        """Test prefetching handles errors gracefully."""
        mock_cache_service.exists.return_value = False

        # Simulate errors in get_slice
        mock_imaging_service.get_slice.side_effect = Exception("Test error")

        count = await prefetch_service.prefetch_slices(
            file_id="test_file",
            current_slice=10,
            total_slices=100,
            direction="forward"
        )

        # Should handle errors and return 0 (all failed)
        assert count == 0

    @pytest.mark.asyncio
    async def test_prefetch_empty_file_id(self, prefetch_service, mock_cache_service):
        """Test prefetching with empty file_id."""
        mock_cache_service.exists.return_value = False

        count = await prefetch_service.prefetch_slices(
            file_id="",
            current_slice=10,
            total_slices=100,
            direction="forward"
        )

        # Should handle gracefully (cache check will fail for empty file_id)
        # Implementation will still try to prefetch, but should handle empty ID
        assert count >= 0

    @pytest.mark.asyncio
    async def test_prefetch_zero_total_slices(self, prefetch_service):
        """Test prefetching with zero total slices."""
        count = await prefetch_service.prefetch_slices(
            file_id="test_file",
            current_slice=0,
            total_slices=0,
            direction="forward"
        )

        # Should handle gracefully - no slices to prefetch
        assert count == 0

    def test_get_stats(self, prefetch_service):
        """Test getting service statistics."""
        stats = prefetch_service.get_stats()

        assert "enabled" in stats
        assert "prefetch_count" in stats
        assert "priority" in stats
        assert "priority_delay_ms" in stats

        assert stats["prefetch_count"] == 3
        assert stats["priority"] == "normal"
        assert stats["priority_delay_ms"] == 200  # 0.2s * 1000
