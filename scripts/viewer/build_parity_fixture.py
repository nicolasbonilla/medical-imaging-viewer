"""Build the committed client/server 2D-rendering PARITY fixture (viewer v3).

Why this exists
---------------
The browser now renders 2D slices itself from the raw NIfTI (full bit depth,
instant window/level). The server PNG path (`ImagingService.process_image`)
remains as a fallback until parity is proven. "Parity" must be shown against the
REAL server code, not against a re-implementation of it — so this script runs
tiny synthetic volumes through the backend's own `ImagingService.load_nifti`
and `ImagingService.process_image`, decodes the PNGs it produces, and records
the exact uint8 pixels. The frontend test `volume/parity.test.ts` parses the
same NIfTI bytes with the client parser and must reproduce every pixel, the
grid (rows/columns/slices), the voxel spacing and the orientation codes.

Every volume is deliberately ASYMMETRIC (all three dimensions differ, values
encode the voxel index) so that a transposition or a flip cannot pass.

Usage (from the repository root, with the backend virtualenv):

    backend/venv/Scripts/python.exe scripts/viewer/build_parity_fixture.py

Output: frontend/src/volume/__fixtures__/parity-cases.json  (small, committed)
"""
from __future__ import annotations

import asyncio
import base64
import gzip
import io
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import nibabel as nib
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))
os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", "nonexistent")

from app.services.imaging_service import ImagingService  # noqa: E402
from app.utils.nifti_utils import get_orientation_codes  # noqa: E402

# Windows-only harness shim: nibabel memory-maps an uncompressed .nii, and Windows
# refuses to delete a mapped temp file (load_nifti_from_bytes unlinks it). Linux /
# Cloud Run allow that, so production is unaffected. mmap=False changes no values.
_orig_load = nib.load
nib.load = lambda path, **kw: _orig_load(path, mmap=False, **kw)  # type: ignore[assignment]

OUT = REPO / "frontend" / "src" / "volume" / "__fixtures__" / "parity-cases.json"


def _index_volume(shape, dtype, scale=1.0, offset=0.0):
    """Value encodes (i, j, k) so any axis swap/flip changes the pixels."""
    i, j, k = np.meshgrid(*[np.arange(n) for n in shape], indexing="ij")
    vol = (i * 1 + j * 11 + k * 131) * scale + offset
    return vol.astype(dtype)


def _to_bytes(img: nib.Nifti1Image, gz: bool) -> bytes:
    suffix = ".nii.gz" if gz else ".nii"
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / f"case{suffix}"
        nib.save(img, str(p))
        return p.read_bytes()


def _rot_z(deg: float) -> np.ndarray:
    t = np.deg2rad(deg)
    return np.array([[np.cos(t), -np.sin(t), 0], [np.sin(t), np.cos(t), 0], [0, 0, 1.0]])


