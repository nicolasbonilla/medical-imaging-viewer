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
BACKEND_TESTS = ["tests/unit/test_prb003_dis_requires_confirmed_segmentation.py",
                 "tests/unit/test_prb003_review1_findings.py"]
FRONTEND_TESTS = ["src/components/LesionDashboard.prb003.test.tsx",
                  "src/components/LesionDashboard.prb003.review1.test.tsx",
                  "src/components/SegmentationPanel.prb003.test.tsx"]

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
TOOLS = "frontend/src/components/ClinicalToolsPanel.tsx"
FLAMES = "frontend/src/components/BrowserFlamesCard.tsx"
REPORT = "frontend/src/components/AIReportPanel.tsx"
VIEWER = "frontend/src/ViewerApp.tsx"
TYPES = "frontend/src/types/lesion.ts"
ES = "frontend/src/i18n/locales/es.json"

MCP_RULE = (
    '        "- DIS is evaluated only on a segmentation a radiologist has confirmed for its current mask "\n'
    '        "(PRB-003). When `dis_assessment.evaluation_status` is not \'evaluated\', say only \'dissemination in "\n'
    '        "space: not evaluated (requires clinician review of the segmentation)\'. Never derive dissemination "\n'
    '        "in space yourself from lesion counts, regions or the region classification. Automatic marking also "\n'
    '        "marks spots in most healthy brains; a marked spot is not evidence of multiple sclerosis.\\n"\n'
)
ES_NOTICE = ('    "automaticMarkingNotice": "La marcación automática de lesiones también marca manchas en la mayoría de los '
             'cerebros sanos, sobre todo junto a los ventrículos. Una mancha marcada no es prueba de esclerosis múltiple; '
             'cada mancha requiere la revisión de un experto."')
ES_NOTICE_EN = ('    "automaticMarkingNotice": "Automatic lesion marking also marks spots in most healthy brains, mostly next '
                'to the ventricles. A marked spot is not evidence of multiple sclerosis; every spot needs expert review."')
CONFIRMED_LINE = '    confirmed = bool(regions["classified"] and ai_review_ok and bound)\n'

