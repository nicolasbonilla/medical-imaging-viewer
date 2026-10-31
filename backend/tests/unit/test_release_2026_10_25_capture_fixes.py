"""Release 2026-10-25 — browser capture session of the release build (2026-10-28), finding F09 (backend side).

F09: the region classification (Class C `ms_region_classifier.py`, every path) does not classify lesion components
smaller than MIN_LESION_VOLUME_MM3 (3 mm³) and builds the classified mask from zeros, so those components disappear
from the stored mask without a word — in the capture the expert mask went from 29,903 to 29,886 voxels, and the
radiologist then confirms "every lesion" of a mask that changed. The classify-regions route now compares the mask
before and after and states how many components and voxels were removed and why — in its response and in the stored
classification record, so the confirmation step can show it in a later session too. The Class C module is not
changed.

Written BEFORE the correction (fails on c7a06cf). Nothing reaches a store or a cloud service (PRB-002).
"""
import nibabel as nib
import numpy as np
import pytest

from app.core import container
from app.main import app
from tests.unit.test_prb003_dis_requires_confirmed_segmentation import (  # noqa: F401  (fixture)
    D, H, W, _mask, _seed, _service, client_for,
)


class _Storage1mm:
    """The source image with 1 x 1 x 1 mm voxels: a one-voxel speck is 1 mm³, below the 3 mm³ minimum."""
    async def download_file(self, bucket, file_id):
        img = nib.Nifti1Image(np.zeros((H, W, D), dtype=np.uint8), np.eye(4))
        img.header.set_zooms((1.0, 1.0, 1.0))
        return img.to_bytes()


def _mask_with_specks():
    mask = (_mask() > 0).astype(np.uint8)
    mask[9, 19, 19] = 1          # two one-voxel components, far from the two lesions (18-connectivity)
    mask[0, 0, 19] = 1
    return mask


def _classify(client_for, monkeypatch, mask):
    import app.api.routes.segmentation_regions as regions_route
    svc = _service()
    entry = _seed(svc, mask=mask)
    monkeypatch.setattr(svc, "list_segmentations", lambda file_id=None, file_ids=None: [], raising=False)
    # the brain outline the geometric rules need (the real classifier runs on it)
    monkeypatch.setattr(regions_route, "prepare_geometric_image", lambda affine, native, shape: np.ones(shape, np.uint8))
    client = client_for(svc)
    app.dependency_overrides[container.get_storage_service] = lambda: _Storage1mm()
    r = client.post("/api/v1/segmentation/seg-1/classify-regions", json={"method": "geometric"})
    assert r.status_code == 200, r.text[:400]
    return r.json(), entry


@pytest.mark.unit
def test_rc070_release_f09_classification_states_the_small_components_it_removed(client_for, monkeypatch):
    before = _mask_with_specks()
    body, entry = _classify(client_for, monkeypatch, before)
    after = entry["masks_3d"]
    lost = int(((before > 0) & ~(after > 0)).sum())
    assert lost == 2, "the real classifier is expected to drop the two one-voxel specks (below 3 mm³)"
    removed = body["removed_small_components"]
    assert removed["components"] == 2 and removed["voxels"] == lost
    assert removed["volume_mm3"] == pytest.approx(2.0)
    assert removed["min_lesion_volume_mm3"] == 3.0
    assert "3 mm³" in removed["reason"] and "removed" in removed["reason"]
    # kept with the classification record, so the confirmation can show it in a later session
    assert entry["metadata"].analysis_data["classification"]["removed_small_components"] == removed


@pytest.mark.unit
def test_rc070_release_f09_nothing_removed_is_stated_as_zero(client_for, monkeypatch):
    body, _entry = _classify(client_for, monkeypatch, (_mask() > 0).astype(np.uint8))
    removed = body["removed_small_components"]
    assert (removed["components"], removed["voxels"], removed["volume_mm3"]) == (0, 0, 0.0)


@pytest.mark.unit
def test_rc070_release_f09_the_route_returns_the_labels_it_stored(client_for, monkeypatch):
    """F08 (backend side): the classification returns the label scheme it stored with the mask, so the viewer can
    draw every region at once with the colours the server keeps (instead of assuming its own copy)."""
    body, entry = _classify(client_for, monkeypatch, (_mask() > 0).astype(np.uint8))
    stored = [lbl.model_dump() if hasattr(lbl, "model_dump") else dict(lbl) for lbl in entry["metadata"].labels]
    assert body["labels"] == [{k: s[k] for k in ("id", "name", "color", "opacity", "visible")} for s in stored]
    assert {lbl["id"] for lbl in body["labels"]} >= {1, 2, 3, 4}
