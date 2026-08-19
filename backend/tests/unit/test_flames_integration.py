"""FLAMeS single-FLAIR SOTA segmenter — backend integration + store-back contract.

Covers three things the summary work introduced:

1. The GCS upload-signature bug: `_store_nifti_as_segmentation` (and the SynthSeg
   CSV helper) called `storage.upload(..., data=...)`, but `GCSStorageService.upload`
   takes `file_data=`. Every clinical-tool store-back therefore raised a TypeError at
   runtime — masked in the other tests because they pass `storage_service=None`. These
   tests inject a fake storage whose `upload` has the REAL signature, so a regression
   to `data=` fails here instead of silently in production.

2. The canonical viewer-loadable path: masks must land at
   `segmentations/{id}/masks.nii.gz` (what `_load_masks_from_gcs` reads), not the old
   `clinical-tools/{id}/mask.bin`.

3. FLAMeS wiring: it is listed as a tool, dark until configured, and `run_flames`
   fails closed (no crash) when the worker endpoint is unset.
"""
from pathlib import Path

import numpy as np
import pytest

from app.services import tool_runner_service
from app.services.tool_runner_service import ToolRunnerService
from app.core.interfaces.ai_interface import ToolTaskStatus


class _FakeDoc:
    def __init__(self, sink):
        self._sink = sink

    def set(self, data):
        self._sink["doc"] = data


class _FakeCollection:
    def __init__(self, sink):
        self._sink = sink

    def document(self, _id):
        return _FakeDoc(self._sink)


class _FakeDB:
    def __init__(self, sink):
        self._sink = sink

    def collection(self, _name):
        return _FakeCollection(self._sink)


class _FakeStorage:
    """Storage double whose upload() mirrors GCSStorageService.upload EXACTLY —
    so a caller passing the wrong kwarg (e.g. data= instead of file_data=) raises
    a TypeError here, the way it would in production."""

    def __init__(self):
        self.uploads = []

    async def upload(self, object_name: str, file_data: bytes, content_type: str,
                     metadata=None):
        self.uploads.append(
            {"object_name": object_name, "file_data": file_data,
             "content_type": content_type}
        )
        return {"name": object_name}


def _write_nifti(path: Path, array: np.ndarray) -> Path:
    import nibabel as nib

    nib.save(nib.Nifti1Image(array.astype(np.uint8), np.eye(4)), str(path))
    return path


@pytest.fixture
def _svc(monkeypatch):
    sink: dict = {}
    import app.core.firebase as firebase_mod
    monkeypatch.setattr(firebase_mod, "get_firestore_client",
                        lambda: _FakeDB(sink), raising=False)
    storage = _FakeStorage()
    svc = ToolRunnerService(storage_service=storage)
    return svc, storage, sink


@pytest.mark.asyncio
async def test_store_back_uploads_with_real_signature_to_canonical_path(tmp_path, _svc):
    """Regression guard for the data=/file_data= upload bug + canonical mask path."""
    svc, storage, sink = _svc
    arr = np.zeros((4, 5, 3), dtype=np.uint8)
    arr[1, 2, 0] = 1
    mask_path = _write_nifti(tmp_path / "m.nii.gz", arr)

    seg_id = await svc._store_nifti_as_segmentation(
        mask_path=mask_path,
        file_id="flair-1",
        description="FLAMeS automated MS lesion segmentation",
        validation_source="flames-v1.0",
    )

    assert seg_id
    assert len(storage.uploads) == 1, "the mask must be uploaded exactly once"
    up = storage.uploads[0]
    # canonical, viewer-loadable path (not clinical-tools/{id}/mask.bin)
    assert up["object_name"] == f"segmentations/{seg_id}/masks.nii.gz"
    assert up["content_type"] == "application/gzip"
    # a real gzip'd NIfTI (starts with gzip magic), not the raw .bin protocol
    assert up["file_data"][:2] == b"\x1f\x8b"
    assert sink["doc"]["gcs_path"] == f"segmentations/{seg_id}/masks.nii.gz"


def test_flames_is_listed_and_dark_by_default():
    svc = ToolRunnerService(storage_service=None)
    tools = {t["id"]: t for t in svc.list_tools()}
    assert "flames" in tools, "FLAMeS must be advertised as a clinical tool"
    assert tools["flames"]["required_inputs"] == ["FLAIR"], "FLAMeS is single-FLAIR"
    assert tools["flames"]["available"] is False, "dark until FLAMES_ENABLED + endpoint"
    assert svc.is_flames_available() is False
    assert svc.is_tool_available("flames") is False


@pytest.mark.asyncio
async def test_run_flames_fails_closed_when_unconfigured():
    """With no endpoint set, run_flames must return a FAILED task, never raise."""
    svc = ToolRunnerService(storage_service=None)
    task_id = await svc.run_flames(flair_file_id="flair-1")
    task = await svc.get_task_status(task_id)
    assert task.status == ToolTaskStatus.FAILED
    assert task.tool == "flames"
    assert "not configured" in (task.error or "").lower()
