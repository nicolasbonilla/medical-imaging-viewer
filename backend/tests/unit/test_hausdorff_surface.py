"""HD95 must be a SURFACE-to-surface distance (MSSEG-2 / Anima / MONAI standard).

The prior implementation took distances over every foreground voxel, so interior
overlap (distance 0) diluted the distribution and biased HD95 low. These tests
pin the surface semantics against known analytical values and show the metric no
longer conflates volume overlap with boundary distance.
"""
import numpy as np
import pytest

from app.services.segmentation_comparison_service import compute_hausdorff

SP = (1.0, 1.0, 1.0)


def _solid(shape, sl):
    m = np.zeros(shape, dtype=np.uint8)
    m[sl] = 1
    return m


def test_identical_masks_zero():
    a = _solid((20, 20, 20), np.s_[3:17, 3:17, 3:17])
    assert compute_hausdorff(a, a.copy(), SP) == 0.0


def test_single_voxel_offset_is_exact_distance():
    a = np.zeros((10, 10, 10), np.uint8); a[2, 2, 2] = 1
    b = np.zeros((10, 10, 10), np.uint8); b[2, 2, 5] = 1  # 3 voxels apart along x
    assert compute_hausdorff(a, b, SP) == pytest.approx(3.0)


def test_anisotropic_spacing_is_respected():
    a = np.zeros((10, 10, 10), np.uint8); a[2, 0, 0] = 1
    b = np.zeros((10, 10, 10), np.uint8); b[4, 0, 0] = 1  # 2 voxels apart along axis0
    # spacing dz=3 -> physical distance = 2 * 3 = 6 mm
    assert compute_hausdorff(a, b, (3.0, 1.0, 1.0)) == pytest.approx(6.0)


def test_measures_boundary_gap_when_one_contains_the_other():
    # B strictly inside A with a 3-voxel gap between their surfaces on every side.
    a = _solid((30, 30, 30), np.s_[0:30, 0:30, 0:30])
    b = _solid((30, 30, 30), np.s_[3:27, 3:27, 3:27])
    hd = compute_hausdorff(a, b, SP)
    # Surfaces are 3 mm apart perpendicular, up to 3*sqrt(3)≈5.2 mm at the corners;
    # the 95th percentile lands on the edge diagonals (3*sqrt(2)≈4.24). The point:
    # it reflects the real boundary disagreement, not 0 — a full-VOLUME metric's
    # directed B->A term would be 0 here because B is inside A, hiding the gap.
    assert 3.0 <= hd <= 5.2, hd


def test_offset_solids_report_the_surface_shift():
    a = _solid((30, 20, 20), np.s_[0:20, 0:20, 0:20])
    b = _solid((30, 20, 20), np.s_[4:24, 0:20, 0:20])  # shifted +4 along axis0
    hd = compute_hausdorff(a, b, SP)
    assert hd == pytest.approx(4.0, abs=1.0), hd


def test_surface_not_diluted_by_interior_overlap():
    # A solid cube vs the SAME cube's hollow shell: their SURFACES coincide, so
    # HD95 must be ~0 — even though a full-volume distance would be large (the
    # solid cube's centre is far from the shell). This isolates the bug fixed.
    from scipy.ndimage import binary_erosion, generate_binary_structure
    a = _solid((20, 20, 20), np.s_[2:18, 2:18, 2:18])
    shell = a & ~binary_erosion(a, structure=generate_binary_structure(3, 1), border_value=1)
    hd = compute_hausdorff(a, shell.astype(np.uint8), SP)
    assert hd <= 1.0, f"surfaces coincide -> HD95 must be ~0, got {hd}"


def test_empty_conventions():
    z = np.zeros((5, 5, 5), np.uint8)
    a = z.copy(); a[2, 2, 2] = 1
    assert compute_hausdorff(z, z, SP) == 0.0
    assert compute_hausdorff(a, z, SP) == float("inf")
