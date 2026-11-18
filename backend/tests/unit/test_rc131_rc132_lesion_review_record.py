"""RC-131 (REQ-FUNC-119) and RC-132 (REQ-FUNC-120), HAZ-001 cause (m): the reader goes along with the AI draft.

RC-131: the AI draft is kept exactly as the model produced it (write-once, at the first save) and, at the confirmation
of the AI review, compared with the confirmed mask lesion by lesion: kept, corrected, removed, and ADDED by the reader
(the misses of the model, which no accept/reject log shows). Evidence only: the confirmation never waits for it.

RC-132: a radiologist's own reading of an image, recorded BEFORE the draft (write-once), is compared at the
confirmation with the draft and the final mask (found by both, by the reader only, adopted from the draft, added
later, dropped after the draft), so a reader study can tell independent agreement from going along with the draft.
The images read without the draft first are a fixed share chosen by a keyed hash of the image id (0 = off).

Suggested by a reader-study researcher (LinkedIn, 2026-11-18): record the lesions a reader adds, and a set of cases
the reader marks before seeing the draft. They drive the real module, the real routes and the real service with the
datastore and the object store replaced by in-memory fakes.
"""
from datetime import datetime, timedelta

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core import container
from app.models.schemas import AIProvenance, LabelInfo, SegmentationMetadata, SegmentationResponse
from app.security import get_current_active_user
from app.security.models import User, UserRole
import app.security.resource_access as ra
from app.services import lesion_review_record as lrr
from app.services.segmentation_service import SegmentationService

PID = "11111111-1111-1111-1111-111111111111"
STUDY = "44444444-4444-4444-4444-444444444444"
SERIES = "55555555-5555-5555-5555-555555555555"
FILE = f"patients/{PID}/studies/{STUDY}/series/{SERIES}/flair.nii.gz"
SHA = "2a10bb9d72dc33381a3f44dd6a59ec612dfd87534e02f15488b426ae127176ae"
CKPT = "4fc7db24e7c1541b59023df2a2f498a964eb629fe38f4eaec763297dd3fdf861"
D, H, W = 4, 12, 12
LABELS = [LabelInfo(id=1, name="Lesion", color="#FF8C00")]


# ─────────────────────────────────────────────────────────────────────────────────────────────── fakes
class _Blob:
    def __init__(self, store, name):
        self.store, self.name = store, name

    def upload_from_string(self, data, content_type=None, if_generation_match=None):
        from google.api_core.exceptions import PreconditionFailed
        if if_generation_match == 0 and self.name in self.store.objects:
            raise PreconditionFailed("exists")
        self.store.objects[self.name] = data if isinstance(data, bytes) else data.encode("utf-8")

    def exists(self):
        return self.name in self.store.objects

    def download_as_bytes(self):
        return self.store.objects[self.name]

    def delete(self):
        del self.store.objects[self.name]


class _Bucket:
    def __init__(self):
        self.objects = {}

    def blob(self, name):
        return _Blob(self, name)

    def list_blobs(self, prefix=""):
        return [_Blob(self, n) for n in list(self.objects) if n.startswith(prefix)]


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
    svc = object.__new__(SegmentationService)
    svc.segmentations_cache = {}
    svc.cache = None
    svc._db = _FakeDB()
    svc._gcs_generations = {}
    svc._gcs_bucket = _Bucket()
    svc._save_masks_to_gcs = lambda *a, **k: None

    def _list(file_id=None, file_ids=None):
        return [SegmentationResponse(segmentation_id=k, file_id=v["metadata"].file_id, metadata=v["metadata"],
                                     total_slices=v["masks_3d"].shape[0], masks=None)
                for k, v in svc.segmentations_cache.items() if v["metadata"].file_id == file_id]
    svc.list_segmentations = _list
    return svc


