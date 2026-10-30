"""PRB-020 .. PRB-026 — run the final tests against the code they were written for (`main` @ 70cc5c7) — evidence.

The tests were written before the fix (failing first). This script puts back, temporarily, the source files of the
base commit for every source file this branch changed or added — tests excepted — runs the PRB test files, records
which tests fail and why (first line), and restores the exact bytes of the working tree, also on exit and on
signals. It refuses to start when those source files have uncommitted changes.

Run from the repository root (needs backend/venv or the current Python with the backend requirements, and
frontend/node_modules):
    python scripts/safety/prb020_tests_on_base.py
        -> docs/iec62304/records/risk_verification/PRB-020_tests_on_base_2026-10-28.json
The backend tests run with no cloud credential (PRB-002): a missing credentials file, an empty gcloud
configuration folder, an offline project id and no model-provider key.
"""
import atexit
import datetime
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.chdir(ROOT)


def _arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


# Defaults: the first run on main @ 70cc5c7. The review of PR #70 re-run uses
#   --base 7de9334 --label "7de9334 (PR #70 head before the review fixes)"
#   --out docs/iec62304/records/risk_verification/PRB-020_review1_tests_on_7de9334_2026-10-28.json
#   --backend tests/unit/test_prb020_review1_findings.py,tests/unit/test_prb021_backfill_creator_care_team.py
#   --frontend src/pages/PatientsPage.prb021.test.tsx,src/pages/LoginPage.prb022.review1.test.tsx
#   --paths backend/app,frontend/src,scripts/owner
BASE = _arg("--base", "70cc5c7")
LABEL = _arg("--label", "70cc5c7 (main, merge of PR #64)")
PY = os.path.join(ROOT, "backend", "venv", "Scripts", "python.exe")
if not os.path.exists(PY):
    PY = sys.executable
OUT = _arg("--out", "docs/iec62304/records/risk_verification/PRB-020_tests_on_base_2026-10-28.json")
BACKEND_TESTS = _arg("--backend", "tests/unit/test_prb020_self_registration_and_accounts.py,"
                                  "tests/unit/test_prb021_patient_scope_creator_counts.py").split(",")
FRONTEND_TESTS = _arg("--frontend", "src/pages/LoginPage.prb020.test.tsx,src/components/StudyCard.prb025.test.tsx,"
                                    "src/components/patientInitials.prb026.test.tsx,"
                                    "src/hooks/useSegmentationData.prb026.test.tsx,"
                                    "src/components/i18nStrings.prb026.test.tsx").split(",")
PATHS = _arg("--paths", "backend/app,frontend/src").split(",")


def offline_env(tmp):
    env = dict(os.environ)
    for name in ("ANTHROPIC_API_KEY", "FIRESTORE_EMULATOR_HOST"):
        env.pop(name, None)
    env.update({"GOOGLE_APPLICATION_CREDENTIALS": os.path.join(tmp, "no-such-credentials.json"),
                "CLOUDSDK_CONFIG": os.path.join(tmp, "empty-gcloud"), "GOOGLE_CLOUD_PROJECT": "mstool-offline-tests",
                "COLUMNS": "400"})
    os.makedirs(env["CLOUDSDK_CONFIG"], exist_ok=True)
    return env


def _is_test(path):
    return "/tests/" in path or ".test." in path or "__tests__" in path


def source_files():
    names = subprocess.run(["git", "diff", "--name-only", BASE, "--", *PATHS],
                           capture_output=True, text=True, check=True).stdout.split()
    names += subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "--", *PATHS],
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


