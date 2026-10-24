"""Negative controls for PRB-002 — the backend test suite must never reach a real external service.

Each mutation removes or weakens ONE layer of the guard in backend/tests/conftest.py (or re-introduces
a defect the independent review found), in the real source, one at a time. The script asserts every anchor occurs exactly once (the sabotage really was
applied), runs tests/unit/test_prb002_no_cloud_in_tests.py, records the failing test names and
restores the exact original bytes.

Safety of the controls themselves: every run gets an outer environment that already hides real
credentials (a credentials file and a gcloud config folder that do not exist, a project name that is
not a real project, and a storage key-file setting pointing at nothing). These outer values differ
from the ones conftest forces, so a removed layer is visible to the tests, but no run can ever find
real credentials. The base without any guard is deliberately NOT run: on a machine with gcloud
application-default credentials it writes to the production user store, which is the defect.

Run from the repository root:
    python scripts/safety/prb002_negative_controls.py
Output: docs/iec62304/records/risk_verification/PRB-002_negative_controls_2026-10-24.json
NEVER run this while anything else edits backend/tests/conftest.py (it restores a snapshot).
"""
import datetime
import hashlib
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.chdir(ROOT)
PY = os.path.join(ROOT, "backend", "venv", "Scripts", "python.exe")
if not os.path.exists(PY):
    PY = sys.executable
OUT = "docs/iec62304/records/risk_verification/PRB-002_negative_controls_2026-10-24.json"
TESTS = ["tests/unit/test_prb002_no_cloud_in_tests.py"]
CONF = "backend/tests/conftest.py"

GUARD_FN = (
    "    _refuse_real_credentials.prb002_guard = True\n"
    "    google.auth.default = _refuse_real_credentials\n"
    "    google.auth._default.default = _refuse_real_credentials\n"
)
REFUSE_FN = (
    "    def _refuse_real_credentials(*_args, **_kwargs):\n"
    "        raise DefaultCredentialsError(\n"
)
MUTATIONS = [
    ("M1_credentials_path_not_forced",
     "os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(_NO_CLOUD_DIR / 'no-credentials.json')\n", ""),
    ("M2_credentials_path_setdefault_only",
     "os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(_NO_CLOUD_DIR / 'no-credentials.json')\n",
     "os.environ.setdefault('GOOGLE_APPLICATION_CREDENTIALS', str(_NO_CLOUD_DIR / 'no-credentials.json'))\n"),
    ("M3_storage_key_file_not_emptied",
     "os.environ['GCS_CREDENTIALS_FILE'] = ''  # a .env cannot point the storage service at a key file\n", ""),
    ("M4_gcloud_config_not_redirected",
     "os.environ['CLOUDSDK_CONFIG'] = str(_NO_CLOUD_DIR / 'gcloud')\n", ""),
    ("M5_project_not_forced",
     "os.environ['GOOGLE_CLOUD_PROJECT'] = OFFLINE_PROJECT_ID\n", ""),
    ("M6_legacy_project_variable_kept",
     "    'GCLOUD_PROJECT', 'ANTHROPIC_API_KEY',", "    'ANTHROPIC_API_KEY',"),
    ("M7_credentials_guard_not_installed",
     "\n_install_no_cloud_guard()\n", "\n"),
    ("M8_only_public_default_patched",
     GUARD_FN,
     "    _refuse_real_credentials.prb002_guard = True\n"
     "    google.auth.default = _refuse_real_credentials\n"),
    ("M9_emulator_variable_unlocks_anonymous_credentials",   # the first version of this PR (review finding 1)
     REFUSE_FN,
     "    def _refuse_real_credentials(*_args, **_kwargs):\n"
     "        if os.environ.get('FIRESTORE_EMULATOR_HOST', '').split(':')[0] in ('localhost', '127.0.0.1'):\n"
     "            from google.auth.credentials import AnonymousCredentials\n"
     "            return AnonymousCredentials(), OFFLINE_PROJECT_ID\n"
     "        raise DefaultCredentialsError(\n"),
    ("M10_app_imported_before_guard",                       # review finding 2 (ordering)
     "PRB002_APP_IMPORTED_BEFORE_GUARD = ",
     "import app.main  # noqa: F401\nPRB002_APP_IMPORTED_BEFORE_GUARD = "),
    ("M11_other_service_variables_kept",
     "for _name in PRB002_REMOVED_VARIABLES:\n    os.environ.pop(_name, None)\n", ""),
    ("M12_socket_guard_not_installed",
     "    socket.socket.connect, socket.socket.connect_ex = _connect, _connect_ex\n", ""),
    ("M13_socket_guard_allows_any_host",
     "        if host.lower() == 'localhost':\n            return True\n",
     "        return True\n"),
]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def outer_env(tmp):
    env = dict(os.environ)
    env.update({
        "GOOGLE_APPLICATION_CREDENTIALS": os.path.join(tmp, "outer-none.json"),
        "CLOUDSDK_CONFIG": os.path.join(tmp, "outer-gcloud"),
        "GOOGLE_CLOUD_PROJECT": "outer-not-a-project",
        "GCLOUD_PROJECT": "outer-not-a-project",
        "GCS_CREDENTIALS_FILE": os.path.join(tmp, "outer-key.json"),
        "ANTHROPIC_API_KEY": "outer-dummy-not-a-key",
        "FLAMES_ENDPOINT": "http://outer.invalid",
    })
    env.pop("FIRESTORE_EMULATOR_HOST", None)
    return env


