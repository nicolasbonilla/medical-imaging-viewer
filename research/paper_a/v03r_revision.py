#!/usr/bin/env python3
"""Paper A revision (2026-10-31) — analyses requested by the independent review (major revision).

POST HOC: written after every v0.3, addendum and manuscript-stage result had been seen, and after the
review. Logged as PROTOCOL-v0.3 §13 entry 11 before this script was run. Local CPU only; reads the
frozen per-candidate cache (SHA-256 2096109e…) and the committed control record; nothing else.
Every value is stored at full precision (no rounding); the manuscript rounds once, at printing.

  R1  every primary cell (ensemble; D3, D2; P1 α 0.1/0.2; P2 γ 0.1/0.2):
        realised FDR / FDX (empty selection counted as FDP = 0, as pre-registered), share of scans
        selecting, FDR among selecting scans, micro-FDR, share of scans with FDP > 0.1 / > 0.2,
        patient-cluster bootstrap intervals and one-sided 95 % upper bounds (calibration fixed),
        a small-sample-valid one-sided 95 % bound (Hoeffding–Bentkus over patients),
        a two-level bootstrap (calibration and test patients resampled; 1000 resamples) with its
        one-sided bound and Monte Carlo error, α·mean per-scan π0 of the test scans.
  R2  the same per-cell quantities for every procedure under D3 (P1, P2, B1, B2, B3).
  R3  the D3 / D1 FDR ratio (MS3SEG, Muslim; α 0.1, 0.2): patient-paired bootstrap interval, and
      its sensitivity to the within-site fold assignment (20 further fold seeds).
  R4  simulation: conformal BH with a scan-level random effect (ICC 0–0.2) and a shift of the
      false-candidate scores, with the empirical candidate counts of the cohorts.
  R5  Monte Carlo precision: D5 key cells and SUB with 2000 draws (mean, SD, MC SE).
  R6  candidate AUROC on the SAME candidates: ensemble mean vs each fold's mean over the ensemble
      candidate (paired, patient-cluster bootstrap).
  R7  validity–power frontier under D3: α ∈ {0.05, …, 0.3} for P1, B1, B2, B3 and SUB.
  R8  controls: median volume of periventricular false candidates; P2 premise on controls.

    python research/paper_a/v03r_revision.py
"""
import json
import math
import os
import pickle
import sys
import time

import numpy as np
from scipy.stats import binom, norm

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import baselines as BL                                     # noqa: E402
import v03_analysis as A                                   # noqa: E402
import v03_metrics as M                                    # noqa: E402
from v03_candidates import CACHE, sha256                   # noqa: E402
from v03_data import RECORDS, SITES, THICK_SITES           # noqa: E402

OUT = os.path.join(RECORDS, "2026-10-31_paper_a_revision.json")
CTL = os.path.join(RECORDS, "2026-10-24_paper_a_v03c_controls.json")
SEED = 20261101
EXPECTED_CACHE = "2096109e4da247aeaf03db43f4f5be02a14f95a450f711bb349e4942b9a6f4ec"
N_BOOT = 2000
N_TWO = 1000
PRIMARY = (("P1", 0.1), ("P1", 0.2), ("P2", 0.1), ("P2", 0.2))
PROCS_D3 = PRIMARY + (("B1", 0.1), ("B1", 0.2), ("B2", 0.1), ("B2", 0.2), ("B3", 0.1), ("B3", 0.2))


def f(x):
    return None if x is None else float(x)


# ------------------------------------------------------------------ bounds
def hb_pvalue(mean, n, mu):
    """Hoeffding–Bentkus p-value for H0: E[X] >= mu, X in [0, 1], n i.i.d. units (Bates et al. 2021)."""
    if mu <= mean:
        return 1.0
    if mu >= 1:
        return 0.0
    a = mean
    h = (a * math.log(a / mu) if a > 0 else 0.0) + (1 - a) * math.log((1 - a) / (1 - mu))
    return min(math.exp(-n * h), math.e * binom.cdf(math.ceil(n * mean - 1e-12), n, mu))


