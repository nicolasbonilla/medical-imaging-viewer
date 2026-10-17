"""Unit tests for the cloud-job helpers (no cloud calls; synthetic NIfTI files + one public index).

    python -m pytest research/cloud/tests -q
"""
import json
import os
import sys

import nibabel as nib
import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import check_outputs as co  # noqa: E402
import job_common as jc  # noqa: E402
import lstai_driver as ld  # noqa: E402
import sibbms_controls_prep as sp  # noqa: E402
import stage_for_detector as sd  # noqa: E402

FIX = os.path.join(HERE, "fixtures", "sibbms_norm_index.json")


def nii(path, data, affine=None, dtype=np.float32):
    img = nib.Nifti1Image(np.asarray(data, dtype), np.eye(4) if affine is None else affine)
    img.set_data_dtype(dtype)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    nib.save(img, path)
    return path


def brain(shape=(12, 10, 8), seed=0):
    rng = np.random.default_rng(seed)
    return (rng.random(shape) * 100 + 1).astype(np.float32)


# ------------------------------------------------------------------ selection / SibBMS index
def test_select_ids_offset_limit_explicit():
    ids = ["c", "a", "b", "d"]
    assert jc.select_ids(ids) == ["a", "b", "c", "d"]
    assert jc.select_ids(ids, 1, 2) == ["b", "c"]
    assert jc.select_ids(ids, 3, 0) == ["d"]
    assert jc.select_ids(ids, 0, 0, ["d", "a"]) == ["a", "d"]
    with pytest.raises(ValueError):
        jc.select_ids(ids, explicit=["zz"])
    assert jc.split_ids("a b,c  ") == ["a", "b", "c"] and jc.split_ids("") == []


def test_sibbms_release_has_100_controls_with_flair_and_t1():
    names = [e["name"] for e in json.load(open(FIX))["entries"]]
    ctl = sp.list_controls(names)
    assert len(ctl) == 100
    assert list(ctl)[0] == "sub-001" and list(ctl)[-1] == "sub-100"
    assert ctl["sub-023"]["t1"].endswith("sub-023_ses-001_T1w.nii.gz")      # not the ce-GAD_T1w
    assert all(v["flair"].endswith("_FLAIR.nii.gz") for v in ctl.values())
    assert jc.select_ids(list(ctl), 50, 50)[0] == "sub-051"


def test_list_controls_needs_both_and_rejects_mismatch():
    names = ["Output/Norm/sub-001/ses-001/anat/sub-001_ses-001_FLAIR.nii.gz",
             "Output/Norm/sub-002/ses-001/anat/sub-002_ses-001_FLAIR.nii.gz",
             "Output/Norm/sub-002/ses-001/anat/sub-002_ses-001_T1w.nii.gz",
             "Output/Norm/sub-003/ses-001/anat/sub-004_ses-001_T1w.nii.gz",       # id mismatch -> ignored
             "Output/MS/sub-005/ses-001/anat/sub-005_ses-001_T1w.nii.gz"]         # patients -> ignored
    assert list(sp.list_controls(names)) == ["sub-002"]


# ------------------------------------------------------------------ grids and resampling
def test_identity_when_same_grid(tmp_path):
    aff = np.diag([-1.0, 1, 1, 1]); aff[:3, 3] = [90, -126, -72]
    d = brain()
    img, ref = nib.load(nii(str(tmp_path / "a.nii.gz"), d, aff)), nib.load(nii(str(tmp_path / "r.nii.gz"), d * 0, aff))
    out, tr = jc.to_grid(img, ref)
    assert tr["kind"] == "identity" and np.array_equal(out, d)


def test_trilinear_translation_is_exact_for_linear_field():
    i, j, k = np.meshgrid(np.arange(12), np.arange(10), np.arange(8), indexing="ij")
    f = (i + 2 * j + 3 * k).astype(np.float32)
    src_aff = np.eye(4); src_aff[0, 3] = 2.0                      # source voxel 0 sits at x = 2 mm
    out, m = jc.resample_to_grid(f, src_aff, f.shape, np.eye(4))
    assert np.allclose(np.array(m)[:3, 3], [-2, 0, 0])
    assert np.allclose(out[2:], (i - 2 + 2 * j + 3 * k)[2:])     # inside the source field of view
    assert np.all(out[:1] == 0)                                   # outside -> 0


def test_las_source_onto_ras_reference_is_a_flip():
    d = brain()
    nx = d.shape[0]
    ras = np.eye(4); ras[:3, 3] = [-5, -4, -3]
    las = np.diag([-1.0, 1, 1, 1]); las[:3, 3] = [-5 + nx - 1, -4, -3]   # same world box, x reversed
    out, _ = jc.resample_to_grid(d, las, d.shape, ras)
    assert np.allclose(out, d[::-1], atol=1e-4)


