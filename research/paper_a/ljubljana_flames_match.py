#!/usr/bin/env python3
"""Paper A v0.2 — which 20 Ljubljana (open_ms_data) scans did FLAMeS train on? (forensic match)

Evidence used (all public, all small):
  * the nnU-Net `dataset_fingerprint.json` shipped inside the released FLAMeS weights
    (Zenodo 17955359 / HF FrancescoLR/FLAMeS-model, fetched by flames_zip_inspect.py with HTTP
    range requests): for each of the 668 anonymised training cases (FLAIR_001..FLAIR_668, in
    identifier order) the ORIGINAL voxel spacing and the shape of the non-zero (skull-stripped)
    bounding box ("shapes_after_crop"), both in SimpleITK axis order (z, y, x) = reversed NIfTI
    order;
  * the 30 Ljubljana raw FLAIR headers (dims + pixdim) — first ~2 kB of each .nii.gz via HTTP
    range request on github.com/muschellij2/open_ms_data (no image body is downloaded);
  * the 30 Ljubljana brain masks (`cross_sectional/coregistered/patientNN/brainmask.nii.gz`,
    ~0.3 MB each) -> bounding-box shape of the brain in the FLAIR grid.

Logic: (1) the Ljubljana raw FLAIR has a distinctive spacing (0.8 x 0.46875 x 0.46875 mm, NIfTI
order). Fingerprint entries with exactly that spacing (reversed) are the PubMRI training cases.
(2) Each such entry's brain bounding box is matched to the 30 patients' brain-mask bounding
boxes by a minimum-cost one-to-one assignment (Hungarian, L1 distance in voxels). An entry is
attributed to a patient ONLY on an EXACT match (identical spacing and identical box in all three
axes). If FLAMeS had skull-stripped with another tool (e.g. SynthStrip) boxes would differ by a
few voxels and the attribution would be weaker; an exact match on every axis means the dataset's
own brain mask defined the crop. We report each entry's best and second-best distance, the
between-patient box distances (how unlikely a coincidental exact match is), and whether the
matched patient order is monotone in the anonymised identifier (independent corroboration).

Run 2026-10-17 result (record docs/research/records/2026-10-17_flames_ljubljana_split.json):
20 exact matches, monotone, = patients 01-15 and 21-25; held out = 16-20 and 26-30.

    python -I research/paper_a/ljubljana_flames_match.py <fingerprint.json> <download_dir> <out_json>
"""
import gzip
import io
import json
import os
import struct
import sys
import urllib.request
import zlib

import numpy as np

RAW = "https://raw.githubusercontent.com/muschellij2/open_ms_data/master/cross_sectional"
PATIENTS = [f"patient{i:02d}" for i in range(1, 31)]