def _prov(annotated, **over):
    base = dict(
        kind="ai_draft", model_name="FLAMeS", model_version="Zenodo 10.5281/zenodo.17955359 v2.0 (Dataset004_WML)",
        model_sha256=SHA, fold=0, source_checkpoint_sha256=CKPT,
        pipeline_version="mstool-flames-browser/0.3.0-prototype", runtime="onnxruntime-web 1.24.1 wasm x1",
        generated_at="2026-11-18T10:00:00.000Z", lesion_count=3, annotated_voxels=int(annotated),
        review_status="unreviewed", reviewed_by=None, reviewed_at=None, sequence_evidence="clinician",
    )
    base.update(over)
    return base


def _user(role=UserRole.RADIOLOGIST, username="dr_rev", uid="u-1"):
    now = datetime.utcnow()
    return User(id=uid, username=username, email="dr@example.org", full_name="Dr Rev", role=role,
                created_at=now, updated_at=now)


def _seed(svc, seg_id, mask, provenance=None, created_by="dr_rev", created_at=None):
    meta = SegmentationMetadata(file_id=FILE, labels=LABELS, created_by=created_by,
                                ai_provenance=AIProvenance(**provenance) if provenance else None,
                                segmentation_type="automatic" if provenance else None,
                                created_at=created_at or datetime.utcnow())
    svc.segmentations_cache[seg_id] = {"metadata": meta, "masks_3d": mask.copy(), "image_shape": (H, W, D),
                                       "source_format": "nifti"}
    return meta


class _ImageStorage:
    async def download_file(self, bucket, file_id):
        import nibabel as nib
        return nib.Nifti1Image(np.zeros((H, W, D), dtype=np.uint8), np.eye(4)).to_bytes()


def _on_screen():
    from app.services.dis_review_gate import drawn_labels_sha256, stored_labels
    return {"drawn_labels_sha256": drawn_labels_sha256(stored_labels(LABELS)), "displayed_image_file_id": FILE}


def _body(mask):
    d, h, w = mask.shape
    return np.array([d, h, w], dtype="<u4").tobytes() + mask.astype(np.uint8).tobytes()


@pytest.fixture
def client_for():
    def make(service, role=UserRole.RADIOLOGIST, username="dr_rev", uid="u-1"):
        async def allow(*a, **k):
            return None

        app.dependency_overrides[container.get_segmentation_service] = lambda: service
        app.dependency_overrides[container.get_storage_service] = lambda: _ImageStorage()
        app.dependency_overrides[get_current_active_user] = lambda: _user(role, username, uid)
        app.dependency_overrides[ra.require_segmentation_access] = lambda: None
        return TestClient(app, raise_server_exceptions=False)

    yield make
    app.dependency_overrides.clear()


def _box(mask, z, y, x, size=2, value=1):
    mask[z:z + size, y:y + size, x:x + size] = value
    return mask


def _draft():
    """Three draft lesions far apart: A (kept), B (to be corrected), C (to be removed)."""
    m = np.zeros((D, H, W), dtype=np.uint8)
    _box(m, 0, 0, 0)        # A, 8 voxels
    _box(m, 0, 0, 6)        # B, 8 voxels
    _box(m, 2, 8, 0)        # C, 8 voxels
    return m


def _final_from(draft):
    """A kept; B grown by one voxel; C removed; D added far from any draft lesion."""
    m = draft.copy()
    m[0, 0, 8] = 1                       # B grows (18-connected to B)
    m[2:4, 8:10, 0:2] = 0                # C removed
    _box(m, 2, 8, 8)                     # D added, 8 voxels
    return m


# ─────────────────────────────────────────────────────────────────────────────────────── the comparison
@pytest.mark.unit
def test_rc131_each_draft_lesion_is_kept_corrected_or_removed_and_added_lesions_are_counted():
    rec = lrr.decision_record(_draft(), _final_from(_draft()))
    s = rec["summary"]
    assert (s["draft_lesions"], s["final_lesions"]) == (3, 3)
    assert (s["kept"], s["corrected"], s["removed"], s["added"]) == (1, 1, 1, 1)
    assert (s["voxels_added"], s["voxels_removed"]) == (9, 8)
    by = {e["outcome"]: e for e in rec["lesions"]}
    assert by["added"]["first_voxel"] == [2, 8, 8] and by["added"]["final_voxels"] == 8
    assert by["removed"]["shared_voxels"] == 0 and by["kept"]["shared_voxels"] == 8
    assert not rec["lesions_truncated"]


