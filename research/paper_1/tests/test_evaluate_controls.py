"""Paper 1 evaluation on synthetic controls: arm masks, lesion rule, missing outputs, paired tests with the
registered Holm family, the paper A reproduction gate and the structural check. The app's DIS functions are
replaced by a stand-in here (they need the 1-mm MNI grid; the real path is exercised by gate G1 on the real
maps). Local, CPU; no cloud.

    python -m pytest research/paper_1/tests -q
"""
import argparse
import json
import os
import sys

import nibabel as nib
import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
P1 = os.path.dirname(HERE)
sys.path.insert(0, P1)
import evaluate_controls as E  # noqa: E402
import hc_core as H  # noqa: E402

SHAPE = (16, 14, 12)
AFF = np.eye(4)


def save(path, data, dtype=np.float32):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img = nib.Nifti1Image(np.asarray(data, dtype), AFF)
    img.set_data_dtype(dtype)
    nib.save(img, path)
    return path


class FakeApp:
    """Stand-in for hc_core.AppDIS: zone 1 (PV) in the left half, 2 (JC) in the right half; DIS = lesions in
    both zones."""
    def __init__(self):
        z = np.zeros(SHAPE, np.uint8)
        z[: SHAPE[0] // 2] = 1
        z[SHAPE[0] // 2:] = 2
        self.zone = np.ascontiguousarray(np.transpose(z, (2, 0, 1)))
        self.znifti = z

    def run(self, vl):
        if not vl:
            return {"dis_met_brain": False, "regions": {}, "any_dis_region": False}, None
        cls = np.zeros(SHAPE, np.uint8)
        regs = set()
        for v in vl:
            r = int(self.znifti.ravel()[v[0]])
            cls.ravel()[v] = r
            regs.add(r)
        pres = {"Periventricular": 1 in regs, "Juxtacortical": 2 in regs, "Infratentorial": False}
        return {"dis_met_brain": len(regs) >= 2, "regions": pres, "any_dis_region": bool(regs)}, cls


@pytest.fixture
def world(tmp_path, monkeypatch):
    cases = ["sub-001", "sub-002", "sub-003", "sub-004"]
    inputs = {c: {"cohort": "sibbms", "flair_sha256": "0" * 64, "shape": list(SHAPE), "zooms": [1.0, 1.0, 1.0],
                  "affine": AFF.tolist(), "band": "iso", "sub_band": "iso"} for c in cases}
    p = tmp_path / "controls_inputs.json"
    p.write_text(json.dumps(inputs))
    monkeypatch.setattr(E, "INPUTS", str(p))
    monkeypatch.setattr(E, "app_for", lambda img: FakeApp())
    d = {k: str(tmp_path / k) for k in ("flames", "lstai", "tool", "brainmask")}
    bm = np.zeros(SHAPE, np.uint8)
    bm[1:-1, 1:-1, 1:-1] = 1
    for c in cases:
        save(f"{d['flames']}/{c}_gt.nii.gz", np.zeros(SHAPE), np.uint8)
        save(f"{d['brainmask']}/{c}_brainmask.nii.gz", bm, np.uint8)
        for k in range(5):
            save(f"{d['flames']}/{c}_f{k}_prob.nii.gz", np.zeros(SHAPE))
        save(f"{d['lstai']}/{c}_lstai_prob.nii.gz", np.zeros(SHAPE))
    # sub-001: FLAMeS ensemble lesions in both zones (means 0.6 and 4 x 0.7 / 5 = 0.56) -> DIS;
    # fold 0 has only the first one
    for k in range(5):
        f = np.zeros(SHAPE, np.float32)
        f[2:4, 2:4, 2:4] = 0.6
        f[12:14, 2:4, 2:4] = 0.0 if k == 0 else 0.7
        save(f"{d['flames']}/sub-001_f{k}_prob.nii.gz", f)
    # sub-002: ensemble below 0.5 (only 2 of 5 folds = 1.0 -> mean 0.4): no ensemble lesion, fold 0 lesion
    for k in (0, 1):
        f = np.zeros(SHAPE, np.float32)
        f[5:7, 5:7, 5:7] = 1.0
        save(f"{d['flames']}/sub-002_f{k}_prob.nii.gz", f)
    # LST-AI: exactly 0.5 counts as lesion (>= 0.5); a 2-voxel blob (2 mm3 < 3 mm3) does not
    lp = np.zeros(SHAPE, np.float32)
    lp[3:5, 3:5, 3:5] = 0.5
    lp[10, 10, 10:12] = 0.9
    save(f"{d['lstai']}/sub-003_lstai_prob.nii.gz", lp)
    # MindGlide: binary masks for sub-001..sub-003, sub-004 missing (failed)
    for c in cases[:3]:
        m = np.zeros(SHAPE, np.uint8)
        if c != "sub-003":
            m[1:3, 8:10, 8:10] = 1
            m[13:15, 8:10, 8:10] = 1
        save(f"{d['tool']}/{c}_mindglide_seg.nii.gz", m, np.uint8)
    return cases, d


def run_all(cases, d, arms):
    return [E.one_control((c, d, arms)) for c in cases]


def test_arm_masks_and_lesion_rule(world):
    cases, d = world
    recs = run_all(cases, d, ["flames_ens", "flames_f0", "lstai", "mindglide"])
    r = {x["case"]: x["arms"] for x in recs}
    assert r["sub-001"]["flames_ens"]["n"] == 2 and r["sub-001"]["flames_ens"]["dis_met_brain"]
    assert r["sub-001"]["flames_f0"]["n"] == 1 and not r["sub-001"]["flames_f0"]["dis_met_brain"]
    assert r["sub-002"]["flames_ens"]["n"] == 0 and r["sub-002"]["flames_f0"]["n"] == 1
    assert r["sub-003"]["lstai"]["n"] == 1 and r["sub-003"]["lstai"]["voxels_equal_0.5"] == 8
    assert r["sub-003"]["lstai"]["gt_half"]["n"] == 0                     # '> 0.5' sensitivity drops it
    assert r["sub-004"]["mindglide"]["available"] is False
    les = r["sub-001"]["flames_ens"]["lesions"]
    assert [l["vol_mm3"] for l in les] == [8.0, 8.0] and {l["region"] for l in les} == {"PV", "JC"}
    assert r["sub-001"]["flames_ens"]["n_pf"] == 0                         # 8 mm3 < 14.137 mm3 (paper F rule)
    assert all(l["min_edt_mm"] >= 1.0 for l in les)
    # E1: the FLAMeS ensemble lesion of sub-001 overlaps no MindGlide lesion (different place)
    assert all(l["n_tools_overlapping"] == 1 for l in les)


def test_analysis_complete_case_and_registered_holm_family(world):
    cases, d = world
    arms = ["flames_ens", "flames_f0", "lstai", "mindglide"]
    res, _ = E.analyse(run_all(cases, d, arms), arms)
    a = res["arms"]
    assert a["flames_ens"]["a_false_alarm_scans"]["x"] == 1 and a["flames_ens"]["n"] == 4
    assert a["mindglide"]["n"] == 3 and a["mindglide"]["missing"] == 1 and not a["mindglide"]["incomplete"]
    assert a["mindglide"]["b_dis_met_brain"]["x"] == 2
    fam = res["comparisons"]["a"]
    assert set(fam) == set(E.COMPARED)                                     # family of 5 always
    assert fam["wmhsynthseg"]["run"] is False and fam["wmhsynthseg"]["p_holm_family"] == 1.0
    assert fam["mindglide"]["n_paired"] == 3                               # complete case
    assert fam["flames_f0"]["arm_only"] == 1 and fam["flames_f0"]["reference_only"] == 0
    s8 = res["secondary"]["mindglide"]["S8_missing"]
    assert s8["a_worst_case"]["x"] == 3 and s8["a_best_case"]["x"] == 2
    assert res["secondary"]["lstai_threshold_check"]["voxels_exactly_0.5_total"] == 8
    assert res["secondary"]["flames_ens"]["S3"]["lesions_by_region"]["PV"] == 1
    assert res["secondary"]["flames_ens"]["S4"]["lesions"]["3-14"] == 2


def test_tool_masks_must_be_binary_and_on_the_grid(world):
    cases, d = world
    save(f"{d['tool']}/sub-001_samseg_seg.nii.gz", np.full(SHAPE, 99), np.uint8)
    with pytest.raises(ValueError, match="not binary"):
        E.one_control(("sub-001", d, ["flames_ens", "samseg"]))
    img = nib.Nifti1Image(np.zeros(SHAPE, np.uint8), np.diag([2, 1, 1, 1]))
    nib.save(img, f"{d['tool']}/sub-002_samseg_seg.nii.gz")
    with pytest.raises(ValueError, match="FLAMeS grid"):
        E.one_control(("sub-002", d, ["flames_ens", "samseg"]))


def test_gate_g1_compares_with_the_paper_a_record(world):
    cases, d = world
    recs = run_all(cases, d, ["flames_ens", "flames_f0"])
    assert E.gate_g1(recs, {})["run"] is False                            # needs 100 controls
    fake = [dict(r, case=f"sub-{i:03d}") for i, r in enumerate(recs * 25, start=1)]
    n_ens = [x["arms"]["flames_ens"]["n"] for x in fake]
    n_f0 = [x["arms"]["flames_f0"]["n"] for x in fake]
    dis = [x["case"] for x in fake if x["arms"]["flames_ens"]["dis_met_brain"]]
    rec_a = {"per_control": [{"case": x["case"], "ens_candidates": a, "f0_candidates": b} for x, a, b in zip(fake, n_ens, n_f0)],
             "raw_candidates": {"ens": {"scans_with_any_candidate": 25, "candidates_total": 50},
                                "f0": {"scans_with_any_candidate": 50, "candidates_total": 50}},
             "app_dis": {"results": {"raw ens|all100": {"dis_met_brain": 25, "any_dis_region": 25, "cases_dis_met": dis},
                                     "raw f0|all100": {"dis_met_brain": 0, "any_dis_region": 50, "cases_dis_met": []}}},
             "location": {"raw ens": {"regions": {"PV": 25, "JC": 25, "IT": 0, "DWM": 0, "none": 0}}}}
    g = E.gate_g1(fake, rec_a)
    assert g["run"] and g["passed"], g
    rec_a["raw_candidates"]["ens"]["candidates_total"] = 51
    assert E.gate_g1(fake, rec_a)["passed"] is False


def test_structural_check(world, tmp_path, capsys):
    cases, d = world
    p = f"{d['tool']}/sub-001_mindglide_seg.nii.gz"
    man = {"run_id": "toolbench-ctl-x", "cases": [
        {"case": "sub-001", "tool": "mindglide", "seg_sha256": E.sha256(p), "lesion_voxels": 16,
         "native_seg": {"labels_found": [0, 18]}, "seg_transform": {"kind": "identity"}},
        {"case": "sub-002", "tool": "mindglide", "seg_sha256": "0" * 64, "lesion_voxels": 16,
         "native_seg": {"labels_found": [0, 18]}, "seg_transform": {"kind": "identity"}}]}
    md = tmp_path / "man"
    md.mkdir()
    (md / "toolbench-ctl-x.json").write_text(json.dumps(man))
    a = argparse.Namespace(tool_dir=d["tool"], manifests=str(md), tools=["mindglide"], cases=["sub-001", "sub-002", "sub-004"])
    assert E.cmd_check(a) == 1
    out = capsys.readouterr().out
    assert "PASS sub-001 mindglide" in out and "FAIL sub-002 mindglide" in out and "SHA-256 differs" in out
    assert "FAIL sub-004 mindglide" in out and "missing" in out
    assert "lesion" not in out.replace("lesion_voxels", "")               # no outcome printed


def test_frozen_inputs_and_registered_arms():
    d = json.load(open(os.path.join(P1, "controls_inputs.json")))
    assert len(d) == 100 and E.REFERENCE == "flames_ens" and len(E.COMPARED) == 5
    assert E.TOOL_LABEL == {"mindglide": 18, "wmhsynthseg": 77, "samseg": 99}
    assert E.SEED == 20261108 and E.N_BOOT == 10000 and E.QC_FLAG == "sub-075"
    assert E.SIZE_EDGES[1] == pytest.approx(14.137, abs=1e-3) and H.MIN_VOL_MM3 == 3.0
