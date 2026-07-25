"""Care-team assignment store — IEC 62304 Class C.

The persistence layer behind RC-026 (object-level authorization, CAPA-002 CA-2.1).

SEPARATION OF CONCERNS
----------------------
The *decision* lives in `app.security.patient_access.decide_patient_access` — a
pure function with no I/O, exhaustively unit-tested. THIS module only fetches the
facts that decision needs and records new assignments. It contains no
authorization logic of its own: a bug here can fail to *find* an assignment, but
it cannot invent one, because `decide_patient_access` grants only on a present,
active, matching record.

That split is deliberate. CAPA-001's root cause was controls whose verification
could not be executed. Keeping the rule pure means the rule is fully tested
without Firestore; keeping the store thin means the untested-in-CI surface (the
actual database calls) carries no security logic to get wrong.

WHY revoke DOES NOT DELETE
--------------------------
Revocation stamps `revoked_at` and never removes the row. Under GDPR
accountability (Art. 5(2)) and ISO 13485 record control, the fact that a
clinician *had* access to a patient during a period is itself auditable
information. Deleting the row would erase the evidence of a past access grant.
"""
from dataclasses import dataclass
from typing import List, Optional

from google.cloud.firestore_v1 import FieldFilter

from app.core.firebase import Collections, get_firestore_client
from app.core.logging import get_logger
from app.security.patient_access import CareTeamAssignment

logger = get_logger(__name__)

# Recognised care-team roles. Kept small and explicit — an assignment with an
# unrecognised role is a data-entry error, not a new privilege level.
VALID_CARE_ROLES = frozenset({"attending", "reading", "referring", "consulting"})


@dataclass(frozen=True)
class AssignmentRecord:
    """A stored assignment, including its own id and provenance.

    Distinct from `CareTeamAssignment` (the minimal shape the decision function
    consumes): this carries the audit fields the decision does not need but the
    record must keep.
    """

    id: str
    patient_id: str
    user_id: str
    role_in_care: str
    granted_by: str
    granted_at: Optional[str]
    revoked_at: Optional[str]
    revoked_by: Optional[str]

    def to_entitlement(self) -> CareTeamAssignment:
        return CareTeamAssignment(
            patient_id=self.patient_id,
            user_id=self.user_id,
            role_in_care=self.role_in_care,
            revoked_at=self.revoked_at,
        )


class CareTeamService:
    """Firestore-backed care-team assignment store."""

    def __init__(self):
        self.db = get_firestore_client()
        self.collection = Collections.PATIENT_ASSIGNMENTS

    # ---- reads --------------------------------------------------------------

    def list_entitlements_for_user(self, user_id: str) -> List[CareTeamAssignment]:
        """Every assignment naming this user, as decision-shaped entitlements.

        Returns both active and revoked rows: the decision function itself tests
        `is_active`, so filtering here would duplicate — and could disagree with
        — that logic. The single source of truth for "does a revoked assignment
        grant access" is `decide_patient_access`, not this query.
        """
        docs = (
            self.db.collection(self.collection)
            .where(filter=FieldFilter("user_id", "==", user_id))
            .stream()
        )
        return [self._to_record(doc.id, doc.to_dict()).to_entitlement() for doc in docs]

    def list_for_patient(self, patient_id: str) -> List[AssignmentRecord]:
        docs = (
            self.db.collection(self.collection)
            .where(filter=FieldFilter("patient_id", "==", patient_id))
            .stream()
        )
        return [self._to_record(doc.id, doc.to_dict()) for doc in docs]

    # ---- writes -------------------------------------------------------------

    def assign(
        self,
        *,
        patient_id: str,
        user_id: str,
        role_in_care: str,
        granted_by: str,
    ) -> AssignmentRecord:
        """Create a care-team assignment.

        Idempotent on the (patient, user) pair: re-assigning a user who already
        has an active assignment returns the existing one rather than creating a
        duplicate. Two active rows for the same pair would not be a security
        problem, but they make revocation error-prone — revoking one would leave
        the other granting access, the classic "we removed their access but they
        can still get in" incident.
        """
        if role_in_care not in VALID_CARE_ROLES:
            raise ValueError(
                f"Unknown care role {role_in_care!r}; expected one of "
                f"{sorted(VALID_CARE_ROLES)}"
            )
        if not patient_id or not user_id:
            raise ValueError("assign requires both patient_id and user_id")

        for existing in self.list_for_patient(patient_id):
            if existing.user_id == user_id and existing.revoked_at is None:
                return existing

        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "patient_id": patient_id,
            "user_id": user_id,
            "role_in_care": role_in_care,
            "granted_by": granted_by,
            "granted_at": now,
            "revoked_at": None,
            "revoked_by": None,
        }
        ref = self.db.collection(self.collection).document()
        ref.set(payload)
        logger.info(
            "Care-team assignment created",
            extra={
                "patient_id": patient_id,
                "assigned_user_id": user_id,
                "granted_by": granted_by,
                "role_in_care": role_in_care,
            },
        )
        return self._to_record(ref.id, payload)

    def revoke(self, *, assignment_id: str, revoked_by: str) -> None:
        """Revoke by stamping revoked_at. Never deletes (see module docstring)."""
        from datetime import datetime, timezone

        ref = self.db.collection(self.collection).document(assignment_id)
        snapshot = ref.get()
        if not snapshot.exists:
            from app.core.exceptions import NotFoundException

            raise NotFoundException(f"Assignment {assignment_id} not found")

        ref.update(
            {
                "revoked_at": datetime.now(timezone.utc).isoformat(),
                "revoked_by": revoked_by,
            }
        )
        logger.info(
            "Care-team assignment revoked",
            extra={"assignment_id": assignment_id, "revoked_by": revoked_by},
        )

    # ---- mapping ------------------------------------------------------------

    @staticmethod
    def _to_record(doc_id: str, data: dict) -> AssignmentRecord:
        return AssignmentRecord(
            id=doc_id,
            patient_id=data.get("patient_id", ""),
            user_id=data.get("user_id", ""),
            role_in_care=data.get("role_in_care", ""),
            granted_by=data.get("granted_by", ""),
            granted_at=data.get("granted_at"),
            revoked_at=data.get("revoked_at"),
            revoked_by=data.get("revoked_by"),
        )
