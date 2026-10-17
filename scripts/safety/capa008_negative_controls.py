"""Negative controls for CAPA-008 (RC-033, RC-034, RC-035) — reproducible evidence.

Each mutation re-introduces ONE defect CAPA-008 removed, in the real source, one at a time;
the script asserts the anchor occurs exactly once (the sabotage really was applied), runs the
bound tests, records the failing test names and restores the originals.

Run from the repository root:
    backend/venv/Scripts/python scripts/safety/capa008_negative_controls.py
Output: docs/iec62304/records/risk_verification/CAPA-008_negative_controls_2026-10-17.json
NEVER run this while anything else edits the files it mutates (it restores a snapshot).
"""
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.chdir(ROOT)
PY = os.path.join(ROOT, "backend", "venv", "Scripts", "python.exe")
if not os.path.exists(PY):
    PY = sys.executable
OUT = "docs/iec62304/records/risk_verification/CAPA-008_negative_controls_2026-10-17.json"
TESTS = ["tests/unit/test_capa008_assistant_read_only.py", "tests/unit/test_longitudinal_clinical_rules.py"]

BACKEND = "backend/app/mcp/_backend.py"
CLINICAL = "backend/app/mcp/ms_clinical_server.py"
IMAGING = "backend/app/mcp/imaging_server.py"
RUN_ALL = "backend/app/mcp/run_all.py"
REPORT = "backend/app/api/routes/ai_report.py"
ANALYSIS = "backend/app/api/routes/segmentation_analysis.py"
LONGI = "backend/app/services/longitudinal_tracking_service.py"
DASH = "frontend/src/components/LesionDashboard.tsx"
PANEL = "frontend/src/components/AIReportPanel.tsx"

WRITE_TOOL = (
    "@mcp.tool()\n"
    "async def annotate_cvs_prl(segmentation_id: str, annotations: list) -> dict:\n"
    "    \"\"\"Write CVS/PRL readings.\"\"\"\n"
    "    return await api_post_compute(f\"/segmentation/{segmentation_id}/lesion-annotations\", "
    "{\"annotations\": annotations})\n\n\n"
)
PROMPTS = "# =============================================================================\n# Workflow prompts (resources for the assistant)\n"
CVS_MAJ = '        "cvs_majority": positive > negative,\n'
SELECT6 = "                  Select 6: {cvsSummary.cvs_positive}/{cvsSummary.total_evaluated} CVS+\n"
PRL_NOTE = '                {/* CAPA-008: neutral count — ">=1 PRL" is not, by itself, a criterion met. */}\n'
LONG_TOOL = ('        "/segmentation/longitudinal/compare",\n        {\n'
             '            "tp1": {"type": "segmentation", "id": baseline_id},\n')

