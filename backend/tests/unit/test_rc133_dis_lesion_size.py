"""RC-133 (REQ-FUNC-121, HAZ-008; SRS/RMF Addendum E, DRAFT — PENDING owner approval): a lesion counts toward brain
DIS only when its largest extent is at least 3 mm (MAGNIMS 2021; paper 1's clinically faithful rule), in addition to
the 3 mm³ noise floor. The largest extent is paper 1's: the maximum distance between the centres of any two voxels."""
import itertools

import numpy as np
import pytest

from app.services.lesion_analysis_service import (
    DIS_LESION_MIN_EXTENT_MM,
    compute_dis_criteria,
    largest_extent_at_least,
)


def _brute(idx, spacing, thr=3.0):
    pts = np.asarray(idx, float) * np.asarray(spacing, float)
    return any(np.linalg.norm(a - b) >= thr - 1e-6 for a, b in itertools.combinations(pts, 2))


# ------------------------------------------------------------------ the largest extent itself
def test_threshold_is_three_mm():
    assert DIS_LESION_MIN_EXTENT_MM == 3.0


def test_single_voxel_has_no_extent():
    assert largest_extent_at_least(np.array([[4, 4, 4]]), (5.0, 5.0, 5.0)) is False


def test_four_voxels_in_a_row_at_1mm_reach_3mm_three_do_not():
    assert largest_extent_at_least(np.array([[0, 0, x] for x in range(4)]), (1.0, 1.0, 1.0)) is True
    assert largest_extent_at_least(np.array([[0, 0, x] for x in range(3)]), (1.0, 1.0, 1.0)) is False


def test_spacing_of_each_axis_is_used():
    two_in_z = np.array([[0, 0, 0], [1, 0, 0]])
    assert largest_extent_at_least(two_in_z, (5.0, 0.9, 0.9)) is True        # thick slices: 5 mm apart
    two_in_x = np.array([[0, 0, 0], [0, 0, 1]])
    assert largest_extent_at_least(two_in_x, (5.0, 0.9, 0.9)) is False       # 0.9 mm in plane


def test_diagonal_pair_is_measured_exactly():
    # bounding-box extent 2 mm per axis: no axis reaches 3 mm, the diagonal pair is 3.46 mm apart
    assert largest_extent_at_least(np.array([[0, 0, 0], [2, 2, 2]]), (1.0, 1.0, 1.0)) is True
    # same bounding box (diagonal 3.46 mm) but no PAIR reaches 3 mm: every pair is 2.83 mm apart
    assert largest_extent_at_least(np.array([[0, 0, 2], [2, 0, 0], [0, 2, 0]]), (1.0, 1.0, 1.0)) is False


@pytest.mark.parametrize("seed", range(40))
def test_agrees_with_brute_force_on_random_sets(seed):
    rng = np.random.default_rng(seed)
    n = int(rng.integers(1, 9))
    idx = rng.integers(0, 4, size=(n, 3))
    spacing = tuple(float(x) for x in rng.choice([0.5, 0.9, 1.0, 1.2, 3.0, 5.0], size=3))
    assert largest_extent_at_least(idx, spacing) is _brute(idx, spacing)


# ------------------------------------------------------------------ the DIS rule
def _mask():
    return np.zeros((10, 20, 20), np.uint8)


def test_small_periventricular_component_no_longer_completes_dis():
    m = _mask()
    m[5, 5, 5:8] = 1          # PV: 3 voxels in a row at 1 mm = 3 mm³ (above the floor) but 2 mm long
    m[5, 12, 5:10] = 2        # JC: 5 voxels in a row = 4 mm long
    r = compute_dis_criteria(m, voxel_spacing=(1.0, 1.0, 1.0))
    pv, jc = r["region_details"]["Periventricular"], r["region_details"]["Juxtacortical"]
    assert pv["present"] is False and pv["qualifying_lesion_count"] == 0 and pv["below_size_lesion_count"] == 1
    assert jc["present"] is True and jc["qualifying_lesion_count"] == 1 and jc["below_size_lesion_count"] == 0
    assert r["brain_regions_with_lesions"] == 1
    assert r["dis_met_brain"] is False and r["dis_met"] is False
    assert r["below_size_lesion_count"] == 1


def test_lesion_of_three_mm_counts():
    m = _mask()
    m[5, 5, 5:9] = 1          # 4 voxels: 3 mm between the outer centres
    m[5, 12, 5:9] = 2
    r = compute_dis_criteria(m, voxel_spacing=(1.0, 1.0, 1.0))
    assert r["dis_met_brain"] is True and r["brain_regions_with_lesions"] == 2
    assert r["below_size_lesion_count"] == 0


def test_thick_slice_lesion_counts_by_its_extent_across_slices():
    m = _mask()
    m[4:6, 5, 5] = 1          # 2 voxels across slices 3 mm apart: 3 mm long, volume 2 x 3 x 0.9 x 0.9 = 4.9 mm³
    m[4:6, 12, 5] = 3
    r = compute_dis_criteria(m, voxel_spacing=(3.0, 0.9, 0.9))
    assert r["region_details"]["Periventricular"]["present"] is True
    assert r["region_details"]["Infratentorial"]["present"] is True
    assert r["dis_met_brain"] is True


def test_volume_floor_still_applies():
    m = _mask()
    m[5, 5, 5] = 1
    m[5, 5, 9] = 1            # two separate single voxels: each under 3 mm³ at 0.5 mm, and no extent
    m[5, 12, 5:12] = 2
    r = compute_dis_criteria(m, voxel_spacing=(0.5, 0.5, 0.5))
    pv = r["region_details"]["Periventricular"]
    assert pv["present"] is False and pv["below_size_lesion_count"] == 2


def test_size_rule_is_stated_in_the_result():
    r = compute_dis_criteria(_mask(), voxel_spacing=(1.0, 1.0, 1.0))
    rule = r["lesion_size_rule"]
    assert rule["min_largest_extent_mm"] == 3.0 and rule["min_volume_mm3"] == 3.0
    assert "MAGNIMS 2021" in rule["source"]
    assert r["below_size_lesion_count"] == 0
