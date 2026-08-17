#!/usr/bin/env python3
"""Deep dive into the duplicated / mislabeled segmentation data.

The metadata inventory (scripts/calm-ms/inventory_expert_masks.py) showed ~20x rows per
(patient, timepoint, rater) and named masks 'Expert Rater 01/02' — but a filename
is NOT proof of a human rater. This script inspects the actual MASK CONTENT to
answer, definitively, for one study:

  1) DUPLICATION: how many segmentations collapse to how many DISTINCT masks
     (by content hash)? Are the ~20 copies byte-identical?
  2) TAXONOMY: what are the genuinely distinct masks, their voxel counts, and
     their pairwise Dice? (So we can tell the human expert from the AI output,
     and see if 'Expert Rater 02' is actually identical to an 'Output Mask'.)
  3) TIMING: the created_at spread of the duplicates (a migration/cross-session
     bug vs deliberate re-annotation).

Downloads mask binaries via GET /segmentation/{id}/mask/binary
(header: uint32 LE depth,height,width; then depth*height*width uint8).

Run (Git Bash) — reuses the same admin token/password env as the inventory:
    python scripts/calm-ms/investigate_duplicates.py --mrn ISBI-MS-001 --study-index 0
"""
import argparse
import collections
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

from app.services.segmentation_comparison_service import compute_dice  # noqa: E402

API = os.environ.get(
    "MSTOOL_API_BASE", "https://brain-mri-7bp6oqdu7a-uc.a.run.app/api/v1"
).rstrip("/")
TIMEOUT = 60


def _headers():
    tok = os.environ.get("MSTOOL_ADMIN_TOKEN")
    if tok:
        return {"Authorization": "Bearer " + tok}
    pw = os.environ.get("ADMIN_DEFAULT_PASSWORD")
    if not pw:
        sys.exit("Set MSTOOL_ADMIN_TOKEN (preferred) or ADMIN_DEFAULT_PASSWORD.")
    r = requests.post(API + "/auth/login", json={"username": "admin", "password": pw}, timeout=TIMEOUT)
    r.raise_for_status()
    return {"Authorization": "Bearer " + r.json()["token"]["access_token"]}


def _items(p):
    if isinstance(p, dict) and "items" in p:
        return p["items"]
    return p if isinstance(p, list) else ([] if p is None else [p])


def _get(H, path, **params):
    r = requests.get(API + path, headers=H, params=params, timeout=TIMEOUT)
    return r.json() if r.status_code == 200 else None


