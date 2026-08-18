#!/usr/bin/env python3
"""CALM-MS v2 — learned lesion scorer research experiment. SUPERSEDED — see WARNING.

!!! RETRACTED / SUPERSEDED (2026-08-18, adversarial round 3) !!!
Two flaws invalidate this script's shift-robustness result:
  1. Its "load-bearing" shift inflates ONLY the FALSE candidates' probability features
     (a scanner cannot know which candidates are false; the shift inverts raw probability
     by construction) — a stacked deck. Under a FAIR monotone shift of all candidates the
     learned score does NOT beat raw probability.
  2. It hardcodes GRID=[182,218,182] but the cohort is 181-voxel, so its features differ
     slightly from the shared module (`calm_ms_lesion_features`) that ships.
The authoritative, honest evaluation of the SHIPPED model is
`scripts/calm-ms/evaluate_lesion_scorer.py` (record `assets/lesion_scorer_record.json`).
This file is retained only for provenance of the retracted result; do not cite its numbers.

Original (superseded) description follows.

CALM-MS v2 — the LOAD-BEARING learned lesion scorer (scanner-robust TP/FP separation).

The F1 investigation showed the conformal wrapper is only as good as the underlying
score's TP/FP separability, and that raw pooled probability collapses when a scanner
emits CONFIDENT false positives (rank inversion: FP score higher than TP). The fix the
state of the art points to is a per-candidate score built on features that a scanner
CANNOT trivially inflate — morphology and anatomical location — the way lesion-wise
false-positive-reduction models work (LST family; nnU-Net FP-reduction cascades;
radiomics), harmonised with conformal selection (Jin & Candes 2023) so the guarantee is
preserved.

This script harmonises that dispersed SOTA with our data (145 labelled FLAMeS cases):
  1. extracts per-candidate features computable at INFERENCE (no GT): morphology
     (volume, sphericity, surface-to-volume, elongation, extent), anatomical location
     (MNI-normalised centroid, laterality, radial position), and probability stats;
  2. trains a learned P(true-lesion) scorer, evaluated with case-grouped CV and, crucially,
     LEAVE-ONE-SITE-OUT (does it generalise across acquisition domains?);
  3. runs the load-bearing test: under an FP-selective confidence inflation (the F1
     failure mode), does the learned score keep TP/FP separation AND recover conformal
     power that raw probability loses?

    python scripts/calm-ms/train_lesion_scorer.py

Writes backend/app/services/assets/lesion_scorer_record.json (aggregate metrics only).
"""
import os, sys, glob, json

