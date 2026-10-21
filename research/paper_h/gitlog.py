"""Read-only access to git history, with parsers that are testable on plain text.

Only ``git log``, ``git show``, ``git cat-file`` and ``git rev-parse`` are used. No e-mail
address is ever returned: author and committer are reduced to a name, and the committer is
reduced further to "GitHub" (a merge or edit made through github.com) or "local".
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

RS, US, GS = "\x1e", "\x1f", "\x1d"   # record, unit and group separators

# One record per commit. The body is last because it is free text; it never contains
# the ASCII separators.
LOG_FORMAT = (
    "%x1e%H%x1f%P%x1f%ad%x1f%cn%x1f%s%x1f"
    "%(trailers:key=Co-Authored-By,valueonly,separator=%x1d)%x1f%B"
)


@dataclass(frozen=True)
class Commit:
    sha: str
    parents: tuple[str, ...]
    date: str                      # author date, YYYY-MM-DD (author's own time zone)
    committer: str                 # "GitHub" or "local"
    subject: str
    coauthors: tuple[str, ...]
    body: str = field(repr=False)

    @property
    def is_merge(self) -> bool:
        return len(self.parents) > 1

    @property
    def month(self) -> str:
        return self.date[:7]

    @property
    def agent_trailer(self) -> str | None:
        """The first Co-Authored-By value that names Claude / Anthropic, else None."""
        for value in self.coauthors:
            if is_agent_coauthor(value):
                return value
        return None

    @property
    def is_agent(self) -> bool:
        return self.agent_trailer is not None


def is_agent_coauthor(value: str) -> bool:
    v = value.strip().lower()
    return "noreply@anthropic.com" in v or v.startswith("claude")


def model_label(trailer: str) -> str:
    """'Claude Opus 4.8 (1M context) <noreply@anthropic.com>' -> 'Claude Opus 4.8 (1M context)'."""
    return trailer.split("<", 1)[0].strip()


def git(repo: Path | str, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout


def parse_log(text: str) -> list[Commit]:
    commits = []
    for chunk in text.split(RS):
        if not chunk.strip():
            continue
        parts = chunk.split(US)
        if len(parts) < 7:
            raise ValueError(f"malformed log record: {chunk[:80]!r}")
        sha, parents, date, cname, subject, trailers, body = parts[:7]
        commits.append(Commit(
            sha=sha.strip(),
            parents=tuple(p for p in parents.split() if p),
            date=date.strip(),
            committer="GitHub" if cname.strip() == "GitHub" else "local",
            subject=subject.strip(),
            coauthors=tuple(t.strip() for t in trailers.split(GS) if t.strip()),
            body=body,
        ))
    return commits


def log(repo: Path | str, ref: str, *extra: str) -> list[Commit]:
    return parse_log(git(repo, "log", ref, "--date=short", "--format=" + LOG_FORMAT, *extra))


def show_commit(repo: Path | str, sha: str) -> Commit:
    commits = parse_log(git(repo, "show", "-s", "--date=short", "--format=" + LOG_FORMAT, sha))
    if len(commits) != 1:
        raise ValueError(f"expected one commit for {sha}")
    return commits[0]


def commit_exists(repo: Path | str, sha: str) -> bool:
    out = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", f"{sha}^{{commit}}"],
        capture_output=True, text=True,
    )
    return out.returncode == 0


def parse_numstat(text: str) -> dict[str, list[tuple[int | None, int | None, str]]]:
    """Parse ``git log --numstat --format=<RS>%H`` output -> {sha: [(added, deleted, path)]}.

    Binary files ("-\t-\tpath") give (None, None, path).
    """
    result: dict[str, list[tuple[int | None, int | None, str]]] = {}
    for chunk in text.split(RS):
        lines = [ln for ln in chunk.splitlines() if ln.strip()]
        if not lines:
            continue
        sha, rows = lines[0].strip(), []
        for ln in lines[1:]:
            a, d, path = ln.split("\t", 2)
            rows.append((None if a == "-" else int(a), None if d == "-" else int(d), path))
        result[sha] = rows
    return result


def numstat(repo: Path | str, ref: str) -> dict[str, list[tuple[int | None, int | None, str]]]:
    """Per non-merge commit, the files it changed. Renames are reported at the new path."""
    text = git(repo, "log", ref, "--no-merges", "--numstat", "--no-renames", "--format=%x1e%H")
    return parse_numstat(text)


def show_file(repo: Path | str, ref: str, path: str) -> str:
    return git(repo, "show", f"{ref}:{path}")


def touched(rows: Iterable[tuple[int | None, int | None, str]], prefixes: Iterable[str]) -> bool:
    prefixes = tuple(prefixes)
    return any(path.startswith(prefixes) or path in prefixes for _, _, path in rows)
