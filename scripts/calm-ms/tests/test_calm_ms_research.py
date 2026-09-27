"""Regression tests for the CALM-MS multi-site research scripts (synthetic, no data needed).

Each test pins a defect that an adversarial review actually found, so it cannot silently
come back:
  * many-to-one matching mislabeling over-segmentation fragments as TP  -> Hungarian 1-to-1
  * per-scan FDP exceedance computed over selecting scans only           -> over ALL scans
  * recall numerator/denominator from inconsistent matches               -> e2e <= selection
  * POOLED null containing the test site (in-sample leak)                -> leave-one-site-out
  * multi-timepoint cohort treated as one-scan-per-subject (ISBI leak)   -> registry fails closed

    backend/venv/Scripts/python -m pytest scripts/calm-ms/tests -q
"""
import importlib.util
import json
import os
import sys
from types import SimpleNamespace

import numpy as np
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_CALM = os.path.dirname(_HERE)
_BACKEND = os.path.join(_CALM, "..", "..", "backend")
for p in (_CALM, _BACKEND):
    if p not in sys.path:
        sys.path.insert(0, p)


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_CALM, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


reg = _load("cohort_registry_t", "cohort_registry.py")
adv = _load("multisite_adv_t", "multisite_conformal_advanced.py")


# ----------------------------------------------------------------------------- registry
def _mk_cohort(root, name, n=2, cohort_json=None):
    d = root / name
    d.mkdir(parents=True)
    for i in range(n):
        (d / f"{name}_c{i}_prob.nii.gz").write_bytes(b"")
        (d / f"{name}_c{i}_gt.nii.gz").write_bytes(b"")
    if cohort_json is not None:
        (d / "cohort.json").write_text(json.dumps(cohort_json))
    return d


def test_registry_builtins_keep_fixed_order(tmp_path):
    for sub in ("isbi19-lstai", "sibbms-controls-flames", "mslesseg-flames", "openms-flames"):
        _mk_cohort(tmp_path, sub)
    sites, skipped = reg.discover_sites(str(tmp_path), log=lambda *_: None)
    assert list(sites) == ["openms", "mslesseg", "sibbms", "isbi"]   # RNG-order stability
    assert sites["isbi"]["null_source"] is False and sites["isbi"]["mondrian"] is False
    assert skipped == []


def test_registry_skips_unknown_cohort_without_cohort_json(tmp_path):
    _mk_cohort(tmp_path, "mystery-cohort")
    sites, skipped = reg.discover_sites(str(tmp_path), log=lambda *_: None)
    assert "mystery-cohort" not in sites and skipped == [("mystery-cohort", "no cohort.json")]


def test_registry_forces_test_only_when_grouping_untrustworthy(tmp_path):
    _mk_cohort(tmp_path, "nnunet-x", cohort_json={"site": "nnx", "seg": "nnU-Net",
                                                  "kind": "patients", "null_source": True})
    sites, _ = reg.discover_sites(str(tmp_path), log=lambda *_: None)
    assert sites["nnx"]["null_source"] is False and sites["nnx"]["mondrian"] is False


def test_registry_accepts_trustworthy_grouping_and_groups_timepoints(tmp_path):
    _mk_cohort(tmp_path, "nnunet-y", cohort_json={"site": "nny", "seg": "nnU-Net",
                                                  "kind": "patients",
                                                  "subject_regex": r"pt(\d+)_t\d+"})
    sites, _ = reg.discover_sites(str(tmp_path), log=lambda *_: None)
    assert sites["nny"]["null_source"] is True and sites["nny"]["mondrian"] is True
    a = reg.subject_of("nny", "pt7_t1", sites["nny"])
    b = reg.subject_of("nny", "pt7_t2", sites["nny"])
    assert a == b                                   # timepoints collapse to one subject
    with pytest.raises(ValueError):                 # never a per-case fallback
        reg.subject_of("nny", "unexpected_name", sites["nny"])


def test_registry_mslesseg_subject_key_is_backward_compatible():
    meta = reg.BUILTIN["mslesseg"]
    assert reg.subject_of("mslesseg", "mslesseg_P10_T2", meta) == "mslesseg_P10"
    assert reg.subject_of("mslesseg", "mslesseg_P54", meta) == "mslesseg_P54"
    assert reg.subject_of("openms", "openms_patient01", reg.BUILTIN["openms"]) == "openms:openms_patient01"


def test_same_seg_pairs_exclude_cross_segmenter_and_test_only():
    sites = {k: dict(v) for k, v in reg.BUILTIN.items()}
    pairs = reg.same_seg_patient_pairs(sites)
    assert pairs == [("openms", "mslesseg"), ("mslesseg", "openms")]


