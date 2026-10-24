"""Negative controls for PRB-003 — DIS only on a segmentation a clinician has confirmed
(RC-070, RC-071, RC-072; REQ-SAFE-038..040; HAZ-008, HAZ-005, HAZ-003).

Each mutation re-introduces ONE defect PRB-003 removed (DIS evaluated on an unconfirmed segmentation, a
confirmation not bound to the mask, a stored or client-supplied DIS conclusion trusted, "NOT MET" for a
missing flag, the assistant receiving a conclusion, the confirmation open to any role or any mask, the
information for safety missing) or removes one sub-control it added — in the real source, one at a time.
The script asserts every anchor occurs exactly once (the sabotage really was applied), runs the bound
tests of the side it mutated (backend: pytest, offline per PRB-002; frontend: vitest, JSON reporter),
records the failing test names and restores the exact original bytes.

Run from the repository root (needs backend/venv or the current Python with the backend requirements,
and frontend/node_modules):
    python scripts/safety/prb003_negative_controls.py            # every mutation
    python scripts/safety/prb003_negative_controls.py --only F   # only the mutations starting with F
Output: docs/iec62304/records/risk_verification/PRB-003_negative_controls_2026-10-24.json
NEVER run this while anything else edits the files it mutates (it restores a snapshot).
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
OUT = "docs/iec62304/records/risk_verification/PRB-003_negative_controls_2026-10-24.json"
BACKEND_TESTS = ["tests/unit/test_prb003_dis_requires_confirmed_segmentation.py"]
FRONTEND_TESTS = ["src/components/LesionDashboard.prb003.test.tsx"]

GATE = "backend/app/services/dis_review_gate.py"
SA = "backend/app/api/routes/segmentation_analysis.py"
SR = "backend/app/api/routes/segmentation_regions.py"
SEG = "backend/app/api/routes/segmentation.py"
SVC = "backend/app/services/segmentation_service.py"
AIR = "backend/app/api/routes/ai_report.py"
BRS = "backend/app/services/brain_report_service.py"
MCPS = "backend/app/mcp/ms_clinical_server.py"
DASH = "frontend/src/components/LesionDashboard.tsx"
BANNER = "frontend/src/components/AiDraftBanner.tsx"
PANEL = "frontend/src/components/SegmentationPanel.tsx"
TYPES = "frontend/src/types/lesion.ts"
ES = "frontend/src/i18n/locales/es.json"

MCP_RULE = (
    '        "- DIS is evaluated only on a segmentation a radiologist has confirmed for its current mask "\n'
    '        "(PRB-003). When `dis_assessment.evaluation_status` is not \'evaluated\', say only \'dissemination in "\n'
    '        "space: not evaluated (requires clinician review of the segmentation)\'. Never derive dissemination "\n'
    '        "in space yourself from lesion counts, regions or the region classification. Automatic marking also "\n'
    '        "marks spots in most healthy brains; a marked spot is not evidence of multiple sclerosis.\\n"\n'
)
ES_NOTICE = ('    "automaticMarkingNotice": "La marcación automática también marca manchas en la mayoría de los cerebros '
             'sanos, sobre todo junto a los ventrículos. Una mancha marcada no es prueba de esclerosis múltiple; cada '
             'mancha requiere la revisión de un experto."')
ES_NOTICE_EN = ('    "automaticMarkingNotice": "Automatic marking also marks spots in most healthy brains, mostly next to '
                'the ventricles. A marked spot is not evidence of multiple sclerosis; every spot needs expert review."')

M = {  # name: ([(file, anchor, replacement), ...], what it re-introduces)
    # ── RC-070: the gate itself (backend) ──
    "G1_route_gate_bypassed": ([(SA, '    if not state["confirmed"]:\n        logger.info("DIS not evaluated',
                                 '    if False:\n        logger.info("DIS not evaluated')],
                               "DIS computed on any loaded segmentation (the defect as found: paper A, 19/100 healthy)"),
    "G2_confirmation_not_bound_to_the_mask": ([(GATE, '    bound = has_record and getattr(record, "reviewed_mask_sha256", None) == current\n',
                                                '    bound = has_record\n')],
                                              "a confirmation given for another mask counts"),
    "G3_unreviewed_ai_draft_counts": ([(GATE, '        has_record = provenance.review_status == "confirmed"\n',
                                       '        has_record = True\n')],
                                      "an unreviewed AI draft counts as confirmed"),
    "G4_clinician_record_replaces_the_ai_review": ([(GATE, '    if provenance is not None:\n        source = SOURCE_AI_DRAFT\n',
                                                    '    if provenance is not None and getattr(metadata, "clinician_review", None) is None:\n'
                                                    '        source = SOURCE_AI_DRAFT\n')],
                                                  "an AI draft confirmed through the clinician record, bypassing RC-047"),
    "G5_stored_state_served_as_a_result": ([(SA, '            and dis_gate.is_evaluated(cached.get("dis_assessment"))):\n',
                                             '            and "dis_assessment" in cached):\n')],
                                           "a stored DIS block (not evaluated, or from before the fix) served as a result"),
    "G6_metadata_route_serves_stored_dis": ([(SEG, '            metadata=dis_gate.without_stored_dis(metadata),\n',
                                              '            metadata=metadata,\n')],
                                            "the stored DIS block reaches the viewer with the segmentation metadata"),
    "G7_list_route_serves_stored_dis": ([(SEG, '        return [r.model_copy(update={"metadata": dis_gate.without_stored_dis(r.metadata)}) for r in listed]\n',
                                          '        return listed\n')],
                                        "the stored DIS block reaches the viewer with the segmentation list"),
    "G8_classify_regions_stores_ungated_dis": ([(SR, '                if review["confirmed"]:\n', '                if True:\n')],
                                               "classify-regions stores a DIS conclusion for any mask (the defect as found)"),
    "G9_not_evaluated_state_carries_a_conclusion": ([(GATE, '        "evaluation_status": NOT_EVALUATED,\n',
                                                      '        "evaluation_status": NOT_EVALUATED,\n        "dis_met": False,\n')],
                                                    "the 'not evaluated' state still says met / not met"),
    # ── RC-071: confirming a segmentation without AI provenance ──
    "C1_any_role_may_confirm": ([(SEG, '    if not _radiologist(current_user):\n', '    if False:\n')],
                                "any authenticated user confirms a segmentation"),
    "C2_confirmation_for_any_mask": ([(SEG, '    if stated != stored_digest:\n', '    if False:\n')],
                                     "a confirmation recorded for a mask other than the stored one"),
    "C3_ai_draft_confirmed_here": ([(SEG, '    if metadata.ai_provenance is not None:\n        raise HTTPException(\n',
                                     '    if False:\n        raise HTTPException(\n')],
                                   "an AI draft confirmed outside its own review (RC-047)"),
    "C4_mask_change_keeps_the_confirmation": ([(SVC, '        clinician_reset = self._enforce_clinician_review_binding(seg_data)\n',
                                                '        clinician_reset = False\n')],
                                              "a confirmation survives a change of the mask"),
    "C5_reviewer_not_the_authenticated_user": ([(SEG, '        reviewed_by=current_user.username,\n',
                                                 '        reviewed_by=str((body or {}).get("reviewed_by") or "client"),\n')],
                                               "the reviewer recorded from the request instead of the authenticated user"),
    # ── RC-070 on the report path (HAZ-003) ──
    "R1_report_trusts_the_client_block": ([(AIR, '        findings["dis_assessment"] = await server_dis_assessment(findings["dis_assessment"], current_user)\n',
                                            '        findings["dis_assessment"] = findings["dis_assessment"]\n')],
                                          "a DIS conclusion sent by the client reaches the model (the defect as found)"),
    "R2_report_skips_authorization": ([(AIR, '    await authorize_mask_specs([{"type": "segmentation", "id": sid}], current_user)\n',
                                        '    pass\n')],
                                      "the report reads a segmentation the caller may not read (RC-029)"),
    "R3_report_route_stores_the_assessment": ([(AIR, '        return await assess_dis(sid, segmentation_service, storage_service, store=False)\n',
                                                '        return await assess_dis(sid, segmentation_service, storage_service, store=True)\n')],
                                              "the compute-only report route writes to the segmentation (RC-033)"),
    "R4_prompt_states_met_for_an_unevaluated_block": ([(BRS, '        if not (isinstance(dis, dict) and dis.get("evaluation_status") == "evaluated"):\n',
                                                        '        if not isinstance(dis, dict):\n')],
                                                      "the prompt prints MET / NOT MET for a block that was not evaluated (the defect as found)"),
    "R5_prompt_lets_the_model_derive_dis": ([(BRS, '            if dis or findings.get("lesion_analysis"):\n', '            if dis:\n')],
                                            "lesion counts without an evaluated DIS reach the model with no rule against deriving DIS"),
    "R6_report_notice_removed": ([(AIR, '        if dis_text:   # PRB-003', '        if False:   # PRB-003')],
                                 "a draft without an evaluated DIS ends without the not-evaluated notice"),
    "R7_report_from_an_unevaluated_dis_only": ([(AIR, '        if not (others or request.volumetry or gate.is_evaluated(findings["dis_assessment"])):\n',
                                                 '        if False:\n')],
                                               "a draft requested with no measurement but a 'not evaluated' DIS state (RC-034)"),
    # ── RC-070 on the assistant path (MCP) ──
    "A1_assistant_receives_unevaluated_conclusion": ([(MCPS, '    if isinstance(dis, dict) and dis.get("evaluation_status") == "evaluated":\n',
                                                       '    if isinstance(dis, dict):\n')],
                                                     "the assistant receives a DIS conclusion that was not evaluated (older backend)"),
    "A2_assistant_rule_removed": ([(MCPS, MCP_RULE, '')],
                                  "the assistant is not told to report 'not evaluated' and never to derive DIS"),
    # ── RC-072: information for safety (backend) ──
    "N1_not_evaluated_state_without_notice": ([(GATE, '    if state is not None and state["source"] in AUTOMATIC_SOURCES:\n',
                                                '    if False:\n')],
                                              "the 'not evaluated' state of an automatic segmentation without the healthy-brain notice"),
    # ── frontend: the dashboard, the banner, the panel ──
    "F1_display_trusts_any_conclusion": ([(TYPES, "(d as { evaluation_status?: unknown }).evaluation_status === 'evaluated'",
                                           "'dis_met_brain' in (d as object)")],
                                         "the dashboard shows met / not met for a block that was not evaluated"),
    "F2_topographies_panel_for_unevaluated": ([(DASH, "      {disOk && (\n        <div className=\"p-2 rounded-lg bg-indigo-950/30",
                                                "      {dis && (dis as any).total_topographies_involved !== undefined && (\n        <div className=\"p-2 rounded-lg bg-indigo-950/30")],
                                              "the five-topography panel (and its 'dissemination in time may be waived' line) shown for any block"),
    "F3_confirm_offered_with_unsaved_changes": ([(DASH, "                  hasUnsavedMaskChanges ? (\n", "                  false ? (\n")],
                                                "the confirm button offered while the mask on screen is not the saved one"),
    "F4_confirmation_not_bound_to_the_mask": ([(DASH, "confirmSegmentationReview(segmentationId, digest)",
                                                "confirmSegmentationReview(segmentationId, '0'.repeat(64))")],
                                              "the confirmation does not send the SHA-256 of the mask on screen"),
    "F5_confirm_offered_for_an_ai_draft": ([(DASH, "{(source === 'automatic_tool' || source === 'origin_not_recorded') && (",
                                             "{true && (")],
                                           "an AI draft confirmed from the DIS card instead of its own review"),
    "F6_card_without_notice": ([(DASH, "{(source === 'ai_draft' || source === 'automatic_tool') && <AutomaticMarkingNotice />}",
                                 "{false && <AutomaticMarkingNotice />}")],
                               "the 'not evaluated' card of an automatic segmentation without the healthy-brain notice"),
    "F7_banner_without_notice": ([(BANNER, '      <AutomaticMarkingNotice className="text-[10px] leading-snug" />\n', '')],
                                 "the AI draft banner without the healthy-brain notice"),
    "F8_panel_without_notice": ([(PANEL, "{!activeSegmentation.ai_provenance && openSegmentationType === 'automatic' && (",
                                  "{false && (")],
                                "a server-tool segmentation shown without the healthy-brain notice"),
    "F9_notice_english_in_spanish": ([(ES, ES_NOTICE, ES_NOTICE_EN)],
                                     "the healthy-brain notice shown in English to Spanish-language users"),
    "F10_confirmed_by_not_shown": ([(DASH, "            {disOk.segmentation_review?.reviewed_by && (", "            {false && (")],
                                   "a DIS result shown without the radiologist whose confirmation it rests on"),
    "F11_no_refresh_after_confirmation": ([(DASH, "      await refreshDis();\n    } catch (e: any) {\n",
                                            "      void 0;\n    } catch (e: any) {\n")],
                                          "after the confirmation the card keeps the old state"),
    "F12_result_shown_for_unsaved_changes": ([(DASH, "  const disOk = isDisEvaluated(dis) && !hasUnsavedMaskChanges ? dis : null;\n",
                                               "  const disOk = isDisEvaluated(dis) ? dis : null;\n")],
                                             "a result shown for a mask on screen that is no longer the confirmed one"),
    "F13_no_refresh_after_saving": ([(DASH, "    if (hadUnsavedChanges.current && !hasUnsavedMaskChanges && dis) void refreshDis();\n",
                                      "    if (false) void refreshDis();\n")],
                                    "after saving a changed mask the panel keeps the result of the confirmed mask"),
}

# Mutations that are NOT defects (equivalent code), stated rather than claimed as tested.
EXPECTED_UNDETECTED = {}


def offline_env():
    """PRB-002: backend tests never reach a real cloud service or the model provider."""
    env = dict(os.environ)
    empty = tempfile.mkdtemp(prefix="prb003-no-gcloud-")
    env.update({"GOOGLE_APPLICATION_CREDENTIALS": os.path.join(empty, "no-such-credentials.json"),
                "CLOUDSDK_CONFIG": empty, "GOOGLE_CLOUD_PROJECT": "mstool-offline-tests"})
    env.pop("ANTHROPIC_API_KEY", None)
    return env


def run_backend():
    r = subprocess.run([PY, "-m", "pytest", *BACKEND_TESTS, "-q", "-p", "no:cacheprovider", "-o", "log_cli=false"],
                       cwd="backend", capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=offline_env())
    f = re.search(r"(\d+) failed", r.stdout)
    p = re.search(r"(\d+) passed", r.stdout)
    e = re.search(r"(\d+) error", r.stdout)
    return {"suite": "backend", "failed": int(f.group(1)) if f else 0, "passed": int(p.group(1)) if p else 0,
            "errors": int(e.group(1)) if e else 0, "skipped": 0,
            "failing_tests": sorted(set(re.findall(r"(?:FAILED|ERROR) \S+::(\S+)", r.stdout)))}


def run_frontend():
    out = os.path.join(tempfile.gettempdir(), "prb003_vitest.json")
    if os.path.exists(out):
        os.remove(out)
    subprocess.run("npx vitest run " + " ".join(FRONTEND_TESTS) + f" --pool=threads --reporter=json --outputFile={out}",
                   cwd="frontend", shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not os.path.exists(out):
        return {"suite": "frontend", "failed": 0, "passed": 0, "skipped": 0, "errors": 1,
                "failing_tests": [], "error_files": ["vitest produced no report"]}
    d = json.load(open(out, encoding="utf-8"))
    res = [a for f in d["testResults"] for a in f["assertionResults"]]
    failed = [a["title"] for a in res if a["status"] == "failed"]
    errors = [f["name"].split("frontend")[-1] for f in d["testResults"] if f["status"] == "failed" and not f["assertionResults"]]
    return {"suite": "frontend", "failed": len(failed), "passed": sum(a["status"] == "passed" for a in res),
            "skipped": sum(a["status"] in ("skipped", "pending") for a in res), "errors": len(errors),
            "failing_tests": failed, "error_files": errors}


def run_for(paths):
    return run_frontend() if all(p.startswith("frontend/") for p in paths) else run_backend()


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main():
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    files = sorted({e[0] for edits, _w in M.values() for e in edits})
    raw = {p: open(p, "rb").read() for p in files}
    text = {p: b.decode("utf-8").replace("\r\n", "\n") for p, b in raw.items()}
    eol = {p: "\r\n" if b"\r\n" in b else "\n" for p, b in raw.items()}
    for name, (edits, _w) in M.items():
        for path, anchor, _r in edits:
            c = text[path].count(anchor)
            assert c == 1, f"{name}: anchor occurs {c}x in {path}, expected 1"
    tests = [f"backend/{t}" for t in BACKEND_TESTS] + [f"frontend/{t}" for t in FRONTEND_TESTS]
    test_sha = {t: sha(open(t, encoding="utf-8").read().replace("\r\n", "\n")) for t in tests}
    previous = json.load(open(OUT, encoding="utf-8")) if only and os.path.exists(OUT) else {"mutations": {}}
    res = {"executed": datetime.datetime.now().isoformat(timespec="seconds"),
           "method": "one mutation at a time; each anchor asserted to occur exactly once; the bound tests of the "
                     "mutated side are run (backend pytest with no cloud credential per PRB-002, frontend vitest "
                     "JSON reporter); original bytes restored after each mutation and checked at the end",
           "hash_basis": "sha256 of the UTF-8 text with LF line endings",
           "source_sha256": {p: sha(text[p]) for p in files},
           "test_sha256": test_sha,
           "tests": tests, "mutations": {}}
    try:
        for name, (edits, what) in M.items():
            if only and not name.startswith(only) and name in previous["mutations"]:
                res["mutations"][name] = previous["mutations"][name]
                continue
            touched = {}
            for path, anchor, repl in edits:
                touched[path] = touched.get(path, text[path]).replace(anchor, repl, 1)
            for path, mutated in touched.items():
                assert mutated != text[path], name
                open(path, "w", encoding="utf-8", newline=eol[path]).write(mutated)
            out = run_for(list(touched))
            out.update({"reintroduces": what, "applied": True,
                        "executed": datetime.datetime.now().isoformat(timespec="seconds")})
            res["mutations"][name] = out
            for path in touched:
                open(path, "wb").write(raw[path])
            print(f"{name:48s} [{out['suite']}] {out['failed']} failed / {out['errors']} errors / {out['passed']} passed",
                  flush=True)
    finally:
        for p, b in raw.items():
            open(p, "wb").write(b)
    for p in files:   # the restore is byte-exact
        assert open(p, "rb").read() == raw[p], p
    res["restored"] = {"backend": run_backend(), "frontend": run_frontend()}
    res["expected_undetected"] = EXPECTED_UNDETECTED
    res["undetected"] = sorted(n for n, v in res["mutations"].items() if v["failed"] == 0 and v["errors"] == 0)
    res["unexpected_undetected"] = sorted(set(res["undetected"]) - set(EXPECTED_UNDETECTED))
    res["summary"] = {"mutations": len(res["mutations"]),
                      "detected": len(res["mutations"]) - len(res["undetected"]),
                      "undetected": len(res["undetected"])}
    json.dump(res, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    rb, rf = res["restored"]["backend"], res["restored"]["frontend"]
    print("restored backend", rb["passed"], "passed /", rb["failed"], "failed | frontend", rf["passed"], "passed /",
          rf["failed"], "failed | detected", res["summary"]["detected"], "of", res["summary"]["mutations"],
          "| undetected:", res["undetected"])
    return 0 if not res["unexpected_undetected"] else 1


if __name__ == "__main__":
    sys.exit(main())
