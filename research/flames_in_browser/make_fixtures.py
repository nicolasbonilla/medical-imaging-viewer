"""Generate the reference fixtures that the TypeScript unit tests compare against.

    python -I make_fixtures.py <out.json>

Every expected value is computed by the ORIGINAL implementation (nnunetv2 2.8.1, scipy, skimage,
SimpleITK, nibabel), never by the TypeScript port, so the vitest suite checks the port against
nnU-Net itself on small synthetic volumes:

  new_shape   nnunetv2 compute_new_shape
  steps       nnunetv2 compute_steps_for_sliding_window
  gaussian    nnunetv2 compute_gaussian (float32 copy, normalised to max 1)
  resample    nnunetv2 resample_data_or_seg_to_shape (is_seg False; order 3 / 1; separate-z cases)
  crop        nnunetv2 create_nonzero_mask (binary_fill_holes) + get_bbox_from_mask
  zscore      nnunetv2 ZScoreNormalization(use_mask_for_norm=True)
  nifti_axes  NIfTI bytes written by nibabel, read by SimpleITK as nnU-Net does, transpose_forward [2,0,1]
"""
import base64, gzip, io, json, sys, tempfile, os

import numpy as np
import nibabel as nib
import SimpleITK as sitk
import torch
from nnunetv2.preprocessing.resampling.default_resampling import compute_new_shape, resample_data_or_seg_to_shape
from nnunetv2.inference.sliding_window_prediction import compute_gaussian, compute_steps_for_sliding_window
from nnunetv2.preprocessing.cropping.cropping import create_nonzero_mask, crop_to_nonzero
from nnunetv2.preprocessing.normalization.default_normalization_schemes import ZScoreNormalization

rng = np.random.default_rng(20261017)
TARGET = [1.0, 0.9000000059604645, 0.9000000059604645]


def flat(a):
    return [float(v) for v in np.asarray(a, dtype=np.float64).ravel(order='C')]


def resample_case(name, data, new_shape, cur_sp, new_sp, order):
    data = data.astype(np.float32)
    out = resample_data_or_seg_to_shape(data[None], new_shape, cur_sp, new_sp, is_seg=False, order=order, order_z=0,
                                        force_separate_z=None)[0]
    return {'name': name, 'shape': list(data.shape), 'new_shape': [int(v) for v in new_shape], 'spacing': list(cur_sp),
            'new_spacing': list(new_sp), 'order': order, 'input': flat(data), 'expected': flat(out.astype(np.float32))}


