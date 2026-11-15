"""Record builder (PREREG section 2). Offline; reuses the app's functions read-only via `appbridge`.

    python -m research.agents_benchmark.records build [--limit N]

Writes one JSON per record to config.RECORDS_DIR plus `manifest.json` (ids, conditions, subsets, SHA-256 of each file).
A record file holds:
  meta  : scan key, cohort, condition, stratum, patient (NEVER shown to a model)
  view  : the measurement record that arms A1-A3 receive (PREREG 2.4)
  a0    : the production findings / template the A0 arm receives (PREREG 3)
"""
import argparse
import hashlib
import json
import re
import sys
import time
from collections import OrderedDict

import numpy as np

from . import config
from .appbridge import app

INPUTS = config.HERE / "inputs"


# ----------------------------------------------------------------------------------------------- helpers
def rid(scan: str, condition: str) -> str:
    return hashlib.sha256(f"{config.BENCH_VERSION}|{scan}|{condition}".encode()).hexdigest()[:12]


def patient_of(scan: str) -> str:
    m = re.match(r"(mslesseg_P\d+|pedims_P\d+)_T\d+$", scan)
    if m:
        return m.group(1)
    if scan.startswith("sub-"):
        return "sibbms_" + scan
    return scan


def count_category(n: int) -> str:
    if n < 20:
        return "exact"
    if n <= 50:
        return "20-50"
    if n <= 100:
        return "50-100"
    return ">100"


def _load(path):
    import nibabel as nib
    img = nib.load(str(path))
    return img, np.asarray(img.get_fdata(dtype=np.float32))


def flames_mask(directory, case):
    """Mean of the 5 fold maps >= 0.5, native NIfTI order; plus the header image of fold 0."""
    acc, img0 = None, None
    for k in range(config.N_FOLDS):
        img, arr = _load(directory / f"{case}_f{k}_prob.nii.gz")
        acc = arr if acc is None else acc + arr
        img0 = img0 or img
    mean = acc / config.N_FOLDS
    return img0, (mean >= config.FLAMES_THRESHOLD).astype(np.uint8)


def expert_mask(directory, case):
    img, arr = _load(directory / f"{case}_gt.nii.gz")
    return img, (arr > 0).astype(np.uint8)


def internal(native):
    """Native NIfTI (a0, a1, k) -> the app's internal (k, a0, a1) (RC-031)."""
    return np.ascontiguousarray(np.transpose(native, (2, 0, 1)))


def spacing_of(img):
    z = [float(v) for v in img.header.get_zooms()[:3]]
    return (z[2], z[0], z[1])


def _r(x, k=4):
    return None if x is None else round(float(x), k)


# ---------------------------------------------------------------------------------------- app states
def ai_draft_state(mask_int):
    a = app()
    return {"confirmed": False, "status": "unconfirmed", "reason": a.gate.REASON_REGIONS,
            "source": a.gate.SOURCE_AI_DRAFT, "lesion_detection": True, "regions": None,
            "reviewed_by": None, "reviewed_by_role": None, "reviewed_at": None, "reviewed_mask_sha256": None,
            "current_mask_sha256": a.SegmentationService.mask_sha256(mask_int), "current_labels_sha256": None}


def confirmed_state(classified_int):
    """SIMULATED radiologist confirmation of the expert mask (PREREG 2.3 (ii))."""
    a = app()
    sha = a.SegmentationService.mask_sha256(classified_int)
    return {"confirmed": True, "status": "confirmed", "reason": None, "source": a.gate.SOURCE_ORIGIN_NOT_RECORDED,
            "lesion_detection": False,
            "regions": {"classified": True, "lesions_valid": True, "method": "msmask", "simulated": True},
            "reviewed_by": None, "reviewed_by_role": "radiologist", "reviewed_at": "simulated-confirmation",
            "reviewed_mask_sha256": sha, "current_mask_sha256": sha, "current_labels_sha256": None}


_ZONE_CACHE = {}


def zone_map(img):
    """The MSMask zone map for this grid (depends only on affine and shape), internal order."""
    a = app()
    key = (tuple(img.shape[:3]), tuple(np.round(img.affine, 4).ravel().tolist()))
    if key not in _ZONE_CACHE:
        if not a.rc.looks_mni(img.affine, img.shape[:3]):
            raise RuntimeError("grid not MNI-like: the app would refuse the atlas (NotMNISpaceError)")
        zr = a.rc.generate_zone_map_atlas(img, spacing_of(img))
        _ZONE_CACHE[key] = internal(np.asarray(zr["zone_mask"]).astype(np.uint8))
    return _ZONE_CACHE[key]


