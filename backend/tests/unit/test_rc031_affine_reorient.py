"""RC-031 step 2 primitive — affine-based reorientation with WORLD-coordinate proof.

Risk control for HAZ-006 (mirrored / mis-oriented overlay). test_rc031_
parcellation_load_order.py proved the parcellation branch serves (k,j,i) while
the display uses (k,i,j), and that a FIXED (0,2,1) swap fixes exactly that one
orientation. `reorient_array_to_reference` generalises the fix: it aligns by the
AFFINES, so it is correct for ANY source orientation — the property five prior
fixed-transpose attempts lacked.

The decisive check here is PHYSICAL, not dimensional: after reorientation, the
value at reference voxel r must be the source value whose WORLD coordinate is
reference_affine @ r. Shape-matching is necessary but not sufficient (that is
the whole square-slice lesson). Every consistent (source_affine, source_data)
pair below is generated with nibabel's own inverse orientation transform, so the
test asserts our primitive INVERTS a known scramble exactly.
"""
import numpy as np
import pytest
from nibabel.orientations import (
    apply_orientation,
    inv_ornt_aff,
)

from app.utils.nifti_utils import reorient_array_to_reference


# Anisotropic reference grid so any missed flip/permutation is detectable, with
# a non-trivial translation so world coordinates are not symmetric about 0.
REF_AFFINE = np.array([
    [2.0, 0.0, 0.0, -10.0],
    [0.0, 3.0, 0.0,  20.0],
    [0.0, 0.0, 4.0,  -5.0],
    [0.0, 0.0, 0.0,   1.0],
])
SHAPE = (3, 4, 5)  # asymmetric on every axis


def _ref_volume():
    return np.arange(np.prod(SHAPE), dtype=np.int32).reshape(SHAPE)


def _scramble_pair(ornt, ref_data):
    """Build a (source_data, source_affine) pair that is ref_data viewed in the
    voxel order described by `ornt` — using nibabel's own inverse so the pair is
    physically consistent with REF_AFFINE by construction."""
    source_data = apply_orientation(ref_data, ornt)
    source_affine = REF_AFFINE @ inv_ornt_aff(ornt, ref_data.shape)
    return source_data, source_affine


# ornt rows = [source axis feeding this output axis, flip(+1/-1)].
SCRAMBLES = {
    "identity":        np.array([[0, 1], [1, 1], [2, 1]]),
    "in_plane_swap":   np.array([[0, 1], [2, 1], [1, 1]]),   # the RC-031 (k,j,i) case
    "flip_axis0":      np.array([[0, -1], [1, 1], [2, 1]]),
    "swap_and_flip":   np.array([[2, 1], [0, -1], [1, 1]]),
    "full_reverse":    np.array([[2, -1], [1, -1], [0, -1]]),
}


class TestRecoversReferenceExactly:
    @pytest.mark.parametrize("name", list(SCRAMBLES))
    def test_reorient_inverts_any_scramble(self, name):
        ref_data = _ref_volume()
        source_data, source_affine = _scramble_pair(SCRAMBLES[name], ref_data)
        out = reorient_array_to_reference(source_data, source_affine, REF_AFFINE)
        assert out.shape == ref_data.shape
        assert np.array_equal(out, ref_data), (
            f"reorient must recover the reference grid exactly for '{name}'"
        )


class TestWorldCoordinatePreserved:
    """The physical guarantee: a marker's world coordinate is identical whether
    read in the source grid (source_affine) or the reoriented grid (REF_AFFINE)."""

    @pytest.mark.parametrize("name", list(SCRAMBLES))
    def test_marker_world_coordinate_is_invariant(self, name):
        # Seed a unique marker in the REFERENCE grid (index always valid), then
        # view it in the source grid — locating it by VALUE, so no assumption is
        # made about the scrambled source shape.
        marker = 999
        ref_data = _ref_volume()
        ref_data[1, 2, 3] = marker
        source_data, source_affine = _scramble_pair(SCRAMBLES[name], ref_data)

        src_idx = tuple(int(v) for v in np.argwhere(source_data == marker)[0])
        world_source = source_affine @ np.array([*src_idx, 1.0])

        out = reorient_array_to_reference(source_data, source_affine, REF_AFFINE)
        out_idx = tuple(int(v) for v in np.argwhere(out == marker)[0])
        world_ref = REF_AFFINE @ np.array([*out_idx, 1.0])

        np.testing.assert_allclose(world_source, world_ref, atol=1e-9, err_msg=(
            f"world coordinate moved under reorientation for '{name}' — the "
            "overlay would be mis-located"
        ))


class TestReproducesFixedTransposeForRC031Case:
    """For the SPECIFIC (k,j,i)->(k,i,j) case, the affine method must reproduce
    the (0,2,1) swap that test_rc031_parcellation_load_order.py hard-proved —
    without hardcoding it. This ties the general primitive to the pinned bug."""

    def test_in_plane_swap_matches_transpose_021(self):
        ref_data = _ref_volume()
        source_data, source_affine = _scramble_pair(SCRAMBLES["in_plane_swap"], ref_data)
        out = reorient_array_to_reference(source_data, source_affine, REF_AFFINE)
        assert np.array_equal(out, np.transpose(source_data, (0, 2, 1))), (
            "for the RC-031 in-plane-swap orientation the affine method must "
            "agree with the (0,2,1) compensation proven in step 1.5"
        )


class TestIdentityAndInverse:
    def test_same_affine_is_a_noop(self):
        data = _ref_volume()
        out = reorient_array_to_reference(data, REF_AFFINE, REF_AFFINE)
        assert np.array_equal(out, data)

    def test_reorient_is_reversible(self):
        ref_data = _ref_volume()
        source_data, source_affine = _scramble_pair(SCRAMBLES["swap_and_flip"], ref_data)
        to_ref = reorient_array_to_reference(source_data, source_affine, REF_AFFINE)
        back = reorient_array_to_reference(to_ref, REF_AFFINE, source_affine)
        assert np.array_equal(back, source_data)


class TestFailsClosed:
    def test_singular_source_affine_raises(self):
        data = _ref_volume()
        singular = REF_AFFINE.copy()
        singular[:3, :3] = 0.0  # zero direction block — no orientation
        with pytest.raises(ValueError, match="singular or non-finite"):
            reorient_array_to_reference(data, singular, REF_AFFINE)

    def test_nonfinite_reference_affine_raises(self):
        data = _ref_volume()
        bad = REF_AFFINE.copy()
        bad[0, 0] = np.nan
        with pytest.raises(ValueError, match="singular or non-finite"):
            reorient_array_to_reference(data, REF_AFFINE, bad)

    def test_requires_3d(self):
        with pytest.raises(ValueError, match=">=3D"):
            reorient_array_to_reference(np.zeros((4, 4)), REF_AFFINE, REF_AFFINE)