def test_trilinear_upsampling_reproduces_linear_world_function():
    src_aff = np.diag([2.0, 2, 2, 1])                              # 2 mm source
    i, j, k = np.meshgrid(np.arange(8), np.arange(8), np.arange(8), indexing="ij")
    f = (2 * i * 0.5 + 3 * j * 2 - k * 2).astype(np.float32)       # linear in world x, y, z
    out, _ = jc.resample_to_grid(f, src_aff, (14, 14, 14), np.eye(4))   # 1 mm reference
    x, y, z = np.meshgrid(np.arange(14), np.arange(14), np.arange(14), indexing="ij")
    want = 0.5 * x + 3 * y - z
    assert np.allclose(out, want, atol=1e-4)


# ------------------------------------------------------------------ storage
@pytest.mark.parametrize("preset_slope", [None, 2.0])
def test_uint8_storage_error_bound_and_exact_zero(tmp_path, preset_slope):
    rng = np.random.default_rng(1)
    p = rng.random((20, 18, 16)).astype(np.float32)
    p[:5] = 0.0
    ref = nib.Nifti1Image(np.zeros(p.shape, np.float32), np.eye(4))
    if preset_slope:
        ref.header.set_slope_inter(preset_slope, 0.0)
    out = str(tmp_path / "p.nii.gz")
    err = jc.save_prob(p, ref, out, "uint8")
    back = np.asarray(nib.load(out).get_fdata())
    assert nib.load(out).get_data_dtype() == np.uint8
    assert err <= jc.UINT8_MAX_ERR + 1e-6 and np.abs(back - p).max() <= jc.UINT8_MAX_ERR + 1e-6
    assert np.all(back[:5] == 0) and back.min() >= 0 and back.max() <= 1 + 1e-6
    assert jc.save_prob(p, ref, str(tmp_path / "f.nii.gz"), "float32") == 0.0


def test_save_prob_refuses_wrong_shape(tmp_path):
    ref = nib.Nifti1Image(np.zeros((4, 4, 4), np.float32), np.eye(4))
    with pytest.raises(ValueError):
        jc.save_prob(np.zeros((4, 4, 5)), ref, str(tmp_path / "x.nii.gz"))


def test_peak_memory_and_versions_never_crash():
    with jc.PeakMemory(period=0.05) as pm:
        _ = np.zeros(10)
    rec = pm.record()
    assert set(rec) == {"peak_mem_used_gb", "peak_swap_used_gb"}          # None off Linux, numbers on Linux
    v = jc.pkg_versions(["numpy", "surely-not-installed-pkg"])
    assert v["numpy"] and v["surely-not-installed-pkg"] is None


def test_blank_reason():
    assert "blank" in jc.blank_reason(np.zeros((10, 10, 10)))
    z = np.zeros((10, 10, 10)); z[0, 0, :5] = 1
    assert "blank" in jc.blank_reason(z)
    assert jc.blank_reason(brain()) is None
    n = brain(); n[0, 0, 0] = np.nan
    assert jc.blank_reason(n) == "non-finite values"


# ------------------------------------------------------------------ LST-AI case list
def make_tree(root):
    ms = os.path.join(root, "mslesseg", "MSLesSeg Dataset")
    for p, t in (("P1", "T1"), ("P1", "T2"), ("P49", "T2")):
        d = os.path.join(ms, "train", p, t)
        for mod in ("FLAIR", "T1", "T2", "MASK"):
            data = np.zeros((12, 10, 8)) if (p == "P49" and mod == "T1") else brain()
            nii(os.path.join(d, f"{p}_{t}_{mod}.nii.gz"), data)
    for mod in ("FLAIR", "T1", "MASK"):
        nii(os.path.join(ms, "test", "P54", f"P54_{mod}.nii.gz"), brain())
    lj = os.path.join(root, "open_ms_data", "cross_sectional", "MNI", "patient01")
    for f in (ld.LJ_FLAIR, ld.LJ_T1, "T1POST_N4_noneck_reduced_winsor_regtoFLAIR_brain_N4_regtoMNI.nii.gz"):
        nii(os.path.join(lj, f), brain())
    ctl = os.path.join(root, "controls")
    for c in ("sub-001", "sub-002"):
        nii(os.path.join(ctl, f"{c}_FLAIR.nii.gz"), brain())
        nii(os.path.join(ctl, f"{c}_T1.nii.gz"), brain())
    return {"mslesseg": os.path.join(root, "mslesseg"), "controls": ctl,
            "openms": os.path.join(root, "open_ms_data", "cross_sectional", "MNI")}


