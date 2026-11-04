"""Paper C — patient-level thresholds on the largest false candidate score, and statistics.

A patient p carries a list of candidates (score, true?). M_F(p) = largest FALSE score (-inf if
none). Selecting every candidate with score > lam makes >= 1 false call iff M_F(p) > lam.

cf_marginal  : lam = k-th smallest calibration M_F, k = ceil((n+1)(1-alpha)); +inf if k > n.
               P(M_F,test > lam) <= alpha for exchangeable patients (ties included).
cf_pac       : k = smallest k with P(Bin(n, 1-alpha) >= k) <= delta; +inf if none.
               P_cal[ P(M_F,test > lam | cal) > alpha ] <= delta  (Neyman-Pearson umbrella).
plug_in      : k = ceil(n (1-alpha)) (empirical quantile, no finite-sample correction).
"""
import math

import numpy as np
from scipy import stats

NEG = float("-inf")
POS = float("inf")


def max_false(cands, key="score"):
    s = [c[key] for c in cands if not c["true"] and np.isfinite(c[key])]
    return max(s) if s else NEG


def max_all(cands, key="score"):
    s = [c[key] for c in cands if np.isfinite(c[key])]
    return max(s) if s else NEG


def _order_stat(values, k):
    v = sorted(values)
    return POS if k > len(v) or k < 1 else float(v[k - 1])


def k_marginal(n, alpha):
    return int(math.ceil((n + 1) * (1 - alpha) - 1e-12))


def k_pac(n, alpha, delta):
    for k in range(1, n + 1):
        # P(Bin(n, 1-alpha) >= k)
        if stats.binom.sf(k - 1, n, 1 - alpha) <= delta:
            return k
    return n + 1


def k_plugin(n, alpha):
    return max(1, int(math.ceil(n * (1 - alpha) - 1e-12)))


def threshold(cal_values, alpha, method="marginal", delta=0.1):
    n = len(cal_values)
    if method == "marginal":
        k = k_marginal(n, alpha)
    elif method == "pac":
        k = k_pac(n, alpha, delta)
    elif method == "plugin":
        k = k_plugin(n, alpha)
    else:
        raise ValueError(method)
    return _order_stat(cal_values, k)


def evaluate_patient(cands, lam, key="score", truth_ids_key="hits"):
    """Outcome of selecting {score > lam} in one patient."""
    sel = [c for c in cands if np.isfinite(c[key]) and c[key] > lam]
    n_false = sum(1 for c in sel if not c["true"])
    n_true = sum(1 for c in sel if c["true"])
    hit = set()
    for c in sel:
        if c["true"]:
            hit.update(c.get(truth_ids_key, []))
    return {"any_flag": bool(sel), "false_call": n_false > 0, "true_flag": n_true > 0,
            "n_false": n_false, "n_true": n_true, "lesions_hit": sorted(hit)}


def clopper_pearson(x, n, level=0.95):
    if n == 0:
        return (float("nan"), float("nan"))
    a = 1 - level
    lo = 0.0 if x == 0 else stats.beta.ppf(a / 2, x, n - x + 1)
    hi = 1.0 if x == n else stats.beta.ppf(1 - a / 2, x + 1, n - x)
    return (float(lo), float(hi))


def cluster_bootstrap(per_patient_num, per_patient_den, B=2000, seed=20261021):
    """Ratio sum(num)/sum(den) with patients resampled; returns (estimate, lo, hi)."""
    num = np.asarray(per_patient_num, dtype=float)
    den = np.asarray(per_patient_den, dtype=float)
    est = num.sum() / den.sum() if den.sum() > 0 else float("nan")
    rng = np.random.default_rng(seed)
    n = len(num)
    vals = []
    for _ in range(B):
        i = rng.integers(0, n, n)
        d = den[i].sum()
        if d > 0:
            vals.append(num[i].sum() / d)
    if not vals:
        return est, float("nan"), float("nan")
    return float(est), float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def auroc_cluster(patients, key="score", B=2000, seed=20261021):
    """Candidate-level AUROC (true vs false) with patient-cluster bootstrap CI."""
    def auc(groups):
        s_t = [c[key] for g in groups for c in g if c["true"] and np.isfinite(c[key])]
        s_f = [c[key] for g in groups for c in g if not c["true"] and np.isfinite(c[key])]
        if not s_t or not s_f:
            return float("nan")
        u = stats.mannwhitneyu(s_t, s_f, alternative="two-sided").statistic
        return float(u / (len(s_t) * len(s_f)))
    groups = [p["cands"] for p in patients]
    est = auc(groups)
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(B):
        i = rng.integers(0, len(groups), len(groups))
        v = auc([groups[j] for j in i])
        if np.isfinite(v):
            vals.append(v)
    if not vals:
        return est, float("nan"), float("nan")
    return est, float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def spearman_perm(x, y, n_perm=10000, seed=20261021):
    """Spearman rho with a permutation p-value; -inf values are ranked lowest."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    x = np.where(np.isfinite(x), x, np.nanmin(np.where(np.isfinite(x), x, np.nan)) - 1.0) if np.isfinite(x).any() else x
    rho = stats.spearmanr(x, y).statistic
    rng = np.random.default_rng(seed)
    cnt = 0
    for _ in range(n_perm):
        r = stats.spearmanr(x, rng.permutation(y)).statistic
        if abs(r) >= abs(rho) - 1e-12:
            cnt += 1
    return float(rho), float((cnt + 1) / (n_perm + 1))
