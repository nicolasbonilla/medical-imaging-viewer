"""Paper 1 addendum 2: plans (launch_x, no cloud call) and the statistics / summary code of evaluate_addendum2 on small
synthetic records (no image data), so the evaluation VM cannot crash in the last step.

    python -m pytest research/paper_1/tests/test_addendum2.py -q
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "mimics"))
import evaluate_addendum2 as E2  # noqa: E402
import launch_x as LX  # noqa: E402

SEC = {"hdbet_b2": 1700, "flames5": 320, "lstai": 130, "mindglide": 75, "wmhsynthseg": 290, "samseg": 600,
       "synthseg": 150, "greedy1": 40}


def test_pilot_plan_and_full_plans_cover_everything_once():
    p = LX.pilot_plan()
    assert p["prep"][0]["ids"] == LX.X2["pilot"]["B2_tools"] and p["steps"][0]["tools"] == LX.TOOLS
    assert len(p["synthseg"]["pre"]) == 9 and len(p["synthseg"]["post"]) == 2
    plans, load = LX.full_plans(SEC, set())
    ids = LX.b2_ids()
    prep = sorted(i for pl in plans.values() for i in pl["prep"][0]["ids"])
    assert prep == sorted(ids)
    for t in LX.TOOLS:
        got = sorted(i for pl in plans.values() for s in pl["steps"] if s["tools"] == [t] for i in s["inputs"])
        assert got == sorted(ids), t
    ss = sorted(k for pl in plans.values() for k in pl["synthseg"]["pre"] + pl["synthseg"]["post"])
    assert len(ss) == len(set(ss)) == 591
    assert sorted(pl["register"]["run"] for pl in plans.values() if pl.get("register")) == ["detreg-a", "detreg-b"]
    assert all(len(pl["register"]["ids"]) == 345 for pl in plans.values() if pl.get("register"))
    assert all(k.startswith("openms_") or k.startswith("mslesseg_") for k in plans["mimics-x3"]["synthseg"]["pre"]
               if k.startswith(("openms_", "mslesseg_")))
    assert not any(k.startswith(("openms_", "mslesseg_")) for v in ("mimics-x1", "mimics-x2")
                   for k in plans[v]["synthseg"]["pre"])
    proj = LX.projection(load, 0.5, {v: LX.VM[v][4] for v in LX.FULL})
    assert proj["usd_high"] < LX.CAP_USD
    assert sum(LX.VM[v][1] for v in LX.FULL) <= 250


def test_statistics():
    lr = E2.lr_plus([("p1", 1), ("p1", 1), ("p2", 1), ("p3", 0)], [1, 0, 0, 0])
    assert abs(lr["lr_plus"] - 3.0) < 1e-9 and lr["ci95_boot"][0] is not None
    inf = E2.lr_plus([("p1", 1)], [0, 0, 0])
    assert inf["lr_plus_infinite"] and inf["lr_plus"] is None
    age = np.repeat([25, 35, 45, 55, 65, 75, 85], 25)
    rng = np.random.RandomState(0)
    y = rng.rand(age.size) < 1 / (1 + np.exp(-(age - 55) / 10))
    t = E2.logit_trend(age, y)
    assert t["estimable"] and t["or_per_decade"] > 1 and t["p_wald"] < 0.05
    assert not E2.logit_trend(age, np.ones(age.size))["estimable"]
    assert not E2.logit_trend(age, age > 50)["estimable"]                 # complete separation
    assert E2.icc_a1([1, 2, 3, 4], [1, 2, 3, 4]) == 1.0
    c = E2.cluster_exact([("a", 1), ("a", 1), ("b", 0), ("c", 1)])
    assert c["x"] == 3 and c["n"] == 4 and c["deff"] >= 1


def _rec(block, iid, age=None, dis=True, cohort=None):
    arms = {}
    for arm in E2.ARMS:
        a = {"available": True, "n_native": 3, "n": 3, "dis": dis, "dis_pv3": False, "any_dis_region": True,
             "lesions": [[20.0, "PV"], [5.0, "JC"], [30.0, "JC"]]}
        if arm in ("flames_ens", "flames_f0"):
            a["grid"] = {f"{0.5 + 0.05 * i:.2f}": {"dis": {f"{m:.3f}": dis for m in (3.0, 14.137, 25.0, 50.0, 100.0)}}
                         for i in range(10)}
        arms[arm] = a
    r = {"id": iid, "block": block, "base": iid, "T": 1.0 if block in ("C1", "C2") else 2.5, "age": age, "arms": arms,
         "gr_pass": True, "gr_dice": 0.95}
    if block in ("A", "C1"):
        r["expert"] = {"dis": True}
    return r


def _frec(cohort, block, iid, age=None, met=True):
    cfgs = {cfg: {"available": True, "rule": met, "rule_pv3": False, "rule_corner": met, "n_components": 4,
                  "n_lesions": 3, "regions": {"PV": 1, "JC": 1, "IT": 0, "other": 1}} for cfg in E2.CONFIGS}
    r = {"id": iid, "block": block, "base": iid, "cohort": cohort, "age": age, "key": iid, "configs": cfgs}
    if cohort == "sibbms":
        r["configs_atlas"] = {k: v for k, v in cfgs.items() if k != "experts"}
    return r


def test_analyses_and_summary_on_synthetic_records(tmp_path):
    recs3 = [_rec("B", f"sub-{1000 + i}", age=50 + i % 40, dis=i % 3 > 0) for i in range(40)]
    recs3 += [_rec("C2", f"sub-{i:03d}", dis=i % 5 == 0) for i in range(1, 21)]
    recs3 += [_rec("A", f"wmh_x_{i}") for i in range(10)] + [_rec("C1", f"mslesseg_P{i}_T1") for i in range(10)]
    recs_b2 = [dict(_rec("B", f"sub-{2000 + i}", age=21 + i % 29, dis=i % 4 == 0), sample="B2") for i in range(30)]
    a2 = E2.analysis2(recs3, recs_b2, [r for r in recs3 if r["block"] == "C2"])
    assert a2["n_20_49"] == 30 and len(a2["family_G1"]) == 6
    assert "E4_safeguard" in a2["arms"]["flames_ens"]["by_decade"] and "E4_safeguard" not in a2["arms"]["lstai"]["by_decade"]
    recs_f = [_frec("ms_1mm", "C1", f"mslesseg_P{i}_T1", met=i % 4 > 0) for i in range(12)]
    recs_f += [_frec("wmh", "A", f"wmh_x_{i}", met=i % 2 == 0) for i in range(10)]
    recs_f += [_frec("dlbs_50_89", "B", f"sub-{1000 + i}", age=50 + i, met=i % 3 == 0) for i in range(20)]
    recs_f += [_frec("dlbs_20_49", "B", f"sub-{2000 + i}", age=21 + i, met=False) for i in range(20)]
    recs_f += [_frec("sibbms", "C2", f"sub-{i:03d}", met=False) for i in range(1, 11)]
    gs = {r["key"]: {"qc_flag": False} for r in recs_f}
    a3 = E2.analysis3(recs_f, E2.app_decisions(recs3, recs_b2), gs)
    assert a3["lr_plus"]["rule"]["flames_ens"]["sibbms"]["lr_plus_infinite"]
    assert a3["vs_app_rule"]["flames_ens"]["wmh"]["n"] == 10
    S = {"gates": {"DG": {"byte_identical": 345, "n_expected": 345, "max_abs_matrix_diff": 0.0, "primary_pass": True},
                   "DC": {"passed": True, "per_unit_rows": 1, "lesion_rows": 1}, "GR_run3": {}, "GR_b2": a2["gr_b2"],
                   "G1_run3": True, "GS": {}},
         "analysis1": {"vs_run1": {"A": {}, "B": {}}, "vs_run2": {"A": {}, "B": {}}, "test_decisions_vs_run1": [],
                       "gr_dice_max_diff_vs_run1": 0, "gr_dice_max_diff_vs_run2": 0,
                       "run3": {"A": {arm: E2.cp(1, 2) for arm in E2.ARMS}, "B": {arm: E2.cp(1, 2) for arm in E2.ARMS},
                                "A_experts": E2.cp(1, 2)}},
         "analysis2": a2, "analysis3": a3}
    E2.write_summary(S, str(tmp_path))
    E2.write_faithful_csv(recs_f, str(tmp_path))
    txt = (tmp_path / "SUMMARY.md").read_text(encoding="utf-8")
    assert "Analysis 3" in txt and "Family G-1" in txt


def test_faithful_unit_on_tiny_images(tmp_path):
    import nibabel as nib
    aff = np.diag([1.0, 1.0, 3.0, 1.0])
    d = {k: str(tmp_path / k) for k in ("pf", "mimics", "wmh", "ss")}
    for sub in ("mimics/inputs", "mimics/flames", "mimics/lstai", "mimics/toolbench", "wmh/x", "ss", "pf/flames",
                "pf/lstai", "pf/toolbench"):
        os.makedirs(tmp_path / sub, exist_ok=True)
    shp = (20, 20, 8)
    m = np.zeros(shp, np.float32)
    m[5:9, 5, 3] = 1                                     # 4 mm in-plane, next to the "ventricle"
    m[14, 14, 6:8] = 1                                   # 2 slices = 3 mm, touching "cortex"
    lab = np.zeros(shp, np.int16)
    lab[2:5, 2:8, 3] = 4
    lab[:, :, 7:] = 3
    save = lambda arr, p, dt=np.float32: nib.save(nib.Nifti1Image(arr.astype(dt), aff), p)  # noqa: E731
    save(np.ones(shp), f"{d['mimics']}/inputs/wmh_t_1_FLAIR.nii.gz")
    for k in range(5):
        save(m, f"{d['mimics']}/flames/wmh_t_1_f{k}_prob.nii.gz")
    save(m, f"{d['mimics']}/lstai/wmh_t_1_lstai_prob.nii.gz")
    for t in ("mindglide", "wmhsynthseg", "samseg"):
        save(m, f"{d['mimics']}/toolbench/wmh_t_1_{t}_seg.nii.gz", np.uint8)
    save(m * 1, f"{d['wmh']}/x/wmh.nii.gz", np.uint8)
    save(lab, f"{d['ss']}/wmh_t_1_synthseg.nii.gz", np.int16)
    u = {"id": "wmh_t_1", "block": "A", "base": "wmh_t_1", "T": 3.0, "warp": True, "src": "mimics", "arms": list(E2.ARMS),
         "wmh": "x/wmh.nii.gz", "cohort": "wmh", "key": "wmh_t_1"}
    r = E2.faithful_unit((u, d))
    assert r["anat"] and set(r["configs"]) == set(E2.CONFIGS)
    for cfg, c in r["configs"].items():
        assert c["available"] and c["n_components"] == 2 and c["regions"]["PV"] == 1 and c["regions"]["JC"] == 1, cfg
        assert c["rule"] and not c["rule_pv3"]
