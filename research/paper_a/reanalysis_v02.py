#!/usr/bin/env python3
"""Paper A v0.2 — re-analysis of manuscript §3-§4 after the training-overlap audit, plus the
baselines and per-cohort AUROC reviewers will ask for. CPU only, cached candidate scores only.

What changed relative to v0.1 (and why):
  * FLAMeS trained on 20 of the 30 Ljubljana (openms) scans: patients 01-15 and 21-25 (exact
    match of the released nnU-Net fingerprint, docs/research/records/2026-10-17_flames_*). The
    maps we use come from fold 0 only, which also did not train on patients 04 and 07 (fold-0
    validation). openms is therefore split into
        heldout10 = 16-20, 26-30  (never seen by any FLAMeS fold)        <- PRIMARY clean subset
        clean12   = heldout10 + 04, 07 (not seen by the fold-0 weights)  <- sensitivity
        trained20 / trained18                                             <- in-distribution
    and every analysis that used openms is re-run on the clean subset (n = 10, reported as such)
    with the full-openms result kept only as an in-distribution reference.
  * Patient nulls that pooled openms (contaminated) are replaced by MSLesSeg-only nulls.
  * Labels: one-to-one Hungarian (lenient IoU > 0) everywhere, as §3 of the paper defines; v0.1
    §4.3/§4.4 had used any-voxel labels for the patient null (both are reported).
  * Proportions over scans use DISTINCT scans with exact Clopper-Pearson intervals (single-
    timepoint cohorts) or subject-cluster bootstrap (MSLesSeg, up to 3 scans per subject).
  * New: per-cohort lesion-level AUROC with subject-clustered bootstrap CIs; ICC of false-
    candidate scores recomputed by a committed script (v0.1 cited 0.078/0.094 with no committed
    code); baselines (a) subsampled null (Dunn-Wasserman-Ramdas style), (b) scan-level CRC / LTT
    global threshold with per-scan FDP loss, (c) Lee & Ren hierarchical / subsampling conformal
    e-values with e-BH.

    python research/paper_a/reanalysis_v02.py
"""
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import baselines as bl                                                    # noqa: E402
from common import (RECORDS, auroc, clopper_pearson, cluster_bootstrap,   # noqa: E402
                    cp_upper_one_sided, flames_split, load_cache, openms_patient)

ALPHAS = (0.30, 0.20, 0.10)
SEED = 20261017
N_BOOT = 2000
N_DRAWS = 200                      # randomised baselines (subsampled null, Lee-Ren subsampling)
CLIN = 14.14
OUT_JSON = os.path.join(RECORDS, "2026-10-17_paper_a_v02_marginal.json")


# ------------------------------------------------------------------ data
def build():
    adv, adv_meta = load_cache(".multisite_adv_cache.npz")
    v2, v2_meta = load_cache(".multisite_cache_v2.npz")
    reg, reg_meta = load_cache(".region_cache.npz")
    any_voxel = {(c["site"], c["case"]): c for c in v2}
    scans = []
    for c in adv:                                   # openms + MSLesSeg, one-to-one labels
        av = any_voxel[(c["site"], c["case"])]
        assert np.allclose(av["scores"], c["scores"])
        scans.append({"site": c["site"], "case": c["case"], "subject": c["subject"],
                      "scores": np.asarray(c["scores"], float),
                      "isf": np.asarray(c["mg0"]) == 0, "isf_strict": np.asarray(c["mg1"]) == 0,
                      "isf_anyvoxel": np.asarray(av["is_false0"], bool),
                      "mg": np.asarray(c["mg0"], int), "mg_strict": np.asarray(c["mg1"], int),
                      "n_gt": int(c["n_gt"]), "n_gt_clin": int(c["n_gt_clin"]),
                      "clin_gt": set(int(x) for x in c["clin_gt"]), "feats": np.asarray(c["feats"], float),
                      "patient": openms_patient(c["case"])})
    controls = [{"site": "sibbms", "case": c["case"], "subject": c["subject"],
                 "scores": np.asarray(c["scores"], float),
                 "isf": np.ones(len(c["scores"]), bool), "region": np.asarray(c["region"], int)}
                for c in reg if c["site"] == "sibbms"]
    isbi = [{"site": "isbi", "case": c["case"], "subject": c["subject"],
             "scores": np.asarray(c["scores"], float), "isf": np.asarray(c["is_false0"], bool)}
            for c in v2 if c["site"] == "isbi"]
    return scans, controls, isbi, [adv_meta, v2_meta, reg_meta]


