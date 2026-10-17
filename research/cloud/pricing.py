"""Official Google Cloud list prices (USD) for the compute ledger — Cloud Billing Catalog API.

Prices are read from the public catalog (no account-specific discounts), so the ledger states
LIST prices; the billed amount is reconciled separately from the billing report. Every price
lookup is snapshotted (date + SKU id + description) so the ledger is auditable later.

    CLOUDSDK_CONFIG=C:/Users/Nicolas/.gcloud-mstool python research/cloud/pricing.py n2-standard-8 us-central1
    ... --spot   ... --gpu nvidia-l4:1   ... --disk-gb 50 --disk-type pd-balanced
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import urllib.request

COMPUTE_SERVICE = "6F81-5844-456A"          # Compute Engine in the Cloud Billing catalog
CACHE_DIR = os.path.join(os.path.dirname(__file__), ".price_cache")
GPU_NAMES = {"nvidia-l4": "Nvidia L4", "nvidia-tesla-t4": "Nvidia Tesla T4",
             "nvidia-tesla-a100": "Nvidia Tesla A100", "nvidia-tesla-p4": "Nvidia Tesla P4",
             "nvidia-tesla-p100": "Nvidia Tesla P100"}
DISK_DESC = {"pd-balanced": "Balanced PD Capacity", "pd-standard": "Storage PD Capacity",
             "pd-ssd": "SSD backed PD Capacity"}


def _token():
    return subprocess.run("gcloud auth print-access-token", shell=True, capture_output=True,
                          text=True).stdout.strip()


def load_skus(service=COMPUTE_SERVICE):
    """All SKUs of a service, cached per UTC day (the catalog has thousands of entries)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
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


def price(machine_type, region, spot=False, gpu=None, disk_gb=50, disk_type="pd-balanced"):
    """Hourly list price (USD) of a VM: cores + RAM (+ GPUs) + boot disk, with the SKUs used."""
    skus = load_skus()
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


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("machine_type")
    ap.add_argument("region")
    ap.add_argument("--spot", action="store_true")
    ap.add_argument("--gpu")
    ap.add_argument("--disk-gb", type=int, default=50)
    ap.add_argument("--disk-type", default="pd-balanced")
    a = ap.parse_args()
    print(json.dumps(price(a.machine_type, a.region, a.spot, a.gpu, a.disk_gb, a.disk_type), indent=1))