M = {  # name: (file, anchor, replacement, what it re-introduces)
    "A1_allow_list_opens_an_unauthorized_route": (BACKEND, '    "/ai/report/generate",\n})', '    "/ai/report/generate",\n    "/ai/segment/auto",\n})',
                                                  "the assistant may POST to an AI route without object-level authorization"),
    "A2_identifiers_reach_the_assistant": (BACKEND, '    """Return a copy of a JSON-like value without the IDENTIFIER_KEYS fields, at any depth."""\n',
                                           '    """Return a copy of a JSON-like value without the IDENTIFIER_KEYS fields, at any depth."""\n    return value\n',
                                           "patient identifiers are passed to the assistant's model provider"),
    "A3_write_tool_restored": (CLINICAL, PROMPTS, WRITE_TOOL + PROMPTS, "the assistant can write CVS/PRL readings again"),
    "A4_report_fields_silently_dropped": (CLINICAL, '            "findings": findings,\n', '            "additional_findings": findings,\n',
                                          "the MS report tool sends its data under a field name the route drops"),
    "A5_diagnosis_framing": (CLINICAL, '"You assist a physician who reviews brain MRI measurements computed by an "',
                             '"You are analyzing brain MRI for MS diagnosis. You assist a physician who reviews brain MRI measurements computed by an "',
                             "the assistant is told it diagnoses MS"),
    "A6_unauthorized_get": (CLINICAL, '    return await api_get(f"/segmentation/{segmentation_id}/lesion-analysis")\n',
                            '    return await api_get(f"/ai/segment/{segmentation_id}/status")\n',
                            "a tool reads a route without object-level authorization"),
    "A7_post_outside_allow_list": (CLINICAL, LONG_TOOL, LONG_TOOL.replace("/segmentation/longitudinal/compare", "/segmentation/longitudinal/sel"),
                                   "a tool posts to a route that is not on the compute-only list"),
    "A8_direct_http_client": (IMAGING, "from fastmcp import FastMCP\nfrom app.mcp._backend import api_get\n",
                              "import httpx\nfrom fastmcp import FastMCP\nfrom app.mcp._backend import api_get\n",
                              "a server imports its own HTTP client"),
    "A9_unauthenticated_http_transport": (RUN_ALL, '    mcp.run(transport="stdio")\n', '    mcp.run(transport="sse")\n',
                                          "the SSE (HTTP) transport without authentication"),
    "R1_report_without_measurements": (REPORT, "    if not any(request.findings.get(k) for k in MEASUREMENT_FINDING_KEYS) and not request.volumetry:\n",
                                       "    if False:\n", "a report is drafted with no measurement"),
    "R2_ui_hides_the_reason": (PANEL, "(generateMutation.error as any)?.response?.status === 422", "(generateMutation.error as any)?.response?.status === 499",
                               "the report panel no longer explains the refusal"),
    "C1_client_chosen_reader": (ANALYSIS, '                "annotated_by": current_user.id,\n', '                "annotated_by": ann.get("annotated_by", "manual"),\n',
                                "the stored reader is whatever the client claims"),
    "C2_any_status_accepted": (ANALYSIS, "                if ann.get(field) not in LESION_MARKER_STATUSES:\n", "                if False:\n",
                               "any CVS/PRL status string is stored"),
    "C3_forty_percent_rule_in_api": (ANALYSIS, CVS_MAJ, CVS_MAJ + '        "meets_40pct": positive >= 0.4 * max(len(evaluated), 1),\n',
                                     "the withdrawn 40% rule is computed again"),
    "C4_forty_percent_rule_in_ui": (DASH, SELECT6, SELECT6 + "                  40% rule\n", "the UI shows the withdrawn 40% rule"),
    "C5_prl_shown_as_criterion_met": (DASH, PRL_NOTE, "                {prlSummary.meets_criteria ? null : null}\n",
                                      "the UI shows >=1 PRL as a criterion met"),
    "C6_activity_needs_two": (LONGI, '        "activity_candidate": (new_significant + enlarging) >= 1,\n',
                              '        "activity_candidate": (new_significant + enlarging) >= 2,\n',
                              "a single new or enlarging candidate raises no activity signal"),
}


def run():
    r = subprocess.run([PY, "-m", "pytest", *TESTS, "-q", "-p", "no:cacheprovider", "-o", "log_cli=false"],
                       cwd="backend", capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=dict(os.environ))
    f = re.search(r"(\d+) failed", r.stdout)
    p = re.search(r"(\d+) passed", r.stdout)
    e = re.search(r"(\d+) error", r.stdout)
    return {"failed": int(f.group(1)) if f else 0, "passed": int(p.group(1)) if p else 0,
            "errors": int(e.group(1)) if e else 0,
            "failing_tests": re.findall(r"FAILED \S+::(\S+)", r.stdout)}


def main():
    files = sorted({v[0] for v in M.values()})
    raw = {p: open(p, "rb").read() for p in files}                      # exact bytes, restored at the end
    text = {p: b.decode("utf-8").replace("\r\n", "\n") for p, b in raw.items()}
    eol = {p: "\r\n" if b"\r\n" in b else "\n" for p, b in raw.items()}  # keep each file's line endings
    for name, (path, anchor, _r, _w) in M.items():
        c = text[path].count(anchor)
        assert c == 1, f"{name}: anchor occurs {c}x in {path}, expected 1"
    res = {"executed": datetime.datetime.now().isoformat(timespec="seconds"),
           "method": "one mutation at a time; each anchor asserted to occur exactly once",
           "hash_basis": "sha256 of the UTF-8 text with LF line endings",
           "source_sha256": {p: hashlib.sha256(text[p].encode("utf-8")).hexdigest() for p in files},
           "tests": TESTS, "mutations": {}}
    try:
        for name, (path, anchor, repl, what) in M.items():
            mutated = text[path].replace(anchor, repl, 1)
            assert mutated != text[path], name
            open(path, "w", encoding="utf-8", newline=eol[path]).write(mutated)
            out = run()
            out.update({"reintroduces": what, "applied": True})
            res["mutations"][name] = out
            open(path, "wb").write(raw[path])
            print(f"{name:45s} {out['failed']} failed / {out['errors']} errors / {out['passed']} passed", flush=True)
    finally:
        for p, b in raw.items():
            open(p, "wb").write(b)
    res["restored"] = run()
    res["undetected"] = sorted(n for n, v in res["mutations"].items() if v["failed"] == 0 and v["errors"] == 0)
    json.dump(res, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("restored", res["restored"]["passed"], "passed /", res["restored"]["failed"], "failed | undetected:", res["undetected"])
    return 1 if res["undetected"] or res["restored"]["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
