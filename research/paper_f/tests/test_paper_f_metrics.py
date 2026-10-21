"""Paper F pre-registered metrics and evaluation (local, CPU, synthetic volumes; no cloud calls).

    python -m pytest research/paper_f/tests -q
"""
import json
import os
import sys

import nibabel as nib
import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import evaluate as ev  # noqa: E402
import metrics as M  # noqa: E402

ISO = (1.0, 1.0, 1.0)


def blob(shape, centre, r):
    i, j, k = np.ogrid[:shape[0], :shape[1], :shape[2]]
    return (i - centre[0]) ** 2 + (j - centre[1]) ** 2 + (k - centre[2]) ** 2 <= r * r


# ------------------------------------------------------------------ definitions
def test_size_filter_uses_physical_volume():
    m = np.zeros((20, 20, 20), bool)
    m[2:4, 2:4, 2:4] = True                       # 8 voxels
    assert M.components(m, ISO)[1] == 0           # 8 mm^3 < 14.137 mm^3 at 1 mm
    assert M.components(m, (1, 1, 2))[1] == 1     # 16 mm^3 at 1 x 1 x 2 mm
    assert M.components(m, ISO, min_mm3=0)[1] == 1
    assert abs(M.MIN_LESION_MM3 - 14.137) < 1e-3


def test_lesion_f1_counts_false_and_missed_lesions():
    shape = (40, 40, 40)
    ref = blob(shape, (10, 10, 10), 3) | blob(shape, (30, 30, 30), 3)
    pred = blob(shape, (10, 10, 11), 3) | blob(shape, (30, 10, 10), 3) | blob(shape, (10, 30, 30), 3)
    r = M.lesion_metrics(pred, ref, ISO)
    assert (r["n_ref"], r["n_pred"], r["tp_ref"], r["tp_pred"]) == (2, 3, 1, 1)
    assert r["false_lesions"] == 2 and r["missed_lesions"] == 1
    assert r["precision"] == pytest.approx(1 / 3) and r["recall"] == pytest.approx(0.5)
    assert r["f1"] == pytest.approx(2 * (1 / 3) * 0.5 / (1 / 3 + 0.5))
    assert 0 < r["dice"] < 1


def test_empty_cases():
    shape = (20, 20, 20)
    z = np.zeros(shape, bool)
    les = blob(shape, (10, 10, 10), 3)
    assert M.lesion_metrics(z, les, ISO)["f1"] == 0.0             # missed everything
    e = M.lesion_metrics(les, z, ISO)                                # healthy reference
    assert e["f1"] is None and e["dice"] is None and e["false_lesions"] == 1
    assert M.lesion_metrics(z, z, ISO)["f1"] is None


def test_inplane_connectivity_splits_across_slices():
    m = np.zeros((10, 10, 4), bool)
    m[3:6, 3:6, 1] = True
    m[3:6, 3:6, 2] = True                                            # two touching slices
    z = (1.0, 1.0, 6.0)
    assert M.components(m, z, 0, 26)[1] == 1 and M.components(m, z, 0, 8)[1] == 2


def test_size_bins_and_bands():
    assert M.size_bin(10) is None and M.size_bin(20) == "14-50" and M.size_bin(5000) == ">=1000"
    assert M.band((1, 1, 1)) == "iso" and M.band((0.9, 0.9, 6.8)) == "thick" and M.band((1, 1, 2)) == "intermediate"
    assert M.sub_band((0.75, 0.75, 3.9)) == "thick_3-5.5" and M.sub_band((0.4, 0.4, 8.3)) == "thick_>5.5"
    assert M.patient_of("mslesseg_P10_T2") == "mslesseg_P10" and M.patient_of("pedims_P3_T4") == "pedims_P3"
    assert M.patient_of("ms3seg_007") == "ms3seg_007" and M.cohort_of("openms_patient16") == "openms"


def test_confirmed_keeps_only_shared_lesions():
    shape = (30, 30, 30)
    a = blob(shape, (8, 8, 8), 3) | blob(shape, (22, 22, 22), 3)
    b = blob(shape, (8, 8, 9), 2)
    c = M.confirmed(a, b, ISO)
    assert c[8, 8, 8] and not c[22, 22, 22]


