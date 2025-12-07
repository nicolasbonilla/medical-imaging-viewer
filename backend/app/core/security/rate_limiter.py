"""
Rate Limiting and DoS Protection
ISO 27001 A.12.2.1 - Controls against malware
ISO 27001 A.13.1.3 - Segregation in networks

Implements multiple rate limiting strategies to protect against:
- Brute force attacks (login, password reset)
- DoS/DDoS attacks
- API abuse
- Resource exhaustion

Uses Redis for distributed rate limiting across multiple instances.

@module core.security.rate_limiter
"""

import time
import hashlib
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from enum import Enum

try:
    import redis
    from redis.exceptions import RedisError
except ImportError:
    redis = None

from app.core.logging import get_logger, get_audit_logger, AuditEventType, AuditSeverity, AuditOutcome

logger = get_logger(__name__)


class RateLimitStrategy(str, Enum):
    """Rate limiting strategies."""
    FIXED_WINDOW = "fixed_window"  # Simple counter per time window
    SLIDING_WINDOW = "sliding_window"  # Sliding window log
    TOKEN_BUCKET = "token_bucket"  # Token bucket algorithm
    LEAKY_BUCKET = "leaky_bucket"  # Leaky bucket algorithm


class RateLimitScope(str, Enum):
    """Scope of rate limiting (ISO 27001 A.12.2.1)."""
    GLOBAL = "global"  # Global limit for all users
    PER_IP = "per_ip"  # Per IP address
    PER_USER = "per_user"  # Per authenticated user
    PER_ENDPOINT = "per_endpoint"  # Per API endpoint
    PER_RESOURCE = "per_resource"  # Per specific resource


class RateLimitExceeded(Exception):
    """
    Exception raised when rate limit is exceeded.

    Attributes:
        limit: Maximum number of requests allowed
        window: Time window in seconds
        retry_after: Seconds until limit resets
        scope: Rate limit scope
    """

    def __init__(
        self,
        limit: int,
        window: int,
        retry_after: int,
        scope: RateLimitScope,
        message: Optional[str] = None
    ):
        self.limit = limit
        self.window = window
        self.retry_after = retry_after
        self.scope = scope
        self.message = message or f"Rate limit exceeded: {limit} requests per {window}s"
        super().__init__(self.message)


