"""RC-047 (REQ-SAFE-030, HAZ-001) — an AI draft is stored only with its AI provenance, always as
'unreviewed', and only an explicit radiologist confirmation, BOUND TO THE EXACT MASK, can mark it reviewed.

CP-FLAMES-BROWSER-001 (in-browser FLAMeS). Findings these tests bind:
  - review 1: a saved AI draft was recorded exactly like manual work;
  - review 2: after a radiologist confirmed, a technician replaced the whole mask and the record still
    said "reviewed by dr_rev" (the mask upload did not reset the review).
They drive the real schema, the real service (`create_segmentation`, `_save_segmentation` with the
datastore stubbed) and the real routes:
  - create stores `ai_provenance` as 'automatic', forces 'unreviewed', records who confirmed the
    sequence (RC-049) from the authenticated user, never from the client;
  - confirm requires the SHA-256 of the mask the clinician reviewed; it must equal the stored mask;
    the confirmation records that hash;
  - ANY later mask change (binary upload, persist) resets the review to 'unreviewed'; re-uploading the
    identical mask keeps it.
Negative controls: research/flames_in_browser/negative_controls_v2.py (B1-B9).
"""
from datetime import datetime

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.core import container
from app.models.schemas import AIProvenance, LabelInfo, SegmentationMetadata
from app.security import get_current_active_user
from app.security.models import User, UserRole
import app.security.resource_access as ra
from app.services.segmentation_service import SegmentationService

PID = "11111111-1111-1111-1111-111111111111"
STUDY = "44444444-4444-4444-4444-444444444444"
SERIES = "55555555-5555-5555-5555-555555555555"
FILE = f"patients/{PID}/studies/{STUDY}/series/{SERIES}/flair.nii.gz"
SHA = "2a10bb9d72dc33381a3f44dd6a59ec612dfd87534e02f15488b426ae127176ae"
CKPT = "4fc7db24e7c1541b59023df2a2f498a964eb629fe38f4eaec763297dd3fdf861"
D, H, W = 3, 4, 5


def _prov(**over):
    base = dict(
        kind="ai_draft", model_name="FLAMeS", model_version="Zenodo 10.5281/zenodo.17955359 v2.0 (Dataset004_WML)",
        model_sha256=SHA, fold=0, source_checkpoint_sha256=CKPT,
        pipeline_version="mstool-flames-browser/0.3.0-prototype", runtime="onnxruntime-web 1.24.1 wasm x1",
        generated_at="2026-10-17T20:00:00.000Z", lesion_count=3, annotated_voxels=120,
        review_status="unreviewed", reviewed_by=None, reviewed_at=None, sequence_evidence="clinician",
    )
    base.update(over)
    return base


class _FakeDB:
    def __init__(self):
        self.docs = {}

    def collection(self, name):
        db = self

        class _C:
            def document(self, doc_id):
                class _D:
                    def set(self, data):
                        db.docs[doc_id] = data
                return _D()
        return _C()


def _service():
    """Real SegmentationService with the datastore stubbed (persist runs the real _save_segmentation)."""
    svc = object.__new__(SegmentationService)
    svc.segmentations_cache = {}
    svc.cache = None
    svc._db = _FakeDB()
    svc._gcs_generations = {}
    svc._save_masks_to_gcs = lambda *a, **k: None
    return svc


def _user(role=UserRole.RADIOLOGIST, username="dr_rev"):
    now = datetime.utcnow()
    return User(id="u-1", username=username, email="dr@example.org", full_name="Dr Rev", role=role,
                created_at=now, updated_at=now)


def _seed(svc, provenance, mask=None):
    mask = np.zeros((D, H, W), dtype=np.uint8) if mask is None else mask
    meta = SegmentationMetadata(file_id=FILE, labels=[LabelInfo(id=1, name="Lesion", color="#FF8C00")],
                                ai_provenance=AIProvenance(**provenance) if provenance else None)
    svc.segmentations_cache["seg-1"] = {"metadata": meta, "masks_3d": mask, "image_shape": (H, W, D),
                                        "source_format": "nifti"}
    return meta


def _mask_body(mask):
    d, h, w = mask.shape
    return np.array([d, h, w], dtype="<u4").tobytes() + mask.astype(np.uint8).tobytes()


@pytest.fixture
def client_for(monkeypatch):
    def make(service, role=UserRole.RADIOLOGIST, username="dr_rev"):
        async def allow(*a, **k):
            return None

        import app.api.routes.segmentation as seg_routes
        monkeypatch.setattr(seg_routes, "require_imaging_access", allow)
        app.dependency_overrides[container.get_segmentation_service] = lambda: service
        app.dependency_overrides[get_current_active_user] = lambda: _user(role, username)
        app.dependency_overrides[ra.require_segmentation_access] = lambda: None
        return TestClient(app, raise_server_exceptions=False)

    yield make
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------------------------- create