def subset(scans, name):
    sp = flames_split()
    if name == "mslesseg":
        return [s for s in scans if s["site"] == "mslesseg"]
    if name == "openms_all":
        return [s for s in scans if s["site"] == "openms"]
    keep = set(sp[name])
    return [s for s in scans if s["site"] == "openms" and s["patient"] in keep]


def one_scan_per_subject(scans, rng):
    by = {}
    for s in scans:
        by.setdefault(s["subject"], []).append(s)
    return [v[rng.randint(len(v))] for _, v in sorted(by.items())]


def relabel(scans, key):
    out = []
    for s in scans:
        t = dict(s)
        t["isf"] = s[key]
        t["mg"] = s["mg_strict"] if key == "isf_strict" else s.get("mg")
        out.append(t)
    return out


# ------------------------------------------------------------------ metrics
def metrics(test, sels, alpha, rng, boot=True):
    rows = []
    for t, sel in zip(test, sels):
        ns = int(sel.sum()); nf = int((sel & t["isf"]).sum())
        rows.append({"subject": t["subject"], "ns": ns, "nf": nf, "fdp": nf / ns if ns else 0.0,
                     "t": t, "sel": sel})
    N = len(rows)
    ns = sum(r["ns"] for r in rows); nf = sum(r["nf"] for r in rows)
    exc = sum(r["fdp"] > alpha for r in rows)
    single_tp = len({r["subject"] for r in rows}) == N
    out = {"scans": N, "subjects": len({r["subject"] for r in rows}), "n_sel": ns,
           "micro_fdr": round(nf / ns, 4) if ns else 0.0,
           "mean_scan_fdp": round(float(np.mean([r["fdp"] for r in rows])), 4) if N else None,
           "scans_fdp_gt_alpha": exc, "frac_fdp_gt_alpha": round(exc / N, 4) if N else None,
           "scans_selecting": sum(r["ns"] > 0 for r in rows)}
    by = {}
    for r in rows:
        by.setdefault(r["subject"], []).append(r)
    if boot and ns:
        out["micro_fdr_ci"] = cluster_bootstrap(
            by, lambda it: (sum(x["nf"] for x in it) / sum(x["ns"] for x in it)) if sum(x["ns"] for x in it) else 0.0,
            N_BOOT, rng)
    if boot and N:
        out["mean_scan_fdp_ci"] = cluster_bootstrap(by, lambda it: float(np.mean([x["fdp"] for x in it])), N_BOOT, rng)
        if single_tp:
            out["frac_fdp_gt_alpha_ci_exact"] = clopper_pearson(exc, N)
        else:
            out["frac_fdp_gt_alpha_ci_cluster"] = cluster_bootstrap(
                by, lambda it: float(np.mean([x["fdp"] > alpha for x in it])), N_BOOT, rng)
    # recalls (one-to-one match ids), only for cohorts with GT bookkeeping
    if all("n_gt" in r["t"] for r in rows):
        hit = det = tot = hit_c = tot_c = 0
        for r in rows:
            mg, sel, t = r["t"]["mg"], r["sel"], r["t"]
            tot += t["n_gt"]; tot_c += t["n_gt_clin"]
            det += len({int(g) for g in mg if g > 0})
            sg = {int(g) for g, s in zip(mg, sel) if s and g > 0}
            hit += len(sg); hit_c += len(sg & t["clin_gt"])
        out["recall_selection"] = round(hit / det, 4) if det else None
        out["recall_end_to_end"] = round(hit / tot, 4) if tot else None
        out["recall_clinical"] = round(hit_c / tot_c, 4) if tot_c else None
    return out