def hb_ucb(values, delta=0.05):
    """One-sided (1 − δ) upper confidence bound for the mean of i.i.d. [0, 1] values."""
    v = np.asarray(values, float)
    n, m = v.size, float(v.mean())
    lo, hi = m, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if hb_pvalue(m, n, mid) <= delta:
            hi = mid
        else:
            lo = mid
    return hi


def boot_ratio(num, den, W, q=(0.025, 0.975, 0.95)):
    r = (W @ num) / np.maximum(W @ den, 1e-12)
    return [float(np.quantile(r, x)) for x in q]


# ------------------------------------------------------------------ R1 / R2 per-cell quantities
def scan_fdp(t, sel):
    s = sel[t["case"]]
    ns = int(s.sum())
    return (float((s & t["isf"]).sum() / ns) if ns else 0.0), ns


def cell_quantities(test, sel, proc, target):
    pats, T = A.patient_table(test, sel)
    W = A.weights(pats, N_BOOT)
    n = T["n_scans"].sum()
    nominal = target if proc in ("P1", "B1", "B2", "B3") else 0.1
    # patient-level means in [0, 1] for the small-sample bound
    fdp_p = T["sum_fdp"] / T["n_scans"]
    exc_key = f"exc_{target}" if proc == "P2" else "exc_0.1"
    exc_p = T[exc_key] / T["n_scans"]
    est_fdr = float(T["sum_fdp"].sum() / n)
    est_exc = float(T[exc_key].sum() / n)
    out = {
        "scans": int(n), "patients": len(pats), "nominal": nominal,
        "realised_fdr": est_fdr, "realised_fdr_ci95": boot_ratio(T["sum_fdp"], T["n_scans"], W)[:2],
        "realised_fdr_ucb95_boot": boot_ratio(T["sum_fdp"], T["n_scans"], W)[2],
        "realised_fdr_ucb95_hb_patients": hb_ucb(fdp_p),
        "share_scans_selecting": float(T["any_sel"].sum() / n),
        "scans_selecting": int(T["any_sel"].sum()),
        "fdr_among_selecting": float(T["sum_fdp"].sum() / T["any_sel"].sum()) if T["any_sel"].sum() else None,
        "fdr_among_selecting_ci95": boot_ratio(T["sum_fdp"], T["any_sel"], W)[:2] if T["any_sel"].sum() else None,
        "micro_fdr": float(T["nf"].sum() / T["ns"].sum()) if T["ns"].sum() else None,
        "n_sel": int(T["ns"].sum()),
        "share_fdp_gt_0.1": float(T["exc_0.1"].sum() / n), "share_fdp_gt_0.1_ci95": boot_ratio(T["exc_0.1"], T["n_scans"], W)[:2],
        "share_fdp_gt_0.2": float(T["exc_0.2"].sum() / n),
        "sens_e2e": float(T["hits"].sum() / T["n_gt"].sum()) if T["n_gt"].sum() else None,
        "exceedance_estimate": est_exc, "exceedance_ucb95_boot": boot_ratio(T[exc_key], T["n_scans"], W)[2],
        "exceedance_ucb95_hb_patients": hb_ucb(exc_p),
        "exceedance_ucb95_cp_scans": float(M.clopper_pearson(int(T[exc_key].sum()), int(n), conf=0.90)[1]),
        "alpha_times_mean_scan_pi0": float(nominal * np.mean([t["isf"].mean() if t["isf"].size else 0.0 for t in test]))
        if proc != "P2" else None,
        "bootstrap_degenerate": bool(boot_ratio(T["sum_fdp"], T["n_scans"], W)[0] == boot_ratio(T["sum_fdp"], T["n_scans"], W)[1]),
    }
    out["low_power_flag_revised"] = bool(out["share_scans_selecting"] < 0.5 or (out["sens_e2e"] or 0) < 0.10)
    return out


