#!/usr/bin/env python3
"""E5 state C on the research VM (PREREG §12, 2026-11-21): the experts' masks through paper 1's pipeline at its run-3
code (a2affb3, `research/paper_1/mimics/evaluate_mimics.py`, unchanged) with the application's code at e559929 (that
copy's `backend/` replaced; checked by `app_pin`). Run with NO cloud credentials, in paper 1's evaluation environment.

    python research/paper_2/app_design_vm.py --pf ... --mimics ... --wmh ... --manifests ... --atlas-t1 ... --work ...
        --p1 <run-3 results: per_unit.csv, registration.json, records.json> --out <dir> --workers 8

Per unit (WMH 2017: the 170 of `A_wmh2017`; MS: the 125 FLAMeS-clean scans of `C1_ms_iso`):
- the experts' mask: WMH 2017 label 1 (label 2 left out), warped to the MSMask template with run 3's transform
  (`warp_float`, linear, >= 0.5); MS: the expert mask on its own 1-mm grid (> 0.5);
- paper 1's lesion rule (`lesion_set`: 18-connected components >= 3 mm³) and the application's region classification
  (`classify_from_zone_mask`, as `hc_core.AppDIS.run` builds its input);
- with e559929's code on the classified mask: `compute_dis_criteria` (RC-133), the same with RC-133 switched off (the
  recount check), `analyze_lesions` (the lesion table); and `acquisition_geometry.derive_from_nifti_image` on the
  source FLAIR's header (MS: the expert mask's header; its shape and affine checked against paper F's FLAIR).
Gates, before any row is written: the backend is e559929; every WMH 2017 transform's SHA-256 equals run 3's; GR passes
as in run 3; and the DIS without RC-133 equals run 3's experts' DIS for every unit. Otherwise only the gate is written.
"""
import argparse
import contextlib
import csv
import json
import os
import sys
import time
from multiprocessing import Pool
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
REGION = {"Periventricular": "PV", "Juxtacortical": "JC", "Infratentorial": "IT", "Deep White Matter": "DWM"}


@contextlib.contextmanager
def rc133_off(las):
    """The DIS rule before RC-133: every component of at least the volume floor counts (largest extent not checked)."""
    saved = las.largest_extent_at_least
    las.largest_extent_at_least = lambda *a, **k: True
    try:
        yield
    finally:
        las.largest_extent_at_least = saved


def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if hasattr(o, "item"):
        return o.item()
    return o


def classified(app, voxel_lists):
    """The application's classified mask (D, H, W) of a lesion set, built as hc_core.AppDIS.run builds it."""
    import numpy as np
    if not voxel_lists:
        return np.zeros((app.shape[2], app.shape[0], app.shape[1]), np.uint8)
    m = np.zeros(int(np.prod(app.shape)), np.uint8)
    for v in voxel_lists:
        m[v] = 1
    m = np.transpose(m.reshape(app.shape), (2, 0, 1)).copy()
    return np.asarray(app.rc.classify_from_zone_mask(m, app.zone, app.spacing)["classified_mask"])


def app_records(app, cm):
    las = app.las
    dis = las.compute_dis_criteria(cm, voxel_spacing=app.spacing)
    with rc133_off(las):
        old = las.compute_dis_criteria(cm, voxel_spacing=app.spacing)
    la = las.analyze_lesions(cm, app.spacing, las.MAGNIMS_REGIONS)
    return dis, old, la


def one(args):
    u, d, fin = args
    import nibabel as nib
    import numpy as np
    sys.path.insert(0, os.path.join(ROOT, "research", "paper_1", "mimics"))
    import evaluate_mimics as EM
    from app.services import acquisition_geometry as AG
    t0 = time.time()
    if u["block"] == "A":
        img = nib.load(os.path.join(d["mimics"], "inputs", f"{u['base']}_FLAIR.nii.gz"))
        lab = np.rint(np.asarray(nib.load(os.path.join(d["wmh"], u["wmh"])).dataobj)).astype(np.int16)
        mm = (EM.warp_float((lab == 1).astype(np.float32), img, u["base"], d, "e5expert") >= 0.5).astype(np.float32)
        dis_img = nib.load(d["msmask"])
        grid = None
    else:
        img = nib.load(os.path.join(d["pf"], "flames", f"{u['base']}_gt.nii.gz"))
        mm = (np.asarray(img.get_fdata(dtype=np.float32)) > 0.5).astype(np.float32)
        dis_img = img
        f = fin.get(u["base"]) or {}
        grid = {"shape_equal": [int(x) for x in img.shape[:3]] == [int(x) for x in f.get("shape", [])],
                "affine_equal": bool(f.get("affine") is not None and np.allclose(img.affine, np.asarray(f["affine"]),
                                                                                  atol=1e-3))}
    app = EM.app_for(dis_img)
    vl, _vox = EM.lesion_set(mm, dis_img)
    cm = classified(app, vl)
    dis, old, la = app_records(app, cm)
    geo = AG.derive_from_nifti_image(img)
    geo = geo.model_dump() if hasattr(geo, "model_dump") else dict(geo)
    regions = {REGION.get(k, k): v["lesion_count"] for k, v in la["regions"].items()}
    return jsonable({"id": u["base"], "block": u["block"], "cohort": "wmh2017" if u["block"] == "A" else "ms",
                     "n_lesions": len(vl), "dis_rc133": dis, "dis_old_met": bool(old["dis_met_brain"]),
                     "dis_old_regions": {k: bool(v["present"]) for k, v in old["region_details"].items()},
                     "region_counts": regions, "lesion_analysis": la, "thickness_geometry": geo, "grid_check": grid,
                     "seconds": round(time.time() - t0, 1)})


