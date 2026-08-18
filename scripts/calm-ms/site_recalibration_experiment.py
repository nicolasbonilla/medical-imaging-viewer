#!/usr/bin/env python3
"""F1 fix — DEMONSTRATION: site-conditional (Mondrian) conformal recalibration.

Adversarial round 2 proved (synthetically) that a frozen pooled null breaks the
lesion-FDR guarantee when a new case's FALSE-candidate scores are not exchangeable
with it (a label-shift the OOD monitor cannot see). The correct fix is class/site-
conditional conformal: judge a case against the null of ITS OWN site, re-estimated
from a small labelled slice per site (Vovk Mondrian conformal; Tibshirani et al. 2019
covariate-shift conformal).

This script tests the claim on REAL data. The two FLAMeS cohorts are two domains/sites
with (potentially) different FALSE-positive score regimes:
    openms   = open_ms_data (single source, 3-rater consensus)   -> "site O"
    mslesseg = MSLesSeg (multi-site)                              -> "site M"

It measures realized lesion-FDR (using ground truth, at experiment time only) under
each (null-source x test-site) combination:
  * DIAGONAL  (test site == null site, leave-one-case-out)  -> should be <= alpha
  * OFF-DIAG  (test site  != null site)                     -> the F1 break, if the
                                                               FP regimes differ
  * POOLED    (the shipped one-size-fits-all null)           -> the status quo

If the off-diagonal / pooled FDR exceeds alpha while the diagonal (site-conditional)
FDR does not, F1 is real on real data AND site recalibration closes it.

    python scripts/calm-ms/site_recalibration_experiment.py
"""
import os, sys, glob, json

