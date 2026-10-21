"""Evaluate the brain-DIS decision of every scan under every pipeline of the paper-D grid.

Grid (protocol §5): source S x threshold T x minimum size M x region rule R x registration G.
One row per (scan, S, T, G, R, M) with the PV / JC / IT / DWM lesion counts and the DIS decision.
Lesion-level tables are kept for the expert mask (all G) and the device default source (FLAMeS
fold 0, t = 0.5, G0) for the LST-AI-rule audit (§6 S4) and the stability-indicator study (§6 S5).

The device's own Class C code is CALLED (never modified) for the reference: on every scan, the
expert mask and the device-default mask are also classified with ms_region_classifier.
generate_zone_map_atlas + classify_from_zone_mask and lesion_analysis_service.compute_dis_criteria,
and the run FAILS if the vectorised grid code disagrees with the device on any count or decision.

    python research/paper_d/run_grid.py --data-root <main checkout>/data --workers 4
Outputs (git-ignored): data/experiments/paper-d/grid.csv.gz, lesions_*.csv.gz, run_record.json
"""
from __future__ import annotations

import argparse
import gzip
import json
import logging
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import nibabel as nib  # noqa: E402
import numpy as np  # noqa: E402

from research.paper_d import atlas as A  # noqa: E402
from research.paper_d import rules as RL  # noqa: E402
from research.paper_d.common import (BACKEND_DIR, DEVICE_MSMASK, MSMASK_SHA256, cache_dir,  # noqa: E402
                                     data_root, enumerate_scans, experiments_dir, sha256)

THRESHOLDS = (0.3, 0.4, 0.5, 0.6, 0.7)
PRIMARY_SOURCES = ("F0", "F1", "F2", "F3", "F4", "FENS", "LENS")
SECONDARY_SOURCES = ("L1", "L2", "L3")
ZONE_RULES = ("APP", "APP-LV", "APP-3MM", "APP-MAJ")
LSTAI_RULES = ("LSTAI", "LSTAI-LV")
G_LEVELS = ("G0", "G1", "G2")
DEFAULT = {"source": "F0", "t": 0.5, "M": "v3", "R": "APP", "G": "G0"}   # device automated default
REFERENCE = {"source": "E", "t": None, "M": "v3", "R": "APP", "G": "G0"}  # device rule on expert mask
COLUMNS = ["case", "source", "t", "G", "R", "M", "n_pv", "n_jc", "n_it", "n_dwm", "n_total",
           "vol_total_mm3", "dis", "dis_pv3"]

_ATLAS = {}


def _atlas_space():
    """Atlas-space zone maps and label maps (built once per worker)."""
    if not _ATLAS:
        labels, aff = A.load_labels(DEVICE_MSMASK)
        split, _ = A.split_third_ventricle(labels, aff)
        lab_all = A.ventricle_variant(split, "all")
        lab_lat = A.ventricle_variant(split, "lateral")
        assert np.array_equal(lab_all, labels)
        _ATLAS.update(
            affine=aff, lab_all=lab_all.astype(np.uint8), lab_lat=lab_lat.astype(np.uint8),
            zone={"APP": A.device_zone_map(lab_all), "APP-LV": A.device_zone_map(lab_lat),
                  "APP-3MM": A.device_zone_map(lab_all, mode="distance")},
            third=(split == A.THIRD_VENT).astype(np.uint8), lateral=(split == A.VENT).astype(np.uint8))
        _ATLAS["zone"]["APP-MAJ"] = _ATLAS["zone"]["APP"]
    return _ATLAS