M = {  # name: ([(file, anchor, replacement), ...], what it re-introduces)
    # ── RC-070: the gate (backend) ──
    "G1_route_gate_bypassed": ([(SA, '    if not state["confirmed"]:\n        logger.info("DIS not evaluated',
                                 '    if False:\n        logger.info("DIS not evaluated')],
                               "DIS computed on any loaded segmentation (the defect as found: paper A, 19/100 healthy)"),
    "G2_confirmation_not_bound_to_the_mask": ([(GATE, '    bound = (has_record and getattr(record, "reviewed_mask_sha256", None) == current\n',
                                                '    bound = (has_record\n')],
                                              "a confirmation given for another mask counts"),
    "G2b_confirmation_not_bound_to_the_labels": ([(GATE, '             and getattr(record, "reviewed_labels_sha256", None) == labels_digest)\n',
                                                   '             and True)\n')],
                                                 "a confirmation survives a renaming of the labels (review finding 6)"),
    "G3_unreviewed_ai_draft_counts": ([(GATE, '        provenance.review_status == "confirmed" and provenance.reviewed_mask_sha256 == current)',
                                       '        True)')],
                                      "an unreviewed AI draft counts as reviewed"),
    "G4_ai_review_not_required": ([(GATE, CONFIRMED_LINE, '    confirmed = bool(regions["classified"] and bound)\n')],
                                  "an AI draft evaluated without its own review (RC-047)"),
    "G5_stored_state_served_as_a_result": ([(SA, '            and dis_gate.is_evaluated(cached.get("dis_assessment"))\n',
                                             '            and "dis_assessment" in cached\n')],
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
    "G10_regions_not_required": ([(GATE, CONFIRMED_LINE, '    confirmed = bool(ai_review_ok and bound)\n')],
                                 "DIS evaluated on any confirmed mask, whatever its labels mean (review blocker 1, as found)"),
    "G11_mask_values_outside_the_scheme_accepted": ([(GATE, '    in_scheme = magnims and set(int(v) for v in np.unique(masks_3d)) <= allowed\n',
                                                      '    in_scheme = magnims\n')],
                                                    "a mask value no MAGNIMS label defines is read anyway"),
    "G12_classification_not_bound_to_the_lesions": ([(GATE, '    classified = bool(in_scheme and record.get("classified_lesion_footprint_sha256") == footprint_sha256(masks_3d))\n',
                                                      '    classified = bool(in_scheme)\n')],
                                                    "MAGNIMS names on lesions that never went through the classification count as regions"),
    "G13_any_label_scheme_is_magnims": ([(GATE, '    if any(pairs.get(i) != MAGNIMS_REGIONS[i] for i in MAGNIMS_REQUIRED_IDS):\n        return False\n',
                                         '    if False:\n        return False\n'),
                                        (GATE, '    return all(MAGNIMS_REGIONS.get(i) == name for i, name in pairs.items())\n',
                                         '    return True\n')],
                                       "the default preset (1 = MS Lesion Active) read as regions: a false MET (review blocker 1)"),
    "G14_classification_does_not_record_the_lesions": ([(SR, '            response_data["classified_lesion_footprint_sha256"] = dis_gate.footprint_sha256(classified_mask)\n', '')],
                                                       "classify-regions records no classified lesions: DIS can never be traced to a classification"),
    # ── RC-071: the DIS confirmation ──
    "C1_any_role_may_confirm": ([(SEG, '    if not _radiologist(current_user):\n', '    if False:\n')],
                                "any authenticated user confirms a segmentation"),
    "C2_confirmation_for_any_mask": ([(SEG, '    if stated != stored_digest:\n', '    if False:\n')],
                                     "a confirmation recorded for a mask other than the stored one"),
    "C3_ai_draft_confirmed_without_its_review": ([(SEG, '    if state["reason"] == dis_gate.REASON_AI_REVIEW:\n', '    if False:\n')],
                                                 "an AI draft DIS-confirmed before its own review (RC-047)"),
    "C4_mask_change_keeps_the_confirmation": ([(SVC, '        clinician_reset = self._enforce_clinician_review_binding(seg_data)\n',
                                                '        clinician_reset = False\n')],
                                              "a confirmation survives a change of the mask"),
    "C5_reviewer_not_the_authenticated_user": ([(SEG, 'reviewed_by=current_user.username, reviewed_by_id=actor_id',
                                                 'reviewed_by=str((body or {}).get("reviewed_by") or "client"), reviewed_by_id=actor_id')],
                                               "the reviewer recorded from the request instead of the authenticated user"),
    "C6_confirmation_before_classification": ([(SEG, '    if not state["regions"]["classified"]:\n', '    if False:\n')],
                                              "the confirmation accepted before the regions are classified (review blocker 1)"),
    "C7_second_confirmation_overwrites_the_first": ([(SEG, '    already = bool(state["confirmed"])\n', '    already = False\n')],
                                                    "a repeat confirmation replaces the first confirmer (review finding 5)"),
    "C8_confirmation_not_in_the_history": ([(SEG, '    metadata.clinician_review_history = [*previous[1], event]\n',
                                             '    metadata.clinician_review_history = previous[1]\n')],
                                           "confirmations leave no history (review finding 5)"),
    "C9_voiding_not_in_the_history": ([(SVC, '        metadata.clinician_review_history = [*(metadata.clinician_review_history or []), ClinicianReviewEvent(',
                                        '        _unrecorded = [*(metadata.clinician_review_history or []), ClinicianReviewEvent(')],
                                      "a voided confirmation disappears without trace (review finding 5)"),
    "C10_confirmation_rewrites_the_mask": ([(SEG, '        tier = segmentation_service.persist_metadata(segmentation_id)\n',
                                             '        tier = segmentation_service.persist(segmentation_id)\n')],
                                           "the confirmation rewrites the mask object: the next save gets a 409 (review finding 5)"),
    "C11_non_durable_confirmation_accepted": ([(SEG, '    if tier is None:\n        metadata.clinician_review, metadata.clinician_review_history = previous\n',
                                                '    if False:\n        metadata.clinician_review, metadata.clinician_review_history = previous\n')],
                                              "a confirmation that was not stored durably is reported as recorded (review finding 5)"),
    "C12_stale_mask_keeps_the_cached_confirmation": ([(SEG, '        segmentation_service.discard_cached(segmentation_id)   # never keep',
                                                       '        pass   # never keep')],
                                                     "after a stale-write conflict the confirmation stays in the instance cache (review finding 5)"),
    "C13_label_change_keeps_the_confirmation": ([(SVC, '        elif review.reviewed_labels_sha256 != labels_sha256(getattr(metadata, "labels", None) or []):\n',
                                                  '        elif False:\n')],
                                                "renaming a label keeps the stored confirmation (review finding 6)"),
    "C14_any_role_may_rename_labels": ([(SEG, '    if getattr(current_user, "role", None) not in (UserRole.RADIOLOGIST, UserRole.TECHNICIAN):\n',
                                         '    if False:\n')],
                                       "a viewer or an administrator renames what the DIS rule reads as regions (review finding 6)"),
    # ── RC-070 on the report path (HAZ-003) ──
    "R1_report_trusts_the_client_block": ([(AIR, '        findings["dis_assessment"] = await server_dis_assessment(report_sid, current_user)\n',
                                            '        findings["dis_assessment"] = findings.get("dis_assessment") or {}\n')],
                                          "a DIS conclusion sent by the client reaches the model (the defect as found)"),
    "R2_report_skips_authorization": ([(AIR, '        await authorize_mask_specs([{"type": "segmentation", "id": report_sid}], current_user)\n',
                                        '        pass\n')],
                                      "the report reads a segmentation the caller may not read (RC-029)"),
    "R3_report_route_stores_the_assessment": ([(AIR, '        return await assess_dis(segmentation_id, segmentation_service, storage_service, store=False)\n',
                                                '        return await assess_dis(segmentation_id, segmentation_service, storage_service, store=True)\n')],
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
    "R8_dis_of_another_segmentation_carried_in": ([(AIR, '        if named and report_sid and named != report_sid:\n', '        if False:\n')],
                                                  "another segmentation's DIS or measurements carried into the report (review finding 2)"),
    "R9_regions_reach_the_model_unconfirmed": ([(AIR, '        findings["lesion_analysis"] = gate.without_region_breakdown(findings["lesion_analysis"])\n',
                                                 '        pass\n')],
                                               "regions of an unconfirmed segmentation reach the model (review finding 3)"),
    "R10_template_still_asks_for_dis": ([(BRS, '            system_prompt = dis_not_evaluated_template(system_prompt)\n', '            pass\n')],
                                        "the templates ask the model for a DIS table although DIS was not evaluated (review finding 4)"),
    "R11_model_dis_statement_kept": ([(AIR, '            content, replaced = gate.scrub_unevaluated_dis(result["content"], request.language)\n',
                                       '            content, replaced = result["content"], 0\n')],
                                     "a DIS statement written by the model stays in the draft (review finding 4)"),
    "R12_misleading_notice_wording": ([(AIR, '"in space; this draft must not be read as a statement on dissemination in space.",',
                                        '"in space; no statement on it in this draft comes from the software.",')],
                                      "the notice claims no DIS statement comes from the software (review finding 4)"),
    # ── RC-070 on the assistant path (MCP) ──
    "A1_assistant_receives_unevaluated_conclusion": ([(MCPS, '    if isinstance(dis, dict) and dis.get("evaluation_status") == "evaluated":\n',
                                                       '    if isinstance(dis, dict):\n')],
                                                     "the assistant receives a DIS conclusion that was not evaluated (older backend)"),
    "A2_assistant_rule_removed": ([(MCPS, MCP_RULE, '')],
                                  "the assistant is not told to report 'not evaluated' and never to derive DIS"),
    "A3_assistant_regions_without_caveat": ([(MCPS, '        "regions_note": REGIONS_ARE_NOT_DIS,\n', ''),
                                             (MCPS, ', "note": REGIONS_ARE_NOT_DIS}', '}')],
                                            "regions reach the assistant without 'not a DIS assessment' (review finding 3)"),
    "A4_assistant_report_without_its_segmentation": ([(MCPS, '            "segmentation_id": segmentation_id,\n', '')],
                                                     "the assistant's report request names no segmentation: DIS never evaluated (review finding 2)"),
    # ── RC-070: hash / spacing race (review finding 8) ──
    "S1_result_cached_for_a_changed_mask": ([(SA, '    if store and not any_external and still_stored:\n', '    if store and not any_external:\n')],
                                            "a result cached for a mask that changed during the assessment"),
    "S2_no_snapshot": ([(SA, '    masks_3d = np.array(seg_data["masks_3d"], dtype=np.uint8, copy=True)   # snapshot\n',
                         '    masks_3d = seg_data["masks_3d"]\n')],
                       "the gate checks one mask and the rule reads another, edited during the spacing download"),
    # ── RC-072: information for safety (backend) ──
    "N1_not_evaluated_state_without_notice": ([(GATE, '    if state is not None and state.get("lesion_detection"):\n', '    if False:\n')],
                                              "the 'not evaluated' state of an automatic lesion segmentation without the healthy-brain notice"),
    "N2_notice_for_structure_parcellations": ([(GATE, '    lesion_detection = source == SOURCE_AI_DRAFT or (\n',
                                                '    lesion_detection = source != SOURCE_ORIGIN_NOT_RECORDED or (\n')],
                                              "the healthy-brain notice on SynthSeg / mindGlide structures, where it is wrong (review finding 9)"),
    # ── frontend: the dashboard, the panels, the cards ──
    "F1_display_trusts_any_conclusion": ([(TYPES, "(d as { evaluation_status?: unknown }).evaluation_status === 'evaluated'",
                                           "'dis_met_brain' in (d as object)")],
                                         "the dashboard shows met / not met for a block that was not evaluated"),
    "F2_topographies_panel_for_unevaluated": ([(DASH, "      {disOk && (\n        <div className=\"p-2 rounded-lg bg-indigo-950/30",
                                                "      {dis && (dis as any).total_topographies_involved !== undefined && (\n        <div className=\"p-2 rounded-lg bg-indigo-950/30")],
                                              "the five-topography panel shown for any block"),
    "F3_confirm_offered_with_unsaved_changes": ([(DASH, "                  ) : hasUnsavedMaskChanges ? (\n", "                  ) : false ? (\n")],
                                                "the confirm button offered while the mask on screen is not the saved one"),
    "F4_confirmation_not_bound_to_the_mask": ([(DASH, "confirmSegmentationReview(segmentationId, digest)",
                                                "confirmSegmentationReview(segmentationId, '0'.repeat(64))")],
                                              "the confirmation does not send the SHA-256 of the mask on screen"),
    "F5_confirm_offered_before_classification": ([(DASH, "              && (reason === 'segmentation_not_confirmed' || reason === 'confirmation_outdated');",
                                                   "              && true;")],
                                                 "the confirm button offered before the regions are classified (review blocker 1)"),
    "F6_card_without_notice": ([(DASH, "                {lesionTool && <AutomaticMarkingNotice />}", "                {false && <AutomaticMarkingNotice />}")],
                               "the 'not evaluated' card of an automatic lesion segmentation without the notice"),
    "F7_banner_without_notice": ([(BANNER, '      <AutomaticMarkingNotice className="text-[10px] leading-snug" />\n', '')],
                                 "the AI draft banner without the healthy-brain notice"),
    "F8_panel_notice_for_any_tool": ([(PANEL, "                      && isLesionDetectionSource(openValidationSource) && (",
                                       "                      && true && (")],
                                     "the panel notice on structure parcellations (review finding 9)"),
    "F9_notice_english_in_spanish": ([(ES, ES_NOTICE, ES_NOTICE_EN)],
                                     "the healthy-brain notice shown in English to Spanish-language users"),
    "F10_confirmed_by_not_shown": ([(DASH, "            {disOk.segmentation_review?.reviewed_by && (", "            {false && (")],
                                   "a DIS result shown without the radiologist whose confirmation it rests on"),
    "F11_no_refresh_after_confirmation": ([(DASH, "      await refreshDis();\n    } catch (e: any) {\n",
                                            "      void 0;\n    } catch (e: any) {\n")],
                                          "after the confirmation the card keeps the old state"),
    "F12_result_shown_for_unsaved_changes": ([(DASH, "  const disOk = isDisEvaluated(dis) && !disHeldForUnsavedChanges ? dis : null;\n",
                                               "  const disOk = isDisEvaluated(dis) ? dis : null;\n")],
                                             "a result shown for a mask on screen that is no longer the confirmed one"),
    "F13_no_refresh_after_saving": ([(DASH, "    if (isOpen && hadUnsavedChanges.current && !hasUnsavedMaskChanges && dis) void refreshDis();\n",
                                      "    if (false) void refreshDis();\n")],
                                    "after saving a changed mask the panel keeps the result of the confirmed mask"),
    "F14_confirm_offered_on_another_segmentation": ([(DASH, "                  !isOpen ? (\n", "                  false ? (\n")],
                                                    "the button confirms an expanded segmentation with the open mask's digest (review finding 7)"),
    "F15_late_reply_overwrites": ([(DASH, "      if (ticket === disSeq.current) setDis(r);\n", "      setDis(r);\n")],
                                  "an older DIS reply overwrites a newer state (review finding 8)"),
    "F16_regions_without_caveat": ([(DASH, "      {analysis && analysis.lesions.length > 0 && !disOk && (\n", "      {false && (\n")],
                                   "regions of an unconfirmed segmentation shown without 'not a DIS assessment' (review finding 3)"),
    "F17_tool_card_notice_for_any_tool": ([(TOOLS, "          {isLesionDetectionSource(task.validation_source) && <AutomaticMarkingNotice />}",
                                            "          {true && <AutomaticMarkingNotice />}")],
                                          "the healthy-brain notice on a SynthSeg result (review finding 9)"),
    "F18_flames_card_without_notice": ([(FLAMES, "          <AutomaticMarkingNotice />\n          {grid && !grid.ok",
                                         "          {grid && !grid.ok")],
                                       "the in-browser FLAMeS result without the notice (review finding 9)"),
    "F19_report_without_its_segmentation": ([(REPORT, "      ...(activeSegId ? { segmentation_id: activeSegId } : {}),\n", "")],
                                            "the report request names no segmentation (review finding 2)"),
    "F20_dashboard_without_error_boundary": ([(VIEWER, '<ErrorBoundary name="LesionDashboard">\n                                <LesionDashboard',
                                               '<>\n                                <LesionDashboard'),
                                              (VIEWER, '                                />\n                                </ErrorBoundary>\n                              </div>',
                                               '                                />\n                                </>\n                              </div>')],
                                             "a failure of the lesion panel takes the viewer down (review finding 10)"),
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
