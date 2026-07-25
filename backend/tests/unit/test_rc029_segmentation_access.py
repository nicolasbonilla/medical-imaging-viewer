"""RC-029 — object-level authorization for segmentations (CAPA-002 CA-2.1).

Risk control for HAZ-010. The last data surface of CAPA-002.

A segmentation's metadata stores no patient_id — it stores the file_id of the
image it segments, and that file_id is patient-scoped
(patients/{patient_id}/studies/.../image). So a segmentation is owned by the
patient of the segmented image, and resolution extracts the patient from
metadata.file_id (reusing RC-027's path knowledge).

Tested with fakes — no Firestore. Negative control (CAPA-001 §5): make the
resolver return a patient for a non-patient file_id, or let a listing run
unscoped for a non-admin, and these MUST fail.
"""
import uuid

import pytest

from app.security.models import UserRole
from app.security.patient_access import CareTeamAssignment
from app.security.resource_access import (
    authorize_file_scope,
    resolve_segmentation_patient_id,
)

PID = str(uuid.uuid4())
SID = str(uuid.uuid4())
SERID = str(uuid.uuid4())
FILE_ID = f"patients/{PID}/studies/{SID}/series/{SERID}/image.dcm"
USER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


class _User:
    def __init__(self, user_id=USER, role=UserRole.RADIOLOGIST):
        self.id = user_id
        self.role = role


class _Meta:
    def __init__(self, file_id=FILE_ID):
        self.file_id = file_id


class _SegService:
    def __init__(self, metadata=None, raises=False):
        self._meta = metadata
        self._raises = raises

    async def get_metadata(self, segmentation_id):
        if self._raises:
            raise RuntimeError("datastore down")
        return self._meta


class _Patient:
    def __init__(self, created_by="someone-else"):
        self.created_by = created_by


class _PatientService:
    async def get_patient(self, patient_id):
        return _Patient()


class _CareTeam:
    def __init__(self, entitlements=()):
        self._e = list(entitlements)

    def list_entitlements_for_user(self, user_id):
        return [e for e in self._e if e.user_id == user_id]


def _assignment(patient_id=PID, user_id=USER):
    return CareTeamAssignment(patient_id=patient_id, user_id=user_id,
                             role_in_care="attending", revoked_at=None)


@pytest.mark.asyncio
class TestRC029Resolver:
    async def test_rc029_resolves_patient_from_segmented_file_id(self):
        pid = await resolve_segmentation_patient_id("seg-1", _SegService(_Meta()))
        assert pid == PID

    async def test_rc029_missing_metadata_resolves_to_none(self):
        assert await resolve_segmentation_patient_id("seg-1", _SegService(None)) is None

    async def test_rc029_datastore_error_resolves_to_none(self):
        assert await resolve_segmentation_patient_id("seg-1", _SegService(raises=True)) is None

    async def test_rc029_non_patient_file_id_resolves_to_none(self):
        """A segmentation whose file_id is not patient-scoped must not resolve to
        any patient — it fails closed rather than inventing an owner."""
        for bad in ["segmentations/x/masks.nii.gz", "config/secrets.json", "", "local-abc"]:
            svc = _SegService(_Meta(file_id=bad))
            assert await resolve_segmentation_patient_id("seg-1", svc) is None

    async def test_rc029_malformed_uuid_in_file_id_resolves_to_none(self):
        svc = _SegService(_Meta(file_id="patients/not-a-uuid/studies/x/series/y/z.dcm"))
        assert await resolve_segmentation_patient_id("seg-1", svc) is None