def false_det(test, sels):
    fd = sum(int(s.sum()) for s in sels)
    scans_any = sum(int(s.any()) for s in sels)
    N = len(test)
    return {"false_detections": fd, "per_100_scans": round(100.0 * fd / N, 1), "scans": N,
            "scans_with_any_false_detection": scans_any,
            "scans_with_any_ci_exact": clopper_pearson(scans_any, N),
            "scans_with_any_upper95_one_sided": cp_upper_one_sided(scans_any, N)}


# ------------------------------------------------------------------ procedures (v0.1 family)
def naive_tau(cal, alpha):
    sc = np.concatenate([c["scores"] for c in cal]); f = np.concatenate([c["isf"] for c in cal])
    o = np.argsort(-sc); ok = (np.cumsum(f[o]) / np.arange(1, sc.size + 1)) <= alpha
    return sc[o][np.max(np.where(ok)[0])] if ok.any() else np.inf


def wcs(cal, test, alpha):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import PolynomialFeatures
    Xc = np.vstack([c["feats"] for c in cal]); Xt = np.vstack([t["feats"] for t in test])
    Xd = np.vstack([Xc, Xt]); yd = np.r_[np.zeros(len(Xc)), np.ones(len(Xt))]
    mu, sd = Xd.mean(0), Xd.std(0) + 1e-9
    pf = PolynomialFeatures(2, include_bias=False)
    dom = LogisticRegression(max_iter=4000, C=1.0).fit(pf.fit_transform((Xd - mu) / sd), yd)

    def w(X):
        q = np.clip(dom.predict_proba(pf.transform((X - mu) / sd))[:, 1], 1e-3, 1 - 1e-3)
        return q / (1 - q)
    null = np.concatenate([c["scores"][c["isf"]] for c in cal])
    wn = w(np.vstack([c["feats"][c["isf"]] for c in cal if c["isf"].any()]))
    out = []
    for t in test:
        wt = w(t["feats"])
        p = np.array([(wj + wn[null >= s].sum()) / (wj + wn.sum()) for s, wj in zip(t["scores"], wt)])
        out.append(bl._bh(p, alpha))
    return out, float(wn.sum() ** 2 / (wn ** 2).sum())


# ------------------------------------------------------------------ sections
def cohort_table(scans, controls, isbi):
    res = {}
    for name in ("mslesseg", "openms_all", "heldout10", "clean12", "trained20", "trained18"):
        cs = subset(scans, name)
        f = np.concatenate([c["isf"] for c in cs]); s = np.concatenate([c["scores"] for c in cs])
        det = sum(len({int(g) for g in c["mg"] if g > 0}) for c in cs)
        gt = sum(c["n_gt"] for c in cs)
        res[name] = {"scans": len(cs), "subjects": len({c["subject"] for c in cs}),
                     "candidates": int(s.size), "false_one_to_one": int(f.sum()),
                     "true_one_to_one": int((~f).sum()),
                     "gt_3mm3": gt, "gt_14mm3": sum(c["n_gt_clin"] for c in cs),
                     "lesion_sensitivity_detectable": round(det / gt, 4) if gt else None,
                     "candidate_precision": round(float((~f).mean()), 4),
                     "false_per_scan": round(float(f.sum()) / len(cs), 2),
                     "fp_score_mean": round(float(s[f].mean()), 4),
                     "tp_score_mean": round(float(s[~f].mean()), 4)}
    s = np.concatenate([c["scores"] for c in controls if c["scores"].size])
    res["controls"] = {"scans": len(controls), "scans_with_candidates": sum(c["scores"].size > 0 for c in controls),
                       "candidates": int(s.size), "fp_score_mean": round(float(s.mean()), 4)}
    s = np.concatenate([c["scores"] for c in isbi]); f = np.concatenate([c["isf"] for c in isbi])
    res["isbi_lstai"] = {"scans": len(isbi), "candidates": int(s.size), "false_any_voxel": int(f.sum()),
                         "fp_score_mean": round(float(s[f].mean()), 4), "tp_score_mean": round(float(s[~f].mean()), 4)}
    return res


