"""Unit tests for the v3 feature families (synthetic volumes only, no patient data).

    python -m pytest research/lesion_detector_v3/test_features_v3.py -q
"""
import inspect
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for p in (os.path.join(ROOT, "backend"), HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import features_v3 as fv                                                  # noqa: E402
from app.services.calm_ms_inference import extract_lesion_candidates    # noqa: E402

SHAPE = (60, 64, 56)


def _ball(center, r, shape=SHAPE):
    g = np.indices(shape).astype(float)
    return ((g[0] - center[0]) ** 2 + (g[1] - center[1]) ** 2 + (g[2] - center[2]) ** 2) <= r * r


def _scene(lesion_delta=80.0, seed=0):
    """Ellipsoidal 'brain' with dark central 'ventricles', two candidate lesions."""
    rng = np.random.RandomState(seed)
    g = np.indices(SHAPE).astype(float)
    c = np.array(SHAPE) / 2.0
    brain = (((g[0] - c[0]) / 27) ** 2 + ((g[1] - c[1]) / 29) ** 2 + ((g[2] - c[2]) / 25) ** 2) <= 1
    flair = np.where(brain, 100.0 + rng.normal(0, 5, SHAPE), 0.0).astype(np.float32)
    vent = _ball(c, 5)
    flair[vent] = 30.0
    l1, l2 = _ball((20, 20, 28), 3), _ball((40, 44, 28), 2)
    flair[l1] += lesion_delta
    flair[l2] += lesion_delta
    prob = np.zeros(SHAPE, np.float32)
    prob[l1] = 0.9
    prob[l2] = 0.7
    t1 = np.where(brain, 200.0 + rng.normal(0, 5, SHAPE), 0.0).astype(np.float32)
    t1[l1] -= 60
    return prob, flair, t1


def _feats(prob, flair=None, t1=None, **kw):
    labeled, cands = extract_lesion_candidates(prob, 0.5, (1.0, 1.0, 1.0), min_volume_mm3=3.0)
    ctx = fv.ScanContext(prob, flair, t1)
    return fv.candidate_features_v3(prob, labeled, cands, ctx, **kw), cands


def test_no_ground_truth_argument_anywhere():
    banned = ("gt", "truth", "label_mask", "expert", "y", "target")
    for name, obj in inspect.getmembers(fv, inspect.isfunction) + inspect.getmembers(fv, inspect.isclass):
        if obj.__module__ != fv.__name__:
            continue
        fn = obj.__init__ if inspect.isclass(obj) else obj
        for p in inspect.signature(fn).parameters:
            assert not any(p == b or p.startswith(b + "_") for b in banned), f"{name}({p})"


def test_bright_lesion_has_positive_contrast_and_dark_has_negative():
    prob, flair, t1 = _scene(+80)
    f, cands = _feats(prob, flair, t1)
    assert len(cands) == 2
    assert np.all(f["fl_contrast"] > 2) and np.all(f["fl_frac_hyper"] > 0.5)
    prob, flair, _ = _scene(-40)
    f, _ = _feats(prob, flair)
    assert np.all(f["fl_contrast"] < 0)


def test_intensity_affine_invariance():
    prob, flair, t1 = _scene()
    f1, _ = _feats(prob, flair, t1)
    brain = flair > 0
    flair2 = np.where(brain, 3.7 * flair + 55.0, 0.0).astype(np.float32)
    t12 = np.where(t1 > 0, 0.5 * t1 + 10.0, 0.0).astype(np.float32)
    f2, _ = _feats(prob, flair2, t12)
    for k in fv.F1 + fv.F2 + fv.F3 + fv.F4_FLAIR + fv.F6:
        np.testing.assert_allclose(f1[k], f2[k], rtol=1e-3, atol=1e-3, err_msg=k)


def test_t1_hypointensity_detected():
    prob, flair, t1 = _scene()
    f, cands = _feats(prob, flair, t1)
    big = int(np.argmax([c.n_voxels for c in cands]))
    assert f["t1_contrast"][big] < -5 and f["t1_frac_hypo"][big] > 0.5


def test_ventricle_and_depth_proxies():
    prob, flair, _ = _scene()
    ctx = fv.ScanContext(prob, flair)
    assert ctx.vent_vox > 0 and ctx.dmax > 15
    f, _ = _feats(prob, flair)
    assert np.all((f["loc_depth_min_rel"] >= 0) & (f["loc_depth_mean_rel"] <= 1))
    assert np.all(f["loc_dvent_min_rel"] > 0)


def test_prob_only_families_without_flair():
    prob, _, _ = _scene()
    f, _ = _feats(prob)
    assert set(f) == set(fv.F4_PROB + fv.F5 + fv.F7)


def test_persistence_merge_and_split():
    prob = np.zeros(SHAPE, np.float32)
    a, b = _ball((20, 30, 28), 3), _ball((30, 30, 28), 3)
    prob[a] = 0.9
    prob[b] = 0.8
    bridge = np.zeros(SHAPE, bool)
    bridge[20:31, 29:32, 27:30] = True
    prob[bridge & ~(a | b)] = 0.3                 # joins the two only at the 0.25 threshold
    f, cands = _feats(prob)
    assert len(cands) == 2
    assert np.all(f["ps_nmerge_025"] == 1)
    assert np.all(f["ps_log_merge_025"] > 0)
    assert np.all(f["ps_surv_075"] == 1.0)
    big = np.zeros(SHAPE, np.float32)
    blob = _ball((30, 32, 28), 5)
    big[blob] = 0.6
    big[_ball((27, 32, 28), 1)] = 0.95
    big[_ball((33, 32, 28), 1)] = 0.95
    f, _ = _feats(big)
    assert f["ps_nsplit_090"][0] == 2


def test_ensemble_placeholder():
    prob, flair, _ = _scene()
    f, _ = _feats(prob, flair, fold_maps=[prob.copy() for _ in range(5)])
    assert np.allclose(f["ens_std"], 0) and np.allclose(f["ens_mi"], 0, atol=1e-9)
    assert np.all(f["ens_frac_detect"] == 1.0)
    folds = [prob * s for s in (1.0, 1.0, 0.5, 0.2, 0.0)]
    f, _ = _feats(prob, fold_maps=folds)
    assert np.all(f["ens_std"] > 0.1) and np.all(f["ens_frac_detect"] < 1.0) and np.all(f["ens_mi"] > 0)
    with pytest.raises(ValueError):
        _feats(prob, fold_maps=[prob])


def test_lstai_placeholder():
    prob, _, _ = _scene()
    f, _ = _feats(prob, lstai=prob.copy())
    assert np.all(f["lst_detect"] == 1) and np.allclose(f["lst_local_dice"], 1.0)
    f, _ = _feats(prob, lstai=np.zeros_like(prob))
    assert np.all(f["lst_detect"] == 0) and np.all(f["lst_local_dice"] == 0)
    with pytest.raises(ValueError):
        _feats(prob, lstai=np.zeros((5, 5, 5), np.float32))


def test_broken_t1_disables_only_the_exploratory_family():
    prob, flair, t1 = _scene()
    empty_t1 = np.zeros_like(t1)
    empty_t1[:3, :3, :3] = 50.0                    # like MSLesSeg P49_T2: almost no T1 signal
    f, _ = _feats(prob, flair, empty_t1)
    assert not any(k in f for k in fv.F2)
    assert all(k in f for k in fv.F1 + fv.F3 + fv.F6)
    assert fv.ScanContext(prob, flair, empty_t1).t1_status.startswith("disabled")


def test_grid_mismatch_is_refused():
    prob, flair, _ = _scene()
    with pytest.raises(ValueError):
        fv.ScanContext(prob, flair[:-1])
