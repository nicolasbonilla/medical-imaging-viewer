#!/usr/bin/env python3
"""Lesion-detector v3.2 — K6 independent re-implementation (PROTOCOL-v3.2.md §7).

Written separately from build_features.py / features_v3.py / evaluate_v3*.py and imports none of
them. Recomputes from the raw inputs and the protocol text:
  (a) the control candidates: own mean of the 5 fold maps (float64), own 18-neighbour union-find
      labelling, own >= 3-voxel rule, own mean probability and across-fold SD;
  (b) the primary H1 AUROC (1-mm MS TRUE vs control candidates) for ENS-RAW and GR+C-LR, with its
      own fold assignment, its own scikit-learn pipeline refit and an explicit pairwise count;
  (c) H3: healthy false candidates per control scan at 90 % 1-mm MS sensitivity.
Pass rules (fixed in the protocol): candidates and counts exact, AUROC within 0.002, FPS within 0.02.

    python research/lesion_detector_v3/check_v32_independent.py --controls-root R --cache C
        --record docs/research/records/2026-10-24_lesion_detector_v32_evaluation.json
"""
import argparse
import json
import os

import nibabel as nib
import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

SEED = 20261017
GR = ["prob_mean", "prob_max", "prob_std", "prob_q90", "log_volume_mm3", "ps_surv_075", "ps_surv_090",
      "ps_log_merge_025", "ps_log_merge_010", "ens_mean", "ens_std", "ens_frac_detect", "ens_voxvar_mean", "ens_mi"]
OFFSETS = [(a, b, c) for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1)
           if (a, b, c) > (0, 0, 0) and abs(a) + abs(b) + abs(c) <= 2]          # 9 forward 18-neighbours
assert len(OFFSETS) == 9


# ------------------------------------------------------------------ (a) candidates
def components(mask):
    """18-connected components of a boolean volume by union-find over its voxels."""
    coords = np.argwhere(mask)
    if not len(coords):
        return []
    lin = np.ravel_multi_index(coords.T, mask.shape)            # ascending (C order)
    parent = np.arange(len(coords))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    shape = np.array(mask.shape)
    for off in OFFSETS:
        nb = coords + np.array(off)
        ok = np.all((nb >= 0) & (nb < shape), axis=1)
        src = np.nonzero(ok)[0]
        nl = np.ravel_multi_index(nb[ok].T, mask.shape)
        pos = np.searchsorted(lin, nl)
        pos[pos >= len(lin)] = 0
        hit = lin[pos] == nl
        for i, j in zip(src[hit], pos[hit]):
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[max(ri, rj)] = min(ri, rj)
    roots = np.array([find(i) for i in range(len(coords))])
    return [coords[roots == r] for r in np.unique(roots)]


def control_candidates(root, case):
    folds = [nib.load(os.path.join(root, "flames", f"{case}_f{k}_prob.nii.gz")).get_fdata() for k in range(5)]
    mean = np.mean(folds, axis=0)
    out = []
    for comp in components(mean >= 0.5):
        if len(comp) < 3:                                       # 1 mm^3 voxels: >= 3 mm^3
            continue
        t = tuple(comp.T)
        per_fold = [float(f[t].mean()) for f in folds]
        out.append((len(comp), float(mean[t].mean()), float(np.std(per_fold))))
    return sorted(out)


# ------------------------------------------------------------------ (b) model
class Winsor(BaseEstimator, TransformerMixin):
    def fit(self, X, y=None):
        self.lo_, self.hi_ = np.percentile(X, 1, axis=0), np.percentile(X, 99, axis=0)
        return self

    def transform(self, X):
        return np.clip(X, self.lo_, self.hi_)


def model():
    return make_pipeline(SimpleImputer(strategy="median"), Winsor(), StandardScaler(),
                         LogisticRegression(C=0.1, solver="lbfgs", max_iter=5000))


def auc_pairs(pos, neg):
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    gt = sum(int((p > neg).sum()) for p in pos)
    eq = sum(int((p == neg).sum()) for p in pos)
    return (gt + 0.5 * eq) / (len(pos) * len(neg))


