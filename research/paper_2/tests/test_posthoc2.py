"""Tests of the post-hoc experiments E3 (D2p) and E4 (D1f, D2f), offline, with scripted model answers."""
import copy
import json

import pytest

from research.agents_benchmark import arms as A
from research.paper_2 import designs as D
from research.paper_2 import posthoc2 as P2
from research.paper_2 import runner as RN
from research.paper_2.tests.test_designs import honest, rec

SECOND = {"tool": "LST-AI", "lesion_count": 6,
          "regions": {"Periventricular": 4, "Juxtacortical": 1, "Infratentorial": 1, "Deep White Matter": 0},
          "dis": {"status": "evaluated", "dis_met_brain": True, "brain_regions_with_lesions": 3}}


def record(dis_extra=True):
    v = honest(second=copy.deepcopy(SECOND))
    if dis_extra:
        v["dis"]["criteria"] = "McDonald 2024 (Montalban et al., Lancet Neurology 2025)"
    return {"scan": "sub-178", "arm": "flames_ens", "set": "dlbs", "views": {"base": v, "d2": copy.deepcopy(v)},
            "meta": {}}


def tool_out(job, name):
    """Drive the agent through one tool call and return what the tool handed back."""
    job.next_request()
    job.consume({"content": [{"type": "tool_use", "id": "t1", "name": name, "input": {}}], "usage": {}})
    return json.loads(job.messages[-1]["content"][0]["content"])


def test_frozen_files_unchanged():
    assert RN.frozen_check()["passed"]


def test_d2p_labels_the_second_tool_and_changes_nothing_else():
    r = record()
    v = P2.view_for(r, "D2p")
    job, ref = P2.D2p(rec(v)), D.D2(rec(r["views"]["d2"]))
    assert job.system == ref.system and job.next_request()["tools"] == ref.next_request()["tools"]   # prompts unchanged
    sec = tool_out(job, "get_second_segmentation")
    assert sec["basis"] == P2.BASIS and sec["confirmed"] is False
    assert sec["regions"] == {"confirmed": False, "source": P2.REGION_SOURCE, "lesion_counts": SECOND["regions"]}
    assert sec["dis"]["basis"] == P2.BASIS and sec["dis"]["dis_met_brain"] is True
    assert "interpretation" not in sec["dis"] and sec["lesion_count"] == 6
    assert tool_out(P2.D2p(rec(v)), "get_dis_status") == r["views"]["d2"]["dis"]                    # primary unchanged
    assert job.key.split("|")[1] == "D2p"


def test_d1f_record_carries_rule_interpretation_and_age():
    r = record()
    v = P2.view_for(r, "D1f", {"dlbs/sub-178": 52})
    job, ref = P2.D1f(rec(v)), D.D1(rec(r["views"]["base"]))
    req, rref = job.next_request(), ref.next_request()
    assert req["system"] == rref["system"]
    sent = json.loads(req["messages"][0]["content"].split("```json\n")[1].split("\n```")[0])
    dis = sent["dis"]
    assert "criteria" not in dis and "McDonald 2024 (" not in json.dumps(sent)
    assert dis["rule"] == P2.RULE and dis["interpretation"] == P2.INTERPRETATION and dis[P2.AGE_FIELD] == 52
    assert list(dis)[:len(r["views"]["base"]["dis"]) - 1] == [k for k in r["views"]["base"]["dis"] if k != "criteria"]
    # where the provider releases no per-person age, the field is omitted
    v2 = P2.view_for(dict(r, set="wmh2017"), "D1f", {"dlbs/sub-178": 52})
    assert P2.AGE_FIELD not in v2["dis"] and v2["dis"]["interpretation"] == P2.INTERPRETATION
    # the exact interpretation text
    assert P2.INTERPRETATION.startswith("Automated location-only count. It does not apply the 2024 McDonald criteria:")
    assert P2.INTERPRETATION.endswith("without a radiologist's review of the lesions and of the clinical context.")


def test_d2f_fixed_record_and_labelled_second_with_interpretation():
    r = record()
    v = P2.view_for(r, "D2f", {"dlbs/sub-178": 70})
    job = P2.D2f(rec(v))
    assert job.system == D.D2(rec(r["views"]["d2"])).system
    dis = tool_out(job, "get_dis_status")
    assert dis["rule"] == P2.RULE and dis[P2.AGE_FIELD] == 70 and "criteria" not in dis
    sec = tool_out(P2.D2f(rec(v)), "get_second_segmentation")
    assert sec["confirmed"] is False and sec["dis"]["interpretation"] == P2.INTERPRETATION
    assert r["views"]["d2"]["dis"].get("criteria")                                                # input untouched


def test_unavailable_second_tool_stays_unavailable():
    assert P2.labelled_second({"available": False}) == {"available": False}
    assert P2.labelled_second(None) is None


