#!/usr/bin/env python3
"""Benchmark: AI (Output Mask) vs expert (Expert Rater), per case.

Provenance is by title (as the data owner confirmed):
  'Expert Rater NN - MS Lesion Annotation'  -> EXPERT ground truth
  'Output Mask N - Lesion Prediction'       -> AI prediction

Each segmentation is mapped to its case by PARSING its file_id
(patients/{pid}/studies/{sid}/...), not by the broken /segmentation/list study
filter. For every case we pair the expert mask with the AI mask, download both,
and compute Dice / HD95 (surface) / ASSD / lesion-wise F1 with the app's own
metric code. Then we aggregate (mean/median/std) across cases.

Masks are in MNI space (181,217,181) at 1 mm iso, so voxel spacing = (1,1,1).

Run (Git Bash or PowerShell), same admin token/env as the inventory:
    python scripts/calm-ms/benchmark_expert_vs_ai.py --out benchmark_results.csv
Options:
    --expert-idx 01   which Expert Rater to use as GT (default 01)
    --ai-idx 1        which Output Mask to use as the AI prediction (default 1)
"""
import argparse
import collections
import csv
import hashlib
import os
import struct
import sys

import numpy as np
import requests

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(_HERE, "..", "..", "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.services.segmentation_comparison_service import compare_two_masks  # noqa: E402
try:
    from app.security.storage_access import parse_patient_storage_ref  # noqa: E402
except Exception:
    parse_patient_storage_ref = None

API = os.environ.get("MSTOOL_API_BASE", "https://brain-mri-7bp6oqdu7a-uc.a.run.app/api/v1").rstrip("/")
SPACING = (1.0, 1.0, 1.0)  # MNI 1 mm iso


def _headers():
    tok = os.environ.get("MSTOOL_ADMIN_TOKEN")
    if tok:
        return {"Authorization": "Bearer " + tok}
    pw = os.environ.get("ADMIN_DEFAULT_PASSWORD")
    if not pw:
        sys.exit("Set MSTOOL_ADMIN_TOKEN (preferred) or ADMIN_DEFAULT_PASSWORD.")
    r = requests.post(API + "/auth/login", json={"username": "admin", "password": pw}, timeout=120)
    r.raise_for_status()
    return {"Authorization": "Bearer " + r.json()["token"]["access_token"]}


def _items(p):
    if isinstance(p, dict) and "items" in p:
        return p["items"]
    return p if isinstance(p, list) else ([] if p is None else [p])


def list_all_segs(H):
    for attempt in range(3):
        try:
            r = requests.get(API + "/segmentation/list", headers=H, params={"limit": 5000}, timeout=180)
            if r.status_code == 200:
                return _items(r.json())
            print("  list HTTP %s, retry..." % r.status_code, flush=True)
        except requests.exceptions.RequestException as e:
            print("  list failed (%s), retry..." % e, flush=True)
    sys.exit("Could not list segmentations.")


def download_mask(H, seg_id):
    r = requests.get(API + "/segmentation/" + seg_id + "/mask/binary", headers=H, timeout=120)
    if r.status_code != 200 or len(r.content) < 12:
        return None
    buf = r.content
    d, h, w = struct.unpack("<III", buf[:12])
    body = buf[12:12 + d * h * w]
    if len(body) != d * h * w:
        return None
    return np.frombuffer(body, dtype=np.uint8).reshape((d, h, w))


def case_of(file_id):
    """(patient_id, study_id) from a file_id, or (file_id, '') if unparseable."""
    if parse_patient_storage_ref and file_id:
        try:
            ref = parse_patient_storage_ref(file_id)
            return (ref.patient_id, ref.study_id)
        except Exception:
            pass
    return (file_id or "?", "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="benchmark_results.csv")
    ap.add_argument("--expert-idx", default="01", help="Expert Rater index used as GT.")
    ap.add_argument("--ai-idx", default="1", help="Output Mask index used as AI prediction.")
    args = ap.parse_args()

    exp_desc = "Expert Rater %s" % args.expert_idx
    ai_desc = "Output Mask %s" % args.ai_idx

    H = _headers()
    print("Listing all segmentations (server hydrates masks — may take 1-3 min)...", flush=True)
    segs = list_all_segs(H)
    print("Distinct segmentations: %d\n" % len(segs), flush=True)

    # Map: case -> {'expert': seg_id, 'ai': seg_id}
    cases = collections.defaultdict(dict)
    for s in segs:
        meta = s.get("metadata", {}) or {}
        desc = (meta.get("description") or s.get("description") or "").strip()
        fid = s.get("file_id") or meta.get("file_id")
        sid = s.get("segmentation_id") or s.get("id")
        key = case_of(fid)
        if desc.startswith(exp_desc):
            cases[key]["expert"] = sid
        elif desc.startswith(ai_desc):
            cases[key]["ai"] = sid

    paired = {k: v for k, v in cases.items() if "expert" in v and "ai" in v}
    print("Cases with BOTH %r and %r: %d\n" % (exp_desc, ai_desc, len(paired)), flush=True)

    rows = []
    for i, (key, v) in enumerate(sorted(paired.items()), 1):
        exp = download_mask(H, v["expert"])
        ai = download_mask(H, v["ai"])
        if exp is None or ai is None:
            print("  [%2d] %s  <download failed>" % (i, key[0][:8]), flush=True)
            continue
        if exp.shape != ai.shape:
            print("  [%2d] %s  shape mismatch %s vs %s" % (i, key[0][:8], exp.shape, ai.shape), flush=True)
            continue
        # A = prediction (AI), B = reference (expert)
        res = compare_two_masks(ai, exp, label_a="AI", label_b="Expert", voxel_spacing=SPACING)
        ld = res.get("lesion_detection", {}) or {}
        row = {
            "patient_id": key[0], "study_id": key[1],
            "dice": res.get("dice"),
            "hd95_mm": res.get("hausdorff_mm"),
            "assd_mm": res.get("assd_mm"),
            "lesion_f1": ld.get("lesion_f1"),
            "sensitivity": ld.get("sensitivity_ltpr"),
            "precision": ld.get("precision_lppv"),
            "expert_vox": int((exp > 0).sum()), "ai_vox": int((ai > 0).sum()),
        }
        rows.append(row)
        print("  [%2d] %s  Dice=%.3f HD95=%s ASSD=%s F1=%.3f"
              % (i, key[0][:8], row["dice"],
                 ("%.1f" % row["hd95_mm"]) if row["hd95_mm"] is not None else "NA",
                 ("%.1f" % row["assd_mm"]) if row["assd_mm"] is not None else "NA",
                 row["lesion_f1"] if row["lesion_f1"] is not None else float("nan")), flush=True)

    if not rows:
        sys.exit("\nNo comparable case pairs found.")

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    def agg(name):
        vals = [r[name] for r in rows if isinstance(r[name], (int, float))]
        if not vals:
            return "n/a"
        a = np.array(vals, dtype=float)
        return "mean=%.3f  median=%.3f  std=%.3f  min=%.3f  max=%.3f  (n=%d)" % (
            a.mean(), np.median(a), a.std(), a.min(), a.max(), len(a))

    print("\n" + "=" * 70)
    print("AI vs EXPERT — AGGREGATE (%d cases)" % len(rows))
    print("=" * 70)
    for m in ["dice", "hd95_mm", "assd_mm", "lesion_f1", "sensitivity", "precision"]:
        print("  %-12s %s" % (m, agg(m)))
    print("\nPer-case CSV: %s" % os.path.abspath(args.out))


if __name__ == "__main__":
    main()
