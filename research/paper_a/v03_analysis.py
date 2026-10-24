#!/usr/bin/env python3
"""Paper A v0.3 — multi-site, multi-thickness audit of conformal lesion-level false-discovery
control on FLAMeS (PROTOCOL-v0.3, commits 9951494 + c0c5fa1). CPU only; reads the candidate cache
written by v03_candidates.py.

Sections (protocol numbering):
  primary   D3 (1-mm -> thick) and D2 (leave-one-site-out) cells of P1 (conformal BH, alpha 0.1/0.2)
            and P2 (scan-conformal FDX threshold, gamma 0.1/0.2, delta 0.1), ensemble arm
  designs   D1, D2, D3, D3r, D4 for every arm x procedure (P1, P2, B1-B3), per site
  thickness bands B1-B4 under D2 / D4; lesion-size bins and minimum reliably detected size
  q3        ensemble vs fold 0 (paired), folds 1-4, per-site AUROC of every score
  q4        D5 recalibration curve (k target patients, site-only / augmented)
  controls  30 healthy controls, fold-0 arm, patient-calibrated
  mechanism false-score laws, ICC, scan-clustered permutation KS (thick vs 1-mm)
  lstai     exploratory: LST-AI within-segmenter, ensemble vs m1, segmenter shift
  sensitivity strict matching, consensus score, PediMS without P9, two-level bootstrap

    python research/paper_a/v03_analysis.py
"""
import json
import os
import pickle
import sys
import time
import zlib

import numpy as np
from scipy.stats import ks_2samp

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import v03_metrics as M                                                     # noqa: E402
from v03_candidates import CACHE, sha256                                    # noqa: E402
from v03_data import ONE_MM_SITES, RECORDS, SITE_INFO, SITES, THICK_SITES  # noqa: E402

SEED = 20261021
N_BOOT, N_BOOT_BONF, N_BOOT2 = 2000, 20000, 500
ALPHAS = (0.1, 0.2, 0.3)
GAMMAS = (0.1, 0.2)
DELTA = 0.1
MARGIN = 0.05
N_PRIMARY = 32
PROCS = [("P1", 0.1), ("P1", 0.2), ("P1", 0.3), ("P2", 0.1), ("P2", 0.2),
         ("B1", 0.1), ("B1", 0.2), ("B2", 0.1), ("B2", 0.2), ("B3", 0.1), ("B3", 0.2)]
P_ONLY = [p for p in PROCS if p[0] in ("P1", "P2")]
BANDS = [("B1", 0.0, 1.5), ("B2", 1.5, 4.5), ("B3", 4.5, 6.5), ("B4", 6.5, np.inf)]
SIZE_EDGES = [3.0, 14.14, 50.0, 150.0, 500.0, np.inf]
OUT_JSON = os.path.join(RECORDS, "2026-10-21_paper_a_v03_results.json")
LOG = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.append(s)


def band_of(z):
    for name, lo, hi in BANDS:
        if lo < z <= hi or (lo == 0.0 and z <= hi):
            return name
    raise ValueError(z)


def rnd(x, k=4):
    if x is None:
        return None
    if isinstance(x, (list, tuple)):
        return [rnd(v, k) for v in x]
    return round(float(x), k)


# ------------------------------------------------------------------ data
def build(cache, arm, score="mean", label="mg0", sites=SITES, flames_only=True, vol_scale=None):
    out = []
    for r in cache["cases"]:
        if r["cohort"] not in sites or (flames_only and not r["flames_clean"]) or arm not in r["arms"]:
            continue
        a = r["arms"][arm]
        if score == "mean":
            sc = np.asarray(a["score"], float)
        elif score == "cons":
            sc = a["fold_means"].min(1) if a["n"] else np.zeros(0)
        elif score == "negsd":
            sc = -a["fold_means"].std(1) if a["n"] else np.zeros(0)
        else:
            raise ValueError(score)
        mg = np.asarray(a[label], int)
        gv = np.asarray(r["gt_vol_mm3"], float)
        if vol_scale and r["cohort"] in vol_scale:
            gv = gv * vol_scale[r["cohort"]]
        out.append({"case": r["case"], "site": r["cohort"], "patient": r["patient"], "slice_mm": r["slice_mm"],
                    "band": band_of(r["slice_mm"]), "scores": sc, "isf": mg == 0, "mg": mg,
                    "gt_ids": np.asarray(r["gt_ids"], int), "gt_vol": gv, "_safe": {}})
    return out


def first_scans(scans):
    by = {}
    for s in sorted(scans, key=lambda x: x["case"]):
        by.setdefault(s["patient"], s)
    return list(by.values())


def safe(s, gamma):
    if gamma not in s["_safe"]:
        s["_safe"][gamma] = M.safe_threshold(s["scores"], s["isf"], gamma)
    return s["_safe"][gamma]


def null_of(cal):
    xs = [s["scores"][s["isf"]] for s in cal]
    return np.concatenate(xs) if xs else np.zeros(0)


def select(cal, test, proc, target):
    """Returns ({case: selection}, threshold or None)."""
    if proc == "P1":
        null = null_of(cal)
        sels = M.conformal_bh([t["scores"] for t in test], null, target)
        return {t["case"]: s for t, s in zip(test, sels)}, None
    fs = first_scans(cal)
    if proc == "P2":
        lam = M.fdx_threshold([safe(s, target) for s in fs], DELTA)
    elif proc == "B1":
        lam = M.naive_threshold(np.concatenate([s["scores"] for s in cal]), np.concatenate([s["isf"] for s in cal]), target)
    elif proc == "B2":
        lam = M.crc_threshold([(s["scores"], s["isf"]) for s in fs], target)
    elif proc == "B3":
        lam = M.ltt_threshold([(s["scores"], s["isf"]) for s in fs], target, 0.1)
    else:
        raise ValueError(proc)
    return {t["case"]: t["scores"] >= lam for t in test}, lam