class RateLimiter:
    """
    Redis-backed rate limiter with multiple strategies.

    ISO 27001 A.12.2.1 - Controls against malware (DoS protection)
    ISO 27001 A.13.1.3 - Segregation in networks
    """

    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        default_limit: int = 60,
        default_window: int = 60,
        strategy: RateLimitStrategy = RateLimitStrategy.SLIDING_WINDOW
    ):
        """
        Initialize rate limiter.

        Args:
            redis_client: Redis client instance (if None, uses in-memory fallback)
            default_limit: Default max requests per window
            default_window: Default time window in seconds
            strategy: Rate limiting strategy
        """
        self.redis_client = redis_client
        self.default_limit = default_limit
        self.default_window = default_window
        self.strategy = strategy

        # In-memory fallback for when Redis is unavailable
        self._memory_cache: Dict[str, Any] = {}

        # Audit logger for security events
        self.audit_logger = get_audit_logger()

        if not self.redis_client:
            logger.warning(
                "Redis client not provided, using in-memory rate limiting (not suitable for production)",
                extra={"iso27001_control": "A.12.2.1"}
            )

    def check_rate_limit(
        self,
        key: str,
        limit: Optional[int] = None,
        window: Optional[int] = None,
        scope: RateLimitScope = RateLimitScope.PER_IP,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if request is within rate limit.

        Args:
            key: Unique key for this rate limit (e.g., "login:192.168.1.1")
            limit: Max requests allowed (uses default if None)
            window: Time window in seconds (uses default if None)
            scope: Rate limit scope
            user_id: User ID (for audit logging)
            ip_address: IP address (for audit logging)

        Returns:
            Tuple of (allowed: bool, metadata: dict)
            metadata contains: current_count, limit, window, retry_after, reset_at

        Raises:
            RateLimitExceeded: If rate limit is exceeded
        """
        limit = limit or self.default_limit
        window = window or self.default_window

        # Choose strategy
        if self.strategy == RateLimitStrategy.FIXED_WINDOW:
            allowed, metadata = self._fixed_window_check(key, limit, window)
        elif self.strategy == RateLimitStrategy.SLIDING_WINDOW:
            allowed, metadata = self._sliding_window_check(key, limit, window)
        elif self.strategy == RateLimitStrategy.TOKEN_BUCKET:
            allowed, metadata = self._token_bucket_check(key, limit, window)
        else:
            # Default to fixed window
            allowed, metadata = self._fixed_window_check(key, limit, window)

        # Log rate limit violation
        if not allowed:
            self._log_rate_limit_violation(
                key=key,
                scope=scope,
                limit=limit,
                window=window,
                current_count=metadata['current_count'],
                user_id=user_id,
                ip_address=ip_address
            )

        return allowed, metadata

    def _fixed_window_check(
        self, key: str, limit: int, window: int
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Fixed window rate limiting.

        Simple counter that resets at fixed intervals.
        """
        now = int(time.time())
        window_key = f"ratelimit:fixed:{key}:{now // window}"

        if self.redis_client:
            try:
                # Increment counter
                current = self.redis_client.incr(window_key)

                # Set expiration on first request
                if current == 1:
                    self.redis_client.expire(window_key, window)

                # Calculate reset time
                reset_at = ((now // window) + 1) * window
                retry_after = reset_at - now

                metadata = {
                    'current_count': current,
                    'limit': limit,
                    'window': window,
                    'retry_after': retry_after if current > limit else 0,
                    'reset_at': reset_at,
                    'strategy': 'fixed_window'
                }

                return current <= limit, metadata

            except RedisError as e:
                logger.error(f"Redis error in rate limiting: {e}", exc_info=True)
                return self._memory_fallback_check(window_key, limit, window)
        else:
            return self._memory_fallback_check(window_key, limit, window)

    def _sliding_window_check(
        self, key: str, limit: int, window: int
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Sliding window rate limiting using sorted sets.

        More accurate than fixed window, prevents burst at window boundaries.
        """
        now = time.time()
        window_key = f"ratelimit:sliding:{key}"

        if self.redis_client:
            try:
                pipe = self.redis_client.pipeline()

                # Remove old entries outside the window
                pipe.zremrangebyscore(window_key, 0, now - window)

                # Count current entries
                pipe.zcard(window_key)

                # Add current request
                pipe.zadd(window_key, {f"{now}:{hashlib.md5(str(now).encode()).hexdigest()[:8]}": now})

                # Set expiration
                pipe.expire(window_key, window + 1)

                results = pipe.execute()
                current_count = results[1] + 1  # Count before adding + 1 for current request

                retry_after = 0
                if current_count > limit:
                    # Get oldest request in window
                    oldest = self.redis_client.zrange(window_key, 0, 0, withscores=True)
                    if oldest:
                        oldest_time = oldest[0][1]
                        retry_after = int(oldest_time + window - now)

                metadata = {
                    'current_count': current_count,
                    'limit': limit,
                    'window': window,
                    'retry_after': max(0, retry_after),
                    'reset_at': int(now + window),
                    'strategy': 'sliding_window'
                }

                return current_count <= limit, metadata

            except RedisError as e:
                logger.error(f"Redis error in rate limiting: {e}", exc_info=True)
                return self._memory_fallback_check(window_key, limit, window)
        else:
            return self._memory_fallback_check(window_key, limit, window)

    def _token_bucket_check(
        self, key: str, limit: int, window: int
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Token bucket algorithm.

        Allows bursts while maintaining average rate.
        """
        now = time.time()
        bucket_key = f"ratelimit:token:{key}"

        if self.redis_client:
            try:
                # Get current tokens and last update time
                bucket_data = self.redis_client.hgetall(bucket_key)

                if bucket_data:
                    tokens = float(bucket_data.get(b'tokens', limit))
                    last_update = float(bucket_data.get(b'last_update', now))
                else:
                    tokens = limit
                    last_update = now

                # Calculate token refill
                time_passed = now - last_update
                refill_rate = limit / window  # tokens per second
                tokens = min(limit, tokens + time_passed * refill_rate)

                # Try to consume one token
                if tokens >= 1:
                    tokens -= 1
                    allowed = True
                else:
                    allowed = False

                # Update bucket
                pipe = self.redis_client.pipeline()
                pipe.hset(bucket_key, 'tokens', tokens)
                pipe.hset(bucket_key, 'last_update', now)
                pipe.expire(bucket_key, window * 2)
                pipe.execute()

                retry_after = int((1 - tokens) / refill_rate) if tokens < 1 else 0

                metadata = {
                    'current_count': int(limit - tokens),
                    'limit': limit,
                    'window': window,
                    'retry_after': max(0, retry_after),
                    'reset_at': int(now + retry_after),
                    'tokens_remaining': tokens,
                    'strategy': 'token_bucket'
                }

                return allowed, metadata

            except RedisError as e:
                logger.error(f"Redis error in rate limiting: {e}", exc_info=True)
                return self._memory_fallback_check(bucket_key, limit, window)
        else:
            return self._memory_fallback_check(bucket_key, limit, window)

    def _memory_fallback_check(
        self, key: str, limit: int, window: int
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        In-memory fallback when Redis is unavailable.

        WARNING: Not suitable for production with multiple instances.
        """
        now = time.time()

        # Clean old entries
        self._memory_cache = {
            k: v for k, v in self._memory_cache.items()
            if v['expires_at'] > now
        }

        # Get or create entry
        if key not in self._memory_cache:
            self._memory_cache[key] = {
                'count': 0,
                'expires_at': now + window
            }

        entry = self._memory_cache[key]
        entry['count'] += 1

        retry_after = int(entry['expires_at'] - now) if entry['count'] > limit else 0

        metadata = {
            'current_count': entry['count'],
            'limit': limit,
            'window': window,
            'retry_after': max(0, retry_after),
            'reset_at': int(entry['expires_at']),
            'strategy': 'memory_fallback'
        }

        return entry['count'] <= limit, metadata

    def _log_rate_limit_violation(
        self,
        key: str,
        scope: RateLimitScope,
        limit: int,
        window: int,
        current_count: int,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> None:
        """
        Log rate limit violation for security monitoring.

        ISO 27001 A.16.1.1 - Reporting information security events
        """
        # Determine if this is a potential brute force attack
        is_brute_force = (
            'login' in key.lower() or
            'password' in key.lower() or
            'auth' in key.lower()
        ) and current_count > limit * 2

        event_type = (
            AuditEventType.SECURITY_BRUTE_FORCE if is_brute_force
            else AuditEventType.SECURITY_POLICY_VIOLATION
        )

        severity = (
            AuditSeverity.CRITICAL if is_brute_force
            else AuditSeverity.HIGH if current_count > limit * 5
            else AuditSeverity.MEDIUM
        )

        threat_indicators = []
        if is_brute_force:
            threat_indicators.append("brute_force_attempt")
        if current_count > limit * 5:
            threat_indicators.append("excessive_requests")
        if current_count > limit * 10:
            threat_indicators.append("potential_dos")

        self.audit_logger.log_security_event(
            event_type=event_type,
            description=f"Rate limit exceeded: {current_count}/{limit} requests in {window}s (key: {key})",
            severity=severity,
            user_id=user_id,
            ip_address=ip_address,
            threat_indicators=threat_indicators,
            metadata={
                'key': key,
                'scope': scope.value,
                'limit': limit,
                'window': window,
                'current_count': current_count,
                'overage': current_count - limit,
                'overage_percentage': ((current_count - limit) / limit) * 100
            }
        )

    def reset_limit(self, key: str) -> bool:
        """
        Reset rate limit for a specific key.

        Args:
            key: Rate limit key to reset

        Returns:
            True if reset successful
        """
        if self.redis_client:
            try:
                # Delete all possible key patterns
                patterns = [
                    f"ratelimit:fixed:{key}:*",
                    f"ratelimit:sliding:{key}",
                    f"ratelimit:token:{key}"
                ]

                deleted = 0
                for pattern in patterns:
                    keys = self.redis_client.keys(pattern)
                    if keys:
                        deleted += self.redis_client.delete(*keys)

                logger.info(
                    f"Rate limit reset for key: {key}",
                    extra={'deleted_keys': deleted}
                )
                return True

            except RedisError as e:
                logger.error(f"Failed to reset rate limit: {e}", exc_info=True)
                return False
        else:
            # Memory fallback
            keys_to_delete = [k for k in self._memory_cache.keys() if key in k]
            for k in keys_to_delete:
                del self._memory_cache[k]
            return True

    def get_limit_info(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get current rate limit information for a key.

        Args:
            key: Rate limit key

        Returns:
            Dictionary with limit info or None if not found
        """
        if self.redis_client:
            try:
                # Try sliding window first
                window_key = f"ratelimit:sliding:{key}"
                count = self.redis_client.zcard(window_key)
                ttl = self.redis_client.ttl(window_key)

                if count > 0:
                    return {
                        'current_count': count,
                        'limit': self.default_limit,
                        'window': self.default_window,
                        'ttl': ttl,
                        'strategy': 'sliding_window'
                    }
                return None

            except RedisError as e:
                logger.error(f"Failed to get rate limit info: {e}", exc_info=True)
                return None
        else:
            if key in self._memory_cache:
                return {
                    'current_count': self._memory_cache[key]['count'],
                    'limit': self.default_limit,
                    'window': self.default_window,
                    'ttl': int(self._memory_cache[key]['expires_at'] - time.time()),
                    'strategy': 'memory_fallback'
                }
            return None


# Predefined rate limit configurations for common use cases
RATE_LIMIT_CONFIGS = {
    # Authentication endpoints (strict limits to prevent brute force)
    'auth.login': {'limit': 5, 'window': 60, 'scope': RateLimitScope.PER_IP},
    'auth.register': {'limit': 3, 'window': 3600, 'scope': RateLimitScope.PER_IP},
    'auth.password_reset': {'limit': 3, 'window': 3600, 'scope': RateLimitScope.PER_IP},
    'auth.refresh_token': {'limit': 10, 'window': 60, 'scope': RateLimitScope.PER_USER},

    # API endpoints (moderate limits)
    'api.general': {'limit': 60, 'window': 60, 'scope': RateLimitScope.PER_USER},
    'api.search': {'limit': 30, 'window': 60, 'scope': RateLimitScope.PER_USER},
    'api.upload': {'limit': 10, 'window': 60, 'scope': RateLimitScope.PER_USER},

    # Resource-intensive endpoints (strict limits)
    'imaging.process': {'limit': 10, 'window': 60, 'scope': RateLimitScope.PER_USER},
    'imaging.download': {'limit': 20, 'window': 60, 'scope': RateLimitScope.PER_USER},
    'segmentation.run': {'limit': 5, 'window': 60, 'scope': RateLimitScope.PER_USER},

    # Global limits (DoS protection)
    'global': {'limit': 1000, 'window': 60, 'scope': RateLimitScope.GLOBAL},
}


def get_rate_limiter(redis_client: Optional[redis.Redis] = None) -> RateLimiter:
    """
    Get rate limiter instance.

    Args:
        redis_client: Redis client (if None, creates new connection)

    Returns:
        RateLimiter instance
    """
    if redis_client is None:
        from app.core.config import get_settings
        settings = get_settings()

        try:
            redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
                decode_responses=False,
                socket_connect_timeout=1,  # Fail fast if Redis unavailable (1 second)
                socket_timeout=1,  # Quick timeout for operations
                socket_keepalive=True,
                retry_on_timeout=False  # Don't retry, fall back immediately
            )
            # Test connection with explicit timeout
            redis_client.ping()
        except Exception as e:
            logger.warning(f"Failed to connect to Redis for rate limiting: {e}")
            redis_client = None

    return RateLimiter(
        redis_client=redis_client,
        default_limit=60,
        default_window=60,
        strategy=RateLimitStrategy.SLIDING_WINDOW
    )
