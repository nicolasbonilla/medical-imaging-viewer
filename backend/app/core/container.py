"""
Dependency Injection Container.

This module defines the DI container that manages all service dependencies.
It uses the dependency-injector library to provide:
- Singleton instances of services
- Automatic dependency resolution
- Easy testing with mock implementations
- Loose coupling between components

Usage in routes:
    from app.core.container import Container
    from dependency_injector.wiring import inject, Provide

    @router.get("/files")
    @inject
    async def list_files(
        drive_service: IDriveService = Depends(Provide[Container.drive_service])
    ):
        files = drive_service.list_files()
        return files
"""

from dependency_injector import containers, providers

from app.core.config import get_settings
from app.core.logging import get_logger

# Lazy imports - DO NOT import service implementations at module level
# This defers heavy medical imaging library imports until first use
# Critical for Cloud Run startup time optimization

logger = get_logger(__name__)


class Container(containers.DeclarativeContainer):
    """
    Application DI Container.

    This container manages all service dependencies and their lifecycle.
    Services are created as singletons by default.

    Attributes:
        config: Configuration provider
        drive_service: Google Drive service singleton
        imaging_service: Medical imaging service singleton
        segmentation_service: Segmentation service singleton
    """

    # Configuration
    config = providers.Singleton(get_settings)

    # Cache Service (initialized first as other services may depend on it)
    # Using Factory with lazy imports to defer heavy library loading
    cache_service = providers.Factory(
        lambda host, port, db, password, max_connections: __import__('app.services.cache_service', fromlist=['RedisCacheService']).RedisCacheService(
            host=host, port=port, db=db, password=password, max_connections=max_connections
        ),
        host=config.provided.REDIS_HOST,
        port=config.provided.REDIS_PORT,
        db=config.provided.REDIS_DB,
        password=config.provided.REDIS_PASSWORD,
        max_connections=config.provided.REDIS_MAX_CONNECTIONS
    )

    # Google Drive Service - Lazy loaded on first access
    drive_service = providers.Factory(
        lambda cache: __import__('app.services.drive_service', fromlist=['GoogleDriveService']).GoogleDriveService(
            cache_service=cache
        ),
        cache=cache_service
    )

    # Medical Imaging Service - Lazy loaded (HEAVY: nibabel, SimpleITK, opencv, skimage)
    imaging_service = providers.Factory(
        lambda cache: __import__('app.services.imaging_service', fromlist=['ImagingService']).ImagingService(
            cache_service=cache
        ),
        cache=cache_service
    )

    # Segmentation Service - Lazy loaded (HEAVY: scikit-image, scipy)
    segmentation_service = providers.Factory(
        lambda cache: __import__('app.services.segmentation_service', fromlist=['SegmentationService']).SegmentationService(
            cache_service=cache
        ),
        cache=cache_service
    )

    # Prefetch Service - Lazy loaded
    prefetch_service = providers.Factory(
        lambda imaging, cache: __import__('app.services.prefetch_service', fromlist=['PrefetchService']).PrefetchService(
            imaging_service=imaging,
            cache_service=cache
        ),
        imaging=imaging_service,
        cache=cache_service
    )


def init_container() -> Container:
    """
    Initialize and configure the DI container.

    This function creates the container and wires it to the application modules.
    It should be called during application startup.

    Returns:
        Container: Configured DI container

    Example:
        from app.core.container import init_container

        # In main.py startup event
        container = init_container()
        app.container = container
    """
    container = Container()

    # Wire the container to modules that use @inject decorator
    # This allows automatic dependency injection in routes
    container.wire(modules=[
        "app.api.routes.drive",
        "app.api.routes.imaging",
        "app.api.routes.segmentation",
    ])

    logger.info("DI Container initialized and wired successfully")

    return container


def get_container() -> Container:
    """
    Get the application's DI container.

    This is a helper function to access the container from anywhere in the app.
    The container should be attached to the FastAPI app instance during startup.

    Returns:
        Container: The application's DI container

    Example:
        from fastapi import Request
        from app.core.container import get_container

        @router.get("/health")
        async def health_check(request: Request):
            container = get_container()
            config = container.config()
            return {"version": config.APP_VERSION}
    """
    from app.main import app
    return app.container


# Convenience function for FastAPI Depends()
def get_drive_service():
    """
    Dependency function for FastAPI routes to get DriveService.

    Usage:
        from fastapi import Depends
        from app.core.container import get_drive_service

        @router.get("/files")
        async def list_files(
            drive_service = Depends(get_drive_service)
        ):
            return drive_service.list_files()
    """
    container = get_container()
    return container.drive_service()


def get_imaging_service():
    """
    Dependency function for FastAPI routes to get ImagingService.

    Usage:
        from fastapi import Depends
        from app.core.container import get_imaging_service

        @router.get("/process/{file_id}")
        async def process_image(
            file_id: str,
            imaging_service = Depends(get_imaging_service)
        ):
            return imaging_service.process_image(...)
    """
    container = get_container()
    return container.imaging_service()


def get_segmentation_service():
    """
    Dependency function for FastAPI routes to get SegmentationService.

    Usage:
        from fastapi import Depends
        from app.core.container import get_segmentation_service

        @router.post("/segmentations")
        async def create_segmentation(
            request: SegmentationCreateRequest,
            segmentation_service = Depends(get_segmentation_service)
        ):
            return segmentation_service.create_segmentation(...)
    """
    container = get_container()
    return container.segmentation_service()


def get_cache_service():
    """
    Dependency function for FastAPI routes to get CacheService.

    Usage:
        from fastapi import Depends
        from app.core.container import get_cache_service

        @router.get("/cached-data")
        async def get_data(
            cache_service = Depends(get_cache_service)
        ):
            return await cache_service.get("key")
    """
    container = get_container()
    return container.cache_service()


def get_prefetch_service():
    """
    Dependency function for FastAPI routes to get PrefetchService.

    Usage:
        from fastapi import Depends
        from app.core.container import get_prefetch_service

        @router.get("/image/{file_id}/{slice_index}")
        async def get_image(
            file_id: str,
            slice_index: int,
            prefetch_service = Depends(get_prefetch_service)
        ):
            # Get slice and prefetch next ones
            await prefetch_service.prefetch_slices(file_id, slice_index, total_slices)
    """
    container = get_container()
    return container.prefetch_service()
