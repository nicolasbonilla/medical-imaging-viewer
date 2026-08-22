"""FLAIR subtraction confirmation of new-lesion candidates (advisory).

On the co-registered intensities, a genuine new lesion is BRIGHTER at follow-up, so
its subtraction signal is strongly positive; a mask-only artifact (segmentation
false positive where the FLAIR is unchanged) shows ~0 signal. These tests pin that
discriminative behavior and the Class C invariant (subtraction NEVER certifies a
candidate — registration_verified stays False).
"""
import base64

import numpy as np

from app.services.registration_service import registered_change_candidates
from app.services.longitudinal_subtraction import (
    normalize_intensity, subtraction_map, confirm_new_candidates,
    quantize_subtraction, encode_subtraction_volume, SUB_CLIP_SD,
)

SPACING = (1.0, 1.0, 1.0)


def _brain_phantom(shape=(64, 64, 64)) -> np.ndarray:
    from scipy.ndimage import gaussian_filter
    z, y, x = np.ogrid[:shape[0], :shape[1], :shape[2]]
    cz, cy, cx = (shape[0] / 2, shape[1] / 2, shape[2] / 2)
    ell = ((z - cz) / 26) ** 2 + ((y - cy) / 22) ** 2 + ((x - cx) / 22) ** 2
    vol = np.where(ell <= 1.0, 100.0, 0.0)
    for dz, dy, dx in ((-8, 0, 0), (8, 0, 0)):
        v = ((z - (cz + dz)) / 5) ** 2 + ((y - cy) / 4) ** 2 + ((x - cx) / 4) ** 2
        vol[v <= 1.0] = 20.0
    return gaussian_filter(vol.astype(np.float32), sigma=1.0)


def _sphere(shape, c, r=4):
    z, y, x = np.ogrid[:shape[0], :shape[1], :shape[2]]
    return ((z - c[0]) ** 2 + (y - c[1]) ** 2 + (x - c[2]) ** 2) <= r * r


def test_normalize_and_subtraction_basic():
    a = _brain_phantom()
    b = a.copy()
    c = (32, 32, 24)
    b[_sphere(a.shape, c, 4)] = 300.0            # a bright new hyperintensity in b
    sub = subtraction_map(a, b)
    assert sub is not None
    # the bright region is strongly positive in (b − a); background ~0
    assert sub[_sphere(a.shape, c, 3)].mean() > 1.0
    assert abs(float(np.median(sub))) < 0.5
    # degenerate input normalizes to None (no contrast)
    assert normalize_intensity(np.zeros((32, 32, 32), np.float32)) is None


def test_quantize_and_encode_subtraction_volume():
    """Diverging-heatmap quantization: 0→128, +clip→255, −clip→0, outside-domain→128;
    and base64 round-trips to the original uint8 volume + shape."""
    shp = (4, 5, 6)
    sub = np.zeros(shp, np.float32)
    sub[0] = SUB_CLIP_SD           # +clip → 255
    sub[1] = -SUB_CLIP_SD          # −clip → 0
    sub[2] = 0.0                   # zero → 128
    domain = np.ones(shp, np.uint8)
    domain[3] = 0                  # outside domain → forced neutral 128

    u8 = quantize_subtraction(sub, domain)
    assert u8[0].min() == 255 and u8[1].max() == 0
    assert (u8[2] == 128).all()
    assert (u8[3] == 128).all()    # neutral outside the domain regardless of value

    b64, out_shape, clip = encode_subtraction_volume(sub, domain)
    assert out_shape == list(shp) and clip == SUB_CLIP_SD
    decoded = np.frombuffer(base64.b64decode(b64), dtype=np.uint8).reshape(out_shape)
    assert np.array_equal(decoded, u8)

    # Size guard: a volume above the cap omits the inline heatmap (returns None b64).
    b64_big, _, _ = encode_subtraction_volume(np.zeros(shp, np.float32), max_voxels=10)
    assert b64_big is None


def test_bright_new_lesion_is_subtraction_confirmed():
    shp = (64, 64, 64)
    c = (32, 32, 24)
    tp1_img = _brain_phantom()
    tp2_img = _brain_phantom()
    tp2_img[_sphere(shp, c, 4)] = 300.0          # new lesion is genuinely bright at TP2
    tp1_mask = np.zeros(shp, np.uint8)           # nothing at baseline
    tp2_mask = _sphere(shp, c, 4).astype(np.uint8)

    res = registered_change_candidates(tp1_img, tp2_img, tp1_mask, tp2_mask, SPACING)

    assert res["registration_verified"] is False   # invariant
    assert res["status_counts"]["new"] == 1
    assert res["subtraction_available"] is True
    assert res["subtraction_summary"]["new_subtraction_confirmed"] == 1
    new_change = next(c for c in res["changes"] if c["status"] == "new")
    assert new_change["subtraction_confirmed"] is True
    assert new_change["subtraction_signal"] > 0.5
    # The inline heatmap volume ships with the response (fixed/TP1 grid).
    assert "subtraction_volume_b64" in res
    assert res["subtraction_shape"] == list(tp1_img.shape)
    decoded = np.frombuffer(base64.b64decode(res["subtraction_volume_b64"]), dtype=np.uint8)
    assert decoded.size == int(np.prod(tp1_img.shape))


def test_border_candidate_is_withheld_not_confirmed():
    """Adversarial Finding 1: a NEW candidate whose component touches the brain/FOV
    boundary must be WITHHELD (subtraction_confirmed=None, note='border'), even when
    the intensity delta there is large — that edge is exactly where a linear-resample
    rim falsely 'confirms' a misregistration phantom."""
    shp = (64, 64, 64)
    edge = (32, 32, 52)                           # near the +x brain boundary (r≈22 @ center 32)
    tp1_img = _brain_phantom()
    tp2_img = _brain_phantom()
    tp2_img[_sphere(shp, edge, 4)] = 300.0        # strong (would-confirm) signal at the edge
    tp1_mask = np.zeros(shp, np.uint8)
    tp2_mask = _sphere(shp, edge, 4).astype(np.uint8)

    res = registered_change_candidates(tp1_img, tp2_img, tp1_mask, tp2_mask, SPACING)

    assert res["status_counts"]["new"] == 1
    assert res["subtraction_available"] is True
    new_change = next(c for c in res["changes"] if c["status"] == "new")
    assert new_change["subtraction_confirmed"] is None        # withheld, not a false True
    assert new_change.get("subtraction_note") == "border"
    assert res["subtraction_summary"]["new_withheld"] >= 1
    assert res["subtraction_summary"]["new_subtraction_confirmed"] == 0


def test_mask_only_artifact_is_not_confirmed():
    """A 'new' candidate whose FLAIR is UNCHANGED (identical intensity at both
    timepoints) is not subtraction-confirmed — the false-positive filter."""
    shp = (64, 64, 64)
    c = (32, 32, 24)
    img = _brain_phantom()                        # SAME intensities at both timepoints
    tp1_mask = np.zeros(shp, np.uint8)
    tp2_mask = _sphere(shp, c, 4).astype(np.uint8)  # mask says new, but intensity unchanged

    res = registered_change_candidates(img, img.copy(), tp1_mask, tp2_mask, SPACING)

    assert res["status_counts"]["new"] == 1
    assert res["subtraction_available"] is True
    new_change = next(c for c in res["changes"] if c["status"] == "new")
    assert new_change["subtraction_confirmed"] is False
    assert res["subtraction_summary"]["new_subtraction_confirmed"] == 0
