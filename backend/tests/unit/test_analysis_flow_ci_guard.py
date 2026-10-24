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
    def __init__(self, masks, confirmed=()):
        self._masks = masks
        self._confirmed = set(confirmed)   # PRB-003 (RC-071): segmentations a radiologist confirmed

    def get_loaded(self, sid):
        if sid not in self._masks:
            return None
        if sid not in self._confirmed:
            return {
                "masks_3d": self._masks[sid],
                "metadata": SegmentationMetadata(
                    file_id=f"img-{sid}",
                    labels=[LabelInfo(id=1, name="MS Lesion", color="#ff0000", opacity=0.5, visible=True)],
                ),
            }
        # PRB-003 (RC-070/071): a MAGNIMS-classified segmentation (regions recorded for these lesions) that a
        # radiologist confirmed for this mask and label scheme — the only case where DIS is evaluated.
        from app.services import dis_review_gate as gate
        from app.services.segmentation_service import SegmentationService
        mask = self._masks[sid]
        labels = [LabelInfo(id=0, name="Background", color="#000000")] + [
            LabelInfo(id=i, name=name, color="#ff0000") for i, name in gate.MAGNIMS_REGIONS.items() if i <= 4]
        return {
            "masks_3d": mask,
            "metadata": SegmentationMetadata(
                file_id=f"img-{sid}", labels=labels,
                analysis_data={"classification": {"classified_lesion_footprint_sha256": gate.footprint_sha256(mask),
                                                  "classified_mask_sha256": SegmentationService.mask_sha256(mask)}},
                clinician_review={"reviewed_by": "dr_rev", "reviewed_at": "2026-10-24T10:00:00Z",
                                  "reviewed_mask_sha256": SegmentationService.mask_sha256(mask),
                                  "reviewed_labels_sha256": gate.labels_sha256(labels)},
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
def client(monkeypatch):
    # Object-level authorization (CAPA-007, RC-029) is exercised by
    # test_capa007_analysis_routes_authorization.py; here it is passed through so this
    # file keeps testing the ANALYSIS flow without a datastore.
    from app.security.resource_access import require_segmentation_access
    import app.api.routes.segmentation_analysis as analysis_routes

    async def _authorized(specs, user):
        return None

    monkeypatch.setattr(analysis_routes, "authorize_mask_specs", _authorized)
    two_regions = _mask_with_lesion()
    two_regions[1:3, 14:18, 14:18] = 2          # a second lesion, juxtacortical (MAGNIMS label 2)
    seg = _FakeSeg({"seg-a": _mask_with_lesion(), "seg-b": _mask_with_lesion(), "seg-c": two_regions},
                   confirmed={"seg-c"})
    app.dependency_overrides[get_current_active_user] = _admin
    app.dependency_overrides[get_segmentation_service] = lambda: seg
    app.dependency_overrides[get_storage_service] = lambda: _FakeStorage()
    app.dependency_overrides[require_segmentation_access] = lambda: None
    try:
        yield TestClient(app)
    finally:
        for dep in (get_current_active_user, get_segmentation_service, get_storage_service,
                    require_segmentation_access):
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
    """The route is alive and computes DIS on a MAGNIMS-classified segmentation a radiologist confirmed
    (PRB-003, RC-070 — the full evaluated contract); on a binary 'MS Lesion' mask, whose labels are not
    regions, it answers 200 with the explicit 'not evaluated' state (review of PR #68, blocker 1)."""
    r = client.get("/api/v1/segmentation/seg-c/dis-assessment")
    assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
    body = r.json()
    assert body["evaluation_status"] == "evaluated"
    assert isinstance(body["dis_met_brain"], bool) and body["dis_met_brain"] is True   # PV + JC lesions
    assert body["brain_regions_with_lesions"] == 2
    assert body["total_dis_regions"] == 5
    assert body["brain_regions_evaluated"] == 3
    assert "McDonald 2024" in body["dis_criteria_version"]
    assert set(body["region_details"]) == {"Periventricular", "Juxtacortical", "Infratentorial"}
    r = client.get("/api/v1/segmentation/seg-a/dis-assessment")
    assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
    assert r.json()["evaluation_status"] == "not_evaluated" and "dis_met_brain" not in r.json()
    assert r.json()["not_evaluated_reason"] == "regions_not_classified"


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