def download_mask(H, seg_id):
    """Return (mask_3d uint8 [D,H,W], sha256_hex, voxel_count) or None."""
    r = requests.get(API + "/segmentation/" + seg_id + "/mask/binary", headers=H, timeout=TIMEOUT)
    if r.status_code != 200 or len(r.content) < 12:
        return None
    buf = r.content
    depth, height, width = struct.unpack("<III", buf[:12])
    body = buf[12:12 + depth * height * width]
    if len(body) != depth * height * width:
        return None
    mask = np.frombuffer(body, dtype=np.uint8).reshape((depth, height, width))
    return mask, hashlib.sha256(body).hexdigest(), int((mask > 0).sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mrn", default=None, help="Patient MRN (default: first patient).")
    ap.add_argument("--study-index", type=int, default=0, help="Which study (by date order).")
    ap.add_argument("--per-group", type=int, default=4,
                    help="Masks to sample per description group (each is ~11 MB).")
    ap.add_argument("--max-total", type=int, default=40, help="Hard cap on downloads.")
    args = ap.parse_args()

    H = _headers()

    patients = _items(_get(H, "/patients", limit=500))
    if args.mrn:
        patients = [p for p in patients if p.get("mrn") == args.mrn] or patients[:1]
    p = patients[0]
    pid, mrn = p["id"], p.get("mrn", p["id"])

    studies = _items(_get(H, "/studies/patient/" + pid, limit=200)) or \
        _items(_get(H, "/studies", patient_id=pid, limit=200))
    studies.sort(key=lambda s: s.get("study_date", "") or "")
    study = studies[args.study_index]
    sid, sdate = study["id"], study.get("study_date", "?")

    segs = _items(_get(H, "/segmentation/list", study_id=sid, limit=500))
    print("=" * 78)
    print("Patient %s  study[%d] date=%s  study_id=%s" % (mrn, args.study_index, sdate, sid))
    print("Segmentations in this study: %d" % len(segs))

    # Group by description so we can SAMPLE a few per type (each mask is ~11 MB).
    groups = collections.defaultdict(list)
    for s in segs:
        meta = s.get("metadata", {}) or {}
        desc = (meta.get("description") or s.get("description") or "").strip()
        groups[desc].append(s)
    print("Description groups (%d): " % len(groups))
    for d, g in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        print("   %4d  %r" % (len(g), d[:50]))
    print("Sampling up to %d per group, %d total.\n" % (args.per_group, args.max_total))
    print("=" * 78)

    # Download + hash a sample from each group.
    records = []  # (seg_id, desc, created_at, hash, voxels, mask)
    n = 0
    for desc, g in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        for s in g[: args.per_group]:
            if n >= args.max_total:
                break
            sid_ = s.get("segmentation_id") or s.get("id")
            meta = s.get("metadata", {}) or {}
            created = meta.get("created_at") or s.get("created_at") or "?"
            got = download_mask(H, sid_)
            n += 1
            if not got:
                print("  %s  <download failed>" % sid_)
                continue
            mask, h, vox = got
            records.append((sid_, desc, str(created), h, vox, mask))
            print("  [%2d] %-34s vox=%-6d hash=%s" % (n, desc[:34], vox, h[:10]), flush=True)
        if n >= args.max_total:
            break

    print("\nDownloaded %d masks." % len(records))

    # 1) DUPLICATION — distinct content hashes.
    by_hash = collections.defaultdict(list)
    for rec in records:
        by_hash[rec[3]].append(rec)
    print("\n--- DUPLICATION ---")
    print("segmentations=%d  DISTINCT content-hashes=%d  (dup factor ~%.1fx)"
          % (len(records), len(by_hash), (len(records) / max(1, len(by_hash)))))

    # 2) TAXONOMY of the distinct masks.
    distinct = []
    print("\n--- DISTINCT MASKS ---")
    for h, recs in sorted(by_hash.items(), key=lambda kv: -len(kv[1])):
        descs = collections.Counter(r[1][:34] for r in recs)
        created = sorted(r[2] for r in recs)
        rep = recs[0]
        distinct.append((h, rep[5], rep[4], descs))
        print("  hash=%s  copies=%3d  voxels=%6d  shape=%s"
              % (h[:10], len(recs), rep[4], tuple(rep[5].shape)))
        for d, c in descs.most_common(4):
            print("        %3dx  %r" % (c, d))
        print("        created_at: %s ... %s" % (created[0], created[-1]))

    # 3) Pairwise Dice among the distinct masks (only if shapes match).
    print("\n--- PAIRWISE DICE (distinct masks) ---")
    labels = ["#%d(%s..)" % (i, distinct[i][0][:6]) for i in range(len(distinct))]
    for i in range(len(distinct)):
        for j in range(i + 1, len(distinct)):
            mi, mj = distinct[i][1], distinct[j][1]
            if mi.shape != mj.shape:
                print("  %s vs %s : shape mismatch %s vs %s"
                      % (labels[i], labels[j], mi.shape, mj.shape))
                continue
            dsc = compute_dice(mi, mj)
            di = list(distinct[i][3])[0][:22]
            dj = list(distinct[j][3])[0][:22]
            print("  Dice=%.4f  #%d(%r, %dvox)  vs  #%d(%r, %dvox)"
                  % (dsc, i, di, distinct[i][2], j, dj, distinct[j][2]))


if __name__ == "__main__":
    main()