def build_cases():
    cases = []

    # 1. int16, LAS (MNI-like, x flipped), scl_slope/inter, anisotropic, sform.
    data = _index_volume((7, 5, 4), np.int16)
    aff = np.diag([-0.9, 1.1, 3.0, 1.0]); aff[:3, 3] = [30, -40, -20]
    img = nib.Nifti1Image(data, aff)
    img.header.set_slope_inter(2.5, -10.0)
    img.header.set_sform(aff, code=1); img.header.set_qform(aff, code=1)
    cases.append(("int16_LAS_scaled_sform", img, False))

    # 2. float32, RAS, sform only, gzipped.
    data = _index_volume((6, 9, 3), np.float32, scale=0.37, offset=-5.25)
    aff = np.diag([1.0, 1.0, 1.0, 1.0])
    img = nib.Nifti1Image(data, aff)
    img.header.set_sform(aff, code=2); img.header.set_qform(None, code=0)
    cases.append(("float32_RAS_gz", img, True))

    # 3. uint8, permuted axes (voxel i -> world P, j -> S, k -> L), qform only.
    data = _index_volume((5, 4, 6), np.uint8)
    aff = np.array([[0, 0, -1.2, 10], [-0.8, 0, 0, 5], [0, 1.5, 0, -3], [0, 0, 0, 1.0]])
    img = nib.Nifti1Image(data, None)
    img.header.set_qform(aff, code=1); img.header.set_sform(None, code=0)
    cases.append(("uint8_PSL_qform_only", img, False))

    # 4. float64, oblique (30 deg about z) RAS-ish.
    data = _index_volume((4, 6, 5), np.float64, scale=1.5)
    aff = np.eye(4); aff[:3, :3] = _rot_z(30) @ np.diag([1.0, 2.0, 1.0])
    img = nib.Nifti1Image(data, aff)
    img.header.set_sform(aff, code=1)
    cases.append(("float64_oblique30", img, False))

    # 5. big-endian int16 (byte-swapped on disk).
    data = _index_volume((5, 7, 3), np.dtype(">i2"))
    aff = np.diag([-1.0, -1.0, 1.0, 1.0])
    hdr = nib.Nifti1Header(endianness=">")
    hdr.set_data_dtype(np.dtype(">i2"))
    img = nib.Nifti1Image(data, aff, header=hdr)
    img.header.set_sform(aff, code=1)
    cases.append(("int16_bigendian_LPS", img, False))

    # 6. Singular affine -> orientation must be UNKNOWN (never guessed).
    data = _index_volume((4, 3, 5), np.int16)
    aff = np.diag([1.0, 1.0, 0.0, 1.0])
    img = nib.Nifti1Image(data, None)  # nibabel cannot derive a qform from it
    img.header.set_sform(aff, code=1); img.header.set_qform(None, code=0)
    cases.append(("int16_singular_affine", img, False))

    # 7. uint16 + int8 extra datatypes (spot-checks).
    data = _index_volume((3, 4, 5), np.uint16, scale=97)
    img = nib.Nifti1Image(data, np.diag([2.0, 2.0, 2.0, 1.0]))
    cases.append(("uint16_RAS", img, False))

    # 8. Strong oblique (50 deg about z): voxel i is closer to world A than R —
    #    exercises the greedy axis assignment with row exclusion (nibabel io_orientation).
    data = _index_volume((3, 5, 4), np.int8)
    aff = np.eye(4); aff[:3, :3] = _rot_z(50)
    img = nib.Nifti1Image(data, aff)
    img.header.set_sform(aff, code=1)
    cases.append(("int8_oblique50", img, False))

    # 9. Sheared direction matrix: only the ORTHOGONALISED (polar) factor gives
    #    nibabel's answer; a naive per-column argmax can disagree.
    data = _index_volume((4, 3, 6), np.float32)
    aff = np.eye(4); aff[:3, :3] = np.array([[1.0, 0.95, 0.0], [0.0, 1.0, 0.3], [0.2, 0.0, 1.0]])
    img = nib.Nifti1Image(data, None)
    img.header.set_sform(aff, code=1); img.header.set_qform(None, code=0)
    cases.append(("float32_sheared", img, False))

    # 10. 3-D oblique where a per-column argmax WITHOUT world-axis exclusion would
    #     name the same world axis twice (R, A, R): pins nibabel's row exclusion.
    from scipy.spatial.transform import Rotation
    rot = Rotation.from_euler("xyz", [-49.7, -31.6, 36.2], degrees=True).as_matrix()
    naive = [int(np.argmax(np.abs(rot[:, c]))) for c in range(3)]
    assert len(set(naive)) < 3, naive  # the case must keep discriminating
    data = _index_volume((5, 3, 4), np.int16)
    aff = np.eye(4); aff[:3, :3] = rot * 1.25
    img = nib.Nifti1Image(data, aff)
    img.header.set_sform(aff, code=1)
    cases.append(("int16_oblique3d_exclusion", img, False))

    return cases


async def main():
    svc = ImagingService()
    out_cases = []
    for name, img, gz in build_cases():
        raw = _to_bytes(img, gz)
        # Reload through nibabel to record what the backend actually sees.
        reloaded = nib.Nifti1Image.from_bytes(gzip.decompress(raw) if gz else raw)
        codes = get_orientation_codes(reloaded)
        data, meta = svc.load_nifti(raw)
        series = await svc.process_image(raw, f"{name}.nii{'.gz' if gz else ''}", (0, 500))
        slices = []
        for s in series.slices:
            px = np.array(Image.open(io.BytesIO(base64.b64decode(s.image_data))))
            assert px.dtype == np.uint8 and px.shape == (s.height, s.width), px.shape
            slices.append(base64.b64encode(px.tobytes()).decode())
        fdata = reloaded.get_fdata()
        out_cases.append({
            "name": name,
            "gzipped": gz,
            "nifti_b64": base64.b64encode(raw).decode(),
            "shape": list(reloaded.shape),
            "server_metadata": json.loads(meta.model_dump_json()),
            "server_total_slices": series.total_slices,
            "server_slices_uint8_b64": slices,  # row-major (rows=a0, cols=a1) per slice k
            "nibabel_axcodes": list(codes) if codes is not None else None,
            "nibabel_affine": np.asarray(reloaded.affine, dtype=float).tolist(),
            "nibabel_zooms": [float(z) for z in reloaded.header.get_zooms()],
            "scaled_min": float(np.nanmin(fdata)),
            "scaled_max": float(np.nanmax(fdata)),
            # A few exact scaled voxel values (i, j, k) -> value, for the readout test.
            "probe_voxels": [
                {"ijk": [int(a), int(b), int(c)], "value": float(fdata[a, b, c])}
                for (a, b, c) in [(0, 0, 0), (1, 2, 1), tuple(n - 1 for n in reloaded.shape[:3])]
            ],
        })
        print(f"{name:28s} shape={reloaded.shape} codes={codes} orient={meta.anatomical_orientation}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generator": "scripts/viewer/build_parity_fixture.py",
        "nibabel": nib.__version__,
        "numpy": np.__version__,
        "cases": out_cases,
    }, indent=1))
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    asyncio.run(main())
