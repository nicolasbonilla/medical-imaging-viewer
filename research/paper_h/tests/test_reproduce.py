"""Reproduction test: the headline numbers of RESULTS.md, re-derived from the pinned refs.

Skipped when the pinned commits are not in the local clone (e.g. a shallow clone);
fetch them with ``git fetch origin <sha>`` or ``git fetch origin 'refs/pull/*/head:refs/remotes/pr/*'``.
"""
import pytest

from research.paper_h import config, gitlog, run_all

REPO = config.repo_root()
MISSING = [k for k, sha in config.REFS.items() if not gitlog.commit_exists(REPO, sha)]
pytestmark = pytest.mark.skipif(bool(MISSING), reason=f"pinned refs not available: {MISSING}")


@pytest.fixture(scope="module")
def results():
    return run_all.compute(REPO)


def test_coding_sheet_is_fully_traceable(results):
    # every quote found verbatim at its ref, every commit exists, every stage consistent with git
    assert results["rq2_failures"]["coding_problems"] == []


def test_rq1_headline(results):
    c = results["rq1_contribution"]
    assert (c["commits"]["all"]["agent"], c["commits"]["all"]["total"]) == (327, 388)   # SDP-001 v1.1 statement
    assert c["controlled_documents"]["agent"] == c["controlled_documents"]["commits"] == 67
    assert c["class_c_modules_any"]["agent"] == c["class_c_modules_any"]["commits"] == 25
    assert c["withdrawn_verification_record"]["created_by_commit"] == "b6be6e7"
    assert c["withdrawn_verification_record"]["creating_commit_agent_trailer"]


def test_rq2_headline(results):
    s = results["rq2_failures"]["summary"]
    assert s["episodes"] == 33
    assert s["by_stage"] == {"escaped": 19, "contained": 14}
    assert s["detected_by_owner"] == 0
    assert s["introduced_by_agent_trailer"] == s["with_introducing_commit"] == 28
    assert s["days_to_detection_by_stage"]["escaped"]["median"] == 91
    assert s["days_to_detection_by_stage"]["contained"]["max"] <= 3


def test_rq3_headline(results):
    v = results["rq3_verification"]
    assert v["rcv_headline"]["rows"]["Verified"] == {"recorded_2026_04_12": 21, "reverified_2026_07_18": 4}
    assert v["rcv_headline"]["controls"] == 22
    p = v["negative_controls_pooled"]
    assert (p["mutations"], p["detected"], p["declared_equivalent_or_redundant"], p["unexpected_undetected"]) \
        == (199, 194, 5, 0)
    assert v["manifest"]["main"]["implemented_with_erratum"] == ["RC-024", "RC-026", "RC-029"]
    assert v["capa010_new_tests_on_main_sources"] == {"total": 27, "failed": 25, "passed": 2, "expected_to_pass": 2}
    stale = {f["record"]: f["at_own_ref"]["differ"] for f in v["evidence_freshness_post_hoc"]}
    assert stale["RC-029 (CAPA-007)"] == ["backend/app/api/routes/segmentation_analysis.py",
                                          "backend/app/security/resource_access.py"]
    assert sum(len(d) for d in stale.values()) == 3


def test_rq4_headline(results):
    g = results["rq4_governance"]
    assert g["github"]["formal_reviews_total"] == 0
    a = g["approval_lines_in_controlled_documents_main"]
    assert a["lines"] == a["written_by_agent_trailered_commits"] == 31
    assert g["merges_on_main"]["local_with_agent_trailer"] == 3