# ------------------------------------------------------------------ designs
def _folds(patients, k, seed):
    perm = np.random.RandomState(seed).permutation(len(patients))
    return [set(patients[i] for i in perm[f::k]) for f in range(k)]


def splits(scans, design):
    by = {}
    for s in scans:
        by.setdefault(s["site"], []).append(s)
    sites = [x for x in SITES if x in by]
    if design == "D1":
        for si, site in enumerate(sites):
            pats = sorted({s["patient"] for s in by[site]})
            folds = [{p} for p in pats] if site in ("openms", "pedims") and len(pats) <= 10 else _folds(pats, 5, SEED + 100 * si)
            for f in folds:
                yield site, [s for s in by[site] if s["patient"] not in f], [s for s in by[site] if s["patient"] in f]
    elif design == "D2":
        for site in sites:
            yield site, [s for x in sites if x != site for s in by[x]], by[site]
    elif design == "D3":
        cal = [s for x in ONE_MM_SITES if x in by for s in by[x]]
        for site in THICK_SITES:
            if site in by:
                yield site, cal, by[site]
    elif design == "D3r":
        cal = [s for x in THICK_SITES if x in by for s in by[x]]
        for site in ONE_MM_SITES:
            if site in by:
                yield site, cal, by[site]
    elif design == "D4":
        fold_of = {}
        for si, site in enumerate(sites):
            pats = sorted({s["patient"] for s in by[site]})
            for f, fs in enumerate(_folds(pats, 5, SEED + 1000 + 100 * si)):
                for p in fs:
                    fold_of[p] = f
        for f in range(5):
            yield "all", [s for s in scans if fold_of[s["patient"]] != f], [s for s in scans if fold_of[s["patient"]] == f]
    else:
        raise ValueError(design)


def run_design(scans, design, procs=PROCS):
    sels = {p: {} for p in procs}
    lams = {f"{p[0]}|{p[1]}": [] for p in procs}
    for site, cal, test in splits(scans, design):
        for p in procs:
            s, lam = select(cal, test, *p)
            sels[p].update(s)
            if lam is not None:
                lams[f"{p[0]}|{p[1]}"].append({"test": site, "threshold": None if not np.isfinite(lam) else rnd(lam)})
    return sels, lams


# ------------------------------------------------------------------ summaries
_W = {}


def weights(pats, n_boot=N_BOOT):
    key = (tuple(pats), n_boot)
    if key not in _W:
        seed = (SEED + zlib.crc32("|".join(pats).encode()) + n_boot) % (2 ** 31)
        _W[key] = M.bootstrap_weights(len(pats), n_boot, np.random.RandomState(seed))
    return _W[key]


FIELDS = ("n_scans", "sum_fdp", "ns", "nf", "hits", "n_gt", "det", "hits_clin", "n_clin", "any_sel",
          "exc_0.1", "exc_0.2", "exc_0.3")


def patient_table(test, sel):
    pats = sorted({t["patient"] for t in test})
    idx = {p: i for i, p in enumerate(pats)}
    A = {f: np.zeros(len(pats)) for f in FIELDS}
    for t in test:
        r = M.scan_row(sel[t["case"]], t["isf"], t["mg"], t["gt_ids"], t["gt_vol"])
        i = idx[t["patient"]]
        A["n_scans"][i] += 1
        A["sum_fdp"][i] += r["fdp"]
        for f in ("ns", "nf", "hits", "n_gt", "det", "hits_clin", "n_clin"):
            A[f][i] += r[f]
        A["any_sel"][i] += r["ns"] > 0
        for g in (0.1, 0.2, 0.3):
            A[f"exc_{g}"][i] += r["fdp"] > g
    return pats, A


def summarize(test, sel, n_boot=N_BOOT):
    pats, A = patient_table(test, sel)
    W = weights(pats, n_boot)
    S = lambda f: float(A[f].sum())                                    # noqa: E731
    n = S("n_scans")
    out = {"scans": int(n), "patients": len(pats), "n_sel": int(S("ns")), "n_false_sel": int(S("nf")),
           "mean_fdp": rnd(S("sum_fdp") / n), "mean_fdp_ci": rnd(M.ratio_ci(A["sum_fdp"], A["n_scans"], W)),
           "micro_fdr": rnd(S("nf") / S("ns")) if S("ns") else None,
           "micro_fdr_ci": rnd(M.ratio_ci(A["nf"], A["ns"], W)) if S("ns") else None,
           "sens_e2e": rnd(S("hits") / S("n_gt")) if S("n_gt") else None,
           "sens_e2e_ci": rnd(M.ratio_ci(A["hits"], A["n_gt"], W)) if S("n_gt") else None,
           "sens_clin": rnd(S("hits_clin") / S("n_clin")) if S("n_clin") else None,
           "sel_recall": rnd(S("hits") / S("det")) if S("det") else None,
           "scans_selecting": int(S("any_sel")), "sel_per_scan": rnd(S("ns") / n, 3),
           "false_per_scan": rnd(S("nf") / n, 3), "true_per_scan": rnd((S("ns") - S("nf")) / n, 3)}
    for g in (0.1, 0.2, 0.3):
        c = int(S(f"exc_{g}"))
        out[f"fdp_gt_{g}"] = {"count": c, "frac": rnd(c / n), "ci_boot": rnd(M.ratio_ci(A[f"exc_{g}"], A["n_scans"], W)),
                              "ci_exact_scans": rnd(M.clopper_pearson(c, int(n)))}
    return out


