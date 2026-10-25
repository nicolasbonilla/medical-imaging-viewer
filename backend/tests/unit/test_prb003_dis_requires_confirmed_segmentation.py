"""PRB-003 — dissemination in space only on a segmentation a clinician has confirmed
(RC-070, RC-071, RC-072; REQ-SAFE-038, REQ-SAFE-039, REQ-SAFE-040; HAZ-008, HAZ-005, HAZ-003).

Paper A (research/paper-a-v0.3, `docs/research/records/2026-10-24_paper_a_v03c_controls.json`, key
`app_dis`): on 100 public healthy controls the device's own brain-DIS code, applied to the raw automatic
FLAMeS 5-fold segmentation, returned "DIS met (brain)" in 19 of 100 (95 % CI 11.8-28.1 %); 85 of 100 got
at least one marked spot; 165 of the 263 false spots (63 %) were periventricular. The DIS route computed
DIS on whatever segmentation was loaded — an unreviewed AI draft, a server-tool mask or a mask uploaded
from another program — and nothing consumed the existing review record (RC-047).

These tests were written BEFORE the fix and fail on `main` @ 70cc5c7. They drive the real routes, the
real SegmentationService (datastore stubbed, as in test_rc047) and the real report prompt builder:
  RC-070  DIS is evaluated and shown only when a radiologist's confirmation is bound to the SHA-256 of the
          current stored mask; otherwise an explicit "not evaluated" state with no met / not met, no region
          presence and no topography count — on the DIS route, the classify-regions route, the stored
          metadata, the AI report (re-derived on the server) and the AI assistant;
  RC-071  a segmentation without AI provenance (drawn here, from a server tool, or uploaded) can be
          confirmed only by a radiologist, only for the exact stored mask; any later change voids it;
  RC-072  the information-for-safety text on automatic marking exists in en/es/de and travels with the
          "not evaluated" state of an automatic segmentation and with the report draft.
Negative controls: scripts/safety/prb003_negative_controls.py.
"""
from __future__ import annotations

import sys
import types
from datetime import datetime

import nibabel as nib
import numpy as np
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.core import container
from app.models.schemas import AIProvenance, LabelInfo, SegmentationMetadata, SegmentationResponse
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
D, H, W = 10, 20, 20

# What a "not evaluated" DIS state must never carry: a conclusion, a region presence, a topography count.
CONCLUSION_KEYS = {"dis_met", "dis_met_brain", "dis_met_full", "dit_waiver_supported", "brain_regions_with_lesions",
                   "regions_with_lesions", "total_topographies_involved", "region_details"}
MAGNIMS = [LabelInfo(id=0, name="Background", color="#000000", opacity=0.0, visible=False),
           LabelInfo(id=1, name="Periventricular", color="#E69F00"),
           LabelInfo(id=2, name="Juxtacortical", color="#56B4E9"),
           LabelInfo(id=3, name="Infratentorial", color="#009E73"),
           LabelInfo(id=4, name="Deep White Matter", color="#CC79A7")]


# ----------------------------------------------------------------------------------------- fixtures
def _mask():
    """Two lesions in two DIS regions (PV, JC): 'DIS met (brain)' when evaluated."""
    m = np.zeros((D, H, W), dtype=np.uint8)
    m[2:4, 2:5, 2:5] = 1      # periventricular
    m[6:8, 12:15, 12:15] = 2  # juxtacortical
    return m


def _sha(mask):
    return SegmentationService.mask_sha256(mask)


def _prov(**over):
    base = dict(
        kind="ai_draft", model_name="FLAMeS", model_version="Zenodo 10.5281/zenodo.17955359 v2.0 (Dataset004_WML)",
        model_sha256=SHA, fold=0, source_checkpoint_sha256=CKPT,
        pipeline_version="mstool-flames-browser/0.3.0-prototype", runtime="onnxruntime-web 1.24.1 wasm x1",
        generated_at="2026-10-17T20:00:00.000Z", lesion_count=2, annotated_voxels=36,
        review_status="unreviewed", reviewed_by=None, reviewed_at=None, sequence_evidence="clinician",
    )
    base.update(over)
    return AIProvenance(**base)


def _clinician_review(mask_sha, by="dr_rev", labels=None):
    """A clinician confirmation record (RC-071), bound to the mask and the label scheme (review of PR #68).
    Built as a dict: on the base the field does not exist."""
    from app.services import dis_review_gate as gate
    return {"reviewed_by": by, "reviewed_by_id": "u-1", "reviewed_at": "2026-10-24T10:00:00Z",
            "reviewed_mask_sha256": mask_sha, "reviewed_labels_sha256": gate.labels_sha256(labels or MAGNIMS)}


