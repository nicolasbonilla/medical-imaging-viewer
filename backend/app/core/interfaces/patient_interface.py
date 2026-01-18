"""
Patient service interface.

@module core.interfaces.patient_interface
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Tuple
from uuid import UUID

from app.models.patient_schemas import (
    PatientCreate,
    PatientUpdate,
    PatientSearch,
    PatientResponse,
    PatientSummary,
    MedicalHistoryCreate,
    MedicalHistoryResponse
)


class IPatientService(ABC):
    """
    Interface for patient management operations.

    Implementations:
    - PatientService (production)
    - MockPatientService (testing)
    """

    @abstractmethod
    async def create_patient(
        self,
        data: PatientCreate,
        created_by: Optional[UUID] = None
    ) -> PatientResponse:
        """
        Create a new patient record.

        Args:
            data: Patient creation data
            created_by: UUID of user creating the record

        Returns:
            Created patient record

        Raises:
            ConflictException: If MRN already exists
            ValidationException: If data validation fails
        """
        pass

    @abstractmethod
    async def get_patient(
        self,
        patient_id: UUID,
        include_stats: bool = False
    ) -> PatientResponse:
        """
        Get a patient by ID.

        Args:
            patient_id: Patient UUID
            include_stats: Include study/document counts

        Returns:
            Patient record

        Raises:
            NotFoundException: If patient not found
        """
        pass

    @abstractmethod
    async def get_patient_by_mrn(
        self,
        mrn: str
    ) -> Optional[PatientResponse]:
        """
        Get a patient by MRN.

        Args:
            mrn: Medical Record Number

        Returns:
            Patient record or None if not found
        """
        pass

    @abstractmethod
    async def update_patient(
        self,
        patient_id: UUID,
        data: PatientUpdate,
        updated_by: Optional[UUID] = None
    ) -> PatientResponse:
        """
        Update a patient record.

        Args:
            patient_id: Patient UUID
            data: Update data (partial)
            updated_by: UUID of user updating the record

        Returns:
            Updated patient record

        Raises:
            NotFoundException: If patient not found
            ValidationException: If data validation fails
        """
        pass

    @abstractmethod
    async def delete_patient(
        self,
        patient_id: UUID,
        deleted_by: Optional[UUID] = None
    ) -> bool:
        """
        Soft delete a patient (set status to inactive).

        Args:
            patient_id: Patient UUID
            deleted_by: UUID of user deleting the record

        Returns:
            True if deleted

        Raises:
            NotFoundException: If patient not found
        """
        pass

    @abstractmethod
    async def search_patients(
        self,
        search: PatientSearch
    ) -> Tuple[List[PatientSummary], int]:
        """
        Search patients with filters and pagination.

        Args:
            search: Search parameters

        Returns:
            Tuple of (patient list, total count)
        """
        pass

    @abstractmethod
    async def list_patients(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None
    ) -> Tuple[List[PatientSummary], int]:
        """
        List all patients with pagination.

        Args:
            page: Page number
            page_size: Items per page
            status: Optional status filter

        Returns:
            Tuple of (patient list, total count)
        """
        pass

    # Medical History

    @abstractmethod
    async def add_medical_history(
        self,
        patient_id: UUID,
        data: MedicalHistoryCreate,
        recorded_by: Optional[str] = None
    ) -> MedicalHistoryResponse:
        """
        Add a medical history entry for a patient.

        Args:
            patient_id: Patient UUID
            data: Medical history data
            recorded_by: Name of recording clinician

        Returns:
            Created medical history entry

        Raises:
            NotFoundException: If patient not found
        """
        pass

    @abstractmethod
    async def get_medical_history(
        self,
        patient_id: UUID,
        active_only: bool = False
    ) -> List[MedicalHistoryResponse]:
        """
        Get medical history for a patient.

        Args:
            patient_id: Patient UUID
            active_only: Return only active conditions

        Returns:
            List of medical history entries

        Raises:
            NotFoundException: If patient not found
        """
        pass

    @abstractmethod
    async def update_medical_history(
        self,
        history_id: UUID,
        is_active: bool,
        resolution_date: Optional[str] = None
    ) -> MedicalHistoryResponse:
        """
        Update a medical history entry (typically to mark as resolved).

        Args:
            history_id: Medical history entry UUID
            is_active: New active status
            resolution_date: Date condition resolved

        Returns:
            Updated medical history entry

        Raises:
            NotFoundException: If entry not found
        """
        pass