def union_ci(a, b):
    if a[0] is None:
        return b
    return [min(a[0], b[0]), max(a[1], b[1])]


def primary_cell(test, sel, proc, target, label):
    s = summarize(test, sel)
    pats, A = patient_table(test, sel)
    Wb = weights(pats, N_BOOT_BONF)
    conf_b = 1 - 0.05 / N_PRIMARY
    if proc == "P1":
        est, ci, nominal = s["mean_fdp"], s["mean_fdp_ci"], target
        ci_b = rnd(M.ratio_ci(A["sum_fdp"], A["n_scans"], Wb, conf=conf_b))
    else:
        g = s[f"fdp_gt_{target}"]
        est, nominal = g["frac"], DELTA
        ci = rnd(union_ci(g["ci_boot"], g["ci_exact_scans"]))
        ci_b = rnd(union_ci(M.ratio_ci(A[f"exc_{target}"], A["n_scans"], Wb, conf=conf_b),
                            M.clopper_pearson(g["count"], s["scans"], conf=conf_b)))
    cls = M.classify(ci, nominal, MARGIN)
    uninf = s["n_sel"] < 10 or (s["sens_e2e"] is not None and s["sens_e2e"] < 0.05)
    return {"cell": label, "procedure": proc, "target": target, "nominal": nominal, "estimate": est, "ci95": ci,
            "class": cls, "ci_bonferroni": ci_b, "class_bonferroni": M.classify(ci_b, nominal, MARGIN),
            "uninformative_abstention": bool(uninf and cls != "violated"),
            "n_sel": s["n_sel"], "sens_e2e": s["sens_e2e"], "sens_e2e_ci": s["sens_e2e_ci"],
            "micro_fdr": s["micro_fdr"], "scans": s["scans"], "patients": s["patients"],
            "scans_selecting": s["scans_selecting"], "false_per_scan": s["false_per_scan"]}


def by_group(scans, sels, key, procs=PROCS):
    groups = {}
    for s in scans:
        groups.setdefault(s[key], []).append(s)
    return {f"{p[0]}|{p[1]}": {g: summarize(ts, sels[p]) for g, ts in sorted(groups.items())} for p in procs}


# ------------------------------------------------------------------ sections
def descriptive(cache, arms):
    res = {}
    for name, scans in arms.items():
        for site in SITES:
            ss = [s for s in scans if s["site"] == site]
            if not ss:
                continue
            f = np.concatenate([s["isf"] for s in ss])
            sc = np.concatenate([s["scores"] for s in ss])
            det = sum(len(set(s["mg"][s["mg"] > 0])) for s in ss)
            ngt = sum(s["gt_ids"].size for s in ss)
            nclin = sum(int((s["gt_vol"] >= 14.14).sum()) for s in ss)
            res[f"{name}|{site}"] = {
                "scans": len(ss), "patients": len({s["patient"] for s in ss}), "candidates": int(sc.size),
                "false": int(f.sum()), "candidate_precision": rnd((~f).mean()) if sc.size else None,
                "false_per_scan": rnd(f.sum() / len(ss), 2), "gt_detectable": ngt, "gt_clinical": nclin,
                "raw_lesion_sensitivity": rnd(det / ngt) if ngt else None,
                "fp_score_mean": rnd(sc[f].mean()) if f.any() else None,
                "fp_score_q": rnd(np.quantile(sc[f], [0.25, 0.5, 0.75]).tolist()) if f.any() else None,
                "tp_score_mean": rnd(sc[~f].mean()) if (~f).any() else None,
                "slice_mm_median": rnd(np.median([s["slice_mm"] for s in ss]), 2)}
    return res


def auroc_ci(scans, n_boot=N_BOOT, seed=0):
    pats = sorted({s["patient"] for s in scans})
    per = {p: ([], []) for p in pats}
    for s in scans:
        per[s["patient"]][0].append(s["scores"])
        per[s["patient"]][1].append(~s["isf"])
    S = [np.concatenate(per[p][0]) if per[p][0] else np.zeros(0) for p in pats]
    Y = [np.concatenate(per[p][1]) if per[p][1] else np.zeros(0, bool) for p in pats]
    pt = M.auroc(np.concatenate(S), np.concatenate(Y))
    rng = np.random.RandomState(SEED + seed)
    vals = []
    for _ in range(n_boot):
        pick = rng.randint(0, len(pats), len(pats))
        v = M.auroc(np.concatenate([S[i] for i in pick]), np.concatenate([Y[i] for i in pick]))
        if v is not None:
            vals.append(v)
    return {"auroc": rnd(pt), "ci95": rnd([np.quantile(vals, 0.025), np.quantile(vals, 0.975)]) if vals else None}


def paired_diff(test_a, sel_a, test_b, sel_b):
    pa, A = patient_table(test_a, sel_a)
    pb, B = patient_table(test_b, sel_b)
    assert pa == pb
    W = weights(pa)
    out = {}
    for name, num, den in (("mean_fdp", "sum_fdp", "n_scans"), ("sens_e2e", "hits", "n_gt"), ("sens_clin", "hits_clin", "n_clin")):
        if A[den].sum() == 0:
            continue
        da = (W @ A[num]) / np.maximum(W @ A[den], 1e-12)
        db = (W @ B[num]) / np.maximum(W @ B[den], 1e-12)
        d = da - db
        out[name] = {"a": rnd(A[num].sum() / A[den].sum()), "b": rnd(B[num].sum() / B[den].sum()),
                     "diff": rnd(A[num].sum() / A[den].sum() - B[num].sum() / B[den].sum()),
                     "ci95": rnd([np.quantile(d, 0.025), np.quantile(d, 0.975)])}
    return out


