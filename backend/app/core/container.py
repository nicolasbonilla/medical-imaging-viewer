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

    @router.get("/image/{file_id}")
    @inject
    async def get_image(
        file_id: str,
        imaging_service: IImagingService = Depends(Provide[Container.imaging_service])
    ):
        return imaging_service.get_image(file_id)
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
        imaging_service: Medical imaging service singleton
        segmentation_service: Segmentation service singleton
        cache_service: Redis cache service singleton
        prefetch_service: Image prefetch service singleton
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

    # Storage Service - GCS-based file storage
    storage_service = providers.Factory(
        lambda: __import__('app.services.storage_service', fromlist=['GCSStorageService']).GCSStorageService()
    )

    # Patient Service - Firestore-based patient management
    patient_service = providers.Factory(
        lambda: __import__('app.services.patient_service_firestore', fromlist=['PatientServiceFirestore']).PatientServiceFirestore()
    )

    # Study Service - Firestore-based study management
    study_service = providers.Factory(
        lambda: __import__('app.services.study_service_firestore', fromlist=['StudyServiceFirestore']).StudyServiceFirestore()
    )

    # Document Service - Firestore-based document management
    document_service = providers.Factory(
        lambda: __import__('app.services.document_service_firestore', fromlist=['DocumentServiceFirestore']).DocumentServiceFirestore()
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


def get_storage_service():
    """
    Dependency function for FastAPI routes to get StorageService.

    Usage:
        from fastapi import Depends
        from app.core.container import get_storage_service

        @router.get("/files/{path}")
        async def get_file(
            path: str,
            storage_service = Depends(get_storage_service)
        ):
            return await storage_service.download_file(bucket, path)
    """
    container = get_container()
    return container.storage_service()


def get_patient_service():
    """
    Dependency function for FastAPI routes to get PatientService.

    Uses Firestore backend for patient data persistence.
    """
    container = get_container()
    return container.patient_service()


def get_study_service():
    """
    Dependency function for FastAPI routes to get StudyService.

    Uses Firestore backend for study data persistence.
    """
    container = get_container()
    return container.study_service()


def get_document_service():
    """
    Dependency function for FastAPI routes to get DocumentService.

    Uses Firestore backend for document data persistence.
    """
    container = get_container()
    return container.document_service()
