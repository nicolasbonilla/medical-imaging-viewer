"""Object-level authorization for patient records — IEC 62304 Class C.

Risk control RC-026 for HAZ-010. Implements CAPA-002 CA-2.1 under the
**care-team** entitlement model.

THE DEFECT THIS CLOSES
----------------------
CAPA-002: every clinical route injected `current_user` and never consulted it.
`file_id` is a caller-supplied GCS path, so any authenticated user could read
any patient's imaging by supplying its path. Authentication was enforced;
authorization was not. OWASP API1:2023, applied to protected health information.

RC-025 subsequently added ROLE-level authorization ("may this role touch patient
records"). This module answers the different question CAPA-002 actually asks:
**"may this user access THIS patient?"**

THE MODEL
---------
Access requires an explicit, unrevoked assignment linking a user to a patient.
Membership of a care team is a positive fact that someone recorded — it is never
inferred from a role, a shared institution, or from having created the record.

DECISION SEPARATED FROM STORAGE
-------------------------------
`decide_patient_access()` is a pure function over already-fetched facts. It
performs no I/O, which is deliberate: authorization logic that can only be
exercised against a live Firestore emulator is authorization logic that will be
tested shallowly, and CAPA-001's root cause was controls whose verification
could not be executed. Every branch below is reachable in a unit test with no
infrastructure.

QUARANTINE
----------
Records created before provenance capture (CAPA-002 §8.1) have no `created_by`
and no assignments. They are **quarantined**: reachable only by an ADMIN, who
must reassign them explicitly. They are not auto-attributed to anyone — the
original attribution is genuinely lost, and inventing one would write a false
record, which is the defect class CAPA-001 exists to eliminate.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence

from app.core.logging import get_logger
from app.security.models import UserRole

logger = get_logger(__name__)


class AccessDecision(str, Enum):
    """Why access was granted or refused.

    Distinguishing the reasons matters for the audit log: "denied, no care-team
    assignment" and "denied, record quarantined" call for different operator
    action, and conflating them makes the log useless for triage.
    """

    GRANTED_ASSIGNED = "granted:care_team_assignment"
    GRANTED_ADMIN = "granted:administrator"
    DENIED_NOT_ASSIGNED = "denied:no_care_team_assignment"
    DENIED_QUARANTINED = "denied:record_unattributed_pending_review"
    DENIED_NO_PATIENT = "denied:patient_not_found"


@dataclass(frozen=True)
class CareTeamAssignment:
    """A recorded link between a user and a patient."""

    patient_id: str
    user_id: str
    role_in_care: str
    revoked_at: Optional[str] = None

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


@dataclass(frozen=True)
class AccessResult:
    decision: AccessDecision

    @property
    def allowed(self) -> bool:
        return self.decision in (
            AccessDecision.GRANTED_ASSIGNED,
            AccessDecision.GRANTED_ADMIN,
        )


def decide_patient_access(
    *,
    user_id: str,
    user_role: UserRole,
    patient_id: Optional[str],
    patient_created_by: Optional[str],
    assignments: Sequence[CareTeamAssignment],
) -> AccessResult:
    """Decide whether a user may access a patient record.

    Pure: no I/O, no globals. Every argument is a fact the caller has already
    resolved. Keyword-only so no future reordering can silently swap `user_id`
    and `patient_id` at a call site — in an authorization function that would be
    a catastrophic and entirely invisible defect.

    The order of the checks is load-bearing and is asserted by tests:
      1. Missing patient  -> deny (never fall through to a grant).
      2. ADMIN            -> grant (needed to bootstrap and to triage quarantine).
      3. Active assignment-> grant.
      4. Quarantined      -> deny with the specific reason.
      5. Otherwise        -> deny.

    Defaults to denial on every path, including unanticipated ones. There is no
    branch that returns a grant without having established a positive reason.
    """
    if not patient_id:
        return AccessResult(AccessDecision.DENIED_NO_PATIENT)

    # ADMIN is exempt by design, not by omission. Without it there would be no
    # way to triage the quarantined set, and no way to make the first
    # assignment on a new deployment. This is an audited privilege: the reason
    # code distinguishes it from a care-team grant so the two are never
    # indistinguishable in the log.
    if user_role == UserRole.ADMIN:
        return AccessResult(AccessDecision.GRANTED_ADMIN)

    for assignment in assignments:
        if (
            assignment.patient_id == patient_id
            and assignment.user_id == user_id
            and assignment.is_active
        ):
            return AccessResult(AccessDecision.GRANTED_ASSIGNED)

    # Unattributed legacy record: no provenance AND no assignment. Reported
    # separately so an operator can tell "this predates provenance capture and
    # needs triage" from "you are simply not on this care team".
    if patient_created_by is None and not assignments:
        return AccessResult(AccessDecision.DENIED_QUARANTINED)

    return AccessResult(AccessDecision.DENIED_NOT_ASSIGNED)


def audit_access_decision(
    *, user_id: str, patient_id: Optional[str], result: AccessResult
) -> None:
    """Record an access decision.

    Both grants and denials are logged. Logging only denials would leave no
    record of who read which patient — the question an investigation actually
    asks. Patient identifiers are logged; patient NAMES are not.
    """
    logger.info(
        "Patient access decision",
        extra={
            "user_id": user_id,
            "patient_id": patient_id,
            "access_decision": result.decision.value,
            "access_allowed": result.allowed,
        },
    )
