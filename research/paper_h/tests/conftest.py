"""Shared fixtures. Run: ``python -m pytest research/paper_h/tests -q`` from the repository root."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _git(repo, *args, env=None):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          encoding="utf-8", check=True, env=env).stdout


@pytest.fixture
def tiny_repo(tmp_path):
    """A throw-away git repository with three commits: one agent-trailered, one plain, one merge."""
    import os
    env = dict(os.environ, GIT_AUTHOR_NAME="Owner", GIT_AUTHOR_EMAIL="owner@example.org",
               GIT_COMMITTER_NAME="Owner", GIT_COMMITTER_EMAIL="owner@example.org",
               GIT_AUTHOR_DATE="2026-01-02T10:00:00+00:00", GIT_COMMITTER_DATE="2026-01-02T10:00:00+00:00")
    _git(tmp_path, "init", "-q", "-b", "main", env=env)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "record.md").write_text("The control was **verified**\nby a test that\nsent a request.\n",
                                                 encoding="utf-8")
    _git(tmp_path, "add", ".", env=env)
    _git(tmp_path, "commit", "-q", "-m", "docs: add record\n\nCo-Authored-By: Claude Opus 9 <noreply@anthropic.com>",
         env=env)
    _git(tmp_path, "checkout", "-q", "-b", "side", env=env)
    (tmp_path / "code.py").write_text("x = 1\n", encoding="utf-8")
    _git(tmp_path, "add", ".", env=env)
    env2 = dict(env, GIT_AUTHOR_DATE="2026-02-03T10:00:00+00:00", GIT_COMMITTER_DATE="2026-02-03T10:00:00+00:00")
    _git(tmp_path, "commit", "-q", "-m", "feat: plain human commit", env=env2)
    _git(tmp_path, "checkout", "-q", "main", env=env2)
    (tmp_path / "other.txt").write_text("y\n", encoding="utf-8")
    _git(tmp_path, "add", ".", env=env2)
    _git(tmp_path, "commit", "-q", "-m", "chore: other", env=env2)
    env3 = dict(env, GIT_AUTHOR_DATE="2026-02-10T10:00:00+00:00", GIT_COMMITTER_DATE="2026-02-10T10:00:00+00:00")
    _git(tmp_path, "merge", "-q", "--no-ff", "side", "-m",
         "Merge side\n\nCo-Authored-By: Claude Opus 9 <noreply@anthropic.com>", env=env3)
    return tmp_path
