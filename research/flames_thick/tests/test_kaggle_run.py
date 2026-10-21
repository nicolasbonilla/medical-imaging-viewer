"""Kaggle port (research/flames_thick/kaggle_run): session plans, generated kernel, data subset rules."""
import base64
import hashlib
import io
import json
import os
import sys
import tarfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "kaggle_run"))
import push  # noqa: E402
import prepare_datasets as prep  # noqa: E402


def test_pilot_first_session_tests_kill_and_hand_over_second_does_not():
    s1, s2 = push.session_config("pilot-s1"), push.session_config("pilot-s2")
    for cfg in (s1, s2):
        assert cfg["accelerator"] == "NvidiaTeslaT4" and cfg["soft_hours"] < cfg["hard_hours"] <= 1.5
        assert [(r["arm"], r["gpu"]) for r in cfg["runs"]] == [("thick", 0), ("ft", 1)]
        assert all(r["env"]["FT_CASE_IDS"] == push.PILOT_CASES for r in cfg["runs"])
    thick1, ft1 = s1["runs"][0]["env"], s1["runs"][1]["env"]
    assert thick1["FT_KILL_TEST_AFTER_EPOCH"] == 0 and "FT_KILL_TEST_AFTER_EPOCH" not in ft1
    assert thick1["FT_PAUSE_AFTER_EPOCH"] == ft1["FT_PAUSE_AFTER_EPOCH"] == 1
    assert not any(k in r["env"] for r in s2["runs"] for k in ("FT_KILL_TEST_AFTER_EPOCH", "FT_PAUSE_AFTER_EPOCH"))
    # timing needs steady epochs after the warm-up of each session
    assert s2["runs"][0]["env"]["FT_EPOCHS"] - 1 - thick1["FT_PAUSE_AFTER_EPOCH"] >= 3


def test_full_sessions_run_both_arms_identically_except_the_augmentation():
    with pytest.raises(SystemExit):
        push.session_config("full-s1")
    cfg = push.session_config("full-s2", epochs=250)
    a, b = cfg["runs"]
    assert (a["run_id"], a["arm"], b["run_id"], b["arm"]) == ("flames-thick-a", "thick", "flames-thick-b", "ft")
    assert a["env"] == b["env"] == {"FT_EPOCHS": 250}                    # pre-registered schedule otherwise
    assert cfg["soft_hours"] < cfg["hard_hours"] < 12                    # Kaggle's session limit is 12 h
    assert "FT_CASE_IDS" not in a["env"] and "FT_LOCAL_TEST_PATCH" not in a["env"]


def test_smoke_is_cpu_only():
    cfg = push.session_config("smoke-s1")
    assert cfg["accelerator"] is None and cfg["runs"][0]["env"]["FT_DEVICE"] == "cpu"


def test_generated_kernel_is_private_with_only_the_two_datasets_and_the_committed_code(tmp_path):
    cfg, meta = push.build("pilot-s2", "pilot-s1", None, True, str(tmp_path))
    assert meta["is_private"] is True and meta["enable_internet"] is True and meta["enable_gpu"] is True
    assert meta["dataset_sources"] == push.DATASETS and len(push.DATASETS) == 2
    assert meta["kernel_sources"] == ["nicolasbonilna/mstool-research-flames-thick-pilot-s1"]
    assert meta["id"].endswith("/mstool-research-flames-thick-pilot-s2") and meta["title"].startswith("MSTool research")
    src = open(tmp_path / "kernel_main.py", encoding="utf-8").read()
    compile(src, "kernel_main.py", "exec")
    assert "__CONFIG_JSON__" not in src and "__CODE_B64__" not in src
    start = src.index("CONFIG = json.loads(r'''") + len("CONFIG = json.loads(r'''")
    embedded = json.loads(src[start:src.index("''')", start)])
    assert embedded["previous_kernel"] == meta["kernel_sources"][0] and embedded["code_sha256"] == cfg["code_sha256"]
    blob = base64.b64decode(src.split('CODE_B64 = "', 1)[1].split('"', 1)[0])
    assert hashlib.sha256(blob).hexdigest() == cfg["code_sha256"]
    names = tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz").getnames()
    assert "flames_thick/vertex_entry.py" in names and "flames_thick/requirements-gpu.lock" in names
    assert blob[:2] == b"\x1f\x8b" and blob[4:8] == b"\x00\x00\x00\x00"   # gzip mtime 0: reproducible bundle
    assert push.code_bundle(True)[1] == cfg["code_sha256"]