def two_level_values(cal, test, proc, target, n_boot, seed):
    rng = np.random.RandomState(seed)
    cal_by = {}
    for s in cal:
        cal_by.setdefault(s["site"], {}).setdefault(s["patient"], []).append(s)
    for d in cal_by.values():
        for p in d:
            d[p].sort(key=lambda s: s["case"])
    pats_t = sorted({t["patient"] for t in test})
    vals = []
    for _ in range(n_boot):
        rc, rf = [], []
        for site, d in cal_by.items():
            ps = sorted(d)
            for i in rng.randint(0, len(ps), len(ps)):
                rc.extend(d[ps[i]])
                rf.append(d[ps[i]][0])
        if proc == "P1":
            sel, _ = A.select(rc, test, "P1", target)
        else:
            lam = M.fdx_threshold([A.safe(s, target) for s in rf], 0.1)
            sel = {t["case"]: t["scores"] >= lam for t in test}
        pats, T = A.patient_table(test, sel)
        w = np.bincount(rng.randint(0, len(pats_t), len(pats_t)), minlength=len(pats_t)).astype(float)
        num = T["sum_fdp"] if proc == "P1" else T[f"exc_{target}"]
        vals.append(float(w @ num / (w @ T["n_scans"])))
    v = np.asarray(vals)
    # Monte Carlo error of the mean and of the 95th percentile (bootstrap of the resamples)
    rr = np.random.RandomState(seed + 1)
    q95 = [np.quantile(v[rr.randint(0, v.size, v.size)], 0.95) for _ in range(500)]
    return {"n": int(v.size), "mean": float(v.mean()), "mc_se_mean": float(v.std(ddof=1) / math.sqrt(v.size)),
            "ci95": [float(np.quantile(v, 0.025)), float(np.quantile(v, 0.975))], "ucb95": float(np.quantile(v, 0.95)),
            "mc_se_ucb95": float(np.std(q95, ddof=1))}


# ------------------------------------------------------------------ R3 ratio
def per_patient_fdp(test, sel):
    pats, T = A.patient_table(test, sel)
    return pats, T["sum_fdp"], T["n_scans"]


def d1_selection(scans, site, proc, target, fold_seed):
    ss = [s for s in scans if s["site"] == site]
    pats = sorted({s["patient"] for s in ss})
    sel = {}
    for fold in A._folds(pats, 5, fold_seed):
        cal = [s for s in ss if s["patient"] not in fold]
        test = [s for s in ss if s["patient"] in fold]
        s_, _ = A.select(cal, test, proc, target)
        sel.update(s_)
    return sel


def ratio_analysis(ens):
    out = {}
    d3 = {}
    for site, cal, test in A.splits(ens, "D3"):
        d3[site] = (cal, test)
    for site in ("ms3seg", "muslim"):
        cal, test = d3[site]
        si = SITES.index(site)
        for a in (0.1, 0.2):
            sel3, _ = A.select(cal, test, "P1", a)
            pre_seed = A.SEED + 100 * si
            sel1 = d1_selection(ens, site, "P1", a, pre_seed)
            p3, x3, n3 = per_patient_fdp(test, sel3)
            p1, x1, n1 = per_patient_fdp(test, sel1)
            assert p3 == p1
            W = A.weights(p3, N_BOOT)
            r = (W @ x3) / np.maximum(W @ x1, 1e-12)
            est3, est1 = float(x3.sum() / n3.sum()), float(x1.sum() / n1.sum())
            seeds = {}
            for j in range(1, 21):
                s1 = d1_selection(ens, site, "P1", a, SEED + 7000 + 31 * j + si)
                _, y, ny = per_patient_fdp(test, s1)
                seeds[j] = float(y.sum() / ny.sum())
            d1v = np.array(list(seeds.values()))
            out[f"{site}|{a}"] = {"d3_fdr": est3, "d1_fdr_preregistered_split": est1, "ratio": est3 / est1,
                                  "ratio_ci95_paired_bootstrap": [float(np.quantile(r, 0.025)), float(np.quantile(r, 0.975))],
                                  "d1_fdr_other_splits": {"n": int(d1v.size), "min": float(d1v.min()), "median": float(np.median(d1v)),
                                                          "max": float(d1v.max())},
                                  "ratio_other_splits": {"min": float(est3 / d1v.max()), "median": float(est3 / np.median(d1v)),
                                                         "max": float(est3 / d1v.min())}}
            print(f"R3 {site} a={a}: ratio {out[f'{site}|{a}']['ratio']:.3f} CI {out[f'{site}|{a}']['ratio_ci95_paired_bootstrap']}"
                  f" D1 splits {d1v.min():.4f}-{d1v.max():.4f}", flush=True)
    return out