@pytest.mark.asyncio
class TestRC029ListScope:
    async def _scope(self, file_ids, user, entitlements=()):
        await authorize_file_scope(
            file_ids=file_ids, user=user,
            patient_service=_PatientService(), care_team_service=_CareTeam(entitlements),
        )

    async def test_rc029_scoped_listing_authorizes_each_file(self):
        await self._scope([FILE_ID], _User(), [_assignment()])  # no raise

    async def test_rc029_scoped_listing_denies_unentitled_patient(self):
        with pytest.raises(Exception) as exc:
            await self._scope([FILE_ID], _User(), [])
        assert exc.value.status_code == 404

    async def test_rc029_unscoped_listing_refused_for_non_admin(self):
        with pytest.raises(Exception) as exc:
            await self._scope([], _User(), [])
        assert exc.value.status_code == 400

    async def test_rc029_unscoped_listing_allowed_for_admin(self):
        await self._scope([], _User(role=UserRole.ADMIN), [])  # no raise

    async def test_rc029_one_unauthorized_file_denies_the_whole_listing(self):
        """If any referenced patient is off-limits, the whole request is denied —
        no partial leak of the accessible subset alongside a probe of the rest."""
        other = f"patients/{uuid.uuid4()}/studies/{SID}/series/{SERID}/image.dcm"
        with pytest.raises(Exception) as exc:
            await self._scope([FILE_ID, other], _User(), [_assignment()])
        assert exc.value.status_code == 404


class TestRC029RoutesAreWired:
    from pathlib import Path as _P
    SOURCE = (_P(__file__).resolve().parents[2] / "app" / "api" / "routes" / "segmentation.py").read_text(encoding="utf-8")

    def test_rc029_object_routes_enforce_access(self):
        handlers = ["get_segmentation", "apply_paint_stroke", "get_slice_mask",
                    "get_overlay_image", "get_segmentation_only", "save_segmentation",
                    "delete_segmentation", "update_labels", "get_segmentation_nifti",
                    "get_binary_mask", "upload_binary_mask", "get_segmentation_info"]
        for fn in handlers:
            start = self.SOURCE.find(f"async def {fn}(")
            assert start > 0, fn
            nxt = self.SOURCE.find("async def ", start + 1)
            body = self.SOURCE[start:nxt if nxt > 0 else len(self.SOURCE)]
            assert "Depends(require_segmentation_access)" in body, (
                f"{fn} does not enforce object-level access"
            )

    def test_rc029_create_authorizes_the_target_image(self):
        start = self.SOURCE.find("async def create_segmentation(")
        nxt = self.SOURCE.find("async def ", start + 1)
        body = self.SOURCE[start:nxt]
        assert "require_imaging_access(request.file_id, current_user)" in body, (
            "create_segmentation must authorize the image it segments"
        )

    def test_rc029_list_is_scoped(self):
        start = self.SOURCE.find("async def list_segmentations(")
        nxt = self.SOURCE.find("async def ", start + 1)
        body = self.SOURCE[start:nxt]
        assert "authorize_file_scope(" in body, (
            "list_segmentations must authorize its file_id scope"
        )


@pytest.mark.asyncio
class TestRC029AdminMayQueryAnyScope:
    """Regression guard for the admin edge case found at deploy time: an admin
    filtering by a file_id that resolves to no patient must get an empty result
    (authorized), not a 404. Surfaced by test_endpoints.sh check #6
    (GET /segmentation/list?file_ids=test)."""

    async def _scope(self, file_ids, role):
        await authorize_file_scope(
            file_ids=file_ids, user=_User(role=role),
            patient_service=_PatientService(), care_team_service=_CareTeam([]),
        )

    async def test_rc029_admin_with_unresolvable_file_id_is_allowed(self):
        await self._scope(["test"], UserRole.ADMIN)  # must not raise (was 404)

    async def test_rc029_admin_with_empty_scope_is_allowed(self):
        await self._scope([], UserRole.ADMIN)  # must not raise

    async def test_rc029_admin_with_real_file_id_is_allowed(self):
        await self._scope([FILE_ID], UserRole.ADMIN)  # must not raise

    async def test_rc029_non_admin_unresolvable_file_id_still_denied(self):
        """The fix must NOT weaken non-admins: a bogus file_id is still 404."""
        with pytest.raises(Exception) as exc:
            await self._scope(["test"], UserRole.RADIOLOGIST)
        assert exc.value.status_code == 404