def atlas_maps(scan, shape, affine, cache: Path, levels=G_LEVELS) -> dict:
    """Per-G zone maps (for the zone rules), LST-AI touch masks and the ventricle masks used to
    attribute PV contacts (third vs lateral ventricle), all on the scan grid."""
    at = _atlas_space()
    out = {}
    for G in levels:
        if G == "G1":
            w = cache / "warped"
            orig = np.asarray(nib.load(str(w / f"{scan.case}_msmask.nii.gz")).dataobj).astype(np.int16)
            split = np.asarray(nib.load(str(w / f"{scan.case}_msmask_split3v.nii.gz")).dataobj).astype(np.int16)
            lab_lat = A.ventricle_variant(split, "lateral")
            zone = {"APP": A.device_zone_map(orig), "APP-LV": A.device_zone_map(lab_lat),
                    "APP-3MM": A.device_zone_map(orig, mode="distance")}
            lab_all_s, lab_lat_s = orig, lab_lat
            third_s, lateral_s = split == A.THIRD_VENT, split == A.VENT
        else:
            src_aff = at["affine"] if G == "G0" else A.perturbation_matrix(A.case_seed(scan.case)) @ at["affine"]
            rs = lambda m: A.resample_nearest(m, src_aff, shape, affine)  # noqa: E731
            zone = {k: rs(at["zone"][k]) for k in ("APP", "APP-LV", "APP-3MM")}
            lab_all_s, lab_lat_s = rs(at["lab_all"]), rs(at["lab_lat"])
            third_s, lateral_s = rs(at["third"]) > 0, rs(at["lateral"]) > 0
        zone["APP-MAJ"] = zone["APP"]
        out[G] = {
            "zone": zone,
            "touch": {"LSTAI": RL.lstai_touch_masks(lab_all_s), "LSTAI-LV": RL.lstai_touch_masks(lab_lat_s)},
            "touch_third": A.ndi.binary_dilation(third_s, structure=A.CUBE),
            "touch_lateral": A.ndi.binary_dilation(lateral_s, structure=A.CUBE),
        }
    return out


def load_sources(scan):
    """Raw uint8 probability codes k (p = k / 255) per source; the expert mask as bool."""
    def raw(path):
        img = nib.load(path)
        k = np.asarray(img.dataobj.get_unscaled())
        if k.dtype != np.uint8:
            raise TypeError(f"{path}: expected uint8 probability codes, got {k.dtype}")
        return img, k
    gt_img = nib.load(scan.gt)
    src = {"E": np.asarray(gt_img.dataobj) > 0}
    folds = []
    for i, p in enumerate(scan.flames):
        img, k = raw(p)
        src[f"F{i}"] = k
        folds.append(k.astype(np.uint16))
        _check_grid(gt_img, img, p)
    src["FENS"] = sum(folds)                     # sum of 5 codes; p_ens = sum / (5 * 255)
    img, src["LENS"] = raw(scan.lstai_ens)
    _check_grid(gt_img, img, scan.lstai_ens)
    for i, p in enumerate(scan.lstai_models, 1):
        img, src[f"L{i}"] = raw(p)
        _check_grid(gt_img, img, p)
    return gt_img, src


def _check_grid(ref, img, path):
    if ref.shape != img.shape or not np.allclose(ref.affine, img.affine, atol=1e-4):
        raise ValueError(f"{path}: grid differs from the expert mask")


def binarise(source: str, arr, t):
    if source == "E":
        return arr
    scale = 5 * 255 if source == "FENS" else 255
    return arr >= (t * scale - 1e-6)            # p >= t on the stored codes (protocol §5.2)


def probability(source: str, arr):
    if source == "E":
        return None
    return arr.astype(np.float32) / (5 * 255 if source == "FENS" else 255)


