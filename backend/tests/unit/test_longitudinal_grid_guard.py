"""Audit A-3: longitudinal comparison must not silently transpose masks onto a
mismatched voxel grid.

Both timepoints are loaded in the same canonical internal order (RC-031 for
segmentations, the (2,0,1) transpose for instances / A-1). The old route
transposed TP2 to whatever axis permutation made the dimension SIZES line up.
That is unsafe:
  - matching sizes != matching anatomical axes, and
  - when two dims are equal (square in-plane) the permutation is AMBIGUOUS and was
    chosen arbitrarily -> a silently mis-aligned longitudinal result.

_require_comparable_grid now demands identical shapes and fails loud otherwise.
"""
import pytest
from fastapi import HTTPException

from app.api.routes.segmentation_analysis import _require_comparable_grid


def test_identical_shapes_pass():
    # No exception == comparable.
    _require_comparable_grid((20, 256, 256), (20, 256, 256))


def test_square_permutation_is_rejected_not_guessed():
    # THE A-3 bug: square in-plane (256==256) made the old greedy permutation
    # ambiguous; a (a0,a1,k)-vs-(k,a0,a1) style swap must now be refused.
    with pytest.raises(HTTPException) as ei:
        _require_comparable_grid((256, 256, 20), (20, 256, 256))
    assert ei.value.status_code == 400
    assert "axis order" in ei.value.detail
    assert "registration" in ei.value.detail.lower()


def test_distinct_dim_permutation_is_rejected():
    # Even with all-distinct dims, size-matching != anatomical correspondence.
    with pytest.raises(HTTPException) as ei:
        _require_comparable_grid((180, 256, 224), (224, 180, 256))
    assert ei.value.status_code == 400
    assert "axis order" in ei.value.detail


def test_different_grids_rejected_with_registration_hint():
    with pytest.raises(HTTPException) as ei:
        _require_comparable_grid((20, 256, 256), (24, 512, 512))
    assert ei.value.status_code == 400
    assert "different voxel grids" in ei.value.detail
    assert "registered" in ei.value.detail.lower()


def test_tuple_vs_tuple_equality_is_order_sensitive():
    # Same multiset but different order is NOT equal -> rejected (order matters).
    with pytest.raises(HTTPException):
        _require_comparable_grid((10, 20, 30), (30, 20, 10))
