"""Build the research compute ledger: every machine, processor, duration and price in one place.

Sources (nothing is estimated where a measurement exists):
  * Cloud runs in mstool-research — gs://mstool-research-data/runs/<run>/{plan,vm,runinfo}.json
    (written by launch_vm.py and by the job itself), {flames-ensemble,controls,lstai}/cost/<run>.txt
    and {flames-ensemble,lstai}/manifests/<run>.json (per case timings, software versions, checksums).
  * August 2026 runs in brain-mri-476110 — docs/calm-ms/cost-ledger.csv (as recorded then).
  * Local computer runs — docs/research/compute-ledger/local_runs.csv (hand-kept, with timings).
  * Human notes per run (parity checks, failure causes) — docs/research/compute-ledger/annotations.json.

Prices: official LIST prices (USD) from the Cloud Billing catalog via pricing.py, looked up on the
day the ledger is built and recorded with their SKU ids. They are what Google charges before
credits; the free credit pays them. The billed amount is reconciled separately (billing report).

    CLOUDSDK_CONFIG=C:/Users/Nicolas/.gcloud-mstool python research/cloud/build_ledger.py
Outputs in docs/research/compute-ledger/: compute_ledger.csv, records/<run>.json, COMPUTE_SUMMARY.md
"""
import csv
import datetime
import glob
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET

os.environ["CLOUDSDK_CONFIG"] = r"C:\Users\Nicolas\.gcloud-mstool"
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(REPO, "docs", "research", "compute-ledger")
BUCKET = "gs://mstool-research-data"
CREDIT_EUR, CREDIT_TARGET_EUR, CREDIT_EXPIRES = 264.0, 240.0, "2027-01-15"
STORAGE_USD_PER_GB_MONTH = 0.020          # Standard storage, us-central1 (list) — checked in the catalog below
sys.path.insert(0, HERE)
import pricing  # noqa: E402

FIELDS = ["run_id", "date_utc", "project", "purpose", "paper_or_feature", "status", "machine_type",
          "machines", "vcpus", "memory_gb", "cpu_platform", "cpu_model", "gpu", "provisioning", "zone",
          "start_utc", "end_utc", "wall_seconds", "vm_hours", "setup_seconds", "compute_seconds",
          "items_ok", "items_failed", "median_seconds_per_item", "usd_per_hour_list", "cost_usd_list",
          "cost_usd_recorded", "price_basis", "notes"]


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


def ts(s):
    return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ") if s else None


def secs(a, b):
    return int((ts(b) - ts(a)).total_seconds()) if a and b else ""


def ecb_usd_per_eur():
    """ECB euro reference rate (USD per 1 EUR) — public, no account data sent."""
    try:
        url = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
        try:
            import certifi, ssl
            x = urllib.request.urlopen(url, timeout=30, context=ssl.create_default_context(cafile=certifi.where())).read()
        except Exception:
            x = subprocess.run(["curl", "-s", url], capture_output=True, timeout=60).stdout
        root = ET.fromstring(x)
        for el in root.iter():
            if el.get("currency") == "USD":
                day = next(e.get("time") for e in root.iter() if e.get("time"))
                return float(el.get("rate")), day
    except Exception as exc:                                 # recorded, never silent
        print("ECB rate unavailable:", exc)
    return None, None


def parse_machine(text):
    """'4x n2-standard-8 CPU' / 'n1-standard-4 + 1x NVIDIA P4' -> (count, machine_type, gpu)."""
    m = re.search(r"(?:(\d+)x\s+)?([a-z0-9]+-(?:standard|highmem|highcpu)-\d+)", text)
    g = re.search(r"(\d+)x\s+NVIDIA\s+(P4|T4|L4|P100|A100)", text, re.I)
    gpu = None
    if g:
        name = g.group(2).upper()
        gpu = ("nvidia-l4" if name == "L4" else f"nvidia-tesla-{name.lower()}") + f":{g.group(1)}"
    return int(m.group(1) or 1), m.group(2), gpu


def fetch_bucket(tmp):
    # Every job writes cost/<run>.txt and manifests/<run>.json under its own prefix; they are merged
    # here (run ids are unique). controls/manifests holds the HD-BET step of a controls run whose
    # per-item timings live in the FLAMeS manifest (flames-ensemble/manifests/<run>.json), so it is
    # not merged.
    sources = {"runs": ["runs"],
               "flames-ensemble_cost": ["flames-ensemble/cost", "controls/cost", "lstai/cost"],
               "flames-ensemble_manifests": ["flames-ensemble/manifests", "lstai/manifests"]}
    for local, subs in sources.items():
        dst = os.path.join(tmp, local)
        os.makedirs(dst, exist_ok=True)
        for sub in subs:
            sh(f'gcloud storage cp -r "{BUCKET}/{sub}/*" "{dst}/" --quiet')
    return tmp


