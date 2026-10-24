#!/usr/bin/env python3
"""Lesion-detector v3.2 — gate V0: integrity inventory of the 100 SibBMS control inputs.

Run BEFORE the v3.2 pre-registration commit. It records only integrity facts (SHA-256, grid, dtype,
scaling, all-zero ground truth, values decode into [0, 1] yes/no, LST-AI file hashes vs the cloud
manifest). It deliberately prints and stores NO outcome-related quantity: no maximum probability, no
count of voxels >= 0.5, no candidate.

    python research/lesion_detector_v3/inventory_v32.py --controls-root <dir with flames/ and lstai/>
        --lstai-manifest <lstai-ctl.json> [--out docs/research/records/2026-10-24_lesion_detector_v32_inventory.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time

import nibabel as nib
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
CASES = [f"sub-{i:03d}" for i in range(1, 101)]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--controls-root", required=True)
    ap.add_argument("--lstai-manifest", required=True)
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "research", "records",
                                                  "2026-10-24_lesion_detector_v32_inventory.json"))
    a = ap.parse_args()
    man = json.load(open(a.lstai_manifest, encoding="utf-8"))
    man_sha = {c["case"]: {k: v["sha256"] for k, v in c["maps"].items()} for c in man["cases"] if c.get("ok")}
    rows, problems, hashes = {}, [], {}
    ref_shape, ref_aff = None, None
    for case in CASES:
        r = {}
        files = {f"f{k}": os.path.join(a.controls_root, "flames", f"{case}_f{k}_prob.nii.gz") for k in range(5)}
        files["gt"] = os.path.join(a.controls_root, "flames", f"{case}_gt.nii.gz")
        files["lst_ens"] = os.path.join(a.controls_root, "lstai", f"{case}_lstai_prob.nii.gz")
        for j in (1, 2, 3):
            files[f"lst_m{j}"] = os.path.join(a.controls_root, "lstai", f"{case}_lstai_prob_m{j}.nii.gz")
        for k, p in files.items():
            if not os.path.exists(p):
                problems.append(f"{case}: missing {k}")
                continue
            hashes[f"{case}:{k}"] = sha256(p)
            img = nib.load(p)
            shape, aff = tuple(img.shape), np.asarray(img.affine)
            if ref_shape is None:
                ref_shape, ref_aff = shape, aff
            if shape != ref_shape or not np.allclose(aff, ref_aff, atol=1e-4):
                problems.append(f"{case}:{k}: grid differs from sub-001 f0")
            zooms = tuple(round(float(z), 4) for z in img.header.get_zooms()[:3])
            if zooms != (1.0, 1.0, 1.0):
                problems.append(f"{case}:{k}: zooms {zooms}")
            arr = np.asarray(img.get_fdata(dtype=np.float32))
            if not np.isfinite(arr).all():
                problems.append(f"{case}:{k}: non-finite values")
            if k == "gt":
                if int((arr != 0).sum()) != 0:
                    problems.append(f"{case}: ground truth is not all-zero")
            else:
                inside = bool(arr.min() >= -1e-4 and arr.max() <= 1 + 1e-4)    # yes/no only
                if not inside:
                    problems.append(f"{case}:{k}: values outside [0, 1]")
            r[k] = {"dtype": str(img.get_data_dtype()), "scl_slope": None if img.dataobj.slope is None else float(img.dataobj.slope)}
        ms = man_sha.get(case)
        if ms is None:
            problems.append(f"{case}: not in the LST-AI manifest (or not ok)")
        else:
            for k, mk in (("lst_ens", "ens"), ("lst_m1", "1"), ("lst_m2", "2"), ("lst_m3", "3")):
                if hashes.get(f"{case}:{k}") != ms.get(mk):
                    problems.append(f"{case}:{k}: SHA-256 differs from the lstai-ctl manifest")
        rows[case] = r
    digest = hashlib.sha256("".join(f"{k}={v};" for k, v in sorted(hashes.items())).encode()).hexdigest()
    rec = {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "purpose": "v3.2 gate V0 (integrity only; no outcome computed)",
           "controls": len(CASES), "files_hashed": len(hashes), "grid_shape": list(ref_shape) if ref_shape else None,
           "grid_affine": ref_aff.round(4).tolist() if ref_aff is not None else None,
           "lstai_manifest": {"run_id": man.get("run_id"), "tool": man.get("tool"), "errors": man.get("errors"),
                              "sha256": sha256(a.lstai_manifest)},
           "problems": problems, "passed": not problems, "inputs_combined_sha256": digest,
           "inputs_sha256": hashes, "per_case_storage": rows}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1)
    print(f"controls {len(CASES)}, files {len(hashes)}, grid {ref_shape}, problems {len(problems)}, "
          f"passed {rec['passed']}, combined sha {digest[:16]}")
    for p in problems[:20]:
        print("  ", p)


if __name__ == "__main__":
    main()
