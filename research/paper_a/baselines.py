"""Paper A v0.2 — selection procedures compared in the re-analysis (CPU, cached scores only).

Every procedure takes calibration GROUPS (one scan per exchangeable subject: a list of dicts with
"scores" and a boolean "isf" = candidate is false) and test scans, and returns one boolean
selection mask per test scan. "Higher score = more lesion-like" throughout.

  conformal_bh            v0.1 wrapper: conformal p-values against ALL calibration false scores,
                          BH within each test scan (candidate-level exchangeability assumed).
  subsampled_bh           Dunn-Wasserman-Ramdas-style subsampling: the null is ONE uniformly drawn
                          false candidate per calibration scan, so calibration draws are i.i.d.
                          across exchangeable scans; BH within each test scan. Randomised: run with
                          many seeds and report the spread. Each null p-value is marginally valid
                          under scan-level exchangeability; BH's PRDS argument is NOT re-established
                          (within-scan p-values share the scan effect), so FDR control is empirical.
  crc_threshold           conformal risk control (Angelopoulos et al. 2024) on a GLOBAL score
                          threshold with the PER-SCAN FDP as loss (monotonised to be non-increasing
                          in the threshold, which upper-bounds the FDP): E[FDP_test] <= alpha under
                          exchangeability of calibration and test SCANS.
  ltt_threshold           Learn-then-Test (Angelopoulos et al. 2021) with Hoeffding-Bentkus p-values
                          and fixed-sequence testing from the strictest threshold: with prob >= 1-delta
                          over the calibration scans, E[FDP_test] <= alpha (scan-level, PAC).
  leeren_hier / _sub      Lee & Ren (arXiv 2501.02514) hierarchical / subsampling conformal e-values
                          + e-BH over the whole BATCH of test scans (Algorithms 2 and 1, alpha~=0.9
                          alpha). Guarantee: batch FDR <= alpha under group (scan) exchangeability
                          AND group sizes independent of the observations (their Assumption 1(2)) —
                          the latter is doubtful for MS (candidate count tracks lesion load).
"""
import math

import numpy as np
from scipy.stats import binom


def _bh(p, alpha):
    p = np.asarray(p, float)
    m = p.size
    if m == 0:
        return np.zeros(0, bool)
    order = np.argsort(p, kind="mergesort")
    ok = np.nonzero(p[order] <= alpha * np.arange(1, m + 1) / m)[0]
    if ok.size == 0:
        return np.zeros(m, bool)
    return p <= p[order][ok.max()]


def _pvals(s, null):
    null = np.sort(np.asarray(null, float))
    n = null.size
    return (1.0 + n - np.searchsorted(null, np.asarray(s, float), side="left")) / (n + 1.0)


def conformal_bh(cal_scans, test_scans, alpha):
    null = np.concatenate([c["scores"][c["isf"]] for c in cal_scans])
    return [_bh(_pvals(t["scores"], null), alpha) if t["scores"].size else np.zeros(0, bool)
            for t in test_scans]


def subsampled_bh(cal_scans, test_scans, alpha, rng):
    pool = [c["scores"][c["isf"]] for c in cal_scans if c["isf"].any()]
    null = np.array([f[rng.randint(f.size)] for f in pool])
    return [_bh(_pvals(t["scores"], null), alpha) if t["scores"].size else np.zeros(0, bool)
            for t in test_scans]


# ------------------------------------------------------------------ global-threshold risk control
LAMBDAS = np.r_[np.round(np.arange(0.50, 1.0001, 0.0025), 4), np.inf]   # threshold grid (score >= lam)


def _fdp_curve(scan):
    """FDP of {score >= lam} for every lam in LAMBDAS (0 when nothing is selected)."""
    s, f = scan["scores"], scan["isf"]
    out = np.zeros(LAMBDAS.size)
    for i, lam in enumerate(LAMBDAS):
        sel = s >= lam
        ns = int(sel.sum())
        out[i] = (sel & f).sum() / ns if ns else 0.0
    return out


def crc_threshold(cal_scans, alpha, B=1.0):
    L = np.array([_fdp_curve(c) for c in cal_scans])                    # (n, |grid|)
    Lmono = np.maximum.accumulate(L[:, ::-1], axis=1)[:, ::-1]          # sup over stricter lam
    n = L.shape[0]
    ok = (n / (n + 1.0)) * Lmono.mean(0) + B / (n + 1.0) <= alpha        # non-increasing in lam
    idx = np.nonzero(ok)[0]
    return float(LAMBDAS[idx.min()]) if idx.size else float("inf")


