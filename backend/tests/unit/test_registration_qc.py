"""Lesion-scale registration QC gate — fail-closed matrix + lesion-scale sensitivity.

The gate must PASS only on a clean, well-spread, >=3-stable-fiducial pair, and REJECT
every degenerate/undefined case + a hazard-scale residual (which whole-brain Dice misses).
A PASS is necessary-not-sufficient and never authorizes the flip.
"""
import numpy as np

from app.services.registration_qc_service import lesion_scale_qc, LesionScaleQC

SP = (1.0, 1.0, 1.0)


def _spheres(shape, centers, radius=5):
    """Binary mask with solid spheres (each ~4/3*pi*r^3 mm3 at 1mm spacing; r=5 -> ~523mm3
    >= the 250mm3 fiducial floor)."""
    m = np.zeros(shape, dtype=np.uint8)
    zz, yy, xx = np.ogrid[:shape[0], :shape[1], :shape[2]]
    for cz, cy, cx in centers:
        m[((zz - cz) ** 2 + (yy - cy) ** 2 + (xx - cx) ** 2) <= radius ** 2] = 1
    return m


# Well-spread centers (pairwise span > 50 mm) for the coverage guard.
_SPREAD = [(25, 25, 25), (25, 30, 95), (85, 90, 60)]
_SHAPE = (110, 120, 120)


def test_pass_on_clean_wellspread_pair():
    m1 = _spheres(_SHAPE, _SPREAD)
    res = lesion_scale_qc(m1, m1.copy(), SP)      # perfectly aligned
    assert isinstance(res, LesionScaleQC)
    assert res.qc_pass is True, res.reason
    assert res.n_fiducials >= 3
    assert res.r_disp_mm is not None and res.r_disp_mm < 1.0
    assert res.coverage_span_mm > 50.0
    assert res.as_dict()["is_flip_authorization"] is False


def test_catches_a_3mm_translation():
    """A 3 mm residual that whole-brain Dice would rubber-stamp must REJECT here."""
    m1 = _spheres(_SHAPE, _SPREAD)
    m2r = _spheres(_SHAPE, [(cz, cy, cx + 3) for cz, cy, cx in _SPREAD])  # shifted 3 vox
    res = lesion_scale_qc(m1, m2r, SP)
    assert res.qc_pass is False
    assert res.r_disp_mm is not None and res.r_disp_mm > 1.0


def test_reject_fewer_than_three_fiducials():
    m1 = _spheres(_SHAPE, _SPREAD[:2])
    res = lesion_scale_qc(m1, m1.copy(), SP)
    assert res.qc_pass is False and "fiducial" in res.reason


def test_reject_no_lesions():
    empty = np.zeros(_SHAPE, dtype=np.uint8)
    res = lesion_scale_qc(empty, _spheres(_SHAPE, _SPREAD), SP)
    assert res.qc_pass is False and "no lesions" in res.reason


def test_reject_centrally_clustered_fiducials():
    """Coverage guard: 3 large lesions all near the centre (span < 50 mm) cannot observe
    the rotational lever arm -> REJECT even at zero residual."""
    central = [(45, 55, 55), (45, 55, 69), (60, 55, 62)]   # separate but central (span ~16mm)
    m1 = _spheres(_SHAPE, central)
    res = lesion_scale_qc(m1, m1.copy(), SP)
    assert res.qc_pass is False and "clustered" in res.reason


def test_reject_only_small_lesions():
    """Only sub-250mm3 specks -> 0 fiducials -> cannot certify the lesion scale."""
    m1 = _spheres(_SHAPE, _SPREAD, radius=2)   # r=2 -> ~33mm3 << 250
    res = lesion_scale_qc(m1, m1.copy(), SP)
    assert res.qc_pass is False


def test_reject_shape_mismatch():
    res = lesion_scale_qc(np.zeros((10, 10, 10), np.uint8), np.zeros((10, 10, 11), np.uint8), SP)
    assert res.qc_pass is False and "shape" in res.reason


def test_jitter_floor_raises_the_cut():
    """A measured jitter floor widens the pass cut (but only upward from 1.0 mm)."""
    m1 = _spheres(_SHAPE, _SPREAD)
    # small sub-cut residual (1 voxel on one lesion) should pass with a generous floor
    res = lesion_scale_qc(m1, m1.copy(), SP, jitter_floor_mm=2.0)
    assert res.cut_mm == 2.25
