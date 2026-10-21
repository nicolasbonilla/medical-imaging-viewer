import copy

from research.paper_h import failures as f
from research.paper_h import gitlog


def _sheet(sha):
    return {"episodes": [{
        "id": "E01", "title": "t", "capa": ["CAPA-X"], "class": "S", "secondary_classes": [], "channel": "BP",
        "stage": "contained", "introduced": None, "detected": {"commit": sha}, "items": 1, "overlaps": [],
        "evidence": [{"ref": sha, "path": "docs/record.md", "quote": "verified**  by a test"},
                     {"ref": sha, "commit_message": True, "quote": "docs: add record"}],
    }], "verified_then_ineffective": {"controls": []}, "capas": []}


def test_normalise_collapses_whitespace():
    assert f.normalise("a\n  b\tc ") == "a b c"


def test_quotes_verified_against_file_and_commit_message(tiny_repo):
    sha = gitlog.log(tiny_repo, "main", "--reverse")[0].sha
    assert f.verify(_sheet(sha), tiny_repo) == []


def test_altered_quote_unknown_commit_and_bad_codes_are_reported(tiny_repo):
    sha = gitlog.log(tiny_repo, "main", "--reverse")[0].sha
    bad = copy.deepcopy(_sheet(sha))
    bad["episodes"][0]["evidence"][0]["quote"] = "verified by a test that did not send a request"
    bad["episodes"][0]["detected"]["commit"] = "0" * 40
    bad["episodes"][0]["class"] = "Z"
    bad["episodes"][0]["channel"] = "XX"
    problems = f.verify(bad, tiny_repo)
    assert any("quote not found" in p for p in problems)
    assert any("not found" in p and "detected commit" in p for p in problems)
    assert any("unknown class" in p for p in problems)
    assert any("unknown channel" in p for p in problems)


def test_summary_counts_and_latency():
    rows = [
        {"id": "E1", "class": "S", "secondary_classes": ["M"], "channel": "BP", "stage": "escaped", "items": 1,
         "overlaps": [], "introduced_commit": "a", "introduced_date": "2026-01-01", "introduced_by_agent_trailer": True,
         "detected_commit": "b", "detected_date": "2026-03-01", "detected_by_agent_trailer": True,
         "days_to_detection": 59},
        {"id": "E2", "class": "M", "secondary_classes": [], "channel": "SC", "stage": "contained", "items": 3,
         "overlaps": ["E1"], "introduced_commit": None, "introduced_date": None, "introduced_by_agent_trailer": None,
         "detected_commit": "c", "detected_date": "2026-03-02", "detected_by_agent_trailer": True,
         "days_to_detection": None},
    ]
    s = f.summarise(rows)
    assert s["episodes"] == 2 and s["episodes_without_overlap"] == 1
    assert s["items_including_multi_item_episodes"] == 4
    assert s["by_class"]["S"] == 1 and s["by_class_including_secondary"]["M"] == 2
    assert s["by_stage"] == {"escaped": 1, "contained": 1}
    assert s["days_to_detection_by_stage"]["escaped"]["median"] == 59
    assert s["days_to_detection_by_stage"]["contained"]["n"] == 0
    assert s["introduced_by_agent_trailer"] == 1 and s["detected_by_owner"] == 0


def test_first_parent_landing_and_stage_rules(tiny_repo):
    cs = gitlog.log(tiny_repo, "main", "--first-parent", "--reverse")
    side = [c for c in gitlog.log(tiny_repo, "side") if c.subject == "feat: plain human commit"][0]
    merge = cs[-1]
    assert f.first_parent_landing(tiny_repo, side.sha, "main") == merge.sha
    assert f.first_parent_landing(tiny_repo, cs[0].sha, "main") == cs[0].sha
