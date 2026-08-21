"""MAGNIMS clinical candidate rules + mutual-best lesion matching (increment C).

Pins:
  * mutual-best matching is conservative + order-independent (it matches the
    highest-IoU reciprocal pair, not whatever a greedy pass reaches first);
  * the ≥3 mm-diameter new-lesion size gate (clinically_significant);
  * the MAGNIMS candidate signals: dit_candidate (≥1 significant new) and
    activity_candidate (≥2 new/enlarging). These are CANDIDATES, never findings.
"""
import numpy as np

from app.services.longitudinal_tracking_service import (
    compare_timepoints, _match_components, _sphere_volume_mm3, NEW_LESION_MIN_DIAMETER_MM,
)

SPACING = (1.0, 1.0, 1.0)


def _comp(cid, coords):
    """A synthetic component dict for _match_components (id + voxel indices)."""
    return {"id": cid, "mask_indices": np.array(coords, dtype=int)}


def test_mutual_best_matches_highest_iou_pair_regardless_of_order():
    """Two TP1 lesions overlap one TP2 lesion; L1 overlaps more. Mutual-best matches
    L1↔M (the reciprocal best) and reports L2 resolved — even when L2 is listed first
    (the order that would trip a greedy first-come matcher)."""
    L1 = _comp(1, [(0, 0, x) for x in range(10)])          # 10 voxels
    L2 = _comp(2, [(0, 1, x) for x in range(10)])          # 10 voxels
    M = _comp(9, [(0, 0, x) for x in range(6)] +           # 6 shared with L1
                 [(0, 1, x) for x in range(5)])            # 5 shared with L2  (11 total)
    # IoU(L1,M)=6/15=0.40 ; IoU(L2,M)=5/16≈0.31 -> M's reciprocal best is L1
    matched, resolved, new = _match_components([L2, L1], [M], iou_threshold=0.3)

    assert len(matched) == 1
    assert matched[0][0]["id"] == 1                        # L1 matched (higher IoU), not L2
    assert {c["id"] for c in resolved} == {2}              # L2 resolved
    assert new == []


def _mask_with_blobs(shape, blobs):
    """blobs: list of (cz,cy,cx,radius). Returns a uint8 mask."""
    m = np.zeros(shape, np.uint8)
    zz, yy, xx = np.ogrid[:shape[0], :shape[1], :shape[2]]
    for cz, cy, cx, r in blobs:
        m[((zz - cz) ** 2 + (yy - cy) ** 2 + (xx - cx) ** 2) <= r * r] = 1
    return m


def test_new_lesion_size_gate_and_dit_candidate():
    shp = (32, 32, 32)
    tp1 = np.zeros(shp, np.uint8)
    big = _sphere_volume_mm3(NEW_LESION_MIN_DIAMETER_MM)   # ≈14.14 mm³ threshold
    # one clearly-suprathreshold new lesion (r=2 ≈ 33 voxels) far from the others
    tp2 = _mask_with_blobs(shp, [(8, 8, 8, 2)])
    res = compare_timepoints(tp1, tp2, voxel_spacing=SPACING)
    new_change = next(c for c in res["changes"] if c["status"] == "new")
    assert new_change["volume_tp2_mm3"] >= big
    assert new_change["clinically_significant"] is True
    assert res["new_clinically_significant_count"] == 1
    assert res["dit_candidate"] is True
    assert res["activity_candidate"] is False              # only one → not "active"


def test_subthreshold_new_lesion_is_not_a_dit_candidate():
    shp = (32, 32, 32)
    tp1 = np.zeros(shp, np.uint8)
    # a tiny 4-voxel new lesion: above the 3 mm³ noise floor but below 3 mm diameter
    tp2 = np.zeros(shp, np.uint8)
    tp2[8, 8, 8:12] = 1                                    # 4 voxels ≈ 4 mm³ < 14.14
    res = compare_timepoints(tp1, tp2, voxel_spacing=SPACING)
    new_change = next(c for c in res["changes"] if c["status"] == "new")
    assert new_change["clinically_significant"] is False
    assert res["new_clinically_significant_count"] == 0
    assert res["dit_candidate"] is False


def test_activity_candidate_needs_two_new_or_enlarging():
    shp = (48, 48, 48)
    tp1 = np.zeros(shp, np.uint8)
    # two well-separated suprathreshold new lesions → ≥2 → active candidate
    tp2 = _mask_with_blobs(shp, [(10, 10, 10, 2), (30, 30, 30, 2)])
    res = compare_timepoints(tp1, tp2, voxel_spacing=SPACING)
    assert res["new_clinically_significant_count"] == 2
    assert res["activity_candidate"] is True
    assert res["dit_candidate"] is True
