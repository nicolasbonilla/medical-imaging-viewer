"""Launch a research VM in mstool-research and register it in the compute ledger.

Before creating the VM, the official hourly LIST price is taken from the Cloud Billing catalog
(pricing.py). After creation, the full instance description (machine type, CPU platform, zone,
provisioning model, disks, labels) is saved with the plan to gs://mstool-research-data/runs/<name>/.
The job itself adds runinfo.json (hardware seen from inside, stage timestamps) when it ends.

Always uses the isolated gcloud configuration and project mstool-research — nothing else.

    python research/cloud/launch_vm.py --name flames-full-1 --machine-type n2-standard-8 \
        --startup research/cloud/vm_flames_ensemble_v2.sh --purpose "FLAMeS 5-fold ensemble, all cases" \
        --meta datasets="openms mslesseg" folds="0 1 2 3 4" max-hours=30 --max-hours 30
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import tempfile
import time

PROJECT = "mstool-research"
BUCKET = "gs://mstool-research-data"
SA = "mstool-runner@mstool-research.iam.gserviceaccount.com"
os.environ["CLOUDSDK_CONFIG"] = r"C:\Users\Nicolas\.gcloud-mstool"
sys.path.insert(0, os.path.dirname(__file__))
import pricing  # noqa: E402


def sh(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"FAILED: {cmd}\n{r.stderr[-2000:]}")
    return r.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--machine-type", required=True)
    ap.add_argument("--zone", default="us-central1-a")
    ap.add_argument("--spot", action="store_true")
    ap.add_argument("--gpu", help="e.g. nvidia-l4:1")
    ap.add_argument("--disk-gb", type=int, default=50)
    ap.add_argument("--startup", required=True)
    ap.add_argument("--purpose", required=True)
    ap.add_argument("--paper", default="", help="paper/feature this run serves, e.g. A,C or app")
    ap.add_argument("--max-hours", type=int, default=24)
    ap.add_argument("--meta", nargs="*", default=[], help='k=v pairs (values may contain spaces if quoted)')
    a = ap.parse_args()

    if b"\r" in open(a.startup, "rb").read():          # bash on the VM fails on Windows line endings
        raise SystemExit(f"{a.startup} has CRLF line endings; convert to LF before launching")
    region = a.zone.rsplit("-", 1)[0]
    price = pricing.price(a.machine_type, region, spot=a.spot, gpu=a.gpu, disk_gb=a.disk_gb)
    meta = dict(kv.split("=", 1) for kv in a.meta)
    meta.setdefault("hourly-rate", str(price["usd_per_hour"]))
    meta.setdefault("machine-desc", a.machine_type + (" spot" if a.spot else ""))
    meta.setdefault("max-hours", str(a.max_hours))
    # gcloud --metadata cannot carry values with commas; write each value to a file instead.
    md_args = []
    for k, v in meta.items():
        p = os.path.join(tempfile.gettempdir(), f"md_{a.name}_{k}.txt")
        open(p, "w").write(v)
        md_args.append(f"{k}={p}")
    md_args.append(f"startup-script={a.startup}")
    # Same region as the bucket (no egress cost); on a zone stockout try the next zone.
    zones = [a.zone] + [f"{region}-{z}" for z in "abcf" if f"{region}-{z}" != a.zone]
    for zone in zones:
        try:
            created = launch(a, zone, md_args)
            a.zone = zone
            break
        except RuntimeError as exc:
            if "stockout" not in str(exc) and "ZONE_RESOURCE_POOL_EXHAUSTED" not in str(exc):
                raise SystemExit(str(exc))
            print(f"stockout in {zone}, trying next zone", flush=True)
    else:
        raise SystemExit(f"no capacity for {a.machine_type} in {zones}")
    vm = json.loads(sh(f"gcloud compute instances describe {a.name} --zone {a.zone} --project {PROJECT} --format=json"))
    plan = {"run_id": a.name, "purpose": a.purpose, "paper_or_feature": a.paper, "created_utc": created,
            "project": PROJECT, "zone": a.zone, "machine_type": a.machine_type, "spot": a.spot, "gpu": a.gpu,
            "cpu_platform": vm.get("cpuPlatform"), "provisioning": vm.get("scheduling", {}).get("provisioningModel"),
            "max_hours": a.max_hours, "metadata": meta, "list_price": price,
            "startup_script": os.path.basename(a.startup),
            "git_commit": subprocess.run("git rev-parse --short HEAD", shell=True, capture_output=True, text=True).stdout.strip()}
    d = tempfile.mkdtemp()
    json.dump(vm, open(os.path.join(d, "vm.json"), "w"), indent=1)
    json.dump(plan, open(os.path.join(d, "plan.json"), "w"), indent=1)
    sh(f'gcloud storage cp "{d}/vm.json" "{d}/plan.json" {BUCKET}/runs/{a.name}/ --quiet')
    print(json.dumps({k: plan[k] for k in ("run_id", "machine_type", "cpu_platform", "provisioning", "zone")}
                     | {"usd_per_hour": price["usd_per_hour"]}, indent=1))


def launch(a, zone, md_args):
    cmd = (f'gcloud compute instances create {a.name} --project={PROJECT} --zone={zone} '
           f'--machine-type={a.machine_type} --provisioning-model={"SPOT" if a.spot else "STANDARD"} '
           f'--max-run-duration={a.max_hours + 1}h --instance-termination-action=DELETE '
           f'--image-family=ubuntu-2204-lts --image-project=ubuntu-os-cloud '
           f'--boot-disk-size={a.disk_gb}GB --boot-disk-type=pd-balanced '
           f'--service-account={SA} --scopes=cloud-platform '
           f'--labels=project=mstool,job={a.name.split("-")[0]},run={a.name} '
           + (f'--accelerator=type={a.gpu.split(":")[0]},count={a.gpu.split(":")[1]} --maintenance-policy=TERMINATE ' if a.gpu else '')
           + f'--metadata-from-file="{",".join(md_args)}"')
    created = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-2000:])
    time.sleep(10)
    return created


if __name__ == "__main__":
    main()