@pytest.mark.unit
def test_rc131_a_split_or_a_merge_is_a_correction_never_an_addition():
    draft = np.zeros((D, H, W), dtype=np.uint8)
    draft[0, 0, 0:6] = 1                                   # one lesion
    split = draft.copy()
    split[0, 0, 2:4] = 0                                   # cut into two
    s = lrr.decision_record(draft, split)["summary"]
    assert (s["kept"], s["corrected"], s["removed"], s["added"]) == (0, 1, 0, 0)
    two = np.zeros((D, H, W), dtype=np.uint8)
    two[0, 0, 0:2] = 1
    two[0, 0, 4:6] = 1
    merged = two.copy()
    merged[0, 0, 2:4] = 1
    s = lrr.decision_record(two, merged)["summary"]
    assert (s["kept"], s["corrected"], s["removed"], s["added"]) == (0, 2, 0, 0)


@pytest.mark.unit
def test_rc131_a_lesion_drawn_touching_a_draft_lesion_is_part_of_it():
    draft = _box(np.zeros((D, H, W), dtype=np.uint8), 0, 0, 0)
    final = draft.copy()
    _box(final, 0, 2, 0)                                   # touches the draft lesion: one lesion
    s = lrr.decision_record(draft, final)["summary"]
    assert (s["corrected"], s["added"]) == (1, 0)


@pytest.mark.unit
def test_rc131_the_record_lists_at_most_the_bound_but_counts_every_lesion(monkeypatch):
    monkeypatch.setattr(lrr, "MAX_ENTRIES", 2)
    rec = lrr.decision_record(_draft(), _final_from(_draft()))
    assert len(rec["lesions"]) == 2 and rec["lesions_truncated"]
    s = rec["summary"]
    assert s["kept"] + s["corrected"] + s["removed"] + s["added"] == 4


@pytest.mark.unit
def test_rc132_final_lesions_are_related_to_the_reading_before_the_draft():
    reading = np.zeros((D, H, W), dtype=np.uint8)
    _box(reading, 0, 0, 0)          # L1: reader and draft
    _box(reading, 0, 6, 6)          # L2: reader only (the model missed it)
    _box(reading, 2, 0, 9)          # L3: reader had it, dropped after the draft
    draft = np.zeros((D, H, W), dtype=np.uint8)
    _box(draft, 0, 0, 0)            # L1
    _box(draft, 2, 9, 0)            # L4: draft only, accepted
    _box(draft, 0, 9, 9)            # L5: draft only, removed
    final = np.zeros((D, H, W), dtype=np.uint8)
    _box(final, 0, 0, 0)            # L1
    _box(final, 0, 6, 6)            # L2
    _box(final, 2, 9, 0)            # L4
    _box(final, 2, 5, 3)            # L6: in neither (added later)
    rec = lrr.unaided_record(reading, draft, final)
    s = rec["summary"]
    assert (s["reader_and_draft"], s["reader_only"], s["adopted_from_draft"], s["added_later"],
            s["dropped_after_draft"]) == (1, 1, 1, 1, 1)
    assert (s["reader_lesions"], s["draft_lesions"], s["final_lesions"]) == (3, 3, 4)
    assert s["draft_removed"] == 1                                                  # L5
    dropped = [e for e in rec["sites"] if e["category"] == "dropped_after_draft"]
    assert dropped[0]["draft_voxels"] == 0


def _line(x0, x1, z=0, y=0):
    m = np.zeros((D, H, W), dtype=np.uint8)
    m[z, y, x0:x1] = 1
    return m


