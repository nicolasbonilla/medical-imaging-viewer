"""Paper 1 addendum evaluation on a tiny synthetic world: every block (A, B, C1, C2), every family and part D run
end to end. The app's DIS functions and the greedy warp are replaced by stand-ins (the real paths are exercised
by gates G1 and GR on the real data). Local, CPU; no cloud.

    python -m pytest research/paper_1/tests/test_evaluate_mimics.py -q
"""
import json
import os
import sys

import nibabel as nib
import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "mimics"))
import evaluate_mimics as E  # noqa: E402

SHAPE = (16, 14, 12)
AFF = np.eye(4)


def save(path, data, dtype=np.float32):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img = nib.Nifti1Image(np.asarray(data, dtype), AFF)
    img.set_data_dtype(dtype)
    nib.save(img, path)


class FakeApp:
    """Zone PV in the left half, JC in the right half; DIS = lesions in both."""
    def __init__(self):
        self.z = np.zeros(SHAPE, np.uint8)
        self.z[: SHAPE[0] // 2] = 1
        self.z[SHAPE[0] // 2:] = 2

    def run(self, vl):
        if not vl:
            return {"dis_met_brain": False, "regions": {}, "any_dis_region": False}, None
        cls = np.zeros(SHAPE, np.uint8)
        regs = set()
        for v in vl:
            r = int(self.z.ravel()[v[0]])
            cls.ravel()[v] = r
            regs.add(r)
        return {"dis_met_brain": len(regs) >= 2, "regions": {}, "any_dis_region": bool(regs)}, cls


def lesion(arr, left=True, val=1.0):
    x0 = 2 if left else 10
    arr[x0:x0 + 3, 3:6, 3:6] = val
    return arr


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "app_for", lambda img: FakeApp())
    monkeypatch.setattr(E, "warp_float", lambda arr, ref, base, d, tag: np.asarray(arr, np.float32))
    monkeypatch.setattr(E, "N_BOOT", 200)
    root = tmp_path
    d = {"pf": str(root / "pf"), "mimics": str(root / "mimics"), "wmh": str(root / "wmh"), "out": str(root / "work"),
         "reg": str(root / "work" / "registration"), "manifests": str(root / "man"),
         "msmask": str(root / "msmask.nii.gz"), "atlas_t1_raw": "", "atlas_t1": ""}
    os.makedirs(d["out"])
    save(d["msmask"], np.ones(SHAPE), np.uint8)
    sets = {"A_wmh2017": {}, "B_dlbs": {}, "C1_ms_iso": {}, "C2_sibbms": ["sub-001", "sub-002", "sub-003"],
            "C1_samseg_subset": {"ids": ["mslesseg_P1_T1"]},
            "C1_native_thickness": {"stratum": {"mslesseg_P1_T1": "3mm", "mslesseg_P2_T1": "<=2.3mm", "openms_patient16": "<=2.3mm"}},
            "B1_sample": {"ids": ["sub-10", "sub-11", "sub-12"], "reduced_75": {"ids": ["sub-10"]}}}
    both = lesion(lesion(np.zeros(SHAPE, np.float32)), left=False)
    left = lesion(np.zeros(SHAPE, np.float32))
    reg = {}
    for k, (i, split) in enumerate((("wmh_utrecht_1", "test"), ("wmh_utrecht_0", "training"))):
        sets["A_wmh2017"][i] = {"split": split, "site": "Utrecht", "wmh": f"{i}/wmh.nii.gz",
                                "extra_observers": [f"{i}/o3.nii.gz", f"{i}/o4.nii.gz"] if split == "training" else []}
        save(f"{d['wmh']}/{i}/wmh.nii.gz", both, np.float32)
        for o in ("o3", "o4"):
            save(f"{d['wmh']}/{i}/{o}.nii.gz", left, np.float32)
        reg[i] = {"pass": True, "dice_brain": 0.9}
    for i, age in (("sub-10", 55), ("sub-11", 72), ("sub-12", 84)):
        sets["B_dlbs"][i] = {"age_mri_w1": age, "recruitment_cohort": 1}
        reg[i] = {"pass": True, "dice_brain": 0.9}
    json.dump({"records": reg}, open(os.path.join(d["out"], "registration.json"), "w"))
    for c, contam in (("mslesseg_P1_T1", False), ("mslesseg_P2_T1", False), ("openms_patient16", False)):
        sets["C1_ms_iso"][c] = {"flames_contaminated": contam, "lstai_missing": False}
    # outputs
    for i in list(sets["A_wmh2017"]) + sets["B1_sample"]["ids"]:
        save(f"{d['mimics']}/inputs/{i}_FLAIR.nii.gz", np.ones(SHAPE))
        for k in range(5):
            save(f"{d['mimics']}/flames/{i}_f{k}_prob.nii.gz", both * 0.8)
        save(f"{d['mimics']}/lstai/{i}_lstai_prob.nii.gz", left * 0.9)
        for t in E.TOOLS:
            save(f"{d['mimics']}/toolbench/{i}_{t}_seg.nii.gz", both, np.uint8)
    for c in sets["C1_ms_iso"]:
        save(f"{d['pf']}/flames/{c}_gt.nii.gz", both, np.uint8)
        ids = [(c, "pf")] + [(f"{c}_th{t}", "mimics") for t in (3, 5, 7)] + [(f"{c}_th1", "mimics")]
        for i, src in ids:
            for k in range(5):
                save(f"{d[src]}/flames/{i}_f{k}_prob.nii.gz", both * (0.9 if src == "pf" else 0.6))
            save(f"{d[src]}/lstai/{i}_lstai_prob.nii.gz", left * 0.9)
            for t in E.TOOLS:
                save(f"{d[src]}/toolbench/{i}_{t}_seg.nii.gz", both if src == "pf" else left, np.uint8)
    for s in sets["C2_sibbms"]:
        save(f"{d['pf']}/flames/{s}_gt.nii.gz", np.zeros(SHAPE), np.uint8)
        for i, src in ((s, "pf"), (f"{s}_th7", "mimics")):
            for k in range(5):
                save(f"{d[src]}/flames/{i}_f{k}_prob.nii.gz", left * 0.7)
            save(f"{d[src]}/lstai/{i}_lstai_prob.nii.gz", np.zeros(SHAPE))
            for t in E.TOOLS:
                save(f"{d[src]}/toolbench/{i}_{t}_seg.nii.gz", both if t == "mindglide" else np.zeros(SHAPE), np.uint8)
    return d, sets


def test_end_to_end_synthetic(world):
    d, sets = world
    us = E.units(sets, d)
    assert sum(u["block"] == "C1" for u in us) == 3 * 4 and sum(u["block"] == "C2" for u in us) == 6
    a_train = next(u for u in us if u["id"] == "wmh_utrecht_0")
    assert "wmhsynthseg" not in a_train["arms"]                      # contaminated cells not produced (15.2)
    recs = [E.one_unit((u, d)) for u in us]
    S = E.analyse(recs, sets, d)
    assert S["A"]["A0_expert_dis"]["x"] == 2 and S["A"]["observers_training"]["O3"] == 0
    assert S["A"]["arms"]["wmhsynthseg"]["dis"]["n"] == 1
    assert S["B"]["arms"]["flames_ens"]["b_dis"]["x"] == 3 and S["B"]["arms"]["lstai"]["b_dis"]["x"] == 0
    assert S["C2"]["arms"]["mindglide"]["T7"]["b"]["x"] == 3 and S["C2"]["arms"]["samseg"]["T7"]["b"]["x"] == 0
    assert S["C1"]["thicknesses"] == [1.0, 3.0, 5.0, 7.0]
    assert S["C1"]["arms"]["mindglide"]["T1"]["accuracy"]["f1"]["median"] == 1.0
    assert S["C1"]["arms"]["mindglide"]["T7"]["accuracy"]["f1"]["median"] < 1.0
    assert S["n_primary_tests"] == 6 + 5 + 5 + 5 + 6 + 5 + 6 + 2
    assert S["consistency_recount_vs_app"] == 0
    assert set(S["D"]) == {"flames_ens", "flames_f0"}
    g = S["D"]["flames_ens"]
    assert len(g["grid"]) == 50 and g["default"]["t"] == 0.5
    for f in S["families"].values():
        assert all("p_holm_family" in e and "p_holm_all_40" in e for e in f)
    S["gate_G1"] = E.gate_g1(recs, d)                       # runs on the real reference files; cannot pass here
    assert S["gate_G1"]["passed"] is False and S["gate_G1"]["paper_d_reference"]["n"] == 3
    S["gate_GR"] = {"by_block": {"A": {"pass": 2, "n": 2}}}
    E.write_tables(S, d["out"])
    E.write_csvs(recs, d["out"])
    assert os.path.getsize(os.path.join(d["out"], "tables.md")) > 500


def test_variant_reductions_change_the_units(world):
    d, sets = world
    json.dump({"with_c2": False, "c1_thick": [3, 7], "dlbs_n": 75}, open(os.path.join(d["out"], "variant.json"), "w"))
    us = E.units(sets, d)
    assert not any(u["id"].endswith("_th7") and u["block"] == "C2" for u in us)
    assert sorted({u["T"] for u in us if u["block"] == "C1"}) == [1.0, 3.0, 7.0]
    assert [u["id"] for u in us if u["block"] == "B"] == ["sub-10"]


def test_dis_recount_rules():
    les = [(5.0, "PV"), (5.0, "PV"), (20.0, "JC"), (2.0, "IT")]
    assert E.dis_from_lesions(les, 3.0) and not E.dis_from_lesions(les, 3.0, pv_min=3)
    assert not E.dis_from_lesions(les, 14.137)
    assert E.newcombe(19, 100, 10, 100)["ci95"][0] < 0.09 < E.newcombe(19, 100, 10, 100)["ci95"][1]
    assert E.fleiss([[1, 1, 1], [0, 0, 0], [1, 1, 0]]) is not None
