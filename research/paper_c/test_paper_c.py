"""Paper C — unit tests on synthetic data (no patient or cohort data needed).

    python -m pytest research/paper_c/test_paper_c.py -q
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import conformal as K  # noqa: E402
import detectors as D  # noqa: E402


# ----------------------------------------------------------------------------- conformal
def test_k_marginal_and_pac_values():
    assert K.k_marginal(19, 0.1) == 18
    assert K.k_marginal(19, 0.2) == 16
    assert K.k_marginal(5, 0.1) == 6          # > n -> abstain
    assert K.k_pac(19, 0.2, 0.1) == 18
    assert K.k_pac(19, 0.1, 0.1) == 20        # 0.9**19 = 0.135 > 0.1 -> abstain
    assert K.k_pac(24, 0.1, 0.1) == 24        # 0.9**24 = 0.080 <= 0.1
    assert K.threshold([1.0, 2.0, 3.0], 0.1) == float("inf")


def test_strict_selection_with_ties():
    cands = [{"score": 2.0, "true": False}, {"score": 3.0, "true": True, "hits": [1]}]
    r = K.evaluate_patient(cands, 2.0)
    assert r["false_call"] is False and r["true_flag"] is True and r["lesions_hit"] == [1]
    r = K.evaluate_patient(cands, float("-inf"))
    assert r["false_call"] is True


@pytest.mark.parametrize("alpha", [0.1, 0.2])
def test_marginal_validity_simulation(alpha):
    """Exchangeable max-false scores with an atom at -inf (patients with no false candidate)."""
    rng = np.random.default_rng(0)
    n, reps = 19, 20000
    exceed = 0
    for _ in range(reps):
        m = rng.gamma(2.0, 1.0, n + 1)
        m[rng.random(n + 1) < 0.3] = float("-inf")
        lam = K.threshold(list(m[:n]), alpha)
        exceed += m[n] > lam
    rate = exceed / reps
    assert rate <= alpha + 3 * np.sqrt(alpha * (1 - alpha) / reps)
    assert rate >= alpha - 1.0 / (n + 1) - 0.02     # not wildly conservative


def test_pac_validity_simulation():
    rng = np.random.default_rng(1)
    n, alpha, delta, reps = 24, 0.1, 0.1, 4000
    bad = 0
    for _ in range(reps):
        m = rng.normal(size=n)
        lam = K.threshold(list(m), alpha, method="pac", delta=delta)
        cond = 1.0 - (0.5 * (1 + __import__("math").erf(lam / np.sqrt(2))) if np.isfinite(lam) else 1.0)
        bad += cond > alpha
    assert bad / reps <= delta + 3 * np.sqrt(delta * (1 - delta) / reps)


def test_clopper_pearson_and_bootstrap():
    lo, hi = K.clopper_pearson(0, 20)
    assert lo == 0.0 and abs(hi - 0.1684) < 1e-3
    est, lo, hi = K.cluster_bootstrap([1, 0, 1, 1], [2, 2, 2, 2], B=200)
    assert est == pytest.approx(3 / 8) and lo <= est <= hi


# ----------------------------------------------------------------------------- truth rules
def _ball(shape, center, r):
    z, y, x = np.ogrid[:shape[0], :shape[1], :shape[2]]
    return (z - center[0]) ** 2 + (y - center[1]) ** 2 + (x - center[2]) ** 2 <= r * r


def test_truth_from_two_masks():
    sh = (40, 40, 40)
    a = _ball(sh, (10, 10, 10), 3)                       # persistent lesion
    a |= _ball(sh, (28, 28, 28), 2)                      # will enlarge
    b = _ball(sh, (10, 10, 10), 3)
    b |= _ball(sh, (28, 28, 28), 4)                      # enlarged (33 -> 257 voxels)
    b |= _ball(sh, (10, 30, 20), 3)                      # new, far away
    t, region, lmap = C.truth_from_two_masks(a, b, 1.0)
    kinds = sorted(it["kind"] for it in t["items"])
    assert kinds == ["enlarging", "new", "persistent"]
    assert t["active"] and t["n_new_clinical"] == 1 and t["n_enlarging"] == 1
    assert region[10, 30, 20] and not region[10, 10, 10] and not region[28, 28, 28]   # growth only
    assert lmap.max() == 2
    t2, _, _ = C.truth_from_two_masks(a, a.copy(), 1.0)
    assert not t2["active"]


def test_truth_adjacent_component_is_not_new():
    sh = (30, 30, 30)
    a = _ball(sh, (15, 15, 10), 3)
    b = a.copy()
    b |= _ball(sh, (15, 15, 15), 2) & ~ _ball(sh, (15, 15, 10), 4)   # within ~1 voxel of a
    t, _, _ = C.truth_from_two_masks(a, b, 1.0)
    assert all(it["kind"] != "new" or it["volume_mm3"] < C.DETECT_MM3 for it in t["items"]) or t["n_new_detectable"] == 0


def test_truth_from_change_mask_sign():
    sh = (30, 30, 30)
    gt = _ball(sh, (8, 8, 8), 3) | _ball(sh, (20, 20, 20), 3)
    sub = np.zeros(sh, np.float32)
    sub[_ball(sh, (8, 8, 8), 3)] = 2.0                  # brighter at follow-up -> positive
    sub[_ball(sh, (20, 20, 20), 3)] = -2.0              # darker -> negative
    t, r_any, r_pos, lmap = C.truth_from_change_mask(gt, sub, np.ones(sh, bool), 1.0)
    assert t["n_components"] == 2 and t["n_positive"] == 1 and t["active"]
    assert r_any[20, 20, 20] and not r_pos[20, 20, 20] and r_pos[8, 8, 8]
    assert lmap.max() >= 1 and lmap[20, 20, 20] == 0


# ----------------------------------------------------------------------------- detectors
def _pair_images(seed=0):
    rng = np.random.default_rng(seed)
    sh = (40, 48, 48)
    brain = _ball(sh, (20, 24, 24), 18)
    fa = (100 + 5 * rng.standard_normal(sh)).astype(np.float32) * brain
    fb = (100 + 5 * rng.standard_normal(sh)).astype(np.float32) * brain
    lesion = _ball(sh, (20, 20, 28), 3)
    fb[lesion] += 60.0                                   # new bright lesion at follow-up
    return fa, fb, brain, lesion


def test_dsub_finds_new_bright_lesion_and_drops_specks():
    fa, fb, brain, lesion = _pair_images()
    fb[20, 30, 15] += 80.0                               # one-voxel speck (< 14.14 mm3)
    d, zb, interior = D.subtraction(fa, fb, brain)
    cands = D.dsub_candidates(d, zb, interior, 1.0)
    assert len(cands) >= 1
    big = max(cands, key=lambda c: c["volume_mm3"])
    assert big["volume_mm3"] >= C.CLIN_MM3 and big["score"] > 1.5
    assert lesion[big["_idx"]].mean() > 0.5
    assert all(c["volume_mm3"] >= C.CLIN_MM3 for c in cands)


def test_dseg_reproduces_app_counts_and_scores():
    fa, fb, brain, lesion = _pair_images(1)
    d, zb, interior = D.subtraction(fa, fb, brain)
    pa = np.zeros(fa.shape, np.float32)
    pb = np.zeros(fa.shape, np.float32)
    old = _ball(fa.shape, (20, 30, 18), 3)
    pa[old] = 0.9
    pb[old] = 0.9
    pb[lesion] = 0.95                                    # new lesion in the follow-up mask
    cands, flags = D.dseg_candidates(pa, pb, d, brain, (1.0, 1.0, 1.0))
    assert flags["app_activity"] and flags["app_new_significant"] == 1
    new = [c for c in cands if c["kind"] == "new"]
    assert len(new) == 1 and new[0]["score_sub"] > 1.0 and new[0]["score_dp"] == pytest.approx(0.95, abs=1e-5)
    assert flags["app_activity_subconfirmed"]
