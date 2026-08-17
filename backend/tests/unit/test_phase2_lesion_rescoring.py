"""CALM-MS Phase 2 headline: a learned score beats the base score under the SAME
conformal FDR guarantee.

The planted cohort is adversarial to the raw score on purpose: true and false
candidates share the same mean posterior (~0.72), so the base segmenter's pooled
probability cannot tell them apart. They differ only in structure — true lesions
are larger with a sharper edge. The test asserts (a) the split-conformal guarantee
still holds for the learned curve (realized FDR stays near/below the target) and
(b) the learned score recovers materially more sensitivity at matched FDR, which
is the entire point of Phase 2.
"""
import numpy as np

from app.services.phase2_lesion_rescoring import (
    build_case_table,
    run_loo_rescoring_experiment,
)

SP = (1.0, 1.0, 1.0)
THR = 0.5
ALPHAS = [0.1, 0.2, 0.3]


def _ball(shape, center, radius):
    zz, yy, xx = np.ogrid[:shape[0], :shape[1], :shape[2]]
    d2 = (zz - center[0]) ** 2 + (yy - center[1]) ** 2 + (xx - center[2]) ** 2
    return d2 <= radius ** 2


def _planted_case(rng, n_true=4, n_false=4):
    """A prob volume where TP and FP share mean posterior but differ in structure.

    TP: radius-3 ball, ring drops to 0.15 (sharp). FP: radius-2 ball, ring 0.45
    (soft, sub-threshold). Interiors both ~0.72 -> raw score is uninformative.
    """
    shape = (16, 80, 80)
    prob = np.full(shape, 0.10)
    gt = np.zeros(shape, dtype=np.uint8)

    # Grid of well-separated slots so components never merge.
    slots = [(z, y, x) for z in (5, 11) for y in range(10, 75, 14) for x in range(10, 75, 14)]
    order = rng.permutation(len(slots))
    ti = 0
    for k in range(n_true):
        c = slots[order[ti]]; ti += 1
        core = _ball(shape, c, 3)
        ring = _ball(shape, c, 4) & ~core
        prob[core] = np.clip(rng.normal(0.72, 0.02, size=core.sum()), 0.55, 0.95)
        prob[ring] = 0.15
        gt[core] = 1
    for k in range(n_false):
        c = slots[order[ti]]; ti += 1
        core = _ball(shape, c, 2)
        ring = _ball(shape, c, 3) & ~core
        prob[core] = np.clip(rng.normal(0.72, 0.02, size=core.sum()), 0.55, 0.95)
        prob[ring] = 0.45
    return prob, gt


def _cohort(n_cases=12, seed=7):
    rng = np.random.default_rng(seed)
    return [_planted_case(rng) for _ in range(n_cases)]


def test_build_case_table_has_both_classes():
    rng = np.random.default_rng(0)
    prob, gt = _planted_case(rng)
    t = build_case_table(prob, gt, THR, SP, min_volume_mm3=8)
    assert t["X"].shape[0] == t["raw"].size == t["tp"].size
    assert t["tp"].any() and (~t["tp"]).any()          # both TP and FP present
    assert t["n_gt"] >= 1


def test_learned_score_lifts_sensitivity_and_keeps_guarantee():
    cases = _cohort()
    res = run_loo_rescoring_experiment(
        cases, ALPHAS, THR, SP, min_volume_mm3=8, l2=0.1, n_iter=800)

    raw = {c["alpha"]: c for c in res["curve_raw"]}
    learned = {c["alpha"]: c for c in res["curve_learned"]}

    # Baseline over-selects: FDR near 0.5 (half the candidates are false).
    assert res["baseline"]["fdr_mean"] > 0.35

    for a in ALPHAS:
        # Guarantee preserved for the learned curve (finite-sample slack allowed).
        assert learned[a]["realized_fdr_mean"] <= a + 0.12
        # Learned never worse than raw on sensitivity...
        assert learned[a]["sensitivity_mean"] >= raw[a]["sensitivity_mean"] - 1e-9

    # ...and materially better where it counts (the most permissive target).
    assert learned[0.3]["sensitivity_mean"] > raw[0.3]["sensitivity_mean"] + 0.05


def test_second_model_agreement_feature_runs():
    """Supplying a second-model mask (agreement feature) must not break the run."""
    cases = _cohort(n_cases=6, seed=11)
    seconds = []
    for prob, gt in cases:
        # A second model that recovers most of the expert GT (strong agreement).
        seconds.append((gt > 0).astype(np.uint8))
    res = run_loo_rescoring_experiment(
        cases, [0.2], THR, SP, min_volume_mm3=8, second_masks=seconds,
        l2=0.1, n_iter=600)
    assert res["curve_learned"][0]["realized_fdr_mean"] <= 0.2 + 0.15
