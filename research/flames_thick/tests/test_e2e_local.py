"""End-to-end run of the training job on the local CPU with a local folder as the bucket.

Exercises exactly the container code path (supervisor + worker, real nnU-Net 2.8.1, real FLAMeS
fold-0 weights, real MSLesSeg scans): input mirrors with SHA-256 sidecars, MSLesSeg-train-only
dataset, FLAMeS plans transfer, preprocessing, strict FLAMeS init, thick-slice augmentation inside
nnU-Net's pipeline, checkpoint upload, SIGKILL of the worker after a checkpoint and resume from the
"bucket" by a fresh worker, final validation, model export, ledger records, then the cost guard.

Opt-in (slow, ~10-20 min on a laptop CPU):
    FLAMES_THICK_E2E_CKPT=<fold_0/checkpoint_final.pth of FLAMeS>
    FLAMES_THICK_E2E_MSLESSEG=<folder containing train/ and test/ of MSLesSeg>
    python -m pytest research/flames_thick/tests/test_e2e_local.py -q -s
"""
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import zipfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
RESEARCH = os.path.dirname(os.path.dirname(HERE))
CKPT = os.environ.get("FLAMES_THICK_E2E_CKPT", "")
MSL = os.environ.get("FLAMES_THICK_E2E_MSLESSEG", "")
pytestmark = pytest.mark.skipif(not (os.path.isfile(CKPT) and os.path.isdir(MSL)),
                                reason="set FLAMES_THICK_E2E_CKPT and FLAMES_THICK_E2E_MSLESSEG to run")
MODEL = "Dataset004_WML/nnUNetTrainer_8000epochs__nnUNetPlans__3d_fullres"


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def mirror(store, name, path):
    dst = os.path.join(store, "inputs", name)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    os.replace(path, dst)
    open(dst + ".sha256", "w").write(sha(dst) + "\n")


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    root = tmp_path_factory.mktemp("e2e")
    st = os.path.join(root, "bucket")
    z = os.path.join(root, "flames_weights.zip")
    with zipfile.ZipFile(z, "w", zipfile.ZIP_STORED) as zf:
        zf.write(os.path.join(HERE, "fixtures", "flames_plans.json"), f"{MODEL}/plans.json")
        zf.write(os.path.join(HERE, "fixtures", "flames_dataset.json"), f"{MODEL}/dataset.json")
        zf.writestr(f"{MODEL}/dataset_fingerprint.json", "{}")
        zf.write(CKPT, f"{MODEL}/fold_0/checkpoint_final.pth")
    mirror(st, "flames_weights.zip", z)
    z = os.path.join(root, "mslesseg.zip")
    with zipfile.ZipFile(z, "w", zipfile.ZIP_STORED) as zf:
        for p in (1, 2, 3):
            for kind in ("FLAIR", "MASK"):
                zf.write(os.path.join(MSL, "train", f"P{p}", "T1", f"P{p}_T1_{kind}.nii.gz"),
                         f"MSLesSeg Dataset/train/P{p}/T1/P{p}_T1_{kind}.nii.gz")
        for kind in ("FLAIR", "MASK"):                      # a test scan in the zip must never be used
            zf.write(os.path.join(MSL, "test", "P54", f"P54_{kind}.nii.gz"), f"MSLesSeg Dataset/test/P54/P54_{kind}.nii.gz")
    mirror(st, "mslesseg_52771814.zip", z)
    return root


def run_job(root, run_id, **extra):
    env = dict(os.environ)
    scripts = os.path.dirname(sys.executable)
    env.update({"PYTHONPATH": RESEARCH, "PATH": scripts + os.pathsep + env.get("PATH", ""),
                "FT_STORE": "local:" + os.path.join(root, "bucket"), "FT_RUN_ID": run_id, "FT_ARM": "thick",
                "FT_RATE_USD_PER_H": "0.43", "FT_MAX_COST_USD": "5", "FT_MAX_HOURS": "5", "FT_DEVICE": "cpu",
                "FT_WORKDIR": os.path.join(root, "w_" + run_id), "FT_NPROC": "2",
                "FT_CASE_IDS": "mslesseg_P1_T1 mslesseg_P2_T1 mslesseg_P3_T1",
                "FT_EPOCHS": "3", "FT_ITERS": "2", "FT_VAL_ITERS": "1", "FT_SAVE_EVERY": "1", "FT_WARMUP_EPOCHS": "1",
                # a 16-GB laptop cannot back-propagate the real 112x128x160 patch on CPU (allocation failure
                # inside oneDNN); the plumbing is identical with a smaller patch (refused on GPU)
                "FT_LOCAL_TEST_PATCH": "64,64,64",
                "nnUNet_n_proc_DA": "0", "nnUNet_compile": "f", "FT_MACHINE_TYPE": "local-cpu", "FT_GPU": "none"})
    for k in ("nnUNet_raw", "nnUNet_preprocessed", "nnUNet_results"):
        env.pop(k, None)
    env.update(extra)
    r = subprocess.run([sys.executable, "-m", "flames_thick.vertex_entry"], env=env, capture_output=True, text=True,
                       timeout=3600)
    print(r.stdout[-6000:], r.stderr[-3000:])
    return r


def load(root, name):
    return json.load(open(os.path.join(root, "bucket", *name.split("/")), encoding="utf-8"))


