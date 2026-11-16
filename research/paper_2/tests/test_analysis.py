"""Tests of the paper-2 analysis, offline (fake provider; no network, no spend)."""
import json

import pytest

from research.paper_2 import analysis as A
from research.paper_2 import runner as RN
from research.paper_2.tests.test_records import _build
from research.paper_2.tests.test_runner import FakeProvider


@pytest.fixture
def recs(tmp_path, monkeypatch):
    monkeypatch.setattr(RN, "RUNS", tmp_path / "runs")
    _, r = _build(tmp_path)
    return [json.loads(json.dumps(x)) for x in r]


def test_statistics():
    assert A.cp(0, 10)["upper95_one_sided"] == pytest.approx(1 - 0.05 ** 0.1, abs=1e-4)
    assert A.cp(5, 10)["ci95"] == [pytest.approx(0.1871, abs=1e-4), pytest.approx(0.8129, abs=1e-4)]
    assert A.lower95_one_sided(30, 100) > 0.22
    assert A.holm([0.01, 0.04]) == [0.02, 0.04]
    assert A.holm([0.04, 0.01]) == [0.04, 0.02]
    t = A.mcnemar([(True, False)] * 9 + [(False, True)] * 1 + [(True, True)] * 5)
    assert (t["first_only"], t["second_only"]) == (9, 1) and t["p_two_sided"] < 0.05
    assert A.patient_of("mslesseg_P12_T3") == "mslesseg_P12" and A.patient_of("dlbs_0042") == "dlbs_0042"


def _row(scan, design, primary, unq, disagree, s="dlbs"):
    return {"scan": scan, "design": design, "arm": "flames_ens", "set": s, "primary": primary, "unq": unq,
            "disagree": disagree, "patient": scan}


def test_h1_gatekeeps_h2_h3():
    rows = [_row(f"s{i}", "D1", i < 20, i < 20, i < 25) for i in range(100)]           # 20 % primary, 25 disagreements
    rows += [_row(f"s{i}", "D2", False, False, i < 25) for i in range(100)]
    rows += [_row(f"s{i}", "D2i", False, False, i < 25) for i in range(100)]
    p = A.primary_family(rows)
    assert p["H1"]["holds"] and p["disagreement_records"] == 25
    assert p["H2"]["tested"] and p["H2"]["fewer"] and p["H2"]["first_only"] == 20
    assert not p["H3"]["fewer"]                                                         # no difference D2 vs D2i
    low = [_row(f"s{i}", "D1", i < 2, i < 2, i < 25) for i in range(100)] + rows[100:]   # 2 %: H1 fails
    q = A.primary_family(low)
    assert not q["H1"]["holds"] and q["H2"]["p_holm"] is None and not q["H2"]["tested"]


def test_too_few_disagreements_keep_p_one():
    rows = [_row(f"s{i}", "D1", True, True, i < 5) for i in range(50)]
    rows += [_row(f"s{i}", d, False, False, i < 5) for d in ("D2", "D2i") for i in range(50)]
    p = A.primary_family(rows)
    assert p["H1"]["holds"] and not p["H2"]["tested"] and p["H2"]["p_used"] == 1.0


def test_analyse_end_to_end_with_fake_drafts(recs):
    for r in recs:                               # the fixture's sets: make one non-pilot setting-P record per arm
        r["set"] = "dlbs" if r["set"] == "sibbms" else r["set"]
    info = RN.run("gemini", "full", recs, provider=FakeProvider(), workers=2)
    assert info["done"] == info["jobs"] > 0
    out, rows = A.analyse(recs, "gemini", RN.RUNS / "gemini-full")
    assert out["drafts"] == len(rows) == info["jobs"] and out["missing_drafts"] == 0
    assert out["frozen"]["passed"]
    assert {"H1", "H2", "H3"} <= set(out["primary"])
    assert all(isinstance(r["clean"], bool) and isinstance(r["primary"], bool) for r in rows)
    s1, s2 = A.samples(rows), A.samples(rows)
    assert s1 == s2 and len(s1["judges"]) <= A.JUDGE_N and set(s1["author"]) <= {r["key"] for r in rows}


def test_repeat_jobs_are_keyed_apart(recs):
    for r in recs:
        r["set"] = "dlbs" if r["set"] == "sibbms" else r["set"]
    jobs = RN.repeat_jobs(recs)
    keep = RN.repeat_set(recs)
    assert len(jobs) == len(keep) * len(RN.REPEAT_DESIGNS) * len(RN.REPEAT_DRAFTS)
    assert all(j.key.endswith(("|draft2", "|draft3")) for j in jobs) and len({j.key for j in jobs}) == len(jobs)
    assert RN.repeat_set(recs) == keep                                                   # seeded