import numpy as np
import nibabel as nib
from scipy import ndimage as ndi

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(_HERE, "..", "..", "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.services.calm_ms_inference import extract_lesion_candidates, label_candidates_tp  # noqa: E402
from app.services.conformal_lesion_fdr import conformal_pvalues, benjamini_hochberg          # noqa: E402

THRESHOLD, MIN_VOL, SCORE, SPACING = 0.5, 3.0, "mean", (1.0, 1.0, 1.0)
SITES = {"openms": "openms-flames", "mslesseg": "mslesseg-flames"}
GRID_CENTER = np.array([91.0, 109.0, 91.0])   # MNI152 1mm brain centre (approx)
GRID = np.array([182.0, 218.0, 182.0])
_CACHE = os.path.join(_HERE, ".scorer_cache.npz")

# Feature layout. PROB_FEATS are the scanner-inflatable ones; MORPH/LOC are the robust
# ones the learned score should lean on.
PROB_FEATS = ["prob_mean", "prob_max", "prob_std", "prob_q90"]
MORPH_FEATS = ["log_volume", "sphericity", "surf_to_vol", "elongation", "extent"]
LOC_FEATS = ["z_norm", "y_norm", "x_norm", "laterality", "radial"]
FEATS = PROB_FEATS + MORPH_FEATS + LOC_FEATS


def _candidate_features(mask_bbox, probs):
    """Scanner-robust morphology + probability summary for one candidate."""
    n = int(mask_bbox.sum())
    vol = float(n)                                        # 1mm^3 voxels
    # surface via 6-connectivity erosion on the small bbox
    surf = float((mask_bbox & ~ndi.binary_erosion(mask_bbox)).sum())
    s2v = surf / max(vol, 1.0)
    sphericity = (np.pi ** (1 / 3) * (6 * vol) ** (2 / 3)) / max(surf, 1.0)  # 1 for a sphere
    coords = np.argwhere(mask_bbox).astype(float)
    if len(coords) >= 3:
        c = coords - coords.mean(0)
        ev = np.sort(np.linalg.eigvalsh(np.cov(c.T)))[::-1]
        ev = np.clip(ev, 1e-6, None)
        elongation = float(np.sqrt(ev[0] / ev[-1]))
    else:
        elongation = 1.0
    extent = vol / max(np.prod(mask_bbox.shape), 1.0)
    q90 = float(np.quantile(probs, 0.9))
    return {"prob_mean": float(probs.mean()), "prob_max": float(probs.max()),
            "prob_std": float(probs.std()), "prob_q90": q90,
            "log_volume": float(np.log(vol)), "sphericity": float(sphericity),
            "surf_to_vol": float(s2v), "elongation": elongation, "extent": float(extent)}


def _extract_all():
    if os.path.exists(_CACHE):
        d = np.load(_CACHE, allow_pickle=True)
        return d["X"], d["y"], d["sites"], d["cases"]
    rows, ys, sites, cases = [], [], [], []
    for site, sub in SITES.items():
        for prob_path in sorted(glob.glob(os.path.join("data", "cohorts", sub, "*_prob.nii.gz"))):
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
            objs = ndi.find_objects(labeled)
            for c in cands:
                sl = objs[c.label - 1]
                m = (labeled[sl] == c.label)
                mf = _candidate_features(m, prob[sl][m])
                cz, cy, cx = c.centroid
                loc = {"z_norm": cz / GRID[0], "y_norm": cy / GRID[1], "x_norm": cx / GRID[2],
                       "laterality": abs(cx / GRID[2] - 0.5),
                       "radial": float(np.linalg.norm(np.array(c.centroid) - GRID_CENTER) / np.linalg.norm(GRID_CENTER))}
                mf.update(loc)
                rows.append([mf[k] for k in FEATS])
                ys.append(0 if is_tp[c.label] else 1)     # y=1 means FALSE positive
                sites.append(site); cases.append(case)
            print(f"  [{site}] {case}", end="\r")
    print()
    X = np.array(rows, float); y = np.array(ys, int)
    sites = np.array(sites); cases = np.array(cases)
    np.savez_compressed(_CACHE, X=X, y=y, sites=sites, cases=cases)
    return X, y, sites, cases


def _auc(scores, is_false):
    """AUC for ranking TRUE lesions above FALSE (higher score = more likely true)."""
    from sklearn.metrics import roc_auc_score
    true = (~is_false).astype(int)
    return float(roc_auc_score(true, scores)) if len(np.unique(true)) == 2 else float("nan")


def main():
    print("Extracting per-candidate features (morphology + location + prob) ...")
    X, y, sites, cases = _extract_all()
    is_false = y.astype(bool)
    print(f"  {len(y)} candidates | {int((~is_false).sum())} TRUE, {int(is_false.sum())} FALSE "
          f"| sites {dict(zip(*np.unique(sites, return_counts=True)))}")

    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.model_selection import GroupKFold

    prob_mean = X[:, FEATS.index("prob_mean")]
    base_auc = _auc(prob_mean, is_false)
    print(f"\nBaseline raw-probability AUC (TP vs FP): {base_auc:.3f}")

    # --- case-grouped CV: learned score vs raw prob ---
    gkf = GroupKFold(n_splits=5)
    oof = np.zeros(len(y))
    for tr, te in gkf.split(X, y, groups=cases):
        clf = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.08,
                                             max_iter=300, l2_regularization=1.0)
        clf.fit(X[tr], y[tr])
        oof[te] = clf.predict_proba(X[te])[:, 1]           # P(false)
    learned_score = 1.0 - oof                              # higher = more likely TRUE
    cv_auc = _auc(learned_score, is_false)
    print(f"Learned score AUC (case-grouped 5-fold OOF):  {cv_auc:.3f}  "
          f"({'+' if cv_auc>base_auc else ''}{cv_auc-base_auc:+.3f} vs raw prob)")

    # --- leave-one-SITE-out: scanner generalisation ---
    print("\nLeave-one-site-out (does it generalise across acquisition domains?):")
    site_learned = {}
    for test_site in SITES:
        tr = sites != test_site; te = sites == test_site
        clf = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.08,
                                             max_iter=300, l2_regularization=1.0)
        clf.fit(X[tr], y[tr])
        s_learned = 1.0 - clf.predict_proba(X[te])[:, 1]
        site_learned[test_site] = (clf, te)
        a_l = _auc(s_learned, is_false[te]); a_p = _auc(X[te, 0], is_false[te])
        print(f"  train !{test_site:9s} -> test {test_site:9s}: learned {a_l:.3f} | raw prob {a_p:.3f}")

    # --- feature importance (permutation) on a full-fit model ---
    clf_full = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.08,
                                              max_iter=300, l2_regularization=1.0).fit(X, y)
    from sklearn.inspection import permutation_importance
    imp = permutation_importance(clf_full, X, y, n_repeats=5, random_state=0, scoring="roc_auc")
    order = np.argsort(imp.importances_mean)[::-1]
    print("\nTop features (permutation importance):")
    for i in order[:8]:
        print(f"  {FEATS[i]:12s} {imp.importances_mean[i]:.4f}")

    # --- LOAD-BEARING TEST: FP-selective confidence inflation (the F1 failure mode) ---
    # Model a scanner whose FALSE candidates become confident: push the PROB features of
    # FP rows up in logit space; MORPHOLOGY/LOCATION untouched (an artifact FP keeps its
    # FP-like shape/location). Score with a model trained on the OTHER site (a real
    # cross-site deployment). Does the learned score survive where raw prob inverts?
    def _logit_shift(v, d):
        v = np.clip(v, 1e-6, 1 - 1e-6)
        return 1.0 / (1.0 + np.exp(-(np.log(v / (1 - v)) + d)))

    print("\nLOAD-BEARING TEST — FP-selective inflation on mslesseg, scored by model trained on openms:")
    tr = sites == "openms"
    clf = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.08,
                                         max_iter=300, l2_regularization=1.0).fit(X[tr], y[tr])
    te = sites == "mslesseg"
    Xs = X[te].copy(); fp = is_false[te]
    for j, f in enumerate(FEATS):
        if f in PROB_FEATS:
            Xs[fp, j] = _logit_shift(Xs[fp, j], 1.5)       # only FALSE candidates inflate
    raw_shift = Xs[:, 0]                                    # inflated prob_mean
    learned_shift = 1.0 - clf.predict_proba(Xs)[:, 1]
    a_raw = _auc(raw_shift, fp); a_learned = _auc(learned_shift, fp)
    print(f"  TP/FP AUC under shift:  raw prob {a_raw:.3f}  |  learned {a_learned:.3f}")

    # conformal power/FDR under shift: null = FALSE-candidate scores from the training site
    def _fdr_power(scores_te, fp_te, null_scores, alpha=0.20):
        # group by case within the test site
        sel = benjamini_hochberg(conformal_pvalues(scores_te, null_scores), alpha=alpha)
        n_sel = int(sel.sum()); n_false = int((sel & fp_te).sum())
        fdr = n_false / n_sel if n_sel else 0.0
        power = int((sel & ~fp_te).sum()) / max(int((~fp_te).sum()), 1)
        return fdr, power, n_sel
    raw_null = X[tr][is_false[tr], 0]                       # openms FP raw prob
    lrn_null = (1.0 - clf.predict_proba(X[tr][is_false[tr]])[:, 1])  # openms FP learned
    fr, pr, _ = _fdr_power(raw_shift, fp, raw_null)
    fl, pl, _ = _fdr_power(learned_shift, fp, lrn_null)
    print(f"  conformal @a=0.20 under shift:  raw  FDR {fr:.3f} power {pr:.3f}  |  "
          f"learned  FDR {fl:.3f} power {pl:.3f}")

    rec = {"n_candidates": int(len(y)), "n_true": int((~is_false).sum()), "n_false": int(is_false.sum()),
           "auc_raw_prob": round(base_auc, 4), "auc_learned_cv": round(cv_auc, 4),
           "leave_one_site_out": {s: round(_auc(1.0 - site_learned[s][0].predict_proba(X[site_learned[s][1]])[:, 1],
                                                is_false[site_learned[s][1]]), 4) for s in SITES},
           "top_features": [FEATS[i] for i in order[:8]],
           "shift_test": {"auc_raw": round(a_raw, 4), "auc_learned": round(a_learned, 4),
                          "conformal_raw": {"fdr": round(fr, 4), "power": round(pr, 4)},
                          "conformal_learned": {"fdr": round(fl, 4), "power": round(pl, 4)}}}
    out = os.path.join(_BACKEND, "app", "services", "assets", "lesion_scorer_record.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=2)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