def kv_cost(path):
    line = open(path).read().strip().splitlines()[-1]
    return dict(p.split("=", 1) for p in line.split(",")[1:] if "=" in p)


def cloud_rows(tmp, notes, price_cache):
    runs_dir, cost_dir, man_dir = (os.path.join(tmp, d) for d in ("runs", "flames-ensemble_cost", "flames-ensemble_manifests"))
    ids = set(os.listdir(runs_dir)) if os.path.isdir(runs_dir) else set()
    ids |= {os.path.splitext(f)[0] for f in os.listdir(cost_dir)} if os.path.isdir(cost_dir) else set()
    rows = []
    for rid in sorted(ids):
        load = lambda p: json.load(open(p)) if os.path.exists(p) else {}
        plan = load(os.path.join(runs_dir, rid, "plan.json"))
        vm = load(os.path.join(runs_dir, rid, "vm.json"))
        info = load(os.path.join(runs_dir, rid, "runinfo.json"))
        man = load(os.path.join(man_dir, f"{rid}.json"))
        cost = kv_cost(os.path.join(cost_dir, f"{rid}.txt")) if os.path.exists(os.path.join(cost_dir, f"{rid}.txt")) else {}
        hw, st = info.get("hardware", {}), info.get("stages_utc", {})
        n = notes.get(rid, {})
        mt = (plan.get("machine_type") or hw.get("machine_type") or (vm.get("machineType", "").rsplit("/", 1)[-1])
              or n.get("machine_type") or cost.get("machine", "").replace("-spot", ""))
        spot = bool(plan.get("spot")) if plan else ("spot" in cost.get("machine", "") or n.get("spot", False))
        prov = (plan.get("provisioning") or hw.get("provisioning") or vm.get("scheduling", {}).get("provisioningModel")
                or ("SPOT" if spot else "STANDARD"))
        spot = prov == "SPOT"
        zone = plan.get("zone") or hw.get("zone") or vm.get("zone", "").rsplit("/", 1)[-1] or n.get("zone", "us-central1-a")
        wall = int(info.get("wall_seconds") or cost.get("seconds") or 0) or ""
        key = (mt, zone.rsplit("-", 1)[0], spot, plan.get("gpu"))
        if key not in price_cache:
            price_cache[key] = pricing.price(mt, key[1], spot=spot, gpu=key[3], disk_gb=50)
        p = price_cache[key]
        if plan.get("list_price", {}).get("usd_per_hour"):     # exact price snapshot taken at launch (real disk size)
            p = plan["list_price"]
        cases = man.get("cases", [])
        per = [c["seconds"] for c in cases if c.get("ok")]
        status = n.get("status") or ("running" if not wall else
                                     ("failed" if man.get("errors") or (man and not per) else "ok"))
        rows.append({
            "run_id": rid, "date_utc": (plan.get("created_utc") or st.get("boot") or man.get("started_utc") or "")[:10],
            "project": "mstool-research", "purpose": plan.get("purpose") or n.get("purpose", ""),
            "paper_or_feature": plan.get("paper_or_feature") or n.get("paper_or_feature", ""), "status": status,
            "machine_type": mt, "vcpus": p["vcpus"], "memory_gb": p["memory_gb"],
            "cpu_platform": plan.get("cpu_platform") or vm.get("cpuPlatform") or hw.get("cpu_platform") or "not recorded",
            "cpu_model": hw.get("cpu_model", "not recorded"), "gpu": plan.get("gpu") or hw.get("gpu") or "",
            "provisioning": prov, "zone": zone, "start_utc": st.get("boot", plan.get("created_utc", "")),
            "end_utc": st.get("end", ""), "wall_seconds": wall,
            "vm_hours": round(wall / 3600, 4) if wall else "",
            "setup_seconds": secs(st.get("boot"), st.get("inference_start")),
            "compute_seconds": secs(st.get("inference_start"), st.get("inference_end")),
            "items_ok": len(per) if man else "", "items_failed": len(man.get("errors", [])) if man else "",
            "median_seconds_per_item": round(statistics.median(per), 1) if per else "",
            "usd_per_hour_list": p["usd_per_hour"],
            "cost_usd_list": round(wall / 3600 * p["usd_per_hour"], 4) if wall else "",
            "cost_usd_recorded": cost.get("cost_usd_compute_estimate") or cost.get("cost_usd", ""),
            "price_basis": f"Cloud Billing catalog list price {p['date_utc'][:10]} (cores+RAM+boot disk)",
            "notes": n.get("notes", ""),
        })
        rows[-1]["_record"] = {"plan": plan, "runinfo": info, "price": p, "cost_record": cost,
                               "manifest_summary": {k: man.get(k) for k in ("versions", "threads", "tta", "folds",
                                                                            "checkpoints_sha256", "errors",
                                                                            "started_utc", "finished_utc")} if man else {},
                               "vm": {k: vm.get(k) for k in ("cpuPlatform", "machineType", "zone", "scheduling",
                                                             "creationTimestamp", "labels", "disks")}}
    return rows


