#!/usr/bin/env python3
"""Lesion-detector v3 — the pre-registered evaluation (docs/research/lesion-detector-v3/PROTOCOL.md).

Reads the feature/label cache written by build_features.py and runs, with the hyper-parameters,
seeds and resampling fixed in the protocol:
  primary   pooled leave-one-cohort-out (MSLesSeg <-> clean Ljubljana-10) lesion-level AUROC,
            V3-LR vs raw probability, paired stratified patient-cluster bootstrap
  S1-S5     within-cohort CV, per-direction/per-cohort LOCO, leak-free conformal power (BH and
            per-scan FDX via research/conformal_fdx/calm_fdx.py), healthy controls
  A1-A9     the adversarial self-check
  E1-E3     exploratory analyses
No hyper-parameter is tuned on any evaluation data.

    python research/lesion_detector_v3/evaluate_v3.py [--cache PATH] [--tag 2026-10-17]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

import numpy as np
from scipy.stats import ks_2samp, rankdata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "research", "conformal_fdx"))
sys.path.insert(0, HERE)
import calm_fdx as cf                                                    # noqa: E402
import features_v3 as fv                                                 # noqa: E402

SEED = 20261017
N_BOOT = 2000
ALPHAS = (0.1, 0.2, 0.3)
FDX_DELTA, FDX_TEMPLATE = 0.1, "hc"
N_SPLITS_XCOHORT = 20
N_SHUFFLE = 20
N_SMALLN = 20
RECORDS = os.path.join(ROOT, "docs", "research", "records")

V2_NAMES = ("prob_mean", "prob_max", "prob_std", "prob_q90", "log_volume", "sphericity", "surf_to_vol",
            "elongation", "extent", "z_norm", "y_norm", "x_norm", "laterality", "radial")
V2_PROB, V2_MORPH, V2_MNI = V2_NAMES[:4], V2_NAMES[4:9], V2_NAMES[9:]
V2_GI = V2_PROB + V2_MORPH
FEATURE_SETS = {
    "V2": V2_NAMES,
    "V3": V2_GI + fv.F1 + fv.F3 + fv.F4_FLAIR + fv.F4_PROB + fv.F5 + fv.F6,
    "V3P": V2_GI + fv.F4_PROB + fv.F5,
    "V3+T1": V2_GI + fv.F1 + fv.F3 + fv.F4_FLAIR + fv.F4_PROB + fv.F5 + fv.F6 + fv.F2,
    "V3+CTX": V2_GI + fv.F1 + fv.F3 + fv.F4_FLAIR + fv.F4_PROB + fv.F5 + fv.F6 + fv.F7,
    "V3+MNI": V2_GI + fv.F1 + fv.F3 + fv.F4_FLAIR + fv.F4_PROB + fv.F5 + fv.F6 + V2_MNI,
    "NEW_ONLY": fv.F1 + fv.F3 + fv.F4_FLAIR + fv.F4_PROB + fv.F5 + fv.F6,
}
ABLATION_FAMILIES = {"v2_prob": V2_PROB, "v2_morph": V2_MORPH, "F1_contrast": fv.F1, "F3_texture": fv.F3,
                     "F4_flair_boundary": fv.F4_FLAIR, "F4_prob_boundary": fv.F4_PROB,
                     "F5_persistence": fv.F5, "F6_location": fv.F6}


# ------------------------------------------------------------------ models (fixed a priori)
class _Prep:
    """Median imputation + train 1st/99th-percentile winsorisation + standardisation."""

    def __init__(self, X, winsor=True, scale=True):
        med = np.nanmedian(X, axis=0)
        self.med = np.where(np.isfinite(med), med, 0.0)
        Xi = self._impute(X)
        self.lo, self.hi = (np.percentile(Xi, 1, axis=0), np.percentile(Xi, 99, axis=0)) if winsor else (None, None)
        Xw = self._clip(Xi)
        self.mu = Xw.mean(0) if scale else 0.0
        sd = Xw.std(0)
        self.sd = np.where(sd > 0, sd, 1.0) if scale else 1.0

    def _impute(self, X):
        X = np.array(X, float, copy=True)
        bad = ~np.isfinite(X)
        X[bad] = np.take(self.med, np.nonzero(bad)[1])
        return X

    def _clip(self, X):
        return X if self.lo is None else np.clip(X, self.lo, self.hi)

    def __call__(self, X):
        return (self._clip(self._impute(X)) - self.mu) / self.sd


def fit_lr(X, y):
    from sklearn.linear_model import LogisticRegression
    prep = _Prep(X)
    clf = LogisticRegression(C=0.1, solver="lbfgs", max_iter=5000).fit(prep(X), y)
    return lambda Z: clf.predict_proba(prep(Z))[:, 1]


def fit_gb(X, y):
    from sklearn.ensemble import HistGradientBoostingClassifier
    prep = _Prep(X, winsor=False, scale=False)
    clf = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=300, min_samples_leaf=30,
                                         l2_regularization=1.0, early_stopping=False, random_state=0).fit(prep(X), y)
    return lambda Z: clf.predict_proba(prep(Z))[:, 1]


def fit_v2_shipped(X, y):
    """v2 as shipped (evaluate_lesion_scorer.py): standardise, degree-2 polynomial, LR C=0.5."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import PolynomialFeatures
    prep = _Prep(X, winsor=False)
    pf = PolynomialFeatures(2, include_bias=False)
    clf = LogisticRegression(C=0.5, max_iter=5000).fit(pf.fit_transform(prep(X)), y)
    return lambda Z: clf.predict_proba(pf.transform(prep(Z)))[:, 1]


