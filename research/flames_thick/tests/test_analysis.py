"""Pre-registered metrics and decision rules on synthetic volumes (before any real map exists)."""
import json
import os
import sys

import nibabel as nib
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from flames_thick import analysis as an, eval_cases as ec  # noqa: E402


def blob(shape, centre, r):
    z, y, x = np.ogrid[:shape[0], :shape[1], :shape[2]]
    return (z - centre[0]) ** 2 + (y - centre[1]) ** 2 + (x - centre[2]) ** 2 <= r * r


def test_scan_metrics_counts_tp_fp_fn_and_f1():
    shape = (40, 40, 40)
    gt = blob(shape, (10, 10, 10), 3) | blob(shape, (30, 30, 30), 3) | blob(shape, (10, 30, 20), 2)
    prob = np.zeros(shape, np.float32)
    prob[blob(shape, (10, 10, 11), 3)] = 0.9            # matches lesion 1
    prob[blob(shape, (30, 30, 30), 2)] = 0.7            # matches lesion 2
    prob[blob(shape, (25, 5, 5), 2)] = 0.8              # false lesion
    prob[20, 20, 20] = 0.99                             # 1 voxel = 1 mm^3 < 3 mm^3: ignored
    m = an.scan_metrics(prob, gt, 1.0)
    assert (m["n_gt"], m["n_pred"], m["tp"], m["fp"], m["fn"]) == (3, 3, 2, 1, 1)
    assert np.isclose(m["f1"], 4 / 6)
    assert sorted(m["gt_detected"]) == [0, 1, 1] and len(m["gt_vol_mm3"]) == 3
    assert 0 < m["dice"] < 1


def test_one_to_one_matching_a_merged_prediction_counts_once():
    shape = (30, 30, 30)
    gt = blob(shape, (15, 10, 15), 3) | blob(shape, (15, 20, 15), 3)
    prob = np.zeros(shape, np.float32)
    prob[10:21, 6:25, 10:21] = 0.9                      # one big component covering both lesions
    m = an.scan_metrics(prob, gt, 1.0)
    assert (m["tp"], m["fp"], m["fn"]) == (1, 0, 1)


def test_strict_iou_rejects_a_tiny_overlap():
    shape = (30, 30, 30)
    gt = blob(shape, (15, 15, 15), 5)
    prob = np.zeros(shape, np.float32)
    prob[15:18, 19:22, 15:18] = 0.9                     # touches the lesion edge, IoU << 0.1
    m = an.scan_metrics(prob, gt, 1.0)
    assert m["tp"] == 1 and m["tp_strict"] == 0 and m["fp_strict"] == 1


def test_empty_scan_f1_is_one():
    m = an.scan_metrics(np.zeros((10, 10, 10), np.float32), np.zeros((10, 10, 10)), 1.0)
    assert m["f1"] == 1.0 and m["dice"] == 1.0


def test_cluster_bootstrap_ci_covers_and_respects_clusters():
    pats = [f"p{i // 3}" for i in range(60)]                   # 20 patients x 3 scans
    rng = np.random.default_rng(0)
    x = np.repeat(rng.normal(0.05, 0.05, 20), 3)              # fully clustered effect
    cl = an.Clustered(pats, b=4000)
    p, (lo, hi) = cl.mean(x)
    assert lo < p < hi and lo < 0.05 < hi + 0.03
    p2, (lo2, hi2) = an.Clustered([f"s{i}" for i in range(60)], b=4000).mean(x)
    assert (hi - lo) > 1.3 * (hi2 - lo2)                       # ignoring clusters would be too narrow
    r, (rlo, rhi) = cl.ratio(np.full(60, 2.0), np.full(60, 1.0))
    assert r == 2.0 and rlo == rhi == 2.0


@pytest.mark.parametrize("d,fr,expected", [
    ((0.05, [0.02, 0.08]), (1.0, [0.9, 1.08]), "success"),
    ((0.02, [0.005, 0.04]), (1.0, [0.9, 1.05]), "inconclusive"),        # CI > 0 but below the SESOI
    ((0.05, [0.02, 0.08]), (1.12, [1.02, 1.25]), "inconclusive"),       # FP ratio CI crosses 1.10
    ((0.0, [-0.02, 0.025]), (1.0, [0.9, 1.1]), "refuted"),               # cannot reach +0.03
    ((0.06, [0.03, 0.09]), (1.3, [1.15, 1.45]), "refuted"),              # clearly more false lesions
])
def test_h1_decision_rule(d, fr, expected):
    assert an.verdict_h1(d, fr) == expected


def test_h2_decision_rule():
    ok = an.verdict_h2((0.0, [-0.01, 0.01]), (0.0, [-0.02, 0.02]), -0.01, -0.02)
    assert ok == "non-inferior"
    assert an.verdict_h2((0.0, [-0.03, 0.01]), (0.0, [-0.02, 0.02]), 0.0, 0.0) == "not shown"
    assert an.verdict_h2((0.0, [-0.01, 0.01]), (0.0, [-0.02, 0.02]), -0.05, 0.0) == "not shown"


