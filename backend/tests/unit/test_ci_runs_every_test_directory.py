"""CAPA-003 PA-3.1: every backend test directory that holds test files is run by at least one CI workflow step.

CAPA-001 root cause #4 and CAPA-003: ``tests/security/`` existed for months and was never executed, so nothing could
contradict it. The same check found ``tests/services/`` (51 tests) never run by CI. A new, unreferenced test directory
now fails the unit-test step.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TESTS = REPO / "backend" / "tests"
WORKFLOWS = REPO / ".github" / "workflows"


def _test_directories():
    return sorted({p.relative_to(TESTS).parts[0] for p in TESTS.rglob("test_*.py") if p.parent != TESTS})


def _workflow_text():
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(WORKFLOWS.glob("*.y*ml")))


def test_every_test_directory_is_run_by_ci():
    text = _workflow_text()
    dirs = _test_directories()
    assert dirs, "no test directory found: the check would pass vacuously"
    missing = [d for d in dirs if not re.search(rf"tests/{re.escape(d)}(/|\s|\"|'|$)", text, re.M)]
    assert not missing, f"test directories never run by any CI workflow step: {missing}"


def test_no_test_file_sits_outside_a_directory():
    loose = sorted(p.name for p in TESTS.glob("test_*.py"))
    assert not loose, f"test files directly under backend/tests/ are not covered by the directory check: {loose}"
