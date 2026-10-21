import pytest

from research.paper_h import verification as v

RCV = """# Title

## 1. Headline

| | 2026-04-12 record | 2026-07-18 actual |
|---|---|---|
| Verified | 21 / 22 (95.5 %) | **4 / 22 (18 %)** |
| Partial | 1 | 6 |
| Overstated / not implemented | **0** | **12** |

---

## 2. Next
| Verified | 99 | 99 |
"""


def test_parse_rcv_headline_reads_only_section_1():
    h = v.parse_rcv_headline(RCV)
    assert h["controls"] == 22
    assert h["rows"]["Verified"] == {"recorded_2026_04_12": 21, "reverified_2026_07_18": 4}
    assert h["rows"]["Overstated / not implemented"]["reverified_2026_07_18"] == 12
    assert len(h["rows"]) == 3


def test_manifest_summary_counts_status_and_errata():
    m = {"controls": {
        "RC-1": {"status": "implemented", "negative_control": "x", "note": "ok"},
        "RC-2": {"status": "implemented", "negative_control": "x", "note": "ERRATUM 2026: did not execute"},
        "RC-3": {"status": "not_implemented"},
        "RC-4": {"status": "implemented", "note": "ERRATUM but no nc"},
    }}
    s = v.manifest_summary(m)
    assert s["status"] == {"implemented": 3, "not_implemented": 1}
    assert s["implemented_with_erratum"] == ["RC-2", "RC-4"]
    assert s["implemented_with_negative_control"] == 2


def test_schema_a_detected_undetected_expected_and_not_applied():
    rec = {
        "mutations": {
            "A": {"failed": 2, "passed": 3, "applied": True},
            "B": {"failed": 0, "passed": 5, "applied": True},
            "C": {"failed": 0, "passed": 5, "errors": 1, "applied": True},
            "D": {"failed": 3, "passed": 2, "applied": False},
            "E": {"failed": 0, "passed": 5, "applied": True},
        },
        "expected_undetected": {"B": "redundant by design"},
        "restored": {"failed": 0, "passed": 5, "errors": 0},
    }
    n = v.normalise_record(rec)
    assert n["mutations"] == 5 and n["detected"] == 2          # A, C (error counts)
    assert n["not_applied"] == ["D"]                            # a mutation not applied is never 'detected'
    assert n["expected_undetected"] == ["B"] and n["unexpected_undetected"] == ["E"]
    assert n["restored_green"] is True


def test_schema_a_restored_per_file():
    rec = {"mutations": {}, "restored": {"a.py": {"failed": 0}, "b.ts": {"failed": 1}}}
    assert v.normalise_record(rec)["restored_green"] is False


def test_schema_b_separates_before_and_old_runs():
    rec = {"results": [
        {"id": "G1", "detected": True}, {"id": "G6", "detected": False},
        {"id": "BEFORE-1", "detected": True}, {"id": "I1-old", "detected": False},
    ], "summary": {"not_detected_explained": {"G6": "phantoms cannot show it"}}, "restored_ok": True}
    n = v.normalise_record(rec)
    assert (n["mutations"], n["detected"]) == (2, 1)
    assert n["expected_undetected"] == ["G6"] and n["unexpected_undetected"] == []
    assert n["new_tests_vs_reviewed_code"] == {"runs": 1, "failing": 1}
    assert n["mutations_vs_pre_fix_tests"] == {"runs": 1, "detected": 0}


def test_unknown_schema_raises():
    with pytest.raises(ValueError):
        v.normalise_record({"something": 1})


def test_lf_sha256_ignores_line_ending_style():
    assert v.lf_sha256("a\r\nb\r\n") == v.lf_sha256("a\nb\n") != v.lf_sha256("a\nb")


def test_evidence_freshness_on_tiny_repo(tiny_repo):
    from research.paper_h import gitlog
    first = gitlog.log(tiny_repo, "main", "--reverse")[0].sha
    text = gitlog.show_file(tiny_repo, first, "docs/record.md")
    rec = {"source_sha256": {"docs/record.md": v.lf_sha256(text), "gone.py": "0" * 64}}
    f = v.evidence_freshness(tiny_repo, rec, "main")
    assert f["match"] == 1 and f["missing"] == ["gone.py"] and f["differ"] == []
    rec["source_sha256"]["docs/record.md"] = "f" * 64
    assert v.evidence_freshness(tiny_repo, rec, "main")["differ"] == ["docs/record.md"]


def test_pooled():
    rows = [{"mutations": 10, "detected": 9, "expected_undetected": ["x"], "unexpected_undetected": [],
             "restored_green": True},
            {"mutations": 5, "detected": 4, "expected_undetected": [], "unexpected_undetected": ["y"],
             "restored_green": True}]
    p = v.pooled(rows)
    assert (p["mutations"], p["detected"], p["unexpected_undetected"]) == (15, 13, 1)
    assert p["detected_share_excluding_declared"] == round(13 / 14, 4)