def test_enumerate_and_build_cases(tmp_path):
    roots = make_tree(str(tmp_path))
    c = ld.enumerate_candidates(roots, ["mslesseg", "openms", "controls"])
    assert list(c) == ["mslesseg_P1_T1", "mslesseg_P1_T2", "mslesseg_P49_T2", "mslesseg_P54",
                       "openms_patient01", "sub-001", "sub-002"]
    assert c["mslesseg_P1_T1"]["t1"].endswith("P1_T1_T1.nii.gz")
    assert c["mslesseg_P1_T1"]["flair"].endswith("P1_T1_FLAIR.nii.gz")
    assert os.path.basename(c["openms_patient01"]["t1"]) == ld.LJ_T1           # never T1POST
    sel, skipped = ld.build_cases(roots, ["mslesseg", "openms", "controls"])
    assert "mslesseg_P49_T2" not in sel and skipped[0]["case"] == "mslesseg_P49_T2"
    assert "blank" in skipped[0]["reason"]
    sel, skipped = ld.build_cases(roots, ["mslesseg", "openms", "controls"], offset=2, limit=2)
    assert list(sel) == ["mslesseg_P54"] and [s["case"] for s in skipped] == ["mslesseg_P49_T2"]
    sel, _ = ld.build_cases(roots, ["mslesseg", "controls"], explicit=["sub-002", "mslesseg_P1_T2"])
    assert list(sel) == ["mslesseg_P1_T2", "sub-002"]


def test_find_outputs_exact_and_fallback(tmp_path):
    d = tmp_path / "tmp"; d.mkdir()
    for f in (ld.ENS, *(ld.MODEL.format(j=j) for j in (1, 2, 3)), "sub-X_ses-Y_space-mni_seg-lst_prob.nii.gz"):
        (d / f).write_bytes(b"x")
    f = ld.find_outputs(str(d))
    assert os.path.basename(f["ens"]) == ld.ENS and os.path.basename(f[3]).endswith("prob_3.nii.gz")
    e = tmp_path / "tmp2"; e.mkdir()
    for f in ("a_space-flair_seg-lst_prob.nii.gz", "a_space-flair_seg-lst_prob_1.nii.gz",
              "a_space-mni_seg-lst_prob_2.nii.gz"):
        (e / f).write_bytes(b"x")
    g = ld.find_outputs(str(e))
    assert os.path.basename(g["ens"]) == "a_space-flair_seg-lst_prob.nii.gz" and 1 in g and 2 not in g


def test_lstai_command_flags():
    cmd = ld.lstai_command("lstai:v1.2.0", 4, True)
    for flag in ("--probability_map", "--stripped", "--segment_only", "--temp"):
        assert flag in cmd
    assert cmd[cmd.index("--device") + 1] == "cpu" and cmd[cmd.index("--threads") + 1] == "4"
    assert "--segment_only" not in ld.lstai_command("x", 4, False)


# ------------------------------------------------------------------ staging for the detector
def test_stage_plan_apply_and_no_overwrite(tmp_path):
    dl, out, aug = tmp_path / "dl", tmp_path / "cohorts", tmp_path / "aug"
    fe = dl / "flames-ensemble" / "cohort"
    for case in ("mslesseg_P10_T1", "sub-001", "sub-021"):
        for k in range(5):
            nii(str(fe / f"{case}_f{k}_prob.nii.gz"), np.full((4, 4, 4), 0.1 * k))
        nii(str(fe / f"{case}_gt.nii.gz"), np.zeros((4, 4, 4)), dtype=np.uint8)
    nii(str(dl / "lstai" / "cohort" / "sub-001_lstai_prob.nii.gz"), np.zeros((4, 4, 4)))
    nii(str(dl / "lstai" / "cohort" / "sub-001_lstai_prob_m2.nii.gz"), np.zeros((4, 4, 4)))
    for k in ("FLAIR", "T1", "brainmask"):
        nii(str(dl / "controls" / "sibbms" / f"sub-021_{k}.nii.gz"), np.ones((4, 4, 4)))
    nii(str(aug / "sub-001_prob.nii.gz"), np.zeros((4, 4, 4)))                # an August control
    pairs = sd.plan(str(dl), str(out), str(aug))
    dsts = {os.path.relpath(d, tmp_path).replace("\\", "/") for _, d in pairs}
    assert "cohorts/all-flames-folds/mslesseg_P10_T1_prob_f4.nii.gz" in dsts
    assert "cohorts/all-flames-folds/sub-021_prob_f0.nii.gz" in dsts
    assert "cohorts/all-lstai/sub-001_lstai_prob_m2.nii.gz" in dsts
    assert "cohorts/sibbms-controls-flair/sub-021_T1.nii.gz" in dsts
    assert "aug/sub-021_prob.nii.gz" in dsts and "aug/sub-021_gt.nii.gz" in dsts
    assert "aug/sub-001_prob.nii.gz" not in dsts                              # August file untouched
    copied, skipped = sd.apply(pairs)
    assert len(copied) == len(pairs) and skipped == 0
    assert sd.apply(pairs) == ([], len(pairs))                                # idempotent
    nii(str(out / "all-lstai" / "sub-001_lstai_prob.nii.gz"), np.ones((4, 4, 4)))
    with pytest.raises(FileExistsError):
        sd.apply(pairs)