def evaluate_mask(mask, prob, maps, keep_lesions: bool):
    """Rows for one binary mask under every G x R x M, plus optional lesion-level tables."""
    lab18, n18 = RL.label(mask, 18)
    lab26, n26 = RL.label(mask, 26)
    f18 = RL.lesion_features(lab18, n18, prob=prob)
    f26 = RL.lesion_features(lab26, n26, prob=prob)
    vox = np.flatnonzero(mask)
    l18, l26 = lab18.ravel()[vox], lab26.ravel()[vox]
    keeps18 = {m: RL.keep_by_min_size(f18, m) for m in RL.MIN_SIZE_RULES}
    keeps26 = {m: RL.keep_by_min_size(f26, m) for m in RL.MIN_SIZE_RULES}
    rows, lesions = [], []
    for G, mp in maps.items():
        regs = {}
        zcs = {}
        for R in ZONE_RULES:
            z = mp["zone"][R].ravel()[vox]
            zc = np.bincount(l18.astype(np.int64) * 5 + z, minlength=(n18 + 1) * 5).reshape(n18 + 1, 5)[1:]
            zcs[R] = zc
            regs[R] = RL.regions_majority(zc) if R == "APP-MAJ" else RL.regions_contact(zc)
        hits = {}
        for R in LSTAI_RULES:
            h = {L: np.bincount(l26, weights=mp["touch"][R][L].ravel()[vox].astype(np.float64),
                                minlength=n26 + 1)[1:] > 0 for L in (4, 2, 5)}
            hits[R] = h
            reg = np.full(n26, RL.DWM, dtype=np.int8)
            reg[h[5]] = RL.IT
            reg[h[2]] = RL.JC
            reg[h[4]] = RL.PV
            regs[R] = reg
        h = hits["LSTAI"]                       # LST-AI paper / v2 order: PV > IT > JC > SC
        reg = np.full(n26, RL.DWM, dtype=np.int8)
        reg[h[2]] = RL.JC
        reg[h[5]] = RL.IT
        reg[h[4]] = RL.PV
        regs["LSTAI-ORD2"] = reg
        for R, reg in regs.items():
            keeps, feat = (keeps26, f26) if R.startswith("LSTAI") else (keeps18, f18)
            for M, keep in keeps.items():
                c = RL.region_counts(reg, keep)
                rows.append((G, R, M, *c.tolist(), int(keep.sum()), float(feat["volume_mm3"][keep].sum()),
                             int(RL.dis_brain(c)), int(RL.dis_brain(c, pv_min=3))))
        if keep_lesions:
            t3 = {k: np.bincount(l, weights=mp["touch_third"].ravel()[vox].astype(np.float64), minlength=n + 1)[1:] > 0
                  for k, l, n in (("18", l18, n18), ("26", l26, n26))}
            tl = {k: np.bincount(l, weights=mp["touch_lateral"].ravel()[vox].astype(np.float64), minlength=n + 1)[1:] > 0
                  for k, l, n in (("18", l18, n18), ("26", l26, n26))}
            for i in range(n18):
                lesions.append({"G": G, "conn": 18, "id": i + 1, "volume_mm3": float(f18["volume_mm3"][i]),
                                "long_axis_mm": float(f18["long_axis_mm"][i]),
                                "mean_prob": (float(f18["mean_prob"][i]) if prob is not None else None),
                                "APP": int(regs["APP"][i]), "APP-LV": int(regs["APP-LV"][i]),
                                "APP-3MM": int(regs["APP-3MM"][i]), "APP-MAJ": int(regs["APP-MAJ"][i]),
                                "zone_vox": zcs["APP"][i].tolist(), "zone_vox_lv": zcs["APP-LV"][i].tolist(),
                                "touch_third": bool(t3["18"][i]), "touch_lateral": bool(tl["18"][i])})
            for i in range(n26):
                lesions.append({"G": G, "conn": 26, "id": i + 1, "volume_mm3": float(f26["volume_mm3"][i]),
                                "long_axis_mm": float(f26["long_axis_mm"][i]),
                                "mean_prob": (float(f26["mean_prob"][i]) if prob is not None else None),
                                "LSTAI": int(regs["LSTAI"][i]), "LSTAI-LV": int(regs["LSTAI-LV"][i]),
                                "hit4": bool(hits["LSTAI"][4][i]), "hit2": bool(hits["LSTAI"][2][i]),
                                "hit5": bool(hits["LSTAI"][5][i]), "hit4_lv": bool(hits["LSTAI-LV"][4][i]),
                                "touch_third": bool(t3["26"][i]), "touch_lateral": bool(tl["26"][i])})
    return rows, lesions


def device_check(gt_img, mask, zone_device_kij):
    """Device code path (READ-ONLY import): counts + DIS for one mask at G0 with the APP rule."""
    from app.services.lesion_analysis_service import compute_dis_criteria
    from app.services.ms_region_classifier import classify_from_zone_mask
    m = np.transpose(mask.astype(np.uint8), (2, 0, 1))
    res = classify_from_zone_mask(m, zone_device_kij, (1.0, 1.0, 1.0))
    s = res["classification_summary"]
    counts = [s.get("Periventricular", 0), s.get("Juxtacortical", 0), s.get("Infratentorial", 0),
              s.get("Deep White Matter", 0)]
    dis = compute_dis_criteria(res["classified_mask"], voxel_spacing=(1.0, 1.0, 1.0))["dis_met_brain"]
    return counts, int(dis)


