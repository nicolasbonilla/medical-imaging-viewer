"""Finding #7 — an all-zero clinical-tool (mindGlide/LST-AI/SynthSeg) mask must
not be stored SILENTLY.

A sidecar can return HTTP 200 yet write an all-zeros mask (the model never ran,
the contrast was wrong, or the volume resampled off-grid). Stored verbatim, that
is indistinguishable from a genuine negative — "0 lesions" reads as a clean scan
when the tool actually produced nothing.

The chosen control is VISIBILITY, not rejection: an empty LESION mask is a valid
clinical result (a healthy brain has zero lesion voxels), so we must not fail it.
Instead `_store_nifti_as_segmentation` records `annotated_voxels` in the stored
metadata and logs a warning when the mask is empty, so downstream consumers and
ops can tell "tool ran, found nothing" from "tool produced nothing".
"""
from pathlib import Path

import numpy as np
import pytest

from app.services import tool_runner_service
from app.services.tool_runner_service import ToolRunnerService


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


def _write_nifti(path: Path, array: np.ndarray) -> Path:
    import nibabel as nib

    nib.save(nib.Nifti1Image(array.astype(np.uint8), np.eye(4)), str(path))
    return path


@pytest.fixture
def _capture(monkeypatch):
    """Instantiate the service with no GCS, capture Firestore writes and warnings."""
    sink: dict = {}
    warnings_seen: list = []

    import app.core.firebase as firebase_mod
    monkeypatch.setattr(firebase_mod, "get_firestore_client", lambda: _FakeDB(sink), raising=False)
    monkeypatch.setattr(
        tool_runner_service.logger, "warning",
        lambda *a, **k: warnings_seen.append((a, k)),
    )
    svc = ToolRunnerService(storage_service=None)  # no GCS upload path
    return svc, sink, warnings_seen


@pytest.mark.asyncio
async def test_empty_mask_is_stored_but_flagged(tmp_path, _capture):
    svc, sink, warnings_seen = _capture
    mask_path = _write_nifti(tmp_path / "empty.nii.gz", np.zeros((4, 5, 3), dtype=np.uint8))

    seg_id = await svc._store_nifti_as_segmentation(
        mask_path=mask_path,
        file_id="file-xyz",
        description="mindGlide MS lesion segmentation",
        validation_source="mindglide-v1.0",
    )

    assert isinstance(seg_id, str) and seg_id  # still stored (not rejected)
    assert sink["doc"]["annotated_voxels"] == 0, "empty mask must record 0 annotated voxels"
    # Scope to the empty-mask warning specifically — other subsystems (e.g. the
    # RC-031 orientation fail-safe when no reference MRI is passed) may log their
    # own warnings, which are irrelevant to this control.
    empty_warnings = [w for w in warnings_seen if w[0] and "ALL-ZERO" in str(w[0][0])]
    assert len(empty_warnings) == 1, "an all-zero clinical-tool mask must emit exactly one warning"
    # the warning must carry enough context to investigate the sidecar run
    _, kwargs = empty_warnings[0]
    assert kwargs["extra"]["validation_source"] == "mindglide-v1.0"
    assert kwargs["extra"]["file_id"] == "file-xyz"


@pytest.mark.asyncio
async def test_nonempty_mask_records_true_count_and_no_warning(tmp_path, _capture):
    svc, sink, warnings_seen = _capture
    arr = np.zeros((4, 5, 3), dtype=np.uint8)
    arr[1, 2, 0] = 1
    arr[1, 2, 1] = 1
    arr[2, 3, 2] = 1  # 3 lesion voxels
    mask_path = _write_nifti(tmp_path / "lesions.nii.gz", arr)

    seg_id = await svc._store_nifti_as_segmentation(
        mask_path=mask_path,
        file_id="file-abc",
        description="mindGlide MS lesion segmentation",
        validation_source="mindglide-v1.0",
    )

    assert isinstance(seg_id, str) and seg_id
    assert sink["doc"]["annotated_voxels"] == 3, "voxel count must reflect the actual mask"
    empty_warnings = [w for w in warnings_seen if w[0] and "ALL-ZERO" in str(w[0][0])]
    assert empty_warnings == [], "a populated mask must not raise the empty-mask warning"