def _hb_pvalue(rhat, n, alpha):
    """Hoeffding-Bentkus p-value for H0: E[loss] > alpha with losses in [0, 1]."""
    a = min(rhat, alpha)
    if a <= 0:
        h1 = math.log(1.0 / (1.0 - alpha))
    else:
        h1 = a * math.log(a / alpha) + (1 - a) * math.log((1 - a) / (1 - alpha))
    p_h = math.exp(-n * h1)
    p_b = math.e * binom.cdf(math.ceil(n * rhat), n, alpha)
    return min(p_h, p_b)


def ltt_threshold(cal_scans, alpha, delta=0.1):
    L = np.array([_fdp_curve(c) for c in cal_scans])
    n = L.shape[0]
    lam_hat = float("inf")
    for i in range(LAMBDAS.size - 1, -1, -1):                            # strictest -> most lenient
        if _hb_pvalue(float(L[:, i].mean()), n, alpha) <= delta:
            lam_hat = float(LAMBDAS[i])
        else:
            break
    return lam_hat


def apply_threshold(test_scans, lam):
    return [t["scores"] >= lam for t in test_scans]


# ------------------------------------------------------------------ Lee & Ren conformal e-values
def _ebh(e, alpha):
    e = np.asarray(e, float)
    n = e.size
    if n == 0:
        return np.zeros(0, bool)
    es = np.sort(e)[::-1]
    ls = np.nonzero(np.arange(1, n + 1) * es / n >= 1.0 / alpha)[0]
    if ls.size == 0:
        return np.zeros(n, bool)
    return e >= es[ls.max()]


def _sup_threshold(fdp_at, grid, at_inf, alpha_t):
    """sup{t : FDPhat(t) <= alpha_t} for a step function evaluated with strict '<' counts at the
    sorted unique values `grid` (value on (u_{k-1}, u_k]) and `at_inf` on (u_L, inf)."""
    if at_inf <= alpha_t:
        return np.inf
    ok = np.nonzero(fdp_at <= alpha_t)[0]
    return grid[ok.max()] if ok.size else -np.inf


def leeren(cal_scans, test_scans, alpha, variant="hier", rng=None, alpha_tilde_ratio=0.9):
    """Batch e-BH over all test scans with V = -score (smaller V = stronger evidence)."""
    at = alpha_tilde_ratio * alpha
    K = len(cal_scans)
    Vc = [-c["scores"] for c in cal_scans]
    Fc = [c["isf"] for c in cal_scans]
    Vt = [-t["scores"] for t in test_scans]
    Nt = np.array([v.size for v in Vt])
    if variant == "sub":
        picks = [rng.randint(v.size) for v in Vc]
        cal_null_v = np.array([v[i] for v, f, i in zip(Vc, Fc, picks) if f[i]])  # subsampled nulls
        cal_w = np.ones(cal_null_v.size)
    else:
        cal_null_v = np.concatenate([v[f] for v, f in zip(Vc, Fc)])
        cal_w = np.concatenate([np.full(int(f.sum()), 1.0 / v.size) for v, f in zip(Vc, Fc)])
    all_test_v = np.concatenate(Vt) if Vt else np.zeros(0)
    grid = np.unique(np.r_[cal_null_v, all_test_v])
    order = np.argsort(cal_null_v)
    cv, cw = cal_null_v[order], np.cumsum(cal_w[order])

    def A(t):                       # weighted count of calibration nulls with V < t
        if t == -np.inf:
            return 0.0
        if t == np.inf:
            return float(cw[-1]) if cw.size else 0.0
        k = np.searchsorted(cv, t, side="left")
        return float(cw[k - 1]) if k else 0.0

    A_grid = np.array([A(t) for t in grid])
    A_inf = A(np.inf)
    ts = np.sort(all_test_v)
    tot_lt = np.searchsorted(ts, grid, side="left")            # all test units with V < t
    e_all = []
    for j, vj in enumerate(Vt):
        own = np.searchsorted(np.sort(vj), grid, side="left")
        den = np.maximum(tot_lt - own, 1)
        den_inf = max(all_test_v.size - vj.size, 1)
        if variant == "sub":
            mult = Nt.sum() / (K + 1.0)
            fdp = (A_grid + 1) / den * mult
            fdp_inf = (A_inf + 1) / den_inf * mult
            T = _sup_threshold(fdp, grid, fdp_inf, at)
            e = (vj < T) * (K + 1.0) / (A(T) + 1.0)
        else:
            mult = (Nt.sum() - vj.size) / (K + 1.0)
            Tp = _sup_threshold((A_grid + 1) / den * mult, grid, (A_inf + 1) / den_inf * mult, at)
            Tm = _sup_threshold(A_grid / den * mult, grid, A_inf / den_inf * mult, at)
            e = (vj < Tp) * (K + 1.0) / (A(Tm) + 1.0)
        e_all.append(np.asarray(e, float))
    sel = _ebh(np.concatenate(e_all) if e_all else np.zeros(0), alpha)
    out, i = [], 0
    for vj in Vt:
        out.append(sel[i:i + vj.size])
        i += vj.size
    return out
