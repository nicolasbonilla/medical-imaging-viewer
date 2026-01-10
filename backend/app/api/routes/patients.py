"""
Patient API Routes.

HL7 FHIR-aligned REST API endpoints for patient management.

@module api.routes.patients
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Path, status

from app.core.container import get_patient_service
from app.core.logging import get_logger
from app.services.patient_service_firestore import PatientServiceFirestore
from app.models.patient_schemas import (
    PatientCreate,
    PatientUpdate,
    PatientSearch,
    PatientResponse,
    PatientListResponse,
    PatientSummary,
    MedicalHistoryCreate,
    MedicalHistoryResponse,
    Gender,
    PatientStatus
)

router = APIRouter(prefix="/patients", tags=["Patients"])
logger = get_logger(__name__)


# ============================================================================
# PATIENT CRUD ENDPOINTS
# ============================================================================

@router.post(
    "",
    response_model=PatientResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new patient",
    description="Register a new patient with demographics and contact information."
)
async def create_patient(
    data: PatientCreate,
    service: PatientServiceFirestore = Depends(get_patient_service)
):
    """
    Create a new patient record.

    Required permissions: PATIENT_CREATE

    Returns the created patient with generated UUID.
    Raises 409 Conflict if MRN already exists.
    """
    patient = await service.create_patient(data)
    return patient


@router.get(
    "",
    response_model=PatientListResponse,
    summary="List all patients",
    description="Get paginated list of patients with optional status filter."
)
async def list_patients(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[PatientStatus] = Query(None, description="Filter by status"),
    service: PatientServiceFirestore = Depends(get_patient_service)
):
    """
    List all patients with pagination.

    Required permissions: PATIENT_VIEW
    """
    patients, total = await service.list_patients(
        page=page,
        page_size=page_size,
        status=status.value if status else None
    )

    total_pages = (total + page_size - 1) // page_size

    return PatientListResponse(
        items=patients,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get(
    "/search",
    response_model=PatientListResponse,
    summary="Search patients",
    description="Search patients by name, MRN, or other criteria."
)
async def search_patients(
    query: Optional[str] = Query(None, min_length=2, description="Search term"),
    mrn: Optional[str] = Query(None, description="Exact MRN match"),
    family_name: Optional[str] = Query(None, description="Last name (partial)"),
    given_name: Optional[str] = Query(None, description="First name (partial)"),
    gender: Optional[Gender] = Query(None, description="Gender filter"),
    status: Optional[PatientStatus] = Query(None, description="Status filter"),
    city: Optional[str] = Query(None, description="City filter"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("family_name", description="Sort field"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$", description="Sort order"),
    service: PatientServiceFirestore = Depends(get_patient_service)
):
    """
    Search patients with filters and pagination.

    Required permissions: PATIENT_VIEW

    Supports full-text search on name, MRN, and email.
    """
    search = PatientSearch(
        query=query,
        mrn=mrn,
        family_name=family_name,
        given_name=given_name,
        gender=gender,
        status=status,
        city=city,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order
    )

    patients, total = await service.search_patients(search)
    total_pages = (total + page_size - 1) // page_size

    return PatientListResponse(
        items=patients,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get(
    "/by-mrn/{mrn}",
    response_model=PatientResponse,
    summary="Get patient by MRN",
    description="Look up a patient by their Medical Record Number."
)
async def get_patient_by_mrn(
    mrn: str = Path(..., description="Medical Record Number"),
    service: PatientServiceFirestore = Depends(get_patient_service)
):
    """
    Get a patient by MRN.

    Required permissions: PATIENT_VIEW

    Returns 404 if not found.
    """
    from app.core.exceptions import NotFoundException

    patient = await service.get_patient_by_mrn(mrn)
    if not patient:
        raise NotFoundException(
            message=f"Patient with MRN '{mrn}' not found",
            error_code="PATIENT_NOT_FOUND",
            details={"mrn": mrn}
        )
    return patient


@router.get(
    "/{patient_id}",
    response_model=PatientResponse,
    summary="Get patient by ID",
    description="Get full patient details including study and document counts."
)
async def get_patient(
    patient_id: UUID = Path(..., description="Patient UUID"),
    include_stats: bool = Query(True, description="Include study/document counts"),
    service: PatientServiceFirestore = Depends(get_patient_service)
):
    """
    Get a patient by ID.

    Required permissions: PATIENT_VIEW

    Optionally includes counts of associated studies and documents.
    """
    patient = await service.get_patient(patient_id, include_stats=include_stats)
    return patient


@router.put(
    "/{patient_id}",
    response_model=PatientResponse,
    summary="Update patient",
    description="Update patient information (partial update supported)."
)
async def update_patient(
    patient_id: UUID = Path(..., description="Patient UUID"),
    data: PatientUpdate = ...,
    service: PatientServiceFirestore = Depends(get_patient_service)
):
    """
    Update a patient record.

    Required permissions: PATIENT_UPDATE

    Only provided fields will be updated.
    """
    patient = await service.update_patient(patient_id, data)
    return patient


@router.delete(
    "/{patient_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate patient",
    description="Soft delete - sets patient status to inactive."
)
async def delete_patient(
    patient_id: UUID = Path(..., description="Patient UUID"),
    service: PatientServiceFirestore = Depends(get_patient_service)
):
    """
    Deactivate a patient (soft delete).

    Required permissions: PATIENT_DELETE

    Does not actually delete data, just sets status to inactive.
    """
    await service.delete_patient(patient_id)
    return None


# ============================================================================
# MEDICAL HISTORY ENDPOINTS
# ============================================================================

@router.post(
    "/{patient_id}/history",
    response_model=MedicalHistoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add medical history",
    description="Add a medical condition to patient's history."
)
async def add_medical_history(
    patient_id: UUID = Path(..., description="Patient UUID"),
    data: MedicalHistoryCreate = ...,
    service: PatientServiceFirestore = Depends(get_patient_service)
):
    """
    Add a medical history entry.

    Required permissions: PATIENT_UPDATE (or RADIOLOGIST role)

    Records conditions, diagnoses, allergies, etc.
    """
    history = await service.add_medical_history(patient_id, data)
    return history


@router.get(
    "/{patient_id}/history",
    response_model=list[MedicalHistoryResponse],
    summary="Get medical history",
    description="Get all medical history entries for a patient."
)
async def get_medical_history(
    patient_id: UUID = Path(..., description="Patient UUID"),
    active_only: bool = Query(False, description="Return only active conditions"),
    service: PatientServiceFirestore = Depends(get_patient_service)
):
    """
    Get medical history for a patient.

    Required permissions: PATIENT_VIEW

    Optionally filter to only active conditions.
    """
    history = await service.get_medical_history(patient_id, active_only=active_only)
    return history


@router.patch(
    "/history/{history_id}",
    response_model=MedicalHistoryResponse,
    summary="Update medical history entry",
    description="Update a medical history entry (typically to resolve a condition)."
)
async def update_medical_history(
    history_id: UUID = Path(..., description="Medical history entry UUID"),
    is_active: bool = Query(..., description="Active status"),
    resolution_date: Optional[str] = Query(None, description="Date condition resolved (ISO format)"),
    service: PatientServiceFirestore = Depends(get_patient_service)
):
    """
    Update a medical history entry.

    Required permissions: PATIENT_UPDATE

    Used to mark conditions as resolved.
    """
    history = await service.update_medical_history(history_id, is_active, resolution_date)
    return history
