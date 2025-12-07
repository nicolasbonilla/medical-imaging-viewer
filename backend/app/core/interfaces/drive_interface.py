"""
Interface for Google Drive service.

Defines the contract that any Drive service implementation must follow.
This enables dependency injection and makes the code testable.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from app.models.schemas import DriveFileInfo


class IDriveService(ABC):
    """
    Abstract interface for Google Drive operations.

    This interface defines all operations that a Drive service must implement.
    Implementations can use Google Drive API, mock data for testing, or any other source.
    """

    @abstractmethod
    def authenticate(self) -> bool:
        """
        Authenticate with Google Drive API.

        Returns:
            bool: True if authentication succeeded, False otherwise

        Raises:
            DriveServiceException: If authentication fails critically
        """
        pass

    @abstractmethod
    async def list_files(
        self,
        folder_id: Optional[str] = None,
        mime_types: Optional[List[str]] = None,
        page_size: int = 100
    ) -> List[DriveFileInfo]:
        """
        List files from Google Drive.

        Args:
            folder_id: Optional folder ID to filter files
            mime_types: Optional list of MIME types to filter
            page_size: Number of files to return (default: 100)

        Returns:
            List of DriveFileInfo objects

        Raises:
            DriveServiceException: If listing fails
        """
        pass

    @abstractmethod
    async def download_file(self, file_id: str) -> bytes:
        """
        Download a file from Google Drive.

        Args:
            file_id: The Google Drive file ID

        Returns:
            bytes: The file content

        Raises:
            NotFoundException: If file not found
            DriveServiceException: If download fails
        """
        pass

    @abstractmethod
    async def get_file_metadata(self, file_id: str) -> dict:
        """
        Get metadata for a specific file.

        Args:
            file_id: The Google Drive file ID

        Returns:
            dict: File metadata including name, size, etc.

        Raises:
            NotFoundException: If file not found
            DriveServiceException: If metadata retrieval fails
        """
        pass

    @abstractmethod
    def upload_file(
        self,
        file_path: str,
        filename: str,
        parent_folder_id: Optional[str] = None,
        mime_type: Optional[str] = None
    ) -> str:
        """
        Upload a file to Google Drive.

        Args:
            file_path: Local path to the file
            filename: Name for the file in Drive
            parent_folder_id: Optional parent folder ID
            mime_type: Optional MIME type

        Returns:
            str: The uploaded file ID

        Raises:
            DriveServiceException: If upload fails
        """
        pass

    @abstractmethod
    def list_folders(
        self,
        parent_folder_id: Optional[str] = None
    ) -> List[DriveFileInfo]:
        """
        List folders from Google Drive.

        Args:
            parent_folder_id: Optional parent folder ID

        Returns:
            List of DriveFileInfo objects for folders

        Raises:
            DriveServiceException: If listing fails
        """
        pass
