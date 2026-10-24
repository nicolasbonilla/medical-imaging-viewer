"""Kaggle code path on the local CPU: inputs from the prepared dataset folders + session hand-over.

Session 1 reads FLAMeS and the MSLesSeg-train subset exactly as the Kaggle kernel mounts them
(kaggle_run/prepare_datasets.py output; every file checked against PROVENANCE.json), is SIGKILLed after
epoch 0 and resumed by a fresh worker, then PAUSES after epoch 1 (forced, like a session deadline).
Session 2 starts with a wiped work folder and only the store (= the previous kernel output), resumes at
epoch 2, finishes, validates and exports the model.

Opt-in (slow, ~10 min on a laptop CPU):
    FLAMES_THICK_E2E_KAGGLE_DATASETS=<folder with flames-fold0/ and mslesseg-train/>
    python -m pytest research/flames_thick/tests/test_e2e_kaggle_local.py -q -s
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
RESEARCH = os.path.dirname(os.path.dirname(HERE))
DS = os.environ.get("FLAMES_THICK_E2E_KAGGLE_DATASETS", "")
pytestmark = pytest.mark.skipif(not os.path.isdir(os.path.join(DS, "flames-fold0")),
                                reason="set FLAMES_THICK_E2E_KAGGLE_DATASETS to run")


def job(root, session, **extra):
    m = os.path.join(DS, "mslesseg-train")
    prov = json.load(open(os.path.join(m, "PROVENANCE.json")))
    env = {k: v for k, v in os.environ.items() if not k.startswith(("nnUNet_raw", "nnUNet_preprocessed", "nnUNet_results"))}
    env.update({"PYTHONPATH": RESEARCH, "PATH": os.path.dirname(sys.executable) + os.pathsep + env.get("PATH", ""),
                "FT_STORE": "local:" + os.path.join(root, "kernel_output", "store"), "FT_RUN_ID": "e2e-kaggle",
                "FT_ARM": "thick", "FT_INPUTS": "dir", "FT_FLAMES_DIR": os.path.join(DS, "flames-fold0"),
                "FT_MSLESSEG_ZIP": os.path.join(m, prov["subset_zip"]),
                "FT_MSLESSEG_PROVENANCE": os.path.join(m, "PROVENANCE.json"),
                "FT_RATE_USD_PER_H": "0", "FT_MAX_COST_USD": "1", "FT_SAFETY": "1", "FT_ATTEMPT_OVERHEAD_S": "0",
                "FT_MAX_HOURS": "5", "FT_RESERVE_S": "300", "FT_SESSION_RESERVE_S": "60",
                "FT_SESSION_DEADLINE_UTC": "2099-01-01T00:00:00Z", "FT_PLATFORM": "kaggle-kernel",
                "FT_PROVISIONING": "Kaggle free GPU quota", "FT_DEVICE": "cpu",
                "FT_WORKDIR": os.path.join(root, "w_" + session), "FT_NPROC": "2",
                "FT_CASE_IDS": "mslesseg_P1_T1 mslesseg_P2_T1", "FT_EPOCHS": "3", "FT_ITERS": "2", "FT_VAL_ITERS": "1",
                "FT_SAVE_EVERY": "1", "FT_WARMUP_EPOCHS": "1", "FT_LOCAL_TEST_PATCH": "64,64,64",
                "nnUNet_n_proc_DA": "0", "nnUNet_compile": "f", "FT_MACHINE_TYPE": "local-cpu", "FT_GPU": "none"})
    env.update(extra)
    r = subprocess.run([sys.executable, "-m", "flames_thick.vertex_entry"], env=env, capture_output=True, text=True,
                       timeout=3600)
    print(r.stdout[-5000:], r.stderr[-3000:])
    return r


def load(root, name):
    return json.load(open(os.path.join(root, "kernel_output", "store", *name.split("/")), encoding="utf-8"))


def test_kaggle_inputs_kill_pause_and_resume_in_a_new_session(tmp_path):
    root = str(tmp_path)
    r = job(root, "s1", FT_KILL_TEST_AFTER_EPOCH="0", FT_PAUSE_AFTER_EPOCH="1")
    assert r.returncode == 0
    st = load(root, "flames-thick/train/e2e-kaggle/status.json")
    assert st["state"] == "paused" and "forced pause after epoch 1" in st["pause"]["reason"]
    man = load(root, "flames-thick/manifests/e2e-kaggle.json")
    assert man["kill_test"]["ok"] is True and man["kill_test"]["resumed_at_epoch"] == 1
    assert [e["epoch"] for e in man["epochs"]] == [0, 1]
    assert man["inputs"]["mslesseg_zip"]["members_sha256_checked"] == 186
    assert man["inputs"]["mslesseg_zip"]["matches_figshare_size"] is True
    assert man["inputs"]["flames_fold0_checkpoint_sha256"].startswith("4fc7db24")
    assert man["platform"] == "kaggle-kernel" and man["status"] == "paused"
    assert sorted(man["training_cases"]) == ["mslesseg_P1_T1", "mslesseg_P2_T1"]

    shutil.rmtree(os.path.join(root, "w_s1"))                  # a new Kaggle session keeps only the store
    r = job(root, "s2")
    assert r.returncode == 0
    st = load(root, "flames-thick/train/e2e-kaggle/status.json")
    assert st["state"] == "completed"
    man = load(root, "flames-thick/manifests/e2e-kaggle.json")
    assert man["init_source"] == {"kind": "checkpoint", "resumed_at_epoch": 2}
    assert [e["epoch"] for e in man["epochs"]] == [0, 1, 2] and len(man["attempts"]) == 2
    assert man["inputs"]["model_export"]["sha256"]
    info = load(root, "runs/e2e-kaggle/runinfo.json")
    assert info["platform"] == "kaggle-kernel" and info["cost_usd_estimate_metadata"] == 0
    # a third session of a completed run does nothing
    assert job(root, "s3").returncode == 0
