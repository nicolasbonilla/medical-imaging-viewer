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
                 "tests/unit/test_prb003_review1_findings.py",
                 "tests/unit/test_prb003_review2_findings.py",
                 "tests/unit/test_prb003_review3_findings.py"]
FRONTEND_TESTS = ["src/components/LesionDashboard.prb003.test.tsx",
                  "src/components/LesionDashboard.prb003.review1.test.tsx",
                  "src/components/LesionDashboard.prb003.review2.test.tsx",
                  "src/components/LesionDashboard.prb003.review3.test.tsx",
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
CONFIRMED_LINE = '    confirmed = bool(regions_ok and ai_review_ok and bound)\n'

M = {  # name: ([(file, anchor, replacement), ...], what it re-introduces)
    # ── RC-070: the gate (backend) ──
    "G1_route_gate_bypassed": ([(SA, '    if not state["confirmed"]:\n        logger.info("DIS not evaluated',
                                 '    if False:\n        logger.info("DIS not evaluated')],
                               "DIS computed on any loaded segmentation (the defect as found: paper A, 19/100 healthy)"),
    "G2_confirmation_not_bound_to_the_mask": ([(GATE, '    bound = (has_record and getattr(record, "reviewed_mask_sha256", None) == current\n',
                                                '    bound = (has_record\n')],
                                              "a confirmation given for another mask counts"),
    "G2b_confirmation_not_bound_to_the_labels": ([(GATE, '             and getattr(record, "reviewed_labels_sha256", None) == labels_digest\n',
                                                   '             and True\n')],
                                                 "a confirmation survives a renaming of the labels (review finding 6)"),
    "G3_unreviewed_ai_draft_counts": ([(GATE, '        provenance.review_status == "confirmed" and provenance.reviewed_mask_sha256 == current)',
                                       '        True)')],
                                      "an unreviewed AI draft counts as reviewed"),
    "G4_ai_review_not_required": ([(GATE, CONFIRMED_LINE, '    confirmed = bool(regions_ok and bound)\n')],
                                  "an AI draft evaluated without its own review (RC-047)"),
    "G5_stored_state_served_as_a_result": ([(SA, '            and dis_gate.is_evaluated(cached.get("dis_assessment"))\n',
                                             '            and "dis_assessment" in cached\n')],
                                           "a stored DIS block (not evaluated, or from before the fix) served as a result"),
    "G6_metadata_route_serves_stored_dis": ([(SEG, 'dis_gate.metadata_for_viewer(dis_gate.without_stored_dis(metadata), current_user)',
                                              'dis_gate.metadata_for_viewer(metadata, current_user)')],
                                            "the stored DIS block reaches the viewer with the segmentation metadata"),
    "G7_list_route_serves_stored_dis": ([(SEG, 'dis_gate.metadata_for_viewer(dis_gate.without_stored_dis(r.metadata), current_user)',
                                          'dis_gate.metadata_for_viewer(r.metadata, current_user)')],
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
    "G12_classification_not_bound_to_the_lesions": ([(GATE, '            and record.get("classified_lesion_footprint_sha256") == footprint_sha256(masks_3d)):\n',
                                                      '            and True):\n'),
                                                     (GATE, '    if len(by_first) != len(lesions) or any(by_first.get(les["first"], (None,))[0] != les["voxels"]\n',
                                                      '    if False and any(by_first.get(les["first"], (None,))[0] != les["voxels"]\n')],
                                                    "MAGNIMS names on lesions that never went through the classification count as regions"),
    "G13_any_label_scheme_is_magnims": ([(GATE, '    if any(pairs.get(i) != MAGNIMS_REGIONS[i] for i in MAGNIMS_REQUIRED_IDS):\n        return False\n',
                                         '    if False:\n        return False\n'),
                                        (GATE, '    return all(MAGNIMS_REGIONS.get(i) == name for i, name in pairs.items())\n',
                                         '    return True\n')],
                                       "the default preset (1 = MS Lesion Active) read as regions: a false MET (review blocker 1)"),
    # Third review of PR #68, m-3: the statement is replaced by `pass` (removing the only statement of the `if` block
    # gave an IndentationError, so the mutation only broke the import).
    "G14_classification_does_not_record_the_lesions": ([(SR, '            response_data.update(dis_gate.classification_record(classified_mask, voxel_spacing))\n',
                                                         '            pass\n')],
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
    "C6_confirmation_before_classification": ([(SEG, '    if not regions["classified"]:\n', '    if False:\n')],
                                              "the confirmation accepted before the regions are classified (review blocker 1)"),
    "C7_second_confirmation_overwrites_the_first": ([(SEG, '    already = bool(state["confirmed"])\n', '    already = False\n')],
                                                    "a repeat confirmation replaces the first confirmer (review finding 5)"),
    "C8_confirmation_not_in_the_history": ([(SEG, '    metadata.clinician_review_history = dis_gate.capped_history([*previous[1], event])',
                                             '    metadata.clinician_review_history = dis_gate.capped_history(previous[1])')],
                                           "confirmations leave no history (review finding 5)"),
    "C9_voiding_not_in_the_history": ([(SVC, '        metadata.clinician_review_history = capped_history([*(metadata.clinician_review_history or []), ClinicianReviewEvent(',
                                        '        _unrecorded = capped_history([*(metadata.clinician_review_history or []), ClinicianReviewEvent(')],
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
    "R1_report_trusts_the_client_block": ([(AIR, '            await server_dis_assessment(report_sid, current_user))\n',
                                            '            findings.get("dis_assessment") or {})\n')],
                                          "a DIS conclusion sent by the client reaches the model (the defect as found)"),
    "R2_report_skips_authorization": ([(AIR, '        await authorize_mask_specs([{"type": "segmentation", "id": report_sid}], current_user)\n',
                                        '        pass\n')],
                                      "the report reads a segmentation the caller may not read (RC-029)"),
    "R3_report_route_stores_the_assessment": ([(AIR, '        return await assess_dis(segmentation_id, segmentation_service, storage_service, store=False)\n',
                                                '        return await assess_dis(segmentation_id, segmentation_service, storage_service, store=True)\n')],
                                              "the compute-only report route writes to the segmentation (RC-033)"),
    # Release 2026-10-25 (integration review of PR #69, item 3): the builder calls the one rule, gate.is_evaluated;
    # the anchor moved to that line, the mutation is unchanged.
    "R4_prompt_states_met_for_an_unevaluated_block": ([(BRS, '        if not gate.is_evaluated(dis):\n',
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
    "F10_confirmed_by_not_shown": ([(DASH, "            {disOk.segmentation_review && (", "            {false && (")],
                                   "a DIS result shown without the radiologist whose confirmation it rests on"),
    # Release 2026-10-25 (capture finding F10): the refresh after the confirmation is one awaited read of the DIS state
    # (with a pending state); the anchor moved to it, the mutation is unchanged (no refresh).
    "F11_no_refresh_after_confirmation": ([(DASH, "        await fetchDis();\n      } catch (refreshError) {\n",
                                            "        void 0;\n      } catch (refreshError) {\n")],
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
    # ── second review of PR #68 (at 29abe29): N1 one region per lesion, corrections acknowledged ──
    "W1_lesion_labels_not_checked": ([(GATE, '    regions_ok = bool(regions["classified"] and regions["lesions_valid"])\n',
                                       '    regions_ok = bool(regions["classified"])\n')],
                                     "a lesion with two regions or relabelled Active (Gd+) is evaluated (N1: false MET / NOT MET)"),
    "W2_active_or_black_hole_counts_as_a_region": ([(GATE, '        if len(les["labels"]) != 1 or les["labels"][0] not in DIS_REGION_IDS:\n',
                                                     '        if len(les["labels"]) != 1:\n')],
                                                   "a lesion relabelled 5 (Active Gd+) or 6 keeps its place in the DIS rule (N1, probe p2c)"),
    "W3_lesion_split_between_regions_counts": ([(GATE, '        if len(les["labels"]) != 1 or les["labels"][0] not in DIS_REGION_IDS:\n',
                                                 '        if les["labels"][0] not in DIS_REGION_IDS:\n')],
                                               "one lesion half-painted another region counts as two (N1, probe p2b)"),
    "W4_corrections_not_bound_to_the_confirmation": ([(GATE, '             and acknowledged == regions["corrections_sha256"])\n',
                                                       '             and True)\n')],
                                                     "a confirmation of mask + labels covers region corrections it never acknowledged (N1, probe p2d)"),
    "W5_corrections_not_detected": ([(GATE, '        elif les["labels"][0] != classified_region:\n', '        elif False:\n')],
                                    "regions changed by hand after the classification are not listed (N1)"),
    "W6_confirmation_without_acknowledgement": ([(SEG, '    if (regions["correction_count"] or acknowledged) and acknowledged != regions["corrections_sha256"]:\n',
                                                  '    if False:\n')],
                                                "the confirmation accepted without acknowledging the corrections listed (N1)"),
    "W7_confirmation_with_invalid_lesions": ([(SEG, '    if regions["lesions_valid"] is False:   # second review', '    if False:   # second review')],
                                             "the confirmation accepted while a lesion carries no region or two (N1)"),
    "W8_classification_without_lesion_regions": ([(GATE, '        "classified_lesion_regions": [\n', '        "classified_lesion_regions_unused": [\n')],
                                                  "classify-regions records no region per lesion: corrections cannot be found (N1)"),
    "W9_corrections_not_recorded_in_the_confirmation": ([(SEG, '        region_correction_count=regions["correction_count"], region_corrections=regions["corrections"],\n',
                                                          '        region_correction_count=0, region_corrections=[],\n')],
                                                        "the confirmation does not record the corrections it acknowledges (N1)"),
    "WF1_corrections_not_listed": ([(DASH, "                {!!pendingRegions?.correction_count && (", "                {false && (")],
                                   "the card does not list the region corrections (N1)"),
    "WF2_confirm_without_acknowledgement": ([(DASH, "    if (correctionsDigest && ackedCorrections !== correctionsDigest) return;\n", ""),
                                             (DASH, "disabled={confirmBusy || (!!correctionsDigest && ackedCorrections !== correctionsDigest)}",
                                              "disabled={confirmBusy}")],
                                            "the confirmation is sent without the explicit acknowledgement (N1)"),
    "WF3_acknowledgement_not_sent": ([(DASH, "confirmSegmentationReview(segmentationId, digest, correctionsDigest)",
                                       "confirmSegmentationReview(segmentationId, digest)")],
                                     "the acknowledged corrections are not sent with the confirmation (N1)"),
    "WF4_dialog_without_the_corrections": ([(DASH, "      correctionsDigest\n        ? `${question}", "      false\n        ? `${question}")],
                                           "the confirm dialog does not list the corrections (N1)"),
    "WF5_invalid_lesions_not_listed": ([(DASH, ") : reason === 'lesion_labels_invalid' ? (", ") : false ? (")],
                                       "the card does not say which lesion carries no region or two (N1)"),
    "WF6_edit_after_classification_not_shown": ([(DASH, "                {pendingRegions?.edited_after_classification && (", "                {false && (")],
                                                "edited_after_classification computed but never shown (N1, as found)"),
    "WF7_confirmed_corrections_not_shown": ([(DASH, "            {!!disOk.regions?.correction_count && (", "            {false && (")],
                                            "an evaluated result does not say it includes acknowledged corrections (N1)"),
    # ── N3: the output check (a backstop) ──
    "W10_markup_not_normalised": ([(GATE, '    t = re.sub(r"[*_`~]+", "", t)\n', '')],
                                  "'dissemination in **space**' passes the output check (N3)"),
    "W11_hyphens_not_normalised": ([(GATE, '    t = re.sub(r"(?<=\\w)[\\-\\u2010\\u2011\\u2012\\u2013\\u2014](?=\\w)", " ", t)\n', '')],
                                   "'Dissemination-in-space' passes the output check (N3)"),
    "W12_accents_not_removed": ([(GATE, '    t = "".join(c for c in t if not unicodedata.combining(c))\n', '')],
                                "Spanish and German wordings with accents pass the output check (N3)"),
    "W13_whole_paragraph_replaced": ([(GATE, '        for unit, space in _units(body):\n', '        for unit, space in [(body, "")]:\n')],
                                     "the whole paragraph is replaced, not the statement (N3: over-removal as found)"),
    "W14_wrapped_lines_not_joined": ([(GATE, '            while (j < len(lines) and lines[j].strip()', '            while (False and lines[j].strip()')],
                                     "a sentence wrapped over two lines passes the output check (N3)"),
    "W15_region_tables_kept": ([(GATE, '            if hits:\n', '            if False:\n')],
                               "a region table ('| Periventricular | Present |') stays in the draft (N3)"),
    "W16_not_evaluated_excuses_a_claim": ([(GATE, '    if _DIS_TERMS.search(n):\n        return True\n',
                                            '    if "not evaluated" in n:\n        return False\n    if _DIS_TERMS.search(n):\n        return True\n')],
                                          "a sentence saying 'not evaluated' and claiming DIS stays (N3, as found)"),
    "W17_region_presence_not_caught": ([(GATE, '    return named >= 2 or (named == 1 and bool(_PRESENCE.search(n)))\n', '    return False\n')],
                                       "'lesions in periventricular and juxtacortical regions' stays in the draft (N3)"),
    "W18_region_headings_kept": ([(GATE, '            if _regions_named(n) and not _DIS_TERMS.search(n):\n', '            if False:\n')],
                                 "a per-region heading stays in the draft (N3)"),
    "W19_german_terms_missing": ([(GATE, '    r"\\b(?:raumlich|ortlich)\\w*\\s+(?:dissemin\\w*|streuung|ausbreitung|verteilung|aussaat)",\n', '')],
                                 "'örtliche Dissemination' / 'räumliche Streuung' pass the output check (N3)"),
    "W20_spanish_terms_missing": ([(GATE, '    r"\\b(?:diseminacion|distribucion)\\s+espacial",\n', '')],
                                  "'diseminación espacial' passes the output check (N3)"),
    "W21_replaced_count_not_stated": ([(AIR, '    if replaced:\n        parts.append(DIS_LINES_REPLACED[lang].format(n=replaced))\n',
                                        '    if False:\n        parts.append(DIS_LINES_REPLACED[lang].format(n=replaced))\n')],
                                      "the draft does not say how many statements were replaced (N3)"),
    # ── N4: the not-evaluated templates ──
    "W22_region_sections_kept": ([(BRS, '    text = _REGION_SECTION.sub(_one_section, text)\n', '')],
                                 "the not-evaluated templates still ask for per-region sections (N4, as found)"),
    "W23_region_columns_kept": ([(BRS, '    for pattern, replacement in _REGION_LINE_EDITS:\n', '    for pattern, replacement in ():\n')],
                                "the not-evaluated templates still ask for a region column / regional distribution (N4)"),
    # ── N5: who confirmed ──
    "W24_names_and_history_to_every_role": ([(GATE, '    if metadata is None or sees_reviewer_identity(user):\n', '    if True:\n')],
                                            "names, ids and the history go to every role with patient access (N5, as found)"),
    "W25_dis_names_the_confirmer_to_every_role": ([(GATE, '    return block if sees_reviewer_identity(user) else without_reviewer_identity(block)\n', '    return block\n')],
                                                  "the DIS state names the confirmer to every role (N5)"),
    "W26_identity_roles_widened": ([(GATE, 'REVIEWER_IDENTITY_ROLES = frozenset({"radiologist", "admin"})',
                                     'REVIEWER_IDENTITY_ROLES = frozenset({"radiologist", "admin", "technician", "viewer"})')],
                                   "technicians and viewers see who confirmed (N5)"),
    "W27_history_unbounded": ([(GATE, '    return events[-REVIEW_HISTORY_CAP:]\n', '    return events\n')],
                              "the confirmation history grows without limit (N5, as found)"),
    "W28_assistant_receives_names": ([(MCPS, '        return _without_reviewer_names(dis)\n', '        return dis\n')],
                                     "the AI assistant receives the confirmer's user name (N5, as found)"),
    "W29_report_model_receives_names": ([(AIR, '        findings["dis_assessment"] = gate.without_reviewer_identity(\n',
                                          '        findings["dis_assessment"] = (\n')],
                                        "the report model receives the confirmer's user name (N5)"),
    "WF8_name_required_to_say_confirmed": ([(DASH, "                  : t('disReview.confirmedByRadiologist', 'Segmentation confirmed by a radiologist')}",
                                             "                  : ''}")],
                                           "without the name (other roles) the card does not say a radiologist confirmed (N5)"),
    # ── N6: only the review fields are written ──
    "W30_whole_document_written": ([(SVC, '                doc_ref.update(fields, option=self.db.write_option(last_update_time=update_time))\n',
                                     '                doc_ref.set({**metadata.model_dump(mode="json"), **fields})\n')],
                                   "the confirmation rewrites the whole metadata document from the cached copy (N6, as found)"),
    "W31_no_update_time_precondition": ([(SVC, '                doc_ref.update(fields, option=self.db.write_option(last_update_time=update_time))\n',
                                          '                doc_ref.update(fields)\n')],
                                        "a document changed between the read and the write is overwritten (N6)"),
    "W32_history_not_merged": ([(SVC, '            for event in [*(stored.get("clinician_review_history") or []), *ours]:\n',
                                 '            for event in ours:\n')],
                               "history events written by another instance are lost (N6)"),
    "W33_conflict_reported_as_failure": ([(SVC, '            if isinstance(e, FailedPrecondition):\n', '            if False:\n')],
                                         "a concurrent change is reported as 'not stored' instead of a conflict to reload (N6)"),
    # ── N7: the report's lesion table ──
    "W34_client_lesion_table_used": ([(AIR, '        findings["lesion_analysis"] = await server_lesion_table(report_sid)\n', '        pass\n')],
                                     "a client lesion table (without segmentation_id) reaches the model (N7, as found)"),
    "W35_failed_table_replaced_silently": ([(AIR, '        logger.error(f"[Report] Lesion measurements could not be computed for the report: {e}")\n',
                                             '        return {"total_count": 0}\n')],
                                           "a lesion table that could not be computed is replaced by an empty one (N7)"),
    # ── third review of PR #68 (at 2e20b8a): m-1 lesions named as the lesion table names them ──
    "W36_raster_numbering": ([(GATE, '        where = {"lesion": head["lesion"],', '        where = {"lesion": lesions.index(les) + 1,')],
                             "the correction list numbers lesions in raster order, not as the lesion table (m-1, as found)"),
    "W37_small_components_numbered": ([(GATE, '        e["small_component"] = not meets_min_volume(e["voxels"], voxel_volume_mm3)\n',
                                        '        e["small_component"] = False\n')],
                                      "a component below the lesion-size floor gets a lesion number the table does not have (m-1)"),
    "W38_slice_of_the_first_voxel": ([(GATE, '"slice": int(math.floor(round(float(centroid[0]), 1) + 0.5))})',
                                       '"slice": int(first_of[comp]) // (mask.shape[1] * mask.shape[2])})')],
                                     "the list gives another slice than the one the table row opens (m-1)"),
    "W39_raster_order_not_size_order": ([(GATE, '    entries.sort(key=lambda e: -e["voxels"])', '    entries.sort(key=lambda e: e["first"])')],
                                        "lesions numbered in raster order instead of the table's size order (m-1)"),
    "W40_voxel_volume_not_recorded": ([(GATE, '        "voxel_volume_mm3": float(np.prod(voxel_spacing)),\n', '')],
                                      "classify-regions records no voxel volume: lesions cannot be named as the table (m-1)"),
    "WF9_parts_not_listed": ([(DASH, "                          {les.parts?.length ? (", "                          {false ? (")],
                             "a lesion with two labels is not listed part by part (m-1)"),
    "WF10_small_component_not_named": ([(DASH, "    return c.small_component\n      ? fill(t('disReview.smallComponentCorrection'",
                                         "    return false\n      ? fill(t('disReview.smallComponentCorrection'")],
                                       "a correction of a small component is shown as a numbered lesion (m-1)"),
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
