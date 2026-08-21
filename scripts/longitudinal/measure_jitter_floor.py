#!/usr/bin/env python3
"""Measure the lesion-scale QC jitter floor on the 40 in-hand MSLesSeg longitudinal pairs.

The pairs are already on the identical MNI grid (zero registration error), so the R_disp of
matched STABLE fiducials is the pure BIOLOGICAL + inter-session SEGMENTATION jitter floor —
the number the adversarial refute demanded as an OUTPUT (not an assumption). If the floor is
close to the 1.0 mm pass cut, the gate has little margin. Runs the shipped `lesion_scale_qc`.

    python scripts/longitudinal/measure_jitter_floor.py

Writes docs/longitudinal-registration/jitter_floor_record.json.
"""
import os, sys, glob, re, json, collections
import numpy as np
import nibabel as nib

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(_HERE, "..", "..", "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.services.registration_qc_service import lesion_scale_qc  # noqa: E402

COHORT = os.path.join("data", "cohorts", "mslesseg-flames")
SPACING = (1.0, 1.0, 1.0)


def _pairs():
    pats = collections.defaultdict(dict)
    for f in sorted(glob.glob(os.path.join(COHORT, "*_gt.nii.gz"))):
        b = os.path.basename(f)
        m = re.match(r"mslesseg_(P\d+)_T(\d+)_gt", b)
        if not m:
            continue
        pats[m.group(1)][int(m.group(2))] = f
    for pat, tps in pats.items():
        ks = sorted(tps)
        for a, b in zip(ks[:-1], ks[1:]):     # consecutive TP{k-1} -> TP{k}
            yield pat, a, b, tps[a], tps[b]


def main():
    floors, measurable, unmeasurable = [], [], []
    for pat, ta, tb, fa, fb in _pairs():
        m1 = (np.asarray(nib.load(fa).get_fdata()) > 0).astype(np.uint8)
        m2 = (np.asarray(nib.load(fb).get_fdata()) > 0).astype(np.uint8)
        res = lesion_scale_qc(m1, m2, SPACING)          # zero registration error -> jitter
        tag = f"{pat}:T{ta}->T{tb}"
        if res.r_disp_mm is not None and res.n_fiducials >= 3 and res.coverage_span_mm:
            floors.append(res.r_disp_mm)
            measurable.append({"pair": tag, "r_disp_mm": round(res.r_disp_mm, 3),
                               "n_fiducials": res.n_fiducials,
                               "coverage_span_mm": round(res.coverage_span_mm, 1)})
        else:
            unmeasurable.append({"pair": tag, "reason": res.reason})
        print(f"{tag}: r_disp={res.r_disp_mm} n_fid={res.n_fiducials} pass={res.qc_pass} :: {res.reason}", flush=True)

    arr = np.array(floors) if floors else np.array([])
    summary = {
        "record": "MSLesSeg jitter-floor characterization (zero registration error)",
        "n_pairs_total": len(measurable) + len(unmeasurable),
        "n_measurable": len(measurable),
        "n_unmeasurable": len(unmeasurable),
        "jitter_floor_mm": {
            "median": round(float(np.median(arr)), 3) if arr.size else None,
            "p90": round(float(np.percentile(arr, 90)), 3) if arr.size else None,
            "max": round(float(arr.max()), 3) if arr.size else None,
        },
        "pass_cut_mm": 1.0,
        "interpretation": (
            "R_disp here is pure biological + segmentation jitter (pairs already MNI-aligned). "
            "If the floor approaches the 1.0mm cut, the gate false-rejects clean pairs; if well "
            "below, the cut has margin. NOTE: most pairs are UNMEASURABLE (fewer than 3 large "
            "well-spread stable fiducials) -> the gate fails closed on them, which is correct "
            "but means the lesion-scale gate can certify only a minority of real MS pairs."),
        "measurable": measurable,
        "unmeasurable_count_by_reason": dict(collections.Counter(
            u["reason"].split(" -> ")[0].split(" (")[0] for u in unmeasurable)),
    }
    out = os.path.join("docs", "longitudinal-registration", "jitter_floor_record.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\nWROTE {out}")
    print(f"measurable {len(measurable)}/{summary['n_pairs_total']} | "
          f"jitter floor median={summary['jitter_floor_mm']['median']} "
          f"p90={summary['jitter_floor_mm']['p90']} max={summary['jitter_floor_mm']['max']} mm")


if __name__ == "__main__":
    main()
