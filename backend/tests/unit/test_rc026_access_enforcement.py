"""RC-026 enforcement layer — the HTTP guard, tested without Firestore.

The pure decision function is covered by test_rc026_patient_access.py. This
module covers the wiring in patient_access_dependency.py: that the guard fetches
the right facts, calls the decision, audits, and — the security-critical part —
denies with 404 (never 403) so patient existence cannot be enumerated.

Every collaborator is a fake. CAPA-001's root cause was controls whose
verification could not be executed; an authorization guard that can only run
against a live database would be tested shallowly, so it is built to be tested
with injected doubles and it is.

Negative control (CAPA-001 §5): make authorize_patient_access return the patient
unconditionally, or raise 403 instead of 404, and these MUST fail.
"""
import pytest

from app.security.models import UserRole
from app.security.patient_access import CareTeamAssignment
from app.security.patient_access_dependency import authorize_patient_access

PATIENT = "11111111-1111-1111-1111-111111111111"
USER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OTHER_USER = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


class _User:
    def __init__(self, user_id=USER, role=UserRole.RADIOLOGIST):
        self.id = user_id
        self.role = role


class _Patient:
    def __init__(self, created_by=USER):
        self.created_by = created_by


class _PatientService:
    """Fake patient store. `missing=True` simulates a nonexistent patient."""

    def __init__(self, patient=None, missing=False, raises=False):
        self._patient = patient if patient is not None else _Patient()
        self._missing = missing
        self._raises = raises

    async def get_patient(self, patient_id):
        if self._raises:
            raise RuntimeError("datastore unavailable")
        if self._missing:
            return None
        return self._patient


class _CareTeamService:
    def __init__(self, entitlements=()):
        self._entitlements = list(entitlements)

    def list_entitlements_for_user(self, user_id):
        return [e for e in self._entitlements if e.user_id == user_id]


def _assignment(patient_id=PATIENT, user_id=USER, revoked_at=None):
    return CareTeamAssignment(
        patient_id=patient_id, user_id=user_id, role_in_care="attending",
        revoked_at=revoked_at,
    )


async def _authorize(user, patient_service, care_team_service):
    return await authorize_patient_access(
        patient_id=PATIENT,
        user=user,
        patient_service=patient_service,
        care_team_service=care_team_service,
    )


@pytest.mark.asyncio
class TestRC026EnforcementGrants:
    async def test_assigned_user_receives_the_patient(self):
        patient = await _authorize(
            _User(),
            _PatientService(_Patient(created_by=OTHER_USER)),
            _CareTeamService([_assignment()]),
        )
        assert patient is not None

    async def test_admin_receives_the_patient_without_assignment(self):
        patient = await _authorize(
            _User(role=UserRole.ADMIN),
            _PatientService(),
            _CareTeamService([]),
        )
        assert patient is not None

    async def test_guard_returns_the_patient_so_the_handler_need_not_refetch(self):
        sentinel = _Patient(created_by=OTHER_USER)
        result = await _authorize(
            _User(), _PatientService(sentinel), _CareTeamService([_assignment()])
        )
        assert result is sentinel