def main(out_path):
    fx = {}
    # --- compute_new_shape ------------------------------------------------------------------
    cases = [((182, 182, 218), (1, 1, 1), TARGET), ((140, 60, 175), (1.0, 3.0, 1.0), TARGET),
             ((256, 48, 256), (0.9375, 5.0, 0.9375), TARGET), ((5, 5, 5), (1, 1, 1), (2, 2, 2)),
             ((7, 9, 3), (0.5, 0.5, 0.5), (1, 1, 1)), ((161, 33, 177), (1.0, 1.2, 0.8), TARGET)]
    fx['new_shape'] = [{'shape': list(s), 'spacing': list(sp), 'new_spacing': list(ns),
                        'expected': [int(v) for v in compute_new_shape(s, sp, ns)]} for s, sp, ns in cases]
    # --- sliding window steps ----------------------------------------------------------------
    steps = []
    for size in [(112, 128, 160), (140, 175, 200), (169, 185, 217), (113, 300, 161), (224, 256, 320)]:
        steps.append({'image_size': list(size), 'tile': [112, 128, 160], 'step': 0.5,
                      'expected': [[int(v) for v in s] for s in compute_steps_for_sliding_window(size, (112, 128, 160), 0.5)]})
    fx['steps'] = steps
    # --- gaussian ------------------------------------------------------------------------------
    small = compute_gaussian((6, 8, 10), 1. / 8, 1, dtype=torch.float32, device=torch.device('cpu')).numpy()
    full = compute_gaussian((112, 128, 160), 1. / 8, 1, dtype=torch.float32, device=torch.device('cpu')).numpy()
    probes = [(56, 64, 80), (0, 0, 0), (111, 127, 159), (0, 64, 80), (56, 0, 80), (56, 64, 0), (30, 100, 7), (100, 3, 150)]
    fx['gaussian'] = {'small_patch': [6, 8, 10], 'small': flat(small / small.max()),
                      'full_patch': [112, 128, 160], 'full_probes': [{'at': list(p), 'value': float(full[p] / full.max())} for p in probes]}
    # --- resampling ---------------------------------------------------------------------------
    smooth = rng.standard_normal((7, 9, 11)).astype(np.float32)
    step = np.zeros((9, 10, 12), np.float32)
    step[:, 4:, :] = 3.0
    step[3:6, :, 5:] -= 1.5
    fx['resample'] = [
        resample_case('iso_up_order3', smooth, (8, 10, 12), (1, 1, 1), TARGET, 3),
        resample_case('iso_down_order3', rng.standard_normal((12, 10, 9)), (9, 8, 7), (1, 1, 1), (1.3, 1.25, 1.3), 3),
        resample_case('step_clip_order3', step, (11, 13, 15), (1, 1, 1), TARGET, 3),
        resample_case('sepz_axis1_order3', rng.standard_normal((6, 5, 8)), tuple(compute_new_shape((6, 5, 8), (1, 4, 1), TARGET)), (1, 4, 1), TARGET, 3),
        resample_case('sepz_axis0_order3', rng.standard_normal((4, 7, 6)), tuple(compute_new_shape((4, 7, 6), (5, 1, 1.1), TARGET)), (5, 1, 1.1), TARGET, 3),
        resample_case('iso_order1', rng.standard_normal((10, 11, 12)), (9, 12, 13), TARGET, (1.1, 0.83, 0.83), 1),
        resample_case('sepz_back_order1', rng.standard_normal((6, 22, 9)), (6, 5, 8), TARGET, (1, 4, 1), 1),
        resample_case('ratio_exactly_3_not_sepz', rng.standard_normal((5, 4, 6)), (5, 13, 7), (1, 3, 1), TARGET, 3),
    ]
    # --- crop_to_nonzero with hole filling --------------------------------------------------------
    vol = np.zeros((12, 11, 10), np.float32)
    vol[2:10, 2:9, 1:8] = rng.uniform(1, 5, (8, 7, 7))
    vol[3:5, 3:5, 3:5] = 0            # enclosed cavity A -> filled by binary_fill_holes
    vol[6:8, 5:7, 4:6] = 0            # cavity B ...
    vol[6, 5, 0:4] = 0                # ... connected to the z=0 face by a 1-voxel tunnel -> stays background
    vol[8, 7, 6] = 0                  # single enclosed voxel -> filled
    nz = create_nonzero_mask(vol[None])
    _, seg, bbox = crop_to_nonzero(vol[None])
    fx['crop'] = {'shape': list(vol.shape), 'input': flat(vol), 'nonzero_filled': [int(v) for v in nz.ravel()],
                  'bbox': [[int(a), int(b)] for a, b in bbox]}
    # --- z-score ------------------------------------------------------------------------------------
    img = rng.uniform(0, 400, (5, 6, 7)).astype(np.float32)
    mask = rng.uniform(0, 1, (5, 6, 7)) > 0.3
    img[~mask] = 0
    seg = np.where(mask, 0, -1).astype(np.int8)[None]
    norm = ZScoreNormalization(use_mask_for_norm=True, intensityproperties={}, target_dtype=np.float32).run(img.copy(), seg[0])
    fx['zscore'] = {'shape': list(img.shape), 'input': flat(img), 'mask': [int(v) for v in mask.ravel()], 'expected': flat(norm)}
    # --- NIfTI axis order through SimpleITK (as nnU-Net reads) -------------------------------------
    nifti_cases = []
    with tempfile.TemporaryDirectory() as d:
        for name, dtype, slope, inter, gz, affine in [
            ('float32_las', np.float32, None, None, True, np.diag([-1.0, 1.0, 1.0, 1.0])),
            ('int16_scaled_oblique', np.int16, 2.0, 10.0, False, np.array([[0, 0, 1.5, -20], [-0.9, 0, 0, 30], [0, 1.2, 0, -5], [0, 0, 0, 1]], float)),
            ('uint8_ras', np.uint8, None, None, True, np.diag([0.8, 0.8, 3.0, 1.0])),
        ]:
            dims = (4, 5, 6)
            arr = (np.arange(np.prod(dims)).reshape(dims, order='F') % 97 + 1).astype(dtype)
            img = nib.Nifti1Image(arr, affine)
            img.set_qform(affine, code=1)
            img.set_sform(affine, code=1)
            if slope is not None:
                img.header.set_slope_inter(slope, inter)
            path = os.path.join(d, name + ('.nii.gz' if gz else '.nii'))
            nib.save(img, path)
            raw = open(path, 'rb').read()
            itk = sitk.ReadImage(path)
            npy = sitk.GetArrayFromImage(itk).astype(np.float32)          # (k, j, i)
            network = npy.transpose(2, 0, 1)                                # transpose_forward [2,0,1] -> (i, k, j)
            spacing_net = [list(itk.GetSpacing())[::-1][i] for i in (2, 0, 1)]
            nibdata = np.asarray(nib.load(path).get_fdata(), np.float32)   # (i, j, k)
            nifti_cases.append({
                'name': name, 'bytes_b64': base64.b64encode(raw).decode(), 'dims': list(dims),
                'expected_network': flat(network), 'expected_network_shape': list(network.shape),
                'expected_network_spacing': spacing_net,
                'expected_nifti_order': flat(nibdata.ravel(order='F')),
                'expected_app_order': flat(nibdata.transpose(2, 0, 1)),     # backend RC-031: m = img.transpose(2,0,1)
                'expected_affine': [[float(v) for v in row] for row in nib.load(path).affine],
                'zooms': [float(z) for z in nib.load(path).header.get_zooms()[:3]],
            })
    fx['nifti_axes'] = nifti_cases
    fx['generator'] = {'nnunetv2': __import__('nnunetv2').__version__ if hasattr(__import__('nnunetv2'), '__version__') else '2.8.1',
                       'numpy': np.__version__, 'scipy': __import__('scipy').__version__,
                       'skimage': __import__('skimage').__version__, 'SimpleITK': sitk.Version_VersionString(),
                       'nibabel': nib.__version__}
    with open(out_path, 'w') as f:
        json.dump(fx, f, separators=(',', ':'))
    print(out_path, os.path.getsize(out_path), 'bytes')


if __name__ == '__main__':
    main(sys.argv[1])
