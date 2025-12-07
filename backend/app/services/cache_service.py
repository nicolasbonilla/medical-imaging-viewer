"""
Redis cache service implementation.

Provides high-performance caching using Redis with support for:
- TTL-based expiration
- Pattern-based key deletion
- Serialization/deserialization
- Connection pooling
- Graceful degradation (fallback if Redis unavailable)
"""

import json
import pickle
from typing import Optional, Any, List
from datetime import timedelta
import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool

from app.core.interfaces.cache_interface import ICacheService
from app.core.exceptions import CacheException
from app.core.logging import get_logger
from app.core.config import get_settings

settings = get_settings()
logger = get_logger(__name__)


class RedisCacheService(ICacheService):
    """
    Redis-based cache implementation.

    Features:
    - Async operations for non-blocking I/O
    - JSON serialization for simple types
    - Pickle serialization for complex objects
    - Automatic reconnection
    - Connection pooling
    - Graceful degradation if Redis unavailable
    """

    def __init__(
        self,
        host: str = None,
        port: int = None,
        db: int = 0,
        password: Optional[str] = None,
        max_connections: int = 50
    ):
        """
        Initialize Redis cache service.

        Args:
            host: Redis host (default from settings)
            port: Redis port (default from settings)
            db: Redis database number
            password: Redis password (if required)
            max_connections: Max connections in pool
        """
        self.host = host or getattr(settings, 'REDIS_HOST', 'localhost')
        self.port = port or getattr(settings, 'REDIS_PORT', 6379)
        self.db = db
        self.password = password
        self.max_connections = max_connections

        # Connection pool (created lazily)
        self._pool: Optional[ConnectionPool] = None
        self._client: Optional[redis.Redis] = None

        # Flag to track if Redis is available
        self._redis_available = True

        logger.info(
            "RedisCacheService initialized",
            extra={
                "host": self.host,
                "port": self.port,
                "db": self.db,
                "max_connections": max_connections
            }
        )

    async def _get_client(self) -> redis.Redis:
        """
        Get or create Redis client with connection pool.

        Returns:
            Redis client instance

        Raises:
            CacheException: If Redis connection fails
        """
        if self._client is None:
            try:
                # Create connection pool
                self._pool = ConnectionPool(
                    host=self.host,
                    port=self.port,
                    db=self.db,
                    password=self.password,
                    max_connections=self.max_connections,
                    decode_responses=False  # We handle encoding ourselves
                )

                # Create client
                self._client = redis.Redis(connection_pool=self._pool)

                # Test connection
                await self._client.ping()
                self._redis_available = True

                logger.info("Redis connection established successfully")

            except Exception as e:
                self._redis_available = False
                logger.error(
                    "Failed to connect to Redis",
                    extra={"error": str(e), "host": self.host, "port": self.port},
                    exc_info=True
                )
                raise CacheException(
                    message=f"Redis connection failed: {str(e)}",
                    error_code="REDIS_CONNECTION_ERROR",
                    details={"host": self.host, "port": self.port}
                )

        return self._client

    def _serialize(self, value: Any) -> bytes:
        """
        Serialize value for storage.

        Uses JSON for simple types, pickle for complex objects.

        Args:
            value: Value to serialize

        Returns:
            Serialized bytes
        """
        try:
            # Try JSON first (faster, human-readable)
            return json.dumps(value).encode('utf-8')
        except (TypeError, ValueError):
            # Fallback to pickle for complex objects
            return pickle.dumps(value)

    def _deserialize(self, data: bytes) -> Any:
        """
        Deserialize value from storage.

        Args:
            data: Serialized bytes

        Returns:
            Deserialized value
        """
        try:
            # Try JSON first
            return json.loads(data.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Fallback to pickle
            return pickle.loads(data)

    async def get(self, key: str) -> Optional[Any]:
        """Get a value from cache."""
        if not self._redis_available:
            return None

        try:
            client = await self._get_client()
            data = await client.get(key)

            if data is None:
                logger.debug(f"Cache miss: {key}")
                return None

            logger.debug(f"Cache hit: {key}")
            return self._deserialize(data)

        except Exception as e:
            logger.warning(
                "Cache get failed, returning None",
                extra={"key": key, "error": str(e)}
            )
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[timedelta] = None
    ) -> bool:
        """Set a value in cache with optional TTL."""
        if not self._redis_available:
            return False

        try:
            client = await self._get_client()
            data = self._serialize(value)

            if ttl:
                await client.setex(key, int(ttl.total_seconds()), data)
            else:
                await client.set(key, data)

            logger.debug(
                f"Cache set: {key}",
                extra={"ttl_seconds": int(ttl.total_seconds()) if ttl else None}
            )
            return True

        except Exception as e:
            logger.warning(
                "Cache set failed",
                extra={"key": key, "error": str(e)}
            )
            return False

    async def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        if not self._redis_available:
            return False

        try:
            client = await self._get_client()
            result = await client.delete(key)
            logger.debug(f"Cache delete: {key}", extra={"deleted": bool(result)})
            return bool(result)

        except Exception as e:
            logger.warning(
                "Cache delete failed",
                extra={"key": key, "error": str(e)}
            )
            return False

    async def exists(self, key: str) -> bool:
        """Check if a key exists in cache."""
        if not self._redis_available:
            return False

        try:
            client = await self._get_client()
            result = await client.exists(key)
            return bool(result)

        except Exception as e:
            logger.warning(
                "Cache exists check failed",
                extra={"key": key, "error": str(e)}
            )
            return False

    async def clear_pattern(self, pattern: str) -> int:
        """
        Clear all keys matching a pattern.

        Uses SCAN for non-blocking iteration (O(N) but non-blocking).
        Processes keys in batches to avoid blocking Redis.
        """
        if not self._redis_available:
            return 0

        try:
            client = await self._get_client()
            deleted = 0
            batch = []
            batch_size = getattr(settings, 'REDIS_SCAN_COUNT', 100)

            # SCAN iteration - non-blocking, cursor-based
            async for key in client.scan_iter(match=pattern, count=batch_size):
                batch.append(key)

                # Delete in batches to avoid large atomic operations
                if len(batch) >= batch_size:
                    deleted += await client.delete(*batch)
                    batch = []

            # Delete remaining keys
            if batch:
                deleted += await client.delete(*batch)

            if deleted > 0:
                logger.info(
                    f"Cleared cache pattern: {pattern}",
                    extra={"keys_deleted": deleted}
                )

            return deleted

        except Exception as e:
            logger.error(
                "Cache pattern clear failed",
                extra={"pattern": pattern, "error": str(e)}
            )
            return 0

    async def scan_keys(self, pattern: str, count: int = None):
        """
        Async generator for iterating over keys matching pattern.

        Uses SCAN for non-blocking iteration.

        Usage:
            async for key in cache_service.scan_keys("slice:*"):
                value = await cache_service.get(key)

        Args:
            pattern: Redis key pattern (e.g., "slice:*", "metadata:*")
            count: Number of keys to process per iteration (default from settings)

        Yields:
            Key names (as strings)
        """
        if not self._redis_available:
            return

        try:
            client = await self._get_client()
            scan_count = count or getattr(settings, 'REDIS_SCAN_COUNT', 100)

            async for key in client.scan_iter(match=pattern, count=scan_count):
                # Decode bytes to string if needed
                if isinstance(key, bytes):
                    yield key.decode('utf-8')
                else:
                    yield key

        except Exception as e:
            logger.error(
                "Cache scan_keys failed",
                extra={"pattern": pattern, "error": str(e)}
            )

    async def get_ttl(self, key: str) -> Optional[int]:
        """Get remaining TTL for a key in seconds."""
        if not self._redis_available:
            return None

        try:
            client = await self._get_client()
            ttl = await client.ttl(key)

            if ttl == -2:  # Key doesn't exist
                return None
            elif ttl == -1:  # Key has no expiration
                return None
            else:
                return ttl

        except Exception as e:
            logger.warning(
                "Cache TTL check failed",
                extra={"key": key, "error": str(e)}
            )
            return None

    async def set_ttl(self, key: str, ttl: timedelta) -> bool:
        """Update TTL for an existing key."""
        if not self._redis_available:
            return False

        try:
            client = await self._get_client()
            result = await client.expire(key, int(ttl.total_seconds()))
            return bool(result)

        except Exception as e:
            logger.warning(
                "Cache TTL set failed",
                extra={"key": key, "error": str(e)}
            )
            return False

    async def get_many(self, keys: List[str]) -> dict[str, Any]:
        """Get multiple values at once."""
        if not self._redis_available or not keys:
            return {}

        try:
            client = await self._get_client()
            values = await client.mget(keys)

            result = {}
            for key, data in zip(keys, values):
                if data is not None:
                    result[key] = self._deserialize(data)

            logger.debug(
                f"Cache get_many: {len(result)}/{len(keys)} hits",
                extra={"requested": len(keys), "found": len(result)}
            )
            return result

        except Exception as e:
            logger.warning(
                "Cache get_many failed",
                extra={"keys_count": len(keys), "error": str(e)}
            )
            return {}

    async def set_many(
        self,
        items: dict[str, Any],
        ttl: Optional[timedelta] = None
    ) -> bool:
        """Set multiple values at once."""
        if not self._redis_available or not items:
            return False

        try:
            client = await self._get_client()

            # Serialize all values
            serialized = {k: self._serialize(v) for k, v in items.items()}

            # Use pipeline for atomic operation
            async with client.pipeline() as pipe:
                await pipe.mset(serialized)

                # Set TTL for each key if specified
                if ttl:
                    for key in items.keys():
                        await pipe.expire(key, int(ttl.total_seconds()))

                await pipe.execute()

            logger.debug(
                f"Cache set_many: {len(items)} items",
                extra={"count": len(items), "ttl_seconds": int(ttl.total_seconds()) if ttl else None}
            )
            return True

        except Exception as e:
            logger.warning(
                "Cache set_many failed",
                extra={"items_count": len(items), "error": str(e)}
            )
            return False

    async def increment(self, key: str, amount: int = 1) -> int:
        """Increment a numeric value in cache."""
        if not self._redis_available:
            raise CacheException("Redis not available")

        try:
            client = await self._get_client()
            new_value = await client.incrby(key, amount)
            logger.debug(f"Cache increment: {key} by {amount} = {new_value}")
            return new_value

        except Exception as e:
            logger.error(
                "Cache increment failed",
                extra={"key": key, "amount": amount, "error": str(e)}
            )
            raise CacheException(
                message=f"Failed to increment key: {str(e)}",
                error_code="CACHE_INCREMENT_ERROR",
                details={"key": key, "amount": amount}
            )

    async def decrement(self, key: str, amount: int = 1) -> int:
        """Decrement a numeric value in cache."""
        if not self._redis_available:
            raise CacheException("Redis not available")

        try:
            client = await self._get_client()
            new_value = await client.decrby(key, amount)
            logger.debug(f"Cache decrement: {key} by {amount} = {new_value}")
            return new_value

        except Exception as e:
            logger.error(
                "Cache decrement failed",
                extra={"key": key, "amount": amount, "error": str(e)}
            )
            raise CacheException(
                message=f"Failed to decrement key: {str(e)}",
                error_code="CACHE_DECREMENT_ERROR",
                details={"key": key, "amount": amount}
            )

    async def clear_all(self) -> bool:
        """Clear all keys in cache (use with caution!)."""
        if not self._redis_available:
            return False

        try:
            client = await self._get_client()
            await client.flushdb()
            logger.warning("Cache cleared: ALL KEYS DELETED")
            return True

        except Exception as e:
            logger.error(
                "Cache clear_all failed",
                extra={"error": str(e)}
            )
            return False

    async def ping(self) -> bool:
        """Check if cache service is available."""
        try:
            client = await self._get_client()
            await client.ping()
            return True
        except Exception:
            return False

    def get_stats(self) -> dict[str, Any]:
        """
        Get cache statistics.

        Note: This is a synchronous wrapper. For async context,
        call client.info() directly.
        """
        if not self._redis_available or self._client is None:
            return {
                "status": "unavailable",
                "redis_available": False
            }

        try:
            # Note: This requires sync context or async wrapper
            return {
                "status": "available",
                "redis_available": True,
                "host": self.host,
                "port": self.port,
                "db": self.db
            }
        except Exception as e:
            logger.error(
                "Failed to get cache stats",
                extra={"error": str(e)}
            )
            return {
                "status": "error",
                "error": str(e)
            }

    async def close(self):
        """Close Redis connection and cleanup resources."""
        if self._client:
            await self._client.close()
            logger.info("Redis connection closed")

        if self._pool:
            await self._pool.disconnect()
            logger.info("Redis connection pool disconnected")

        self._client = None
        self._pool = None
