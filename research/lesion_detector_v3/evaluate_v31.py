#!/usr/bin/env python3
"""Lesion-detector v3.1 — the pre-registered evaluation (docs/research/lesion-detector-v3/PROTOCOL-v3.1.md).

Reads the cache written by `build_features.py --cloud-root ...` and runs, with the v3 model
specifications, seeds and resampling:
  primary   pooled external AUROC on the never-analysed sites (MS3SEG + Muslim + PediMS), GR-LR trained
            on MSLesSeg + clean Ljubljana-10 vs raw fold-0 probability
  H2 / H3   vs the plain 5-fold ensemble score; does fold disagreement add (vs GR without F8)
  H4 / H4b  site signature of the new families vs the FLAIR families / vs grid-robust features
  S         per-site AUROC, M <-> L10 analyses (not confirmatory), external conformal selection
  B1-B8     adversarial self-check
Reuses the helpers of evaluate_v3.py (same models, bootstrap, conformal code).

    python research/lesion_detector_v3/evaluate_v31.py [--cache PATH] [--tag 2026-10-21]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

import numpy as np
from scipy.stats import ks_2samp

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import evaluate_v3 as ev                                                  # noqa: E402
import features_v3 as fv                                                  # noqa: E402

SEED = ev.SEED
SITES = ("ms3seg", "muslim", "pedims")
GR_BASE = ("prob_mean", "prob_max", "prob_std", "prob_q90", "log_volume_mm3", "ps_surv_075", "ps_surv_090",
           "ps_log_merge_025", "ps_log_merge_010")
ev.FEATURE_SETS.update({
    "GR": GR_BASE + fv.F8,
    "GR-noENS": GR_BASE,
    "ENS-only": fv.F8,
    "V31": ev.FEATURE_SETS["V3"] + fv.F8 + fv.F9 + fv.F9B,
    "V3P+ENS+LST": ev.FEATURE_SETS["V3P"] + fv.F8 + fv.F9 + fv.F9B,
    "LST-only": fv.F9 + fv.F9B,
})
ev.MODELS.update({
    "GR-LR": ("GR", ev.fit_lr), "GR-GB": ("GR", ev.fit_gb), "GR-noENS-LR": ("GR-noENS", ev.fit_lr),
    "ENS-only-LR": ("ENS-only", ev.fit_lr), "V31-LR": ("V31", ev.fit_lr),
    "V3P+ENS+LST-LR": ("V3P+ENS+LST", ev.fit_lr),
})
EXT_MODELS = ("GR-LR", "GR-noENS-LR", "ENS-only-LR", "GR-GB")
SIG_FAMILIES = {"F1_flair_contrast": fv.F1, "F3_flair_texture": fv.F3, "F4_flair_boundary": fv.F4_FLAIR,
                "F8_fold_disagreement": fv.F8, "F9_lstai_agreement": fv.F9 + fv.F9B,
                "v2_prob": ev.V2_PROB, "F5_persistence": fv.F5, "GR-noENS": GR_BASE}


class Data31(ev.Data):
    def __init__(self, path):
        super().__init__(path)
        d = np.load(path, allow_pickle=False)
        self.s_spacing = d["scan_spacing"]
        for s in SITES:
            self.sets[s] = self.cohort == s
            self.scan_sets[s] = self.s_cohort == s
        self.sets["EXT"] = np.isin(self.cohort, SITES)
        self.sets["TRAIN"] = self.sets["M"] | self.sets["L10"]
        self.ens = self.X[:, self.col["ens_mean"]]


def ext_scores(D, y, models, train_mask, test_mask, perm_rng=None):
    idx = np.nonzero(test_mask)[0]
    out = {"RAW": D.raw[idx], "ENS-RAW": D.ens[idx]}
    ev.assert_disjoint(D, train_mask, test_mask)
    for m in models:
        out[m] = ev.fit_predict(D, m, train_mask, test_mask, y, perm_rng)
    return out, idx


def site_strata(D):
    return [D.sets[s] for s in SITES]


def separability_boot(D, oof, labels, idx, strata_masks, seed):
    """|AUROC - 0.5| per family + paired bootstrap matrix (B x families)."""
    names = list(oof)
    pos = {g: k for k, g in enumerate(idx)}
    inidx = np.isin(np.arange(len(D.raw)), idx)
    strata = [[np.array([pos[g] for g in cl]) for cl in D.clusters(sm & inidx)] for sm in strata_masks]
    strata = [s for s in strata if s]
    lab = labels[idx]

    def stat(ii):
        vals = [ev.auroc(oof[n][ii], lab[ii]) for n in names]
        return np.array([np.nan if v is None else abs(v - 0.5) for v in vals])
    point = stat(np.arange(len(idx)))
    bs = ev.cluster_boot(strata, stat, ev.N_BOOT, np.random.RandomState(seed))
    return names, point, bs


def site_identity(D, fam_cols, mask_a, mask_b, seed):
    """Out-of-fold cohort-identity scores (cohort-stratified patient folds), per family."""
    both = mask_a | mask_b
    folds = {**ev.patient_folds(D, mask_a, 5, seed), **ev.patient_folds(D, mask_b, 5, seed + 1)}
    fo = np.array([folds.get(p, -1) for p in D.patient])
    idx = np.nonzero(both)[0]
    lab = mask_b.astype(bool)
    oof = {}
    for g, cols in fam_cols.items():
        Xg = D.X[:, [D.col[c] for c in cols]]
        o = np.zeros(len(idx))
        for f in range(5):
            tr, te = both & (fo != f), both & (fo == f)
            o[np.isin(idx, np.nonzero(te)[0])] = ev.fit_lr(Xg[tr], lab[tr].astype(int))(Xg[te])
        oof[g] = o
    return oof, idx, lab


def conformal_external(D, y, models=("GR-LR",)):
    """20 seeded splits: scorer trained on M-train-half + L10, null = FALSE candidates of M-calibration
    half, test = each new site. RAW / ENS-RAW use the identical calibration patients."""
    M = D.sets["M"]
    pats = np.array(sorted(set(D.patient[M])))
    names = ("RAW", "ENS-RAW") + tuple(models)
    acc = {(s, a, meth): {m: [] for m in names} for s in SITES for a in ev.ALPHAS for meth in ("bh", "fdx")}
    for sp in range(ev.N_SPLITS_XCOHORT):
        rng = np.random.RandomState(SEED + 100 + sp)
        perm = rng.permutation(pats)
        tr_p = set(perm[:len(pats) // 2])
        tr = (M & np.isin(D.patient, list(tr_p))) | D.sets["L10"]
        ca = M & ~np.isin(D.patient, list(tr_p))
        ev.assert_disjoint(D, tr, ca, D.sets["EXT"])
        ev.assert_disjoint(D, ca, D.sets["L10"])
        E = np.nonzero(D.sets["EXT"])[0]
        sc = {"RAW": (D.raw, D.raw[ca & ~y]), "ENS-RAW": (D.ens, D.ens[ca & ~y])}
        for m in models:
            fset, fitter = ev.MODELS[m]
            f = fitter(D.F(fset, tr), y[tr].astype(int))
            full = np.full(len(y), np.nan)
            full[E] = f(D.F(fset, D.sets["EXT"]))
            sc[m] = (full, f(D.F(fset, ca & ~y)))
        for s in SITES:
            scans = np.nonzero(D.scan_sets[s])[0]
            for a in ev.ALPHAS:
                for meth in ("bh", "fdx"):
                    for m in names:
                        s_, null = sc[m]
                        acc[(s, a, meth)][m].append(ev.conformal_counts(D, scans, s_, null, y, a, meth))
    out = {}
    for (s, a, meth), d in acc.items():
        scans = np.nonzero(D.scan_sets[s])[0]
        rows = {m: np.sum(v, axis=0) for m, v in d.items()}
        res = ev.conf_summary(D, rows, scans, a, SEED + 11)
        for m, v in d.items():
            r_ = res[m]
            for key in ("frac_scans_fdp_gt_alpha", "frac_scans_fdp_gt_alpha_ci95", "mean_scan_fdp"):
                r_.pop(key, None)
            r_["frac_scans_never_selecting"] = r_.pop("frac_scans_selecting_nothing")
            fdp = np.array([np.where(r[:, 0] > 0, r[:, 1] / np.maximum(r[:, 0], 1), 0.0) for r in v])
            r_["frac_scans_fdp_gt_alpha_per_draw"] = ev._r(float((fdp > a).mean()))
            r_["mean_scan_fdp_per_draw"] = ev._r(float(fdp.mean()))
            pw = [ev.conf_metrics(r, a)[0] for r in v]
            r_["power_split_range"] = [ev._r(min(pw)), ev._r(max(pw))]
        out[f"{s}|{meth}|alpha={a}"] = res
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=os.path.join(HERE, ".cache", "features_v31.npz"))
    ap.add_argument("--tag", default="2026-10-21")
    ap.add_argument("--records-dir", default=ev.RECORDS)
    ap.add_argument("--quick", action="store_true", help="debug: B=200, 3 splits, 3 shuffles")
    ap.add_argument("--debug-no-gate", action="store_true", help="debug on synthetic caches only")
    a = ap.parse_args()
    if a.quick:
        ev.N_BOOT, ev.N_SPLITS_XCOHORT, ev.N_SHUFFLE = 200, 3, 3
    t0 = time.time()
    D = Data31(a.cache)
    y = D.labels["lenient"]
    log = []

    def say(m):
        print(m, flush=True)
        log.append(m)

    rec = {"protocol": "docs/research/lesion-detector-v3/PROTOCOL-v3.1.md", "seed": SEED, "n_boot": ev.N_BOOT,
           "cache": {"path": os.path.relpath(a.cache, ev.ROOT),
                     "sha256": hashlib.sha256(open(a.cache, "rb").read()).hexdigest()},
           "feature_sets": {k: list(ev.FEATURE_SETS[k]) for k in ("GR", "GR-noENS", "ENS-only", "V31", "V3P+ENS+LST")}}

    # ---------------- gate + descriptives
    gate = {nm: {"scans": int(D.scan_sets[nm].sum()) if nm in D.scan_sets else None,
                 "patients": len(set(D.s_patient[D.scan_sets[nm]])) if nm in D.scan_sets else None,
                 "candidates": int(D.sets[nm].sum()), "false": int((D.sets[nm] & ~y).sum()),
                 "false_rate": ev._r(float((D.sets[nm] & ~y).sum() / max(D.sets[nm].sum(), 1))),
                 "ens_features_missing": int(np.isnan(D.ens[D.sets[nm]]).sum())}
            for nm in ("M", "L10") + SITES}
    ok = (gate["M"]["candidates"], gate["M"]["false"], gate["L10"]["candidates"], gate["L10"]["false"]) == (3866, 1348, 534, 94)
    gate["M_L10_match_v3"] = bool(ok)
    for s in SITES:
        sc = D.sets[s]
        nvox = np.exp(D.X[sc, D.col["log_volume"]])
        gate[s]["single_voxel_candidate_share"] = ev._r(float((np.round(nvox) <= 1).mean()))
    rec["gate_and_descriptives"] = gate
    say(f"gate: {json.dumps(gate)}")
    if not ok and not a.debug_no_gate:
        raise SystemExit("MSLesSeg / Ljubljana-10 candidates differ from v3 — stop")
    for nm in ("TRAIN", "EXT"):
        if np.isnan(D.ens[D.sets[nm]]).any():
            raise SystemExit(f"fold-disagreement features missing in {nm} — stop")

    # ---------------- PRIMARY: pooled external
    say("primary: pooled external (MS3SEG + Muslim + PediMS), trained on M + L10 ...")
    sc, idx = ext_scores(D, y, EXT_MODELS, D.sets["TRAIN"], D.sets["EXT"])
    prim = ev.auc_table(D, sc, idx, y, site_strata(D), ref="RAW", ref2="ENS-RAW", seed=SEED + 31)
    prim_h3 = ev.auc_table(D, sc, idx, y, site_strata(D), ref="GR-noENS-LR", seed=SEED + 31)   # same resamples
    rec["primary_pooled_external"] = prim
    d = prim["GR-LR"]
    met = bool(d["delta_vs_RAW"] >= 0.05 and d["delta_vs_RAW_ci95"][0] is not None and d["delta_vs_RAW_ci95"][0] > 0)
    h2 = d["delta_vs_ENS-RAW_ci95"]
    h3 = prim_h3["GR-LR"]["delta_vs_GR-noENS-LR_ci95"]
    rec["criteria"] = {
        "primary_rule": "delta(GR-LR - RAW) >= 0.05 AND paired 95% CI lower bound > 0 (pooled external)",
        "primary_delta": d["delta_vs_RAW"], "primary_ci95": d["delta_vs_RAW_ci95"], "primary_met": met,
        "primary_statistically_positive": bool(d["delta_vs_RAW_ci95"][0] is not None and d["delta_vs_RAW_ci95"][0] > 0),
        "H2_delta_vs_ENS_RAW": d["delta_vs_ENS-RAW"], "H2_ci95": h2, "H2_met": bool(h2[0] is not None and h2[0] > 0),
        "H3_delta_vs_GR_noENS": prim_h3["GR-LR"]["delta_vs_GR-noENS-LR"], "H3_ci95": h3,
        "H3_met": bool(h3[0] is not None and h3[0] > 0)}
    for n in sc:
        say(f"  {n:12s} AUROC {prim[n]['auroc']} {prim[n]['ci95']}  dRAW {prim[n].get('delta_vs_RAW')} "
            f"{prim[n].get('delta_vs_RAW_ci95')}  dENS {prim[n].get('delta_vs_ENS-RAW')} {prim[n].get('delta_vs_ENS-RAW_ci95')}")
    say(f"  criteria: {json.dumps(rec['criteria'])}")

    # ---------------- per site
    per = {}
    for s in SITES:
        m = D.sets[s]
        keep = m[idx]
        per[s] = ev.auc_table(D, {k: v[keep] for k, v in sc.items()}, idx[keep], y, [m], ref="RAW", ref2="ENS-RAW",
                              seed=SEED + 32)
        say(f"  {s}: " + ", ".join(f"{k} {per[s][k]['auroc']}" for k in sc) + f" | n {per[s]['_n']}")
    rec["S_per_site_external"] = per

    # ---------------- H4: site signature M vs L10
    say("H4: site signature (M vs L10) ...")
    oof, sidx, slab = site_identity(D, SIG_FAMILIES, D.sets["M"], D.sets["L10"], SEED + 41)
    names, point, bs = separability_boot(D, oof, slab, sidx, [D.sets["M"], D.sets["L10"]], SEED + 42)
    h4 = {"site_identity_auroc": {n: ev._r(ev.auroc(oof[n], slab[sidx])) for n in names},
          "separability": {n: ev._r(p) for n, p in zip(names, point)}}
    comp = {}
    for new in ("F8_fold_disagreement", "F9_lstai_agreement"):
        for old in ("F1_flair_contrast", "F3_flair_texture", "F4_flair_boundary"):
            i, j = names.index(new), names.index(old)
            c_ = ev.ci(bs[:, i] - bs[:, j])
            comp[f"{new}_minus_{old}"] = {"delta": ev._r(point[i] - point[j]), "ci95": c_,
                                          "less_site_specific": bool(c_[1] is not None and c_[1] < 0)}
    h4["paired_separability_differences"] = comp
    h4["H4_met_F8"] = all(v["less_site_specific"] for k, v in comp.items() if k.startswith("F8"))
    h4["H4_met_F9"] = all(v["less_site_specific"] for k, v in comp.items() if k.startswith("F9"))
    rec["H4_site_signature_M_vs_L10"] = h4
    say(f"  {json.dumps(h4)}")

    # ---------------- H4b: M vs each new site, F8 vs GR-noENS (+ other grid-robust families)
    say("H4b: site signature (M vs each new site) ...")
    h4b = {}
    fam_b = {"F8_fold_disagreement": fv.F8, "GR-noENS": GR_BASE, "v2_prob": ev.V2_PROB,
             "persistence_GR": ("ps_surv_075", "ps_surv_090", "ps_log_merge_025", "ps_log_merge_010"),
             "log_volume_mm3": ("log_volume_mm3",)}
    for s in SITES:
        oofb, bidx, blab = site_identity(D, fam_b, D.sets["M"], D.sets[s], SEED + 51)
        nb, pb, bsb = separability_boot(D, oofb, blab, bidx, [D.sets["M"], D.sets[s]], SEED + 52)
        i, j = nb.index("F8_fold_disagreement"), nb.index("GR-noENS")
        c_ = ev.ci(bsb[:, i] - bsb[:, j])
        h4b[s] = {"site_identity_auroc": {n: ev._r(ev.auroc(oofb[n], blab[bidx])) for n in nb},
                  "F8_minus_GRnoENS_separability": {"delta": ev._r(pb[i] - pb[j]), "ci95": c_},
                  "F8_less_site_specific": bool(c_[1] is not None and c_[1] < 0)}
        say(f"  {s}: {json.dumps(h4b[s])}")
    rec["H4b_site_signature_M_vs_new_sites"] = h4b

    # ---------------- M <-> L10 (not confirmatory)
    say("M <-> L10 (re-uses v3 data; not confirmatory) ...")
    ml_models = ("V3-LR", "V31-LR", "V3P+ENS+LST-LR", "GR-LR", "V3P-LR")
    scl, idl = ev.loco(D, ml_models, y)
    scl["ENS-RAW"] = D.ens[idl]
    ml = {"pooled_loco": ev.auc_table(D, scl, idl, y, [D.sets["M"], D.sets["L10"]], ref="RAW", ref2="V3-LR", seed=SEED + 61)}
    nA = int(D.sets["L10"].sum())
    for nm, sl_, mk in (("A_M_to_L10", slice(0, nA), D.sets["L10"]), ("B_L10_to_M", slice(nA, None), D.sets["M"])):
        ml[nm] = ev.auc_table(D, {k: v[sl_] for k, v in scl.items()}, idl[sl_], y, [mk], ref="RAW", ref2="V3-LR",
                              seed=SEED + 62)
    scw, idw = ev.within_cohort(D, ml_models, y, "M", 5)
    scw["ENS-RAW"] = D.ens[idw]
    ml["within_M_cv"] = ev.auc_table(D, scw, idw, y, [D.sets["M"]], ref="RAW", ref2="V3-LR", seed=SEED + 63)
    # does F8 + F9 add on top of the prob-only set? (same resamples)
    ml["within_M_cv_vs_V3P"] = {k: v for k, v in ev.auc_table(D, scw, idw, y, [D.sets["M"]], ref="V3P-LR",
                                                              seed=SEED + 63).items() if k in ("V3P+ENS+LST-LR", "_n")}
    rec["S_M_L10_not_confirmatory"] = ml
    for k in ("pooled_loco", "A_M_to_L10", "B_L10_to_M", "within_M_cv"):
        say(f"  {k}: " + ", ".join(f"{m} {ml[k][m]['auroc']}" for m in scl))

    # ---------------- external conformal
    say("external conformal (20 splits) ...")
    rec["S_conformal_external"] = conformal_external(D, y, ("GR-LR",))
    for s in SITES:
        r_ = rec["S_conformal_external"][f"{s}|bh|alpha=0.2"]
        say(f"  {s} bh a=0.2: " + ", ".join(f"{m} power {v['power']} FDR {v['micro_fdr']} exc {v['frac_scans_fdp_gt_alpha_per_draw']}"
                                           for m, v in r_.items()))

    # ---------------- adversarial
    say("B1 shuffle-label null ...")
    nul = []
    for r in range(ev.N_SHUFFLE):
        s_, i_ = ext_scores(D, y, ("GR-LR",), D.sets["TRAIN"], D.sets["EXT"], np.random.RandomState(SEED + 2000 + r))
        nul.append(ev.auroc(s_["GR-LR"], y[i_]))
    rec["B1_shuffle_null_external"] = {"mean": ev._r(np.mean(nul)), "min": ev._r(min(nul)), "max": ev._r(max(nul))}
    say(f"  {rec['B1_shuffle_null_external']}")
    rec["B2_integrity"] = "assert_disjoint on every train/calibration/test split; GT-free features (unit tests)"

    say("B4 label definitions ...")
    b4 = {}
    for lab in ("strict", "anyvox"):
        yl = D.labels[lab]
        s_, i_ = ext_scores(D, yl, ("GR-LR",), D.sets["TRAIN"], D.sets["EXT"])
        t = ev.auc_table(D, s_, i_, yl, site_strata(D), ref="RAW", ref2="ENS-RAW", seed=SEED + 71)
        b4[lab] = t
        say(f"  {lab}: " + ", ".join(f"{k} {t[k]['auroc']} dRAW {t[k].get('delta_vs_RAW')} {t[k].get('delta_vs_RAW_ci95')}" for k in s_))
    rec["B4_label_definitions_external"] = b4

    say("B5 refit variance ...")
    tp = np.array(sorted(set(D.patient[D.sets["TRAIN"]])))
    fset, fitter = ev.MODELS["GR-LR"]
    cols = [D.col[c] for c in ev.FEATURE_SETS[fset]]
    te = D.sets["EXT"]
    raw_ext = ev.auroc(D.raw[te], y[te])
    refit = []
    for r in range(50):
        rng = np.random.RandomState(SEED + 3000 + r)
        pick = rng.choice(tp, len(tp), replace=True)
        rows = np.concatenate([np.nonzero(D.sets["TRAIN"] & (D.patient == p))[0] for p in pick])
        f = fitter(D.X[rows][:, cols], y[rows].astype(int))
        refit.append(ev.auroc(f(D.F(fset, te)), y[te]))
    rec["B5_refit_variance_external"] = {"auroc_mean": ev._r(np.mean(refit)), "p2.5_p97.5": ev.ci(refit),
                                         "raw_auroc": ev._r(raw_ext),
                                         "frac_refits_below_raw": ev._r(float(np.mean(np.array(refit) < raw_ext)))}
    say(f"  {rec['B5_refit_variance_external']}")

    say("B6 contamination reference ...")
    b6 = {}
    for nm in ("L10", "Ltr"):
        s_, i_ = ext_scores(D, y, ("GR-LR",), D.sets["M"], D.sets[nm])
        b6[nm] = ev.auc_table(D, s_, i_, y, [D.sets[nm]], ref="RAW", ref2="ENS-RAW", seed=SEED + 81)
        say(f"  M -> {nm}: " + ", ".join(f"{k} {b6[nm][k]['auroc']}" for k in s_))
    rec["B6_contamination"] = b6

    say("B7 KS (M vs each site, GR features) ...")
    b7 = {}
    for s in SITES:
        row = {}
        for c in ev.FEATURE_SETS["GR"]:
            j = D.col[c]
            for cls, cm in (("true", y), ("false", ~y)):
                u, v = D.X[D.sets["M"] & cm, j], D.X[D.sets[s] & cm, j]
                u, v = u[np.isfinite(u)], v[np.isfinite(v)]
                row[f"{c}|{cls}"] = ev._r(ks_2samp(u, v).statistic, 3) if u.size and v.size else None
        b7[s] = row
    rec["B7_ks_M_vs_site"] = b7

    say("B8 resolution: candidates with >= 3 voxels ...")
    b8 = {}
    nvox = np.round(np.exp(D.X[:, D.col["log_volume"]]))
    keep = nvox[idx] >= 3
    b8["pooled_ge3vox"] = ev.auc_table(D, {k: v[keep] for k, v in sc.items()}, idx[keep], y, site_strata(D),
                                       ref="RAW", ref2="ENS-RAW", seed=SEED + 91)
    say("  " + ", ".join(f"{k} {b8['pooled_ge3vox'][k]['auroc']} dRAW {b8['pooled_ge3vox'][k].get('delta_vs_RAW')}" for k in sc))
    rec["B8_resolution"] = b8

    rec["runtime_s"] = round(time.time() - t0, 1)
    os.makedirs(a.records_dir, exist_ok=True)
    out = os.path.join(a.records_dir, f"{a.tag}_lesion_detector_v31_evaluation.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1)
    with open(out.replace(".json", "_output.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(log) + "\n")
    say(f"wrote {out} in {rec['runtime_s']} s")


if __name__ == "__main__":
    main()
