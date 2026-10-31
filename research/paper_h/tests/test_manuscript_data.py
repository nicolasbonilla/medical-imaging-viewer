"""Parsers of the manuscript update on synthetic input, plus the headline numbers at the pinned ref."""
from __future__ import annotations

import json

import pytest

from research.paper_h import config, manuscript_data as md


def test_nc_record_dict_format_counts_declared_equivalents():
    rec = {"executed": "2026-10-30T11:28:43",
           "mutations": {"A": {"failed": 2}, "B": {"failed": 0}, "C": {"failed": 1}},
           "expected_undetected": {"B": "equivalent: ..."}, "undetected": ["B"], "unexpected_undetected": []}
    r = md.parse_nc_record(rec)
    assert (r["mutations"], r["detected"], r["declared_equivalent"], r["unexpected_undetected"]) == (3, 2, 1, [])


def test_nc_record_list_format_uses_per_mutation_flags():
    rec = {"generated": "2026-10-30", "mutations": [{"name": "M1", "detected": True},
                                                   {"name": "M2", "detected": False}],
           "summary": {"mutations": 2, "detected": 1, "undetected": ["M2"]}}
    r = md.parse_nc_record(rec)
    assert (r["mutations"], r["detected"], r["unexpected_undetected"]) == (2, 1, ["M2"])


def test_nc_record_summary_string_format():
    rec = {"record": "x", "dates": ["2026-10-17"], "script": "s", "restored_ok": True, "results": [],
           "summary": {"mutations_detected": "45/46", "not_detected": ["G6"],
                       "not_detected_explained": {"G6": "not detectable with phantoms"}}}
    r = md.parse_nc_record(rec)
    assert (r["mutations"], r["detected"], r["declared_equivalent"], r["unexpected_undetected"]) == (46, 45, 1, [])


@pytest.mark.parametrize("line, kind", [
    ("| Approved By | PENDING owner approval |", "approval placeholder"),
    ("the agent writes `PENDING owner approval` and never writes an approval line", "name of the marker (procedure text or quotation)"),
    ("No Class C module changed. **PENDING owner approval and code review.**", "conjoined with a review (\"... and code review\")"),
    ("Every approval field still reads PENDING owner approval here", "statement about the pre-sign-off state"),
])
def test_replacement_kind(line, kind):
    assert md._replacement_kind(line, line.index(md.MARKER)) == kind


def test_headline_numbers_reproduce():
    """Re-derives the numbers the manuscript states (needs the pinned commits; ~5 min)."""
    data = md.compute()
    assert data["problems"] == []
    c = data["contribution"]["commits"]
    assert (c["all"]["total"], c["all"]["agent"]) == (595, 525)
    nc = data["negative_controls"]
    assert nc["release_2026_10_30_first_run"]["totals"]["mutations"] == 772
    assert nc["release_2026_10_30_final"]["totals"] == {"mutations": 873, "detected": 868,
                                                        "declared_equivalent": 5, "unexpected_undetected": 0}
    assert nc["history"]["runs_with_unexpected_survivor"] == []
    a = data["approvals"]
    assert a["lines_at_draft"]["by_writer"] == {"agent-trailered commit": 31}
    assert a["lines_at_final"]["lines"] == 489
    assert data["reviews"]["total_findings"] == 189
    stored = json.loads((config.OUT_DIR / "manuscript_data.json").read_text(encoding="utf-8"))
    assert stored["reviews"]["total"] == data["reviews"]["total"]