import numpy as np
import nibabel as nib

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(_HERE, "..", "..", "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.services.calm_ms_inference import extract_lesion_candidates, label_candidates_tp  # noqa: E402
from app.services.conformal_lesion_fdr import conformal_pvalues, benjamini_hochberg      # noqa: E402

THRESHOLD, MIN_VOL, SCORE, SPACING = 0.5, 3.0, "mean", (1.0, 1.0, 1.0)
ALPHAS = (0.30, 0.20, 0.10)
SITES = {"openms": "openms-flames", "mslesseg": "mslesseg-flames"}
_CACHE = os.path.join(_HERE, ".site_cache.npz")


def _extract_all():
    """Per case: (site, score array, is_false boolean array). Cached to disk."""
    if os.path.exists(_CACHE):
        d = np.load(_CACHE, allow_pickle=True)
        return list(d["cases"])
    cases = []
    for site, sub in SITES.items():
        pairs = sorted(glob.glob(os.path.join("data", "cohorts", sub, "*_prob.nii.gz")))
        for i, prob_path in enumerate(pairs):
            case = os.path.basename(prob_path)[:-len("_prob.nii.gz")]
            gt_path = os.path.join(os.path.dirname(prob_path), case + "_gt.nii.gz")
            if not os.path.exists(gt_path):
                continue
            prob = np.asarray(nib.load(prob_path).get_fdata(), dtype=np.float32)
            gt = (np.asarray(nib.load(gt_path).get_fdata()) > 0).astype(np.uint8)
            labeled, cands = extract_lesion_candidates(prob, THRESHOLD, SPACING,
                                                       min_volume_mm3=MIN_VOL, score=SCORE)
            if not cands:
                continue
            is_tp = label_candidates_tp(labeled, cands, gt, min_overlap=0.0)
            scores = np.array([c.score for c in cands], dtype=float)
            is_false = np.array([not is_tp[c.label] for c in cands], dtype=bool)
            cases.append({"case": case, "site": site, "scores": scores, "is_false": is_false})
            print(f"  [{site}] {case}: {len(cands)} cand, {int(is_false.sum())} false", end="\r")
    print()
    np.savez_compressed(_CACHE, cases=np.array(cases, dtype=object))
    return cases


def _realized_fdr(test_cases, null_scores, alpha):
    """Micro- and macro-averaged realized FDR over test_cases judged against a FIXED
    null (used for the off-diagonal cross-site and the pooled/shipped null; the
    site-conditional diagonal is computed with per-case leave-one-out in main)."""
    tot_sel, tot_false_sel, per_case = 0, 0, []
    for tc in test_cases:
        p = conformal_pvalues(tc["scores"], null_scores)
        sel = benjamini_hochberg(p, alpha=alpha)
        n_sel = int(sel.sum())
        n_false_sel = int((sel & tc["is_false"]).sum())
        tot_sel += n_sel
        tot_false_sel += n_false_sel
        if n_sel:
            per_case.append(n_false_sel / n_sel)
    micro = (tot_false_sel / tot_sel) if tot_sel else 0.0
    macro = float(np.mean(per_case)) if per_case else 0.0
    return micro, macro, tot_sel


def _site_null(cases, site, exclude_case=None):
    return np.concatenate([c["scores"][c["is_false"]] for c in cases
                           if c["site"] == site and c["case"] != exclude_case]) \
        if any(c["site"] == site for c in cases) else np.array([])


def main():
    print("Extracting candidates + TP/FP labels over the two sites (cached) ...")
    cases = _extract_all()
    by_site = {s: [c for c in cases if c["site"] == s] for s in SITES}
    for s in SITES:
        fp = np.concatenate([c["scores"][c["is_false"]] for c in by_site[s]])
        tp = np.concatenate([c["scores"][~c["is_false"]] for c in by_site[s]])
        print(f"  site {s:9s}: {len(by_site[s]):3d} cases | FP scores n={fp.size} "
              f"mean={fp.mean():.3f} q10={np.quantile(fp,0.1):.3f} | TP n={tp.size} mean={tp.mean():.3f}")

    # Do the FP regimes actually differ between sites? (the exchangeability question)
    from scipy.stats import ks_2samp
    fp_o = np.concatenate([c["scores"][c["is_false"]] for c in by_site["openms"]])
    fp_m = np.concatenate([c["scores"][c["is_false"]] for c in by_site["mslesseg"]])
    ks = ks_2samp(fp_o, fp_m)
    print(f"\nFP-score distribution shift between sites: KS D={ks.statistic:.3f} p={ks.pvalue:.2e}"
          f"  ({'DIFFERENT (exchangeability broken cross-site)' if ks.pvalue < 0.05 else 'not distinguishable'})")

    pooled_null = np.concatenate([fp_o, fp_m])
    results = {}
    print("\nRealized micro-FDR  (rows = NULL source, cols = TEST site):")
    for alpha in ALPHAS:
        print(f"\n  alpha = {alpha:.2f}")
        header = "    {:14s}".format("null \\ test") + "".join(f"{s:>12s}" for s in SITES)
        print(header)
        for null_site in list(SITES) + ["POOLED"]:
            row = f"    {null_site:14s}"
            for test_site in SITES:
                if null_site == "POOLED":
                    micro, macro, nsel = _realized_fdr(by_site[test_site], pooled_null, alpha)
                elif null_site == test_site:
                    # site-conditional, leave-one-case-out (honest diagonal)
                    micros = []
                    tot_sel = tot_false = 0
                    for tc in by_site[test_site]:
                        null = _site_null(cases, test_site, exclude_case=tc["case"])
                        p = conformal_pvalues(tc["scores"], null)
                        sel = benjamini_hochberg(p, alpha=alpha)
                        tot_sel += int(sel.sum()); tot_false += int((sel & tc["is_false"]).sum())
                    micro = (tot_false / tot_sel) if tot_sel else 0.0
                else:
                    micro, macro, nsel = _realized_fdr(by_site[test_site], _site_null(cases, null_site), alpha)
                row += f"{micro:12.3f}"
                results[f"{alpha}|{null_site}|{test_site}"] = round(micro, 4)
            print(row)

    # ---------------------------------------------------------------------------
    # SEVERE-SHIFT demonstration: a new site whose segmenter emits CONFIDENT false
    # positives (the clinically-likely, F1-dangerous scanner shift). We model it by
    # pushing ONLY the FALSE-candidate scores of the mslesseg cases up in logit space
    # (delta=1.5); the TRUE candidates are untouched, so the MIXED marginal barely
    # moves and the score-only OOD monitor is blind to it — exactly the F1 regime.
    def _logit_shift(s, delta):
        s = np.clip(s, 1e-6, 1 - 1e-6)
        return 1.0 / (1.0 + np.exp(-(np.log(s / (1 - s)) + delta)))

    DELTA = 1.5
    shifted = []
    for c in by_site["mslesseg"]:
        sc = c["scores"].copy()
        sc[c["is_false"]] = _logit_shift(sc[c["is_false"]], DELTA)   # inflate FP confidence only
        shifted.append({"case": c["case"], "site": "shifted", "scores": sc, "is_false": c["is_false"]})

    from app.services.conformal_ood import assess_ood
    from app.services.conformal_null_asset import get_null_asset
    ood_ref = get_null_asset().ood_reference
    n_ood_flag = sum(assess_ood(c["scores"], ood_ref).is_ood for c in shifted)
    fp_shifted = np.concatenate([c["scores"][c["is_false"]] for c in shifted])
    print("\n" + "=" * 74)
    print("SEVERE-SHIFT SITE (confident-FP inflation; TP untouched -> marginal ~unchanged)")
    print(f"  shifted-FP mean {fp_shifted.mean():.3f} (was {fp_m.mean():.3f}); "
          f"OOD monitor flags {n_ood_flag}/{len(shifted)} cases as OOD  "
          f"({'BLIND — F1 confirmed' if n_ood_flag < 0.2*len(shifted) else 'detects'})")
    def _counts(cases, null_fn, alpha):
        tot_sel = tot_false = tot_true = 0
        for tc in cases:
            null = null_fn(tc)
            sel = benjamini_hochberg(conformal_pvalues(tc["scores"], null), alpha=alpha)
            tot_sel += int(sel.sum())
            tot_false += int((sel & tc["is_false"]).sum())
            tot_true += int((sel & ~tc["is_false"]).sum())
        fdr = (tot_false / tot_sel) if tot_sel else 0.0
        return fdr, tot_sel, tot_true, tot_false

    n_true_total = int(sum((~c["is_false"]).sum() for c in shifted))
    print(f"  (site has {n_true_total} TRUE lesions total across {len(shifted)} cases)")
    shift_rec = {}
    for alpha in ALPHAS:
        f_p, s_p, tp_p, fp_p = _counts(shifted, lambda tc: pooled_null, alpha)
        f_s, s_s, tp_s, fp_s = _counts(
            shifted, lambda tc: np.concatenate([o["scores"][o["is_false"]] for o in shifted if o["case"] != tc["case"]]), alpha)
        print(f"  alpha={alpha:.2f}:")
        print(f"     POOLED null : FDR={f_p:.3f}{'  BREAKS' if f_p>alpha else ''}  "
              f"selected={s_p} (TP {tp_p}/{n_true_total}, FP {fp_p})")
        print(f"     SITE-cond   : FDR={f_s:.3f}{'  BREAKS' if f_s>alpha else ''}  "
              f"selected={s_s} (TP {tp_s}/{n_true_total}, FP {fp_s})  <- power collapses: score can't separate")
        shift_rec[f"{alpha}"] = {"pooled": {"fdr": round(f_p,4), "sel": s_p, "tp": tp_p, "fp": fp_p},
                                 "site_conditional": {"fdr": round(f_s,4), "sel": s_s, "tp": tp_s, "fp": fp_s}}

    rec = {"ks_fp_shift": {"D": round(float(ks.statistic), 4), "p": float(ks.pvalue)},
           "realized_micro_fdr": results, "alphas": list(ALPHAS),
           "severe_shift_demo": {"delta_logit": DELTA, "ood_flagged": f"{n_ood_flag}/{len(shifted)}",
                                 "by_alpha": shift_rec},
           "note": "diagonal = site-conditional leave-one-case-out; POOLED = shipped null; "
                   "severe_shift = confident-FP inflation, pooled-null vs site-conditional-null"}
    out = os.path.join(_BACKEND, "app", "services", "assets", "site_recalibration_record.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=2)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
