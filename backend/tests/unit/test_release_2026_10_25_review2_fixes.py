"""Release 2026-10-25 — second independent review of PR #69 (6d1fde2..dd22708), backend side.

Written BEFORE the corrections (they fail on ebf39c3):
- M1: the F09 disclosure is served with the server's DIS state of the segmentation itself (regions state), only while
  the classification record describes the current lesions; the viewer no longer reads it from whichever segmentation
  is open.
- M2: a second classification of the same lesions (the "before" mask is the previously classified one) carries the
  earlier removal forward instead of overwriting it with 0; a newly saved mask starts again.
- m7: F09 with anisotropic voxels (3 x 0.5 x 0.4 mm).
- n1: a lesion table that fails for another reason than the image geometry says so (not "geometry").
- m4: the AI assistant passes a DIS block on only when it is evaluated AND carries a yes/no conclusion.

Nothing reaches a store or a cloud service (PRB-002).
"""
import nibabel as nib
import numpy as np
import pytest

from app.core import container
from app.main import app
from tests.unit.test_prb003_dis_requires_confirmed_segmentation import (  # noqa: F401  (fixtures)
    D, H, W, _mask, _seed, _service, client_for, ms_server,
)
from tests.unit.test_release_2026_10_25_capture_fixes import _mask_with_specks


class _StorageZooms:
    def __init__(self, zooms):
        self.zooms = zooms

    async def download_file(self, bucket, file_id):
        img = nib.Nifti1Image(np.zeros((H, W, D), dtype=np.uint8), np.eye(4))
        img.header.set_zooms(self.zooms)
        return img.to_bytes()


@pytest.fixture
def classify(client_for, monkeypatch):
    import app.api.routes.segmentation_regions as regions_route
    monkeypatch.setattr(regions_route, "prepare_geometric_image", lambda affine, native, shape: np.ones(shape, np.uint8))
    state = {}

    def make(mask, zooms=(1.0, 1.0, 1.0)):
        svc = _service()
        entry = _seed(svc, mask=mask)
        monkeypatch.setattr(svc, "list_segmentations", lambda file_id=None, file_ids=None: [], raising=False)
        client = client_for(svc)
        app.dependency_overrides[container.get_storage_service] = lambda: _StorageZooms(zooms)
        state.update(svc=svc, entry=entry, client=client)

        def run():
            r = client.post("/api/v1/segmentation/seg-1/classify-regions", json={"method": "geometric"})
            assert r.status_code == 200, r.text[:400]
            return r.json()
        return run, entry, client

    return make


# ─────────────────────────────────────────────── M1: the disclosure comes with the server's DIS state
@pytest.mark.unit
def test_rc070_release2_m1_the_dis_state_carries_the_removal_for_these_lesions_only(classify):
    run, entry, client = classify(_mask_with_specks())
    body = run()
    dis = client.get("/api/v1/segmentation/seg-1/dis-assessment").json()
    assert dis["evaluation_status"] == "not_evaluated"
    assert dis["regions"]["removed_small_components"] == body["removed_small_components"]
    assert dis["regions"]["removed_small_components"]["components"] == 2
    # the lesions change (a saved new mask): the record no longer describes them — no disclosure with that mask
    entry["masks_3d"] = entry["masks_3d"].copy()
    entry["masks_3d"][5, 10, 10] = 1
    dis = client.get("/api/v1/segmentation/seg-1/dis-assessment").json()
    assert not (dis.get("regions") or {}).get("removed_small_components")


# ─────────────────────────────────────────────── M2: a second classification keeps the earlier removal
@pytest.mark.unit
def test_rc070_release2_m2_a_second_classification_carries_the_earlier_removal_forward(classify):
    run, entry, _client = classify(_mask_with_specks())
    first = run()["removed_small_components"]
    assert first["components"] == 2
    second = run()["removed_small_components"]          # the "before" mask is now the classified one: nothing new
    assert (second["components"], second["voxels"]) == (2, first["voxels"])
    assert second["volume_mm3"] == pytest.approx(first["volume_mm3"])
    assert entry["metadata"].analysis_data["classification"]["removed_small_components"]["components"] == 2


@pytest.mark.unit
def test_rc070_release2_m2_a_newly_saved_mask_starts_again(classify):
    run, entry, _client = classify(_mask_with_specks())
    assert run()["removed_small_components"]["components"] == 2
    # the user saves a different mask (another lesion footprint): its classification states only its own removal
    new = (entry["masks_3d"] > 0).astype(np.uint8)
    new[0, 19, 0] = 1                                    # one new one-voxel speck
    entry["masks_3d"] = new
    third = run()["removed_small_components"]
    assert third["components"] == 1


# ─────────────────────────────────────────────── m7: anisotropic voxels
@pytest.mark.unit
def test_rc070_release2_m7_removed_volume_uses_the_anisotropic_voxel_volume(classify):
    run, _entry, _client = classify(_mask_with_specks(), zooms=(0.4, 0.5, 3.0))   # spacing 3.0 x 0.5 x 0.4 mm
    removed = run()["removed_small_components"]
    assert removed["components"] == 2 and removed["voxels"] == 2
    assert removed["volume_mm3"] == pytest.approx(2 * 3.0 * 0.5 * 0.4)


# ─────────────────────────────────────────────── n1: the real reason of a lesion-table failure
@pytest.mark.unit
async def test_rc070_release2_n1_a_lesion_table_failure_names_its_real_reason(monkeypatch):
    from fastapi import HTTPException
    import app.api.routes.ai_report as ai_report
    import app.api.routes.segmentation_analysis as analysis
    from app.utils import VoxelSpacingUnavailableError

    monkeypatch.setattr(ai_report, "_dis_services", lambda: (object(), object()))

    async def boom(*a, **k):
        raise RuntimeError("mask buffer truncated")

    monkeypatch.setattr(analysis, "lesion_table", boom)
    with pytest.raises(HTTPException) as other:
        await ai_report.server_lesion_table("seg-1")
    assert other.value.status_code == 422
    assert not other.value.detail.startswith(ai_report.GEOMETRY_UNREADABLE_PHRASE)
    assert other.value.detail.startswith(ai_report.LESION_TABLE_FAILED_PHRASE)
    assert "nothing was sent" in other.value.detail.lower()

    async def geometry(*a, **k):
        raise VoxelSpacingUnavailableError("segmentation seg-1: could not read voxel geometry")

    monkeypatch.setattr(analysis, "lesion_table", geometry)
    with pytest.raises(HTTPException) as geo:
        await ai_report.server_lesion_table("seg-1")
    assert geo.value.detail.startswith(ai_report.GEOMETRY_UNREADABLE_PHRASE)


# ─────────────────────────────────────────────── m4: the assistant applies the whole rule
@pytest.mark.unit
def test_rc070_release2_m4_the_assistant_needs_a_yes_no_conclusion_too(ms_server):
    only_evaluated_dis = ms_server.only_evaluated_dis       # the real module, fastmcp stubbed (not installed here)
    without = only_evaluated_dis({"evaluation_status": "evaluated", "regions_with_lesions": 2})
    assert without["evaluation_status"] == "not_evaluated" and "regions_with_lesions" not in without
    with_conclusion = only_evaluated_dis({"evaluation_status": "evaluated", "dis_met": True})
    assert with_conclusion["evaluation_status"] == "evaluated" and with_conclusion["dis_met"] is True
