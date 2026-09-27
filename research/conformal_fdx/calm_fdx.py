"""CALM-FDX — per-scan false-discovery-exceedance (FDX) control for conformal lesion selection,
plus certified per-region true-lesion counts (certified dissemination in space).

Guarantee (Layer 1, under assumption A1 below):
    P( FDP_scan > gamma ) <= delta          for the selected set of each scan, and simultaneously
    P( some certified region count is too high ) <= delta   for ALL candidate subsets / regions.

Construction (not novel; we cite it): the null conformal p-values of one scan against a shared
calibration set follow a universal rank law P_{n,m0} (uniform lattice-path interleaving; Gazin,
Blanchard & Roquain 2024). An integer envelope G is calibrated so that the null count process
V_k = #{null p_j <= k/(n+1)} crosses it with probability <= delta, computed EXACTLY by a lattice-
path dynamic program (no Monte Carlo); unknown m0 is handled by the completion coupling + an
m0-adaptive closure, and the bound is self-refined (Song, Jin & Candes 2026; Blanchard, Neuvial &
Roquain 2020). Selection takes the largest threshold whose certified FDP bound is <= gamma.

A1 (load-bearing): conditional on the scan, the calibration false scores and the scan's false-
candidate scores are jointly exchangeable. Scan-level random effects violate A1 — the multi-site
study measured ICC 0.08-0.09 on real false-candidate scores — so Layer 1 alone is not guaranteed on
real MS data; `scan_level_theta` (Layer 2) restores validity under exchangeability of SCANS only.

Pure NumPy, CPU. Everything a-priori (template, grid, gamma, delta) must be fixed before any
evaluation scan is seen; re-tuning on evaluation data voids the guarantee.
"""
from __future__ import annotations

import numpy as np

SAFETY = 1e-10
T_MAX = 0.5          # envelope constraints act on t in (0, T_MAX]; beyond, G = r (vacuous)


# ------------------------------------------------------------------ conformal ranks
def conformal_ranks(test_scores, calib_false_scores):
    """k_j = (n+1) p_j = 1 + #{c_i >= s_j}  in {1..n+1} (ties counted as >=: conservative).
    Higher score = more lesion-like. Returns (ranks int array, n)."""
    c = np.sort(np.asarray(calib_false_scores, float))
    s = np.asarray(test_scores, float)
    if c.size == 0:
        raise ValueError("empty calibration set")
    if not (np.isfinite(c).all() and np.isfinite(s).all()):
        raise ValueError("non-finite score")
    return (1 + (c.size - np.searchsorted(c, s, side="left"))).astype(np.int64), int(c.size)


# ------------------------------------------------------------------ exact crossing probability
def crossing_prob(n: int, r: int, G) -> np.ndarray:
    """Exact P_{n,r}( exists k in 1..n+1 : V_k > G[k-1] ) for each row of G (shape (P, n+1),
    non-decreasing integer rows). V_k = #null tests ranked above the k-th largest calibration
    score; all C(n+r, r) interleavings are equally likely.

    DP over anti-diagonals s = i + j (i calibration, j tests consumed, in descending order).
    State (i, j) violates the envelope iff j > G[i] (the tests seen before the (i+1)-th
    calibration point already exceed G_{i+1}); with c_j = min{i : G[i] >= j} it is allowed iff
    s >= c_j + j."""
    G = np.atleast_2d(np.asarray(G, np.int64))
    if r == 0:
        return np.zeros(G.shape[0])
    if G.shape[1] != n + 1:
        raise ValueError("G must have n+1 columns")
    if (np.diff(G, axis=1) < 0).any():
        raise ValueError("envelope rows must be non-decreasing")
    active = np.nonzero((G < r).any(axis=0))[0]
    if active.size == 0:
        return np.zeros(G.shape[0])
    s_end = min(n + r, int(active.max()) + 1 + r)
    j = np.arange(r + 1)
    D = np.stack([np.searchsorted(g, j, side="left") for g in G]) + j   # first allowed diagonal
    f = np.zeros((G.shape[0], r + 1))
    f[:, 0] = 1.0
    for s in range(s_end):
        den = float(n + r - s)
        nf = f * (np.clip(n - s + j, 0, n) / den)            # calibration step: (i,j)->(i+1,j)
        nf[:, 1:] += f[:, :-1] * ((r - j[:-1]) / den)        # null-test step:   (i,j)->(i,j+1)
        nf[D > s + 1] = 0.0                                   # kill envelope-crossing states
        f = nf
    return 1.0 - f.sum(axis=1)


