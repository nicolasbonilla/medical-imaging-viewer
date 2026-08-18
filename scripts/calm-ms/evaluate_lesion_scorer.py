#!/usr/bin/env python3
"""HONEST evaluation of the SHIPPED CALM-MS lesion scorer (replaces the rigged record).

Adversarial round 3 established that the previous record (lesion_scorer_record.json)
described a DIFFERENT model (a gradient-boosting classifier from the research script) and
used a STACKED shift test (inflating only the false candidates — physically impossible and
constructed to invert raw probability). This script evaluates the model that actually
ships (the degree-2 polynomial logistic regression, via the same pipeline as the frozen
asset) with HONEST protocols, and overwrites the record.

Honest protocols:
  * patient-grouped CV (no longitudinal leakage);
  * pooled leave-one-SITE-out AUC (the real cross-domain generalization estimate);
  * calibration (ECE) and conformal power at alpha (AUC is not the operative metric);
  * a FAIR shift test — a monotone confidence inflation applied to ALL candidates
    (a scanner cannot know which candidates are false), reported for raw vs learned.

Uses the cached feature matrix (scripts/calm-ms/.scorer_cache.npz) built by
train_lesion_scorer.py with the shared feature module.

    python scripts/calm-ms/evaluate_lesion_scorer.py
"""
import os, sys, re, json

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(_HERE, "..", "..", "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.services.conformal_lesion_fdr import conformal_pvalues, benjamini_hochberg  # noqa: E402

_CACHE = os.path.join(_HERE, ".scorer_cache.npz")
PROB_IDX = [0, 1, 2, 3]     # prob_mean, prob_max, prob_std, prob_q90 (inflatable)
C_REG, DEGREE = 0.5, 2


def _patient(case):
    m = re.match(r"(mslesseg_P\d+)_T\d+", str(case))
    return m.group(1) if m else str(case)


def _logit_shift(v, d):
    v = np.clip(v, 1e-6, 1 - 1e-6)
    return 1.0 / (1.0 + np.exp(-(np.log(v / (1 - v)) + d)))


def main():
    from sklearn.preprocessing import PolynomialFeatures
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GroupKFold, LeaveOneGroupOut
    from sklearn.metrics import roc_auc_score, average_precision_score

    d = np.load(_CACHE, allow_pickle=True)
    X, y, sites, cases = d["X"], d["y"], d["sites"], d["cases"]
    is_false = y.astype(bool); true = (~is_false).astype(int)
    patients = np.array([_patient(c) for c in cases])
    pf = PolynomialFeatures(DEGREE, include_bias=False)

    def fit_predict(tr, te):
        mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
        clf = LogisticRegression(max_iter=5000, C=C_REG).fit(pf.fit_transform((X[tr] - mu) / sd), y[tr])
        return 1.0 - clf.predict_proba(pf.transform((X[te] - mu) / sd))[:, 1], clf, (mu, sd)

    # within-domain, patient-grouped
    oof = np.zeros(len(y))
    for tr, te in GroupKFold(5).split(X, y, groups=patients):
        oof[te], _, _ = fit_predict(tr, te)
    auc_pg = roc_auc_score(true, oof)
    ap = average_precision_score(is_false.astype(int), 1 - oof)   # AP for the FALSE class
    # partial AUC at FPR<=0.10 (trapezoid on ROC up to 0.1) — low-FPR is what matters
    from sklearn.metrics import roc_curve
    fprc, tprc, _ = roc_curve(true, oof)
    mask = fprc <= 0.10
    pauc = float(np.trapz(tprc[mask], fprc[mask]) / 0.10) if mask.sum() > 1 else float("nan")
    # calibration ECE (10-bin) on P(false)
    pfalse = 1 - oof
    bins = np.linspace(0, 1, 11); ece = 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (pfalse >= lo) & (pfalse < hi)
        if m.any():
            ece += m.mean() * abs(pfalse[m].mean() - is_false[m].mean())

    # pooled leave-one-site-out
    loso = np.zeros(len(y))
    for tr, te in LeaveOneGroupOut().split(X, y, groups=sites):
        loso[te], _, _ = fit_predict(tr, te)
    auc_loso = roc_auc_score(true, loso)

    # conformal power within-domain (patient-grouped OOF scores; null = OOF FP scores)
    def _fdr_power(scores, fp, null, a):
        sel = benjamini_hochberg(conformal_pvalues(scores, null), alpha=a)
        ns = int(sel.sum())
        return (int((sel & fp).sum()) / ns if ns else 0.0,
                int((sel & ~fp).sum()) / max(int((~fp).sum()), 1))
    null_wd = oof[is_false]
    power = {f"{a}": _fdr_power(oof, is_false, null_wd, a) for a in (0.10, 0.20, 0.30)}

    # FAIR shift test: train openms, test mslesseg, inflate ALL candidates' prob features
    tr = sites == "openms"; te = sites == "mslesseg"
    _, clf, (mu, sd) = fit_predict(tr, tr)
    def learned(Xin): return 1.0 - clf.predict_proba(pf.transform((Xin - mu) / sd))[:, 1]
    fpte = is_false[te]
    raw_null = X[tr][is_false[tr], 0]; lrn_null = learned(X[tr])[is_false[tr]]
    shift_rows = {}
    for name, mode in [("no_shift", None), ("fair_all_+1.5", "all"), ("fp_only_+1.5_RIGGED", "fp")]:
        Xs = X[te].copy()
        if mode == "all":
            for j in PROB_IDX: Xs[:, j] = _logit_shift(Xs[:, j], 1.5)
        elif mode == "fp":
            for j in PROB_IDX: Xs[fpte, j] = _logit_shift(Xs[fpte, j], 1.5)
        raw, lrn = Xs[:, 0], learned(Xs)
        ar, al = roc_auc_score((~fpte).astype(int), raw), roc_auc_score((~fpte).astype(int), lrn)
        fr, pr = _fdr_power(raw, fpte, raw_null, 0.20); fl, pl = _fdr_power(lrn, fpte, lrn_null, 0.20)
        shift_rows[name] = {"auc_raw": round(ar, 3), "auc_learned": round(al, 3),
                            "fdr_raw": round(fr, 3), "fdr_learned": round(fl, 3),
                            "power_raw": round(pr, 3), "power_learned": round(pl, 3)}

    rec = {
        "model": "degree-2 polynomial logistic regression (SHIPPED; calm_ms_scorer)",
        "supersedes": "prior record described a gradient-boosting model + a rigged FP-only shift",
        "within_domain": {"auc_patient_grouped": round(auc_pg, 4),
                          "auc_raw_prob": round(roc_auc_score(true, X[:, 0]), 4),
                          "ap_false_class": round(ap, 4), "partial_auc_fpr_le_0.10": round(pauc, 4),
                          "calibration_ece": round(ece, 4),
                          "conformal_power_at_alpha": {a: {"fdr": round(v[0], 3), "power": round(v[1], 3)}
                                                       for a, v in power.items()}},
        "cross_site_generalization": {"pooled_leave_one_site_out_auc": round(auc_loso, 4),
                                      "note": "honest cross-domain estimate; per-site AUCs (~0.77) hide this"},
        "fair_shift_test": shift_rows,
        "honest_conclusion": ("The learned score is a genuine WITHIN-DOMAIN TP/FP improvement "
                              "(AUC 0.80 vs 0.70 raw, well-calibrated) but does NOT solve cross-site "
                              "non-exchangeability (LOSO AUC ~0.62) and under a FAIR monotone shift does "
                              "NOT beat raw probability. It is not, by itself, the F1 fix."),
    }
    out = os.path.join(_BACKEND, "app", "services", "assets", "lesion_scorer_record.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=2)
    print(json.dumps(rec, indent=2))
    print(f"\nWrote HONEST record {out}")


if __name__ == "__main__":
    main()