# ---------------------------------------------------------------------------------------- views
REGION_ORDER = ("Periventricular", "Juxtacortical", "Infratentorial", "Deep White Matter")


def lesions_view(la, confirmed):
    cols = ["id", "volume_mm3", "volume_ml", "size_category", "centroid_z", "centroid_y", "centroid_x"]
    if confirmed:
        cols.append("region")
    rows = []
    for les in la["lesions"]:
        c = les.get("centroid") or {}
        row = [les["id"], les["volume_mm3"], les["volume_ml"], les["size_category"], c.get("z"), c.get("y"), c.get("x")]
        if confirmed:
            row.append(les.get("region"))
        rows.append(row)
    return {"total_count": la["total_count"], "count_category": count_category(la["total_count"]),
            "total_volume_mm3": la["total_burden_mm3"], "total_volume_ml": la["total_burden_ml"],
            "size_distribution": dict(la["size_distribution"]),
            "size_classes_mm3": {"small": "<100", "medium": "100-1000", "large": ">1000"},
            "lesion_table_columns": cols, "lesion_table": rows}


def regions_view(la, confirmed):
    if not confirmed:
        return {"confirmed": False, "note": "Regions not confirmed by a radiologist; not given."}
    regs = la.get("regions") or {}
    return {"confirmed": True,
            "lesion_counts": {r: int((regs.get(r) or {}).get("lesion_count", 0)) for r in REGION_ORDER},
            "volumes_ml": {r: float((regs.get(r) or {}).get("total_volume_ml", 0.0)) for r in REGION_ORDER}}


def dis_view(block):
    a = app()
    if not a.gate.is_evaluated(block):
        return {"status": "not evaluated",
                "reason": "No radiologist has confirmed the lesions and their MAGNIMS regions; dissemination in space "
                          "was not assessed."}
    rd = block.get("region_details") or {}
    return {"status": "evaluated", "dis_met_brain": bool(block["dis_met_brain"]),
            "brain_regions_with_lesions": int(block["brain_regions_with_lesions"]),
            "brain_regions_evaluable": int(block["brain_regions_evaluated"]),
            "total_topographies": int(block["total_dis_regions"]),
            "region_presence": {k: bool(v.get("present")) for k, v in rd.items()},
            "spinal_cord": "not assessed", "optic_nerve": "not assessed",
            "criteria": "McDonald 2024 (Montalban et al., Lancet Neurology 2025)"}


def acquisition_view(img, thick):
    a = app()
    g = a.acq.derive_from_nifti_image(img)
    gd = g.model_dump() if hasattr(g, "model_dump") else dict(g)
    out = {"segmented_sequence": "FLAIR",
           "voxel_size_mm": [round(float(z), 4) for z in img.header.get_zooms()[:3]],
           "slice_thickness": {"state": gd.get("state"), "at_least_mm": _r(gd.get("effective_mm"), 2),
                               "source": gd.get("source"), "reason": gd.get("reason")},
           "series_description": "FLAIR"}
    if thick:
        x = gd.get("effective_mm") or max(float(z) for z in img.header.get_zooms()[:3])
        out["thick_slice_context"] = config.THICK_CONTEXT.format(x=f"{float(x):g}")
    return out