def size_bins(test, sel):
    """Per-bin expert-lesion sensitivity: raw (any lenient match) and selected, patient-cluster CI."""
    pats = sorted({t["patient"] for t in test})
    idx = {p: i for i, p in enumerate(pats)}
    nb = len(SIZE_EDGES) - 1
    tot = np.zeros((len(pats), nb)); raw = np.zeros((len(pats), nb)); got = np.zeros((len(pats), nb))
    for t in test:
        i = idx[t["patient"]]
        matched = set(int(g) for g in t["mg"][t["mg"] > 0])
        chosen = set(int(g) for g in t["mg"][sel[t["case"]] & (t["mg"] > 0)]) if sel is not None else set()
        b = np.clip(np.searchsorted(SIZE_EDGES, t["gt_vol"], side="right") - 1, 0, nb - 1)
        for g, bb in zip(t["gt_ids"], b):
            tot[i, bb] += 1
            raw[i, bb] += int(g) in matched
            got[i, bb] += int(g) in chosen
    W = weights(pats)
    res = {"bins_mm3": [SIZE_EDGES[j] for j in range(nb)], "n_lesions": tot.sum(0).astype(int).tolist(),
           "sens_raw": [], "sens_raw_ci": [], "sens_selected": [], "sens_selected_ci": []}
    for j in range(nb):
        T = tot[:, j].sum()
        res["sens_raw"].append(rnd(raw[:, j].sum() / T) if T else None)
        res["sens_raw_ci"].append(rnd(M.ratio_ci(raw[:, j], tot[:, j], W)) if T else None)
        res["sens_selected"].append(rnd(got[:, j].sum() / T) if T else None)
        res["sens_selected_ci"].append(rnd(M.ratio_ci(got[:, j], tot[:, j], W)) if T else None)
    for lev in (0.8, 0.5):
        res[f"min_reliable_raw_{lev}"] = M.min_reliable_size(res["bins_mm3"], res["sens_raw"], res["n_lesions"], lev)
        res[f"min_reliable_selected_{lev}"] = M.min_reliable_size(res["bins_mm3"], res["sens_selected"], res["n_lesions"], lev)
    return res


def two_level(cal, test, proc, target, n_boot=N_BOOT2, seed=0):
    """Marginal view: resample calibration patients (within site) and test patients."""
    rng = np.random.RandomState(SEED + 7 + seed)
    cal_by = {}
    for s in cal:
        cal_by.setdefault(s["site"], {}).setdefault(s["patient"], []).append(s)
    for d in cal_by.values():
        for p in d:
            d[p].sort(key=lambda s: s["case"])
    vals = []
    for _ in range(n_boot):
        rc, rf = [], []                         # all scans / first scan of each drawn patient
        for site, d in cal_by.items():
            ps = sorted(d)
            for i in rng.randint(0, len(ps), len(ps)):
                rc.extend(d[ps[i]])
                rf.append(d[ps[i]][0])
        if proc == "P1":
            sel, _ = select(rc, test, "P1", target)
        else:
            lam = M.fdx_threshold([safe(s, target) for s in rf], DELTA)
            sel = {t["case"]: t["scores"] >= lam for t in test}
        pats, A = patient_table(test, sel)
        w = np.bincount(rng.randint(0, len(pats), len(pats)), minlength=len(pats)).astype(float)
        num = A["sum_fdp"] if proc == "P1" else A[f"exc_{target}"]
        vals.append(float(w @ num / (w @ A["n_scans"])))
    return {"mean": rnd(np.mean(vals)), "ci95": rnd([np.quantile(vals, 0.025), np.quantile(vals, 0.975)]),
            "n_boot": n_boot}


def recal_curve(scans_all, site, d1_power, reps=200):
    rng = np.random.RandomState(SEED + 31 + SITES.index(site))
    tgt = [s for s in scans_all if s["site"] == site]
    pool1mm = [s for s in scans_all if s["site"] in ONE_MM_SITES]
    pats = sorted({s["patient"] for s in tgt})
    ks = [k for k in (1, 2, 3, 5, 10, 20, 40) if k <= len(pats) - 4]
    out = {}
    for mode in ("site_only", "augmented"):
        for k in ks:
            acc = {p: {"fdr": [], "fdx": [], "sens": [], "nsel": []} for p in P_ONLY[:2] + P_ONLY[3:]}
            for _ in range(reps):
                pick = set(rng.choice(pats, k, replace=False))
                cal = [s for s in tgt if s["patient"] in pick] + (pool1mm if mode == "augmented" else [])
                test = [s for s in tgt if s["patient"] not in pick]
                for p in acc:
                    sel, _ = select(cal, test, *p)
                    pt, A = patient_table(test, sel)
                    n = A["n_scans"].sum()
                    acc[p]["fdr"].append(A["sum_fdp"].sum() / n)
                    acc[p]["fdx"].append(A[f"exc_{p[1]}"].sum() / n)
                    acc[p]["sens"].append(A["hits"].sum() / max(A["n_gt"].sum(), 1))
                    acc[p]["nsel"].append(A["ns"].sum())
            for p, v in acc.items():
                key = f"{mode}|{p[0]}|{p[1]}|k={k}"
                stat = np.array(v["fdr"] if p[0] == "P1" else v["fdx"])
                nominal = p[1] if p[0] == "P1" else DELTA
                out[key] = {"k": k, "mode": mode, "procedure": p[0], "target": p[1],
                            "realised_mean": rnd(stat.mean()), "realised_p10_p90": rnd(np.quantile(stat, [0.1, 0.9]).tolist()),
                            "share_draws_above_nominal": rnd((stat > nominal + 1e-12).mean()),
                            "mean_fdp_mean": rnd(np.mean(v["fdr"])), "sens_e2e_mean": rnd(np.mean(v["sens"])),
                            "n_sel_mean": rnd(np.mean(v["nsel"]), 1), "draws": reps}
    kstar = {}
    for mode in ("site_only", "augmented"):
        for p in P_ONLY[:2] + P_ONLY[3:]:
            pw = d1_power.get(f"{p[0]}|{p[1]}")
            nominal = p[1] if p[0] == "P1" else DELTA
            k_ok = None
            for k in ks:
                c = out[f"{mode}|{p[0]}|{p[1]}|k={k}"]
                if c["realised_mean"] <= nominal and pw is not None and c["sens_e2e_mean"] >= 0.9 * pw:
                    k_ok = k
                    break
            kstar[f"{mode}|{p[0]}|{p[1]}"] = {"k_star": k_ok, "d1_power": pw,
                                             "note": "D1 power is 0 -> criterion trivial" if pw == 0 else None}
    return {"k_grid": ks, "cells": out, "k_star": kstar}


