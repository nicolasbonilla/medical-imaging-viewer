"""Pilot projection and the pre-registered GPU / epoch decision rule."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from flames_thick import pilot_report as pr  # noqa: E402


def manifest(train_s_per_iter, val_s_per_iter, iters=40, val_iters=10, gpu="Tesla T4"):
    eps = [{"epoch": e, "train_seconds": train_s_per_iter * iters * (3 if e == 0 else 1),
            "val_seconds": val_s_per_iter * val_iters, "iters": iters, "val_iters": val_iters} for e in range(3)]
    return {"run_id": "p", "status": "completed", "errors": [], "arm": "thick", "epochs": eps,
            "init_source": {"kind": "checkpoint", "resumed_at_epoch": 1},
            "kill_test": {"killed_after_epoch": 0, "resumed_at_epoch": 1, "ok": True},
            "inputs": {"flames_fold0_checkpoint_sha256": "4fc7db24e7c1541b59023df2a2f498a964eb629fe38f4eaec763297dd3fdf861",
                       "model_export": {"sha256": "x"}, "mslesseg_zip": {"matches_figshare_size": True}},
            "training_cases": {"mslesseg_P1_T1": {}, "mslesseg_P2_T1": {}},
            "thick_augmentation": {"axis_map": {"axial": 1, "coronal": 2, "sagittal": 0}},
            "hardware": {"selftest": {"device_name": gpu}}}


def plan(rate, gpu="nvidia-tesla-t4:1"):
    return {"gpu": gpu, "machine_type": "n1-standard-8", "list_price": {"usd_per_hour": rate}}


def test_projection_uses_post_warmup_epochs_and_full_iterations():
    p = pr.projection(manifest(0.9, 0.3), plan(0.42756))
    assert p["epoch_s_projected"] == round(250 * 0.9 + 50 * 0.3, 1) == 240.0
    assert p["epochs"] == 300 and abs(p["usd_per_arm_list"] - 300 * 240 / 3600 * 0.42756) < 0.01


def test_epochs_reduced_when_300_would_exceed_the_cap():
    p = pr.projection(manifest(1.6, 0.5), plan(0.42756))          # ~425 s/epoch -> 15.1 USD with factor
    assert p["epochs"] < 300 and p["epochs"] >= 150
    assert p["usd_per_arm_guard"] <= 15.0


def test_checks_and_gpu_choice(tmp_path):
    for name, obj in (("t4.json", manifest(0.9, 0.3)), ("t4plan.json", plan(0.42756)),
                      ("a.json", manifest(0.25, 0.08, gpu="A100")), ("aplan.json", plan(2.2273, "nvidia-tesla-a100:1"))):
        json.dump(obj, open(tmp_path / name, "w"))
    rc = pr.main([str(tmp_path / "t4.json"), str(tmp_path / "t4plan.json"),
                  "--other", str(tmp_path / "a.json"), str(tmp_path / "aplan.json")])
    assert rc == 0
    t4 = pr.projection(manifest(0.9, 0.3), plan(0.42756))["usd_per_epoch_list"]
    a = pr.projection(manifest(0.25, 0.08), plan(2.2273))["usd_per_epoch_list"]
    assert a > 0.85 * t4                                          # A100 not >15 % cheaper -> T4 kept
    bad = manifest(0.9, 0.3)
    bad["training_cases"]["ms3seg_001"] = {}
    assert pr.checks(bad)["only_mslesseg_train"] is False
