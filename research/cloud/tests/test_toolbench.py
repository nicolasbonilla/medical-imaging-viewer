"""Paper F tool-benchmark job: case list, input identity, commands, outputs onto the FLAMeS grid,
footprint resampling and script safety (local, CPU, synthetic NIfTI; no cloud calls, no Docker).

    python -m pytest research/cloud/tests/test_toolbench.py -q
"""
import json
import os
import re
import sys

import nibabel as nib
import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
CLOUD = os.path.dirname(HERE)
sys.path.insert(0, CLOUD)
import job_common as jc  # noqa: E402
import toolbench_driver as tb  # noqa: E402


def nii(path, data, affine=None, dtype=np.float32):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img = nib.Nifti1Image(np.asarray(data, dtype), np.eye(4) if affine is None else affine)
    img.set_data_dtype(dtype)
    nib.save(img, path)
    return path


def brain(shape=(12, 10, 8), seed=0):
    return (np.random.default_rng(seed).random(shape) * 100 + 1).astype(np.float32)


# ------------------------------------------------------------------ case list and input identity
def make_tree(root):
    ms = os.path.join(root, "mslesseg", "MSLesSeg Dataset")
    for p, t in (("P1", "T1"), ("P1", "T2")):
        d = os.path.join(ms, "train", p, t)
        for mod in ("FLAIR", "T1", "MASK"):
            nii(os.path.join(d, f"{p}_{t}_{mod}.nii.gz"), brain())
    for mod in ("FLAIR", "MASK"):
        nii(os.path.join(ms, "test", "P54", f"P54_{mod}.nii.gz"), brain())
    lj = os.path.join(root, "oms", "patient01")
    nii(os.path.join(lj, "FLAIR_N4_noneck_reduced_winsor_regtoFLAIR_brain_N4_regtoMNI.nii.gz"), brain())
    nii(os.path.join(lj, "GOLD_STANDARD_regtoMNI.nii.gz"), brain())
    nii(os.path.join(root, "oms", "patient02", "FLAIR_x_regtoMNI.nii.gz"), brain())      # no GT -> not a case
    raw, br = os.path.join(root, "extra_raw"), os.path.join(root, "extra_brain")
    cases = {}
    for cid, coh, strip in (("ms3seg_001", "ms3seg", True), ("muslim_01", "muslim", True), ("pedims_P1_T1", "pedims", False)):
        fl = nii(os.path.join(raw, coh, f"{cid}_flair.nii.gz"), brain(seed=1))
        nii(os.path.join(raw, coh, f"{cid}_lesion.nii.gz"), np.zeros((12, 10, 8)), dtype=np.uint8)
        cases[cid] = {"cohort": coh, "flair": os.path.relpath(fl, raw), "gt": f"{coh}/{cid}_lesion.nii.gz", "strip": strip}
        if strip:
            nii(os.path.join(br, f"{cid}_flair_brain.nii.gz"), brain(seed=2))
    json.dump(cases, open(os.path.join(raw, "cases_extra.json"), "w"))
    return {"mslesseg": os.path.join(root, "mslesseg"), "openms": os.path.join(root, "oms"),
            "extra_raw": raw, "extra_brain": br}


def test_enumerate_cases_matches_flames_ids_and_uses_the_flames_brains(tmp_path):
    roots = make_tree(str(tmp_path))
    c = tb.enumerate_cases(roots, list(tb.COHORTS))
    assert list(c) == ["ms3seg_001", "mslesseg_P1_T1", "mslesseg_P1_T2", "mslesseg_P54", "muslim_01",
                       "openms_patient01", "pedims_P1_T1"]
    assert c["ms3seg_001"]["flair"].endswith(os.path.join("extra_brain", "ms3seg_001_flair_brain.nii.gz"))
    assert c["pedims_P1_T1"]["flair"].endswith("pedims_P1_T1_flair.nii.gz")              # ships skull-stripped
    assert c["mslesseg_P1_T2"]["flair"].endswith("P1_T2_FLAIR.nii.gz")
    only = tb.enumerate_cases(roots, ["pedims", "openms"])
    assert list(only) == ["openms_patient01", "pedims_P1_T1"]