# ------------------------------------------------------------------ templates (a-priori)
def _t(n):
    K = int(min(n, max(1, np.floor(T_MAX * (n + 1)))))
    return K, np.arange(1, K + 1) / (n + 1.0)


def env_hc(n, r, theta):
    """Truncated higher-criticism envelope; theta = lambda (larger = looser = safer)."""
    theta = np.atleast_1d(np.asarray(theta, float))
    K, t = _t(n)
    sd = np.sqrt(r * t * (1 - t) * (1.0 + r / n))
    G = np.full((theta.size, n + 1), r, np.int64)
    G[:, :K] = np.minimum(np.floor(r * t + theta[:, None] * sd + 1e-9), r)
    return np.maximum.accumulate(G, axis=1)


def env_simes(n, r, theta):
    """Simes / linear JER envelope (BNR 2020 Simes family): V(t) <= ceil(r t theta) - 1;
    theta = 1/lambda (larger = looser). Front-loaded: G = 0 wherever r t theta <= 1, so a few
    top-ranked lesions can be certified with zero false positives."""
    theta = np.atleast_1d(np.asarray(theta, float))
    K, t = _t(n)
    G = np.full((theta.size, n + 1), r, np.int64)
    G[:, :K] = np.minimum(np.maximum(np.ceil(r * t * theta[:, None] - 1e-9) - 1, 0), r)
    return np.maximum.accumulate(G, axis=1)


def env_hybrid(n, r, theta):
    """min(HC, Simes) along one parameter (theta scales both): HC's strength with many true
    lesions, Simes' zero-prefix in the few-lesion regime. Validity is unaffected — the exact DP
    certifies whatever integer vector results."""
    return np.minimum(env_hc(n, r, theta), env_simes(n, r, 1.0 + theta))


TEMPLATES = {"hc": env_hc, "simes": env_simes, "hybrid": env_hybrid}


def calibrate(n, r, delta, template="hc", lo=0.0, hi=30.0, points=16, rounds=6):
    """Smallest theta on nested grids whose EXACT crossing prob is <= delta - SAFETY.
    Deterministic; the returned integer envelope is itself exactly certified."""
    if r == 0:
        return np.zeros(n + 1, np.int64), 0.0
    env = TEMPLATES[template]
    best = None
    for _ in range(rounds):
        grid = np.linspace(lo, hi, points)
        G = env(n, r, grid)
        cp = crossing_prob(n, r, G)
        ok = np.nonzero(cp <= delta - SAFETY)[0]
        if ok.size == 0:
            lo, hi = hi, 2 * hi
            continue
        i = int(ok.min())
        best = (G[i].copy(), float(cp[i]))
        if i == 0:
            break
        lo, hi = grid[i - 1], grid[i]
    if best is None:
        raise RuntimeError(f"no envelope met delta at n={n} r={r}")
    return best


def r_grid(m, dense=12, ratio=1.12):
    g, x = list(range(1, dense + 1)), float(dense)
    while x < m:
        x *= ratio
        g.append(int(np.ceil(x)))
    return sorted({v for v in g if v < m} | {m})


