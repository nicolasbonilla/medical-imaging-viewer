"""Read-only snapshot of GitHub pull-request metadata WITH descriptions (manuscript update, 2026-10-31).

    python research/paper_h/snapshot_github_full.py   # needs an authenticated `gh`; writes data/github_prs_full_<date>.json

Only ``gh pr list`` and ``gh api .../commits/<sha>`` (reads) are called. The repository is public, so
the PR descriptions are already public; they are stored so that the manuscript's counts can be
re-derived offline. Two redactions are applied before writing (see REDACT_TOKEN_SHA256): the name and the
project identifier of an unrelated product of the owner, which appear in one PR description as test
data of a project allow-list. No e-mail address is stored.

The commit-verification block records, for the owner sign-off commits, what GitHub reports about the
signature (``verification.verified`` / ``reason``) — the evidence that those commits were made in the
GitHub web interface (signed by GitHub's web-flow key) and not in the agent's local session.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.paper_h import config  # noqa: E402

FIELDS = ("number,title,state,isDraft,createdAt,mergedAt,closedAt,headRefName,baseRefName,"
          "reviews,comments,mergedBy,body,additions,deletions,changedFiles,mergeCommit")

#: SHA-256 of the lower-cased tokens to redact (an unrelated product of the owner and its cloud project
#: identifier, which appear in one PR description as test data of a project allow-list). Stored as hashes so
#: that the names themselves are not repeated in the paper's files.
REDACT_TOKEN_SHA256 = frozenset({
    "53f16999d772bc17039ba3f22e0eaecedcf82661942e116ae3e38c933c01173c",
    "edfd430f5339370d6ec51d0f89a607b14efa58d3af74743f8c646965fdb11a72",
})
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*")

#: Commits whose GitHub verification status is recorded (owner sign-offs and the merges that carry them).
VERIFY_COMMITS = ("5561999", "c1d0e04", "042d50b", "8832dae", "cc7b692", "ca600c2", "0830b38", "8805882",
                  "70cc5c7")


def _redact(s: str) -> str:
    def rep(m: re.Match) -> str:
        tok = m.group(0)
        return "[unrelated-project]" if hashlib.sha256(tok.lower().encode()).hexdigest() in REDACT_TOKEN_SHA256 else tok
    return _TOKEN.sub(rep, s)


def _reduce(pr: dict) -> dict:
    return {
        "number": pr["number"],
        "title": _redact(pr["title"]),
        "state": pr["state"],
        "is_draft": pr["isDraft"],
        "created": pr["createdAt"],
        "merged": pr.get("mergedAt"),
        "closed": pr.get("closedAt"),
        "head": pr["headRefName"],
        "base": pr["baseRefName"],
        "merge_commit": (pr.get("mergeCommit") or {}).get("oid"),
        "merged_by": (pr.get("mergedBy") or {}).get("login"),
        "formal_reviews": [{"state": r.get("state"), "author": (r.get("author") or {}).get("login")}
                           for r in (pr.get("reviews") or [])],
        "comments": [{"author": (c.get("author") or {}).get("login"), "created": c.get("createdAt"),
                      "body": _redact(c.get("body") or "")} for c in (pr.get("comments") or [])],
        "additions": pr.get("additions"),
        "deletions": pr.get("deletions"),
        "changed_files": pr.get("changedFiles"),
        "body": _redact(pr.get("body") or ""),
    }


def _verification(repo: Path, sha: str) -> dict:
    full = subprocess.run(["git", "-C", str(repo), "rev-parse", sha], capture_output=True, text=True,
                          check=True).stdout.strip()
    out = subprocess.run(["gh", "api", f"repos/nicolasbonilla/medical-imaging-viewer/commits/{full}",
                          "--jq", "{sha: .sha, committer: .commit.committer.name, author: .commit.author.name,"
                                  " message: .commit.message, verified: .commit.verification.verified,"
                                  " reason: .commit.verification.reason}"],
                         capture_output=True, text=True, encoding="utf-8", cwd=str(repo), check=True)
    d = json.loads(out.stdout)
    d["message"] = _redact(d["message"])
    return d


def _gh_json(repo: Path, args: list[str]):
    out = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", cwd=str(repo), check=True)
    return json.loads(out.stdout) if out.stdout.strip() else None


def _ci(repo: Path, numbers: list[int]) -> dict:
    """CI runs of the repository's only workflow, and the check roll-up on each PR's last head (reads only)."""
    runs = _gh_json(repo, ["run", "list", "--limit", "1000", "--json",
                           "databaseId,workflowName,event,headBranch,headSha,status,conclusion,createdAt"]) or []
    checks = []
    for n in numbers:
        d = _gh_json(repo, ["pr", "view", str(n), "--json", "number,headRefOid,statusCheckRollup"])
        checks.append({"number": d["number"], "head": d["headRefOid"],
                       "checks": [{"name": c.get("name"), "conclusion": c.get("conclusion"),
                                   "completed": c.get("completedAt")} for c in d.get("statusCheckRollup") or []]})
    return {"runs": [{k: (_redact(v) if isinstance(v, str) else v) for k, v in r.items()} for r in runs],
            "pr_head_checks": checks}


def _protection(repo: Path) -> dict:
    """``main`` branch protection and repository rulesets as GitHub reports them (reads only)."""
    out = subprocess.run(["gh", "api", "repos/nicolasbonilla/medical-imaging-viewer/branches/main/protection"],
                         capture_output=True, text=True, encoding="utf-8", cwd=str(repo))
    rules = subprocess.run(["gh", "api", "repos/nicolasbonilla/medical-imaging-viewer/rulesets"],
                           capture_output=True, text=True, encoding="utf-8", cwd=str(repo))
    return {"protection_exit_code": out.returncode, "protection_response": out.stdout.strip()[:300],
            "rulesets_response": rules.stdout.strip()[:300]}


def snapshot(repo=None) -> dict:
    repo = repo or config.repo_root()
    out = subprocess.run(["gh", "pr", "list", "--state", "all", "--limit", "500", "--json", FIELDS],
                         capture_output=True, text=True, encoding="utf-8", cwd=str(repo), check=True)
    prs = sorted((_reduce(p) for p in json.loads(out.stdout)), key=lambda p: p["number"])
    return {
        "retrieved_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "command": "gh pr list --state all --limit 500 --json " + FIELDS,
        "redactions": "tokens whose SHA-256 is in REDACT_TOKEN_SHA256 -> [unrelated-project]",
        "commit_verification": [_verification(repo, s) for s in VERIFY_COMMITS],
        "pull_requests": prs,
        "ci": _ci(repo, [p["number"] for p in prs]),
        "branch_protection_main": _protection(repo),
    }


if __name__ == "__main__":
    data = snapshot()
    day = data["retrieved_utc"][:10]
    path = config.DATA_DIR / f"github_prs_full_{day}.json"
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path} ({len(data['pull_requests'])} PRs)")
