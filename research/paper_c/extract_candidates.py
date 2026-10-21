#!/usr/bin/env python3
"""Paper C — extract candidates for every arm (PROTOCOL.md §3, §6) into research/paper_c/.cache/.

Per unit (open_ms patient or MSLesSeg pair) the cache holds: truth summary, burden, number of
countable truth lesions, and the candidates WITHOUT voxels: score(s), true (overlaps the truth
change region), true_pos (open_ms: overlaps a positive expert component), hits (ids of the
countable truth lesions it overlaps), kind, volume. D-seg units also hold the app's flags.

    python research/paper_c/extract_candidates.py [--workers 4]
"""
import argparse
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import detectors as D  # noqa: E402

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
DSUB_THRESHOLDS = (1.5, 1.0, 2.0)          # primary first (PROTOCOL §3, §11)


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _hits(idx, lesion_map):
    v = np.unique(lesion_map[idx])
    return [int(x) for x in v if x > 0]


def _finish(cands, region, lesion_map, region_pos=None):
    for c in cands:
        idx = c["_idx"]
        c["true"] = bool(region[idx].any())
        if region_pos is not None:
            c["true_pos"] = bool(region_pos[idx].any())
        c["hits"] = _hits(idx, lesion_map)
    return D.strip(cands)


def oms_unit(pid):
    t0 = time.time()
    x = C.load_oms_long(pid)
    d, zb, interior = D.subtraction(x["flair_a"], x["flair_b"], x["brain"])
    truth, region_any, region_pos, lesion_map = C.truth_from_change_mask(x["gt"], d, x["brain"], x["voxvol"])
    out = {"unit": pid, "patient": pid, "first_pair": True, "active": truth["active"],
           "burden": truth["n_components"], "n_truth_lesions": int(lesion_map.max()),
           "truth": {k: v for k, v in truth.items() if k != "items"}, "dsub": {}}
    for t in DSUB_THRESHOLDS:
        cands = D.dsub_candidates(d, zb, interior, x["voxvol"], t_sub=t)
        out["dsub"][str(t)] = _finish(cands, region_any, lesion_map, region_pos)
    # A4: FLAMeS maps from the cloud job, when present
    pa = [os.path.join(C.OMS_LONG_FLAMES, f"openmslong_{pid}_s1_f{k}_prob.nii.gz") for k in range(5)]
    pb = [os.path.join(C.OMS_LONG_FLAMES, f"openmslong_{pid}_s2_f{k}_prob.nii.gz") for k in range(5)]
    if all(os.path.exists(p) for p in pa + pb):
        import nibabel as nib
        prob_a = np.mean([nib.load(p).get_fdata(dtype=np.float32) for p in pa], axis=0)
        prob_b = np.mean([nib.load(p).get_fdata(dtype=np.float32) for p in pb], axis=0)
        if prob_a.shape != x["flair_a"].shape:
            raise ValueError(f"{pid}: FLAMeS grid differs from the co-registered FLAIR")
        cands, flags = D.dseg_candidates(prob_a, prob_b, d, x["brain"], x["zooms"])
        out["dseg"] = _finish(cands, region_any, lesion_map, region_pos)
        out["app_flags"] = flags
        out["flames_sha256"] = {os.path.basename(p): _sha(p) for p in pa + pb}
    out["seconds"] = round(time.time() - t0, 1)
    return out


