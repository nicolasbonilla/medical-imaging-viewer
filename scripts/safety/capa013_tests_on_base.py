"""CAPA-013 — run the CAPA-013 tests against the code they were written for (PR #62) — evidence.

The tests were written before the fix. This script puts back, temporarily, the source files of the
base commit (PR #62, `qms/capa012-and-problem-reports` @ 2018277) for every file CAPA-013 changed or
added — tests excepted — runs the two CAPA-013 test files, records which tests fail and why
(first line), and restores the exact bytes of the working tree.

Run from the repository root (needs backend/venv or the current Python with the backend
requirements, and frontend/node_modules):
    python scripts/safety/capa013_tests_on_base.py
Output: docs/iec62304/records/risk_verification/CAPA-013_tests_on_base_2026-10-22.json
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
BASE = "2018277"
PY = os.path.join(ROOT, "backend", "venv", "Scripts", "python.exe")
if not os.path.exists(PY):
    PY = sys.executable
OUT = "docs/iec62304/records/risk_verification/CAPA-013_tests_on_base_2026-10-22.json"
BACKEND_TEST = "tests/unit/test_capa013_longitudinal_candidates.py"
FRONTEND_TEST = "src/components/LongitudinalCompare.capa013.test.tsx"

# Source files CAPA-013 changed (restored to BASE) or added (removed for the run).
CHANGED = [
    "backend/app/api/routes/ai_report.py",
    "backend/app/api/routes/segmentation_analysis.py",
    "backend/app/mcp/_backend.py",
    "backend/app/mcp/ms_clinical_server.py",
    "backend/app/services/brain_report_service.py",
    "backend/app/services/dicomweb_service.py",
    "frontend/src/api/segmentation.ts",
    "frontend/src/components/LongitudinalCompare.tsx",
    "frontend/src/i18n/locales/de.json",
    "frontend/src/i18n/locales/en.json",
    "frontend/src/i18n/locales/es.json",
    "frontend/src/types/lesion.ts",
]
ADDED = [
    "backend/app/services/longitudinal_candidate_safety.py",
    "backend/app/services/assets/longitudinal_false_candidate_evidence.json",
    "frontend/src/components/LongitudinalResultPanel.tsx",
]


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
        "base": f"{BASE} (qms/capa012-and-problem-reports, PR #62)",
        "method": "source files changed by CAPA-013 restored to the base commit, files it added removed; the "
                  "CAPA-013 test files run unchanged; working tree restored byte for byte",
        "test_sha256": {t: hashlib.sha256(open(t, encoding="utf-8").read().replace("\r\n", "\n").encode("utf-8")).hexdigest()
                        for t in ("backend/" + BACKEND_TEST, "frontend/" + FRONTEND_TEST)},
        "backend": backend,
        "frontend": frontend,
        "note": "test_rc060_assistant_cannot_record_a_decision passes on the base too: it is a regression guard "
                "(the review route must never join the assistant's compute-only list), not a defect detector.",
    }
    json.dump(rec, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("base: backend", backend["passed"], "passed /", backend["failed"], "failed /", backend["errors"],
          "errors | frontend", frontend["passed"], "passed /", frontend["failed"], "failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
