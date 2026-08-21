"""Audit A-2: cross-instance whole-mask last-writer-wins data loss.

Two sessions (tabs / Cloud Run instances) that both load segmentation X and both
Save would previously let the second write silently CLOBBER the first — the mask
was uploaded to GCS unconditionally. This suite drives the REAL _save_masks_to_gcs
/ _save_segmentation / persist through a fake GCS bucket that enforces
`if_generation_match` exactly as Google Cloud Storage does, and pins the
optimistic-concurrency contract:

  * a fresh mask is written create-only (generation 0) and its generation tracked;
  * a sequential same-instance re-save matches its own advanced baseline;
  * a stale baseline (another writer moved the object on) is REFUSED with 409;
  * an UNKNOWN baseline against an existing object is refused, never clobbered;
  * force=True is the deliberate unconditional overwrite escape hatch;
  * an explicit client token (round-tripped If-Match) is honored verbatim;
  * persist() PROPAGATES the conflict and never launders it into a "local" save.
"""
from types import SimpleNamespace

import numpy as np
import pytest
from google.api_core.exceptions import PreconditionFailed

from app.services.segmentation_service import SegmentationService
from app.core.exceptions import ConflictException

NIFTI_PATH = "segmentations/{sid}/masks.nii.gz"


class _GenBlob:
    """Blob whose upload honors if_generation_match with GCS semantics:
    match==0 => must NOT exist; match==N => current generation must equal N."""

    def __init__(self, bucket, name):
        self._bucket = bucket
        self.name = name

    @property
    def generation(self):
        entry = self._bucket.store.get(self.name)
        return entry[0] if entry else None

    def exists(self):
        return self.name in self._bucket.store

    def download_to_file(self, buf):
        buf.write(self._bucket.store[self.name][1])

    def upload_from_file(self, buf, content_type=None, if_generation_match=None, **kwargs):
        data = buf.read()
        present = self.name in self._bucket.store
        cur_gen = self._bucket.store[self.name][0] if present else None
        if if_generation_match is not None:
            if if_generation_match == 0:
                if present:
                    raise PreconditionFailed("object already exists (create-only)")
            elif cur_gen != if_generation_match:
                raise PreconditionFailed(f"generation {cur_gen} != expected {if_generation_match}")
        new_gen = (cur_gen or 0) + 1
        self._bucket.store[self.name] = (new_gen, data)

    def reload(self):
        pass


class _GenBucket:
    def __init__(self):
        self.store = {}  # name -> (generation:int, bytes)

    def blob(self, name):
        return _GenBlob(self, name)

    def get_blob(self, name):
        return _GenBlob(self, name) if name in self.store else None


class _FakeDoc:
    def set(self, d):
        self._d = d


class _FakeDb:
    def collection(self, _name):
        return SimpleNamespace(document=lambda _id: _FakeDoc())


def _svc(tmp_path):
    s = SegmentationService(storage_path=str(tmp_path), cache_service=None)
    s._gcs_bucket = _GenBucket()
    s._db = _FakeDb()
    return s


def _seed(svc, sid):
    mask = np.zeros((3, 4, 5), dtype=np.uint8)
    mask[0, 0, 0] = 1
    svc.segmentations_cache[sid] = {
        "metadata": SimpleNamespace(
            file_id="img-x", model_dump=lambda mode=None: {"file_id": "img-x"}
        ),
        "masks_3d": mask,
        "source_format": "nifti",
    }
    return mask


def test_fresh_mask_is_create_only_then_tracks_generation(tmp_path):
    svc = _svc(tmp_path)
    sid = "seg-fresh"
    mask = _seed(svc, sid)
    path = NIFTI_PATH.format(sid=sid)

    # No baseline -> create-only (generation 0). Object created at gen 1.
    svc._save_masks_to_gcs(sid, mask)
    assert svc._gcs_generations[sid] == 1
    assert svc.gcs_bucket.store[path][0] == 1

    # A sequential same-instance re-save matches its own advanced baseline -> gen 2.
    svc._save_masks_to_gcs(sid, mask)
    assert svc._gcs_generations[sid] == 2
    assert svc.gcs_bucket.store[path][0] == 2


