"""Negative controls for the next safety round, PRB-028 .. PRB-031 (PENDING owner approval).

  PRB-028 (RC-090)  regions from the geometric fallback feed DIS only after the radiologist checked them lesion by
                    lesion (DIS state lists them; Confirm refused without the digest of the ticked list).
  PRB-029 (RC-091)  the AI-draft review runs the same check of the view on screen as the DIS confirmation (shared code)
                    and states the drawn label table, which the server checks.
  PRB-030 (RC-092)  both confirmations refused while the image under the mask is on another grid (browser: shape;
                    server: header shape and affine, same study).
  PRB-031 (RC-093)  both confirmations refused while a layer under the lesions is above 30 %; a high zone-map opacity is
                    not restored; the longitudinal overlay in the colour-blind-safe palette.

Each mutation re-introduces ONE defect the fix removed (or removes one sub-control it added) in the real source, one
at a time, IN A THROWAWAY WORKTREE of the commit (scripts/safety/prb004_throwaway_worktree.py: detached, created for
the run under the system temporary folder, node_modules a junction, removed afterwards; one safety run at a time), so
an interrupted run can never leave a mutation in the developer's checkout. The script:
  - refuses to start when a file it mutates, a test it runs or this script has uncommitted changes (the run uses
    the commit);
  - asserts every anchor occurs exactly once in the LF text (a Windows CRLF checkout works), writes the mutation with
    the file's own line endings, restores the exact original bytes after each mutation, at exit, on Ctrl+C and on
    SIGTERM/SIGBREAK/SIGHUP, and checks the restore byte for byte at the end;
  - runs only the bound tests of the mutated side — backend offline per PRB-002 (a credentials file and a gcloud
    configuration folder that do not exist, an offline project id, no model-provider key), frontend with vitest
    (--pool=threads, JSON reporter) on the test files bound to that mutation;
  - checks the baseline passes first, and records the failing test names per mutation.

Independent review of PR #74 (290e407), corrections m1, m2, m4, m5, m6, m7, m9: mutations G9, A3, R10, R11, U6-U8, Z1-Z3,
L3-L5 added; G4, A1 and L2 re-anchored on the corrected code (same defect re-introduced).

Run from the repository root, with the backend's Python (it needs the backend requirements) and frontend/node_modules:
    python scripts/safety/prb028_031_negative_controls.py              # every mutation
    python scripts/safety/prb028_031_negative_controls.py --only G     # only the mutations whose name starts with G
          (--only merges with the previous record, and refuses unless that record is of the same commit)
Output: docs/iec62304/records/risk_verification/PRB-028-031_negative_controls_2026-10-31.json
"""
import atexit
import datetime
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prb004_throwaway_worktree import throwaway_worktree, require_committed  # noqa: E402

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.chdir(REPO)
PY = os.path.join(REPO, "backend", "venv", "Scripts", "python.exe")
if not os.path.exists(PY):
    PY = sys.executable
OUT = "docs/iec62304/records/risk_verification/PRB-028-031_negative_controls_2026-10-31.json"
HARNESS = ["scripts/safety/prb004_throwaway_worktree.py"]

BACKEND = [
    "tests/unit/test_prb028_geometric_fallback_review.py",
    "tests/unit/test_prb029_prb030_confirm_view_checks.py",
    "tests/unit/test_prb003_dis_requires_confirmed_segmentation.py",
    "tests/unit/test_prb003_review1_findings.py",
    "tests/unit/test_prb003_review2_findings.py",
    "tests/unit/test_rc047_ai_draft_provenance.py",
    "tests/unit/test_release_2026_10_25_final_check.py",
    "tests/unit/test_release_2026_10_30_merge.py",
    # Independent review of PR #74 (m4, m7, m9):
    "tests/unit/test_prb028_031_review_findings.py",
]