class EnvelopeFamily:
    """Exact envelopes G^{(r)} cached per (n, r); depend only on (n, r, delta, template)."""

    def __init__(self, delta=0.1, template="hc"):
        self.delta, self.template, self._c = delta, template, {}

    def G(self, n, r):
        if r == 0:
            return np.zeros(n + 1, np.int64)
        key = (n, r)
        if key not in self._c:
            self._c[key] = calibrate(n, r, self.delta, self.template)
        return self._c[key][0]

    def cp(self, n, r):
        self.G(n, r)
        return self._c[(n, r)][1]


# ------------------------------------------------------------------ per-scan bound + selection
def simultaneous_bound(k, n, fam: EnvelopeFamily, inflate: int = 0):
    """B*_k (k = 1..n+1): on the event E (prob >= 1-delta), #null candidates with rank <= k is
    <= B*_k for ALL k simultaneously. Also returns R_k and the m0 estimate.
    `inflate` >= 0 adds a constant to every envelope (Layer-2 nested family)."""
    k = np.asarray(k, np.int64)
    m = k.size
    R = np.cumsum(np.bincount(k, minlength=n + 2))[1:n + 2]           # R_k, k = 1..n+1
    if m == 0:
        return np.zeros(n + 1, np.int64), R, 0
    A = m - R                                                          # #{p_j > t_k}
    rg = r_grid(m)
    cells = list(zip([0] + rg[:-1], rg))                               # r in (a, b] -> G^{(b)}
    Gs = {b: np.minimum(fam.G(n, b) + inflate, b) for _, b in cells}
    feas = []
    for a, b in cells:
        M = int(np.min(A + Gs[b]))
        if M >= a + 1:
            feas.append(min(b, M))
    m0_hat = max(feas) if feas else 0
    B = np.zeros(n + 1, np.int64)
    for a, b in cells:
        if a + 1 <= m0_hat:
            B = np.maximum(B, Gs[b])
    Bmono = np.minimum.accumulate(B[::-1])[::-1]
    Bstar = np.minimum(Bmono, R - np.maximum.accumulate(np.maximum(R - Bmono, 0)))
    return Bstar, R, m0_hat


def select_fdx(k, n, gamma, fam: EnvelopeFamily, inflate: int = 0):
    """Largest certified threshold: select ranks <= k* where k* = max{k : R_k>=1, B*_k <= gamma R_k}.
    Returns (selected mask, info)."""
    k = np.asarray(k, np.int64)
    Bstar, R, m0_hat = simultaneous_bound(k, n, fam, inflate)
    ok = np.nonzero((R >= 1) & (Bstar <= gamma * R))[0]
    kstar = int(ok.max()) + 1 if ok.size else 0
    return k <= kstar, {"kstar": kstar, "m0_hat": m0_hat, "Bstar": Bstar, "R": R,
                        "fdp_bound": float(Bstar[kstar - 1] / R[kstar - 1]) if kstar else 0.0}


def null_upper_bound(subset_mask, k, Bstar):
    """Simultaneous (on E) upper bound on #nulls inside ANY candidate subset S:
    V(S) <= min( |S|, min_k ( |S ∩ {rank > k}| + B*_k ) )   (interpolation bound)."""
    S = np.asarray(subset_mask, bool)
    kS = np.asarray(k, np.int64)[S]
    if kS.size == 0:
        return 0
    n1 = Bstar.size                                        # = n+1 grid points
    cnt_le = np.cumsum(np.bincount(kS, minlength=n1 + 1))[1:n1 + 1]   # |S ∩ {rank <= k}|
    above = kS.size - cnt_le                               # |S ∩ {rank > k}|
    return int(min(kS.size, int(np.min(above + Bstar))))


def certified_true_counts(regions, k, Bstar, region_ids=(1, 2, 3)):
    """(1-delta)-simultaneous lower bounds on true lesions per region: |S_r| - Vbar(S_r)."""
    regions = np.asarray(regions)
    return {r: int((regions == r).sum() - null_upper_bound(regions == r, k, Bstar))
            for r in region_ids}