def _get(url, rng=None, timeout=120):
    req = urllib.request.Request(url, headers={"Range": f"bytes={rng}"} if rng else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def nifti_header(gz_bytes):
    d = zlib.decompressobj(31).decompress(gz_bytes)
    h = d[:348]
    dim = struct.unpack("<8h", h[40:56])
    pix = struct.unpack("<8f", h[76:108])
    return [int(x) for x in dim[1:1 + dim[0]]], [round(float(x), 5) for x in pix[1:1 + dim[0]]]


def mask_bbox_shape(gz_bytes):
    """Bounding-box shape (NIfTI axis order) of the non-zero voxels of a NIfTI-1 .nii.gz."""
    raw = gzip.decompress(gz_bytes)
    h = raw[:348]
    dim = struct.unpack("<8h", h[40:56])
    datatype = struct.unpack("<h", h[70:72])[0]
    vox_offset = int(struct.unpack("<f", h[108:112])[0])
    shape = tuple(int(x) for x in dim[1:1 + dim[0]])
    dt = {2: np.uint8, 4: np.int16, 8: np.int32, 16: np.float32, 64: np.float64, 256: np.int8,
          512: np.uint16, 768: np.uint32}[datatype]
    arr = np.frombuffer(raw, dtype=dt, count=int(np.prod(shape)), offset=vox_offset)
    arr = arr.reshape(shape, order="F")
    nz = np.argwhere(arr > 0)
    lo, hi = nz.min(0), nz.max(0)
    return [int(x) for x in (hi - lo + 1)], shape


def main():
    fp_path, dl_dir, out_json = sys.argv[1:4]
    os.makedirs(dl_dir, exist_ok=True)
    fp = json.load(open(fp_path, encoding="utf-8"))
    sp = [tuple(round(float(v), 4) for v in s) for s in fp["spacings"]]
    sh = [tuple(int(v) for v in s) for s in fp["shapes_after_crop"]]

    pats = {}
    for p in PATIENTS:
        dims, pix = nifti_header(_get(f"{RAW}/raw/{p}/FLAIR.nii.gz", "0-4095"))
        mpath = os.path.join(dl_dir, f"{p}_brainmask.nii.gz")
        if not os.path.exists(mpath):
            with open(mpath, "wb") as fh:
                fh.write(_get(f"{RAW}/coregistered/{p}/brainmask.nii.gz"))
        bb, mshape = mask_bbox_shape(open(mpath, "rb").read())
        pats[p] = {"flair_dims_nifti": dims, "flair_pixdim_nifti": pix,
                   "brainmask_grid": list(mshape), "brain_bbox_nifti": bb,
                   "spacing_sitk_order": [round(v, 4) for v in pix[::-1]],
                   "brain_bbox_sitk_order": bb[::-1]}
        print(f"  {p}: FLAIR dims {dims} pixdim {pix} | brain bbox {bb} (mask grid {list(mshape)})")

    lj_spacings = {tuple(v["spacing_sitk_order"]) for v in pats.values()}
    print(f"\nLjubljana raw FLAIR spacings (sitk order): {sorted(lj_spacings)}")
    cand = [i for i, s in enumerate(sp) if s in lj_spacings]
    print(f"fingerprint entries with a Ljubljana spacing: {len(cand)} -> indices {cand}")

    from scipy.optimize import linear_sum_assignment
    P = np.array([pats[p]["brain_bbox_sitk_order"] for p in PATIENTS], float)
    E = np.array([sh[i] for i in cand], float)
    # spacing must agree exactly; otherwise forbid the pair
    S_ok = np.array([[tuple(pats[p]["spacing_sitk_order"]) == sp[i] for p in PATIENTS] for i in cand])
    C = np.abs(E[:, None, :] - P[None, :, :]).sum(-1)
    C_forbid = np.where(S_ok, C, 1e6)
    ri, ci = linear_sum_assignment(C_forbid)
    rows = []
    for r, c in zip(ri, ci):
        order = np.argsort(C_forbid[r])
        rows.append({"fingerprint_index": int(cand[r]), "anonymised_id_guess": f"FLAIR_{cand[r] + 1:03d}",
                     "fingerprint_bbox_sitk": list(map(int, E[r])), "spacing": list(sp[cand[r]]),
                     "matched_patient": PATIENTS[c], "l1_voxels": float(C_forbid[r, c]),
                     "best": PATIENTS[order[0]], "best_l1": float(C_forbid[r, order[0]]),
                     "second": PATIENTS[order[1]], "second_l1": float(C_forbid[r, order[1]])})
    rows.sort(key=lambda x: x["fingerprint_index"])
    # A training entry is attributed to a patient ONLY on an EXACT match (same spacing and the
    # same brain bounding box in all three axes, L1 = 0). Entries that merely share a spacing but
    # match no box exactly are NOT Ljubljana (e.g. MSSEG-2016 centre-03 GE scans at 0.47x0.47x0.9).
    for x in rows:
        x["exact"] = bool(x["l1_voxels"] == 0)
    matched = [x["matched_patient"] for x in rows if x["exact"]]
    non_lj = [x["fingerprint_index"] for x in rows if not x["exact"]]
    print(f"entries sharing a Ljubljana spacing but matching NO patient exactly (not Ljubljana): {non_lj}")
    held_out = [p for p in PATIENTS if p not in matched]
    pnum = [int(m[-2:]) for m in matched]
    monotone = all(a < b for a, b in zip(pnum, pnum[1:]))
    print("\nassignment (fingerprint entry -> patient, L1 voxels; best / second best):")
    for x in rows:
        print(f"  idx {x['fingerprint_index']:3d} bbox {x['fingerprint_bbox_sitk']} sp {x['spacing']} -> "
              f"{x['matched_patient']} L1={x['l1_voxels']:.0f} | best {x['best']} {x['best_l1']:.0f}, "
              f"2nd {x['second']} {x['second_l1']:.0f}")
    print(f"\nmatched (trained) patients: {matched}")
    print(f"monotone in anonymised id: {monotone}")
    print(f"NOT matched (candidate held-out) patients: {held_out}")

    # Null calibration of the match quality: the same assignment against a random 20-subset of
    # the boxes with the rows shuffled tells us what L1 values look like by chance.
    # How unusual is an exact 3-axis box match by chance? Over all ordered pairs of DIFFERENT
    # Ljubljana patients, how often do two brain boxes coincide exactly?
    PP = np.abs(P[:, None, :] - P[None, :, :]).sum(-1)
    off = PP[~np.eye(len(PATIENTS), dtype=bool)]
    exact_rows = [x for x in rows if x["exact"]]
    rec = {"patients": pats, "candidate_indices": cand, "assignment": rows,
           "matched_trained": matched, "held_out": held_out, "monotone_in_anonymised_id": monotone,
           "n_exact_matches": len(matched),
           "min_second_best_l1_among_exact": float(min(x["second_l1"] for x in exact_rows)) if exact_rows else None,
           "between_patient_box_l1": {"min": float(off.min()), "median": float(np.median(off)),
                                      "n_pairs_exactly_equal": int((off == 0).sum())},
           "not_ljubljana_entries_sharing_spacing": non_lj}
    print(f"exact matches: {len(matched)}; smallest second-best distance among them "
          f"{rec['min_second_best_l1_among_exact']} voxels; between-patient box L1: min "
          f"{off.min():.0f}, median {np.median(off):.0f}, exactly-equal pairs {(off == 0).sum()}")
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1)
    print(f"wrote {out_json}")


if __name__ == "__main__":
    main()
