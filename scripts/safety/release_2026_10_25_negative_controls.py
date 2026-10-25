"""Negative controls for the release integration of 2026-10-25 (PRs #66, #65, #67, #68).

The four PRs keep their own negative-control scripts (prb002_, capa015_, capa014_, prb003_negative_controls.py);
they are re-run on the integrated tree. This script covers only the decisions taken AT the integration, which none
of those scripts can see (docs/iec62304/records/releases/RELEASE-2026-10-25_integration_notes.md):

  I1/I1b  PRB-003's output check runs on the model's text only, before CAPA-014's draft assembly (merge notes of
          #67 and #68) — re-introduced: the check also, or only, runs on the assembled draft;
  I2      the template variant is chosen on the DIS block of the RC-064 payload (RC-064 amended);
  I3      #68's confirmation route is a recorded clinical action in CAPA-015's ROUTE_ACTIONS;
  I4-I6   conftest forces CAPA-015's in-memory backends and lifetimes after the PRB-002 guard (never setdefault).

Method (as the other scripts): one mutation at a time in the real source; every anchor asserted to occur exactly
once; only the bound backend tests are run, offline (PRB-002: a credentials file and a gcloud configuration folder
that do not exist, an offline project id, no model-provider key); the exact original bytes are restored after each
mutation and verified at the end. The outer environment also sets AUDIT_SINK_BACKEND / REFRESH_TOKEN_BACKEND to
"firestore" and the access-token lifetime to 60 minutes, so a conftest that stops forcing its values is visible;
the baseline must pass with that same environment.

Run from the repository root (nothing else may edit these files meanwhile):
    python scripts/safety/release_2026_10_25_negative_controls.py
Output: docs/iec62304/records/releases/RELEASE-2026-10-25_integration_negative_controls.json
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
PY = os.path.join(ROOT, "backend", "venv", "Scripts", "python.exe")
if not os.path.exists(PY):
    PY = sys.executable
OUT = "docs/iec62304/records/releases/RELEASE-2026-10-25_integration_negative_controls.json"

AIR = "backend/app/api/routes/ai_report.py"
BRS = "backend/app/services/brain_report_service.py"
AMW = "backend/app/core/logging/audit_middleware.py"
CONF = "backend/tests/conftest.py"

REL = "tests/unit/test_release_2026_10_25_integration.py"
CAPA015 = "tests/unit/test_capa015_audit_and_session.py"

ASSEMBLED = '        result = {**result, **parts, "content": draft_text(parts, request.language)}\n'
SCRUB = '            content, replaced = gate.scrub_unevaluated_dis(result["content"], request.language)\n'

# name: ([(file, anchor, replacement), ...], bound backend tests (pytest node selection), what it re-introduces)
M = {
    "I1_check_also_runs_on_the_assembled_draft": (
        [(AIR, ASSEMBLED, ASSEMBLED + "        if not dis_evaluated:\n"
                                      "            result[\"content\"] = gate.scrub_unevaluated_dis(result[\"content\"], "
                                      "request.language)[0]\n")],
        [REL + "::test_rc070_release_i1_the_dis_check_changes_the_model_text_never_the_clinicians_entry"],
        "PRB-003's output check also rewrites the assembled draft, including the clinician's typed entry"),
    "I1b_check_moved_after_the_draft_assembly": (
        [(AIR, SCRUB, '            content, replaced = result["content"], 0\n'),
         (AIR, ASSEMBLED, ASSEMBLED + "        if not dis_evaluated:\n"
                                      "            result[\"content\"], replaced = gate.scrub_unevaluated_dis("
                                      "result[\"content\"], request.language)\n")],
        [REL + "::test_rc070_release_i1_the_dis_check_changes_the_model_text_never_the_clinicians_entry"],
        "the output check runs after the draft assembly instead of before it (merge notes of #67 and #68)"),
    "I2_template_variant_chosen_on_the_raw_findings": (
        [(BRS, '        dis_block = payload.findings.get("dis_assessment")\n',
          '        dis_block = findings.get("dis_assessment")\n')],
        [REL + "::test_rc064_release_i2_the_template_variant_follows_the_dis_block_the_model_receives"],
        "the template asks for a DIS table while the payload sends the DIS as not evaluated"),
    "I3_dis_confirmation_route_not_audited": (
        [(AMW, '    ("POST", "/api/v1/segmentation/{segmentation_id}/review/confirm"): '
               '(E.CLINICAL_SEGMENTATION_CONFIRM, "segmentation"),\n', "")],
        [CAPA015 + "::test_rc067_prb003_dis_confirmation_is_a_recorded_clinical_action"],
        "#68's radiologist confirmation is not recorded as a clinical action (CAPA-015 + PRB-003)"),
    "I4_audit_backend_not_forced": (
        [(CONF, "os.environ['AUDIT_SINK_BACKEND'] = 'memory'\n",
          "os.environ.setdefault('AUDIT_SINK_BACKEND', 'memory')\n")],
        [REL + "::test_release_c1_conftest_forces_the_capa015_test_settings"],
        "a developer's environment selects the Firestore audit backend in the test suite (CAPA-015's setdefault)"),
    "I5_refresh_backend_not_forced": (
        [(CONF, "os.environ['REFRESH_TOKEN_BACKEND'] = 'memory'\n",
          "os.environ.setdefault('REFRESH_TOKEN_BACKEND', 'memory')\n")],
        [REL + "::test_release_c1_conftest_forces_the_capa015_test_settings"],
        "a developer's environment selects the Firestore refresh-token store in the test suite"),
    "I6_access_lifetime_not_forced": (
        [(CONF, "os.environ['JWT_ACCESS_TOKEN_EXPIRE_MINUTES'] = '15'\n",
          "os.environ.setdefault('JWT_ACCESS_TOKEN_EXPIRE_MINUTES', '15')\n")],
        [REL + "::test_release_c1_conftest_forces_the_capa015_test_settings"],
        "an old 60-minute access-token setting reaches the test suite (the start-up check refuses it)"),
}
BOUND = sorted({t.split("::")[0] for _e, tests, _w in M.values() for t in tests})


def outer_env(tmp):
    env = dict(os.environ)
    for name in ("ANTHROPIC_API_KEY", "FIRESTORE_EMULATOR_HOST"):
        env.pop(name, None)
    env.update({
        "GOOGLE_APPLICATION_CREDENTIALS": os.path.join(tmp, "no-credentials.json"),
        "CLOUDSDK_CONFIG": os.path.join(tmp, "empty-gcloud"),
        "GOOGLE_CLOUD_PROJECT": "mstool-offline-tests",
        "AUDIT_SINK_BACKEND": "firestore",
        "REFRESH_TOKEN_BACKEND": "firestore",
        "JWT_ACCESS_TOKEN_EXPIRE_MINUTES": "60",
    })
    os.makedirs(env["CLOUDSDK_CONFIG"], exist_ok=True)
    return env


def run(tests, env):
    r = subprocess.run([PY, "-m", "pytest", *tests, "-q", "-p", "no:cacheprovider", "-o", "log_cli=false"],
                       cwd="backend", capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
                       timeout=900)
    f = re.search(r"(\d+) failed", r.stdout)
    p = re.search(r"(\d+) passed", r.stdout)
    e = re.search(r"(\d+) error", r.stdout)
    return {"exit": r.returncode, "failed": int(f.group(1)) if f else 0, "passed": int(p.group(1)) if p else 0,
            "errors": int(e.group(1)) if e else 0,
            "failing_tests": sorted(set(re.findall(r"(?:FAILED|ERROR) \S+::(\S+)", r.stdout)))}


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main():
    files = sorted({e[0] for edits, _t, _w in M.values() for e in edits})
    dirty = subprocess.run(["git", "status", "--porcelain", "--", *files], capture_output=True, text=True).stdout
    if dirty.strip():
        raise SystemExit(f"uncommitted changes in {dirty.split()}: commit them first (the script restores the bytes)")
    raw = {p: open(p, "rb").read() for p in files}
    text = {p: b.decode("utf-8").replace("\r\n", "\n") for p, b in raw.items()}
    eol = {p: "\r\n" if b"\r\n" in b else "\n" for p, b in raw.items()}
    for name, (edits, _t, _w) in M.items():
        for path, anchor, _r in edits:
            c = text[path].count(anchor)
            assert c == 1, f"{name}: anchor occurs {c}x in {path}, expected 1"
    res = {"executed": datetime.datetime.now().isoformat(timespec="seconds"),
           "tree": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
           "method": "one mutation at a time; each anchor asserted to occur exactly once; only the bound backend "
                     "tests run, offline per PRB-002, with an outer environment asking for the Firestore backends "
                     "and a 60-minute access token (conftest must override it); bytes restored after each mutation",
           "hash_basis": "sha256 of the UTF-8 text with LF line endings",
           "source_sha256": {p: sha(text[p]) for p in files},
           "test_sha256": {t: sha(open(os.path.join("backend", t), encoding="utf-8").read().replace("\r\n", "\n"))
                           for t in BOUND},
           "baseline": None, "mutations": {}}
    with tempfile.TemporaryDirectory() as tmp:
        env = outer_env(tmp)
        all_bound = sorted({t for _e, tests, _w in M.values() for t in tests})
        res["baseline"] = run(all_bound, env)
        print("baseline", res["baseline"], flush=True)
        if res["baseline"]["failed"] or res["baseline"]["errors"] or not res["baseline"]["passed"]:
            raise SystemExit("the baseline must pass before the mutations mean anything")
        try:
            for name, (edits, tests, what) in M.items():
                touched = {}
                for path, anchor, repl in edits:
                    touched[path] = touched.get(path, text[path]).replace(anchor, repl, 1)
                for path, mutated in touched.items():
                    assert mutated != text[path], name
                    open(path, "w", encoding="utf-8", newline=eol[path]).write(mutated)
                out = run(tests, env)
                out.update({"reintroduces": what, "tests": tests,
                            "executed": datetime.datetime.now().isoformat(timespec="seconds"),
                            "detected": bool(out["failed"] or out["errors"] or out["exit"] != 0)})
                res["mutations"][name] = out
                for path in touched:
                    open(path, "wb").write(raw[path])
                print(f"{name:46s} detected={out['detected']} {out['failing_tests']}", flush=True)
        finally:
            for p, b in raw.items():
                open(p, "wb").write(b)
        for p in files:   # the restore is byte-exact
            assert open(p, "rb").read() == raw[p], p
        res["restored"] = run(all_bound, env)
    undetected = sorted(n for n, v in res["mutations"].items() if not v["detected"])
    res["summary"] = {"mutations": len(M), "detected": len(M) - len(undetected), "undetected": undetected}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"restored {res['restored']}; {res['summary']['detected']}/{len(M)} detected -> {OUT}")
    bad = res["restored"]["failed"] or res["restored"]["errors"]
    return 1 if undetected or bad else 0


if __name__ == "__main__":
    sys.exit(main())