def auroc_section(scans, isbi, rng):
    res = {}
    for name in ("mslesseg", "openms_all", "heldout10", "clean12", "trained20", "trained18"):
        cs = subset(scans, name)
        for lab in ("isf", "isf_anyvoxel"):
            by = {}
            for c in cs:
                by.setdefault(c["subject"], []).append(c)

            def stat(items, lab=lab):
                return auroc(np.concatenate([x["scores"] for x in items]),
                             ~np.concatenate([x[lab] for x in items]))
            pt = stat(cs)
            res[f"{name}|{'one_to_one' if lab == 'isf' else 'any_voxel'}"] = {
                "auroc": round(pt, 4), "ci95_subject_cluster": cluster_bootstrap(by, stat, N_BOOT, rng),
                "scans": len(cs), "subjects": len(by)}
    by = {c["case"]: [c] for c in isbi}         # ISBI subject identity not recoverable -> scan clusters
    stat = lambda items: auroc(np.concatenate([x["scores"] for x in items]), ~np.concatenate([x["isf"] for x in items]))  # noqa: E731
    res["isbi_lstai|any_voxel"] = {"auroc": round(stat(isbi), 4),
                                   "ci95_scan_cluster": cluster_bootstrap(by, stat, N_BOOT, rng),
                                   "scans": len(isbi),
                                   "note": "scan-level clusters (5 ISBI patients not identifiable) -> CI too narrow"}
    # trained vs held-out difference (independent subject resampling within each group)
    tr, ho = subset(scans, "trained20"), subset(scans, "heldout10")
    d = []
    for _ in range(N_BOOT):
        a = [tr[i] for i in rng.randint(0, len(tr), len(tr))]
        b = [ho[i] for i in rng.randint(0, len(ho), len(ho))]
        d.append(auroc(np.concatenate([x["scores"] for x in a]), ~np.concatenate([x["isf"] for x in a]))
                 - auroc(np.concatenate([x["scores"] for x in b]), ~np.concatenate([x["isf"] for x in b])))
    res["diff_trained20_minus_heldout10|one_to_one"] = {
        "point": round(res["trained20|one_to_one"]["auroc"] - res["heldout10|one_to_one"]["auroc"], 4),
        "ci95": [round(float(np.quantile(d, 0.025)), 4), round(float(np.quantile(d, 0.975)), 4)]}
    return res


def transport_section(scans, rng):
    res = {}
    pairs = [("mslesseg", "heldout10"), ("heldout10", "mslesseg"), ("mslesseg", "clean12"),
             ("mslesseg", "trained20"), ("mslesseg", "openms_all"), ("openms_all", "mslesseg")]
    for key in ("isf", "isf_strict"):
        tag = "lenient" if key == "isf" else "strict"
        for cal_name, test_name in pairs:
            cal, test = relabel(subset(scans, cal_name), key), relabel(subset(scans, test_name), key)
            for alpha in ALPHAS:
                cell = {}
                cell["conformal_bh"] = metrics(test, bl.conformal_bh(cal, test, alpha), alpha, rng)
                tau = naive_tau(cal, alpha)
                cell["naive_threshold"] = metrics(test, bl.apply_threshold(test, tau), alpha, rng)
                cell["naive_threshold"]["tau"] = None if not np.isfinite(tau) else round(float(tau), 4)
                sw, ess = wcs(cal, test, alpha)
                cell["wcs"] = metrics(test, sw, alpha, rng)
                cell["wcs"]["ess"] = round(ess, 1)
                res[f"{tag}|{alpha}|{cal_name}->{test_name}"] = cell
            print(f"  transport {tag} {cal_name}->{test_name} done")
    # within-MSLesSeg leave-one-subject-out (clean within-site reference)
    ms = subset(scans, "mslesseg")
    for alpha in ALPHAS:
        sels = []
        for t in ms:
            cal = [c for c in ms if c["subject"] != t["subject"]]
            sels.append(bl.conformal_bh(cal, [t], alpha)[0])
        res[f"lenient|{alpha}|mslesseg LOSO"] = {"conformal_bh": metrics(ms, sels, alpha, rng)}
    return res