def _lesion_regions(mask):
    """Each 18-connected lesion of `mask` (first voxel in C order, voxel count, region; 0 = more than one label).
    Computed here, independently of the code under test (second review of PR #68, N1)."""
    from scipy import ndimage
    components, n = ndimage.label(mask > 0, structure=ndimage.generate_binary_structure(3, 2))
    out = []
    for i in range(1, n + 1):
        where = np.flatnonzero(components.ravel() == i)
        values = np.unique(mask.ravel()[where])
        out.append([int(where[0]), int(where.size), int(values[0]) if values.size == 1 else 0])
    return sorted(out)


def _classification(mask, voxel_volume_mm3=3.0):
    """The record classify-regions stores for the lesions of `mask` (review of PR #68, blocker 1; second review,
    N1: with each lesion's region; third review, m-1: with the voxel volume, default that of `_Storage`)."""
    from app.services import dis_review_gate as gate
    return {"classification": {"method": "geometric", "classified_lesion_footprint_sha256": gate.footprint_sha256(mask),
                               "classified_mask_sha256": _sha(mask),
                               "classified_lesion_regions": _lesion_regions(mask), "lesion_connectivity": 18,
                               "voxel_volume_mm3": voxel_volume_mm3}}


class _FakeDB:
    """The metadata store: whole-document `set`, and field `update` with an optional update-time precondition
    (second review of PR #68, N6). `writes` records every write as (kind, document id, data)."""

    def __init__(self):
        self.docs, self.times, self.writes = {}, {}, []

    def write_option(self, last_update_time=None):
        return {"last_update_time": last_update_time}

    def collection(self, name):
        db = self

        class _C:
            def document(self, doc_id):
                class _Snapshot:
                    def __init__(self):
                        self.exists = doc_id in db.docs
                        self.update_time = db.times.get(doc_id)

                    def to_dict(self):
                        return dict(db.docs.get(doc_id) or {})

                class _D:
                    def set(self, data):
                        db.writes.append(("set", doc_id, data))
                        db.docs[doc_id] = data
                        db.times[doc_id] = db.times.get(doc_id, 0) + 1

                    def get(self):
                        return _Snapshot()

                    def update(self, data, option=None):
                        from google.api_core.exceptions import FailedPrecondition, NotFound
                        if doc_id not in db.docs:
                            raise NotFound("no such document")
                        if option is not None and option["last_update_time"] != db.times.get(doc_id):
                            raise FailedPrecondition("the document changed since it was read")
                        db.writes.append(("update", doc_id, data))
                        db.docs[doc_id] = {**db.docs[doc_id], **data}
                        db.times[doc_id] = db.times.get(doc_id, 0) + 1
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


def _seed(svc, sid="seg-1", mask=None, classified=False, **meta):
    mask = _mask() if mask is None else mask
    if classified:
        meta["analysis_data"] = {**(meta.get("analysis_data") or {}), **_classification(mask)}
    metadata = SegmentationMetadata(file_id=FILE, labels=MAGNIMS, **meta)
    svc.segmentations_cache[sid] = {"metadata": metadata, "masks_3d": mask, "image_shape": (H, W, D),
                                    "source_format": "nifti"}
    if isinstance(getattr(svc, "_db", None), _FakeDB):     # the stored metadata document (it exists in production)
        svc._db.docs[sid] = metadata.model_dump(mode="json")
        svc._db.times[sid] = 1
    return svc.segmentations_cache[sid]


class _Storage:
    """The source image: real voxel geometry (zooms 1 x 1 x 3 mm -> spacing (3, 1, 1))."""
    async def download_file(self, bucket, file_id):
        img = nib.Nifti1Image(np.zeros((H, W, D), dtype=np.uint8), np.eye(4))
        img.header.set_zooms((1.0, 1.0, 3.0))
        return img.to_bytes()


def _user(role=UserRole.RADIOLOGIST, username="dr_rev"):
    now = datetime.utcnow()
    return User(id="u-1", username=username, email="dr@example.org", full_name="Dr Rev", role=role,
                created_at=now, updated_at=now)


