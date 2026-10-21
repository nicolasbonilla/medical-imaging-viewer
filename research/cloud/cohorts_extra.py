#!/usr/bin/env python3
"""Fetchers for three extra public MS FLAIR cohorts, for the FLAMeS cloud job (research only).

    fetch_ms3seg(workdir) -> MS3SEG   (Bawil/Bashiri et al., Sci Data 2026; Figshare 30393475; CC BY 4.0)
    fetch_muslim(workdir) -> Muslim et al., Data in Brief 2022 (Mendeley 10.17632/8bctsm8jz7.1; CC BY 4.0)
    fetch_pedims(workdir) -> PediMS   (Popa et al., Sci Data 2025; Figshare 28701065; CC BY 4.0)

Every fetcher returns a list of ``(case_id, flair_path, lesion_mask_path, needs_skull_strip)``:

* ``flair_path`` / ``lesion_mask_path`` are NIfTI-1 ``.nii.gz`` files written by this module with the
  SAME affine, qform and sform (codes 1); the mask is binary ``uint8`` on the FLAIR voxel grid.
* ``needs_skull_strip`` is True when the FLAIR still contains skull/scalp (FLAMeS expects a
  brain-extracted FLAIR). Use :func:`hdbet_strip` (HD-BET v2, folder mode) on those cases; it keeps
  the original grid and affine so the ground truth stays aligned.
* Case ids are prefixed ``ms3seg_``, ``muslim_``, ``pedims_``.
* A ``manifest.json`` with geometry, provenance and QC numbers is written next to the files.

Downloads are minimal and streaming: only the needed members are read from the remote archives with
HTTP range requests (MS3SEG ships RAR5 archives whose members are *stored*, so each member is one
contiguous byte range; the Muslim zip is read with a range-backed ``zipfile``). Nothing else is
downloaded. Only the Python standard library, numpy, nibabel and scipy are needed (scipy is already
a dependency of nnU-Net v2). Designed for Ubuntu 22.04 + Python venv; also runs on Windows.

Layout facts this module relies on (verified 2026-10-17, see docs/research/cohorts-extra.md):

* MS3SEG: ``MS_100_patient_registered.rar`` holds, per patient NNN, ``NNN_FLAIR.nii.gz`` (native
  256x256xN axial 2D FLAIR, 0.898 mm in-plane, 6.0-8.1 mm slice spacing, NOT skull-stripped),
  ``NNN_FLAIR_brain.nii.gz`` / ``NNN_brain_mask.nii.gz`` (authors' FSL-BET). The lesion ground truth
  is ``MS_100_patient_masks.rar`` -> ``abWMH_Masks/NNN/NNN_abWMH_Mask.nii.gz`` (values 0/255) on the
  same grid (checked for all 100). Ventricle and normal-WMH masks are NOT ground truth for lesions.
* Muslim: one zip with ``Patient-K/K-Flair.nii`` and ``K-LesionSeg-Flair.nii`` (same grid), stored
  as raw arrays with NO geometry (pixdim 1 mm, qform/sform codes 0). Slice spacing comes from the
  dataset's Supplementary Table 2 (hard-coded below). In-plane pixel spacing is NOT published: it is
  ESTIMATED per case from the head size (calibrated on MS3SEG, see ``_estimate_inplane_spacing``).
  51 scans are axial, 6 coronal, 3 sagittal (visually curated); arrays are reoriented to LAS.
* PediMS: Figshare files with ``folder_structure`` ``PediMS/P<p>/T<t>/processed``:
  ``brain_FLAIR.nii.gz`` (SynthStrip skull-stripped) and ``Consensus.nii`` (lesion mask, float 0/1)
  on the same 290x320xN grid (0.75x0.75x3.9 mm), checked for all 28 scans.

CLI (local test):  python cohorts_extra.py --cohort muslim --workdir /tmp/x --ids 1
"""
from __future__ import annotations

import argparse
import http.client
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
import zlib
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import nibabel as nib
import numpy as np

try:  # scipy ships with nnU-Net v2; only used for QC / head measurements
    from scipy import ndimage as ndi
except ImportError:  # pragma: no cover
    ndi = None

Case = Tuple[str, str, str, bool]

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) mstool-research-cohort-fetch/1.0"}

# ----------------------------------------------------------------------------------------------
# Source identifiers (resolved through the public APIs at run time; constants are fallbacks)
# ----------------------------------------------------------------------------------------------
MS3SEG_ARTICLE = 30393475
MS3SEG_FALLBACK = {
    "MS_100_patient_registered.rar": "https://ndownloader.figshare.com/files/61900141",
    "MS_100_patient_masks.rar": "https://ndownloader.figshare.com/files/65733546",
}
PEDIMS_ARTICLE = 28701065
MUSLIM_API = "https://data.mendeley.com/public-api/datasets/8bctsm8jz7"
MUSLIM_FALLBACK_URL = ("https://prod-dcd-datasets-public-files-eu-west-1.s3.eu-west-1.amazonaws.com/"
                       "f6eda4e0-ca67-4b7b-b155-a7d77b9f7396")

