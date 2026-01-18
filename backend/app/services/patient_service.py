"""
Patient Service Implementation.

Manages patient demographics, medical history, and related operations
following HL7 FHIR standards.

@module services.patient_service
"""

from typing import Optional, List, Tuple
from uuid import UUID
from datetime import date
import logging

from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.interfaces.patient_interface import IPatientService
from app.core.exceptions import NotFoundException, ConflictException, ValidationException
from app.models.database import Patient, MedicalHistory, ImagingStudy, Document
from app.models.patient_schemas import (
    PatientCreate,
    PatientUpdate,
    PatientSearch,
    PatientResponse,
    PatientSummary,
    MedicalHistoryCreate,
    MedicalHistoryResponse,
    PatientStatus
)

logger = logging.getLogger(__name__)


class PatientService(IPatientService):
    """
    Patient service implementation with PostgreSQL backend.
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize patient service.

        Args:
            db: Async database session
        """
        self.db = db

    def _patient_to_response(
        self,
        patient: Patient,
        study_count: Optional[int] = None,
        document_count: Optional[int] = None
    ) -> PatientResponse:
        """Convert Patient model to PatientResponse."""
        return PatientResponse(
            id=patient.id,
            mrn=patient.mrn,
            given_name=patient.given_name,
            middle_name=patient.middle_name,
            family_name=patient.family_name,
            name_prefix=patient.name_prefix,
            name_suffix=patient.name_suffix,
            full_name=patient.full_name,
            birth_date=patient.birth_date,
            gender=patient.gender,
            age=patient.age,
            phone_home=patient.phone_home,
            phone_mobile=patient.phone_mobile,
            phone_work=patient.phone_work,
            email=patient.email,
            address_line1=patient.address_line1,
            address_line2=patient.address_line2,
            city=patient.city,
            state=patient.state,
            postal_code=patient.postal_code,
            country=patient.country,
            emergency_contact_name=patient.emergency_contact_name,
            emergency_contact_phone=patient.emergency_contact_phone,
            emergency_contact_relationship=patient.emergency_contact_relationship,
            insurance_provider=patient.insurance_provider,
            insurance_policy_number=patient.insurance_policy_number,
            status=patient.status,
            deceased_date=patient.deceased_date,
            created_at=patient.created_at,
            updated_at=patient.updated_at,
            study_count=study_count,
            document_count=document_count
        )

    def _patient_to_summary(self, patient: Patient) -> PatientSummary:
        """Convert Patient model to PatientSummary."""
        return PatientSummary(
            id=patient.id,
            mrn=patient.mrn,
            full_name=patient.full_name,
            birth_date=patient.birth_date,
            gender=patient.gender,
            status=patient.status
        )

    async def create_patient(
        self,
        data: PatientCreate,
        created_by: Optional[UUID] = None
    ) -> PatientResponse:
        """Create a new patient record."""
        # Check if MRN already exists
        existing = await self.db.execute(
            select(Patient).where(Patient.mrn == data.mrn)
        )
        if existing.scalar_one_or_none():
            raise ConflictException(
                message=f"Patient with MRN '{data.mrn}' already exists",
                error_code="PATIENT_MRN_EXISTS",
                details={"mrn": data.mrn}
            )

        # Create patient
        patient = Patient(
            mrn=data.mrn,
            given_name=data.given_name,
            middle_name=data.middle_name,
            family_name=data.family_name,
            name_prefix=data.name_prefix,
            name_suffix=data.name_suffix,
            birth_date=data.birth_date,
            gender=data.gender,
            phone_home=data.phone_home,
            phone_mobile=data.phone_mobile,
            phone_work=data.phone_work,
            email=data.email,
            address_line1=data.address_line1,
            address_line2=data.address_line2,
            city=data.city,
            state=data.state,
            postal_code=data.postal_code,
            country=data.country,
            emergency_contact_name=data.emergency_contact_name,
            emergency_contact_phone=data.emergency_contact_phone,
            emergency_contact_relationship=data.emergency_contact_relationship,
            insurance_provider=data.insurance_provider,
            insurance_policy_number=data.insurance_policy_number,
            created_by=created_by
        )

        self.db.add(patient)
        await self.db.flush()
        await self.db.refresh(patient)

        logger.info(
            "Patient created",
            extra={
                "patient_id": str(patient.id),
                "mrn": patient.mrn,
                "created_by": str(created_by) if created_by else None
            }
        )

        return self._patient_to_response(patient, study_count=0, document_count=0)

    async def get_patient(
        self,
        patient_id: UUID,
        include_stats: bool = False
    ) -> PatientResponse:
        """Get a patient by ID."""
        result = await self.db.execute(
            select(Patient).where(Patient.id == patient_id)
        )
        patient = result.scalar_one_or_none()

        if not patient:
            raise NotFoundException(
                message="Patient not found",
                error_code="PATIENT_NOT_FOUND",
                details={"patient_id": str(patient_id)}
            )

        study_count = None
        document_count = None

        if include_stats:
            # Get study count
            study_result = await self.db.execute(
                select(func.count(ImagingStudy.id))
                .where(ImagingStudy.patient_id == patient_id)
            )
            study_count = study_result.scalar() or 0

            # Get document count
            doc_result = await self.db.execute(
                select(func.count(Document.id))
                .where(Document.patient_id == patient_id)
            )
            document_count = doc_result.scalar() or 0

        return self._patient_to_response(patient, study_count, document_count)

    async def get_patient_by_mrn(self, mrn: str) -> Optional[PatientResponse]:
        """Get a patient by MRN."""
        result = await self.db.execute(
            select(Patient).where(Patient.mrn == mrn.upper())
        )
        patient = result.scalar_one_or_none()

        if not patient:
            return None

        return self._patient_to_response(patient)

    async def update_patient(
        self,
        patient_id: UUID,
        data: PatientUpdate,
        updated_by: Optional[UUID] = None
    ) -> PatientResponse:
        """Update a patient record."""
        result = await self.db.execute(
            select(Patient).where(Patient.id == patient_id)
        )
        patient = result.scalar_one_or_none()

        if not patient:
            raise NotFoundException(
                message="Patient not found",
                error_code="PATIENT_NOT_FOUND",
                details={"patient_id": str(patient_id)}
            )

        # Update only provided fields
        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(patient, field, value)

        patient.updated_by = updated_by

        await self.db.flush()
        await self.db.refresh(patient)

        logger.info(
            "Patient updated",
            extra={
                "patient_id": str(patient_id),
                "updated_fields": list(update_data.keys()),
                "updated_by": str(updated_by) if updated_by else None
            }
        )

        return self._patient_to_response(patient)

    async def delete_patient(
        self,
        patient_id: UUID,
        deleted_by: Optional[UUID] = None
    ) -> bool:
        """Soft delete a patient (set status to inactive)."""
        result = await self.db.execute(
            select(Patient).where(Patient.id == patient_id)
        )
        patient = result.scalar_one_or_none()

        if not patient:
            raise NotFoundException(
                message="Patient not found",
                error_code="PATIENT_NOT_FOUND",
                details={"patient_id": str(patient_id)}
            )

        patient.status = PatientStatus.INACTIVE
        patient.updated_by = deleted_by

        await self.db.flush()

        logger.info(
            "Patient deactivated",
            extra={
                "patient_id": str(patient_id),
                "deleted_by": str(deleted_by) if deleted_by else None
            }
        )

        return True

    async def search_patients(
        self,
        search: PatientSearch
    ) -> Tuple[List[PatientSummary], int]:
        """Search patients with filters and pagination."""
        # Base query
        query = select(Patient)
        count_query = select(func.count(Patient.id))

        # Apply filters
        conditions = []

        if search.query:
            # Full-text search on name, MRN, email
            search_term = f"%{search.query}%"
            conditions.append(
                or_(
                    Patient.mrn.ilike(search_term),
                    Patient.given_name.ilike(search_term),
                    Patient.family_name.ilike(search_term),
                    Patient.email.ilike(search_term)
                )
            )

        if search.mrn:
            conditions.append(Patient.mrn == search.mrn.upper())

        if search.family_name:
            conditions.append(Patient.family_name.ilike(f"%{search.family_name}%"))

        if search.given_name:
            conditions.append(Patient.given_name.ilike(f"%{search.given_name}%"))

        if search.birth_date:
            conditions.append(Patient.birth_date == search.birth_date)

        if search.gender:
            conditions.append(Patient.gender == search.gender)

        if search.status:
            conditions.append(Patient.status == search.status)

        if search.city:
            conditions.append(Patient.city.ilike(f"%{search.city}%"))

        # Apply conditions
        if conditions:
            query = query.where(and_(*conditions))
            count_query = count_query.where(and_(*conditions))

        # Get total count
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply sorting
        sort_column = getattr(Patient, search.sort_by, Patient.family_name)
        if search.sort_order == "desc":
            sort_column = sort_column.desc()
        query = query.order_by(sort_column)

        # Apply pagination
        offset = (search.page - 1) * search.page_size
        query = query.offset(offset).limit(search.page_size)

        # Execute
        result = await self.db.execute(query)
        patients = result.scalars().all()

        return [self._patient_to_summary(p) for p in patients], total

    async def list_patients(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None
    ) -> Tuple[List[PatientSummary], int]:
        """List all patients with pagination."""
        query = select(Patient)
        count_query = select(func.count(Patient.id))

        if status:
            query = query.where(Patient.status == status)
            count_query = count_query.where(Patient.status == status)

        # Get total
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.order_by(Patient.family_name, Patient.given_name)
        query = query.offset(offset).limit(page_size)

        result = await self.db.execute(query)
        patients = result.scalars().all()

        return [self._patient_to_summary(p) for p in patients], total

    # Medical History

    async def add_medical_history(
        self,
        patient_id: UUID,
        data: MedicalHistoryCreate,
        recorded_by: Optional[str] = None
    ) -> MedicalHistoryResponse:
        """Add a medical history entry for a patient."""
        # Verify patient exists
        patient_result = await self.db.execute(
            select(Patient.id).where(Patient.id == patient_id)
        )
        if not patient_result.scalar_one_or_none():
            raise NotFoundException(
                message="Patient not found",
                error_code="PATIENT_NOT_FOUND",
                details={"patient_id": str(patient_id)}
            )

        history = MedicalHistory(
            patient_id=patient_id,
            condition_name=data.condition_name,
            condition_code=data.condition_code,
            condition_system=data.condition_system,
            is_active=data.is_active,
            onset_date=data.onset_date,
            resolution_date=data.resolution_date,
            severity=data.severity,
            notes=data.notes,
            recorded_by=recorded_by
        )

        self.db.add(history)
        await self.db.flush()
        await self.db.refresh(history)

        logger.info(
            "Medical history added",
            extra={
                "patient_id": str(patient_id),
                "history_id": str(history.id),
                "condition": data.condition_name
            }
        )

        return MedicalHistoryResponse.model_validate(history)

    async def get_medical_history(
        self,
        patient_id: UUID,
        active_only: bool = False
    ) -> List[MedicalHistoryResponse]:
        """Get medical history for a patient."""
        # Verify patient exists
        patient_result = await self.db.execute(
            select(Patient.id).where(Patient.id == patient_id)
        )
        if not patient_result.scalar_one_or_none():
            raise NotFoundException(
                message="Patient not found",
                error_code="PATIENT_NOT_FOUND",
                details={"patient_id": str(patient_id)}
            )

        query = select(MedicalHistory).where(
            MedicalHistory.patient_id == patient_id
        )

        if active_only:
            query = query.where(MedicalHistory.is_active == True)

        query = query.order_by(MedicalHistory.recorded_at.desc())

        result = await self.db.execute(query)
        history_entries = result.scalars().all()

        return [MedicalHistoryResponse.model_validate(h) for h in history_entries]

    async def update_medical_history(
        self,
        history_id: UUID,
        is_active: bool,
        resolution_date: Optional[str] = None
    ) -> MedicalHistoryResponse:
        """Update a medical history entry."""
        result = await self.db.execute(
            select(MedicalHistory).where(MedicalHistory.id == history_id)
        )
        history = result.scalar_one_or_none()

        if not history:
            raise NotFoundException(
                message="Medical history entry not found",
                error_code="MEDICAL_HISTORY_NOT_FOUND",
                details={"history_id": str(history_id)}
            )

        history.is_active = is_active
        if resolution_date:
            history.resolution_date = date.fromisoformat(resolution_date)

        await self.db.flush()
        await self.db.refresh(history)

        logger.info(
            "Medical history updated",
            extra={
                "history_id": str(history_id),
                "is_active": is_active
            }
        )

        return MedicalHistoryResponse.model_validate(history)