def msl_unit(pair):
    p, a, b, first = pair
    t0 = time.time()
    xa = C.load_mslesseg_tp(p, a)
    xb = C.load_mslesseg_tp(p, b)
    domain = (xa["flair"] > 0) & (xb["flair"] > 0)
    d, zb, interior = D.subtraction(xa["flair"], xb["flair"], domain)
    truth, region, lesion_map = C.truth_from_two_masks(xa["mask"], xb["mask"], xa["voxvol"])
    zooms = (1.0, 1.0, 1.0) if abs(xa["voxvol"] - 1.0) < 1e-6 else None
    if zooms is None:
        raise ValueError(f"{p}: MSLesSeg expected at 1 mm")
    out = {"unit": f"{p}_{a}_{b}", "patient": p, "first_pair": first, "active": truth["active"],
           "active_lenient": truth["active_lenient"],
           "burden": truth["n_new_detectable"] + truth["n_enlarging"], "n_truth_lesions": int(lesion_map.max()),
           "truth": {k: v for k, v in truth.items() if k != "items"}, "dsub": {}}
    for t in DSUB_THRESHOLDS:
        cands = D.dsub_candidates(d, zb, interior, xa["voxvol"], t_sub=t)
        out["dsub"][str(t)] = _finish(cands, region, lesion_map)
    cands, flags = D.dseg_candidates(xa["prob"], xb["prob"], d, domain, zooms)
    out["dseg"] = _finish(cands, region, lesion_map)
    out["app_flags"] = flags
    out["seconds"] = round(time.time() - t0, 1)
    return out


UNITS = os.path.join(CACHE, "units")


def _cached(kind, arg):
    """Per-unit cache (resumable): a unit is recomputed only if its file is missing, or for open_ms
    when FLAMeS maps have appeared since it was cached."""
    name = arg if kind == "oms" else f"{arg[0]}_{arg[1]}_{arg[2]}"
    path = os.path.join(UNITS, f"{kind}_{name}.json")
    if os.path.exists(path):
        u = json.load(open(path))
        flames_now = kind == "oms" and os.path.exists(
            os.path.join(C.OMS_LONG_FLAMES, f"openmslong_{arg}_s2_f4_prob.nii.gz"))
        if not (flames_now and "dseg" not in u):
            return u
    u = oms_unit(arg) if kind == "oms" else msl_unit(arg)
    json.dump(u, open(path, "w"))
    return u


def _oms(pid):
    return _cached("oms", pid)


def _msl(pair):
    return _cached("msl", pair)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args()
    os.makedirs(UNITS, exist_ok=True)
    t0 = time.time()
    pairs = []
    for p, tl in C.mslesseg_timepoints().items():
        for i in range(len(tl) - 1):
            pairs.append((p, tl[i], tl[i + 1], i == 0))
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        oms = list(ex.map(_oms, C.oms_long_patients()))
        msl = list(ex.map(_msl, pairs))
    for o in oms:
        print(f"open_ms {o['unit']}: active {o['active']} burden {o['burden']} truth lesions {o['n_truth_lesions']} "
              f"D-sub cands {len(o['dsub']['1.5'])} | {o['seconds']} s" + (" | FLAMeS present" if "dseg" in o else ""))
    for o in msl:
        print(f"MSLesSeg {o['unit']}: active {o['active']} burden {o['burden']} truth lesions {o['n_truth_lesions']} "
              f"D-sub cands {len(o['dsub']['1.5'])} D-seg cands {len(o['dseg'])} | {o['seconds']} s")
    hashes = {}
    for p, a, b, _ in pairs:
        for t in (a, b):
            for s in ("FLAIR", "MASK"):
                f = os.path.join(C.MSL, "train", p, t, f"{p}_{t}_{s}.nii.gz")
                hashes[os.path.basename(f)] = _sha(f)
            for k in range(5):
                f = os.path.join(C.FLAMES, f"mslesseg_{p}_{t}_f{k}_prob.nii.gz")
                hashes[os.path.basename(f)] = _sha(f)
    json.dump({"open_ms": oms, "mslesseg": msl, "mslesseg_input_sha256": hashes,
               "params": {"T_SUB": D.T_SUB, "T_FU": D.T_FU, "dsub_thresholds": DSUB_THRESHOLDS,
                          "CLIN_MM3": C.CLIN_MM3, "APP_CONFIRM_SD": D.APP_CONFIRM_SD}},
              open(os.path.join(CACHE, "candidates.json"), "w"))
    print(f"wrote {os.path.join(CACHE, 'candidates.json')} in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
