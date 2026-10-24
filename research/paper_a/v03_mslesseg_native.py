#!/usr/bin/env python3
"""Paper A v0.3 — MSLesSeg native FLAIR geometry (POST HOC; added after the v0.3 results).

MSLesSeg is distributed co-registered to MNI 1 mm, so v0.3 put it in the "<= 1.5 mm" band. The
dataset's own acquisition table — `info_dataset/patient_scanners_info/patient_scanners_info_FLAIR.csv`,
part of the public MSLesSeg release (Rondinella/Guarnera et al., Sci Data 2025) — lists the native
FLAIR slice thickness, scanner and sequence timing of every scan. This script
  1. records that table's SHA-256 and the distribution of native slice thickness / scanner over the
     115 MSLesSeg scans used in v0.3;
  2. [post hoc] stratifies MSLesSeg results by native slice thickness (2-2.3 mm, 3 mm, 4-5 mm,
     unknown): raw lesion detection by lesion size and P1 (alpha = 0.2) under leave-one-site-out
     and within-site calibration. Descriptive only (one site, up to 3 scans per patient).

    python research/paper_a/v03_mslesseg_native.py [path/to/patient_scanners_info_FLAIR.csv]
"""
import csv
import json
import os
import pickle
import sys
from collections import Counter


HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import v03_analysis as A                                   # noqa: E402
from v03_candidates import CACHE, sha256                   # noqa: E402
from v03_data import DATA_ROOT, RECORDS                    # noqa: E402

OUT = os.path.join(RECORDS, "2026-10-21_paper_a_v03_mslesseg_native.json")
DEFAULT_CSV = os.path.join(os.path.dirname(DATA_ROOT), "external", "mslesseg", "MSLesSeg Dataset",
                           "info_dataset", "patient_scanners_info", "patient_scanners_info_FLAIR.csv")


def group(th):
    if th is None:
        return "unknown"
    if th <= 2.3 + 1e-9:
        return "2-2.3 mm"
    if th <= 3.0 + 1e-9:
        return "3 mm"
    return "4-5 mm"


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CSV
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig"), delimiter=";"))
    info = {}
    for r in rows:
        t = r["SliceThickness[mm]"]
        th = None if t.strip().upper() == "NONE" else float(t)
        info[(r["Patient"], r["Timepoint"])] = {"thickness": th, "scanner": f"{r['MANUFACTURER']} {r['SCANNER']}",
                                                "tr": r["RT"], "te": r["ET"], "pixel": r["PixelSpacing"]}
    cache = pickle.load(open(CACHE, "rb"))
    ens = A.build(cache, "ens")
    ms = [s for s in ens if s["site"] == "mslesseg"]
    th_of = {}
    for s in ms:
        parts = s["case"].split("_")                       # mslesseg_P10_T1 | mslesseg_P68
        key = (parts[1], parts[2] if len(parts) > 2 else "T1")
        th_of[s["case"]] = info.get(key, {}).get("thickness")
        s["_native"] = group(th_of[s["case"]])
    rec = {"status": "POST HOC (added after the v0.3 results)",
           "source_csv": "MSLesSeg Dataset/info_dataset/patient_scanners_info/patient_scanners_info_FLAIR.csv",
           "source_csv_sha256": sha256(path), "csv_rows": len(rows), "cache_sha256": sha256(CACHE),
           "matched_scans": sum(c in th_of for c in [s["case"] for s in ms]),
           "native_thickness_counts": dict(Counter(str(v) for v in th_of.values())),
           "native_group_counts": dict(Counter(s["_native"] for s in ms)),
           "scanner_counts": dict(Counter(v["scanner"] for v in info.values())),
           "tr_counts": dict(Counter(v["tr"] for v in info.values()))}
    sels = {}
    for d in ("D2", "D1"):
        sels[d], _ = A.run_design(ens, d, [("P1", 0.2), ("P1", 0.1)])
    for g in ("2-2.3 mm", "3 mm", "4-5 mm", "unknown"):
        sub = [s for s in ms if s["_native"] == g]
        if not sub:
            continue
        cell = {"scans": len(sub), "patients": len({s["patient"] for s in sub})}
        sb = A.size_bins(sub, sels["D2"][("P1", 0.2)])
        cell["raw_sensitivity_by_size_bin"] = sb["sens_raw"]
        cell["lesions_by_size_bin"] = sb["n_lesions"]
        for d in ("D2", "D1"):
            for a in (0.1, 0.2):
                sm = A.summarize(sub, sels[d][("P1", a)])
                cell[f"{d}|P1|{a}"] = {"realised_fdr": sm["mean_fdp"], "ci95": sm["mean_fdp_ci"],
                                       "sens_e2e": sm["sens_e2e"], "n_sel": sm["n_sel"]}
        rec[f"group|{g}"] = cell
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1, default=float)
    print(json.dumps(rec, indent=1, default=float))


if __name__ == "__main__":
    main()
