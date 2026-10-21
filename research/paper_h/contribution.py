"""RQ1 — extent of the agent's contribution (PROTOCOL.md §5, metrics 1-5).

    python research/paper_h/contribution.py        # prints the RQ1 block as JSON
"""
from __future__ import annotations

import json
import sys
from collections import Counter, OrderedDict
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.paper_h import config, gitlog  # noqa: E402


def share(part: int, whole: int) -> float | None:
    return None if whole == 0 else round(part / whole, 4)


def commit_counts(commits: list[gitlog.Commit]) -> dict:
    nm = [c for c in commits if not c.is_merge]
    return {
        "all": {"total": len(commits), "agent": sum(c.is_agent for c in commits),
                "share": share(sum(c.is_agent for c in commits), len(commits))},
        "non_merge": {"total": len(nm), "agent": sum(c.is_agent for c in nm),
                      "share": share(sum(c.is_agent for c in nm), len(nm))},
        "merges": {"total": len(commits) - len(nm),
                   "agent": sum(c.is_agent for c in commits if c.is_merge)},
        "claude_code_footer": sum("Generated with [Claude Code]" in c.body for c in commits),
        "first_commit_date": min(c.date for c in commits) if commits else None,
        "last_commit_date": max(c.date for c in commits) if commits else None,
    }


def monthly(commits: list[gitlog.Commit]) -> "OrderedDict[str, dict]":
    out: "OrderedDict[str, dict]" = OrderedDict()
    for month in sorted({c.month for c in commits}):
        cs = [c for c in commits if c.month == month]
        agent = sum(c.is_agent for c in cs)
        out[month] = {"total": len(cs), "agent": agent, "other": len(cs) - agent,
                      "share": share(agent, len(cs))}
    return out


def models(commits: list[gitlog.Commit]) -> dict[str, int]:
    counts = Counter(gitlog.model_label(c.agent_trailer) for c in commits if c.is_agent)
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def model_first_last(commits: list[gitlog.Commit]) -> dict[str, dict]:
    spans: dict[str, dict] = {}
    for c in commits:
        if not c.is_agent:
            continue
        m = gitlog.model_label(c.agent_trailer)
        s = spans.setdefault(m, {"first": c.date, "last": c.date})
        s["first"], s["last"] = min(s["first"], c.date), max(s["last"], c.date)
    return dict(sorted(spans.items(), key=lambda kv: kv[1]["first"]))


def lines(commits: list[gitlog.Commit], stats: dict) -> dict:
    """Lines added/deleted in text files by non-merge commits, split by trailer status.

    The initial import (the repository's first commit) is reported separately because it
    is one commit of ~70 k lines and would dominate any share.
    """
    root = min((c for c in commits if not c.parents), key=lambda c: c.date, default=None)
    acc = {k: {"commits": 0, "added": 0, "deleted": 0} for k in ("agent", "other")}
    acc_no_root = {k: {"commits": 0, "added": 0, "deleted": 0} for k in ("agent", "other")}
    for c in commits:
        if c.is_merge or c.sha not in stats:
            continue
        key = "agent" if c.is_agent else "other"
        a = sum(r[0] for r in stats[c.sha] if r[0] is not None)
        d = sum(r[1] for r in stats[c.sha] if r[1] is not None)
        for bucket in ([acc] if (root and c.sha == root.sha) else [acc, acc_no_root]):
            bucket[key]["commits"] += 1
            bucket[key]["added"] += a
            bucket[key]["deleted"] += d
    tot = acc["agent"]["added"] + acc["other"]["added"]
    tot_nr = acc_no_root["agent"]["added"] + acc_no_root["other"]["added"]
    return {
        "including_initial_commit": {**acc, "agent_share_of_added": share(acc["agent"]["added"], tot)},
        "excluding_initial_commit": {**acc_no_root,
                                     "agent_share_of_added": share(acc_no_root["agent"]["added"], tot_nr)},
        "initial_commit": None if root is None else {
            "sha": root.sha[:7], "date": root.date, "agent_trailer": root.is_agent,
            "added": sum(r[0] for r in stats.get(root.sha, []) if r[0] is not None),
            "files": len(stats.get(root.sha, [])),
        },
    }


def touching(commits: list[gitlog.Commit], stats: dict, prefixes) -> dict:
    hits = [c for c in commits if not c.is_merge and c.sha in stats and gitlog.touched(stats[c.sha], prefixes)]
    agent = sum(c.is_agent for c in hits)
    return {"commits": len(hits), "agent": agent, "share": share(agent, len(hits))}


def per_class_c_module(commits: list[gitlog.Commit], stats: dict) -> dict:
    return {m: touching(commits, stats, (m,)) for m in config.CLASS_C_MODULES}


def file_authorship(repo, ref: str, path: str) -> dict:
    """Which commits added / changed one file, with their trailer status."""
    cs = gitlog.log(repo, ref, "--follow", "--", path)
    created = cs[-1] if cs else None
    return {
        "path": path,
        "created_by_commit": None if created is None else created.sha[:7],
        "created_on": None if created is None else created.date,
        "creating_commit_agent_trailer": None if created is None else created.agent_trailer,
        "commits": [{"sha": c.sha[:7], "date": c.date, "agent": c.is_agent, "subject": c.subject} for c in cs],
    }


def compute(repo=None, ref_key: str = "main") -> dict:
    repo = repo or config.repo_root()
    ref = config.REFS[ref_key]
    commits = gitlog.log(repo, ref)
    stats = gitlog.numstat(repo, ref)
    return {
        "ref": ref,
        "commits": commit_counts(commits),
        "monthly": monthly(commits),
        "models": models(commits),
        "model_spans": model_first_last(commits),
        "lines": lines(commits, stats),
        "controlled_documents": touching(commits, stats, config.CONTROLLED_DOC_PREFIXES),
        "class_c_modules_any": touching(commits, stats, config.CLASS_C_MODULES),
        "class_c_modules": per_class_c_module(commits, stats),
        "withdrawn_verification_record": file_authorship(repo, ref, config.RCV_2026_04_12),
    }


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2, ensure_ascii=False))