# ------------------------------------------------------------------ R4 simulation
def bh_select(p, alpha):
    m = p.size
    if m == 0:
        return np.zeros(0, bool)
    order = np.argsort(p, kind="mergesort")
    ok = np.nonzero(p[order] <= alpha * np.arange(1, m + 1) / m)[0]
    if ok.size == 0:
        return np.zeros(m, bool)
    return p <= p[order][ok.max()]


def simulate(cal_counts, test_counts, rho, shift, reps, rng, mu):
    res = {a: {"fdr": [], "pi0": [], "exc": [], "fdr_sel": []} for a in (0.1, 0.2)}
    sd_e = math.sqrt(1 - rho)
    sd_b = math.sqrt(rho)
    for _ in range(reps):
        null = []
        for nf, nt in cal_counts:
            b = rng.normal(0, sd_b)
            null.append(b + sd_e * rng.normal(size=nf))
        null = np.sort(np.concatenate(null))
        n = null.size
        tests = []
        for nf, nt in test_counts:
            b = rng.normal(0, sd_b)
            fs = b + shift + sd_e * rng.normal(size=nf)
            ts = mu + b + sd_e * rng.normal(size=nt)
            tests.append((np.r_[fs, ts], np.r_[np.ones(nf, bool), np.zeros(nt, bool)]))
        for a in (0.1, 0.2):
            fdps, sel_any, pi0s = [], [], []
            for s, isf in tests:
                p = (1.0 + n - np.searchsorted(null, s, side="left")) / (n + 1.0)
                sel = bh_select(p, a)
                k = int(sel.sum())
                fdps.append((sel & isf).sum() / k if k else 0.0)
                sel_any.append(k > 0)
                pi0s.append(isf.mean() if isf.size else 0.0)
            fdps = np.asarray(fdps)
            sel_any = np.asarray(sel_any)
            res[a]["fdr"].append(fdps.mean())
            res[a]["pi0"].append(a * np.mean(pi0s))
            res[a]["exc"].append((fdps > 0.1).mean())
            res[a]["fdr_sel"].append(fdps[sel_any].mean() if sel_any.any() else 0.0)
    out = {}
    for a, d in res.items():
        out[str(a)] = {k: {"mean": float(np.mean(v)), "mc_se": float(np.std(v, ddof=1) / math.sqrt(len(v)))} for k, v in d.items()}
    return out


