"""Negative controls for the release integration of 2026-10-25 (PRs #66, #65, #67, #68).

The four PRs keep their own negative-control scripts (prb002_, capa015_, capa014_, prb003_negative_controls.py);
they are re-run on the integrated tree. This script covers only the decisions taken AT the integration, which none
of those scripts can see (docs/iec62304/records/releases/RELEASE-2026-10-25_integration_notes.md):

  I1/I1b  PRB-003's output check runs on the model's text only, before CAPA-014's draft assembly (merge notes of
          #67 and #68) — re-introduced: the check also, or only, runs on the assembled draft;
  I2      the template variant is chosen on the DIS block of the RC-064 payload (RC-064 amended);
  I3      #68's confirmation route is a recorded clinical action in CAPA-015's ROUTE_ACTIONS;
  I4-I6   conftest forces CAPA-015's in-memory backends and lifetimes after the PRB-002 guard (never setdefault).
Added after the independent integration review of PR #69 at 6d1fde2 (items 1-3 and 6):
  I7/I7b  unconfirmed regions: no region in the payload rows, a fixed "regions not confirmed" line in the prompt;
  I8      format characters (ZWJ, ZWSP) removed from the model's text BEFORE the DIS check;
  I9/I10  one "evaluated" rule (status AND a yes/no conclusion) for the route, the payload, the prompt and the template;
  I11/I12 the geometry 422 names itself and the report panel shows its own message.
Added after the browser capture session of the release build (2026-10-28):
  I13/I14/I16 F08 — the labels the server stored reach what the viewer draws, before the mask reload;
  I15/I17/I18 F09 — the components the classification removed are counted and named before the confirmation;
  I19/I20     F10 — the pending state after confirming;
  I21         F04 — a dash, not the escape text, in the per-region rows.
Added after the second independent review of PR #69 (2026-10-28):
  I22-I25 B1 — list caches refreshed, open from the server, fallback colour and warning for unlabelled values;
  I26-I30 B1/M3 — the confirmation refuses undrawn lesions (guard, eye toggle, overlay, opacity, stored opacity);
  I31-I35 M1/M2 — the removal belongs to the segmentation and survives a second classification;
  I36-I41 m1, m2, m4 (viewer, assistant), m5, n1.
  The canvas's own call of the fallback colours (SegmentationCanvasLocal) is not reachable from a jsdom test (no
  2D canvas); its helper is (I24), and the capture session checks the drawing.
Added after the film capture of the release build (2026-10-28, "DWM: 1 lesions"):
  I42/I43 the lesion counts of the dashboard: singular for one, in the user's language;
  I44/I45 the findings prompt says "1 lesion", and the RC-065 allow-list keeps both forms.
Added after the re-review of PR #71 (2026-10-29):
  I46/I47 the B1 fallback colour is cyan, apart from every preset colour (magenta is Active (Gd+)), and the
          warnings name it.
Added after the final check of PR #69 (2026-10-29):
  I48-I50 R1 — only the standard 2D view in segmentation mode publishes the segmentation it draws, and the
          confirmation needs it;
  I51-I53 R2 — the label preset is locked on a classified segmentation, and each value is drawn with its stored
          label;
  I54-I57 R2, server side — the drawn label table is sent, digested alike, served and checked.
Added at the merge with PR #71 (release 2026-10-30): I58 the stored table served and checked as drawn (#71's region
  colours); I59 one fallback colour definition. I46 and I54 re-anchored (the constant now lives in regionColors.ts;
  the route compares the table as drawn).

Method (as the other scripts): one mutation at a time in the real source; every anchor asserted to occur exactly
once (on the LF text, so a Windows CRLF checkout works); only the bound tests are run — backend offline (PRB-002: a
credentials file and a gcloud configuration folder that do not exist, an offline project id, no model-provider key),
frontend with vitest; the exact original bytes are restored after each mutation and verified at the end. The outer
environment also sets AUDIT_SINK_BACKEND / REFRESH_TOKEN_BACKEND to "firestore" and the access-token lifetime to 60
minutes, so a conftest that stops forcing its values is visible; the baseline must pass with that same environment.

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
GUARD = "backend/app/services/report_payload_guard.py"
GATE = "backend/app/services/dis_review_gate.py"
AMW = "backend/app/core/logging/audit_middleware.py"
CONF = "backend/tests/conftest.py"
PANEL = "frontend/src/components/AIReportPanel.tsx"

REL = "tests/unit/test_release_2026_10_25_integration.py"
REV = "tests/unit/test_release_2026_10_25_review_fixes.py"
CAPA015 = "tests/unit/test_capa015_audit_and_session.py"
PANEL_TEST = "frontend/src/components/AIReportPanel.release20261025.test.tsx"
# browser capture session of the release build (2026-10-28)
DASH = "frontend/src/components/LesionDashboard.tsx"
STORE = "frontend/src/store/useSegmentationStore.ts"
REGIONS = "backend/app/api/routes/segmentation_regions.py"
CAPTURE_UI = "frontend/src/components/LesionDashboard.release20261028.test.tsx"
CAPTURE_API = "tests/unit/test_release_2026_10_25_capture_fixes.py"
# second independent review of PR #69 (2026-10-28)
VIEWER = "frontend/src/ViewerApp.tsx"
DRAWN = "frontend/src/utils/drawnLabels.ts"
TYPES = "frontend/src/types/lesion.ts"
MCPS = "backend/app/mcp/ms_clinical_server.py"
UI_B = "frontend/src/components/LesionDashboard.release20261028b.test.tsx"
UI_C = "frontend/src/components/LesionDashboard.release20261028c.test.tsx"
UI_VIEWER = "frontend/src/ViewerApp.release20261028.test.tsx"
UI_STORE = "frontend/src/store/useSegmentationStore.release20261028.test.ts"
UI_DRAWN = "frontend/src/utils/drawnLabels.test.ts"
API_R2 = "tests/unit/test_release_2026_10_25_review2_fixes.py"
# film capture of the release build (2026-10-28): "DWM: 1 lesions"
UI_D = "frontend/src/components/LesionDashboard.release20261028d.test.tsx"
API_P = "tests/unit/test_release_2026_10_25_plural_counts.py"
# re-review of PR #71 (2026-10-29): the B1 fallback colour
UI_FALLBACK = "frontend/src/utils/drawnLabels.fallback.test.ts"
# final check of PR #69 (2026-10-29): R1, R2
VIEW2D = "frontend/src/components/ImageViewer2D.tsx"
APISEG = "frontend/src/api/segmentation.ts"
SEGROUTE = "backend/app/api/routes/segmentation.py"
UI_VIEWER29 = "frontend/src/ViewerApp.release20261029.test.tsx"
UI_DASH29 = "frontend/src/components/LesionDashboard.release20261029.test.tsx"
UI_DIGEST = "frontend/src/utils/drawnLabels.digest.test.ts"
API_FINAL = "tests/unit/test_release_2026_10_25_final_check.py"
# release 2026-10-30: merge with PR #71
REGCOL = "frontend/src/utils/regionColors.ts"
API_MERGE = "tests/unit/test_release_2026_10_30_merge.py"
UI_ONE_FALLBACK = "frontend/src/utils/fallbackColour.release20261030.test.ts"
EN = "frontend/src/i18n/locales/en.json"

ASSEMBLED = '        result = {**result, **parts, "content": draft_text(parts, request.language)}\n'
SCRUB = '            content, replaced = gate.scrub_unevaluated_dis(result["content"], request.language)\n'
I1_TEST = REL + "::test_rc070_release_i1_the_dis_check_changes_the_model_text_never_the_clinicians_entry"
R1_TEST = REV + "::test_rc064_release_r1_unconfirmed_regions_give_no_placeholder_and_no_app_note"
R2_TEST = REV + "::test_rc070_release_r2_zero_width_characters_do_not_hide_a_dis_statement"
R3_TEST = REV + "::test_rc070_release_r3_one_rule_decides_evaluated_for_route_prompt_and_template"
R6_TEST = REV + "::test_rc070_release_r6_unreadable_geometry_names_itself_and_the_panel_knows_the_phrase"

# name: ([(file, anchor, replacement), ...], bound tests (pytest node ids or a frontend test file), what it re-introduces)
M = {
    "I1_check_also_runs_on_the_assembled_draft": (
        [(AIR, ASSEMBLED, ASSEMBLED + "        if not dis_evaluated:\n"
                                      "            result[\"content\"] = gate.scrub_unevaluated_dis(result[\"content\"], "
                                      "request.language)[0]\n")],
        [I1_TEST],
        "PRB-003's output check also rewrites the assembled draft, including the clinician's typed entry"),
    "I1b_check_moved_after_the_draft_assembly": (
        [(AIR, SCRUB, '            content, replaced = result["content"], 0\n'),
         (AIR, ASSEMBLED, ASSEMBLED + "        if not dis_evaluated:\n"
                                      "            result[\"content\"], replaced = gate.scrub_unevaluated_dis("
                                      "result[\"content\"], request.language)\n")],
        [I1_TEST],
        "the output check runs after the draft assembly instead of before it (merge notes of #67 and #68)"),
    # Redefined after the integration review of PR #69 (item 3): with the one rule, the payload marks "evaluated"
    # exactly when gate.is_evaluated holds for the request's block, so choosing the template on the raw block ALONE is
    # now equivalent by construction (it went undetected on 2026-10-28, as expected). The mutation therefore
    # re-introduces the whole defect: the template on the raw block with its own status-only rule.
    "I2_template_variant_on_the_raw_block_with_its_own_rule": (
        [(BRS, '        dis_block = payload.findings.get("dis_assessment")\n',
          '        dis_block = findings.get("dis_assessment")\n'),
         (BRS, '        if not gate.is_evaluated(dis_block):\n',
          '        if not (isinstance(dis_block, dict) and dis_block.get("evaluation_status") == "evaluated"):\n')],
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
    "I7_unconfirmed_regions_sent_as_labels": (
        [(GUARD, '        confirmed = not (isinstance(status, dict) and status.get("confirmed") is False)\n',
          "        confirmed = True\n")],
        [R1_TEST],
        "unconfirmed regions reach the payload as labels: '[unlisted label 1] = not confirmed' and an app note"),
    "I7b_prompt_ignores_unconfirmed_regions": (
        [(BRS, '            regions_confirmed = la.get("regions_confirmed") is not False      # release 2026-10-25, item 1\n',
          "            regions_confirmed = True\n")],
        [R1_TEST],
        "the prompt has a region column of 'Unknown' and no 'regions not confirmed' line"),
    "I8_format_characters_removed_only_after_the_check": (
        [(AIR, '        result = {**result, "content": without_format_characters(result["content"])}\n', "")],
        [R2_TEST],
        "a zero-width joiner or space hides a DIS statement from PRB-003's output check (review item 2)"),
    "I9_evaluated_without_a_conclusion": (
        [(GATE, '            and isinstance(block.get("dis_met"), bool))\n', "            )\n")],
        [R3_TEST],
        "the one rule accepts an 'evaluated' block without a yes/no conclusion (review item 3)"),
    "I10_route_uses_its_own_status_only_rule": (
        [(AIR, '    dis_evaluated = gate.is_evaluated(findings.get("dis_assessment"))\n',
          '    dis_evaluated = (isinstance(findings.get("dis_assessment"), dict)\n'
          '                     and findings["dis_assessment"].get("evaluation_status") == "evaluated")\n')],
        [R3_TEST],
        "the route decides 'evaluated' by the status alone while the prompt and template need a conclusion (as on 6d1fde2)"),
    "I11_panel_shows_no_measurements_for_a_geometry_422": (
        [(PANEL, "                    ? (serverMessage(generateMutation.error).startsWith(GEOMETRY_UNREADABLE_PHRASE)\n",
          "                    ? (false\n")],
        [PANEL_TEST],
        "the report panel shows 'no measurements' for an unreadable image geometry (review item 6)"),
    "I12_geometry_422_without_its_phrase": (
        [(AIR, '                detail=(f"{GEOMETRY_UNREADABLE_PHRASE}: the lesion measurements of segmentation {segmentation_id} "\n',
          '                detail=(f"The lesion measurements of segmentation {segmentation_id} "\n')],
        [R6_TEST],
        "the server's geometry 422 no longer starts with the phrase the panel recognises"),
    # ── browser capture session of the release build (2026-10-28): F08, F09, F10, F04 ──
    "I13_classification_labels_not_applied_to_the_viewer": (
        [(DASH, "        useSegmentationStore.getState().applyServerLabels(segmentationId, result.labels ?? MAGNIMS_LESION_LABELS);\n",
          "")],
        [CAPTURE_UI],
        "F08: after the classification lesions labelled 2-4 are not drawn until the study is reopened"),
    "I14_server_labels_skip_the_drawn_segmentation": (
        [(STORE, "              activeSegmentation: activeMatches ? { ...active!, labels } : active,\n",
          "              activeSegmentation: active,\n")],
        [CAPTURE_UI],
        "F08: the labels reach currentSegmentation only, not what the 2D canvas and NiiVue draw from"),
    "I15_removed_components_not_counted": (
        [(REGIONS, "        gone = (sizes > 0) & (kept == 0)\n", "        gone = (sizes > 0) & (kept < 0)\n")],
        [CAPTURE_API],
        "F09: the classification removes small components from the mask without saying so"),
    "I16_labels_not_returned_by_the_classification": (
        [(REGIONS, '            response_data["labels"] = [\n', '            response_data["labels_not_returned"] = [\n')],
        [CAPTURE_API],
        "F08: the viewer cannot draw the server's label scheme (it is not returned)"),
    "I17_classification_card_silent_on_removed_components": (
        [(DASH, "            {removedText && (\n", "            {false && (\n")],
        [CAPTURE_UI],
        "F09: the classification card does not say which components were removed"),
    "I18_confirm_dialog_silent_on_removed_components": (
        [(DASH, "    const ok = window.confirm(confirmRemovedText ? `${dialogText}\\n\\n${confirmRemovedText}` : dialogText);\n",
          "    const ok = window.confirm(dialogText);\n")],
        [CAPTURE_UI],
        "F09: the radiologist confirms without being told that components were removed"),
    "I19_no_pending_state_after_confirming": (
        [(DASH, "            if (confirmPhase) {\n", "            if (false) {\n")],
        [CAPTURE_UI],
        "F10: the card keeps saying 'No radiologist has confirmed' for seconds after the confirmation"),
    "I20_confirmation_never_shown_as_recorded": (
        [(DASH, "      setConfirmPhase('refreshing');\n", "")],
        [CAPTURE_UI],
        "F10: the card does not say that the confirmation was recorded while the DIS state is read"),
    "I21_escape_text_in_region_rows": (
        [(DASH, "                    {region.lesion_count} {'\\u2014'} {region.total_volume_ml.toFixed(2)} mL\n",
          "                    {region.lesion_count} \\u2014 {region.total_volume_ml.toFixed(2)} mL\n")],
        [CAPTURE_UI],
        "F04: a literal escape text in the per-region rows"),
    # ── second independent review of PR #69: B1, M3, M1, M2, m1, m2, m4, m5, n1 ──
    "I22_list_caches_kept_after_classification": (
        [(DASH, "      void queryClient?.invalidateQueries({ queryKey: ['segmentations'] });\n", "")],
        [UI_B], "B1: the sidebar list fetched before the classification is used again on the next open"),
    "I23_open_from_the_cached_list": (
        [(VIEWER, "      fullSeg = await segmentationAPI.getSegmentation(segmentation.id);\n",
          "      fullSeg = segmentationsData?.find((s) => s.segmentation_id === segmentation.id);\n")],
        [UI_VIEWER], "B1: a segmentation is (re)opened with the labels of the stale sidebar list"),
    "I24_no_fallback_colour_for_unlabelled_values": (
        [(DRAWN, "  for (let id = 1; id <= 255; id++) if (!named.has(id)) out.push(id);\n", "")],
        [UI_DRAWN], "B1: a mask value without a label is left transparent"),
    "I25_no_warning_for_unlabelled_values": (
        [(VIEWER, "          {unlabelled.length > 0 && (\n", "          {false && (\n")],
        [UI_VIEWER], "B1: a mask value without a label is not announced"),
    "I26_confirmation_without_the_drawn_check": (
        [(DASH, "    if (maskReloadFailed || undrawn === null || undrawn.length > 0) {\n", "    if (false) {\n")],
        [UI_B], "B1/M3: a mask with undrawn lesions is confirmed"),
    "I27_hidden_label_not_checked": (
        [(DRAWN, "    } else if (input.labelVisibility[value] === false) {\n", "    } else if (false) {\n")],
        [UI_B], "M3: a label switched off with its eye toggle does not stop the confirmation"),
    "I28_overlay_switch_not_checked": (
        [(DRAWN, "  if (!input.isOverlayVisible) out.push({ kind: 'overlay_off' });\n", "")],
        [UI_B], "M3: the overlay switched off does not stop the confirmation"),
    "I29_low_opacity_not_checked": (
        [(DRAWN, "  if (!(input.lesionOpacity >= MIN_VISIBLE_LESION_OPACITY)) out.push({ kind: 'opacity_low', opacity: input.lesionOpacity });\n", "")],
        [UI_B], "M3: an invisible lesion opacity does not stop the confirmation"),
    "I30_invisible_opacity_restored_next_session": (
        [(STORE, "          return { ...current, ...stored, lesionOpacity: visible ? opacity : current.lesionOpacity };\n",
          "          return { ...current, ...stored };\n")],
        [UI_STORE], "M3: a stored opacity of 0 hides every lesion in the next session"),
    "I31_dis_state_without_the_removal": (
        [(GATE, '        "removed_small_components": (record.get("removed_small_components")\n',
          '        "removed_small_components": (None\n')],
        [API_R2 + "::test_rc070_release2_m1_the_dis_state_carries_the_removal_for_these_lesions_only"],
        "M1: the server's DIS state does not carry the removal of this segmentation"),
    "I32_dis_card_takes_the_open_segmentations_classification": (
        [(DASH, "  const confirmRemovedVals = removedValsOf(pendingRegions?.removed_small_components);\n",
          "  const confirmRemovedVals = removedValsOf(classification?.removed_small_components);\n")],
        [UI_C], "M1: the DIS card and the dialog show the removal of whichever classification was read"),
    "I33_reads_another_segmentations_analysis": (
        [(DASH, "    const cached = currentSegmentation?.segmentation_id === segmentationId\n", "    const cached = true\n")],
        [UI_C], "M1: a dashboard reads the open segmentation's analysis data, whichever it shows"),
    "I34_writes_into_another_segmentation": (
        [(DASH, "    if (!cur || cur.segmentation_id !== segmentationId) return;\n", "    if (!cur) return;\n")],
        [UI_C], "M1: a dashboard writes its results into the open segmentation of another"),
    "I35_second_classification_overwrites_the_removal": (
        [(REGIONS, '            if (isinstance(previous, dict) and previous_classification.get("classified_lesion_footprint_sha256")\n',
          '            if (False and previous_classification.get("classified_lesion_footprint_sha256")\n')],
        [API_R2 + "::test_rc070_release2_m2_a_second_classification_carries_the_earlier_removal_forward"],
        "M2: a second classification records 0 removed and erases the disclosure"),
    "I36_reload_failure_silent": (
        [(DASH, "        if (reloaded === false) {\n", "        if (false) {\n")],
        [UI_C], "m1: a failed reload after the classification is silent and does not block the confirmation"),
    "I37_classify_allowed_anywhere": (
        [(DASH, "          disabled={isClassifying || !(isOpen && !hasUnsavedMaskChanges)}\n", "          disabled={isClassifying}\n")],
        [UI_C], "m2: classifying a segmentation that is not open, or with unsaved changes, is offered"),
    "I38_viewer_evaluated_without_conclusion": (
        [(TYPES, "    && typeof (d as { dis_met?: unknown }).dis_met === 'boolean';\n", "    ;\n")],
        [UI_C], "m4: the viewer shows an evaluated block without a yes/no conclusion as a result"),
    "I39_assistant_evaluated_without_conclusion": (
        [(MCPS, '    if isinstance(dis, dict) and dis.get("evaluation_status") == "evaluated" and isinstance(dis.get("dis_met"), bool):\n',
          '    if isinstance(dis, dict) and dis.get("evaluation_status") == "evaluated":\n')],
        [API_R2 + "::test_rc070_release2_m4_the_assistant_needs_a_yes_no_conclusion_too"],
        "m4: the assistant passes an evaluated block without a yes/no conclusion"),
    "I40_recorded_but_unread_shows_not_confirmed": (
        [(DASH, "        setConfirmedUnread(true);\n", "")],
        [UI_C], "m5: 'No radiologist has confirmed' and the confirm button next to a recorded confirmation"),
    "I41_every_lesion_table_failure_called_geometry": (
        [(AIR, "        if isinstance(e, VoxelSpacingUnavailableError):\n", "        if True:\n")],
        [API_R2 + "::test_rc070_release2_n1_a_lesion_table_failure_names_its_real_reason"],
        "n1: every lesion-table failure is reported as an unreadable image geometry"),
    # ── film capture of the release build: "DWM: 1 lesions" ──
    "I42_dashboard_count_plural_for_one": (
        [(DASH, "  const [suffix, text] = n === 1 ? ['One', one] : ['Other', other];\n",
          "  const [suffix, text] = ['Other', other];\n")],
        [UI_D], "'DWM: 1 lesions' and '1 lesions' in the dashboard"),
    "I43_dwm_count_english_only": (
        [(DASH, "              {countText(t, 'lesions.dwmCount', disOk.dwm_lesion_count,\n",
          "              {countText(t, 'lesions.dwmCountUntranslated', disOk.dwm_lesion_count,\n")],
        [UI_D], "the deep-white-matter count of the DIS card in English whatever the user's language"),
    "I44_prompt_plural_for_one": (
        [(BRS, '    return f"{count} lesion" if count == 1 and not isinstance(count, bool) else f"{count} lesions"\n',
          '    return f"{count} lesions"\n')],
        [API_P], "the findings prompt says '1 lesions' and the model copies it into the report"),
    "I45_allow_list_without_the_plural": (
        [(BRS, "        for count in (1, 2):\n", "        for count in (1,):\n")],
        [API_P], "the RC-065 allow-list loses the plural word pairs (a real prompt's pairs are not the device's)"),
    # ── re-review of PR #71: the fallback colour of a value without a label ──
    "I46_fallback_colour_is_the_active_gd_magenta": (
        [(REGCOL, "export const UNLABELLED_FALLBACK_COLOR = '#00FFFF';\n",
          "export const UNLABELLED_FALLBACK_COLOR = '#FF00FF';\n")],
        [UI_FALLBACK], "a mask value without a label is drawn like an active (Gd+) lesion"),
    "I47_warning_names_magenta": (
        [(EN, "label table: drawn in cyan. Reopen the segmentation", "label table: drawn in magenta. Reopen the segmentation")],
        [UI_FALLBACK], "the warning names a colour the canvas does not use"),
    # ── final check of PR #69: R1 (the view on screen), R2 (the labels drawn are the labels stored) ──
    "I48_every_view_publishes_the_overlay": (
        [(VIEW2D, "  const drawnHere = renderMode === 'standard' && segmentationMode && currentSeries\n",
          "  const drawnHere = currentSeries\n")],
        [UI_VIEWER29], "R1: segmentation mode off, NiiVue or matplotlib still count as drawing the segmentation"),
    "I49_view_not_checked": (
        [(DRAWN, "  if (input.onScreen === false) out.push({ kind: 'not_on_screen' });\n", "")],
        [UI_DASH29], "R1: a confirmation from a view that does not draw the segmentation is accepted"),
    "I50_dashboard_ignores_the_view": (
        [(DASH, "      onScreen: state.overlayOnScreen === segmentationId,\n", "")],
        [UI_DASH29], "R1: the confirmation does not ask which segmentation the view on screen draws"),
    "I51_preset_not_locked": (
        [(VIEWER, "                disabled={presetLocked}\n", "")],
        [UI_VIEWER29], "R2: the label preset can be switched on a classified segmentation"),
    "I52_stored_labels_not_compared": (
        [(DRAWN, "    if (label && input.storedLabels) {\n", "    if (false) {\n")],
        [UI_DASH29], "R2: values drawn with other names or colours than the stored labels are confirmed"),
    "I53_dashboard_without_stored_labels": (
        [(DASH, "      storedLabels: pendingRegions?.classified ? (pendingRegions.stored_labels ?? null) : undefined,\n", "")],
        [UI_DASH29], "R2: the confirmation does not compare the drawn labels with the stored ones"),
    "I54_server_ignores_the_drawn_table": (
        [(SEGROUTE, '    if drawn_labels != dis_gate.drawn_labels_sha256(as_drawn):\n',
          '    if False:\n')],
        [API_FINAL + "::test_rc071_release_final_a_confirmation_drawn_with_other_labels_is_refused"],
        "R2: the server records a confirmation drawn with another label table"),
    "I55_drawn_table_not_sent": (
        [(APISEG, "        : { mask_sha256: maskSha256, drawn_labels_sha256: drawnLabelsSha256Hex },\n",
          "        : { mask_sha256: maskSha256 },\n")],
        [UI_DIGEST], "R2: the confirmation does not state the label table it was drawn with"),
    "I56_server_digest_case_sensitive": (
        [(GATE, '            rows.append({"id": lid, "name": str(get("name")), "color": str(get("color")).upper()})\n',
          '            rows.append({"id": lid, "name": str(get("name")), "color": str(get("color"))})\n')],
        [API_FINAL + "::test_rc071_release_final_drawn_labels_digest_is_the_shared_canonical_text"],
        "R2: the server digests the table differently from the browser (a correct client is refused)"),
    "I57_dis_state_without_stored_labels": (
        [(GATE, '        "stored_labels": stored_labels(labels),\n', "")],
        [API_FINAL + "::test_rc071_release_final_the_dis_state_serves_the_stored_label_table"],
        "R2: the DIS state does not serve the stored label table"),
    # ── release 2026-10-30, merge with PR #71 ──
    "I58_stored_table_not_as_drawn": (
        [(GATE, '    return [{**r, "color": shared.get(r["name"].strip().lower(), r["color"])} for r in _label_rows(labels)]\n',
          '    return _label_rows(labels)\n')],
        [API_MERGE], "a segmentation classified before #71, drawn in the shared region colours, cannot be confirmed"),
    "I59_two_fallback_colours": (
        [(DRAWN, "export { UNLABELLED_FALLBACK_COLOR } from './regionColors';\n",
          "export const UNLABELLED_FALLBACK_COLOR = '#00FFFF';\n")],
        [UI_ONE_FALLBACK], "the 2D canvas and the GPU / 3D views define their fallback colour separately (they can drift)"),
}
# Recorded with the result (integration review of PR #69, item 5: kept, and stated as by design).
NOTES = {
    "I6_access_lifetime_not_forced":
        "Detected by design through a start-up failure, not an assertion: with a 60-minute access token and a "
        "30-minute refresh idle limit the application's own start-up check (CAPA-015, RC-068) refuses to start, so the "
        "bound test module cannot even be collected and the suite goes red (pytest exit 4). That refusal is the "
        "protection the forced setting keeps out of the test suite.",
}
FRONTEND = {t for _e, tests, _w in M.values() for t in tests if t.startswith("frontend/")}
BACKEND_BOUND = sorted({t.split("::")[0] for _e, tests, _w in M.values() for t in tests if not t.startswith("frontend/")})


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


def run_backend(tests, env):
    r = subprocess.run([PY, "-m", "pytest", *tests, "-q", "-p", "no:cacheprovider", "-o", "log_cli=false"],
                       cwd="backend", capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
                       timeout=900)
    f = re.search(r"(\d+) failed", r.stdout)
    p = re.search(r"(\d+) passed", r.stdout)
    e = re.search(r"(\d+) error", r.stdout)
    return {"suite": "backend", "exit": r.returncode, "failed": int(f.group(1)) if f else 0,
            "passed": int(p.group(1)) if p else 0, "errors": int(e.group(1)) if e else 0,
            "failing_tests": sorted(set(re.findall(r"(?:FAILED|ERROR) \S+::(\S+)", r.stdout)))}


def run_frontend(test_file):
    out = os.path.join(tempfile.gettempdir(), "release_2026_10_25_vitest.json")
    if os.path.exists(out):
        os.remove(out)
    rel = test_file[len("frontend/"):]
    r = subprocess.run(f"npx vitest run {rel} --pool=threads --reporter=json --outputFile={out}", cwd="frontend",
                       shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    if not os.path.exists(out):
        return {"suite": "frontend", "exit": r.returncode, "failed": 0, "passed": 0, "errors": 1,
                "failing_tests": [], "error_files": ["vitest produced no report"]}
    d = json.load(open(out, encoding="utf-8"))
    res = [a for f in d["testResults"] for a in f["assertionResults"]]
    return {"suite": "frontend", "exit": r.returncode, "failed": sum(a["status"] == "failed" for a in res),
            "passed": sum(a["status"] == "passed" for a in res),
            "errors": sum(1 for f in d["testResults"] if f["status"] == "failed" and not f["assertionResults"]),
            "failing_tests": [a["title"] for a in res if a["status"] == "failed"]}


def run(tests, env):
    if all(t.startswith("frontend/") for t in tests):
        return run_frontend(tests[0])
    return run_backend(tests, env)


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
    tests_used = BACKEND_BOUND + sorted(FRONTEND)
    res = {"executed": datetime.datetime.now().isoformat(timespec="seconds"),
           "tree": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
           "method": "one mutation at a time; each anchor asserted to occur exactly once (LF text); only the bound "
                     "tests run (backend offline per PRB-002, with an outer environment asking for the Firestore "
                     "backends and a 60-minute access token that conftest must override; frontend with vitest); "
                     "bytes restored after each mutation and verified at the end",
           "hash_basis": "sha256 of the UTF-8 text with LF line endings",
           "source_sha256": {p: sha(text[p]) for p in files},
           "test_sha256": {t: sha(open(t if t.startswith("frontend/") else os.path.join("backend", t),
                                       encoding="utf-8").read().replace("\r\n", "\n")) for t in tests_used},
           "baseline": {}, "mutations": {}}
    with tempfile.TemporaryDirectory() as tmp:
        env = outer_env(tmp)
        res["baseline"] = {"backend": run_backend(BACKEND_BOUND, env),
                           "frontend": [run_frontend(t) for t in sorted(FRONTEND)]}
        print("baseline", res["baseline"], flush=True)
        base_bad = [b for b in [res["baseline"]["backend"], *res["baseline"]["frontend"]]
                    if b["failed"] or b["errors"] or not b["passed"]]
        if base_bad:
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
                if name in NOTES:
                    out["note"] = NOTES[name]
                res["mutations"][name] = out
                for path in touched:
                    open(path, "wb").write(raw[path])
                print(f"{name:52s} detected={out['detected']} {out['failing_tests'][:3]}", flush=True)
        finally:
            for p, b in raw.items():
                open(p, "wb").write(b)
        for p in files:   # the restore is byte-exact
            assert open(p, "rb").read() == raw[p], p
        res["restored"] = {"backend": run_backend(BACKEND_BOUND, env),
                           "frontend": [run_frontend(t) for t in sorted(FRONTEND)]}
    undetected = sorted(n for n, v in res["mutations"].items() if not v["detected"])
    res["summary"] = {"mutations": len(M), "detected": len(M) - len(undetected), "undetected": undetected}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"restored {res['restored']}; {res['summary']['detected']}/{len(M)} detected -> {OUT}")
    restored = [res["restored"]["backend"], *res["restored"]["frontend"]]
    bad = any(r["failed"] or r["errors"] for r in restored)
    return 1 if undetected or bad else 0


if __name__ == "__main__":
    sys.exit(main())
