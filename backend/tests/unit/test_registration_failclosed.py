"""Longitudinal registration service — recovery sanity + FAIL-CLOSED matrix + deformable ban.

The QC gate is the load-bearing safety piece (adversarial refute, workflow w3p81u3kz): the
FAIL path must fire on every degenerate input, and PASS is only ever advisory here
(registration_verified is never true in shadow mode). Deformable registration is banned by
a static assertion — a warp would erase real lesion change (HAZ-LONG-2).
"""
import os

import numpy as np
import pytest

from app.services import registration_service as rs
from app.services.registration_service import register_timepoints, RegistrationResult

SPACING = (1.0, 1.0, 1.0)


def _brain_phantom(shape=(64, 64, 64), shift=(0, 0, 0)) -> np.ndarray:
    """A smooth bright ellipsoid (brain) with two dark internal spheres (ventricles) so
    mutual information has real features to align. `shift` translates it by whole voxels."""
    from scipy.ndimage import gaussian_filter
    z, y, x = np.ogrid[:shape[0], :shape[1], :shape[2]]
    cz, cy, cx = (shape[0] / 2 + shift[0], shape[1] / 2 + shift[1], shape[2] / 2 + shift[2])
    ell = ((z - cz) / 26) ** 2 + ((y - cy) / 22) ** 2 + ((x - cx) / 22) ** 2
    vol = np.where(ell <= 1.0, 100.0, 0.0)
    for dz, dy, dx in ((-8, 0, 0), (8, 0, 0)):
        v = ((z - (cz + dz)) / 5) ** 2 + ((y - cy) / 4) ** 2 + ((x - cx) / 4) ** 2
        vol[v <= 1.0] = 20.0
    return gaussian_filter(vol.astype(np.float32), sigma=1.0)


def test_recovery_on_a_known_translation():
    """Register a translated copy back onto the original: it must converge, register_ok,
    and the resampled brain overlap must be high. (Runs real SimpleITK.)"""
    fixed = _brain_phantom()
    moving = _brain_phantom(shift=(0, 0, 3))          # TP2 = TP1 shifted 3 voxels in x
    mask = (moving > 50).astype(np.uint8)             # lesion-mask stand-in

    res = register_timepoints(fixed, moving, mask, SPACING)

    assert isinstance(res, RegistrationResult)
    assert res.registration_verified is False          # NEVER true in shadow mode
    assert res.registration_ok is True, res.reason
    assert res.resampled_moving_mask is not None
    assert res.resampled_moving_mask.shape == fixed.shape
    # brain overlap after alignment should be strong (advisory readout only)
    assert res.advisory_qc["brain_overlap_dice"] > 0.85, res.advisory_qc


def test_failclosed_non_finite():
    fixed = _brain_phantom()
    moving = _brain_phantom()
    moving[0, 0, 0] = np.nan
    res = register_timepoints(fixed, moving, (moving > 50).astype(np.uint8), SPACING)
    assert res.registration_ok is False and res.registration_verified is False
    assert "non-finite" in res.reason


def test_failclosed_non_3d():
    res = register_timepoints(np.zeros((10, 10)), np.zeros((10, 10)), np.zeros((10, 10)), (1.0, 1.0))
    assert res.registration_ok is False and res.registration_verified is False


def test_failclosed_degenerate_brain_mask():
    """A volume whose bright region is below the brain-voxel floor must fail closed rather
    than register against noise."""
    fixed = np.zeros((64, 64, 64), dtype=np.float32)
    fixed[30:33, 30:33, 30:33] = 100.0   # 27 bright voxels << _MIN_BRAIN_VOXELS
    moving = fixed.copy()
    res = register_timepoints(fixed, moving, (moving > 50).astype(np.uint8), SPACING)
    assert res.registration_ok is False and res.registration_verified is False
    assert "degenerate" in res.reason or "brain mask" in res.reason


def test_registration_verified_is_never_true_in_the_dict():
    """The response contract must never carry registration_verified=true from this module."""
    fixed = _brain_phantom()
    res = register_timepoints(fixed, _brain_phantom(shift=(0, 0, 2)), (fixed > 50).astype(np.uint8), SPACING)
    assert res.as_dict()["registration_verified"] is False


def _lesion(shape, c, r=4):
    z, y, x = np.ogrid[:shape[0], :shape[1], :shape[2]]
    return (((z - c[0]) ** 2 + (y - c[1]) ** 2 + (x - c[2]) ** 2) <= r * r).astype(np.uint8)


def test_registered_change_candidates_contract_and_value():
    """SHADOW register-then-compare: registration_verified must be False (invariant), the
    comparison runs on the CO-REGISTERED mask, and a lesion that merely SHIFTED between
    timepoints is matched as stable (registration removes the misregistration phantom) —
    not reported as new+resolved."""
    from app.services.registration_service import registered_change_candidates
    shift = (0, 0, 3)
    tp1_img = _brain_phantom()
    tp2_img = _brain_phantom(shift=shift)
    shp = tp1_img.shape
    c = (shp[0] // 2, shp[1] // 2, shp[2] // 2 - 8)
    tp1_mask = _lesion(shp, c)
    tp2_mask = _lesion(shp, (c[0] + shift[0], c[1] + shift[1], c[2] + shift[2]))

    res = registered_change_candidates(tp1_img, tp2_img, tp1_mask, tp2_mask, (1.0, 1.0, 1.0))

    assert res["registration_verified"] is False          # INVARIANT — never true in shadow
    assert res["registration_applied"] is True
    assert "status_counts" in res and "registration_advisory_qc" in res
    # the shifted lesion re-aligns -> matched/stable, no phantom new/resolved
    assert res["status_counts"]["new"] == 0 and res["status_counts"]["resolved"] == 0


def test_no_deformable_registration_symbol_present():
    """HAZ-LONG-2: deformable registration is BANNED (a warp erases real lesion change).
    Statically assert the service imports/uses no deformable transform or filter."""
    src = open(rs.__file__, encoding="utf-8").read()
    banned = ["BSpline", "Demons", "DisplacementField", "BSplineTransform",
              "FastSymmetricForces", "DiffeomorphicDemons"]
    present = [b for b in banned if b in src]
    assert not present, f"deformable symbol(s) present in registration_service: {present}"