def test_stale_baseline_is_refused_and_object_untouched(tmp_path):
    svc = _svc(tmp_path)
    sid = "seg-stale"
    mask = _seed(svc, sid)
    path = NIFTI_PATH.format(sid=sid)

    # This instance loaded at generation 1...
    svc._gcs_generations[sid] = 1
    # ...but another session already moved the durable object to generation 2.
    svc.gcs_bucket.store[path] = (2, b"newer-work-from-other-session")

    with pytest.raises(ConflictException) as ei:
        svc._save_masks_to_gcs(sid, mask)
    assert ei.value.error_code == "SEGMENTATION_STALE_WRITE"
    # The other session's work is intact — never clobbered.
    assert svc.gcs_bucket.store[path] == (2, b"newer-work-from-other-session")


def test_unknown_baseline_against_existing_object_is_refused(tmp_path):
    """None token + existing blob must synthesize a conflict, NEVER write
    unconditionally (the refute's key gap)."""
    svc = _svc(tmp_path)
    sid = "seg-unknown"
    mask = _seed(svc, sid)
    path = NIFTI_PATH.format(sid=sid)
    svc.gcs_bucket.store[path] = (7, b"existing")
    # No cached baseline AND an explicit None token.
    with pytest.raises(ConflictException):
        svc._save_masks_to_gcs(sid, mask, expected_generation=None)
    assert svc.gcs_bucket.store[path] == (7, b"existing")


def test_force_overwrites_unconditionally(tmp_path):
    svc = _svc(tmp_path)
    sid = "seg-force"
    mask = _seed(svc, sid)
    path = NIFTI_PATH.format(sid=sid)
    svc._gcs_generations[sid] = 1
    svc.gcs_bucket.store[path] = (9, b"newer")  # stale baseline vs reality

    svc._save_masks_to_gcs(sid, mask, force=True)  # deliberate overwrite
    assert svc.gcs_bucket.store[path][0] == 10  # bumped, write happened


def test_explicit_client_token_honored_verbatim(tmp_path):
    svc = _svc(tmp_path)
    sid = "seg-token"
    mask = _seed(svc, sid)
    path = NIFTI_PATH.format(sid=sid)
    svc.gcs_bucket.store[path] = (2, b"x")

    # Matching token -> succeeds.
    svc._save_masks_to_gcs(sid, mask, expected_generation=2)
    assert svc.gcs_bucket.store[path][0] == 3

    # Stale token -> refused.
    with pytest.raises(ConflictException):
        svc._save_masks_to_gcs(sid, mask, expected_generation=2)


def test_persist_propagates_conflict_and_does_not_launder_to_local(tmp_path):
    svc = _svc(tmp_path)
    sid = "seg-launder"
    _seed(svc, sid)
    path = NIFTI_PATH.format(sid=sid)
    svc.gcs_bucket.store[path] = (5, b"existing")  # exists, unknown baseline

    def _must_not_run(*a, **k):
        pytest.fail("conflict must NOT fall back to the ephemeral local tier")

    svc._save_segmentation_local = _must_not_run
    with pytest.raises(ConflictException):
        svc.persist(sid)
    # durable object untouched
    assert svc.gcs_bucket.store[path] == (5, b"existing")


def test_discard_cached_evicts_mask_and_generation(tmp_path):
    """A-2 Finding 1: the 409 rollback must EVICT in-memory state (not restore the
    instance's possibly-stale cached mask), so the next read reloads the
    authoritative durable version and the reconcile 'reload' shows the newer work."""
    svc = _svc(tmp_path)
    sid = "seg-evict"
    _seed(svc, sid)
    svc._gcs_generations[sid] = 3
    assert sid in svc.segmentations_cache and sid in svc._gcs_generations

    svc.discard_cached(sid)

    assert sid not in svc.segmentations_cache      # mask evicted
    assert sid not in svc._gcs_generations          # stale baseline dropped
    # Idempotent: safe to call again on an already-absent id.
    svc.discard_cached(sid)


def test_load_records_generation_baseline(tmp_path):
    """A real load through _load_masks_from_gcs must capture the generation so the
    subsequent save is conditioned on it (the end-to-end A-2 path)."""
    svc = _svc(tmp_path)
    sid = "seg-load"
    mask = _seed(svc, sid)
    # Persist once so a real NIfTI object exists at a known generation.
    svc._save_masks_to_gcs(sid, mask)
    gen_after_save = svc._gcs_generations[sid]
    # Forget the in-memory baseline (simulate a fresh instance) and reload.
    svc._gcs_generations.pop(sid, None)
    loaded = svc._load_masks_from_gcs(sid)
    assert loaded is not None
    assert svc._gcs_generations[sid] == gen_after_save  # baseline recovered from GCS
