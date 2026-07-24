"""Object-level authorization for studies and documents — IEC 62304 Class C.

Risk control RC-028 for HAZ-010. Extends CAPA-002 CA-2.1 from the patient
resource (RC-026) and imaging objects (RC-027) to the study, series, instance
and clinical-document resources.

THE SHARED SHAPE
----------------
Every one of these objects belongs to exactly one patient, and the datastore
already records that link:

    study     -> study.patient_id            (direct)
    series    -> series.study_id -> study    (one hop)
    instance  -> instance.study_id -> study  (one hop)
    document  -> document.patient_id         (direct)

So authorization is uniform: RESOLVE the object to its owning patient_id, then
reuse the care-team decision (RC-026) against that patient. This module is the
resolve step; the decision is unchanged.

WHY A RESOLVER, NOT A per-route CHECK
-------------------------------------
Writing `if study.patient_id == ...` inline in each of ~15 routes is how CAPA-002
happened in the first place — a control duplicated by hand is a control that will
be omitted from the next route added. A single resolve-then-authorize chokepoint,
wired as a dependency, cannot be forgotten silently: the wiring test asserts each
data route depends on it.

ENUMERATION DEFENCE (inherited)
-------------------------------
An object that does not exist and an object the caller may not see both resolve
to "no authorized patient" and raise an identical 404. Distinguishing them would
let a caller enumerate study/document ids. The resolvers therefore return None on
BOTH "not found" and "datastore error" — never raise a distinguishable error —
and the guard maps None to the same 404 as a denied authorization.
"""
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Path, status

from app.core.logging import get_logger
from app.security.auth import get_current_active_user
from app.security.models import User
from app.security.patient_access import (
    audit_access_decision,
    decide_patient_access,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Core: resolve an already-fetched patient_id and authorize it.
# Pure over injected collaborators — no I/O, fully unit-testable.
# ---------------------------------------------------------------------------
async def authorize_resolved_patient(
    *,
    patient_id: Optional[str],
    resource_label: str,
    user: User,
    patient_service,
    care_team_service,
) -> None:
    """Authorize a caller against a resolved patient_id, or raise 404.

    `patient_id is None` means the object did not resolve — not found, or a
    datastore error, or an object with no owning patient. All of these must be
    indistinguishable from "you are not entitled", so all raise the same 404.
    """
    not_found = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource_label} not found",
    )

    if patient_id is None:
        # No patient to authorize against. Deny, and record it — a burst of these
        # is the signature of an enumeration attempt.
        logger.warning(
            "Resource access denied: unresolved owning patient",
            extra={"user_id": str(user.id), "resource": resource_label},
        )
        raise not_found

    created_by = None
    patient = None
    try:
        patient = await patient_service.get_patient(patient_id)
    except Exception:
        patient = None
    if patient is not None:
        created_by = getattr(patient, "created_by", None)
        created_by = str(created_by) if created_by is not None else None

    entitlements = care_team_service.list_entitlements_for_user(str(user.id))

    result = decide_patient_access(
        user_id=str(user.id),
        user_role=user.role,
        patient_id=str(patient_id) if patient is not None else None,
        patient_created_by=created_by,
        assignments=entitlements,
    )
    audit_access_decision(user_id=str(user.id), patient_id=str(patient_id), result=result)

    if not result.allowed:
        raise not_found


# ---------------------------------------------------------------------------
# Resolvers: object id -> owning patient_id. Return None on any failure.
# ---------------------------------------------------------------------------
async def resolve_study_patient_id(study_id, study_service) -> Optional[str]:
    try:
        study = await study_service.get_study(study_id, include_stats=False)
    except Exception:
        return None
    return _patient_id_of(study)


async def resolve_series_patient_id(series_id, study_service) -> Optional[str]:
    try:
        series = await study_service.get_series(series_id)
    except Exception:
        return None
    study_id = getattr(series, "study_id", None)
    if study_id is None:
        return None
    return await resolve_study_patient_id(study_id, study_service)


async def resolve_instance_patient_id(instance_id, study_service) -> Optional[str]:
    try:
        instance = await study_service.get_instance(instance_id)
    except Exception:
        return None
    study_id = getattr(instance, "study_id", None)
    if study_id is not None:
        return await resolve_study_patient_id(study_id, study_service)
    series_id = getattr(instance, "series_id", None)
    if series_id is not None:
        return await resolve_series_patient_id(series_id, study_service)
    return None


async def resolve_document_patient_id(document_id, document_service) -> Optional[str]:
    try:
        document = await document_service.get_document(document_id)
    except Exception:
        return None
    return _patient_id_of(document)


async def resolve_segmentation_patient_id(segmentation_id, segmentation_service) -> Optional[str]:
    """Resolve a segmentation to its owning patient.

    A segmentation's metadata does not store patient_id directly — it stores the
    file_id of the image it segments, which IS patient-scoped
    (patients/{patient_id}/studies/.../image). So the owning patient is the
    patient of the segmented image, extracted from that file_id.

    Returns None on: not found, no metadata, no file_id, or a file_id that is not
    patient-scoped — all of which fail closed to a 404.
    """
    from app.security.storage_access import extract_patient_id_from_path

    try:
        metadata = await segmentation_service.get_metadata(segmentation_id)
    except Exception:
        return None
    if metadata is None:
        return None
    file_id = getattr(metadata, "file_id", None)
    if file_id is None and isinstance(metadata, dict):
        file_id = metadata.get("file_id")
    if not file_id:
        return None
    return extract_patient_id_from_path(str(file_id))


def _patient_id_of(obj) -> Optional[str]:
    value = getattr(obj, "patient_id", None)
    if value is None and isinstance(obj, dict):
        value = obj.get("patient_id")
    return str(value) if value is not None else None


