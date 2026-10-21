"""RQ4 — the human-approval boundary (PROTOCOL.md §5, metrics 13-16).

    python research/paper_h/governance.py          # prints the RQ4 block as JSON

Metric 16 (harness permission decisions) is qualitative and comes from operator notes outside
the repository; it is reported in RESULTS.md as such and is not computed here.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.paper_h import config, gitlog  # noqa: E402

APPROVAL_SUBJECT = re.compile(r"record (?:the )?(?:human )?approval|record human approval", re.I)
APPROVAL_TEXT = re.compile(r"Approved by N\. G\. Bonilla Vargas", re.I)


def approval_commits(commits: list[gitlog.Commit]) -> list[dict]:
    hits = [c for c in commits if APPROVAL_SUBJECT.search(c.subject)]
    return [{"sha": c.sha[:7], "date": c.date, "agent_trailer": c.is_agent,
             "merge": c.is_merge, "subject": c.subject} for c in sorted(hits, key=lambda c: c.date)]


def merge_summary(commits: list[gitlog.Commit]) -> dict:
    merges = [c for c in commits if c.is_merge]
    return {
        "merges": len(merges),
        "via_github": sum(c.committer == "GitHub" for c in merges),
        "local": sum(c.committer == "local" for c in merges),
        "local_with_agent_trailer": sum(c.committer == "local" and c.is_agent for c in merges),
        "local_with_agent_trailer_subjects": [c.subject for c in merges if c.committer == "local" and c.is_agent],
    }


def approval_statements(repo, ref: str) -> dict:
    """Occurrences of the owner's approval sentence in the CAPA records and register at ``ref``."""
    paths = [p for p in gitlog.git(repo, "ls-tree", "-r", "--name-only", ref,
                                   "--", "docs/iec62304/records/").split() if p.endswith(".md")]
    counts = {}
    for p in paths:
        n = len(APPROVAL_TEXT.findall(gitlog.show_file(repo, ref, p)))
        if n:
            counts[p] = n
    return {"files": counts, "total": sum(counts.values())}


def approval_lines_authorship(repo, ref: str) -> dict:
    """Every line of a controlled document that records the owner's approval, and the trailer
    status of the commit that last wrote it (``git blame``)."""
    out = gitlog.git(repo, "grep", "-n", "-i", "-E", r"Bonilla Vargas.{0,80}approv|approv.{0,80}Bonilla Vargas",
                     ref, "--", *config.CONTROLLED_DOC_PREFIXES)
    rows, cache = [], {}
    for line in out.splitlines():
        _, path, lineno, _text = line.split(":", 3)
        blame = gitlog.git(repo, "blame", "--porcelain", "-L", f"{lineno},{lineno}", ref, "--", path)
        sha = blame.split()[0]
        if sha not in cache:
            cache[sha] = gitlog.show_commit(repo, sha)
        c = cache[sha]
        rows.append({"path": path, "line": int(lineno), "written_by": c.sha[:7], "date": c.date,
                     "agent_trailer": c.is_agent})
    return {
        "lines": len(rows),
        "documents": len({r["path"] for r in rows}),
        "written_by_agent_trailered_commits": sum(r["agent_trailer"] for r in rows),
        "writing_commits": sorted({r["written_by"] for r in rows}),
        "rows": rows,
    }


def pr_summary(snapshot: dict) -> dict:
    prs = snapshot["pull_requests"]
    merged = [p for p in prs if p["state"] == "MERGED"]
    open_ = [p for p in prs if p["state"] == "OPEN"]
    return {
        "retrieved_utc": snapshot["retrieved_utc"],
        "pull_requests": len(prs),
        "merged": len(merged),
        "open": len(open_),
        "open_draft": sum(p["is_draft"] for p in open_),
        "formal_reviews_total": sum(p["formal_reviews"] for p in prs),
        "prs_with_any_formal_review": sum(p["formal_reviews"] > 0 for p in prs),
        "merged_by": dict(Counter(p["merged_by"] for p in merged)),
        "agent_footer_in_body": sum(p["body_has_claude_code_footer"] for p in prs),
        "open_stating_owner_approval_pending": [p["number"] for p in open_ if p["body_states_owner_approval_pending"]],
        "open_reporting_blocking_review_verdict": [p["number"] for p in open_ if p["body_reports_review_verdict_blocking"]],
    }


def compute(repo=None) -> dict:
    repo = repo or config.repo_root()
    commits = gitlog.log(repo, config.REFS["main"])
    snap = json.loads((config.DATA_DIR / "github_prs_snapshot.json").read_text(encoding="utf-8"))
    return {
        "approval_recording_commits": approval_commits(commits),
        "approval_statements_in_records_main": approval_statements(repo, config.REFS["main"]),
        "approval_lines_in_controlled_documents_main": approval_lines_authorship(repo, config.REFS["main"]),
        "merges_on_main": merge_summary(commits),
        "github": pr_summary(snap),
    }


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2, ensure_ascii=False))
