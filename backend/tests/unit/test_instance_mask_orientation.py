"""Instance (expert-NIfTI) masks must be loaded in the SAME internal orientation
as segmentation masks, so an algorithm-vs-expert comparison is spatially aligned.

Audit A-1: the compare / agreement-map / longitudinal routes loaded instance
NIfTIs with np.transpose(mask,(2,1,0)) -> internal (k,a1,a0), while segmentation
masks are (k,a0,a1). The in-plane axes were swapped, so on square-in-plane data
the shapes matched but the content was transposed -> silently wrong Dice/HD
(near-zero overlap) between an algorithm mask and an expert reference. Fixed to
(2,0,1), the app-wide display convention (native (a0,a1,k) -> internal (k,a0,a1)).

This test drives the REAL compare route with an instance NIfTI that encodes the
SAME asymmetric lesion as a segmentation mask; correct orientation -> Dice 1.0.
With the old (2,1,0) the lesion would be transposed and Dice ~0.
"""
from datetime import datetime

import numpy as np
import nibabel as nib
import pytest

try:
    from app.main import app
    from app.core.container import get_segmentation_service, get_storage_service
    from app.security import get_current_active_user
    from app.security.models import User, UserRole
    from app.models.schemas import SegmentationMetadata, LabelInfo
    from fastapi.testclient import TestClient
    _AVAILABLE = app is not None
except Exception:  # pragma: no cover
    _AVAILABLE = False

pytestmark = pytest.mark.skipif(not _AVAILABLE, reason="FastAPI app not importable")

INSTANCE_PATH = "patients/p/studies/s/series/se/expert.nii.gz"


def _admin():
    now = datetime.utcnow()
    return User(id="admin-1", username="admin", email="admin@example.com", full_name="Admin",
                role=UserRole.ADMIN, is_active=True, is_locked=False, email_verified=True,
                created_at=now, updated_at=now)


def _seg_internal_mask():
    # internal (D,H,W) = (k, a0, a1) with an ASYMMETRIC lesion (a0-extent != a1-extent)
    # so an in-plane transpose is observable as a near-zero Dice.
    m = np.zeros((10, 20, 20), dtype=np.uint8)
    m[2:5, 3:8, 12:16] = 1
    return m


def _instance_nifti_bytes_for(seg_internal):
    # The expert NIfTI is stored in native order (a0,a1,k) = transpose(internal,(1,2,0)),
    # so that loading it with the correct (2,0,1) reproduces the same internal mask.
    native = np.transpose(seg_internal, (1, 2, 0)).astype(np.uint8)  # (a0,a1,k)
    img = nib.Nifti1Image(native, np.eye(4))
    img.header.set_zooms((1.0, 1.0, 1.0))
    return img.to_bytes()


class _FakeSeg:
    def __init__(self, mask):
        self._mask = mask

    def get_loaded(self, sid):
        return {"masks_3d": self._mask,
                "metadata": SegmentationMetadata(file_id="img-1",
                    labels=[LabelInfo(id=1, name="MS Lesion", color="#f00", opacity=0.5, visible=True)])}


class _FakeStorage:
    def __init__(self, seg_mask):
        self._instance = _instance_nifti_bytes_for(seg_mask)

    async def download_file(self, bucket, file_id):
        if file_id == INSTANCE_PATH:
            return self._instance
        # source image for spacing resolution
        img = nib.Nifti1Image(np.zeros((20, 20, 10), np.uint8), np.eye(4))
        img.header.set_zooms((1.0, 1.0, 1.0))
        return img.to_bytes()


@pytest.fixture
def client():
    m = _seg_internal_mask()
    app.dependency_overrides[get_current_active_user] = _admin
    app.dependency_overrides[get_segmentation_service] = lambda: _FakeSeg(m)
    app.dependency_overrides[get_storage_service] = lambda: _FakeStorage(m)
    try:
        yield TestClient(app)
    finally:
        for dep in (get_current_active_user, get_segmentation_service, get_storage_service):
            app.dependency_overrides.pop(dep, None)


def test_segmentation_vs_instance_of_same_lesion_is_aligned(client):
    r = client.post("/api/v1/segmentation/compare", json={
        "masks": [
            {"type": "segmentation", "id": "seg-a", "label": "Algorithm"},
            {"type": "instance", "id": "inst-1", "gcs_path": INSTANCE_PATH, "label": "Expert"},
        ],
    })
    assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
    comp = r.json()["comparisons"][0]
    # Same lesion, correctly oriented -> near-perfect overlap. The old (2,1,0)
    # would transpose the expert mask -> Dice ~0 for this asymmetric lesion.
    assert comp["dice"] == pytest.approx(1.0, abs=1e-6), comp
    assert comp["hausdorff_mm"] == pytest.approx(0.0, abs=1e-6), comp