# ---------------------------------------------------------------------------
# Service accessors (lazy, so importing this module needs no Firestore).
# ---------------------------------------------------------------------------
def _study_service():
    from app.core.container import get_study_service
    return get_study_service()


def _document_service():
    from app.core.container import get_document_service
    return get_document_service()


def _segmentation_service():
    from app.core.container import get_segmentation_service
    return get_segmentation_service()


def _patient_service():
    from app.core.container import get_patient_service
    return get_patient_service()


def _care_team_service():
    from app.services.care_team_service import CareTeamService
    return CareTeamService()


# ---------------------------------------------------------------------------
# FastAPI dependencies. One per object level; each resolves then authorizes.
# ---------------------------------------------------------------------------
async def require_study_access(
    study_id: UUID = Path(..., description="Study UUID"),
    current_user: User = Depends(get_current_active_user),
) -> None:
    pid = await resolve_study_patient_id(study_id, _study_service())
    await authorize_resolved_patient(
        patient_id=pid, resource_label="Study", user=current_user,
        patient_service=_patient_service(), care_team_service=_care_team_service(),
    )


async def require_series_access(
    series_id: UUID = Path(..., description="Series UUID"),
    current_user: User = Depends(get_current_active_user),
) -> None:
    pid = await resolve_series_patient_id(series_id, _study_service())
    await authorize_resolved_patient(
        patient_id=pid, resource_label="Series", user=current_user,
        patient_service=_patient_service(), care_team_service=_care_team_service(),
    )


async def require_instance_access(
    instance_id: UUID = Path(..., description="Instance UUID"),
    current_user: User = Depends(get_current_active_user),
) -> None:
    pid = await resolve_instance_patient_id(instance_id, _study_service())
    await authorize_resolved_patient(
        patient_id=pid, resource_label="Instance", user=current_user,
        patient_service=_patient_service(), care_team_service=_care_team_service(),
    )


async def require_document_access(
    document_id: UUID = Path(..., description="Document UUID"),
    current_user: User = Depends(get_current_active_user),
) -> None:
    pid = await resolve_document_patient_id(document_id, _document_service())
    await authorize_resolved_patient(
        patient_id=pid, resource_label="Document", user=current_user,
        patient_service=_patient_service(), care_team_service=_care_team_service(),
    )


async def require_segmentation_access(
    segmentation_id: str = Path(..., description="Segmentation ID"),
    current_user: User = Depends(get_current_active_user),
) -> None:
    pid = await resolve_segmentation_patient_id(segmentation_id, _segmentation_service())
    await authorize_resolved_patient(
        patient_id=pid, resource_label="Segmentation", user=current_user,
        patient_service=_patient_service(), care_team_service=_care_team_service(),
    )


# ---------------------------------------------------------------------------
# List routes: authorize the patient scope of a listing.
# ---------------------------------------------------------------------------
async def authorize_list_scope(
    *,
    patient_id: Optional[str],
    user,
    patient_service,
    care_team_service,
) -> None:
    """Authorize a list/search whose results are patient-scoped.

    A list route that returns records across ALL patients is a bulk version of
    the CAPA-002 defect. The rule:

      - patient_id filter present  -> authorize that patient (same 404 on denial).
      - patient_id filter absent + ADMIN     -> allowed (archive-wide listing).
      - patient_id filter absent + non-ADMIN -> 400: the query must be scoped to
        a patient. Without result-level filtering by the caller's entitlements
        (not yet built), an unscoped listing would leak every patient's study or
        document metadata. Requiring the scope is the safe, clinically ordinary
        rule: you list records for a patient you are caring for.
    """
    from app.security.models import UserRole

    if patient_id is not None:
        await authorize_resolved_patient(
            patient_id=str(patient_id), resource_label="Patient", user=user,
            patient_service=patient_service, care_team_service=care_team_service,
        )
        return

    if user.role == UserRole.ADMIN:
        return

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            "A patient_id filter is required for this listing. Listing records "
            "across all patients is restricted."
        ),
    )


async def authorize_file_scope(
    *,
    file_ids,
    user,
    patient_service,
    care_team_service,
) -> None:
    """Authorize a segmentation listing scoped by imaging file_ids.

    Segmentations are listed by the file_id of the image they segment. Each
    file_id is patient-scoped, so authorizing the listing means authorizing each
    referenced patient. Same rule as the other list routes: a scope is required
    for non-admins; every referenced patient must be one the caller may access.

    A file_id that does not resolve to a patient, or that resolves to a patient
    the caller may not access, denies the whole request with a 404 — consistent
    with never revealing which patients or objects exist.
    """
    from app.security.models import UserRole
    from app.security.storage_access import extract_patient_id_from_path

    ids = [f for f in (file_ids or []) if f]
    if not ids:
        if user.role == UserRole.ADMIN:
            return
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "A file_id scope is required for this listing. Listing "
                "segmentations across all patients is restricted."
            ),
        )

    for file_id in ids:
        patient_id = extract_patient_id_from_path(str(file_id))
        await authorize_resolved_patient(
            patient_id=patient_id, resource_label="Segmentation", user=user,
            patient_service=patient_service, care_team_service=care_team_service,
        )


async def require_study_list_scope(
    patient_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_active_user),
) -> None:
    await authorize_list_scope(
        patient_id=patient_id, user=current_user,
        patient_service=_patient_service(), care_team_service=_care_team_service(),
    )


async def require_document_list_scope(
    patient_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_active_user),
) -> None:
    await authorize_list_scope(
        patient_id=patient_id, user=current_user,
        patient_service=_patient_service(), care_team_service=_care_team_service(),
    )
