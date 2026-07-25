"""RC-027 — storage references are parsed against a positive grammar (CAPA-002 CA-2.3).

Risk control for HAZ-010. The imaging routes took a raw, caller-supplied GCS
object key and fetched it directly, so a caller could read any object in the
bucket — another patient's image, or a non-patient object. This parser refuses
anything that is not exactly a patient-scoped imaging reference, and yields a
patient_id that the authorization layer (RC-026) can then check.

The bulk of these tests are ATTACK VECTORS. A parser whose rejection paths are
untested is a parser that will let one through. Each rejection below corresponds
to a way a caller could otherwise have reached data they must not.

Negative control (CAPA-001 §5): relax the grammar — accept any prefix, skip the
UUID check, or echo the raw input into object_path — and these MUST fail.
"""
import uuid

import pytest

from app.security.storage_access import (
    PatientStorageRef,
    StorageRefError,
    parse_patient_storage_ref,
)

PID = str(uuid.uuid4())
SID = str(uuid.uuid4())
SERID = str(uuid.uuid4())


def _ref(filename="image.dcm", patient=PID, study=SID, series=SERID):
    return f"patients/{patient}/studies/{study}/series/{series}/{filename}"


class TestRC027ParsesValidReferences:
    def test_rc027_parses_a_canonical_reference(self):
        ref = parse_patient_storage_ref(_ref())
        assert isinstance(ref, PatientStorageRef)
        assert ref.patient_id == PID
        assert ref.study_id == SID
        assert ref.series_id == SERID
        assert ref.filename == "image.dcm"

    @pytest.mark.parametrize("name", [
        f"{uuid.uuid4()}.dcm", "series.nii", "masks.nii.gz", "volume.npz", "meta.json",
    ])
    def test_rc027_accepts_supported_file_types(self, name):
        assert parse_patient_storage_ref(_ref(name)).filename == name

    def test_rc027_object_path_is_rebuilt_not_echoed(self):
        """object_path must be reconstructed from parsed components, so no
        unparsed caller byte can reach the storage key. Upper-case UUIDs prove
        it: the output is normalised, not the input verbatim."""
        raw = _ref(patient=PID.upper())
        ref = parse_patient_storage_ref(raw)
        assert ref.object_path == _ref()  # normalised, lower-case
        assert ref.patient_id == PID


class TestRC027RejectsCrossPatientAndNonPatientAccess:
    """The actual CAPA-002 defect: reaching data you are not entitled to."""

    def test_rc027_rejects_a_non_patient_prefix(self):
        """`segmentations/...`, `config/...`, anything not under patients/."""
        for raw in [
            f"segmentations/{uuid.uuid4()}/masks.nii.gz",
            "config/secrets.json",
            f"users/{uuid.uuid4()}/token.json",
        ]:
            with pytest.raises(StorageRefError):
                parse_patient_storage_ref(raw)

    def test_rc027_rejects_wrong_infix_keywords(self):
        raw = f"patients/{PID}/exams/{SID}/series/{SERID}/image.dcm"
        with pytest.raises(StorageRefError):
            parse_patient_storage_ref(raw)


