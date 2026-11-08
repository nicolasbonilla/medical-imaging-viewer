"""Paper A v0.3 — selection procedures, per-scan metrics, patient-cluster bootstrap and the cell
classification rule of PROTOCOL-v0.3 (§5, §8, §9). Pure functions, no I/O; tested in
test_v03_metrics.py.

Conventions: higher score = more lesion-like; `isf` = candidate is false (unmatched);
FDP of an empty selection = 0.
"""
import math

import numpy as np
from scipy.stats import beta, binom, rankdata

GRID = np.r_[np.round(np.arange(0.0, 1.0 + 1e-9, 0.001), 3), np.inf]   # global-threshold grid


# ------------------------------------------------------------------ conformal p-values + BH
def conformal_pvalues(scores, null):
    """p_j = (1 + #{null >= s_j}) / (n + 1)."""
    null = np.sort(np.asarray(null, float))
    n = null.size
    return (1.0 + n - np.searchsorted(null, np.asarray(scores, float), side="left")) / (n + 1.0)


def bh(p, alpha):
    """Benjamini-Hochberg step-up at level alpha; boolean mask (ties at the cut are selected)."""
    p = np.asarray(p, float)
    m = p.size
    if m == 0:
        return np.zeros(0, bool)
    order = np.argsort(p, kind="mergesort")
    ok = np.nonzero(p[order] <= alpha * np.arange(1, m + 1) / m)[0]
    if ok.size == 0:
        return np.zeros(m, bool)
    return p <= p[order][ok.max()]


def conformal_bh(test_scores, null, alpha):
    """P1: one BH selection per test scan against a pooled false-candidate null."""
    return [bh(conformal_pvalues(s, null), alpha) if len(s) else np.zeros(0, bool) for s in test_scores]


# ------------------------------------------------------------------ global-threshold procedures
def fdp_curve(scores, isf, grid=GRID):
    """FDP of {s >= lam} for every lam in grid (0 when nothing is selected)."""
    s = np.asarray(scores, float)
    f = np.asarray(isf, bool)
    if s.size == 0:
        return np.zeros(grid.size)
    o = np.argsort(s)
    ss, ff = s[o], f[o]
    # number of candidates with s >= lam = n - searchsorted(ss, lam, 'left')
    first = np.searchsorted(ss, grid, side="left")
    n_sel = s.size - first
    cum_false_from_top = np.r_[np.cumsum(ff[::-1])[::-1], 0]       # false among indices >= i
    n_false = cum_false_from_top[first]
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(n_sel > 0, n_false / np.maximum(n_sel, 1), 0.0)


def safe_threshold(scores, isf, gamma, grid=GRID):
    """Smallest grid lam such that FDP(lam') <= gamma for every grid lam' >= lam."""
    bad = np.nonzero(fdp_curve(scores, isf, grid) > gamma + 1e-12)[0]
    return float(grid[0]) if bad.size == 0 else float(grid[bad.max() + 1])


def fdx_threshold(safe_values, delta):
    """P2: the ceil((K+1)(1-delta))-th smallest safe threshold (inf = abstain if index > K)."""
    t = np.sort(np.asarray(safe_values, float))
    K = t.size
    idx = math.ceil((K + 1) * (1 - delta) - 1e-12)
    return float("inf") if idx > K or K == 0 else float(t[idx - 1])


def crc_threshold(cal, alpha, grid=GRID, B=1.0):
    """B2: conformal risk control with the (monotonised) per-scan FDP as loss. cal = [(scores, isf)]."""
    if not cal:
        return float("inf")
    L = np.array([fdp_curve(s, f, grid) for s, f in cal])
    Lmono = np.maximum.accumulate(L[:, ::-1], axis=1)[:, ::-1]
    n = L.shape[0]
    ok = (n / (n + 1.0)) * Lmono.mean(0) + B / (n + 1.0) <= alpha
    idx = np.nonzero(ok)[0]
    return float(grid[idx.min()]) if idx.size else float("inf")


def _hb_pvalue(rhat, n, alpha):
    a = min(rhat, alpha)
    if a <= 0:
        h1 = math.log(1.0 / (1.0 - alpha))
    else:
        h1 = a * math.log(a / alpha) + (1 - a) * math.log((1 - a) / (1 - alpha))
    return min(math.exp(-n * h1), math.e * binom.cdf(math.ceil(n * rhat), n, alpha))


def ltt_threshold(cal, alpha, delta=0.1, grid=GRID):
    """B3: Learn-then-Test, Hoeffding-Bentkus p-values, fixed sequence from the strictest lam."""
    if not cal:
        return float("inf")
    L = np.array([fdp_curve(s, f, grid) for s, f in cal])
    n = L.shape[0]
    lam = float("inf")
    for i in range(grid.size - 1, -1, -1):
        if _hb_pvalue(float(L[:, i].mean()), n, alpha) <= delta:
            lam = float(grid[i])
        else:
            break
    return lam