def controls_section(cache):
    pat = build(cache, "f0")
    ctr = []
    for r in cache["controls"]:
        a = r["arms"]["f0"]
        ctr.append({"case": r["case"], "site": "sibbms", "patient": r["patient"], "scores": np.asarray(a["score"], float),
                    "isf": np.ones(a["n"], bool), "mg": np.zeros(a["n"], int), "gt_ids": np.zeros(0, int),
                    "gt_vol": np.zeros(0), "_safe": {}, "slice_mm": 1.0, "band": "B1"})
    pools = {"all five patient sites": pat, "1-mm sites": [s for s in pat if s["site"] in ONE_MM_SITES],
             "MSLesSeg only (v0.2 reference)": [s for s in pat if s["site"] == "mslesseg"],
             "thick sites": [s for s in pat if s["site"] in THICK_SITES]}
    res = {"controls": len(ctr), "controls_with_candidates": sum(int(c["scores"].size > 0) for c in ctr),
           "candidates": int(sum(c["scores"].size for c in ctr)),
           "fp_score_mean": rnd(np.concatenate([c["scores"] for c in ctr]).mean())}

    def fd(sel):
        n = sum(int(sel[c["case"]].sum()) for c in ctr)
        k = sum(int(sel[c["case"]].any()) for c in ctr)
        return {"false_detections": n, "per_100_scans": rnd(100.0 * n / len(ctr), 1), "scans_with_any": k,
                "scans_with_any_ci_exact": rnd(M.clopper_pearson(k, len(ctr)))}
    for pname, pool in pools.items():
        for p in PROCS:
            sel, lam = select(pool, ctr, *p)
            res[f"{pname}|{p[0]}|{p[1]}"] = dict(fd(sel), threshold=None if lam is None or not np.isfinite(lam) else rnd(lam))
    for a in ALPHAS:
        sel = {}
        for c in ctr:
            null = null_of([x for x in ctr if x["patient"] != c["patient"]])
            sel[c["case"]] = M.bh(M.conformal_pvalues(c["scores"], null), a) if c["scores"].size else np.zeros(0, bool)
        res[f"own-null floor (leave-one-control-out)|P1|{a}"] = fd(sel)
    return res


def mechanism(arms, n_perm=2000):
    res = {}
    for name in ("ens", "f0"):
        scans = arms[name]
        one = [s for s in scans if s["site"] in ONE_MM_SITES]
        for site in SITES:
            ss = [s for s in scans if s["site"] == site]
            groups = [s["scores"][s["isf"]] for s in ss]
            icc = M.icc1(groups)
            res[f"{name}|{site}|icc1_false_scores"] = rnd(icc)
        for site in THICK_SITES:
            ss = [s for s in scans if s["site"] == site]
            A = [s["scores"][s["isf"]] for s in one]
            B = [s["scores"][s["isf"]] for s in ss]
            obs = ks_2samp(np.concatenate(A), np.concatenate(B)).statistic
            allg = A + B
            nA = len(A)
            rng = np.random.RandomState(SEED + 77 + SITES.index(site))
            cnt = 0
            for _ in range(n_perm):
                perm = rng.permutation(len(allg))
                a = np.concatenate([allg[i] for i in perm[:nA]])
                b = np.concatenate([allg[i] for i in perm[nA:]])
                cnt += ks_2samp(a, b).statistic >= obs
            res[f"{name}|{site}_vs_1mm|scan_clustered_KS"] = {"D": rnd(obs), "p": rnd((cnt + 1) / (n_perm + 1), 5),
                                                              "n_perm": n_perm}
    return res


