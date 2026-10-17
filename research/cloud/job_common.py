"""Shared helpers for the research cloud jobs (project mstool-research only).

Pure functions (no cloud calls) so they can be unit-tested locally on synthetic NIfTI files:
  * case selection (offset / limit / explicit list) identical in every job;
  * grid comparison and trilinear resampling into a reference grid (world coordinates);
  * compact probability storage (uint8 + NIfTI slope, max error = range / 510 <= 0.00196);
  * blank-image detection (e.g. MSLesSeg P49_T2 has an all-zero T1);
  * sha256 and a /proc/meminfo peak-memory sampler (Linux VMs; returns None elsewhere).
"""
import hashlib
import os
import threading

import numpy as np

GRID_ATOL = 1e-4          # mm; affines closer than this are the same grid (header float rounding)
UINT8_MAX_ERR = 1.0 / 510.0   # nibabel scales [min, max] onto 0..255: worst rounding = range / 510


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def split_ids(text):
    """'a b,c' -> ['a', 'b', 'c'] (metadata values arrive as one string)."""
    return [t for t in (text or "").replace(",", " ").split() if t]


def select_ids(ids, offset=0, limit=0, explicit=None):
    """Deterministic chunking: sort, then an explicit list wins, else ids[offset:offset+limit]."""
    ids = sorted(ids)
    if explicit:
        missing = [c for c in explicit if c not in ids]
        if missing:
            raise ValueError(f"requested cases not found: {missing}")
        return [c for c in ids if c in set(explicit)]
    return ids[offset:] if limit <= 0 else ids[offset:offset + limit]


def same_grid(shape_a, affine_a, shape_b, affine_b, atol=GRID_ATOL):
    return tuple(shape_a[:3]) == tuple(shape_b[:3]) and np.allclose(affine_a, affine_b, atol=atol)


def resample_to_grid(data, src_affine, ref_shape, ref_affine, order=1):
    """Resample `data` (voxel grid src_affine) onto (ref_shape, ref_affine) through world space.

    order=1 is trilinear. Returns (array float32, voxel-to-voxel matrix ref->src as a list).
    Voxels outside the source field of view are 0.
    """
    from scipy.ndimage import affine_transform
    m = np.linalg.inv(np.asarray(src_affine, float)) @ np.asarray(ref_affine, float)
    out = affine_transform(np.asarray(data, np.float32), m[:3, :3], offset=m[:3, 3],
                           output_shape=tuple(ref_shape[:3]), order=order, mode="constant", cval=0.0)
    return out.astype(np.float32), np.round(m, 8).tolist()


def to_grid(img, ref_img, order=1):
    """Image data on the reference grid. Identity when the grids already match (no interpolation).

    Returns (array float32, transform record) — the record goes into the run manifest.
    """
    data = np.asarray(img.get_fdata(dtype=np.float32))
    if data.ndim == 4 and data.shape[3] == 1:
        data = data[..., 0]
    if same_grid(img.shape, img.affine, ref_img.shape, ref_img.affine):
        return data, {"kind": "identity", "max_affine_diff": float(np.abs(img.affine - ref_img.affine).max())}
    out, m = resample_to_grid(data, img.affine, ref_img.shape, ref_img.affine, order=order)
    return out, {"kind": "trilinear" if order == 1 else f"spline{order}", "ref_vox_to_src_vox": m,
                 "src_shape": list(img.shape[:3]), "src_affine": np.round(img.affine, 6).tolist()}


def save_prob(arr, ref_img, out_path, dtype="uint8"):
    """Probability map in [0, 1] saved on the reference grid (affine + header of ref_img).

    uint8: nibabel stores value = byte * slope + inter (slope = range/255); max error = range/510.
    float32: exact. Returns the measured max abs error after reading the file back.
    """
    import nibabel as nib
    a = np.clip(np.asarray(arr, np.float32), 0.0, 1.0)
    if a.shape != tuple(ref_img.shape[:3]):
        raise ValueError(f"shape {a.shape} != reference {ref_img.shape[:3]}")
    hdr = ref_img.header.copy()
    hdr.set_slope_inter(None, None)
    img = nib.Nifti1Image(a, ref_img.affine, hdr)
    img.set_data_dtype(np.uint8 if dtype == "uint8" else np.float32)
    nib.save(img, out_path)
    back = np.asarray(nib.load(out_path).get_fdata(dtype=np.float32))
    return float(np.abs(back - a).max())


def save_like(arr, ref_img, out_path, dtype):
    """Non-probability volume (image, mask) on the reference grid with an explicit dtype."""
    import nibabel as nib
    hdr = ref_img.header.copy()
    hdr.set_slope_inter(None, None)
    img = nib.Nifti1Image(np.asarray(arr).astype(dtype), ref_img.affine, hdr)
    img.set_data_dtype(dtype)
    nib.save(img, out_path)


def blank_reason(data, min_fraction=0.01):
    """Why an image cannot be used (None if it is fine). Catches all-zero / near-empty / NaN volumes."""
    d = np.asarray(data)
    if d.size == 0:
        return "empty array"
    if not np.isfinite(d).all():
        return "non-finite values"
    nz = np.count_nonzero(d) / d.size
    if nz < min_fraction:
        return f"blank: only {nz:.4%} non-zero voxels"
    if float(d.max()) == float(d.min()):
        return "constant image"
    return None


def dice(a, b):
    a, b = np.asarray(a, bool), np.asarray(b, bool)
    s = a.sum() + b.sum()
    return 1.0 if s == 0 else float(2.0 * np.logical_and(a, b).sum() / s)


class PeakMemory:
    """Samples /proc/meminfo (used = MemTotal - MemAvailable, and swap) while a block runs."""

    def __init__(self, period=1.0):
        self.period, self.peak_used_gb, self.peak_swap_gb = period, None, None
        self._stop = threading.Event()

    @staticmethod
    def _read():
        try:
            info = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    k, v = line.split(":", 1)
                    info[k] = int(v.split()[0]) / 1048576.0      # kB -> GB
            return info["MemTotal"] - info["MemAvailable"], info.get("SwapTotal", 0) - info.get("SwapFree", 0)
        except (OSError, KeyError, ValueError):
            return None

    def _loop(self):
        while not self._stop.is_set():
            r = self._read()
            if r:
                self.peak_used_gb = max(self.peak_used_gb or 0.0, r[0])
                self.peak_swap_gb = max(self.peak_swap_gb or 0.0, r[1])
            self._stop.wait(self.period)

    def __enter__(self):
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._t.join(timeout=5)
        return False

    def record(self):
        r = lambda x: None if x is None else round(x, 2)   # noqa: E731
        return {"peak_mem_used_gb": r(self.peak_used_gb), "peak_swap_used_gb": r(self.peak_swap_gb)}


def code_hashes(paths):
    return {os.path.basename(p): sha256(p) for p in paths if p and os.path.exists(p)}


def pkg_versions(names):
    """Installed distribution versions (None when absent) — from package metadata, not __version__."""
    from importlib import metadata
    out = {}
    for n in names:
        try:
            out[n] = metadata.version(n)
        except metadata.PackageNotFoundError:
            out[n] = None
    return out