def test_ages_from_provider_files(tmp_path):
    (tmp_path / "p.tsv").write_text("participant_id\tAgeMRI_W1\tSex\nsub-178\t52\tf\nsub-9\tn/a\tm\n", encoding="utf-8")
    (tmp_path / "c.csv").write_text("﻿Patient;Timepoint;Age;Sex;\nP10;T1;28,91;F;\nP55;T1;35,61;F;\n",
                                    encoding="utf-8")
    (tmp_path / "l.csv").write_text("patient_id,age,sex\n26,40,F\n27,N/A,F\n", encoding="utf-8")
    recs = [{"scan": s, "arm": "flames_ens", "set": st} for s, st in
            (("sub-178", "dlbs"), ("sub-9", "dlbs"), ("wmh_utrecht_1", "wmh2017"), ("mslesseg_P10_T1", "ms"),
             ("mslesseg_P55", "ms"), ("openms_patient26", "ms"), ("openms_patient27", "ms"), ("sub-178", "sibbms"))]
    out = P2.build_ages(recs, {"dlbs": tmp_path / "p.tsv", "mslesseg": tmp_path / "c.csv",
                               "ljubljana": tmp_path / "l.csv"})
    assert out["ages"] == {"dlbs/sub-178": 52, "ms/mslesseg_P10_T1": 28, "ms/mslesseg_P55": 35,
                           "ms/openms_patient26": 40}
    assert out["availability"]["wmh2017"] == {"records": 1, "with_age": 0}
    assert all(len(v["sha256"]) == 64 for v in out["sources"].values())


def test_jobs_exclude_pilot_records_and_need_ages(tmp_path, monkeypatch):
    from research.paper_2.tests.test_records import _build
    monkeypatch.setattr(RN, "RUNS", tmp_path / "runs")
    _, recs = _build(tmp_path)
    pilot = RN.pilot_set(recs)
    jobs = P2.jobs_for(recs, "D2p", "gemini", "full")
    assert jobs and all((j.rec["meta"]["scan"], "flames_ens") not in pilot for j in jobs)
    assert all(j.rec["meta"]["set"] in P2.SETS for j in jobs)
    with pytest.raises(SystemExit):
        P2.jobs_for(recs, "D1f", "gemini", "full", None)
    assert len({j.key for j in jobs + P2.jobs_for(recs, "D2f", "gemini", "full", {})}) == 2 * len(jobs)


def test_reduction_order():
    costs = {(a, d): 0.001 for d, al in P2.PLAN.items() for a in al}
    costs.update({("sonnet", "D2p"): 0.0075, ("sonnet", "D2f"): 0.0075, ("sonnet", "D1f"): 0.0065})
    spent = {"anthropic": 17.5, "anthropic_amendment": 0.1, "gemini": 31.9, "maas": 2.2, "mistral": 1.6}
    p = P2.plan_runs(costs, spent, 393, 123, 61, 270)
    assert ("sonnet", "D1f", "full") not in p["runs"] and ("sonnet", "D2f", "full") in p["runs"]
    assert p["reductions"] == ["anthropic (1): Sonnet D1f dropped"]
    costs.update({("sonnet", "D2p"): 0.009, ("sonnet", "D2f"): 0.009})
    p = P2.plan_runs(costs, spent, 393, 123, 61, 270)
    assert ("sonnet", "D2p", "ms_half") in p["runs"] and len(p["reductions"]) == 2
    costs[("mistral3", "D2p")] = 0.006
    p = P2.plan_runs(costs, spent, 393, 123, 61, 270)
    assert ("mistral3", "D2p", "setting_p") in p["runs"]


def test_cluster_exact_never_zero_width():
    all_yes = [(f"p{i // 2}", 1) for i in range(40)]                 # 40 examinations of 20 patients, all conveyed
    c = P2.cluster_exact(all_yes)
    assert c["rate"] == 1.0 and c["n_effective"] == 20 and c["ci95_cluster_exact"][0] < 1.0
    mixed = [("a", 1), ("a", 1), ("b", 0), ("b", 0), ("c", 1), ("d", 0), ("e", 1), ("f", 1)]
    m = P2.cluster_exact(mixed)
    assert m["design_effect"] >= 1 and m["ci95_cluster_exact"][0] < m["rate"] < m["ci95_cluster_exact"][1]


def test_flags_no_clinical_caveat_outcome():
    plain = A.DISCLAIMER["en"] + "\n\n## Impression\nThe brain dissemination in space criterion is met."
    caveat = plain + " Small-vessel disease is an alternative explanation."
    f1, f2 = P2.flags(plain), P2.flags(caveat)
    assert f1["ms"] and f1["unq"] and f1["ms_no_clinical"] and not f1["clinical_any"]
    assert f2["ms"] and f2["clinical_any"] and not f2["ms_no_clinical"]
    auto = A.DISCLAIMER["en"] + "\n\n## Impression\nThe automated rule's dissemination in space criterion is met."
    assert P2.flags(auto)["unq"] and not P2.flags(auto)["unq_automat"]          # frozen list lacks "automated"


def test_paired_difference():
    a = {f"s{i}": {"unq": i < 5} for i in range(20)}
    b = {f"s{i}": {"unq": i < 9} for i in range(20)}
    p = P2.paired(a, b, "unq")
    assert p["first_only"] == 0 and p["second_only"] == 4 and p["difference"] == 0.2
    assert p["ci95_people_bootstrap"][0] <= 0.2 <= p["ci95_people_bootstrap"][1]
