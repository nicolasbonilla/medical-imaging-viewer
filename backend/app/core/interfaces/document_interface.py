"""
Document Service Interface.

Defines the contract for clinical document management operations.

@module core.interfaces.document_interface
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Tuple
from uuid import UUID

from app.models.document_schemas import (
    DocumentCreate,
    DocumentUpdate,
    DocumentResponse,
    DocumentSummary,
    DocumentSearch,
    DocumentVersionResponse,
    DocumentUploadInit,
    DocumentUploadInitResponse,
    DocumentUploadComplete,
    DocumentUploadCompleteResponse,
    VersionUploadInit,
    VersionUploadInitResponse,
    VersionUploadComplete,
    VersionUploadCompleteResponse,
    DocumentDownloadUrl,
)


class IDocumentService(ABC):
    """
    Interface for clinical document operations.

    Manages documents with versioning and GCS storage.
    """

    # =========================================================================
    # Document CRUD Operations
    # =========================================================================

    @abstractmethod
    async def create_document(
        self,
        data: DocumentCreate,
        filename: str,
        content_type: str,
        file_size_bytes: int,
        checksum_sha256: str,
        gcs_object_name: str,
        created_by: Optional[UUID] = None
    ) -> DocumentResponse:
        """
        Create a new document record.

        Args:
            data: Document metadata
            filename: Original filename
            content_type: MIME type
            file_size_bytes: File size
            checksum_sha256: File checksum
            gcs_object_name: GCS object path
            created_by: User ID who created

        Returns:
            Created document
        """
        pass

    @abstractmethod
    async def get_document(
        self,
        document_id: UUID
    ) -> DocumentResponse:
        """
        Get a document by ID.

        Args:
            document_id: Document UUID

        Returns:
            Document data

        Raises:
            NotFoundException: If document not found
        """
        pass

    @abstractmethod
    async def update_document(
        self,
        document_id: UUID,
        data: DocumentUpdate,
        updated_by: Optional[UUID] = None
    ) -> DocumentResponse:
        """
        Update document metadata.

        Args:
            document_id: Document UUID
            data: Fields to update
            updated_by: User ID

        Returns:
            Updated document

        Raises:
            NotFoundException: If document not found
        """
        pass

    @abstractmethod
    async def delete_document(
        self,
        document_id: UUID,
        deleted_by: Optional[UUID] = None,
        hard_delete: bool = False
    ) -> bool:
        """
        Delete a document.

        Args:
            document_id: Document UUID
            deleted_by: User ID
            hard_delete: If True, delete from GCS too

        Returns:
            True if deleted

        Raises:
            NotFoundException: If document not found
        """
        pass

    @abstractmethod
    async def search_documents(
        self,
        search: DocumentSearch
    ) -> Tuple[List[DocumentSummary], int]:
        """
        Search documents with filters and pagination.

        Args:
            search: Search parameters

        Returns:
            Tuple of (documents, total_count)
        """
        pass

    @abstractmethod
    async def list_patient_documents(
        self,
        patient_id: UUID,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[DocumentSummary], int]:
        """
        List all documents for a patient.

        Args:
            patient_id: Patient UUID
            page: Page number
            page_size: Items per page

        Returns:
            Tuple of (documents, total_count)
        """
        pass

    @abstractmethod
    async def list_study_documents(
        self,
        study_id: UUID,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[DocumentSummary], int]:
        """
        List all documents linked to a study.

        Args:
            study_id: Study UUID
            page: Page number
            page_size: Items per page

        Returns:
            Tuple of (documents, total_count)
        """
        pass

    # =========================================================================
    # Version Operations
    # =========================================================================

    @abstractmethod
    async def create_version(
        self,
        document_id: UUID,
        filename: str,
        content_type: str,
        file_size_bytes: int,
        checksum_sha256: str,
        gcs_object_name: str,
        change_summary: Optional[str] = None,
        created_by: Optional[UUID] = None
    ) -> DocumentVersionResponse:
        """
        Create a new version of a document.

        Args:
            document_id: Document UUID
            filename: New version filename
            content_type: MIME type
            file_size_bytes: File size
            checksum_sha256: Checksum
            gcs_object_name: GCS path
            change_summary: Description of changes
            created_by: User ID

        Returns:
            Created version
        """
        pass

    @abstractmethod
    async def get_version(
        self,
        version_id: UUID
    ) -> DocumentVersionResponse:
        """
        Get a specific version by ID.

        Args:
            version_id: Version UUID

        Returns:
            Version data

        Raises:
            NotFoundException: If version not found
        """
        pass

    @abstractmethod
    async def list_versions(
        self,
        document_id: UUID
    ) -> List[DocumentVersionResponse]:
        """
        List all versions of a document.

        Args:
            document_id: Document UUID

        Returns:
            List of versions, ordered by version number desc
        """
        pass

    @abstractmethod
    async def get_latest_version(
        self,
        document_id: UUID
    ) -> DocumentVersionResponse:
        """
        Get the latest version of a document.

        Args:
            document_id: Document UUID

        Returns:
            Latest version

        Raises:
            NotFoundException: If document not found
        """
        pass

    # =========================================================================
    # Upload Operations
    # =========================================================================

    @abstractmethod
    async def init_upload(
        self,
        request: DocumentUploadInit,
        user_id: Optional[UUID] = None
    ) -> DocumentUploadInitResponse:
        """
        Initialize a new document upload.

        Generates a signed URL and pre-creates the document record.

        Args:
            request: Upload parameters
            user_id: Uploading user ID

        Returns:
            Signed URL and upload session info
        """
        pass

    @abstractmethod
    async def complete_upload(
        self,
        request: DocumentUploadComplete,
        user_id: Optional[UUID] = None
    ) -> DocumentUploadCompleteResponse:
        """
        Complete an upload and finalize the document.

        Verifies checksum and marks document as available.

        Args:
            request: Completion info with checksum
            user_id: User ID

        Returns:
            Finalized document

        Raises:
            ValidationException: If checksum mismatch
        """
        pass

    @abstractmethod
    async def init_version_upload(
        self,
        request: VersionUploadInit,
        user_id: Optional[UUID] = None
    ) -> VersionUploadInitResponse:
        """
        Initialize upload for a new version.

        Args:
            request: Upload parameters
            user_id: User ID

        Returns:
            Signed URL and version info
        """
        pass

    @abstractmethod
    async def complete_version_upload(
        self,
        request: VersionUploadComplete,
        user_id: Optional[UUID] = None
    ) -> VersionUploadCompleteResponse:
        """
        Complete a version upload.

        Args:
            request: Completion info
            user_id: User ID

        Returns:
            Updated document and new version
        """
        pass

    # =========================================================================
    # Download Operations
    # =========================================================================

    @abstractmethod
    async def get_download_url(
        self,
        document_id: UUID,
        version: Optional[int] = None,
        expiration_minutes: int = 60
    ) -> DocumentDownloadUrl:
        """
        Get a signed download URL for a document.

        Args:
            document_id: Document UUID
            version: Specific version (None = latest)
            expiration_minutes: URL validity duration

        Returns:
            Signed download URL
        """
        pass

    @abstractmethod
    async def get_patient_documents_urls(
        self,
        patient_id: UUID,
        expiration_minutes: int = 60
    ) -> List[DocumentDownloadUrl]:
        """
        Get download URLs for all patient documents.

        Args:
            patient_id: Patient UUID
            expiration_minutes: URL validity

        Returns:
            List of download URLs
        """
        pass
