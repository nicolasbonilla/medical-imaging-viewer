"""Compare binary lesion masks on the same grid: Dice, differing voxels, 26-connected lesion counts, volumes.

    python -I compare_masks.py name=<mask.nii.gz> name=<mask.nii.gz|mask.u8> ... [--ref-geometry <any.nii.gz>]

A `.u8` file is the raw uint8 NIfTI-order mask written by the TypeScript parity harness; it takes its
shape from --ref-geometry. Every pair is compared; output is JSON.
"""
import argparse, itertools, json
import numpy as np
import nibabel as nib
from scipy import ndimage


def load(path, geometry):
    if path.endswith('.u8'):
        img = nib.load(geometry)
        data = np.fromfile(path, dtype=np.uint8).reshape(img.shape[:3], order='F')
        return data > 0, img.header.get_zooms()[:3]
    img = nib.load(path)
    return np.asarray(img.dataobj) > 0.5, img.header.get_zooms()[:3]


def describe(mask, zooms):
    _, n = ndimage.label(mask, structure=np.ones((3, 3, 3)))
    return {'voxels': int(mask.sum()), 'lesions': int(n), 'volume_ml': float(mask.sum() * np.prod(zooms) / 1000)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('masks', nargs='+')
    ap.add_argument('--ref-geometry')
    a = ap.parse_args()
    masks = {}
    for item in a.masks:
        name, path = item.split('=', 1)
        masks[name] = load(path, a.ref_geometry)
    out = {'masks': {k: describe(m, z) for k, (m, z) in masks.items()}, 'pairs': {}}
    for (na, (ma, _)), (nb, (mb, _)) in itertools.combinations(masks.items(), 2):
        inter = np.logical_and(ma, mb).sum()
        denom = ma.sum() + mb.sum()
        out['pairs'][f'{na}~{nb}'] = {'dice': float(2 * inter / denom) if denom else 1.0,
                                      'differing_voxels': int(np.logical_xor(ma, mb).sum())}
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
