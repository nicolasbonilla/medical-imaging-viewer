"""Read-only snapshot of GitHub pull-request metadata (data source D7).

    python research/paper_h/snapshot_github.py     # needs an authenticated `gh`; writes data/github_prs_snapshot.json

Only ``gh pr list`` (a read) is called. The snapshot keeps derived flags, not PR bodies, and
no e-mail address. Re-running it later gives a newer snapshot; the committed one is what
RESULTS.md cites (its retrieval time is stored inside).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.paper_h import config  # noqa: E402

FIELDS = "number,title,state,isDraft,createdAt,mergedAt,headRefName,reviews,comments,mergedBy,body"

PENDING = re.compile(r"PENDING owner approval|owner approval[^.\n]{0,40}PENDING|Owner must approve|"
                     r"Do not merge or deploy without owner approval|DRAFT\s*[—-]+\s*do not merge", re.I)
REVIEW_BLOCK = re.compile(r"do not (approve|merge) yet", re.I)
CLASS_C_FLAG = re.compile(r"Class C", re.I)


def reduce_pr(pr: dict) -> dict:
    body = pr.get("body") or ""
    return {
        "number": pr["number"],
        "title": pr["title"],
        "state": pr["state"],
        "is_draft": pr["isDraft"],
        "created": pr["createdAt"][:10],
        "merged": (pr.get("mergedAt") or "")[:10] or None,
        "head": pr["headRefName"],
        "formal_reviews": len(pr.get("reviews") or []),
        "review_states": sorted({r.get("state") for r in (pr.get("reviews") or [])}),
        "comments": len(pr.get("comments") or []),
        "merged_by": (pr.get("mergedBy") or {}).get("login"),
        "body_states_owner_approval_pending": bool(PENDING.search(body)),
        "body_reports_review_verdict_blocking": bool(REVIEW_BLOCK.search(body)),
        "body_mentions_class_c": bool(CLASS_C_FLAG.search(body)),
        "body_has_claude_code_footer": "Generated with [Claude Code]" in body,
    }


def snapshot(repo=None) -> dict:
    repo = repo or config.repo_root()
    out = subprocess.run(["gh", "pr", "list", "--state", "all", "--limit", "500", "--json", FIELDS],
                         capture_output=True, text=True, encoding="utf-8", cwd=str(repo), check=True)
    prs = sorted((reduce_pr(p) for p in json.loads(out.stdout)), key=lambda p: p["number"])
    return {"retrieved_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "command": "gh pr list --state all --limit 500 --json " + FIELDS,
            "pull_requests": prs}


if __name__ == "__main__":
    data = snapshot()
    path = config.DATA_DIR / "github_prs_snapshot.json"
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path} ({len(data['pull_requests'])} PRs)")