@pytest.fixture
def client_for(monkeypatch):
    def make(service, role=UserRole.RADIOLOGIST, username="dr_rev"):
        async def allow(*a, **k):
            return None

        import app.api.routes.segmentation as seg_routes
        monkeypatch.setattr(seg_routes, "require_imaging_access", allow)
        monkeypatch.setattr(seg_routes, "authorize_file_scope", allow)
        # Never build a real patient / care-team service (Firestore) in a unit test (PRB-002).
        monkeypatch.setattr(seg_routes, "_seg_patient_service", lambda: None)
        monkeypatch.setattr(seg_routes, "_seg_care_team_service", lambda: None)
        app.dependency_overrides[container.get_segmentation_service] = lambda: service
        app.dependency_overrides[container.get_storage_service] = lambda: _Storage()
        app.dependency_overrides[get_current_active_user] = lambda: _user(role, username)
        app.dependency_overrides[ra.require_segmentation_access] = lambda: None
        return TestClient(app, raise_server_exceptions=False)

    yield make
    app.dependency_overrides.clear()


def _dis(client, sid="seg-1", **params):
    r = client.get(f"/api/v1/segmentation/{sid}/dis-assessment", params=params)
    assert r.status_code == 200, r.text[:300]
    return r.json()


def _assert_not_evaluated(body):
    assert body.get("evaluation_status") == "not_evaluated", body
    leaked = CONCLUSION_KEYS & set(body)
    assert not leaked, f"a DIS conclusion was returned for a segmentation no clinician confirmed: {leaked}"
    assert "requires clinician review of the segmentation" in body.get("message", "")


# ------------------------------------------------------------------ RC-070: the DIS route (HAZ-008)
@pytest.mark.unit
def test_rc070_unreviewed_ai_draft_dis_is_not_evaluated(client_for):
    """The paper A path: a raw automatic segmentation is never turned into 'DIS met'."""
    svc = _service()
    _seed(svc, ai_provenance=_prov(), segmentation_type="automatic")
    body = _dis(client_for(svc))
    _assert_not_evaluated(body)
    assert body["segmentation_review"]["source"] == "ai_draft"
    assert body["segmentation_review"]["status"] == "unconfirmed"


@pytest.mark.unit
def test_rc070_server_tool_segmentation_dis_is_not_evaluated(client_for):
    """LST-AI / FLAMeS-worker / SynthSeg / mindGlide masks carry no AI provenance, only 'automatic'."""
    svc = _service()
    _seed(svc, segmentation_type="automatic", validation_source="lst-ai-v1.0.3")
    body = _dis(client_for(svc))
    _assert_not_evaluated(body)
    assert body["segmentation_review"]["source"] == "automatic_tool"


@pytest.mark.unit
def test_rc070_segmentation_of_unrecorded_origin_dis_is_not_evaluated(client_for):
    """A segmentation without provenance may be hand-drawn or a mask uploaded from another program
    (PUT /mask/binary accepts any bytes): its origin cannot be told, so it needs a confirmation too."""
    svc = _service()
    _seed(svc)
    body = _dis(client_for(svc))
    _assert_not_evaluated(body)
    assert body["segmentation_review"]["source"] == "origin_not_recorded"


@pytest.mark.unit
def test_rc070_confirmed_ai_draft_bound_to_the_current_mask_is_evaluated(client_for):
    """Changed after the review of PR #68: an AI draft needs its own review AND the DIS confirmation of its
    classified regions (the AI review alone is tested in test_prb003_review1_findings.py)."""
    svc = _service()
    mask = _mask()
    _seed(svc, mask=mask, segmentation_type="automatic", classified=True,
          ai_provenance=_prov(review_status="confirmed", reviewed_by="dr_rev", reviewed_at="2026-10-24T09:00:00Z",
                              reviewed_mask_sha256=_sha(mask)),
          clinician_review=_clinician_review(_sha(mask)))
    body = _dis(client_for(svc))
    assert body.get("evaluation_status") == "evaluated", body
    assert body["dis_met_brain"] is True and body["brain_regions_with_lesions"] == 2
    review = body["segmentation_review"]
    assert review["status"] == "confirmed" and review["reviewed_by"] == "dr_rev"
    assert review["reviewed_mask_sha256"] == _sha(mask)


@pytest.mark.unit
def test_rc070_clinician_confirmed_segmentation_is_evaluated(client_for):
    svc = _service()
    mask = _mask()
    _seed(svc, mask=mask, classified=True, clinician_review=_clinician_review(_sha(mask)))
    body = _dis(client_for(svc))
    assert body.get("evaluation_status") == "evaluated", body
    assert body["dis_met_brain"] is True
    assert body["segmentation_review"]["source"] == "origin_not_recorded"
    assert body["segmentation_review"]["reviewed_by"] == "dr_rev"


