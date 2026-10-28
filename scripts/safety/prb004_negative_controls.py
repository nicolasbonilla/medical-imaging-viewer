"""Negative controls for PRB-004 .. PRB-010 — viewer display, orientation and region colours
(RC-073 / RC-074 / RC-075 / RC-076; REQ-SAFE-041 / 042 / 043; REQ-FUNC-101 .. REQ-FUNC-104; HAZ-006, HAZ-001,
HAZ-007, HAZ-004, HAZ-005).

Each mutation re-introduces ONE defect the fixes removed, or removes one sub-control they added, in the real source,
one at a time:
  PRB-004  the W/L GPU view lays the image / the mask out by the scanner affine, a transposed or flipped layout, the
           radiological flip, each refusal of a mask not on the image grid removed or loosened, the refusal or a load
           failure not stated, the slider back between two slices, the grid read after the display transform;
  PRB-005  a volume handed to niivue without a NIfTI name (blob URL on a host without a dot);
  PRB-006  a mask overlay coloured with its header's display range, a wrong fixed range, the stored header keeping the
           MRI window;
  PRB-007  the grid not falling back to the images the study has, not filling spare panels, an image twice, the source
           switch naming the requested group;
  PRB-008  opening on slice 0, the viewer bypassing the rule, the slice kept across studies or sizes, grid panels on
           slice 0, a different middle;
  PRB-009  the screening on by default, mounted without the flag, the model looked for at every opening, the button
           while looking, an absent model written to the console;
  PRB-010  a region drawn in the colour stored with its label, the 2D zone layers / the 3D zone colormap / the zone
           legend / the lesion legend with colours of their own, red and green back in the mapping, the label preset
           or the backend's stored colours off the mapping, region names matched case-sensitively.
  Review of PR #71 (V1-V38): the aligned-mask route (realign only on the image's grid, marker and own range, never
           the reference affine on another mask), GPU / 3D masks requested aligned, the 3D order / position checks
           and notice, unsaved work announced, 3D "go to slice" on its own axis, deep white matter vermillion, label
           colours in GPU / 3D, the later visit not white, niivue's own controls off, the slice kept only on the
           same grid, the notice placement and wording, no mask input on the grid, no mask files as grid images.
Review m8: the run happens in a THROWAWAY WORKTREE of HEAD (scripts/safety/prb004_throwaway_worktree.py), never in the
developer's checkout, so an interrupted run cannot leave a mutation in real code. node_modules is a junction there.
The script refuses to start when a file it mutates, or a test it runs, has uncommitted changes (the run uses the
commit), asserts that every anchor occurs exactly
once (on the LF text — a Windows checkout has CRLF line endings; a mutation is written with the file's own line
endings), runs the bound tests of the mutated side (backend: pytest offline per PRB-002; frontend: vitest JSON
reporter), records the failing tests and restores the exact original bytes — after each mutation, at exit, and on
Ctrl-C / SIGTERM / SIGBREAK.

Run from the repository root (needs backend/venv or the current Python with the backend requirements, and
frontend/node_modules):
    python scripts/safety/prb004_negative_controls.py            # every mutation
    python scripts/safety/prb004_negative_controls.py --only O   # only the mutations starting with O
          (--only merges with the previous record, and refuses unless that record is of the same commit)
Output: docs/iec62304/records/risk_verification/PRB-004_negative_controls_2026-10-28.json
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
OUT = "docs/iec62304/records/risk_verification/PRB-004_negative_controls_2026-10-28.json"

NV = "frontend/src/components/NiivueViewer2D.tsx"
VG = "frontend/src/utils/niivueVoxelGrid.ts"
WL = "frontend/src/utils/niivueWindowLevel.ts"
I3 = "frontend/src/components/ImageViewer3D.tsx"
SVC = "backend/app/services/segmentation_service.py"
IC = "frontend/src/utils/instanceClassification.ts"
SD = "frontend/src/utils/sequenceDetection.ts"
VA = "frontend/src/ViewerApp.tsx"
SO = "frontend/src/utils/sliceOnOpen.ts"
MP = "frontend/src/components/MultiPanelViewer.tsx"
FT = "frontend/src/config/features.ts"
IV2 = "frontend/src/components/ImageViewer2D.tsx"
EA = "frontend/src/hooks/useEdgeAI.ts"
QS = "frontend/src/components/QuickScreenBadge.tsx"
RC = "frontend/src/utils/regionColors.ts"
SCL = "frontend/src/components/SegmentationCanvasLocal.tsx"
ZP = "frontend/src/components/MAGNIMSZoneMapPanel.tsx"
LD = "frontend/src/components/LesionDashboard.tsx"
TY = "frontend/src/types/segmentation.ts"
STORE = "frontend/src/store/useSegmentationStore.ts"
REG = "backend/app/api/routes/segmentation_regions.py"
SEG = "backend/app/api/routes/segmentation.py"
MLC = "frontend/src/utils/maskLabelColormap.ts"

T_NV = "src/components/NiivueViewer2D.prb004.test.tsx"
T_WL = "src/utils/niivueWindowLevel.test.ts"
T_3D = "src/components/ImageViewer3D.prb005.test.tsx"
T_PAGE = "src/ViewerApp.prb007.test.tsx"
T_SD = "src/utils/sequenceDetection.prb007.test.ts"
T_SO = "src/utils/sliceOnOpen.test.ts"
T_QS = "src/components/QuickScreenBadge.prb009.test.tsx"
T_FT = "src/config/features.quickScreen.test.ts"
T_SCL = "src/components/SegmentationCanvasLocal.prb010.test.tsx"
T_RC = "src/utils/regionColors.test.ts"
T_NVR = "src/components/NiivueViewer2D.prb004.review.test.tsx"
T_3DR = "src/components/ImageViewer3D.prb004.review.test.tsx"
T_SOR = "src/utils/sliceOnOpen.review.test.ts"
T_ICR = "src/utils/instanceClassification.prb007.review.test.ts"
T_MPR = "src/components/MultiPanelViewer.prb004.review.test.ts"
T_NVL = "src/components/NiivueViewer2D.prb004.layout.test.tsx"
T_CP = "src/components/ControlPanel.prb008.test.tsx"
CP = "frontend/src/components/ControlPanel.tsx"
BACKEND = ["tests/unit/test_prb006_mask_display_range.py", "tests/unit/test_prb010_region_label_colours.py",
           "tests/unit/test_prb004_review_ref_alignment.py"]
HARNESS = ["frontend/src/test/niivueHarness.ts", "frontend/src/test/syntheticNifti.ts"]

M = {  # name: ([(file, anchor, replacement), ...], [bound frontend tests] or None for backend, what it re-introduces)
    # ── PRB-004 / RC-073: the GPU view lays voxels out as the standard view ──
    "O1_image_keeps_scanner_layout": (
        [(NV, "        placeAsStandardView(base as unknown as VolumeLike, imageGrid);\n", "")], [T_NV],
        "the GPU view draws the image by the scanner affine (the defect as found: rotated 90 degrees)"),
    "O2_mask_keeps_its_scanner_layout": (
        [(NV, "              placeAsStandardView(seg, imageGrid); // the IMAGE's layout: voxel for voxel\n", "")], [T_NV],
        "the mask drawn by its own affine on an image laid out as the standard view"),
    "O3_layout_transposed": (
        [(VG, "    [0, s1, 0, 0],\n    [-s0, 0, 0, 0],\n", "    [s0, 0, 0, 0],\n    [0, -s1, 0, 0],\n")], [T_NV],
        "rows and columns swapped in the GPU layout"),
    "O4_rows_drawn_upwards": (
        [(VG, "    [-s0, 0, 0, 0],\n", "    [s0, 0, 0, 0],\n")], [T_NV],
        "the GPU layout mirrored top to bottom"),
    "O5_radiological_flip": (
        [(NV, "          isRadiologicalConvention: false,\n", "          isRadiologicalConvention: true,\n")], [T_NV],
        "niivue's radiological flip mirrors the layout left to right"),
    "O6_grid_dimensions_not_checked": (
        [(VG, "  if (mask.dims.some((d, n) => d !== image.dims[n])) return { ok: false, reason: 'grid' };\n", "")], [T_NV],
        "a mask of other dimensions drawn on the image"),
    "O7_position_not_checked": (
        [(VG, "        return { ok: false, reason: 'position' };\n", "        continue;\n")], [T_NV],
        "a mask placed elsewhere in the scanner drawn on the image voxels"),
    "O8_voxel_order_marker_not_checked": (
        [(VG, "  if (!(maskDescription ?? '').includes(RC031_V2_MARKER)) return { ok: false, reason: 'order' };\n", "")],
        [T_NV], "a legacy mask (in-plane transpose on disk) drawn transposed"),
    "O9_position_tolerance_one_mm": (
        [(VG, "export const SAME_GRID_TOLERANCE = 1e-3;", "export const SAME_GRID_TOLERANCE = 1;")], [T_NV],
        "a mask half a voxel away accepted as on the image grid"),
    "O10_refusal_not_stated": (
        [(NV, "              setMaskLoadProblem(check.reason);\n", "")], [T_NV],
        "a refused mask silently missing from the view"),
    "O11_slice_between_two_voxel_slices": (
        [(WL, "  return (i + 0.5) / n;\n", "  return n > 1 ? Math.min(0.999, i / (n - 1)) : 0.5;\n")], [T_NV, T_WL],
        "the GPU slider back to index / (depth - 1): a blend of two slices, slice 0 at the volume edge"),
    "O12_grid_read_after_the_display_transform": (
        [(NV, "        const imageGrid = voxelGridOf(base as unknown as VolumeLike);\n"
              "        placeAsStandardView(base as unknown as VolumeLike, imageGrid);\n",
          "        placeAsStandardView(base as unknown as VolumeLike, voxelGridOf(base as unknown as VolumeLike));\n"
          "        const imageGrid = voxelGridOf(base as unknown as VolumeLike);\n")], [T_NV],
        "the mask compared with the display transform instead of the image's scanner grid"),
    "O13_mask_load_failure_silent": (
        [(NV, "            if (!cancelled) setMaskLoadProblem('load');\n", "")], [T_NV],
        "a mask that fails to load silently missing (the base behaviour)"),
    # ── PRB-005: niivue file type from an explicit NIfTI name ──
    "N1_gpu_view_back_to_a_blob_url": (
        [(NV, "        const base = await NVImage.loadFromUrl({ url: baseName, name: baseName, buffer, colormap: 'gray', opacity: 1 });\n",
          "        await nv.loadVolumes([{ url: URL.createObjectURL(new Blob([buffer])), colormap: 'gray', opacity: 1 }]);\n"
          "        const base = nv.volumes[0];\n        nv.volumes = [];\n")], [T_NV],
        "the GPU view loads the image from a nameless blob URL (the defect as found)"),
    "N2_3d_volume_without_name": (
        [(I3, "        await nv.loadVolumes([{ url: mainUrl, name: niftiNameFor(niftiBuffer, 'image'), colormap: colormap3D, opacity: 1 }]);",
          "        await nv.loadVolumes([{ url: mainUrl, colormap: colormap3D, opacity: 1 }]);")], [T_3D],
        "the 3D volume view loads a nameless blob URL"),
    "N3_3d_multiplanar_without_name": (
        [(I3, "          await nvInstances[i].loadVolumes([{ url, name: niftiNameFor(niftiBuffer, 'image'), colormap: colormap3D, opacity: 1 }]); // PRB-005",
          "          await nvInstances[i].loadVolumes([{ url, colormap: colormap3D, opacity: 1 }]);")], [T_3D],
        "the 3D multiplanar view loads nameless blob URLs"),
    "N4_name_without_extension": (
        [(VG, "  return b.length === 2 && b[0] === 0x1f && b[1] === 0x8b ? `${stem}.nii.gz` : `${stem}.nii`;", "  return stem;")],
        [T_NV, T_3D], "a name that carries no NIfTI extension"),
    # ── PRB-006 / RC-074: mask display range ──
    "R1_gpu_mask_header_range": (
        [(NV, "                : { colormap: 'red', ...LABEL_MASK_DISPLAY_RANGE }), // PRB-006: never the MRI window\n",
          "                : { colormap: 'red' }),\n")], [T_NV],
        "the GPU view colours the mask with the MRI window its header carries"),
    "R2_3d_mask_header_range": (
        [(I3, "  if (!labelCm) return { colormap: 'red', ...LABEL_MASK_DISPLAY_RANGE }; // PRB-006: never the MRI window\n",
          "  if (!labelCm) return { colormap: 'red' };\n")], [T_3D],
        "the 3D lesion mask (volume and multiplanar) tints the whole volume red (the defect as found)"),
    "R3_3d_volume_visit1_header_range": (
        [(I3, "          const tp1 = await loadMask3D(longTp1Buffer, 'visit1', { colormap: 'blue', opacity: 0.5, ...LABEL_MASK_DISPLAY_RANGE });\n",
          "          const tp1 = await loadMask3D(longTp1Buffer, 'visit1', { colormap: 'blue', opacity: 0.5 });\n")], [T_3D],
        "the earlier-visit mask in 3D coloured with its header range"),
    "R4_3d_multiplanar_visit2_header_range": (
        [(I3, "              colormap: 'red', opacity: i === 0 ? 0.5 : 0.3, ...LABEL_MASK_DISPLAY_RANGE,\n",
          "              colormap: 'red', opacity: i === 0 ? 0.5 : 0.3,\n")], [T_3D],
        "the later-visit mask in the multiplanar view coloured with its header range"),
    "R5_3d_multiplanar_visit1_header_range": (
        [(I3, "              colormap: 'blue', opacity: i === 0 ? 0.5 : 0.3, ...LABEL_MASK_DISPLAY_RANGE,\n",
          "              colormap: 'blue', opacity: i === 0 ? 0.5 : 0.3,\n")], [T_3D],
        "the earlier-visit mask in the multiplanar view coloured with its header range"),
    "R6_fixed_range_hides_label_one": (
        [(VG, "export const LABEL_MASK_DISPLAY_RANGE = Object.freeze({ cal_min: 0, cal_max: 1 });",
          "export const LABEL_MASK_DISPLAY_RANGE = Object.freeze({ cal_min: 0, cal_max: 2 });")], [T_NV, T_3D],
        "label 1 drawn at half colour"),
    "R7_stored_header_keeps_the_mri_window": (
        [(SVC, '                header["cal_min"], header["cal_max"] = self._label_display_range(nifti_data)\n', "")], None,
        "a stored mask keeps the MRI's cal_min/cal_max (the defect as found)"),
    "R8_stored_range_always_zero_to_one": (
        [(SVC, "        return 0.0, float(max(1, top))\n", "        return 0.0, 1.0\n")], None,
        "a stored multi-label mask's range cut at 1"),
    "R9_fallback_header_without_range": (
        [(SVC, '                nifti_img.header["cal_min"], nifti_img.header["cal_max"] = self._label_display_range(nifti_data)  # PRB-006\n', "")],
        None, "a mask stored without the MRI header carries no range of its own"),
    # ── PRB-007: grid from the images the study has ──
    "G1_no_fallback_to_preprocessed": (
        [(IC, "  if (originals.length > 0) return { source: 'originals', instances: originals };\n"
              "  return { source: 'preprocessed', instances: preprocessed };\n",
          "  return { source: 'originals', instances: originals };\n")], [T_PAGE],
        "a study of preprocessed images only gives a grid of empty panels (the defect as found)"),
    "G2_spare_panels_not_filled": (
        [(SD, "    if (assigned.length >= 4) break;\n    if (shown.has(inst)) continue;\n", "    break;\n")], [T_SD, T_PAGE],
        "a second image of one sequence (T1w after contrast) never shown"),
    "G3_same_image_twice": (
        [(SD, "    if (shown.has(inst)) continue;\n", "")], [T_SD],
        "one image assigned to two panels"),
    "G4_switch_names_the_requested_source": (
        [(VA, "{shownMultiPanelSource === 'preprocessed' ? 'Preproc' : 'Original'}",
          "{multiPanelSource === 'preprocessed' ? 'Preproc' : 'Original'}")], [T_PAGE],
        "the switch says 'Original' while preprocessed images are shown"),
    # ── PRB-008: slice on open ──
    "S1_opens_on_slice_zero": (
        [(SO, "  return keep ? previousIndex : middleSliceIndex(n);\n", "  return keep ? previousIndex : 0;\n")], [T_SO, T_PAGE],
        "an image opens on slice 1 (the defect as found)"),
    "S2_viewer_bypasses_the_rule": (
        [(VA, "        openSeries(resultWithFileId, { sameStudy: openedStudyRef.current === studyId });\n",
          "        useViewerStore.getState().setCurrentSeries(resultWithFileId);\n")], [T_PAGE],
        "the viewer page keeps whatever slice index was set before"),
    "S3_slice_kept_across_studies": (
        [(SO, "  const keep = sameStudy && previous !== null", "  const keep = previous !== null")], [T_SO],
        "another study opens on the previous study's slice"),
    "S4_slice_kept_for_another_size": (
        [(SO, "  if (sliceCount(a) !== sliceCount(b)) return false;\n", "")], [T_SO, T_PAGE],
        "an image of another size opens on the previous image's slice"),
    "S5_grid_panels_open_on_slice_zero": (
        [(MP, "          const start = current > 0 && current < slices.length ? current : middleSliceIndex(slices.length);\n",
          "          const start = 0;\n")], [T_PAGE],
        "grid panels open on slice 1"),
    "S6_middle_rounded_up": (
        [(SO, "  return Number.isFinite(n) && n > 1 ? Math.floor((n - 1) / 2) : 0;\n",
          "  return Number.isFinite(n) && n > 1 ? Math.floor(n / 2) : 0;\n")], [T_SO],
        "the middle of an even volume taken one slice too far"),
    # ── PRB-009 / RC-075: screening behind its build flag ──
    "Q1_screening_on_by_default": (
        [(FT, "  QUICK_SCREEN: getFeatureFlag('ENABLE_QUICK_SCREEN', false),", "  QUICK_SCREEN: getFeatureFlag('ENABLE_QUICK_SCREEN', true),")],
        [T_FT, T_PAGE], "the unshipped screening model requested at every viewer opening (the defect as found)"),
    "Q2_badge_not_behind_the_flag": (
        [(IV2, "{FEATURES.QUICK_SCREEN && currentSeries?.slices?.[currentSliceIndex]?.image_data && (",
          "{currentSeries?.slices?.[currentSliceIndex]?.image_data && (")], [T_FT, T_PAGE],
        "the viewer mounts the screening whatever the flag"),
    "Q3_model_looked_for_at_every_opening": (
        [(EA, "  if (!modelAvailability) {\n", "  if (true) {\n")], [T_QS],
        "one model request per viewer opening"),
    "Q4_button_while_looking": (
        [(QS, "  if (isModelAvailable !== true) {\n", "  if (isModelAvailable === false) {\n")], [T_QS],
        "the Quick Screen button shown before the model is known to exist"),
    "Q5_absent_model_logged_as_error": (
        [(EA, "      .catch(() => false);\n",
          "      .catch(() => false)\n      .then((ok) => { if (!ok) console.error('[EdgeAI] model not found'); return ok; });\n")],
        [T_QS], "an absent model written to the console as an error"),
    # ── PRB-010 / RC-076: one MAGNIMS region colour mapping ──
    "P1_region_drawn_in_its_stored_colour": (
        [(STORE, "            ? { ...rawSegmentation, labels: withRegionColors(rawSegmentation.labels) }\n",
          "            ? { ...rawSegmentation, labels: rawSegmentation.labels }\n")], [T_SCL],
        "a classified segmentation drawn red / green / blue / gold as stored (the defect as found)"),
    "P2_zone_coloured_lesions_red_green": (
        [(SCL, "const MAGNIMS_ZONE_COLORS_LESION: Record<number, ParsedColor> = regionZoneRgba(153);",
          "const MAGNIMS_ZONE_COLORS_LESION: Record<number, ParsedColor> = { 1: { r: 255, g: 0, b: 0, a: 153 }, 2: { r: 0, g: 204, b: 0, a: 153 }, 3: { r: 0, g: 102, b: 255, a: 153 }, 4: { r: 255, g: 215, b: 0, a: 153 } };")],
        [T_SCL, T_RC], "zone-coloured lesions back to red / green / blue / yellow"),
    "P3_zone_map_layer_red_green": (
        [(SCL, "        const zoneColors: Record<number, ParsedColor> = regionZoneRgba(zmAlpha); // PRB-010",
          "        const zoneColors: Record<number, ParsedColor> = { 1: { r: 255, g: 0, b: 0, a: zmAlpha }, 2: { r: 0, g: 204, b: 0, a: zmAlpha }, 3: { r: 0, g: 102, b: 255, a: zmAlpha }, 4: { r: 255, g: 215, b: 0, a: zmAlpha } };")],
        [T_SCL, T_RC], "the zone-map background layer back to red / green / blue / yellow"),
    "P4_3d_zone_colormap_red_green": (
        [(I3, "    for (let i = from; i < to; i++) { R[i] = zone[id].r; G[i] = zone[id].g; B[i] = zone[id].b; A[i] = 255; }\n",
          "    for (let i = from; i < to; i++) { R[i] = id === 1 || id === 4 ? 255 : 0; G[i] = [0, 0, 204, 102, 215][id]; B[i] = id === 3 ? 255 : 0; A[i] = 255; }\n")],
        [T_SCL], "the 3D zone colormap back to red / green / blue / yellow"),
    "P5_zone_legend_own_colours": (
        [(ZP, "const REGION_COLORS: Record<string, string> = REGION_DOT_CLASSES;",
          "const REGION_COLORS: Record<string, string> = { Periventricular: 'bg-red-500', Juxtacortical: 'bg-green-500', Infratentorial: 'bg-blue-500', 'Deep White Matter': 'bg-yellow-500' };")],
        [T_SCL, T_RC], "the zone-map legend back to its own red / green / blue / yellow"),
    "P6_lesion_legend_own_copy": (
        [(LD, "const REGION_COLORS: Record<string, string> = REGION_DOT_CLASSES;",
          "const REGION_COLORS: Record<string, string> = { Periventricular: 'bg-[#E69F00]', Juxtacortical: 'bg-[#56B4E9]', Infratentorial: 'bg-[#009E73]', 'Deep White Matter': 'bg-[#D55E00]' };")],
        [T_RC], "the lesion legend keeps its own copy of the colours (two mappings that can drift apart again)"),
    "P7_red_and_green_in_the_mapping": (
        [(RC, "  Periventricular: { id: 1, hex: '#E69F00', dot: 'bg-[#E69F00]', text: 'text-[#F0A800]' },     // orange\n"
              "  Juxtacortical: { id: 2, hex: '#56B4E9', dot: 'bg-[#56B4E9]', text: 'text-[#7FC7F0]' },       // sky blue\n",
          "  Periventricular: { id: 1, hex: '#FF0000', dot: 'bg-[#FF0000]', text: 'text-[#FF0000]' },     // orange\n"
          "  Juxtacortical: { id: 2, hex: '#00CC00', dot: 'bg-[#00CC00]', text: 'text-[#00CC00]' },       // sky blue\n")],
        [T_SCL, T_RC], "the shared mapping itself puts periventricular red against juxtacortical green"),
    "P8_label_preset_off_the_mapping": (
        [(TY, "  { id: 1, name: 'Periventricular', color: MAGNIMS_REGION_PALETTE.Periventricular.hex, opacity: 0.6, visible: true,",
          "  { id: 1, name: 'Periventricular', color: '#FF0000', opacity: 0.6, visible: true,")],
        [T_RC], "the MAGNIMS label preset keeps its own (red) periventricular colour"),
    "P9_backend_stores_red": (
        [(REG, '    "Periventricular": "#E69F00",\n', '    "Periventricular": "#FF0000",\n')], None,
        "classify-regions / generate-zone-map store periventricular red"),
    "P11_zone_colouring_legend_red_green": (
        [(ZP, "              <span className={`w-2 h-2 rounded-full ${REGION_DOT_CLASSES[region]}`} />{ZONE_ABBREV[region]}",
          "              <span className={`w-2 h-2 rounded-full ${({ Periventricular: 'bg-red-500', Juxtacortical: 'bg-green-500', Infratentorial: 'bg-blue-500', 'Deep White Matter': 'bg-yellow-500' } as Record<string, string>)[region]}`} />{ZONE_ABBREV[region]}")],
        [T_SCL], "the zone-colouring legend back to red / green / blue / yellow (found during the PRB-010 work)"),
    "P10_region_names_case_sensitive": (
        [(RC, "  return MAGNIMS_REGIONS.find((r) => r.toLowerCase() === n);\n",
          "  return MAGNIMS_REGIONS.find((r) => r === name);\n")], [T_RC],
        "a region label stored in another letter case keeps its stored colour"),
    # ── Review of PR #71 @ 39f9d44 (RC-073 / RC-074 / RC-076; REQ-SAFE-041 / 043; REQ-FUNC-103) ──
    # M1 — masks requested aligned to the image; the route realigns only a mask on the image's grid
    "V1_route_io_not_imported": (
        [(SEG, "import io\nimport struct\n", "import struct\n")], None,
        "GET /segmentation/{id}/nifti?ref_file_id= raises NameError again (the defect as found)"),
    "V2_reference_affine_stamped_on_any_mask": (
        [(SVC, "        if seg_affine.shape != (4, 4) or not np.allclose(seg_affine, ref_affine, atol=tolerance, rtol=0):\n"
               "            return None\n", "")], None,
        "an identity-fallback or other-grid mask served under the image's affine: a fabricated alignment"),
    "V3_realigned_mask_without_marker": (
        [(SVC, '        header["descrip"] = cls._RC031_ORIENT_MARKER\n', "")], None,
        "a realigned mask served without the RC-031 marker (refused by the viewers: the 3D/GPU view loses it)"),
    "V4_realigned_mask_with_the_mri_window": (
        [(SVC, '        header["cal_min"], header["cal_max"] = cls._label_display_range(labels)\n', "")], None,
        "a realigned mask served with the MRI's display window (PRB-006 again through the aligned route)"),
    "V5_legacy_mask_not_reoriented": (
        [(SVC, "        oriented = cls._seg_native_to_reference_order(seg_data, cls._header_has_v2_marker(seg_header))\n",
          "        oriented = seg_data\n")], None,
        "a pre-RC-031 mask (in-plane transpose) not un-transposed by the aligned route"),
    "V6_aligned_mask_not_served": (
        [(SEG, "                if aligned is not None:\n                    nifti_data = aligned\n", "")], None,
        "the route computes the aligned mask and serves the stored one"),
    "V7_gpu_mask_not_requested_aligned": (
        [(NV, "            const segBuf = await fetchBuffer(`${API_BASE_URL}${segmentationNiftiPath(overlaySegId, fileId)}`);\n",
          "            const segBuf = await fetchBuffer(`${API_BASE_URL}/api/v1/segmentation/${overlaySegId}/nifti`);\n")],
        [T_NVR], "the W/L GPU view asks for the mask as stored (a legacy mask on the image's grid refused, D-3)"),
    "V8_3d_mask_not_requested_aligned": (
        [(I3, "    return `${API_BASE_URL}${segmentationNiftiPath(segId, fileId)}`;\n",
          "    return `${API_BASE_URL}/api/v1/segmentation/${segId}/nifti`;\n")],
        [T_3DR], "the 3D view asks for the lesion mask as stored"),
    "V9_3d_later_visit_not_requested_aligned": (
        [(I3, "    const url = `${API_BASE_URL}${segmentationNiftiPath(longTp2SegId, fileId)}`;\n",
          "    const url = `${API_BASE_URL}/api/v1/segmentation/${longTp2SegId}/nifti`;\n")],
        [T_3DR], "the 3D view asks for the later-visit mask as stored"),
    "V10_3d_marker_not_checked": (
        [(VG, "  if (!inImageOrder) return { ok: false, reason: 'order' };\n", "")], [T_3DR],
        "the 3D view draws a legacy mask (in-plane transpose) mirrored about the diagonal (the defect as found)"),
    "V11_3d_position_not_checked": (
        [(VG, "  if (isIdentityAffine(mask.affine)) return { ok: false, reason: 'position' };\n", "")], [T_3DR],
        "the 3D view draws an identity-fallback mask at an arbitrary place (the defect as found)"),
    "V12_3d_refused_mask_drawn_anyway": (
        [(I3, "  return check.ok ? { vol, problem: null } : { vol: null, problem: check.reason };\n",
          "  return { vol, problem: null };\n")], [T_3DR],
        "the 3D view checks a mask and draws it whatever the check says"),
    "V13_3d_refusal_not_stated": (
        [(I3, "  const notDrawnList = (Object.entries({ ...masksNotDrawn, ...(lesionUnsaved ? { lesion: 'unsaved' } : {}) }) as Array<[Mask3D, Mask3DProblem]>)\n",
          "  const notDrawnList = (Object.entries({ ...(lesionUnsaved ? { lesion: 'unsaved' } : {}) }) as Array<[Mask3D, Mask3DProblem]>)\n")],
        [T_3DR], "a mask the 3D view refuses is silently missing"),
    # M2 — unsaved work announced
    "V14_gpu_unsaved_segmentation_silent": (
        [(NV, "  const maskNotShown: MaskNotShown | null = segIsLocal ? 'unsaved' : maskLoadProblem;\n",
          "  const maskNotShown: MaskNotShown | null = maskLoadProblem;\n")], [T_NVR],
        "a segmentation not saved yet silently absent from the GPU view (the defect as found)"),
    "V15_gpu_unsaved_edits_silent": (
        [(NV, "  const showEditsNotice = hasUnsavedEdits && !!overlaySegId && maskNotShown === null;\n",
          "  const showEditsNotice = false;\n")], [T_NVR],
        "the GPU view draws the saved mask without saying the unsaved edits are not shown"),
    "V16_viewer_does_not_report_unsaved_edits": (
        [(IV2, "            <NiivueViewer2D hasUnsavedEdits={segmentationMask.state.isDirty || segmentationStoreDirty} />",
          "            <NiivueViewer2D />")], [T_NVR],
        "the 2D viewer never tells the GPU view about unsaved edits"),
    "V17_3d_unsaved_segmentation_silent": (
        [(I3, "  const notDrawnList = (Object.entries({ ...masksNotDrawn, ...(lesionUnsaved ? { lesion: 'unsaved' } : {}) }) as Array<[Mask3D, Mask3DProblem]>)\n",
          "  const notDrawnList = (Object.entries({ ...masksNotDrawn }) as Array<[Mask3D, Mask3DProblem]>)\n")],
        [T_3DR], "a segmentation not saved yet silently absent from the 3D view"),
    # M3 — 3D "go to slice"
    "V18_3d_slice_index_over_depth": (
        [(I3, "      nvInst.scene.crosshairPos[target.axis] = target.frac;\n",
          "      nvInst.scene.crosshairPos[2] = currentSliceIndex / Math.max(1, (nvInst.volumes[0].dims?.[3] ?? 1) - 1);\n")],
        [T_3DR], "3D 'go to slice' back to index / (depth - 1) on the axial axis (the defect as found)"),
    "V19_3d_slice_always_on_the_axial_axis": (
        [(I3, "  const axis = deltas.indexOf(Math.max(...deltas));\n", "  const axis = 2;\n")], [T_3DR],
        "3D 'go to slice' on the axial axis for a sagittally stored volume"),
    # m1 / m6 — colours
    "V20_deep_white_matter_reddish_purple": (
        [(RC, "  'Deep White Matter': { id: 4, hex: '#D55E00', dot: 'bg-[#D55E00]', text: 'text-[#F07A3A]' },     // vermillion\n",
          "  'Deep White Matter': { id: 4, hex: '#CC79A7', dot: 'bg-[#CC79A7]', text: 'text-[#DB93BC]' },     // vermillion\n")],
        [T_SCL], "deep white matter back to reddish purple: dE76 5.3 from infratentorial for a deutan reader, as drawn"),
    "V21_gpu_mask_all_red": (
        [(NV, "            const labelCm = maskLabelColormap(labelsRef.current);\n",
          "            const labelCm = null as ReturnType<typeof maskLabelColormap>;\n")], [T_NVR],
        "the GPU view draws a region-classified mask all red (the defect as found)"),
    "V22_3d_lesion_mask_all_red": (
        [(I3, "  const lesionLabelCm = useMemo(() => maskLabelColormap(savedLabels),\n",
          "  const lesionLabelCm = useMemo(() => null as ReturnType<typeof maskLabelColormap>,\n")], [T_3DR],
        "the 3D view draws a region-classified mask all red (the defect as found)"),
    "V23_niivue_regions_in_stored_colours": (
        [(MLC, "  const listed = withRegionColors(\n", "  const listed = (<T,>(x: T) => x)(\n")], [T_NVR, T_3DR],
        "GPU / 3D draw a region label in the colour stored with it (red / green / blue / gold)"),
    "V24_unlisted_label_value_not_drawn": (
        [(MLC, "    v === 0 ? null : (v <= top ? listed.find((l) => l.id === v)?.color : undefined) ?? UNLISTED_LABEL_HEX;\n",
          "    v === 0 ? null : (v <= top ? listed.find((l) => l.id === v)?.color ?? null : null);\n")], [T_NVR],
        "a label value missing from the table silently not drawn in GPU / 3D"),
    "V25_3d_label_colours_with_header_range": (
        [(I3, "  return { colormap: labelCm.name, cal_min: labelCm.cal_min, cal_max: labelCm.cal_max };\n",
          "  return { colormap: labelCm.name };\n")], [T_3DR],
        "the 3D label colours read through the mask header's display range: each region in another region's colour"),
    # m2 — later visit
    "V26_3d_later_visit_white": (
        [(I3, "          const tp2 = await loadMask3D(longTp2Buffer, 'visit2', { colormap: 'red', opacity: 0.5, ...LABEL_MASK_DISPLAY_RANGE });\n",
          "          const tp2 = await loadMask3D(longTp2Buffer, 'visit2', { colormap: 'hot', opacity: 0.5, ...LABEL_MASK_DISPLAY_RANGE });\n")],
        [T_3DR], "the later visit drawn white in 3D (the defect as found)"),
    # m3 — niivue's own controls
    "V27_gpu_niivue_hotkeys_on": (
        [(NV, "          ...NIIVUE_HOTKEYS_OFF,\n", "")], [T_NVR],
        "niivue's view-type and clip-plane hotkeys active in the GPU view"),
    "V28_gpu_canvas_focusable": (
        [(NV, "        canvasRef.current?.removeAttribute('tabindex');\n", "")], [T_NVR],
        "the GPU canvas takes keyboard focus (niivue's keys act on it)"),
    "V29_gpu_keys_reach_niivue": (
        [(NV, "    const block = (e: Event) => { if (onCanvas(e)) e.stopPropagation(); };\n",
          "    const block = (_e: Event) => {};\n")], [T_NVR],
        "keys and double-click on the GPU canvas reach niivue (slice, drag mode, contrast reset behind the store)"),
    "V30_gpu_wheel_reaches_niivue": (
        [(NV, "      if (!onCanvas(e)) return;\n      e.stopPropagation();\n", "      if (!onCanvas(e)) return;\n")],
        [T_NVR], "the wheel on the GPU canvas reaches niivue (it changes niivue's slice behind the store)"),
    # m4 — slice kept only on the same grid
    "V31_slice_kept_on_another_matrix": (
        [(SO, "  if (!sameNumber(ma.rows, mb.rows) || !sameNumber(ma.columns, mb.columns) || !sameNumber(ma.slices, mb.slices)) return false;\n", "")],
        [T_SOR], "the slice kept for an image with another matrix"),
    "V32_slice_kept_on_another_spacing": (
        [(SO, "  if (pa && pb && (pa.length !== pb.length || pa.some((v, n) => !sameNumber(v, pb[n], GRID_TOLERANCE_MM)))) return false;\n", "")],
        [T_SOR], "the slice kept for an image with another pixel spacing"),
    "V33_slice_kept_on_another_thickness": (
        [(SO, "  if (!sameNumber(ma.slice_thickness, mb.slice_thickness, GRID_TOLERANCE_MM)) return false;\n", "")],
        [T_SOR], "the slice kept for an image with another slice thickness"),
    "V34_slice_kept_on_another_orientation": (
        [(SO, "  return (ma.anatomical_orientation ?? null) === (mb.anatomical_orientation ?? null);\n", "  return true;\n")],
        [T_SOR], "the slice kept for an image stored in another orientation"),
    # m5 / m9 — the GPU notice
    "V35_gpu_notice_at_the_top": (
        [(NV, "  const noticeClass = 'pointer-events-none absolute bottom-14 left-1/2",
          "  const noticeClass = 'pointer-events-none absolute top-12 left-1/2")], [T_NVR, T_NVL],
        "the GPU notice back at the top, where the identity block can cover it"),
    "V39_gpu_notice_on_the_two_line_caveat": (
        [(NV, "  const noticeClass = 'pointer-events-none absolute bottom-14 left-1/2",
          "  const noticeClass = 'pointer-events-none absolute bottom-10 left-1/2")], [T_NVL],
        "the GPU notice low enough to cover the laterality caveat when it wraps in a narrow view (the first review fix)"),
    # ── Film capture (coordinator, 2026-10-28): two display findings ──
    "V40_3d_colour_bar_under_the_caveat": (
        [(I3, "    isColorbar: false,\n", "    isColorbar: sliceType === SLICE_TYPE.RENDER,\n")], [T_3DR],
        "niivue's colour bar back along the bottom of the 3D render, under the laterality caveat (the defect as found)"),
    "V41_sidebar_slice_reads_the_single_view": (
        [(CP, "  const navIndex = isMultiPanel ? activeSlice.sliceIndex : currentSliceIndex;\n",
          "  const navIndex = currentSliceIndex;\n")], [T_CP],
        "the sidebar names the single view's slice while the side-by-side panels show another (the defect as found)"),
    "V42_sidebar_slider_moves_the_single_view": (
        [(CP, "  const setNavIndex = isMultiPanel ? activeSlice.setSliceIndex : setCurrentSliceIndex;\n",
          "  const setNavIndex = setCurrentSliceIndex;\n")], [T_CP],
        "the sidebar slider moves a hidden single-view index, nothing on screen"),
    "V43_sidebar_slice_count_of_the_single_view": (
        [(CP, "  const navTotal = isMultiPanel ? activeSlice.totalSlices : totalSlices;\n",
          "  const navTotal = totalSlices;\n")], [T_CP],
        "the sidebar gives the single view's slice count for a panel of another size"),
    "V36_gpu_grid_notice_sends_to_standard": (
        [(NV, "new Set<MaskNotShown>(['order', 'load', 'unsaved']);", "new Set<MaskNotShown>(['grid', 'position', 'order', 'load', 'unsaved']);")],
        [T_NVR], "the notice for a mask on another grid sends the reader to the Standard view"),
    # m7 / m10 — the grid
    "V37_multi_panel_mask_prop_back": (
        [(MP, "interface MultiPanelViewerProps extends PatientIdentity {\n  instances: ImagingInstance[];\n}",
          "interface MultiPanelViewerProps extends PatientIdentity {\n  instances: ImagingInstance[];\n  segmentationMask?: unknown;\n}")],
        [T_MPR], "a mask input on the multi-panel grid (the path without a grid check)"),
    "V38_grid_shows_segmentation_files": (
        [(IC, "  const imagesOnly = (list: T[]) => list.filter((i) => !isSegmentationDerivative(i.original_filename ?? ''));\n",
          "  const imagesOnly = (list: T[]) => list;\n")], [T_ICR],
        "a segmentation file shown as a grey image in the grid"),
}


def offline_env():
    """PRB-002: backend tests never reach a real cloud service or the model provider."""
    env = dict(os.environ)
    empty = tempfile.mkdtemp(prefix="prb004-no-gcloud-")
    env.update({"GOOGLE_APPLICATION_CREDENTIALS": os.path.join(empty, "no-such-credentials.json"),
                "CLOUDSDK_CONFIG": empty, "GOOGLE_CLOUD_PROJECT": "mstool-offline-tests"})
    env.pop("ANTHROPIC_API_KEY", None)
    return env


def run_backend():
    r = subprocess.run([PY, "-m", "pytest", *BACKEND, "-q", "-p", "no:cacheprovider", "-o", "log_cli=false"],
                       cwd="backend", capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=offline_env())

    def count(word):
        m = re.search(rf"(\d+) {word}", r.stdout)
        return int(m.group(1)) if m else 0

    return {"suite": "backend", "failed": count("failed"), "passed": count("passed"), "errors": count("error"),
            "failing_tests": sorted(set(re.findall(r"(?:FAILED|ERROR) \S+::(\S+)", r.stdout)))}


def run_frontend(tests):
    out = os.path.join(tempfile.gettempdir(), "prb004_negctl_vitest.json")
    if os.path.exists(out):
        os.remove(out)
    subprocess.run("npx vitest run " + " ".join(tests) + f" --pool=threads --reporter=json --outputFile={out}",
                   cwd="frontend", shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not os.path.exists(out):
        return {"suite": "frontend", "failed": 0, "passed": 0, "errors": 1, "failing_tests": [],
                "error_files": ["vitest produced no report"]}
    d = json.load(open(out, encoding="utf-8"))
    res = [a for f in d["testResults"] for a in f["assertionResults"]]
    errors = [f["name"].replace("\\", "/").split("/frontend/")[-1] for f in d["testResults"]
              if f["status"] == "failed" and not f["assertionResults"]]
    return {"suite": "frontend", "failed": sum(a["status"] == "failed" for a in res),
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
    res["worktree"] = {"run_in": "throwaway detached worktree of the commit, removed after the run (review m8)",
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
    eol = {p: "\r\n" if b"\r\n" in b else "\n" for p, b in raw.items()}
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
           "method": "in a throwaway detached worktree of the commit (review m8); "
                     "one mutation at a time; each anchor asserted to occur exactly once (LF text, written back with "
                     "the file's own line endings); only the bound tests of the mutated side run (backend pytest with "
                     "no cloud credential per PRB-002; frontend vitest, JSON reporter, --pool=threads); original bytes "
                     "restored after each mutation, at exit and on a signal, and checked at the end",
           "hash_basis": "sha256 of the UTF-8 text with LF line endings",
           "source_sha256": {p: sha(text[p]) for p in files},
           "test_sha256": {t: sha(open(t, encoding="utf-8").read().replace("\r\n", "\n")) for t in test_paths},
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
