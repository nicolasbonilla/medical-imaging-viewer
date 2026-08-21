"""Audit P-4.3: persist() must report whether the save was DURABLE.

_save_segmentation falls back to an ephemeral local write when GCS/Firestore
fails. Previously it returned nothing, so PUT /mask/binary reported an
unqualified `success: True` even when the clinician's edit was only in ephemeral
local storage (lost on Cloud Run restart). persist() now returns the tier:
  "gcs"   -> durable, "local" -> ephemeral fallback only, None -> nothing to save.
"""
from types import SimpleNamespace

import numpy as np
import pytest

from app.services.segmentation_service import SegmentationService


class _FakeDoc:
    def set(self, d):
        self._d = d


class _FakeCollection:
    def document(self, _id):
        return _FakeDoc()


class _FakeDb:
    def collection(self, _name):
        return _FakeCollection()


class _FakeMeta:
    created_at = None
    modified_at = None

    def model_dump(self, mode=None):
        return {"file_id": "img-1"}


@pytest.fixture
def svc(tmp_path):
    s = SegmentationService(storage_path=str(tmp_path), cache_service=None)
    s._db = _FakeDb()
    return s


def _seed(svc, sid):
    svc.segmentations_cache[sid] = {
        "masks_3d": np.zeros((2, 4, 4), dtype=np.uint8),
        "metadata": _FakeMeta(),
        "source_format": "nifti",
    }


def test_returns_gcs_when_durable(svc):
    sid = "seg-gcs"
    _seed(svc, sid)
    # Accept the A-2 keyword args (expected_generation/force) persist now threads.
    svc._save_masks_to_gcs = lambda segmentation_id, masks_3d, **kwargs: None  # succeed
    assert svc.persist(sid) == "gcs"


def test_returns_local_when_gcs_fails(svc):
    sid = "seg-local"
    _seed(svc, sid)

    def _boom(segmentation_id, masks_3d, **kwargs):
        raise RuntimeError("GCS unavailable")

    saved = {}
    svc._save_masks_to_gcs = _boom
    svc._save_segmentation_local = lambda *a, **k: saved.setdefault("local", True)

    assert svc.persist(sid) == "local"
    assert saved.get("local") is True


def test_returns_none_when_absent(svc):
    assert svc.persist("does-not-exist") is None


def test_raises_when_both_tiers_fail(svc):
    sid = "seg-dead"
    _seed(svc, sid)

    def _boom(*a, **k):
        raise RuntimeError("storage down")

    svc._save_masks_to_gcs = _boom
    svc._save_segmentation_local = _boom
    with pytest.raises(RuntimeError):
        svc.persist(sid)
