"""Negative controls for CAPA-010 — viewer safety (RC-016, RC-023, RC-037, RC-038) — reproducible evidence.

Each mutation re-introduces ONE defect CAPA-010 removed (or removes one sub-control it added),
in the real source, one at a time; the script asserts every anchor occurs exactly once (the
sabotage really was applied), runs the bound frontend tests (vitest, JSON reporter), records
the failing test names and restores the exact original bytes.

Run from the repository root (needs frontend/node_modules; the layout test also needs a
Chromium-family browser — Edge or Chrome — see frontend/src/test/realBrowserLayout.ts):
    python scripts/safety/capa010_negative_controls.py
Output: docs/iec62304/records/risk_verification/CAPA-010_negative_controls_2026-10-17.json
NEVER run this while anything else edits the files it mutates (it restores a snapshot).
"""
import datetime
import hashlib
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.chdir(ROOT)
OUT = "docs/iec62304/records/risk_verification/CAPA-010_negative_controls_2026-10-17.json"
TESTS = [
    "src/components/ImageViewer3D.capa010.test.tsx",
    "src/components/MultiPanelViewer.capa010.test.tsx",
    "src/components/MeasurementOverlay.rc038.test.tsx",
    "src/ViewerApp.capa010.test.tsx",
    "src/components/ViewportSafetyOverlay.test.tsx",
]

F = "frontend/src/"
APP = F + "ViewerApp.tsx"
V3D = F + "components/ImageViewer3D.tsx"
MPV = F + "components/MultiPanelViewer.tsx"
STORE = F + "store/useMultiViewerStore.ts"
BBOX = F + "utils/boundingBoxMesh.ts"
MEAS = F + "components/MeasurementOverlay.tsx"

APP_3D_PROPS = (
    "                <ImageViewer3D\n"
    "                  patientName={patientData?.full_name}\n"
    "                  patientMRN={patientData?.mrn}\n"
    "                  studyDescription={studyInfo?.study.study_description}\n"
    "                />\n"
)
APP_MPV_PROPS = (
    "                  instances={[...originalInstances, ...preprocessedInstances]}\n"
    "                  patientName={patientData?.full_name}\n"
    "                  patientMRN={patientData?.mrn}\n"
    "                  studyDescription={studyInfo?.study.study_description}\n"
    "                />\n"
)
V3D_OVERLAY = (
    "      <ViewportSafetyOverlay\n"
    "        patientName={patientName}\n"
    "        patientMRN={patientMRN}\n"
    "        studyDescription={studyDescription}\n"
    "        anatomicalOrientation={currentSeries?.metadata?.anatomical_orientation}\n"
    "      />\n"
)
MPV_OVERLAY = (
    "      <ViewportSafetyOverlay\n"
    "        patientName={identity.patientName}\n"
    "        patientMRN={identity.patientMRN}\n"
    "        studyDescription={identity.studyDescription}\n"
    "        anatomicalOrientation={panel.orientation}\n"
    "      />\n"
)
APP_COLUMN = '          className="flex flex-1 flex-col"\n'
APP_VIEWPORT = "          <div className=\"min-h-0 flex-1 overflow-hidden\" style={{ background: '#000' }}>\n"
V3D_CENTROID = (
    "    const [i, j, k] = lesionVoxelToNifti(\n"
    "      selectedLesion.centroid.z, selectedLesion.centroid.y, selectedLesion.centroid.x,\n"
    "    );\n"
)
MEAS_TRANSFORM = (
    "  const scaleX = (canvasWidth / imageWidth) * zoomLevel;\n"
    "  const scaleY = (canvasHeight / imageHeight) * zoomLevel;\n"
    "  const originX = (canvasWidth / 2) * (1 - zoomLevel) + panOffset.x;\n"
    "  const originY = (canvasHeight / 2) * (1 - zoomLevel) + panOffset.y;\n"
)
MEAS_ANGLE = (
    "    const v1 = { x: (p1.x - p2.x) * pixelSpacing[1], y: (p1.y - p2.y) * pixelSpacing[0] };\n"
    "    const v2 = { x: (p3.x - p2.x) * pixelSpacing[1], y: (p3.y - p2.y) * pixelSpacing[0] };\n"
)

