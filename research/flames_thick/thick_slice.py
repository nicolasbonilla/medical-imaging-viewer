"""Thick-slice (2D multi-slice) acquisition simulator for FLAMeS-thick (PROTOCOL.md §5.3).

Pure numpy (no torch, no nnU-Net) so it can be unit-tested anywhere. A 2D FLAIR with slice thickness
T, gap G and slice spacing S = T + G is modelled along one axis of a thin image:

    thick_s = sum_x W[s, x] * I[x]      (slice profile integrated over each voxel, renormalised)
    out[x]  = sum_s R[x, s] * thick_s   (back onto the thin grid: nearest slice or linear)

Positions are in mm, voxel x is centred at x * sp and covers [x*sp - sp/2, x*sp + sp/2]; slice s is
centred at c_s = phase + s * S. Slices are generated so that every voxel lies within S/2 of a slice
centre. Only the image is changed; the label (the thin expert mask) is never touched.
"""
import math

import numpy as np

FWHM_TO_SIGMA = 1.0 / (2.0 * math.sqrt(2.0 * math.log(2.0)))   # 1 / 2.3548

# Pre-registered parameters (PROTOCOL.md §5.3). Changing them is a protocol deviation.
PREREGISTERED = {
    "p_apply": 2.0 / 3.0,
    "axis_probs": {"axial": 0.8, "coronal": 0.1, "sagittal": 0.1},
    "thickness_mm": (3.0, 8.0),
    "p_gap": 0.5,
    "gap_fraction": (0.0, 0.5),          # G ~ U(0, 0.5 T) when a gap is drawn
    "max_spacing_mm": 10.0,
    "profile_probs": {"box": 0.5, "gaussian": 0.5},
    "resample_probs": {"nearest": 0.7, "linear": 0.3},
}
WORLD_AXIS = {"sagittal": 0, "coronal": 1, "axial": 2}   # LPS world axis normal to the slice plane


def _voxel_edges(n_vox, sp):
    x = np.arange(n_vox, dtype=np.float64) * sp
    return x - sp / 2.0, x + sp / 2.0


def slice_centres(n_vox, sp, slice_spacing, phase):
    """Slice centres (mm) covering voxel centres 0 .. (n_vox-1)*sp: every voxel centre is within S/2."""
    first = math.floor((0.0 - phase) / slice_spacing - 0.5)
    last = math.ceil(((n_vox - 1) * sp - phase) / slice_spacing + 0.5)
    c = phase + np.arange(first, last + 1, dtype=np.float64) * slice_spacing
    lo, hi = -slice_spacing / 2.0, (n_vox - 1) * sp + slice_spacing / 2.0
    return c[(c >= lo) & (c <= hi)]


def _profile_mass(a, b, centre, thickness, profile):
    """Integral of the (unnormalised) slice profile over [a, b] (vectorised)."""
    if profile == "box":
        lo, hi = centre - thickness / 2.0, centre + thickness / 2.0
        return np.clip(np.minimum(b, hi) - np.maximum(a, lo), 0.0, None)
    if profile == "gaussian":
        s = thickness * FWHM_TO_SIGMA
        from scipy.special import erf
        k = 1.0 / (s * math.sqrt(2.0))
        return 0.5 * (erf((b - centre) * k) - erf((a - centre) * k))
    raise ValueError(f"unknown profile {profile!r}")


def slab_weights(n_vox, sp, thickness, slice_spacing, phase, profile):
    """(W, centres): W[s, x] = share of thick slice s coming from voxel x (rows sum to 1).

    Slices whose profile does not touch the field of view at all are dropped. Rows are renormalised
    over the voxels inside the patch (edge slices see only part of their slab).
    """
    if not (thickness > 0 and slice_spacing > 0 and sp > 0):
        raise ValueError("thickness, slice spacing and voxel size must be positive")
    centres = slice_centres(n_vox, sp, slice_spacing, phase)
    a, b = _voxel_edges(n_vox, sp)
    w = _profile_mass(a[None, :], b[None, :], centres[:, None], thickness, profile)
    if profile == "gaussian":
        w[w < 1e-6 * w.max(initial=0.0)] = 0.0          # truncate far tails (> ~5 sigma)
    keep = w.sum(1) > 0
    w, centres = w[keep], centres[keep]
    w = w / w.sum(1, keepdims=True)
    return w, centres


def resample_matrix(n_vox, sp, centres, mode):
    """R[x, s]: thin voxel x from thick slices. nearest = closest centre; linear = between centres."""
    x = np.arange(n_vox, dtype=np.float64) * sp
    r = np.zeros((n_vox, centres.size), dtype=np.float64)
    if centres.size == 1:
        r[:, 0] = 1.0
        return r
    if mode == "nearest":
        idx = np.abs(x[:, None] - centres[None, :]).argmin(1)
        r[np.arange(n_vox), idx] = 1.0
        return r
    if mode == "linear":
        j = np.clip(np.searchsorted(centres, x) - 1, 0, centres.size - 2)
        t = np.clip((x - centres[j]) / (centres[j + 1] - centres[j]), 0.0, 1.0)
        r[np.arange(n_vox), j] = 1.0 - t
        r[np.arange(n_vox), j + 1] = t
        return r
    raise ValueError(f"unknown resampling mode {mode!r}")


