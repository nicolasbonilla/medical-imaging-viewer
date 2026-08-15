"""ASSD (average symmetric surface distance) — the MSSEG-2/Anima mean-boundary
metric that complements HD95's worst-case. Pinned against analytical geometry.
"""
import numpy as np
import pytest

from app.services.segmentation_comparison_service import compute_assd, compute_hausdorff

SP = (1.0, 1.0, 1.0)


def _solid(shape, sl):
    m = np.zeros(shape, dtype=np.uint8)
    m[sl] = 1
    return m


def test_identical_is_zero():
    a = _solid((20, 20, 20), np.s_[3:17, 3:17, 3:17])
    assert compute_assd(a, a.copy(), SP) == 0.0


def test_single_voxel_offset_is_exact():
    a = np.zeros((10, 10, 10), np.uint8); a[2, 2, 2] = 1
    b = np.zeros((10, 10, 10), np.uint8); b[2, 2, 5] = 1  # 3 apart
    assert compute_assd(a, b, SP) == pytest.approx(3.0)


def test_is_symmetric():
    a = _solid((30, 30, 30), np.s_[0:30, 0:30, 0:30])
    b = _solid((30, 30, 30), np.s_[3:27, 3:27, 3:27])
    assert compute_assd(a, b, SP) == pytest.approx(compute_assd(b, a, SP))


def test_assd_le_hd95():
    # The mean surface distance can never exceed the 95th percentile.
    a = _solid((30, 30, 30), np.s_[0:30, 0:30, 0:30])
    b = _solid((30, 30, 30), np.s_[3:27, 3:27, 3:27])
    assd = compute_assd(a, b, SP)
    hd95 = compute_hausdorff(a, b, SP)
    assert 0.0 < assd <= hd95, (assd, hd95)


def test_anisotropic_spacing_respected():
    a = np.zeros((10, 10, 10), np.uint8); a[2, 0, 0] = 1
    b = np.zeros((10, 10, 10), np.uint8); b[4, 0, 0] = 1  # 2 apart along axis0
    assert compute_assd(a, b, (3.0, 1.0, 1.0)) == pytest.approx(6.0)


def test_empty_conventions():
    z = np.zeros((5, 5, 5), np.uint8)
    a = z.copy(); a[2, 2, 2] = 1
    assert compute_assd(z, z, SP) == 0.0
    assert compute_assd(a, z, SP) == float("inf")