def test_verify_inputs_refuses_other_bytes(tmp_path):
    roots = make_tree(str(tmp_path))
    c = tb.enumerate_cases(roots, ["ms3seg", "pedims"])
    exp = {"ms3seg_001": {"flair_sha256": jc.sha256(c["ms3seg_001"]["flair"])},
           "pedims_P1_T1": {"flair_sha256": "0" * 64}}
    ok, bad = tb.verify_inputs(c, exp)
    assert list(ok) == ["ms3seg_001"] and ok["ms3seg_001"]["flair_sha256"] == exp["ms3seg_001"]["flair_sha256"]
    assert bad[0]["case"] == "pedims_P1_T1" and "differs" in bad[0]["reason"]
    ok, bad = tb.verify_inputs(c, {})
    assert not ok and all("no FLAMeS checksum" in b["reason"] for b in bad)


def test_thick_slice_cases_run_first():
    exp = {"ms3seg_001": {"band": "thick"}, "mslesseg_P10_T1": {"band": "iso"}, "pedims_P1_T1": {"band": "thick"}}
    sel = {c: {} for c in sorted(exp)}
    assert [c for c, _ in tb.thick_first(sel, exp)] == ["ms3seg_001", "pedims_P1_T1", "mslesseg_P10_T1"]


def test_frozen_inputs_cover_every_flames_case():
    d = json.load(open(os.path.join(os.path.dirname(CLOUD), "paper_f", "flames_inputs.json")))
    assert len(d) == 324 and all(re.fullmatch(r"[0-9a-f]{64}", v["flair_sha256"]) for v in d.values())


# ------------------------------------------------------------------ commands
def test_docker_prefix_isolated_and_licence_read_only():
    cmd = tb.docker_prefix("/w/run/x", "freesurfer:bench", 4, "/w/fs_license/license.txt")
    assert "--network=none" in cmd and "OMP_NUM_THREADS=4" in cmd
    assert "/w/fs_license/license.txt:/fs_license/license.txt:ro" in cmd and "FS_LICENSE=/fs_license/license.txt" in cmd
    assert cmd[-1] == "freesurfer:bench"
    assert not any("license" in x for x in tb.docker_prefix("/w", "mindglide:bench", 4))


@pytest.mark.parametrize("tool", sorted(tb.TOOLS))
def test_tool_commands_are_cpu_and_read_the_staged_flair(tool):
    cmd = " ".join(tb.tool_command(tool, 4))
    assert "/work/in/flair.nii.gz" in cmd and "/work/out" in cmd
    assert "cpu" in cmd or tool == "samseg"                                            # SAMSEG is CPU-only
    if tool == "samseg":
        assert "--lesion" in cmd and "--lesion-mask-pattern 1" in cmd and "--threads 4" in cmd
    if tool == "wmhsynthseg":
        assert "--threads 4" in cmd


def test_full_docker_commands():
    imgs = {"fs": "freesurfer:bench", "mindglide": "mindglide:bench"}
    w = tb.tool_docker("wmhsynthseg", "/w/run/c", imgs, 4, "/w/fs_license/license.txt", "/usr/local/freesurfer/8.2.0-1",
                       "/w/models/" + tb.WMH_MODEL_NAME, name="tb-x")
    assert f"/w/models/{tb.WMH_MODEL_NAME}:/usr/local/freesurfer/8.2.0-1/models/{tb.WMH_MODEL_NAME}:ro" in w
    assert w[w.index("--entrypoint") + 1] == "/bin/bash" and w[w.index("freesurfer:bench") + 1] == "-c"
    assert "--crop" not in w and "--crop" in tb.tool_docker("wmhsynthseg", "/c", imgs, 4, "l", "/fs", "/m", wmh_crop=True)
    s = tb.tool_docker("samseg", "/c", imgs, 4, "/lic", "/fs")
    for flag in ("--pallidum-separate", "--random-seed", str(tb.SAMSEG_SEED), "Lesions"):
        assert flag in s
    m = tb.tool_docker("mindglide", "/c", imgs, 4)
    assert "--entrypoint" not in m and m[m.index("mindglide:bench") + 1] == "-i" and "/lic" not in m
    with pytest.raises(ValueError):
        tb.tool_docker("wmhsynthseg", "/c", imgs, 4, "/lic", None, None)
    assert tb.container_name("toolbench-pilot", "mslesseg_P10_T1", "samseg") == "tb-toolbench-pilot-samseg-mslesseg_P10_T1"