@pytest.mark.unit
def test_rc132_a_lesion_is_followed_through_outlines_that_differ_between_reading_draft_and_result():
    # review of PR #84, case C: the reader's lesion overlaps the draft's; the result keeps a part the draft lacks
    s = lrr.unaided_record(_line(0, 10), _line(8, 12), _line(0, 6))["summary"]
    assert (s["reader_and_draft"], s["reader_only"]) == (1, 0)
    # case D: the reader's outline touches the draft lesion without sharing a voxel; the result is the draft's
    s = lrr.unaided_record(_line(0, 4), _line(4, 8), _line(4, 8))["summary"]
    assert (s["reader_and_draft"], s["adopted_from_draft"], s["dropped_after_draft"]) == (1, 0, 0)
    # case E: the result bridges a lesion only the reader found and one only the model found: one site, two of each
    rec = lrr.unaided_record(_line(0, 3), _line(5, 8), _line(0, 8))
    assert rec["summary"]["reader_and_draft"] == 1
    site = rec["sites"][0]
    assert (site["reader_lesions"], site["draft_lesions"], site["final_lesions"]) == (1, 1, 1)


@pytest.mark.unit
def test_rc131_a_component_below_the_minimum_lesion_volume_is_never_a_lesion():
    draft = _box(np.zeros((D, H, W), dtype=np.uint8), 0, 0, 0)          # 8 voxels of 1 mm3: a lesion
    remnant = np.zeros_like(draft)
    remnant[0, 0, 0] = 1                                                 # one voxel left of it
    s = lrr.decision_record(draft, remnant, voxel_volume=1.0)["summary"]
    assert (s["removed"], s["corrected"], s["final_small_components"]) == (1, 0, 1)
    click = draft.copy()
    click[3, 11, 11] = 1                                                 # a stray click elsewhere
    s = lrr.decision_record(draft, click, voxel_volume=1.0)["summary"]
    assert (s["kept"], s["added"], s["final_small_components"]) == (1, 0, 1)
    assert s["min_volume_applied"] is True and s["min_lesion_volume_mm3"] == 3.0
    s = lrr.decision_record(draft, click)["summary"]                     # voxel volume unknown: stated
    assert s["min_volume_applied"] is False and s["added"] == 1


@pytest.mark.unit
def test_rc132_the_set_read_without_the_draft_is_a_fixed_share_chosen_by_the_image_alone():
    ids = [f"patients/p/studies/s/series/{i}/flair.nii.gz" for i in range(4000)]
    assert not any(lrr.in_unaided_first_set(i, 0.0, "k") for i in ids)          # off by default
    assert all(lrr.in_unaided_first_set(i, 1.0, "k") for i in ids)
    chosen = [i for i in ids if lrr.in_unaided_first_set(i, 0.2, "k")]
    assert 0.17 < len(chosen) / len(ids) < 0.23
    assert chosen == [i for i in ids if lrr.in_unaided_first_set(i, 0.2, "k")]   # never changes
    assert chosen != [i for i in ids if lrr.in_unaided_first_set(i, 0.2, "another key")]


@pytest.mark.unit
def test_rc132_only_a_reading_recorded_before_the_draft_counts():
    draft_created = datetime(2026, 11, 18, 12, 0, 0)
    before = (object(), {"at": "2026-11-18T11:00:00Z"})
    latest = (object(), {"at": "2026-11-18T13:30:00+02:00"})          # 11:30 UTC, with an offset
    after = (object(), {"at": "2026-11-18T12:00:01Z"})
    assert lrr.reading_before([before, after, latest], draft_created) is latest
    assert lrr.reading_before([after], draft_created) is None


@pytest.mark.unit
def test_rc131_the_object_carries_its_mask_and_meta_and_refuses_a_mismatch():
    svc = _service()
    mask = _draft()
    assert lrr.store_once(svc, "s", lrr.ORIGINAL, mask, {"mask_sha256": lrr.mask_sha256(mask), "at": "t"})
    assert not lrr.store_once(svc, "s", lrr.ORIGINAL, np.zeros_like(mask), {"mask_sha256": "x"})   # never replaced
    got, meta = lrr.load(svc, "s", lrr.ORIGINAL)
    assert np.array_equal(got, mask) and meta["at"] == "t"
    svc._gcs_bucket.objects[lrr.blob_path("t", lrr.UNAIDED)] = lrr.encode(mask, {"mask_sha256": "0" * 64})
    with pytest.raises(lrr.Unreadable):                                            # digest does not match
        lrr.load(svc, "t", lrr.UNAIDED)
    lrr.delete_all(svc, "s")
    assert lrr.load(svc, "s", lrr.ORIGINAL) is None                                # not stored (a different reason)


