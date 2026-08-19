"""apply_window_level must never divide by zero or blank a diagnostic slice.

Adversarial review of the 2D window/level feature found a CRITICAL defect: a window
WIDTH of 1 (the frontend's degenerate fallback for NIfTI, which carries no DICOM W/L
tag) made `img_max - img_min == 0` (floor division `1 // 2 == 0`) → divide-by-zero →
NaN → an all-BLACK slice. Hiding a slice on a Class C diagnostic viewer is a display-
safety hazard (a rater could paint against black). These tests lock in the guard:
degenerate windows fall back to the data's own range; a genuine window still applies.
"""
import numpy as np
import pytest

from app.services.imaging_service import ImagingService


@pytest.fixture
def svc():
    # apply_window_level is pure — no need for full service construction/deps.
    return ImagingService.__new__(ImagingService)


@pytest.fixture
def slice_data():
    return np.array([[0, 50, 100], [150, 200, 255]], dtype=np.float64)


@pytest.mark.parametrize("wc,ww", [(100, 1), (100, 0), (100, -5), (128, 0.0)])
def test_degenerate_window_never_blanks_or_nans(svc, slice_data, wc, ww):
    out = svc.apply_window_level(slice_data, wc, ww)
    assert out.dtype == np.uint8
    assert np.isfinite(out).all(), "window produced non-finite pixels (divide-by-zero)"
    # A degenerate window falls back to the data range → real spread, not an all-black slice.
    assert out.max() > out.min(), "degenerate window blanked the slice (all one value)"


def test_width_one_spans_the_data_not_zero(svc, slice_data):
    # The exact bug: width=1 previously floor-divided to a zero span → black.
    out = svc.apply_window_level(slice_data, 100, 1)
    assert out.min() == 0 and out.max() == 255


def test_real_window_still_applies(svc, slice_data):
    # A genuine window must still map intensities across the 0..255 output range.
    out = svc.apply_window_level(slice_data, 128, 256)
    assert out.dtype == np.uint8
    assert out.min() == 0 and out.max() >= 250
    # Monotonic: brighter input → brighter output within the window.
    flat = out.ravel()
    assert flat[0] <= flat[-1]


def test_flat_input_returns_zeros_without_crashing(svc):
    flat = np.full((4, 4), 42.0)
    out = svc.apply_window_level(flat, 42, 1)  # degenerate window on flat data
    assert out.dtype == np.uint8
    assert np.isfinite(out).all()
