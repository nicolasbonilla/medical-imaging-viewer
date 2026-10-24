"""FLAMeS-thick pre-registered analysis (PROTOCOL.md §8-§9). Runs locally on probability maps.

    python research/flames_thick/analysis.py \
        --ref-dir data/cohorts/cloud-2026-10/flames --new-dir data/cohorts/flames-thick-eval \
        --ref-manifests data/cohorts/cloud-2026-10/manifests --new-manifest <eval manifest json> \
        --tag A=ftA --tag B=ftB --mslesseg-info "<MSLesSeg Dataset>/info_dataset/patient_scanners_info/patient_scanners_info_FLAIR.csv" \
        --out docs/research/records/<date>_flames_thick_results.json

Arms: R = FLAMeS fold 0 ({case}_f0_prob), E = 5-fold mean ({case}_f{0..4}_prob), A/B = new maps
({case}_{tag}_f0_prob). Lesion definitions are Paper A v0.3's (research/paper_a/v03_candidates.py):
p >= 0.5, 18-connected components >= 3 mm^3, one-to-one Hungarian max-IoU matching, IoU > 0
(lenient, primary) or >= 0.10 (strict). Resampling unit = patient; paired percentile bootstrap,
B = 10 000, seed 20261021.
"""
import argparse
import csv
import glob
import json
import os
import sys
from multiprocessing import Pool

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from flames_thick import eval_cases as ec  # noqa: E402

THRESHOLD, MIN_VOL_MM3 = 0.5, 3.0
BINS = [3.0, 14.0, 50.0, 150.0, 500.0, np.inf]
BIN_NAMES = ["[3,14)", "[14,50)", "[50,150)", "[150,500)", ">=500"]
B_DEFAULT, SEED = 10000, 20261021
SESOI_F1, FP_MARGIN = 0.03, 1.10
NI_DICE, NI_F1 = -0.02, -0.03


# ====================================================================== per-scan metrics
def _struct():
    from scipy import ndimage as ndi
    return ndi.generate_binary_structure(3, 2)               # 18-connectivity


def components(mask, vox_mm3):
    """Labels of 18-connected components >= 3 mm^3: (label array, kept ids, voxel counts)."""
    from scipy import ndimage as ndi
    lab, n = ndi.label(mask, structure=_struct())
    counts = np.bincount(lab.ravel(), minlength=n + 1)
    keep = np.array([i for i in range(1, n + 1) if counts[i] * vox_mm3 >= MIN_VOL_MM3 - 1e-9], int)
    return lab, keep, counts


def match(pred_lab, pred_ids, pred_counts, gt_lab, gt_ids, gt_counts, iou_thr):
    """One-to-one Hungarian max-IoU matching; returns (matched pred ids, matched gt ids)."""
    from scipy.optimize import linear_sum_assignment
    if pred_ids.size == 0 or gt_ids.size == 0:
        return np.zeros(0, int), np.zeros(0, int)
    both = (pred_lab > 0) & (gt_lab > 0)
    m = int(gt_lab.max()) + 1
    key = pred_lab[both].astype(np.int64) * m + gt_lab[both]
    uk, inter = np.unique(key, return_counts=True)
    pi = {int(x): i for i, x in enumerate(pred_ids)}
    gi = {int(x): j for j, x in enumerate(gt_ids)}
    iou = np.zeros((pred_ids.size, gt_ids.size))
    for k, c in zip(uk, inter):
        a, b = int(k // m), int(k % m)
        if a in pi and b in gi:
            v = c / (pred_counts[a] + gt_counts[b] - c)
            if v > iou_thr:                                  # lenient: IoU > 0; strict: IoU > 0.10 (as v0.2/v0.3)
                iou[pi[a], gi[b]] = v
    r, c = linear_sum_assignment(-iou)
    ok = iou[r, c] > 0
    return pred_ids[r[ok]], gt_ids[c[ok]]


def scan_metrics(prob, gt, vox_mm3, strict_iou=0.10):
    pred = prob >= THRESHOLD
    gt = gt > 0
    plab, pids, pcnt = components(pred, vox_mm3)
    glab, gids, gcnt = components(gt, vox_mm3)
    out = {"n_pred": int(pids.size), "n_gt": int(gids.size)}
    for tag, thr in (("", 0.0), ("_strict", strict_iou)):
        mp, mg = match(plab, pids, pcnt, glab, gids, gcnt, thr)
        tp, fp, fn = int(mp.size), int(pids.size - mp.size), int(gids.size - mg.size)
        out[f"tp{tag}"], out[f"fp{tag}"], out[f"fn{tag}"] = tp, fp, fn
        out[f"f1{tag}"] = 1.0 if tp + fp + fn == 0 else 2 * tp / (2 * tp + fp + fn)
        if tag == "":
            det = np.isin(gids, mg)
            out["gt_vol_mm3"] = (gcnt[gids] * vox_mm3).round(2).tolist()
            out["gt_detected"] = det.astype(int).tolist()
    s = pred.sum() + gt.sum()
    out["dice"] = 1.0 if s == 0 else float(2 * np.logical_and(pred, gt).sum() / s)
    out["sens"] = out["tp"] / out["n_gt"] if out["n_gt"] else None
    out["prec"] = out["tp"] / out["n_pred"] if out["n_pred"] else None
    return out


# ====================================================================== bootstrap
class Clustered:
    """Per-patient sums for a scan-level quantity; vectorised patient bootstrap."""

    def __init__(self, patients, seed=SEED, b=B_DEFAULT):
        self.pats = sorted(set(patients))
        self.idx = np.array([self.pats.index(p) for p in patients])
        self.n = np.bincount(self.idx, minlength=len(self.pats)).astype(float)
        rng = np.random.default_rng(seed)
        self.w = rng.multinomial(len(self.pats), [1.0 / len(self.pats)] * len(self.pats), size=b).astype(float)

    def sums(self, x):
        return np.bincount(self.idx, weights=np.asarray(x, float), minlength=len(self.pats))

    def mean(self, x):
        x = np.asarray(x, float)
        point = float(x.mean())
        bs = (self.w @ self.sums(x)) / (self.w @ self.n)
        return point, ci(bs)

    def ratio(self, num, den):
        point = float(np.sum(num) / np.sum(den)) if np.sum(den) else float("inf")
        with np.errstate(divide="ignore", invalid="ignore"):
            bs = (self.w @ self.sums(num)) / (self.w @ self.sums(den))
        return point, ci(bs[np.isfinite(bs)])


def ci(bs):
    return [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))] if len(bs) else [None, None]