def simulation(ens):
    cal_counts = [(int(s["isf"].sum()), int((~s["isf"]).sum())) for s in ens if s["site"] in ("mslesseg", "openms")]
    test_counts = [(int(s["isf"].sum()), int((~s["isf"]).sum())) for s in ens if s["site"] == "ms3seg"]
    mu = math.sqrt(2) * norm.ppf(0.80)
    rng = np.random.RandomState(SEED + 4)
    out = {"design": "calibration = candidate counts (false, true) of the 125 1-mm-grid scans; test = counts of the 100 "
                     "MS3SEG scans; latent scores: false = b + e, true = mu + b + e, b ~ N(0, rho), e ~ N(0, 1 - rho), "
                     "mu = sqrt(2)·Phi^-1(0.80) (pooled AUROC ≈ 0.80); 'shift' is added to the TEST false scores only.",
           "mu": mu, "reps": 400, "scenarios": {}}
    for rho in (0.0, 0.03, 0.10, 0.20):
        for shift in (0.0, 0.15, 0.30):
            out["scenarios"][f"rho={rho}|shift={shift}"] = simulate(cal_counts, test_counts, rho, shift, 400, rng, mu)
            s = out["scenarios"][f"rho={rho}|shift={shift}"]["0.1"]
            print(f"R4 rho={rho} shift={shift}: FDR {s['fdr']['mean']:.4f} (alpha*pi0 {s['pi0']['mean']:.4f}) "
                  f"exc {s['exc']['mean']:.3f} fdr_sel {s['fdr_sel']['mean']:.3f}", flush=True)
    return out


# ------------------------------------------------------------------ R5 Monte Carlo precision
def d5_mc(ens, site, reps):
    rng = np.random.RandomState(SEED + 31 + SITES.index(site))
    tgt = [s for s in ens if s["site"] == site]
    pool1mm = [s for s in ens if s["site"] in ("mslesseg", "openms")]
    pats = sorted({s["patient"] for s in tgt})
    out = {}
    for mode in ("site_only", "augmented"):
        for k in (3, 10, 40):
            acc = {p: {"v": [], "sens": []} for p in (("P1", 0.1), ("P1", 0.2), ("P2", 0.1))}
            for _ in range(reps):
                pick = set(rng.choice(pats, k, replace=False))
                cal = [s for s in tgt if s["patient"] in pick] + (pool1mm if mode == "augmented" else [])
                test = [s for s in tgt if s["patient"] not in pick]
                for p in acc:
                    sel, _ = A.select(cal, test, *p)
                    _, T = A.patient_table(test, sel)
                    n = T["n_scans"].sum()
                    acc[p]["v"].append((T["sum_fdp"].sum() if p[0] == "P1" else T[f"exc_{p[1]}"].sum()) / n)
                    acc[p]["sens"].append(T["hits"].sum() / max(T["n_gt"].sum(), 1))
            for p, d in acc.items():
                v, s = np.asarray(d["v"]), np.asarray(d["sens"])
                nominal = p[1] if p[0] == "P1" else 0.1
                out[f"{mode}|{p[0]}|{p[1]}|k={k}"] = {
                    "draws": reps, "realised_mean": float(v.mean()), "realised_sd": float(v.std(ddof=1)),
                    "realised_mc_se": float(v.std(ddof=1) / math.sqrt(reps)),
                    "share_draws_above_nominal": float((v > nominal + 1e-12).mean()),
                    "sens_mean": float(s.mean()), "sens_sd": float(s.std(ddof=1)), "sens_mc_se": float(s.std(ddof=1) / math.sqrt(reps)),
                    "mc_se_if_200_draws": {"realised": float(v.std(ddof=1) / math.sqrt(200)), "sens": float(s.std(ddof=1) / math.sqrt(200))}}
        print(f"R5 D5 {site} {mode} done", flush=True)
    return out


def sub_mc(ens, reps):
    out = {}
    for site, cal, test in A.splits(ens, "D3"):
        fs = A.first_scans(cal)
        for a in (0.1, 0.2):
            rng = np.random.RandomState(SEED + 13 * SITES.index(site) + int(100 * a))
            v, s = [], []
            for _ in range(reps):
                sels = BL.subsampled_bh(fs, test, a, rng)
                sel = {t["case"]: x for t, x in zip(test, sels)}
                _, T = A.patient_table(test, sel)
                v.append(T["sum_fdp"].sum() / T["n_scans"].sum())
                s.append(T["hits"].sum() / T["n_gt"].sum())
            v, s = np.asarray(v), np.asarray(s)
            out[f"{site}|{a}"] = {"draws": reps, "realised_mean": float(v.mean()), "realised_mc_se": float(v.std(ddof=1) / math.sqrt(reps)),
                                  "q025_q975": [float(np.quantile(v, 0.025)), float(np.quantile(v, 0.975))],
                                  "share_draws_above_alpha": float((v > a + 1e-12).mean()),
                                  "sens_mean": float(s.mean()), "sens_mc_se": float(s.std(ddof=1) / math.sqrt(reps)),
                                  "mc_se_if_200_draws": float(v.std(ddof=1) / math.sqrt(200))}
    print("R5 SUB done", flush=True)
    return out


