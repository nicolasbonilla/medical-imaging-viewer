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

# Import concrete implementations
from app.services.drive_service import GoogleDriveService
from app.services.imaging_service import ImagingService
from app.services.segmentation_service import SegmentationService
from app.services.cache_service import RedisCacheService
from app.services.prefetch_service import PrefetchService

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
    cache_service = providers.Singleton(
        RedisCacheService,
        host=config.provided.REDIS_HOST,
        port=config.provided.REDIS_PORT,
        db=config.provided.REDIS_DB,
        password=config.provided.REDIS_PASSWORD,
        max_connections=config.provided.REDIS_MAX_CONNECTIONS
    )

    # Google Drive Service
    drive_service = providers.Singleton(
        GoogleDriveService,
        cache_service=cache_service
    )

    # Medical Imaging Service
    imaging_service = providers.Singleton(
        ImagingService,
        cache_service=cache_service
    )

    # Segmentation Service
    segmentation_service = providers.Singleton(
        SegmentationService,
        cache_service=cache_service
    )

    # Prefetch Service (FASE 1: Quick Wins)
    prefetch_service = providers.Singleton(
        PrefetchService,
        imaging_service=imaging_service,
        cache_service=cache_service
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