M = {  # name: ([(file, anchor, replacement), ...], what it re-introduces)
    # ── RC-016: identity on every view ──
    "I1_3d_overlay_removed": ([(V3D, V3D_OVERLAY, "")], "no identity / orientation / caveat on the 3D viewport (the defect as found)"),
    "I2_3d_identity_not_passed": ([(APP, APP_3D_PROPS, "                <ImageViewer3D />\n")],
                                  "the page loads the patient but does not hand it to the 3D viewer"),
    "I3_panel_overlay_removed": ([(MPV, MPV_OVERLAY, "")], "no identity / orientation / caveat on multi-panel cells (the defect as found)"),
    "I4_multipanel_identity_not_passed": ([(APP, APP_MPV_PROPS, "                  instances={[...originalInstances, ...preprocessedInstances]}\n                />\n")],
                                          "the page does not hand the patient to the multi-panel viewer"),
    "I5_panel_identity_dropped": ([(MPV, "          identity={{ patientName, patientMRN, studyDescription }}\n", "          identity={{}}\n")],
                                  "a dead prop: the multi-panel viewer receives the identity but its panels do not"),
    # ── RC-023: orientation reported per image, no glyphs, caveat visible ──
    "O1_panel_orientation_not_stored": ([(MPV, "            }, result.metadata.anatomical_orientation); // RC-023: this panel's own image\n", "            });\n")],
                                        "panels never learn the orientation of their own image"),
    "O2_orientation_lost_on_slice_change": ([(MPV, "          setPanelImageData(panel.id, newImage, panel.metadata, panel.orientation);\n",
                                              "          setPanelImageData(panel.id, newImage, panel.metadata);\n")],
                                            "a panel loses its orientation when the slice changes"),
    "O3_stale_orientation_on_assign": ([(STORE, "isLoading: false, orientation: undefined }", "isLoading: false }")],
                                       "a reassigned panel keeps showing the previous image's orientation"),
    "O4_stale_orientation_on_autoassign": ([(STORE, "          orientation: undefined, // never show the previous image's orientation\n", "")],
                                           "auto-assignment keeps the previous image's orientation"),
    "G1_orientation_cube_restored": ([(V3D, "    isOrientCube: false,\n", "    isOrientCube: sliceType === SLICE_TYPE.RENDER,\n")],
                                     "the 3D orientation cube with L/R/A/P/S/I letters (the defect as found)"),
    "G2_slice_letters_by_default": ([(V3D, "    isOrientationTextVisible: false,\n", "")],
                                    "niivue's default L/A slice letters in the 3D multiplanar panels"),
    "L1_layout_as_main": ([(APP, APP_COLUMN, '          className="flex-1"\n'),
                           (APP, APP_VIEWPORT, "          <div className=\"h-full overflow-hidden\" style={{ background: '#000' }}>\n")],
                          "the 2D viewport pushed under the frame: caveat off-screen (the defect as found)"),
    "L2_viewport_full_height_only": ([(APP, APP_VIEWPORT, "          <div className=\"h-full overflow-hidden\" style={{ background: '#000' }}>\n")],
                                     "flex column kept, viewport back to h-full"),
    "L3_column_block_only": ([(APP, APP_COLUMN, '          className="flex-1"\n')],
                             "viewport kept flex-1, column back to a block"),
    # ── RC-037: 3D lesion markers on the reported voxel ──
    "M1_crosshair_xyz": ([(V3D, V3D_CENTROID, "    const { x: i, y: j, z: k } = selectedLesion.centroid;\n")],
                         "the 3D crosshair transposed in-plane (the defect as found)"),
    "M2_bbox_xyz": ([(BBOX, "voxCorners.push(lesionVoxelToNifti(z, y, x));", "voxCorners.push([x, y, z]);")],
                    "the 3D bounding box transposed in-plane (the defect as found)"),
    "M3_mapping_xyz": ([(BBOX, "  return [y, x, z];\n}", "  return [x, y, z];\n}")],
                       "the shared (z, y, x) -> (i, j, k) mapping wrong for both markers"),
    # ── RC-038: measurements zoom/pan invariant, angle in mm ──
    "R1_zoom_and_pan_ignored": ([(MEAS, MEAS_TRANSFORM,
                                  "  const scaleX = canvasWidth / imageWidth;\n  const scaleY = canvasHeight / imageHeight;\n"
                                  "  const originX = 0;\n  const originY = 0;\n")],
                                "the ruler ignores zoom and pan: x2 length at zoom 2 (the defect as found)"),
    "R2_zoom_ignored_in_scale": ([(MEAS, "  const scaleX = (canvasWidth / imageWidth) * zoomLevel;\n  const scaleY = (canvasHeight / imageHeight) * zoomLevel;\n",
                                   "  const scaleX = canvasWidth / imageWidth;\n  const scaleY = canvasHeight / imageHeight;\n")],
                                 "lengths scaled by the zoom factor"),
    "R3_pan_ignored": ([(MEAS, "(1 - zoomLevel) + panOffset.x;\n", "(1 - zoomLevel);\n"),
                        (MEAS, "(1 - zoomLevel) + panOffset.y;\n", "(1 - zoomLevel);\n")],
                       "measurements detached from the anatomy when the image is panned"),
    "R4_angle_in_pixels": ([(MEAS, MEAS_ANGLE,
                             "    const v1 = { x: p1.x - p2.x, y: p1.y - p2.y };\n    const v2 = { x: p3.x - p2.x, y: p3.y - p2.y };\n")],
                           "the angle computed in pixel units on anisotropic pixels (the defect as found)"),
}