@pytest.mark.unit
@pytest.mark.parametrize("record", ["ai", "clinician"])
def test_rc070_a_confirmation_given_for_another_mask_does_not_count(client_for, record):
    """The confirmation is bound to the mask that was reviewed (as RC-047), never to the segmentation id."""
    svc = _service()
    other = "c" * 64
    if record == "ai":
        _seed(svc, segmentation_type="automatic", classified=True,
              ai_provenance=_prov(review_status="confirmed", reviewed_by="dr_rev", reviewed_at="x",
                                  reviewed_mask_sha256=other),
              clinician_review=_clinician_review(_sha(_mask())))
    else:
        _seed(svc, classified=True, clinician_review=_clinician_review(other))
    body = _dis(client_for(svc))
    _assert_not_evaluated(body)
    assert body["not_evaluated_reason"] == ("ai_review_missing" if record == "ai" else "confirmation_outdated")


@pytest.mark.unit
def test_rc070_a_clinician_record_never_replaces_the_review_of_an_ai_draft(client_for):
    """An AI draft is confirmed only through its own review (RC-047)."""
    svc = _service()
    mask = _mask()
    _seed(svc, mask=mask, segmentation_type="automatic", ai_provenance=_prov(), classified=True,
          clinician_review=_clinician_review(_sha(mask)))
    body = _dis(client_for(svc))
    _assert_not_evaluated(body)
    assert body["not_evaluated_reason"] == "ai_review_missing"


@pytest.mark.unit
def test_rc070_a_stored_dis_conclusion_is_never_served_for_an_unconfirmed_segmentation(client_for):
    """Records written before the fix (classify-regions stored 'dis_met_brain' for any mask) are not reused."""
    svc = _service()
    entry = _seed(svc, ai_provenance=_prov(), segmentation_type="automatic")
    meta = entry["metadata"]
    meta.analysis_data = {"dis_assessment": {"dis_met_brain": True, "dis_met": True, "brain_regions_with_lesions": 2,
                                             "region_details": {}},
                          "analysis_mask_modified_at": meta.modified_at.isoformat()}
    _assert_not_evaluated(_dis(client_for(svc)))


@pytest.mark.unit
def test_rc070_a_stored_not_evaluated_state_is_never_served_as_a_result_after_confirmation(client_for):
    """classify-regions stores the 'not evaluated' state; a later confirmation must lead to a real computation,
    never to that stored state relabelled as evaluated."""
    svc = _service()
    mask = _mask()
    entry = _seed(svc, mask=mask)
    meta = entry["metadata"]
    # as classify-regions stores it: the 'not evaluated' state of THIS mask (same digest)
    meta.analysis_data = {"dis_assessment": {"evaluation_status": "not_evaluated", "segmentation_id": "seg-1",
                                             "segmentation_review": {"current_mask_sha256": _sha(mask)}},
                          "analysis_mask_modified_at": meta.modified_at.isoformat(), **_classification(mask)}
    client = client_for(svc)
    assert _confirm(client, _sha(mask)).status_code == 200
    body = _dis(client)
    assert body["evaluation_status"] == "evaluated" and body["dis_met_brain"] is True


@pytest.mark.unit
def test_rc070_external_evidence_does_not_bypass_the_gate(client_for):
    svc = _service()
    _seed(svc, ai_provenance=_prov(), segmentation_type="automatic")
    body = _dis(client_for(svc), spinal_cord_involved="true", optic_nerve_involved="true")
    _assert_not_evaluated(body)


@pytest.mark.unit
def test_rc070_segmentation_metadata_responses_carry_no_stored_dis_conclusion(client_for, monkeypatch):
    """The viewer used to show `analysis_data.dis_assessment` straight from the metadata (no route, no gate)."""
    svc = _service()
    entry = _seed(svc, ai_provenance=_prov(), segmentation_type="automatic")
    entry["metadata"].analysis_data = {"dis_assessment": {"dis_met_brain": True, "dis_met": True},
                                       "lesion_analysis": {"total_count": 2}}
    client = client_for(svc)
    r = client.get("/api/v1/segmentation/seg-1")
    assert r.status_code == 200, r.text[:300]
    data = r.json()["metadata"]["analysis_data"]
    assert "dis_assessment" not in data and data["lesion_analysis"] == {"total_count": 2}

    monkeypatch.setattr(svc, "list_segmentations", lambda file_id=None, file_ids=None: [SegmentationResponse(
        segmentation_id="seg-1", file_id=FILE, metadata=entry["metadata"], total_slices=D)], raising=False)
    r = client.get("/api/v1/segmentation/list", params={"file_id": FILE})
    assert r.status_code == 200, r.text[:300]
    listed = r.json()[0]["metadata"]["analysis_data"]
    assert "dis_assessment" not in listed and listed["lesion_analysis"] == {"total_count": 2}
    # The stored record itself is not rewritten by a read.
    assert "dis_assessment" in entry["metadata"].analysis_data


