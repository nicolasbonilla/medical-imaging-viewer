#!/usr/bin/env python3
"""Build the FROZEN, transparent CALM-MS v2 lesion-scorer asset.

Trains a degree-2 polynomial logistic regression (P(false candidate)) on the 145
labelled FLAMeS cases using the SHARED inference-time feature extractor
(`calm_ms_lesion_features`), then serializes ONLY plain arrays — feature means/stds, the
monomial-exponent matrix, coefficients, intercept — so the production scorer
(`calm_ms_scorer`) needs no pickle and no sklearn at inference. Reports the reproduced
case-grouped AUC as a build-time check that the frozen asset matches the validated result.

    python scripts/calm-ms/build_lesion_scorer_asset.py

Output: backend/app/services/assets/calm_ms_lesion_scorer_v1.npz
"""
import os, sys, glob, json, re, datetime, hashlib

import numpy as np
import nibabel as nib

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(_HERE, "..", "..", "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.services.calm_ms_inference import extract_lesion_candidates, label_candidates_tp  # noqa: E402
from app.services.calm_ms_lesion_features import candidate_feature_matrix, FEATURE_NAMES     # noqa: E402

THRESHOLD, MIN_VOL, SCORE, SPACING = 0.5, 3.0, "mean", (1.0, 1.0, 1.0)
SITES = {"openms": "openms-flames", "mslesseg": "mslesseg-flames"}
DEGREE, C_REG = 2, 0.5


def _patient_of(case):
    """Group longitudinal timepoints of one patient together to avoid CV leakage
    (MSLesSeg 'mslesseg_P12_T3' -> 'mslesseg_P12'; openms cases are their own patient)."""
    m = re.match(r"(mslesseg_P\d+)_T\d+", case)
    return m.group(1) if m else case


def _load():
    X, y, cases = [], [], []
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
            fm = candidate_feature_matrix(prob, labeled, cands, SPACING)
            for i, c in enumerate(cands):
                X.append(fm[i]); y.append(0 if is_tp[c.label] else 1); cases.append(case)
            print(f"  [{site}] {case}", end="\r")
    print()
    return np.array(X, float), np.array(y, int), np.array(cases)


def main():
    from sklearn.preprocessing import PolynomialFeatures
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GroupKFold
    from sklearn.metrics import roc_auc_score

    print("Extracting features via the SHARED module (calm_ms_lesion_features) ...")
    X, y, cases = _load()
    print(f"  {len(y)} candidates ({int((y==0).sum())} TRUE, {int((y==1).sum())} FALSE)")

    mean, std = X.mean(0), X.std(0) + 1e-9
    pf = PolynomialFeatures(DEGREE, include_bias=False)
    Z = pf.fit_transform((X - mean) / std)
    powers = pf.powers_.astype(int)                          # (n_terms, d)

    # honest reproduced AUC — grouped by PATIENT (not timepoint) to avoid longitudinal
    # leakage across a patient's repeated scans.
    patients = np.array([_patient_of(str(c)) for c in cases])
    gkf, oof = GroupKFold(5), np.zeros(len(y))
    for tr, te in gkf.split(Z, y, groups=patients):
        m = LogisticRegression(max_iter=5000, C=C_REG).fit(Z[tr], y[tr])
        oof[te] = m.predict_proba(Z[te])[:, 1]
    auc = roc_auc_score((y == 0).astype(int), 1 - oof)
    print(f"  reproduced patient-grouped AUC (leak-free) = {auc:.3f}")

    clf = LogisticRegression(max_iter=5000, C=C_REG).fit(Z, y)
    coef = clf.coef_.ravel().astype(float)
    intercept = float(clf.intercept_[0])

    prov = {"asset": "calm_ms_lesion_scorer_v1", "version": "v1",
            "model": "degree-2 polynomial logistic regression (P false candidate)",
            "feature_names": list(FEATURE_NAMES), "degree": DEGREE, "C": C_REG,
            "base_model": "FLAMeS", "n_candidates": int(len(y)),
            "n_true": int((y == 0).sum()), "n_false": int((y == 1).sum()),
            "cv_auc_patient_grouped": round(float(auc), 4),
            "sites": list(SITES), "built_utc": datetime.datetime.utcnow().isoformat() + "Z",
            "note": "Transparent: parameters are plain arrays; inference is pure-NumPy in "
                    "calm_ms_scorer (no pickle, no sklearn). Investigational — DARK.",
            "requirement": "REQ-FUNC-CALM-001"}
    prov["sha256"] = hashlib.sha256(
        (json.dumps(prov, sort_keys=True) + coef.tobytes().hex()[:1024]).encode()).hexdigest()[:16]

    out = os.path.join(_BACKEND, "app", "services", "assets", "calm_ms_lesion_scorer_v1.npz")
    np.savez_compressed(out, mean=mean, std=std, powers=powers, coef=coef,
                        intercept=np.float64(intercept), provenance=json.dumps(prov))
    print(f"WROTE {out}  ({powers.shape[0]} terms, sha {prov['sha256']})")

    # self-check: the pure-NumPy scorer must reproduce sklearn's probabilities exactly
    from app.services.calm_ms_scorer import load_lesion_scorer
    s = load_lesion_scorer(out)
    ours = s.score(X)                                        # 1 - P(false)
    ref = 1 - clf.predict_proba(Z)[:, 1]
    print(f"  pure-NumPy vs sklearn max abs diff = {np.max(np.abs(ours - ref)):.2e}")


if __name__ == "__main__":
    main()
