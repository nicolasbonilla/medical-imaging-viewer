"""RC-130 negative controls (PR #82; REQ-SAFE-060; HAZ-003, HAZ-017) — DRAFT, PENDING owner approval.

Run off the owner's PC (Google Cloud Build, node:22) on an archive of the PR head:
    python3 scripts/safety/rc130_negative_controls.py <repo root> <out.json>
Each mutation is applied to a pristine copy of ONE file (its anchor must occur exactly once), the two RC-130 test files
run with vitest's JSON reporter, the file is restored byte for byte, and the outcome is classified:
  killed   - at least one rc130 test FAILED by assertion while every test file loaded;
  survived - every rc130 test passed;
  invalid  - a test file failed to load (a syntax or import error is never counted as a kill).
A baseline run (no mutation) must pass first; a final run on the restored code must pass too.
M follows the repository convention read by backend/tests/unit/test_negative_controls_validity.py:
name -> (file, anchor, replacement or transform, what).
"""
import json
import os
import subprocess
import sys

TESTS = ["src/components/ReportViewerModal.inTesting.test.tsx", "src/utils/aiInTesting.test.ts"]
U = "frontend/src/utils/aiInTesting.ts"
V = "frontend/src/components/ReportViewerModal.tsx"
P = "frontend/src/components/AIReportPanel.tsx"

_NOTICE = "                      {inTestingNotice && <InTestingNotice text={inTestingNotice} />}\n"
_STRUCTURED_NOTICE = (_NOTICE + "                      <ReactMarkdown remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>\n"
                      "                        {report.ai_text ?? ''}")
_DISCLAIMER = "                      {report.disclaimer && ("


def _notice_above_clinician_entry(text):
    """N6: move the structured-branch notice above the disclaimer and the clinician's entry."""
    assert text.count(_STRUCTURED_NOTICE) == 1 and text.count(_DISCLAIMER) == 1
    return text.replace(_STRUCTURED_NOTICE, _STRUCTURED_NOTICE[len(_NOTICE):]).replace(_DISCLAIMER, _NOTICE + _DISCLAIMER)


M = {
    "N1": (U, "  if (!modelWroteText(report)) return null;\n", "  return null;\n", "notice never shown"),
    "N2": (U, "  if (!modelWroteText(report)) return null;\n", "  if (false) return null;\n",
           "notice on a draft no model wrote"),
    "N3": (U, "  const lng = report.language || i18n.language;\n", "  const lng = i18n.language;\n",
           "interface language instead of the report's"),
    "N4": (V, "await navigator.clipboard.writeText(textToCopy(report));",
           "await navigator.clipboard.writeText(report.content);", "viewer copies without the notice"),
    "N5": (P, "await navigator.clipboard.writeText(textToCopy(report));",
           "await navigator.clipboard.writeText(report.content);", "panel copies without the notice"),
    "N6": (V, _STRUCTURED_NOTICE, _notice_above_clinician_entry, "notice above the clinician entry"),
}


def _run_tests(front, tag):
    out = os.path.join("/tmp", f"vitest_{tag}.json")
    r = subprocess.run(["npx", "vitest", "run", *TESTS, "--reporter=json", f"--outputFile={out}"], cwd=front,
                       capture_output=True, text=True)
    try:
        d = json.load(open(out, encoding="utf-8"))
    except Exception:
        return {"exit": r.returncode, "loaded": False, "failed": [], "passed": 0, "note": r.stderr[-800:]}
    failed, passed, load_error = [], 0, False
    for f in d.get("testResults", []):
        if f.get("status") == "failed" and not f.get("assertionResults"):
            load_error = True
        for a in f.get("assertionResults", []):
            if a.get("status") == "passed":
                passed += 1
            elif a.get("status") == "failed":
                failed.append(a.get("title"))
    return {"exit": r.returncode, "loaded": not load_error, "failed": failed, "passed": passed}


def main(repo, out_path):
    front = os.path.join(repo, "frontend")
    results = {"baseline": _run_tests(front, "baseline"), "mutations": []}
    assert results["baseline"]["exit"] == 0 and not results["baseline"]["failed"], results["baseline"]
    for name, (rel, anchor, repl, what) in M.items():
        path = os.path.join(repo, rel)
        pristine = open(path, encoding="utf-8", newline="").read()
        assert pristine.count(anchor) == 1, (name, rel, pristine.count(anchor))
        mutated = repl(pristine) if callable(repl) else pristine.replace(anchor, repl, 1)
        open(path, "w", encoding="utf-8", newline="").write(mutated)
        res = _run_tests(front, name)
        open(path, "w", encoding="utf-8", newline="").write(pristine)
        if not res["loaded"]:
            verdict = "invalid"
        elif any((t or "").startswith("rc130") for t in res["failed"]):
            verdict = "killed"
        else:
            verdict = "survived"
        results["mutations"].append({"id": f"{name} {what}", "file": rel, "verdict": verdict,
                                     "failed_tests": res["failed"], "passed": res["passed"]})
        print(name, what, "->", verdict, len(res["failed"]), "failing")
    results["restored"] = _run_tests(front, "restored")
    json.dump(results, open(out_path, "w", encoding="utf-8"), indent=1)
    print("baseline passed", results["baseline"]["passed"], "| restored failed", len(results["restored"]["failed"]))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