# sources
GATE = "backend/app/services/dis_review_gate.py"
ROUTE = "backend/app/api/routes/segmentation.py"
GRID = "backend/app/services/displayed_image_check.py"
DASH = "frontend/src/components/LesionDashboard.tsx"
BANNER = "frontend/src/components/AiDraftBanner.tsx"
CHECK = "frontend/src/utils/confirmDrawCheck.ts"
DRAWN = "frontend/src/utils/drawnLabels.ts"
API = "frontend/src/api/segmentation.ts"
IV2 = "frontend/src/components/ImageViewer2D.tsx"
STORE = "frontend/src/store/useSegmentationStore.ts"
COLORS = "frontend/src/utils/regionColors.ts"
IFACE = "backend/app/core/interfaces/storage_interface.py"
GCS = "backend/app/services/storage_service.py"
LEGEND = "frontend/src/components/LongitudinalOverlayLegend.tsx"
PANEL_L = "frontend/src/components/LongitudinalResultPanel.tsx"

# frontend tests bound to each mutation
T28 = ["src/components/LesionDashboard.prb028.test.tsx", "src/components/LesionDashboard.prb028.review.test.tsx"]
T29 = ["src/components/AiDraftBanner.prb029.test.tsx", "src/components/AiDraftBanner.test.tsx",
       "src/components/AiDraftBanner.prb029.review.test.tsx"]
T30 = ["src/components/LesionDashboard.prb030.test.tsx"]
T30V = ["src/ViewerApp.prb030.test.tsx"]
T31 = ["src/components/LesionDashboard.prb031.test.tsx"]
T31S = ["src/store/useSegmentationStore.prb031.test.ts"]
T31C = ["src/components/SegmentationCanvasLocal.prb031.test.tsx"]
T31L = ["src/components/LongitudinalOverlayLegend.prb031.test.tsx"]
T31P = ["src/components/LongitudinalCompare.capa013.test.tsx"]
TZ = ["src/components/AiDraftBanner.prb029.review.test.tsx"]
TDIG = ["src/utils/drawnLabels.digest.test.ts"]
TDRAWN = ["src/components/LesionDashboard.release20261029.test.tsx", "src/components/LesionDashboard.release20261028b.test.tsx"]