def run_backend(env):
    r = subprocess.run([PY, "-m", "pytest", *BACKEND_TESTS, "-q", "-p", "no:cacheprovider", "-o", "log_cli=false",
                        "--tb=short", "-rA"], cwd="backend", capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env, timeout=1200)
    tests = {}
    for m in re.finditer(r"^(FAILED|ERROR|PASSED) [^:\s]+::(.+?)(?: - (.*))?$", r.stdout, re.M):
        tests[m.group(2)] = {"status": m.group(1).lower(), "reason": (m.group(3) or "")[:240]}
    p = re.search(r"(\d+) passed", r.stdout)
    f = re.search(r"(\d+) failed", r.stdout)
    e = re.search(r"(\d+) error", r.stdout)
    return {"passed": int(p.group(1)) if p else 0, "failed": int(f.group(1)) if f else 0,
            "errors": int(e.group(1)) if e else 0, "results": tests}


def run_frontend():
    out = os.path.join(tempfile.gettempdir(), "prb020_base_vitest.json")
    if os.path.exists(out):
        os.remove(out)
    subprocess.run(f"npx vitest run {' '.join(FRONTEND_TESTS)} --pool=threads --reporter=json --outputFile={out}",
                   cwd="frontend", shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace",
                   timeout=1200)
    d = json.load(open(out, encoding="utf-8"))
    res = [a for f in d["testResults"] for a in f["assertionResults"]]
    return {"passed": sum(a["status"] == "passed" for a in res),
            "failed": sum(a["status"] == "failed" for a in res),
            "file_errors": [f["name"].split("frontend")[-1] for f in d["testResults"]
                            if f["status"] == "failed" and not f["assertionResults"]],
            "not_passing": {a["title"]: {"status": a["status"],
                                         "reason": (a.get("failureMessages") or [""])[0].split("\n")[0][:240]}
                            for a in res if a["status"] != "passed"}}


SNAPSHOT = {}


def _restore():
    for p, b in SNAPSHOT.items():
        if not os.path.exists(p) or open(p, "rb").read() != b:
            open(p, "wb").write(b)


def _on_signal(signum, _frame):
    _restore()
    raise SystemExit(f"interrupted by signal {signum}; working tree restored")


def main():
    changed, added = source_files()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", *changed, *added], capture_output=True,
                           text=True).stdout
    if dirty.strip():
        raise SystemExit(f"uncommitted changes in {dirty.split()}: commit them first (the script restores bytes)")
    SNAPSHOT.update({p: open(p, "rb").read() for p in changed + added})
    atexit.register(_restore)
    for sig in ("SIGTERM", "SIGBREAK", "SIGHUP"):
        if hasattr(signal, sig):
            signal.signal(getattr(signal, sig), _on_signal)
    with tempfile.TemporaryDirectory() as tmp:
        try:
            for p in changed:
                open(p, "wb").write(base_bytes(p))
            for p in added:
                os.remove(p)
            backend, frontend = run_backend(offline_env(tmp)), run_frontend()
        finally:
            _restore()
    for p, b in SNAPSHOT.items():
        assert open(p, "rb").read() == b, p
    rec = {
        "executed": datetime.datetime.now().isoformat(timespec="seconds"),
        "base": LABEL,
        "tree": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
        "method": "source files that differ from the base commit restored to it, files it did not have removed; "
                  "the PRB test files run unchanged; working tree restored byte for byte",
        "swapped": {"restored_to_base": changed, "removed": added},
        "test_sha256": {t: hashlib.sha256(open(t, encoding="utf-8").read().replace("\r\n", "\n").encode("utf-8")).hexdigest()
                        for t in [*("backend/" + b for b in BACKEND_TESTS), *("frontend/" + f for f in FRONTEND_TESTS)]},
        "backend": backend,
        "frontend": frontend,
        "note": _arg("--note", None) or "Tests that pass on the base are positive controls of behaviour that must not change (an "
                "administrator lists every patient; an administrator who creates a patient is not put on a care team; "
                "a client cannot set the segmentation creator; self-registration works when explicitly enabled outside "
                "production; the Register tab appears when the server says it is on; SEGM. 0 shown when the server "
                "reports 0). Every other test fails on the base.",
    }
    json.dump(rec, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("base: backend", backend["passed"], "passed /", backend["failed"], "failed /", backend["errors"],
          "errors | frontend", frontend["passed"], "passed /", frontend["failed"], "failed", frontend["file_errors"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
