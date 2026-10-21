"""Prepare (default) or submit (--submit) a Vertex AI CustomJob for FLAMeS-thick in mstool-research.

Default is a DRY RUN: nothing is sent anywhere. It prices the replica from the cached Cloud Billing
catalogue (Compute Engine Spot SKUs, see pricing.vertex_training_price), writes the exact REST request
body and the ledger plan to --out-dir, and prints the command that --submit would run.

--submit (coordinator only, after review): re-prices from the live catalogue, POSTs the CustomJob to
us-central1-aiplatform.googleapis.com for project mstool-research with the isolated gcloud
configuration, and stores plan.json + request + response in gs://mstool-research-data/runs/<name>/
(what research/cloud/build_ledger.py reads). Spot strategy, a hard scheduling.timeout and the
container's own cost guard (FT_MAX_COST_USD) bound the bill.

    python research/cloud/launch_vertex.py --name flames-thick-pilot-t4 --arm thick \
        --image us-central1-docker.pkg.dev/mstool-research/mstool-research-images/flames-thick@sha256:<digest> \
        --machine-type n1-standard-8 --accelerator NVIDIA_TESLA_T4 --max-hours 1 --max-cost-usd 0.5 \
        --purpose "FLAMeS-thick pilot" --env FT_EPOCHS=4 FT_ITERS=20 [--submit]
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

PROJECT = "mstool-research"
REGION = "us-central1"
BUCKET = "gs://mstool-research-data"
SA = "mstool-runner@mstool-research.iam.gserviceaccount.com"
IMAGE_PREFIX = f"{REGION}-docker.pkg.dev/{PROJECT}/"
ENDPOINT = f"https://{REGION}-aiplatform.googleapis.com/v1/projects/{PROJECT}/locations/{REGION}/customJobs"
GPU_CE = {"NVIDIA_TESLA_T4": "nvidia-tesla-t4", "NVIDIA_TESLA_A100": "nvidia-tesla-a100",
          "NVIDIA_TESLA_V100": "nvidia-tesla-v100", "NVIDIA_TESLA_P100": "nvidia-tesla-p100",
          "NVIDIA_TESLA_P4": "nvidia-tesla-p4"}
# Spot (preemptible) custom-training GPU quota that exists for the project: 1 each.
QUOTA_ONE = set(GPU_CE)
DA_PROCS = {"n1-standard-4": 3, "n1-standard-8": 6, "n1-highmem-8": 6, "n1-standard-16": 12, "a2-highgpu-1g": 10}
MAX_COST_CAP_USD = 15.0           # PROTOCOL §5.2: per arm
FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests", "fixtures",
                       "ce_skus_us-central1_2026-10-18.json")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pricing  # noqa: E402


def git_commit():
    return subprocess.run("git rev-parse --short HEAD", shell=True, capture_output=True, text=True).stdout.strip()


def run_id(a):
    return a.resume_of or a.name


def build_request(a, rate, commit):
    env = {"FT_RUN_ID": run_id(a), "FT_ARM": a.arm, "FT_STORE": BUCKET, "FT_PREFIX": "flames-thick",
           "FT_RATE_USD_PER_H": f"{rate:.5f}", "FT_MAX_COST_USD": f"{a.max_cost_usd:.2f}",
           "FT_MAX_HOURS": f"{a.max_hours:g}", "FT_MACHINE_TYPE": a.machine_type,
           "FT_GPU": f"{GPU_CE[a.accelerator]}:1", "FT_IMAGE": a.image, "FT_GIT_COMMIT": commit,
           "FT_PURPOSE": a.purpose, "nnUNet_n_proc_DA": str(DA_PROCS.get(a.machine_type, 6)),
           "nnUNet_compile": "f", "FT_NPROC": "8"}
    for kv in a.env:
        k, v = kv.split("=", 1)
        env[k] = v
    return {
        "displayName": a.name,
        "labels": {"project": "mstool", "job": "flames-thick", "run": run_id(a)},
        "jobSpec": {
            "workerPoolSpecs": [{
                "machineSpec": {"machineType": a.machine_type, "acceleratorType": a.accelerator,
                                "acceleratorCount": 1},
                "replicaCount": "1",
                "diskSpec": {"bootDiskType": "pd-ssd", "bootDiskSizeGb": a.disk_gb},
                "containerSpec": {"imageUri": a.image,
                                  "env": [{"name": k, "value": v} for k, v in sorted(env.items())]},
            }],
            "scheduling": {"timeout": f"{int(round(a.max_hours * 3600))}s", "strategy": "SPOT"},
            "serviceAccount": SA,
        },
    }


def validate(a):
    if not re.fullmatch(r"[a-z][a-z0-9-]{2,50}", a.name):
        raise SystemExit("--name: lowercase letters, digits, '-' (3-51 chars)")
    if not a.image.startswith(IMAGE_PREFIX):
        raise SystemExit(f"--image must live in Artifact Registry of {PROJECT} ({IMAGE_PREFIX}...)")
    if a.submit and "@sha256:" not in a.image:
        raise SystemExit("--submit needs the image pinned by digest (...@sha256:...)")
    if a.accelerator not in QUOTA_ONE:
        raise SystemExit(f"--accelerator must be one of {sorted(QUOTA_ONE)} (Spot training quota = 1 each)")
    if not 0 < a.max_cost_usd <= MAX_COST_CAP_USD:
        raise SystemExit(f"--max-cost-usd must be in (0, {MAX_COST_CAP_USD}] (PROTOCOL §5.2)")
    if not 0 < a.max_hours <= 72:
        raise SystemExit("--max-hours must be in (0, 72]")
    for kv in a.env:
        if "=" not in kv or not kv.split("=", 1)[0].replace("_", "").isalnum():
            raise SystemExit(f"bad --env item {kv!r}")
        if kv.split("=", 1)[0] in ("FT_STORE", "FT_RUN_ID", "FT_RATE_USD_PER_H", "FT_MAX_COST_USD", "FT_MAX_HOURS"):
            raise SystemExit(f"{kv.split('=', 1)[0]} is set by the launcher, not by --env")
        if kv.split("=", 1)[0] in ("FT_LOCAL_TEST_PATCH", "FT_DEVICE"):
            raise SystemExit(f"{kv.split('=', 1)[0]} is for local CPU tests only")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True)
    ap.add_argument("--arm", choices=["thick", "ft"], required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--machine-type", default="n1-standard-8")
    ap.add_argument("--accelerator", default="NVIDIA_TESLA_T4")
    ap.add_argument("--disk-gb", type=int, default=100)
    ap.add_argument("--max-hours", type=float, required=True)
    ap.add_argument("--max-cost-usd", type=float, required=True)
    ap.add_argument("--purpose", required=True)
    ap.add_argument("--paper", default="flames-thick")
    ap.add_argument("--env", nargs="*", default=[], help="extra container env K=V (schedule knobs for pilots)")
    ap.add_argument("--resume-of", help="continue an earlier run (same FT_RUN_ID, its checkpoints and cost guard) "
                                         "after the job failed or exhausted its 6 Spot restarts; --name is new")
    ap.add_argument("--out-dir", default=os.path.join(tempfile.gettempdir(), "flames-thick-launch"))
    ap.add_argument("--submit", action="store_true", help="really create the job (coordinator only)")
    a = ap.parse_args(argv)
    validate(a)
    try:
        price = pricing.vertex_training_price(a.machine_type, REGION, a.accelerator, 1, True, a.disk_gb, "pd-ssd",
                                              offline=not a.submit)
    except LookupError:                      # dry run without a cached catalogue: the committed SKU subset
        skus = json.load(open(FIXTURE))["skus"]
        price = pricing.vertex_training_price(a.machine_type, REGION, a.accelerator, 1, True, a.disk_gb, "pd-ssd",
                                              skus=skus)
        price["basis"] += " Dry run: SKU subset cached 2026-10-18 (tests/fixtures)."
    rate = price["usd_per_hour"]
    commit = git_commit()
    req = build_request(a, rate, commit)
    plan = {"run_id": run_id(a), "job_name": a.name, "resume_of": a.resume_of, "purpose": a.purpose, "paper_or_feature": a.paper, "project": PROJECT,
            "platform": "vertex-ai-customjob", "region": REGION, "zone": f"{REGION} (Vertex AI)",
            "machine_type": a.machine_type, "spot": True, "provisioning": "SPOT",
            "gpu": f"{GPU_CE[a.accelerator]}:1", "accelerator_type": a.accelerator, "max_hours": a.max_hours,
            "max_cost_usd": a.max_cost_usd, "list_price": price, "image": a.image, "git_commit": commit,
            "startup_script": "research/flames_thick/vertex_entry.py (container entry point)",
            "created_utc": None, "customjob": None}
    out = os.path.join(a.out_dir, a.name)
    os.makedirs(out, exist_ok=True)
    json.dump(req, open(os.path.join(out, "customjob_request.json"), "w"), indent=1)
    if not a.submit:
        json.dump(plan, open(os.path.join(out, "plan.json"), "w"), indent=1)
        hours_cost = a.max_hours * rate
        print(json.dumps({"dry_run": True, "files": out, "usd_per_hour_list": rate,
                          "cost_if_it_ran_max_hours_usd": round(hours_cost, 2),
                          "cost_guard_usd": a.max_cost_usd,
                          "would_POST": ENDPOINT}, indent=1))
        return 0
    os.environ["CLOUDSDK_CONFIG"] = r"C:\Users\Nicolas\.gcloud-mstool"
    proj = subprocess.run("gcloud config get-value project", shell=True, capture_output=True, text=True).stdout.strip()
    if proj != PROJECT:
        raise SystemExit(f"isolated gcloud config points to {proj!r}, not {PROJECT}; refusing")
    runs_dir = f"{BUCKET}/runs/{run_id(a)}/" + (f"resubmit_{a.name}/" if a.resume_of else "")
    exists = subprocess.run(f"gcloud storage ls {runs_dir}", shell=True, capture_output=True, text=True)
    if exists.returncode == 0 and exists.stdout.strip():
        raise SystemExit(f"{runs_dir} already exists: choose a new --name (use --resume-of RUN_ID to continue a run)")
    if a.resume_of:
        prev = subprocess.run(f"gcloud storage ls {BUCKET}/runs/{a.resume_of}/plan.json", shell=True,
                              capture_output=True, text=True)
        if prev.returncode != 0:
            raise SystemExit(f"--resume-of {a.resume_of}: no such run in {BUCKET}/runs/")
    token = subprocess.run("gcloud auth print-access-token", shell=True, capture_output=True, text=True).stdout.strip()
    body = json.dumps(req).encode()
    r = urllib.request.Request(ENDPOINT, data=body, method="POST",
                               headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                                        "x-goog-user-project": PROJECT})
    resp = json.load(urllib.request.urlopen(r, timeout=120))
    plan["created_utc"] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    plan["customjob"] = resp.get("name")
    json.dump(plan, open(os.path.join(out, "plan.json"), "w"), indent=1)
    json.dump(resp, open(os.path.join(out, "customjob.json"), "w"), indent=1)
    subprocess.run(f'gcloud storage cp "{out}/plan.json" "{out}/customjob_request.json" "{out}/customjob.json" '
                   f'{runs_dir} --quiet', shell=True, check=True)
    print(json.dumps({"submitted": resp.get("name"), "state": resp.get("state"), "usd_per_hour_list": rate}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
