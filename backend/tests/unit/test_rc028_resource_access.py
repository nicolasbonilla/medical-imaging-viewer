"""RC-028 — object-level authorization for studies and documents (CAPA-002 CA-2.1).

Risk control for HAZ-010. Extends RC-026 (patient resource) and RC-027 (imaging
objects) to study/series/instance/document resources by resolving each object to
its owning patient and reusing the care-team decision.

Tested entirely with fakes — no Firestore. Every resolver returns None on failure
and every guard maps None to the same 404 as a denial, so an attacker cannot tell
"this study id does not exist" from "it exists but is not yours".

Negative control (CAPA-001 §5): make a resolver raise instead of returning None,
make the guard grant on patient_id=None, or let a non-admin list without a
patient scope — each MUST fail a test here.
"""
import pytest

from app.security.models import UserRole
from app.security.patient_access import CareTeamAssignment
from app.security.resource_access import (
    authorize_list_scope,
    authorize_resolved_patient,
    resolve_document_patient_id,
    resolve_series_patient_id,
    resolve_study_patient_id,
)

PID = "11111111-1111-1111-1111-111111111111"
STUDY = "22222222-2222-2222-2222-222222222222"
SERIES = "33333333-3333-3333-3333-333333333333"
USER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


class _User:
    def __init__(self, user_id=USER, role=UserRole.RADIOLOGIST):
        self.id = user_id
        self.role = role


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Patient:
    def __init__(self, created_by=USER):
        self.created_by = created_by


class _PatientService:
    def __init__(self, patient=None):
        self._patient = patient or _Patient()

    async def get_patient(self, patient_id):
        return self._patient


class _CareTeam:
    def __init__(self, entitlements=()):
        self._e = list(entitlements)

    def list_entitlements_for_user(self, user_id):
        return [e for e in self._e if e.user_id == user_id]


class _StudyService:
    """Fake study service. Any lookup can be told to raise or return None."""

    def __init__(self, study=None, series=None, raises=False, missing=False):
        self._study = study
        self._series = series
        self._raises = raises
        self._missing = missing

    async def get_study(self, study_id, include_stats=False):
        if self._raises:
            raise RuntimeError("datastore down")
        if self._missing:
            raise Exception("not found")
        return self._study or _Obj(patient_id=PID)

    async def get_series(self, series_id):
        if self._raises or self._series is None:
            raise Exception("not found")
        return self._series


class _DocService:
    def __init__(self, document=None, raises=False):
        self._doc = document
        self._raises = raises

    async def get_document(self, document_id):
        if self._raises or self._doc is None:
            raise Exception("not found")
        return self._doc


def _assignment(patient_id=PID, user_id=USER, revoked_at=None):
    return CareTeamAssignment(patient_id=patient_id, user_id=user_id,
                             role_in_care="attending", revoked_at=revoked_at)


# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestRC028Resolvers:
    async def test_rc028_study_resolves_to_its_patient(self):
        pid = await resolve_study_patient_id(STUDY, _StudyService(_Obj(patient_id=PID)))
        assert pid == PID

    async def test_rc028_missing_study_resolves_to_none_not_an_error(self):
        pid = await resolve_study_patient_id(STUDY, _StudyService(missing=True))
        assert pid is None

    async def test_rc028_datastore_error_resolves_to_none(self):
        pid = await resolve_study_patient_id(STUDY, _StudyService(raises=True))
        assert pid is None

    async def test_rc028_series_resolves_via_its_study(self):
        svc = _StudyService(study=_Obj(patient_id=PID), series=_Obj(study_id=STUDY))
        pid = await resolve_series_patient_id(SERIES, svc)
        assert pid == PID

    async def test_rc028_series_with_no_study_resolves_to_none(self):
        svc = _StudyService(series=_Obj(study_id=None))
        assert await resolve_series_patient_id(SERIES, svc) is None

    async def test_rc028_document_resolves_to_its_patient(self):
        pid = await resolve_document_patient_id("doc-1", _DocService(_Obj(patient_id=PID)))
        assert pid == PID

    async def test_rc028_missing_document_resolves_to_none(self):
        assert await resolve_document_patient_id("doc-1", _DocService(raises=True)) is None


