"""CAPA-015 — run the CAPA-015 tests against the code they were written for (main @ 70cc5c7) — evidence.

The tests were written before the fix (commit ecbcdad, on top of 70cc5c7). This script puts back,
temporarily, the base version of every source file CAPA-015 changed or added — tests excepted —
runs the two CAPA-015 test files, records which tests fail and why (first line), and restores the
exact bytes of the working tree.

Run from the repository root (needs backend/venv — or BACKEND_PYTHON — and frontend/node_modules).
No cloud service is contacted (GOOGLE_APPLICATION_CREDENTIALS points at a file that does not exist):
    python scripts/safety/capa015_tests_on_base.py
        -> docs/iec62304/records/risk_verification/CAPA-015_tests_on_base_2026-10-24.json
    python scripts/safety/capa015_tests_on_base.py --base 2c618ec         --label "2c618ec (PR #65 head before the independent review fixes)"         --backend-tests tests/unit/test_capa015_review_fixes.py,tests/unit/test_capa015_audit_and_session.py         --frontend-tests src/services/session.capa015.review.test.tsx         --out docs/iec62304/records/risk_verification/CAPA-015_review1_tests_on_pr65_2026-10-24.json
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


BASE = _arg("--base", "70cc5c7")
LABEL = _arg("--label", "70cc5c7 (main, Merge PR #64)")
PY = os.environ.get("BACKEND_PYTHON") or os.path.join(ROOT, "backend", "venv", "Scripts", "python.exe")
if not os.path.exists(PY):
    PY = sys.executable
OUT = _arg("--out", "docs/iec62304/records/risk_verification/CAPA-015_tests_on_base_2026-10-24.json")
BACKEND_TESTS = _arg("--backend-tests", "tests/unit/test_capa015_audit_and_session.py").split(",")
FRONTEND_TESTS = _arg("--frontend-tests", "src/services/session.capa015.test.tsx").split(",")
# PRB-002: no cloud credentials, an empty gcloud configuration and a project that does not exist.
_EMPTY_GCLOUD = os.path.join(tempfile.gettempdir(), "capa015-empty-gcloud-config")
os.makedirs(_EMPTY_GCLOUD, exist_ok=True)
NO_CLOUD = {"GOOGLE_APPLICATION_CREDENTIALS": os.path.join(tempfile.gettempdir(), "capa015-no-cloud-credentials.json"),
            "CLOUDSDK_CONFIG": _EMPTY_GCLOUD, "GOOGLE_CLOUD_PROJECT": "mstool-offline-tests",
            "AUDIT_SINK_BACKEND": "memory", "REFRESH_TOKEN_BACKEND": "memory", "COLUMNS": "400"}


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
    r = subprocess.run([PY, "-m", "pytest", *BACKEND_TESTS, "-q", "-p", "no:cacheprovider", "-o", "log_cli=false",
                        "--tb=short", "-rA"], cwd="backend", capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env={**os.environ, **NO_CLOUD})
    tests = {}
    for m in re.finditer(r"^(FAILED|ERROR|PASSED) [^:\s]+::(.+?)(?: - (.*))?$", r.stdout, re.M):
        tests[m.group(2)] = {"status": m.group(1).lower(), "reason": (m.group(3) or "")[:240]}
    p = re.search(r"(\d+) passed", r.stdout)
    f = re.search(r"(\d+) failed", r.stdout)
    e = re.search(r"(\d+) error", r.stdout)
    return {"passed": int(p.group(1)) if p else 0, "failed": int(f.group(1)) if f else 0,
            "errors": int(e.group(1)) if e else 0, "results": tests}


def run_frontend():
    out = os.path.join(tempfile.gettempdir(), "capa015_base_vitest.json")
    if os.path.exists(out):
        os.remove(out)
    subprocess.run(f"npx vitest run {' '.join(FRONTEND_TESTS)} --pool=threads --reporter=json --outputFile={out}",
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
                  "the CAPA-015 test files run unchanged, without cloud credentials; working tree restored byte for byte",
        "swapped": {"restored_to_base": CHANGED, "removed": ADDED},
        "test_sha256": {t: hashlib.sha256(open(t, encoding="utf-8").read().replace("\r\n", "\n").encode("utf-8")).hexdigest()
                        for t in ["backend/" + b for b in BACKEND_TESTS] + ["frontend/" + f for f in FRONTEND_TESTS]},
        "backend": backend,
        "frontend": frontend,
    }
    json.dump(rec, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("base: backend", backend["passed"], "passed /", backend["failed"], "failed /", backend["errors"],
          "errors | frontend", frontend["passed"], "passed /", frontend["failed"], "failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
