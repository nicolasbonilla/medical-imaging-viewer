"""PRB-003 — finding m-1 of the third independent review of PR #68 at 2e20b8a (written BEFORE the correction).

m-1 (usability, IEC 62366): the DIS gate numbered lesions in raster order of their first voxel and counted components
below the lesion-size floor, while the lesion table numbers them by size (largest first) and leaves those components
out. "Lesion 2 … Juxtacortical → Periventricular" in the correction list could be "Lesion 1" in the table. The gate
now uses the table's numbering (per-label 18-connected components, size order, the table's floor from the voxel volume
recorded by the classification) and the table's slice (rounded centroid), and names a component below the floor
"small component (N voxels)" with its slice.

These tests compare the gate's lists with the real lesion table of the same segmentation (`/lesion-analysis`). They
fail on 2e20b8a (`records/risk_verification/PRB-003_review3_tests_on_2e20b8a_2026-10-24.json`).
"""
from __future__ import annotations

import math

import nibabel as nib
import numpy as np
import pytest

from app.core import container
from app.main import app
from tests.unit.test_prb003_dis_requires_confirmed_segmentation import (  # noqa: F401  (fixtures)
    D, H, W, _confirm, _dis, _seed, _service, _sha, client_for,
)
from tests.unit.test_prb003_review1_findings import _classify


class _Storage1mm:
    """A source image with 1 x 1 x 1 mm voxels: the lesion floor (3 mm³) is 3 voxels."""
    async def download_file(self, bucket, file_id):
        img = nib.Nifti1Image(np.zeros((H, W, D), dtype=np.uint8), np.eye(4))
        img.header.set_zooms((1.0, 1.0, 1.0))
        return img.to_bytes()


def _slice_of(entry):
    """The slice the viewer goes to when the table row is clicked: Math.round(centroid.z)."""
    return math.floor(entry["centroid"]["z"] + 0.5)


def _table(client):
    r = client.get("/api/v1/segmentation/seg-1/lesion-analysis")
    assert r.status_code == 200, r.text[:300]
    return r.json()["lesions"]


@pytest.mark.unit
def test_rc070_m1_a_correction_names_the_lesion_as_the_lesion_table_does(client_for):
    m = np.zeros((D, H, W), dtype=np.uint8)
    m[1:3, 1:3, 1:3] = 1            # small lesion, first in raster order
    m[5:7, 10:14, 10:14] = 2        # larger lesion, later in raster order: number 1 in the table
    svc = _service()
    entry = _seed(svc, mask=m)
    _classify(entry)
    corrected = m.copy()
    corrected[5:7, 10:14, 10:14] = 1                     # its region corrected by hand (JC → PV)
    entry["masks_3d"] = corrected
    client = client_for(svc)
    correction = _dis(client)["regions"]["corrections"][0]
    row = next(les for les in _table(client) if les["voxel_count"] == 32)
    assert correction["lesion"] == row["id"] == 1
    assert correction["slice"] == _slice_of(row)
    assert correction["small_component"] is False


@pytest.mark.unit
def test_rc070_m1_a_lesion_with_two_labels_names_its_parts_as_the_table_does(client_for):
    m = np.zeros((D, H, W), dtype=np.uint8)
    m[1:3, 1:3, 1:3] = 4            # deep white matter lesion, first in raster order, 8 voxels
    m[5:7, 10:13, 10:13] = 1        # periventricular lesion, 18 voxels
    svc = _service()
    entry = _seed(svc, mask=m)
    _classify(entry, voxel_volume_mm3=1.0)
    painted = m.copy()
    painted[6, 12, 11:13] = 2       # 2 voxels of it painted juxtacortical: 2 mm³, below the 3 mm³ floor
    entry["masks_3d"] = painted
    client = client_for(svc)
    app.dependency_overrides[container.get_storage_service] = lambda: _Storage1mm()
    invalid = _dis(client)["regions"]["invalid_lesions"][0]
    table = _table(client)
    main = next(les for les in table if les["voxel_count"] == 16)
    assert invalid["lesion"] == main["id"] == 1
    parts = {p["label_name"]: p for p in invalid["parts"]}
    assert (parts["Periventricular"]["lesion"], parts["Periventricular"]["slice"]) == (main["id"], _slice_of(main))
    small = parts["Juxtacortical"]
    assert small["small_component"] is True and small["lesion"] is None
    assert (small["voxels"], small["slice"]) == (2, 6)
    assert not any(les["voxel_count"] == 2 for les in table)        # the table leaves it out


@pytest.mark.unit
def test_rc071_m1_the_refused_confirmation_names_lesions_as_the_table_does(client_for):
    m = np.zeros((D, H, W), dtype=np.uint8)
    m[1:3, 1:3, 1:3] = 4
    m[5:7, 10:13, 10:13] = 1
    svc = _service()
    entry = _seed(svc, mask=m)
    _classify(entry, voxel_volume_mm3=1.0)
    painted = m.copy()
    painted[6, 12, 11:13] = 2
    entry["masks_3d"] = painted
    client = client_for(svc)
    app.dependency_overrides[container.get_storage_service] = lambda: _Storage1mm()
    main = next(les for les in _table(client) if les["voxel_count"] == 16)
    r = _confirm(client, _sha(painted))
    assert r.status_code == 409, r.text[:300]
    message = r.json()["error"]["message"]
    assert f"lesion {main['id']} (slice {_slice_of(main) + 1}): Periventricular" in message
    assert "small component (2 voxels, slice 7): Juxtacortical" in message


@pytest.mark.unit
def test_rc070_m1_classify_regions_records_the_voxel_volume(client_for, monkeypatch):
    """The lesion-size floor of the table needs the voxel volume: classify-regions records it with the lesions."""
    import app.api.routes.segmentation_regions as regions_route

    m = np.zeros((D, H, W), dtype=np.uint8)
    m[1:3, 1:3, 1:3] = 1
    m[5:7, 10:14, 10:14] = 2
    svc = _service()
    entry = _seed(svc, mask=(m > 0).astype(np.uint8))
    monkeypatch.setattr(svc, "list_segmentations", lambda file_id=None, file_ids=None: [], raising=False)
    monkeypatch.setattr(regions_route, "prepare_geometric_image", lambda affine, native, shape: np.ones(shape, np.uint8))
    monkeypatch.setattr(regions_route, "classify_lesions_geometric", lambda mask, image, spacing: {
        "classified_mask": m, "method": "geometric", "total_classified": 40, "processing_time_ms": 1,
        "lesions": [], "classification_summary": {}})
    client = client_for(svc)
    assert client.post("/api/v1/segmentation/seg-1/classify-regions", json={"method": "geometric"}).status_code == 200
    assert entry["metadata"].analysis_data["classification"]["voxel_volume_mm3"] == 3.0
    assert _dis(client)["regions"]["classified"] is True