# ------------------------------------------------------------- one-to-one matching
def _cands(labeled):
    return [SimpleNamespace(label=int(l)) for l in np.unique(labeled) if l != 0]


def test_hungarian_is_one_to_one_surplus_fragment_becomes_fp():
    # One GT lesion (label 1) covered by TWO candidate fragments (labels 1 and 2).
    gt = np.zeros((1, 1, 10), int); gt[0, 0, 0:6] = 1
    lab = np.zeros((1, 1, 10), int); lab[0, 0, 0:3] = 1; lab[0, 0, 3:6] = 2
    counts = np.bincount(gt.ravel())
    m = adv._hungarian(lab, _cands(lab), gt, counts, {1}, 0.0)
    matched = [c for c, (g, _) in m.items() if g > 0]
    assert len(matched) == 1, "a GT lesion must be claimed by at most ONE candidate"


def test_hungarian_respects_iou_threshold():
    gt = np.zeros((1, 1, 20), int); gt[0, 0, 0:20] = 1          # big GT
    lab = np.zeros((1, 1, 20), int); lab[0, 0, 0:1] = 1           # tiny fragment IoU=0.05
    counts = np.bincount(gt.ravel())
    assert adv._hungarian(lab, _cands(lab), gt, counts, {1}, 0.0)[1][0] == 1
    assert adv._hungarian(lab, _cands(lab), gt, counts, {1}, 0.10)[1][0] == 0   # strict -> FP


# ------------------------------------------------------ denominators / recalls
def _case(mg, n_gt, clin, scores=None):
    mg = np.asarray(mg, int)
    return {"mg0": mg, "mg1": mg, "n_gt": n_gt, "n_gt_clin": len(clin),
            "clin_gt": np.asarray(clin, int),
            "scores": np.asarray(scores if scores is not None else np.ones(len(mg)))}


def test_perscan_exceedance_counts_zero_selection_scans_in_denominator():
    c1 = _case([0, 0], 2, [])            # selects 2 FPs -> FDP 1.0 > alpha
    c2 = _case([1, 2], 2, [])            # selects nothing -> FDP 0, cannot exceed
    sel = [np.array([True, True]), np.array([False, False])]
    micro, nsel, fdps, frac = adv._agg_fdr_perscan([c1, c2], sel, "lenient_iou0", 0.2)
    assert micro == 1.0 and nsel == 2
    assert frac == 0.5, "exceedance must be over ALL scans (1 of 2), not selecting-only (1 of 1)"


def test_recalls_are_consistent_and_ordered():
    # GT ids 1..4 valid; candidates matched to 1,2 (detectable), GT 3,4 never proposed.
    c = _case([1, 2, 0], n_gt=4, clin=[1, 3])
    sel = [np.array([True, False, True])]
    seln, e2e, clin = adv._recalls([c], sel, "lenient_iou0")
    assert seln == pytest.approx(1 / 2)          # 1 of 2 detectable GT selected
    assert e2e == pytest.approx(1 / 4)           # 1 of 4 valid GT
    assert clin == pytest.approx(1 / 2)          # GT 1 is clinical-size, of {1,3}
    assert e2e <= seln


# ------------------------------------------------------------ pooled null leak
def test_pooled_null_is_leave_one_site_out_and_same_segmenter(monkeypatch):
    ms = _load("multisite_fdr_t", "multisite_conformal_fdr.py")
    sites = {k: dict(v) for k, v in reg.BUILTIN.items()}
    monkeypatch.setattr(ms, "SITES", sites)
    cases = [
        {"site": "openms", "subject": "o1", "scores": np.array([0.1, 0.2]), "is_false0": np.array([True, True])},
        {"site": "mslesseg", "subject": "m1", "scores": np.array([0.3]), "is_false0": np.array([True])},
        {"site": "isbi", "subject": "i1", "scores": np.array([0.9]), "is_false0": np.array([True])},
    ]
    assert sorted(ms._pooled_for(cases, "is_false0", "openms")) == [0.3]          # excludes itself
    assert sorted(ms._pooled_for(cases, "is_false0", "mslesseg")) == [0.1, 0.2]
    # isbi (LST-AI) has no same-seg null source -> shipped FLAMeS pool (cross-seg probe),
    # and isbi's own untrustworthy scores never enter any null.
    assert sorted(ms._pooled_for(cases, "is_false0", "isbi")) == [0.1, 0.2, 0.3]