# ------------------------------------------------------------------ main
def main():
    t0 = time.time()
    cache = pickle.load(open(CACHE, "rb"))
    rec = {"protocol": "docs/research/paper/PROTOCOL-v0.3.md (commits 9951494, c0c5fa1)",
           "cache": {"file": "research/paper_a/.cache/v03_candidates.pkl", "sha256": sha256(CACHE)},
           "seed": SEED, "n_boot": N_BOOT, "n_boot_bonferroni": N_BOOT_BONF, "n_boot_two_level": N_BOOT2,
           "site_info": SITE_INFO, "bands": BANDS[:3] + [("B4", 6.5, "inf")], "size_edges_mm3": SIZE_EDGES[:-1]}
    arms = {"ens": build(cache, "ens"), "f0": build(cache, "f0")}
    for k in range(1, 5):
        arms[f"f{k}"] = build(cache, f"f{k}")
    arms["ens_cons"] = build(cache, "ens", "cons")
    log("scans per arm:", {k: len(v) for k, v in arms.items()})
    rec["descriptive"] = descriptive(cache, {"ens": arms["ens"], "f0": arms["f0"]})

    # ---------------- designs (ensemble + fold-0 full; folds 1-4 and consensus: P1/P2 only)
    designs = ("D1", "D2", "D3", "D3r", "D4")
    SELS = {}
    rec["designs"], rec["thresholds"] = {}, {}
    for arm in ("ens", "f0", "f1", "f2", "f3", "f4", "ens_cons"):
        procs = PROCS if arm in ("ens", "f0") else P_ONLY
        for d in designs:
            sels, lams = run_design(arms[arm], d, procs)
            SELS[(arm, d)] = sels
            test_sites = {"D3": THICK_SITES, "D3r": ONE_MM_SITES}.get(d, SITES)
            tested = [s for s in arms[arm] if s["site"] in test_sites]
            rec["designs"][f"{arm}|{d}"] = by_group(tested, sels, "site", procs)
            rec["thresholds"][f"{arm}|{d}"] = lams
        log(f"designs done for {arm} ({time.time() - t0:.0f} s)")

    # ---------------- primary cells
    prim = []
    for d, sites in (("D3", THICK_SITES), ("D2", SITES)):
        for site in sites:
            test = [s for s in arms["ens"] if s["site"] == site]
            for p in (("P1", 0.1), ("P1", 0.2), ("P2", 0.1), ("P2", 0.2)):
                prim.append(dict(primary_cell(test, SELS[("ens", d)][p], *p, f"{d}|{site}"), design=d, site=site))
    rec["primary"] = prim
    for c in prim:
        log(f"PRIMARY {c['cell']:16s} {c['procedure']} {c['target']}: est {c['estimate']} CI {c['ci95']} -> {c['class']}"
            f" (bonf {c['class_bonferroni']}){' [uninformative]' if c['uninformative_abstention'] else ''}"
            f" n_sel {c['n_sel']} sens {c['sens_e2e']}")
    # two-level bootstrap for primary cells
    tl = {}
    for d, sites in (("D3", THICK_SITES), ("D2", SITES)):
        for site, cal, test in splits(arms["ens"], d):
            if site not in sites:
                continue
            for p in (("P1", 0.1), ("P1", 0.2), ("P2", 0.1), ("P2", 0.2)):
                tl[f"{d}|{site}|{p[0]}|{p[1]}"] = two_level(cal, test, *p, seed=SITES.index(site))
    rec["primary_two_level_bootstrap"] = tl
    log(f"primary done ({time.time() - t0:.0f} s)")

    # ---------------- Q1 verdicts
    def verdict(proc, design="D3", sites=THICK_SITES):
        cells = [c for c in prim if c["design"] == design and c["procedure"] == proc and c["site"] in sites]
        if any(c["class"] == "violated" for c in cells):
            return "refuted"
        big = [c for c in cells if c["site"] in ("ms3seg", "muslim")]
        if big and all(c["class"] == "holds" for c in big):
            return "supported" + (" (some cells only by abstention)" if any(c["uninformative_abstention"] for c in cells) else "")
        return "inconclusive"
    rec["q1_verdict"] = {"P1": verdict("P1"), "P2": verdict("P2")}
    log("Q1 verdicts:", rec["q1_verdict"])

    # ---------------- thickness (Q2)
    th = {}
    for d in ("D2", "D4"):
        th[f"{d}|by_band"] = by_group(arms["ens"], SELS[("ens", d)], "band")
        for s in arms["ens"]:
            s["_siteband"] = f"{s['site']}|{s['band']}"
        th[f"{d}|by_site_band"] = by_group(arms["ens"], SELS[("ens", d)], "_siteband", P_ONLY)
    bands_scans = {}
    for s in arms["ens"]:
        bands_scans.setdefault(s["band"], []).append(s)
    sizes = {}
    for b, ss in sorted(bands_scans.items()):
        for p in (("P1", 0.2), ("P1", 0.1), ("P2", 0.2), ("P2", 0.1)):
            sizes[f"{b}|D2|{p[0]}|{p[1]}"] = size_bins(ss, SELS[("ens", "D2")][p])
    for site in SITES:
        ss = [s for s in arms["ens"] if s["site"] == site]
        sizes[f"site:{site}|D2|P1|0.2"] = size_bins(ss, SELS[("ens", "D2")][("P1", 0.2)])
    for scale in (0.9, 1.1):
        mus = build(cache, "ens", vol_scale={"muslim": scale}, sites=("muslim",))
        sel = {k: v for k, v in SELS[("ens", "D2")][("P1", 0.2)].items()}
        sizes[f"site:muslim|volx{scale}|D2|P1|0.2"] = size_bins(mus, sel)
    th["size_bins"] = sizes
    # app-facing summary per band
    app = {}
    for b in sorted(bands_scans):
        row = {"scans": len(bands_scans[b]), "patients": len({s["patient"] for s in bands_scans[b]}),
               "sites": sorted({s["site"] for s in bands_scans[b]})}
        for p in (("P1", 0.1), ("P1", 0.2), ("P2", 0.1), ("P2", 0.2)):
            sm = th["D2|by_band"][f"{p[0]}|{p[1]}"][b]
            if p[0] == "P1":
                ci, est, nominal = sm["mean_fdp_ci"], sm["mean_fdp"], p[1]
            else:
                g = sm[f"fdp_gt_{p[1]}"]
                ci, est, nominal = union_ci(g["ci_boot"], g["ci_exact_scans"]), g["frac"], DELTA
            cls = M.classify(ci, nominal, MARGIN)
            uninf = sm["n_sel"] < 10 or (sm["sens_e2e"] or 0) < 0.05
            row[f"{p[0]}|{p[1]}"] = {"realised": est, "ci95": rnd(ci), "class": cls,
                                     "uninformative": bool(uninf and cls != "violated"),
                                     "sens_e2e": sm["sens_e2e"], "sens_clin": sm["sens_clin"],
                                     "false_per_scan": sm["false_per_scan"], "true_per_scan": sm["true_per_scan"]}
        z = sizes[f"{b}|D2|P1|0.2"]
        row["min_reliable_raw_0.8"] = z["min_reliable_raw_0.8"]
        row["min_reliable_raw_0.5"] = z["min_reliable_raw_0.5"]
        row["min_reliable_at_P1_0.2_0.8"] = z["min_reliable_selected_0.8"]
        row["min_reliable_at_P1_0.2_0.5"] = z["min_reliable_selected_0.5"]
        row["raw_lesion_sensitivity"] = rnd(sum(len(set(s["mg"][s["mg"] > 0])) for s in bands_scans[b]) /
                                            max(sum(s["gt_ids"].size for s in bands_scans[b]), 1))
        row["raw_false_per_scan"] = rnd(sum(int(s["isf"].sum()) for s in bands_scans[b]) / len(bands_scans[b]), 2)
        row["label_guarantee_holds"] = all(row[f"P1|{a}"]["class"] == "holds" and not row[f"P1|{a}"]["uninformative"]
                                           for a in (0.1, 0.2))
        app[b] = row
    th["app_table"] = app
    rec["thickness"] = th
    log(f"thickness done ({time.time() - t0:.0f} s)")

    # ---------------- Q3 ensemble vs fold 0
    q3 = {"paired_ens_minus_f0": {}, "folds_point": {}, "auroc": {}}
    for d in ("D2", "D3", "D4", "D1"):
        test_sites = {"D3": THICK_SITES}.get(d, SITES)
        for site in test_sites:
            te = [s for s in arms["ens"] if s["site"] == site]
            tf = [s for s in arms["f0"] if s["site"] == site]
            for p in P_ONLY:
                q3["paired_ens_minus_f0"][f"{d}|{site}|{p[0]}|{p[1]}"] = paired_diff(te, SELS[("ens", d)][p], tf, SELS[("f0", d)][p])
        allt = [s for s in arms["ens"] if s["site"] in test_sites]
        allf = [s for s in arms["f0"] if s["site"] in test_sites]
        for p in P_ONLY:
            q3["paired_ens_minus_f0"][f"{d}|ALL|{p[0]}|{p[1]}"] = paired_diff(allt, SELS[("ens", d)][p], allf, SELS[("f0", d)][p])
    for arm in ("f0", "f1", "f2", "f3", "f4", "ens", "ens_cons"):
        for d in ("D2", "D3"):
            for p in (("P1", 0.2), ("P2", 0.2)):
                test_sites = {"D3": THICK_SITES}.get(d, SITES)
                ts = [s for s in arms[arm] if s["site"] in test_sites]
                sm = summarize(ts, SELS[(arm, d)][p], n_boot=200)
                q3["folds_point"][f"{arm}|{d}|ALL|{p[0]}|{p[1]}"] = {k: sm[k] for k in ("mean_fdp", "sens_e2e", "n_sel", "micro_fdr")} | {
                    "fdp_gt_0.2": sm["fdp_gt_0.2"]["frac"]}
    negsd = build(cache, "ens", "negsd")
    for site in SITES:
        for name, scans in (("ens_mean", arms["ens"]), ("ens_consensus_min", arms["ens_cons"]), ("ens_neg_fold_sd", negsd),
                            ("f0", arms["f0"]), ("f1", arms["f1"]), ("f2", arms["f2"]), ("f3", arms["f3"]), ("f4", arms["f4"])):
            q3["auroc"][f"{name}|{site}"] = auroc_ci([s for s in scans if s["site"] == site], seed=SITES.index(site))
    # fold-0 classification of the 32 primary cells (needed by the Q3 criterion "no new violated cell")
    f0cells = []
    for d, sites in (("D3", THICK_SITES), ("D2", SITES)):
        for site in sites:
            test = [s for s in arms["f0"] if s["site"] == site]
            for p in (("P1", 0.1), ("P1", 0.2), ("P2", 0.1), ("P2", 0.2)):
                c = primary_cell(test, SELS[("f0", d)][p], *p, f"{d}|{site}")
                f0cells.append({k: c[k] for k in ("cell", "procedure", "target", "estimate", "ci95", "class",
                                                  "uninformative_abstention", "n_sel", "sens_e2e")})
    q3["f0_primary_cells"] = f0cells
    ens_cls = {(c["cell"], c["procedure"], c["target"]): c["class"] for c in prim}
    f0_cls = {(c["cell"], c["procedure"], c["target"]): c["class"] for c in f0cells}
    new_viol = [list(k) for k in ens_cls if ens_cls[k] == "violated" and f0_cls[k] != "violated"]
    removed_viol = [list(k) for k in ens_cls if f0_cls[k] == "violated" and ens_cls[k] != "violated"]
    d_ok = {d: q3["paired_ens_minus_f0"][f"{d}|ALL|P1|0.2"]["sens_e2e"]["ci95"] for d in ("D2", "D3")}
    helps = all(ci[0] > 0 for ci in d_ok.values())
    hurts = any(ci[1] < 0 for ci in d_ok.values())
    q3["verdict"] = {"sens_diff_ci_P1_0.2": d_ok, "violations_new_with_ensemble": new_viol,
                     "violations_removed_by_ensemble": removed_viol,
                     "verdict": ("helps" if helps and not new_viol else
                                 "helps on power, but with new violated cell(s)" if helps else
                                 "hurts" if hurts else "no detectable difference")}
    log("Q3 verdict:", q3["verdict"])
    rec["q3"] = q3
    log(f"Q3 done ({time.time() - t0:.0f} s)")

    # ---------------- Q4 recalibration
    q4 = {}
    for site in ("ms3seg", "muslim", "pedims", "openms"):
        d1 = rec["designs"]["ens|D1"]
        pw = {f"{p[0]}|{p[1]}": d1[f"{p[0]}|{p[1]}"][site]["sens_e2e"] for p in P_ONLY}
        q4[site] = recal_curve(arms["ens"], site, pw)
        log(f"Q4 {site} done ({time.time() - t0:.0f} s)")
    # Q4 verdict (protocol §10): for each site/procedure whose D2 or D3 cell was violated
    q4v = {}
    for c in prim:
        if c["class"] != "violated":
            continue
        site, p, t = c["site"], c["procedure"], c["target"]
        d1 = rec["designs"]["ens|D1"][f"{p}|{t}"][site]
        if p == "P1":
            ci, nominal = d1["mean_fdp_ci"], t
        else:
            g = d1[f"fdp_gt_{t}"]
            ci, nominal = union_ci(g["ci_boot"], g["ci_exact_scans"]), DELTA
        ks = {m: q4.get(site, {}).get("k_star", {}).get(f"{m}|{p}|{t}") for m in ("site_only", "augmented")}
        q4v[f"{c['cell']}|{p}|{t}"] = {"d1_estimate": d1["mean_fdp"] if p == "P1" else d1[f"fdp_gt_{t}"]["frac"],
                                       "d1_ci": rnd(ci), "d1_class": M.classify(ci, nominal, MARGIN),
                                       "d1_sens_e2e": d1["sens_e2e"], "k_star": ks,
                                       "restores": M.classify(ci, nominal, MARGIN) != "violated"
                                       and ks["site_only"] and ks["site_only"]["k_star"] is not None}
    q4["verdict"] = q4v
    log("Q4 verdict:", q4v)
    rec["q4"] = q4

    # ---------------- controls
    rec["controls"] = controls_section(cache)
    log(f"controls done ({time.time() - t0:.0f} s)")

    # ---------------- mechanism
    rec["mechanism"] = mechanism(arms)
    log(f"mechanism done ({time.time() - t0:.0f} s)")

    # ---------------- sensitivity analyses on the primary cells
    sens = {}
    variants = {"strict_IoU0.10": build(cache, "ens", label="mg1"), "consensus_score": arms["ens_cons"],
                "pedims_without_P9": [s for s in arms["ens"] if s["patient"] != "pedims_P9"]}
    for vname, scans in variants.items():
        for d, sites in (("D3", THICK_SITES), ("D2", SITES)):
            sels, _ = run_design(scans, d, P_ONLY)
            for site in sites:
                test = [s for s in scans if s["site"] == site]
                for p in P_ONLY:
                    c = primary_cell(test, sels[p], *p, f"{d}|{site}")
                    sens[f"{vname}|{d}|{site}|{p[0]}|{p[1]}"] = {k: c[k] for k in ("estimate", "ci95", "class", "n_sel", "sens_e2e", "uninformative_abstention")}
    rec["sensitivity"] = sens
    log(f"sensitivity done ({time.time() - t0:.0f} s)")

    # ---------------- LST-AI (exploratory)
    lst = {}
    L = {"lstai": build(cache, "lstai", sites=ONE_MM_SITES, flames_only=False),
         "lstai_m1": build(cache, "lstai_m1", sites=ONE_MM_SITES, flames_only=False)}
    for name, scans in L.items():
        sels, _ = run_design(scans, "D1", P_ONLY)
        lst[f"{name}|D1"] = by_group(scans, sels, "site", P_ONLY)
        lst[f"_sels_{name}"] = sels
    for site in ONE_MM_SITES:
        te = [s for s in L["lstai"] if s["site"] == site]
        tm = [s for s in L["lstai_m1"] if s["site"] == site]
        for p in P_ONLY:
            lst[f"ens_minus_m1|D1|{site}|{p[0]}|{p[1]}"] = paired_diff(te, lst["_sels_lstai"][p], tm, lst["_sels_lstai_m1"][p])
    del lst["_sels_lstai"], lst["_sels_lstai_m1"]
    # segmenter shift on MSLesSeg, patient 5-fold cross-fit (calibration and test patients disjoint)
    fl = [s for s in arms["ens"] if s["site"] == "mslesseg"]
    ls = [s for s in L["lstai"] if s["site"] == "mslesseg"]
    pats = sorted({s["patient"] for s in fl})
    folds = _folds(pats, 5, SEED + 555)
    for direction, (calset, testset) in {"FLAMeS->LST-AI": (fl, ls), "LST-AI->FLAMeS": (ls, fl),
                                         "LST-AI->LST-AI": (ls, ls), "FLAMeS->FLAMeS": (fl, fl)}.items():
        for p in P_ONLY:
            sel = {}
            for f in folds:
                cal = [s for s in calset if s["patient"] not in f]
                test = [s for s in testset if s["patient"] in f]
                sel.update(select(cal, test, *p)[0])
            lst[f"segmenter_shift|mslesseg|{direction}|{p[0]}|{p[1]}"] = summarize(testset, sel)
    lst["descriptive"] = descriptive(cache, L)
    for site in ONE_MM_SITES:
        for name, scans in L.items():
            lst[f"auroc|{name}|{site}"] = auroc_ci([s for s in scans if s["site"] == site], seed=11)
    rec["lstai"] = lst
    log(f"LST-AI done ({time.time() - t0:.0f} s)")

    rec["runtime_s"] = round(time.time() - t0, 1)
    rec["log"] = LOG
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    log(f"wrote {OUT_JSON} in {rec['runtime_s']} s")


if __name__ == "__main__":
    main()
