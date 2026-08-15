"""A segmentation whose mask is missing from durable storage must FAIL loudly,
never be fabricated as an all-zero mask.

Data-integrity hazard: _save_segmentation wrote the Firestore doc before the GCS
mask, so a GCS-upload failure left a doc pointing at a non-existent mask. On the
next load, _load_segmentation saw the doc, missed the GCS blob, and FABRICATED an
np.zeros(mask_shape) mask returning success — silently replacing the radiologist's
work with a blank mask. The fix: try the local fallback, else fail (return False)
rather than fabricate.
"""
import numpy as np
import pytest

from app.services.segmentation_service import SegmentationService


class _FakeDoc:
    exists = True

    def to_dict(self):
        return {"file_id": "img-1", "mask_shape": [3, 4, 5], "source_format": "nifti"}


class _FakeDocRef:
    def get(self):
        return _FakeDoc()


class _FakeColl:
    def document(self, _id):
        return _FakeDocRef()


class _FakeDB:
    def collection(self, _name):
        return _FakeColl()


def _service(tmp_path):
    svc = SegmentationService(storage_path=str(tmp_path))
    svc._db = _FakeDB()  # Firestore doc "exists" with a mask_shape
    return svc


def test_load_fails_loud_when_mask_missing_everywhere(tmp_path, monkeypatch):
    svc = _service(tmp_path)
    monkeypatch.setattr(svc, "_load_masks_from_gcs", lambda sid: None)      # GCS blob gone
    monkeypatch.setattr(svc, "_load_segmentation_local", lambda sid: False)  # not on local either

    ok = svc._load_segmentation("seg-1")

    assert ok is False, "must FAIL, not fabricate an empty mask and report success"
    assert "seg-1" not in svc.segmentations_cache, "no all-zero mask may be cached"


def test_load_recovers_from_local_when_gcs_missing(tmp_path, monkeypatch):
    svc = _service(tmp_path)
    monkeypatch.setattr(svc, "_load_masks_from_gcs", lambda sid: None)

    def _local_ok(sid):
        # emulate a successful local recovery populating the cache
        svc.segmentations_cache[sid] = {"masks_3d": np.ones((3, 4, 5), np.uint8)}
        return True
    monkeypatch.setattr(svc, "_load_segmentation_local", _local_ok)

    assert svc._load_segmentation("seg-1") is True
    assert int(svc.segmentations_cache["seg-1"]["masks_3d"].sum()) > 0


def test_load_returns_real_mask_when_gcs_present(tmp_path, monkeypatch):
    svc = _service(tmp_path)
    real = np.ones((3, 4, 5), dtype=np.uint8)
    monkeypatch.setattr(svc, "_load_masks_from_gcs", lambda sid: real)

    assert svc._load_segmentation("seg-1") is True
    assert svc.segmentations_cache["seg-1"]["masks_3d"] is real