@pytest.mark.asyncio
class TestRC026EnforcementDenies:
    async def test_unassigned_user_is_denied(self):
        with pytest.raises(Exception) as exc:
            await _authorize(_User(), _PatientService(), _CareTeamService([]))
        assert exc.value.status_code == 404

    async def test_denial_is_404_not_403_to_prevent_enumeration(self):
        """The security-critical assertion. 403 would confirm the patient exists
        to a caller not entitled to know it does."""
        with pytest.raises(Exception) as exc:
            await _authorize(
                _User(user_id=OTHER_USER),
                _PatientService(_Patient(created_by=USER)),
                _CareTeamService([_assignment(user_id=USER)]),  # someone else's
            )
        assert exc.value.status_code == 404

    async def test_missing_patient_and_forbidden_patient_are_indistinguishable(self):
        """Same status AND same body for 'does not exist' and 'not entitled'."""
        missing = None
        try:
            await _authorize(_User(), _PatientService(missing=True), _CareTeamService([]))
        except Exception as e:
            missing = e

        forbidden = None
        try:
            await _authorize(
                _User(user_id=OTHER_USER),
                _PatientService(_Patient(created_by=USER)),
                _CareTeamService([]),
            )
        except Exception as e:
            forbidden = e

        assert missing.status_code == forbidden.status_code == 404
        assert missing.detail == forbidden.detail

    async def test_assignment_for_a_different_patient_is_denied(self):
        with pytest.raises(Exception) as exc:
            await _authorize(
                _User(),
                _PatientService(),
                _CareTeamService([_assignment(patient_id="99999999-9999-9999-9999-999999999999")]),
            )
        assert exc.value.status_code == 404

    async def test_revoked_assignment_is_denied(self):
        with pytest.raises(Exception) as exc:
            await _authorize(
                _User(),
                _PatientService(),
                _CareTeamService([_assignment(revoked_at="2026-07-19T00:00:00Z")]),
            )
        assert exc.value.status_code == 404

    async def test_quarantined_record_denies_a_non_admin(self):
        """created_by is None (legacy record) and no assignment: quarantined."""
        with pytest.raises(Exception) as exc:
            await _authorize(
                _User(),
                _PatientService(_Patient(created_by=None)),
                _CareTeamService([]),
            )
        assert exc.value.status_code == 404

    async def test_datastore_error_denies_rather_than_leaking(self):
        """If the patient lookup throws, the guard must fail closed — treat the
        patient as unresolvable and deny, never fall through to a grant."""
        with pytest.raises(Exception) as exc:
            await _authorize(_User(), _PatientService(raises=True), _CareTeamService([]))
        assert exc.value.status_code == 404


@pytest.mark.asyncio
class TestRC026EnforcementAudits:
    async def test_grant_and_denial_are_both_audited(self, monkeypatch):
        recorded = []
        import app.security.patient_access_dependency as dep

        monkeypatch.setattr(
            dep, "audit_access_decision",
            lambda **kw: recorded.append(kw),
        )

        await _authorize(_User(), _PatientService(), _CareTeamService([_assignment()]))
        try:
            await _authorize(_User(), _PatientService(), _CareTeamService([]))
        except Exception:
            pass

        assert len(recorded) == 2
        assert recorded[0]["result"].allowed is True
        assert recorded[1]["result"].allowed is False


class TestRC026RoutesAreWired:
    """Guard the wiring, not just the function. The enforcement tests above prove
    authorize_patient_access is correct; these prove the routes actually call it.
    RC-016/RC-018 taught that a correct control helps nothing if no route invokes
    it (the call-site vs enforcement-site blind spots, CAPA-004 §5)."""

    from pathlib import Path as _P
    SOURCE = (_P(__file__).resolve().parents[2] / "app" / "api" / "routes" / "patients.py").read_text(encoding="utf-8")

    def test_rc026_patient_scoped_routes_enforce_object_access(self):
        import re
        # Every route whose path contains {patient_id} and returns/mutates data
        # must depend on require_patient_access.
        scoped = ["get_patient", "update_patient", "delete_patient",
                  "add_medical_history", "get_medical_history", "update_medical_history"]
        for fn in scoped:
            start = self.SOURCE.find(f"async def {fn}(")
            assert start > 0, f"{fn} not found"
            end = self.SOURCE.find("):", start)
            signature = self.SOURCE[start:end]
            assert "Depends(require_patient_access)" in signature, (
                f"{fn} does not enforce object-level access — an authenticated "
                "user with the role could reach a patient they are not assigned to"
            )

    def test_rc026_care_team_mutations_require_object_access(self):
        """Assigning/revoking must itself require access to the patient, so a
        clinician cannot add themselves to a care team they are not on."""
        for fn in ("assign_care_team_member", "revoke_care_team_member", "list_care_team"):
            start = self.SOURCE.find(f"async def {fn}(")
            assert start > 0, f"{fn} not found"
            end = self.SOURCE.find("):", start)
            assert "Depends(require_patient_access)" in self.SOURCE[start:end], (
                f"{fn} does not require object-level access"
            )