@pytest.mark.unit
def test_rc047_schema_rejects_a_malformed_hash_and_requires_sequence_evidence():
    with pytest.raises(ValidationError):
        AIProvenance(**_prov(model_sha256="not-a-hash"))
    with pytest.raises(ValidationError):
        AIProvenance(**_prov(fold=9))
    p = _prov()
    p.pop("sequence_evidence")
    with pytest.raises(ValidationError):
        AIProvenance(**p)


@pytest.mark.unit
def test_rc047_service_stores_provenance_as_automatic_and_forces_unreviewed():
    svc = _service()
    # The most adversarial client claim: "confirmed", with the hash of exactly the empty mask that create() makes,
    # so the mask binding alone would NOT reset it — the create path itself must force "unreviewed".
    empty_mask_sha = SegmentationService.mask_sha256(np.zeros((D, H, W), dtype=np.uint8))
    seg = svc.create_segmentation(
        file_id=FILE, image_shape=(H, W, D), description="AI DRAFT (unreviewed)", created_by="dr_seq",
        ai_provenance=AIProvenance(**_prov(review_status="confirmed", reviewed_by="mallory", reviewed_at="x",
                                           reviewed_mask_sha256=empty_mask_sha, sequence_confirmed_by="mallory")),
    )
    p = seg.metadata.ai_provenance
    assert seg.metadata.segmentation_type == "automatic"
    assert p.model_sha256 == SHA and p.fold == 0
    assert p.review_status == "unreviewed" and p.reviewed_by is None and p.reviewed_mask_sha256 is None
    assert svc.db.docs[seg.segmentation_id]["ai_provenance"]["review_status"] == "unreviewed"  # as persisted
    assert seg.metadata.validation_source.startswith("flames-browser-fold0-2a10bb9d72dc")
    dumped = seg.metadata.model_dump(mode="json")
    assert SegmentationMetadata(**dumped).ai_provenance.review_status == "unreviewed"


@pytest.mark.unit
def test_rc049_who_confirmed_the_sequence_is_the_authenticated_user_never_the_client():
    svc = _service()
    clin = svc.create_segmentation(
        file_id=FILE, image_shape=(H, W, D), created_by="dr_seq",
        ai_provenance=AIProvenance(**_prov(sequence_evidence="clinician", sequence_confirmed_by="mallory")),
    ).metadata.ai_provenance
    assert clin.sequence_evidence == "clinician" and clin.sequence_confirmed_by == "dr_seq"
    hdr = svc.create_segmentation(
        file_id=FILE, image_shape=(H, W, D), created_by="dr_seq",
        ai_provenance=AIProvenance(**_prov(sequence_evidence="header", sequence_confirmed_by="mallory")),
    ).metadata.ai_provenance
    assert hdr.sequence_evidence == "header" and hdr.sequence_confirmed_by is None  # no person confirmed it


@pytest.mark.unit
def test_rc047_manual_creation_is_unchanged():
    meta = _service().create_segmentation(file_id=FILE, image_shape=(H, W, D)).metadata
    assert meta.ai_provenance is None and meta.segmentation_type is None and meta.validation_source is None


@pytest.mark.unit
def test_rc047_create_route_passes_the_provenance_to_the_service(client_for):
    svc = _service()
    r = client_for(svc, username="dr_seq").post("/api/v1/segmentation/create", json={
        "file_id": FILE, "image_shape": {"rows": H, "columns": W, "slices": D},
        "description": "AI DRAFT (unreviewed)", "ai_provenance": _prov(review_status="confirmed"),
    })
    assert r.status_code == 200, r.text
    body = r.json()["metadata"]
    assert body["segmentation_type"] == "automatic"
    assert body["ai_provenance"]["model_sha256"] == SHA
    assert body["ai_provenance"]["review_status"] == "unreviewed"
    assert body["ai_provenance"]["sequence_confirmed_by"] == "dr_seq"


# --------------------------------------------------------------------------------------------- confirm

@pytest.mark.unit
def test_rc047_confirm_binds_the_review_to_the_exact_mask(client_for):
    svc = _service()
    mask = np.zeros((D, H, W), dtype=np.uint8)
    mask[1, 2, 3] = 1
    _seed(svc, _prov(), mask)
    digest = SegmentationService.mask_sha256(mask)
    r = client_for(svc).post("/api/v1/segmentation/seg-1/ai-review/confirm", json={"mask_sha256": digest})
    assert r.status_code == 200, r.text
    p = r.json()["ai_provenance"]
    assert p["review_status"] == "confirmed" and p["reviewed_by"] == "dr_rev" and p["reviewed_at"]
    assert p["reviewed_mask_sha256"] == digest
    assert p["model_sha256"] == SHA  # identity never changes
    assert svc.db.docs["seg-1"]["ai_provenance"]["review_status"] == "confirmed"