class TestRC027RejectsTraversalAndInjection:
    def test_rc027_rejects_parent_directory_tokens(self):
        for raw in [
            f"patients/{PID}/studies/{SID}/series/{SERID}/../../../../etc/passwd",
            f"patients/{PID}/../{uuid.uuid4()}/studies/{SID}/series/{SERID}/x.dcm",
        ]:
            with pytest.raises(StorageRefError):
                parse_patient_storage_ref(raw)

    def test_rc027_rejects_absolute_paths(self):
        with pytest.raises(StorageRefError):
            parse_patient_storage_ref(f"/patients/{PID}/studies/{SID}/series/{SERID}/x.dcm")

    def test_rc027_rejects_backslashes(self):
        with pytest.raises(StorageRefError):
            parse_patient_storage_ref(f"patients\\{PID}\\studies\\{SID}\\series\\{SERID}\\x.dcm")

    def test_rc027_rejects_a_scheme(self):
        with pytest.raises(StorageRefError):
            parse_patient_storage_ref(f"gs://bucket/patients/{PID}/studies/{SID}/series/{SERID}/x.dcm")

    def test_rc027_rejects_control_characters_and_nul(self):
        for raw in [
            f"patients/{PID}/studies/{SID}/series/{SERID}/x.dcm\x00.png",
            f"patients/{PID}/studies/{SID}/series/{SERID}/x\n.dcm",
        ]:
            with pytest.raises(StorageRefError):
                parse_patient_storage_ref(raw)

    def test_rc027_rejects_a_filename_with_an_embedded_separator(self):
        """A filename segment can never smuggle in another path component."""
        with pytest.raises(StorageRefError):
            parse_patient_storage_ref(
                f"patients/{PID}/studies/{SID}/series/{SERID}/../{PID}"
            )


class TestRC027RejectsMalformedShape:
    def test_rc027_rejects_non_uuid_segments(self):
        for bad in ["not-a-uuid", "12345", PID[:-1], f"{PID}x"]:
            with pytest.raises(StorageRefError):
                parse_patient_storage_ref(_ref(patient=bad))

    def test_rc027_rejects_too_few_segments(self):
        with pytest.raises(StorageRefError):
            parse_patient_storage_ref(f"patients/{PID}/studies/{SID}/image.dcm")

    def test_rc027_rejects_too_many_segments(self):
        with pytest.raises(StorageRefError):
            parse_patient_storage_ref(_ref() + "/extra.dcm")

    def test_rc027_rejects_trailing_and_leading_slash(self):
        for raw in [_ref() + "/", "patients//studies//series//x.dcm"]:
            with pytest.raises(StorageRefError):
                parse_patient_storage_ref(raw)

    def test_rc027_rejects_empty_and_none(self):
        for raw in ["", None]:
            with pytest.raises(StorageRefError):
                parse_patient_storage_ref(raw)

    def test_rc027_rejects_unsupported_file_type(self):
        for name in ["image.exe", "image.php", "image", "image."]:
            with pytest.raises(StorageRefError):
                parse_patient_storage_ref(_ref(name))


class TestRC027NeverPartiallyResolves:
    def test_rc027_a_rejected_input_yields_no_reference(self):
        """Belt and braces: every malformed input raises rather than returning a
        half-built reference the caller might use anyway."""
        malformed = [
            "", None, "/etc/passwd", f"patients/{PID}",
            f"segmentations/{uuid.uuid4()}/masks.nii.gz",
            _ref(patient="not-a-uuid"), _ref("bad.exe"),
        ]
        for raw in malformed:
            with pytest.raises(StorageRefError):
                parse_patient_storage_ref(raw)


# ---------------------------------------------------------------------------
# Enforcement: parse + authorize composed, and the routes that must call it.
# ---------------------------------------------------------------------------
import pytest as _pytest
from app.security.models import UserRole
from app.security.patient_access import CareTeamAssignment
from app.security.patient_access_dependency import authorize_storage_ref


class _User:
    def __init__(self, user_id="u-1", role=UserRole.RADIOLOGIST):
        self.id = user_id
        self.role = role


class _Patient:
    def __init__(self, created_by="u-1"):
        self.created_by = created_by


class _PatientService:
    def __init__(self, patient=None):
        self._patient = patient or _Patient()

    async def get_patient(self, patient_id):
        return self._patient


class _CareTeamService:
    def __init__(self, entitlements=()):
        self._entitlements = list(entitlements)

    def list_entitlements_for_user(self, user_id):
        return [e for e in self._entitlements if e.user_id == user_id]


async def _authz(raw, user, patient_service, care_team):
    return await authorize_storage_ref(
        raw_file_id=raw, user=user,
        patient_service=patient_service, care_team_service=care_team,
    )