def test_subset_keeps_bytes_on_kaggle_and_cites_the_licences():
    assert prep.SUBSET.endswith(".bin")                               # Kaggle expands .zip and gunzips .nii.gz
    assert "CC BY 4.0" in prep.FLAMES_NOTICE and "17955359" in prep.FLAMES_NOTICE
    assert "CC BY 4.0" in prep.MSLESSEG_NOTICE and "Guarnera" in prep.MSLESSEG_NOTICE
    assert "P54-P75" in prep.MSLESSEG_NOTICE and "NOT included" in prep.MSLESSEG_NOTICE


def test_session_record_becomes_a_zero_cost_kaggle_ledger_row(tmp_path, monkeypatch):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "cloud"))
    import build_ledger as bl
    import ledger_rows as lr
    rec = {"session": "full-s1", "session_id": "full-s1-20261022T000000Z", "kernel": "o/k", "previous_kernel": None,
           "start_utc": "2026-10-22T00:00:00Z", "end_utc": "2026-10-22T11:00:00Z", "wall_seconds": 39600.0,
           "gpu_hours": 11.0, "purpose": "p", "errors": [], "venv_python": "3.10.12", "torch": "2.14.1+cu126 12.6 True 1 [x]",
           "machine": {"gpus": ["0, Tesla T4, 15360 MiB, 560.35, 00000000:00:04.0",
                                "1, Tesla T4, 15360 MiB, 560.35, 00000000:00:05.0"],
                       "accelerator_requested": "NvidiaTeslaT4", "vcpus": 4, "memory_gb": "31", "cpu_model": "Xeon"},
           "runs": {"flames-thick-a": {"epochs_this_session": 150, "epochs_done_at_start": 0, "epochs_done_at_end": 150,
                                       "median_s_per_epoch": 250.0, "state_at_end": "paused"},
                    "flames-thick-b": {"epochs_this_session": 152, "epochs_done_at_start": 0, "epochs_done_at_end": 152,
                                       "median_s_per_epoch": 248.0, "state_at_end": "paused"}}}
    row = lr.row(rec)
    assert row["status"] == "ok" and row["gpu"].startswith("2 × Tesla T4") and row["run_id"] == "kaggle-full-s1"
    out = tmp_path / "ledger"
    out.mkdir()
    import csv
    with open(out / "kaggle_runs.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=lr.COLUMNS)
        w.writeheader()
        w.writerow(row)
    monkeypatch.setattr(bl, "OUT", str(out))
    (r,) = bl.kaggle_rows()
    assert r["cost_usd_list"] == 0 and r["vm_hours"] == 11.0 and r["project"] == bl.KAGGLE_PROJECT
    assert r["provisioning"] == "Kaggle free quota" and r["_kind"] == "training"
    rec["runs"]["flames-thick-a"]["state_at_end"] = "failed"
    assert lr.row(rec)["status"] == "failed"


def test_manifest_reference_hashes_must_agree(tmp_path):
    json.dump({"inputs_sha256": {"mslesseg_P1_T1": "a" * 64}}, open(tmp_path / "x.json", "w"))
    assert prep.manifest_flair_sha(str(tmp_path)) == {"mslesseg_P1_T1": "a" * 64}
    json.dump({"inputs_sha256": {"mslesseg_P1_T1": "b" * 64}}, open(tmp_path / "y.json", "w"))
    with pytest.raises(SystemExit):
        prep.manifest_flair_sha(str(tmp_path))