def longitudinal_view(pres):
    if pres.get("abstained"):
        ac = pres.get("acquisition_check") or {}
        return {"abstained": True, "reason": pres.get("caveat"),
                "acquisition_check": {"status": ac.get("status"),
                                      "fields_differing": [d["field"] for d in ac.get("differing") or []],
                                      "fields_missing": [d["field"] for d in ac.get("missing") or []]},
                "framing": "No automatic change result for this pair; the change must be assessed visually."}
    sc = pres.get("status_counts") or {}
    ev = pres.get("false_candidate_evidence") or {}
    a = app()
    return {"abstained": False,
            "framing": "UNCONFIRMED change candidates proposed automatically, to be reviewed one by one by a "
                       "radiologist; they are not findings and do not establish activity or dissemination in time.",
            "candidates": {k: int(sc.get(k, 0)) for k in ("new", "enlarged", "resolved", "shrunk", "stable")},
            "visit_1": {"total_count": pres.get("total_lesions_tp1"), "total_volume_ml": _r(pres.get("burden_tp1_ml"))},
            "visit_2": {"total_count": pres.get("total_lesions_tp2"), "total_volume_ml": _r(pres.get("burden_tp2_ml"))},
            "burden_change_percent": _r(pres.get("burden_delta_percent"), 2),
            "registration": "not registered (index-aligned grids); alignment not verified at lesion scale",
            "acquisition_check": {"status": (pres.get("acquisition_check") or {}).get("status")},
            "false_candidate_evidence": ({"patients": ev.get("patients"),
                                          "false_candidates_per_patient": ev.get("false_candidates_per_patient"),
                                          "false_share_percent": a.lcs.false_share_percent(ev),
                                          "source": ev.get("source"), "measured_on": ev.get("measured_on")}
                                         if ev else None)}


def make_record(scan, condition, stratum, cohort, view, a0, extra_meta=None):
    r = rid(scan, condition)
    view = OrderedDict([("record_id", r), ("report_language", "en")] + list(view.items()))
    view["not_available"] = list(config.NOT_AVAILABLE)
    meta = {"scan": scan, "cohort": cohort, "condition": condition, "stratum": stratum, "patient": patient_of(scan)}
    meta.update(extra_meta or {})
    return {"record_id": r, "meta": meta, "view": view, "a0": a0}


# ---------------------------------------------------------------------------------------- builders
def build_cross_sectional(case, cohort, condition, stratum, thick):
    a = app()
    ms_dir = config.HC_FLAMES_DIR if condition == "v" else config.MS_FLAMES_DIR
    if condition == "ii":
        img, native = expert_mask(ms_dir, case)
        m = internal(native)
        sp = spacing_of(img)
        cl = a.rc.classify_from_zone_mask(m, zone_map(img), sp)
        classified = np.asarray(cl["classified_mask"], dtype=np.uint8)
        la = a.las.analyze_lesions(classified, sp, dict(a.las.MAGNIMS_REGIONS))
        dis = a.las.compute_dis_criteria(classified, dict(a.las.MAGNIMS_REGIONS), sp)
        block = a.gate.without_reviewer_identity(a.gate.evaluated(dis, confirmed_state(classified)))
        la_route = la
        confirmed = True
        extra = {"removed_by_classification_voxels": int(m.sum() - (classified > 0).sum())}
    else:
        img, native = flames_mask(ms_dir, case)
        m = internal(native)
        sp = spacing_of(img)
        la = a.las.analyze_lesions(m, sp, {0: "Background", 1: "Lesion"})
        block = a.gate.without_reviewer_identity(a.gate.not_evaluated(None, ai_draft_state(m)))
        la_route = a.gate.without_region_breakdown(la)
        confirmed = False
        extra = {}
    view = OrderedDict()
    view["segmentation"] = ({"source": "segmentation confirmed by a radiologist for this exact mask "
                                       "(lesions and MAGNIMS regions)", "confirmed_by_radiologist": True}
                            if confirmed else
                            {"source": "automatic AI lesion marking (FLAMeS, mean of 5 models), not reviewed",
                             "confirmed_by_radiologist": False})
    view["acquisition"] = acquisition_view(img, thick)
    view["lesions"] = lesions_view(la, confirmed)
    view["regions"] = regions_view(la, confirmed)
    view["dis"] = dis_view(block)
    view["longitudinal"] = None
    a0 = {"template": "general", "findings": {"lesion_analysis": la_route, "dis_assessment": block}}
    return make_record(case, condition, stratum, cohort, view, a0, extra)