def _working_bash():
    import shutil
    import subprocess
    for b in (shutil.which("bash"), r"C:\Program Files\Git\bin\bash.exe", "/bin/bash"):
        try:
            if b and subprocess.run([b, "-c", "echo ok"], capture_output=True, text=True, timeout=20).stdout.strip() == "ok":
                return b
        except (OSError, subprocess.SubprocessError):
            continue
    return None


BASH = _working_bash()


@pytest.mark.skipif(BASH is None, reason="no working bash")
def test_freesurfer_wrapper_passes_arguments_verbatim():
    import subprocess
    r = subprocess.run([BASH, "-c", tb.FS_SETUP, "printf", "%s|", "--i", "/work/in/a b.nii.gz"],
                       capture_output=True, text=True, env={**os.environ, "FREESURFER_HOME": "/nonexistent"})
    assert r.returncode == 0 and r.stdout == "--i|/work/in/a b.nii.gz|"


@pytest.mark.skipif(BASH is None, reason="no working bash")
def test_vm_script_drops_only_the_failing_tool():
    import subprocess
    s = open(os.path.join(CLOUD, "vm_toolbench.sh")).read()
    fn = re.search(r"^drop\(\)\{.*?^\}", s, re.S | re.M).group(0)
    script = fn + '\nTOOLS="wmhsynthseg mindglide samseg"; REASON=test\ndrop wmhsynthseg samseg\necho "[$TOOLS]"\ndrop mindglide\necho unreachable\n'
    r = subprocess.run([BASH, "-c", script], capture_output=True, text=True)
    assert "[mindglide]" in r.stdout and "TOOL DROPPED: samseg (test)" in r.stdout
    assert r.returncode == 1 and "no tool left" in r.stdout and "unreachable" not in r.stdout


def test_samseg_mgz_output_on_the_input_grid(tmp_path):
    aff = np.diag([-0.75, 0.75, 3.9, 1.0]); aff[:3, 3] = [100, -110, -70]
    ref = nib.load(nii(str(tmp_path / "flair.nii.gz"), brain((16, 16, 6)), aff))
    lab = np.zeros((16, 16, 6), np.int32); lab[4:8, 4:8, 2:4] = 99; lab[0:2, 0:2, 0] = 2
    (tmp_path / "out" / "samseg" / "posteriors").mkdir(parents=True)
    nib.save(nib.MGHImage(lab, aff), str(tmp_path / "out" / "samseg" / "seg.mgz"))
    nib.save(nib.MGHImage((lab == 99).astype(np.float32) * 0.9, aff), str(tmp_path / "out" / "samseg" / "posteriors" / "Lesions.mgz"))
    outs = tb.find_outputs("samseg", str(tmp_path / "out"))
    seg, prob, rec = tb.to_reference("samseg", outs, ref)
    assert rec["seg_transform"]["kind"] == "identity" and rec["prob_transform"]["kind"] == "identity"
    assert int(seg.sum()) == 32 and prob.max() == pytest.approx(0.9) and rec["native_seg"]["labels_found"] == [0, 2, 99]
    out = str(tmp_path / "s.nii.gz")
    jc.save_like(seg, ref, out, np.uint8)
    back = nib.load(out)
    assert np.allclose(back.affine, ref.affine) and back.get_data_dtype() == np.uint8


def test_find_outputs(tmp_path):
    o = tmp_path / "out"
    (o / "samseg" / "posteriors").mkdir(parents=True)
    for f in ("samseg/seg.mgz", "samseg/posteriors/Lesions.mgz", "samseg/samseg.stats", "wmh_seg.nii.gz",
              "mindglide_seg.nii.gz"):
        (o / f).write_bytes(b"x")
    s = tb.find_outputs("samseg", str(o))
    assert s["seg"].endswith("seg.mgz") and s["prob"].endswith("Lesions.mgz") and s["aux"]["samseg.stats"]
    assert tb.find_outputs("mindglide", str(o))["prob"] is None
    assert tb.find_outputs("wmhsynthseg", str(o))["seg"].endswith("wmh_seg.nii.gz")


# ------------------------------------------------------------------ onto the FLAMeS grid
def test_lesion_label_extraction():
    lab = np.array([[[0, 18, 13], [77, 99, 18]]])
    assert tb.lesion_mask(lab, (18,)).sum() == 2 and tb.lesion_mask(lab, (77,)).sum() == 1
    assert tb.label_values(lab) == [0, 13, 18, 77, 99]


