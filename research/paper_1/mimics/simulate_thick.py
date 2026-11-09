"""Paper 1 addendum, part C (PREREG-mimics-thickness.md section 5): the pre-registered thick-section simulation.

The operator is `thick_slice.py`, copied VERBATIM from research/flames-thick @ b6342ec (git blob
34ba9ec519c296305b8d04ff6a24c227cd9dab8a; unit-tested there in research/flames_thick/tests/test_thick_slice.py).
Its module docstring and PREREGISTERED dict belong to the FLAMeS-thick protocol and are NOT used here; only
`thicken` is called, with the fixed parameters below.

Primary simulation (fixed; changing any value is a protocol deviation):
  * axis       : the axial axis = voxel axis 2 of the 1-mm MNI grids (I-S world axis; checked);
  * thickness  : T in {3, 5, 7} mm, no gap (slice spacing = T, as in "no-gap" 2D clinical FLAIR);
  * profile    : box (slab average: each thick slice is the mean of the T mm of tissue it covers);
  * phase      : 0 (the first slice is centred on voxel 0 along the axis);
  * back to the 1-mm grid : linear interpolation between slice centres (mode "linear");
  * background : voxels that are 0 in the 1-mm input (outside the skull-stripped brain) are set back to 0,
                 so every tool sees the same brain extent at every thickness.
The expert mask is NOT changed: the 1-mm expert mask stays the reference at every thickness (section 5.2).

    python -I research/paper_1/mimics/simulate_thick.py in_FLAIR.nii.gz out_FLAIR_T5.nii.gz --thickness 5
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thick_slice as ts  # noqa: E402  (verbatim copy, see docstring)

THICKNESSES_MM = (3.0, 5.0, 7.0)
PRIMARY = {"axis": 2, "gap_mm": 0.0, "phase_mm": 0.0, "profile": "box", "mode": "linear"}
THICK_SLICE_BLOB = "34ba9ec519c296305b8d04ff6a24c227cd9dab8a"


def check_grid(affine, zooms):
    """The axis that is thickened must be the world I-S axis with ~1 mm voxels (the MNI grids of part C)."""
    a = np.asarray(affine, float)[:3, :3]
    col = a[:, PRIMARY["axis"]] / np.linalg.norm(a[:, PRIMARY["axis"]])
    if abs(col[2]) < 0.999:
        raise ValueError(f"voxel axis {PRIMARY['axis']} is not the I-S axis (direction {col.round(3).tolist()})")
    if not np.isclose(float(zooms[PRIMARY["axis"]]), 1.0, atol=1e-3):
        raise ValueError(f"voxel size along the axial axis is {zooms[PRIMARY['axis']]} mm, not 1 mm")


def simulate_array(data, thickness_mm, voxel_mm=1.0):
    if thickness_mm not in THICKNESSES_MM:
        raise ValueError(f"thickness {thickness_mm} not pre-registered {THICKNESSES_MM}")
    x = np.asarray(data, np.float32)
    out = ts.thicken(x, PRIMARY["axis"], voxel_mm, float(thickness_mm), PRIMARY["gap_mm"], PRIMARY["phase_mm"],
                     PRIMARY["profile"], PRIMARY["mode"])
    out = np.asarray(out, np.float32)
    out[x == 0] = 0.0
    return out


def simulate_file(src, dst, thickness_mm):
    import nibabel as nib
    img = nib.load(src)
    zooms = img.header.get_zooms()[:3]
    check_grid(img.affine, zooms)
    out = simulate_array(np.asarray(img.dataobj), thickness_mm, float(zooms[PRIMARY["axis"]]))
    hdr = img.header.copy()
    hdr.set_data_dtype(np.float32)
    nib.save(nib.Nifti1Image(out, img.affine, hdr), dst)
    return {"src": os.path.basename(src), "dst": os.path.basename(dst), "thickness_mm": thickness_mm, **PRIMARY}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--thickness", type=float, required=True)
    a = ap.parse_args()
    print(simulate_file(a.src, a.dst, a.thickness))


if __name__ == "__main__":
    main()
