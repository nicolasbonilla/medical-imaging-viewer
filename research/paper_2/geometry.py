"""Acquisition blocks of the paper-2 records (PREREG §2; record-builder rules in §12).

Each block is computed with the CURRENT app's `acquisition_geometry.derive_from_nifti_image`, from the main checkout,
read-only. The input is a header-only image: shape and affine only, no voxel content.

Header sources:
- C1 (MS): paper F's `flames_inputs.json`;
- C2 (SibBMS): paper 1's `controls_inputs.json`;
- A and B: paper 1's prep manifests in the bucket. Only shape and affine are read; no other field is printed or kept.

Run it with the main checkout's backend venv, which has nibabel and pydantic:

    backend/venv/Scripts/python.exe -m research.paper_2.geometry --backend <main>/backend --p1 <paper-1 worktree> \
        --out research/paper_2/runs/geometry.json
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np


def _prep_headers(bucket_prefix="gs://mstool-research-data/mimics/manifests"):
    env = dict(os.environ, CLOUDSDK_CONFIG="C:/Users/Nicolas/.gcloud-mstool")
    ls = subprocess.run(f'gcloud storage ls "{bucket_prefix}/prep-*.json" --project=mstool-research', shell=True,
                        capture_output=True, text=True, env=env).stdout.split()
    out = {}
    for uri in sorted(ls):                                   # later runs win, as paper 1's merged_records
        m = json.loads(subprocess.run(f'gcloud storage cat "{uri}" --project=mstool-research', shell=True,
                                      capture_output=True, text=True, env=env).stdout or "{}")
        for iid, r in (m.get("records") or {}).items():
            if "shape" in r and "affine" in r:
                out[iid] = {"shape": json.loads(r["shape"]) if isinstance(r["shape"], str) else r["shape"],
                            "affine": json.loads(r["affine"]) if isinstance(r["affine"], str) else r["affine"]}
    return out


def headers(p1_root):
    sets = json.load(open(os.path.join(p1_root, "research/paper_1/mimics/analysis_sets.json"), encoding="utf-8"))
    fin = json.load(open(os.path.join(p1_root, "research/paper_f/flames_inputs.json"), encoding="utf-8"))
    ctl = json.load(open(os.path.join(p1_root, "research/paper_1/controls_inputs.json"), encoding="utf-8"))
    want_a, want_b = set(sets["A_wmh2017"]), set(sets["B1_sample"]["ids"])
    hd = {}
    for k, v in sets["C1_ms_iso"].items():
        if not v["flames_contaminated"]:
            hd[k] = {"shape": fin[k]["shape"], "affine": fin[k]["affine"]}
    for k in sets["C2_sibbms"]:
        hd[k] = {"shape": ctl[k]["shape"], "affine": ctl[k]["affine"]}
    prep = _prep_headers()
    for k in want_a | want_b:
        if k in prep:
            hd[k] = prep[k]
    missing = sorted((want_a | want_b) - set(prep))
    return hd, missing


def block(acq, shape, affine):
    import nibabel as nib
    img = nib.Nifti1Image(np.broadcast_to(np.uint8(0), tuple(int(x) for x in shape[:3])), np.asarray(affine, float))
    g = acq.derive_from_nifti_image(img)
    gd = g.model_dump() if hasattr(g, "model_dump") else dict(g)
    em = gd.get("effective_mm")
    return {"segmented_sequence": "FLAIR",
            "voxel_size_mm": [round(float(z), 4) for z in img.header.get_zooms()[:3]],
            "slice_thickness": {"state": gd.get("state"), "at_least_mm": round(float(em), 2) if em is not None else None,
                                "source": gd.get("source"), "reason": gd.get("reason")},
            "series_description": "FLAIR"}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", required=True, help="the main checkout's backend (the current app, read-only)")
    ap.add_argument("--p1", required=True, help="the paper-1 worktree (analysis sets, input lists)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    sys.path.insert(0, a.backend)
    from app.services import acquisition_geometry as acq                      # read-only use of the app
    hd, missing = headers(a.p1)
    out = {k: block(acq, v["shape"], v["affine"]) for k, v in sorted(hd.items())}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(out, open(a.out, "w", encoding="utf-8"), indent=1)
    states = {}
    for v in out.values():
        s = v["slice_thickness"]["state"]
        states[s] = states.get(s, 0) + 1
    print(json.dumps({"scans": len(out), "missing_headers": missing[:10], "n_missing": len(missing),
                      "states": states}, indent=1))
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