# ====================================================================== decision rules
def verdict_h1(d_f1, fp_ratio):
    """PROTOCOL §9.1. A ratio without a CI (reference arm with no false lesion at all) cannot pass."""
    (p, (lo, hi)), (_, (rlo, rhi)) = d_f1, fp_ratio
    fp_ok = rhi is not None and rhi <= FP_MARGIN
    fp_bad = rlo is not None and rlo > FP_MARGIN
    if lo > 0 and p >= SESOI_F1 and fp_ok:
        return "success"
    if hi < SESOI_F1 or fp_bad:
        return "refuted"
    return "inconclusive"


def verdict_h2(d_dice_pooled, d_f1_pooled, d_dice_lj, d_f1_lj):
    ok = (d_dice_pooled[1][0] > NI_DICE and d_f1_pooled[1][0] > NI_F1
          and d_dice_lj >= NI_DICE and d_f1_lj >= NI_F1)
    return "non-inferior" if ok else "not shown"


def min_reliable(sens_by_bin, thr):
    """Smallest bin from which sensitivity >= thr in that bin and every larger bin (None if never)."""
    best = None
    for i in range(len(sens_by_bin) - 1, -1, -1):
        s = sens_by_bin[i]
        if s is None or s < thr:
            break
        best = i
    return None if best is None else BIN_NAMES[best]


def size_table(rows, arm, b=2000, seed=SEED):
    """Per-bin detection (pooled lesions) with a patient bootstrap CI."""
    vols, det, pats = [], [], []
    for r in rows:
        m = r["arms"][arm]
        vols += m["gt_vol_mm3"]
        det += m["gt_detected"]
        pats += [r["patient"]] * len(m["gt_vol_mm3"])
    vols, det = np.asarray(vols), np.asarray(det, float)
    out = []
    for i in range(len(BIN_NAMES)):
        sel = (vols >= BINS[i]) & (vols < BINS[i + 1])
        if sel.sum() == 0:
            out.append({"bin": BIN_NAMES[i], "n": 0, "sens": None, "ci": [None, None]})
            continue
        cl = Clustered([p for p, s in zip(pats, sel) if s], seed, b)
        p, c = cl.mean(det[sel])
        out.append({"bin": BIN_NAMES[i], "n": int(sel.sum()), "sens": p, "ci": c})
    sens = [x["sens"] for x in out]
    return {"bins": out, "min_size_50": min_reliable(sens, 0.5), "min_size_80": min_reliable(sens, 0.8)}


# ====================================================================== data
def load(path):
    import nibabel as nib
    img = nib.load(path)
    return np.asarray(img.get_fdata(dtype=np.float32)), img