MODELS = {  # name -> (feature set, fitter)
    "V3-LR": ("V3", fit_lr), "V3-GB": ("V3", fit_gb),
    "V2-shipped": ("V2", fit_v2_shipped), "V2-LR": ("V2", fit_lr),
    "V3P-LR": ("V3P", fit_lr), "V3P-GB": ("V3P", fit_gb),
}
PRIMARY_MODELS = ("V3-LR", "V3-GB", "V2-shipped", "V2-LR", "V3P-LR")


# ------------------------------------------------------------------ statistics
def auroc(s, y):
    s, y = np.asarray(s, float), np.asarray(y, bool)
    n1, n0 = int(y.sum()), int((~y).sum())
    if n1 == 0 or n0 == 0:
        return None
    r = rankdata(s)
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def _r(x, d=4):
    return None if x is None or not np.isfinite(x) else round(float(x), d)


def cluster_boot(strata, stat, B, rng):
    """strata: list of lists of index arrays (clusters). stat(idx) -> 1-D array. Returns (B, k)."""
    out = []
    for _ in range(B):
        parts = []
        for cl in strata:
            pick = rng.randint(0, len(cl), size=len(cl))
            parts.extend(cl[i] for i in pick)
        out.append(stat(np.concatenate(parts)))
    return np.asarray(out, float)


def ci(v):
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    return [_r(np.percentile(v, 2.5)), _r(np.percentile(v, 97.5))] if v.size else [None, None]


class Data:
    def __init__(self, path):
        d = np.load(path, allow_pickle=False)
        self.path = path
        self.X, self.names = d["X"], [str(x) for x in d["names"]]
        self.col = {n: i for i, n in enumerate(self.names)}
        si = d["scan_idx"]
        self.scan_idx = si
        self.raw = d["score"]
        self.mg0, self.mg1, self.anyvox, self.mg0_clin = d["mg0"], d["mg1"], d["anyvox"], d["mg0_clin"]
        self.s_case, self.s_cohort = d["scan_case"], d["scan_cohort"]
        self.s_patient, self.s_status = d["scan_patient"], d["scan_status"]
        self.s_ncand, self.s_ngt, self.s_ngt_clin = d["scan_ncand"], d["scan_ngt"], d["scan_ngt_clin"]
        self.cohort, self.patient, self.status = self.s_cohort[si], self.s_patient[si], self.s_status[si]
        self.labels = {"lenient": self.mg0 > 0, "strict": self.mg1 > 0, "anyvox": self.anyvox.astype(bool)}
        assert np.allclose(self.raw, self.X[:, self.col["prob_mean"]]), "raw score != prob_mean feature"
        n = len(self.raw)
        lj = self.cohort == "openms"
        self.sets = {"M": self.cohort == "mslesseg",
                     "L10": lj & (self.status == "heldout10"),
                     "L12": lj & np.isin(self.status, ["heldout10", "fold0_validation"]),
                     "Ltr": lj & (self.status != "heldout10"),
                     "LALL": lj, "C": self.cohort == "sibbms"}
        self.scan_sets = {"M": self.s_cohort == "mslesseg",
                          "L10": (self.s_cohort == "openms") & (self.s_status == "heldout10"),
                          "C": self.s_cohort == "sibbms"}
        assert all(v.shape == (n,) for v in self.sets.values())

    def F(self, fset, mask=None):
        cols = [self.col[c] for c in FEATURE_SETS[fset]]
        X = self.X[:, cols]
        return X if mask is None else X[mask]

    def clusters(self, mask):
        """Index arrays of candidates in `mask`, one per patient."""
        idx = np.nonzero(mask)[0]
        by = {}
        for i in idx:
            by.setdefault(self.patient[i], []).append(i)
        return [np.asarray(v) for _, v in sorted(by.items())]


def fit_predict(D, model, train_mask, test_mask, y, perm_rng=None):
    fset, fitter = MODELS[model]
    ytr = y[train_mask].astype(int)
    if perm_rng is not None:
        ytr = perm_rng.permutation(ytr)
    f = fitter(D.F(fset, train_mask), ytr)
    return f(D.F(fset, test_mask))


def patient_folds(D, mask, k, seed):
    pats = sorted(set(D.patient[mask]))
    rng = np.random.RandomState(seed)
    perm = rng.permutation(pats)
    return {p: i % k for i, p in enumerate(perm)}


def assert_disjoint(D, *masks):
    sets = [set(D.patient[m]) for m in masks]
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            assert not (sets[i] & sets[j]), "patient appears in two roles of one split"


# ------------------------------------------------------------------ AUROC analyses
def loco(D, models, y, train_A="M", test_A="L10", train_B="L10", test_B="M", perm_seed=None):
    """Pooled leave-one-cohort-out scores. Returns dict model -> score array over pooled idx, pooled idx."""
    A_tr, A_te, B_tr, B_te = D.sets[train_A], D.sets[test_A], D.sets[train_B], D.sets[test_B]
    assert_disjoint(D, A_tr, A_te)
    assert_disjoint(D, B_tr, B_te)
    idx = np.concatenate([np.nonzero(A_te)[0], np.nonzero(B_te)[0]])
    out = {"RAW": D.raw[idx]}
    for m in models:
        ra = np.random.RandomState(perm_seed) if perm_seed is not None else None
        rb = np.random.RandomState(perm_seed + 1) if perm_seed is not None else None
        sa = fit_predict(D, m, A_tr, A_te, y, ra)
        sb = fit_predict(D, m, B_tr, B_te, y, rb)
        out[m] = np.concatenate([sa, sb])
    return out, idx


