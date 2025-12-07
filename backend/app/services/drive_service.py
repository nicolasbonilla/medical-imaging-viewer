import os
import io
from typing import List, Optional
from datetime import timedelta
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
import pickle

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.exceptions import DriveServiceException, NotFoundException
from app.core.interfaces.drive_interface import IDriveService
from app.core.interfaces.cache_interface import ICacheService
from app.models.schemas import DriveFileInfo

logger = get_logger(__name__)


class GoogleDriveService(IDriveService):
    """Service for interacting with Google Drive API."""

    def __init__(self, cache_service: Optional[ICacheService] = None):
        self.settings = get_settings()
        self.creds = None
        self.service = None
        self.cache = cache_service

    def authenticate(self) -> bool:
        """Authenticate with Google Drive API."""
        scopes = [self.settings.GOOGLE_DRIVE_SCOPES]

        # Token file stores the user's access and refresh tokens
        if os.path.exists(self.settings.GOOGLE_DRIVE_TOKEN_FILE):
            with open(self.settings.GOOGLE_DRIVE_TOKEN_FILE, 'rb') as token:
                self.creds = pickle.load(token)

        # If no valid credentials, let user log in
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                except Exception as e:
                    # If refresh fails (token revoked/expired), delete token and re-authenticate
                    logger.warning(
                        "Google Drive token refresh failed, removing token file",
                        extra={"error": str(e), "error_type": type(e).__name__}
                    )
                    if os.path.exists(self.settings.GOOGLE_DRIVE_TOKEN_FILE):
                        os.remove(self.settings.GOOGLE_DRIVE_TOKEN_FILE)
                    self.creds = None

            if not self.creds:
                if not os.path.exists(self.settings.GOOGLE_DRIVE_CREDENTIALS_FILE):
                    raise DriveServiceException(
                        message=f"Credentials file not found: {self.settings.GOOGLE_DRIVE_CREDENTIALS_FILE}. "
                                "Please download credentials.json from Google Cloud Console",
                        error_code="DRIVE_CREDENTIALS_NOT_FOUND",
                        status_code=500,
                        details={
                            "credentials_file": self.settings.GOOGLE_DRIVE_CREDENTIALS_FILE
                        }
                    )

                flow = InstalledAppFlow.from_client_secrets_file(
                    self.settings.GOOGLE_DRIVE_CREDENTIALS_FILE, scopes
                )
                self.creds = flow.run_local_server(port=0)

            # Save credentials for next run
            with open(self.settings.GOOGLE_DRIVE_TOKEN_FILE, 'wb') as token:
                pickle.dump(self.creds, token)

        self.service = build('drive', 'v3', credentials=self.creds)
        return True

    async def list_files(
        self,
        folder_id: Optional[str] = None,
        mime_types: Optional[List[str]] = None,
        page_size: int = 100
    ) -> List[DriveFileInfo]:
        """List files from Google Drive with caching."""
        # Create cache key from parameters
        cache_key = f"drive:files:{folder_id or 'root'}:{','.join(mime_types or [])}:{page_size}"

        # Try cache first
        if self.cache:
            cached_files = await self.cache.get(cache_key)
            if cached_files:
                logger.debug(
                    "Cache hit for file list",
                    extra={"folder_id": folder_id, "cache_key": cache_key}
                )
                # Convert cached dicts back to DriveFileInfo objects
                return [DriveFileInfo(**file_dict) for file_dict in cached_files]

        if not self.service:
            self.authenticate()

        query_parts = []

        if folder_id:
            query_parts.append(f"'{folder_id}' in parents")

        if mime_types:
            mime_queries = [f"mimeType='{mt}'" for mt in mime_types]
            query_parts.append(f"({' or '.join(mime_queries)})")

        # Filter for medical imaging files by extension
        extensions = ["dcm", "nii", "nii.gz", "img", "hdr"]
        ext_queries = [f"name contains '.{ext}'" for ext in extensions]
        query_parts.append(f"({' or '.join(ext_queries)})")

        query_parts.append("trashed=false")

        query = " and ".join(query_parts)

        try:
            results = self.service.files().list(
                q=query,
                pageSize=page_size,
                fields="files(id, name, mimeType, size, modifiedTime, webViewLink, thumbnailLink)",
                includeItemsFromAllDrives=True,
                supportsAllDrives=True
            ).execute()

            files = results.get('files', [])

            file_infos = [
                DriveFileInfo(
                    id=file['id'],
                    name=file['name'],
                    mimeType=file['mimeType'],
                    size=int(file.get('size', 0)) if file.get('size') else None,
                    modifiedTime=file.get('modifiedTime'),
                    webViewLink=file.get('webViewLink'),
                    thumbnailLink=file.get('thumbnailLink')
                )
                for file in files
            ]

            # Store in cache (convert to dicts for serialization)
            if self.cache:
                file_dicts = [file_info.model_dump() for file_info in file_infos]
                await self.cache.set(
                    cache_key,
                    file_dicts,
                    ttl=timedelta(seconds=self.settings.CACHE_DRIVE_FILES_TTL)
                )
                logger.debug(
                    "Cached file list",
                    extra={"folder_id": folder_id, "count": len(file_infos), "cache_key": cache_key}
                )

            return file_infos
        except DriveServiceException:
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            raise DriveServiceException(
                message="Failed to list files from Google Drive",
                error_code="DRIVE_LIST_FILES_ERROR",
                status_code=500,
                details={
                    "original_error": str(e),
                    "error_type": type(e).__name__,
                    "folder_id": folder_id
                }
            )

    async def download_file(self, file_id: str) -> bytes:
        """Download a file from Google Drive with caching."""
        # Try cache first
        cache_key = f"drive:file:{file_id}"

        if self.cache:
            cached_data = await self.cache.get(cache_key)
            if cached_data:
                logger.debug(f"Cache hit for file download: {file_id}")
                return cached_data

        if not self.service:
            self.authenticate()

        try:
            request = self.service.files().get_media(fileId=file_id)
            file_buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(file_buffer, request)

            done = False
            while not done:
                status, done = downloader.next_chunk()

            file_buffer.seek(0)
            file_data = file_buffer.read()

            # Store in cache
            if self.cache:
                await self.cache.set(
                    cache_key,
                    file_data,
                    ttl=timedelta(seconds=self.settings.CACHE_DRIVE_FILES_TTL)
                )
                logger.debug(
                    f"Cached file download: {file_id}",
                    extra={"file_id": file_id, "size_bytes": len(file_data)}
                )

            return file_data
        except DriveServiceException:
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            # Check if it's a 404 not found error
            error_str = str(e).lower()
            if 'not found' in error_str or '404' in error_str:
                raise NotFoundException(
                    message=f"File not found in Google Drive",
                    error_code="DRIVE_FILE_NOT_FOUND",
                    details={
                        "file_id": file_id,
                        "original_error": str(e)
                    }
                )
            else:
                raise DriveServiceException(
                    message="Failed to download file from Google Drive",
                    error_code="DRIVE_DOWNLOAD_ERROR",
                    status_code=500,
                    details={
                        "file_id": file_id,
                        "original_error": str(e),
                        "error_type": type(e).__name__
                    }
                )

    async def get_file_metadata(self, file_id: str) -> dict:
        """Get metadata for a specific file including parent folder with caching."""
        # Try cache first
        cache_key = f"drive:metadata:{file_id}"

        if self.cache:
            cached_metadata = await self.cache.get(cache_key)
            if cached_metadata:
                logger.debug(f"Cache hit for file metadata: {file_id}")
                return cached_metadata

        if not self.service:
            self.authenticate()

        try:
            file = self.service.files().get(
                fileId=file_id,
                fields="id, name, mimeType, size, modifiedTime, webViewLink, thumbnailLink, parents"
            ).execute()

            metadata = {
                'id': file['id'],
                'name': file['name'],
                'mimeType': file['mimeType'],
                'size': int(file.get('size', 0)) if file.get('size') else None,
                'modifiedTime': file.get('modifiedTime'),
                'webViewLink': file.get('webViewLink'),
                'thumbnailLink': file.get('thumbnailLink'),
                'parents': file.get('parents', [])  # List of parent folder IDs
            }

            # Store in cache
            if self.cache:
                await self.cache.set(
                    cache_key,
                    metadata,
                    ttl=timedelta(seconds=self.settings.CACHE_METADATA_TTL)
                )
                logger.debug(f"Cached file metadata: {file_id}")

            return metadata
        except DriveServiceException:
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            # Check if it's a 404 not found error
            error_str = str(e).lower()
            if 'not found' in error_str or '404' in error_str:
                raise NotFoundException(
                    message=f"File not found in Google Drive",
                    error_code="DRIVE_FILE_NOT_FOUND",
                    details={
                        "file_id": file_id,
                        "original_error": str(e)
                    }
                )
            else:
                raise DriveServiceException(
                    message="Failed to get file metadata from Google Drive",
                    error_code="DRIVE_METADATA_ERROR",
                    status_code=500,
                    details={
                        "file_id": file_id,
                        "original_error": str(e),
                        "error_type": type(e).__name__
                    }
                )

    def upload_file(self, file_path: str, filename: str, parent_folder_id: Optional[str] = None, mime_type: str = None) -> str:
        """Upload a file to Google Drive.

        Args:
            file_path: Local path to the file to upload
            filename: Name for the file in Google Drive
            parent_folder_id: ID of parent folder (optional)
            mime_type: MIME type of the file (optional, will be auto-detected)

        Returns:
            File ID of the uploaded file
        """
        if not self.service:
            self.authenticate()

        try:
            file_metadata = {
                'name': filename
            }

            if parent_folder_id:
                file_metadata['parents'] = [parent_folder_id]

            media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)

            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, webViewLink',
                supportsAllDrives=True
            ).execute()

            logger.info(
                "File uploaded to Google Drive",
                extra={
                    "filename": filename,
                    "file_id": file.get('id'),
                    "mime_type": mime_type
                }
            )
            return file.get('id')
        except DriveServiceException:
            # Re-raise our custom exceptions
            raise
        except FileNotFoundError as e:
            raise DriveServiceException(
                message=f"Local file not found: {file_path}",
                error_code="DRIVE_LOCAL_FILE_NOT_FOUND",
                status_code=400,
                details={
                    "file_path": file_path,
                    "filename": filename,
                    "original_error": str(e)
                }
            )
        except Exception as e:
            raise DriveServiceException(
                message="Failed to upload file to Google Drive",
                error_code="DRIVE_UPLOAD_ERROR",
                status_code=500,
                details={
                    "filename": filename,
                    "file_path": file_path,
                    "parent_folder_id": parent_folder_id,
                    "original_error": str(e),
                    "error_type": type(e).__name__
                }
            )

    def list_folders(self, parent_folder_id: Optional[str] = None) -> List[DriveFileInfo]:
        """List all folders in Drive."""
        if not self.service:
            self.authenticate()

        # When no parent_id, get ALL folders (not just root)
        # This allows users to see folders that might not have explicit parents
        if parent_folder_id:
            query = f"'{parent_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
        else:
            query = "mimeType='application/vnd.google-apps.folder' and trashed=false"

        try:
            results = self.service.files().list(
                q=query,
                pageSize=1000,  # Increased to show more folders
                fields="files(id, name, mimeType, modifiedTime)",
                includeItemsFromAllDrives=True,
                supportsAllDrives=True
            ).execute()

            folders = results.get('files', [])

            # Sort alphabetically by name
            folders_sorted = sorted(folders, key=lambda x: x['name'].lower())

            return [
                DriveFileInfo(
                    id=folder['id'],
                    name=folder['name'],
                    mimeType=folder['mimeType'],
                    modifiedTime=folder.get('modifiedTime')
                )
                for folder in folders_sorted
            ]
        except DriveServiceException:
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            raise DriveServiceException(
                message="Failed to list folders from Google Drive",
                error_code="DRIVE_LIST_FOLDERS_ERROR",
                status_code=500,
                details={
                    "parent_folder_id": parent_folder_id,
                    "original_error": str(e),
                    "error_type": type(e).__name__
                }
            )
