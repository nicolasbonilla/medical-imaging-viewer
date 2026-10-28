"""Negative controls for PRB-004 .. PRB-009 — viewer display and orientation
(RC-073 / RC-074 / RC-075; REQ-SAFE-041 / REQ-SAFE-042; REQ-FUNC-101 .. REQ-FUNC-104; HAZ-006, HAZ-001, HAZ-007,
HAZ-004).

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
           while looking, an absent model written to the console.
The script refuses to start when a file it mutates has uncommitted changes, asserts that every anchor occurs exactly
once (on the LF text — a Windows checkout has CRLF line endings; a mutation is written with the file's own line
endings), runs the bound tests of the mutated side (backend: pytest offline per PRB-002; frontend: vitest JSON
reporter), records the failing tests and restores the exact original bytes — after each mutation, at exit, and on
Ctrl-C / SIGTERM / SIGBREAK.

Run from the repository root (needs backend/venv or the current Python with the backend requirements, and
frontend/node_modules):
    python scripts/safety/prb004_negative_controls.py            # every mutation
    python scripts/safety/prb004_negative_controls.py --only O   # only the mutations starting with O
Output: docs/iec62304/records/risk_verification/PRB-004_negative_controls_2026-10-28.json
NEVER run this while anything else edits the files it mutates (it restores a snapshot).
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

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.chdir(ROOT)
PY = os.path.join(ROOT, "backend", "venv", "Scripts", "python.exe")
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

T_NV = "src/components/NiivueViewer2D.prb004.test.tsx"
T_WL = "src/utils/niivueWindowLevel.test.ts"
T_3D = "src/components/ImageViewer3D.prb005.test.tsx"
T_PAGE = "src/ViewerApp.prb007.test.tsx"
T_SD = "src/utils/sequenceDetection.prb007.test.ts"
T_SO = "src/utils/sliceOnOpen.test.ts"
T_QS = "src/components/QuickScreenBadge.prb009.test.tsx"
T_FT = "src/config/features.quickScreen.test.ts"
BACKEND = ["tests/unit/test_prb006_mask_display_range.py"]

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
        [(NV, "              setMaskNotShown(check.reason);\n", "")], [T_NV],
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
        [(NV, "            if (!cancelled) setMaskNotShown('load');\n", "")], [T_NV],
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
        [(NV, "              ...LABEL_MASK_DISPLAY_RANGE, // PRB-006\n", "")], [T_NV],
        "the GPU view colours the mask with the MRI window its header carries"),
    "R2_3d_volume_mask_header_range": (
        [(I3, "            url: segUrl, name: niftiNameFor(segBuffer, 'mask'), colormap: 'red', opacity: 0.5, ...LABEL_MASK_DISPLAY_RANGE,\n",
          "            url: segUrl, name: niftiNameFor(segBuffer, 'mask'), colormap: 'red', opacity: 0.5,\n")], [T_3D],
        "the 3D volume render tints the whole volume red (the defect as found)"),
    "R3_3d_volume_visit1_header_range": (
        [(I3, "            url: tp1Url, name: niftiNameFor(longTp1Buffer, 'visit1'), colormap: 'blue', opacity: 0.5, ...LABEL_MASK_DISPLAY_RANGE,\n",
          "            url: tp1Url, name: niftiNameFor(longTp1Buffer, 'visit1'), colormap: 'blue', opacity: 0.5,\n")], [T_3D],
        "the earlier-visit mask in 3D coloured with its header range"),
    "R4_3d_multiplanar_visit2_header_range": (
        [(I3, "              url: tp2Url, name: niftiNameFor(longTp2Buffer, 'visit2'), colormap: 'hot', opacity: i === 0 ? 0.5 : 0.3, ...LABEL_MASK_DISPLAY_RANGE,\n",
          "              url: tp2Url, name: niftiNameFor(longTp2Buffer, 'visit2'), colormap: 'hot', opacity: i === 0 ? 0.5 : 0.3,\n")], [T_3D],
        "the later-visit mask in the multiplanar view coloured with its header range"),
    "R5_3d_multiplanar_mask_header_range": (
        [(I3, "              ...LABEL_MASK_DISPLAY_RANGE, // PRB-006\n", "")], [T_3D],
        "the lesion mask in the multiplanar view coloured with its header range"),
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
        [(SO, " && sliceCount(previous) === n\n", "\n")], [T_SO, T_PAGE],
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

    def restore():
        for p, b in raw.items():
            with open(p, "wb") as fh:
                fh.write(b)

    def on_signal(signum, _frame):
        restore()
        raise SystemExit(f"interrupted by signal {signum}; sources restored")

    atexit.register(restore)
    for sig in ("SIGINT", "SIGTERM", "SIGBREAK", "SIGHUP"):
        if hasattr(signal, sig):
            signal.signal(getattr(signal, sig), on_signal)

    frontend_tests = sorted({t for _e, tests, _w in M.values() if tests for t in tests})
    test_paths = [f"backend/{t}" for t in BACKEND] + [f"frontend/{t}" for t in frontend_tests]
    previous = json.load(open(OUT, encoding="utf-8")) if only and os.path.exists(OUT) else {"mutations": {}}
    res = {"executed": datetime.datetime.now().isoformat(timespec="seconds"),
           "tree": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
           "method": "one mutation at a time; each anchor asserted to occur exactly once (LF text, written back with "
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
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    rb, rf = res["restored"]["backend"], res["restored"]["frontend"]
    print("restored backend", rb["passed"], "passed /", rb["failed"], "failed | frontend", rf["passed"], "passed /",
          rf["failed"], "failed | detected", res["summary"]["detected"], "of", res["summary"]["mutations"],
          "| undetected:", undetected)
    bad = rb["failed"] or rb["errors"] or rf["failed"] or rf["errors"]
    return 1 if undetected or bad else 0


if __name__ == "__main__":
    sys.exit(main())
