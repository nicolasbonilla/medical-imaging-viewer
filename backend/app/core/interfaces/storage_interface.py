"""
Storage service interface for file operations.

Provides abstraction for cloud storage operations following
dependency inversion principle.

@module core.interfaces.storage_interface
"""

from abc import ABC, abstractmethod
from typing import Optional, List, BinaryIO, Dict, Any, Union
from datetime import timedelta, datetime
from dataclasses import dataclass


@dataclass
class StorageObject:
    """Represents a stored object."""
    bucket: str
    name: str
    size: int
    content_type: str
    checksum_sha256: str
    created_at: str
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class SignedUrl:
    """Signed URL for upload or download."""
    url: str
    expires_at: Union[str, datetime]
    method: str  # GET or PUT


class IStorageService(ABC):
    """
    Interface for cloud storage operations.

    Implementations:
    - GCSStorageService (Google Cloud Storage)
    - LocalStorageService (for testing)
    """

    @abstractmethod
    async def upload_file(
        self,
        bucket_name: str,
        object_name: str,
        file_data: bytes,
        content_type: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> StorageObject:
        """
        Upload a file to storage.

        Args:
            bucket_name: Target bucket
            object_name: Object path/name in bucket
            file_data: File content as bytes
            content_type: MIME type
            metadata: Optional custom metadata

        Returns:
            StorageObject with upload details
        """
        pass

    @abstractmethod
    async def upload_from_file(
        self,
        bucket_name: str,
        object_name: str,
        file_path: str,
        content_type: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> StorageObject:
        """
        Upload a file from local filesystem.

        Args:
            bucket_name: Target bucket
            object_name: Object path/name in bucket
            file_path: Local file path
            content_type: MIME type
            metadata: Optional custom metadata

        Returns:
            StorageObject with upload details
        """
        pass

    @abstractmethod
    async def download_file(
        self,
        bucket_name: str,
        object_name: str
    ) -> bytes:
        """
        Download a file from storage.

        Args:
            bucket_name: Source bucket
            object_name: Object path/name

        Returns:
            File content as bytes
        """
        pass

    @abstractmethod
    async def delete_file(
        self,
        bucket_name: str,
        object_name: str
    ) -> bool:
        """
        Delete a file from storage.

        Args:
            bucket_name: Bucket name
            object_name: Object path/name

        Returns:
            True if deleted successfully
        """
        pass

    @abstractmethod
    async def file_exists(
        self,
        bucket_name: str,
        object_name: str
    ) -> bool:
        """
        Check if a file exists.

        Args:
            bucket_name: Bucket name
            object_name: Object path/name

        Returns:
            True if file exists
        """
        pass

    @abstractmethod
    async def get_file_metadata(
        self,
        bucket_name: str,
        object_name: str
    ) -> Optional[StorageObject]:
        """
        Get file metadata without downloading.

        Args:
            bucket_name: Bucket name
            object_name: Object path/name

        Returns:
            StorageObject if exists, None otherwise
        """
        pass

    @abstractmethod
    async def list_files(
        self,
        bucket_name: str,
        prefix: Optional[str] = None,
        max_results: int = 1000
    ) -> List[StorageObject]:
        """
        List files in a bucket with optional prefix filter.

        Args:
            bucket_name: Bucket name
            prefix: Optional path prefix
            max_results: Maximum files to return

        Returns:
            List of StorageObject
        """
        pass

    @abstractmethod
    async def generate_signed_upload_url(
        self,
        bucket_name: str,
        object_name: str,
        content_type: str,
        expiration: timedelta = timedelta(hours=1)
    ) -> SignedUrl:
        """
        Generate a signed URL for direct upload.

        Args:
            bucket_name: Target bucket
            object_name: Object path/name
            content_type: Expected MIME type
            expiration: URL validity period

        Returns:
            SignedUrl with PUT URL
        """
        pass

    @abstractmethod
    async def generate_signed_download_url(
        self,
        bucket_name: str,
        object_name: str,
        expiration: timedelta = timedelta(hours=1)
    ) -> SignedUrl:
        """
        Generate a signed URL for download.

        Args:
            bucket_name: Source bucket
            object_name: Object path/name
            expiration: URL validity period

        Returns:
            SignedUrl with GET URL
        """
        pass

    @abstractmethod
    async def copy_file(
        self,
        source_bucket: str,
        source_object: str,
        dest_bucket: str,
        dest_object: str
    ) -> StorageObject:
        """
        Copy a file within or between buckets.

        Args:
            source_bucket: Source bucket
            source_object: Source object path
            dest_bucket: Destination bucket
            dest_object: Destination object path

        Returns:
            StorageObject of the copy
        """
        pass

    @abstractmethod
    async def move_file(
        self,
        source_bucket: str,
        source_object: str,
        dest_bucket: str,
        dest_object: str
    ) -> StorageObject:
        """
        Move a file (copy + delete original).

        Args:
            source_bucket: Source bucket
            source_object: Source object path
            dest_bucket: Destination bucket
            dest_object: Destination object path

        Returns:
            StorageObject of the moved file
        """
        pass
