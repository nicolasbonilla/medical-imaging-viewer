"""Build the CANDIDATE evidence asset v3 of the slice-thickness reliability card from the paper-1 addendum (C1).

Source: the frozen final evaluation's `results/records.json` (PREREG-mimics-thickness.md section 6.3, "descriptive
dose-response ... size bins of reference lesions" — a registered quantity, not post hoc). C1 = the 145 1-mm MS
examinations (MSLesSeg CC BY 4.0, Ljubljana open_ms_data CC BY: both commercially usable), resectioned to 3, 5 and
7 mm from the same 1 mm scan, so every examination is its own control (no site / scanner confounding, unlike v2).
FLAMeS arms were never run on the 20 FLAMeS-training (contaminated) scans, so no filtering is needed here.

Band mapping (v2 bands, unchanged): B1 <= 1.5 mm <- T = 1 mm; B2 (1.5, 4.5] <- 3 mm; B3 (4.5, 6.5] <- 5 mm;
B4 > 6.5 mm <- 7 mm. Resectioned thickness is a simulation of a thicker acquisition (slab averaging), stated as such.

Size bins: paper F's lesion rule (26-connected components >= 14.137 mm3) and bins 14-50, 50-200, 200-1000,
>= 1000 mm3 — FOUR bins. Lesions below 14.1 mm3 are NOT measured by this experiment; the card must say so and its
validator (frontend/src/utils/sliceThicknessReliability.ts, which requires exactly 5 bins today) must take the bin
count from the asset. That UI change is a separate, reviewed change (RC-057); this script only writes the candidate.

Usage (after `launch_mimics.py evaluate`):
    python research/paper_1/mimics/build_thickness_card_v3.py [--arm flames_f0] [--boot 10000]
Writes results/sliceThicknessReliability.v3.candidate.json. Nothing is copied into the app.
"""
import argparse
import hashlib
import json
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
BINS = ("14-50", "50-200", "200-1000", ">=1000")
EDGES_MM3 = (14.137, 50.0, 200.0, 1000.0, None)
THICK_TO_ROW = {1.0: "B1_grid", 3.0: "B2", 5.0: "B3", 7.0: "B4"}
SEED = 20261112


def diameter(v):
    return None if v is None else round((6.0 * v / math.pi) ** (1.0 / 3.0), 2)


def patient_of(base):
    # mslesseg_P10_T1 -> mslesseg_P10 (time points of one patient form one cluster); openms_patient01 -> itself
    parts = base.split("_")
    return "_".join(parts[:2]) if base.startswith("mslesseg_") else base


def pooled(rows):
    n = [0] * len(BINS)
    d = [0] * len(BINS)
    for sb in rows:
        for i, b in enumerate(BINS):
            nb, db = sb.get(b, (0, 0))
            n[i] += int(nb)
            d[i] += int(db)
    return n, d


def cluster_ci(by_patient, n_boot, rng):
    """Percentile 95% CI of pooled detection per bin, resampling patients (clusters) with replacement."""
    pats = sorted(by_patient)
    draws = [[] for _ in BINS]
    for _ in range(n_boot):
        sample = [by_patient[pats[rng.randrange(len(pats))]] for _ in pats]
        n, d = pooled([sb for rows in sample for sb in rows])
        for i in range(len(BINS)):
            if n[i]:
                draws[i].append(d[i] / n[i])
    out = []
    for xs in draws:
        if not xs:
            out.append([None, None])
            continue
        xs.sort()
        out.append([round(xs[int(0.025 * (len(xs) - 1))], 4), round(xs[int(0.975 * (len(xs) - 1))], 4)])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="flames_f0", help="segmenter configuration the app runs (default: fold 0)")
    ap.add_argument("--boot", type=int, default=10000)
    a = ap.parse_args()
    path = os.path.join(RESULTS, "records.json")
    raw = open(path, "rb").read()
    recs = json.loads(raw)
    rng = random.Random(SEED)
    rows = {}
    for t, row_id in THICK_TO_ROW.items():
        sel = [r for r in recs if r.get("block") == "C1" and float(r.get("T")) == t
               and r.get("arms", {}).get(a.arm, {}).get("acc")]
        by_patient = {}
        for r in sel:
            by_patient.setdefault(patient_of(r["base"]), []).append(r["arms"][a.arm]["acc"]["size_bins"])
        n, d = pooled([sb for v in by_patient.values() for sb in v])
        rows[row_id] = {
            "thickness_mm_simulated": t,
            "scans": len(sel),
            "patients": len(by_patient),
            "lesions": n,
            "detection": [round(d[i] / n[i], 4) if n[i] else None for i in range(len(BINS))],
            "detection_ci95_cluster_bootstrap": cluster_ci(by_patient, a.boot, rng),
            "post_hoc": False,
        }
    asset = {
        "asset_id": "slice-thickness-reliability",
        "asset_version": "3.0.0-candidate",
        "status": ("CANDIDATE - not in the app. Needs: independent review, the RC-057 validator change (bin count "
                   "from the asset; lesions < 14.1 mm3 shown as 'not measured'), owner approval of HAZ-015 residual."),
        "source": {
            "paper": "Paper 1 addendum, block C1 (controlled section thickness, same examinations at 1/3/5/7 mm)",
            "prereg": "docs/research/paper-1/PREREG-mimics-thickness.md (sections 2.3, 6.3) + amendment d0fdee6",
            "records": {"path": "research/paper_1/mimics/results/records.json",
                        "sha256": hashlib.sha256(raw).hexdigest()},
            "segmenter_arm": a.arm,
            "data_licences": "MSLesSeg CC BY 4.0; Ljubljana open_ms_data CC BY (commercial use permitted)",
            "detection_definition": ("Share of expert lesions (26-connected, >= 14.137 mm3) overlapped by the "
                                     "segmenter's lesions, pooled over examinations; CI: percentile bootstrap "
                                     "resampling patients. Thickness is simulated by slab averaging of 1 mm scans."),
        },
        "size_bins": [{"label": b, "min_mm3": EDGES_MM3[i], "max_mm3": EDGES_MM3[i + 1],
                       "min_diameter_mm": diameter(EDGES_MM3[i]), "max_diameter_mm": diameter(EDGES_MM3[i + 1])}
                      for i, b in enumerate(BINS)],
        "not_measured_below_mm3": 14.137,
        "evidence_rows": rows,
        "band_mapping": {"B1": "1 mm", "B2": "3 mm", "B3": "5 mm", "B4": "7 mm"},
    }
    out = os.path.join(RESULTS, "sliceThicknessReliability.v3.candidate.json")
    json.dump(asset, open(out, "w", encoding="utf-8"), indent=1)
    for rid, r in rows.items():
        print(rid, r["scans"], "scans", r["patients"], "patients", "detection", r["detection"])
    print("written:", out)


if __name__ == "__main__":
    main()
