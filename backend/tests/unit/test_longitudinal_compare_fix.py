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


def test_counts_are_spacing_independent():
    """Counts (the safety-relevant part) do not depend on voxel spacing — so the (1,1,1)
    fallback used when source spacing is unavailable keeps counts correct (only mL differs)."""
    a = _lesion(np.zeros((8, 16, 16), np.uint8), 3, 4, 4)
    b = _lesion(np.zeros((8, 16, 16), np.uint8), 5, 10, 10)
    r1 = compare_timepoints((a > 0).astype(np.uint8), (b > 0).astype(np.uint8), voxel_spacing=(1.0, 1.0, 1.0))
    r2 = compare_timepoints((a > 0).astype(np.uint8), (b > 0).astype(np.uint8), voxel_spacing=(3.0, 0.5, 0.5))
    assert r1["status_counts"] == r2["status_counts"]
