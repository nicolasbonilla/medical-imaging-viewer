#!/usr/bin/env python3
"""Paper C — input inventory (gate G0). TRUTH ONLY: no detector, candidate, score or flag is computed.

Records, for the protocol's eligibility section:
  * open_ms longitudinal: grids, voxel sizes, interval, number of expert change components and
    their direction (sign of the mean normalised subtraction inside each component);
  * MSLesSeg: patients with >= 2 timepoints, consecutive pairs, approximate new/enlarging truth
    from the per-timepoint masks (common.truth_from_two_masks), scanner / slice thickness change
    between the two timepoints, interval; FLAMeS map grids.

    python -I research/paper_c/inventory.py
"""
import hashlib
import json
import os
import sys

import nibabel as nib
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
from detectors import subtraction  # noqa: E402

OUT = os.path.join(C.RECORDS, "2026-10-21_paper_c_inventory.json")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    rec = {"open_ms_longitudinal": {}, "mslesseg": {}, "input_sha256": {}}
    print("=== open_ms_data longitudinal (Lesjak 2016), expert change truth")
    import csv
    info = {}
    with open(os.path.join(os.path.dirname(C.OMS_LONG), "patient_info.csv")) as f:
        for row in csv.DictReader(f):
            info[f"patient{int(row['patient_id']):02d}"] = row
    for pid in C.oms_long_patients():
        x = C.load_oms_long(pid)
        for k, p in x["paths"].items():
            rec["input_sha256"][f"oms_long/{pid}/{os.path.basename(p)}"] = sha(p)
        s = subtraction(x["flair_a"], x["flair_b"], x["brain"])
        d = s[0]
        t = C.truth_from_change_mask(x["gt"], d, x["brain"], x["voxvol"])[0]
        r = {"shape": list(x["flair_a"].shape), "zooms": [round(z, 3) for z in x["zooms"]],
             "days_between": int(info[pid]["days_between_studies"]), "ms_type": info[pid]["ms_type"],
             "n_change_components": t["n_components"], "n_positive": t["n_positive"],
             "n_positive_clinical": t["n_positive_clinical"], "active": t["active"],
             "component_volumes_mm3": [it["volume_mm3"] for it in t["items"]],
             "component_mean_sub": [it["mean_sub"] for it in t["items"]]}
        rec["open_ms_longitudinal"][pid] = r
        print(f"{pid}: {r['shape']} {r['zooms']} {r['days_between']} d | change comps {r['n_change_components']}"
              f" positive {r['n_positive']} (clinical {r['n_positive_clinical']}) active {r['active']}")
    oms = rec["open_ms_longitudinal"]
    allc = sum(v["n_change_components"] for v in oms.values())
    pos = sum(v["n_positive"] for v in oms.values())
    print(f"open_ms: {len(oms)} patients, active {sum(v['active'] for v in oms.values())}, "
          f"stable {sum(not v['active'] for v in oms.values())}; change components {allc}, positive {pos}")

    print("\n=== MSLesSeg, patients with >= 2 timepoints, approximate truth from per-timepoint masks")
    acq = C.mslesseg_acquisition()
    ages = C.mslesseg_ages()
    tps = C.mslesseg_timepoints()
    multi = {p: t for p, t in tps.items() if len(t) >= 2}
    rec["mslesseg"]["patients_multi"] = {p: t for p, t in multi.items()}
    pairs = []
    for p, tl in multi.items():
        for i in range(len(tl) - 1):
            a, b = tl[i], tl[i + 1]
            xa = C.load_mslesseg_tp(p, a, with_prob=False)
            xb = C.load_mslesseg_tp(p, b, with_prob=False)
            if xa["shape"] != xb["shape"] or np.abs(xa["affine"] - xb["affine"]).max() > 1e-3:
                raise ValueError(f"{p} {a}/{b}: grids differ")
            for k in range(5):
                h = nib.load(os.path.join(C.FLAMES, f"mslesseg_{p}_{b}_f{k}_prob.nii.gz"))
                assert h.shape[:3] == xb["shape"]
            t = C.truth_from_two_masks(xa["mask"], xb["mask"], xa["voxvol"])[0]
            qa, qb = acq.get((p, a), {}), acq.get((p, b), {})
            same_scanner = bool(qa and qb and qa["scanner"] == qb["scanner"] and qa["manufacturer"] == qb["manufacturer"])
            interval = (ages.get((p, b), np.nan) - ages.get((p, a), np.nan))
            r = {"patient": p, "a": a, "b": b, "first_pair": i == 0,
                 "n_new_clinical": t["n_new_clinical"], "n_new_detectable": t["n_new_detectable"],
                 "n_enlarging": t["n_enlarging"], "active": t["active"], "active_lenient": t["active_lenient"],
                 "scanner_a": f"{qa.get('manufacturer')} {qa.get('scanner')}", "scanner_b": f"{qb.get('manufacturer')} {qb.get('scanner')}",
                 "slice_a": qa.get("slice_mm"), "slice_b": qb.get("slice_mm"), "same_scanner": same_scanner,
                 "interval_years": None if np.isnan(interval) else round(float(interval), 2),
                 "lesions_a": len(C.components(xa["mask"], xa["voxvol"], C.DETECT_MM3)[1])}
            pairs.append(r)
            print(f"{p} {a}->{b}: new(clin) {r['n_new_clinical']} new(>=3mm3) {r['n_new_detectable']} enl {r['n_enlarging']} "
                  f"active {r['active']} | {r['scanner_a']} {r['slice_a']}mm -> {r['scanner_b']} {r['slice_b']}mm "
                  f"same {same_scanner} | {r['interval_years']} y")
    rec["mslesseg"]["pairs"] = pairs
    fp = [r for r in pairs if r["first_pair"]]
    summ = {"patients_multi": len(multi), "pairs_all": len(pairs), "pairs_first": len(fp),
            "first_active": sum(r["active"] for r in fp), "first_stable": sum(not r["active"] for r in fp),
            "first_stable_lenient": sum(not r["active_lenient"] for r in fp),
            "all_active": sum(r["active"] for r in pairs), "all_stable": sum(not r["active"] for r in pairs),
            "first_same_scanner": sum(r["same_scanner"] for r in fp),
            "first_stable_same_scanner": sum((not r["active"]) and r["same_scanner"] for r in fp)}
    rec["mslesseg"]["summary"] = summ
    rec["open_ms_longitudinal_summary"] = {"patients": len(oms), "active": sum(v["active"] for v in oms.values()),
                                           "change_components": allc, "positive_components": pos}
    print("MSLesSeg summary:", summ)
    os.makedirs(C.RECORDS, exist_ok=True)
    json.dump(rec, open(OUT, "w"), indent=1)
    print("wrote", os.path.relpath(OUT, C.ROOT))


if __name__ == "__main__":
    main()
