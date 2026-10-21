"""GPU sanity check on Kaggle: the UNCHANGED FLAMeS fold 0 predicts one MSLesSeg-TRAIN scan on the GPU.

Same predictor settings as the reference maps of Paper A (tile step 0.5, Gaussian weighting, no
mirroring), only the device differs (GPU, autocast). The probability map is saved so it can be
compared voxel by voxel with the CPU reference map (data/cohorts/cloud-2026-10/flames/<case>_f0_prob)
and the Dice against the expert mask is recorded. Run with the venv python inside a Kaggle session:

    python gpu_sanity.py <flames_dir> <mslesseg_train.zip.bin> <case_id> <out_dir>
"""
import json
import os
import shutil
import sys
import time
import zipfile

import nibabel as nib
import numpy as np
import torch

from flames_thick import data_prep as dp


def main(flames_dir, zip_path, case, out_dir):
    dp.assert_trainable(case)                                   # train scans only, never an evaluation site
    work = os.path.join(out_dir, "_sanity_tmp")
    os.makedirs(work, exist_ok=True)
    model = os.path.join(work, dp.FLAMES_DATASET, dp.FLAMES_MODEL)
    os.makedirs(os.path.join(model, "fold_0"), exist_ok=True)
    for f in ("plans.json", "dataset.json", "dataset_fingerprint.json"):
        shutil.copyfile(os.path.join(flames_dir, f), os.path.join(model, f))
    shutil.copyfile(os.path.join(flames_dir, "fold_0__checkpoint_final.pth"), os.path.join(model, "fold_0", "checkpoint_final.pth"))
    with zipfile.ZipFile(zip_path) as zf:
        m = dp.train_members(zf.namelist())[case]
        paths = {}
        for k in ("flair", "mask"):
            paths[k] = os.path.join(work, f"{case}_{k}.nii.gz")
            with zf.open(m[k]) as s, open(paths[k], "wb") as d:
                shutil.copyfileobj(s, d)
    from nnunetv2.imageio.simpleitk_reader_writer import SimpleITKIO
    from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")      # cpu: local test of this script only
    pred = nnUNetPredictor(tile_step_size=0.5, use_gaussian=True, use_mirroring=False,
                           perform_everything_on_device=dev.type == "cuda", device=dev, verbose=False,
                           verbose_preprocessing=False, allow_tqdm=False)
    pred.initialize_from_trained_model_folder(model, use_folds=(0,), checkpoint_name="checkpoint_final.pth")
    img, props = SimpleITKIO().read_images([paths["flair"]])
    t0 = time.time()
    _seg, prob = pred.predict_single_npy_array(img, props, None, None, True)
    secs = time.time() - t0
    p = np.asarray(prob[1], dtype=np.float32).transpose(2, 1, 0)          # SimpleITK (z, y, x) -> nibabel (x, y, z)
    fl = nib.load(paths["flair"])
    gt = np.asarray(nib.load(paths["mask"]).dataobj, dtype=np.float32) > 0.5
    if p.shape != gt.shape:
        raise RuntimeError(f"map {p.shape} != mask {gt.shape}")
    b = p >= 0.5
    hdr = fl.header.copy()
    hdr.set_data_dtype(np.float32)
    hdr.set_slope_inter(1, 0)
    out_map = os.path.join(out_dir, f"{case}_gpu_f0_prob.nii.gz")
    nib.save(nib.Nifti1Image(p, fl.affine, hdr), out_map)
    res = {"case": case, "device": torch.cuda.get_device_name() if dev.type == "cuda" else "cpu", "seconds": round(secs, 1),
           "settings": "tile 0.5, gaussian, no mirroring, fold 0 checkpoint_final (unchanged FLAMeS)",
           "dice": round(float(2 * (b & gt).sum() / max(1, b.sum() + gt.sum())), 4),
           "n_pred_voxels": int(b.sum()), "n_ref_voxels": int(gt.sum()), "map": os.path.basename(out_map)}
    json.dump(res, open(os.path.join(out_dir, f"{case}_gpu_sanity.json"), "w"), indent=1)
    shutil.rmtree(work, ignore_errors=True)
    print(json.dumps(res), flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:5])
