"""Thick-slice simulator: thickness, gaps, alignment, means, label safety, parameter law (PROTOCOL §5.3).

    python -m pytest research/flames_thick/tests -q
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from flames_thick import thick_slice as ts  # noqa: E402

SP = 0.9          # FLAMeS training grid along the axial patch axis (mm)


def delta_response(n, k, thickness, gap, phase, profile, mode, sp=SP):
    """Output of the operator for a unit impulse at voxel k (column k of M)."""
    m, _, _ = ts.thickening_operator(n, sp, thickness, thickness + gap, phase, profile, mode)
    return m[:, k]


# ------------------------------------------------------------------ operator structure
@pytest.mark.parametrize("profile", ["box", "gaussian"])
@pytest.mark.parametrize("mode", ["nearest", "linear"])
def test_rows_sum_to_one_constant_image_is_unchanged(profile, mode):
    for t, g, ph in [(3.0, 0.0, 0.0), (5.3, 1.7, 2.2), (8.0, 2.0, 9.9)]:
        m, w, c = ts.thickening_operator(128, SP, t, t + g, ph, profile, mode)
        assert np.allclose(w.sum(1), 1.0) and np.allclose(m.sum(1), 1.0)
        img = np.full((7, 128, 5), 3.25, np.float32)
        out = ts.thicken(img, 1, SP, t, g, ph, profile, mode)
        assert out.shape == img.shape and out.dtype == img.dtype
        assert np.allclose(out, 3.25, atol=1e-5)


def test_every_voxel_has_a_slice_within_half_spacing():
    for n in (16, 112, 160):
        for s in (3.0, 4.86, 8.3, 10.0):
            for ph in (0.0, 0.37 * s, 0.99 * s):
                c = ts.slice_centres(n, SP, s, ph)
                x = np.arange(n) * SP
                assert np.abs(x[:, None] - c[None, :]).min(1).max() <= s / 2 + 1e-9
                assert np.allclose(np.diff(c), s)


def test_box_slab_width_equals_thickness():
    """A box slice of thickness T integrates exactly T mm of tissue (sum of voxel overlaps)."""
    for t in (3.0, 4.5, 6.9, 8.0):
        a, b = ts._voxel_edges(200, SP)
        centre = 60.13
        mass = ts._profile_mass(a, b, centre, t, "box")
        assert np.isclose(mass.sum(), t)
        support = np.nonzero(mass)[0]
        assert (support.size - 2) * SP <= t <= support.size * SP


def test_gaussian_profile_fwhm():
    """Gaussian slice profile has FWHM = T (sampled on a fine grid)."""
    t = 5.0
    a, b = ts._voxel_edges(4000, 0.01)
    m = ts._profile_mass(a, b, 20.0, t, "gaussian") / 0.01
    half = m >= m.max() / 2
    assert abs(half.sum() * 0.01 - t) < 0.03


def test_impulse_response_width_matches_spacing_for_nearest():
    """An impulse inside one slab spreads into a flat plateau of about one slice spacing (nearest),
    and never further than one spacing + one voxel from its position whatever the slice phase."""
    k = 80
    for t, g in [(3.0, 0.0), (5.0, 1.5), (7.0, 0.0)]:
        s = t + g
        r = delta_response(160, k, t, g, (k * SP) % s, "box", "nearest")   # slab centred on voxel k
        nz = np.nonzero(r > 1e-9)[0]
        assert s - 2 * SP <= nz.size * SP <= s + 2 * SP
        assert np.allclose(r[nz], r[nz][0])                   # a flat plateau (staircase)
        assert np.isclose(r[nz][0], SP / t)                   # the voxel's share of the slab
        for ph in np.linspace(0, s, 9, endpoint=False):
            nz = np.nonzero(delta_response(160, k, t, g, ph, "box", "nearest") > 1e-9)[0]
            if g == 0:
                assert nz.size > 0                            # contiguous slices see every voxel
            if nz.size:                                       # (with a gap the impulse may be unseen)
                assert np.abs(nz - k).max() * SP <= s + SP


def test_gaps_are_never_seen():
    """With a box profile, tissue lying wholly in an inter-slice gap does not change the output."""
    t, g, ph = 3.0, 2.7, 0.0                                   # gap > 2 voxels
    n = 120
    w, c = ts.slab_weights(n, SP, t, t + g, ph, "box")
    seen = w.sum(0) > 0
    assert (~seen).sum() > 0
    rng = np.random.default_rng(0)
    img = rng.random((n, 6)).astype(np.float32)
    img2 = img.copy()
    img2[~seen] += 100.0
    out = ts.thicken(img, 0, SP, t, g, ph, "box", "nearest")
    out2 = ts.thicken(img2, 0, SP, t, g, ph, "box", "nearest")
    assert np.allclose(out, out2)


def test_thick_slices_change_the_image_and_reduce_detail():
    rng = np.random.default_rng(1)
    img = rng.normal(size=(40, 128, 30)).astype(np.float32)
    out = ts.thicken(img, 1, SP, 6.0, 1.0, 0.5, "box", "nearest")
    assert not np.allclose(out, img)
    assert out.std() < 0.6 * img.std()                        # averaging ~7 voxels removes noise


# ------------------------------------------------------------------ alignment (no shift)
@pytest.mark.parametrize("profile", ["box", "gaussian"])
def test_linear_ramp_is_kept_in_place_with_linear_resampling(profile):
    """Symmetric slice profiles + linear interpolation reproduce a linear ramp (no spatial shift)."""
    n = 160
    x = np.arange(n, dtype=np.float64) * SP
    for t, g, ph in [(3.0, 0.0, 0.4), (5.5, 1.2, 3.3), (8.0, 0.0, 7.1)]:
        out = ts.thicken(x[:, None].astype(np.float32), 0, SP, t, g, ph, profile, "linear")[:, 0]
        s = t + g
        interior = (x > 2 * s) & (x < x[-1] - 2 * s)
        err = np.abs(out[interior] - x[interior])
        assert err.max() <= SP / 2 + 1e-4, (profile, t, g, ph, err.max())


def test_nearest_resampling_error_bounded_by_half_spacing_and_unbiased():
    n = 160
    x = np.arange(n, dtype=np.float64) * SP
    biases = []
    for ph in np.linspace(0, 6.0, 25, endpoint=False):
        out = ts.thicken(x[:, None].astype(np.float32), 0, SP, 5.0, 1.0, ph, "box", "nearest")[:, 0]
        interior = (x > 12) & (x < x[-1] - 12)
        d = out[interior] - x[interior]
        assert np.abs(d).max() <= 3.0 + SP                      # <= S/2 (+ voxel discretisation)
        biases.append(d.mean())
    assert abs(np.mean(biases)) < 0.1 * SP                      # no systematic shift over phases


def test_centre_of_mass_of_a_small_lesion_stays_put():
    """A 3-voxel bright blob keeps its centre (averaged over slice phases) after thickening."""
    n, k = 128, 63
    img = np.zeros(n, np.float32)
    img[k - 1:k + 2] = 1.0
    coms = []
    for ph in np.linspace(0, 7.0, 35, endpoint=False):
        out = ts.thicken(img[:, None], 0, SP, 5.0, 2.0, ph, "gaussian", "linear")[:, 0]
        coms.append((out * np.arange(n)).sum() / out.sum())
    assert abs(np.mean(coms) - k) < 0.2


# ------------------------------------------------------------------ parameters
def test_sample_params_law_and_ranges():
    rng = np.random.default_rng(42)
    axis_map, spacing = {"sagittal": 0, "axial": 1, "coronal": 2}, [1.0, 0.9, 0.9]
    draws = [ts.sample_params(rng, axis_map, spacing) for _ in range(20000)]
    applied = [d for d in draws if d["apply"]]
    assert abs(len(applied) / len(draws) - 2 / 3) < 0.015
    t = np.array([d["thickness_mm"] for d in applied])
    s = np.array([d["spacing_mm"] for d in applied])
    g = np.array([d["gap_mm"] for d in applied])
    assert t.min() >= 3.0 and t.max() <= 8.0
    assert (g >= -1e-12).all() and (g <= 0.5 * t + 1e-9).all() and s.max() <= 10.0 + 1e-9
    assert abs((g > 0).mean() - 0.5) < 0.02
    names = [d["axis_name"] for d in applied]
    assert abs(names.count("axial") / len(names) - 0.8) < 0.015
    assert {d["axis"] for d in applied if d["axis_name"] == "axial"} == {1}
    assert {d["voxel_mm"] for d in applied if d["axis_name"] == "axial"} == {0.9}
    assert abs(np.mean([d["profile"] == "box" for d in applied]) - 0.5) < 0.02
    assert abs(np.mean([d["resample"] == "nearest" for d in applied]) - 0.7) < 0.02
    assert all(0 <= d["phase_mm"] < d["spacing_mm"] for d in applied)


def test_apply_params_identity_when_not_applied_and_channel_axis_handled():
    img = np.random.default_rng(3).random((1, 20, 30, 10)).astype(np.float32)
    assert ts.apply_params(img, {"apply": False}) is img
    p = {"apply": True, "axis": 1, "voxel_mm": 0.9, "thickness_mm": 5.0, "gap_mm": 0.0, "phase_mm": 0.0,
         "profile": "box", "resample": "nearest"}
    out = ts.apply_params(img, p)
    ref = ts.thicken(img[0], 1, 0.9, 5.0, 0.0, 0.0, "box", "nearest")
    assert np.allclose(out[0], ref)
    assert np.allclose(out.mean(axis=2), img.mean(axis=2), atol=0.05)   # untouched axes keep their profile


# ------------------------------------------------------------------ orientation
def test_anatomical_axes_mslesseg_las_with_flames_transpose():
    """MSLesSeg (NIfTI LAS, 1 mm) read by SimpleITK -> LPS direction diag(1, -1, 1); FLAMeS
    transpose_forward [2, 0, 1] makes patch axis 1 the superior-inferior (axial slice) axis."""
    d = (1, 0, 0, 0, -1, 0, 0, 0, 1)
    assert ts.anatomical_axes(d, [2, 0, 1]) == {"sagittal": 0, "coronal": 2, "axial": 1}
    assert ts.anatomical_axes(d, [0, 1, 2]) == {"sagittal": 2, "coronal": 1, "axial": 0}


def _rot_z(deg):
    c, s = np.cos(np.radians(deg)), np.sin(np.radians(deg))
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]]).ravel()


@pytest.mark.parametrize("deg", [45.0, 44.0, 46.0, 40.0])
def test_anatomical_axes_rejects_near_45_degree_oblique(deg):
    # Must not depend on an exact floating-point tie (cos/sin of 45 degrees differ by 1 ulp on some
    # Linux builds, which made the old argmax-only test pass silently inside the image).
    with pytest.raises(ValueError):
        ts.anatomical_axes(_rot_z(deg), [0, 1, 2])


@pytest.mark.parametrize("deg", [0.0, 15.0, 30.0])
def test_anatomical_axes_accepts_moderate_obliquity(deg):
    assert ts.anatomical_axes(_rot_z(deg), [0, 1, 2]) == ts.anatomical_axes(_rot_z(0.0), [0, 1, 2])


def test_simulate_volume_shape_and_mean():
    vol = np.random.default_rng(5).random((30, 40, 50)).astype(np.float32)
    thick, centres = ts.simulate_volume(vol, 2, 1.0, 5.0, 1.0, phase=0.0, profile="box")
    assert thick.shape[:2] == (30, 40) and thick.shape[2] == centres.size
    assert np.allclose(np.diff(centres), 6.0)
    assert abs(thick.mean() - vol.mean()) < 0.02
