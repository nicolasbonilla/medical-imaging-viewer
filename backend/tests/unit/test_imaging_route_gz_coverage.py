"""Route-level guard for the imaging P0: a `.gz` object must parse at the
storage-ref gate and flow through /imaging/process to a 200.

The production outage — every original image 500'ing — slipped through because
CI runs only `tests/unit/` and no route-level test exercised the imaging endpoint
end to end. The storage-ref allowlist rejected bare `.gz` objects (originals are
stored as `{uuid}.gz`), and the parser unit test had encoded that wrong
assumption.

This drives the REAL FastAPI app and the REAL storage-ref parser
(`parse_patient_storage_ref`) — the exact layer that failed. Only the
Firestore-backed patient-authorization step (RC-026) is stubbed to "granted", so
the test needs no Firestore/GCS and runs in CI. It would have gone red before the
`.gz` allowlist fix.
"""
from datetime import datetime
import uuid

import pytest

try:
    from app.main import app
    from app.core.container import get_imaging_service, get_storage_service
    from app.security import get_current_active_user
    from app.security.models import User, UserRole
    from app.models.schemas import ImageSeriesResponse, ImageMetadata, ImageFormat
    from app.security.storage_access import parse_patient_storage_ref
    from app.api.routes import imaging as imaging_routes
    from fastapi.testclient import TestClient
    _AVAILABLE = app is not None
except Exception:  # pragma: no cover
    _AVAILABLE = False

pytestmark = pytest.mark.skipif(not _AVAILABLE, reason="FastAPI app not importable")


def _admin_user():
    now = datetime.utcnow()
    return User(
        id="test-admin-001", username="test-admin", email="test-admin@example.com",
        full_name="Test Admin", role=UserRole.ADMIN, is_active=True,
        is_locked=False, email_verified=True, created_at=now, updated_at=now,
    )


class _FakeStorage:
    async def download_file(self, bucket, object_path):
        return b"\x1f\x8b\x08\x00fake-gzip-payload"  # never parsed (imaging is faked)


class _FakeImaging:
    async def process_image(self, file_data, filename, slice_range):
        return ImageSeriesResponse(
            id="img-x", name=filename, format=ImageFormat.NIFTI,
            metadata=ImageMetadata(rows=4, columns=4, slices=1),
            total_slices=1, slices=[],
        )


async def _parse_only_authz(file_id, user):
    """Runs the REAL storage-ref parser (the P0 layer) and grants access —
    Firestore-backed patient authorization (RC-026) is out of scope for a CI
    unit test. A malformed/unsupported ref still raises here, exactly as in prod."""
    return parse_patient_storage_ref(file_id)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(imaging_routes, "require_imaging_access", _parse_only_authz)
    app.dependency_overrides[get_current_active_user] = _admin_user
    app.dependency_overrides[get_storage_service] = lambda: _FakeStorage()
    app.dependency_overrides[get_imaging_service] = lambda: _FakeImaging()
    try:
        yield TestClient(app)
    finally:
        for dep in (get_current_active_user, get_storage_service, get_imaging_service):
            app.dependency_overrides.pop(dep, None)


def _ref(filename):
    return f"patients/{uuid.uuid4()}/studies/{uuid.uuid4()}/series/{uuid.uuid4()}/{filename}"


def test_gz_original_image_flows_through_to_200(client):
    """The exact P0 scenario: a bare `.gz` object must be accepted and served."""
    path = _ref(f"{uuid.uuid4()}.gz")
    r = client.get(f"/api/v1/imaging/process/{path}?start_slice=0&end_slice=1&max_slices=1")
    assert r.status_code == 200, (
        f"a `.gz` original image must load; got {r.status_code}: {r.text[:200]}"
    )
    assert r.json()["format"] == "nifti"


def test_nii_gz_still_flows_through(client):
    r = client.get(f"/api/v1/imaging/process/{_ref('image.nii.gz')}?max_slices=1")
    assert r.status_code == 200


def test_dcm_still_flows_through(client):
    r = client.get(f"/api/v1/imaging/process/{_ref('slice.dcm')}?max_slices=1")
    assert r.status_code == 200


def test_unsupported_extension_is_rejected_not_served(client):
    """Security property intact: an extension outside the allowlist is refused by
    the real parser (never reaches the image service). Not 200."""
    r = client.get(f"/api/v1/imaging/process/{_ref('payload.xyz')}")
    assert r.status_code != 200


def test_unauthenticated_request_is_blocked(client):
    """Auth gate fires before the route body (drop the auth override)."""
    app.dependency_overrides.pop(get_current_active_user, None)
    r = client.get(f"/api/v1/imaging/process/{_ref('x.gz')}")
    assert r.status_code in (401, 403)
