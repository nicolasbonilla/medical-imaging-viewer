"""CALM-MS inference layer: probability map -> risk-controlled lesion mask.

The headline test drives the FULL pipeline on synthetic probability volumes —
extract candidates, calibrate on cases with ground truth, select at a target
alpha — and verifies the realized lesion-level FDR stays <= alpha. This is the
mask-level proof of the guarantee, not just the abstract-score version.
"""
import numpy as np
import pytest

from app.services.calm_ms_inference import (
    extract_lesion_candidates,
    label_candidates_tp,
    build_calibration_nulls,
    select_lesions_conformal,
    SCORE_MAX,
)

SP = (1.0, 1.0, 1.0)
THR = 0.5


def _synthetic_case(rng, n_true=6, n_false=10, shape=(20, 60, 60),
                    true_p=0.86, false_p=0.62, sigma=0.03):
    """A soft probability volume with separated true/false lesion blobs + GT.

    True blobs score high, false blobs score lower but still above threshold;
    background is sub-threshold noise. base - 3σ > threshold keeps each blob a
    single 18-connected component.
    """
    prob = rng.uniform(0.0, 0.12, size=shape)
    gt = np.zeros(shape, np.uint8)
    positions = [(z, y, x)
                 for z in range(2, shape[0] - 3, 5)
                 for y in range(2, shape[1] - 4, 8)
                 for x in range(2, shape[2] - 4, 8)]
    rng.shuffle(positions)
    for i, (z, y, x) in enumerate(positions[:n_true + n_false]):
        is_true = i < n_true
        base = true_p if is_true else false_p
        block = np.clip(base + rng.normal(0, sigma, size=(3, 3, 3)), 0, 1)
        prob[z:z + 3, y:y + 3, x:x + 3] = block
        if is_true:
            gt[z:z + 3, y:y + 3, x:x + 3] = 1
    return prob, gt


# --- extraction -------------------------------------------------------------

def test_extract_counts_and_scores():
    rng = np.random.RandomState(0)
    prob, gt = _synthetic_case(rng, n_true=4, n_false=6)
    labeled, cands = extract_lesion_candidates(prob, THR, SP)
    assert len(cands) == 10                       # all blobs recovered
    assert all(c.n_voxels == 27 for c in cands)   # 3x3x3
    assert all(0.5 < c.score <= 1.0 for c in cands)


def test_min_volume_filter_drops_specks():
    prob = np.zeros((6, 20, 20), dtype=float)
    prob[1:4, 2:5, 2:5] = 0.9      # 27-voxel real blob
    prob[1, 10, 10] = 0.9          # 1-voxel speck -> below 3 mm3 floor
    _, cands = extract_lesion_candidates(prob, THR, SP)
    assert len(cands) == 1
    assert cands[0].n_voxels == 27


def test_extract_empty():
    _, cands = extract_lesion_candidates(np.zeros((5, 5, 5)), THR, SP)
    assert cands == []


def test_score_max_vs_mean():
    prob = np.zeros((4, 10, 10))
    prob[1:3, 2:4, 2:4] = 0.6
    prob[1, 2, 2] = 0.99            # one peak voxel
    _, mean_c = extract_lesion_candidates(prob, THR, SP, score="mean")
    _, max_c = extract_lesion_candidates(prob, THR, SP, score=SCORE_MAX)
    assert max_c[0].score == pytest.approx(0.99)
    assert mean_c[0].score < max_c[0].score


# --- TP/FP labelling & calibration -----------------------------------------

def test_tp_labelling():
    rng = np.random.RandomState(1)
    prob, gt = _synthetic_case(rng, n_true=5, n_false=7)
    labeled, cands = extract_lesion_candidates(prob, THR, SP)
    is_tp = label_candidates_tp(labeled, cands, gt)
    assert sum(is_tp.values()) == 5           # exactly the true blobs match GT
    assert len(is_tp) == 12


def test_calibration_collects_only_false_scores():
    rng = np.random.RandomState(2)
    cases = [_synthetic_case(rng, n_true=4, n_false=8) for _ in range(3)]
    nulls = build_calibration_nulls(cases, THR, SP)
    assert nulls.size == 24                     # 8 false * 3 cases
    # false blobs centre on 0.62; nulls should sit well below the true 0.86
    assert nulls.mean() < 0.72


# --- selection & the guarantee ---------------------------------------------

def test_selection_paints_only_selected():
    rng = np.random.RandomState(4)
    calib = build_calibration_nulls([_synthetic_case(rng) for _ in range(6)], THR, SP)
    prob, gt = _synthetic_case(rng)
    res = select_lesions_conformal(prob, calib, 0.1, THR, SP)
    assert res.n_selected == sum(c.selected for c in res.candidates)
    # painted voxels equal the union of selected candidate footprints
    labeled, cands = extract_lesion_candidates(prob, THR, SP)
    sel_labels = {c.label for c in res.candidates if c.selected}
    expected = np.isin(labeled, list(sel_labels)) if sel_labels else np.zeros_like(labeled, bool)
    assert np.array_equal(res.mask > 0, expected)
    # every candidate carries a calibrated confidence
    assert all(c.confidence is not None and 0.0 <= c.confidence <= 1.0 for c in res.candidates)


def test_dial_monotone():
    rng = np.random.RandomState(5)
    calib = build_calibration_nulls([_synthetic_case(rng) for _ in range(6)], THR, SP)
    prob, _ = _synthetic_case(rng)
    counts = [select_lesions_conformal(prob, calib, a, THR, SP).n_selected
              for a in (0.02, 0.05, 0.1, 0.2, 0.4)]
    assert counts == sorted(counts), counts


@pytest.mark.parametrize("alpha", [0.10, 0.20])
def test_pipeline_controls_lesion_fdr(alpha):
    """Full pipeline: realized lesion-level FDR <= alpha across synthetic cohorts."""
    rng = np.random.RandomState(11)
    calib = build_calibration_nulls([_synthetic_case(rng) for _ in range(10)], THR, SP)
    assert calib.size > 0
    fdps = []
    for _ in range(120):
        prob, gt = _synthetic_case(rng)
        res = select_lesions_conformal(prob, calib, alpha, THR, SP)
        labeled, cands = extract_lesion_candidates(prob, THR, SP)
        is_tp = label_candidates_tp(labeled, cands, gt)
        sel = [c for c in res.candidates if c.selected]
        if sel:
            fp = sum(1 for c in sel if not is_tp[c.label])
            fdps.append(fp / len(sel))
    assert float(np.mean(fdps)) <= alpha + 0.03, (np.mean(fdps), alpha)