# Muslim et al. Supplementary Table 2 (FLAIR): patient -> (slice thickness mm, spacing between
# slices mm). Transcribed from "Supplementary Table 2 for  sequence parameters .xlsx" in the zip.
MUSLIM_FLAIR_SLICES: Dict[int, Tuple[float, float]] = {
    1: (5, 5.5), 2: (5, 6.75), 3: (5, 6.5), 4: (5, 5.5), 5: (5, 5.5), 6: (5, 5.5), 7: (5, 5.5),
    8: (5, 6), 9: (3, 4.86), 10: (5, 8), 11: (5, 5.5), 12: (5, 5.5), 13: (5, 5.5), 14: (5, 6.5),
    15: (5, 6), 16: (5, 6), 17: (5, 5.5), 18: (5, 5.5), 19: (5, 6), 20: (5, 5.5), 21: (5, 5.5),
    22: (5, 5.5), 23: (5, 6.5), 24: (5, 5.5), 25: (5, 6), 26: (4, 5.2), 27: (5, 6), 28: (5, 6.5),
    29: (5, 5.5), 30: (5, 5.5), 31: (4.5, 5.175), 32: (5, 5.5), 33: (5, 6.5), 34: (5, 7),
    35: (5, 6.5), 36: (5, 6.5), 37: (4, 5.2), 38: (5, 5.5), 39: (5, 7), 40: (5, 5.5),
    41: (4, 6.579), 42: (5, 8.3), 43: (6, 7), 44: (5, 5.5), 45: (5, 6), 46: (5, 6.5), 47: (5, 5.5),
    48: (5, 5.5), 49: (5, 6), 50: (5, 6), 51: (5, 6), 52: (5, 6), 53: (5, 6.75), 54: (3.5, 6.65),
    55: (5, 6), 56: (4, 5.2), 57: (5, 6.35), 58: (5, 6.5), 59: (5, 6.5), 60: (5, 6),
}
# Acquisition plane, curated visually on 2026-10-17 from every scan (not in the dataset metadata).
MUSLIM_CORONAL = {14, 23, 41, 53, 54, 57}
MUSLIM_SAGITTAL = {32, 48, 56}
# Stored array shapes (header scan 2026-10-17) -> guards against silent upstream changes.
MUSLIM_SHAPES: Dict[int, Tuple[int, int, int]] = {
    1: (256, 256, 23), 2: (320, 280, 23), 3: (320, 280, 20), 4: (256, 256, 18), 5: (256, 256, 26),
    6: (256, 256, 26), 7: (256, 256, 22), 8: (256, 256, 26), 9: (512, 512, 30), 10: (320, 280, 20),
    11: (256, 256, 18), 12: (256, 256, 26), 13: (256, 256, 18), 14: (320, 280, 24),
    15: (288, 288, 25), 16: (512, 512, 26), 17: (256, 256, 18), 18: (256, 256, 21),
    19: (256, 256, 26), 20: (256, 256, 26), 21: (256, 256, 26), 22: (256, 256, 26),
    23: (320, 280, 28), 24: (256, 256, 26), 25: (256, 256, 26), 26: (320, 320, 22),
    27: (256, 256, 26), 28: (320, 280, 21), 29: (256, 256, 18), 30: (256, 256, 23),
    31: (448, 512, 27), 32: (256, 256, 25), 33: (320, 280, 20), 34: (512, 512, 28),
    35: (512, 448, 20), 36: (256, 256, 22), 37: (320, 320, 30), 38: (256, 256, 32),
    39: (512, 368, 21), 40: (512, 448, 33), 41: (512, 512, 28), 42: (448, 512, 19),
    43: (512, 512, 18), 44: (256, 256, 26), 45: (512, 512, 24), 46: (256, 256, 23),
    47: (256, 256, 26), 48: (256, 256, 25), 49: (256, 256, 26), 50: (256, 256, 26),
    51: (256, 256, 26), 52: (512, 512, 22), 53: (256, 176, 19), 54: (320, 180, 24),
    55: (224, 224, 29), 56: (512, 480, 30), 57: (512, 480, 27), 58: (512, 448, 25),
    59: (256, 224, 22), 60: (288, 288, 24),
}
# Head-size references for the in-plane spacing estimate, measured with EXACTLY the recipe in
# _head_extents() on 15 MS3SEG adults with known 0.898 mm pixels (Toshiba 1.5T, Tabriz):
# max left-right breadth 158.7 +/- 7.3 mm (CV 4.6 %), max antero-posterior length 193.0 +/- 7.5 mm.
HEAD_LR_MM = 158.7
HEAD_AP_MM = 193.0
FOV_PRIOR_MM = 240.0  # fallback when the head is cropped by the field of view


def _log(*a) -> None:
    print("[cohorts_extra]", *a, flush=True)


# ----------------------------------------------------------------------------------------------
# HTTP helpers (stdlib only), with retries
# ----------------------------------------------------------------------------------------------
def _retry(fn: Callable, what: str, tries: int = 6):
    for i in range(tries):
        try:
            return fn()
        except urllib.error.HTTPError as e:
            if e.code in (400, 401, 404) or i == tries - 1:
                raise
            _log(f"retry {i + 1}/{tries} {what}: HTTP {e.code}")
        except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
            if i == tries - 1:
                raise
            _log(f"retry {i + 1}/{tries} {what}: {e}")
        time.sleep(min(60, 2 ** i))


