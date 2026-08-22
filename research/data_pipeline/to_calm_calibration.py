#!/usr/bin/env python3
"""Emit the CALM-MS calibration format from a base segmenter's outputs + expert masks.

The conformal FDR layer (``app.services.conformal_lesion_fdr``) calibrates on a set
of lesion CANDIDATES for which we know, per candidate: its **score** (the conformal
statistic), whether it is a false positive (``is_false`` — the null members), and a
**site** tag (for site-conditional / Mondrian nulls). This module turns a cohort of
``(probability map, expert mask, site)`` into exactly that table, using the repo's
FROZEN candidate extraction + feature code so the calibration set is byte-for-byte
what the served path scores against:

  * ``extract_lesion_candidates`` — 18-connected components >= threshold, pooled score
  * ``label_candidates_tp``       — TP/FP by voxel overlap with the expert mask
  * ``candidate_feature_matrix``  — the FEATURE_NAMES vector per candidate (lets a
                                    learned scorer be retrained per site)
  * ``load_lesion_scorer`` (opt.) — the frozen learned score, if its asset is present

Outputs
-------
* ``calibration.csv`` — one row per candidate: dataset, case, site, candidate_label,
  ``score`` (pooled), ``is_false`` (True = null member = FP), n_voxels, volume_mm3,
  optional ``edss`` and ``learned_score``, plus every FEATURE_NAMES column.
* ``calibration_nulls.npz`` — ready-to-load conformal nulls: a POOLED null array
  (all FP scores) and a per-site null (``site::<tag>``) array — the two inputs the
  site-recalibration experiment consumes. Also stores the site labels + scores so a
  learned scorer can be refit.

This makes each public site a first-class conformal stratum: calibrate on a site's
own FP scores (diagonal Mondrian null) and externally validate the FDR guarantee on
the others.

Usage
-----
    # from a preprocessed cohort dir that has {case}_prob.nii.gz + {case}_gt.nii.gz
    # and a cohort.csv carrying the `site` column:
    python -m research.data_pipeline.to_calm_calibration \\
        --data-dir ./cohorts/mslesseg --site-from-cohort ./cohorts/mslesseg/cohort.csv \\
        --out ./calib/mslesseg --threshold 0.5 --score mean
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import numpy as np

try:
    from .common import (ensure_backend_on_path, CALIB_BASE_FIELDS, calib_feature_fields)
except ImportError:  # pragma: no cover - direct-script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from common import (ensure_backend_on_path, CALIB_BASE_FIELDS, calib_feature_fields)  # type: ignore


# ---------------------------------------------------------------------------
# case spec loaders
# ---------------------------------------------------------------------------
class CaseSpec(dict):
    """A calibration input: keys case, prob_path, gt_path, site, edss(optional)."""


def cases_from_data_dir(data_dir: str, site: str = "unknown",
                        site_map: Optional[dict] = None,
                        edss_map: Optional[dict] = None) -> List[CaseSpec]:
    """Discover ``{case}_prob.nii*`` + ``{case}_gt.nii*`` pairs in a cohort dir.

    ``site_map``/``edss_map`` (case_id -> value) override the default ``site`` /
    a missing EDSS. This is the same on-disk layout the LST-AI runner writes.
    """
    site_map = site_map or {}
    edss_map = edss_map or {}
    specs: List[CaseSpec] = []
    for prob in sorted(glob.glob(os.path.join(data_dir, "*_prob.nii*"))):
        case = os.path.basename(prob).split("_prob.nii")[0]
        gts = glob.glob(os.path.join(data_dir, case + "_gt.nii*"))
        if not gts:
            continue
        specs.append(CaseSpec(case=case, prob_path=prob, gt_path=gts[0],
                              site=site_map.get(case, site),
                              edss=edss_map.get(case)))
    return specs


def site_map_from_cohort_csv(path: str) -> Tuple[dict, dict]:
    """Read a preprocess.py ``cohort.csv`` -> ({case: site}, {case: edss})."""
    site_map, edss_map = {}, {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            case = row.get("case")
            if not case:
                continue
            if row.get("site"):
                site_map[case] = row["site"]
            edss = row.get("edss")
            if edss not in (None, ""):
                try:
                    edss_map[case] = float(edss)
                except ValueError:
                    pass
    return site_map, edss_map


# ---------------------------------------------------------------------------
# the core: candidates -> calibration rows
# ---------------------------------------------------------------------------
def _load_nifti(path: str):
    import nibabel as nib
    img = nib.load(path)
    return np.asarray(img.get_fdata()), tuple(float(z) for z in img.header.get_zooms()[:3])


def build_calibration_rows(
    cases: Iterable[CaseSpec],
    threshold: float = 0.5,
    spacing: Optional[Tuple[float, float, float]] = None,
    min_volume_mm3: float = 3.0,
    score: str = "mean",
    min_overlap: float = 0.0,
    use_learned_scorer: bool = True,
    dataset: str = "",
) -> List[dict]:
    """Per-candidate calibration rows across a cohort.

    Each row carries the conformal statistic (``score``), the null-membership flag
    (``is_false``), the site tag, and the full feature vector. If the frozen learned
    scorer asset loads, a ``learned_score`` column is added too. ``spacing`` defaults
    to each case's own NIfTI voxel size.
    """
    ensure_backend_on_path()
    from app.services.calm_ms_inference import (extract_lesion_candidates,
                                                label_candidates_tp)
    from app.services.calm_ms_lesion_features import candidate_feature_matrix, FEATURE_NAMES

    scorer = None
    if use_learned_scorer:
        try:
            from app.services.calm_ms_scorer import load_lesion_scorer
            scorer = load_lesion_scorer()
        except Exception as e:            # asset optional — pooled score still works
            print(f"    [info] learned scorer unavailable ({e}); pooled score only")

    rows: List[dict] = []
    for spec in cases:
        prob, sp = _load_nifti(spec["prob_path"])
        gt, _ = _load_nifti(spec["gt_path"])
        prob = prob.astype(float)
        gt = (gt > 0).astype(np.uint8)
        if prob.shape != gt.shape:
            raise ValueError(f"[{spec['case']}] prob {prob.shape} vs gt {gt.shape} mismatch")
        use_sp = spacing or sp
        labeled, cands = extract_lesion_candidates(
            prob, threshold, use_sp, min_volume_mm3=min_volume_mm3, score=score)
        if not cands:
            continue
        is_tp = label_candidates_tp(labeled, cands, gt, min_overlap=min_overlap)
        feats = candidate_feature_matrix(prob, labeled, cands, use_sp)
        learned = scorer.score(feats) if scorer is not None else [None] * len(cands)

        for i, c in enumerate(cands):
            row = {
                "dataset": dataset or spec.get("dataset", ""),
                "case": spec["case"],
                "site": spec.get("site", "unknown"),
                "candidate_label": int(c.label),
                "score": float(c.score),
                "is_false": bool(not is_tp[c.label]),
                "n_voxels": int(c.n_voxels),
                "volume_mm3": round(float(c.volume_mm3), 2),
                "edss": spec.get("edss"),
            }
            if scorer is not None:
                row["learned_score"] = float(learned[i])
            for j, name in enumerate(FEATURE_NAMES):
                row[name] = float(feats[i, j])
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# conformal-null assembly (what the conformal layer actually loads)
# ---------------------------------------------------------------------------
def pooled_null(rows: List[dict], score_key: str = "score") -> np.ndarray:
    """All FALSE-candidate scores across every site — the shipped one-size null."""
    return np.asarray([r[score_key] for r in rows if r["is_false"]], dtype=float)


def site_conditional_nulls(rows: List[dict], score_key: str = "score") -> dict:
    """{site: FP-score array} — the Mondrian nulls for site-conditional calibration."""
    out: dict[str, list] = {}
    for r in rows:
        if r["is_false"]:
            out.setdefault(r["site"], []).append(r[score_key])
    return {s: np.asarray(v, dtype=float) for s, v in out.items()}


def write_calibration(rows: List[dict], out_dir: str,
                      score_key: str = "score") -> Tuple[str, str]:
    """Write ``calibration.csv`` + ``calibration_nulls.npz``.

    The CSV is the human/audit artifact; the npz is the machine artifact the
    conformal experiment loads (pooled null + per-site nulls + raw score/site/label
    arrays so a learned scorer can be refit)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    feature_fields = calib_feature_fields()
    extra = ["learned_score"] if rows and "learned_score" in rows[0] else []
    fields = CALIB_BASE_FIELDS + extra + feature_fields

    csv_path = out / "calibration.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    nulls = site_conditional_nulls(rows, score_key)
    npz_path = out / "calibration_nulls.npz"
    payload = {
        "pooled_null": pooled_null(rows, score_key),
        "scores": np.asarray([r[score_key] for r in rows], dtype=float),
        "is_false": np.asarray([r["is_false"] for r in rows], dtype=bool),
        "sites": np.asarray([r["site"] for r in rows], dtype=object),
        "cases": np.asarray([r["case"] for r in rows], dtype=object),
    }
    for site, arr in nulls.items():
        payload[f"site::{site}"] = arr
    np.savez(npz_path, **payload)

    # a small human-readable summary alongside
    summary = {
        "n_candidates": len(rows),
        "n_false": int(sum(r["is_false"] for r in rows)),
        "n_true": int(sum(not r["is_false"] for r in rows)),
        "sites": {s: int(a.size) for s, a in nulls.items()},
        "score_key": score_key,
    }
    (out / "calibration_summary.json").write_text(json.dumps(summary, indent=2),
                                                  encoding="utf-8")
    print(f"    wrote {csv_path.name} ({len(rows)} candidates), {npz_path.name} "
          f"({len(nulls)} site null(s)), calibration_summary.json")
    return str(csv_path), str(npz_path)


