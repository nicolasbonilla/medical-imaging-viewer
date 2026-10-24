"""Official Google Cloud list prices (USD) for the compute ledger — Cloud Billing Catalog API.

Prices are read from the public catalog (no account-specific discounts), so the ledger states
LIST prices; the billed amount is reconciled separately from the billing report. Every price
lookup is snapshotted (date + SKU id + description) so the ledger is auditable later.

    CLOUDSDK_CONFIG=C:/Users/Nicolas/.gcloud-mstool python research/cloud/pricing.py n2-standard-8 us-central1
    ... --spot   ... --gpu nvidia-l4:1   ... --disk-gb 50 --disk-type pd-balanced
    ... n1-standard-8 us-central1 --vertex --spot --gpu nvidia-tesla-t4:1 --disk-gb 100 --disk-type pd-ssd

Vertex AI custom training (`vertex_training_price`): the Vertex AI pricing page states that Spot VMs
used by custom training "are billed according to Compute Engine Spot VMs pricing"
(https://cloud.google.com/vertex-ai/pricing, section on Spot VMs; checked 2026-10-21), so a Spot
training job is priced here from the Compute Engine Spot SKUs (cores + RAM of the machine type,
GPU attached to Spot VMs, boot disk). Vertex's own training SKUs (service id still to be confirmed
with services.list, see VERTEX_AI_SERVICE) are needed only for on-demand (non-Spot) training.
"""
import argparse
import datetime
import glob
import json
import os
import re
import subprocess
import urllib.request

COMPUTE_SERVICE = "6F81-5844-456A"          # Compute Engine in the Cloud Billing catalog
# TODO(verify): Vertex AI's service id in the Cloud Billing catalog. Believed to be
# "C7E2-9256-1C43" (display name "Vertex AI"); confirm with find_service_id("Vertex AI") — it needs
# an authenticated call (gcloud token or API key), which this branch was prepared without.
VERTEX_AI_SERVICE = None
CACHE_DIR = os.path.join(os.path.dirname(__file__), ".price_cache")
GPU_NAMES = {"nvidia-l4": "Nvidia L4", "nvidia-tesla-t4": "Nvidia Tesla T4",
             "nvidia-tesla-a100": "Nvidia Tesla A100", "nvidia-tesla-p4": "Nvidia Tesla P4",
             "nvidia-tesla-p100": "Nvidia Tesla P100", "nvidia-tesla-v100": "Nvidia Tesla V100"}
# Vertex AI accelerator enum -> Compute Engine accelerator name
VERTEX_GPU = {"NVIDIA_TESLA_T4": "nvidia-tesla-t4", "NVIDIA_TESLA_A100": "nvidia-tesla-a100",
              "NVIDIA_TESLA_V100": "nvidia-tesla-v100", "NVIDIA_TESLA_P100": "nvidia-tesla-p100",
              "NVIDIA_TESLA_P4": "nvidia-tesla-p4", "NVIDIA_L4": "nvidia-l4"}
# Public machine shapes (vCPU, GB) so pricing never needs a describe call for these types
# (https://cloud.google.com/compute/docs/general-purpose-machines, .../accelerator-optimized-machines).
KNOWN_SHAPES = {"n1-standard-4": (4, 15.0), "n1-standard-8": (8, 30.0), "n1-standard-16": (16, 60.0),
                "n1-highmem-8": (8, 52.0), "a2-highgpu-1g": (12, 85.0), "g2-standard-8": (8, 32.0),
                "n2d-standard-4": (4, 16.0), "n2-standard-4": (4, 16.0), "n2-standard-8": (8, 32.0),
                "e2-standard-8": (8, 32.0)}
DISK_DESC = {"pd-balanced": "Balanced PD Capacity", "pd-standard": "Storage PD Capacity",
             "pd-ssd": "SSD backed PD Capacity"}


def _token():
    return subprocess.run("gcloud auth print-access-token", shell=True, capture_output=True,
                          text=True).stdout.strip()


def latest_cached(service=COMPUTE_SERVICE):
    """(path, day) of the newest cached catalogue of a service, or (None, None)."""
    files = sorted(glob.glob(os.path.join(CACHE_DIR, f"{service}_????-??-??.json")))
    if not files:
        return None, None
    return files[-1], os.path.basename(files[-1])[len(service) + 1:-5]