def august_rows(price_cache):
    rows = []
    for r in csv.DictReader(open(os.path.join(REPO, "docs", "calm-ms", "cost-ledger.csv"), encoding="utf-8")):
        count, mt, gpu = parse_machine(r["machine"])
        spot = r["spot"].strip().lower() == "yes"
        ran = bool(r["actual_cost_usd"].strip())
        rate, cost = float(r["hourly_rate_usd"] or 0), float(r["actual_cost_usd"] or 0)
        vm_hours = round(cost / rate, 4) if ran and rate else ""
        key = (mt, "us-central1", spot, gpu)
        if key not in price_cache:
            price_cache[key] = pricing.price(mt, "us-central1", spot=spot, gpu=gpu, disk_gb=10, disk_type="pd-standard")
        p = price_cache[key]
        rows.append({
            "run_id": r["run_id"], "date_utc": r["date"], "project": "brain-mri-476110 (app project, paid account)",
            "purpose": r["purpose"], "paper_or_feature": "CALM-MS (A,C)",
            "status": {"done": "ok", "done-GREEN": "ok", "done-bugs": "failed (pilot bugs fixed)",
                       "planned": "no run time recorded", "running": "no run time recorded"}.get(r["status"], r["status"]),
            "machine_type": mt, "machines": count, "vcpus": p["vcpus"], "memory_gb": p["memory_gb"],
            "cpu_platform": "not recorded", "cpu_model": "not recorded",
            "gpu": gpu or "", "provisioning": "SPOT" if spot else "STANDARD", "zone": r["region"],
            "start_utc": "", "end_utc": "", "wall_seconds": r["actual_seconds"], "vm_hours": vm_hours,
            "setup_seconds": "", "compute_seconds": "", "items_ok": "", "items_failed": "", "median_seconds_per_item": "",
            "usd_per_hour_list": p["usd_per_hour"],
            "cost_usd_list": round(vm_hours * p["usd_per_hour"], 4) if vm_hours != "" else "",
            "cost_usd_recorded": r["actual_cost_usd"],
            "price_basis": (f"Recorded Aug-2026 at an assumed {rate} USD/h; list price re-checked "
                            f"{p['date_utc'][:10]} (Spot prices change; 10 GB pd-standard boot disk assumed)"),
            "notes": r["notes"] + ("" if ran else " — no actual run time in the August ledger")
                     + (f" — {count} machines in parallel; vm_hours is their sum" if count > 1 else ""),
        })
    return rows


def local_rows():
    path = os.path.join(OUT, "local_runs.csv")
    if not os.path.exists(path):
        return []
    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        w = int(r["wall_seconds"]) if r["wall_seconds"].strip() else ""
        rows.append({**{f: "" for f in FIELDS}, **{k: r[k] for k in r if k in FIELDS},
                     "project": "local computer", "provisioning": "own hardware", "wall_seconds": w,
                     "vm_hours": round(w / 3600, 4) if w != "" else "", "usd_per_hour_list": 0,
                     "cost_usd_list": 0, "price_basis": "own computer (electricity not counted)"})
    return rows


def bucket_storage():
    out = sh(f"gcloud storage du -s {BUCKET}").stdout.split()
    gb = int(out[0]) / 1e9 if out and out[0].isdigit() else None
    return gb


ES = {"not recorded": "no registrado", "ok": "correcta", "running": "en curso", "SPOT": "Spot (interrumpible)",
      "STANDARD": "estándar", "own hardware": "equipo propio", "no run time recorded": "sin tiempo registrado",
      "failed (pilot bugs fixed)": "fallida (errores del piloto corregidos)",
      "failed (software environment)": "fallida (entorno de software)", "failed": "fallida"}


def es(v):
    return ES.get(v, v) if isinstance(v, str) else v


def hms(s):
    if s in ("", None):
        return "—"
    s = int(float(s))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def money(x):
    return "—" if x in ("", None) else f"{float(x):.4f}"