def test_full_job_with_kill_and_resume(store):
    r = run_job(store, "e2e-thick", FT_KILL_TEST_AFTER_EPOCH="0")
    assert r.returncode == 0
    status = load(store, "flames-thick/train/e2e-thick/status.json")
    assert status["state"] == "completed"
    man = load(store, "flames-thick/manifests/e2e-thick.json")
    assert man["kill_test"]["killed_after_epoch"] == 0 and man["kill_test"]["resumed_at_epoch"] == 1
    assert man["kill_test"]["ok"] is True
    assert sorted(man["training_cases"]) == ["mslesseg_P1_T1", "mslesseg_P2_T1", "mslesseg_P3_T1"]
    assert man["inputs"]["flames_fold0_checkpoint_sha256"] == "4fc7db24e7c1541b59023df2a2f498a964eb629fe38f4eaec763297dd3fdf861"
    assert man["thick_augmentation"]["axis_map"] == {"axial": 1, "coronal": 2, "sagittal": 0}
    assert [c["case"] for c in man["cases"]] == ["epoch_0000", "epoch_0001", "epoch_0002"]
    assert man["split"]["val"] and not set(man["split"]["val"]) & set(man["split"]["train"])
    info = load(store, "runs/e2e-thick/runinfo.json")
    assert info["wall_seconds"] > 0 and "train_start" in info["stages_utc"] and info["status"] == "completed"
    cost = open(os.path.join(store, "bucket", "flames-thick", "cost", "e2e-thick.txt")).read()
    assert cost.startswith("COST_RECORD,run_id=e2e-thick")
    tar = os.path.join(store, "bucket", "flames-thick", "train", "e2e-thick", "model.tar.gz")
    assert open(tar + ".sha256").read().strip() == sha(tar)
    names = tarfile.open(tar).getnames()
    top = "Dataset501_MSLesSegFT/nnUNetTrainerFLAMeSThick__nnUNetPlans__3d_fullres"
    for f in ("plans.json", "dataset.json", "NOTICE.txt", "fold_0/checkpoint_final.pth", "fold_0/validation/summary.json"):
        assert f"{top}/{f}" in names
    raw = os.path.join(store, "w_e2e-thick", "nnunet_raw", "Dataset501_MSLesSegFT", "imagesTr")
    assert not any("P54" in f for f in os.listdir(raw))
    # a second launch of a completed run does nothing
    assert run_job(store, "e2e-thick").returncode == 0


def test_exported_model_runs_through_the_evaluation_driver(store, monkeypatch):
    """The evaluation VM path: model.tar.gz -> nnU-Net predictor via nnUNet_extTrainer -> driver.save_prob."""
    pytest.importorskip("google.cloud.storage")
    tar = os.path.join(store, "bucket", "flames-thick", "train", "e2e-thick", "model.tar.gz")
    if not os.path.isfile(tar):
        pytest.skip("needs test_full_job_with_kill_and_resume first")
    dst = os.path.join(store, "eval_model")
    tarfile.open(tar).extractall(dst)
    folder = os.path.join(dst, "Dataset501_MSLesSegFT", "nnUNetTrainerFLAMeSThick__nnUNetPlans__3d_fullres")
    monkeypatch.setenv("nnUNet_extTrainer", os.path.join(RESEARCH, "flames_thick", "nnunet_ext"))
    monkeypatch.setenv("nnUNet_results", dst)
    monkeypatch.syspath_prepend(os.path.join(RESEARCH, "cloud"))
    monkeypatch.syspath_prepend(RESEARCH)
    import importlib
    import nnunetv2.paths
    importlib.reload(nnunetv2.paths)
    import nnunetv2.utilities.find_objects as fo
    importlib.reload(fo)
    import nnunetv2.inference.predict_from_raw_data as pfr
    importlib.reload(pfr)
    import torch
    import flames_ensemble_driver as drv
    assert drv.parse_models([f"ftA={folder}"]) == [("ftA", folder)]
    assert drv.out_name("ms3seg_001", 0, "ftA") == "ms3seg_001_ftA_f0_prob.nii.gz"
    assert drv.out_name("ms3seg_001", 0) == "ms3seg_001_f0_prob.nii.gz"
    from nnunetv2.imageio.simpleitk_reader_writer import SimpleITKIO
    pred = pfr.nnUNetPredictor(tile_step_size=0.5, use_gaussian=True, use_mirroring=False,
                               perform_everything_on_device=False, device=torch.device("cpu"),
                               verbose=False, verbose_preprocessing=False, allow_tqdm=False)
    pred.initialize_from_trained_model_folder(folder, use_folds=(0,), checkpoint_name="checkpoint_final.pth")
    assert pred.trainer_name == "nnUNetTrainerFLAMeSThick"
    flair = os.path.join(MSL, "test", "P54", "P54_FLAIR.nii.gz")
    img, props = SimpleITKIO().read_images([flair])
    _seg, prob = pred.predict_single_npy_array(img, props, None, None, True)
    out = os.path.join(store, "P54_ftA_f0_prob.nii.gz")
    drv.save_prob(prob[1], flair, out)
    import nibabel as nib
    import numpy as np
    m, f = nib.load(out), nib.load(flair)
    a = np.asarray(m.get_fdata())
    assert m.shape == f.shape and np.allclose(m.affine, f.affine) and 0 <= a.min() and a.max() <= 1.0
    assert (a >= 0.5).sum() > 0                                       # FLAMeS-initialised model finds lesions


def test_cost_guard_stops_cleanly_with_a_resumable_checkpoint(store):
    # 0.43 USD/h * 1.15: 300 s start-up allowance + 600 s reserve already cost ~0.124 USD
    r = run_job(store, "e2e-budget", FT_MAX_COST_USD="0.13", FT_RESERVE_S="600", FT_EPOCHS="50")
    assert r.returncode == 0
    status = load(store, "flames-thick/train/e2e-budget/status.json")
    assert status["state"] == "budget_stop" and "max_cost" in json.dumps(status)
    assert os.path.isfile(os.path.join(store, "bucket", "flames-thick", "train", "e2e-budget", "fold_0",
                                       "checkpoint_latest.pth"))