# ─────────────────────────────────────────────────────────────────────────────────────────────── routes
def _store_original(client, seg_id, mask):
    return client.put(f"/api/v1/segmentation/{seg_id}/ai-draft/original", content=_body(mask),
                      headers={"Content-Type": "application/octet-stream"})


@pytest.mark.unit
def test_rc131_the_draft_is_stored_once_as_produced_and_never_replaced(client_for):
    svc = _service()
    draft = _draft()
    _seed(svc, "seg-ai", np.zeros_like(draft), _prov((draft > 0).sum()))
    c = client_for(svc)
    r = _store_original(c, "seg-ai", draft)
    assert r.status_code == 200, r.text
    got, meta = lrr.load(svc, "seg-ai", lrr.ORIGINAL)
    assert np.array_equal(got, draft) and meta["stored_by"] == "dr_rev" and meta["stored_by_id"] == "u-1"
    assert _store_original(c, "seg-ai", draft).status_code == 409


@pytest.mark.unit
def test_rc131_what_is_not_the_produced_draft_is_refused(client_for):
    svc = _service()
    draft = _draft()
    _seed(svc, "seg-ai", np.zeros_like(draft), _prov((draft > 0).sum()))
    _seed(svc, "seg-manual", np.zeros_like(draft))
    _seed(svc, "seg-other", np.zeros_like(draft), _prov((draft > 0).sum()), created_by="someone_else")
    _seed(svc, "seg-done", np.zeros_like(draft), _prov((draft > 0).sum(), review_status="confirmed"))
    c = client_for(svc)
    corrected = _final_from(draft)
    assert _store_original(c, "seg-ai", corrected).status_code == 409             # not the produced voxels
    assert _store_original(c, "seg-manual", draft).status_code == 409             # no AI provenance
    assert _store_original(c, "seg-other", draft).status_code == 403              # not who saved it
    assert _store_original(c, "seg-done", draft).status_code == 409               # review already confirmed
    assert _store_original(c, "seg-ai", np.zeros((D, W, H + 1), dtype=np.uint8)).status_code == 400
    assert lrr.load(svc, "seg-ai", lrr.ORIGINAL) is None


def _confirm(client, seg_id, mask):
    return client.post(f"/api/v1/segmentation/{seg_id}/ai-review/confirm",
                       json={"mask_sha256": SegmentationService.mask_sha256(mask), **_on_screen()})


@pytest.mark.unit
def test_rc131_the_confirmation_records_what_the_reviewer_did_with_each_lesion(client_for):
    svc = _service()
    draft = _draft()
    _seed(svc, "seg-ai", np.zeros_like(draft), _prov((draft > 0).sum()))
    c = client_for(svc)
    assert _store_original(c, "seg-ai", draft).status_code == 200
    final = _final_from(draft)
    svc.segmentations_cache["seg-ai"]["masks_3d"] = final           # the reviewer's corrections, saved
    r = _confirm(c, "seg-ai", final)
    assert r.status_code == 200, r.text
    record = r.json()["ai_review_record"]
    assert record["available"] and record["summary"]["added"] == 1 and record["summary"]["removed"] == 1
    assert record["reviewed_mask_sha256"] == SegmentationService.mask_sha256(final)
    summary = r.json()["ai_provenance"]["review_record_summary"]
    assert (summary["kept"], summary["corrected"], summary["removed"], summary["added"]) == (1, 1, 1, 1)
    assert "unaided" not in summary and record["unaided"]["reason"] == "no_reading_before_draft"
    stored = [n for n in svc._gcs_bucket.objects if "/review_records/" in n]
    assert len(stored) == 1                                           # every confirmation's record, write-once
    assert "dr_rev" not in str(record)                                 # no names in the record