def load_skus(service=COMPUTE_SERVICE, offline=False):
    """All SKUs of a service, cached per UTC day (the catalog has thousands of entries).

    offline=True uses the newest cached day without any network call (dry runs, tests).
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    if offline:
        path, _ = latest_cached(service)
        if not path:
            raise LookupError(f"no cached catalogue for {service} in {CACHE_DIR}")
        return json.load(open(path))
    day = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    path = os.path.join(CACHE_DIR, f"{service}_{day}.json")
    if os.path.exists(path):
        return json.load(open(path))
    skus, page = [], ""
    while True:
        url = (f"https://cloudbilling.googleapis.com/v1/services/{service}/skus?currencyCode=USD"
               f"&pageSize=5000" + (f"&pageToken={page}" if page else ""))
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {_token()}",
                                                   "x-goog-user-project": "mstool-research"})
        d = json.load(urllib.request.urlopen(req, timeout=120))
        skus += d.get("skus", [])
        page = d.get("nextPageToken", "")
        if not page:
            break
    json.dump(skus, open(path, "w"))
    return skus


def unit_price(sku):
    rates = sku["pricingInfo"][0]["pricingExpression"]["tieredRates"]
    p = rates[-1]["unitPrice"]
    return int(p.get("units", 0)) + p.get("nanos", 0) / 1e9


def find(skus, desc_regex, region):
    hits = [s for s in skus if re.fullmatch(desc_regex, s["description"]) and region in s.get("serviceRegions", [])]
    if len(hits) != 1:
        raise LookupError(f"{len(hits)} SKUs for /{desc_regex}/ in {region}: "
                          f"{[h['description'] for h in hits][:5]}")
    s = hits[0]
    return {"sku_id": s["skuId"], "description": s["description"],
            "unit": s["pricingInfo"][0]["pricingExpression"]["usageUnit"], "usd": unit_price(s)}


def machine_shape(machine_type, zone):
    """(vCPUs, memory GB) of a predefined machine type, cached (shapes do not change)."""
    if machine_type in KNOWN_SHAPES:
        return KNOWN_SHAPES[machine_type]
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, "shapes.json")
    shapes = json.load(open(path)) if os.path.exists(path) else {}
    if machine_type in shapes:
        return tuple(shapes[machine_type])
    out = subprocess.run(f"gcloud compute machine-types describe {machine_type} --zone {zone} "
                         f"--project mstool-research --format=json", shell=True, capture_output=True, text=True)
    d = json.loads(out.stdout)
    shapes[machine_type] = [d["guestCpus"], d["memoryMb"] / 1024.0]
    json.dump(shapes, open(path, "w"), indent=1)
    return tuple(shapes[machine_type])


def price(machine_type, region, spot=False, gpu=None, disk_gb=50, disk_type="pd-balanced", skus=None):
    """Hourly list price (USD) of a VM: cores + RAM (+ GPUs) + boot disk, with the SKUs used."""
    skus = load_skus() if skus is None else skus
    family = machine_type.split("-")[0].upper()
    vcpus, mem_gb = machine_shape(machine_type, f"{region}-a")
    pre = "Spot Preemptible " if spot else ""
    region_word = "Americas" if region.startswith("us-") else ("EMEA" if region.startswith("europe-") else "APAC")
    core = find(skus, rf"{pre}{family} (?:AMD )?(?:Predefined )?Instance Core running in {region_word}", region)
    ram = find(skus, rf"{pre}{family} (?:AMD )?(?:Predefined )?Instance Ram running in {region_word}", region)
    parts = {"cores": {"qty": vcpus, **core}, "ram_gb": {"qty": mem_gb, **ram}}
    total = vcpus * core["usd"] + mem_gb * ram["usd"]
    if gpu:
        gname, gcount = gpu.split(":")
        gdesc = (rf"{GPU_NAMES[gname]} GPU attached to Spot Preemptible VMs running in {region_word}" if spot
                 else rf"{GPU_NAMES[gname]} GPU running in {region_word}")
        g = find(skus, gdesc, region)
        parts["gpu"] = {"qty": int(gcount), **g}
        total += int(gcount) * g["usd"]
    if disk_gb:
        dsk = find(skus, rf"{DISK_DESC[disk_type]}(?: in .*)?", region)
        per_hour = dsk["usd"] / 730.0                      # catalog unit is GiB-month
        parts["boot_disk"] = {"qty": disk_gb, **dsk, "usd_per_gib_hour": per_hour}
        total += disk_gb * per_hour
    return {"date_utc": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "machine_type": machine_type, "region": region, "spot": spot, "gpu": gpu,
            "vcpus": vcpus, "memory_gb": round(mem_gb, 2), "usd_per_hour": round(total, 5), "parts": parts}


def vertex_training_price(machine_type, region, accelerator_type=None, accelerator_count=1, spot=True,
                          disk_gb=100, disk_type="pd-ssd", skus=None, offline=False):
    """Hourly list price (USD) of one Vertex AI custom-training replica.

    Spot: Compute Engine Spot SKUs (Vertex AI pricing page: Spot VMs for training are billed at
    Compute Engine Spot prices). accelerator_type uses Vertex's enum (NVIDIA_TESLA_T4, ...).
    Vertex's default training boot disk is pd-ssd 100 GB.
    """
    if not spot:
        raise NotImplementedError(
            "on-demand Vertex AI training uses Vertex's own SKUs: confirm VERTEX_AI_SERVICE with "
            "find_service_id('Vertex AI') and add the SKU patterns (TODO, not needed for Spot jobs)")
    if skus is None:
        skus = load_skus(offline=offline)
    gpu = f"{VERTEX_GPU[accelerator_type]}:{accelerator_count}" if accelerator_type else None
    p = price(machine_type, region, spot=True, gpu=gpu, disk_gb=disk_gb, disk_type=disk_type, skus=skus)
    eff = sorted({s["pricingInfo"][0].get("effectiveTime", "")[:10] for s in skus
                  if s.get("skuId") in {v.get("sku_id") for v in p["parts"].values()}})
    p.update({"platform": "vertex-ai-customjob", "accelerator_type": accelerator_type,
              "accelerator_count": accelerator_count if accelerator_type else 0,
              "catalog_effective_dates": eff,
              "basis": ("Compute Engine Spot SKUs (cores + RAM + GPU attached to Spot VMs + boot disk); Vertex AI "
                        "pricing page: Spot VMs for custom training are billed at Compute Engine Spot prices "
                        "(https://cloud.google.com/vertex-ai/pricing). Guard adds a 1.15 safety factor.")})
    return p


def find_service_id(display_name="Vertex AI"):
    """Cloud Billing catalogue service id by display name (authenticated call; run where gcloud works)."""
    out, page = [], ""
    while True:
        url = "https://cloudbilling.googleapis.com/v1/services?pageSize=5000" + (f"&pageToken={page}" if page else "")
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {_token()}",
                                                   "x-goog-user-project": "mstool-research"})
        d = json.load(urllib.request.urlopen(req, timeout=120))
        out += [s for s in d.get("services", []) if s.get("displayName") == display_name]
        page = d.get("nextPageToken", "")
        if not page:
            break
    return [s["serviceId"] for s in out]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("machine_type")
    ap.add_argument("region")
    ap.add_argument("--spot", action="store_true")
    ap.add_argument("--gpu", help="nvidia-tesla-t4:1 (Compute Engine name) or NVIDIA_TESLA_T4:1 with --vertex")
    ap.add_argument("--disk-gb", type=int, default=50)
    ap.add_argument("--disk-type", default="pd-balanced")
    ap.add_argument("--vertex", action="store_true", help="Vertex AI custom-training replica")
    ap.add_argument("--offline", action="store_true", help="use the newest cached catalogue (no network)")
    a = ap.parse_args()
    if a.vertex:
        acc, n = (a.gpu.split(":") + ["1"])[:2] if a.gpu else (None, 0)
        acc = {v: k for k, v in VERTEX_GPU.items()}.get(acc, acc)
        print(json.dumps(vertex_training_price(a.machine_type, a.region, acc, int(n), a.spot, a.disk_gb,
                                               a.disk_type, offline=a.offline), indent=1))
    else:
        print(json.dumps(price(a.machine_type, a.region, a.spot, a.gpu, a.disk_gb, a.disk_type,
                               skus=load_skus(offline=a.offline)), indent=1))
