#!/usr/bin/env python3
"""V&V for the CALM-MS OOD monitor (RC-CALM-5 second axis).

Characterises the monitor the adversarial review demanded we validate:
  * SPECIFICITY (false-OOD rate): leave-one-case-out over the 145 calibration cases —
    for each case, build the robust envelope from the OTHER 144 and check whether the
    held-out (legitimate, in-distribution) case is wrongly flagged OOD.
  * SENSITIVITY (detection): apply increasing score-regime shifts (the exact failure
    mode the adversary exploited — realized FDR up to ~8x) to each case and measure
    the fraction flagged, as a function of shift magnitude.
Prints a threshold sweep so OOD_THRESHOLD is chosen from evidence, not guessed, and
writes a JSON V&V record.

    python scripts/calm-ms/validate_ood_monitor.py
"""
import os, sys, json

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(_HERE, "..", "..", "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.services.conformal_null_asset import get_null_asset  # noqa: E402

# Feature layout: [n_candidates, mean, q10, q50, q90]. The score-regime features are
# indices 1..4 (the adversarial shift moves these); index 0 is candidate load.
SCORE_FEATS = [1, 2, 3, 4]


def _robust_center_scale(ref):
    med = np.median(ref, axis=0)
    mad = np.median(np.abs(ref - med), axis=0) * 1.4826
    mad = np.where(mad < 1e-6, 1e-6, mad)
    return med, mad


def _max_z(feat, ref):
    med, mad = _robust_center_scale(ref)
    return float(np.max(np.abs((feat - med) / mad)))


def _mahalanobis(feat, ref):
    """Mahalanobis distance — accounts for the strong correlation among the
    score-quantile features, so a coherent score-regime shift shows up as one large
    distance rather than being diluted across correlated per-feature z-scores."""
    mu = np.median(ref, axis=0)
    # standardize per feature first (n_candidates vs scores are different scales),
    # then covariance-whiten; ridge for the near-collinear quantile features.
    _, sc = _robust_center_scale(ref)
    R = (ref - mu) / sc
    C = np.cov(R, rowvar=False) + 1e-3 * np.eye(ref.shape[1])
    Ci = np.linalg.pinv(C)
    v = (feat - mu) / sc
    return float(np.sqrt(max(0.0, v @ Ci @ v)))


def _shifted(feat, mad, shift_sd):
    """The adversarial failure mode: false-candidate scores pushed up — raises the
    case's mean/quantile score features by `shift_sd` robust-SD each."""
    f = feat.copy()
    for j in SCORE_FEATS:
        f[j] += shift_sd * mad[j]
    return f


def _evaluate(name, stat_fn, ref, mad, thresholds, shift_grid):
    """Leave-one-case-out specificity + shift-detection sensitivity for one statistic."""
    n = ref.shape[0]
    # distance of each legitimate case to the envelope built from the OTHER 144
    loo = np.array([stat_fn(ref[i], np.delete(ref, i, axis=0)) for i in range(n)])
    # distance of each case AFTER an adversarial up-shift, same held-out envelope
    shifted = {s: np.array([stat_fn(_shifted(ref[i], mad, s), np.delete(ref, i, axis=0))
                            for i in range(n)]) for s in shift_grid}
    print(f"\n=== {name} ===")
    print("  LOO distance of legit cases:",
          {q: round(float(np.percentile(loo, q)), 2) for q in (50, 90, 95, 99, 100)})
    print("  threshold | false-OOD | " + " | ".join(f"det+{s}SD" for s in shift_grid))
    rows = []
    for thr in thresholds:
        false_ood = float(np.mean(loo > thr))
        dets = {s: float(np.mean(shifted[s] > thr)) for s in shift_grid}
        rows.append({"threshold": thr, "false_ood_rate": round(false_ood, 3),
                     **{f"detect_+{s}SD": round(dets[s], 3) for s in shift_grid}})
        print(f"    {thr:>6}  |  {false_ood:6.3f}  | "
              + " | ".join(f"{dets[s]:6.3f}" for s in shift_grid))
    return {"loo_p99": round(float(np.percentile(loo, 99)), 2),
            "loo_max": round(float(loo.max()), 2), "sweep": rows}


def main():
    ref = get_null_asset().ood_reference
    if ref is None:
        sys.exit("asset has no OOD reference — rebuild with build_null_bundle.py")
    ref = np.asarray(ref, dtype=float)
    n = ref.shape[0]
    _, mad = _robust_center_scale(ref)
    print(f"OOD reference: {n} calibration cases x {ref.shape[1]} features "
          f"(median row {np.round(np.median(ref,0),3)})")

    shift_grid = [2, 3, 4, 6]
    maxz = _evaluate("max robust-z (v1 statistic)", _max_z, ref, mad,
                     [4, 5, 6, 7, 8, 10, 12], shift_grid)
    maha = _evaluate("Mahalanobis (covariance-aware)", _mahalanobis, ref, mad,
                     [3, 4, 5, 6, 7, 8], shift_grid)

    # The monitor is scoped as a GROSS-shift backstop (the adversarial break was a
    # large score-regime shift → realized FDR ~8x). Criterion: catch a +6SD shift at
    # >=0.95 while withholding the guarantee on <=3% of legitimate in-distribution
    # cases (a fail-closed, utility-only cost). Detection of subtle (+3SD) shift is
    # NOT claimed and is recorded as a residual limitation.
    def choose(record):
        for r in record["sweep"]:
            if r["false_ood_rate"] <= 0.03 and r.get("detect_+6SD", 0) >= 0.95:
                return r["threshold"]
        return None
    maha_thr, maxz_thr = choose(maha), choose(maxz)
    if maha_thr is not None:
        chosen = {"statistic": "mahalanobis", "threshold": maha_thr,
                  "scope": "gross-shift backstop; +6SD detected >=0.95, +3SD NOT claimed"}
    elif maxz_thr is not None:
        chosen = {"statistic": "max_z", "threshold": maxz_thr}
    else:
        chosen = {"statistic": None, "threshold": None,
                  "note": "no statistic meets the gross-shift backstop criterion"}
    print(f"\nDECISION: {chosen}")

    out = {"n_cases": n, "shift_grid_sd": shift_grid,
           "max_z": maxz, "mahalanobis": maha, "chosen": chosen}
    rec_dir = os.path.join(_BACKEND, "app", "services", "assets")
    with open(os.path.join(rec_dir, "ood_validation_record.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print("Wrote V&V record: backend/app/services/assets/ood_validation_record.json")


if __name__ == "__main__":
    main()