def thickening_operator(n_vox, sp, thickness, slice_spacing, phase, profile, mode):
    """M = R @ W (n_vox x n_vox): thin profile along one axis -> simulated thick -> thin grid."""
    w, centres = slab_weights(n_vox, sp, thickness, slice_spacing, phase, profile)
    return resample_matrix(n_vox, sp, centres, mode) @ w, w, centres


def apply_along_axis(arr, axis, w, r):
    """out = R @ (W @ arr) along `axis` (two small matrix products; arr float32/float64, any ndim)."""
    a = np.moveaxis(np.asarray(arr), axis, 0)
    shp = a.shape
    flat = a.reshape(shp[0], -1)
    thick = w.astype(flat.dtype, copy=False) @ flat
    out = r.astype(flat.dtype, copy=False) @ thick
    return np.moveaxis(out.reshape(shp), 0, axis)


def thicken(arr, axis, sp, thickness, gap, phase, profile, mode):
    """Simulated thick-slice image of `arr` along `axis` (voxel size `sp` mm), same shape and dtype."""
    s = thickness + gap
    w, centres = slab_weights(arr.shape[axis], sp, thickness, s, phase, profile)
    r = resample_matrix(arr.shape[axis], sp, centres, mode)
    out = apply_along_axis(np.asarray(arr, np.float32), axis, w, r)
    return out.astype(np.asarray(arr).dtype, copy=False)


def _choice(rng, probs):
    keys = list(probs)
    p = np.asarray([probs[k] for k in keys], float)
    return keys[int(rng.choice(len(keys), p=p / p.sum()))]


def sample_params(rng, axis_map, spacing_by_axis, cfg=None):
    """Draw one augmentation (dict). axis_map: {'axial': patch_axis, ...}; spacing_by_axis: mm per patch axis.

    rng: numpy Generator or RandomState (anything with .random(), .uniform(), .choice()).
    """
    cfg = PREREGISTERED if cfg is None else cfg
    if rng.random() >= cfg["p_apply"]:
        return {"apply": False}
    name = _choice(rng, cfg["axis_probs"])
    axis = int(axis_map[name])
    t = float(rng.uniform(*cfg["thickness_mm"]))
    gap = 0.0
    if rng.random() < cfg["p_gap"]:
        gap = float(rng.uniform(cfg["gap_fraction"][0] * t, cfg["gap_fraction"][1] * t))
    s = min(t + gap, cfg["max_spacing_mm"])
    gap = s - t
    return {"apply": True, "axis_name": name, "axis": axis, "voxel_mm": float(spacing_by_axis[axis]),
            "thickness_mm": t, "gap_mm": gap, "spacing_mm": s, "phase_mm": float(rng.uniform(0.0, s)),
            "profile": _choice(rng, cfg["profile_probs"]), "resample": _choice(rng, cfg["resample_probs"])}


def apply_params(img, params):
    """Apply sampled params to an image (C, X, Y, Z) or (X, Y, Z); identity if params['apply'] is False."""
    if not params.get("apply"):
        return img
    spatial_axis = params["axis"] + (1 if np.ndim(img) == 4 else 0)
    return thicken(img, spatial_axis, params["voxel_mm"], params["thickness_mm"], params["gap_mm"],
                   params["phase_mm"], params["profile"], params["resample"])


AXIS_MARGIN = 0.2


def anatomical_axes(direction, transpose_forward):
    """Map anatomical slice orientations to nnU-Net patch axes.

    direction: SimpleITK direction (9 floats, row-major; column c = world (LPS) direction of image
    index axis c, c = 0 is the fastest axis i). nnU-Net reads the array as (k, j, i) and applies
    transpose_forward, so patch axis a is image index axis 2 - transpose_forward[a].
    Returns {'sagittal': a0, 'coronal': a1, 'axial': a2} (patch axis normal to each slice plane).
    """
    d = np.asarray(direction, float).reshape(3, 3)
    tf = list(transpose_forward)
    cols = [d[:, 2 - tf[a]] for a in range(3)]                  # world direction of each patch axis
    out = {}
    for name, w in WORLD_AXIS.items():
        comp = np.array([abs(c[w]) for c in cols])
        top, second = np.sort(comp)[::-1][:2]
        # An exact-tie test is platform dependent (cos/sin of 45 degrees differ in the last bit on some
        # builds), so require a clear winner: margin 0.2 accepts obliquity up to ~37 degrees.
        if top - second < AXIS_MARGIN:
            raise ValueError(f"ambiguous orientation (oblique by ~45 degrees?): margin {top - second:.3f} "
                             f"for {name} from {d.tolist()}")
        out[name] = int(np.argmax(comp))
    if len(set(out.values())) != 3:
        raise ValueError(f"ambiguous orientation (oblique by ~45 degrees?): {out} from {d.tolist()}")
    return out


def simulate_volume(arr, axis, voxel_mm, thickness, gap, phase=0.0, profile="box"):
    """Thick volume on its own (coarse) grid, for evaluation-side simulations (PROTOCOL §9.4).

    Returns (thick array with n_slices along `axis`, slice centres in mm relative to voxel 0).
    """
    w, centres = slab_weights(arr.shape[axis], voxel_mm, thickness, thickness + gap, phase, profile)
    a = np.moveaxis(np.asarray(arr, np.float32), axis, 0)
    thick = (w.astype(np.float32) @ a.reshape(a.shape[0], -1)).reshape((w.shape[0],) + a.shape[1:])
    return np.moveaxis(thick, 0, axis), centres