@pytest.mark.unit
def test_rc131_without_the_original_the_confirmation_still_works_and_says_so(client_for):
    svc = _service()
    final = _final_from(_draft())
    _seed(svc, "seg-ai", final, _prov((final > 0).sum()))
    r = _confirm(client_for(svc), "seg-ai", final)
    assert r.status_code == 200, r.text
    assert r.json()["ai_review_record"] == {**r.json()["ai_review_record"], "available": False,
                                            "reason": "original_not_stored"}
    assert r.json()["ai_provenance"]["review_status"] == "confirmed"


@pytest.mark.unit
def test_rc131_the_counts_go_with_the_review_when_the_mask_changes(client_for):
    svc = _service()
    draft = _draft()
    _seed(svc, "seg-ai", np.zeros_like(draft), _prov((draft > 0).sum()))
    c = client_for(svc)
    _store_original(c, "seg-ai", draft)
    svc.segmentations_cache["seg-ai"]["masks_3d"] = draft.copy()
    assert _confirm(c, "seg-ai", draft).status_code == 200
    changed = _final_from(draft)
    r = c.put("/api/v1/segmentation/seg-ai/mask/binary", content=_body(changed),
              headers={"Content-Type": "application/octet-stream"})
    assert r.status_code == 200, r.text
    prov = svc.segmentations_cache["seg-ai"]["metadata"].ai_provenance
    assert prov.review_status == "unreviewed" and prov.review_record_summary is None


@pytest.mark.unit
def test_rc131_a_client_cannot_send_its_own_counts_at_creation():
    svc = _service()
    resp = svc.create_segmentation(file_id=FILE, image_shape=(H, W, D),
                                   ai_provenance=AIProvenance(**_prov(8, review_record_summary={"kept": 99})),
                                   created_by="dr_rev")
    assert resp.metadata.ai_provenance.review_record_summary is None


def _record_reading(client, seg_id, mask):
    return client.post(f"/api/v1/segmentation/{seg_id}/unaided-read",
                       json={"mask_sha256": SegmentationService.mask_sha256(mask)})


@pytest.fixture
def study_on(monkeypatch):
    """The reader-study set switched on with its own key, every image in it."""
    import app.api.routes.segmentation as seg_routes
    settings = seg_routes.get_settings()
    monkeypatch.setattr(settings, "READER_STUDY_UNAIDED_FRACTION", 1.0)
    monkeypatch.setattr(settings, "READER_STUDY_KEY", "test-study-key")
    return settings


@pytest.mark.unit
def test_rc132_a_reading_before_the_draft_is_recorded_once_and_compared_at_the_confirmation(client_for, study_on):
    svc = _service()
    reading = np.zeros((D, H, W), dtype=np.uint8)
    _box(reading, 0, 0, 0)                      # also drafted
    _box(reading, 0, 6, 6)                      # the model will miss it
    _seed(svc, "seg-reading", reading)
    c = client_for(svc)
    r = _record_reading(c, "seg-reading", reading)
    assert r.status_code == 200, r.text
    assert _record_reading(c, "seg-reading", reading).status_code == 409          # never replaced
    draft = _draft()
    _seed(svc, "seg-ai", np.zeros_like(draft), _prov((draft > 0).sum()),
          created_at=datetime.utcnow() + timedelta(seconds=5))
    assert _store_original(c, "seg-ai", draft).status_code == 200
    final = _final_from(draft)
    _box(final, 0, 6, 6)                        # the reviewer keeps their own lesion
    svc.segmentations_cache["seg-ai"]["masks_3d"] = final
    r = _confirm(c, "seg-ai", final)
    assert r.status_code == 200, r.text
    unaided = r.json()["ai_review_record"]["unaided"]
    assert unaided["available"] and unaided["segmentation_id"] == "seg-reading"
    s = unaided["summary"]
    assert (s["reader_and_draft"], s["reader_only"], s["adopted_from_draft"], s["added_later"],
            s["draft_removed"]) == (1, 1, 1, 1, 1)
    assert r.json()["ai_provenance"]["review_record_summary"]["unaided"]["reader_only"] == 1
    assert r.json()["ai_review_record"]["summary"]["min_volume_applied"] is True     # from the image's own header