@pytest.mark.unit
def test_rc070_classify_regions_stores_no_dis_conclusion_for_an_unconfirmed_segmentation(client_for, monkeypatch):
    """classify-regions computed and stored DIS for any mask; the viewer displayed it from the metadata."""
    import app.api.routes.segmentation_regions as regions

    svc = _service()
    binary = (_mask() > 0).astype(np.uint8)
    entry = _seed(svc, mask=binary, ai_provenance=_prov(), segmentation_type="automatic")
    monkeypatch.setattr(svc, "list_segmentations", lambda file_id=None, file_ids=None: [], raising=False)
    monkeypatch.setattr(regions, "prepare_geometric_image", lambda affine, native, shape: np.ones(shape, np.uint8))
    monkeypatch.setattr(regions, "classify_lesions_geometric", lambda mask, image, spacing: {
        "classified_mask": _mask(), "method": "geometric", "total_classified": 36, "processing_time_ms": 1,
        "lesions": [], "classification_summary": {"Periventricular": 1, "Juxtacortical": 1}})
    r = client_for(svc).post("/api/v1/segmentation/seg-1/classify-regions", json={"method": "geometric"})
    assert r.status_code == 200, r.text[:300]
    stored = entry["metadata"].analysis_data["dis_assessment"]
    _assert_not_evaluated(stored)


# ------------------------------------------- RC-071: confirming a segmentation without AI provenance
def _confirm(client, digest, sid="seg-1"):
    return client.post(f"/api/v1/segmentation/{sid}/review/confirm", json={"mask_sha256": digest})


@pytest.mark.unit
def test_rc071_a_radiologist_confirms_the_exact_stored_mask_and_dis_becomes_evaluable(client_for):
    svc = _service()
    mask = _mask()
    entry = _seed(svc, mask=mask, segmentation_type="automatic", validation_source="lst-ai-v1.0.3", classified=True)
    client = client_for(svc, username="dr_rev")
    _assert_not_evaluated(_dis(client))
    r = _confirm(client, _sha(mask))
    assert r.status_code == 200, r.text[:300]
    review = entry["metadata"].clinician_review
    assert review.reviewed_by == "dr_rev" and review.reviewed_mask_sha256 == _sha(mask)
    assert review.reviewed_at
    body = _dis(client)
    assert body["evaluation_status"] == "evaluated" and body["dis_met_brain"] is True


@pytest.mark.unit
@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.TECHNICIAN])
def test_rc071_only_a_radiologist_can_confirm(client_for, role):
    svc = _service()
    mask = _mask()
    entry = _seed(svc, mask=mask)
    r = _confirm(client_for(svc, role=role), _sha(mask))
    assert r.status_code == 403, r.text[:300]
    assert getattr(entry["metadata"], "clinician_review", None) is None


@pytest.mark.unit
def test_rc071_a_confirmation_for_another_mask_is_refused(client_for):
    svc = _service()
    entry = _seed(svc, classified=True)
    r = _confirm(client_for(svc), "d" * 64)
    assert r.status_code == 409, r.text[:300]
    assert "not the one you checked" in r.text
    assert getattr(entry["metadata"], "clinician_review", None) is None


@pytest.mark.unit
def test_rc071_an_ai_draft_is_confirmed_only_through_its_own_review(client_for):
    svc = _service()
    mask = _mask()
    entry = _seed(svc, mask=mask, ai_provenance=_prov(), segmentation_type="automatic", classified=True)
    r = _confirm(client_for(svc), _sha(mask))
    assert r.status_code == 409, r.text[:300]
    assert "AI draft" in r.text
    assert getattr(entry["metadata"], "clinician_review", None) is None
    assert entry["metadata"].ai_provenance.review_status == "unreviewed"


@pytest.mark.unit
def test_rc071_any_later_change_of_the_mask_voids_the_confirmation():
    svc = _service()
    mask = _mask()
    entry = _seed(svc, mask=mask, classified=True, clinician_review=_clinician_review(_sha(mask)))
    assert svc.enforce_review_binding(entry) is False          # unchanged mask: kept
    assert entry["metadata"].clinician_review is not None
    changed = mask.copy()
    changed[0, 0, 0] = 4
    entry["masks_3d"] = changed
    svc.persist("seg-1")                                        # the single save point (as RC-047)
    assert entry["metadata"].clinician_review is None


