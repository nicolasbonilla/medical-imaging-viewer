"""Negative controls for CP-SLICE-THICKNESS-001 — reliability by slice thickness
(RC-054, RC-055, RC-056, RC-057, RC-058) — reproducible evidence. DRAFT, PENDING owner approval.

Each mutation re-introduces ONE defect the controls exist to prevent, in the real source, one
at a time; the script asserts every anchor occurs exactly once (the sabotage really was
applied), runs the bound tests (backend pytest for RC-054 with a JUnit report; frontend vitest
for RC-055..RC-058 with the JSON reporter), records the failing test names and restores the
exact original bytes (hash-checked after every mutation).

It also re-derives the evidence asset from its source record (PROVENANCE): the SHA-256 of each
research record at the pinned commit, and every detection figure, lesion count, scan and
patient count of the asset against the record.

Run from the repository root with the backend virtual environment's Python (needs
frontend/node_modules and the research commit object in the local git store):
    backend/venv/Scripts/python.exe scripts/safety/slice_thickness_negative_controls.py
Output: docs/iec62304/records/risk_verification/CP-SLICE-THICKNESS-001_negative_controls_2026-10-23.json
(re-run after the independent review of PR #59; the 2026-10-21 record is kept as history)
NEVER run this while anything else edits the files it mutates (it restores a snapshot).
"""
import datetime
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.chdir(ROOT)
OUT = "docs/iec62304/records/risk_verification/CP-SLICE-THICKNESS-001_negative_controls_2026-10-23.json"

BACKEND_TESTS = ["tests/unit/test_rc054_acquisition_geometry.py"]
FRONTEND_TESTS = [
    "src/utils/sliceThicknessReliability.test.ts",
    "src/components/SliceThicknessReliabilityCard.test.tsx",
    "src/config/features.sliceThickness.test.ts",
]

GEO = "backend/app/services/acquisition_geometry.py"
IMG = "backend/app/services/imaging_service.py"
F = "frontend/src/"
FLAGS = F + "config/features.ts"
DASH = F + "components/LesionDashboard.tsx"
CARD = F + "components/SliceThicknessReliabilityCard.tsx"
LOGIC = F + "utils/sliceThicknessReliability.ts"
ASSET = F + "config/sliceThicknessReliability.v2.json"

NIFTI_TRY = (
    "    try:\n"
    "        return _derive_from_nifti_image(img)\n"
    "    except Exception:  # noqa: BLE001 — fail to \"not determinable\", never break loading\n"
    "        return _not_determinable(\"unreadable\", source=\"nifti_grid\")\n"
)