# ------------------------------------------------------------------ R6 paired AUROC on the same candidates
def paired_auroc(ens, cache):
    fold_means = {r["case"]: np.asarray(r["arms"]["ens"]["fold_means"], float).reshape(-1, 5)
                  for r in cache["cases"] if "ens" in r["arms"]}
    out = {}
    for site in SITES:
        ss = [s for s in ens if s["site"] == site]
        pats = sorted({s["patient"] for s in ss})
        per = {p: [] for p in pats}
        for s in ss:
            assert fold_means[s["case"]].shape[0] == s["scores"].size
            per[s["patient"]].append(s)
        rng = np.random.RandomState(SEED + 61 + SITES.index(site))

        def aucs(pick):
            sc = np.concatenate([x["scores"] for p in pick for x in per[p]])
            fm = np.concatenate([fold_means[x["case"]] for p in pick for x in per[p]])
            y = np.concatenate([~x["isf"] for p in pick for x in per[p]])
            return [M.auroc(sc, y)] + [M.auroc(fm[:, k], y) for k in range(5)]
        point = aucs(pats)
        diffs = []
        for _ in range(N_BOOT):
            pick = [pats[i] for i in rng.randint(0, len(pats), len(pats))]
            v = aucs(pick)
            if None not in v:
                diffs.append([v[0] - v[k] for k in range(1, 6)])
        diffs = np.asarray(diffs)
        out[site] = {"auroc_ensemble_mean": point[0], "auroc_fold_mean_on_ensemble_candidates": point[1:],
                     "diff_ens_minus_fold0": point[0] - point[1],
                     "diff_ens_minus_fold0_ci95": [float(np.quantile(diffs[:, 0], 0.025)), float(np.quantile(diffs[:, 0], 0.975))],
                     "diff_ens_minus_best_fold": point[0] - max(point[1:])}
    print("R6 done", flush=True)
    return out


# ------------------------------------------------------------------ R7 frontier
def frontier(ens, sub_reps):
    grid = (0.05, 0.1, 0.15, 0.2, 0.25, 0.3)
    out = {}
    for site, cal, test in A.splits(ens, "D3"):
        pats = sorted({t["patient"] for t in test})
        W = A.weights(pats, N_BOOT)
        for proc in ("P1", "B1", "B2", "B3", "SUB"):
            for a in grid:
                if proc == "SUB":
                    fs = A.first_scans(cal)
                    rng = np.random.RandomState(SEED + 97 + int(1000 * a) + SITES.index(site))
                    acc_s = acc_h = None
                    for _ in range(sub_reps):
                        sels = BL.subsampled_bh(fs, test, a, rng)
                        sel = {t["case"]: x for t, x in zip(test, sels)}
                        _, T = A.patient_table(test, sel)
                        acc_s = T["sum_fdp"] if acc_s is None else acc_s + T["sum_fdp"]
                        acc_h = T["hits"] if acc_h is None else acc_h + T["hits"]
                    sf, hh = acc_s / sub_reps, acc_h / sub_reps
                    _, T = A.patient_table(test, {t["case"]: np.zeros(t["scores"].size, bool) for t in test})
                else:
                    sel, _ = A.select(cal, test, proc, a)
                    _, T = A.patient_table(test, sel)
                    sf, hh = T["sum_fdp"], T["hits"]
                out[f"{site}|{proc}|{a}"] = {"realised_fdr": float(sf.sum() / T["n_scans"].sum()),
                                             "realised_fdr_ci95": boot_ratio(sf, T["n_scans"], W)[:2],
                                             "sens_e2e": float(hh.sum() / T["n_gt"].sum()),
                                             "sens_e2e_ci95": boot_ratio(hh, T["n_gt"], W)[:2]}
        # FDR at matched sensitivity (linear interpolation along the alpha grid)
        for proc in ("P1", "B1", "B2", "B3", "SUB"):
            xs = [out[f"{site}|{proc}|{a}"]["sens_e2e"] for a in grid]
            ys = [out[f"{site}|{proc}|{a}"]["realised_fdr"] for a in grid]
            for target in (0.2, 0.3):
                val = None
                for i in range(len(grid) - 1):
                    if min(xs[i], xs[i + 1]) <= target <= max(xs[i], xs[i + 1]) and xs[i + 1] != xs[i]:
                        val = ys[i] + (ys[i + 1] - ys[i]) * (target - xs[i]) / (xs[i + 1] - xs[i])
                        break
                out[f"{site}|{proc}|fdr_at_sens_{target}"] = val
    print("R7 done", flush=True)
    return out