def summary(rows, usd_per_eur, ecb_day, storage_gb, built):
    done = [r for r in rows if r["wall_seconds"] not in ("", None)]
    research = [r for r in done if r["project"] == "mstool-research"]
    aug = [r for r in done if r["project"].startswith("brain-mri")]
    tot = lambda rs, k: sum(float(r[k]) for r in rs if r[k] not in ("", None))
    eur = (lambda usd: usd / usd_per_eur) if usd_per_eur else (lambda usd: None)
    st_usd_month = storage_gb * STORAGE_USD_PER_GB_MONTH if storage_gb is not None else None
    used_usd = tot(research, "cost_usd_list") + (st_usd_month or 0)
    used_eur = eur(used_usd)
    L = []
    L.append("# Registro de cómputo de la investigación MSTool-AI\n")
    L.append(f"Generado el {built} con `research/cloud/build_ledger.py`. Precios: **precio oficial de lista de Google "
             f"Cloud en USD** (Cloud Billing Catalog API, consultado el mismo día, con el código SKU de cada parte en "
             f"`records/`). " + (f"Cambio: 1 EUR = {usd_per_eur} USD (tipo de referencia del BCE del {ecb_day}). "
                                if usd_per_eur else "Cambio EUR/USD no disponible hoy. ") +
             "Google factura en EUR con su propio cambio; la cifra exacta se cruza después con el informe de facturación.\n")
    L.append("## Resumen\n")
    L.append("| Concepto | Valor |\n|---|---|")
    L.append(f"| Corridas en la nube con tiempo medido | {len(research)} en mstool-research · {len(aug)} en agosto (brain-mri-476110) |")
    L.append(f"| Horas de máquina, proyecto de investigación | {tot(research, 'vm_hours'):.2f} h |")
    L.append(f"| Coste a precio de lista, proyecto de investigación | {tot(research, 'cost_usd_list'):.2f} USD"
             + (f" ≈ {eur(tot(research, 'cost_usd_list')):.2f} EUR |" if usd_per_eur else " |"))
    if storage_gb is not None:
        L.append(f"| Almacenamiento en el cubo (hoy) | {storage_gb:.2f} GB ≈ {st_usd_month:.3f} USD/mes |")
    if used_eur is not None:
        L.append(f"| Crédito gratuito usado (estimado) | {used_eur:.2f} EUR de {CREDIT_EUR:.0f} EUR "
                 f"(tope propio {CREDIT_TARGET_EUR:.0f} EUR; caduca {CREDIT_EXPIRES}) — quedan ≈ {CREDIT_TARGET_EUR - used_eur:.2f} EUR |")
    L.append(f"| Horas de máquina, agosto (proyecto de la app) | {tot(aug, 'vm_hours'):.2f} h · registrado {tot(aug, 'cost_usd_recorded'):.2f} USD"
             f" · a precio de lista de hoy {tot(aug, 'cost_usd_list'):.2f} USD (pagado por la cuenta de la app, no por el crédito) |")
    L.append("")
    L.append("## Máquinas usadas\n")
    L.append("| Máquina | Procesador | vCPU | Memoria (GB) | Tarjeta gráfica | Modalidad | USD/hora (lista) |\n|---|---|---|---|---|---|---|")
    seen = set()
    for r in rows:
        k = (r["machine_type"], r["cpu_platform"], r["provisioning"], r["gpu"])
        if k in seen or r["project"] == "local computer" or (r["wall_seconds"] in ("", None) and r["status"] != "running"):
            continue
        seen.add(k)
        L.append(f"| {r['machine_type']} | {es(r['cpu_platform'])}{(' — ' + r['cpu_model']) if r['cpu_model'] not in ('', 'not recorded') else ''} "
                 f"| {r['vcpus']} | {r['memory_gb']} | {r['gpu'] or '—'} | {es(r['provisioning'])} | {r['usd_per_hour_list']} |")
    L.append("")
    L.append("## Todas las corridas\n")
    L.append("| Fecha | Corrida | Para qué | Máquina | Procesador | Modalidad | Duración (h:mm:ss) | Preparación / cálculo | Casos ok / fallos | s por caso | Coste lista USD | Registrado USD | Estado |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        mach = (f"{r['machines']} × " if int(r.get("machines") or 1) > 1 else "") + r["machine_type"]
        L.append(f"| {r['date_utc']} | {r['run_id']} | {r['purpose_es']} | {mach} | {es(r['cpu_platform'])} | {es(r['provisioning'])} "
                 f"| {hms(r['wall_seconds'])} | {hms(r['setup_seconds'])} / {hms(r['compute_seconds'])} "
                 f"| {r['items_ok'] if r['items_ok'] != '' else '—'} / {r['items_failed'] if r['items_failed'] != '' else '—'} "
                 f"| {r['median_seconds_per_item'] or '—'} | {money(r['cost_usd_list'])} | {money(r['cost_usd_recorded'])} | {es(r['status'])} |")
    L.append("")
    perf = [r for r in research if r["median_seconds_per_item"] not in ("", None)]
    if perf:
        L.append("## Rendimiento medido (FLAMeS, un modelo, un caso, sin TTA)\n")
        L.append("| Corrida | Máquina | Procesador | Mediana s por caso-modelo | USD por caso-modelo (lista) |\n|---|---|---|---|---|")
        for r in perf:
            L.append(f"| {r['run_id']} | {r['machine_type']} | {es(r['cpu_platform'])} | {r['median_seconds_per_item']} "
                     f"| {float(r['median_seconds_per_item']) / 3600 * float(r['usd_per_hour_list']):.5f} |")
        L.append("")
    loc = [r for r in rows if r["project"] == "local computer"]
    if loc:
        L.append("## Computador local\n")
        L.append("| Fecha | Tarea | Equipo | Duración | Notas |\n|---|---|---|---|---|")
        for r in loc:
            L.append(f"| {r['date_utc']} | {r['purpose_es']} | {r['machine_type']} — {r['cpu_model']} | {hms(r['wall_seconds'])} | {r['notes_es'] or r['notes']} |")
        L.append("")
    noted = [r for r in rows if r.get("notes_es") and r["project"] != "local computer"]
    if noted:
        L.append("## Notas por corrida\n")
        for r in noted:
            L.append(f"- **{r['run_id']}**: {r['notes_es']}")
        L.append("")
    L.append("## Cómo se mide\n")
    L.append("- **Duración**: reloj de la propia máquina, desde que arranca hasta que se borra sola (`runinfo.json`), con marca de hora por etapa: preparación del entorno, pesos del modelo, datos, lista de casos, cálculo y final.\n"
             "- **Procesador**: el que Google asigna (`cpuPlatform`) y el modelo que ve el sistema (`lscpu`). Las corridas de agosto no lo registraron.\n"
             "- **Coste**: segundos × precio de lista por hora (núcleos + memoria + disco de arranque con su tamaño real, 50 o 100 GB, según el precio guardado al lanzar cada máquina). No incluye almacenamiento ni red, que van en su propia línea. La red de entrada es gratis y los datos no salen de la región.\n"
             "- **Agosto**: copiado tal cual de `docs/calm-ms/cost-ledger.csv`; allí la tarifa era una estimación, por eso se recalcula también a precio de lista. Las horas de máquina se derivan de coste ÷ tarifa registrados.\n"
             "- **Comprobación**: cada mapa lleva su huella SHA-256 de entrada y de pesos en el manifiesto de la corrida; el piloto 2 reprodujo los mapas de agosto (mismas lesiones, diferencia máx. 0,002 por redondeo).\n")
    return "\n".join(L) + "\n"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(os.path.join(OUT, "records"), exist_ok=True)
    notes_path = os.path.join(OUT, "annotations.json")
    notes = json.load(open(notes_path, encoding="utf-8")) if os.path.exists(notes_path) else {}
    built = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    price_cache = {}
    tmp = tempfile.mkdtemp()
    try:
        rows = cloud_rows(fetch_bucket(tmp), notes, price_cache)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    rows = august_rows(price_cache) + rows + local_rows()
    for r in rows:                                   # human annotations: Spanish text, dates, verified results
        a = notes.get(r["run_id"], {})
        r["machines"] = int(r.get("machines") or 1)
        r["date_utc"] = r["date_utc"] or a.get("date_utc", "")
        r["purpose_es"] = a.get("purpose_es", r["purpose"])
        r["notes_es"] = a.get("notes_es", "")
    rows.sort(key=lambda r: (r["date_utc"] or "9999", r["project"] == "local computer"))
    for r in rows:
        rec = r.pop("_record", None)
        if rec:
            json.dump({"row": r, **rec}, open(os.path.join(OUT, "records", f"{r['run_id']}.json"), "w"), indent=1, default=str)
    with open(os.path.join(OUT, "compute_ledger.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    usd_per_eur, day = ecb_usd_per_eur()
    md = summary(rows, usd_per_eur, day, bucket_storage(), built)
    open(os.path.join(OUT, "COMPUTE_SUMMARY.md"), "w", encoding="utf-8").write(md)
    print(md)


if __name__ == "__main__":
    main()
