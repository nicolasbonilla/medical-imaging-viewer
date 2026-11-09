"""Part C thick-section simulation (PREREG-mimics-thickness.md section 5): fixed parameters, slab means,
background kept at zero, grid checks, verbatim operator.

    python -m pytest research/paper_1/tests/test_simulate_thick.py -q
"""
import hashlib
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "mimics"))
import simulate_thick as st  # noqa: E402


def test_operator_is_the_verbatim_flames_thick_copy():
    data = open(os.path.join(HERE, "..", "mimics", "thick_slice.py"), "rb").read().replace(b"\r\n", b"\n")
    blob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
    assert blob == st.THICK_SLICE_BLOB


def test_parameters_are_the_registered_ones():
    assert st.THICKNESSES_MM == (3.0, 5.0, 7.0)
    assert st.PRIMARY == {"axis": 2, "gap_mm": 0.0, "phase_mm": 0.0, "profile": "box", "mode": "linear"}
    with pytest.raises(ValueError):
        st.simulate_array(np.ones((4, 4, 20)), 4.0)


@pytest.mark.parametrize("t", [3.0, 5.0, 7.0])
def test_slice_centres_hold_the_slab_mean(t):
    """Box, no gap, phase 0: slice s is centred on voxel s*T and equals the mean of the T voxels it covers."""
    rng = np.random.RandomState(0)
    z = 70
    x = rng.uniform(1.0, 2.0, size=(3, 3, z)).astype(np.float32)          # no zeros: no background reset
    out = st.simulate_array(x, t)
    k = int(t)
    for s in range(1, z // k - 1):
        c = s * k
        lo, hi = c - (k - 1) // 2, c + (k - 1) // 2 + 1
        assert np.allclose(out[..., c], x[..., lo:hi].mean(-1), atol=1e-5)


@pytest.mark.parametrize("t", [3.0, 5.0, 7.0])
def test_constant_brain_is_unchanged_and_background_stays_zero(t):
    x = np.zeros((6, 6, 60), np.float32)
    x[1:5, 1:5, 10:50] = 2.5
    out = st.simulate_array(x, t)
    assert out.shape == x.shape and out.dtype == np.float32
    assert np.all(out[x == 0] == 0)
    assert np.allclose(out[2:4, 2:4, 20:40], 2.5, atol=1e-5)


def test_thin_lesion_is_diluted_more_by_thicker_sections():
    x = np.ones((3, 3, 63), np.float32)
    x[1, 1, 31] = 11.0                                                      # one bright 1-mm voxel
    peaks = [st.simulate_array(x, t)[1, 1].max() for t in (3.0, 5.0, 7.0)]
    assert peaks[0] > peaks[1] > peaks[2] > 1.0
    assert np.isclose(st.simulate_array(x, 7.0)[1, 1].sum(), x[1, 1].sum(), rtol=0.05)


def test_grid_check():
    st.check_grid(np.diag([-1.0, 1.0, 1.0, 1.0]), (1.0, 1.0, 1.0))
    with pytest.raises(ValueError):
        st.check_grid(np.diag([-1.0, 1.0, 3.0, 1.0]), (1.0, 1.0, 3.0))          # not 1 mm along the axis
    perm = np.array([[0, 0, 1, 0], [0, 1, 0, 0], [1, 0, 0, 0], [0, 0, 0, 1]], float)
    with pytest.raises(ValueError):
        st.check_grid(perm, (1.0, 1.0, 1.0))                                   # voxel axis 2 is L-R here
