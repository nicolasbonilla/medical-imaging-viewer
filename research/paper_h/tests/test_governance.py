from research.paper_h import gitlog, governance, snapshot_github


def _c(subject, merge=False, agent=True, committer="local"):
    return gitlog.Commit(sha="f" * 40, parents=("a", "b") if merge else ("a",), date="2026-10-17",
                         committer=committer, subject=subject,
                         coauthors=("Claude Opus 5.5 <noreply@anthropic.com>",) if agent else (), body="")


def test_approval_commits_match_only_recording_subjects():
    cs = [_c("docs(iec62304): record human approval of CAPA-006 (PR #43)"),
          _c("Merge main (PR #46 approval) into CAPA-009; record human approval of CAPA-009 (PR #47)", merge=True),
          _c("fix: approve nothing here")]
    hits = governance.approval_commits(cs)
    assert len(hits) == 2 and all(h["agent_trailer"] for h in hits)


def test_merge_summary_splits_github_and_local():
    cs = [_c("Merge PR #1", merge=True, agent=False, committer="GitHub"),
          _c("Merge PR #2", merge=True, agent=True, committer="local"),
          _c("feat: x")]
    m = governance.merge_summary(cs)
    assert (m["merges"], m["via_github"], m["local"], m["local_with_agent_trailer"]) == (2, 1, 1, 1)


def test_reduce_pr_flags_without_body_or_email():
    pr = {"number": 51, "title": "t", "state": "OPEN", "isDraft": True, "createdAt": "2026-10-17T10:00:00Z",
          "mergedAt": None, "headRefName": "x", "reviews": [], "comments": [], "mergedBy": None,
          "body": "**Approval**: PENDING owner approval\n... re-review 2 (\"do not merge yet\")\n"
                  "Class C\n🤖 Generated with [Claude Code](https://claude.com/claude-code)"}
    r = snapshot_github.reduce_pr(pr)
    assert r["body_states_owner_approval_pending"] and r["body_reports_review_verdict_blocking"]
    assert r["body_mentions_class_c"] and r["body_has_claude_code_footer"]
    assert "body" not in r and r["formal_reviews"] == 0


def test_pr_summary():
    snap = {"retrieved_utc": "2026-10-21T00:00:00Z", "pull_requests": [
        {"number": 1, "state": "MERGED", "is_draft": False, "formal_reviews": 0, "merged_by": "owner",
         "body_has_claude_code_footer": True, "body_states_owner_approval_pending": False,
         "body_reports_review_verdict_blocking": False},
        {"number": 2, "state": "OPEN", "is_draft": True, "formal_reviews": 1, "merged_by": None,
         "body_has_claude_code_footer": True, "body_states_owner_approval_pending": True,
         "body_reports_review_verdict_blocking": True}]}
    s = governance.pr_summary(snap)
    assert s["merged"] == 1 and s["open_draft"] == 1 and s["formal_reviews_total"] == 1
    assert s["open_stating_owner_approval_pending"] == [2] and s["merged_by"] == {"owner": 1}