def auc_table(D, scores, idx, y, strata_masks, ref="RAW", ref2=None, seed=SEED, B=N_BOOT):
    """AUROC + stratified patient-cluster bootstrap CIs + paired differences vs ref (and ref2)."""
    names = list(scores)
    yy = y[idx]
    pos = {g: k for k, g in enumerate(idx)}
    strata = [[np.array([pos[g] for g in cl]) for cl in D.clusters(sm & np.isin(np.arange(len(y)), idx))]
              for sm in strata_masks]
    strata = [s for s in strata if s]

    def stat(ii):
        vals = [auroc(scores[n][ii], yy[ii]) for n in names]
        return np.array([np.nan if v is None else v for v in vals])
    point = stat(np.arange(len(idx)))
    bs = cluster_boot(strata, stat, B, np.random.RandomState(seed))
    res = {}
    for j, n in enumerate(names):
        r = {"auroc": _r(point[j]), "ci95": ci(bs[:, j])}
        for rf in (ref, ref2):
            if rf and rf in names and rf != n:
                k = names.index(rf)
                r[f"delta_vs_{rf}"] = _r(point[j] - point[k])
                r[f"delta_vs_{rf}_ci95"] = ci(bs[:, j] - bs[:, k])
        res[n] = r
    res["_n"] = {"candidates": int(len(idx)), "true": int(yy.sum()), "false": int((~yy).sum()),
                 "patients": int(sum(len(s) for s in strata))}
    return res


def within_cohort(D, models, y, cohort, k=None):
    mask = D.sets[cohort]
    folds = patient_folds(D, mask, k or 10 ** 6, SEED)
    fold_of = np.array([folds.get(p, -1) for p in D.patient])
    idx = np.nonzero(mask)[0]
    scores = {"RAW": D.raw[idx]}
    for m in models:
        s = np.zeros(len(idx))
        for f in sorted(set(fold_of[idx])):
            te = mask & (fold_of == f)
            tr = mask & (fold_of != f)
            assert_disjoint(D, tr, te)
            s[np.isin(idx, np.nonzero(te)[0])] = fit_predict(D, m, tr, te, y)
        scores[m] = s
    return scores, idx


# ------------------------------------------------------------------ conformal analyses
def _bh(p, alpha):
    p = np.asarray(p, float)
    m = p.size
    if m == 0:
        return np.zeros(0, bool)
    order = np.argsort(p, kind="mergesort")
    ok = np.nonzero(p[order] <= alpha * np.arange(1, m + 1) / m)[0]
    if ok.size == 0:
        return np.zeros(m, bool)
    return p <= p[order][ok.max()]


FAM = cf.EnvelopeFamily(FDX_DELTA, FDX_TEMPLATE)


def select_scan(scores, null, alpha, method):
    if scores.size == 0:
        return np.zeros(0, bool)
    k, n = cf.conformal_ranks(scores, null)
    if method == "bh":
        return _bh(k / (n + 1.0), alpha)
    return cf.select_fdx(k, n, alpha, FAM)[0]


def conformal_counts(D, test_scans, cand_scores, null, y, alpha, method):
    """Per-scan counts (n_sel, n_false_sel, n_true_sel, n_true, n_gt, clin_sel, n_gt_clin) for test scans.
    cand_scores: dict global-candidate-index -> score for every candidate of the test scans."""
    rows = []
    for s in test_scans:
        ci_ = np.nonzero(D.scan_idx == s)[0]
        sc = np.array([cand_scores[i] for i in ci_]) if ci_.size else np.zeros(0)
        sel = select_scan(sc, null, alpha, method)
        yt = y[ci_]
        rows.append((int(sel.sum()), int((sel & ~yt).sum()), int((sel & yt).sum()), int(yt.sum()),
                     int(D.s_ngt[s]), int((sel & yt & D.mg0_clin[ci_]).sum()), int(D.s_ngt_clin[s])))
    return np.asarray(rows, float).reshape(-1, 7)


def conf_metrics(rows, alpha):
    ns, nf, nt_sel, nt = rows[:, 0].sum(), rows[:, 1].sum(), rows[:, 2].sum(), rows[:, 3].sum()
    fdp = np.where(rows[:, 0] > 0, rows[:, 1] / np.maximum(rows[:, 0], 1), 0.0)
    return np.array([nt_sel / nt if nt else np.nan,                      # power (selection recall)
                     nt_sel / rows[:, 4].sum() if rows[:, 4].sum() else np.nan,   # end-to-end recall
                     rows[:, 5].sum() / rows[:, 6].sum() if rows[:, 6].sum() else np.nan,   # clinical recall
                     nf / ns if ns else 0.0,                              # micro FDR
                     fdp.mean(),                                          # mean per-scan FDP
                     (fdp > alpha).mean(),                                # per-scan exceedance
                     (rows[:, 0] == 0).mean()])                           # scans selecting nothing


CONF_KEYS = ("power", "recall_end_to_end", "recall_clinical", "micro_fdr", "mean_scan_fdp",
             "frac_scans_fdp_gt_alpha", "frac_scans_selecting_nothing")