M = {  # name: ([(file, anchor, replacement), ...], frontend tests (None: the backend tests), what it re-introduces)
    # ── PRB-028 (RC-090): geometric-fallback regions checked lesion by lesion — server ──
    "G1_geometric_regions_not_listed": (
        [(GATE, '    from_geometric = record.get("method") == GEOMETRIC_METHOD\n', "    from_geometric = False\n")], None,
        "a geometric-fallback classification is treated like the atlas: nothing to check lesion by lesion (the defect as found)"),
    "G2_corrected_lesions_listed_too": (
        [(GATE, "        elif from_geometric:\n", "        if from_geometric:\n")], None,
        "a lesion the radiologist already corrected must be ticked again as if still at its geometric region"),
    "G3_digest_without_the_region": (
        [(GATE, '    canonical = json.dumps([[g["first_voxel"], g["region"]] for g in lesions], separators=(",", ":"))\n',
          '    canonical = json.dumps([[g["first_voxel"]] for g in lesions], separators=(",", ":"))\n')], None,
        "the digest of the checked list does not bind the region each lesion was checked with"),
    "G4_record_does_not_bind_the_review": (
        [(GATE, "    geometric_ok = regions[\"geometric_region_count\"] == 0 or checked == regions[\"geometric_regions_sha256\"]\n",
          "    geometric_ok = True\n")], None,
        "a confirmation recorded without the per-lesion review makes DIS evaluable on a geometric classification"),
    "G5_reason_not_named": (
        [(GATE, "    elif has_record and not geometric_ok:\n        reason = REASON_GEOMETRIC_REVIEW\n", "")], None,
        "a confirmation without the per-lesion review is reported as 'not confirmed', not why"),
    "G6_confirm_without_the_review": (
        [(ROUTE, '    if (geometric_count or checked) and checked != regions["geometric_regions_sha256"]:\n',
          "    if False:\n")], None,
        "the DIS confirmation accepted without the digest of the geometric regions checked one by one (the defect as found)"),
    "G7_more_than_the_list_accepted": (
        [(ROUTE, "    if geometric_count > dis_gate.LESION_LIST_CAP:\n", "    if False:\n")], None,
        "more geometric-fallback lesions than the list holds: confirmed although some could not be shown to be checked"),
    "G8_review_not_recorded": (
        [(ROUTE, '        reviewed_geometric_regions_sha256=regions["geometric_regions_sha256"],\n',
          "        reviewed_geometric_regions_sha256=None,\n")], None,
        "the confirmation does not record which geometric regions were checked (DIS stays unevaluable)"),
    # ── PRB-029 (RC-091): the AI-draft review states the drawn label table — server ──
    "A1_ai_review_without_the_drawn_labels": (
        [(ROUTE, "        problem = _drawn_labels_problem(body, metadata)                          # PRB-029 (RC-091)\n",
          "        problem = None\n")], None,
        "the AI-draft review accepted whatever labels the mask was drawn with (the defect as found)"),
    "A2_drawn_label_table_not_compared": (
        [(ROUTE, "    if drawn_labels != dis_gate.drawn_labels_sha256(as_drawn):\n        return (", "    if False:\n        return (")],
        None, "the shared server check no longer compares the drawn label table with the stored one (both confirmations)"),
    # ── PRB-030 (RC-092): the image under the mask on the mask's grid — server ──
    "R1_ai_review_image_not_checked": (
        [(ROUTE, "        problem = await _displayed_image_problem(body, metadata, entry[\"masks_3d\"], storage_service,\n"
                 "                                                 current_user)                   # PRB-030 (RC-092)\n",
          "        pass\n")], None,
        "the AI-draft review accepted over an image of another grid (the defect as found)"),
    "R2_dis_confirmation_image_not_checked": (
        [(ROUTE, "        problem = await _displayed_image_problem(body, metadata, entry[\"masks_3d\"], storage_service, current_user)\n",
          "        pass\n")], None,
        "the DIS confirmation accepted over an image of another grid (the defect as found)"),
    "R3_image_not_stated_accepted": (
        [(GRID, "    if not displayed:\n        return NOT_STATED\n", "    if not displayed:\n        return None\n")], None,
        "a confirmation that does not say which image was under the mask is accepted (an old or another client)"),
    "R4_other_visit_accepted": (
        [(GRID, "        if (shown.patient_id, shown.study_id) != (segmented.patient_id, segmented.study_id):\n            return OTHER_STUDY\n",
          "        if False:\n            return OTHER_STUDY\n")], None,
        "an image of another visit on the same (MNI) grid accepted under the mask"),
    "R5_unreadable_image_accepted": (
        [(GRID, "    except Exception:  # noqa: BLE001 — anything unreadable is refused (fail closed)\n        return UNREADABLE\n",
          "    except Exception:  # noqa: BLE001 — anything unreadable is refused (fail closed)\n        return None\n")], None,
        "an image whose header cannot be read is accepted (fail open)"),
    "R6_mask_shape_not_checked": (
        [(GRID, "    if tuple(int(v) for v in mask_shape) != internal:\n", "    if False:\n")], None,
        "a mask whose shape is not the image grid accepted (drawn sheared or cut off)"),
    "R7_affine_not_compared": (
        [(GRID, "        if own_shape != shape or not np.allclose(own_affine, affine, atol=GRID_TOLERANCE, rtol=0):\n",
          "        if own_shape != shape:\n")], None,
        "another image with the same array shape but another voxel size, position or orientation accepted"),
    "R8_tolerance_one_millimetre": (
        [(GRID, "GRID_TOLERANCE = 1e-3\n", "GRID_TOLERANCE = 1.0\n")], None,
        "a half-millimetre shift or shear accepted as the same grid"),
    "R9_displayed_image_not_authorized": (
        [(ROUTE, "    if displayed and displayed != own:\n        await authorize_file_scope(\n",
          "    if False:\n        await authorize_file_scope(\n")], None,
        "the header of an image the user may not open is read (an existence and geometry oracle)"),
    # ── PRB-028 — viewer ──
    "U1_confirm_with_unticked_regions": (
        [(DASH, "                        disabled={confirmBusy || (!!correctionsDigest && ackedCorrections !== correctionsDigest)\n"
                "                          || !allGeometricChecked}",
          "                        disabled={confirmBusy || (!!correctionsDigest && ackedCorrections !== correctionsDigest)}"),
         (DASH, "    if (geometricDigest && !allGeometricChecked) return;\n", "")], T28,
        "Confirm offered and accepted with geometric-fallback regions not ticked"),
    "U2_digest_not_sent": (
        [(DASH, "        drawnLabels, { geometricRegionsReviewedSha256: geometricDigest, displayedImageFileId });",
          "        drawnLabels, { geometricRegionsReviewedSha256: null, displayedImageFileId });")], T28,
        "the confirmation does not state the per-lesion review (the server would refuse it)"),
    "U3_too_many_still_offered": (
        [(DASH, "                {confirmable && !(geometricDigest && geometricTooMany) && (\n", "                {confirmable && (\n")],
        T28, "Confirm offered for more geometric-fallback lesions than the list can show"),
    "U4_list_not_shown": (
        [(DASH, "                {!!pendingRegions?.geometric_region_count && (\n", "                {false && (\n")], T28,
        "the geometric-fallback lesions are not listed (nothing to open, check or tick)"),
    "U5_reason_not_confirmable": (
        [(DASH, "                || reason === 'geometric_regions_not_reviewed');", ");")], T28,
        "a confirmation recorded without the per-lesion review cannot be redone from the card"),
    # ── PRB-029 — viewer: the AI-draft review runs the shared check ──
    "B1_ai_review_not_checked_on_screen": (
        [(BANNER, "    if (check.problems === null || check.problems.length > 0) {\n", "    if (false) {\n")], T29,
        "the AI-draft review confirmed whatever the view shows (the defect as found)"),
    "B2_stored_labels_not_compared": (
        [(BANNER, "    const check = confirmDrawCheck(segmentationId, stored);\n",
          "    const check = confirmDrawCheck(segmentationId, undefined);\n")], T29,
        "the AI draft drawn with other labels than the stored ones (another preset) is confirmed"),
    "B3_request_without_the_drawn_table": (
        [(API, "      { mask_sha256: maskSha256, drawn_labels_sha256: await drawnLabelsSha256(onScreen.drawnLabels),\n"
               "        displayed_image_file_id: onScreen.displayedImageFileId },",
          "      { mask_sha256: maskSha256, displayed_image_file_id: onScreen.displayedImageFileId },")], TDIG,
        "the AI-draft review request does not state the drawn label table"),
    # ── PRB-030 — viewer ──
    "C1_unknown_grid_accepted": (
        [(DRAWN, "  if (input.grid === null || (input.grid && !input.grid.mask)) {\n", "  if (false) {\n")], T30,
        "a confirmation accepted when it cannot be told which image (or mask grid) is on screen"),
    "C2_grid_mismatch_accepted": (
        [(DRAWN, "  } else if (input.grid?.mask && !sameGrid(input.grid.image, input.grid.mask)) {\n", "  } else if (false) {\n")],
        T30, "Confirm accepted while the mask is drawn over an image of another grid (the defect as found)"),
    "C3_slices_not_compared": (
        [(DRAWN, "a.width === b.width && a.height === b.height && a.depth === b.depth;",
          "a.width === b.width && a.height === b.height;")], T30,
        "an image with fewer slices accepted (the mask cut off)"),
    "C4_check_without_the_grid": (
        [(CHECK, "    grid: imageHere ? { image: imageHere.image, mask: imageHere.mask } : null,\n", "    grid: undefined,\n")],
        T30 + T29, "the shared check does not look at the image under the mask (both confirmations)"),
    "C5_image_of_another_segmentation_used": (
        [(CHECK, "  const imageHere = image && image.segmentationId === segmentationId && image.imageFileId ? image : null;\n",
          "  const imageHere = image && image.imageFileId ? image : null;\n")], T30,
        "the grid published for another segmentation is taken for this one"),
    "C6_image_not_sent": (
        [(CHECK, "    displayedImageFileId: imageHere?.imageFileId ?? null,\n", "    displayedImageFileId: null,\n")], T30 + T29,
        "the confirmation does not tell the server which image was under the mask (the server check cannot run)"),
    "C7_view_does_not_publish_the_image": (
        [(IV2, "    setOverlayImageOnScreen(drawnHere && known(imageCols)", "    setOverlayImageOnScreen(false && known(imageCols)")],
        T30V, "the standard 2D view does not say which image it draws under the segmentation"),
    "C8_published_in_every_view": (
        [(IV2, "    setOverlayImageOnScreen(drawnHere && known(imageCols) && known(imageRows) && known(imageSlices) ? {\n"
               "      segmentationId: drawnHere,\n",
          "    setOverlayImageOnScreen(currentSegmentation && known(imageCols) && known(imageRows) && known(imageSlices) ? {\n"
          "      segmentationId: currentSegmentation.segmentation_id,\n")], T30V,
        "the image is published also in views that do not draw the segmentation over it"),
    # ── PRB-031 — viewer ──
    "O1_underlays_not_checked": (
        [(DRAWN, "    if (!(Math.round(u.opacity * 100) <= Math.round(MAX_UNDERLAY_OPACITY * 100))) {\n", "    if (false) {\n")],
        T31 + T29, "Confirm accepted while a layer under the lesions can hide them (the defect as found)"),
    "O2_limit_raised_to_100": (
        [(DRAWN, "export const MAX_UNDERLAY_OPACITY = 0.3;\n", "export const MAX_UNDERLAY_OPACITY = 1;\n")], T31 + T31S,
        "the safe limit at 100 %: the zone map at any opacity accepted and restored"),
    "O3_zone_map_not_counted": (
        [(CHECK, "  if (state.zoneMapVisible && state.zoneMapMask && state.zoneMapDims) out.push({ layer: 'zone_map', opacity: state.zoneMapOpacity });\n", "")],
        T31 + T29, "the zone map is not counted as a layer under the lesions"),
    "O4_longitudinal_not_counted": (
        [(CHECK, "    out.push({ layer: 'longitudinal', opacity: LONGITUDINAL_OVERLAY_OPACITY });\n", "")], T31,
        "the longitudinal overlay is not counted as a layer under the lesions"),
    "O5_subtraction_not_counted": (
        [(CHECK, "    out.push({ layer: 'subtraction', opacity: SUBTRACTION_MAX_OPACITY });\n", "")], T31,
        "the FLAIR subtraction heat map is not counted as a layer under the lesions"),
    "O6_conformal_not_counted": (
        [(CHECK, "out.push({ layer: 'conformal', opacity: CONFORMAL_TIER_OPACITY });", "void 0;")], T31,
        "the conformal tiers are not counted as a layer under the lesions"),
    "O7_check_without_underlays": (
        [(CHECK, "    underlays: underlaysOnScreen(state),\n", "    underlays: [],\n")], T31 + T29,
        "the shared check does not look at the layers under the lesions (both confirmations)"),
    "O8_high_zone_opacity_restored": (
        [(STORE, "            zoneMapOpacity: safeZone ? zone : current.zoneMapOpacity,\n",
          "            zoneMapOpacity: zone ?? current.zoneMapOpacity,\n")], T31S,
        "a zone-map opacity above 30 % comes back in a new session (the defect as found)"),
    "L1_persistent_green_again": (
        [(COLORS, "  persistent: '#F0E442',", "  persistent: '#32CD32',")], T31C,
        "persistent lesions green against new red-ish lesions (red-green colour blindness, the defect as found)"),
    "L2_new_red_again": (
        [(COLORS, "  new: '#CC79A7',", "  new: '#F54646',")], T31C,
        "new lesions in the former red, outside the shared colour-blind-safe palette"),
    # ── the DIS confirmation uses the shared check and sends what it found ──
    "D1_dashboard_ignores_the_check": (
        [(DASH, "    if (maskReloadFailed || undrawn === null || undrawn.length > 0) {\n", "    if (maskReloadFailed) {\n")],
        T30 + T31 + TDRAWN, "the DIS confirmation ignores the shared check of the view on screen"),
    "D2_dashboard_does_not_send_the_image": (
        [(DASH, "        drawnLabels, { geometricRegionsReviewedSha256: geometricDigest, displayedImageFileId });",
          "        drawnLabels, { geometricRegionsReviewedSha256: geometricDigest, displayedImageFileId: null });")], T30,
        "the DIS confirmation does not tell the server which image was under the mask"),
    "P1_request_without_the_image": (
        [(API, "        displayed_image_file_id: onScreen.displayedImageFileId,\n        ...(regionCorrectionsSha256", "        ...(regionCorrectionsSha256")],
        TDIG, "the DIS confirmation request leaves the image under the mask out"),
    "P2_request_without_the_geometric_review": (
        [(API, "          ? { geometric_regions_reviewed_sha256: onScreen.geometricRegionsReviewedSha256 } : {}),",
          "          ? {} : {}),")], TDIG,
        "the DIS confirmation request leaves the per-lesion review out"),
    # ── independent review of PR #74 (290e407) ──
    "G9_binding_compared_without_geometric_lesions": (
        [(GATE, "    geometric_ok = regions[\"geometric_region_count\"] == 0 or checked == regions[\"geometric_regions_sha256\"]\n",
          "    geometric_ok = checked == regions[\"geometric_regions_sha256\"]\n")], None,
        "m4: the same mask classified again with the atlas loses a confirmation given with ticks (false reason, as found)"),
    "A3_out_of_date_viewer_not_named": (
        [(ROUTE, "        return OUTDATED_VIEWER\n", "        return None\n")], None,
        "m7: a viewer from before the update gets the label-table message instead of 'reload' (as found)"),
    "R10_whole_image_downloaded": (
        [(GRID, '    ranged = getattr(storage_service, "download_file_range", None)\n', "    ranged = None\n")], None,
        "m9: two whole images downloaded on every confirmation to read their headers (as found)"),
    "R11_gcs_range_not_requested": (
        [(GCS, "            return await self._run_sync(blob.download_as_bytes, start=start, end=end)\n",
          "            return await self._run_sync(blob.download_as_bytes)\n")], None,
        "m9: the GCS storage reads the whole object although a range was asked"),
    "U6_ticks_kept_on_a_changed_list": (
        [(DASH, "  useEffect(() => { setCheckedGeometric(new Set()); setOpenedGeometric(new Set()); }, [geometricDigest]);\n", "")],
        T28, "m5: ticks given on the earlier list survive a re-served list (a corrected region, a new classification)"),
    "U7_ticks_on_a_segmentation_not_open_or_drawn": (
        [(DASH, "                                disabled={!ticksAllowed || !openedGeometric.has(geometricKey(g))}\n",
          "                                disabled={!openedGeometric.has(geometricKey(g))}\n")], T28,
        "m2: ticks given on the card of a segmentation that is not open or not drawn (as found)"),
    "U8_tick_without_opening_the_slice": (
        [(DASH, "                                disabled={!ticksAllowed || !openedGeometric.has(geometricKey(g))}\n",
          "                                disabled={!ticksAllowed}\n")], T28,
        "m2: a tick without its 'open slice' pressed"),
    "Z1_zone_colouring_not_checked": (
        [(DRAWN, "  if (input.zoneColorized && input.values.some((v) => v !== 0\n", "  if (false && input.values.some((v) => v !== 0\n")],
        TZ, "m1: Confirm accepted while lesions are coloured by zone (values 5/6 not drawn, labels not as stored; as found)"),
    "Z2_zone_colouring_not_passed": (
        [(CHECK, "    zoneColorized: !!(state.zoneColorizeEnabled && state.zoneMapMask && state.zoneMapDims),\n",
          "    zoneColorized: false,\n")], TZ, "m1: the shared check is not told that lesions are coloured by zone"),
    "Z3_any_value_1_4_accepted": (
        [(DRAWN, "      && !(v >= 1 && v <= 4 && input.labels.find((l) => l.id === v)?.name === MAGNIMS_REGIONS[v - 1]))) {\n",
          "      && !(v >= 1 && v <= 4))) {\n")], TZ,
        "m1: a value 1-4 that is not a region label (an AI draft 'Lesion') accepted in zone colours"),
    "L3_legend_in_the_former_colours": (
        [(LEGEND, "                style={{ backgroundColor: LONGITUDINAL_OVERLAY_COLORS[key] }} />\n",
          "                style={{ backgroundColor: ({ resolved: '#4187F5', persistent: '#32CD32', new: '#F54646' })[key] }} />\n")],
        T31L, "m6: the legend shows the former blue / green / red while the overlay draws the new colours (as found)"),
    "L5_result_panel_without_the_shared_legend": (
        [(PANEL_L, "      <LongitudinalOverlayLegend />\n", "")], T31P,
        "m6: the comparison result shows no legend of the overlay"),
    "L4_new_is_the_white_matter_colour": (
        [(COLORS, "  new: '#CC79A7',", "  new: '#D55E00',")], T31C,
        "m6: new candidates drawn in the deep-white-matter vermillion (as found)"),
}


