"""Score MS-lesion predictions on the public-leaderboard metrics (voxel + lesion-wise).

Two axes the field always reports together (see segmentation_comparison_service docstring):

  * VOXEL overlap: Dice (both-empty -> 1.0).
  * LESION detection (18-connectivity, ISBI-2015 / MSSEG-2016 any-voxel convention):
    per-case TPR (LTPR), PPV (LPPV = 1 - LFPR), F1, plus TP/FP/FN counts.

Metrics come from the repo's audited implementation when reachable (RC-030 18-conn
labelling + `compute_lesion_detection_metrics`); a convention-identical vendored fallback
keeps the benchmark runnable on a bare Kaggle/Colab checkout (see `_bridge`).

Aggregation reports BOTH conventions the leaderboards use:
  * MACRO  = unweighted mean of per-case metrics (each patient counts once).
  * MICRO  = pooled TP/FP/FN across all cases, then one F1 (challenge "overall" number).
The FLAMeS single-FLAIR reference bar is Dice ~0.74; treat that as the target, not a floor.

Writes a small results table (CSV + Markdown). Importable; a synthetic pair is covered by
test_pipeline.py on CPU.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
from typing import Optional

import numpy as np
import nibabel as nib

from _bridge import (
    compute_dice,
    compute_lesion_detection_metrics,
    USING_REPO_METRICS,
    bridge_status,
)


def score_case(pred_mask: np.ndarray, ref_mask: np.ndarray,
               voxel_spacing: Optional[tuple] = None,
               min_overlap_ratio: float = 0.0) -> dict:
    """Voxel Dice + lesion-wise TPR/PPV/F1 for one (prediction, reference) pair."""
    pred = np.asarray(pred_mask)
    ref = np.asarray(ref_mask)
    if pred.shape != ref.shape:
        raise ValueError(f"shape mismatch: pred {pred.shape} vs ref {ref.shape}")
    det = compute_lesion_detection_metrics(pred, ref, min_overlap_ratio, voxel_spacing)
    return {
        "dice": round(compute_dice(pred, ref), 4),
        "lesion_tpr": det["sensitivity_ltpr"],
        "lesion_ppv": det["precision_lppv"],
        "lesion_f1": det["lesion_f1"],
        "ref_lesions": det["ref_lesion_count"],
        "pred_lesions": det["pred_lesion_count"],
        "tp": det["true_positives"],
        "fp": det["false_positives"],
        "fn": det["false_negatives"],
    }


def aggregate(per_case: list[dict]) -> dict:
    """Macro means + micro (pooled-count) lesion F1 across cases."""
    if not per_case:
        return {}
    keys = ("dice", "lesion_tpr", "lesion_ppv", "lesion_f1")
    macro = {f"macro_{k}": round(float(np.mean([c[k] for c in per_case])), 4) for k in keys}
    tp = sum(c["tp"] for c in per_case)
    fp = sum(c["fp"] for c in per_case)
    fn = sum(c["fn"] for c in per_case)
    micro_ppv = tp / (tp + fp) if (tp + fp) else 1.0
    micro_tpr = tp / (tp + fn) if (tp + fn) else 1.0
    denom = micro_ppv + micro_tpr
    micro_f1 = (2 * micro_ppv * micro_tpr / denom) if denom else 0.0
    macro.update({
        "n_cases": len(per_case),
        "micro_lesion_tpr": round(micro_tpr, 4),
        "micro_lesion_ppv": round(micro_ppv, 4),
        "micro_lesion_f1": round(micro_f1, 4),
        "total_tp": tp, "total_fp": fp, "total_fn": fn,
    })
    return macro


def score_dataset(pairs, voxel_spacing: Optional[tuple] = None,
                  min_overlap_ratio: float = 0.0, verbose: bool = True) -> dict:
    """Score an iterable of (case_id, pred_mask, ref_mask). Returns per-case + aggregate."""
    rows = []
    for case_id, pred, ref in pairs:
        m = score_case(pred, ref, voxel_spacing, min_overlap_ratio)
        m["case"] = case_id
        rows.append(m)
        if verbose:
            print(f"  {case_id}: Dice={m['dice']:.3f} F1={m['lesion_f1']:.3f} "
                  f"(TP{m['tp']} FP{m['fp']} FN{m['fn']})")
    return {"per_case": rows, "aggregate": aggregate(rows),
            "using_repo_metrics": USING_REPO_METRICS}


_COLUMNS = ("case", "dice", "lesion_tpr", "lesion_ppv", "lesion_f1",
            "ref_lesions", "pred_lesions", "tp", "fp", "fn")


def write_results_table(result: dict, out_csv: Optional[str] = None,
                        out_md: Optional[str] = None) -> None:
    """Write per-case rows + an AGGREGATE row to CSV and/or a Markdown table."""
    rows = result["per_case"]
    agg = result["aggregate"]
    if out_csv:
        os.makedirs(os.path.dirname(os.path.abspath(out_csv)) or ".", exist_ok=True)
        with open(out_csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=_COLUMNS)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in _COLUMNS})
        # aggregate as a JSON sidecar (mixed macro/micro keys don't fit the per-case columns)
        with open(os.path.splitext(out_csv)[0] + "_aggregate.json", "w", encoding="utf-8") as fh:
            json.dump(agg, fh, indent=2)
    if out_md:
        os.makedirs(os.path.dirname(os.path.abspath(out_md)) or ".", exist_ok=True)
        lines = ["| " + " | ".join(_COLUMNS) + " |",
                 "| " + " | ".join(["---"] * len(_COLUMNS)) + " |"]
        for r in rows:
            lines.append("| " + " | ".join(str(r.get(k, "")) for k in _COLUMNS) + " |")
        lines += ["", "### Aggregate", "",
                  "| metric | value |", "| --- | --- |"]
        for k, v in agg.items():
            lines.append(f"| {k} | {v} |")
        lines.append("")
        lines.append(f"_metrics source: {'repo (RC-030)' if USING_REPO_METRICS else 'vendored fallback'}; "
                     "FLAMeS single-FLAIR reference Dice ~0.74._")
        with open(out_md, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))


def _load_mask(path: str) -> np.ndarray:
    return (np.asarray(nib.load(path).dataobj) > 0).astype(np.uint8)


def _match_pairs(pred_dir: str, ref_dir: str):
    """Match predictions to references by shared stem (nnU-Net names or *_gt/_mask suffixes)."""
    preds = {}
    for p in sorted(glob.glob(os.path.join(pred_dir, "*.nii*"))):
        stem = os.path.basename(p).split(".")[0]
        preds[stem] = p
    for stem, ppath in preds.items():
        for cand in (stem, stem.replace("_pred", ""), stem + "_gt", stem + "_mask"):
            rpath = None
            for ext in (".nii.gz", ".nii"):
                guess = os.path.join(ref_dir, cand + ext)
                if os.path.exists(guess):
                    rpath = guess
                    break
            if rpath:
                yield stem, _load_mask(ppath), _load_mask(rpath)
                break


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pred-dir", required=True, help="dir of predicted mask NIfTIs")
    ap.add_argument("--ref-dir", required=True, help="dir of reference (GT) mask NIfTIs")
    ap.add_argument("--spacing", type=float, nargs=3, default=None,
                    help="voxel spacing mm (for mm3 size-stratified detection); default voxel counts")
    ap.add_argument("--min-overlap", type=float, default=0.0,
                    help="detection overlap gate (0=ISBI any-voxel; raise for MSSEG-style)")
    ap.add_argument("--out-csv", default="benchmark_results.csv")
    ap.add_argument("--out-md", default="benchmark_results.md")
    args = ap.parse_args(argv)

    print("[bridge]", bridge_status())
    spacing = tuple(args.spacing) if args.spacing else None
    result = score_dataset(_match_pairs(args.pred_dir, args.ref_dir),
                           voxel_spacing=spacing, min_overlap_ratio=args.min_overlap)
    if not result["per_case"]:
        print("No matched (prediction, reference) pairs found.")
        return 1
    write_results_table(result, out_csv=args.out_csv, out_md=args.out_md)
    print("\nAggregate:", json.dumps(result["aggregate"], indent=2))
    print(f"Wrote {args.out_csv} and {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
