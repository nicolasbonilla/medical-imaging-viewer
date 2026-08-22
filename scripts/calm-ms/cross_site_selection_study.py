#!/usr/bin/env python3
"""CALM-MS — honest cross-site lesion-selection study (supersedes the flawed WCS prototype).

Two adversarial audits demolished an earlier `wcs_experiment.py`: (a) it used the
calibration site's candidates BOTH to fit the learned scorer AND as the conformal null
(double-use leak) — which manufactured its headline power; (b) plain BH on marginal
weighted conformal p-values is NOT Weighted Conformalized Selection and carries no FDR
guarantee; (c) the shift is plausibly *posterior drift* (P(true|x) changes across
scanners), a regime weighted-covariate methods cannot fix. Both agreed the honest
deployable answer is likely *site-conditional (Mondrian) calibration with a few labelled
cases per new site*.

This study answers three decisive questions HONESTLY, with leak-free protocols and
repetition-based intervals:

  Q1 (diagnostic): is the cross-site shift covariate-only or POSTERIOR DRIFT? — measured by
     cross-site calibration error of P(true|x) vs within-site.
  Q2: does leak-free weighted-conformal (marginal approximation, NO finite-sample
     guarantee — labelled as such) deliver controlled-and-powerful selection cross-site?
  Q3: how many labelled cases from the NEW site does site-conditional (Mondrian) selection
     need to control FDR with usable power? — a k-shot sweep with intervals.

Leak fix: the learned scorer is CROSS-FIT on the calibration site (K-fold out-of-fold), so
the null uses OOF scores; the test site is scored by a scorer trained on all calib data
(out-of-sample). No test labels enter any selection procedure (only evaluation).

    python scripts/calm-ms/cross_site_selection_study.py
"""
import os, sys, json, re

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(_HERE, "..", "..", "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


def _subject_of(case: str) -> str:
    """Patient id for patient-level (leak-free) grouping. MSLesSeg cases are
    `mslesseg_P<n>_T<k>`; a subject key groups a patient's timepoints so they never
    split across the calibration slice and the eval set (the k-shot leak). openms is
    single-timepoint → subject == case."""
    m = re.match(r"mslesseg_(P\d+)(?:_|$)", str(case))
    return "mslesseg_" + m.group(1) if m else str(case)

_CACHE = os.path.join(_HERE, ".scorer_cache.npz")
ALPHAS = (0.10, 0.20, 0.30)
PROB_MEAN_IDX = 0
K_SHOTS = (2, 5, 10, 20)
N_REPEAT = 30
SEED = 12345


def _bh(p, alpha):
    p = np.asarray(p, float); n = p.size
    if n == 0:
        return np.zeros(0, bool)
    order = np.argsort(p)
    passed = p[order] <= alpha * (np.arange(1, n + 1) / n)
    k = np.max(np.where(passed)[0]) + 1 if passed.any() else 0
    sel = np.zeros(n, bool)
    if k:
        sel[order[:k]] = True
    return sel


def _wpvals(s_test, s_null, w_null, w_test):
    s_null = np.asarray(s_null); w_null = np.asarray(w_null); denom = w_null.sum()
    return np.array([(wj + w_null[s_null >= s].sum()) / (wj + denom)
                     for s, wj in zip(s_test, w_test)])


def _fp(sel, isf):
    ns = int(sel.sum())
    return (int((sel & isf).sum()) / ns if ns else 0.0,
            int((sel & ~isf).sum()) / max(int((~isf).sum()), 1))


def _ece(pfalse, isf, bins=10):
    edges = np.linspace(0, 1, bins + 1); e = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (pfalse >= lo) & (pfalse < hi)
        if m.any():
            e += m.mean() * abs(pfalse[m].mean() - isf[m].mean())
    return float(e)


def main():
    from sklearn.preprocessing import PolynomialFeatures
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedGroupKFold

    d = np.load(_CACHE, allow_pickle=True)
    X, y, sites, cases = d["X"], d["y"], d["sites"], d["cases"]
    subjects = np.array([_subject_of(c) for c in cases])   # patient-level grouping key
    isf = y.astype(bool)
    pf = PolynomialFeatures(2, include_bias=False)
    rng = np.random.RandomState(SEED)
    out = {"alphas": list(ALPHAS), "pairs": {}}

    def scorer_oof(Xc, yc, groups):
        """Cross-fit P(false) on the calib site -> honest OOF scores + a full-fit model.
        Folds are SUBJECT-grouped (StratifiedGroupKFold) so a patient's timepoints never
        span train/OOF — the OOF null is patient-clean, not just candidate-out-of-fold."""
        mu, sd = Xc.mean(0), Xc.std(0) + 1e-9
        oof = np.zeros(len(yc))
        for tr, te in StratifiedGroupKFold(5, shuffle=True, random_state=0).split(Xc, yc, groups):
            m = LogisticRegression(max_iter=4000, C=0.5).fit(pf.fit_transform((Xc[tr] - mu) / sd), yc[tr])
            oof[te] = m.predict_proba(pf.transform((Xc[te] - mu) / sd))[:, 1]
        full = LogisticRegression(max_iter=4000, C=0.5).fit(pf.fit_transform((Xc - mu) / sd), yc)
        return 1.0 - oof, full, (mu, sd)   # learned score = 1 - P(false)

    for calib, test in [("openms", "mslesseg"), ("mslesseg", "openms")]:
        c, t = sites == calib, sites == test
        learned_oof, full, (mu, sd) = scorer_oof(X[c], y[c], subjects[c])
        def score(Xin): return 1.0 - full.predict_proba(pf.transform((Xin - mu) / sd))[:, 1]
        learned_te, fte = score(X[t]), isf[t]
        cf = isf[c]                                    # calib false mask
        null_oof = learned_oof[cf]                     # honest (leak-free) null

        # Q1 posterior-drift diagnostic: cross-site vs within-site calibration of P(false|x)
        pfalse_te = 1.0 - learned_te
        ece_cross = _ece(pfalse_te, fte)
        ece_within = _ece(1.0 - learned_oof, isf[c])   # OOF within calib
        # per-score-bin false-rate shift (posterior drift signature): compare P(false|score-bin)
        drift_bins = []
        for lo, hi in [(0.0, 0.3), (0.3, 0.6), (0.6, 0.85), (0.85, 1.0)]:
            sc = 1.0 - learned_oof; st = pfalse_te
            mc = (sc >= lo) & (sc < hi); mt = (st >= lo) & (st < hi)
            if mc.sum() > 5 and mt.sum() > 5:
                drift_bins.append({"bin": f"{lo}-{hi}", "calib_false_rate": round(isf[c][mc].mean(), 3),
                                   "test_false_rate": round(fte[mt].mean(), 3)})

        # domain-classifier weights (marginal density ratio) for the weighted-approx method
        Xd = np.vstack([X[c], X[t]]); yd = np.r_[np.zeros(c.sum()), np.ones(t.sum())]
        md, sdd = Xd.mean(0), Xd.std(0) + 1e-9
        dom = LogisticRegression(max_iter=4000, C=1.0).fit(pf.fit_transform((Xd - md) / sdd), yd)
        def wfun(Xin):
            q = np.clip(dom.predict_proba(pf.transform((Xin - md) / sdd))[:, 1], 1e-3, 1 - 1e-3)
            return q / (1 - q)
        w_null, w_te = wfun(X[c])[cf], wfun(X[t])
        ess = float((w_null.sum() ** 2) / (w_null ** 2).sum())

        pair = {"posterior_drift": {"ece_within_site": round(ece_within, 3),
                                    "ece_cross_site": round(ece_cross, 3),
                                    "per_score_bin_false_rate": drift_bins},
                "weighted_ess": round(ess, 1), "n_null": int(cf.sum()),
                "methods": {}}
        # Q2: leak-free naive vs weighted (marginal approx; no guarantee) — point estimates
        for a in ALPHAS:
            naive = _fp(_bh(_wpvals(learned_te, null_oof, np.ones(cf.sum()), np.ones(len(learned_te))), a), fte)
            wgt = _fp(_bh(_wpvals(learned_te, null_oof, w_null, w_te), a), fte)
            pair["methods"][f"a={a}"] = {"naive_learned": {"fdr": round(naive[0], 3), "power": round(naive[1], 3)},
                                         "weighted_approx": {"fdr": round(wgt[0], 3), "power": round(wgt[1], 3)}}

        # Q3: k-shot site-conditional (Mondrian) — sample k test SUBJECTS (patients) as the
        # labelled slice, their false scores are the test null, select on the remaining
        # test candidates. Sampling SUBJECTS (not cases) prevents a patient's T1 landing in
        # the calibration slice while their T2 stays in the eval set (the k-shot leak).
        sub_t = subjects[t]
        test_subjects = np.unique(sub_t)
        kshot = {}
        for k in K_SHOTS:
            if k >= len(test_subjects):
                continue
            per_alpha = {a: {"fdr": [], "power": []} for a in ALPHAS}
            for _ in range(N_REPEAT):
                slice_subjects = set(rng.choice(test_subjects, size=k, replace=False).tolist())
                in_slice = np.array([s in slice_subjects for s in sub_t])
                null_k = learned_te[in_slice & fte]                 # labelled test-slice false scores
                if null_k.size < 3:
                    continue
                ev = ~in_slice
                for a in ALPHAS:
                    sel = _bh(_wpvals(learned_te[ev], null_k, np.ones(null_k.size), np.ones(ev.sum())), a)
                    f, p = _fp(sel, fte[ev])
                    per_alpha[a]["fdr"].append(f); per_alpha[a]["power"].append(p)
            kshot[f"k={k}"] = {f"a={a}": {"fdr_mean": round(float(np.mean(per_alpha[a]["fdr"])), 3),
                                          "fdr_sd": round(float(np.std(per_alpha[a]["fdr"])), 3),
                                          "power_mean": round(float(np.mean(per_alpha[a]["power"])), 3)}
                               for a in ALPHAS}
        pair["site_conditional_kshot"] = kshot
        out["pairs"][f"{calib}->{test}"] = pair

        print(f"\n=== calibrate {calib} -> deploy {test} ===")
        print(f"  Q1 posterior-drift: ECE within {pair['posterior_drift']['ece_within_site']} "
              f"vs cross-site {pair['posterior_drift']['ece_cross_site']}  "
              f"| per-bin false-rate: {drift_bins}")
        print(f"  Q2 leak-free (weighted ESS {ess:.0f}/{int(cf.sum())} null):")
        for a in ALPHAS:
            m = pair["methods"][f"a={a}"]
            print(f"     a={a}: naive FDR {m['naive_learned']['fdr']:.2f}/pow {m['naive_learned']['power']:.2f}"
                  f" | weighted FDR {m['weighted_approx']['fdr']:.2f}/pow {m['weighted_approx']['power']:.2f}")
        print(f"  Q3 site-conditional k-shot (FDR mean+-sd / power, {N_REPEAT} samples):")
        for k, v in kshot.items():
            cells = " | ".join(f"a={a.split('=')[1]}: {v[a]['fdr_mean']:.2f}+-{v[a]['fdr_sd']:.2f}/{v[a]['power_mean']:.2f}"
                               for a in [f"a={al}" for al in ALPHAS])
            print(f"     {k:5s}: {cells}")

    rec = os.path.join(_BACKEND, "app", "services", "assets", "cross_site_selection_record.json")
    with open(rec, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print(f"\nWrote {rec}")


if __name__ == "__main__":
    main()