def fdx_operating_point(scans):
    """v0.1 §4.2: alpha* = largest alpha whose own-site LOSO exceedance P(FDP>0.2) <= 0.1, then
    applied cross-site. Re-run with the clean openms subset."""
    GAMMA, DELTA = 0.2, 0.1
    grid = np.round(np.linspace(0.02, 0.60, 30), 3)

    def exceed(test, null_fn, a):
        f = []
        for t in test:
            sel = bl._bh(bl._pvals(t["scores"], null_fn(t)), a) if t["scores"].size else np.zeros(0, bool)
            ns = int(sel.sum()); f.append(((sel & t["isf"]).sum() / ns) if ns else 0.0)
        return f
    out = {}
    for cal_name, test_name in [("mslesseg", "heldout10"), ("heldout10", "mslesseg"),
                                ("mslesseg", "openms_all"), ("openms_all", "mslesseg")]:
        cc = subset(scans, cal_name)
        loo = lambda t, cc=cc: np.concatenate([c["scores"][c["isf"]] for c in cc if c["subject"] != t["subject"]])  # noqa: E731
        a_star = None
        for a in grid:
            if np.mean([x > GAMMA for x in exceed(cc, loo, a)]) <= DELTA:
                a_star = float(a)
        if a_star is None:
            out[f"{cal_name}->{test_name}"] = {"alpha_star": None}
            continue
        null = np.concatenate([c["scores"][c["isf"]] for c in cc])
        test = subset(scans, test_name)
        f = exceed(test, lambda t: null, a_star)
        x = sum(v > GAMMA for v in f)
        single = len({t["subject"] for t in test}) == len(test)
        out[f"{cal_name}->{test_name}"] = {"alpha_star": a_star, "test_scans": len(test),
                                           "test_scans_fdp_gt_0.2": int(x),
                                           "test_exceed": round(x / len(test), 4),
                                           "ci_exact": clopper_pearson(x, len(test)) if single else None}
    return out


def controls_section(scans, controls):
    res = {}
    nulls = {"mslesseg(one-to-one)": np.concatenate([c["scores"][c["isf"]] for c in subset(scans, "mslesseg")]),
             "mslesseg(any-voxel, v0.1 labels)": np.concatenate([c["scores"][c["isf_anyvoxel"]] for c in subset(scans, "mslesseg")]),
             "openms_heldout10(one-to-one)": np.concatenate([c["scores"][c["isf"]] for c in subset(scans, "heldout10")]),
             "openms_all(any-voxel, v0.1, CONTAMINATED)": np.concatenate([c["scores"][c["isf_anyvoxel"]] for c in subset(scans, "openms_all")]),
             "pooled openms_all+mslesseg(any-voxel, v0.1, CONTAMINATED)": np.concatenate(
                 [c["scores"][c["isf_anyvoxel"]] for c in subset(scans, "openms_all") + subset(scans, "mslesseg")])}
    for alpha in ALPHAS:
        own = []
        for t in controls:
            null = np.concatenate([c["scores"] for c in controls if c["subject"] != t["subject"]])
            own.append(bl._bh(bl._pvals(t["scores"], null), alpha) if t["scores"].size else np.zeros(0, bool))
        res[f"{alpha}|own LOSO null (floor)"] = false_det(controls, own)
        for nm, null in nulls.items():
            sels = [bl._bh(bl._pvals(t["scores"], null), alpha) if t["scores"].size else np.zeros(0, bool)
                    for t in controls]
            res[f"{alpha}|{nm}"] = false_det(controls, sels)
            res[f"{alpha}|{nm}"]["null_size"] = int(null.size)
    return res


