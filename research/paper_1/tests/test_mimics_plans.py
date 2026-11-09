"""Paper 1 addendum, amendment 1: frozen sets, budget rule, work plans and the flat-folder enumerators.
No cloud call (launch_mimics only builds plans here).

    python -m pytest research/paper_1/tests/test_mimics_plans.py -q
"""
import json
import os
import sys
from collections import Counter

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "mimics"))
sys.path.insert(0, os.path.join(ROOT, "research", "cloud"))
import freeze_amendment_sets as FS  # noqa: E402
import launch_mimics as LM  # noqa: E402
import mimics_prep as MP  # noqa: E402
import plan_mimics as PM  # noqa: E402

SETS = json.load(open(os.path.join(HERE, "..", "mimics", "analysis_sets.json")))


def test_dlbs_sample_is_reproducible_and_stratified():
    sample, rank, reduced = FS.dlbs_sample(SETS["B_dlbs"])
    assert sample == SETS["B1_sample"]["ids"] and reduced == SETS["B1_sample"]["reduced_75"]["ids"]
    assert Counter(rank[s]["decade"] for s in sample) == {50: 25, 60: 25, 70: 25, 80: 25}
    assert all(SETS["B_dlbs"][s]["set"] == "B1" for s in sample) and set(reduced) <= set(sample) and len(reduced) == 75


def test_samseg_subset_rule():
    sub = FS.samseg_subset(SETS["C1_ms_iso"], SETS["C1_native_thickness"]["mm"])
    assert sub == SETS["C1_samseg_subset"]["ids"] and len(sub) == 50
    assert not any(SETS["C1_ms_iso"][c]["flames_contaminated"] for c in sub)
    assert sum(c.startswith("openms_") for c in sub) == 10


def test_budget_rule_full_plan_fits_with_ledger_seconds_and_reductions_are_ordered():
    r = PM.apply_rule(PM.LEDGER_SECONDS)
    assert r["selected"] == "full amendment-1 plan" and r["projection"]["usd_high"] <= PM.CAP_USD
    slow = {k: v * 1.6 for k, v in PM.LEDGER_SECONDS.items()}
    r2 = PM.apply_rule(slow)
    labels = [x["variant"] for x in r2["considered"]]
    assert labels == [v[0] for v in PM.VARIANTS][:len(labels)]
    costs = [PM.projection(PM.work(**kw), PM.LEDGER_SECONDS)["usd_high"] for _, kw in PM.VARIANTS]
    assert costs == sorted(costs, reverse=True)
    g = PM.guards(r["kwargs"], PM.LEDGER_SECONDS, 0.5)
    assert g and g["worst_case_usd"] <= PM.CAP_USD


@pytest.mark.parametrize("kw", [kw for _, kw in PM.VARIANTS])
def test_every_input_tool_pair_is_planned_exactly_once(kw):
    plans, hours = LM.full_plans(SETS, kw, dict(PM.LEDGER_SECONDS))
    got = Counter((i, t) for p in plans.values() for st in p["steps"] for t in st["tools"] for i in st["inputs"])
    thick = tuple(kw.get("c1_thick", (3, 5, 7)))
    b = SETS["B1_sample"]["reduced_75"]["ids"] if kw.get("dlbs_n") == 75 else SETS["B1_sample"]["ids"]
    a = sorted(SETS["A_wmh2017"])
    a_test = [i for i in a if SETS["A_wmh2017"][i]["split"] == "test"]
    c1 = [f"{c}_th{t}" for c in SETS["C1_ms_iso"] for t in thick]
    sam = [f"{c}_th{t}" for c in SETS["C1_samseg_subset"]["ids"] for t in (1,) + thick]
    c2 = [f"{c}_th7" for c in SETS["C2_sibbms"]] if kw.get("with_c2", True) else []
    want = Counter()
    for t in ("flames", "lstai", "mindglide"):                 # LST-AI: P49_T2 has a blank T1 (registered skip)
        want.update((i, t) for i in a + b + c1 + c2 if not (t == "lstai" and i.startswith("mslesseg_P49_T2")))
    want.update((i, "wmhsynthseg") for i in a_test + b + c1 + c2)
    want.update((i, "samseg") for i in a + b + sam + c2)
    assert got == want                                    # nothing missing, nothing twice
    assert all(v > 0 for v in hours.values())
    assert max(hours.values()) / min(hours.values()) < 1.6


