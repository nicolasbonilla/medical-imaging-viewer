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
from app.security import get_current_active_user
from app.security.auth import require_permission, require_role
from app.security.models import Permission, UserRole
from app.security.patient_access_dependency import require_patient_access
from app.security.models import User
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


def get_care_team_service():
    """The care-team store (RC-026). Defined before the routes that depend on it (PRB-021, PRB-023)."""
    from app.services.care_team_service import CareTeamService
    return CareTeamService()


def _listing_scope(current_user: User, care_team) -> Optional[set]:
    """PRB-021 (REQ-SEC-014, REQ-SEC-032): which patients a list or search may return to this caller.

    None for an administrator (every record, as for every object route: GRANTED_ADMIN); otherwise the ids of
    the patients the caller holds an ACTIVE care-team assignment for — possibly none. A store that cannot be
    read refuses the listing (503) rather than returning an empty or an unfiltered registry.
    """
    if current_user.role == UserRole.ADMIN:
        return None
    try:
        entitlements = care_team.list_entitlements_for_user(str(current_user.id))
    except Exception:
        logger.error("Care-team store unavailable: patient listing refused",
                     extra={"user_id": str(current_user.id)})
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Patient list temporarily unavailable")
    return {e.patient_id for e in entitlements if e.user_id == str(current_user.id) and e.is_active}


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
    service: PatientServiceFirestore = Depends(get_patient_service),
    current_user: User = Depends(require_permission(Permission.PATIENT_CREATE)),
    care_team=Depends(get_care_team_service),
):
    """
    Create a new patient record.

    Required permissions: PATIENT_CREATE

    Returns the created patient with generated UUID.
    Raises 409 Conflict if MRN already exists.
    """
    # CAPA-002: record WHO created this patient. The service has accepted a
    # `created_by` argument all along and no caller ever supplied it, so every
    # existing patient document has created_by = None.
    #
    # This matters beyond audit: object-level authorization (CA-2.1) needs an
    # entitlement relation to authorize against, and provenance is the minimum
    # such relation. It CANNOT be reconstructed retroactively — records created
    # before this change have irrecoverably lost who made them. That is the
    # reason this is landing now rather than waiting for the entitlement model
    # to be decided: every day without it enlarges the un-attributable set.
    patient = await service.create_patient(data, created_by=current_user.id)

    # PRB-023 (REQ-SEC-033): the clinician who creates a patient record is RECORDED on its care team at
    # creation — an explicit, attributable assignment (granted_by = the creator), not an inference from
    # created_by at access time (REQ-SEC-014/018 stay as they are). Without it the creator's next request
    # answered "Patient not found". An administrator is not put on a care team: administrator access is
    # its own audited grant (GRANTED_ADMIN), and an IT administrator does not treat the patient.
    if current_user.role != UserRole.ADMIN:
        try:
            care_team.assign(patient_id=str(patient.id), user_id=str(current_user.id),
                             role_in_care="attending", granted_by=str(current_user.id))
        except Exception as e:
            logger.error(
                "Patient created but the creator's care-team assignment was not recorded",
                extra={"patient_id": str(patient.id), "user_id": str(current_user.id),
                       "error_type": type(e).__name__},
            )
            from fastapi import HTTPException
            raise HTTPException(
                status_code=500,
                detail=(f"The patient record was created (id {patient.id}), but your access to it could not "
                        "be recorded on its care team. Ask an administrator to add you to the care team; do "
                        "not create the patient again."),
            )
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
    service: PatientServiceFirestore = Depends(get_patient_service),
    current_user: User = Depends(require_permission(Permission.PATIENT_VIEW)),
    care_team=Depends(get_care_team_service),
):
    """
    List the patients the caller may access, with pagination.

    Required permissions: PATIENT_VIEW. PRB-021 (REQ-SEC-014, REQ-SEC-032): an administrator sees every record; any
    other user only the patients of their active care-team assignments. This route returned EVERY patient
    (name, record number, birth date, sex) to every signed-in user.
    """
    patients, total = await service.list_patients(
        page=page,
        page_size=page_size,
        status=status.value if status else None,
        allowed_ids=_listing_scope(current_user, care_team),
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
    service: PatientServiceFirestore = Depends(get_patient_service),
    current_user: User = Depends(require_permission(Permission.PATIENT_VIEW)),
    care_team=Depends(get_care_team_service),
):
    """
    Search the patients the caller may access, with filters and pagination.

    Required permissions: PATIENT_VIEW. PRB-021 (REQ-SEC-014, REQ-SEC-032): scoped like the list — an administrator
    searches every record, any other user only the patients of their active care-team assignments.

    Filters applied: exact MRN, family-name prefix, gender, status. `query`, `given_name` and `city` are
    accepted but not applied (no full-text search exists; this docstring claimed one).
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

    patients, total = await service.search_patients(search, allowed_ids=_listing_scope(current_user, care_team))
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
    service: PatientServiceFirestore = Depends(get_patient_service),
    current_user: User = Depends(require_permission(Permission.PATIENT_VIEW))
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
    # CAPA-009 (RC-036): an MRN lookup must not bypass the care-team check. MRNs are often
    # sequential, so without it any PATIENT_VIEW user could enumerate every patient.
    from app.security.resource_access import authorize_patient_id
    await authorize_patient_id(getattr(patient, "id", None), current_user)
    return patient


@router.get(
    "/quarantined",
    summary="List quarantined (unattributed) patient records",
    description="Administrator triage view of records that carry no provenance "
                "and cannot be auto-attributed. Reassign with POST "
                "/{patient_id}/care-team. Admin only.",
)
async def list_quarantined_patients(
    limit: int = Query(200, ge=1, le=1000, description="Scan cap for the triage view"),
    service: PatientServiceFirestore = Depends(get_patient_service),
    # CAPA-002 CA-2.1 / REQ-SEC-018: quarantined records are ADMIN-only. This is
    # the first use of require_role in the codebase — the audit (RC-018) found it
    # defined but applied nowhere.
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """List patient records with no provenance, for administrator triage.

    Reassignment is not a new mechanism: an admin grants a care-team assignment
    via POST /{patient_id}/care-team (the admin passes the object-access guard on
    any patient), after which the record is no longer quarantined.
    """
    patients = await service.list_unattributed_patients(limit=limit)
    return {
        "quarantined": patients,
        "count": len(patients),
        "scan_capped": len(patients) >= limit,
        "note": (
            "Records here carry no created_by and no care-team assignment. "
            "They are accessible only to administrators until reassigned. "
            "If scan_capped is true, raise `limit` to see the rest — the omission "
            "is not silent."
        ),
    }


@router.get(
    "/{patient_id}",
    response_model=PatientResponse,
    summary="Get patient by ID",
    description="Get full patient details including study and document counts."
)
async def get_patient(
    patient_id: UUID = Path(..., description="Patient UUID"),
    include_stats: bool = Query(True, description="Include study/document counts"),
    service: PatientServiceFirestore = Depends(get_patient_service),
    current_user: User = Depends(require_permission(Permission.PATIENT_VIEW)),
    # CAPA-002 CA-2.1: object-level authorization. Runs after the role
    # check; denies with 404 (never 403) if the caller is not on the care team.
    _authorized_patient=Depends(require_patient_access),
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
    service: PatientServiceFirestore = Depends(get_patient_service),
    current_user: User = Depends(require_permission(Permission.PATIENT_UPDATE)),
    # CAPA-002 CA-2.1: object-level authorization. Runs after the role
    # check; denies with 404 (never 403) if the caller is not on the care team.
    _authorized_patient=Depends(require_patient_access),
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
    service: PatientServiceFirestore = Depends(get_patient_service),
    current_user: User = Depends(require_permission(Permission.PATIENT_DELETE)),
    # CAPA-002 CA-2.1: object-level authorization. Runs after the role
    # check; denies with 404 (never 403) if the caller is not on the care team.
    _authorized_patient=Depends(require_patient_access),
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
    service: PatientServiceFirestore = Depends(get_patient_service),
    current_user: User = Depends(require_permission(Permission.PATIENT_UPDATE)),
    # CAPA-002 CA-2.1: object-level authorization. Runs after the role
    # check; denies with 404 (never 403) if the caller is not on the care team.
    _authorized_patient=Depends(require_patient_access),
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
    service: PatientServiceFirestore = Depends(get_patient_service),
    current_user: User = Depends(require_permission(Permission.PATIENT_VIEW)),
    # CAPA-002 CA-2.1: object-level authorization. Runs after the role
    # check; denies with 404 (never 403) if the caller is not on the care team.
    _authorized_patient=Depends(require_patient_access),
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
    service: PatientServiceFirestore = Depends(get_patient_service),
    current_user: User = Depends(require_permission(Permission.PATIENT_UPDATE)),
    # CAPA-002 CA-2.1: object-level authorization. Runs after the role
    # check; denies with 404 (never 403) if the caller is not on the care team.
    _authorized_patient=Depends(require_patient_access),
):
    """
    Update a medical history entry.

    Required permissions: PATIENT_UPDATE

    Used to mark conditions as resolved.
    """
    history = await service.update_medical_history(history_id, is_active, resolution_date)
    return history


# =============================================================================
# Care-team assignment management — CAPA-002 CA-2.1 (RC-026)
#
# These endpoints administer the entitlement relation that object-level
# authorization reads. The security posture is deliberate: creating and listing
# assignments both require object-level access to the patient (require_patient_
# access), so a clinician can only add colleagues to a care team they are
# already on. ADMIN bootstraps the first assignment on any patient, including
# quarantined legacy records.
# =============================================================================
from pydantic import BaseModel, Field as PydField  # noqa: E402
from app.services.care_team_service import CareTeamService, VALID_CARE_ROLES  # noqa: E402
# get_care_team_service is defined at the top of this module (PRB-021/PRB-023 use it in the list,
# search and create routes, which are declared before this section).


class CareTeamAssignRequest(BaseModel):
    user_id: str = PydField(..., description="User to grant care-team access to")
    role_in_care: str = PydField("attending", description=f"One of {sorted(VALID_CARE_ROLES)}")


@router.post(
    "/{patient_id}/care-team",
    summary="Assign a user to a patient's care team",
    description="Grant a colleague object-level access. Requires you to already "
                "have access to this patient (or be an administrator).",
)
async def assign_care_team_member(
    patient_id: UUID = Path(..., description="Patient UUID"),
    body: CareTeamAssignRequest = ...,
    care_team: CareTeamService = Depends(get_care_team_service),
    current_user: User = Depends(require_permission(Permission.PATIENT_UPDATE)),
    # Object-level: only a member of this care team (or ADMIN) may extend it.
    _authorized_patient=Depends(require_patient_access),
):
    try:
        record = care_team.assign(
            patient_id=str(patient_id),
            user_id=body.user_id,
            role_in_care=body.role_in_care,
            granted_by=str(current_user.id),
        )
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc))
    return {
        "id": record.id,
        "patient_id": record.patient_id,
        "user_id": record.user_id,
        "role_in_care": record.role_in_care,
        "granted_by": record.granted_by,
        "granted_at": record.granted_at,
    }


@router.get(
    "/{patient_id}/care-team",
    summary="List a patient's care team",
    description="List all assignments (active and revoked) for the patient.",
)
async def list_care_team(
    patient_id: UUID = Path(..., description="Patient UUID"),
    care_team: CareTeamService = Depends(get_care_team_service),
    current_user: User = Depends(require_permission(Permission.PATIENT_VIEW)),
    _authorized_patient=Depends(require_patient_access),
):
    records = care_team.list_for_patient(str(patient_id))
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "role_in_care": r.role_in_care,
            "granted_by": r.granted_by,
            "granted_at": r.granted_at,
            "revoked_at": r.revoked_at,
            "revoked_by": r.revoked_by,
            "active": r.revoked_at is None,
        }
        for r in records
    ]


@router.delete(
    "/{patient_id}/care-team/{assignment_id}",
    summary="Revoke a care-team assignment",
    description="Revoke access. The assignment is retained (stamped revoked), "
                "never deleted, for GDPR accountability.",
)
async def revoke_care_team_member(
    patient_id: UUID = Path(..., description="Patient UUID"),
    assignment_id: str = Path(..., description="Assignment ID to revoke"),
    care_team: CareTeamService = Depends(get_care_team_service),
    current_user: User = Depends(require_permission(Permission.PATIENT_UPDATE)),
    _authorized_patient=Depends(require_patient_access),
):
    care_team.revoke(assignment_id=assignment_id, revoked_by=str(current_user.id))
    return {"revoked": assignment_id}
