"""Longitudinal compare — the 500 fix + candidate-framing safety contract.

Adversarial design/refute of the TP1/TP2 feature found: (1) the /longitudinal/compare
route called compare_timepoints WITHOUT its required `voxel_spacing` arg → TypeError →
500 for every request (a dead endpoint); (2) the "obvious" arg-only fix would have turned
it into a LIVE false-new-lesion path, because equal array shape is NOT spatial registration
(two sessions of one patient share dimensions but are not voxel-aligned), and those raw
counts fed dissemination-in-time report language. These tests lock in the contract:
compare_timepoints requires spacing, and counts are candidate-framed (registration
unverified) — verified by the route, but the pure engine's spacing requirement is the
regression anchor here.
"""
import inspect

import numpy as np
import pytest

from app.services.longitudinal_tracking_service import compare_timepoints


def _lesion(vol, z, y, x, size=3):
    vol[z, y:y + size, x:x + size] = 1
    return vol


def test_compare_timepoints_requires_voxel_spacing():
    """The exact bug: voxel_spacing is a required positional arg with no default.
    A 2-arg call (what the route did) must fail — documenting why the route 500'd."""
    sig = inspect.signature(compare_timepoints)
    ws = sig.parameters["voxel_spacing"]
    assert ws.default is inspect.Parameter.empty, "voxel_spacing must stay required (route passes it)"
    a = np.zeros((6, 12, 12), np.uint8)
    b = np.zeros((6, 12, 12), np.uint8)
    with pytest.raises(TypeError):
        compare_timepoints(a, b)  # the pre-fix call — must raise, not silently pass


def test_compare_timepoints_three_arg_call_detects_new_lesion():
    """The fix: called with spacing, it works and reports a genuine new lesion."""
    a = _lesion(np.zeros((8, 16, 16), np.uint8), 3, 4, 4)
    b = _lesion(np.zeros((8, 16, 16), np.uint8), 3, 4, 4)  # same lesion persists
    b = _lesion(b, 5, 10, 10)                               # + a NEW lesion at TP2
    r = compare_timepoints((a > 0).astype(np.uint8), (b > 0).astype(np.uint8), voxel_spacing=(1.0, 1.0, 1.0))
    assert r["status_counts"]["new"] >= 1
    assert r["status_counts"]["stable"] >= 1


def test_suprafloor_counts_are_spacing_independent():
    """ABOVE the 3 mm³ noise floor, counts don't depend on spacing — so the (1,1,1)
    fallback keeps supra-floor counts correct (only mL burden differs). A 9-voxel lesion
    clears the floor at every spacing tested."""
    a = _lesion(np.zeros((8, 16, 16), np.uint8), 3, 4, 4)  # 3x3 = 9 voxels
    b = _lesion(np.zeros((8, 16, 16), np.uint8), 5, 10, 10)
    r1 = compare_timepoints((a > 0).astype(np.uint8), (b > 0).astype(np.uint8), voxel_spacing=(1.0, 1.0, 1.0))
    r2 = compare_timepoints((a > 0).astype(np.uint8), (b > 0).astype(np.uint8), voxel_spacing=(3.0, 0.5, 0.5))
    assert r1["status_counts"] == r2["status_counts"]


def test_near_floor_counts_ARE_spacing_dependent():
    """Adversarial finding D3: the 3 mm³ noise floor (voxels x prod(spacing)) IS
    spacing-dependent, so the (1,1,1) fallback can RETAIN a near-floor candidate that true
    geometry would drop. Documents the real behaviour the fallback comment now admits;
    bounded by candidate framing (never a finding), but not to be claimed away."""
    a = np.zeros((8, 16, 16), np.uint8)  # TP1 empty
    b = _lesion(np.zeros((8, 16, 16), np.uint8), 4, 8, 8, size=1)  # 1 voxel at one z-slice
    # 1-voxel component; add two neighbours in-plane to make a 3-voxel component.
    b[4, 8, 9] = 1
    b[4, 9, 8] = 1  # 3 voxels total
    fallback = compare_timepoints(a, (b > 0).astype(np.uint8), voxel_spacing=(1.0, 1.0, 1.0))
    real = compare_timepoints(a, (b > 0).astype(np.uint8), voxel_spacing=(1.0, 0.5, 0.5))  # 3x0.25=0.75mm³
    assert fallback["status_counts"]["new"] >= real["status_counts"]["new"]
    # true geometry drops the sub-floor candidate; the fallback keeps it → they differ
    assert fallback["status_counts"]["new"] != real["status_counts"]["new"]