@pytest.mark.unit
def test_rc071_saving_a_changed_mask_through_the_upload_route_voids_the_confirmation(client_for):
    svc = _service()
    mask = _mask()
    entry = _seed(svc, mask=mask, clinician_review=_clinician_review(_sha(mask)))
    changed = mask.copy()
    changed[5, 10, 10] = 4
    body = np.array(changed.shape, dtype="<u4").tobytes() + changed.tobytes()
    r = client_for(svc, role=UserRole.TECHNICIAN).put("/api/v1/segmentation/seg-1/mask/binary", content=body)
    assert r.status_code == 200, r.text[:300]
    assert entry["metadata"].clinician_review is None
    _assert_not_evaluated(_dis(client_for(svc)))


@pytest.mark.unit
def test_rc071_the_confirmation_cannot_be_sent_by_the_client_on_create(client_for):
    svc = _service()
    client = client_for(svc)
    r = client.post("/api/v1/segmentation/create", json={
        "file_id": FILE, "image_shape": {"rows": H, "columns": W, "slices": D},
        "clinician_review": _clinician_review(_sha(np.zeros((D, H, W), np.uint8)), by="mallory")})
    assert r.status_code == 200, r.text[:300]
    sid = r.json()["segmentation_id"]
    assert getattr(svc.segmentations_cache[sid]["metadata"], "clinician_review", None) is None
    _assert_not_evaluated(_dis(client, sid))


# ---------------------------------------------------- RC-070 / RC-072: the AI report (HAZ-003, HAZ-008)
def _prompt(findings, language="en"):
    from app.services.brain_report_service import BrainReportService
    return BrainReportService.__new__(BrainReportService)._build_findings_prompt(findings, language=language)


@pytest.mark.unit
@pytest.mark.parametrize("block", [
    {"dis_met": True, "regions_with_lesions": 3, "total_dis_regions": 4,
     "region_details": {"Periventricular": {"present": True}}},            # a block from before the fix
    {"evaluation_status": "not_evaluated", "segmentation_id": "s"},         # the new explicit state
    {"segmentation_id": "s"},                                                # a block without any flag
], ids=["legacy-met", "not-evaluated", "no-flag"])
def test_rc070_report_prompt_never_states_met_or_not_met_unless_evaluated(block):
    prompt = _prompt({"dis_assessment": block})
    assert "DIS Assessment: MET" not in prompt and "NOT MET" not in prompt
    assert "NOT EVALUATED" in prompt
    assert "requires clinician review of the segmentation" in prompt


@pytest.mark.unit
def test_rc070_report_prompt_with_lesions_and_no_evaluated_dis_forbids_deriving_dis():
    prompt = _prompt({"lesion_analysis": {"total_count": 3, "regions": {
        "Periventricular": {"lesion_count": 2, "total_volume_mm3": 30.0, "total_volume_ml": 0.03}}}})
    assert "NOT EVALUATED" in prompt
    assert "Do NOT state or imply dissemination in space" in prompt


@pytest.mark.unit
def test_rc070_report_prompt_states_the_result_of_an_evaluated_assessment():
    prompt = _prompt({"dis_assessment": {"evaluation_status": "evaluated", "dis_met": True,
                                         "regions_with_lesions": 2, "total_dis_regions": 5,
                                         "region_details": {"Periventricular": {"present": True}}}})
    assert "DIS Assessment: MET" in prompt and "NOT EVALUATED" not in prompt


class _CapturingReport:
    def __init__(self):
        self.calls = []

    async def generate_report(self, **kw):
        self.calls.append(kw)
        return {"report_id": "r", "content": "draft body", "template_type": kw["template_type"],
                "language": kw["language"], "processing_time_ms": 1}


@pytest.fixture
def report_env(monkeypatch):
    """The report route with the model stubbed; the DIS block is re-derived from the stored segmentation."""
    import app.api.routes.ai_report as ai_report

    svc = _service()
    report = _CapturingReport()
    authorized = []

    async def authorize(specs, user):
        authorized.extend(specs)

    monkeypatch.setattr(ai_report, "get_report_service", lambda: report)
    monkeypatch.setattr(ai_report, "_dis_services", lambda: (svc, _Storage()), raising=False)
    monkeypatch.setattr(ai_report, "authorize_mask_specs", authorize, raising=False)
    app.dependency_overrides[get_current_active_user] = lambda: _user()
    yield TestClient(app, raise_server_exceptions=False), svc, report, authorized
    app.dependency_overrides.clear()