def offline_env():
    """PRB-002: backend tests never reach a real cloud service or the model provider."""
    env = dict(os.environ)
    empty = tempfile.mkdtemp(prefix="prb028-no-gcloud-")
    env.update({"GOOGLE_APPLICATION_CREDENTIALS": os.path.join(empty, "no-such-credentials.json"),
                "CLOUDSDK_CONFIG": empty, "GOOGLE_CLOUD_PROJECT": "mstool-offline-tests"})
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("FIRESTORE_EMULATOR_HOST", None)
    return env


def run_backend():
    r = subprocess.run([PY, "-m", "pytest", *BACKEND, "-q", "-p", "no:cacheprovider", "-o", "log_cli=false"],
                       cwd="backend", capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=offline_env(), timeout=1800)

    def count(word):
        m = re.search(rf"(\d+) {word}", r.stdout)
        return int(m.group(1)) if m else 0

    return {"suite": "backend", "exit": r.returncode, "failed": count("failed"), "passed": count("passed"),
            "errors": count("error"), "failing_tests": sorted(set(re.findall(r"(?:FAILED|ERROR) \S+::(\S+)", r.stdout)))}


def run_frontend(tests):
    out = os.path.join(tempfile.gettempdir(), "prb028_negctl_vitest.json")
    if os.path.exists(out):
        os.remove(out)
    r = subprocess.run("npx vitest run " + " ".join(tests) + f" --pool=threads --reporter=json --outputFile={out}",
                       cwd="frontend", shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=1800)
    if not os.path.exists(out):
        return {"suite": "frontend", "exit": r.returncode, "failed": 0, "passed": 0, "errors": 1, "failing_tests": [],
                "error_files": ["vitest produced no report"]}
    d = json.load(open(out, encoding="utf-8"))
    res = [a for f in d["testResults"] for a in f["assertionResults"]]
    errors = [f["name"].replace("\\", "/").split("/frontend/")[-1] for f in d["testResults"]
              if f["status"] == "failed" and not f["assertionResults"]]
    return {"suite": "frontend", "exit": r.returncode, "failed": sum(a["status"] == "failed" for a in res),
            "passed": sum(a["status"] == "passed" for a in res), "errors": len(errors),
            "failing_tests": [a["title"] for a in res if a["status"] == "failed"], "error_files": errors}


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main():
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    files = sorted({e[0] for edits, _t, _w in M.values() for e in edits})
    frontend_tests = sorted({t for _e, tests, _w in M.values() if tests for t in tests})
    test_paths = [f"backend/{t}" for t in BACKEND] + [f"frontend/{t}" for t in frontend_tests]
    require_committed(REPO, files + test_paths + HARNESS + [os.path.relpath(__file__, REPO).replace(os.sep, "/")])
    previous = json.load(open(OUT, encoding="utf-8")) if only and os.path.exists(OUT) else {"mutations": {}}
    with throwaway_worktree(REPO) as wt:
        if only and previous.get("tree") != wt["sha"]:
            raise SystemExit(f"--only merges with {OUT}, which is of {previous.get('tree')}, not {wt['sha']}: run all")
        os.chdir(wt["path"])
        try:
            res = run_in_worktree(only, files, frontend_tests, test_paths, previous)
        finally:
            os.chdir(REPO)
    res["worktree"] = {"run_in": "throwaway detached worktree of the commit, removed after the run",
                       "commit": wt["sha"], "stale_worktrees_removed_first": wt["stale_removed"]}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    rb, rf = res["restored"]["backend"], res["restored"]["frontend"]
    undetected = res["summary"]["undetected"]
    print("restored backend", rb["passed"], "passed /", rb["failed"], "failed | frontend", rf["passed"], "passed /",
          rf["failed"], "failed | detected", res["summary"]["detected"], "of", res["summary"]["mutations"],
          "| undetected:", undetected)
    bad = rb["failed"] or rb["errors"] or rf["failed"] or rf["errors"]
    return 1 if undetected or bad else 0