# ------------------------------------------------------------------ R8 controls
def controls_extra():
    C = json.load(open(CTL, encoding="utf-8"))
    rows = C["location_rows_ens"]
    pv = [r["vol_mm3"] for r in rows if r["region"] == "PV"]
    return {"candidates": len(rows), "median_volume_all_mm3": float(np.median([r["vol_mm3"] for r in rows])),
            "pv_candidates": len(pv), "median_volume_pv_mm3": float(np.median(pv)),
            "p2_premise": "on a lesion-free scan every candidate is false, so the scan's safe threshold always lies above its "
                          "top candidate; in patients this holds only for a share of scans (see posthoc fullprec)"}


def main():
    t0 = time.time()
    h = sha256(CACHE)
    assert h == EXPECTED_CACHE, h
    cache = pickle.load(open(CACHE, "rb"))
    ens = A.build(cache, "ens")
    rec = {"status": "POST HOC (revision after the independent review, 2026-10-31); PROTOCOL-v0.3 §13 entry 11; not pre-registered",
           "cache_sha256": h, "seed": SEED, "n_boot": N_BOOT, "n_two_level": N_TWO, "precision": "full (unrounded)"}
    # R1 + R2
    cells = {}
    for design in ("D3", "D2"):
        for site, cal, test in A.splits(ens, design):
            procs = PROCS_D3 if design == "D3" else PRIMARY
            for proc, tgt in procs:
                sel, lam = A.select(cal, test, proc, tgt)
                q = cell_quantities(test, sel, proc, tgt)
                q["threshold"] = None if lam is None or not np.isfinite(lam) else float(lam)
                if (proc, tgt) in PRIMARY:
                    q["two_level"] = two_level_values(cal, test, proc, tgt, N_TWO,
                                                      SEED + 1000 * SITES.index(site) + 10 * PRIMARY.index((proc, tgt)) + (0 if design == "D3" else 5))
                cells[f"{design}|{site}|{proc}|{tgt}"] = q
            print(f"R1 {design} {site} done ({time.time() - t0:.0f} s)", flush=True)
    rec["cells"] = cells
    rec["ratio_d3_over_d1"] = ratio_analysis(ens)
    rec["simulation"] = simulation(ens)
    rec["d5_mc"] = {site: d5_mc(ens, site, 2000) for site in ("ms3seg", "muslim")}
    rec["sub_mc"] = sub_mc(ens, 2000)
    rec["paired_auroc"] = paired_auroc(ens, cache)
    rec["frontier_d3"] = frontier(ens, 200)
    rec["controls"] = controls_extra()
    rec["runtime_s"] = round(time.time() - t0, 1)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(rec, fh, indent=1)
    print("wrote", OUT, f"in {rec['runtime_s']} s")


if __name__ == "__main__":
    main()