def test_minimum_reliable_size():
    assert an.min_reliable([0.36, 0.72, 0.81, 0.87, 0.90], 0.8) == "[50,150)"
    assert an.min_reliable([0.36, 0.72, 0.81, 0.87, 0.90], 0.5) == "[14,50)"
    assert an.min_reliable([0.13, 0.45, 0.59, 0.66, 0.76], 0.8) is None
    assert an.min_reliable([0.6, 0.4, 0.7, 0.8, 0.9], 0.5) == "[50,150)"     # must hold for all larger bins


def test_eval_set_selection_and_guards():
    ids = ([f"mslesseg_P{p}_T1" for p in range(1, 54)] + [f"mslesseg_P{p}" for p in range(54, 76)]
           + [f"openms_patient{n:02d}" for n in range(1, 31)] + [f"ms3seg_{i:03d}" for i in range(1, 101)]
           + [f"muslim_{i:02d}" for i in range(1, 52)] + [f"pedims_P{i}_T1" for i in range(1, 29)])
    sel, counts = ec.select(ids)
    assert counts == ec.EXPECTED and len(sel) == 211
    assert not any(c.startswith("mslesseg_P") and "_T" in c for c in sel)
    assert {c for c in sel if c.startswith("openms")} == {f"openms_patient{n:02d}" for n in ec.OPENMS_CLEAN}
    with pytest.raises(SystemExit):
        ec.select(ids[:-1])                                        # one PediMS scan missing
    assert ec.band(1.0) == "B1" and ec.band(3.9) == "B2" and ec.band(6.0) == "B3" and ec.band(7.2) == "B4"
    assert ec.patient_of("pedims_P3_T4") == "pedims_P3" and ec.patient_of("mslesseg_P60") == "mslesseg_P60"


def _write(path, data, zooms=(1.0, 1.0, 1.0)):
    img = nib.Nifti1Image(np.asarray(data, np.float32), np.diag(list(zooms) + [1.0]))
    nib.save(img, path)


def test_main_end_to_end_on_a_synthetic_mini_cohort(tmp_path):
    """Runs the CLI on 211 tiny synthetic scans (A better than R on thick sites by construction)."""
    ref, new, man = tmp_path / "ref", tmp_path / "new", tmp_path / "man"
    for d in (ref, new, man):
        d.mkdir()
    ids = ([f"mslesseg_P{p}" for p in range(54, 76)] + [f"openms_patient{n:02d}" for n in ec.OPENMS_CLEAN]
           + [f"ms3seg_{i:03d}" for i in range(1, 101)] + [f"muslim_{i:02d}" for i in range(1, 52)]
           + [f"pedims_P{1 + i % 9}_T{1 + i // 9}" for i in range(28)])
    rng = np.random.default_rng(1)
    shape = (16, 16, 12)
    for c in ids:
        thick = ec.site_of(c) in ec.THICK_SITES
        z = (0.9, 0.9, 6.0) if thick else (1.0, 1.0, 1.0)
        gt = blob(shape, (5, 5, 5), 2) | blob(shape, (11, 11, 6), 2)
        _write(ref / f"{c}_gt.nii.gz", gt.astype(np.float32), z)
        _write(new / f"{c}_gt.nii.gz", gt.astype(np.float32), z)
        miss = rng.random() < 0.6
        r = np.zeros(shape, np.float32)
        r[blob(shape, (5, 5, 5), 2)] = 0.9
        if not miss:
            r[blob(shape, (11, 11, 6), 2)] = 0.8
        if rng.random() < 0.5:
            r[blob(shape, (3, 13, 2), 1)] = 0.7                     # a false lesion in half the scans
        for k in range(5):
            _write(ref / f"{c}_f{k}_prob.nii.gz", r, z)
        a = r.copy()
        if thick:                                                    # A finds the missed lesions, same FPs
            a[gt] = 0.9
        _write(new / f"{c}_ftA_f0_prob.nii.gz", a, z)
    json.dump({"inputs_sha256": {c: "h" + c for c in ids}}, open(man / "ref.json", "w"))
    json.dump({"inputs_sha256": {c: "h" + c for c in ids}}, open(tmp_path / "new.json", "w"))
    out = tmp_path / "res.json"
    assert an.main(["--ref-dir", str(ref), "--new-dir", str(new), "--ref-manifests", str(man),
                    "--new-manifest", str(tmp_path / "new.json"), "--tag", "A=ftA", "--out", str(out),
                    "--workers", "2", "--bootstrap", "2000"]) == 0
    res = json.load(open(out))
    assert res["H1"]["verdict"] == "success" and res["H1"]["n"] == 179 and res["H1"]["patients"] == 160
    assert res["H2"]["verdict"] == "non-inferior"
    json.dump({"inputs_sha256": {c: "other" for c in ids}}, open(tmp_path / "new.json", "w"))
    with pytest.raises(SystemExit):                                  # a different input must abort
        an.main(["--ref-dir", str(ref), "--new-dir", str(new), "--ref-manifests", str(man),
                 "--new-manifest", str(tmp_path / "new.json"), "--tag", "A=ftA", "--out", str(out)])