# ------------------------------------------------------------------ pilot checks
def control_files(root, case, aff, fold_value=0.2, leak=False):
    m = np.zeros((12, 10, 8), np.uint8); m[2:10, 2:8, 1:7] = 1
    fl = brain() * m
    if leak:
        fl[0, 0, 0] = 5.0
    nii(os.path.join(root, "controls", f"{case}_FLAIR.nii.gz"), fl, aff)
    nii(os.path.join(root, "controls", f"{case}_T1.nii.gz"), brain(seed=3) * m, aff)
    nii(os.path.join(root, "controls", f"{case}_brainmask.nii.gz"), m, aff, np.uint8)
    for k in range(5):
        p = np.zeros(m.shape, np.float32); p[4:6, 4:6, 3:5] = fold_value + 0.1 * k
        nii(os.path.join(root, "folds", f"{case}_f{k}_prob.nii.gz"), p, aff)


def test_check_control_pass_and_fail(tmp_path):
    aff = np.eye(4)
    control_files(str(tmp_path), "sub-001", aff)
    aug = tmp_path / "aug"
    p = np.zeros((12, 10, 8), np.float32); p[4:6, 4:6, 3:5] = 0.2
    nii(str(aug / "sub-001_prob.nii.gz"), p, aff)
    r = co.check_control("sub-001", str(tmp_path / "controls"), str(tmp_path / "folds"), str(aug))
    assert r["fails"] == [] and r["august_dice_0.5"] == 1.0 and r["august_max_abs_diff"] < 1e-6
    assert any("brain volume" in w for w in r["warns"])                       # toy brain is tiny
    control_files(str(tmp_path), "sub-002", aff, leak=True)
    r = co.check_control("sub-002", str(tmp_path / "controls"), str(tmp_path / "folds"))
    assert not r["pass"] and any("outside the brain mask" in f for f in r["fails"])


def test_check_lstai_pass_and_fail(tmp_path):
    aff = np.eye(4)
    ref = tmp_path / "ref"; lst = tmp_path / "lst"
    gt = np.zeros((12, 10, 8), np.uint8); gt[3:7, 3:7, 2:5] = 1
    nii(str(ref / "c1_prob.nii.gz"), gt * 0.9, aff)
    nii(str(ref / "c1_gt.nii.gz"), gt, aff, np.uint8)
    ms = [gt * v for v in (0.9, 0.6, 0.75)]
    for j, m in enumerate(ms, 1):
        nii(str(lst / f"c1_lstai_prob_m{j}.nii.gz"), m, aff)
    nii(str(lst / "c1_lstai_prob.nii.gz"), sum(ms) / 3, aff)
    r = co.check_lstai("c1", str(lst), [str(ref)])
    assert r["pass"] and r["dice_vs_gt_0.5"] == 1.0
    shifted = np.eye(4); shifted[0, 3] = 1.0                                   # wrong grid
    nii(str(lst / "c1_lstai_prob.nii.gz"), sum(ms) / 3, shifted)
    assert not co.check_lstai("c1", str(lst), [str(ref)])["pass"]


# ------------------------------------------------------------------ dry run on the local public data
def _local_data_root():
    p = HERE
    for _ in range(8):
        p = os.path.dirname(p)
        if os.path.isdir(os.path.join(p, "data", "external", "mslesseg")):
            return os.path.join(p, "data")
    return os.environ.get("CALM_DATA_ROOT")


@pytest.mark.skipif(not (_local_data_root() and os.path.isdir(os.path.join(_local_data_root() or "", "external"))),
                    reason="local public data not present")
def test_dry_run_case_list_on_local_public_data():
    root = _local_data_root()
    roots = {"mslesseg": os.path.join(root, "external", "mslesseg"),
             "openms": os.path.join(root, "external", "open_ms_data", "cross_sectional", "MNI")}
    sel, skipped = ld.build_cases(roots, ["mslesseg", "openms"])
    assert [s["case"] for s in skipped] == ["mslesseg_P49_T2"]
    assert sum(c.startswith("mslesseg_") for c in sel) == 114 and sum(c.startswith("openms_") for c in sel) == 30
    flames = {f[:-len("_prob.nii.gz")] for coh in ("mslesseg-flames", "openms-flames")
              for f in os.listdir(os.path.join(root, "cohorts", coh)) if f.endswith("_prob.nii.gz")}
    assert set(sel) | {"mslesseg_P49_T2"} == flames                         # same ids as the FLAMeS cohort