# ------------------------------------------------------------------ inference
def test_bootstrap_is_deterministic_and_clusters_patients():
    v = [0.1, 0.1, 0.1, 0.3, -0.1]
    s = ["a", "a", "a", "b", "b"]
    c = ["p1", "p1", "p1", "p2", "p3"]
    r1 = M.stratified_cluster_bootstrap(v, s, c, n_boot=500)
    r2 = M.stratified_cluster_bootstrap(v, s, c, n_boot=500)
    assert r1 == r2 and r1["n_clusters"] == 3 and r1["n_scans"] == 5
    assert r1["estimate"] == pytest.approx((0.1 + 0.1) / 2)          # cohort-weighted: a=0.1, b=0.1
    assert M.stratified_cluster_bootstrap(v, s, c, n_boot=200, weighting="scan")["estimate"] == pytest.approx(0.1)
    nan = M.stratified_cluster_bootstrap([float("nan")], ["a"], ["p"], n_boot=10)
    assert nan["estimate"] is None


def test_equivalence_flag_and_holm():
    r = M.stratified_cluster_bootstrap([0.001, -0.002, 0.0, 0.003] * 10, ["a"] * 40, [str(i) for i in range(40)],
                                       n_boot=300, margin=0.05)
    assert r["equivalent_within_margin"] is True
    adj = M.holm([0.01, 0.04, None, 0.03])
    assert adj[2] is None and adj[0] == pytest.approx(0.03) and adj[1] == pytest.approx(0.06)


def test_auroc():
    assert M.auroc([0.9, 0.8, 0.1], [True, True, False]) == 1.0
    assert M.auroc([0.5, 0.5], [True, False]) == 0.5
    assert M.auroc([1, 2], [True, True]) is None


# ------------------------------------------------------------------ evaluation on a synthetic cohort
def nii(path, data, affine=None, zooms=None, dtype=np.float32):
    aff = np.eye(4) if affine is None else affine
    if zooms is not None:
        aff = np.diag(list(zooms) + [1.0])
    img = nib.Nifti1Image(np.asarray(data, dtype), aff)
    img.set_data_dtype(dtype)
    nib.save(img, path)
    return path


def make_cohort(root):
    """Two thick-slice cases (MS3SEG, Muslim), one iso (MSLesSeg), one contaminated Ljubljana case."""
    fl, tb, ls = (root / d for d in ("flames", "tool", "lstai"))
    for d in (fl, tb, ls):
        d.mkdir()
    cases = {"ms3seg_001": (0.9, 0.9, 6.8), "muslim_02": (0.5, 0.5, 5.5), "mslesseg_P1_T1": ISO,
             "openms_patient01": ISO}
    shape = (40, 40, 12)
    for case, z in cases.items():
        gt = blob(shape, (10, 10, 5), 4) | blob(shape, (30, 30, 6), 4)
        nii(str(fl / f"{case}_gt.nii.gz"), gt, zooms=z, dtype=np.uint8)
        for k in range(5):
            nii(str(fl / f"{case}_f{k}_prob.nii.gz"), blob(shape, (10, 10, 5), 4) * 0.9, zooms=z)
        nii(str(tb / f"{case}_mindglide_seg.nii.gz"), gt, zooms=z, dtype=np.uint8)        # perfect
        nii(str(tb / f"{case}_wmhsynthseg_seg.nii.gz"), gt | blob(shape, (30, 8, 6), 3), zooms=z, dtype=np.uint8)
        if case.startswith(("mslesseg", "openms")):
            nii(str(ls / f"{case}_lstai_prob.nii.gz"), gt * 0.8, zooms=z)
    return {"flames": str(fl), "tool": str(tb), "lstai": str(ls)}, list(cases)