M = {  # name: ([(file, anchor, replacement), ...], what it re-introduces, runner)
    # ── RC-054: backend reads the acquisition thickness, never guesses ──
    "B1_nifti_grid_called_native": ([(GEO, 'state="at_least", effective_mm=round(through_plane, 4), source="nifti_grid",',
                                      'state="native", effective_mm=round(through_plane, 4), source="nifti_grid",')],
                                    "a NIfTI grid reported as the native acquisition thickness", "backend"),
    "B2_fine_grid_accepted": ([(GEO, "    if through_plane > THIN_LIMIT_MM:\n", "    if through_plane > 0:\n")],
                              "a 1-mm grid (e.g. MSLesSeg, acquired at 2-5 mm) taken as a thickness", "backend"),
    "B3_default_thickness": ([(GEO, 'raw_thickness = base.get("slice_thickness")\n', 'raw_thickness = base.get("slice_thickness", 1.0)\n')],
                             "a missing SliceThickness defaulted to 1.0 mm (the legacy behaviour)", "backend"),
    "B4_derived_called_original": ([(GEO, 'original = bool(image_type) and image_type[0] == "ORIGINAL"\n', "original = True\n")],
                                   "a derived/reformatted or untyped DICOM reported as native", "backend"),
    "B5_gap_ignored": ([(GEO, "effective = max(v for v, ok in ((thickness, thickness_ok), (spacing, spacing_ok)) if ok)\n",
                         "effective = thickness if thickness_ok else spacing\n")],
                       "the gap between slices ignored (thickness used instead of spacing)", "backend"),
    "B6_2d_without_spacing_native": ([(GEO, 'if original and (spacing_ok or acq_type == "3D"):\n', "if original:\n")],
                                     "a 2D image without the spacing between slices reported as native", "backend"),
    "B7_implausible_kept": ([(GEO, "return value is not None and math.isfinite(value) and 0.0 < value <= PLAUSIBLE_MAX_MM\n",
                              "return value is not None and math.isfinite(value) and value > 0.0\n")],
                            "implausible header values (e.g. 25 mm) kept instead of rejected", "backend"),
    "B8_contradiction_ignored": ([(GEO, "    if np.any(np.abs(pix_mm - grid) > _PIXDIM_ABS_TOL_MM + _PIXDIM_REL_TOL * grid):\n",
                                   "    if False:\n")],
                                 "a NIfTI whose pixdim contradicts its affine used anyway", "backend"),
    "B9_units_ignored": ([(GEO, "    scale = _UNIT_TO_MM.get(unit)\n", "    scale = 1.0\n")],
                         "NIfTI spatial units ignored (metres read as millimetres)", "backend"),
    "B10_not_total": ([(GEO, NIFTI_TRY, "    return _derive_from_nifti_image(img)\n")],
                      "an unreadable header raises instead of 'not determinable' (could break image loading)", "backend"),
    "B11_loader_not_wired": ([(IMG, "                acquisition_geometry=derive_from_nifti_image(img),\n", "")],
                             "the NIfTI loader does not expose the geometry", "backend"),
    "B12_legacy_value_exposed": ([(IMG, "                acquisition_geometry=derive_from_dicom_dataset(ds),\n",
                                   "                acquisition_geometry={'state': 'native', 'effective_mm': float(ds.get('SliceThickness', 1.0)), 'source': 'dicom_header'},\n")],
                                 "the legacy slice_thickness (1.0 mm default) exposed as the native thickness", "backend"),
    # Added 2026-10-23 after the independent review of PR #59 (release/owner-signoff-2026-10).
    "B13_spacing_taken_as_thickness": ([(GEO, '        return _not_determinable("invalid" if thickness is not None else "missing", source="dicom_header", **fields)\n',
                                         "        pass\n")],
                                       "a SpacingBetweenSlices without SliceThickness reported as the thickness ('2.5 mm, from the header')", "backend"),
    # ── RC-055: the card reads the right image, strictly ──
    "P1_native_from_any_source": ([(LOGIC, "    if (!plausible || g.source !== 'dicom_header') return ND('malformed');\n",
                                    "    if (!plausible) return ND('malformed');\n")],
                                  "a 'native' value accepted from a NIfTI grid", "frontend"),
    "P2_legacy_fallback": ([(CARD, "  else if (ownFromViewer) own = parseGeometry(currentSeries?.metadata?.acquisition_geometry);\n",
                             "  else if (ownFromViewer) own = parseGeometry(currentSeries?.metadata?.acquisition_geometry ?? { state: 'native', effective_mm: currentSeries?.metadata?.slice_thickness, source: 'dicom_header' });\n")],
                           "the legacy slice_thickness (1.0 mm default) used when the geometry is absent", "frontend"),
    "P3_viewer_image_for_any_segmentation": ([(CARD, "  const ownFromViewer = !!sourceFileId && currentSeries?.file_id === sourceFileId;\n",
                                               "  const ownFromViewer = !!currentSeries;\n")],
                                             "the thickness of whatever image is on screen shown for another image's segmentation", "frontend"),
    "P4_thin_lower_bound_accepted": ([(LOGIC, "    if (!plausible || (mm as number) <= a.thin_limit_mm) return ND('malformed');\n",
                                       "    if (!plausible) return ND('malformed');\n")],
                                     "a lower bound at or below 1.5 mm accepted", "frontend"),
    "P5_first_original_guessed": ([(LOGIC, "  if (originals.length > 1) return { ownFilename, ownIsProcessed, original: { kind: 'ambiguous', count: originals.length } };\n", "")],
                                  "with several original FLAIRs, the first one taken as the source", "frontend"),
    "P6_thinner_source_wins": ([(LOGIC, "(c.mm > m.mm || (c.mm === m.mm && c.basis === 'native') ? c : m)",
                                 "(c.mm < m.mm || (c.mm === m.mm && c.basis === 'native') ? c : m)")],
                               "the thinner of two sources shown (a thin value hides a thicker one)", "frontend"),
    "P7_masks_taken_for_images": ([(LOGIC, "const NOT_AN_IMAGE = /(mask|seg|label|lesion|roi|zonemap|probab)/i;",
                                    "const NOT_AN_IMAGE = /(?!)/;")],
                                  "a mask file named *FLAIR* taken for the original FLAIR", "frontend"),
    "P8_original_never_consulted": ([(LOGIC, "  if (ownIsProcessed) {\n    if (original.kind === 'found') {\n",
                                      "  if (false) {\n    if (original.kind === 'found') {\n")],
                                    "a processed (resampled) image never traced to its original FLAIR", "frontend"),
    # ── RC-056: no false-lesion figure ──
    "R1_false_lesion_percentage": ([(ASSET, '"false_lesion_thick": "At this slice thickness it is not reliable without a calibration on at least 10 patients from this site, and none exists.",',
                                     '"false_lesion_thick": "Controlled at 10 % with the thin-slice calibration.",')],
                                   "a false-lesion percentage shown on thick slices", "frontend"),
    "R2_calibrated_asset_accepted": ([(LOGIC, "  if (a.false_lesion_figure?.site_calibration !== null) {\n",
                                       "  if (false) {\n")],
                                     "an asset carrying a site calibration accepted", "frontend"),
    "R3_thick_reason_lost": ([(LOGIC, "falseLesionFigure: { shown: false, reason: thick ? 'thick_or_unknown' : 'no_calibration_for_deployed_segmenter' },",
                               "falseLesionFigure: { shown: false, reason: 'no_calibration_for_deployed_segmenter' },")],
                             "thick slices not told that the figure is unreliable at this thickness", "frontend"),
    # ── RC-057: detection figures from the asset, worst case ──
    "D1_best_case": ([(LOGIC, "    if (bin === null) return null;\n    worst = Math.max(worst, bin);\n",
                       "    if (bin === null) continue;\n    worst = worst < 0 ? bin : Math.min(worst, bin);\n")],
                     "the best evidence row of the band used instead of the worst", "frontend"),
    "D2_any_bin_enough": ([(LOGIC, "    if (detection[i] >= fraction) from = i;\n    else break;\n",
                            "    if (detection[i] >= fraction) from = i;\n")],
                          "'from this size' without requiring every larger size", "frontend"),
    "D3_lower_bound_own_band_only": ([(LOGIC, "      : a.bands.filter((b) => b.max_mm >= res.mm && b.min_mm >= a.thin_limit_mm);\n",
                                       "      : a.bands.filter((b) => res.mm > b.min_mm && res.mm <= b.max_mm);\n")],
                                     "an 'at least' thickness read as exactly that thickness", "frontend"),
    "D4_asset_figure_changed": ([(ASSET, '"detection": [0.125, 0.4494, 0.5932, 0.6553, 0.7551],', '"detection": [0.125, 0.4494, 0.8932, 0.8553, 0.8551],')],
                                "an evidence figure no longer equal to the paper", "frontend"),
    # D5 (v1: post-hoc marker dropped) replaced 2026-10-23: asset v2 holds no post-hoc row and the
    # logic refuses one (independent review of PR #59); D5, D10 and D11 test that refusal and the bands.
    "D5_post_hoc_row_accepted": ([(LOGIC, "    if (row.post_hoc !== false) problems.push(`${id}: post-hoc evidence row`);\n", "")],
                                 "an evidence row added after the results were seen accepted in the clinical asset", "frontend"),
    "D6_evidence_size_dropped": ([(CARD, "                        {fill(m.evidence, { scans: row.scans, patients: row.patients, sites: row.sites })}\n", "")],
                                 "figures shown without their evidence size", "frontend"),
    "D7_empty_list_warning_dropped": ([(CARD, "        <p>{m.empty_list}</p>\n", "")],
                                      "no 'an empty or short list does not mean no lesions' warning", "frontend"),
    "D8_no_3d_recommendation": ([(LOGIC, "  const thick = res.basis === 'at_least' || bands.some((b) => b.thick);\n", "  const thick = false;\n")],
                                "thick-slice studies without the 3D FLAIR recommendation", "frontend"),
    "D9_unknown_guessed_thin": ([(LOGIC, "    return { kind: 'not_determinable', thick: true, ...empty, reasons: res.reasons, falseLesionFigure: { shown: false, reason: 'thick_or_unknown' } };\n",
                                  "    return assessReliability({ kind: 'band', basis: 'native', mm: 1, file: '', viaOriginal: false }, a);\n")],
                                "an unknown thickness shown as a thin-slice band (a guess)", "frontend"),
    "D10_post_hoc_record_accepted": ([(LOGIC, "  if (!a.source?.records?.length || a.source.records.some((r) => r.post_hoc !== false)) problems.push('post-hoc source record');\n", "")],
                                     "a post-hoc research record accepted as a source of the clinical asset", "frontend"),
    "D11_band_not_preregistered": ([(ASSET, '{ "id": "B2", "min_mm": 1.5, "max_mm": 4.5, "thick": true, "rows": ["B2"],',
                                     '{ "id": "B2", "min_mm": 1.5, "max_mm": 4.5, "thick": true, "rows": ["B1_grid"],')],
                                   "a thickness band fed by evidence that is not its pre-registered band (v1 used post-hoc rows at 1.5-3.5 mm)", "frontend"),
    # ── RC-058: feature flag ──
    "F1_flag_default_on": ([(FLAGS, "getFeatureFlag('ENABLE_SLICE_THICKNESS_RELIABILITY', false)", "getFeatureFlag('ENABLE_SLICE_THICKNESS_RELIABILITY', true)")],
                           "the card ON by default", "frontend"),
    "F2_card_outside_flag": ([(DASH, "      {FEATURES.SLICE_THICKNESS_RELIABILITY && (\n        <Suspense fallback={null}>\n",
                               "      {true && (\n        <Suspense fallback={null}>\n")],
                             "the card rendered whatever the flag", "frontend"),
    "F3_card_not_lazy": ([(DASH, "const SliceThicknessReliabilityCard = lazy(() => import('./SliceThicknessReliabilityCard'));\n",
                           "import SliceThicknessReliabilityCard from './SliceThicknessReliabilityCard';\n")],
                         "the card (and its evidence asset) bundled into the main chunk", "frontend"),
}

