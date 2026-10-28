"""PRB-004 .. PRB-009 (viewer display and orientation) — run the new tests against the code they were
written for (`main` @ 70cc5c7) — evidence that each test detects its defect.

The tests were written before the fixes. This script puts back, temporarily, the base version of every
source file the fixes changed or added (tests and test helpers excepted), runs the PRB test files, records
which tests fail and why (first line), and restores the exact bytes of the working tree (also on Ctrl-C /
SIGTERM / SIGBREAK, and at exit).

Run from the repository root (needs backend/venv or the current Python with the backend requirements, and
frontend/node_modules):
    python scripts/safety/prb004_tests_on_base.py
        -> docs/iec62304/records/risk_verification/PRB-004_tests_on_base_2026-10-28.json
Refuses to start if a file it would swap has uncommitted changes (it restores what it read).
NEVER run this while anything else edits the files it swaps.
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


BASE = _arg("--base", "70cc5c7")
LABEL = _arg("--label", "70cc5c7 (main, merge of PR #64)")
OUT = _arg("--out", "docs/iec62304/records/risk_verification/PRB-004_tests_on_base_2026-10-28.json")
PY = os.path.join(ROOT, "backend", "venv", "Scripts", "python.exe")
if not os.path.exists(PY):
    PY = sys.executable
BACKEND_TESTS = ["tests/unit/test_prb006_mask_display_range.py"]
FRONTEND_TESTS = [
    "src/components/NiivueViewer2D.prb004.test.tsx",
    "src/components/ImageViewer3D.prb005.test.tsx",
    "src/ViewerApp.prb007.test.tsx",
    "src/utils/sequenceDetection.prb007.test.ts",
    "src/utils/sliceOnOpen.test.ts",
    "src/utils/niivueWindowLevel.test.ts",
    "src/components/QuickScreenBadge.prb009.test.tsx",
    "src/config/features.quickScreen.test.ts",
]


def _is_test(path):
    return ("/tests/" in path or ".test." in path or "__tests__" in path
            or path.startswith("frontend/src/test/"))


def source_files():
    """(changed, added): source files that differ from BASE — put back at their BASE version, or removed."""
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


def offline_env():
    """PRB-002: backend tests never reach a real cloud service or the model provider."""
    env = dict(os.environ)
    empty = tempfile.mkdtemp(prefix="prb004-no-gcloud-")
    env.update({"GOOGLE_APPLICATION_CREDENTIALS": os.path.join(empty, "no-such-credentials.json"),
                "CLOUDSDK_CONFIG": empty, "GOOGLE_CLOUD_PROJECT": "mstool-offline-tests", "COLUMNS": "400"})
    env.pop("ANTHROPIC_API_KEY", None)
    return env


def run_backend():
    r = subprocess.run([PY, "-m", "pytest", *BACKEND_TESTS, "-q", "-p", "no:cacheprovider", "-o", "log_cli=false",
                        "--tb=short", "-rA"], cwd="backend", capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=offline_env())
    tests = {}
    for m in re.finditer(r"^(FAILED|ERROR|PASSED) [^:\s]+::(.+?)(?: - (.*))?$", r.stdout, re.M):
        tests[m.group(2)] = {"status": m.group(1).lower(), "reason": (m.group(3) or "")[:240]}
    def count(word):
        m = re.search(rf"(\d+) {word}", r.stdout)
        return int(m.group(1)) if m else 0

    return {"passed": count("passed"), "failed": count("failed"), "errors": count("error"), "results": tests}


def run_frontend():
    out = os.path.join(tempfile.gettempdir(), "prb004_base_vitest.json")
    if os.path.exists(out):
        os.remove(out)
    subprocess.run("npx vitest run " + " ".join(FRONTEND_TESTS) + f" --pool=threads --reporter=json --outputFile={out}",
                   cwd="frontend", shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    d = json.load(open(out, encoding="utf-8"))
    files = {}
    for f in d["testResults"]:
        name = "frontend" + f["name"].replace("\\", "/").split("/frontend")[-1]
        res = f["assertionResults"]
        files[name] = {
            "passed": sum(a["status"] == "passed" for a in res),
            "failed": sum(a["status"] == "failed" for a in res),
            "file_error": (f.get("message") or "").split("\n")[0][:240] if f["status"] == "failed" and not res else "",
            "not_passing": {a["title"]: (a.get("failureMessages") or [""])[0].split("\n")[0][:240]
                            for a in res if a["status"] != "passed"},
            "passing": [a["title"] for a in res if a["status"] == "passed"],
        }
    return files


def main():
    changed, added = source_files()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", *changed, *added],
                           capture_output=True, text=True).stdout
    if dirty.strip():
        raise SystemExit(f"uncommitted changes in {dirty.split()}: commit them first (the script restores the bytes)")
    snapshot = {p: open(p, "rb").read() for p in changed + added}

    def restore():
        for p, b in snapshot.items():
            with open(p, "wb") as fh:
                fh.write(b)

    def on_signal(signum, _frame):
        restore()
        raise SystemExit(f"interrupted by signal {signum}; working tree restored")

    atexit.register(restore)
    for sig in ("SIGINT", "SIGTERM", "SIGBREAK", "SIGHUP"):
        if hasattr(signal, sig):
            signal.signal(getattr(signal, sig), on_signal)
    try:
        for p in changed:
            with open(p, "wb") as fh:
                fh.write(base_bytes(p))
        for p in added:
            os.remove(p)
        backend, frontend = run_backend(), run_frontend()
    finally:
        restore()
    for p, b in snapshot.items():
        assert open(p, "rb").read() == b, p
    tests = [f"backend/{t}" for t in BACKEND_TESTS] + [f"frontend/{t}" for t in FRONTEND_TESTS]
    rec = {
        "executed": datetime.datetime.now().isoformat(timespec="seconds"),
        "base": LABEL,
        "method": "source files that differ from the base commit restored to it, files it did not have removed "
                  "(tests and frontend/src/test helpers kept); the PRB-004..009 test files run unchanged; working "
                  "tree restored byte for byte",
        "swapped": {"restored_to_base": changed, "removed": added},
        "test_sha256": {t: hashlib.sha256(open(t, encoding="utf-8").read().replace("\r\n", "\n").encode("utf-8")).hexdigest()
                        for t in tests},
        "backend": backend,
        "frontend": frontend,
        "note": _arg("--note", "Tests that pass on the base are guards (stated in their names: 'guard', 'harness pin') "
                               "or check behaviour the base already had; a file whose module did not exist on the base "
                               "fails as a whole (file_error)."),
    }
    json.dump(rec, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    fp = sum(v["passed"] for v in frontend.values())
    ff = sum(v["failed"] for v in frontend.values())
    fe = sum(1 for v in frontend.values() if v["file_error"])
    print("base: backend", backend["passed"], "passed /", backend["failed"], "failed /", backend["errors"],
          "errors | frontend", fp, "passed /", ff, "failed /", fe, "files failing to load ->", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