def _get_json(url: str):
    def go():
        req = urllib.request.Request(url, headers={**UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode("utf-8"))
    return _retry(go, url)


def _get_range(url: str, start: int, length: int) -> bytes:
    """Bytes [start, start+length) of a remote file; refuses servers that ignore Range."""
    def go():
        req = urllib.request.Request(url, headers={**UA, "Range": f"bytes={start}-{start + length - 1}"})
        with urllib.request.urlopen(req, timeout=300) as r:
            if r.status != 206 and not (start == 0 and r.status == 200):
                raise OSError(f"server ignored Range (HTTP {r.status}) for {url}")
            data = r.read(length) if r.status == 200 else r.read()
        if len(data) != length:
            raise OSError(f"short range read {len(data)}/{length} from {url}")
        return data
    return _retry(go, f"range {start}+{length}")


def _remote_size(url: str) -> int:
    def go():
        req = urllib.request.Request(url, headers={**UA, "Range": "bytes=0-0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            cr = r.headers.get("Content-Range", "")
            if "/" in cr:
                return int(cr.rsplit("/", 1)[1])
            n = r.headers.get("Content-Length")
            if r.status == 200 and n:
                return int(n)
        raise OSError(f"cannot determine size of {url}")
    return _retry(go, f"size {url}")


def _download(url: str, dest: str) -> str:
    def go():
        tmp = dest + ".part"
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=300) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)
        os.replace(tmp, dest)
        return dest
    return _retry(go, f"download {url}")


def _resolve_redirect(url: str) -> str:
    """Location of a 30x without following it (Mendeley -> public S3 object)."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):  # noqa: D401
            return None

    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(urllib.request.Request(url, headers=UA), timeout=60) as r:
            return r.geturl()
    except urllib.error.HTTPError as e:
        loc = e.headers.get("Location") if e.headers else None
        if e.code in (301, 302, 303, 307, 308) and loc:
            return loc
        raise


class HttpRangeFile(io.RawIOBase):
    """Read-only, seekable file over HTTP range requests (for zipfile / RAR header walking)."""

    def __init__(self, url: str, readahead: int = 1 << 16):
        super().__init__()
        self.url = url
        self.size = _remote_size(url)
        self.pos = 0
        self.readahead = readahead
        self._buf_start = -1
        self._buf = b""
        self.requests = 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=io.SEEK_SET):
        if whence == io.SEEK_SET:
            self.pos = offset
        elif whence == io.SEEK_CUR:
            self.pos += offset
        elif whence == io.SEEK_END:
            self.pos = self.size + offset
        self.pos = max(0, self.pos)
        return self.pos

    def readinto(self, b):
        n = min(len(b), self.size - self.pos)
        if n <= 0:
            return 0
        end = self.pos + n
        if not (self._buf_start <= self.pos and end <= self._buf_start + len(self._buf)):
            want = min(max(n, self.readahead), self.size - self.pos)
            self._buf = _get_range(self.url, self.pos, want)
            self._buf_start = self.pos
            self.requests += 1
        s = self.pos - self._buf_start
        b[:n] = self._buf[s:s + n]
        self.pos = end
        return n


# ----------------------------------------------------------------------------------------------
# RAR5 (stored members) over HTTP ranges
# ----------------------------------------------------------------------------------------------
class RarEntry(tuple):
    """(name, data_offset, packed_size, unpacked_size, method, crc32_or_None, is_dir)"""

    name = property(lambda s: s[0])
    offset = property(lambda s: s[1])
    packed = property(lambda s: s[2])
    size = property(lambda s: s[3])
    method = property(lambda s: s[4])
    crc = property(lambda s: s[5])
    is_dir = property(lambda s: s[6])


def _vint(buf: bytes, p: int) -> Tuple[int, int]:
    v = shift = 0
    while True:
        b = buf[p]
        p += 1
        v |= (b & 0x7F) << shift
        shift += 7
        if not b & 0x80:
            return v, p


def rar5_entries(url: str) -> List[RarEntry]:
    """Walk the block headers of a remote single-volume RAR5 archive (one small range read each)."""
    rf = HttpRangeFile(url, readahead=1 << 16)
    rf.seek(0)
    if rf.read(8) != b"Rar!\x1a\x07\x01\x00":
        raise ValueError(f"not a RAR5 archive: {url}")
    off = 8
    out: List[RarEntry] = []
    while off < rf.size:
        rf.seek(off)
        head = rf.read(16)
        hsize, p = _vint(head, 4)
        rf.seek(off)
        full = rf.read(p + hsize)
        htype, q = _vint(full, p)
        hflags, q = _vint(full, q)
        dsize = 0
        if hflags & 0x0001:
            _, q = _vint(full, q)  # extra area size
        if hflags & 0x0002:
            dsize, q = _vint(full, q)
        data_off = off + p + hsize
        if htype == 1:  # main archive header
            aflags, _ = _vint(full, q)
            if aflags & 0x0001:
                raise ValueError("multi-volume RAR not supported")
        elif htype == 2:  # file header
            fflags, q = _vint(full, q)
            unp, q = _vint(full, q)
            _, q = _vint(full, q)  # attributes
            if fflags & 0x0002:
                q += 4  # mtime
            crc = None
            if fflags & 0x0004:
                crc = struct.unpack("<I", full[q:q + 4])[0]
                q += 4
            comp, q = _vint(full, q)
            _, q = _vint(full, q)  # host OS
            nlen, q = _vint(full, q)
            name = full[q:q + nlen].decode("utf-8", "replace")
            if hflags & 0x0018:
                raise ValueError(f"split member not supported: {name}")
            out.append(RarEntry((name, data_off, dsize, unp, (comp >> 7) & 7, crc, bool(fflags & 1))))
        elif htype == 4:
            raise ValueError("encrypted RAR headers not supported")
        elif htype == 5:  # end of archive
            break
        off = data_off + dsize
    _log(f"RAR5 listing: {len(out)} entries, {rf.requests} range requests ({url})")
    return out


def _rar_extract_stored(url: str, e: RarEntry, dest: str) -> str:
    if e.method != 0 or e.packed != e.size:
        raise ValueError(f"{e.name}: compressed RAR member (method {e.method}) - needs unrar")
    data = _get_range(url, e.offset, e.packed)
    if e.crc is not None and (zlib.crc32(data) & 0xFFFFFFFF) != e.crc:
        raise OSError(f"CRC mismatch for {e.name}")
    with open(dest, "wb") as f:
        f.write(data)
    return dest


# ----------------------------------------------------------------------------------------------
# NIfTI helpers
# ----------------------------------------------------------------------------------------------
def _load(path: str) -> nib.Nifti1Image:
    """nib.load without memory-mapping (temporary files must be deletable, also on Windows)."""
    return nib.load(path, mmap=False)


def _raw_array(img: nib.Nifti1Image) -> np.ndarray:
    """Voxel values; the on-disk integer type is kept when the file applies no scaling.

    (nibabel moves scl_slope/scl_inter from the header into the array proxy on load, so the
    proxy - not the header - says whether the stored integers are scaled.)
    """
    proxy = img.dataobj
    slope = float(getattr(proxy, "slope", 1.0))
    inter = float(getattr(proxy, "inter", 0.0))
    if slope == 1.0 and inter == 0.0 and hasattr(proxy, "get_unscaled"):
        return np.asarray(proxy.get_unscaled())
    return img.get_fdata(dtype=np.float32)


def _compact(arr: np.ndarray) -> np.ndarray:
    """Store integer-valued intensities as int16/uint16 when lossless, else float32."""
    if arr.dtype.kind in "iu" and arr.dtype.itemsize <= 2:
        return arr
    a = np.asarray(arr)
    if np.all(np.isfinite(a)) and np.array_equal(a, np.round(a)):
        lo, hi = float(a.min()), float(a.max())
        if -32768 <= lo and hi <= 32767:
            return a.astype(np.int16)
        if lo >= 0 and hi <= 65535:
            return a.astype(np.uint16)
    return a.astype(np.float32)


def _save(arr: np.ndarray, affine: np.ndarray, path: str) -> str:
    img = nib.Nifti1Image(arr, affine)
    img.set_sform(affine, code=1)
    img.set_qform(affine, code=1)
    img.header.set_xyzt_units("mm", "sec")
    nib.save(img, path)
    return path


def _ring(mask: np.ndarray, slice_axis: int = 2, iters: int = 2) -> np.ndarray:
    """In-plane dilation ring around a 3D mask (thick slices: never dilate across slices)."""
    st = np.ones((3, 3, 3), bool)
    idx = [slice(None)] * 3
    for k in (0, 2):
        idx[slice_axis] = k
        st[tuple(idx)] = False
    dil = ndi.binary_dilation(mask, structure=st, iterations=iters)
    return dil & ~mask


def _qc(flair: np.ndarray, mask: np.ndarray, zooms, slice_axis: int = 2) -> dict:
    """Lesion burden + a misalignment detector: FLAIR lesions are hyperintense, so the median FLAIR
    inside the mask must exceed the median of a 2-voxel in-plane ring around it (ratio > 1)."""
    vox_ml = float(np.prod(zooms[:3])) / 1000.0
    q = {"lesion_voxels": int(mask.sum()), "lesion_ml": round(float(mask.sum()) * vox_ml, 3),
         "empty_mask": bool(mask.sum() == 0)}
    if ndi is not None and mask.any():
        lab, n = ndi.label(mask)
        q["lesion_components_3d"] = int(n)
        ring = _ring(mask, slice_axis) & (flair > 0)
        if ring.any():
            les = float(np.median(flair[mask]))
            rng = float(np.median(flair[ring]))
            q["lesion_to_ring_median_ratio"] = round(les / rng, 3) if rng > 0 else None
    return q


def _check_pair(flair_img: nib.Nifti1Image, mask_img: nib.Nifti1Image, label: str, atol: float = 1e-3):
    if flair_img.shape != mask_img.shape:
        raise ValueError(f"{label}: FLAIR shape {flair_img.shape} != mask shape {mask_img.shape}")
    if not np.allclose(flair_img.affine, mask_img.affine, atol=atol):
        raise ValueError(f"{label}: FLAIR and mask affines differ:\n{flair_img.affine}\n{mask_img.affine}")


def _write_manifest(outdir: str, cohort: str, entries: List[dict], extra: dict) -> str:
    path = os.path.join(outdir, "manifest.json")
    old = {}
    if os.path.exists(path):
        try:
            old = {e["case_id"]: e for e in json.load(open(path)).get("cases", [])}
        except (OSError, ValueError, KeyError):
            old = {}
    old.update({e["case_id"]: e for e in entries})
    doc = {"cohort": cohort, "written": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **extra,
           "cases": [old[k] for k in sorted(old)]}
    with open(path, "w") as f:
        json.dump(doc, f, indent=1)
    return path


def _norm_ids(ids, fmt: Callable[[str], str]) -> Optional[set]:
    if ids is None:
        return None
    if isinstance(ids, (str, int)):
        ids = [ids]
    return {fmt(str(i)) for i in ids}


# ----------------------------------------------------------------------------------------------
# MS3SEG
# ----------------------------------------------------------------------------------------------
def _figshare_files(article: int) -> dict:
    d = _get_json(f"https://api.figshare.com/v2/articles/{article}")
    files = d.get("files", [])
    if len(files) >= 10:  # the article endpoint can truncate; the files endpoint pages
        more = _get_json(f"https://api.figshare.com/v2/articles/{article}/files?page_size=1000")
        if len(more) > len(files):
            files = more
    d["files"] = files
    return d


def fetch_ms3seg(workdir: str, ids=None, use_authors_brain: bool = False, with_nwmh: bool = False) -> List[Case]:
    """MS3SEG: 100 Toshiba 1.5T axial 2D FLAIR + MS-lesion (abnormal WMH) masks.

    Default: native FLAIR with skull (needs_skull_strip=True -> HD-BET). With
    ``use_authors_brain=True`` the authors' FSL-BET output is used instead (needs_skull_strip=False;
    note it leaves orbital fat in some slices). ``ids``: e.g. ["001"] or [1] to fetch a subset.
    ``with_nwmh=True`` also writes ``<case>_nwmh.nii.gz`` (the authors' "normal WMH" class: hyperintensities
    judged NOT to be MS lesions) for an optional ignore-region analysis; it is never ground truth.
    """
    out = os.path.join(workdir, "ms3seg")
    os.makedirs(out, exist_ok=True)
    want = _norm_ids(ids, lambda s: f"{int(s):03d}")
    try:
        art = _figshare_files(MS3SEG_ARTICLE)
        urls = {f["name"]: f["download_url"] for f in art["files"]}
        licence = art.get("license", {}).get("name")
    except Exception as e:  # noqa: BLE001  (API down -> use pinned v6 file ids)
        _log("Figshare API unavailable, using pinned file ids:", e)
        urls, licence = {}, None
    reg_url = urls.get("MS_100_patient_registered.rar", MS3SEG_FALLBACK["MS_100_patient_registered.rar"])
    msk_url = urls.get("MS_100_patient_masks.rar", MS3SEG_FALLBACK["MS_100_patient_masks.rar"])
    msk = {e.name: e for e in rar5_entries(msk_url)}
    cids = sorted(m.group(1) for n in msk
                  if (m := re.fullmatch(r"MS_100_patient_masks/abWMH_Masks/(\d{3})/\1_abWMH_Mask\.nii\.gz", n)))
    if want is not None:
        cids = [c for c in cids if c in want]
    reg = {e.name: e for e in rar5_entries(reg_url)}
    suffix = "_FLAIR_brain.nii.gz" if use_authors_brain else "_FLAIR.nii.gz"
    cases: List[Case] = []
    entries: List[dict] = []
    for cid in cids:
        case_id = f"ms3seg_{cid}"
        fp = os.path.join(out, f"{case_id}_flair.nii.gz")
        mp = os.path.join(out, f"{case_id}_lesion.nii.gz")
        if os.path.exists(fp) and os.path.exists(mp):
            cases.append((case_id, fp, mp, not use_authors_brain))
            continue
        fe = reg.get(f"MS_100_patient_registered/{cid}/{cid}{suffix}")
        me = msk[f"MS_100_patient_masks/abWMH_Masks/{cid}/{cid}_abWMH_Mask.nii.gz"]
        ne = msk.get(f"MS_100_patient_masks/nWMH_Masks/{cid}/{cid}_nWMH_Mask.nii.gz")
        if fe is None:
            _log(f"{case_id}: FLAIR member missing in registered archive -> skipped")
            continue
        try:
            with tempfile.TemporaryDirectory(dir=out) as tmp:
                f_raw = _rar_extract_stored(reg_url, fe, os.path.join(tmp, "flair.nii.gz"))
                m_raw = _rar_extract_stored(msk_url, me, os.path.join(tmp, "mask.nii.gz"))
                fi, mi = _load(f_raw), _load(m_raw)
                _check_pair(fi, mi, case_id)
                flair = _compact(_raw_array(fi))
                mask = np.asarray(mi.dataobj) > 0.5
                aff = fi.affine.copy()
                if with_nwmh and ne is not None:
                    ni = _load(_rar_extract_stored(msk_url, ne, os.path.join(tmp, "nwmh.nii.gz")))
                    _check_pair(fi, ni, case_id + " nWMH")
                    _save((np.asarray(ni.dataobj) > 0.5).astype(np.uint8), aff,
                          os.path.join(out, f"{case_id}_nwmh.nii.gz"))
                _save(flair, aff, fp)
                _save(mask.astype(np.uint8), aff, mp)
                entries.append({
                    "case_id": case_id, "source_flair": fe.name, "source_mask": me.name,
                    "shape": list(flair.shape), "zooms_mm": [round(float(z), 4) for z in fi.header.get_zooms()[:3]],
                    "axcodes": "".join(nib.aff2axcodes(aff)), "plane": "axial",
                    "needs_skull_strip": not use_authors_brain, "inplane_spacing_source": "DICOM header (dcm2niix)",
                    **_qc(flair.astype(np.float32), mask, fi.header.get_zooms()),
                })
        except Exception as e:  # noqa: BLE001  one bad case must not lose the cohort
            _log(f"{case_id}: FAILED ({e!r}) -> skipped")
            continue
        cases.append((case_id, fp, mp, not use_authors_brain))
        _log(f"{case_id}: ok {entries[-1]['shape']} lesion {entries[-1]['lesion_ml']} ml")
    _write_manifest(out, "ms3seg", entries, {
        "licence": licence or "CC BY 4.0 (Figshare record)", "doi_data": "10.6084/m9.figshare.30393475",
        "doi_paper": "10.1038/s41597-026-07184-5", "ground_truth": "abWMH (MS lesion) class only"})
    return cases


# ----------------------------------------------------------------------------------------------
# Muslim et al. (Baghdad)
# ----------------------------------------------------------------------------------------------
def _muslim_zip_url() -> str:
    try:
        d = _get_json(MUSLIM_API)
        f = [x for x in d["files"] if x["filename"].lower().endswith(".zip")][0]
        dl = f["content_details"]["download_url"]
        url = _resolve_redirect(dl)
        _remote_size(url)
        return url
    except Exception as e:  # noqa: BLE001
        _log("Mendeley API/redirect failed, using pinned S3 object:", e)
        return MUSLIM_FALLBACK_URL


def _head_extents(vol: np.ndarray, slice_axis: int) -> Dict[int, Tuple[int, int]]:
    """Max head extent (voxels) along each in-plane axis over all slices, and how many slices touch
    that axis' border. Head = largest component of (I > 10 % of the 99th percentile), holes filled.
    Calibration of HEAD_LR_MM / HEAD_AP_MM used exactly this recipe."""
    a = np.moveaxis(vol.astype(np.float32), slice_axis, 2)
    inplane = [ax for ax in range(3) if ax != slice_axis]
    pos = a[a > 0]
    thr = 0.10 * np.percentile(pos, 99) if pos.size else 0.0
    m = a > thr
    ext = [0, 0]
    touch = [0, 0]
    for k in range(a.shape[2]):
        s = m[:, :, k]
        lab, n = ndi.label(s)
        if n == 0:
            continue
        sizes = ndi.sum(s, lab, range(1, n + 1))
        s = ndi.binary_fill_holes(lab == (int(np.argmax(sizes)) + 1))
        idx = np.argwhere(s)
        for j in range(2):
            ext[j] = max(ext[j], int(np.ptp(idx[:, j])) + 1)
        touch[0] += int(s[0, :].any() or s[-1, :].any())
        touch[1] += int(s[:, 0].any() or s[:, -1].any())
    return {inplane[0]: (ext[0], touch[0]), inplane[1]: (ext[1], touch[1])}


def _estimate_inplane_spacing(vol_las: np.ndarray, plane: str) -> Tuple[float, str, dict]:
    """Square in-plane pixel size (mm) for a LAS-ordered volume whose header lost its spacing."""
    slice_axis = {"axial": 2, "coronal": 1, "sagittal": 0}[plane]
    ext = _head_extents(vol_las, slice_axis)
    n_inplane = max(vol_las.shape[ax] for ax in range(3) if ax != slice_axis)
    fov_prior = FOV_PRIOR_MM / n_inplane
    est = {}
    if 0 in ext and ext[0][1] == 0 and ext[0][0] > 0:
        est["lr"] = HEAD_LR_MM / ext[0][0]
    if plane == "axial" and 1 in ext and ext[1][1] == 0 and ext[1][0] > 0:
        est["ap"] = HEAD_AP_MM / ext[1][0]
    info = {"head_extent_vox": {str(k): v[0] for k, v in ext.items()},
            "slices_touching_border": {str(k): v[1] for k, v in ext.items()},
            "estimates_mm": {k: round(v, 4) for k, v in est.items()}}
    if est:
        s = float(np.exp(np.mean(np.log(list(est.values())))))
        method = "head_size_" + "+".join(sorted(est))
    else:
        s, method = fov_prior, "fov_prior_240mm"
    fov = s * n_inplane
    if not 150.0 <= fov <= 450.0:
        _log(f"implausible implied FOV {fov:.0f} mm -> FOV prior")
        s, method = fov_prior, "fov_prior_240mm(after implausible estimate)"
    info["implied_fov_mm"] = round(s * n_inplane, 1)
    return s, method, info


def _muslim_las_transform(flair: np.ndarray, plane: str) -> Tuple[Tuple[int, int, int], Tuple[bool, bool, bool], str]:
    """(transpose axes, flips after transpose, note) taking a stored Muslim array to LAS voxel axes
    (axis0 -> patient Left, axis1 -> Anterior, axis2 -> Superior). The SAME transform must be
    applied to FLAIR and mask (see _apply_las).

    Stored conventions (visual check of all 60 scans, 2026-10-17):
      axial:    axis0 anterior->posterior (DICOM rows), axis1 = DICOM columns (patient left assumed),
                axis2 = slice order (inferior/superior varies per scan -> decided from the head area)
      coronal:  axis0 superior->inferior (rows), axis1 = columns (left assumed), axis2 anterior->posterior
      sagittal: axis0 posterior->anterior, axis1 inferior->superior, axis2 = slices (L/R unknown)
    Left/right polarity cannot be recovered (no DICOM orientation was shared); it is irrelevant to
    mirror-augmented models (FLAMeS, HD-BET) and to Dice on this grid, but never use it for laterality.
    """
    if plane == "axial":
        axes, flips = (1, 0, 2), [False, True, False]
        note = "AP visually verified; LR assumed from DICOM column convention"
        # superior end = the end whose outermost head-bearing slices have the smaller head area
        pos = flair[flair > 0]
        thr = 0.10 * np.percentile(pos, 99) if pos.size else 0.0
        area = (flair > thr).sum(axis=(0, 1)).astype(float)
        nz = np.where(area > 0.05 * area.max())[0] if area.max() > 0 else np.array([])
        if nz.size >= 6:
            first, last = area[nz[:2]].mean(), area[nz[-2:]].mean()
            if first < 0.8 * last:  # stored superior -> inferior
                flips[2] = True
                note += "; slice order reversed (stored superior->inferior, from head area)"
            elif last < 0.8 * first:
                note += "; S/I from head area"
            else:
                note += "; S/I polarity ambiguous (stored order kept)"
        return axes, tuple(flips), note
    if plane == "coronal":
        return (1, 2, 0), (False, True, True), "AP and SI visually verified; LR assumed from DICOM column convention"
    if plane == "sagittal":
        return (2, 0, 1), (False, False, False), "AP and SI visually verified; LR (slice order) unknown"
    raise ValueError(plane)


def _apply_las(arr: np.ndarray, axes, flips) -> np.ndarray:
    out = np.transpose(arr, axes)
    sl = tuple(slice(None, None, -1) if f else slice(None) for f in flips)
    return np.ascontiguousarray(out[sl])


def fetch_muslim(workdir: str, ids=None, planes: Iterable[str] = ("axial",)) -> List[Case]:
    """Muslim et al. 2022 (Baghdad, 1.5T, ~20 centres): FLAIR + consensus lesion mask.

    Default keeps only the 51 AXIAL scans (``planes=("axial", "coronal", "sagittal")`` adds 6 coronal
    and 3 sagittal ones, whose spacing estimate is weaker). Every FLAIR has skull -> needs_skull_strip.
    """
    out = os.path.join(workdir, "muslim")
    os.makedirs(out, exist_ok=True)
    want = _norm_ids(ids, lambda s: str(int(s)))
    planes = set(planes)
    url = _muslim_zip_url()
    rf = HttpRangeFile(url, readahead=1 << 22)
    zf = zipfile.ZipFile(rf)
    names = set(zf.namelist())
    cases: List[Case] = []
    entries: List[dict] = []
    for pid in sorted(MUSLIM_FLAIR_SLICES):
        plane = "coronal" if pid in MUSLIM_CORONAL else "sagittal" if pid in MUSLIM_SAGITTAL else "axial"
        if (want is not None and str(pid) not in want) or plane not in planes:
            continue
        case_id = f"muslim_{pid:02d}"
        fp = os.path.join(out, f"{case_id}_flair.nii.gz")
        mp = os.path.join(out, f"{case_id}_lesion.nii.gz")
        if os.path.exists(fp) and os.path.exists(mp):
            cases.append((case_id, fp, mp, True))
            continue
        fn, mn = f"Patient-{pid}/{pid}-Flair.nii", f"Patient-{pid}/{pid}-LesionSeg-Flair.nii"
        if fn not in names or mn not in names:
            _log(f"{case_id}: members missing -> skipped")
            continue
        try:
            with tempfile.TemporaryDirectory(dir=out) as tmp:
                paths = []
                for member, local in ((fn, "flair.nii"), (mn, "mask.nii")):
                    # read-ahead sized to the member: one range request per small member
                    rf.readahead = max(1 << 16, min(1 << 22, zf.getinfo(member).compress_size + 4096))
                    with zf.open(member) as src, open(os.path.join(tmp, local), "wb") as dst:
                        shutil.copyfileobj(src, dst, 1 << 20)
                    paths.append(os.path.join(tmp, local))
                fi, mi = _load(paths[0]), _load(paths[1])
                if fi.shape != mi.shape:
                    _log(f"{case_id}: FLAIR {fi.shape} != mask {mi.shape} -> skipped")
                    continue
                if tuple(fi.shape) != MUSLIM_SHAPES[pid]:
                    _log(f"{case_id}: unexpected shape {fi.shape} (expected {MUSLIM_SHAPES[pid]}) -> skipped")
                    continue
                stored_shape = list(fi.shape)
                f_arr = np.asarray(fi.dataobj, dtype=np.float32)
                m_arr = np.asarray(mi.dataobj) > 0.5
                del fi, mi
            axes, flips, orient_note = _muslim_las_transform(f_arr, plane)
            f_las = _apply_las(f_arr, axes, flips)
            m_las = _apply_las(m_arr, axes, flips)
            thick, dz = MUSLIM_FLAIR_SLICES[pid]
            slice_axis = {"axial": 2, "coronal": 1, "sagittal": 0}[plane]
            s, method, sinfo = _estimate_inplane_spacing(f_las, plane)
            zooms = [s, s, s]
            zooms[slice_axis] = float(dz)
            aff = np.diag([-zooms[0], zooms[1], zooms[2], 1.0])
            aff[:3, 3] = -aff[:3, :3] @ ((np.array(f_las.shape) - 1) / 2.0)
            flair = _compact(f_las)
            _save(flair, aff, fp)
            _save(m_las.astype(np.uint8), aff, mp)
            entries.append({
                "case_id": case_id, "source_flair": fn, "source_mask": mn, "plane": plane,
                "stored_shape": stored_shape, "shape": list(flair.shape), "zooms_mm": [round(z, 4) for z in zooms],
                "axcodes": "".join(nib.aff2axcodes(aff)), "orientation_note": orient_note,
                "slice_thickness_mm": thick, "slice_spacing_mm": dz,
                "inplane_spacing_source": "ESTIMATED (" + method + ")", "inplane_spacing_detail": sinfo,
                "needs_skull_strip": True, **_qc(f_las, m_las, zooms, slice_axis),
            })
        except Exception as e:  # noqa: BLE001  one bad case must not lose the cohort
            _log(f"{case_id}: FAILED ({e!r}) -> skipped")
            continue
        cases.append((case_id, fp, mp, True))
        _log(f"{case_id}: ok {plane} {flair.shape} pix {s:.3f} mm ({method}) dz {dz} lesion {entries[-1]['lesion_ml']} ml")
    _log(f"Muslim zip: {rf.requests} range requests")
    _write_manifest(out, "muslim", entries, {
        "licence": "CC BY 4.0 (Mendeley Data record)", "doi_data": "10.17632/8bctsm8jz7.1",
        "doi_paper": "10.1016/j.dib.2022.108139",
        "warning": "in-plane pixel spacing ESTIMATED from head size (+/-~5-8 %); L/R polarity unknown",
        "planes_included": sorted(planes)})
    return cases


# ----------------------------------------------------------------------------------------------
# PediMS
# ----------------------------------------------------------------------------------------------
def fetch_pedims(workdir: str, ids=None, flair_kind: str = "brain_FLAIR.nii.gz") -> List[Case]:
    """PediMS: 9 children, 28 scans (3T Siemens Skyra), skull-stripped FLAIR + consensus lesion mask.

    ``ids``: e.g. ["P1_T1"]. ``flair_kind``: "brain_FLAIR.nii.gz" (default, SynthStrip) or
    "n4_brain_FLAIR.nii.gz" (same + N4 bias correction). needs_skull_strip is False.
    """
    out = os.path.join(workdir, "pedims")
    os.makedirs(out, exist_ok=True)
    want = _norm_ids(ids, lambda s: s.upper().replace("PEDIMS_", ""))
    art = _figshare_files(PEDIMS_ARTICLE)
    fs = art.get("folder_structure") or {}
    groups: Dict[Tuple[str, str], Dict[str, dict]] = {}
    for f in art["files"]:
        m = re.fullmatch(r"PediMS/(P\d+)/(T\d+)/processed", fs.get(str(f["id"]), ""))
        if m:
            groups.setdefault((m.group(1), m.group(2)), {})[f["name"]] = f
    cases: List[Case] = []
    entries: List[dict] = []
    for (p, t) in sorted(groups, key=lambda k: (int(k[0][1:]), int(k[1][1:]))):
        tag = f"{p}_{t}"
        if want is not None and tag not in want:
            continue
        case_id = f"pedims_{tag}"
        fp = os.path.join(out, f"{case_id}_flair.nii.gz")
        mp = os.path.join(out, f"{case_id}_lesion.nii.gz")
        if os.path.exists(fp) and os.path.exists(mp):
            cases.append((case_id, fp, mp, False))
            continue
        g = groups[(p, t)]
        if flair_kind not in g or "Consensus.nii" not in g:
            _log(f"{case_id}: {flair_kind} or Consensus.nii missing -> skipped")
            continue
        try:
            with tempfile.TemporaryDirectory(dir=out) as tmp:
                f_raw = _download(g[flair_kind]["download_url"], os.path.join(tmp, "flair.nii.gz"))
                m_raw = _download(g["Consensus.nii"]["download_url"], os.path.join(tmp, "mask.nii"))
                fi, mi = _load(f_raw), _load(m_raw)
                _check_pair(fi, mi, case_id)
                flair = _compact(_raw_array(fi))
                mask = np.asarray(mi.dataobj) > 0.5
                aff = fi.affine.copy()
                _save(flair, aff, fp)
                _save(mask.astype(np.uint8), aff, mp)
                entries.append({
                    "case_id": case_id, "source_flair": f"PediMS/{p}/{t}/processed/{flair_kind}",
                    "source_mask": f"PediMS/{p}/{t}/processed/Consensus.nii", "plane": "axial",
                    "shape": list(flair.shape), "zooms_mm": [round(float(z), 4) for z in fi.header.get_zooms()[:3]],
                    "axcodes": "".join(nib.aff2axcodes(aff)), "needs_skull_strip": False,
                    "inplane_spacing_source": "NIfTI header", "balo_concentric_sclerosis": p == "P9",
                    **_qc(flair.astype(np.float32), mask, fi.header.get_zooms()),
                })
        except Exception as e:  # noqa: BLE001  one bad case must not lose the cohort
            _log(f"{case_id}: FAILED ({e!r}) -> skipped")
            continue
        cases.append((case_id, fp, mp, False))
        _log(f"{case_id}: ok {entries[-1]['shape']} lesion {entries[-1]['lesion_ml']} ml")
    _write_manifest(out, "pedims", entries, {
        "licence": art.get("license", {}).get("name", "CC BY 4.0"), "doi_data": "10.6084/m9.figshare.28701065",
        "doi_paper": "10.1038/s41597-025-05346-5", "note": "longitudinal: scans of one patient are NOT independent"})
    return cases


def fetch_pedims_raw(workdir: str, ids=None) -> Dict[str, str]:
    """PediMS RAW FLAIR (``raw/defaced_FLAIR.nii.gz``: defaced, skull present), byte-identical to Figshare.

    Same scans and ids as ``fetch_pedims`` (pedims_P1_T1 ...). The raw FLAIR shares shape and affine with
    ``processed/brain_FLAIR.nii.gz`` (header check of all 28, docs/research/cohorts-extra.md 3.3); the paper F
    driver re-checks every grid against the FLAMeS input before use. Figshare's computed MD5 is verified.
    Returns ``{case_id: path}``.
    """
    import hashlib
    out = os.path.join(workdir, "pedims_raw")
    os.makedirs(out, exist_ok=True)
    want = _norm_ids(ids, lambda s: s.upper().replace("PEDIMS_", ""))
    art = _figshare_files(PEDIMS_ARTICLE)
    fs = art.get("folder_structure") or {}
    got: Dict[str, str] = {}
    for f in art["files"]:
        m = re.fullmatch(r"PediMS/(P\d+)/(T\d+)/raw", fs.get(str(f["id"]), ""))
        if not m or f["name"] != "defaced_FLAIR.nii.gz":
            continue
        tag = f"{m.group(1)}_{m.group(2)}"
        if want is not None and tag not in want:
            continue
        dest = os.path.join(out, f"pedims_{tag}_flair_raw.nii.gz")
        if not os.path.exists(dest):
            _download(f["download_url"], dest)
        md5 = f.get("computed_md5") or f.get("supplied_md5")
        if md5:
            h = hashlib.md5()
            with open(dest, "rb") as fh:
                for b in iter(lambda: fh.read(1 << 20), b""):
                    h.update(b)
            if h.hexdigest() != md5:
                os.remove(dest)
                _log(f"pedims_{tag}: raw FLAIR MD5 mismatch -> skipped")
                continue
        got[f"pedims_{tag}"] = dest
    _log(f"PediMS raw FLAIR: {len(got)} files")
    return dict(sorted(got.items()))


FETCHERS: Dict[str, Callable[..., List[Case]]] = {
    "ms3seg": fetch_ms3seg,
    "muslim": fetch_muslim,
    "pedims": fetch_pedims,
}


# ----------------------------------------------------------------------------------------------
# HD-BET skull stripping that preserves the ground-truth grid
# ----------------------------------------------------------------------------------------------
def hdbet_strip(flairs: Dict[str, str], outdir: str, gts: Optional[Dict[str, str]] = None,
                device: str = "cpu", tta: bool = False) -> Dict[str, str]:
    """Run HD-BET v2 ONCE in folder mode on ``{case_id: flair_path}``; return ``{case_id: brain_path}``.

    Only the HD-BET brain MASK is used: the brain image is rebuilt here as raw * mask and saved with
    the ORIGINAL affine/dtype, so it shares the exact grid of the lesion mask. Writes
    ``hdbet_qc.json`` (brain fraction; share of ground-truth lesion voxels outside the brain mask).
    Cases where HD-BET fails or returns an implausible mask are left out of the result.
    """
    os.makedirs(outdir, exist_ok=True)
    stage, res = os.path.join(outdir, "_in"), os.path.join(outdir, "_out")
    for d in (stage, res):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
    for cid, p in flairs.items():
        shutil.copy(p, os.path.join(stage, f"{cid}.nii.gz"))
    cmd = ["hd-bet", "-i", stage, "-o", res, "-device", device, "--save_bet_mask", "--no_bet_image"]
    if not tta:
        cmd.append("--disable_tta")
    _log("running:", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        _log("hd-bet failed:", r.stderr[-2000:])
    done: Dict[str, str] = {}
    qc: Dict[str, dict] = {}
    for cid, p in flairs.items():
        bm = os.path.join(res, f"{cid}_bet.nii.gz")
        if not os.path.exists(bm):
            _log(f"{cid}: no HD-BET mask -> dropped")
            continue
        fi = _load(p)
        brain = np.asarray(_load(bm).dataobj) > 0
        if brain.shape != fi.shape:
            _log(f"{cid}: HD-BET mask shape {brain.shape} != {fi.shape} -> dropped")
            continue
        frac = float(brain.mean())
        q = {"brain_fraction": round(frac, 4)}
        if gts and cid in gts:
            les = np.asarray(_load(gts[cid]).dataobj) > 0
            q["lesion_voxels"] = int(les.sum())
            q["lesion_outside_brain_frac"] = round(float((les & ~brain).sum()) / max(1, int(les.sum())), 4)
        qc[cid] = q
        if not 0.02 <= frac <= 0.8:
            _log(f"{cid}: implausible brain fraction {frac:.3f} -> dropped")
            continue
        arr = _raw_array(fi)
        out_arr = np.where(brain, arr, 0).astype(arr.dtype)
        dst = os.path.join(outdir, f"{cid}_flair_brain.nii.gz")
        _save(out_arr, fi.affine, dst)
        done[cid] = dst
    with open(os.path.join(outdir, "hdbet_qc.json"), "w") as f:
        json.dump(qc, f, indent=1)
    shutil.rmtree(stage, ignore_errors=True)
    _log(f"HD-BET: {len(done)}/{len(flairs)} stripped")
    return done


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cohort", required=True, choices=sorted(FETCHERS))
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--ids", nargs="*", help="subset, e.g. 001 (ms3seg), 1 (muslim), P1_T1 (pedims)")
    ap.add_argument("--all-planes", action="store_true", help="muslim: include coronal/sagittal scans")
    ap.add_argument("--authors-brain", action="store_true", help="ms3seg: use authors' FSL-BET FLAIR")
    a = ap.parse_args(argv)
    kw = {}
    if a.cohort == "muslim" and a.all_planes:
        kw["planes"] = ("axial", "coronal", "sagittal")
    if a.cohort == "ms3seg" and a.authors_brain:
        kw["use_authors_brain"] = True
    for c in FETCHERS[a.cohort](a.workdir, ids=a.ids, **kw):
        print("\t".join(str(x) for x in c))
    return 0


if __name__ == "__main__":
    sys.exit(main())
