"""RC-026 — object-level authorization for patient records (CAPA-002 CA-2.1).

Risk control for HAZ-010. Care-team entitlement model.

THE DEFECT
CAPA-002 found that every clinical route injected `current_user` and never
consulted it, while `file_id` is a caller-supplied storage path. Any
authenticated user could read any patient's data. Authentication was enforced;
authorization was not.

RC-025 added ROLE-level authorization. This is the different control: not "may
this role touch patient records" but "may this user access THIS patient".

These tests exercise the decision function directly, with no Firestore and no
emulator. That is deliberate — CAPA-001's root cause was controls whose
verification could not be executed, and an authorization rule that only runs
against live infrastructure gets tested shallowly or not at all.

Negative control (CAPA-001 §5): make `decide_patient_access` return a grant by
default, drop the assignment check, or remove the `is_active` test, and these
MUST fail.
"""
import pytest

from app.security.models import UserRole
from app.security.patient_access import (
    AccessDecision,
    CareTeamAssignment,
    decide_patient_access,
)

PATIENT = "patient-1"
OTHER_PATIENT = "patient-2"
USER = "user-a"
OTHER_USER = "user-b"


def _assignment(patient_id=PATIENT, user_id=USER, revoked_at=None):
    return CareTeamAssignment(
        patient_id=patient_id,
        user_id=user_id,
        role_in_care="attending",
        revoked_at=revoked_at,
    )


def _decide(role=UserRole.RADIOLOGIST, user_id=USER, patient_id=PATIENT,
            created_by=USER, assignments=()):
    return decide_patient_access(
        user_id=user_id,
        user_role=role,
        patient_id=patient_id,
        patient_created_by=created_by,
        assignments=assignments,
    )


class TestRC026GrantsOnlyOnAPositiveFact:
    def test_rc026_active_assignment_grants_access(self):
        result = _decide(assignments=[_assignment()])
        assert result.allowed
        assert result.decision is AccessDecision.GRANTED_ASSIGNED

    def test_rc026_admin_is_granted_and_the_reason_is_distinguishable(self):
        """ADMIN exemption is by design — it is the only way to triage the
        quarantined set. It must never be indistinguishable from a care-team
        grant in the audit log."""
        result = _decide(role=UserRole.ADMIN, assignments=[])
        assert result.allowed
        assert result.decision is AccessDecision.GRANTED_ADMIN

    def test_rc026_assignment_for_a_different_patient_does_not_grant(self):
        """The cross-patient case — the actual CAPA-002 defect."""
        result = _decide(assignments=[_assignment(patient_id=OTHER_PATIENT)])
        assert not result.allowed
        assert result.decision is AccessDecision.DENIED_NOT_ASSIGNED

    def test_rc026_assignment_belonging_to_another_user_does_not_grant(self):
        result = _decide(assignments=[_assignment(user_id=OTHER_USER)])
        assert not result.allowed

    def test_rc026_revoked_assignment_does_not_grant(self):
        """Revocation must take effect. A clinician removed from a care team
        who retains access is a GDPR incident, not a stale cache."""
        result = _decide(assignments=[_assignment(revoked_at="2026-07-18T10:00:00Z")])
        assert not result.allowed
        assert result.decision is AccessDecision.DENIED_NOT_ASSIGNED

    def test_rc026_creating_a_record_does_not_by_itself_grant_access(self):
        """Provenance is not entitlement under the care-team model. Someone who
        registered a patient but was never assigned to their care has no
        clinical need to know."""
        result = _decide(created_by=USER, assignments=[])
        assert not result.allowed

    def test_rc026_role_alone_never_grants_access(self):
        """A senior role is not a care-team membership. This is the check that
        distinguishes RC-026 from RC-025."""
        for role in (UserRole.VIEWER, UserRole.TECHNICIAN, UserRole.RADIOLOGIST):
            assert not _decide(role=role, assignments=[]).allowed, (
                f"{role} was granted access with no assignment"
            )


class TestRC026FailsClosed:
    def test_rc026_no_assignments_denies(self):
        assert not _decide(assignments=[]).allowed

    def test_rc026_missing_patient_id_denies(self):
        for empty in (None, ""):
            result = _decide(patient_id=empty, assignments=[_assignment()])
            assert not result.allowed
            assert result.decision is AccessDecision.DENIED_NO_PATIENT

    def test_rc026_missing_patient_denies_even_for_admin(self):
        """Order matters: the patient check precedes the ADMIN grant, so a
        malformed request cannot be answered affirmatively."""
        result = _decide(role=UserRole.ADMIN, patient_id=None)
        assert not result.allowed
        assert result.decision is AccessDecision.DENIED_NO_PATIENT

    def test_rc026_every_denial_reason_is_actually_a_denial(self):
        """Guard against a reason being added to the granted set by mistake."""
        from app.security.patient_access import AccessResult

        for decision in AccessDecision:
            allowed = AccessResult(decision).allowed
            assert allowed == decision.value.startswith("granted:"), (
                f"{decision.value} classifies as allowed={allowed}"
            )

    def test_rc026_unrelated_assignments_do_not_leak_access(self):
        result = _decide(
            assignments=[
                _assignment(patient_id=OTHER_PATIENT, user_id=OTHER_USER),
                _assignment(patient_id=OTHER_PATIENT),
                _assignment(user_id=OTHER_USER),
            ]
        )
        assert not result.allowed


class TestRC026Quarantine:
    """CAPA-002 §8.1: records predating provenance capture cannot be attributed,
    and inventing an attribution would write a false record."""

    def test_rc026_unattributed_record_is_quarantined(self):
        result = _decide(created_by=None, assignments=[])
        assert not result.allowed
        assert result.decision is AccessDecision.DENIED_QUARANTINED

    def test_rc026_quarantine_is_distinguishable_from_a_plain_denial(self):
        """The operator action differs: quarantine needs ADMIN triage, a plain
        denial needs a care-team assignment. Conflating them makes the audit log
        useless for that decision."""
        quarantined = _decide(created_by=None, assignments=[])
        not_assigned = _decide(created_by=OTHER_USER, assignments=[])

        assert quarantined.decision is not not_assigned.decision

    def test_rc026_admin_can_reach_a_quarantined_record_to_triage_it(self):
        result = _decide(role=UserRole.ADMIN, created_by=None, assignments=[])
        assert result.allowed

    def test_rc026_an_assignment_lifts_quarantine(self):
        """Once an ADMIN reassigns the record it behaves normally."""
        result = _decide(created_by=None, assignments=[_assignment()])
        assert result.allowed
        assert result.decision is AccessDecision.GRANTED_ASSIGNED

    def test_rc026_quarantined_record_is_not_auto_attributed(self):
        """No path may treat a null created_by as ownership by the caller."""
        result = _decide(user_id=USER, created_by=None, assignments=[])
        assert not result.allowed


class TestRC026SignatureResistsMisuse:
    def test_rc026_arguments_are_keyword_only(self):
        """Positional arguments would allow user_id and patient_id to be
        transposed at a call site — in an authorization function that is a
        catastrophic and entirely invisible defect."""
        with pytest.raises(TypeError):
            decide_patient_access(USER, UserRole.ADMIN, PATIENT, USER, [])

    def test_rc026_decision_is_pure_and_repeatable(self):
        args = dict(assignments=[_assignment()])
        assert _decide(**args).decision is _decide(**args).decision