def run3_expert(p1):
    """Run 3's experts' DIS per unit (per_unit.csv: one value per unit, repeated on every arm row)."""
    out = {}
    with open(os.path.join(p1, "per_unit.csv"), newline="") as fh:
        for r in csv.DictReader(fh):
            if r["block"] in ("A", "C1") and r["expert_dis"] in ("0", "1") and "_th" not in r["id"]:
                out[r["id"]] = r["expert_dis"] == "1"
    return out


def run3_records(p1):
    p = os.path.join(p1, "records.json")
    if not os.path.exists(p):
        return {}
    return {r["id"]: r.get("expert") for r in json.load(open(p)) if r.get("block") in ("A", "C1") and r.get("expert")}


def main(argv=None):
    ap = argparse.ArgumentParser()
    for k in ("pf", "mimics", "wmh", "manifests", "atlas-t1", "work", "p1", "out"):
        ap.add_argument(f"--{k}", required=True)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    sys.path.insert(0, os.path.join(ROOT, "backend"))
    sys.path.insert(0, HERE)
    import app_pin
    pin = app_pin.check(ROOT)
    gate = {"app": pin, "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    def stop(why):
        gate.update({"passed": False, "stopped": why})
        json.dump(gate, open(os.path.join(a.out, "e5_vm_gate.json"), "w"), indent=1)
        print("E5 VM gate FAILED:", why, flush=True)
        return 1
    if not pin["passed"]:
        return stop(f"backend is not e559929: {pin['differ_or_missing']}")
    sys.path.insert(0, os.path.join(ROOT, "research", "paper_1", "mimics"))
    import evaluate_mimics as EM
    sets = json.load(open(EM.SETS))
    d = EM.dirs(SimpleNamespace(pf=a.pf, mimics=a.mimics, wmh=a.wmh, work=a.work, manifests=a.manifests,
                                atlas_t1=a.atlas_t1))
    # paper 1's registration step on WMH 2017 only, with run 3's kept transforms (no new affine): the brain-masked atlas
    # T1 that warp_float needs, and GR recomputed
    only_a = {"A_wmh2017": sets["A_wmh2017"], "B1_sample": {"ids": []}, "B_dlbs": {}, "C1_ms_iso": {},
              "C1_samseg_subset": {"ids": []}, "C2_sibbms": []}
    EM.cmd_register(SimpleNamespace(threads=1), d, only_a)
    mine = json.load(open(os.path.join(a.work, "registration.json")))["records"]
    ref = json.load(open(os.path.join(a.p1, "registration.json")))["records"]
    bad = [k for k in sets["A_wmh2017"] if mine.get(k, {}).get("mat_sha256") != ref.get(k, {}).get("mat_sha256")
           or mine.get(k, {}).get("pass") != ref.get(k, {}).get("pass")]
    gate["transforms"] = {"compared": len(sets["A_wmh2017"]), "equal": len(sets["A_wmh2017"]) - len(bad),
                          "gr_pass": sum(bool(mine[k]["pass"]) for k in sets["A_wmh2017"] if k in mine)}
    if bad:
        return stop(f"{len(bad)} transforms or GR decisions differ from run 3, e.g. {bad[:3]}")
    units = [u for u in EM.units(only_a, d) if u["block"] == "A"]
    units += [{"id": c, "base": c, "block": "C1"} for c, v in sorted(sets["C1_ms_iso"].items())
              if not v["flames_contaminated"]]
    fin = json.load(open(os.path.join(ROOT, "research", "paper_f", "flames_inputs.json")))
    with Pool(a.workers) as pool:
        rows = pool.map(one, [(u, d, fin) for u in units], chunksize=1)
    ref_dis, ref_rec = run3_expert(a.p1), run3_records(a.p1)
    mism = [r["id"] for r in rows if ref_dis.get(r["id"]) is None or ref_dis[r["id"]] != r["dis_old_met"]]
    cnt = [r["id"] for r in rows if r["id"] in ref_rec and (ref_rec[r["id"]].get("n") != r["n_lesions"] or any(
        (ref_rec[r["id"]].get("regions") or {}).get(k, 0) != r["region_counts"].get(k, 0) for k in ("PV", "JC", "IT", "DWM")))]
    grid_bad = [r["id"] for r in rows if r["grid_check"] is not None and not all(r["grid_check"].values())]
    gate["recount"] = {"units": len(rows), "wmh2017": sum(r["cohort"] == "wmh2017" for r in rows),
                       "ms": sum(r["cohort"] == "ms" for r in rows), "dis_without_rc133_differs_from_run3": mism,
                       "lesion_or_region_counts_differ_from_run3 (reported, not a gate)": cnt,
                       "ms_grid_differs_from_flames_input (reported)": grid_bad}
    if mism:
        return stop(f"{len(mism)} units: the DIS without RC-133 differs from run 3's experts' DIS, e.g. {mism[:3]}")
    gate.update({"passed": True, "ended_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 "dis_met_rc133": {c: sum(r["dis_rc133"]["dis_met_brain"] for r in rows if r["cohort"] == c)
                                   for c in ("wmh2017", "ms")}})
    with open(os.path.join(a.out, "e5_vm_rows.jsonl"), "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    json.dump(gate, open(os.path.join(a.out, "e5_vm_gate.json"), "w"), indent=1)
    print("E5 VM gate PASSED;", json.dumps({k: gate[k] for k in ("transforms", "dis_met_rc133")}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
