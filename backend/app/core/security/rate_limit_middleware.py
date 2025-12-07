"""
Rate Limit Middleware for FastAPI
ISO 27001 A.12.2.1 - Controls against malware (DoS protection)

Automatically applies rate limiting to HTTP requests based on configurable rules.

@module core.security.rate_limit_middleware
"""

from typing import Callable, Optional, Dict
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.security.rate_limiter import (
    get_rate_limiter,
    RateLimiter,
    RateLimitExceeded,
    RateLimitScope,
    RATE_LIMIT_CONFIGS
)
from app.core.logging import get_logger

logger = get_logger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware for automatic rate limiting of HTTP requests.

    ISO 27001 A.12.2.1 - Controls against malware (DoS protection)
    """

    def __init__(
        self,
        app: ASGIApp,
        rate_limiter: Optional[RateLimiter] = None,
        enabled: bool = True
    ):
        """
        Initialize rate limit middleware.

        Args:
            app: ASGI application
            rate_limiter: RateLimiter instance (creates new if None)
            enabled: Whether rate limiting is enabled
        """
        super().__init__(app)
        self.rate_limiter = rate_limiter or get_rate_limiter()
        self.enabled = enabled

        # Paths that should bypass rate limiting
        self.bypass_paths = [
            '/api/health',
            '/api/docs',
            '/api/redoc',
            '/api/openapi.json',
            '/',
        ]

        # Path-specific rate limit configurations
        self.path_configs = self._build_path_configs()

        logger.info(
            "Rate limiting middleware initialized",
            extra={
                "enabled": self.enabled,
                "strategy": self.rate_limiter.strategy.value,
                "iso27001_control": "A.12.2.1"
            }
        )

    def _build_path_configs(self) -> Dict[str, Dict]:
        """Build path-specific rate limit configurations."""
        configs = {}

        # Authentication endpoints
        configs['/api/v1/auth/login'] = RATE_LIMIT_CONFIGS['auth.login']
        configs['/api/v1/auth/register'] = RATE_LIMIT_CONFIGS['auth.register']
        configs['/api/v1/auth/reset-password'] = RATE_LIMIT_CONFIGS['auth.password_reset']
        configs['/api/v1/auth/refresh'] = RATE_LIMIT_CONFIGS['auth.refresh_token']

        # Upload endpoints
        configs['/api/v1/imaging/upload'] = RATE_LIMIT_CONFIGS['api.upload']

        # Processing endpoints
        configs['/api/v1/imaging/process'] = RATE_LIMIT_CONFIGS['imaging.process']
        configs['/api/v1/segmentation'] = RATE_LIMIT_CONFIGS['segmentation.run']

        return configs

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """
        Process request and apply rate limiting.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware in chain

        Returns:
            HTTP response
        """
        # Skip if disabled
        if not self.enabled:
            return await call_next(request)

        # Skip bypass paths
        if self._should_bypass(request.url.path):
            return await call_next(request)

        # Get rate limit configuration for this path
        config = self._get_config_for_path(request.url.path)

        # Build rate limit key
        key = self._build_key(request, config['scope'])

        # Extract client info for audit logging
        client_ip = self._get_client_ip(request)
        user_id = self._get_user_id(request)

        try:
            # Check rate limit
            allowed, metadata = self.rate_limiter.check_rate_limit(
                key=key,
                limit=config['limit'],
                window=config['window'],
                scope=config['scope'],
                user_id=user_id,
                ip_address=client_ip
            )

            if not allowed:
                # Rate limit exceeded
                return self._create_rate_limit_response(metadata)

            # Add rate limit headers to response
            response = await call_next(request)
            self._add_rate_limit_headers(response, metadata)

            return response

        except Exception as e:
            # Log error but don't block request (fail open for availability)
            logger.error(
                f"Rate limiting error: {e}",
                extra={
                    "path": request.url.path,
                    "client_ip": client_ip,
                    "user_id": user_id
                },
                exc_info=True
            )
            return await call_next(request)

    def _should_bypass(self, path: str) -> bool:
        """Check if path should bypass rate limiting."""
        return any(path.startswith(bypass) for bypass in self.bypass_paths)

    def _get_config_for_path(self, path: str) -> Dict:
        """Get rate limit configuration for path."""
        # Check exact match first
        if path in self.path_configs:
            return self.path_configs[path]

        # Check prefix match
        for config_path, config in self.path_configs.items():
            if path.startswith(config_path):
                return config

        # Default to general API limit
        return RATE_LIMIT_CONFIGS['api.general']

    def _build_key(self, request: Request, scope: RateLimitScope) -> str:
        """
        Build rate limit key based on scope.

        Args:
            request: HTTP request
            scope: Rate limit scope

        Returns:
            Rate limit key
        """
        path = request.url.path

        if scope == RateLimitScope.GLOBAL:
            return f"global:{path}"

        elif scope == RateLimitScope.PER_IP:
            client_ip = self._get_client_ip(request)
            return f"ip:{client_ip}:{path}"

        elif scope == RateLimitScope.PER_USER:
            user_id = self._get_user_id(request)
            if user_id:
                return f"user:{user_id}:{path}"
            else:
                # Fall back to IP if user not authenticated
                client_ip = self._get_client_ip(request)
                return f"ip:{client_ip}:{path}"

        elif scope == RateLimitScope.PER_ENDPOINT:
            return f"endpoint:{path}"

        else:
            # Default to IP-based
            client_ip = self._get_client_ip(request)
            return f"ip:{client_ip}:{path}"

    def _get_client_ip(self, request: Request) -> str:
        """
        Get client IP address from request.

        Handles X-Forwarded-For header for proxied requests.
        """
        # Check X-Forwarded-For header (for reverse proxy)
        forwarded_for = request.headers.get('X-Forwarded-For')
        if forwarded_for:
            # Get first IP (original client)
            return forwarded_for.split(',')[0].strip()

        # Check X-Real-IP header
        real_ip = request.headers.get('X-Real-IP')
        if real_ip:
            return real_ip

        # Fall back to direct connection
        if request.client:
            return request.client.host

        return 'unknown'

    def _get_user_id(self, request: Request) -> Optional[str]:
        """
        Get user ID from request state.

        User ID is set by authentication middleware.
        """
        if hasattr(request.state, 'user'):
            user = request.state.user
            return getattr(user, 'id', None)
        return None

    def _create_rate_limit_response(self, metadata: Dict) -> JSONResponse:
        """
        Create HTTP 429 response for rate limit exceeded.

        Args:
            metadata: Rate limit metadata

        Returns:
            JSONResponse with 429 status
        """
        headers = {
            'X-RateLimit-Limit': str(metadata['limit']),
            'X-RateLimit-Remaining': '0',
            'X-RateLimit-Reset': str(metadata['reset_at']),
            'Retry-After': str(metadata['retry_after'])
        }

        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                'error': 'rate_limit_exceeded',
                'message': f"Rate limit exceeded: {metadata['limit']} requests per {metadata['window']} seconds",
                'limit': metadata['limit'],
                'window': metadata['window'],
                'retry_after': metadata['retry_after'],
                'reset_at': metadata['reset_at']
            },
            headers=headers
        )

    def _add_rate_limit_headers(self, response: Response, metadata: Dict) -> None:
        """
        Add rate limit headers to response.

        Args:
            response: HTTP response
            metadata: Rate limit metadata
        """
        remaining = max(0, metadata['limit'] - metadata['current_count'])

        response.headers['X-RateLimit-Limit'] = str(metadata['limit'])
        response.headers['X-RateLimit-Remaining'] = str(remaining)
        response.headers['X-RateLimit-Reset'] = str(metadata['reset_at'])
        response.headers['X-RateLimit-Window'] = str(metadata['window'])


class IPBlacklistMiddleware(BaseHTTPMiddleware):
    """
    Middleware for IP blacklisting based on security threats.

    ISO 27001 A.13.1.3 - Segregation in networks
    """

    def __init__(
        self,
        app: ASGIApp,
        redis_client=None,
        auto_blacklist_threshold: int = 100,
        auto_blacklist_window: int = 60
    ):
        """
        Initialize IP blacklist middleware.

        Args:
            app: ASGI application
            redis_client: Redis client for blacklist storage
            auto_blacklist_threshold: Requests per window to trigger auto-blacklist
            auto_blacklist_window: Time window for auto-blacklist detection
        """
        super().__init__(app)
        self.redis_client = redis_client
        self.auto_blacklist_threshold = auto_blacklist_threshold
        self.auto_blacklist_window = auto_blacklist_window

        # In-memory blacklist (fallback)
        self.memory_blacklist = set()

        logger.info(
            "IP blacklist middleware initialized",
            extra={
                "auto_blacklist_threshold": auto_blacklist_threshold,
                "auto_blacklist_window": auto_blacklist_window,
                "iso27001_control": "A.13.1.3"
            }
        )

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """
        Check if IP is blacklisted.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware in chain

        Returns:
            HTTP response or 403 if blacklisted
        """
        client_ip = self._get_client_ip(request)

        # Check if IP is blacklisted
        if await self._is_blacklisted(client_ip):
            logger.warning(
                f"Blocked request from blacklisted IP: {client_ip}",
                extra={
                    "client_ip": client_ip,
                    "path": request.url.path,
                    "iso27001_control": "A.13.1.3"
                }
            )

            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    'error': 'ip_blacklisted',
                    'message': 'Access denied: IP address is blacklisted due to security policy violations'
                }
            )

        return await call_next(request)

    async def _is_blacklisted(self, ip: str) -> bool:
        """Check if IP is in blacklist."""
        if self.redis_client:
            try:
                blacklist_key = f"blacklist:ip:{ip}"
                return bool(self.redis_client.exists(blacklist_key))
            except Exception as e:
                logger.error(f"Redis error checking blacklist: {e}")
                return ip in self.memory_blacklist
        else:
            return ip in self.memory_blacklist

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP from request."""
        forwarded_for = request.headers.get('X-Forwarded-For')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()

        real_ip = request.headers.get('X-Real-IP')
        if real_ip:
            return real_ip

        if request.client:
            return request.client.host

        return 'unknown'

    async def add_to_blacklist(
        self, ip: str, duration: int = 3600, reason: str = "Security policy violation"
    ) -> bool:
        """
        Add IP to blacklist.

        Args:
            ip: IP address to blacklist
            duration: Duration in seconds (0 = permanent)
            reason: Reason for blacklisting

        Returns:
            True if successful
        """
        if self.redis_client:
            try:
                blacklist_key = f"blacklist:ip:{ip}"
                self.redis_client.set(blacklist_key, reason)

                if duration > 0:
                    self.redis_client.expire(blacklist_key, duration)

                logger.warning(
                    f"IP added to blacklist: {ip}",
                    extra={
                        "ip": ip,
                        "duration": duration,
                        "reason": reason,
                        "iso27001_control": "A.13.1.3"
                    }
                )
                return True

            except Exception as e:
                logger.error(f"Failed to add IP to blacklist: {e}")
                self.memory_blacklist.add(ip)
                return False
        else:
            self.memory_blacklist.add(ip)
            return True

    async def remove_from_blacklist(self, ip: str) -> bool:
        """
        Remove IP from blacklist.

        Args:
            ip: IP address to remove

        Returns:
            True if successful
        """
        if self.redis_client:
            try:
                blacklist_key = f"blacklist:ip:{ip}"
                self.redis_client.delete(blacklist_key)

                logger.info(
                    f"IP removed from blacklist: {ip}",
                    extra={"ip": ip}
                )
                return True

            except Exception as e:
                logger.error(f"Failed to remove IP from blacklist: {e}")
                self.memory_blacklist.discard(ip)
                return False
        else:
            self.memory_blacklist.discard(ip)
            return True
