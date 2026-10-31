"""PRB-028 — regions from the geometric fallback feed DIS only after the radiologist checked them lesion by lesion.

When the MNI atlas cannot be used (the image is not on an MNI grid) the region classification falls back to the
"geometric" heuristics of `ms_region_classifier.py` (Class C; coordinate rules, not anatomical landmarks). Evidence
(film capture of 2026-10-28, MSLesSeg P51, `mstool-film/assets/app-captures-p51/data/`): on the same 45 lesions the
geometric fallback labelled 42 periventricular and agreed with the MSMask atlas on 11 of 45 (both app outputs, not
expert labels). The app only warned "accuracy not measured"; one DIS confirmation covered every region at once.

Rule (route level; the Class C classifier is not changed — as for the < 3 mm³ removals):
- the DIS state lists every lesion whose region comes from the geometric fallback and that the radiologist has not
  corrected (`regions.geometric_regions`, with their count and a digest);
- the confirmation is refused unless it states, with `geometric_regions_reviewed_sha256`, that each of those lesions
  was checked one by one (a lesion corrected by hand is a region correction, acknowledged as before, RC-071 N1);
- a confirmation recorded without that review does not make DIS evaluable on a geometric classification;
- more lesions than the DIS state can list cannot be checked one by one in the viewer: refused;
- an atlas (or parcellation) classification needs no per-lesion tick (positive control).

Written BEFORE the correction (the refusals fail on ca600c2). Nothing reaches a store or a cloud service (PRB-002).
"""
import hashlib
import json

import numpy as np
import pytest

from app.services import dis_review_gate as gate
from tests.unit.test_prb003_dis_requires_confirmed_segmentation import (  # noqa: F401  (fixture)
    D, FILE, H, MAGNIMS, W, _assert_not_evaluated, _classification, _dis, _drawn, _lesion_regions, _seed, _service,
    _sha, client_for,
)


def _two_lesions(a=1, b=2):
    m = np.zeros((D, H, W), dtype=np.uint8)
    m[2:4, 2:5, 2:5] = a        # first lesion in raster order (18 voxels)
    m[6:8, 12:15, 12:15] = b    # second lesion (18 voxels)
    return m


def _classified(method, classified=None, current=None):
    """A segmentation classified by `method` (the record classify-regions stores), mask now `current`."""
    classified = _two_lesions(1, 2) if classified is None else classified
    svc = _service()
    entry = _seed(svc, mask=classified)
    record = _classification(classified)
    record["classification"]["method"] = method
    entry["metadata"].analysis_data = record
    if current is not None:
        entry["masks_3d"] = current
    return svc, entry


def _body(client, mask, **extra):
    body = {"mask_sha256": _sha(mask), "drawn_labels_sha256": _drawn(client),
            # PRB-030: the image the standard 2D view draws under the mask (here the segmentation's own image)
            "displayed_image_file_id": FILE}
    body.update(extra)
    return body


def _confirm(client, mask, **extra):
    return client.post("/api/v1/segmentation/seg-1/review/confirm", json=_body(client, mask, **extra))


