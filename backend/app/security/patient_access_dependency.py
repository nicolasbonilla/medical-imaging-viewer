"""FastAPI enforcement of object-level patient authorization — Class C.

This is the wiring that turns RC-026's decision function into an HTTP guard.
It is the third and final layer of CAPA-002 CA-2.1:

    decide_patient_access()   pure rule        (app.security.patient_access)
    CareTeamService           fact store       (app.services.care_team_service)
    require_patient_access()  HTTP enforcement (this module)

WHAT IT DOES, IN ORDER
  1. Resolves the patient. A patient that does not exist yields 404 — and,
     critically, the SAME 404 whether the record is absent or the caller is
     simply not entitled to know it exists. Returning 403 for "exists but you
     may not see it" leaks the existence of a patient record to an unauthorised
     caller, which is itself a disclosure.
  2. Fetches the caller's care-team entitlements.
  3. Calls the pure decision function.
  4. Audits the decision (grant AND denial).
  5. Raises on denial, returns the patient on grant so the handler need not
     re-fetch it.

WHY 404-NOT-403 ON DENIAL
Enumeration protection. With 403-on-forbidden, a caller can probe patient ids
and learn which exist. Collapsing "not found" and "not entitled" to an
indistinguishable 404 is the standard defence and is what a GDPR reviewer
expects for a patient-existence oracle. The audit log still records the true
reason (`denied:no_care_team_assignment` vs `denied:patient_not_found`), so the
distinction is preserved where it is safe — server-side — and hidden where it is
dangerous — from the client.
"""
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Path, status

from app.core.logging import get_logger
from app.security.auth import get_current_active_user
from app.security.models import User
from app.security.patient_access import (
    AccessResult,
    audit_access_decision,
    decide_patient_access,
)

logger = get_logger(__name__)


def _get_care_team_service():
    """Lazy accessor, so importing this module does not require Firestore.

    Kept as a module-level function specifically so tests can monkeypatch it
    with a fake store and exercise every branch of the guard without a database.
    """
    from app.services.care_team_service import CareTeamService

    return CareTeamService()


def _get_patient_service():
    from app.core.container import get_patient_service

    return get_patient_service()


async def authorize_patient_access(
    *,
    patient_id: str,
    user: User,
    patient_service,
    care_team_service,
):
    """Core enforcement, expressed over injected collaborators.

    Separated from the FastAPI dependency so it can be tested directly with
    fakes. Returns the patient object on success; raises HTTPException(404) on
    any denial — never 403 (see module docstring).

    The 404 body is deliberately generic. It must not vary with the denial
    reason, or the variation itself becomes the enumeration oracle the 404 was
    meant to close.
    """
    not_found = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Patient not found",
    )

    patient = None
    try:
        patient = await patient_service.get_patient(patient_id)
    except Exception:
        patient = None

    created_by = _created_by_of(patient)

    entitlements = care_team_service.list_entitlements_for_user(str(user.id))

    result: AccessResult = decide_patient_access(
        user_id=str(user.id),
        user_role=user.role,
        patient_id=str(patient_id) if patient is not None else None,
        patient_created_by=created_by,
        assignments=entitlements,
    )

    audit_access_decision(user_id=str(user.id), patient_id=str(patient_id), result=result)

    if not result.allowed:
        raise not_found

    return patient


def _created_by_of(patient) -> Optional[str]:
    """Read created_by off a patient record of unknown concrete shape."""
    if patient is None:
        return None
    value = getattr(patient, "created_by", None)
    if value is None and isinstance(patient, dict):
        value = patient.get("created_by")
    return str(value) if value is not None else None


def require_patient_access(
    patient_id: UUID = Path(..., description="Patient UUID"),
    current_user: User = Depends(get_current_active_user),
):
    """FastAPI dependency: enforce object-level access, return the patient.

    Usage on a route with `{patient_id}` in its path:

        patient = Depends(require_patient_access)

    The dependency runs AFTER authentication and role checks and BEFORE the
    handler body, so an unentitled caller never reaches the data-returning code.
    """
    return _run_authorization(patient_id, current_user)


async def _run_authorization(patient_id: UUID, current_user: User):
    return await authorize_patient_access(
        patient_id=str(patient_id),
        user=current_user,
        patient_service=_get_patient_service(),
        care_team_service=_get_care_team_service(),
    )
