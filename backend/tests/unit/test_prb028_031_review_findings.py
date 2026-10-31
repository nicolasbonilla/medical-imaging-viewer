"""Independent review of PR #74 (290e407) — the server-side findings m4, m7 and m9.

- m4: after a confirmation that covered geometric-fallback regions, re-running the classification with the atlas on the
  same mask gave "not evaluated: geometric_regions_not_reviewed" on an atlas classification. The geometric binding is
  compared only while there ARE geometric-fallback lesions.
- m7: a viewer tab opened before the deployment sends only the mask digest; the AI-draft route answered with the
  label-table message ("another label preset… reopen"). A request that states neither the drawn label table nor the
  image under the mask now gets one clear answer: this viewer is out of date, reload it.
- m9: the image-grid check downloaded two whole images on every confirmation to read a header of a few hundred bytes.
  It now reads a byte range (`download_file_range`, a ranged GCS read) and grows it only while a compressed header is
  not complete; a storage without ranges still works (whole download).

Written BEFORE the correction (fail on 290e407). Nothing reaches a store or a cloud service (PRB-002).
"""
import asyncio
import gzip

import nibabel as nib
import numpy as np
import pytest

from app.core import container
from app.main import app
from app.services import dis_review_gate as gate
from tests.unit.test_prb003_dis_requires_confirmed_segmentation import (  # noqa: F401  (fixture)
    D, FILE, H, PID, STUDY, W, _classification, _dis, _drawn, _prov, _seed, _service, _sha, client_for,
)
from tests.unit.test_prb028_geometric_fallback_review import _two_lesions

OTHER = f"patients/{PID}/studies/{STUDY}/series/66666666-6666-6666-6666-666666666666/t1.nii.gz"


def _classified(svc, method):
    entry = _seed(svc, mask=_two_lesions(1, 2))
    record = _classification(entry["masks_3d"])
    record["classification"]["method"] = method
    entry["metadata"].analysis_data = record
    return entry


# ─────────────────────────────────────────────────────────────────────────────────────────────── m4
@pytest.mark.unit
def test_rc090_review_m4_an_atlas_rerun_on_the_same_mask_keeps_the_confirmation(client_for):
    svc = _service()
    entry = _classified(svc, "geometric")
    client = client_for(svc)
    digest = _dis(client)["regions"]["geometric_regions_sha256"]
    r = client.post("/api/v1/segmentation/seg-1/review/confirm", json={
        "mask_sha256": _sha(entry["masks_3d"]), "drawn_labels_sha256": _drawn(client),
        "displayed_image_file_id": FILE, "geometric_regions_reviewed_sha256": digest})
    assert r.status_code == 200, r.text[:300]
    # the classification is run again with the atlas and gives the identical mask: no geometric region any more
    entry["metadata"].analysis_data["classification"]["method"] = "msmask"
    body = _dis(client)
    assert body.get("not_evaluated_reason") != "geometric_regions_not_reviewed", body.get("reason_detail")
    assert body["evaluation_status"] == "evaluated"


@pytest.mark.unit
def test_rc090_review_m4_the_geometric_binding_still_holds_while_geometric_lesions_exist(client_for):
    """Positive control of m4's correction: a confirmation without the per-lesion review on a geometric classification
    still does not make DIS evaluable."""
    from app.models.schemas import ClinicianReview
    svc = _service()
    entry = _classified(svc, "geometric")
    entry["metadata"].clinician_review = ClinicianReview(
        reviewed_by="dr_rev", reviewed_at="2026-10-31T10:00:00Z", reviewed_mask_sha256=_sha(entry["masks_3d"]),
        reviewed_labels_sha256=gate.labels_sha256(entry["metadata"].labels),
        reviewed_region_corrections_sha256=gate.NO_CORRECTIONS_SHA256)
    assert _dis(client_for(svc))["not_evaluated_reason"] == "geometric_regions_not_reviewed"


# ─────────────────────────────────────────────────────────────────────────────────────────────── m7
@pytest.mark.unit
@pytest.mark.parametrize("route", ["ai", "dis"])
def test_rc091_review_m7_a_viewer_from_before_the_update_is_told_to_reload(client_for, route):
    svc = _service()
    entry = _seed(svc, ai_provenance=_prov()) if route == "ai" else _classified(svc, "msmask")
    path = "ai-review/confirm" if route == "ai" else "review/confirm"
    r = client_for(svc).post(f"/api/v1/segmentation/seg-1/{path}", json={"mask_sha256": _sha(entry["masks_3d"])})
    assert r.status_code == 409, r.text[:300]
    message = r.json()["error"]["message"].lower()
    assert "out of date" in message and "reload" in message
    assert "label" in message                       # the release 2026-10-25 check of a missing drawn table still holds


# ─────────────────────────────────────────────────────────────────────────────────────────────── m9
def _big_image(gz=False):
    img = nib.Nifti1Image(np.zeros((H, W, D), dtype=np.float32) + np.arange(D, dtype=np.float32), np.eye(4))
    raw = img.to_bytes() + np.random.default_rng(0).bytes(400_000)   # incompressible padding: a large file
    return gzip.compress(raw) if gz else raw


class _RangedStorage:
    """A storage that serves byte ranges; a whole download fails the test."""

    def __init__(self, gz):
        self.files = {FILE: _big_image(gz), OTHER: _big_image(gz)}
        self.ranges = []

    async def download_file(self, bucket, file_id):
        raise AssertionError(f"whole image downloaded: {file_id}")

    async def download_file_range(self, bucket, file_id, start, end):
        self.ranges.append((file_id, start, end))
        return self.files[file_id][start:end + 1]


@pytest.mark.unit
@pytest.mark.parametrize("gz", [False, True])
def test_rc092_review_m9_only_the_header_of_the_image_under_the_mask_is_read(client_for, gz):
    svc = _service()
    entry = _seed(svc, ai_provenance=_prov())
    client = client_for(svc)
    storage = _RangedStorage(gz)
    app.dependency_overrides[container.get_storage_service] = lambda: storage
    r = client.post("/api/v1/segmentation/seg-1/ai-review/confirm", json={
        "mask_sha256": _sha(entry["masks_3d"]), "drawn_labels_sha256": _drawn(client), "displayed_image_file_id": OTHER})
    assert r.status_code == 200, r.text[:300]
    read = sum(end - start + 1 for _f, start, end in storage.ranges)
    assert {f for f, _s, _e in storage.ranges} == {FILE, OTHER}
    assert read <= 2 * 65536 < len(storage.files[OTHER]), storage.ranges


@pytest.mark.unit
def test_rc092_review_m9_the_gcs_storage_reads_a_byte_range():
    from app.services.storage_service import GCSStorageService

    calls = []

    class _Blob:
        def download_as_bytes(self, start=None, end=None):
            calls.append((start, end))
            return b"x" * (end - start + 1)

    class _Bucket:
        def blob(self, name):
            calls.append(name)
            return _Blob()

    class _Client:
        def bucket(self, name):
            return _Bucket()

    svc = object.__new__(GCSStorageService)
    svc._get_client = lambda: _Client()
    loop = asyncio.new_event_loop()        # never asyncio.run: it would leave no current loop for later tests
    try:
        data = loop.run_until_complete(svc.download_file_range("bucket", "patients/x.nii.gz", 0, 1023))
    finally:
        loop.close()
    assert len(data) == 1024
    assert calls == ["patients/x.nii.gz", (0, 1023)]
