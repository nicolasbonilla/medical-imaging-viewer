"""Slowly-Expanding Lesion (SEL) detection — synthetic validation (hardened).

Pins the scientific contract after adversarial review:
  * the Jacobian sign is correct in BOTH directions (grow → J>1, shrink → J<1);
  * a concentrically GROWING pre-existing lesion is an SEL candidate;
  * STABLE, SHRINKING, NOISY-STABLE, and NEW lesions are NOT SEL candidates (the
    per-subject noise-floor calibration rejects registration noise);
  * the pipeline fails closed on bad input.
"""
import numpy as np

from app.services.sel_detection_service import detect_sels, deformable_jacobian

SPACING = (1.0, 1.0, 1.0)
SHAPE = (72, 72, 72)
_LES_CENTER = (SHAPE[0] // 2 + 6, SHAPE[1] // 2, SHAPE[2] // 2)


def _brain_with_lesion(lesion_r=6.0, noise=0.0, seed=0) -> np.ndarray:
    from scipy.ndimage import gaussian_filter
    z, y, x = np.ogrid[:SHAPE[0], :SHAPE[1], :SHAPE[2]]
    cz, cy, cx = SHAPE[0] / 2, SHAPE[1] / 2, SHAPE[2] / 2
    ell = ((z - cz) / 28) ** 2 + ((y - cy) / 28) ** 2 + ((x - cx) / 28) ** 2
    vol = np.where(ell <= 1.0, 100.0, 0.0)
    lz, ly, lx = _LES_CENTER
    vol[(z - lz) ** 2 + (y - ly) ** 2 + (x - lx) ** 2 <= lesion_r ** 2] = 260.0
    vol = gaussian_filter(vol.astype(np.float32), 1.0)
    if noise > 0:
        rng = np.random.default_rng(seed)
        vol = vol + rng.normal(0, noise, SHAPE).astype(np.float32) * (vol > 5)
    return vol


def _lesion_mask(lesion_r=6.0) -> np.ndarray:
    z, y, x = np.ogrid[:SHAPE[0], :SHAPE[1], :SHAPE[2]]
    lz, ly, lx = _LES_CENTER
    return ((z - lz) ** 2 + (y - ly) ** 2 + (x - lx) ** 2 <= lesion_r ** 2).astype(np.uint8)


def _mean_jac_in(jac, mask):
    return float(jac[mask > 0].mean())


def test_jacobian_sign_both_directions():
    """Grow → mean J>1 in the lesion; shrink → mean J<1. Pins the sign convention in
    BOTH directions (a flipped/inverse-field bug would fail one of these)."""
    grow = deformable_jacobian(_brain_with_lesion(6.0), _brain_with_lesion(10.0), SPACING)
    shrink = deformable_jacobian(_brain_with_lesion(10.0), _brain_with_lesion(6.0), SPACING)
    assert grow is not None and shrink is not None
    assert _mean_jac_in(grow, _lesion_mask(8.0)) > 1.0     # expansion
    assert _mean_jac_in(shrink, _lesion_mask(8.0)) < 1.0   # contraction


def test_growing_lesion_is_sel_candidate():
    res = detect_sels(_brain_with_lesion(6.0), _brain_with_lesion(11.0),
                      _lesion_mask(6.0), _lesion_mask(11.0), SPACING)
    assert res.ok is True, res.reason
    assert res.n_existing == 1
    assert res.n_sel == 1, f"expected 1 SEL, got {res.n_sel} (frac vs floor {res.background_expanding_fraction})"
    assert res.sels[0]["expanding_fraction"] > res.background_expanding_fraction


def test_stable_lesion_is_not_sel():
    img, mask = _brain_with_lesion(7.0), _lesion_mask(7.0)
    res = detect_sels(img, img.copy(), mask, mask.copy(), SPACING)
    assert res.ok is True and res.n_existing == 1 and res.n_sel == 0


def test_noisy_stable_lesion_is_not_sel():
    """A stable lesion imaged with inter-scan NOISE must NOT be an SEL — the
    per-subject noise-floor calibration rejects registration/intensity noise (F2)."""
    tp1 = _brain_with_lesion(7.0, noise=0.0)
    tp2 = _brain_with_lesion(7.0, noise=8.0, seed=1)   # same lesion size, noisy
    mask = _lesion_mask(7.0)
    res = detect_sels(tp1, tp2, mask, mask.copy(), SPACING)
    assert res.ok is True and res.n_sel == 0, (
        f"noise-driven false SEL: frac vs bar (bg={res.background_expanding_fraction})")


def test_shrinking_lesion_is_not_sel():
    res = detect_sels(_brain_with_lesion(11.0), _brain_with_lesion(6.0),
                      _lesion_mask(11.0), _lesion_mask(6.0), SPACING)
    assert res.ok is True and res.n_sel == 0


def test_new_lesion_is_not_sel():
    res = detect_sels(_brain_with_lesion(6.0), _brain_with_lesion(6.0),
                      np.zeros(SHAPE, np.uint8), _lesion_mask(6.0), SPACING)
    assert res.ok is True and res.n_existing == 0 and res.n_sel == 0


def test_fail_closed_on_shape_mismatch():
    res = detect_sels(np.zeros((8, 8, 8), np.float32), np.zeros((8, 8, 8), np.float32),
                      np.zeros((8, 8, 8), np.uint8), np.zeros((4, 4, 4), np.uint8), SPACING)
    assert res.ok is False and res.n_sel == 0


def test_jacobian_none_on_nonfinite():
    a = _brain_with_lesion()
    b = a.copy(); b[0, 0, 0] = np.nan
    assert deformable_jacobian(a, b, SPACING) is None
