"""CI guard for the analysis flow that was DEAD in production (spacing outage).

lesion-analysis, dis-assessment and compare all 500'd because voxel_spacing was
resolved from segmentation metadata that never carries it. That shipped green
because no test exercised the real route end to end. This drives the REAL FastAPI
app through TestClient with only the leaf dependencies (segmentation + storage)
faked — no GCS/Firestore — so it runs in CI and would have gone red on the outage.

It also pins the state-of-the-art metric plumbing: spacing is taken from the
SOURCE IMAGE's geometry, and volumes/HD95 come back as real numbers.
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


def _admin():
    now = datetime.utcnow()
    return User(id="admin-1", username="admin", email="admin@example.com", full_name="Admin",
                role=UserRole.ADMIN, is_active=True, is_locked=False, email_verified=True,
                created_at=now, updated_at=now)


def _mask_with_lesion(shape=(10, 20, 20)):
    m = np.zeros(shape, dtype=np.uint8)
    m[3:7, 5:11, 5:11] = 1   # a ~144-voxel blob (well above the 3 mm^3 floor)
    return m


class _FakeSeg:
    """Minimal stand-in for SegmentationService: masks + real metadata, no I/O."""
    def __init__(self, masks):
        self._masks = masks

    def get_loaded(self, sid):
        if sid not in self._masks:
            return None
        return {
            "masks_3d": self._masks[sid],
            "metadata": SegmentationMetadata(
                file_id=f"img-{sid}",
                labels=[LabelInfo(id=1, name="MS Lesion", color="#ff0000", opacity=0.5, visible=True)],
            ),
        }

    def get_mask(self, sid):
        return self._masks.get(sid)

    def persist(self, sid):
        # analysis routes cache their result via persist(); no durable store here.
        return None


class _FakeStorage:
    """download_file returns a NIfTI carrying real voxel geometry (zooms)."""
    async def download_file(self, bucket, file_id):
        img = nib.Nifti1Image(np.zeros((20, 20, 10), dtype=np.uint8), np.eye(4))
        img.header.set_zooms((1.0, 1.0, 3.0))  # native (za0, za1, zk) -> spacing (3,1,1)
        return img.to_bytes()


@pytest.fixture
def client():
    seg = _FakeSeg({"seg-a": _mask_with_lesion(), "seg-b": _mask_with_lesion()})
    app.dependency_overrides[get_current_active_user] = _admin
    app.dependency_overrides[get_segmentation_service] = lambda: seg
    app.dependency_overrides[get_storage_service] = lambda: _FakeStorage()
    try:
        yield TestClient(app)
    finally:
        for dep in (get_current_active_user, get_segmentation_service, get_storage_service):
            app.dependency_overrides.pop(dep, None)


def test_lesion_analysis_returns_200_with_real_volumes(client):
    """The exact flow that 500'd: lesion-analysis must resolve spacing from the
    source image and return lesions with mm^3 volumes."""
    r = client.get("/api/v1/segmentation/seg-a/lesion-analysis")
    assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
    body = r.json()
    assert body["total_count"] >= 1
    les = body["lesions"][0]
    # spacing (3,1,1) -> volume = voxel_count * 3 mm^3 (not the old assumed 1 mm^3)
    assert les["volume_mm3"] == pytest.approx(les["voxel_count"] * 3.0)


def test_dis_assessment_returns_200(client):
    r = client.get("/api/v1/segmentation/seg-a/dis-assessment")
    assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
    assert "dis_met_brain" in r.json()


def test_compare_two_segmentations_returns_200_with_metrics(client):
    """The comparison panel (#11) flow: two segmentations must compare without a
    500 and return Dice/Hausdorff (identical masks -> Dice 1.0, HD95 0)."""
    r = client.post("/api/v1/segmentation/compare", json={
        "masks": [
            {"type": "segmentation", "id": "seg-a", "label": "A"},
            {"type": "segmentation", "id": "seg-b", "label": "B"},
        ],
    })
    assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
    comp = r.json()["comparisons"][0]
    assert comp["dice"] == pytest.approx(1.0)          # identical masks
    assert comp["hausdorff_mm"] == pytest.approx(0.0)  # surface HD95 of identical masks
