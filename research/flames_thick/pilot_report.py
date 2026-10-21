"""Pilot pass/fail + full-run projection from a finished pilot (RUNBOOK.md §3). Local, read-only.

    gcloud storage cp -r gs://mstool-research-data/flames-thick/manifests/flames-thick-pilot-t4.json \
        gs://mstool-research-data/runs/flames-thick-pilot-t4/plan.json <dir>/
    python research/flames_thick/pilot_report.py <dir>/flames-thick-pilot-t4.json <dir>/plan.json [--other <a100 pair>]

Projection (pre-registered, PROTOCOL §5.2): epoch_s = 250 x train_s/iter + 50 x val_s/iter, from the
pilot epochs after the first (warm-up); USD/epoch = epoch_s/3600 x catalogue USD/h; epochs = 300 unless
300 x USD/epoch x 1.15 > 15 USD, then floor(15 / (USD/epoch x 1.15)), never below 150.
"""
import argparse
import json
import math
import statistics
import sys

FULL_ITERS, FULL_VAL_ITERS, EPOCHS, CAP_USD, SAFETY, MIN_EPOCHS = 250, 50, 300, 15.0, 1.15, 150


def projection(manifest, plan):
    eps = [e for e in manifest.get("epochs", []) if e.get("train_seconds") and e["epoch"] >= 1]
    if not eps:
        raise SystemExit("no timed epoch after the first one in the pilot manifest")
    t_it = statistics.median(e["train_seconds"] / e["iters"] for e in eps)
    t_val = statistics.median(e["val_seconds"] / e["val_iters"] for e in eps)
    epoch_s = FULL_ITERS * t_it + FULL_VAL_ITERS * t_val
    rate = plan["list_price"]["usd_per_hour"]
    usd_epoch = epoch_s / 3600 * rate
    epochs = EPOCHS if EPOCHS * usd_epoch * SAFETY <= CAP_USD else max(MIN_EPOCHS, math.floor(CAP_USD / (usd_epoch * SAFETY)))
    return {"run_id": manifest.get("run_id"), "gpu": plan.get("gpu"), "machine_type": plan.get("machine_type"),
            "train_s_per_iter": round(t_it, 3), "val_s_per_iter": round(t_val, 3), "epoch_s_projected": round(epoch_s, 1),
            "usd_per_hour_list": rate, "usd_per_epoch_list": round(usd_epoch, 5), "epochs": epochs,
            "hours_per_arm": round(epochs * epoch_s / 3600, 2), "usd_per_arm_list": round(epochs * usd_epoch, 2),
            "usd_per_arm_guard": round(epochs * usd_epoch * SAFETY, 2)}


def checks(manifest):
    out = {}
    out["status_completed"] = manifest.get("status") == "completed"
    out["no_errors"] = not manifest.get("errors")
    init = manifest.get("init_source") or {}
    kt = manifest.get("kill_test")
    out["kill_test_ok"] = (kt is None) or bool(kt.get("ok"))
    out["flames_checkpoint_sha_ok"] = (manifest.get("inputs", {}).get("flames_fold0_checkpoint_sha256")
                                       == "4fc7db24e7c1541b59023df2a2f498a964eb629fe38f4eaec763297dd3fdf861")
    out["mslesseg_zip_is_the_figshare_file"] = bool(manifest.get("inputs", {}).get("mslesseg_zip", {})
                                                    .get("matches_figshare_size"))
    out["only_mslesseg_train"] = all(c.startswith("mslesseg_P") and "_T" in c for c in manifest.get("training_cases", {}))
    th = manifest.get("thick_augmentation") or {}
    out["axial_axis_is_1"] = (manifest.get("arm") != "thick") or (th.get("axis_map", {}).get("axial") == 1)
    out["model_exported"] = bool(manifest.get("inputs", {}).get("model_export", {}).get("sha256"))
    out["gpu_selftest"] = bool((manifest.get("hardware") or {}).get("selftest", {}).get("device_name"))
    out["resumed_kind"] = init.get("kind")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("plan")
    ap.add_argument("--other", nargs=2, metavar=("MANIFEST", "PLAN"), help="a second pilot (e.g. A100) to compare")
    a = ap.parse_args(argv)
    m, p = json.load(open(a.manifest)), json.load(open(a.plan))
    res = {"checks": checks(m), "projection": projection(m, p)}
    if a.other:
        m2, p2 = json.load(open(a.other[0])), json.load(open(a.other[1]))
        res["other"] = {"checks": checks(m2), "projection": projection(m2, p2)}
        u1, u2 = res["projection"]["usd_per_epoch_list"], res["other"]["projection"]["usd_per_epoch_list"]
        # pre-registered: the other GPU only if >15 % cheaper per epoch (ties go to the T4: capacity)
        res["choice"] = res["other"]["projection"] if u2 < 0.85 * u1 else res["projection"]
    else:
        res["choice"] = res["projection"]
    res["pass"] = all(v for k, v in res["checks"].items() if k != "resumed_kind")
    print(json.dumps(res, indent=1))
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