def folds_by_protocol(units, seed):
    perm = np.random.RandomState(seed).permutation(sorted(units))
    return {u: i % 5 for i, u in enumerate(perm)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--controls-root", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--record", required=True)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    d = np.load(a.cache, allow_pickle=False)
    names = [str(x) for x in d["names"]]
    col = {n: i for i, n in enumerate(names)}
    X, si = d["X"], d["scan_idx"]
    case, coh, pat, stat = d["scan_case"], d["scan_cohort"], d["scan_patient"], d["scan_status"]
    y = d["mg0"] > 0
    c_coh, c_pat, c_stat = coh[si], pat[si], stat[si]
    M = c_coh == "mslesseg"
    L10 = (c_coh == "openms") & (c_stat == "heldout10")
    C = c_coh == "sibbms"
    rep = {}

    # (a) candidates
    ctl_scans = [i for i in range(len(case)) if coh[i] == "sibbms"]
    bad, n_tot, n_any = [], 0, 0
    for s in ctl_scans:
        mine = control_candidates(a.controls_root, str(case[s]))
        ii = np.nonzero(si == s)[0]
        theirs = sorted((int(round(np.exp(X[i, col["log_volume_mm3"]]))), float(X[i, col["prob_mean"]]),
                         float(X[i, col["ens_std"]])) for i in ii)
        n_tot += len(mine)
        n_any += int(len(mine) > 0)
        if len(mine) != len(theirs):
            bad.append(f"{case[s]}: {len(mine)} vs cache {len(theirs)}")
            continue
        for (v1, s1, e1), (v2, s2, e2) in zip(mine, theirs):
            if v1 != v2 or abs(s1 - s2) > 1e-4 or abs(e1 - e2) > 1e-4:
                bad.append(f"{case[s]}: ({v1},{s1:.5f},{e1:.5f}) vs ({v2},{s2:.5f},{e2:.5f})")
    rep["a_candidates"] = {"controls": len(ctl_scans), "candidates": n_tot, "scans_with_any": n_any,
                           "mismatches": bad[:20], "passed": not bad}
    print("(a)", json.dumps(rep["a_candidates"]))

    # (b) folds + refit + AUROC
    fold = {}
    fold.update(folds_by_protocol(set(c_pat[M]), SEED + 200))
    fold.update(folds_by_protocol(set(c_pat[L10]), SEED + 201))
    fold.update(folds_by_protocol({str(pat[s]) for s in ctl_scans}, SEED + 202))
    pool = M | L10 | C
    fo = np.array([fold.get(str(p), -1) for p in c_pat])
    Xg = X[:, [col[c] for c in GR]]
    oof = np.full(len(y), np.nan)
    for k in range(5):
        tr, te = pool & (fo != k), pool & (fo == k)
        assert not (set(c_pat[tr]) & set(c_pat[te]))
        m = model().fit(Xg[tr], y[tr].astype(int))
        oof[te] = m.predict_proba(Xg[te])[:, 1]
    pos, neg = (M | L10) & y, C
    raw = X[:, col["prob_mean"]]
    auc_raw, auc_grc = auc_pairs(raw[pos], raw[neg]), auc_pairs(oof[pos], oof[neg])
    rec = json.load(open(a.record, encoding="utf-8"))
    h1 = rec["H1_primary_ms_true_vs_controls"]
    rep["b_H1"] = {"ENS-RAW": round(auc_raw, 4), "GR+C-LR": round(auc_grc, 4), "delta": round(auc_grc - auc_raw, 4),
                   "record_ENS-RAW": h1["ENS-RAW"]["auroc"], "record_GR+C-LR": h1["GR+C-LR"]["auroc"],
                   "passed": bool(abs(auc_raw - h1["ENS-RAW"]["auroc"]) <= 0.002 and abs(auc_grc - h1["GR+C-LR"]["auroc"]) <= 0.002)}
    print("(b)", json.dumps(rep["b_H1"]))

    # (c) H3
    fps = {}
    for nm, sc in (("ENS-RAW", raw), ("GR+C-LR", oof)):
        tau = np.quantile(sc[pos], 0.10, method="lower")
        counts = [int((sc[np.nonzero(si == s)[0]] >= tau).sum()) for s in ctl_scans]
        fps[nm] = (float(np.mean(counts)), float(np.mean(np.array(counts) > 0)))
    h3 = rec["H3_false_per_control_at_90pct_sensitivity"]
    rep["c_H3"] = {nm: {"fps": round(v[0], 4), "share_any": round(v[1], 4),
                        "record_fps": h3[nm]["false_per_control_scan"], "record_share": h3[nm]["share_controls_with_any"]}
                   for nm, v in fps.items()}
    rep["c_H3"]["passed"] = all(abs(v[0] - h3[nm]["false_per_control_scan"]) <= 0.02 for nm, v in fps.items())
    print("(c)", json.dumps(rep["c_H3"]))
    rep["passed"] = bool(rep["a_candidates"]["passed"] and rep["b_H1"]["passed"] and rep["c_H3"]["passed"])
    print("K6 passed:", rep["passed"])
    out = a.out or a.record.replace("_evaluation.json", "_independent_check.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1)
    print("wrote", out)


if __name__ == "__main__":
    main()
