"""Vertex AI pricing, CustomJob request (dry run, no cloud call) and ledger rows for training jobs."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import build_ledger as bl  # noqa: E402
import launch_vertex as lv  # noqa: E402
import pricing  # noqa: E402

SKUS = json.load(open(os.path.join(HERE, "fixtures", "ce_skus_us-central1_2026-10-18.json")))["skus"]
IMAGE = "us-central1-docker.pkg.dev/mstool-research/mstool-research-images/flames-thick@sha256:" + "0" * 64


def test_vertex_spot_prices_from_compute_engine_spot_skus():
    t4 = pricing.vertex_training_price("n1-standard-8", "us-central1", "NVIDIA_TESLA_T4", 1, True, 100, "pd-ssd", skus=SKUS)
    assert t4["usd_per_hour"] == pytest.approx(0.42756, abs=1e-5)
    assert t4["parts"]["gpu"]["sku_id"] == "1A25-07A3-AB6D" and t4["parts"]["gpu"]["usd"] == pytest.approx(0.1986)
    assert t4["parts"]["cores"]["description"].startswith("Spot Preemptible N1")
    a100 = pricing.vertex_training_price("a2-highgpu-1g", "us-central1", "NVIDIA_TESLA_A100", 1, True, 100, "pd-ssd", skus=SKUS)
    assert a100["usd_per_hour"] == pytest.approx(2.2273, abs=1e-4)
    v100 = pricing.vertex_training_price("n1-standard-8", "us-central1", "NVIDIA_TESLA_V100", 1, True, 100, "pd-ssd", skus=SKUS)
    assert v100["usd_per_hour"] == pytest.approx(1.69866, abs=1e-4)
    with pytest.raises(NotImplementedError):
        pricing.vertex_training_price("n1-standard-8", "us-central1", "NVIDIA_TESLA_T4", spot=False, skus=SKUS)


def test_cpu_eval_vm_price_matches_the_ledger():
    p = pricing.price("n2d-standard-4", "us-central1", False, None, 50, "pd-balanced", skus=SKUS)
    assert p["usd_per_hour"] == pytest.approx(0.17583, abs=1e-5)


def test_dry_run_writes_a_spot_customjob_with_guards(tmp_path, capsys):
    rc = lv.main(["--name", "flames-thick-pilot-t4", "--arm", "thick", "--image", IMAGE, "--max-hours", "1",
                  "--max-cost-usd", "0.5", "--purpose", "pilot", "--out-dir", str(tmp_path),
                  "--env", "FT_EPOCHS=4", "FT_ITERS=20", "FT_KILL_TEST_AFTER_EPOCH=1"])
    assert rc == 0
    req = json.load(open(tmp_path / "flames-thick-pilot-t4" / "customjob_request.json"))
    spec = req["jobSpec"]
    assert spec["scheduling"] == {"timeout": "3600s", "strategy": "SPOT"}
    wp = spec["workerPoolSpecs"][0]
    assert wp["machineSpec"] == {"machineType": "n1-standard-8", "acceleratorType": "NVIDIA_TESLA_T4", "acceleratorCount": 1}
    env = {e["name"]: e["value"] for e in wp["containerSpec"]["env"]}
    assert env["FT_STORE"] == "gs://mstool-research-data" and env["FT_MAX_COST_USD"] == "0.50"
    assert env["FT_EPOCHS"] == "4" and env["FT_ARM"] == "thick" and float(env["FT_RATE_USD_PER_H"]) > 0.4
    assert spec["serviceAccount"].endswith("@mstool-research.iam.gserviceaccount.com")
    plan = json.load(open(tmp_path / "flames-thick-pilot-t4" / "plan.json"))
    assert plan["platform"] == "vertex-ai-customjob" and plan["spot"] and plan["gpu"] == "nvidia-tesla-t4:1"
    assert '"dry_run": true' in capsys.readouterr().out


@pytest.mark.parametrize("bad", [
    ["--image", "us-docker.pkg.dev/other-project/x/y:1"],          # image outside mstool-research
    ["--max-cost-usd", "40"],                                       # above the per-arm cap
    ["--accelerator", "NVIDIA_L4"],                                 # no Spot training quota for L4
    ["--env", "FT_STORE=gs://another-bucket"],                     # launcher-owned variable
])
def test_launcher_refuses_unsafe_requests(tmp_path, bad):
    args = {"--name": "x-run", "--arm": "ft", "--image": IMAGE, "--max-hours": "2", "--max-cost-usd": "1",
            "--purpose": "p", "--out-dir": str(tmp_path)}
    extra = []
    for i in range(0, len(bad), 2):
        if bad[i] == "--env":
            extra = bad[i:i + 2]
        else:
            args[bad[i]] = bad[i + 1]
    with pytest.raises(SystemExit):
        lv.main([x for kv in args.items() for x in kv] + extra)


def test_ledger_reads_a_vertex_training_run(tmp_path):
    rid = "flames-thick-a"
    for d in ("runs/" + rid, "flames-ensemble_cost", "flames-ensemble_manifests"):
        os.makedirs(tmp_path / d, exist_ok=True)
    price = pricing.vertex_training_price("n1-standard-8", "us-central1", "NVIDIA_TESLA_T4", 1, True, 100, "pd-ssd", skus=SKUS)
    json.dump({"run_id": rid, "platform": "vertex-ai-customjob", "region": "us-central1", "zone": "us-central1 (Vertex AI)",
               "machine_type": "n1-standard-8", "spot": True, "provisioning": "SPOT", "gpu": "nvidia-tesla-t4:1",
               "list_price": price, "created_utc": "2026-11-01T08:00:00Z", "purpose": "arm A", "paper_or_feature": "flames-thick"},
              open(tmp_path / "runs" / rid / "plan.json", "w"))
    json.dump({"run_id": rid, "platform": "vertex-ai-customjob", "wall_seconds": 72000, "billed_seconds_estimate": 73200,
               "status": "completed", "hardware": {"gpu": "Tesla T4, 15360 MiB"},
               "stages_utc": {"boot": "2026-11-01T08:05:00Z", "train_start": "2026-11-01T08:20:00Z",
                              "train_end": "2026-11-02T04:00:00Z", "end": "2026-11-02T04:10:00Z"}},
              open(tmp_path / "runs" / rid / "runinfo.json", "w"))
    json.dump({"kind": "training", "status": "completed", "errors": [],
               "cases": [{"case": f"epoch_{i:04d}", "seconds": 230.0 + i % 3, "ok": True} for i in range(300)]},
              open(tmp_path / "flames-ensemble_manifests" / f"{rid}.json", "w"))
    open(tmp_path / "flames-ensemble_cost" / f"{rid}.txt", "w").write(
        f"COST_RECORD,run_id={rid},machine=n1-standard-8+nvidia-tesla-t4:1 spot (Vertex AI),seconds=73200,"
        f"rate_usd_per_h=0.42756,cost_usd_compute_estimate=8.6937\n")
    rows = bl.cloud_rows(str(tmp_path), {}, {})
    r = [x for x in rows if x["run_id"] == rid][0]
    assert r["wall_seconds"] == 73200 and r["provisioning"] == "SPOT" and r["gpu"] == "nvidia-tesla-t4:1"
    assert r["cost_usd_list"] == pytest.approx(73200 / 3600 * 0.42756, abs=1e-3)
    assert r["items_ok"] == 300 and r["median_seconds_per_item"] == 231.0 and r["status"] == "ok"
    assert r["_kind"] == "training" and r["compute_seconds"] == 70800
