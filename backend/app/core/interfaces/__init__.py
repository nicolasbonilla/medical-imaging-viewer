"""
Service interfaces for dependency injection.

This package defines abstract interfaces for all services,
enabling loose coupling and testability through dependency injection.
"""

from app.core.interfaces.imaging_interface import IImagingService
from app.core.interfaces.segmentation_interface import ISegmentationService
from app.core.interfaces.cache_interface import ICacheService

__all__ = [
    "IImagingService",
    "ISegmentationService",
    "ICacheService",
]