# Mutations that are NOT defects (equivalent code), stated rather than claimed as tested.
EXPECTED_UNDETECTED = {
    "L2_viewport_full_height_only": (
        "equivalent: once the centre column is a flex column, an overflow-hidden child with "
        "height 100% shrinks to the space left by the toolbar (flex-shrink 1; a scroll container's "
        "automatic minimum height is 0), so the page lays out the same. The defect needs the column "
        "to be a block again (L1, L3: detected). `min-h-0 flex-1` on the viewport is kept as the "
        "explicit form; confirmed in the real browser by this run"),
}


def run():
    out = os.path.join(tempfile.gettempdir(), "capa010_vitest.json")
    if os.path.exists(out):
        os.remove(out)
    subprocess.run("npx vitest run " + " ".join(TESTS) + f" --pool=threads --reporter=json --outputFile={out}",
                   cwd="frontend", shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    d = json.load(open(out, encoding="utf-8"))
    res = [a for f in d["testResults"] for a in f["assertionResults"]]
    failed = [a["title"] for a in res if a["status"] == "failed"]
    # A file that fails to load reports no assertions: count it as an error, never as a pass.
    errors = [f["name"].split("frontend")[-1] for f in d["testResults"] if f["status"] == "failed" and not f["assertionResults"]]
    return {"failed": len(failed), "passed": sum(a["status"] == "passed" for a in res),
            "skipped": sum(a["status"] in ("skipped", "pending") for a in res), "errors": len(errors),
            "failing_tests": failed, "error_files": errors}


def main():
    files = sorted({e[0] for edits, _w in M.values() for e in edits})
    raw = {p: open(p, "rb").read() for p in files}
    text = {p: b.decode("utf-8").replace("\r\n", "\n") for p, b in raw.items()}
    eol = {p: "\r\n" if b"\r\n" in b else "\n" for p, b in raw.items()}
    for name, (edits, _w) in M.items():
        for path, anchor, _r in edits:
            c = text[path].count(anchor)
            assert c == 1, f"{name}: anchor occurs {c}x in {path}, expected 1"
    res = {"executed": datetime.datetime.now().isoformat(timespec="seconds"),
           "method": "one mutation at a time; each anchor asserted to occur exactly once; vitest JSON reporter",
           "hash_basis": "sha256 of the UTF-8 text with LF line endings",
           "source_sha256": {p: hashlib.sha256(text[p].encode("utf-8")).hexdigest() for p in files},
           "test_sha256": {t: hashlib.sha256(open(os.path.join("frontend", t), encoding="utf-8").read().replace("\r\n", "\n").encode("utf-8")).hexdigest()
                           for t in TESTS},
           "tests": TESTS, "mutations": {}}
    try:
        for name, (edits, what) in M.items():
            touched = {}
            for path, anchor, repl in edits:
                touched[path] = touched.get(path, text[path]).replace(anchor, repl, 1)
            for path, mutated in touched.items():
                assert mutated != text[path], name
                open(path, "w", encoding="utf-8", newline=eol[path]).write(mutated)
            out = run()
            out.update({"reintroduces": what, "applied": True})
            res["mutations"][name] = out
            for path in touched:
                open(path, "wb").write(raw[path])
            print(f"{name:38s} {out['failed']} failed / {out['errors']} errors / {out['passed']} passed", flush=True)
    finally:
        for p, b in raw.items():
            open(p, "wb").write(b)
    res["restored"] = run()
    res["expected_undetected"] = EXPECTED_UNDETECTED
    res["undetected"] = sorted(n for n, v in res["mutations"].items() if v["failed"] == 0 and v["errors"] == 0)
    res["unexpected_undetected"] = sorted(set(res["undetected"]) - set(EXPECTED_UNDETECTED))
    json.dump(res, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("restored", res["restored"]["passed"], "passed /", res["restored"]["failed"], "failed /",
          res["restored"]["skipped"], "skipped | undetected:", res["undetected"],
          "| unexpected:", res["unexpected_undetected"])
    return 1 if res["unexpected_undetected"] or res["restored"]["failed"] or res["restored"]["skipped"] else 0


if __name__ == "__main__":
    sys.exit(main())
