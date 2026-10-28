"""A throwaway git worktree for the PRB-004 safety scripts (review of PR #71, m8).

The negative-control run and the tests-on-base run change source files while they run. Run in the developer's own
checkout, an interrupted run (a killed process, a closed terminal, a stopped tool) can leave a mutation behind in
real code. They therefore run in a separate, detached worktree of the commit under test, created for the run and
removed after it:

- the worktree is created under the system temporary folder, named with PREFIX, at a commit (HEAD by default);
- `frontend/node_modules` in it is a directory JUNCTION to the repository's node_modules (no install, nothing
  copied). A junction is removed with `os.rmdir`, which removes the link only — never recursively: a recursive
  delete through the junction would delete the shared node_modules;
- leftovers of earlier interrupted runs (registered worktrees named with PREFIX) are cleaned the same way first.

Only worktrees whose folder name starts with PREFIX are ever touched.
"""
import contextlib
import os
import shutil
import stat
import subprocess
import tempfile
import time

PREFIX = "prb004-safety-run-"


def _git(root, *args, check=True):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=check)


def _is_junction(path):
    if hasattr(os.path, "isjunction") and os.path.isjunction(path):
        return True
    try:
        st = os.lstat(path)
    except OSError:
        return False
    return bool(getattr(st, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)) \
        or os.path.islink(path)


def _unlink_node_modules(worktree):
    link = os.path.join(worktree, "frontend", "node_modules")
    if os.path.lexists(link):
        if not _is_junction(link):
            raise RuntimeError(f"{link} is not a junction: refusing to delete it")
        os.rmdir(link)                      # removes the link only
        if os.path.lexists(link):
            raise RuntimeError(f"junction {link} still present")


def _remove(root, worktree):
    _unlink_node_modules(worktree)
    _git(root, "worktree", "remove", "--force", worktree, check=False)
    if os.path.isdir(worktree):             # not registered any more: nothing linked inside, plain delete
        assert not os.path.lexists(os.path.join(worktree, "frontend", "node_modules"))
        shutil.rmtree(worktree, ignore_errors=True)
    _git(root, "worktree", "prune", check=False)


def clean_stale(root):
    """Remove worktrees left by interrupted earlier runs (only those named with PREFIX)."""
    listing = _git(root, "worktree", "list", "--porcelain").stdout
    paths = [ln.split(" ", 1)[1].strip() for ln in listing.splitlines() if ln.startswith("worktree ")]
    stale = [p for p in paths if os.path.basename(os.path.normpath(p)).startswith(PREFIX)]
    for p in stale:
        _remove(root, os.path.normpath(p))
    return stale


@contextlib.contextmanager
def throwaway_worktree(root, rev="HEAD"):
    """Yield the path of a detached worktree of `rev` with node_modules linked; removed afterwards."""
    stale = clean_stale(root)
    sha = _git(root, "rev-parse", rev).stdout.strip()
    path = os.path.join(tempfile.gettempdir(), f"{PREFIX}{os.getpid()}-{int(time.time())}")
    _git(root, "worktree", "add", "--detach", path, sha)
    try:
        target = os.path.realpath(os.path.join(root, "frontend", "node_modules"))
        if not os.path.isdir(target):
            raise RuntimeError(f"no frontend/node_modules at {target}")
        link = os.path.join(path, "frontend", "node_modules")
        subprocess.run(["cmd", "/c", "mklink", "/J", link, target], capture_output=True, check=True)
        yield {"path": path, "sha": sha, "stale_removed": stale}
    finally:
        _remove(root, path)


def require_committed(root, paths):
    """The run uses the commit, not the working tree: refuse when a file it covers has uncommitted changes."""
    dirty = _git(root, "status", "--porcelain", "--", *paths).stdout
    if dirty.strip():
        raise SystemExit(f"uncommitted changes in {dirty.split()}: commit them first (the run uses the commit, "
                         "in a throwaway worktree)")