def build_and_write(data_dir: str, out_dir: str, dataset: str = "",
                    site: str = "unknown", cohort_csv: Optional[str] = None,
                    threshold: float = 0.5, score: str = "mean",
                    min_volume_mm3: float = 3.0,
                    use_learned_scorer: bool = True) -> List[dict]:
    """End-to-end from a cohort dir to the CALM-MS calibration artifacts."""
    site_map, edss_map = ({}, {})
    if cohort_csv:
        site_map, edss_map = site_map_from_cohort_csv(cohort_csv)
    cases = cases_from_data_dir(data_dir, site=site, site_map=site_map, edss_map=edss_map)
    if not cases:
        print(f"[{dataset or data_dir}] no {{case}}_prob/_gt pairs found in {data_dir}")
        return []
    print(f"[{dataset or data_dir}] scoring {len(cases)} case(s) -> calibration rows ...")
    rows = build_calibration_rows(
        cases, threshold=threshold, min_volume_mm3=min_volume_mm3, score=score,
        use_learned_scorer=use_learned_scorer, dataset=dataset)
    write_calibration(rows, out_dir)
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", required=True,
                    help="cohort dir with {case}_prob.nii.gz + {case}_gt.nii.gz")
    ap.add_argument("--out", required=True, help="output dir for calibration artifacts")
    ap.add_argument("--dataset", default="", help="dataset tag to stamp on rows")
    ap.add_argument("--site", default="unknown", help="fallback site tag")
    ap.add_argument("--site-from-cohort", help="cohort.csv to read per-case site/edss from")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--min-volume-mm3", type=float, default=3.0)
    ap.add_argument("--score", default="mean", choices=["mean", "max"])
    ap.add_argument("--no-learned-scorer", action="store_true",
                    help="use pooled probability only (skip the frozen learned scorer)")
    args = ap.parse_args(argv)

    build_and_write(
        args.data_dir, args.out, dataset=args.dataset, site=args.site,
        cohort_csv=args.site_from_cohort, threshold=args.threshold,
        score=args.score, min_volume_mm3=args.min_volume_mm3,
        use_learned_scorer=not args.no_learned_scorer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
