"""RC-047 (REQ-SAFE-030, HAZ-001) — an AI draft is stored only with its AI provenance, always as
'unreviewed', and only an explicit radiologist action can confirm its review.

CP-FLAMES-BROWSER-001 (in-browser FLAMeS). The reviewer found that a saved AI draft was recorded
exactly like manual work. These tests drive the real schema, the real service method and the real
routes (with the datastore faked):
  - the create request carries `ai_provenance`; the service stores it with segmentation_type
    'automatic', a model-derived validation_source, and review_status forced to 'unreviewed'
    (a client cannot create a pre-confirmed draft);
  - manual creation is unchanged (no provenance, no type);
  - the confirm route records reviewer + time for a radiologist, refuses other roles (403) and
    segmentations without AI provenance (409).
Negative controls: research/flames_in_browser/negative_controls_v2.py (B1-B4).
"""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.core import container
from app.models.schemas import AIProvenance, CreateSegmentationRequest, SegmentationMetadata
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


def _prov(**over):
    base = dict(
        kind="ai_draft", model_name="FLAMeS", model_version="Zenodo 10.5281/zenodo.17955359 v2.0 (Dataset004_WML)",
        model_sha256=SHA, fold=0, source_checkpoint_sha256=CKPT,
        pipeline_version="mstool-flames-browser/0.2.0-prototype", runtime="onnxruntime-web 1.24.1 wasm x1",
        generated_at="2026-10-17T20:00:00.000Z", lesion_count=3, annotated_voxels=120,
        review_status="unreviewed", reviewed_by=None, reviewed_at=None,
    )
    base.update(over)
    return base


def _bare_service():
    svc = object.__new__(SegmentationService)
    svc.segmentations_cache = {}
    svc.cache = None
    svc._save_segmentation = lambda *a, **k: "gcs"  # no datastore in unit tests
    return svc


def _user(role=UserRole.RADIOLOGIST):
    now = datetime.utcnow()
    return User(id="u-1", username="dr_rev", email="dr@example.org", full_name="Dr Rev", role=role,
                created_at=now, updated_at=now)


@pytest.mark.unit
def test_rc047_schema_rejects_a_malformed_model_hash():
    with pytest.raises(ValidationError):
        AIProvenance(**_prov(model_sha256="not-a-hash"))
    with pytest.raises(ValidationError):
        AIProvenance(**_prov(fold=9))


@pytest.mark.unit
def test_rc047_service_stores_provenance_as_automatic_and_forces_unreviewed():
    svc = _bare_service()
    seg = svc.create_segmentation(
        file_id=FILE, image_shape=(4, 5, 3), description="AI DRAFT (unreviewed)",
        ai_provenance=AIProvenance(**_prov(review_status="confirmed", reviewed_by="mallory", reviewed_at="x")),
    )
    meta = seg.metadata
    assert meta.segmentation_type == "automatic"
    assert meta.ai_provenance is not None
    assert meta.ai_provenance.model_sha256 == SHA and meta.ai_provenance.fold == 0
    assert meta.ai_provenance.review_status == "unreviewed"
    assert meta.ai_provenance.reviewed_by is None and meta.ai_provenance.reviewed_at is None
    assert meta.validation_source.startswith("flames-browser-fold0-2a10bb9d72dc")
    # persisted form (Firestore document) keeps the provenance
    dumped = meta.model_dump(mode="json")
    assert dumped["ai_provenance"]["model_sha256"] == SHA
    assert SegmentationMetadata(**dumped).ai_provenance.review_status == "unreviewed"


@pytest.mark.unit
def test_rc047_manual_creation_is_unchanged():
    svc = _bare_service()
    meta = svc.create_segmentation(file_id=FILE, image_shape=(4, 5, 3)).metadata
    assert meta.ai_provenance is None
    assert meta.segmentation_type is None
    assert meta.validation_source is None


class _FakeSegService:
    def __init__(self, provenance=None):
        self.created = []
        self.persisted = []
        self.meta = SegmentationMetadata(file_id=FILE, labels=[],
                                         ai_provenance=AIProvenance(**provenance) if provenance else None)

    def create_segmentation(self, **kw):
        self.created.append(kw)
        return _bare_service().create_segmentation(**kw)

    def get_loaded(self, segmentation_id):
        return {"metadata": self.meta}

    def persist(self, segmentation_id, **kw):
        self.persisted.append(segmentation_id)
        return "gcs"


@pytest.fixture
def client_for(monkeypatch):
    def make(service, role=UserRole.RADIOLOGIST):
        async def allow(*a, **k):
            return None

        import app.api.routes.segmentation as seg_routes
        monkeypatch.setattr(seg_routes, "require_imaging_access", allow)
        app.dependency_overrides[container.get_segmentation_service] = lambda: service
        app.dependency_overrides[get_current_active_user] = lambda: _user(role)
        app.dependency_overrides[ra.require_segmentation_access] = lambda: None
        return TestClient(app, raise_server_exceptions=False)

    yield make
    app.dependency_overrides.clear()


@pytest.mark.unit
def test_rc047_create_route_passes_the_provenance_to_the_service(client_for):
    svc = _FakeSegService()
    r = client_for(svc).post("/api/v1/segmentation/create", json={
        "file_id": FILE, "image_shape": {"rows": 4, "columns": 5, "slices": 3},
        "description": "AI DRAFT (unreviewed)", "ai_provenance": _prov(review_status="confirmed"),
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["metadata"]["segmentation_type"] == "automatic"
    assert body["metadata"]["ai_provenance"]["model_sha256"] == SHA
    assert body["metadata"]["ai_provenance"]["review_status"] == "unreviewed"


@pytest.mark.unit
def test_rc047_confirm_records_the_reviewer(client_for):
    svc = _FakeSegService(provenance=_prov())
    r = client_for(svc).post("/api/v1/segmentation/seg-1/ai-review/confirm")
    assert r.status_code == 200, r.text
    p = r.json()["ai_provenance"]
    assert p["review_status"] == "confirmed" and p["reviewed_by"] == "dr_rev" and p["reviewed_at"]
    assert p["model_sha256"] == SHA  # identity never changes
    assert svc.persisted == ["seg-1"]


@pytest.mark.unit
def test_rc047_only_a_radiologist_can_confirm(client_for):
    svc = _FakeSegService(provenance=_prov())
    r = client_for(svc, role=UserRole.TECHNICIAN).post("/api/v1/segmentation/seg-1/ai-review/confirm")
    assert r.status_code == 403
    assert svc.meta.ai_provenance.review_status == "unreviewed" and svc.persisted == []


@pytest.mark.unit
def test_rc047_manual_work_has_nothing_to_confirm(client_for):
    svc = _FakeSegService(provenance=None)
    r = client_for(svc).post("/api/v1/segmentation/seg-1/ai-review/confirm")
    assert r.status_code == 409
    assert svc.persisted == []
