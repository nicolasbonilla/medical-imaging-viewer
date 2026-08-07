"""RC-031 — marker-driven realignment of a served segmentation NIfTI (HAZ-006).

The ref_file_id serve path used a greedy `sorted(seg_shape)==sorted(ref_shape)`
permutation to realign a stored mask to the reference MRI. That guess cannot
detect an in-plane swap on SQUARE (a0==a1) data — the shapes are identical — so
legacy masks were served MIRRORED there. `_seg_native_to_reference_order` uses
the v2 header marker instead: v2 masks are already MRI-native; legacy masks are
the (1,0,2) in-plane transpose. Deterministic, square or not.
"""
import numpy as np

from app.services.segmentation_service import SegmentationService as S


A0, A1, K = 5, 8, 3


def test_v2_is_identity():
    seg = np.arange(A0 * A1 * K, dtype=np.uint8).reshape(A0, A1, K)  # MRI-native
    assert np.array_equal(S._seg_native_to_reference_order(seg, oriented_v2=True), seg)


def test_legacy_in_plane_swap_recovers_reference_order():
    ref_native = np.zeros((A0, A1, K), dtype=np.uint8)
    ref_native[1, 6, 0] = 7
    legacy = np.transpose(ref_native, (1, 0, 2))          # how legacy stored it: (a1,a0,k)
    out = S._seg_native_to_reference_order(legacy, oriented_v2=False)
    assert out.shape == (A0, A1, K)
    assert np.array_equal(out, ref_native), "legacy mask must be reoriented to reference order"


def test_legacy_square_slice_is_corrected_where_permutation_could_not():
    # Square in-plane: legacy and reference share a shape, so the old greedy
    # permutation left it unchanged (mirrored). The marker-driven path fixes it.
    n = 6
    ref_native = np.zeros((n, n, K), dtype=np.uint8)
    ref_native[1, 4, 0] = 7                               # asymmetric position within the square
    legacy = np.transpose(ref_native, (1, 0, 2))          # in-plane swapped, SAME shape
    assert legacy.shape == ref_native.shape               # square: indistinguishable by dims
    assert not np.array_equal(legacy, ref_native)         # but the data IS transposed
    out = S._seg_native_to_reference_order(legacy, oriented_v2=False)
    assert np.array_equal(out, ref_native), "legacy square overlay must be un-mirrored"