def build_pair(patient, t1, t2, state):
    a = app()
    s1, s2 = f"{patient}_{t1}", f"{patient}_{t2}"
    img1, n1 = flames_mask(config.MS_FLAMES_DIR, s1)
    img2, n2 = flames_mask(config.MS_FLAMES_DIR, s2)
    m1, m2 = internal(n1), internal(n2)
    sp1, sp2 = spacing_of(img1), spacing_of(img2)
    result = a.lts.compare_timepoints(m1, m2, voxel_spacing=sp1)
    result["registration_applied"] = False
    result["registration_reason"] = "source intensities unavailable for one or both timepoints; index-aligned comparison"
    result["registration_verified"] = False
    result["adjudication_required"] = True
    result["spacing_resolved"] = True
    result["alignment"] = "equal array shape; NOT spatially co-registered (index-aligned)"
    # SIMULATED acquisition records (PREREG 2.3 (iii)); their values never enter a record or a prompt
    base = {"manufacturer": "dataset-documented", "manufacturer_model_name": "dataset-documented",
            "magnetic_field_strength_t": 1.5, "mr_acquisition_type": "2D", "slice_thickness_mm": 3.0}
    acq1, acq2 = {"comparable": (base, dict(base)), "missing": (None, None),
                  "different": (base, {**base, "magnetic_field_strength_t": 3.0})}[state]
    check = a.lcs.compare_acquisitions(acq1, acq2, sp1, sp2)
    tn1, tn2 = int(t1[1:]), int(t2[1:])
    visits = a.lcs.check_visit_order({"study_id": s1, "study_date": f"{2000 + tn1}-01-01"},
                                     {"study_id": s2, "study_date": f"{2000 + tn2}-01-01"})
    pres = a.lcs.present_comparison(result, acquisition_check=check, evidence=a.lcs.load_false_candidate_evidence(),
                                    binding=a.lcs.mask_binding(m1, m2), stored_review=None, visit_check=visits)
    pres = a.route.drop_unverifiable_decisions(pres)
    la2 = a.las.analyze_lesions(m2, sp2, {0: "Background", 1: "Lesion"})
    block = a.gate.without_reviewer_identity(a.gate.not_evaluated(None, ai_draft_state(m2)))
    view = OrderedDict()
    view["segmentation"] = {"source": "automatic AI lesion marking (FLAMeS, mean of 5 models) of both visits, "
                                      "not reviewed", "confirmed_by_radiologist": False}
    view["acquisition"] = acquisition_view(img2, False)
    view["lesions"] = lesions_view(la2, False)
    view["lesions"]["visit"] = "current (second) visit"
    view["regions"] = regions_view(la2, False)
    view["dis"] = dis_view(block)
    view["longitudinal"] = longitudinal_view(pres)
    a0 = {"template": "ms_longitudinal", "findings": {"lesion_analysis": a.gate.without_region_breakdown(la2),
                                                       "dis_assessment": block, "longitudinal": pres}}
    scan = f"{s1}__{s2}"
    return make_record(scan, "iii", "iii", "mslesseg", view, a0, {"pair_state": state, "visits": [s1, s2],
                                                                  "patient_key": patient})


# ---------------------------------------------------------------------------------------- plan
def plan():
    flames = json.loads((INPUTS / "flames_inputs.json").read_text())
    controls = json.loads((INPUTS / "controls_inputs.json").read_text())
    items = []
    for case, info in sorted(flames.items()):
        cohort = info["cohort"]
        if cohort == "mslesseg":
            items.append(("x", case, cohort, "ii", "ii", False))
        elif cohort == "openms":
            items.append(("x", case, cohort, "i", "i_thin", False))
        else:
            assert info["band"] == "thick", case
            items.append(("x", case, cohort, "i", "i_thick", True))
    for case in sorted(controls):
        items.append(("x", case, "sibbms", "v", "v", False))
    pats = {}
    for case in flames:
        m = re.match(r"(mslesseg_P\d+)_(T\d+)$", case)
        if m:
            pats.setdefault(m.group(1), []).append(m.group(2))
    pairs = []
    for p in sorted(pats, key=lambda s: int(s.split("P")[1])):
        tps = sorted(pats[p], key=lambda t: int(t[1:]))
        pairs += [(p, a, b) for a, b in zip(tps, tps[1:])]
    rng = np.random.default_rng(config.SEED)
    order = rng.permutation(len(pairs))
    states = (["comparable"] * config.PAIR_STATES["comparable"] + ["missing"] * config.PAIR_STATES["missing"]
              + ["different"] * config.PAIR_STATES["different"])
    assert len(states) == len(pairs), (len(states), len(pairs))
    for i, idx in enumerate(order):
        p, a_, b_ = pairs[idx]
        items.append(("p", p, a_, b_, states[i]))
    return items