def run_in_worktree(only, files, frontend_tests, test_paths, previous):
    here = os.getcwd()   # the throwaway worktree; restores always write THERE (absolute paths), never elsewhere
    raw = {p: open(p, "rb").read() for p in files}
    text = {p: b.decode("utf-8").replace("\r\n", "\n") for p, b in raw.items()}
    for name, (edits, _t, _w) in M.items():
        for path, anchor, _r in edits:
            c = text[path].count(anchor)
            assert c == 1, f"{name}: anchor occurs {c}x in {path}, expected 1"

    def restore():
        for p, b in raw.items():
            target = os.path.join(here, p)
            if os.path.isdir(os.path.dirname(target)):
                with open(target, "wb") as fh:
                    fh.write(b)

    def on_signal(signum, _frame):
        restore()
        raise SystemExit(f"interrupted by signal {signum}; sources restored")

    atexit.register(restore)
    handlers = {}
    for sig in ("SIGINT", "SIGTERM", "SIGBREAK", "SIGHUP"):
        if hasattr(signal, sig):
            handlers[sig] = signal.signal(getattr(signal, sig), on_signal)
    try:
        return _mutate_all(only, files, frontend_tests, test_paths, previous, raw, restore)
    finally:
        restore()
        atexit.unregister(restore)
        for sig, h in handlers.items():
            signal.signal(getattr(signal, sig), h)


