"""Negative controls of the report panel's error contract — tenth independent review of PR #78, I16 (Class C;
REQ-SAFE-048/051, RC-103; DRAFT, PENDING owner approval).

Each mutation re-introduces one defect the reviewer found or one way to undo the fix: the panel decides by the HTTP
status instead of the server's code (every 422 "No measurements are available", the reviewer's case), the
implausible measurement is not named, a code is left without its message. One mutation at a time, each anchor asserted
to occur exactly once (LF text, written back with the file's own line endings); the panel tests run with vitest (JSON
reporter); a mutation counts as detected only when at least one test FAILS (a run that produced no report or a test
file that could not load is an error, never a detection); the original bytes are restored after each mutation and
checked at the end, and the restored tests must pass.

Run it in a throwaway copy of the commit (the frontend needs its node_modules): `python scripts/safety/
report_panel_negative_controls.py`; NC_OUT names the record, NC_ONLY=name,name re-runs some.
"""
import datetime
import hashlib
import json
import os
import subprocess
import sys
import tempfile

OUT = os.environ.get("NC_OUT", "docs/iec62304/records/risk_verification/REPORT-PANEL_negative_controls_review10_2026-11-12.json")
PANEL = "frontend/src/components/AIReportPanel.tsx"
FRONTEND_TESTS = ["src/components/AIReportPanel.errorCodes.test.tsx", "src/components/AIReportPanel.release20261025.test.tsx"]

M = {  # name: ([(file, anchor, replacement), ...], what it re-introduces)
    "U1_panel_decides_by_status": ([(PANEL, "    const entry = code ? REPORT_ERROR_MESSAGES[code] : undefined;\n",
                                     "    const entry = (error as any)?.response?.status === 422 ? REPORT_ERROR_MESSAGES.nothing_to_report : "
                                     "(code ? REPORT_ERROR_MESSAGES[code] : undefined);\n")],
                                   "I16: every 422 reads 'No measurements are available' (the reviewer's case)"),
    "U2_implausible_not_named": ([(PANEL, "      return t(entry[0], { defaultValue: entry[1], measurement });\n",
                                   "      return t(entry[0], { defaultValue: entry[1], measurement: '' });\n")],
                                 "I16: the implausible measurement is not named"),
    "U3_code_without_its_message": ([(PANEL, "  identifier_in_prompt: ['report.errors.identifierInPrompt', ",
                                      "  identifier_in_prompt_unmapped: ['report.errors.identifierInPrompt', ")],
                                    "I16: a code the route returns has no message of its own (the transport's text instead)"),
}

if os.environ.get("NC_ONLY"):
    _only = set(os.environ["NC_ONLY"].split(","))
    M = {k: v for k, v in M.items() if k in _only}
    assert set(M) == _only, f"unknown control(s): {sorted(_only - set(M))}"


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_frontend():
    out = os.path.join(tempfile.gettempdir(), "report_panel_vitest.json")
    if os.path.exists(out):
        os.remove(out)
    subprocess.run("npx vitest run " + " ".join(FRONTEND_TESTS) + f" --pool=threads --reporter=json --outputFile={out}",
                   cwd="frontend", shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not os.path.exists(out):
        return {"failed": 0, "passed": 0, "errors": 1, "failing_tests": [], "error_files": ["vitest produced no report"]}
    d = json.load(open(out, encoding="utf-8"))
    res = [a for f in d["testResults"] for a in f["assertionResults"]]
    errors = [f["name"].split("frontend")[-1] for f in d["testResults"] if f["status"] == "failed" and not f["assertionResults"]]
    return {"failed": sum(a["status"] == "failed" for a in res), "passed": sum(a["status"] == "passed" for a in res),
            "errors": len(errors), "failing_tests": [a["title"] for a in res if a["status"] == "failed"][:40],
            "error_files": errors}


def main():
    files = sorted({e[0] for edits, _w in M.values() for e in edits})
    raw = {p: open(p, "rb").read() for p in files}
    text = {p: b.decode("utf-8").replace("\r\n", "\n") for p, b in raw.items()}
    eol = {p: "\r\n" if b"\r\n" in b else "\n" for p, b in raw.items()}
    for name, (edits, _w) in M.items():
        for path, anchor, _r in edits:
            c = text[path].count(anchor)
            assert c == 1, f"{name}: anchor occurs {c}x in {path}, expected 1"
    tests = [f"frontend/{t}" for t in FRONTEND_TESTS]
    res = {"executed": datetime.datetime.now().isoformat(timespec="seconds"),
           "method": "one mutation at a time; each anchor asserted to occur exactly once; the panel tests run with "
                     "vitest (JSON reporter); detected only when a test fails (a load error is not a detection); "
                     "original bytes restored after each mutation and checked at the end",
           "hash_basis": "sha256 of the UTF-8 text with LF line endings",
           "source_sha256": {p: sha(text[p]) for p in files},
           "test_sha256": {t: sha(open(t, encoding="utf-8").read().replace("\r\n", "\n")) for t in tests},
           "tests": tests, "baseline": run_frontend(), "mutations": {}}
    base = res["baseline"]
    if base["failed"] or base["errors"] or not base["passed"]:
        raise SystemExit(f"the baseline must pass before the mutations mean anything: {base}")
    try:
        for name, (edits, what) in M.items():
            touched = {}
            for path, anchor, repl in edits:
                touched[path] = touched.get(path, text[path]).replace(anchor, repl, 1)
            for path, mutated in touched.items():
                assert mutated != text[path], name
                open(path, "w", encoding="utf-8", newline=eol[path]).write(mutated)
            out = run_frontend()
            out.update({"reintroduces": what, "detected": out["failed"] > 0 and not out["errors"],
                        "executed": datetime.datetime.now().isoformat(timespec="seconds")})
            res["mutations"][name] = out
            for path in touched:
                open(path, "wb").write(raw[path])
            print(f"{name:40s} detected={out['detected']} {out['failed']} failed / {out['errors']} errors / "
                  f"{out['passed']} passed", flush=True)
    finally:
        for p, b in raw.items():
            open(p, "wb").write(b)
    for p in files:   # the restore is byte-exact
        assert open(p, "rb").read() == raw[p], p
    res["restored"] = run_frontend()
    res["summary"] = {"mutations": len(res["mutations"]),
                      "detected": sum(1 for v in res["mutations"].values() if v["detected"]),
                      "undetected": sorted(n for n, v in res["mutations"].items() if not v["detected"])}
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    json.dump(res, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    r = res["restored"]
    print("restored", r["passed"], "passed /", r["failed"], "failed | detected", res["summary"]["detected"], "of",
          res["summary"]["mutations"], "| undetected:", res["summary"]["undetected"])
    return 1 if res["summary"]["undetected"] or r["failed"] or r["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