@pytest.mark.unit
def test_rc047_confirm_refuses_a_mask_other_than_the_one_reviewed(client_for):
    svc = _service()
    _seed(svc, _prov())
    r = client_for(svc).post("/api/v1/segmentation/seg-1/ai-review/confirm", json={"mask_sha256": "f" * 64})
    assert r.status_code == 409
    assert svc.segmentations_cache["seg-1"]["metadata"].ai_provenance.review_status == "unreviewed"


@pytest.mark.unit
def test_rc047_only_a_radiologist_can_confirm(client_for):
    svc = _service()
    meta = _seed(svc, _prov())
    digest = SegmentationService.mask_sha256(svc.segmentations_cache["seg-1"]["masks_3d"])
    r = client_for(svc, role=UserRole.TECHNICIAN).post("/api/v1/segmentation/seg-1/ai-review/confirm",
                                                       json={"mask_sha256": digest})
    assert r.status_code == 403
    assert meta.ai_provenance.review_status == "unreviewed" and "seg-1" not in svc.db.docs


@pytest.mark.unit
def test_rc047_manual_work_has_nothing_to_confirm(client_for):
    svc = _service()
    _seed(svc, None)
    digest = SegmentationService.mask_sha256(svc.segmentations_cache["seg-1"]["masks_3d"])
    r = client_for(svc).post("/api/v1/segmentation/seg-1/ai-review/confirm", json={"mask_sha256": digest})
    assert r.status_code == 409


# ------------------------------------------------------------------- any mask change resets the review

@pytest.mark.unit
def test_rc047_replacing_the_mask_after_confirmation_resets_the_review(client_for):
    """Re-review finding: a technician replaced the whole mask and the record still said 'reviewed'."""
    svc = _service()
    reviewed = np.zeros((D, H, W), dtype=np.uint8)
    reviewed[0, 0, 0] = 1
    _seed(svc, _prov(), reviewed)
    rad = client_for(svc)
    assert rad.post("/api/v1/segmentation/seg-1/ai-review/confirm",
                    json={"mask_sha256": SegmentationService.mask_sha256(reviewed)}).status_code == 200

    other = np.ones((D, H, W), dtype=np.uint8)
    tech = client_for(svc, role=UserRole.TECHNICIAN, username="tech_1")
    r = tech.put("/api/v1/segmentation/seg-1/mask/binary", content=_mask_body(other),
                 headers={"Content-Type": "application/octet-stream"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ai_review_reset"] is True
    assert body["ai_provenance"]["review_status"] == "unreviewed"
    assert body["ai_provenance"]["reviewed_by"] is None and body["ai_provenance"]["reviewed_mask_sha256"] is None
    stored = svc.db.docs["seg-1"]["ai_provenance"]
    assert stored["review_status"] == "unreviewed" and stored["reviewed_by"] is None


@pytest.mark.unit
def test_rc047_re_uploading_the_identical_mask_keeps_the_review(client_for):
    svc = _service()
    mask = np.zeros((D, H, W), dtype=np.uint8)
    mask[2, 3, 4] = 1
    _seed(svc, _prov(), mask)
    c = client_for(svc)
    assert c.post("/api/v1/segmentation/seg-1/ai-review/confirm",
                  json={"mask_sha256": SegmentationService.mask_sha256(mask)}).status_code == 200
    r = c.put("/api/v1/segmentation/seg-1/mask/binary", content=_mask_body(mask.copy()),
              headers={"Content-Type": "application/octet-stream"})
    assert r.status_code == 200, r.text
    assert r.json()["ai_provenance"]["review_status"] == "confirmed"


@pytest.mark.unit
def test_rc047_persist_resets_a_confirmation_whatever_path_changed_the_mask():
    svc = _service()
    mask = np.zeros((D, H, W), dtype=np.uint8)
    meta = _seed(svc, _prov(review_status="confirmed", reviewed_by="dr_rev", reviewed_at="t",
                            reviewed_mask_sha256=SegmentationService.mask_sha256(mask)), mask)
    svc.segmentations_cache["seg-1"]["masks_3d"][1, 1, 1] = 1  # e.g. a paint stroke
    svc.persist("seg-1")
    assert svc.segmentations_cache["seg-1"]["metadata"].ai_provenance.review_status == "unreviewed"
    assert svc.db.docs["seg-1"]["ai_provenance"]["reviewed_by"] is None
    assert meta is not None