def test_three_vms_images_waits_and_preparation():
    plans, hours = LM.full_plans(SETS, {}, dict(PM.LEDGER_SECONDS))
    assert set(plans) == set(LM.FULL_VMS) and len(plans) == 3                 # global quota: 12 vCPUs
    assert sum(LM.VM[v][1] for v in LM.FULL_VMS) <= 250                      # regional SSD quota
    tools = {v: {t for st in p["steps"] for t in st["tools"]} for v, p in plans.items()}
    assert "lstai" in tools["mimics-v1"] and not tools["mimics-v1"] & {"wmhsynthseg", "samseg", "mindglide"}
    assert {"wmhsynthseg", "mindglide"} <= tools["mimics-v2"] and "lstai" not in tools["mimics-v2"]
    assert not tools["mimics-v3"] & {"lstai", "mindglide", "wmhsynthseg"}
    for v, needs in (("mimics-v1", "lstai"), ("mimics-v2", "fs"), ("mimics-v3", "fs")):
        assert needs in LM.VM[v][3].split()
    assert plans["mimics-v1"]["prep"][0]["block"] == "A" and len(plans["mimics-v1"]["prep"][0]["finalize"]) == 170
    assert plans["mimics-v3"]["prep"][0]["block"] == "B" and len(plans["mimics-v3"]["prep"][0]["finalize"]) == 100
    assert all(st.get("wait_blocks") for st in plans["mimics-v2"]["steps"]) and not plans["mimics-v2"]["prep"]
    own = {"mimics-v1": "A", "mimics-v3": "B"}
    for v, b in own.items():                                              # no VM waits for the block it prepares
        assert all(st.get("wait_blocks") != [b] for st in plans[v]["steps"])
    c = LM.plan_cost(hours, 0.33)
    assert c["usd_high"] <= PM.CAP_USD


def test_pilot_plan_simulates_every_c_input_and_runs_one_input_per_data_type():
    p = LM.pilot_plan(SETS)
    c1 = next(x for x in p["prep"] if x.get("block") == "C1")
    assert len(c1["finalize"]) == 145 * 3 + 50 and c1["thicknesses"] == [3, 5, 7]
    assert p["steps"][0]["inputs"] == ["wmh_utrecht_1", "sub-178", "mslesseg_P10_T1_th7", "sub-001_th7"]
    assert "mslesseg_P10_T1" in SETS["C1_samseg_subset"]["ids"]
    assert SETS["A_wmh2017"]["wmh_utrecht_1"]["split"] == "test" and "sub-178" in SETS["B1_sample"]["ids"]


def test_flat_enumerators(tmp_path):
    import lstai_driver as LD
    import toolbench_driver as TD
    for n in ("wmh_utrecht_1_FLAIR.nii.gz", "wmh_utrecht_1_T1.nii.gz", "sub-001_th7_FLAIR.nii.gz", "notes.txt"):
        (tmp_path / n).write_bytes(b"x")
    t = TD.enumerate_cases({"flat": str(tmp_path)}, ["flat"])
    assert sorted(t) == ["sub-001_th7", "wmh_utrecht_1"] and t["sub-001_th7"]["cohort"] == "mimics"
    c = LD.enumerate_candidates({"flat": str(tmp_path)}, ["flat"])
    assert c["wmh_utrecht_1"]["t1"].endswith("wmh_utrecht_1_T1.nii.gz") and c["sub-001_th7"]["t1"] is None


class _Blob:
    def __init__(self, store, name):
        self.store, self.name = store, name

    def exists(self):
        return self.name in self.store

    def download_as_text(self):
        return self.store[self.name]

    def upload_from_filename(self, p):
        self.store[self.name] = open(p).read()

    def upload_from_string(self, s):
        self.store[self.name] = s


class _Bucket:
    def __init__(self):
        self.store = {}

    def blob(self, name):
        return _Blob(self.store, name)

    def list_blobs(self, prefix):
        return [_Blob(self.store, n) for n in sorted(self.store) if n.startswith(prefix)]


def test_finalize_needs_every_input_and_refuses_disagreeing_hashes(tmp_path):
    b = _Bucket()
    b.store[f"{MP.MANIFESTS}/prep-pilot.json"] = json.dumps({"records": {"x_th3": {"flair_sha256": "a"}}})
    assert not MP.finalize(b, "C1", ["x_th3", "y_th3"], str(tmp_path))
    b.store[f"{MP.MANIFESTS}/prep-nn.json"] = json.dumps({"records": {"y_th3": {"flair_sha256": "b"}}})
    assert MP.finalize(b, "C1", ["x_th3", "y_th3"], str(tmp_path))
    assert f"{MP.INPUTS}/_done_C1.json" in b.store and json.loads(b.store[f"{MP.INPUTS}/expected_C1.json"])["y_th3"]
    b.store[f"{MP.MANIFESTS}/prep-zz.json"] = json.dumps({"records": {"x_th3": {"flair_sha256": "DIFFERENT"}}})
    with pytest.raises(SystemExit):
        MP.merged_records(b)
