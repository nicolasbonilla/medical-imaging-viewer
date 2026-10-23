"""CAPA-013 — run the CAPA-013 tests against the code they were written for (PR #62) — evidence.

The tests were written before the fix. This script puts back, temporarily, the source files of the
base commit (PR #62, `qms/capa012-and-problem-reports` @ 2018277) for every file CAPA-013 changed or
added — tests excepted — runs the two CAPA-013 test files, records which tests fail and why
(first line), and restores the exact bytes of the working tree.

Run from the repository root (needs backend/venv or the current Python with the backend
requirements, and frontend/node_modules):
    python scripts/safety/capa013_tests_on_base.py
        -> PR #62 (2018277); docs/iec62304/records/risk_verification/CAPA-013_tests_on_base_2026-10-22.json
    python scripts/safety/capa013_tests_on_base.py --base ad144ba \
        --out docs/iec62304/records/risk_verification/CAPA-013_review1_tests_on_pr63_2026-10-23.json \
        --label "ad144ba (PR #63 head before the independent review fixes)"
The source files (backend/app, frontend/src; tests excepted) that differ from the base commit are
taken from git: put back at their base version, or removed when the base did not have them.
NEVER run this while anything else edits the files it swaps (it restores a snapshot).
"""
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.chdir(ROOT)
def _arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


BASE = _arg("--base", "2018277")
LABEL = _arg("--label", "2018277 (qms/capa012-and-problem-reports, PR #62)")
PY = os.path.join(ROOT, "backend", "venv", "Scripts", "python.exe")
if not os.path.exists(PY):
    PY = sys.executable
OUT = _arg("--out", "docs/iec62304/records/risk_verification/CAPA-013_tests_on_base_2026-10-22.json")
BACKEND_TEST = "tests/unit/test_capa013_longitudinal_candidates.py"
FRONTEND_TEST = "src/components/LongitudinalCompare.capa013.test.tsx"

def _is_test(path):
    return "/tests/" in path or ".test." in path or "__tests__" in path


def source_files():
    """(changed, added): source files that differ from BASE — at their BASE version, or new since."""
    names = subprocess.run(["git", "diff", "--name-only", BASE, "--", "backend/app", "frontend/src"],
                           capture_output=True, text=True, check=True).stdout.split()
    names += subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "--", "backend/app", "frontend/src"],
                            capture_output=True, text=True, check=True).stdout.split()
    changed, added = [], []
    for n in sorted(set(names)):
        if _is_test(n) or not os.path.exists(n):
            continue
        in_base = subprocess.run(["git", "cat-file", "-e", f"{BASE}:{n}"], capture_output=True).returncode == 0
        (changed if in_base else added).append(n)
    return changed, added


def base_bytes(path):
    return subprocess.run(["git", "show", f"{BASE}:{path}"], capture_output=True, check=True).stdout


def run_backend():
    r = subprocess.run([PY, "-m", "pytest", BACKEND_TEST, "-q", "-p", "no:cacheprovider", "-o", "log_cli=false",
                        "--tb=short", "-rA"], cwd="backend", capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env={**os.environ, "COLUMNS": "400"})
    tests = {}
    for m in re.finditer(r"^(FAILED|ERROR|PASSED) [^:\s]+::(.+?)(?: - (.*))?$", r.stdout, re.M):
        tests[m.group(2)] = {"status": m.group(1).lower(), "reason": (m.group(3) or "")[:240]}
    p = re.search(r"(\d+) passed", r.stdout)
    f = re.search(r"(\d+) failed", r.stdout)
    e = re.search(r"(\d+) error", r.stdout)
    return {"passed": int(p.group(1)) if p else 0, "failed": int(f.group(1)) if f else 0,
            "errors": int(e.group(1)) if e else 0, "results": tests}


def run_frontend():
    out = os.path.join(tempfile.gettempdir(), "capa013_base_vitest.json")
    if os.path.exists(out):
        os.remove(out)
    subprocess.run(f"npx vitest run {FRONTEND_TEST} --pool=threads --reporter=json --outputFile={out}",
                   cwd="frontend", shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    d = json.load(open(out, encoding="utf-8"))
    res = [a for f in d["testResults"] for a in f["assertionResults"]]
    return {"passed": sum(a["status"] == "passed" for a in res),
            "failed": sum(a["status"] == "failed" for a in res),
            "not_passing": {a["title"]: {"status": a["status"],
                                         "reason": (a.get("failureMessages") or [""])[0].split("\n")[0][:240]}
                            for a in res if a["status"] != "passed"}}


def main():
    CHANGED, ADDED = source_files()
    snapshot = {p: open(p, "rb").read() for p in CHANGED + ADDED}
    try:
        for p in CHANGED:
            open(p, "wb").write(base_bytes(p))
        for p in ADDED:
            os.remove(p)
        backend, frontend = run_backend(), run_frontend()
    finally:
        for p, b in snapshot.items():
            open(p, "wb").write(b)
    for p, b in snapshot.items():
        assert open(p, "rb").read() == b, p
    rec = {
        "executed": datetime.datetime.now().isoformat(timespec="seconds"),
        "base": LABEL,
        "method": "source files that differ from the base commit restored to it, files it did not have removed; "
                  "the CAPA-013 test files run unchanged; working tree restored byte for byte",
        "swapped": {"restored_to_base": CHANGED, "removed": ADDED},
        "test_sha256": {t: hashlib.sha256(open(t, encoding="utf-8").read().replace("\r\n", "\n").encode("utf-8")).hexdigest()
                        for t in ("backend/" + BACKEND_TEST, "frontend/" + FRONTEND_TEST)},
        "backend": backend,
        "frontend": frontend,
        "note": _arg("--note", "test_rc060_assistant_cannot_record_a_decision passes on the base too: it is a "
                               "regression guard (the review route must never join the assistant's compute-only "
                               "list), not a defect detector."),
    }
    json.dump(rec, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("base: backend", backend["passed"], "passed /", backend["failed"], "failed /", backend["errors"],
          "errors | frontend", frontend["passed"], "passed /", frontend["failed"], "failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
