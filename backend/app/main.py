from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import asyncio
import warnings
import sys
from contextlib import asynccontextmanager

from app.core.config import get_settings
from app.core.logging import setup_logging, get_logger, AuditMiddleware
from app.core.logging.middleware import LoggingMiddleware
from app.core.security import (
    RateLimitMiddleware,
    IPBlacklistMiddleware,
    InputValidationMiddleware,
    TLSEnforcementMiddleware,
    SecurityHeaderLevel,
)
from app.core.exception_handlers import register_exception_handlers
from app.core.container import init_container
from app.api.routes import auth, drive, imaging, segmentation, websocket, authentication
from app.models.schemas import HealthCheck

settings = get_settings()

# Suppress RuntimeWarnings for unawaited coroutines during development server reload
# These warnings occur when Uvicorn's --reload kills pending requests
# In production (without --reload), these warnings won't appear
if settings.DEBUG:
    warnings.filterwarnings(
        "ignore",
        message="coroutine.*was never awaited",
        category=RuntimeWarning
    )
    # Also suppress at sys level for warnings from external packages like starlette
    if not sys.warnoptions:
        warnings.simplefilter("ignore", RuntimeWarning)

# Initialize structured logging
setup_logging()
logger = get_logger(__name__)

logger.info(
    "Starting Medical Imaging Viewer API",
    extra={
        "version": settings.APP_VERSION,
        "debug": settings.DEBUG,
        "log_level": settings.LOG_LEVEL
    }
)


# Lifespan event handler for startup and shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan event handler for application startup and shutdown.
    Replaces deprecated on_event decorators.
    """
    # Startup: Create default admin user if no users exist
    try:
        from app.api.routes.auth import auth_service
        from app.security.models import UserCreate, UserRole

        # Check if any users exist in AuthService
        all_users = auth_service.list_users()

        if len(all_users) == 0:
            logger.info("No users found in AuthService - creating default admin user")

            # Create default admin user
            username = "admin"
            password = "Admin123!@2024"
            email = "admin@example.com"
            full_name = "Administrator"

            user_create = UserCreate(
                username=username,
                email=email,
                password=password,
                full_name=full_name,
                role=UserRole.ADMIN
            )

            # Register user through AuthService (same as registration endpoint)
            created_user = auth_service.register_user(user_create)

            logger.info(
                "Default admin user created successfully",
                extra={
                    "username": username,
                    "user_id": created_user.id,
                    "role": created_user.role.value
                }
            )
            logger.warning(
                "SECURITY WARNING: Default admin credentials in use. "
                "Change password immediately after first login!"
            )
        else:
            logger.info(f"AuthService initialized with {len(all_users)} existing users")
    except Exception as e:
        logger.error(f"Failed to initialize default admin user: {e}", exc_info=True)
        # Don't fail startup - allow app to run even if user creation fails

    yield

    # Shutdown: gracefully handle shutdown
    logger.info("Application shutdown initiated - waiting for pending tasks")
    await asyncio.sleep(0.1)
    logger.info("Application shutdown complete")


# Create FastAPI app with lifespan
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Professional Medical Imaging Viewer API",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan
)

# Initialize Dependency Injection Container
container = init_container()
app.container = container

logger.info("DI Container initialized and attached to app")

# Register exception handlers (MUST be before routes)
register_exception_handlers(app)

# Add IP blacklist middleware (ISO 27001 A.13.1.3 - MUST be first to block malicious IPs)
app.add_middleware(IPBlacklistMiddleware)

# Add rate limit middleware (ISO 27001 A.12.2.1 - DoS protection)
rate_limit_enabled = getattr(settings, 'RATE_LIMIT_ENABLED', True)
app.add_middleware(RateLimitMiddleware, enabled=rate_limit_enabled)

# Add input validation middleware (ISO 27001 A.14.2.1 - Injection prevention)
validation_enabled = getattr(settings, 'INPUT_VALIDATION_ENABLED', True)
validation_strict = getattr(settings, 'INPUT_VALIDATION_STRICT', True)
app.add_middleware(
    InputValidationMiddleware,
    enabled=validation_enabled,
    strict_mode=validation_strict
)

# Add audit middleware (ISO 27001 A.12.4.1 - Security logging)
app.add_middleware(AuditMiddleware)

# Add logging middleware (Operational logging)
app.add_middleware(LoggingMiddleware)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add TLS enforcement middleware (ISO 27001 A.13.1.1, A.13.2.1 - MUST be after CORS)
tls_enabled = getattr(settings, 'TLS_ENABLED', False)
if tls_enabled:
    # Parse security header level
    header_level_str = getattr(settings, 'SECURITY_HEADER_LEVEL', 'STANDARD')
    header_level = SecurityHeaderLevel[header_level_str]

    # Parse allowed hosts
    allowed_hosts = getattr(settings, 'ALLOWED_HOSTS', [])
    if not allowed_hosts:
        allowed_hosts = None  # No restriction if empty

    app.add_middleware(
        TLSEnforcementMiddleware,
        enabled=tls_enabled,
        enforce_https=getattr(settings, 'TLS_ENFORCE_HTTPS', True),
        redirect_to_https=getattr(settings, 'TLS_REDIRECT_TO_HTTPS', False),
        security_header_level=header_level,
        hsts_enabled=getattr(settings, 'HSTS_ENABLED', False),
        hsts_max_age=getattr(settings, 'HSTS_MAX_AGE', 31536000),
        hsts_include_subdomains=getattr(settings, 'HSTS_INCLUDE_SUBDOMAINS', True),
        hsts_preload=getattr(settings, 'HSTS_PRELOAD', False),
        custom_csp=getattr(settings, 'CUSTOM_CSP', None) or None,
        report_uri=getattr(settings, 'CSP_REPORT_URI', None) or None,
        allowed_hosts=allowed_hosts,
    )

    logger.info(
        "TLS enforcement enabled",
        extra={
            "enforce_https": getattr(settings, 'TLS_ENFORCE_HTTPS', True),
            "hsts_enabled": getattr(settings, 'HSTS_ENABLED', False),
            "security_level": header_level_str,
            "iso27001_control": "A.13.1.1, A.13.2.1"
        }
    )


# Health check endpoint
@app.get("/", response_model=HealthCheck, tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return HealthCheck(
        status="healthy",
        version=settings.APP_VERSION,
        timestamp=datetime.utcnow()
    )


@app.get("/api/health", response_model=HealthCheck, tags=["Health"])
async def api_health_check():
    """API health check endpoint."""
    return HealthCheck(
        status="healthy",
        version=settings.APP_VERSION,
        timestamp=datetime.utcnow()
    )


# Include routers
# Authentication routes (ISO 27001 A.9.4.2)
app.include_router(authentication.router, prefix=settings.API_V1_STR)
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(drive.router, prefix=settings.API_V1_STR)
app.include_router(imaging.router, prefix=settings.API_V1_STR)
app.include_router(segmentation.router, prefix=settings.API_V1_STR)
app.include_router(websocket.router, prefix=settings.API_V1_STR)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )
