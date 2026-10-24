#!/usr/bin/env python3
"""Lesion-detector v3.2 — the pre-registered evaluation (docs/research/lesion-detector-v3/PROTOCOL-v3.2.md).

Healthy controls (100 SibBMS) added to the v3.1 design, candidates from the 5-fold MEAN FLAMeS map:
  gate V1   reproduction of the v3.1 mean5 cache (MS + external) and of paper A's control candidates
  H1        AUROC 1-mm MS TRUE vs control candidates (out-of-fold), GR+C-LR vs ENS-RAW  [primary]
  H2        GR+C-LR vs GR-LR (the MS-trained v3.1 detector) on the H1 endpoint
  H3        healthy false candidates per control scan at 90 % 1-mm MS sensitivity
  H4        unseen MS sites: non-inferiority of GR+C-LR vs GR-LR (+ deployable operating point)
  S1-S3     per cohort / MS-only / per site;  S-CAL healthy-calibrated threshold;  S-REG regions
  K1-K9     confound and leakage checks (K2 cohort-identity probe, K3 controls-only transfer test, ...)
Reuses evaluate_v3 (models, AUROC, cluster bootstrap) and evaluate_v31 (data class, GR features).

    python research/lesion_detector_v3/evaluate_v32.py --cache .cache/features_v32.npz
        --v31-mean5-cache .cache/features_v31_mean5.npz --paper-a-record <2026-10-24_paper_a_v03c_controls.json>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.stats import beta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import evaluate_v3 as ev                                                  # noqa: E402
import evaluate_v31 as e31                                                # noqa: E402
import features_v3 as fv                                                  # noqa: E402

SEED = ev.SEED
K = 5
SITES = e31.SITES
GR = e31.GR_BASE + fv.F8
ev.FEATURE_SETS.update({
    "GR": GR,
    "GR-noVOL": tuple(c for c in GR if c != "log_volume_mm3"),
    "GRL": GR + fv.F9 + fv.F9B,
    "GR-noENS": e31.GR_BASE,
    "F8": fv.F8,
    "LST": fv.F9 + fv.F9B,
    "VOL": ("log_volume_mm3",),
    "PROB": ("prob_mean",),
})
# name -> (feature set, fitter, controls in training, controls are the ONLY negatives)
MODELS = {
    "GR-LR": ("GR", ev.fit_lr, False, False),
    "GR+C-LR": ("GR", ev.fit_lr, True, False),
    "GR+C-GB": ("GR", ev.fit_gb, True, False),
    "GR+C-noVOL-LR": ("GR-noVOL", ev.fit_lr, True, False),
    "GRL-LR": ("GRL", ev.fit_lr, False, False),
    "GRL+C-LR": ("GRL", ev.fit_lr, True, False),
    "GR-Conly-LR": ("GR", ev.fit_lr, True, True),
}
FIXED = ("ENS-RAW", "DIS-RAW")
ALL_SCORES = FIXED + tuple(MODELS)
EXT_MODELS = ("GR-LR", "GR+C-LR", "GR-Conly-LR")      # no LST-AI maps on the external sites
H3_SCORES = ("ENS-RAW", "DIS-RAW", "GR-LR", "GR+C-LR", "GR+C-GB", "GR+C-noVOL-LR", "GRL-LR", "GRL+C-LR")
PROBE_FAMILIES = ("GR", "GR-noENS", "F8", "LST", "VOL", "PROB")
AUGUST = {f"sub-{i:03d}" for i in list(range(1, 21)) + list(range(31, 41))}
QC_FLAG = "sub-075"
EXPECTED = {"M": (3788, 1257), "L10": (517, 82), "ms3seg": (3402, 1162), "muslim": (1540, 568),
            "pedims": (1110, 321)}
OOF_OUT = os.path.join(HERE, ".cache", "v32_scores.npz")


class Data32(e31.Data31):
    def __init__(self, path):
        super().__init__(path)
        self.sets["MS1"] = self.sets["M"] | self.sets["L10"]
        self.ctl_scans = np.nonzero(self.scan_sets["C"])[0]
        self.case = self.s_case[self.scan_idx]
        fm = ev.patient_folds(self, self.sets["M"], K, SEED + 200)
        fl = ev.patient_folds(self, self.sets["L10"], K, SEED + 201)
        subj = sorted(set(self.s_patient[self.ctl_scans]))          # all controls, incl. 0 candidates
        perm = np.random.RandomState(SEED + 202).permutation(subj)
        fc = {p: i % K for i, p in enumerate(perm)}
        assert not (set(fm) & set(fc)) and not (set(fl) & set(fc)) and not (set(fm) & set(fl))
        self.fold_map = {**fm, **fl, **fc}
        self.fold = np.array([self.fold_map.get(p, -1) for p in self.patient])
        self.s_fold = np.array([self.fold_map.get(p, -1) for p in self.s_patient])
        self.pool1 = self.sets["MS1"] | self.sets["C"]
        assert (self.fold[self.pool1] >= 0).all()

    def scan_cands(self, s):
        return np.nonzero(self.scan_idx == s)[0]


# ------------------------------------------------------------------ helpers
def r_(x, d=4):
    return ev._r(x, d)


def cp(x, n, level=0.95):
    a = 1 - level
    lo = 0.0 if x == 0 else beta.ppf(a / 2, x, n - x + 1)
    hi = 1.0 if x == n else beta.ppf(1 - a / 2, x + 1, n - x)
    return [r_(lo), r_(hi)]


def crossfit(D, y, name, perm_seed=None):
    """Out-of-fold scores for every 1-mm candidate (MS + controls), §4 folds."""
    fset, fitter, use_c, conly = MODELS[name]
    out = np.full(len(y), np.nan)
    for k in range(K):
        te = D.pool1 & (D.fold == k)
        tr_ms = D.sets["MS1"] & (D.fold != k)
        if conly:
            tr_ms = tr_ms & y
        tr_c = (D.sets["C"] & (D.fold != k)) if use_c else np.zeros(len(y), bool)
        tr = tr_ms | tr_c
        ev.assert_disjoint(D, tr, te)
        ev.assert_disjoint(D, tr, D.sets["EXT"])
        ytr = y[tr].astype(int)
        if perm_seed is not None:
            ytr = np.random.RandomState(perm_seed + k).permutation(ytr)
        f = fitter(D.F(fset, tr), ytr)
        out[te] = f(D.F(fset, te))
    return out


def fit_full(D, y, name):
    """Model trained on ALL 1-mm data (for the external sites). Returns the fitted scorer and mask."""
    fset, fitter, use_c, conly = MODELS[name]
    tr = D.sets["MS1"] & (y if conly else np.ones(len(y), bool))
    if use_c:
        tr = tr | D.sets["C"]
    ev.assert_disjoint(D, tr, D.sets["EXT"])
    f = fitter(D.F(fset, tr), y[tr].astype(int))
    return (lambda mask: f(D.F(fset, mask))), tr


def table(D, S, idx, y, strata, names, ref="ENS-RAW", ref2="GR-LR", seed=SEED + 301, B=None):
    sc = {n: S[n][idx] for n in names}
    return ev.auc_table(D, sc, idx, y, strata, ref=ref, ref2=ref2, seed=seed, B=B or ev.N_BOOT)


def strata_1mm(D, with_c=True):
    return [D.sets["M"], D.sets["L10"]] + ([D.sets["C"]] if with_c else [])


def foldwise_table(D, scores, idx, lab, strata, names, ref, seed, B=None):
    """Deviation D1 (PROTOCOL-v3.2 §11): mean over the 5 folds of the WITHIN-fold AUROC. Pooling
    out-of-fold scores of 5 different models adds fold-specific offsets that bias the pooled AUROC
    below 0.5 for weak signals (dry run on random features: down to 0.29). Cluster bootstrap as
    auc_table (clusters keep their fold); paired differences vs `ref`."""
    B = B or ev.N_BOOT
    pos = {g: k for k, g in enumerate(idx)}
    inidx = np.isin(np.arange(len(lab)), idx)
    st = [[np.array([pos[g] for g in cl]) for cl in D.clusters(sm & inidx)] for sm in strata]
    st = [s for s in st if s]
    fo, ll = D.fold[idx], np.asarray(lab, bool)[idx]
    sc = {n: np.asarray(scores[n])[idx] for n in names}

    def stat(ii):
        out = []
        for n in names:
            v = [ev.auroc(sc[n][ii][fo[ii] == k], ll[ii][fo[ii] == k]) for k in range(K)]
            v = [x for x in v if x is not None]
            out.append(np.mean(v) if v else np.nan)
        return np.array(out)
    point = stat(np.arange(len(idx)))
    bs = ev.cluster_boot(st, stat, B, np.random.RandomState(seed))
    res = {}
    for j, n in enumerate(names):
        r = {"auroc_foldwise_mean": r_(point[j]), "ci95": ev.ci(bs[:, j])}
        if ref in names and ref != n:
            kk = names.index(ref)
            r[f"delta_vs_{ref}"] = r_(point[j] - point[kk])
            r[f"delta_vs_{ref}_ci95"] = ev.ci(bs[:, j] - bs[:, kk])
        res[n] = r
    return res


# ------------------------------------------------------------------ gate V1
def cand_keys(D, mask):
    pos = np.zeros(len(D.scan_idx), int)
    for s in np.unique(D.scan_idx):
        ii = np.nonzero(D.scan_idx == s)[0]
        pos[ii] = np.arange(len(ii))
    idx = np.nonzero(mask)[0]
    return idx, [f"{D.s_case[D.scan_idx[i]]}#{pos[i]}" for i in idx]


def gate_v31(D, D0, y, y0):
    out = {}
    for nm, (n_c, n_f) in EXPECTED.items():
        got = (int(D.sets[nm].sum()), int((D.sets[nm] & ~y).sum()))
        out[nm] = {"candidates_false": list(got), "expected": [n_c, n_f], "ok": got == (n_c, n_f)}
    m = D.sets["MS1"] | D.sets["EXT"]
    m0 = D0.sets["M"] | D0.sets["L10"] | D0.sets["EXT"]
    i1, k1 = cand_keys(D, m)
    i0, k0 = cand_keys(D0, m0)
    same_keys = k1 == k0
    maxdiff, lab_equal = None, None
    if same_keys:
        cols = list(ev.FEATURE_SETS["GR"])
        a = D.X[i1][:, [D.col[c] for c in cols]]
        b = D0.X[i0][:, [D0.col[c] for c in cols]]
        both_nan = np.isnan(a) & np.isnan(b)
        diff = np.where(both_nan, 0.0, np.abs(a - b))
        maxdiff = float(np.nanmax(np.where(np.isnan(diff), np.inf, diff)))
        lab_equal = bool((y[i1] == y0[i0]).all())
    out["ms_external_same_candidates"] = bool(same_keys)
    out["gr_features_max_abs_diff"] = maxdiff
    out["labels_equal"] = lab_equal
    out["passed"] = bool(all(v["ok"] for k, v in out.items() if isinstance(v, dict)) and same_keys
                         and maxdiff is not None and maxdiff <= 1e-6 and lab_equal)
    return out


def gate_paper_a(D, rec_a):
    """Control candidates vs paper A's ensemble arm; returns (gate dict, region label per candidate)."""
    per = {r["case"]: int(r["ens_candidates"]) for r in rec_a["per_control"]}
    rows = {}
    for r in rec_a["location_rows_ens"]:
        rows.setdefault(r["case"], []).append(r)
    region = np.array([""] * len(D.raw), dtype=object)
    bad, worst_score, n_scans_any, total = [], 0.0, 0, 0
    vol = np.round(np.exp(D.X[:, D.col["log_volume_mm3"]]))
    for s in D.ctl_scans:
        case = str(D.s_case[s])
        ci = D.scan_cands(s)
        total += len(ci)
        n_scans_any += int(len(ci) > 0)
        ra = rows.get(case, [])
        if len(ci) != per.get(case, -1) or len(ra) != len(ci):
            bad.append(f"{case}: {len(ci)} candidates vs paper A {per.get(case)}")
            continue
        if not len(ci):
            continue
        cost = np.array([[abs(D.raw[i] - r["score"]) + (0 if vol[i] == round(r["vol_mm3"]) else 10.0)
                          for r in ra] for i in ci])
        rr, cc = linear_sum_assignment(cost)
        for a_, b_ in zip(rr, cc):
            i, r = ci[a_], ra[b_]
            d = abs(D.raw[i] - r["score"])
            worst_score = max(worst_score, d)
            if d > 0.003 or vol[i] != round(r["vol_mm3"]):
                bad.append(f"{case}: score {D.raw[i]:.4f}/{r['score']:.4f} vol {vol[i]}/{r['vol_mm3']}")
            region[i] = r["region"]
    g = {"controls": int(len(D.ctl_scans)), "candidates_total": int(total), "scans_with_any": n_scans_any,
         "paper_a_total": int(sum(per.values())), "max_abs_score_diff": r_(worst_score, 5),
         "mismatches": bad[:20], "n_mismatches": len(bad),
         "passed": bool(not bad and len(D.ctl_scans) == 100 and total == sum(per.values()))}
    return g, region


# ------------------------------------------------------------------ H3 healthy false candidates at fixed sensitivity
def h3(D, y, S, names, seed, ctl_scans=None, sens=0.90, B=None):
    B = B or ev.N_BOOT
    ctl_scans = D.ctl_scans if ctl_scans is None else ctl_scans
    ms_cl = [[cl[y[cl]] for cl in D.clusters(D.sets[s])] for s in ("M", "L10")]
    ctl_cl = [D.scan_cands(s) for s in ctl_scans]
    q = 1.0 - sens

    def stat(ms_idx, ctl_lists):
        lens = np.array([len(c) for c in ctl_lists])
        allc = np.concatenate(ctl_lists) if lens.sum() else np.zeros(0, int)
        owner = np.repeat(np.arange(len(ctl_lists)), lens)
        row = []
        for n in names:
            s = S[n]
            tau = np.quantile(s[ms_idx], q, method="lower")
            hit = s[allc] >= tau
            per = np.bincount(owner[hit], minlength=len(ctl_lists))
            row += [per.mean(), (per > 0).mean(), tau]
        return np.array(row, float)

    ms_all = np.concatenate([c for st in ms_cl for c in st])
    point = stat(ms_all, ctl_cl)
    rng = np.random.RandomState(seed)
    bs = []
    for _ in range(B):
        ms = []
        for st in ms_cl:
            pick = rng.randint(0, len(st), len(st))
            ms.extend(st[i] for i in pick)
        pick = rng.randint(0, len(ctl_cl), len(ctl_cl))
        bs.append(stat(np.concatenate(ms), [ctl_cl[i] for i in pick]))
    bs = np.asarray(bs)
    res = {"sensitivity_kept": sens, "n_controls": len(ctl_cl), "n_ms_true": int(ms_all.size)}
    j = {n: 3 * k for k, n in enumerate(names)}
    for n in names:
        a = j[n]
        r = {"false_per_control_scan": r_(point[a]), "fps_ci95": ev.ci(bs[:, a]),
             "share_controls_with_any": r_(point[a + 1]), "share_ci95": ev.ci(bs[:, a + 1]),
             "share_cp95_fixed_tau": cp(int(round(point[a + 1] * len(ctl_cl))), len(ctl_cl)),
             "threshold": r_(point[a + 2])}
        for ref in ("ENS-RAW", "GR-LR"):
            if ref in j and ref != n:
                b = j[ref]
                r[f"fps_minus_{ref}"] = r_(point[a] - point[b])
                r[f"fps_minus_{ref}_ci95"] = ev.ci(bs[:, a] - bs[:, b])
                r[f"fps_ratio_to_{ref}"] = r_(point[a] / point[b]) if point[b] > 0 else None
                with np.errstate(divide="ignore", invalid="ignore"):
                    rat = np.where(bs[:, b] > 0, bs[:, a] / bs[:, b], np.nan)
                r[f"fps_ratio_to_{ref}_ci95"] = ev.ci(rat)
        res[n] = r
    return res


# ------------------------------------------------------------------ H4 deployable operating point (external)
def ext_operating(D, y, sc_full, taus, names, seed, B=None):
    B = B or ev.N_BOOT
    strata = []
    for s in SITES:
        pats = sorted(set(D.s_patient[D.scan_sets[s]]))
        strata.append([(np.nonzero(D.sets[s] & (D.patient == p))[0],
                        int(((D.s_patient == p) & D.scan_sets[s]).sum())) for p in pats])

    def stat(items):
        cand = np.concatenate([c for c, _ in items])
        nsc = sum(n for _, n in items)
        yt = y[cand]
        row = []
        for n in names:
            hit = sc_full[n][cand] >= taus[n]
            row += [hit[yt].mean() if yt.any() else np.nan, (hit & ~yt).sum() / max(nsc, 1)]
        return np.array(row, float)

    point = stat([it for st in strata for it in st])
    rng = np.random.RandomState(seed)
    bs = np.asarray([stat([st[i] for st in strata for i in rng.randint(0, len(st), len(st))]) for _ in range(B)])
    res = {}
    j = {n: 2 * k for k, n in enumerate(names)}
    for n in names:
        a = j[n]
        r = {"threshold": r_(taus[n]), "external_sensitivity": r_(point[a]), "sens_ci95": ev.ci(bs[:, a]),
             "external_false_per_scan": r_(point[a + 1]), "fp_ci95": ev.ci(bs[:, a + 1])}
        for ref in ("GR-LR", "ENS-RAW"):
            if ref != n:
                b = j[ref]
                r[f"sens_minus_{ref}"] = r_(point[a] - point[b])
                r[f"sens_minus_{ref}_ci95"] = ev.ci(bs[:, a] - bs[:, b])
                r[f"fp_minus_{ref}"] = r_(point[a + 1] - point[b + 1])
                r[f"fp_minus_{ref}_ci95"] = ev.ci(bs[:, a + 1] - bs[:, b + 1])
        res[n] = r
    return res


# ------------------------------------------------------------------ S-CAL healthy-calibrated threshold
def scal(D, y, alphas=(0.1, 0.2), names=("ENS-RAW", "GR-LR", "GR+C-LR")):
    acc = {(n, a): {"flag": [], "fp": [], "ms_hit": np.zeros(len(y), bool), "ext_sens": [], "ext_fp": [],
                    "tau": []} for n in names for a in alphas}
    ms_tested = np.zeros(len(y), bool)
    ext = D.sets["EXT"]
    n_ext_scans = int(sum(D.scan_sets[s].sum() for s in SITES))
    for k in range(K):
        cal_f, trn_f = [(k + 1) % K, (k + 2) % K], [(k + 3) % K, (k + 4) % K]
        tr_c = D.sets["C"] & np.isin(D.fold, trn_f)
        cal_c = D.sets["C"] & np.isin(D.fold, cal_f)
        te_c = D.sets["C"] & (D.fold == k)
        tr_ms = D.sets["MS1"] & (D.fold != k)
        te_ms = D.sets["MS1"] & (D.fold == k)
        ev.assert_disjoint(D, tr_ms | tr_c, cal_c, te_c | te_ms, ext)
        cal_scans = [s for s in D.ctl_scans if D.s_fold[s] in cal_f]
        te_scans = [s for s in D.ctl_scans if D.s_fold[s] == k]
        need = cal_c | te_c | te_ms | ext
        sc = {"ENS-RAW": D.raw}
        for n, tr in (("GR-LR", tr_ms), ("GR+C-LR", tr_ms | tr_c)):
            f = ev.fit_lr(D.F("GR", tr), y[tr].astype(int))
            full = np.full(len(y), np.nan)
            full[need] = f(D.F("GR", need))
            sc[n] = full
        ms_tested |= te_ms & y
        for n in names:
            s = sc[n]
            Mi = np.array([s[D.scan_cands(c)].max() if D.scan_cands(c).size else -np.inf for c in cal_scans])
            nc = len(Mi)
            for a in alphas:
                rk = math.ceil(round((nc + 1) * (1 - a), 9))
                tau = np.sort(Mi)[rk - 1] if rk <= nc else np.inf
                A = acc[(n, a)]
                A["tau"].append(float(tau))
                for c in te_scans:
                    hits = int((s[D.scan_cands(c)] > tau).sum())
                    A["fp"].append(hits)
                    A["flag"].append(hits > 0)
                A["ms_hit"] |= te_ms & y & (s > tau)
                et = ext & y
                A["ext_sens"].append(float((s[et] > tau).mean()))
                A["ext_fp"].append(float((ext & ~y & (s > tau)).sum()) / n_ext_scans)
    out = {}
    ms_cl = [[cl[y[cl]] for cl in D.clusters(D.sets[s])] for s in ("M", "L10")]
    for (n, a), A in acc.items():
        x, nn = int(np.sum(A["flag"])), len(A["flag"])
        hit = A["ms_hit"]

        def sens_stat(ii, hit=hit):
            return np.array([hit[ii].mean()])
        bs = ev.cluster_boot(ms_cl, sens_stat, ev.N_BOOT, np.random.RandomState(SEED + 351))
        out[f"{n}|alpha={a}"] = {
            "held_out_controls_flagged": x, "n_controls": nn, "share_flagged": r_(x / nn), "cp95": cp(x, nn),
            "within_alpha_plus_0.05": bool(x / nn <= a + 0.05),
            "false_per_control_scan": r_(float(np.mean(A["fp"]))),
            "ms_1mm_sensitivity": r_(float(hit[ms_tested].mean())), "ms_1mm_sens_ci95": ev.ci(bs[:, 0]),
            "external_sensitivity_mean_over_rotations": r_(float(np.mean(A["ext_sens"]))),
            "external_sensitivity_range": [r_(min(A["ext_sens"])), r_(max(A["ext_sens"]))],
            "external_false_per_scan_mean": r_(float(np.mean(A["ext_fp"]))),
            "thresholds": [r_(t) for t in A["tau"]]}
    return out


# ------------------------------------------------------------------ K2 cohort-identity probe
def probe(D, fset, mask_a, mask_b, extra=None):
    """Out-of-fold LR (the §4 folds) separating mask_b (label 1) from mask_a (label 0); candidates in
    `extra` are scored by the model of their fold as well."""
    both = mask_a | mask_b
    lab = mask_b.astype(int)
    tgt = both | (extra if extra is not None else np.zeros(len(lab), bool))
    out = np.full(len(lab), np.nan)
    for k in range(K):
        tr = both & (D.fold != k)
        te = tgt & (D.fold == k)
        ev.assert_disjoint(D, tr, te)
        f = ev.fit_lr(D.F(fset, tr), lab[tr])
        out[te] = f(D.F(fset, te))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=os.path.join(HERE, ".cache", "features_v32.npz"))
    ap.add_argument("--v31-mean5-cache", default=os.path.join(HERE, ".cache", "features_v31_mean5.npz"))
    ap.add_argument("--paper-a-record", required=True)
    ap.add_argument("--tag", default="2026-10-24")
    ap.add_argument("--records-dir", default=ev.RECORDS)
    ap.add_argument("--quick", action="store_true", help="debug: B=200, 3 shuffles")
    ap.add_argument("--debug-no-gate", action="store_true", help="debug on synthetic caches only")
    a = ap.parse_args()
    if a.quick:
        ev.N_BOOT, ev.N_SHUFFLE = 200, 3
    t0 = time.time()
    D = Data32(a.cache)
    y = D.labels["lenient"]
    assert not y[D.sets["C"]].any(), "a control candidate is labelled TRUE"
    log = []

    def say(m):
        print(m, flush=True)
        log.append(m)

    sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()          # noqa: E731
    rec = {"protocol": "docs/research/lesion-detector-v3/PROTOCOL-v3.2.md", "seed": SEED, "n_boot": ev.N_BOOT,
           "cache": {"path": os.path.relpath(a.cache, ev.ROOT), "sha256": sha(a.cache)},
           "paper_a_record_sha256": sha(a.paper_a_record),
           "code_sha256": {f: sha(os.path.join(HERE, f)) for f in
                           ("evaluate_v32.py", "evaluate_v3.py", "evaluate_v31.py", "features_v3.py", "build_features.py")},
           "feature_sets": {k: list(ev.FEATURE_SETS[k]) for k in ("GR", "GR-noVOL", "GRL", "GR-noENS", "F8", "LST")},
           "folds": {"M": SEED + 200, "L10": SEED + 201, "controls": SEED + 202, "K": K}}
    meta_path = a.cache.replace(".npz", "_meta.json")
    if os.path.exists(meta_path):
        m = json.load(open(meta_path, encoding="utf-8"))
        rec["cache"]["inputs_combined_sha256"] = m.get("inputs_combined_sha256")
        rec["cache"]["options"] = m.get("options")

    # ---------------- gate V1
    D0 = e31.Data31(a.v31_mean5_cache)
    g1 = gate_v31(D, D0, y, D0.labels["lenient"])
    rec_a = json.load(open(a.paper_a_record, encoding="utf-8"))
    g2, region = gate_paper_a(D, rec_a)
    rec["gate_V1"] = {"a_v31_mean5": g1, "b_paper_a_controls": g2}
    say(f"gate V1a: {json.dumps(g1)}")
    say(f"gate V1b: {json.dumps(g2)}")
    if not (g1["passed"] and g2["passed"]) and not a.debug_no_gate:
        raise SystemExit("gate V1 failed - stop")
    for nm in ("MS1", "C", "EXT"):
        if np.isnan(D.X[D.sets[nm]][:, [D.col[c] for c in GR]]).any():
            raise SystemExit(f"GR features missing in {nm} - stop")
    # folds / integrity (K1)
    k1 = {"fold_sizes_controls": [int((D.s_fold[D.ctl_scans] == k).sum()) for k in range(K)],
          "fold_sizes_M_patients": [sum(1 for p, f in D.fold_map.items() if f == k and p.startswith("mslesseg")) for k in range(K)],
          "fold_sizes_L10_patients": [sum(1 for p, f in D.fold_map.items() if f == k and p.startswith("openms")) for k in range(K)],
          "control_subjects": int(len(set(D.s_patient[D.ctl_scans]))),
          "assertions": "assert_disjoint on every train/calibration/test split; external never trained or calibrated on"}
    rec["K1_integrity"] = k1
    say(f"K1: {json.dumps(k1)}")

    # ---------------- descriptives
    nc = np.array([D.scan_cands(s).size for s in D.ctl_scans])
    rec["descriptives"] = {
        nm: {"candidates": int(D.sets[nm].sum()), "true": int((D.sets[nm] & y).sum()), "false": int((D.sets[nm] & ~y).sum())}
        for nm in ("M", "L10", "C") + SITES}
    rec["descriptives"]["C"].update({"scans": int(len(D.ctl_scans)), "scans_with_any": int((nc > 0).sum()),
                                     "per_scan_mean": r_(nc.mean())})

    # ---------------- scores
    say("cross-fitting ...")
    S = {"ENS-RAW": D.raw.astype(float), "DIS-RAW": -D.X[:, D.col["ens_std"]]}
    for n in MODELS:
        S[n] = crossfit(D, y, n)
    pos_ms = D.sets["MS1"] & y
    idx_h1 = np.nonzero(pos_ms | D.sets["C"])[0]

    # ---------------- H1 / H2
    say("H1 / H2 ...")
    h1 = table(D, S, idx_h1, y, strata_1mm(D), ALL_SCORES, seed=SEED + 301)
    rec["H1_primary_ms_true_vs_controls"] = h1
    for n in ALL_SCORES:
        say(f"  {n:14s} AUROC {h1[n]['auroc']} {h1[n]['ci95']}  dENS {h1[n].get('delta_vs_ENS-RAW')} "
            f"{h1[n].get('delta_vs_ENS-RAW_ci95')}  dGR {h1[n].get('delta_vs_GR-LR')} {h1[n].get('delta_vs_GR-LR_ci95')}")
    p_ = h1["GR+C-LR"]
    crit = {"primary_rule": "delta(GR+C-LR - ENS-RAW) >= 0.05 AND paired 95% CI lower bound > 0 (H1 endpoint)",
            "primary_delta": p_["delta_vs_ENS-RAW"], "primary_ci95": p_["delta_vs_ENS-RAW_ci95"]}
    lo = p_["delta_vs_ENS-RAW_ci95"][0]
    crit["primary_statistically_positive"] = bool(lo is not None and lo > 0)
    crit["primary_met"] = bool(crit["primary_statistically_positive"] and p_["delta_vs_ENS-RAW"] >= 0.05)
    crit["H2_delta_vs_GR_LR"], crit["H2_ci95"] = p_["delta_vs_GR-LR"], p_["delta_vs_GR-LR_ci95"]
    crit["H2_met"] = bool(p_["delta_vs_GR-LR_ci95"][0] is not None and p_["delta_vs_GR-LR_ci95"][0] > 0)

    # ---------------- H3
    say("H3 healthy false candidates at 90 % sensitivity ...")
    h3r = h3(D, y, S, H3_SCORES, SEED + 311)
    rec["H3_false_per_control_at_90pct_sensitivity"] = h3r
    for n in H3_SCORES:
        say(f"  {n:14s} FPS {h3r[n]['false_per_control_scan']} {h3r[n]['fps_ci95']}  any {h3r[n]['share_controls_with_any']} "
            f"ratio/ENS {h3r[n].get('fps_ratio_to_ENS-RAW')} diff {h3r[n].get('fps_minus_ENS-RAW')} {h3r[n].get('fps_minus_ENS-RAW_ci95')}")
    hh = h3r["GR+C-LR"]
    crit["H3_ratio"], crit["H3_diff"], crit["H3_diff_ci95"] = hh["fps_ratio_to_ENS-RAW"], hh["fps_minus_ENS-RAW"], hh["fps_minus_ENS-RAW_ci95"]
    crit["H3_met"] = bool(hh["fps_ratio_to_ENS-RAW"] is not None and hh["fps_ratio_to_ENS-RAW"] <= 0.75
                          and hh["fps_minus_ENS-RAW_ci95"][1] is not None and hh["fps_minus_ENS-RAW_ci95"][1] < 0)

    # ---------------- H4 external
    say("H4 external (unseen MS sites) ...")
    ext = D.sets["EXT"]
    idx_ext = np.nonzero(ext)[0]
    S_ext = {"ENS-RAW": D.raw.astype(float).copy()}
    taus = {"ENS-RAW": float(np.quantile(D.raw[pos_ms], 0.10, method="lower"))}
    for n in EXT_MODELS:
        f, _ = fit_full(D, y, n)
        full = np.full(len(y), np.nan)
        full[ext] = f(ext)
        S_ext[n] = full
        taus[n] = float(np.quantile(f(pos_ms), 0.10, method="lower"))
    ext_names = ("ENS-RAW",) + EXT_MODELS
    h4 = ev.auc_table(D, {n: S_ext[n][idx_ext] for n in ext_names}, idx_ext, y, [D.sets[s] for s in SITES],
                      ref="GR-LR", ref2="ENS-RAW", seed=SEED + 341)
    rec["H4_external_pooled"] = h4
    for n in ext_names:
        say(f"  {n:14s} AUROC {h4[n]['auroc']} {h4[n]['ci95']} dGR {h4[n].get('delta_vs_GR-LR')} {h4[n].get('delta_vs_GR-LR_ci95')} "
            f"dENS {h4[n].get('delta_vs_ENS-RAW')} {h4[n].get('delta_vs_ENS-RAW_ci95')}")
    crit["H4_delta_vs_GR_LR"], crit["H4_ci95"] = h4["GR+C-LR"]["delta_vs_GR-LR"], h4["GR+C-LR"]["delta_vs_GR-LR_ci95"]
    crit["H4_noninferior"] = bool(crit["H4_ci95"][0] is not None and crit["H4_ci95"][0] > -0.01)
    opx = ext_operating(D, y, S_ext, taus, ext_names, SEED + 342)
    rec["H4_external_deployable_operating_point"] = opx
    for n in ext_names:
        say(f"  {n:14s} tau {opx[n]['threshold']} sens {opx[n]['external_sensitivity']} {opx[n]['sens_ci95']} "
            f"FP/scan {opx[n]['external_false_per_scan']} {opx[n]['fp_ci95']}")
    per_site = {}
    for s in SITES:
        ii = np.nonzero(D.sets[s])[0]
        per_site[s] = ev.auc_table(D, {n: S_ext[n][ii] for n in ext_names}, ii, y, [D.sets[s]], ref="GR-LR",
                                   ref2="ENS-RAW", seed=SEED + 343)
        say(f"  {s}: " + ", ".join(f"{n} {per_site[s][n]['auroc']}" for n in ext_names))
    rec["S3_external_per_site"] = per_site

    # ---------------- S1 / S2
    say("S1 per MS cohort; S2 MS-only and all negatives ...")
    s1 = {}
    for coh in ("M", "L10"):
        ii = np.nonzero((D.sets[coh] & y) | D.sets["C"])[0]
        s1[f"{coh}_true_vs_controls"] = table(D, S, ii, y, [D.sets[coh], D.sets["C"]], ALL_SCORES, seed=SEED + 302)
    rec["S1_per_cohort"] = s1
    idx_ms1 = np.nonzero(D.sets["MS1"])[0]
    s2 = {"ms_only_true_vs_ms_false": table(D, S, idx_ms1, y, strata_1mm(D, False), ALL_SCORES, seed=SEED + 303),
          "true_vs_all_negatives": table(D, S, np.nonzero(D.pool1)[0], y, strata_1mm(D), ALL_SCORES, seed=SEED + 304)}
    rec["S2_1mm"] = s2
    for k_, t in s2.items():
        say(f"  {k_}: " + ", ".join(f"{n} {t[n]['auroc']}" for n in ALL_SCORES))

    # ---------------- S-CAL
    say("S-CAL healthy-calibrated threshold ...")
    rec["S_CAL_healthy_calibrated_threshold"] = scal(D, y)
    for k_, v in rec["S_CAL_healthy_calibrated_threshold"].items():
        say(f"  {k_}: flagged {v['held_out_controls_flagged']}/{v['n_controls']} {v['cp95']} FP/ctl {v['false_per_control_scan']} "
            f"MS-1mm sens {v['ms_1mm_sensitivity']} ext sens {v['external_sensitivity_mean_over_rotations']} ext FP/scan {v['external_false_per_scan_mean']}")

    # ---------------- S-REG
    sreg = {}
    for lab_name, cond in (("PV", region == "PV"), ("non_PV", (region != "PV") & (region != ""))):
        ii = np.nonzero(pos_ms | (D.sets["C"] & cond))[0]
        sreg[lab_name] = table(D, S, ii, y, strata_1mm(D), ("ENS-RAW", "DIS-RAW", "GR-LR", "GR+C-LR"), seed=SEED + 305)
        sreg[lab_name]["_control_candidates"] = int((D.sets["C"] & cond).sum())
    rec["S_REG_paper_a_regions"] = sreg
    say("S-REG: " + "; ".join(f"{k_} (n={v['_control_candidates']}): " + ", ".join(
        f"{n} {v[n]['auroc']}" for n in ("ENS-RAW", "DIS-RAW", "GR-LR", "GR+C-LR")) for k_, v in sreg.items()))

    # ---------------- K2 cohort-identity probe
    say("K2 cohort-identity probe (MS FALSE vs controls) ...")
    ms_false = D.sets["MS1"] & ~y
    k2 = {}
    pairs = {"MSfalse_vs_C": (ms_false, D.sets["C"], strata_1mm(D)),
             "Mfalse_vs_C": (D.sets["M"] & ~y, D.sets["C"], [D.sets["M"], D.sets["C"]]),
             "L10false_vs_C": (D.sets["L10"] & ~y, D.sets["C"], [D.sets["L10"], D.sets["C"]]),
             "Mfalse_vs_L10false_reference": (D.sets["M"] & ~y, D.sets["L10"] & ~y, [D.sets["M"], D.sets["L10"]])}
    probe_gr_with_true = None
    for pn, (ma, mb, st) in pairs.items():
        oof = {}
        for fam in PROBE_FAMILIES:
            extra = pos_ms if (pn == "MSfalse_vs_C" and fam == "GR") else None
            o = probe(D, fam, ma, mb, extra)
            if extra is not None:
                probe_gr_with_true = o
            oof[fam] = o
        ii = np.nonzero(ma | mb)[0]
        k2[pn] = ev.auc_table(D, {f: oof[f][ii] for f in PROBE_FAMILIES}, ii, mb, st, ref="GR", seed=SEED + 361)
        k2[pn]["_foldwise_D1"] = foldwise_table(D, oof, ii, mb, st, list(PROBE_FAMILIES), ref="GR", seed=SEED + 363)
        say(f"  {pn}: pooled " + ", ".join(f"{f} {k2[pn][f]['auroc']}" for f in PROBE_FAMILIES)
            + " | fold-wise (D1) " + ", ".join(f"{f} {k2[pn]['_foldwise_D1'][f]['auroc_foldwise_mean']} "
                                                f"{k2[pn]['_foldwise_D1'][f]['ci95']}" for f in PROBE_FAMILIES))
    rec["K2_cohort_identity_probe"] = k2
    k2_gr = k2["MSfalse_vs_C"]["_foldwise_D1"]["GR"]["auroc_foldwise_mean"]      # D1: decision uses fold-wise

    # ---------------- K3 transfer + K3b cohort-only upper bound
    k3 = {"held_out_1mm_ms": {n: s2["ms_only_true_vs_ms_false"][n] for n in ("ENS-RAW", "GR-LR", "GR+C-LR", "GR-Conly-LR")},
          "external": {n: h4[n] for n in ("ENS-RAW", "GR-LR", "GR-Conly-LR")}}
    tr_ci = s2["ms_only_true_vs_ms_false"]["GR-Conly-LR"]["delta_vs_ENS-RAW_ci95"]
    k3["transfer_delta_vs_ENS_RAW"] = s2["ms_only_true_vs_ms_false"]["GR-Conly-LR"]["delta_vs_ENS-RAW"]
    k3["transfer_ci95"] = tr_ci
    k3["transfer_positive"] = bool(tr_ci[0] is not None and tr_ci[0] > 0)
    S["K3b-cohort-probe"] = -probe_gr_with_true
    k3["K3b_cohort_probe_on_H1_endpoint"] = table(D, S, idx_h1, y, strata_1mm(D), ("ENS-RAW", "GR+C-LR", "K3b-cohort-probe"),
                                                  ref="GR+C-LR", ref2="ENS-RAW", seed=SEED + 362)
    k3["foldwise_D1_held_out_1mm_ms"] = foldwise_table(D, S, idx_ms1, y, strata_1mm(D, False),
                                                       ["ENS-RAW", "GR-LR", "GR+C-LR", "GR-Conly-LR"],
                                                       ref="ENS-RAW", seed=SEED + 364)
    rec["K3_transfer"] = k3
    say(f"K3 fold-wise (D1): " + ", ".join(f"{n} {v['auroc_foldwise_mean']} d {v.get('delta_vs_ENS-RAW')} {v.get('delta_vs_ENS-RAW_ci95')}"
                                           for n, v in k3["foldwise_D1_held_out_1mm_ms"].items()))
    # K10 (D1): H1 endpoint with fold-wise AUROC
    rec["K10_H1_foldwise_D1"] = foldwise_table(D, S, idx_h1, y, strata_1mm(D),
                                               ["ENS-RAW", "DIS-RAW", "GR-LR", "GR+C-LR", "GR-Conly-LR"],
                                               ref="ENS-RAW", seed=SEED + 308)
    say("K10 H1 fold-wise (D1): " + ", ".join(f"{n} {v['auroc_foldwise_mean']} d {v.get('delta_vs_ENS-RAW')} {v.get('delta_vs_ENS-RAW_ci95')}"
                                             for n, v in rec["K10_H1_foldwise_D1"].items()))
    say(f"K3 transfer (GR-Conly-LR - ENS-RAW, held-out 1-mm MS): {k3['transfer_delta_vs_ENS_RAW']} {tr_ci}; "
        f"K3b cohort-probe AUROC on H1 {k3['K3b_cohort_probe_on_H1_endpoint']['K3b-cohort-probe']['auroc']} "
        f"{k3['K3b_cohort_probe_on_H1_endpoint']['K3b-cohort-probe']['ci95']}")

    # ---------------- K5 shuffle null
    say("K5 shuffle-label null ...")
    nul = []
    for r in range(ev.N_SHUFFLE):
        o = crossfit(D, y, "GR+C-LR", perm_seed=SEED + 2000 + 10 * r)
        nul.append(ev.auroc(o[idx_h1], y[idx_h1]))
    rec["K5_shuffle_null"] = {"mean": r_(np.mean(nul)), "min": r_(min(nul)), "max": r_(max(nul)),
                              "flagged": bool(np.mean(nul) > 0.55)}
    say(f"  {rec['K5_shuffle_null']}")

    # ---------------- K7 seeds, K8 blindness, K9 QC
    k7 = {}
    for sd in (SEED + 301, SEED + 3301, SEED + 6301):
        t = table(D, S, idx_h1, y, strata_1mm(D), ("ENS-RAW", "GR-LR", "GR+C-LR"), seed=sd)
        k7[str(sd)] = {"delta": t["GR+C-LR"]["delta_vs_ENS-RAW"], "ci95": t["GR+C-LR"]["delta_vs_ENS-RAW_ci95"]}
    rec["K7_bootstrap_seeds"] = k7
    ctl_case = np.array([str(c) for c in D.case])
    k8 = {}
    for nm, cond in (("august30", np.isin(ctl_case, list(AUGUST))), ("new70", ~np.isin(ctl_case, list(AUGUST)))):
        ii = np.nonzero(pos_ms | (D.sets["C"] & cond))[0]
        k8[nm] = table(D, S, ii, y, strata_1mm(D), ("ENS-RAW", "DIS-RAW", "GR-LR", "GR+C-LR"), seed=SEED + 306)
    rec["K8_blindness_split"] = k8
    say("K8: " + "; ".join(f"{k_}: " + ", ".join(f"{n} {v[n]['auroc']}" for n in ("ENS-RAW", "GR-LR", "GR+C-LR"))
                           for k_, v in k8.items()))
    keep = ~(D.sets["C"] & (ctl_case == QC_FLAG))
    ii = np.nonzero((pos_ms | D.sets["C"]) & keep)[0]
    k9 = {"H1": table(D, S, ii, y, strata_1mm(D), ("ENS-RAW", "GR-LR", "GR+C-LR"), seed=SEED + 307),
          "H3": h3(D, y, S, ("ENS-RAW", "GR-LR", "GR+C-LR"), SEED + 312,
                   ctl_scans=np.array([s for s in D.ctl_scans if str(D.s_case[s]) != QC_FLAG]))}
    rec["K9_without_sub075"] = k9

    # ---------------- decisions (PROTOCOL-v3.2 §8)
    gate_conf = bool(k3["transfer_positive"] or (k2_gr is not None and k2_gr <= 0.70))
    crit["K2_identity_GR_MSfalse_vs_C"] = k2_gr
    crit["K2_controls_no_more_identifiable_than_a_site"] = bool(k2_gr is not None and k2_gr <= 0.70)
    crit["K3_transfer_positive"] = k3["transfer_positive"]
    crit["confound_gate_passed"] = gate_conf
    dis_lo = h1["DIS-RAW"]["ci95"][0]
    sc_ok = {n: all(rec["S_CAL_healthy_calibrated_threshold"][f"{n}|alpha={a_}"]["within_alpha_plus_0.05"] for a_ in (0.1, 0.2))
             for n in ("ENS-RAW", "GR-LR", "GR+C-LR")}
    if crit["primary_met"] and crit["H3_met"] and crit["H4_noninferior"] and gate_conf:
        dec = "learned healthy-aware re-scorer may be PROPOSED as a future dark research feature (SRS/RMF/review needed)"
    elif crit["primary_met"] and not gate_conf:
        dec = "H1 met but confound gate failed: not shippable (cohort recognition); app keeps the v3.1 decision"
    elif crit["primary_met"]:
        dec = "H1 met but H3 and/or H4 not met: no learned model shipped; app keeps the v3.1 decision"
    else:
        dec = "H1 not met: no learned model; app keeps the 5-fold ensemble + fold disagreement (v3.1 decision)"
    rec["decisions"] = {"learned_rescorer": dec,
                        "disagreement_healthy_statement_allowed": bool(dis_lo is not None and dis_lo > 0.5),
                        "S_CAL_describable": sc_ok, "lstai": "never a decision input (site leak); reported only"}
    rec["criteria"] = crit
    say(f"criteria: {json.dumps(crit)}")
    say(f"decisions: {json.dumps(rec['decisions'])}")

    # ---------------- save out-of-fold scores (gitignored) + record
    os.makedirs(os.path.dirname(OOF_OUT), exist_ok=True)
    np.savez_compressed(OOF_OUT, names=np.array(list(S) + [f"EXT:{n}" for n in S_ext]),
                        **{f"s{i}": v for i, v in enumerate(list(S.values()) + list(S_ext.values()))},
                        fold=D.fold, y=y, idx_h1=idx_h1)
    rec["oof_scores"] = {"path": os.path.relpath(OOF_OUT, ev.ROOT), "sha256": sha(OOF_OUT)}
    rec["runtime_s"] = round(time.time() - t0, 1)
    os.makedirs(a.records_dir, exist_ok=True)
    out = os.path.join(a.records_dir, f"{a.tag}_lesion_detector_v32_evaluation.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1)
    with open(out.replace(".json", "_output.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(log) + "\n")
    say(f"wrote {out} in {rec['runtime_s']} s")


if __name__ == "__main__":
    main()