def test_evaluate_end_to_end(tmp_path):
    dirs, cases = make_cohort(tmp_path)
    mdir = tmp_path / "man"; mdir.mkdir()
    json.dump({"cases": [], "errors": [{"case": "ms3seg_001", "tool": "samseg", "error": "boom"}]},
              open(mdir / "run.json", "w"))
    rows = ev.per_scan_rows(cases, dirs, ev.manifest_outcomes(str(mdir)))
    prim = {(r["case"], r["tool"]): r for r in rows if r["variant"] == "primary"}
    assert prim[("ms3seg_001", "mindglide")]["f1"] == 1.0
    assert prim[("ms3seg_001", "flames")]["f1"] == pytest.approx(2 * 1 * 0.5 / 1.5)
    assert prim[("ms3seg_001", "wmhsynthseg")]["false_lesions"] == 1
    assert prim[("ms3seg_001", "samseg")]["status"] == "failed-as-empty" and prim[("ms3seg_001", "samseg")]["f1"] == 0.0
    assert prim[("muslim_02", "samseg")]["status"] == "missing"
    assert prim[("openms_patient01", "flames")]["contaminated"]
    assert prim[("ms3seg_001", "lstai")]["status"] == "missing"
    assert any(r["variant"] == "S3_inplane_8conn" and r["band"] == "thick" for r in rows)
    assert not any(r["variant"] == "S3_inplane_8conn" and r["band"] == "iso" for r in rows)
    res = ev.prestated(rows, n_boot=200)
    p = {(r["tool"], r["outcome"]): r for r in res["primary"]}
    assert len(res["primary"]) == 6 and all("p_holm" in r for r in res["primary"])
    assert p[("mindglide", "f1")]["estimate"] == pytest.approx(1 - 2 / 3)
    assert p[("mindglide", "f1")]["n_scans"] == 2
    iso = [r for r in res["secondary"] if r.get("band") == "iso" and r["tool"] == "lstai" and r["outcome"] == "f1"][0]
    assert iso["n_scans"] == 1                                       # contaminated Ljubljana case dropped (FLAMeS)
    sens = {(r["analysis"], r["tool"], r["outcome"]): r for r in res["sensitivity"]}
    assert p[("samseg", "f1")]["n_scans"] == 1                                       # failure scored as empty
    assert sens[("S4_complete_case", "samseg", "f1")]["n_scans"] == 0                # ... or dropped
    assert sens[("S6_thick_without_muslim", "mindglide", "f1")]["n_scans"] == 1
    assert sens[("S5_iso_with_flames_training_cases", "lstai", "f1")]["n_scans"] == 2
    assert ("S3_inplane_8conn", "wmhsynthseg", "false_lesions") in sens


def test_check_flags_wrong_grid_and_non_binary(tmp_path):
    dirs, _ = make_cohort(tmp_path)
    r = ev.check_case("ms3seg_001", dirs["tool"], dirs["flames"], tools=("mindglide",))
    assert r["pass"] and r["mindglide_dice"] == 1.0
    shape = (40, 40, 12)
    nii(os.path.join(dirs["tool"], "ms3seg_001_mindglide_seg.nii.gz"), np.ones(shape), zooms=(1, 1, 1), dtype=np.uint8)
    assert not ev.check_case("ms3seg_001", dirs["tool"], dirs["flames"], tools=("mindglide",))["pass"]
    nii(os.path.join(dirs["tool"], "ms3seg_001_mindglide_seg.nii.gz"), np.full(shape, 2), zooms=(0.9, 0.9, 6.8),
        dtype=np.uint8)
    r = ev.check_case("ms3seg_001", dirs["tool"], dirs["flames"], tools=("mindglide",))
    assert any("not binary" in f for f in r["fails"])


def test_frozen_inputs_file_is_consistent():
    p = os.path.join(os.path.dirname(HERE), "flames_inputs.json")
    d = json.load(open(p))
    assert len(d) == 324
    count = {}
    for c, v in d.items():
        count[v["cohort"]] = count.get(v["cohort"], 0) + 1
        assert len(v["flair_sha256"]) == 64 and v["band"] == M.band(v["zooms"]) and v["cohort"] == M.cohort_of(c)
    assert count == {"ms3seg": 100, "mslesseg": 115, "muslim": 51, "openms": 30, "pedims": 28}
    assert sum(v["band"] == "thick" for v in d.values()) == 179 and sum(v["band"] == "iso" for v in d.values()) == 145