@pytest.mark.unit
def test_rc132_a_reading_is_refused_when_it_cannot_be_independent_of_a_draft(client_for, study_on, monkeypatch):
    svc = _service()
    mask = _box(np.zeros((D, H, W), dtype=np.uint8), 0, 0, 0)
    _seed(svc, "seg-mine", mask)
    _seed(svc, "seg-theirs", mask, created_by="dr_other")
    _seed(svc, "seg-ai", mask, _prov((mask > 0).sum()), created_by="dr_other")   # a colleague's draft
    assert _record_reading(client_for(svc, role=UserRole.TECHNICIAN), "seg-mine", mask).status_code == 403
    c = client_for(svc)
    assert _record_reading(c, "seg-theirs", mask).status_code == 403             # not drawn by the caller
    assert _record_reading(c, "seg-ai", mask).status_code == 409                 # an AI draft
    assert _record_reading(c, "seg-mine", np.zeros_like(mask)).status_code == 409   # not the saved mask
    assert _record_reading(c, "seg-mine", mask).status_code == 409               # an AI draft of the image is saved
    del svc.segmentations_cache["seg-ai"]
    lrr.mark_ai_draft_saved(svc, FILE, _user(), "2026-11-18T09:00:00Z")          # caller saved one, then deleted it
    assert _record_reading(c, "seg-mine", mask).status_code == 409
    svc._gcs_bucket.objects.clear()
    monkeypatch.setattr(study_on, "READER_STUDY_UNAIDED_FRACTION", 0.0)
    assert _record_reading(c, "seg-mine", mask).status_code == 409               # not in the study set
    monkeypatch.setattr(study_on, "READER_STUDY_UNAIDED_FRACTION", 1.0)
    assert _record_reading(c, "seg-mine", mask).status_code == 200


@pytest.mark.unit
def test_rc131_the_original_cannot_be_recorded_after_the_clinicians_version(client_for):
    svc = _service()
    draft = _draft()
    corrected = _final_from(draft)
    _seed(svc, "seg-ai", corrected, _prov((corrected > 0).sum()))                # a version is already saved
    r = _store_original(client_for(svc), "seg-ai", corrected)
    assert r.status_code == 409 and lrr.load(svc, "seg-ai", lrr.ORIGINAL) is None


@pytest.mark.unit
def test_rc132_a_reading_recorded_after_the_draft_is_not_counted(client_for):
    svc = _service()
    draft = _draft()
    _seed(svc, "seg-ai", np.zeros_like(draft), _prov((draft > 0).sum()),
          created_at=datetime.utcnow() - timedelta(hours=1))
    late = _seed(svc, "seg-late", draft)
    lrr.store_once(svc, "seg-late", lrr.UNAIDED, draft, {"by_id": "u-1", "at": datetime.utcnow().isoformat() + "Z",
                                                          "mask_sha256": lrr.mask_sha256(draft)})
    assert late.created_by == "dr_rev"
    c = client_for(svc)
    _store_original(c, "seg-ai", draft)
    svc.segmentations_cache["seg-ai"]["masks_3d"] = draft.copy()
    r = _confirm(c, "seg-ai", draft)
    assert r.json()["ai_review_record"]["unaided"] == {"available": False, "reason": "no_reading_before_draft"}


@pytest.mark.unit
def test_rc131_a_record_that_could_not_be_made_is_made_again_on_a_repeat_confirmation(client_for, monkeypatch):
    svc = _service()
    draft = _draft()
    _seed(svc, "seg-ai", np.zeros_like(draft), _prov((draft > 0).sum()))
    c = client_for(svc)
    assert _store_original(c, "seg-ai", draft).status_code == 200
    final = _final_from(draft)
    svc.segmentations_cache["seg-ai"]["masks_3d"] = final
    real_load = lrr.load

    def flaky(service, seg_id, kind):
        raise lrr.Unreadable("storage hiccup")
    monkeypatch.setattr(lrr, "load", flaky)
    r = _confirm(c, "seg-ai", final)
    assert r.json()["ai_review_record"]["reason"] == "original_unreadable"      # not "not stored"
    monkeypatch.setattr(lrr, "load", real_load)
    r = _confirm(c, "seg-ai", final)
    assert r.json()["ai_review_record"]["available"] is True
    assert r.json()["ai_provenance"]["reviewed_by"] == "dr_rev"


