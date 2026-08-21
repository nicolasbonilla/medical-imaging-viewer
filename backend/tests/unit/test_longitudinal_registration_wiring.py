"""Longitudinal registration WIRING (keystone harmonization).

The live /segmentation/longitudinal/compare route now co-registers TP2→TP1 (rigid,
fail-closed) when both source FLAIR intensities are available, instead of comparing
index-aligned masks. These tests pin the VALUE and the SAFETY of that wiring at the
service level (the route branch itself is thin glue over these functions):

  * CONTRAST: a lesion that only MOVED between sessions (pure head-pose shift, no real
    disease change) is reported as a FALSE new+resolved pair by the index-aligned
    comparison, but as matched/stable once registration re-aligns it — the exact
    misregistration false-positive the candidate firewall warns about.
  * FAIL-CLOSED: when registration cannot run (degenerate/uninformative intensities),
    registered_change_candidates still returns a full comparison with
    registration_applied=False (never blocks), and registration_verified stays False.
"""
import numpy as np

from app.services.longitudinal_tracking_service import compare_timepoints
from app.services.registration_service import registered_change_candidates

SPACING = (1.0, 1.0, 1.0)


def _brain_phantom(shape=(64, 64, 64), shift=(0, 0, 0)) -> np.ndarray:
    from scipy.ndimage import gaussian_filter
    z, y, x = np.ogrid[:shape[0], :shape[1], :shape[2]]
    cz, cy, cx = (shape[0] / 2 + shift[0], shape[1] / 2 + shift[1], shape[2] / 2 + shift[2])
    ell = ((z - cz) / 26) ** 2 + ((y - cy) / 22) ** 2 + ((x - cx) / 22) ** 2
    vol = np.where(ell <= 1.0, 100.0, 0.0)
    for dz, dy, dx in ((-8, 0, 0), (8, 0, 0)):
        v = ((z - (cz + dz)) / 5) ** 2 + ((y - cy) / 4) ** 2 + ((x - cx) / 4) ** 2
        vol[v <= 1.0] = 20.0
    return gaussian_filter(vol.astype(np.float32), sigma=1.0)


def _lesion(shape, c, r=4):
    z, y, x = np.ogrid[:shape[0], :shape[1], :shape[2]]
    return (((z - c[0]) ** 2 + (y - c[1]) ** 2 + (x - c[2]) ** 2) <= r * r).astype(np.uint8)


def test_index_aligned_manufactures_a_false_new_resolved_pair():
    """The PROBLEM the wiring solves: without registration, a lesion that merely shifted
    with head position is scored as one NEW lesion (at the new location) + one RESOLVED
    lesion (at the old location) — a fabricated finding from misregistration."""
    shp = (64, 64, 64)
    c = (32, 32, 24)
    shift = (0, 0, 6)  # a 6-voxel head-pose shift, no real disease change
    tp1_mask = _lesion(shp, c)
    tp2_mask = _lesion(shp, (c[0] + shift[0], c[1] + shift[1], c[2] + shift[2]))

    idx = compare_timepoints(tp1_mask, tp2_mask, voxel_spacing=SPACING)
    # index-aligned: the shifted lesion no longer overlaps itself -> false new + resolved
    assert idx["status_counts"]["new"] == 1
    assert idx["status_counts"]["resolved"] == 1


def test_registration_removes_the_false_pair():
    """The FIX: co-registering the intensities re-aligns the shifted lesion, so the same
    pair is matched/stable — no phantom new/resolved — while registration_verified stays
    False (advisory only)."""
    shp = (64, 64, 64)
    c = (32, 32, 24)
    shift = (0, 0, 6)
    tp1_img = _brain_phantom()
    tp2_img = _brain_phantom(shift=shift)
    tp1_mask = _lesion(shp, c)
    tp2_mask = _lesion(shp, (c[0] + shift[0], c[1] + shift[1], c[2] + shift[2]))

    reg = registered_change_candidates(tp1_img, tp2_img, tp1_mask, tp2_mask, SPACING)

    assert reg["registration_applied"] is True
    assert reg["registration_verified"] is False   # invariant: advisory, never certified
    assert reg["status_counts"]["new"] == 0
    assert reg["status_counts"]["resolved"] == 0


def test_fail_closed_still_returns_a_comparison():
    """When registration cannot run (uninformative/degenerate intensities below the brain
    floor), the call must NOT raise or block — it falls back to the un-registered
    comparison with registration_applied=False, registration_verified=False."""
    shp = (32, 32, 32)
    flat = np.zeros(shp, dtype=np.float32)          # no brain -> registration fails closed
    tp1_mask = _lesion(shp, (16, 16, 16))
    tp2_mask = _lesion(shp, (16, 16, 16))

    res = registered_change_candidates(flat, flat, tp1_mask, tp2_mask, SPACING)

    assert res["registration_applied"] is False
    assert res["registration_verified"] is False
    assert "status_counts" in res                   # a full comparison was still produced