def isbi_section(scans, isbi):
    res = {}
    for nm, null in {"mslesseg(one-to-one)": np.concatenate([c["scores"][c["isf"]] for c in subset(scans, "mslesseg")]),
                     "mslesseg(any-voxel)": np.concatenate([c["scores"][c["isf_anyvoxel"]] for c in subset(scans, "mslesseg")]),
                     "openms_heldout10(one-to-one)": np.concatenate([c["scores"][c["isf"]] for c in subset(scans, "heldout10")])}.items():
        for alpha in ALPHAS:
            sels = [bl._bh(bl._pvals(t["scores"], null), alpha) for t in isbi]
            ns = sum(int(s.sum()) for s in sels)
            nf = sum(int((s & t["isf"]).sum()) for s, t in zip(sels, isbi))
            res[f"{alpha}|{nm}"] = {"n_sel": ns, "n_false_sel": nf, "scans_selecting": sum(int(s.any()) for s in sels)}
    return res


def icc_section(scans, rng, n_perm=5000):
    """One-way random-effects ICC(1) of FALSE-candidate scores grouped by scan (scans with >= 2
    false candidates), and a permutation test of the between-scan mean square (false scores
    shuffled across scans, scan sizes fixed)."""
    res = {}
    for name in ("mslesseg", "openms_all", "heldout10", "trained20"):
        groups = [c["scores"][c["isf"]] for c in subset(scans, name)]
        groups = [g for g in groups if g.size >= 2]
        sizes = np.array([g.size for g in groups]); N = sizes.sum(); k = len(groups)
        allv = np.concatenate(groups)

        def msb_msw(gs):
            gm = np.array([g.mean() for g in gs]); m = allv.mean()
            ssb = float((sizes * (gm - m) ** 2).sum())
            ssw = float(sum(((g - g.mean()) ** 2).sum() for g in gs))
            return ssb / (k - 1), ssw / (N - k)
        msb, msw = msb_msw(groups)
        n0 = (N - (sizes ** 2).sum() / N) / (k - 1)
        icc = (msb - msw) / (msb + (n0 - 1) * msw)
        perm = []
        cuts = np.cumsum(sizes)[:-1]
        for _ in range(n_perm):
            p = rng.permutation(allv)
            perm.append(msb_msw(np.split(p, cuts))[0])
        perm = np.array(perm)
        res[name] = {"scans": int(k), "false_candidates": int(N), "icc1": round(float(icc), 4),
                     "msb_over_mean_perm_msb": round(float(msb / perm.mean()), 3),
                     "perm_p": round(float(((perm >= msb).sum() + 1) / (n_perm + 1)), 5), "n_perm": n_perm}
    return res