EXPECTED_UNDETECTED = {}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_backend():
    xml_path = os.path.join(tempfile.gettempdir(), "slice_thickness_pytest.xml")
    if os.path.exists(xml_path):
        os.remove(xml_path)
    subprocess.run([sys.executable, "-m", "pytest", *BACKEND_TESTS, "-q", "-p", "no:cacheprovider", "-o", "log_cli=false",
                    f"--junitxml={xml_path}"], cwd="backend", capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not os.path.exists(xml_path):
        return {"failed": 0, "passed": 0, "skipped": 0, "errors": 1, "failing_tests": [], "error_files": BACKEND_TESTS}
    root = ET.parse(xml_path).getroot()
    cases = root.iter("testcase")
    failed, passed, skipped, errors, names = 0, 0, 0, 0, []
    for c in cases:
        if c.find("failure") is not None:
            failed += 1
            names.append(c.get("name"))
        elif c.find("error") is not None:
            errors += 1
            names.append(c.get("name"))
        elif c.find("skipped") is not None:
            skipped += 1
        else:
            passed += 1
    suite_errors = sum(int(s.get("errors", 0)) for s in root.iter("testsuite"))
    if passed + failed + skipped == 0:  # collection error: never count as a pass
        errors = max(errors, suite_errors, 1)
    return {"failed": failed, "passed": passed, "skipped": skipped, "errors": errors, "failing_tests": names, "error_files": []}


def run_frontend():
    out = os.path.join(tempfile.gettempdir(), "slice_thickness_vitest.json")
    if os.path.exists(out):
        os.remove(out)
    subprocess.run("npx vitest run " + " ".join(FRONTEND_TESTS) + f" --pool=threads --reporter=json --outputFile={out}",
                   cwd="frontend", shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not os.path.exists(out):
        return {"failed": 0, "passed": 0, "skipped": 0, "errors": 1, "failing_tests": [], "error_files": FRONTEND_TESTS}
    d = json.load(open(out, encoding="utf-8"))
    res = [a for f in d["testResults"] for a in f["assertionResults"]]
    failed = [a["title"] for a in res if a["status"] == "failed"]
    # A file that fails to load reports no assertions: count it as an error, never as a pass.
    errors = [f["name"].split("frontend")[-1] for f in d["testResults"] if f["status"] == "failed" and not f["assertionResults"]]
    return {"failed": len(failed), "passed": sum(a["status"] == "passed" for a in res),
            "skipped": sum(a["status"] in ("skipped", "pending") for a in res), "errors": len(errors),
            "failing_tests": failed, "error_files": errors}


def provenance():
    """Re-derive every figure of the evidence asset from the research records at the pinned commit."""
    asset = json.load(open(ASSET, encoding="utf-8"))
    commit = asset["source"]["commit"]
    out = {"commit": commit, "records": {}, "rows": {}, "ok": True}
    blobs = {}
    for rec in asset["source"]["records"]:
        p = subprocess.run(["git", "show", f"{commit}:{rec['path']}"], capture_output=True)
        if p.returncode != 0:
            out["records"][rec["path"]] = {"available": False}
            out["ok"] = False
            continue
        sha = hashlib.sha256(p.stdout).hexdigest()
        out["records"][rec["path"]] = {"available": True, "sha256": sha, "matches_asset": sha == rec["sha256"]}
        out["ok"] &= sha == rec["sha256"]
        blobs[rec["path"].split("/")[-1]] = json.loads(p.stdout.decode("utf-8"))
    results = blobs.get("2026-10-21_paper_a_v03_results.json")
    native = blobs.get("2026-10-21_paper_a_v03_mslesseg_native.json")
    groups = {"MSL_2": "group|2-2.3 mm", "MSL_3": "group|3 mm", "MSL_45": "group|4-5 mm"}
    for rid, row in asset["evidence_rows"].items():
        if rid in groups and native:
            g = native[groups[rid]]
            expect = {"detection": g["raw_sensitivity_by_size_bin"], "lesions": g["lesions_by_size_bin"],
                      "scans": g["scans"], "patients": g["patients"], "post_hoc": True}
        elif results and rid.startswith("B"):
            band = rid.split("_")[0]
            sb = results["thickness"]["size_bins"][f"{band}|D2|P1|0.2"]
            bb = results["thickness"]["D2|by_band"]["P1|0.2"][band]
            expect = {"detection": sb["sens_raw"], "lesions": sb["n_lesions"], "scans": bb["scans"],
                      "patients": bb["patients"], "post_hoc": False}
        else:
            out["rows"][rid] = {"checked": False}
            out["ok"] = False
            continue
        got = {k: row[k] for k in expect}
        same = got == expect
        out["rows"][rid] = {"checked": True, "matches_record": same, **({} if same else {"record": expect, "asset": got})}
        out["ok"] &= same
    return out


def main():
    files = sorted({e[0] for edits, _w, _r in M.values() for e in edits})
    raw = {p: open(p, "rb").read() for p in files}
    text = {p: b.decode("utf-8").replace("\r\n", "\n") for p, b in raw.items()}
    eol = {p: "\r\n" if b"\r\n" in b else "\n" for p, b in raw.items()}
    for name, (edits, _w, _r) in M.items():
        for path, anchor, _repl in edits:
            c = text[path].count(anchor)
            assert c == 1, f"{name}: anchor occurs {c}x in {path}, expected 1"
    res = {"executed": datetime.datetime.now().isoformat(timespec="seconds"),
           "change": "CP-SLICE-THICKNESS-001 (DRAFT, PENDING owner approval; feature flag OFF)",
           "method": "one mutation at a time; each anchor asserted to occur exactly once; backend pytest (JUnit XML) "
                     "or frontend vitest (JSON reporter); original bytes restored and hash-checked after each mutation",
           "hash_basis": "sha256 of the UTF-8 text with LF line endings",
           "source_sha256": {p: _sha(text[p]) for p in files},
           "tests": {"backend": BACKEND_TESTS, "frontend": FRONTEND_TESTS},
           "test_sha256": {**{t: _sha(open(os.path.join("backend", t), encoding="utf-8").read().replace("\r\n", "\n")) for t in BACKEND_TESTS},
                           **{t: _sha(open(os.path.join("frontend", t), encoding="utf-8").read().replace("\r\n", "\n")) for t in FRONTEND_TESTS}},
           "provenance": provenance(),
           "mutations": {}}
    print("provenance ok:", res["provenance"]["ok"], flush=True)
    try:
        for name, (edits, what, runner) in M.items():
            touched = {}
            for path, anchor, repl in edits:
                touched[path] = touched.get(path, text[path]).replace(anchor, repl, 1)
            for path, mutated in touched.items():
                assert mutated != text[path], name
                open(path, "w", encoding="utf-8", newline=eol[path]).write(mutated)
            out = run_backend() if runner == "backend" else run_frontend()
            out.update({"reintroduces": what, "runner": runner, "applied": True})
            res["mutations"][name] = out
            for path in touched:
                open(path, "wb").write(raw[path])
                assert open(path, "rb").read() == raw[path], f"{name}: {path} not restored"
            print(f"{name:40s} {out['failed']} failed / {out['errors']} errors / {out['passed']} passed", flush=True)
    finally:
        for p, b in raw.items():
            open(p, "wb").write(b)
    res["restored"] = {"backend": run_backend(), "frontend": run_frontend()}
    res["expected_undetected"] = EXPECTED_UNDETECTED
    res["undetected"] = sorted(n for n, v in res["mutations"].items() if v["failed"] == 0 and v["errors"] == 0)
    res["unexpected_undetected"] = sorted(set(res["undetected"]) - set(EXPECTED_UNDETECTED))
    json.dump(res, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    rb, rf = res["restored"]["backend"], res["restored"]["frontend"]
    print("restored backend", rb["passed"], "passed /", rb["failed"], "failed | frontend", rf["passed"], "passed /",
          rf["failed"], "failed | undetected:", res["undetected"], "| provenance ok:", res["provenance"]["ok"])
    bad = (res["unexpected_undetected"] or rb["failed"] or rb["errors"] or rf["failed"] or rf["errors"]
           or rb["skipped"] or rf["skipped"] or not res["provenance"]["ok"])
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