@pytest.mark.unit
def test_rc131_rc132_the_record_goes_with_the_review_and_reader_data_only_to_radiologists(client_for):
    from app.services import dis_review_gate as gate
    svc = _service()
    draft = _draft()
    _seed(svc, "seg-ai", np.zeros_like(draft), _prov((draft > 0).sum()))
    c = client_for(svc)
    _store_original(c, "seg-ai", draft)
    final = _final_from(draft)
    svc.segmentations_cache["seg-ai"]["masks_3d"] = final
    assert _confirm(c, "seg-ai", final).status_code == 200
    meta = svc.segmentations_cache["seg-ai"]["metadata"]
    meta.ai_provenance = meta.ai_provenance.model_copy(update={"review_record_summary": {
        **meta.ai_provenance.review_record_summary, "unaided": {"reader_only": 1}}})
    shown, _ = gate.metadata_for_viewer(meta, _user(role=UserRole.TECHNICIAN, username="tech"))
    assert shown.ai_review_record is None and "unaided" not in shown.ai_provenance.review_record_summary
    assert shown.ai_provenance.review_record_summary["added"] == 1                  # the lesion counts stay
    shown, _ = gate.metadata_for_viewer(meta, _user())
    assert shown.ai_review_record is not None
    assert lrr.slim(meta.ai_review_record).get("lesions") is None                   # listings carry no lists
    svc.segmentations_cache["seg-ai"]["masks_3d"] = draft.copy()                     # the mask changes
    svc.enforce_review_binding(svc.segmentations_cache["seg-ai"])
    assert meta.ai_review_record is None


@pytest.mark.unit
def test_rc132_the_assignment_route_says_whether_this_image_is_read_without_the_draft_first(client_for, monkeypatch):
    import app.api.routes.segmentation as seg_routes

    async def allow(*a, **k):
        return None
    monkeypatch.setattr(seg_routes, "authorize_file_scope", allow)
    monkeypatch.setattr(ra, "_patient_service", lambda: None)
    monkeypatch.setattr(ra, "_care_team_service", lambda: None)
    svc = _service()
    c = client_for(svc)
    r = c.get("/api/v1/segmentation/reader-study/assignment", params={"file_id": FILE})
    assert r.status_code == 200 and r.json()["study_on"] is False and r.json()["unaided_first"] is False
    settings = seg_routes.get_settings()
    monkeypatch.setattr(settings, "READER_STUDY_UNAIDED_FRACTION", 1.0)
    r = c.get("/api/v1/segmentation/reader-study/assignment", params={"file_id": FILE})
    assert r.json()["study_on"] is False and r.json()["unaided_first"] is False     # no key: the set stays off
    monkeypatch.setattr(settings, "READER_STUDY_KEY", "test-study-key")
    r = c.get("/api/v1/segmentation/reader-study/assignment", params={"file_id": FILE})
    assert r.json()["unaided_first"] is True and r.json()["reading_recorded"] is False
    tech = client_for(svc, role=UserRole.TECHNICIAN, username="tech").get(
        "/api/v1/segmentation/reader-study/assignment", params={"file_id": FILE})
    assert tech.json()["in_set"] is True and tech.json()["unaided_first"] is False  # never held back
    c = client_for(svc)
    mask = _box(np.zeros((D, H, W), dtype=np.uint8), 0, 0, 0)
    _seed(svc, "seg-reading", mask)
    assert _record_reading(c, "seg-reading", mask).status_code == 200
    r = c.get("/api/v1/segmentation/reader-study/assignment", params={"file_id": FILE})
    assert r.json()["reading_recorded"] is True and r.json()["reading_segmentation_ids"] == ["seg-reading"]