def baselines_section(scans, controls, rng):
    """Baselines in three clean designs (each test scan evaluated exactly once):
       D1 MSLesSeg -> openms heldout10 (calibration: one scan per MSLesSeg subject);
       D2 MSLesSeg within-site, 5-fold subject-grouped cross-fitting;
       D3 MSLesSeg -> healthy controls (false detections)."""
    res = {}
    ms = subset(scans, "mslesseg")
    cal1 = [c for c in one_scan_per_subject(ms, np.random.RandomState(SEED)) if c["scores"].size]
    ho = subset(scans, "heldout10")
    subj = sorted({c["subject"] for c in ms})
    perm = np.random.RandomState(SEED + 1).permutation(len(subj))
    folds = [set(subj[i] for i in perm[f::5]) for f in range(5)]

    def run(method, cal, test, alpha, seed):
        r = np.random.RandomState(seed)
        if method == "conformal_bh":
            return bl.conformal_bh(cal, test, alpha)
        if method == "subsampled_bh":
            return bl.subsampled_bh(cal, test, alpha, r)
        if method == "crc":
            return bl.apply_threshold(test, bl.crc_threshold(cal, alpha))
        if method == "ltt":
            return bl.apply_threshold(test, bl.ltt_threshold(cal, alpha, 0.1))
        if method == "leeren_hier":
            return bl.leeren(cal, test, alpha, "hier")
        if method == "leeren_sub":
            return bl.leeren(cal, test, alpha, "sub", rng=r)
        raise ValueError(method)

    methods = ("conformal_bh", "subsampled_bh", "crc", "ltt", "leeren_hier", "leeren_sub")
    randomised = {"subsampled_bh", "leeren_sub"}

    def d2_sels(method, alpha, seed):
        sels = {}
        for f in range(5):
            test = [c for c in ms if c["subject"] in folds[f]]
            pool = [c for c in ms if c["subject"] not in folds[f]]
            cal = [c for c in one_scan_per_subject(pool, np.random.RandomState(SEED + 10 + f)) if c["scores"].size]
            for t, s in zip(test, run(method, cal, test, alpha, seed + f)):
                sels[t["case"]] = s
        return [sels[t["case"]] for t in ms]

    for alpha in ALPHAS:
        for method in methods:
            for design in ("D1 mslesseg->openms_heldout10", "D2 mslesseg 5-fold", "D3 mslesseg->controls"):
                test = ho if design.startswith("D1") else ms if design.startswith("D2") else controls
                draws = N_DRAWS if method in randomised else 1
                summ = []
                for d in range(draws):
                    seed = SEED + 1000 * d
                    sels = (d2_sels(method, alpha, seed) if design.startswith("D2")
                            else run(method, cal1, test, alpha, seed))
                    if design.startswith("D3"):
                        summ.append(false_det(test, sels))
                    else:
                        summ.append(metrics(test, sels, alpha, rng, boot=(draws == 1)))
                key = f"{alpha}|{design}|{method}"
                if draws == 1:
                    res[key] = summ[0]
                else:
                    agg = {"draws": draws}
                    for fld in summ[0]:
                        vals = [s[fld] for s in summ if isinstance(s.get(fld), (int, float)) and s.get(fld) is not None]
                        if vals and len(vals) == draws:
                            agg[fld] = {"mean": round(float(np.mean(vals)), 4),
                                        "p05": round(float(np.quantile(vals, 0.05)), 4),
                                        "p95": round(float(np.quantile(vals, 0.95)), 4)}
                    res[key] = agg
        print(f"  baselines alpha={alpha} done")
    res["thresholds"] = {f"{a}|{m}": (lambda v: None if not np.isfinite(v) else round(v, 4))(
        bl.crc_threshold(cal1, a) if m == "crc" else bl.ltt_threshold(cal1, a, 0.1))
        for a in ALPHAS for m in ("crc", "ltt")}
    res["design_notes"] = {"D1_calibration_scans": len(cal1), "D1_test_scans": len(ho),
                           "D2_folds": [len(f) for f in folds]}
    return res


def main():
    t0 = time.time()
    scans, controls, isbi, meta = build()
    rng = np.random.RandomState(SEED)
    rec = {"inputs": meta, "flames_split": flames_split(), "seed": SEED, "n_boot": N_BOOT}
    print("cohort table ..."); rec["cohorts"] = cohort_table(scans, controls, isbi)
    print("AUROC ..."); rec["auroc"] = auroc_section(scans, isbi, rng)
    print("transport ..."); rec["transport"] = transport_section(scans, rng)
    print("per-scan operating point ..."); rec["fdx_operating_point"] = fdx_operating_point(scans)
    print("controls ..."); rec["controls"] = controls_section(scans, controls)
    print("ISBI / LST-AI ..."); rec["isbi_segmenter_shift"] = isbi_section(scans, isbi)
    print("ICC ..."); rec["icc"] = icc_section(scans, rng)
    print("baselines ..."); rec["baselines"] = baselines_section(scans, controls, rng)
    rec["runtime_s"] = round(time.time() - t0, 1)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    print(f"wrote {OUT_JSON} in {rec['runtime_s']} s")


if __name__ == "__main__":
    main()
