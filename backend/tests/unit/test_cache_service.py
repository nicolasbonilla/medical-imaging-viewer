"""
Unit tests for RedisCacheService.
"""

import pytest
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.cache_service import RedisCacheService


@pytest.mark.unit
class TestCacheService:
    """Test suite for cache service."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        mock = AsyncMock()
        mock.ping = AsyncMock(return_value=True)
        mock.get = AsyncMock(return_value=None)
        mock.set = AsyncMock(return_value=True)
        mock.delete = AsyncMock(return_value=1)
        mock.exists = AsyncMock(return_value=1)
        mock.keys = AsyncMock(return_value=[])
        mock.ttl = AsyncMock(return_value=300)
        mock.expire = AsyncMock(return_value=True)
        mock.incr = AsyncMock(return_value=1)
        mock.decr = AsyncMock(return_value=0)
        mock.flushdb = AsyncMock(return_value=True)
        return mock

    @pytest.fixture
    async def cache_service(self, mock_redis):
        """Create cache service with mocked Redis."""
        with patch('redis.asyncio.Redis') as mock_redis_class:
            mock_redis_class.return_value = mock_redis
            service = RedisCacheService(host="localhost", port=6379)
            service._client = mock_redis
            service._redis_available = True
            yield service

    @pytest.mark.asyncio
    async def test_set_and_get_string(self, cache_service, mock_redis):
        """Test setting and getting a string value."""
        # Arrange
        key = "test_key"
        value = "test_value"
        mock_redis.set.return_value = True
        mock_redis.get.return_value = b'"test_value"'

        # Act
        set_result = await cache_service.set(key, value)
        get_result = await cache_service.get(key)

        # Assert
        assert set_result is True
        assert get_result == value
        mock_redis.set.assert_called_once()
        mock_redis.get.assert_called_once_with(key)

    @pytest.mark.asyncio
    async def test_set_with_ttl(self, cache_service, mock_redis):
        """Test setting a value with TTL."""
        # Arrange
        key = "test_key"
        value = "test_value"
        ttl = timedelta(seconds=300)

        # Act
        await cache_service.set(key, value, ttl=ttl)

        # Assert
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args.kwargs.get('ex') == 300

    @pytest.mark.asyncio
    async def test_delete_key(self, cache_service, mock_redis):
        """Test deleting a key."""
        # Arrange
        key = "test_key"
        mock_redis.delete.return_value = 1

        # Act
        result = await cache_service.delete(key)

        # Assert
        assert result is True
        mock_redis.delete.assert_called_once_with(key)

    @pytest.mark.asyncio
    async def test_exists_key(self, cache_service, mock_redis):
        """Test checking if key exists."""
        # Arrange
        key = "test_key"
        mock_redis.exists.return_value = 1

        # Act
        result = await cache_service.exists(key)

        # Assert
        assert result is True
        mock_redis.exists.assert_called_once_with(key)

    @pytest.mark.asyncio
    async def test_clear_pattern(self, cache_service, mock_redis):
        """Test clearing keys by pattern."""
        # Arrange
        pattern = "test_*"
        mock_redis.keys.return_value = [b"test_1", b"test_2", b"test_3"]
        mock_redis.delete.return_value = 3

        # Act
        count = await cache_service.clear_pattern(pattern)

        # Assert
        assert count == 3
        mock_redis.keys.assert_called_once_with(pattern)
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_increment(self, cache_service, mock_redis):
        """Test incrementing a counter."""
        # Arrange
        key = "counter"
        mock_redis.incr.return_value = 5

        # Act
        result = await cache_service.increment(key)

        # Assert
        assert result == 5
        mock_redis.incr.assert_called_once_with(key, 1)

    @pytest.mark.asyncio
    async def test_decrement(self, cache_service, mock_redis):
        """Test decrementing a counter."""
        # Arrange
        key = "counter"
        mock_redis.decr.return_value = 3

        # Act
        result = await cache_service.decrement(key)

        # Assert
        assert result == 3
        mock_redis.decr.assert_called_once_with(key, 1)

    @pytest.mark.asyncio
    async def test_get_ttl(self, cache_service, mock_redis):
        """Test getting TTL of a key."""
        # Arrange
        key = "test_key"
        mock_redis.ttl.return_value = 300

        # Act
        ttl = await cache_service.get_ttl(key)

        # Assert
        assert ttl == 300
        mock_redis.ttl.assert_called_once_with(key)

    @pytest.mark.asyncio
    async def test_graceful_degradation_on_error(self, cache_service, mock_redis):
        """Test that cache returns None on errors instead of crashing."""
        # Arrange
        key = "test_key"
        mock_redis.get.side_effect = Exception("Redis connection failed")

        # Act
        result = await cache_service.get(key)

        # Assert
        assert result is None  # Should return None, not raise exception

    @pytest.mark.asyncio
    async def test_set_many(self, cache_service, mock_redis):
        """Test setting multiple key-value pairs."""
        # Arrange
        items = {
            "key1": "value1",
            "key2": "value2",
            "key3": "value3",
        }
        mock_redis.set.return_value = True

        # Act
        result = await cache_service.set_many(items)

        # Assert
        assert result is True
        assert mock_redis.set.call_count == 3

    @pytest.mark.asyncio
    async def test_get_many(self, cache_service, mock_redis):
        """Test getting multiple keys."""
        # Arrange
        keys = ["key1", "key2", "key3"]
        mock_redis.get.side_effect = [b'"value1"', b'"value2"', b'"value3"']

        # Act
        result = await cache_service.get_many(keys)

        # Assert
        assert result == {"key1": "value1", "key2": "value2", "key3": "value3"}
        assert mock_redis.get.call_count == 3

    @pytest.mark.asyncio
    async def test_clear_all(self, cache_service, mock_redis):
        """Test clearing all keys."""
        # Arrange
        mock_redis.flushdb.return_value = True

        # Act
        result = await cache_service.clear_all()

        # Assert
        assert result is True
        mock_redis.flushdb.assert_called_once()

    @pytest.mark.asyncio
    async def test_ping(self, cache_service, mock_redis):
        """Test ping to check Redis availability."""
        # Arrange
        mock_redis.ping.return_value = True

        # Act
        result = await cache_service.ping()

        # Assert
        assert result is True
        mock_redis.ping.assert_called_once()