def conf_summary(D, rows_by_model, scans, alpha, seed, ref="RAW"):
    """Point + patient-cluster bootstrap CI for each model, paired delta of power vs ref."""
    by = {}
    for j, s in enumerate(scans):
        by.setdefault(D.s_patient[s], []).append(j)
    strata = [[np.asarray(v) for _, v in sorted(by.items())]]
    names = list(rows_by_model)

    def stat(ii):
        return np.concatenate([conf_metrics(rows_by_model[n][ii], alpha) for n in names])
    point = stat(np.arange(len(scans)))
    bs = cluster_boot(strata, stat, N_BOOT, np.random.RandomState(seed))
    K = len(CONF_KEYS)
    out = {}
    for j, n in enumerate(names):
        r = {}
        for q, key in enumerate(CONF_KEYS):
            r[key] = _r(point[j * K + q])
            if key in ("power", "micro_fdr", "frac_scans_fdp_gt_alpha"):
                r[key + "_ci95"] = ci(bs[:, j * K + q])
        if ref in names and n != ref:
            k = names.index(ref)
            r["delta_power_vs_RAW"] = _r(point[j * K] - point[k * K])
            r["delta_power_vs_RAW_ci95"] = ci(bs[:, j * K] - bs[:, k * K])
        r["n_selected"] = int(rows_by_model[n][:, 0].sum())
        out[n] = r
    return out


def conformal_within_M(D, models, y):
    """Three-way patient cross-fit inside MSLesSeg: train 3 folds, null from fold k+1, test fold k."""
    mask = D.sets["M"]
    folds = patient_folds(D, mask, 5, SEED)
    fold_of_c = np.array([folds.get(p, -1) for p in D.patient])
    fold_of_s = np.array([folds.get(p, -1) for p in D.s_patient])
    scans_all = np.nonzero(D.scan_sets["M"])[0]
    per = {(a, meth): {m: [] for m in ("RAW",) + tuple(models)} for a in ALPHAS for meth in ("bh", "fdx")}
    scan_order = []
    for k in range(5):
        cal_f = (k + 1) % 5
        te = mask & (fold_of_c == k)
        ca = mask & (fold_of_c == cal_f)
        tr = mask & (fold_of_c != k) & (fold_of_c != cal_f)
        assert_disjoint(D, tr, ca, te)
        test_scans = scans_all[fold_of_s[scans_all] == k]
        scan_order.extend(test_scans)
        te_idx = np.nonzero(te)[0]
        scores = {"RAW": (D.raw[te_idx], D.raw[ca & ~y])}
        for m in models:
            fset, fitter = MODELS[m]
            f = fitter(D.F(fset, tr), y[tr].astype(int))
            scores[m] = (f(D.F(fset, te)), f(D.F(fset, ca & ~y)))
        for m, (s_te, null) in scores.items():
            cs = dict(zip(te_idx, s_te))
            for a in ALPHAS:
                for meth in ("bh", "fdx"):
                    per[(a, meth)][m].append(conformal_counts(D, test_scans, cs, null, y, a, meth))
    out = {}
    for (a, meth), d in per.items():
        rows = {m: np.vstack(v) for m, v in d.items()}
        out[f"{meth}|alpha={a}"] = conf_summary(D, rows, np.asarray(scan_order), a, SEED + 7)
    return out