@pytest.mark.asyncio
class TestRC028Authorization:
    async def _authz(self, patient_id, user, entitlements=()):
        await authorize_resolved_patient(
            patient_id=patient_id, resource_label="Study", user=user,
            patient_service=_PatientService(_Patient(created_by="other")),
            care_team_service=_CareTeam(entitlements),
        )

    async def test_rc028_assigned_user_is_allowed(self):
        await self._authz(PID, _User(), [_assignment()])  # no raise

    async def test_rc028_unassigned_user_is_denied_404(self):
        with pytest.raises(Exception) as exc:
            await self._authz(PID, _User(), [])
        assert exc.value.status_code == 404

    async def test_rc028_unresolved_patient_is_denied_404(self):
        """patient_id=None (object not found / no owner) must deny, not grant."""
        with pytest.raises(Exception) as exc:
            await self._authz(None, _User(role=UserRole.ADMIN), [])
        assert exc.value.status_code == 404

    async def test_rc028_admin_is_allowed_for_a_resolved_patient(self):
        await self._authz(PID, _User(role=UserRole.ADMIN), [])  # no raise

    async def test_rc028_not_found_and_forbidden_share_status_and_body(self):
        errs = []
        for pid, ents in [(None, []), (PID, [])]:
            try:
                await self._authz(pid, _User(), ents)
            except Exception as e:
                errs.append(e)
        assert errs[0].status_code == errs[1].status_code == 404
        assert errs[0].detail == errs[1].detail


@pytest.mark.asyncio
class TestRC028ListScope:
    async def _scope(self, patient_id, user, entitlements=()):
        await authorize_list_scope(
            patient_id=patient_id, user=user,
            patient_service=_PatientService(_Patient(created_by="other")),
            care_team_service=_CareTeam(entitlements),
        )

    async def test_rc028_scoped_listing_authorizes_the_filter(self):
        await self._scope(PID, _User(), [_assignment()])  # no raise

    async def test_rc028_scoped_listing_denies_an_unentitled_patient(self):
        with pytest.raises(Exception) as exc:
            await self._scope(PID, _User(), [])
        assert exc.value.status_code == 404

    async def test_rc028_unscoped_listing_is_refused_for_non_admin(self):
        with pytest.raises(Exception) as exc:
            await self._scope(None, _User(role=UserRole.RADIOLOGIST), [])
        assert exc.value.status_code == 400

    async def test_rc028_unscoped_listing_is_allowed_for_admin(self):
        await self._scope(None, _User(role=UserRole.ADMIN), [])  # no raise


class TestRC028RoutesAreWired:
    from pathlib import Path as _P
    _root = _P(__file__).resolve().parents[2] / "app" / "api" / "routes"
    STUDIES = (_root / "studies.py").read_text(encoding="utf-8")
    DOCUMENTS = (_root / "documents.py").read_text(encoding="utf-8")

    def test_rc028_study_object_routes_enforce_access(self):
        for fn in ["get_study", "update_study", "delete_study",
                   "list_series", "create_series"]:
            start = self.STUDIES.find(f"async def {fn}(")
            assert start > 0, fn
            nxt = self.STUDIES.find("async def ", start + 1)
            end = nxt if nxt > 0 else len(self.STUDIES)
            assert "Depends(require_study_access)" in self.STUDIES[start:end], (
                f"{fn} does not enforce object-level access"
            )

    def test_rc028_series_and_instance_routes_enforce_access(self):
        for fn, dep in [("get_series", "require_series_access"),
                        ("delete_series", "require_series_access"),
                        ("list_instances", "require_series_access"),
                        ("get_instance", "require_instance_access"),
                        ("update_instance", "require_instance_access"),
                        ("delete_instance", "require_instance_access")]:
            start = self.STUDIES.find(f"async def {fn}(")
            assert start > 0, fn
            nxt = self.STUDIES.find("async def ", start + 1)
            end = nxt if nxt > 0 else len(self.STUDIES)
            assert f"Depends({dep})" in self.STUDIES[start:end], (
                f"{fn} does not enforce {dep}"
            )

    def test_rc028_document_object_routes_enforce_access(self):
        for fn in ["get_document", "update_document", "delete_document",
                   "list_document_versions"]:
            start = self.DOCUMENTS.find(f"async def {fn}(")
            assert start > 0, fn
            nxt = self.DOCUMENTS.find("async def ", start + 1)
            end = nxt if nxt > 0 else len(self.DOCUMENTS)
            assert "Depends(require_document_access)" in self.DOCUMENTS[start:end], (
                f"{fn} does not enforce object-level access"
            )

    def test_rc028_list_routes_enforce_scope(self):
        s_start = self.STUDIES.find("async def list_studies(")
        assert "Depends(require_study_list_scope)" in self.STUDIES[s_start:self.STUDIES.find("async def ", s_start + 1)]
        d_start = self.DOCUMENTS.find("async def list_documents(")
        assert "Depends(require_document_list_scope)" in self.DOCUMENTS[d_start:self.DOCUMENTS.find("async def ", d_start + 1)]

    def test_rc028_patient_scoped_document_listing_reuses_patient_guard(self):
        start = self.DOCUMENTS.find("async def list_patient_documents(")
        nxt = self.DOCUMENTS.find("async def ", start + 1)
        end = nxt if nxt > 0 else len(self.DOCUMENTS)
        assert "Depends(require_patient_access)" in self.DOCUMENTS[start:end], (
            "list_patient_documents must authorize the patient in its path"
        )