def _generate(client, findings, language="en", sid="seg-1"):
    """Changed after the review of PR #68: the request names its segmentation; DIS is derived for it."""
    body = {"template_type": "ms_comprehensive", "language": language, "findings": findings}
    if sid is not None:
        body["segmentation_id"] = sid
    return client.post("/api/v1/ai/report/generate", json=body)


@pytest.mark.unit
def test_rc070_report_route_replaces_a_client_dis_conclusion_with_the_server_state(report_env):
    client, svc, report, authorized = report_env
    _seed(svc, ai_provenance=_prov(), segmentation_type="automatic")
    forged = {"segmentation_id": "seg-1", "evaluation_status": "evaluated", "dis_met": True, "dis_met_brain": True,
              "regions_with_lesions": 3, "region_details": {"Periventricular": {"present": True}}}
    r = _generate(client, {"dis_assessment": forged, "lesion_analysis": {"total_count": 2}})
    assert r.status_code == 200, r.text[:300]
    sent = report.calls[0]["findings"]["dis_assessment"]
    _assert_not_evaluated(sent)
    assert authorized == [{"type": "segmentation", "id": "seg-1"}]       # RC-029: the caller may read it


@pytest.mark.unit
def test_rc070_report_route_uses_the_server_assessment_of_a_confirmed_segmentation(report_env):
    client, svc, report, _ = report_env
    mask = _mask()
    _seed(svc, mask=mask, classified=True, clinician_review=_clinician_review(_sha(mask)))
    r = _generate(client, {"dis_assessment": {"segmentation_id": "seg-1", "evaluation_status": "evaluated",
                                              "dis_met": False, "regions_with_lesions": 0}})
    assert r.status_code == 200, r.text[:300]
    sent = report.calls[0]["findings"]["dis_assessment"]
    assert sent["evaluation_status"] == "evaluated" and sent["dis_met"] is True   # the server's, not the client's
    # Compute-only for the assistant (RC-033): the report route stores nothing on the segmentation.
    assert not (svc.segmentations_cache["seg-1"]["metadata"].analysis_data or {}).get("dis_assessment")


@pytest.mark.unit
def test_rc070_report_route_dis_block_naming_no_segmentation_is_not_evaluated(report_env):
    client, _svc, report, authorized = report_env
    r = _generate(client, {"dis_assessment": {"dis_met": True, "evaluation_status": "evaluated"},
                           "lesion_analysis": {"total_count": 1}}, sid=None)
    assert r.status_code == 200, r.text[:300]
    _assert_not_evaluated(report.calls[0]["findings"]["dis_assessment"])
    assert authorized == []


@pytest.mark.unit
def test_rc070_report_route_refuses_a_request_whose_only_measurement_is_an_unevaluated_dis(report_env):
    """A 'not evaluated' DIS state is not a measurement: the model would draft from nothing (RC-034)."""
    client, svc, report, _ = report_env
    _seed(svc, ai_provenance=_prov(), segmentation_type="automatic")
    r = _generate(client, {"dis_assessment": {"segmentation_id": "seg-1", "dis_met": True}})
    assert r.status_code == 422, r.text[:300]
    assert report.calls == []


@pytest.mark.unit
def test_rc070_report_route_refuses_a_segmentation_the_caller_cannot_read(report_env, monkeypatch):
    import app.api.routes.ai_report as ai_report
    client, svc, report, _ = report_env
    _seed(svc)

    async def deny(specs, user):
        raise HTTPException(status_code=404, detail="Segmentation not found")

    monkeypatch.setattr(ai_report, "authorize_mask_specs", deny, raising=False)
    r = _generate(client, {"dis_assessment": {"segmentation_id": "seg-1", "dis_met": True}})
    assert r.status_code == 404, r.text[:300]
    assert report.calls == []


@pytest.mark.unit
@pytest.mark.parametrize("lang,phrase", [
    ("en", "Dissemination in space: not evaluated"),
    ("es", "Diseminación en el espacio: no evaluada"),
    ("de", "Räumliche Dissemination: nicht beurteilt"),
])
def test_rc072_report_draft_ends_with_the_not_evaluated_notice_in_its_language(report_env, lang, phrase):
    client, svc, _report, _ = report_env
    _seed(svc, ai_provenance=_prov(), segmentation_type="automatic")
    r = _generate(client, {"dis_assessment": {"segmentation_id": "seg-1"}, "lesion_analysis": {"total_count": 2}},
                  language=lang)
    assert r.status_code == 200, r.text[:300]
    content = r.json()["content"]
    assert content.startswith("draft body")
    notice = content[len("draft body"):]
    assert phrase in notice
    from app.services import dis_review_gate as gate
    assert gate.AUTOMATIC_MARKING_NOTICE[lang] in notice