def conformal_cross(D, models, y, control_models=("V3P-LR",)):
    """M -> L10 (and controls): 20 seeded 50/50 splits of the M patients into train / calibration."""
    M = D.sets["M"]
    pats = np.array(sorted(set(D.patient[M])))
    L_scans = np.nonzero(D.scan_sets["L10"])[0]
    C_scans = np.nonzero(D.scan_sets["C"])[0]
    names = ("RAW",) + tuple(models)
    acc = {(a, meth): {m: [] for m in names} for a in ALPHAS for meth in ("bh", "fdx")}
    acc_c = {(a, meth): {m: [] for m in ("RAW",) + tuple(control_models)} for a in ALPHAS for meth in ("bh", "fdx")}
    for sp in range(N_SPLITS_XCOHORT):
        rng = np.random.RandomState(SEED + 100 + sp)
        perm = rng.permutation(pats)
        tr_p, ca_p = set(perm[:len(pats) // 2]), set(perm[len(pats) // 2:])
        tr = M & np.isin(D.patient, list(tr_p))
        ca = M & np.isin(D.patient, list(ca_p))
        assert_disjoint(D, tr, ca, D.sets["L10"], D.sets["C"])
        L_idx = np.nonzero(D.sets["L10"])[0]
        C_idx = np.nonzero(D.sets["C"])[0]
        sc = {"RAW": (D.raw, D.raw[ca & ~y])}
        for m in set(models) | set(control_models):
            fset, fitter = MODELS[m]
            f = fitter(D.F(fset, tr), y[tr].astype(int))
            full = np.full(len(y), np.nan)
            full[L_idx] = f(D.F(fset, D.sets["L10"]))
            full[C_idx] = f(D.F(fset, D.sets["C"]))
            sc[m] = (full, f(D.F(fset, ca & ~y)))
        for a in ALPHAS:
            for meth in ("bh", "fdx"):
                for m in names:
                    s, null = sc[m]
                    acc[(a, meth)][m].append(conformal_counts(D, L_scans, s, null, y, a, meth))
                for m in ("RAW",) + tuple(control_models):
                    s, null = sc[m]
                    acc_c[(a, meth)][m].append(conformal_counts(D, C_scans, s, null, y, a, meth))
    out, out_c = {}, {}
    for (a, meth), d in acc.items():
        # sum counts over splits per scan (each scan = one cluster with 20 draws), exceedance per draw
        rows = {m: np.sum(v, axis=0) for m, v in d.items()}
        res = conf_summary(D, rows, L_scans, a, SEED + 11)
        for m, v in d.items():
            r_ = res[m]
            # summed-over-splits rows make per-scan FDP / exceedance meaningless: replace them by
            # per-draw quantities (each L10 scan = one cluster with N_SPLITS draws)
            for key in ("frac_scans_fdp_gt_alpha", "frac_scans_fdp_gt_alpha_ci95", "mean_scan_fdp"):
                r_.pop(key, None)
            r_["frac_scans_never_selecting"] = r_.pop("frac_scans_selecting_nothing")
            fdp = np.array([np.where(r[:, 0] > 0, r[:, 1] / np.maximum(r[:, 0], 1), 0.0) for r in v])   # splits x scans
            exc_scan = (fdp > a).mean(0)
            r_["frac_scans_fdp_gt_alpha_per_draw"] = _r(exc_scan.mean())
            bs = cluster_boot([[np.array([j]) for j in range(len(exc_scan))]], lambda ii: np.array([exc_scan[ii].mean()]),
                              N_BOOT, np.random.RandomState(SEED + 12))
            r_["frac_scans_fdp_gt_alpha_per_draw_ci95"] = ci(bs[:, 0])
            r_["mean_scan_fdp_per_draw"] = _r(fdp.mean())
            r_["frac_scans_selecting_nothing_per_draw"] = _r(np.mean([(r[:, 0] == 0).mean() for r in v]))
            pw = [conf_metrics(r, a)[0] for r in v]
            r_["power_split_range"] = [_r(min(pw)), _r(max(pw))]
        out[f"{meth}|alpha={a}"] = res
    for (a, meth), d in acc_c.items():
        res = {}
        for m, v in d.items():
            det = np.array([r[:, 0] for r in v])            # splits x control scans (all detections false)
            res[m] = {"false_detections_per_100_scans": _r(100 * det.sum(1).mean() / det.shape[1], 2),
                      "frac_control_scans_with_any_detection": _r((det > 0).mean()),
                      "control_scans_ever_with_detection": int((det > 0).any(0).sum()),
                      "control_scans": int(det.shape[1])}
        out_c[f"{meth}|alpha={a}"] = res
    return out, out_c


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=os.path.join(HERE, ".cache", "features_v3.npz"))
    ap.add_argument("--tag", default="2026-10-17")
    ap.add_argument("--quick", action="store_true", help="debug: B=200, fewer splits")
    ap.add_argument("--debug-no-gate", action="store_true", help="debug on synthetic caches only")
    ap.add_argument("--records-dir", default=RECORDS)
    a = ap.parse_args()
    global N_BOOT, N_SPLITS_XCOHORT, N_SHUFFLE, N_SMALLN
    if a.quick:
        N_BOOT, N_SPLITS_XCOHORT, N_SHUFFLE, N_SMALLN = 200, 3, 3, 3
    t0 = time.time()
    D = Data(a.cache)
    y = D.labels["lenient"]
    log = []

    def say(msg):
        print(msg, flush=True)
        log.append(msg)

    rec = {"protocol": "docs/research/lesion-detector-v3/PROTOCOL.md", "seed": SEED, "n_boot": N_BOOT,
           "cache": {"path": os.path.relpath(a.cache, ROOT), "sha256": hashlib.sha256(open(a.cache, "rb").read()).hexdigest()},
           "feature_sets": {k: list(v) for k, v in FEATURE_SETS.items()}}

    # ---------------- reproduction gate (PROTOCOL §4)
    gate = {}
    for nm in ("M", "L10", "C"):
        m = D.sets[nm]
        gate[nm] = {"candidates": int(m.sum()), "false_lenient": int((m & ~y).sum()),
                    "scans": int(D.scan_sets[nm].sum()) if nm in D.scan_sets else None}
    expected = {"M": (3866, 1348), "L10": (534, 94), "C": (83, None)}
    ok = all(gate[k]["candidates"] == v[0] and (v[1] is None or gate[k]["false_lenient"] == v[1]) for k, v in expected.items())
    gate["matches_paper_a_v02_cohort_table"] = bool(ok)
    rec["reproduction_gate"] = gate
    say(f"reproduction gate: {gate}")
    if not ok and not a.debug_no_gate:
        raise SystemExit("candidate/label counts do not reproduce paper A — stop (PROTOCOL §4)")
    rec["base_rates"] = {k: {"false_rate": _r(float((D.sets[k] & ~y).sum() / max(D.sets[k].sum(), 1))),
                             "fragment_false_share": _r(float((D.sets[k] & ~y & D.labels['anyvox']).sum() / max((D.sets[k] & ~y).sum(), 1)))}
                         for k in ("M", "L10", "Ltr")}

    # ---------------- PRIMARY: pooled LOCO
    say("primary: pooled leave-one-cohort-out ...")
    sc, idx = loco(D, PRIMARY_MODELS, y)
    prim = auc_table(D, sc, idx, y, [D.sets["M"], D.sets["L10"]], ref="RAW", ref2="V2-shipped")
    rec["primary_pooled_loco"] = prim
    d = prim["V3-LR"]
    met = bool(d["delta_vs_RAW"] >= 0.05 and d["delta_vs_RAW_ci95"][0] is not None and d["delta_vs_RAW_ci95"][0] > 0)
    stat_pos = bool(d["delta_vs_RAW_ci95"][0] is not None and d["delta_vs_RAW_ci95"][0] > 0)
    rec["primary_criterion"] = {
        "rule": "delta(V3-LR - RAW) >= 0.05 AND paired 95% CI lower bound > 0",
        "delta": d["delta_vs_RAW"], "delta_ci95": d["delta_vs_RAW_ci95"],
        "met": met, "statistically_positive": stat_pos,
        "h2_delta_vs_v2_shipped": d.get("delta_vs_V2-shipped"), "h2_ci95": d.get("delta_vs_V2-shipped_ci95"),
        "h2_met": bool(d.get("delta_vs_V2-shipped_ci95", [None])[0] is not None and d["delta_vs_V2-shipped_ci95"][0] > 0)}
    for n in sc:
        say(f"  {n:11s} pooled LOCO AUROC {prim[n]['auroc']} {prim[n]['ci95']}  dRAW {prim[n].get('delta_vs_RAW')} {prim[n].get('delta_vs_RAW_ci95')}")
    say(f"  PRIMARY criterion met: {met} (statistically positive: {stat_pos}); H2 vs V2-shipped: {rec['primary_criterion']['h2_met']}")

    # ---------------- S2: per direction / per cohort
    s2 = {}
    nA = int(D.sets["L10"].sum())
    for nm, sl, mk in (("A_M_to_L10", slice(0, nA), D.sets["L10"]), ("B_L10_to_M", slice(nA, None), D.sets["M"])):
        sub = {k: v[sl] for k, v in sc.items()}
        s2[nm] = auc_table(D, sub, idx[sl], y, [mk], ref="RAW", ref2="V2-shipped", seed=SEED + 1)
        say(f"  {nm}: " + ", ".join(f"{k} {s2[nm][k]['auroc']}" for k in sub))
    rec["S2_loco_per_direction"] = s2

    # ---------------- S1: within-cohort CV
    say("S1: within-cohort CV ...")
    s1 = {}
    for nm, k in (("M", 5), ("L10", None)):
        scw, idw = within_cohort(D, PRIMARY_MODELS, y, nm, k)
        s1[nm] = auc_table(D, scw, idw, y, [D.sets[nm]], ref="RAW", ref2="V2-shipped", seed=SEED + 2)
        say(f"  {nm}: " + ", ".join(f"{m} {s1[nm][m]['auroc']}" for m in scw))
    rec["S1_within_cohort"] = s1

    # ---------------- S5a: controls AUROC (L10 true vs control candidates), direction-A models
    say("S5: controls ...")
    trM = D.sets["M"]
    ctrl = {}
    te = D.sets["L10"] & y | D.sets["C"]
    idx_c = np.nonzero(te)[0]
    yc = np.zeros(len(y), bool)
    yc[D.sets["L10"] & y] = True
    scores_c = {"RAW": D.raw[idx_c]}
    for m in ("V3P-LR", "V3P-GB"):
        fset, fitter = MODELS[m]
        f = fitter(D.F(fset, trM), y[trM].astype(int))
        scores_c[m] = f(D.F(fset, te))
    ctrl["auroc_L10true_vs_control"] = auc_table(D, scores_c, idx_c, yc, [D.sets["L10"], D.sets["C"]], seed=SEED + 3)
    ctrl["note"] = "controls have no local FLAIR: only probability-map families (V3P) can be applied"
    rec["S5_controls"] = ctrl
    say("  " + ", ".join(f"{k} {ctrl['auroc_L10true_vs_control'][k]['auroc']}" for k in scores_c))

    # ---------------- S3 / S4 conformal
    if True:  # conformal analyses always run (quick mode only shrinks splits/bootstrap)
        say("S3: conformal within MSLesSeg (three-way cross-fit) ...")
        rec["S3_conformal_within_M"] = conformal_within_M(D, ("V3-LR", "V3-GB", "V2-shipped"), y)
        for key in ("bh|alpha=0.2", "fdx|alpha=0.2"):
            say(f"  {key}: " + ", ".join(f"{m} power {v['power']} FDR {v['micro_fdr']} exc {v['frac_scans_fdp_gt_alpha']}"
                                        for m, v in rec["S3_conformal_within_M"][key].items()))
        say("S4/S5: conformal M -> L10 and controls (20 splits) ...")
        s4, s5c = conformal_cross(D, ("V3-LR", "V3-GB", "V2-shipped"), y)
        rec["S4_conformal_M_to_L10"] = s4
        rec["S5_controls"]["conformal_false_detections"] = s5c
        for key in ("bh|alpha=0.2", "fdx|alpha=0.2"):
            say(f"  L10 {key}: " + ", ".join(f"{m} power {v['power']} FDR {v['micro_fdr']} exc {v['frac_scans_fdp_gt_alpha_per_draw']}"
                                            for m, v in s4[key].items()))
            say(f"  controls {key}: " + ", ".join(f"{m} FD/100 {v['false_detections_per_100_scans']}" for m, v in s5c[key].items()))

    # ---------------- adversarial self-check
    say("A1: shuffle-label null ...")
    nulls_loco, nulls_wm = [], []
    for r in range(N_SHUFFLE):
        s_, i_ = loco(D, ("V3-LR",), y, perm_seed=SEED + 1000 + 2 * r)
        nulls_loco.append(auroc(s_["V3-LR"], y[i_]))
        yp = y.copy()
        rng = np.random.RandomState(SEED + 5000 + r)
        Mi = np.nonzero(D.sets["M"])[0]
        yp[Mi] = rng.permutation(y[Mi])
        folds = patient_folds(D, D.sets["M"], 5, SEED)
        fo = np.array([folds.get(p, -1) for p in D.patient])
        oof = np.zeros(len(Mi))
        for f in range(5):
            trm, tem = D.sets["M"] & (fo != f), D.sets["M"] & (fo == f)
            fset, fitter = MODELS["V3-LR"]
            oof[np.isin(Mi, np.nonzero(tem)[0])] = fitter(D.F(fset, trm), yp[trm].astype(int))(D.F(fset, tem))
        nulls_wm.append(auroc(oof, y[Mi]))
    rec["A1_shuffle_null"] = {"pooled_loco_V3-LR": {"mean": _r(np.mean(nulls_loco)), "min": _r(min(nulls_loco)), "max": _r(max(nulls_loco))},
                              "within_M_V3-LR": {"mean": _r(np.mean(nulls_wm)), "min": _r(min(nulls_wm)), "max": _r(max(nulls_wm))},
                              "flag_if_mean_gt": 0.53,
                              "flagged": bool(np.mean(nulls_loco) > 0.53 or np.mean(nulls_wm) > 0.53)}
    say(f"  {rec['A1_shuffle_null']}")
    rec["A2_integrity"] = {"patient_disjointness_assertions": "passed (assert_disjoint in every split)",
                           "feature_code_takes_no_ground_truth": "unit test test_no_ground_truth_argument_anywhere"}

    say("A3: site-identity probe ...")
    ML = D.sets["M"] | D.sets["L10"]
    site = (D.cohort == "openms").astype(int)
    # folds stratified by cohort (PROTOCOL §11 D4): each fold has the same M / L10 patient mix
    folds = {**patient_folds(D, D.sets["M"], 5, SEED + 9), **patient_folds(D, D.sets["L10"], 5, SEED + 10)}
    fo = np.array([folds.get(p, -1) for p in D.patient])
    idxML = np.nonzero(ML)[0]
    a3 = {}
    groups = {"RAW(prob_mean)": ("prob_mean",), **{k: v for k, v in ABLATION_FAMILIES.items()}, "V3_all": FEATURE_SETS["V3"]}
    for gname, cols in groups.items():
        Xg = D.X[:, [D.col[c] for c in cols]]
        oof = np.zeros(len(idxML))
        for f in range(5):
            trm, tem = ML & (fo != f), ML & (fo == f)
            oof[np.isin(idxML, np.nonzero(tem)[0])] = fit_lr(Xg[trm], site[trm])(Xg[tem])
        a3[gname] = _r(auroc(oof, site[idxML].astype(bool)))
    rec["A3_site_identity_auroc"] = a3
    say(f"  {a3}")

    say("A4: label definitions ...")
    a4 = {}
    for lab in ("strict", "anyvox"):
        yl = D.labels[lab]
        s_, i_ = loco(D, ("V3-LR", "V2-shipped"), yl)
        t = auc_table(D, s_, i_, yl, [D.sets["M"], D.sets["L10"]], seed=SEED + 4)
        a4[lab] = t
        say(f"  {lab}: " + ", ".join(f"{k} {t[k]['auroc']} d {t[k].get('delta_vs_RAW')} {t[k].get('delta_vs_RAW_ci95')}" for k in s_))
    # A4b (added before any outcome was seen, PROTOCOL §11 D1): under one-to-one labels surplus
    # FRAGMENTS of a real lesion are FALSE. A detector could win by flagging fragments, which is
    # not removing false lesions. Re-score the primary pooled LOCO predictions with fragment-false
    # candidates (FALSE but overlapping GT) removed: TRUE vs PURE-false only.
    pure = ~(~y & D.labels["anyvox"])
    keep = pure[idx]
    sc_pure = {k: v[keep] for k, v in sc.items()}
    a4["pure_false_only_primary_predictions"] = auc_table(D, sc_pure, idx[keep], y, [D.sets["M"], D.sets["L10"]],
                                                          ref="RAW", ref2="V2-shipped", seed=SEED + 13)
    say("  pure-false only: " + ", ".join(f"{k} {a4['pure_false_only_primary_predictions'][k]['auroc']} "
                                           f"d {a4['pure_false_only_primary_predictions'][k].get('delta_vs_RAW')}" for k in sc_pure))
    rec["A4_label_definitions"] = a4

    say("A5: small-n optimism ...")
    Mm = D.sets["M"]
    pats = np.array(sorted(set(D.patient[Mm])))
    deltas, aucs = [], []
    for r in range(N_SMALLN):
        rng = np.random.RandomState(SEED + 300 + r)
        tp = set(rng.choice(pats, 10, replace=False))
        tr = Mm & np.isin(D.patient, list(tp))
        te = Mm & ~np.isin(D.patient, list(tp))
        s = fit_predict(D, "V3-LR", tr, te, y)
        a_m, a_r = auroc(s, y[te]), auroc(D.raw[te], y[te])
        aucs.append(a_m)
        deltas.append(a_m - a_r)
    nfeat = len(FEATURE_SETS["V3"])
    rec["A5_small_n"] = {"train_10_M_patients_test_rest": {"auroc_mean": _r(np.mean(aucs)), "auroc_range": [_r(min(aucs)), _r(max(aucs))],
                                                           "delta_vs_raw_mean": _r(np.mean(deltas)),
                                                           "delta_range": [_r(min(deltas)), _r(max(deltas))]},
                         "events_per_variable": {"L10_false_per_feature": _r((D.sets["L10"] & ~y).sum() / nfeat, 2),
                                                 "M_false_per_feature": _r((D.sets["M"] & ~y).sum() / nfeat, 2), "n_features_V3": nfeat}}
    # A5b (added before any outcome was seen, PROTOCOL §11 D2): the bootstrap CIs hold the fitted
    # model fixed. Direction B trains on only 10 patients, so add model-refit variance: refit V3-LR
    # on 50 patient-bootstrap resamples of L10 and score M.
    L10p = np.array(sorted(set(D.patient[D.sets["L10"]])))
    te = D.sets["M"]
    refit = []
    for r in range(50):
        rng = np.random.RandomState(SEED + 700 + r)
        pick = rng.choice(L10p, len(L10p), replace=True)
        rows_ = np.concatenate([np.nonzero(D.sets["L10"] & (D.patient == p))[0] for p in pick])
        fset, fitter = MODELS["V3-LR"]
        if len(set(y[rows_])) < 2:
            continue
        f = fitter(D.X[rows_][:, [D.col[c] for c in FEATURE_SETS[fset]]], y[rows_].astype(int))
        refit.append(auroc(f(D.F(fset, te)), y[te]))
    raw_M = auroc(D.raw[te], y[te])
    rec["A5_small_n"]["direction_B_refit_variance"] = {
        "n_refits": len(refit), "auroc_mean": _r(np.mean(refit)), "auroc_p2.5_p97.5": ci(refit),
        "raw_auroc_on_M": _r(raw_M), "frac_refits_below_raw": _r(np.mean(np.array(refit) < raw_M))}
    say(f"  {rec['A5_small_n']}")

    say("A6: contamination reference ...")
    a6 = {}
    for nm in ("L10", "L12", "Ltr", "LALL"):
        te = D.sets[nm]
        sc6 = {"RAW": D.raw[te]}
        for m in ("V3-LR", "V2-shipped"):
            sc6[m] = fit_predict(D, m, D.sets["M"], te, y)
        a6[nm] = auc_table(D, sc6, np.nonzero(te)[0], y, [te], seed=SEED + 5)
        say(f"  M -> {nm}: " + ", ".join(f"{k} {a6[nm][k]['auroc']}" for k in sc6))
    rec["A6_contamination"] = a6

    say("A7: drop-one-family ablation ...")
    a7 = {}
    base_cols = FEATURE_SETS["V3"]
    for fam, cols in ABLATION_FAMILIES.items():
        FEATURE_SETS["_ABL"] = tuple(c for c in base_cols if c not in cols)
        MODELS["_ABL-LR"] = ("_ABL", fit_lr)
        s_, i_ = loco(D, ("_ABL-LR",), y)
        a7[f"V3_minus_{fam}"] = _r(auroc(s_["_ABL-LR"], y[i_]))
    del FEATURE_SETS["_ABL"], MODELS["_ABL-LR"]
    a7["V3_full"] = prim["V3-LR"]["auroc"]
    rec["A7_ablation_pooled_loco_auroc"] = a7
    say(f"  {a7}")

    say("A8: intensity-preprocessing confound (KS M vs L10) ...")
    a8 = {}
    for c in fv.F1 + fv.F3 + fv.F4_FLAIR + fv.F6 + ("prob_mean",):
        j = D.col[c]
        row = {}
        for cls, cm in (("true", y), ("false", ~y)):
            u = D.X[D.sets["M"] & cm, j]
            v = D.X[D.sets["L10"] & cm, j]
            u, v = u[np.isfinite(u)], v[np.isfinite(v)]
            row[f"ks_D_{cls}"] = _r(ks_2samp(u, v).statistic, 3) if u.size and v.size else None
        a8[c] = row
    rec["A8_ks_M_vs_L10"] = a8

    say("E: exploratory ...")
    ex = {}
    s_ = {"RAW": D.raw[D.sets["M"]], "V3-LR": fit_predict(D, "V3-LR", D.sets["LALL"], D.sets["M"], y),
          "V2-shipped": fit_predict(D, "V2-shipped", D.sets["LALL"], D.sets["M"], y)}
    ex["E1_train_all30_Ljubljana_test_M"] = auc_table(D, s_, np.nonzero(D.sets["M"])[0], y, [D.sets["M"]], seed=SEED + 6)
    for fsn in ("V3+T1", "V3+CTX", "V3+MNI", "NEW_ONLY"):
        MODELS[f"{fsn}-LR"] = (fsn, fit_lr)
    s_, i_ = loco(D, ("V3+T1-LR", "V3+CTX-LR", "V3+MNI-LR", "NEW_ONLY-LR", "V3-LR"), y)
    ex["E2_E3_pooled_loco"] = auc_table(D, s_, i_, y, [D.sets["M"], D.sets["L10"]], seed=SEED + 8)
    rec["exploratory"] = ex
    say("  E1: " + ", ".join(f"{k} {ex['E1_train_all30_Ljubljana_test_M'][k]['auroc']}" for k in ("RAW", "V3-LR", "V2-shipped")))
    say("  E2/E3: " + ", ".join(f"{k} {ex['E2_E3_pooled_loco'][k]['auroc']}" for k in s_))

    rec["runtime_s"] = round(time.time() - t0, 1)
    tag = a.tag + ("_quick" if a.quick else "")
    os.makedirs(a.records_dir, exist_ok=True)
    out = os.path.join(a.records_dir, f"{tag}_lesion_detector_v3_evaluation.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1)
    with open(out.replace(".json", "_output.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(log) + "\n")
    say(f"wrote {out} in {rec['runtime_s']} s")


if __name__ == "__main__":
    main()