@_pytest.mark.asyncio
class TestRC027Enforcement:
    async def test_valid_ref_for_assigned_patient_returns_normalised_path(self):
        assignment = CareTeamAssignment(patient_id=PID, user_id="u-1",
                                        role_in_care="attending", revoked_at=None)
        ref = await _authz(_ref(), _User(),
                           _PatientService(_Patient(created_by="other")),
                           _CareTeamService([assignment]))
        assert ref.object_path == _ref()

    async def test_malformed_ref_is_404_not_a_500(self):
        """A bad reference must be a clean 404, not an unhandled error, and must
        not reveal why it was refused."""
        with _pytest.raises(Exception) as exc:
            await _authz("config/secrets.json", _User(),
                         _PatientService(), _CareTeamService([]))
        assert exc.value.status_code == 404

    async def test_valid_ref_for_unassigned_patient_is_denied_404(self):
        """The cross-patient case: the reference parses, but the caller is not on
        this patient's care team."""
        with _pytest.raises(Exception) as exc:
            await _authz(_ref(), _User(),
                         _PatientService(_Patient(created_by="someone-else")),
                         _CareTeamService([]))
        assert exc.value.status_code == 404

    async def test_malformed_and_unauthorised_are_indistinguishable(self):
        """404 with the same body for 'not a valid object' and 'not yours' — no
        oracle over either the key space or the patient space."""
        errs = []
        for raw, svc in [("bad/key.json", _PatientService()),
                         (_ref(), _PatientService(_Patient(created_by="x")))]:
            try:
                await _authz(raw, _User(), svc, _CareTeamService([]))
            except Exception as e:
                errs.append(e)
        assert errs[0].status_code == errs[1].status_code == 404
        assert errs[0].detail == errs[1].detail

    async def test_admin_reaches_a_valid_ref_without_assignment(self):
        ref = await _authz(_ref(), _User(role=UserRole.ADMIN),
                           _PatientService(), _CareTeamService([]))
        assert ref.patient_id == PID


class TestRC027RoutesAreWired:
    from pathlib import Path as _P
    SOURCE = (_P(__file__).resolve().parents[2] / "app" / "api" / "routes" / "imaging.py").read_text(encoding="utf-8")

    def test_every_imaging_handler_authorizes_before_download(self):
        import re
        # Each handler must call require_imaging_access, and must NOT pass the raw
        # file_id to download_file after that (it reassigns file_id = ref.object_path).
        handlers = ["process_image", "apply_window_level", "get_slice",
                    "get_3d_volume", "get_image_metadata",
                    "get_voxel_3d_visualization", "get_matplotlib_2d_slice",
                    "get_nifti_file"]
        for fn in handlers:
            start = self.SOURCE.find(f"async def {fn}(")
            assert start > 0, fn
            nxt = self.SOURCE.find("async def ", start + 1)
            body = self.SOURCE[start:nxt if nxt > 0 else len(self.SOURCE)]
            assert "require_imaging_access(file_id, current_user)" in body, (
                f"{fn} does not authorize the storage reference before access"
            )

    def test_authorization_precedes_any_storage_call(self):
        """The guard line must appear before the first storage access in each
        handler, or a request could touch storage before being authorized."""
        for storage_call in ["download_file(settings.GCS_BUCKET_NAME",
                             "get_file_metadata(settings.GCS_BUCKET_NAME"]:
            idx = 0
            while True:
                idx = self.SOURCE.find(storage_call, idx)
                if idx < 0:
                    break
                preceding = self.SOURCE.rfind("require_imaging_access", 0, idx)
                handler_start = self.SOURCE.rfind("async def ", 0, idx)
                assert preceding > handler_start, (
                    f"a storage call at offset {idx} is not preceded by "
                    "authorization within its handler"
                )
                idx += len(storage_call)
