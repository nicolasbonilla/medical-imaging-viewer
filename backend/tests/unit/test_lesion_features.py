"""CALM-MS Phase 2 — per-lesion feature extraction.

A sharp, large true lesion and a small, diffuse false candidate are planted in
one probability map; the extracted features must reflect exactly the structural
differences the scorer will lean on (volume, edge sharpness, shape), and the
optional second-model agreement feature must fire only where the two masks agree.
"""
import numpy as np

from app.services.calm_ms_inference import extract_lesion_candidates
from app.services.lesion_features import feature_matrix, FEATURE_NAMES

SP = (1.0, 1.0, 1.0)
THR = 0.5


def _ball(shape, center, radius):
    zz, yy, xx = np.ogrid[:shape[0], :shape[1], :shape[2]]
    d2 = (zz - center[0]) ** 2 + (yy - center[1]) ** 2 + (xx - center[2]) ** 2
    return d2 <= radius ** 2


def _planted_map():
    shape = (16, 48, 48)
    prob = np.full(shape, 0.10)
    # TP: big sharp ball at (8,14,14) — interior 0.72, ring drops to 0.15.
    tp_core = _ball(shape, (8, 14, 14), 3)
    tp_ring = _ball(shape, (8, 14, 14), 4) & ~tp_core
    prob[tp_core] = 0.72
    prob[tp_ring] = 0.15
    # FP: small diffuse ball at (8,34,34) — same interior 0.72, soft ring 0.45.
    fp_core = _ball(shape, (8, 34, 34), 2)
    fp_ring = _ball(shape, (8, 34, 34), 3) & ~fp_core
    prob[fp_core] = 0.72
    prob[fp_ring] = 0.45
    return prob, tp_core, fp_core


def test_feature_matrix_shape_and_finiteness():
    prob, _, _ = _planted_map()
    labeled, cands = extract_lesion_candidates(prob, THR, SP, min_volume_mm3=8)
    X, names = feature_matrix(prob, labeled, cands, SP)
    assert names == FEATURE_NAMES
    assert X.shape == (len(cands), len(FEATURE_NAMES))
    assert np.isfinite(X).all()
    assert len(cands) == 2


def test_features_separate_sharp_large_from_diffuse_small():
    prob, tp_core, _ = _planted_map()
    labeled, cands = extract_lesion_candidates(prob, THR, SP, min_volume_mm3=8)
    X, names = feature_matrix(prob, labeled, cands, SP)
    idx = {n: k for k, n in enumerate(names)}
    # Identify rows by which one overlaps the planted TP core.
    tp_row = max(range(len(cands)),
                 key=lambda r: np.logical_and(labeled == cands[r].label, tp_core).sum())
    fp_row = 1 - tp_row
    assert X[tp_row, idx["log_volume"]] > X[fp_row, idx["log_volume"]]
    assert X[tp_row, idx["boundary_contrast"]] > X[fp_row, idx["boundary_contrast"]]
    assert X[tp_row, idx["surface_to_vol"]] < X[fp_row, idx["surface_to_vol"]]
    # Mean posterior is deliberately near-equal — raw score cannot separate these.
    assert abs(X[tp_row, idx["mean_prob"]] - X[fp_row, idx["mean_prob"]]) < 0.05


def test_agreement_feature_fires_only_where_masks_overlap():
    prob, tp_core, fp_core = _planted_map()
    labeled, cands = extract_lesion_candidates(prob, THR, SP, min_volume_mm3=8)
    second = tp_core.astype(np.uint8)          # a 2nd model that found only the TP
    X, names = feature_matrix(prob, labeled, cands, SP, second_mask=second)
    idx = {n: k for k, n in enumerate(names)}
    tp_row = max(range(len(cands)),
                 key=lambda r: np.logical_and(labeled == cands[r].label, tp_core).sum())
    fp_row = 1 - tp_row
    assert X[tp_row, idx["agreement"]] > 0.9    # TP fully agreed
    assert X[fp_row, idx["agreement"]] < 0.1    # FP unsupported by the 2nd model