def _digest(pairs):
    """Independent digest of [[first voxel (z, y, x), region], ...] in raster order of the first voxel."""
    canonical = json.dumps([[list(fv), region] for fv, region in pairs], separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _first_voxels(mask):
    return [(list(int(v) for v in np.unravel_index(first, mask.shape)), region)
            for first, _n, region in _lesion_regions(mask)]


# ─────────────────────────────────────────────────────────────── the DIS state lists what must be checked
@pytest.mark.unit
def test_rc090_prb028_dis_state_lists_every_geometric_region_to_check_lesion_by_lesion(client_for):
    svc, _entry = _classified("geometric")
    regions = _dis(client_for(svc))["regions"]
    assert regions["method"] == "geometric"
    assert regions["geometric_fallback"] is True
    assert regions["geometric_region_count"] == 2
    listed = regions["geometric_regions"]
    assert [(r["first_voxel"], r["region"]) for r in listed] == _first_voxels(_two_lesions(1, 2))
    assert [r["region_name"] for r in listed] == ["Periventricular", "Juxtacortical"]
    assert all(isinstance(r["lesion"], int) and isinstance(r["slice"], int) for r in listed)  # named as the table
    assert regions["geometric_regions_sha256"] == _digest(_first_voxels(_two_lesions(1, 2)))


# ─────────────────────────────────────────────────────────────── the confirmation needs the per-lesion review
@pytest.mark.unit
def test_rc090_prb028_confirm_refused_while_geometric_regions_were_not_checked_one_by_one(client_for):
    svc, entry = _classified("geometric")
    client = client_for(svc)
    r = _confirm(client, entry["masks_3d"])
    assert r.status_code == 409, r.text[:300]
    assert "geometric" in r.json()["error"]["message"]
    assert entry["metadata"].clinician_review is None
    _assert_not_evaluated(_dis(client))


@pytest.mark.unit
def test_rc090_prb028_a_partial_or_foreign_review_is_refused(client_for):
    svc, entry = _classified("geometric")
    client = client_for(svc)
    only_first = _digest(_first_voxels(_two_lesions(1, 2))[:1])
    for stated in (only_first, "0" * 64, _digest([])):
        r = _confirm(client, entry["masks_3d"], geometric_regions_reviewed_sha256=stated)
        assert r.status_code == 409, (stated, r.text[:300])
    assert entry["metadata"].clinician_review is None


@pytest.mark.unit
def test_rc090_prb028_every_region_checked_one_by_one_is_accepted_recorded_and_dis_evaluated(client_for):
    svc, entry = _classified("geometric")
    client = client_for(svc)
    digest = _dis(client)["regions"]["geometric_regions_sha256"]
    r = _confirm(client, entry["masks_3d"], geometric_regions_reviewed_sha256=digest)
    assert r.status_code == 200, r.text[:300]
    review = entry["metadata"].clinician_review
    assert review.reviewed_geometric_regions_sha256 == digest
    assert review.geometric_region_count == 2
    assert [g["region"] for g in review.geometric_regions] == [1, 2]
    body = _dis(client)
    assert body["evaluation_status"] == "evaluated" and body["dis_met_brain"] is True


@pytest.mark.unit
def test_rc090_prb028_a_corrected_lesion_is_a_correction_the_rest_still_checked_one_by_one(client_for):
    """The existing region-correction mechanism: a lesion relabelled by hand is listed as a correction and
    acknowledged; only the lesions left at their geometric region need the per-lesion tick."""
    svc, entry = _classified("geometric", current=_two_lesions(4, 2))     # lesion 1: PV -> deep white matter
    client = client_for(svc)
    regions = _dis(client)["regions"]
    assert regions["correction_count"] == 1
    assert regions["geometric_region_count"] == 1
    assert [g["region"] for g in regions["geometric_regions"]] == [2]
    # the corrections alone are not enough ...
    r = _confirm(client, entry["masks_3d"], region_corrections_sha256=regions["corrections_sha256"])
    assert r.status_code == 409, r.text[:300]
    # ... with the remaining lesion checked, accepted
    r = _confirm(client, entry["masks_3d"], region_corrections_sha256=regions["corrections_sha256"],
                 geometric_regions_reviewed_sha256=regions["geometric_regions_sha256"])
    assert r.status_code == 200, r.text[:300]
    assert _dis(client)["evaluation_status"] == "evaluated"


@pytest.mark.unit
def test_rc090_prb028_a_confirmation_recorded_without_the_review_does_not_make_dis_evaluable(client_for):
    """A confirmation stored before this rule (or by another client) on a geometric classification."""
    from app.models.schemas import ClinicianReview

    svc, entry = _classified("geometric")
    mask = entry["masks_3d"]
    entry["metadata"].clinician_review = ClinicianReview(
        reviewed_by="dr_rev", reviewed_by_id="u-1", reviewed_at="2026-10-29T10:00:00Z",
        reviewed_mask_sha256=_sha(mask), reviewed_labels_sha256=gate.labels_sha256(MAGNIMS),
        reviewed_region_corrections_sha256=gate.NO_CORRECTIONS_SHA256)
    body = _dis(client_for(svc))
    _assert_not_evaluated(body)
    assert body["not_evaluated_reason"] == "geometric_regions_not_reviewed"


@pytest.mark.unit
def test_rc090_prb028_more_lesions_than_the_list_can_hold_cannot_be_checked_here(client_for, monkeypatch):
    monkeypatch.setattr(gate, "LESION_LIST_CAP", 1)
    svc, entry = _classified("geometric")
    client = client_for(svc)
    regions = _dis(client)["regions"]
    assert regions["geometric_region_count"] == 2 and len(regions["geometric_regions"]) == 1
    r = _confirm(client, entry["masks_3d"], geometric_regions_reviewed_sha256=regions["geometric_regions_sha256"])
    assert r.status_code == 409, r.text[:300]
    assert entry["metadata"].clinician_review is None


@pytest.mark.unit
@pytest.mark.parametrize("method", ["msmask", "parcellation", "lst-ai"])
def test_rc090_prb028_an_atlas_or_parcellation_classification_needs_no_per_lesion_tick(client_for, method):
    """Positive control: only the geometric fallback needs the per-lesion review."""
    svc, entry = _classified(method)
    client = client_for(svc)
    regions = _dis(client)["regions"]
    assert regions["geometric_region_count"] == 0 and regions["geometric_regions"] == []
    r = _confirm(client, entry["masks_3d"])
    assert r.status_code == 200, r.text[:300]
    assert _dis(client)["evaluation_status"] == "evaluated"
