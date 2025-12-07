"""
Interface for cache service.

Defines the contract for caching operations with Redis or other cache backends.
"""

from abc import ABC, abstractmethod
from typing import Optional, Any, List
from datetime import timedelta


class ICacheService(ABC):
    """
    Abstract interface for cache operations.

    This interface defines all operations for caching data with support
    for TTL, key patterns, and different data types.
    """

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """
        Get a value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired

        Raises:
            CacheException: If cache operation fails
        """
        pass

    @abstractmethod
    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[timedelta] = None
    ) -> bool:
        """
        Set a value in cache with optional TTL.

        Args:
            key: Cache key
            value: Value to cache (will be serialized)
            ttl: Time to live (None = no expiration)

        Returns:
            True if successfully cached

        Raises:
            CacheException: If cache operation fails
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """
        Delete a key from cache.

        Args:
            key: Cache key to delete

        Returns:
            True if key was deleted, False if key didn't exist

        Raises:
            CacheException: If cache operation fails
        """
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """
        Check if a key exists in cache.

        Args:
            key: Cache key to check

        Returns:
            True if key exists

        Raises:
            CacheException: If cache operation fails
        """
        pass

    @abstractmethod
    async def clear_pattern(self, pattern: str) -> int:
        """
        Clear all keys matching a pattern.

        Args:
            pattern: Redis pattern (e.g., "drive:*", "image:123:*")

        Returns:
            Number of keys deleted

        Raises:
            CacheException: If cache operation fails
        """
        pass

    @abstractmethod
    async def get_ttl(self, key: str) -> Optional[int]:
        """
        Get remaining TTL for a key in seconds.

        Args:
            key: Cache key

        Returns:
            TTL in seconds, None if key doesn't exist or has no expiration

        Raises:
            CacheException: If cache operation fails
        """
        pass

    @abstractmethod
    async def set_ttl(self, key: str, ttl: timedelta) -> bool:
        """
        Update TTL for an existing key.

        Args:
            key: Cache key
            ttl: New time to live

        Returns:
            True if TTL was set

        Raises:
            CacheException: If cache operation fails
        """
        pass

    @abstractmethod
    async def get_many(self, keys: List[str]) -> dict[str, Any]:
        """
        Get multiple values at once.

        Args:
            keys: List of cache keys

        Returns:
            Dictionary mapping keys to values (missing keys excluded)

        Raises:
            CacheException: If cache operation fails
        """
        pass

    @abstractmethod
    async def set_many(
        self,
        items: dict[str, Any],
        ttl: Optional[timedelta] = None
    ) -> bool:
        """
        Set multiple values at once.

        Args:
            items: Dictionary mapping keys to values
            ttl: Time to live for all items (None = no expiration)

        Returns:
            True if all items were cached successfully

        Raises:
            CacheException: If cache operation fails
        """
        pass

    @abstractmethod
    async def increment(self, key: str, amount: int = 1) -> int:
        """
        Increment a numeric value in cache.

        Args:
            key: Cache key
            amount: Amount to increment by

        Returns:
            New value after increment

        Raises:
            CacheException: If cache operation fails
        """
        pass

    @abstractmethod
    async def decrement(self, key: str, amount: int = 1) -> int:
        """
        Decrement a numeric value in cache.

        Args:
            key: Cache key
            amount: Amount to decrement by

        Returns:
            New value after decrement

        Raises:
            CacheException: If cache operation fails
        """
        pass

    @abstractmethod
    async def clear_all(self) -> bool:
        """
        Clear all keys in cache (use with caution!).

        Returns:
            True if cache was cleared

        Raises:
            CacheException: If cache operation fails
        """
        pass

    @abstractmethod
    async def ping(self) -> bool:
        """
        Check if cache service is available.

        Returns:
            True if cache is responsive

        Raises:
            CacheException: If cache is not available
        """
        pass

    @abstractmethod
    def get_stats(self) -> dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache stats (hits, misses, keys, memory, etc.)

        Raises:
            CacheException: If stats cannot be retrieved
        """
        pass