def certify_dis(regions, k, Bstar, areas=(1, 2, 3), min_areas=2):
    """Certified dissemination in space (brain areas PV=1, JC=2, IT=3): True iff at least
    `min_areas` areas have a certified true-lesion count >= 1. On E every certified area truly
    contains a true lesion, so P(certified DIS is false) <= delta."""
    lb = certified_true_counts(regions, k, Bstar, areas)
    return sum(1 for a in areas if lb[a] >= 1) >= min_areas, lb


# ------------------------------------------------------------------ Layer 2: scan-level repair
def scan_safe_inflation_simultaneous(k, n, is_false, fam, max_inflate=400):
    """Smallest inflation c >= 0 such that the scan's TRUE null counts satisfy V_k <= B*_k(c)
    for ALL k (the simultaneous event), hence for every c' >= c (B* is non-decreasing in c:
    G+c grows -> m0_hat grows -> B grows -> B* grows). Calibrating Layer 2 on THIS statistic
    covers the selection, any post-hoc threshold AND every interpolation bound (certified region
    counts / certified DIS) under scan-level exchangeability — calibrating on the selected set's
    FDP alone would cover only that one selection. Returns max_inflate+1 if never satisfied."""
    k = np.asarray(k, np.int64)
    is_false = np.asarray(is_false, bool)
    if k.size == 0 or not is_false.any():
        return 0
    V = np.cumsum(np.bincount(k[is_false], minlength=n + 2))[1:n + 2]

    def ok(c):
        return bool(np.all(V <= simultaneous_bound(k, n, fam, inflate=c)[0]))

    if ok(0):
        return 0
    if not ok(max_inflate):
        return max_inflate + 1
    lo, hi = 0, max_inflate                      # ok(lo) False, ok(hi) True
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if ok(mid):
            hi = mid
        else:
            lo = mid
    return hi


def scan_safe_inflation(k, n, is_false, gamma, fam, max_inflate=200):
    """SELECTION-ONLY variant (kept for comparison): smallest c such that the selected set's FDP
    <= gamma for every c' >= c. Covers ONLY that selection — not the FDP curve, post-hoc
    thresholds or region certificates. Prefer scan_safe_inflation_simultaneous."""
    is_false = np.asarray(is_false, bool)
    last_bad = -1
    for c in range(max_inflate, -1, -1):
        sel, _ = select_fdx(k, n, gamma, fam, inflate=c)
        ns = int(sel.sum())
        if ns and (sel & is_false).sum() / ns > gamma:
            last_bad = c
            break
    return last_bad + 1


def scan_level_theta_pac(safe_values, delta, delta_L=0.05):
    """Training-conditional (PAC) quantile for DEVICE claims (one fixed labelled set is shipped):
    with probability >= 1 - delta_L over the labelled set, P(test curve violated | set) <= delta
    (Vovk 2012 training-conditional split conformal). theta = the (K - j*)-th smallest safe value,
    j* = max{j >= 0 : BinomCDF(j; K, delta) <= delta_L}; None if no j qualifies (K too small —
    e.g. K=20 at delta=0.1, delta_L=0.05; K=29 gives theta = max)."""
    from scipy.stats import binom
    v = np.sort(np.asarray(safe_values, int))
    K = v.size
    js = [j for j in range(K) if binom.cdf(j, K, delta) <= delta_L]
    if not js:
        return None
    return int(v[K - max(js) - 1])


def scan_level_theta(safe_values, delta):
    """Split-conformal quantile over K exchangeable labelled scans: the ceil((K+1)(1-delta))-th
    smallest safe inflation, or None (= abstain on every test scan) if that index exceeds K."""
    v = np.sort(np.asarray(safe_values, int))
    K = v.size
    idx = int(np.ceil((K + 1) * (1 - delta)))
    return None if idx > K else int(v[idx - 1])
