"""CAPA-003 PA-3.1: every backend test directory that holds test files is run by a pytest command in a CI workflow.

CAPA-001 root cause #4 and CAPA-003: ``tests/security/`` existed for months and was never executed, so nothing could
contradict it. The same check found ``tests/services/`` (51 tests) never run by CI. A new, unreferenced test directory
now fails the unit-test step. Only pytest command lines count: a directory named in a YAML comment is not "run".
"""
import os
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TESTS = REPO / "backend" / "tests"
WORKFLOWS = REPO / ".github" / "workflows"


def _pytest_command_lines():
    lines = []
    for wf in sorted(WORKFLOWS.glob("*.y*ml")):
        for line in wf.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("#"):  # a comment never runs anything
                continue
            if "pytest" in line:
                lines.append(line)
    return lines


def _test_directories():
    return sorted({p.relative_to(TESTS).parts[0] for p in TESTS.rglob("test_*.py") if p.parent != TESTS})


@pytest.fixture(autouse=True)
def _repository_layout():
    if not WORKFLOWS.is_dir():
        if os.environ.get("GITHUB_ACTIONS") == "true":
            pytest.fail("the CI workflows are not where this check expects them: the guard would be blind")
        pytest.skip("repository layout not present (packaged backend); CI always runs this check")


def test_every_test_directory_is_run_by_a_ci_pytest_command():
    commands = "\n".join(_pytest_command_lines())
    dirs = _test_directories()
    assert dirs, "no test directory found: the check would pass vacuously"
    assert commands, "no pytest command found in the workflows: the check would fail every directory"
    missing = [d for d in dirs if not re.search(rf"tests/{re.escape(d)}(/|\s|\"|'|$)", commands, re.M)]
    assert not missing, f"test directories never run by a CI pytest command: {missing}"


def test_a_directory_named_only_in_a_comment_does_not_count(tmp_path, monkeypatch):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text("# tests/security/ is run below\n      - run: python -m pytest tests/unit/\n",
                               encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "WORKFLOWS", wf)
    text = "\n".join(_pytest_command_lines())
    assert "tests/unit/" in text and "tests/security/" not in text


def test_no_test_file_sits_outside_a_directory():
    loose = sorted(p.name for p in TESTS.glob("test_*.py"))
    assert not loose, f"test files directly under backend/tests/ are not covered by the directory check: {loose}"