def one_case(job):
    case, ref_dir, new_dir, tags = job
    import nibabel as nib
    gimg = nib.load(os.path.join(ref_dir, f"{case}_gt.nii.gz"))
    gt = np.asarray(gimg.dataobj) > 0
    zooms = [float(z) for z in gimg.header.get_zooms()[:3]]
    vox = float(np.prod(zooms))
    new_gt = os.path.join(new_dir, f"{case}_gt.nii.gz")
    gt_same = None
    if os.path.exists(new_gt):
        gt_same = bool(np.array_equal(np.asarray(nib.load(new_gt).dataobj) > 0, gt))
    folds = [load(os.path.join(ref_dir, f"{case}_f{k}_prob.nii.gz"))[0] for k in range(5)]
    arms = {"R": scan_metrics(folds[0], gt, vox), "E": scan_metrics(np.mean(folds, 0), gt, vox)}
    del folds
    for arm, tag in tags.items():
        p, img = load(os.path.join(new_dir, f"{case}_{tag}_f0_prob.nii.gz"))
        if p.shape != gt.shape or not np.allclose(img.affine, gimg.affine, atol=1e-4):
            raise ValueError(f"{case} arm {arm}: map grid differs from the expert mask grid")
        arms[arm] = scan_metrics(p, gt, vox)
    return {"case": case, "site": ec.site_of(case), "patient": ec.patient_of(case), "zooms": zooms,
            "slice_mm": max(zooms), "band": ec.band(max(zooms)), "gt_identical_to_reference": gt_same, "arms": arms}


def input_identity(cases, ref_manifest_dir, new_manifest):
    ref = {}
    for p in sorted(glob.glob(os.path.join(ref_manifest_dir, "*.json"))):
        m = json.load(open(p))
        for c, h in (m.get("inputs_sha256") or {}).items():
            ref.setdefault(c, set()).add(h)
    new = json.load(open(new_manifest)).get("inputs_sha256", {})
    bad = {c: {"ref": sorted(ref.get(c, [])), "new": new.get(c)} for c in cases
           if new.get(c) is None or new.get(c) not in ref.get(c, set())}
    return bad


def mslesseg_native_thickness(csv_path):
    out = {}
    if not csv_path or not os.path.exists(csv_path):
        return out
    for r in csv.DictReader(open(csv_path, encoding="utf-8-sig"), delimiter=";"):
        try:
            out[f"mslesseg_{r['Patient']}"] = float(r["SliceThickness[mm]"])     # test scans: one timepoint
        except ValueError:
            pass
    return out