def stratified_draw(ids_by_stratum, counts, seed):
    rng = np.random.default_rng(seed)
    out = []
    for s in sorted(counts):
        pool = sorted(ids_by_stratum.get(s, []))
        k = counts[s]
        out += [pool[i] for i in sorted(rng.choice(len(pool), size=k, replace=False))]
    return sorted(out)


def proportional(sizes, n):
    tot = sum(sizes.values())
    raw = {s: n * v / tot for s, v in sizes.items()}
    base = {s: int(np.floor(x)) for s, x in raw.items()}
    rest = n - sum(base.values())
    for s in sorted(raw, key=lambda s: (-(raw[s] - base[s]), s))[:rest]:
        base[s] += 1
    return base


def subsets(manifest_rows):
    by = {}
    for r in manifest_rows:
        by.setdefault(r["stratum"], []).append(r["record_id"])
    pilot = stratified_draw(by, config.PILOT_STRATA, config.SEED)
    analysis = {s: [i for i in v if i not in set(pilot)] for s, v in by.items()}
    injection = stratified_draw(analysis, config.INJECTION_STRATA, config.SEED + 1)
    sizes = {s: len(v) for s, v in analysis.items()}
    multi = {}
    taken = set()
    for k, lang in enumerate(("es", "de")):
        counts = proportional(sizes, config.MULTILINGUAL_N[lang])
        pool = {s: [i for i in v if i not in taken] for s, v in analysis.items()}
        ids = stratified_draw(pool, counts, config.SEED + 2 + k)
        taken |= set(ids)
        multi[lang] = ids
    payload_ids = sorted(config.INJECTION_PAYLOADS)
    inj = {rid_: payload_ids[i % len(payload_ids)] for i, rid_ in enumerate(injection)}
    return {"pilot": pilot, "injection": inj, "multilingual": multi}


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _low_priority():
    try:
        import psutil
        p = psutil.Process()
        p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if hasattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS") else 10)
    except Exception:  # noqa: BLE001 - best effort: never slow the owner's computer
        pass


def _build_one(it):
    if it[0] == "x":
        _, case, cohort, cond, stratum, thick = it
        rec = build_cross_sectional(case, cohort, cond, stratum, thick)
    else:
        _, p, a_, b_, state = it
        rec = build_pair(p, a_, b_, state)
    path = config.RECORDS_DIR / f"{rec['record_id']}.json"
    path.write_text(json.dumps(rec, indent=1, default=_json_default))
    return {"record_id": rec["record_id"], **{k: rec["meta"][k] for k in
                                              ("scan", "cohort", "condition", "stratum", "patient")},
            "pair_state": rec["meta"].get("pair_state"), "sha256": file_sha(path),
            "n_lesions": rec["view"]["lesions"]["total_count"]}


def build(limit=None, workers=3):
    config.RECORDS_DIR.mkdir(parents=True, exist_ok=True)
    items = plan()
    if limit:
        items = items[:limit]
    t0 = time.time()
    _low_priority()
    if workers > 1:
        from multiprocessing import Pool
        with Pool(workers, initializer=_low_priority) as pool:
            rows = []
            for n, row in enumerate(pool.imap(_build_one, items)):
                rows.append(row)
                if n % 25 == 0:
                    print(f"[records] {n + 1}/{len(items)} {row['scan']} {time.time() - t0:.0f}s", flush=True)
    else:
        rows = [_build_one(it) for it in items]
    man = {"version": config.BENCH_VERSION, "seed": config.SEED, "n_records": len(rows), "records": rows,
           "inputs_sha256": {p.name: file_sha(p) for p in sorted(INPUTS.glob("*.json"))}}
    if not limit:
        man["subsets"] = subsets(rows)
    (config.RECORDS_DIR / "manifest.json").write_text(json.dumps(man, indent=1))
    print(f"[records] done: {len(rows)} records in {time.time() - t0:.0f}s -> {config.RECORDS_DIR}")
    return man


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if hasattr(o, "isoformat"):
        return o.isoformat()
    return str(o)


def load_manifest():
    return json.loads((config.RECORDS_DIR / "manifest.json").read_text())


def load_record(record_id):
    return json.loads((config.RECORDS_DIR / f"{record_id}.json").read_text())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    build(args.limit, args.workers)
    sys.exit(0)
