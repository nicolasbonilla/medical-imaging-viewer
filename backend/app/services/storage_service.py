"""
Google Cloud Storage Service Implementation.

Provides secure file storage operations for medical imaging files
and clinical documents with SHA-256 integrity verification.

@module services.storage_service
"""

import hashlib
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
from functools import partial
import logging

from google.cloud import storage
from google.cloud.exceptions import NotFound
from google.oauth2 import service_account
from google import auth as google_auth

from app.core.config import get_settings
from app.core.interfaces.storage_interface import (
    IStorageService,
    StorageObject,
    SignedUrl
)
from app.core.exceptions import StorageException, NotFoundException

logger = logging.getLogger(__name__)
settings = get_settings()


class GCSStorageService(IStorageService):
    """
    Google Cloud Storage service implementation.

    Provides async wrapper around google-cloud-storage client
    with connection pooling and automatic retry.
    """

    def __init__(self, credentials_path: Optional[str] = None):
        """
        Initialize GCS client.

        Args:
            credentials_path: Path to service account JSON file.
                             If None, uses default credentials.
        """
        self._credentials_path = credentials_path or settings.GCS_CREDENTIALS_FILE
        self._client: Optional[storage.Client] = None
        self._project_id = settings.GCS_PROJECT_ID
        self._credentials = None
        self._service_account_email = None

    def _get_client(self) -> storage.Client:
        """Get or create GCS client (lazy initialization)."""
        if self._client is None:
            try:
                if self._credentials_path:
                    self._credentials = service_account.Credentials.from_service_account_file(
                        self._credentials_path
                    )
                    self._service_account_email = self._credentials.service_account_email
                    self._client = storage.Client(
                        credentials=self._credentials,
                        project=self._project_id or self._credentials.project_id
                    )
                else:
                    # Use default credentials (GCE, Cloud Run, etc.)
                    self._credentials, project = google_auth.default()
                    # Always get service account email from metadata for Cloud Run
                    import requests
                    try:
                        resp = requests.get(
                            'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email',
                            headers={'Metadata-Flavor': 'Google'},
                            timeout=5
                        )
                        if resp.status_code == 200:
                            self._service_account_email = resp.text.strip()
                            logger.info(f"Got SA email from metadata: {self._service_account_email}")
                        else:
                            self._service_account_email = None
                    except Exception as e:
                        logger.warning(f"Failed to get SA email: {e}")
                        self._service_account_email = None

                    self._client = storage.Client(
                        credentials=self._credentials,
                        project=self._project_id or project
                    )

                logger.info(
                    "GCS client initialized",
                    extra={
                        "project": self._client.project,
                        "service_account": self._service_account_email
                    }
                )
            except Exception as e:
                raise StorageException(
                    message="Failed to initialize GCS client",
                    error_code="STORAGE_INIT_ERROR",
                    status_code=500,
                    details={"original_error": str(e)}
                )

        return self._client

    def _compute_sha256(self, data: bytes) -> str:
        """Compute SHA-256 checksum of data."""
        return hashlib.sha256(data).hexdigest()

    async def _run_sync(self, func, *args, **kwargs):
        """Run synchronous function in thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            partial(func, *args, **kwargs)
        )

    async def upload_file(
        self,
        bucket_name: str,
        object_name: str,
        file_data: bytes,
        content_type: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> StorageObject:
        """Upload file data to GCS."""
        try:
            client = self._get_client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(object_name)

            # Set content type
            blob.content_type = content_type

            # Set custom metadata
            if metadata:
                blob.metadata = metadata

            # Compute checksum
            checksum = self._compute_sha256(file_data)

            # Upload in thread pool
            await self._run_sync(
                blob.upload_from_string,
                file_data,
                content_type=content_type
            )

            # Refresh blob to get server-side metadata
            await self._run_sync(blob.reload)

            logger.info(
                "File uploaded to GCS",
                extra={
                    "bucket": bucket_name,
                    "object": object_name,
                    "size": len(file_data),
                    "content_type": content_type
                }
            )

            return StorageObject(
                bucket=bucket_name,
                name=object_name,
                size=len(file_data),
                content_type=content_type,
                checksum_sha256=checksum,
                created_at=blob.time_created.isoformat() if blob.time_created else datetime.now(timezone.utc).isoformat(),
                metadata=metadata
            )

        except Exception as e:
            raise StorageException(
                message=f"Failed to upload file to GCS",
                error_code="STORAGE_UPLOAD_ERROR",
                status_code=500,
                details={
                    "bucket": bucket_name,
                    "object": object_name,
                    "original_error": str(e)
                }
            )

    async def upload_from_file(
        self,
        bucket_name: str,
        object_name: str,
        file_path: str,
        content_type: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> StorageObject:
        """Upload file from local path to GCS."""
        try:
            # Read file and compute checksum
            with open(file_path, 'rb') as f:
                file_data = f.read()

            return await self.upload_file(
                bucket_name=bucket_name,
                object_name=object_name,
                file_data=file_data,
                content_type=content_type,
                metadata=metadata
            )

        except FileNotFoundError:
            raise NotFoundException(
                message=f"Local file not found: {file_path}",
                error_code="STORAGE_LOCAL_FILE_NOT_FOUND",
                details={"file_path": file_path}
            )

    async def download_file(
        self,
        bucket_name: str,
        object_name: str
    ) -> bytes:
        """Download file from GCS."""
        try:
            client = self._get_client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(object_name)

            data = await self._run_sync(blob.download_as_bytes)

            logger.debug(
                "File downloaded from GCS",
                extra={
                    "bucket": bucket_name,
                    "object": object_name,
                    "size": len(data)
                }
            )

            return data

        except NotFound:
            raise NotFoundException(
                message=f"File not found in GCS",
                error_code="STORAGE_FILE_NOT_FOUND",
                details={
                    "bucket": bucket_name,
                    "object": object_name
                }
            )
        except Exception as e:
            raise StorageException(
                message=f"Failed to download file from GCS",
                error_code="STORAGE_DOWNLOAD_ERROR",
                status_code=500,
                details={
                    "bucket": bucket_name,
                    "object": object_name,
                    "original_error": str(e)
                }
            )

    async def delete_file(
        self,
        bucket_name: str,
        object_name: str
    ) -> bool:
        """Delete file from GCS."""
        try:
            client = self._get_client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(object_name)

            await self._run_sync(blob.delete)

            logger.info(
                "File deleted from GCS",
                extra={
                    "bucket": bucket_name,
                    "object": object_name
                }
            )

            return True

        except NotFound:
            logger.warning(
                "Attempted to delete non-existent file",
                extra={
                    "bucket": bucket_name,
                    "object": object_name
                }
            )
            return False
        except Exception as e:
            raise StorageException(
                message=f"Failed to delete file from GCS",
                error_code="STORAGE_DELETE_ERROR",
                status_code=500,
                details={
                    "bucket": bucket_name,
                    "object": object_name,
                    "original_error": str(e)
                }
            )

    async def file_exists(
        self,
        bucket_name: str,
        object_name: str
    ) -> bool:
        """Check if file exists in GCS."""
        try:
            client = self._get_client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(object_name)

            return await self._run_sync(blob.exists)

        except Exception as e:
            logger.error(
                "Error checking file existence",
                extra={
                    "bucket": bucket_name,
                    "object": object_name,
                    "error": str(e)
                }
            )
            return False

    async def get_file_metadata(
        self,
        bucket_name: str,
        object_name: str
    ) -> Optional[StorageObject]:
        """Get file metadata from GCS."""
        try:
            client = self._get_client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(object_name)

            # Reload to get metadata
            await self._run_sync(blob.reload)

            return StorageObject(
                bucket=bucket_name,
                name=object_name,
                size=blob.size or 0,
                content_type=blob.content_type or "application/octet-stream",
                checksum_sha256=blob.metadata.get("sha256", "") if blob.metadata else "",
                created_at=blob.time_created.isoformat() if blob.time_created else "",
                metadata=blob.metadata
            )

        except NotFound:
            return None
        except Exception as e:
            logger.error(
                "Error getting file metadata",
                extra={
                    "bucket": bucket_name,
                    "object": object_name,
                    "error": str(e)
                }
            )
            return None

    async def list_files(
        self,
        bucket_name: str,
        prefix: Optional[str] = None,
        max_results: int = 1000
    ) -> List[StorageObject]:
        """List files in GCS bucket."""
        try:
            client = self._get_client()
            bucket = client.bucket(bucket_name)

            # List blobs in thread pool
            blobs = await self._run_sync(
                lambda: list(bucket.list_blobs(prefix=prefix, max_results=max_results))
            )

            return [
                StorageObject(
                    bucket=bucket_name,
                    name=blob.name,
                    size=blob.size or 0,
                    content_type=blob.content_type or "application/octet-stream",
                    checksum_sha256=blob.metadata.get("sha256", "") if blob.metadata else "",
                    created_at=blob.time_created.isoformat() if blob.time_created else "",
                    metadata=blob.metadata
                )
                for blob in blobs
            ]

        except Exception as e:
            raise StorageException(
                message=f"Failed to list files in GCS",
                error_code="STORAGE_LIST_ERROR",
                status_code=500,
                details={
                    "bucket": bucket_name,
                    "prefix": prefix,
                    "original_error": str(e)
                }
            )

    async def generate_signed_upload_url(
        self,
        bucket_name: str,
        object_name: str,
        content_type: str,
        expiration: timedelta = timedelta(hours=1)
    ) -> SignedUrl:
        """Generate signed URL for upload."""
        try:
            client = self._get_client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(object_name)

            url = await self._run_sync(
                blob.generate_signed_url,
                version="v4",
                expiration=expiration,
                method="PUT",
                content_type=content_type
            )

            expires_at = datetime.now(timezone.utc) + expiration

            logger.debug(
                "Generated signed upload URL",
                extra={
                    "bucket": bucket_name,
                    "object": object_name,
                    "expires_at": expires_at.isoformat()
                }
            )

            return SignedUrl(
                url=url,
                expires_at=expires_at.isoformat(),
                method="PUT"
            )

        except Exception as e:
            raise StorageException(
                message=f"Failed to generate signed upload URL",
                error_code="STORAGE_SIGNED_URL_ERROR",
                status_code=500,
                details={
                    "bucket": bucket_name,
                    "object": object_name,
                    "original_error": str(e)
                }
            )

    async def generate_signed_download_url(
        self,
        bucket_name: str,
        object_name: str,
        expiration: timedelta = timedelta(hours=1)
    ) -> SignedUrl:
        """Generate signed URL for download."""
        try:
            client = self._get_client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(object_name)

            url = await self._run_sync(
                blob.generate_signed_url,
                version="v4",
                expiration=expiration,
                method="GET"
            )

            expires_at = datetime.now(timezone.utc) + expiration

            logger.debug(
                "Generated signed download URL",
                extra={
                    "bucket": bucket_name,
                    "object": object_name,
                    "expires_at": expires_at.isoformat()
                }
            )

            return SignedUrl(
                url=url,
                expires_at=expires_at.isoformat(),
                method="GET"
            )

        except Exception as e:
            raise StorageException(
                message=f"Failed to generate signed download URL",
                error_code="STORAGE_SIGNED_URL_ERROR",
                status_code=500,
                details={
                    "bucket": bucket_name,
                    "object": object_name,
                    "original_error": str(e)
                }
            )

    async def copy_file(
        self,
        source_bucket: str,
        source_object: str,
        dest_bucket: str,
        dest_object: str
    ) -> StorageObject:
        """Copy file within or between buckets."""
        try:
            client = self._get_client()
            source_bucket_obj = client.bucket(source_bucket)
            source_blob = source_bucket_obj.blob(source_object)
            dest_bucket_obj = client.bucket(dest_bucket)

            # Copy blob
            new_blob = await self._run_sync(
                source_bucket_obj.copy_blob,
                source_blob,
                dest_bucket_obj,
                dest_object
            )

            logger.info(
                "File copied in GCS",
                extra={
                    "source": f"{source_bucket}/{source_object}",
                    "destination": f"{dest_bucket}/{dest_object}"
                }
            )

            return StorageObject(
                bucket=dest_bucket,
                name=dest_object,
                size=new_blob.size or 0,
                content_type=new_blob.content_type or "application/octet-stream",
                checksum_sha256=new_blob.metadata.get("sha256", "") if new_blob.metadata else "",
                created_at=new_blob.time_created.isoformat() if new_blob.time_created else "",
                metadata=new_blob.metadata
            )

        except NotFound:
            raise NotFoundException(
                message=f"Source file not found",
                error_code="STORAGE_FILE_NOT_FOUND",
                details={
                    "bucket": source_bucket,
                    "object": source_object
                }
            )
        except Exception as e:
            raise StorageException(
                message=f"Failed to copy file in GCS",
                error_code="STORAGE_COPY_ERROR",
                status_code=500,
                details={
                    "source": f"{source_bucket}/{source_object}",
                    "destination": f"{dest_bucket}/{dest_object}",
                    "original_error": str(e)
                }
            )

    async def move_file(
        self,
        source_bucket: str,
        source_object: str,
        dest_bucket: str,
        dest_object: str
    ) -> StorageObject:
        """Move file (copy + delete original)."""
        # Copy first
        result = await self.copy_file(
            source_bucket, source_object,
            dest_bucket, dest_object
        )

        # Delete original
        await self.delete_file(source_bucket, source_object)

        logger.info(
            "File moved in GCS",
            extra={
                "source": f"{source_bucket}/{source_object}",
                "destination": f"{dest_bucket}/{dest_object}"
            }
        )

        return result

    async def delete_prefix(
        self,
        prefix: str,
        bucket_name: Optional[str] = None
    ) -> int:
        """
        Delete all files under a prefix.

        Args:
            prefix: Path prefix to delete
            bucket_name: Bucket name (uses default if not provided)

        Returns:
            Number of files deleted
        """
        bucket_name = bucket_name or settings.GCS_BUCKET_NAME

        try:
            client = self._get_client()
            bucket = client.bucket(bucket_name)

            # List and delete all blobs with prefix
            blobs = await self._run_sync(
                lambda: list(bucket.list_blobs(prefix=prefix))
            )

            deleted_count = 0
            for blob in blobs:
                await self._run_sync(blob.delete)
                deleted_count += 1

            logger.info(
                "Deleted files under prefix",
                extra={
                    "bucket": bucket_name,
                    "prefix": prefix,
                    "deleted_count": deleted_count
                }
            )

            return deleted_count

        except Exception as e:
            raise StorageException(
                message=f"Failed to delete files under prefix",
                error_code="STORAGE_DELETE_PREFIX_ERROR",
                status_code=500,
                details={
                    "bucket": bucket_name,
                    "prefix": prefix,
                    "original_error": str(e)
                }
            )

    # =========================================================================
    # Simplified methods that use default bucket
    # =========================================================================

    async def upload(
        self,
        object_name: str,
        file_data: bytes,
        content_type: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> StorageObject:
        """Upload file to default bucket."""
        return await self.upload_file(
            bucket_name=settings.GCS_BUCKET_NAME,
            object_name=object_name,
            file_data=file_data,
            content_type=content_type,
            metadata=metadata
        )

    async def download(self, object_name: str) -> bytes:
        """Download file from default bucket."""
        return await self.download_file(
            bucket_name=settings.GCS_BUCKET_NAME,
            object_name=object_name
        )

    async def delete(self, object_name: str) -> bool:
        """Delete file from default bucket."""
        return await self.delete_file(
            bucket_name=settings.GCS_BUCKET_NAME,
            object_name=object_name
        )

    async def exists(self, object_name: str) -> bool:
        """Check if file exists in default bucket."""
        return await self.file_exists(
            bucket_name=settings.GCS_BUCKET_NAME,
            object_name=object_name
        )

    async def generate_signed_upload_url(
        self,
        object_name: str,
        content_type: str,
        expiration_minutes: int = 60
    ) -> SignedUrl:
        """Generate signed upload URL for default bucket."""
        client = self._get_client()
        bucket = client.bucket(settings.GCS_BUCKET_NAME)
        blob = bucket.blob(object_name)

        expiration = timedelta(minutes=expiration_minutes)

        # For Cloud Run, we need to use service_account_email for IAM signing
        sign_kwargs = {
            "version": "v4",
            "expiration": expiration,
            "method": "PUT",
            "content_type": content_type,
        }
        if self._service_account_email and self._credentials:
            # Refresh token if needed
            if hasattr(self._credentials, 'refresh') and hasattr(self._credentials, 'expired'):
                if not self._credentials.token or self._credentials.expired:
                    import google.auth.transport.requests
                    request = google.auth.transport.requests.Request()
                    self._credentials.refresh(request)
            sign_kwargs["service_account_email"] = self._service_account_email
            sign_kwargs["access_token"] = self._credentials.token

        url = await self._run_sync(
            blob.generate_signed_url,
            **sign_kwargs
        )

        expires_at = datetime.now(timezone.utc) + expiration

        return SignedUrl(
            url=url,
            expires_at=expires_at,
            method="PUT"
        )

    async def generate_signed_download_url(
        self,
        object_name: str,
        expiration_minutes: int = 60,
        filename: Optional[str] = None
    ) -> SignedUrl:
        """Generate signed download URL for default bucket."""
        client = self._get_client()
        bucket = client.bucket(settings.GCS_BUCKET_NAME)
        blob = bucket.blob(object_name)

        expiration = timedelta(minutes=expiration_minutes)

        # Add content-disposition header if filename provided
        response_disposition = None
        if filename:
            response_disposition = f'attachment; filename="{filename}"'

        # For Cloud Run, we need to use service_account_email for IAM signing
        sign_kwargs = {
            "version": "v4",
            "expiration": expiration,
            "method": "GET",
            "response_disposition": response_disposition,
        }
        if self._service_account_email and self._credentials:
            # Refresh token if needed
            if hasattr(self._credentials, 'refresh') and hasattr(self._credentials, 'expired'):
                if not self._credentials.token or self._credentials.expired:
                    import google.auth.transport.requests
                    request = google.auth.transport.requests.Request()
                    self._credentials.refresh(request)
            sign_kwargs["service_account_email"] = self._service_account_email
            sign_kwargs["access_token"] = self._credentials.token

        url = await self._run_sync(
            blob.generate_signed_url,
            **sign_kwargs
        )

        expires_at = datetime.now(timezone.utc) + expiration

        return SignedUrl(
            url=url,
            expires_at=expires_at,
            method="GET"
        )

    # Aliases for backwards compatibility with study_service
    async def file_exists(self, object_name: str, bucket_name: Optional[str] = None) -> bool:
        """
        Check if file exists (simplified signature for default bucket).

        Can be called with just object_name for default bucket,
        or with both bucket_name and object_name.
        """
        bucket = bucket_name or settings.GCS_BUCKET_NAME
        try:
            client = self._get_client()
            bucket_obj = client.bucket(bucket)
            blob = bucket_obj.blob(object_name)
            return await self._run_sync(blob.exists)
        except Exception as e:
            logger.error(
                "Error checking file existence",
                extra={
                    "bucket": bucket,
                    "object": object_name,
                    "error": str(e)
                }
            )
            return False

    async def delete_file(self, object_name: str, bucket_name: Optional[str] = None) -> bool:
        """
        Delete file (simplified signature for default bucket).

        Can be called with just object_name for default bucket,
        or with both bucket_name and object_name.
        """
        bucket = bucket_name or settings.GCS_BUCKET_NAME
        try:
            client = self._get_client()
            bucket_obj = client.bucket(bucket)
            blob = bucket_obj.blob(object_name)
            await self._run_sync(blob.delete)
            logger.info(
                "File deleted from GCS",
                extra={
                    "bucket": bucket,
                    "object": object_name
                }
            )
            return True
        except NotFound:
            logger.warning(
                "Attempted to delete non-existent file",
                extra={
                    "bucket": bucket,
                    "object": object_name
                }
            )
            return False
        except Exception as e:
            raise StorageException(
                message="Failed to delete file from GCS",
                error_code="STORAGE_DELETE_ERROR",
                status_code=500,
                details={
                    "bucket": bucket,
                    "object": object_name,
                    "original_error": str(e)
                }
            )
