#!/usr/bin/env python3
"""Paper C — fetch the open_ms_data LONGITUDINAL subset (Lesjak et al. 2016, CC-BY) selectively.

Small files (README, LICENSE, csv, pdf, and per patient: brain mask, change mask, transform .txt)
are always fetched (~1.2 MB). The two co-registered FLAIRs (~10 MB each, 0.29 GB for 20 patients)
are fetched only with --flair, optionally for ONE patient (--patient patientNN) so the analysis can
stream patient by patient on a full disk (extract_candidates.py --stream deletes them after use).
Files go to <dest>/longitudinal/...; sizes are checked against the GitHub tree listing.

    python research/paper_c/fetch_open_ms_longitudinal.py <dest> [--flair] [--patient patientNN]
"""
import argparse
import json
import os
import urllib.request

RAW = "https://raw.githubusercontent.com/muschellij2/open_ms_data/master/"
TREE = "https://api.github.com/repos/muschellij2/open_ms_data/git/trees/master?recursive=1"
_tree_cache = {}


def tree():
    if "t" not in _tree_cache:
        with urllib.request.urlopen(TREE, timeout=120) as r:
            _tree_cache["t"] = json.load(r)["tree"]
    return _tree_cache["t"]


def wanted(flair=False, patient=None):
    out = []
    for e in tree():
        p = e["path"]
        if e["type"] != "blob" or not p.startswith("longitudinal/"):
            continue
        parts = p.split("/")
        if len(parts) == 2:
            out.append((p, e["size"]))
            continue
        if patient and parts[2] != patient:
            continue
        fn = parts[-1]
        if parts[1] == "coregistered":
            if fn in ("gt.nii.gz", "brainmask.nii.gz") or fn.endswith(".txt"):
                out.append((p, e["size"]))
            elif flair and fn in ("study1_FLAIR.nii.gz", "study2_FLAIR.nii.gz"):
                out.append((p, e["size"]))
        elif parts[1] == "raw" and (fn == "gt.nii.gz" or fn.endswith(".txt")):
            out.append((p, e["size"]))
    return out


def fetch(dest, flair=False, patient=None):
    files = wanted(flair, patient)
    for p, size in files:
        out = os.path.join(dest, *p.split("/"))
        if os.path.exists(out) and os.path.getsize(out) == size:
            continue
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with urllib.request.urlopen(RAW + p, timeout=300) as r:
            data = r.read()
        if len(data) != size:
            raise IOError(f"size mismatch for {p}: {len(data)} != {size}")
        with open(out, "wb") as f:
            f.write(data)
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dest")
    ap.add_argument("--flair", action="store_true")
    ap.add_argument("--patient")
    a = ap.parse_args()
    files = fetch(a.dest, a.flair, a.patient)
    print(f"{len(files)} files, {sum(s for _, s in files) / 1e6:.1f} MB listed; present in {a.dest}")


if __name__ == "__main__":
    main()