def _mutate_all(only, files, frontend_tests, test_paths, previous, raw, restore):
    text = {p: b.decode("utf-8").replace("\r\n", "\n") for p, b in raw.items()}
    eol = {p: "\r\n" if b"\r\n" in b else "\n" for p, b in raw.items()}
    res = {"executed": datetime.datetime.now().isoformat(timespec="seconds"),
           "tree": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
           "method": "in a throwaway detached worktree of the commit; one mutation at a time; each anchor asserted to "
                     "occur exactly once (LF text, written back with the file's own line endings); only the bound tests "
                     "of the mutated side run (backend pytest with no cloud credential per PRB-002; frontend vitest, "
                     "JSON reporter, --pool=threads, the files bound to the mutation); original bytes restored after "
                     "each mutation, at exit and on a signal, and checked at the end; the baseline must pass first",
           "hash_basis": "sha256 of the UTF-8 text with LF line endings",
           "source_sha256": {p: sha(text[p]) for p in files},
           "test_sha256": {t: sha(open(t, encoding="utf-8").read().replace("\r\n", "\n")) for t in test_paths},
           "backend_tests": BACKEND,
           "baseline": {"backend": run_backend(), "frontend": run_frontend(frontend_tests)},
           "mutations": {}}
    base_bad = [b for b in res["baseline"].values() if b["failed"] or b["errors"] or not b["passed"]]
    if base_bad:
        raise SystemExit(f"the baseline must pass before the mutations mean anything: {base_bad}")
    print("baseline ok", {k: (v["passed"], v["failed"]) for k, v in res["baseline"].items()}, flush=True)
    try:
        for name, (edits, tests, what) in M.items():
            if only and not name.startswith(only) and name in previous["mutations"]:
                res["mutations"][name] = previous["mutations"][name]
                continue
            touched = {}
            for path, anchor, repl in edits:
                touched[path] = touched.get(path, text[path]).replace(anchor, repl, 1)
            for path, mutated in touched.items():
                assert mutated != text[path], name
                with open(path, "w", encoding="utf-8", newline=eol[path]) as fh:
                    fh.write(mutated)
            out = run_backend() if tests is None else run_frontend(tests)
            out.update({"reintroduces": what, "files": sorted(touched), "tests": tests or BACKEND,
                        "executed": datetime.datetime.now().isoformat(timespec="seconds"),
                        "detected": bool(out["failed"] or out["errors"])})
            res["mutations"][name] = out
            for path in touched:
                with open(path, "wb") as fh:
                    fh.write(raw[path])
            print(f"{name:46s} [{out['suite']}] detected={out['detected']} {out['failed']} failed / "
                  f"{out['errors']} errors / {out['passed']} passed", flush=True)
    finally:
        restore()
    for p in files:   # the restore is byte-exact
        assert open(p, "rb").read() == raw[p], p
    res["restored"] = {"backend": run_backend(), "frontend": run_frontend(frontend_tests)}
    undetected = sorted(n for n, v in res["mutations"].items() if not v["detected"])
    res["summary"] = {"mutations": len(res["mutations"]), "detected": len(res["mutations"]) - len(undetected),
                      "undetected": undetected}
    return res


if __name__ == "__main__":
    sys.exit(main())