def naive_threshold(scores, isf, alpha):
    """B1: lowest score whose pooled calibration micro-FDR (top-down) is <= alpha."""
    s = np.asarray(scores, float)
    f = np.asarray(isf, bool)
    if s.size == 0:
        return float("inf")
    o = np.argsort(-s, kind="mergesort")
    ok = (np.cumsum(f[o]) / np.arange(1, s.size + 1)) <= alpha
    return float(s[o][np.max(np.where(ok)[0])]) if ok.any() else float("inf")


# ------------------------------------------------------------------ per-scan outcome rows
def scan_row(sel, isf, mg, gt_ids, gt_vol, clin_mm3=14.14):
    """Per-scan counts: selections, false selections, FDP, expert-lesion hits (by id)."""
    sel = np.asarray(sel, bool)
    isf = np.asarray(isf, bool)
    mg = np.asarray(mg, int)
    ns, nf = int(sel.sum()), int((sel & isf).sum())
    hit_ids = set(int(g) for g in mg[sel & (mg > 0)])
    det_ids = set(int(g) for g in mg[mg > 0])
    clin = set(int(g) for g, v in zip(gt_ids, gt_vol) if v >= clin_mm3)
    return {"ns": ns, "nf": nf, "fdp": nf / ns if ns else 0.0, "hits": len(hit_ids),
            "n_gt": len(gt_ids), "det": len(det_ids), "hits_clin": len(hit_ids & clin), "n_clin": len(clin)}


# ------------------------------------------------------------------ patient-cluster bootstrap
def bootstrap_weights(n_clusters, n_boot, rng):
    """(n_boot, n_clusters) multiplicities of a cluster bootstrap (resampling with replacement)."""
    idx = rng.randint(0, n_clusters, size=(n_boot, n_clusters))
    W = np.zeros((n_boot, n_clusters))
    np.add.at(W, (np.repeat(np.arange(n_boot), n_clusters), idx.ravel()), 1)
    return W


def ratio_ci(num, den, W, conf=0.95):
    """Percentile CI of sum(w*num)/sum(w*den) over bootstrap weight rows (rows with den = 0 dropped)."""
    a = W @ np.asarray(num, float)
    b = W @ np.asarray(den, float)
    ok = b > 0
    if not ok.any():
        return [None, None]
    v = a[ok] / b[ok]
    q = (1 - conf) / 2
    return [float(np.quantile(v, q)), float(np.quantile(v, 1 - q))]


def clopper_pearson(x, n, conf=0.95):
    if n == 0:
        return [None, None]
    a = 1 - conf
    lo = 0.0 if x == 0 else float(beta.ppf(a / 2, x, n - x + 1))
    hi = 1.0 if x == n else float(beta.ppf(1 - a / 2, x + 1, n - x))
    return [lo, hi]


def classify(ci, nominal, margin=0.05):
    """PROTOCOL-v0.3 §9: violated / holds / inconclusive."""
    lo, hi = ci
    if lo is None:
        return "undefined"
    if lo > nominal + 1e-12:
        return "violated"
    if hi <= nominal + margin + 1e-12:
        return "holds"
    return "inconclusive"


def auroc(scores, is_true):
    s = np.asarray(scores, float)
    y = np.asarray(is_true, bool)
    n1, n0 = int(y.sum()), int((~y).sum())
    if n1 == 0 or n0 == 0:
        return None
    r = rankdata(s)
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def icc1(groups):
    """One-way random-effects ICC(1) of values grouped (groups with >= 2 values)."""
    groups = [np.asarray(g, float) for g in groups if len(g) >= 2]
    k = len(groups)
    if k < 2:
        return None
    sizes = np.array([g.size for g in groups])
    N = sizes.sum()
    allv = np.concatenate(groups)
    gm = np.array([g.mean() for g in groups])
    msb = float((sizes * (gm - allv.mean()) ** 2).sum()) / (k - 1)
    msw = float(sum(((g - g.mean()) ** 2).sum() for g in groups)) / (N - k)
    n0 = (N - (sizes ** 2).sum() / N) / (k - 1)
    return (msb - msw) / (msb + (n0 - 1) * msw)


def min_reliable_size(bin_edges, sens, n_les, level=0.8, min_n=10):
    """Lower edge of the smallest bin b such that bins b..last all have sensitivity >= level.
    Returns (edge or None, flag) with flag 'insufficient' if any bin from b on has < min_n lesions."""
    k = len(sens)
    best = None
    for b in range(k - 1, -1, -1):
        if sens[b] is not None and sens[b] >= level:
            best = b
        else:
            break
    if best is None:
        return None, ("insufficient" if n_les[-1] < min_n else "ok")
    flag = "insufficient" if any(n_les[j] < min_n for j in range(best, k)) else "ok"
    return float(bin_edges[best]), flag
