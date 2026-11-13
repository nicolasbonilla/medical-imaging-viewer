"""RC-130 negative controls (PR #82), run inside Cloud Build on a git archive of the PR head.

Each mutation is applied to a pristine copy of ONE file (its anchor must occur exactly once), the two RC-130 test
files are run with vitest's JSON reporter, the file is restored byte for byte, and the outcome is classified:
  killed  - at least one rc130 test FAILED by assertion while every test file loaded;
  survived - every rc130 test passed;
  invalid - a test file failed to load (a syntax/import error is never counted as a kill).
A baseline run (no mutation) must pass first. Results: nc_rc130.json.
"""
import json
import os
import subprocess
import sys

FRONT = sys.argv[1]
OUT = sys.argv[2]
TESTS = ["src/components/ReportViewerModal.inTesting.test.tsx", "src/utils/aiInTesting.test.ts"]
U = "src/utils/aiInTesting.ts"
V = "src/components/ReportViewerModal.tsx"
P = "src/components/AIReportPanel.tsx"

MUTATIONS = [
    ("N1 notice never shown", U, "  if (!modelWroteText(report)) return null;\n", "  return null;\n"),
    ("N2 notice on a draft no model wrote", U, "  if (!modelWroteText(report)) return null;\n", "  if (false) return null;\n"),
    ("N3 interface language instead of the report's", U, "  const lng = report.language || i18n.language;\n",
     "  const lng = i18n.language;\n"),
    ("N4 viewer copies without the notice", V, "await navigator.clipboard.writeText(textToCopy(report));",
     "await navigator.clipboard.writeText(report.content);"),
    ("N5 panel copies without the notice", P, "await navigator.clipboard.writeText(textToCopy(report));",
     "await navigator.clipboard.writeText(report.content);"),
    ("N6 notice above the clinician entry", V, None, None),  # special: move the structured-branch notice
]


def run_tests(tag):
    out = os.path.join("/tmp", f"vitest_{tag}.json")
    r = subprocess.run(["npx", "vitest", "run", *TESTS, "--reporter=json", f"--outputFile={out}"], cwd=FRONT,
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


def apply(rel, old, new):
    path = os.path.join(FRONT, rel)
    src = open(path, encoding="utf-8", newline="").read()
    if old is None:  # N6: move the structured notice above the disclaimer
        line = "                      {inTestingNotice && <InTestingNotice text={inTestingNotice} />}\n"
        key = line + "                      <ReactMarkdown remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>\n                        {report.ai_text ?? ''}"
        anchor = "                      {report.disclaimer && ("
        assert src.count(key) == 1 and src.count(anchor) == 1, "N6 anchors"
        mutated = src.replace(key, key[len(line):]).replace(anchor, line + anchor)
    else:
        assert src.count(old) == 1, (rel, old, src.count(old))
        mutated = src.replace(old, new)
    open(path, "w", encoding="utf-8", newline="").write(mutated)
    return src


results = {"baseline": run_tests("baseline"), "mutations": []}
assert results["baseline"]["exit"] == 0 and not results["baseline"]["failed"], results["baseline"]
for name, rel, old, new in MUTATIONS:
    pristine = apply(rel, old, new)
    res = run_tests(name.split()[0])
    open(os.path.join(FRONT, rel), "w", encoding="utf-8", newline="").write(pristine)
    if not res["loaded"]:
        verdict = "invalid"
    elif any((t or "").startswith("rc130") for t in res["failed"]):
        verdict = "killed"
    else:
        verdict = "survived"
    results["mutations"].append({"id": name, "file": rel, "verdict": verdict, "failed_tests": res["failed"],
                                 "passed": res["passed"]})
    print(name, "->", verdict, len(res["failed"]), "failing")
results["restored"] = run_tests("restored")
json.dump(results, open(OUT, "w", encoding="utf-8"), indent=1)
print("baseline passed", results["baseline"]["passed"], "| restored failed", len(results["restored"]["failed"]))
