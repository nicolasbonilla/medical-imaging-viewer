"""Derive a thick-slice (anisotropic) FLAIR from a public 1 mm FLAIR, to exercise nnU-Net's separate-z path.

    python -I make_thick_slice_case.py <in FLAIR.nii.gz> <out.nii.gz> [--factor 4] [--axis 2]

Averages `factor` consecutive slices along NIfTI axis `axis` (simulating a 2D acquisition with thick
slices), sets the voxel size along that axis to factor x the original and shifts the affine origin to
the centre of each slab. With 1 mm input and factor 4 the network-order spacing is (1, 4, 1) mm:
max/min = 4 > 3, so nnU-Net resamples in-plane with cubic splines and along the slice axis with
nearest neighbour (order_z 0) — the code path the isotropic public data never reach.
"""
import argparse
import numpy as np
import nibabel as nib


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('inp')
    ap.add_argument('out')
    ap.add_argument('--factor', type=int, default=4)
    ap.add_argument('--axis', type=int, default=2)
    a = ap.parse_args()
    img = nib.load(a.inp)
    data = np.asarray(img.dataobj, dtype=np.float32)
    n = data.shape[a.axis] // a.factor
    data = np.take(data, range(n * a.factor), axis=a.axis)
    shape = list(data.shape)
    shape[a.axis] = n
    shape.insert(a.axis + 1, a.factor)
    thick = data.reshape(shape).mean(axis=a.axis + 1).astype(np.float32)
    affine = img.affine.copy()
    affine[:3, 3] += affine[:3, a.axis] * (a.factor - 1) / 2.0
    affine[:3, a.axis] *= a.factor
    out = nib.Nifti1Image(thick, affine)
    out.set_qform(affine, code=1)
    out.set_sform(affine, code=1)
    nib.save(out, a.out)
    print(a.out, thick.shape, out.header.get_zooms())


if __name__ == '__main__':
    main()