def run_tests(env, tmp):
    report = os.path.join(tmp, "junit.xml")
    p = subprocess.run(
        [PY, "-m", "pytest", *TESTS, "-q", "-p", "no:cacheprovider", f"--junitxml={report}"],
        cwd=os.path.join(ROOT, "backend"), env=env, capture_output=True, text=True, timeout=900)
    failed = []
    if os.path.exists(report):
        import xml.etree.ElementTree as ET
        for case in ET.parse(report).getroot().iter("testcase"):
            if case.find("failure") is not None or case.find("error") is not None:
                failed.append(case.get("name"))
    return p.returncode, failed, p.stdout[-1500:]


def main():
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", CONF]).returncode != 0:
        raise SystemExit(f"{CONF} has uncommitted changes: commit them first (the script restores HEAD bytes)")
    original = open(CONF, "rb").read()

    def _restore_and_exit(signum, _frame):
        open(CONF, "wb").write(original)
        raise SystemExit(f"interrupted by signal {signum}; {CONF} restored")

    import signal
    for sig in ("SIGTERM", "SIGBREAK", "SIGHUP"):
        if hasattr(signal, sig):
            signal.signal(getattr(signal, sig), _restore_and_exit)
    text = original.decode("utf-8")
    results = {"generated": datetime.datetime.now().isoformat(timespec="seconds"),
               "tests": {t: sha(os.path.join("backend", t)) for t in TESTS},
               "conftest_sha256": sha(CONF), "baseline": None, "mutations": []}
    with tempfile.TemporaryDirectory() as tmp:
        env = outer_env(tmp)
        code, failed, tail = run_tests(env, tmp)
        results["baseline"] = {"exit": code, "failed": failed}
        print(f"baseline (guard intact)            exit {code} failed {failed}")
        if code != 0:
            print(tail)
            raise SystemExit("baseline must pass before mutations mean anything")
        try:
            for name, anchor, replacement in MUTATIONS:
                count = text.count(anchor)
                assert count == 1, (name, count)
                open(CONF, "wb").write(text.replace(anchor, replacement).encode("utf-8"))
                code, failed, _ = run_tests(env, tmp)
                detected = code != 0 and bool(failed)
                results["mutations"].append({
                    "name": name, "executed": datetime.datetime.now().isoformat(timespec="seconds"),
                    "exit": code, "failed_tests": failed, "detected": detected})
                print(f"{name:36s} exit {code} detected={detected} {failed}")
                open(CONF, "wb").write(original)
        finally:
            open(CONF, "wb").write(original)
    assert open(CONF, "rb").read() == original, "conftest not restored"
    undetected = [m["name"] for m in results["mutations"] if not m["detected"]]
    results["summary"] = {"mutations": len(MUTATIONS), "detected": len(MUTATIONS) - len(undetected),
                          "undetected": undetected}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(results, open(OUT, "w", encoding="utf-8"), indent=1)
    print(f"restored; {results['summary']['detected']}/{len(MUTATIONS)} detected -> {OUT}")
    return 1 if undetected else 0


if __name__ == "__main__":
    sys.exit(main())
