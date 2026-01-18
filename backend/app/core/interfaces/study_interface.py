"""
Study Service Interface.

Defines the contract for imaging study management operations.

@module core.interfaces.study_interface
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Tuple
from uuid import UUID
from datetime import datetime

from app.models.study_schemas import (
    StudyCreate,
    StudyUpdate,
    StudyResponse,
    StudySummary,
    StudySearch,
    SeriesCreate,
    SeriesResponse,
    InstanceCreate,
    InstanceResponse,
    UploadInitRequest,
    UploadInitResponse,
    UploadCompleteRequest,
    UploadCompleteResponse
)


class IStudyService(ABC):
    """
    Interface for imaging study operations.

    Manages DICOM/NIfTI studies, series, and instances with GCS storage.
    """

    # =========================================================================
    # Study Operations
    # =========================================================================

    @abstractmethod
    async def create_study(
        self,
        data: StudyCreate,
        created_by: Optional[UUID] = None
    ) -> StudyResponse:
        """
        Create a new imaging study.

        Args:
            data: Study creation data
            created_by: User ID who created the study

        Returns:
            Created study with generated accession number and UIDs
        """
        pass

    @abstractmethod
    async def get_study(
        self,
        study_id: UUID,
        include_stats: bool = False
    ) -> StudyResponse:
        """
        Get a study by ID.

        Args:
            study_id: Study UUID
            include_stats: Whether to include series/instance counts

        Returns:
            Study data

        Raises:
            NotFoundException: If study not found
        """
        pass

    @abstractmethod
    async def get_study_by_accession(
        self,
        accession_number: str
    ) -> Optional[StudyResponse]:
        """
        Get a study by accession number.

        Args:
            accession_number: Hospital-assigned accession number

        Returns:
            Study data or None if not found
        """
        pass

    @abstractmethod
    async def update_study(
        self,
        study_id: UUID,
        data: StudyUpdate,
        updated_by: Optional[UUID] = None
    ) -> StudyResponse:
        """
        Update a study.

        Args:
            study_id: Study UUID
            data: Fields to update
            updated_by: User ID who updated

        Returns:
            Updated study

        Raises:
            NotFoundException: If study not found
        """
        pass

    @abstractmethod
    async def delete_study(
        self,
        study_id: UUID,
        deleted_by: Optional[UUID] = None,
        hard_delete: bool = False
    ) -> bool:
        """
        Delete or cancel a study.

        Args:
            study_id: Study UUID
            deleted_by: User ID who deleted
            hard_delete: If True, delete from GCS; else just mark cancelled

        Returns:
            True if deleted

        Raises:
            NotFoundException: If study not found
        """
        pass

    @abstractmethod
    async def search_studies(
        self,
        search: StudySearch
    ) -> Tuple[List[StudySummary], int]:
        """
        Search studies with filters and pagination.

        Args:
            search: Search parameters

        Returns:
            Tuple of (studies, total_count)
        """
        pass

    @abstractmethod
    async def list_patient_studies(
        self,
        patient_id: UUID,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[StudySummary], int]:
        """
        List all studies for a patient.

        Args:
            patient_id: Patient UUID
            page: Page number
            page_size: Items per page

        Returns:
            Tuple of (studies, total_count)
        """
        pass

    # =========================================================================
    # Series Operations
    # =========================================================================

    @abstractmethod
    async def create_series(
        self,
        data: SeriesCreate
    ) -> SeriesResponse:
        """
        Create a new series within a study.

        Args:
            data: Series creation data

        Returns:
            Created series with generated UID
        """
        pass

    @abstractmethod
    async def get_series(
        self,
        series_id: UUID
    ) -> SeriesResponse:
        """
        Get a series by ID.

        Args:
            series_id: Series UUID

        Returns:
            Series data

        Raises:
            NotFoundException: If series not found
        """
        pass

    @abstractmethod
    async def list_study_series(
        self,
        study_id: UUID
    ) -> List[SeriesResponse]:
        """
        List all series in a study.

        Args:
            study_id: Study UUID

        Returns:
            List of series
        """
        pass

    @abstractmethod
    async def delete_series(
        self,
        series_id: UUID
    ) -> bool:
        """
        Delete a series and all its instances from GCS.

        Args:
            series_id: Series UUID

        Returns:
            True if deleted
        """
        pass

    # =========================================================================
    # Instance Operations
    # =========================================================================

    @abstractmethod
    async def register_instance(
        self,
        data: InstanceCreate
    ) -> InstanceResponse:
        """
        Register a new instance in the database.

        Args:
            data: Instance metadata

        Returns:
            Created instance record
        """
        pass

    @abstractmethod
    async def get_instance(
        self,
        instance_id: UUID
    ) -> InstanceResponse:
        """
        Get an instance by ID.

        Args:
            instance_id: Instance UUID

        Returns:
            Instance data with metadata

        Raises:
            NotFoundException: If instance not found
        """
        pass

    @abstractmethod
    async def list_series_instances(
        self,
        series_id: UUID
    ) -> List[InstanceResponse]:
        """
        List all instances in a series.

        Args:
            series_id: Series UUID

        Returns:
            List of instances
        """
        pass

    @abstractmethod
    async def delete_instance(
        self,
        instance_id: UUID
    ) -> bool:
        """
        Delete an instance from database and GCS.

        Args:
            instance_id: Instance UUID

        Returns:
            True if deleted
        """
        pass

    # =========================================================================
    # Upload Operations
    # =========================================================================

    @abstractmethod
    async def init_upload(
        self,
        request: UploadInitRequest,
        user_id: Optional[UUID] = None
    ) -> UploadInitResponse:
        """
        Initialize a file upload to GCS.

        Generates a signed URL for direct upload to GCS.

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
        request: UploadCompleteRequest,
        user_id: Optional[UUID] = None
    ) -> UploadCompleteResponse:
        """
        Complete an upload and register the instance.

        Verifies checksum, extracts DICOM metadata, creates instance record.

        Args:
            request: Completion info with checksum
            user_id: User ID

        Returns:
            Created instance info

        Raises:
            ValidationException: If checksum mismatch or invalid file
        """
        pass

    @abstractmethod
    async def get_download_url(
        self,
        instance_id: UUID,
        expiration_minutes: int = 60
    ) -> str:
        """
        Get a signed download URL for an instance.

        Args:
            instance_id: Instance UUID
            expiration_minutes: URL validity duration

        Returns:
            Signed download URL
        """
        pass

    @abstractmethod
    async def get_study_download_urls(
        self,
        study_id: UUID,
        expiration_minutes: int = 60
    ) -> List[dict]:
        """
        Get download URLs for all instances in a study.

        Args:
            study_id: Study UUID
            expiration_minutes: URL validity duration

        Returns:
            List of {instance_id, url, filename}
        """
        pass

    # =========================================================================
    # DICOM Metadata
    # =========================================================================

    @abstractmethod
    async def extract_dicom_metadata(
        self,
        file_data: bytes,
        filename: str
    ) -> dict:
        """
        Extract metadata from a DICOM file.

        Args:
            file_data: Raw file bytes
            filename: Original filename

        Returns:
            Dictionary of DICOM tags and values
        """
        pass

    @abstractmethod
    async def update_instance_metadata(
        self,
        instance_id: UUID,
        metadata: dict
    ) -> InstanceResponse:
        """
        Update instance with extracted DICOM metadata.

        Args:
            instance_id: Instance UUID
            metadata: Extracted DICOM metadata

        Returns:
            Updated instance
        """
        pass