@pytest.mark.unit
def test_rc072_automatic_marking_notice_exists_in_every_language():
    from app.services import dis_review_gate as gate
    texts = gate.AUTOMATIC_MARKING_NOTICE
    assert set(texts) == {"en", "es", "de"}
    assert "healthy brains" in texts["en"] and "not evidence of multiple sclerosis" in texts["en"]
    assert "cerebros sanos" in texts["es"] and "esclerosis múltiple" in texts["es"]
    assert "gesunden Gehirnen" in texts["de"] and "Multiplen Sklerose" in texts["de"]


@pytest.mark.unit
@pytest.mark.parametrize("seed,expected", [
    ({"ai_provenance": "draft", "segmentation_type": "automatic"}, True),
    ({"segmentation_type": "automatic", "validation_source": "flames-v1.0"}, True),
    ({}, False),
], ids=["ai-draft", "server-tool", "origin-not-recorded"])
def test_rc072_not_evaluated_state_of_an_automatic_segmentation_carries_the_notice(client_for, seed, expected):
    from app.services import dis_review_gate as gate
    svc = _service()
    meta = dict(seed)
    if meta.get("ai_provenance") == "draft":
        meta["ai_provenance"] = _prov()
    _seed(svc, **meta)
    body = _dis(client_for(svc))
    _assert_not_evaluated(body)
    assert (body.get("information_for_safety") == gate.AUTOMATIC_MARKING_NOTICE["en"]) is expected


# ------------------------------------------------------------------- RC-070: the AI assistant (MCP)
@pytest.fixture
def ms_server(monkeypatch):
    """The real assistant server module, with the `fastmcp` package (not installed here) stubbed."""
    fake = types.ModuleType("fastmcp")

    class FastMCP:
        def __init__(self, name, description="", instructions=""):
            self.instructions = instructions

        def tool(self):
            return lambda f: f

        def resource(self, uri):
            return lambda f: f

    fake.FastMCP = FastMCP
    monkeypatch.setitem(sys.modules, "fastmcp", fake)
    monkeypatch.delitem(sys.modules, "app.mcp.ms_clinical_server", raising=False)
    import app.mcp.ms_clinical_server as server
    yield server
    sys.modules.pop("app.mcp.ms_clinical_server", None)


def _run(coro):
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.mark.unit
def test_rc070_assistant_never_receives_a_dis_conclusion_that_was_not_evaluated(ms_server, monkeypatch):
    """Also against an older backend that still returns a bare 'dis_met' block."""
    async def api_get(path, params=None):
        if path.endswith("/dis-assessment"):
            return {"segmentation_id": "seg-1", "dis_met": True, "dis_met_brain": True, "region_details": {}}
        if path.endswith("/lesion-analysis"):
            return {"total_count": 2}
        return {"metadata": {"analysis_data": {}}}

    monkeypatch.setattr(ms_server, "api_get", api_get)
    out = _run(ms_server.summarize_dis_items("seg-1"))
    _assert_not_evaluated(out["dis_assessment"])


@pytest.mark.unit
def test_rc070_assistant_receives_an_evaluated_assessment_unchanged(ms_server, monkeypatch):
    evaluated = {"segmentation_id": "seg-1", "evaluation_status": "evaluated", "dis_met_brain": True,
                 "segmentation_review": {"status": "confirmed", "reviewed_by": "dr_rev"}}

    async def api_get(path, params=None):
        if path.endswith("/dis-assessment"):
            return dict(evaluated)
        return {"metadata": {"analysis_data": {}}} if path == "/segmentation/seg-1" else {"total_count": 2}

    monkeypatch.setattr(ms_server, "api_get", api_get)
    # Changed by the second review of PR #68 (N5): unchanged except the confirmer, given by role, never by name.
    assert _run(ms_server.summarize_dis_items("seg-1"))["dis_assessment"] == {
        **evaluated, "segmentation_review": {"status": "confirmed", "reviewed_by_role": "radiologist"}}


@pytest.mark.unit
def test_rc070_assistant_instructions_forbid_deriving_dis_from_an_unconfirmed_segmentation(ms_server):
    text = ms_server.mcp.instructions
    assert "requires clinician review of the segmentation" in text
    assert "never derive dissemination in space" in text.lower()