def test_identity_when_tool_returns_the_input_grid(tmp_path):
    aff = np.diag([-0.9, 0.9, 6.8, 1.0]); aff[:3, 3] = [100, -90, -60]
    ref = nib.load(nii(str(tmp_path / "flair.nii.gz"), brain((20, 20, 6)), aff))
    lab = np.zeros((20, 20, 6), np.uint8); lab[5:9, 5:9, 2:4] = 18; lab[0:3, 0:3, 0] = 13
    seg_p = nii(str(tmp_path / "out" / "mindglide_seg.nii.gz"), lab, aff, np.uint8)
    seg, prob, rec = tb.to_reference("mindglide", {"seg": seg_p, "prob": None}, ref)
    assert rec["seg_transform"]["kind"] == "identity" and prob is None
    assert seg.dtype == np.uint8 and int(seg.sum()) == 32 and rec["native_seg"]["labels_found"] == [0, 13, 18]


def test_one_mm_output_onto_thick_slices_uses_the_voxel_footprint(tmp_path):
    """A 1 mm lesion 3 mm thick inside an 8 mm slice is 3/8 of that slice: majority -> not lesion;
    a 6 mm thick lesion is 6/8 -> lesion. Point trilinear sampling would keep or lose both by luck."""
    ref_aff = np.diag([1.0, 1.0, 8.0, 1.0]); ref_aff[2, 3] = 3.5           # slice k covers z in [8k, 8k+8)
    ref = nib.load(nii(str(tmp_path / "flair.nii.gz"), brain((20, 20, 5)), ref_aff))
    lab = np.zeros((20, 20, 40), np.uint8)
    lab[2:6, 2:6, 10:13] = 77                                               # 3 mm in slice 1 -> dropped
    lab[10:14, 10:14, 16:22] = 77                                           # 6 mm in slice 2 -> kept
    seg_p = nii(str(tmp_path / "out" / "wmh_seg.nii.gz"), lab, np.eye(4), np.uint8)
    prob = (lab == 77).astype(np.float32) * 0.8
    prob_p = nii(str(tmp_path / "out" / "probs.nii.gz"), prob, np.eye(4))
    seg, p, rec = tb.to_reference("wmhsynthseg", {"seg": seg_p, "prob": prob_p}, ref)
    assert rec["seg_transform"]["kind"] == "footprint-mean" and rec["seg_transform"]["subsamples"] == [1, 1, 8]
    assert seg[3, 3, 1] == 0 and seg[11, 11, 2] == 1 and int(seg.sum()) == 16
    assert p[3, 3, 1] == pytest.approx(0.8 * 3 / 8, abs=1e-5) and p[11, 11, 2] == pytest.approx(0.6, abs=1e-5)


def test_footprint_equals_trilinear_without_downsampling():
    d = brain((10, 10, 10))
    shift = np.eye(4); shift[0, 3] = 0.5
    a, rec = jc.footprint_to_grid(d, np.eye(4), (10, 10, 10), shift)
    b, _ = jc.resample_to_grid(d, np.eye(4), (10, 10, 10), shift)
    assert rec["subsamples"] == [1, 1, 1] and np.allclose(a, b)


# ------------------------------------------------------------------ script and ledger safety
def test_vm_script_is_safe_to_launch():
    raw = open(os.path.join(CLOUD, "vm_toolbench.sh"), "rb").read()
    assert b"\r" not in raw                                                   # launch_vm.py refuses CRLF
    s = raw.decode()
    for forbidden in ("daita", "brain-mri-476110", "--gpus", "docker push"):
        assert forbidden not in s
    assert 'BKT="mstool-research-data"' in s and "trap finish EXIT" in s and "WALL-CLOCK GUARD" in s
    assert "--network=none" in open(os.path.join(CLOUD, "toolbench_driver.py")).read()
    assert "FS_IMAGE_DEFAULT" not in s and "FS_CHECK" not in s                # placeholders filled
    assert re.search(r"freesurfer/freesurfer@sha256:[0-9a-f]{64}", s)
    assert re.search(r"mindglide@sha256:[0-9a-f]{64}", s)


def test_ledger_reads_toolbench_cost_and_manifests():
    s = open(os.path.join(CLOUD, "build_ledger.py")).read()
    assert '"toolbench/cost"' in s and '"toolbench/manifests"' in s