# ====================================================================== analysis
def analyse(rows, arms, b=B_DEFAULT):
    res = {"n_scans": len(rows), "arms": arms}
    thick = [r for r in rows if r["site"] in ec.THICK_SITES]
    onemm = [r for r in rows if r["site"] in ec.ONE_MM_SITES]
    lj = [r for r in rows if r["site"] == "openms"]

    def h1(sub, a="A", ref="R", key=""):
        cl = Clustered([r["patient"] for r in sub], SEED, b)
        d = cl.mean([r["arms"][a][f"f1{key}"] - r["arms"][ref][f"f1{key}"] for r in sub])
        fr = cl.ratio([r["arms"][a][f"fp{key}"] for r in sub], [r["arms"][ref][f"fp{key}"] for r in sub])
        return {"n": len(sub), "patients": len(cl.pats), "delta_f1": d, "fp_ratio": fr,
                "mean_f1": {x: float(np.mean([r["arms"][x][f"f1{key}"] for r in sub])) for x in (a, ref)},
                "mean_fp": {x: float(np.mean([r["arms"][x][f"fp{key}"] for r in sub])) for x in (a, ref)},
                "verdict": verdict_h1(d, fr)}

    if "A" in arms:
        res["H1"] = h1(thick)
        res["H1_by_site"] = {s: h1([r for r in thick if r["site"] == s]) for s in ec.THICK_SITES}
        harm = [s for s, v in res["H1_by_site"].items() if v["delta_f1"][1][1] < 0]
        if res["H1"]["verdict"] == "success" and harm:
            res["H1"]["verdict"] = "success with harm at " + ", ".join(harm)
        cl = Clustered([r["patient"] for r in onemm], SEED, b)
        dd = cl.mean([r["arms"]["A"]["dice"] - r["arms"]["R"]["dice"] for r in onemm])
        df = cl.mean([r["arms"]["A"]["f1"] - r["arms"]["R"]["f1"] for r in onemm])
        lj_dd = float(np.mean([r["arms"]["A"]["dice"] - r["arms"]["R"]["dice"] for r in lj])) if lj else None
        lj_df = float(np.mean([r["arms"]["A"]["f1"] - r["arms"]["R"]["f1"] for r in lj])) if lj else None
        res["H2"] = {"n": len(onemm), "delta_dice": dd, "delta_f1": df, "ljubljana_delta_dice": lj_dd,
                     "ljubljana_delta_f1": lj_df,
                     "verdict": verdict_h2(dd, df, lj_dd, lj_df) if lj else "not shown (no Ljubljana scans)"}
        res["S6_strict"] = h1(thick, key="_strict")
        res["S6_without_pedims_P9"] = h1([r for r in thick if r["patient"] != "pedims_P9"])
    if "A" in arms and "B" in arms:
        res["S3_A_vs_B"] = h1(thick, "A", "B")
    if "A" in arms:
        res["S4_A_vs_E"] = h1(thick, "A", "E")
    if "B" in arms:
        res["B_vs_R_thick"] = h1(thick, "B", "R")
    res["S1_size"] = {f"{band}|{arm}": size_table([r for r in rows if r["band"] == band], arm, min(b, 2000))
                      for band in ("B1", "B2", "B3", "B4") for arm in ["R", "E"] + [x for x in ("A", "B") if x in arms]
                      if any(r["band"] == band for r in rows)}
    res["S2_by_site"] = {}
    for s in sorted({r["site"] for r in rows}):
        sub = [r for r in rows if r["site"] == s]
        res["S2_by_site"][s] = {arm: {k: float(np.mean([r["arms"][arm][k] for r in sub if r["arms"][arm][k] is not None]))
                                      if any(r["arms"][arm][k] is not None for r in sub) else None
                                      for k in ("f1", "fp", "dice", "sens", "prec")}
                                for arm in ["R", "E"] + [x for x in ("A", "B") if x in arms]}
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref-dir", required=True)
    ap.add_argument("--new-dir", required=True)
    ap.add_argument("--ref-manifests", required=True)
    ap.add_argument("--new-manifest", required=True)
    ap.add_argument("--tag", action="append", default=[], help="ARM=TAG, e.g. A=ftA B=ftB")
    ap.add_argument("--mslesseg-info")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--bootstrap", type=int, default=B_DEFAULT)
    ap.add_argument("--allow-count", type=int)
    a = ap.parse_args(argv)
    tags = dict(t.split("=", 1) for t in a.tag)
    if set(tags) - {"A", "B"}:
        raise SystemExit("--tag arms must be A and/or B")
    avail = sorted({os.path.basename(p)[:-len("_f0_prob.nii.gz")] for p in glob.glob(os.path.join(a.ref_dir, "*_f0_prob.nii.gz"))})
    cases, counts = ec.select(avail, a.allow_count)
    bad = input_identity(cases, a.ref_manifests, a.new_manifest)
    if bad:
        raise SystemExit(f"input FLAIR SHA-256 differs from the reference runs for {len(bad)} scans: "
                         f"{dict(list(bad.items())[:5])}")
    missing = [c for c in cases for t in tags.values() if not os.path.exists(os.path.join(a.new_dir, f"{c}_{t}_f0_prob.nii.gz"))]
    if missing:
        raise SystemExit(f"{len(missing)} maps missing (PROTOCOL §9: re-run, never drop): {missing[:10]}")
    with Pool(a.workers) as pool:
        rows = pool.map(one_case, [(c, a.ref_dir, a.new_dir, tags) for c in cases])
    if any(r["gt_identical_to_reference"] is False for r in rows):
        raise SystemExit("an expert mask from the evaluation job differs from the reference mask")
    native = mslesseg_native_thickness(a.mslesseg_info)
    for r in rows:
        if r["site"] == "mslesseg":
            r["native_slice_mm"] = native.get(r["case"])
    res = analyse(rows, sorted(tags), a.bootstrap)
    ms = [r for r in rows if r["site"] == "mslesseg" and r.get("native_slice_mm")]
    if "A" in tags and ms:
        res["S5_mslesseg_by_native_thickness"] = {
            name: {"n": len(sub), "delta_f1_mean": float(np.mean([r["arms"]["A"]["f1"] - r["arms"]["R"]["f1"] for r in sub])),
                   "delta_dice_mean": float(np.mean([r["arms"]["A"]["dice"] - r["arms"]["R"]["dice"] for r in sub]))}
            for name, sub in (("<=3mm", [r for r in ms if r["native_slice_mm"] <= 3]),
                              ("4-5mm", [r for r in ms if r["native_slice_mm"] >= 4])) if sub}
    res["counts"] = counts
    res["per_scan"] = rows
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(res, open(a.out, "w"), indent=1, default=float)
    for k in ("H1", "H2", "S3_A_vs_B", "S4_A_vs_E"):
        if k in res:
            print(k, json.dumps({x: res[k][x] for x in res[k] if x != "mean_fp"}, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