def process_scan(scan, cache: Path, out_dir: Path) -> dict:
    os.chdir(BACKEND_DIR)
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    logging.disable(logging.CRITICAL)
    from app.services.ms_region_classifier import generate_zone_map_atlas
    t0 = time.time()
    gt_img, src = load_sources(scan)
    t1img = nib.load(scan.t1)
    _check_grid(gt_img, t1img, scan.t1)
    maps = atlas_maps(scan, gt_img.shape, gt_img.affine, cache)
    zdev = generate_zone_map_atlas(gt_img, (1.0, 1.0, 1.0))["zone_mask"]
    zone_equal = bool(np.array_equal(zdev, maps["G0"]["zone"]["APP"]))
    zdev_kij = np.transpose(zdev, (2, 0, 1))
    rows, lesion_tables, checks = [], {}, {}
    for source, arr in src.items():
        prob_full = probability(source, arr)
        for t in ((None,) if source == "E" else THRESHOLDS):
            mask = binarise(source, arr, t)
            keep_l = (source == "E") or (source == DEFAULT["source"] and t == DEFAULT["t"])
            r, les = evaluate_mask(mask, prob_full, maps, keep_l)
            rows += [(scan.case, source, t, *x) for x in r]
            if keep_l:
                lesion_tables[source] = les
                dc, dd = device_check(gt_img, mask, zdev_kij)
                mine = [x for x in r if x[0] == "G0" and x[1] == "APP" and x[2] == "v3"][0]
                checks[source] = {"device_counts": dc, "device_dis": dd, "grid_counts": list(mine[3:7]),
                                  "grid_dis": mine[9], "equal": dc == list(mine[3:7]) and dd == mine[9]}
    with gzip.open(out_dir / "scans" / f"{scan.case}.json.gz", "wt") as f:
        json.dump({"case": scan.case, "rows": rows, "lesions": lesion_tables}, f)
    return {"case": scan.case, "seconds": round(time.time() - t0, 1), "zone_map_equals_device": zone_equal,
            "device_checks": checks}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--cases", nargs="*")
    args = ap.parse_args()
    root = data_root(args.data_root)
    cache = cache_dir(root)
    out = experiments_dir(root)
    (out / "scans").mkdir(exist_ok=True)
    if sha256(DEVICE_MSMASK) != MSMASK_SHA256:
        raise RuntimeError("MSMask hash mismatch")
    scans = enumerate_scans(root, include_contaminated=True)
    if args.cases:
        scans = [s for s in scans if s.case in set(args.cases)]
    if args.limit:
        scans = scans[: args.limit]
    todo = [s for s in scans if not (out / "scans" / f"{s.case}.json.gz").exists()]
    rec_path = out / "run_record.json"
    record = json.loads(rec_path.read_text()) if rec_path.exists() else {"scans": {}}
    record.update({"thresholds": THRESHOLDS, "sources_primary": PRIMARY_SOURCES,
                   "sources_secondary": SECONDARY_SOURCES, "rules": ZONE_RULES + LSTAI_RULES + ("LSTAI-ORD2",),
                   "min_size": RL.MIN_SIZE_RULES, "registration": G_LEVELS, "default": DEFAULT,
                   "reference": REFERENCE, "columns": COLUMNS,
                   "scan_meta": {s.case: s.as_dict() for s in scans}})
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(process_scan, s, cache, out): s for s in todo}
        for i, f in enumerate(as_completed(futs), 1):
            res = f.result()
            record["scans"][res["case"]] = res
            bad = [k for k, v in res["device_checks"].items() if not v["equal"]] + \
                  ([] if res["zone_map_equals_device"] else ["zone_map"])
            print(f"[{i}/{len(todo)}] {res['case']} {res['seconds']}s device-agreement "
                  f"{'OK' if not bad else 'MISMATCH ' + str(bad)}", flush=True)
            rec_path.write_text(json.dumps(record, indent=1, default=str))
            if bad:
                raise SystemExit(f"grid code disagrees with the device on {res['case']}: {bad}")


if __name__ == "__main__":
    main()
