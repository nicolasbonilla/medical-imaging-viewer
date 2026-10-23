"""Negative controls for CAPA-011 / RC-039 (HAZ-006, HAZ-001, HAZ-005) — reproducible evidence.

Each mutation re-introduces the CAPA-011 defect (a clinical-tool mask stored in the app's
internal axis order under the RC-031 v2 marker, so the loader transposes it twice) or a
variant of it — or, F1-F5, re-introduces the former fallback that stored a mask whose
position could not be established (no / missing / unreadable reference image, or an
indeterminate affine) instead of refusing it — or, G1-G4, removes or loosens the check that the
mask is on the image's own grid (shape and voxel-to-scanner transform), or, M1, computes the
stored record's dimensions from the mask read in the legacy order — in the real source, one at a
time. The script asserts every anchor occurs
exactly once (the sabotage really was applied), runs the bound tests, records the failing
test names and restores the exact original bytes.

Run from the repository root:
    backend/venv/Scripts/python scripts/safety/capa011_negative_controls.py
Output: docs/iec62304/records/risk_verification/CAPA-011_negative_controls_2026-10-17.json
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
OUT = "docs/iec62304/records/risk_verification/CAPA-011_negative_controls_2026-10-17.json"
TESTS = ["tests/unit/test_rc039_tool_runner_mask_axes.py"]

TR = "backend/app/services/tool_runner_service.py"
SEG = "backend/app/services/segmentation_service.py"

MARKER_LINE = "        nifti_img.header[\"descrip\"] = SegmentationService._RC031_ORIENT_MARKER\n"
STORE_FIXED = (
    "        nifti_img = nib.Nifti1Image(stored_data.astype(np.uint8), stored_affine)\n"
    "        nifti_img.header.set_data_dtype(np.uint8)\n"
    "        nifti_img.header.set_slope_inter(1.0, 0.0)\n"
    + MARKER_LINE
)
# Byte-for-byte the store block on main before CAPA-011 (commit 7fcf1cd, 2026-08-19).
STORE_DEFECT = (
    "        affine = source_affine if source_affine is not None else np.eye(4)\n"
    "        nifti_img = nib.Nifti1Image(mask_data.astype(np.uint8), affine)\n"
    "        nifti_img.header.set_data_dtype(np.uint8)\n"
    "        nifti_img.header.set_slope_inter(1.0, 0.0)\n"
    "        nifti_img.header[\"descrip\"] = b\"RC031-ORIENT-V2\"   # matches segmentation_service._RC031_ORIENT_MARKER\n"
)
ALIGNED_RETURN = "                return aligned, aligned_affine\n"
REFUSAL = "        logger.error(\n            \"[RC-039] Clinical-tool mask NOT stored: %s\", reason,\n"
# The former fallback's result: legacy (2,1,0) internal order. Stored as (a1,a0,k) under the
# v2 marker, the loader's (2,0,1) yields exactly mask^(2,1,0), as the fallback did.
OLD_FALLBACK = "return np.transpose(mask_native, (1, 0, 2)), source_affine"
SHAPE_CHECK = "                if tuple(aligned.shape[:3]) != ref_shape:\n"
AFFINE_CHECK = ("                elif not np.allclose(aligned_affine, ref_affine, rtol=0.0, "
                "atol=self._GRID_TOLERANCE):\n")
STORE_CALL = (
    "        stored_data, stored_affine = self._orient_mask_for_storage(\n"
    "            mask_data, source_affine, reference_mri_path\n"
    "        )\n"
)


def ref_dropped(anchor):
    return (TR, anchor, anchor.replace("reference_mri_path=flair_path,", "reference_mri_path=None,")
            .replace("reference_mri_path=input_path,", "reference_mri_path=None,"))


M = {  # name: ([(file, anchor, replacement), ...], what it re-introduces)
    "D0_original_defect": ([(TR, STORE_FIXED, STORE_DEFECT)],
                           "the CAPA-011 defect exactly as on main: the internal (k,a0,a1) array stored "
                           "under the v2 marker with the tool's affine, so the loader transposes it twice"),
    "D1_internal_array_under_marker": ([(TR, "        nifti_img = nib.Nifti1Image(stored_data.astype(np.uint8), stored_affine)\n",
                                         "        nifti_img = nib.Nifti1Image(mask_data.astype(np.uint8), stored_affine)\n")],
                                       "only the array: the internal order stored, affine and marker otherwise correct"),
    "D2_in_plane_swap_under_marker": ([(TR, ALIGNED_RETURN,
                                        "                return np.transpose(aligned, (1, 0, 2)), aligned_affine\n")],
                                      "the RC-031 legacy in-plane swap (a1,a0,k) stored under the v2 marker"),
    "D3_tool_affine_after_reorientation": ([(TR, ALIGNED_RETURN, "                return aligned, source_affine\n")],
                                           "the reoriented array stored with the tool's own affine (wrong physical "
                                           "position in the directly served file when the tool used another voxel order)"),
    "D4_reorientation_skipped": ([(TR, ALIGNED_RETURN, "                return mask_native, source_affine\n")],
                                 "the tool's array stored as if it were in the MRI's voxel order (no affine alignment)"),
    "D6_marker_never_set": ([(TR, MARKER_LINE, "")],
                            "a correctly ordered file stored without its marker, so the loader applies the legacy order"),
    "F1_legacy_fallback_restored": ([(TR, REFUSAL, "        " + OLD_FALLBACK + "  # former fallback\n" + REFUSAL)],
                                    "the former fallback: with no usable reference image the mask is stored in the "
                                    "legacy (2,1,0) order, known to be in-plane transposed, instead of being refused"),
    "F2_fallback_stores_tool_array_as_is": ([(TR, REFUSAL, "        return mask_native, source_affine\n" + REFUSAL)],
                                            "with no usable reference image the tool's array is stored as if it were "
                                            "in the image's voxel order"),
    "F3_missing_reference_accepted": ([(TR, "                reason = \"the image it was computed on is missing\"\n",
                                        "                " + OLD_FALLBACK + "\n")],
                                      "only the missing / absent reference falls back instead of refusing"),
    "F4_unreadable_reference_accepted": ([(TR, "            reason = f\"the image it was computed on could not be read or the mask "
                                               "could not be placed on it ({e})\"\n",
                                           "            " + OLD_FALLBACK + "\n")],
                                         "only an unreadable reference / indeterminate affine falls back instead of refusing"),
    "F5_refusal_swallowed_by_store": ([(TR, STORE_CALL,
                                        "        try:\n"
                                        "            stored_data, stored_affine = self._orient_mask_for_storage(\n"
                                        "                mask_data, source_affine, reference_mri_path\n"
                                        "            )\n"
                                        "        except SegmentationException:\n"
                                        "            stored_data, stored_affine = np.transpose(mask_data, (1, 0, 2)), source_affine\n")],
                                      "the store path catches the refusal and stores the legacy-order mask anyway"),
    "G1_grid_check_removed": ([(TR, SHAPE_CHECK, "                if False:\n"), (TR, AFFINE_CHECK, "                elif False:\n")],
                              "a mask on another grid (other shape or transform, e.g. resampled to 1 mm) is "
                              "stored after axis reorientation only, as the review reproduced"),
    "G2_shape_check_removed": ([(TR, SHAPE_CHECK, "                if False:\n")],
                               "only the transform is compared: a mask with another array shape is stored"),
    "G3_transform_check_removed": ([(TR, AFFINE_CHECK, "                elif False:\n")],
                                   "only the shape is compared: a mask shifted or with other voxel sizes is stored"),
    "G4_tolerance_of_a_millimetre": ([(TR, "    _GRID_TOLERANCE = 1e-3\n", "    _GRID_TOLERANCE = 1.0\n")],
                                     "a grid tolerance of 1 mm accepts sub-millimetre misplacement"),
    "M1_record_from_mask_in_legacy_order": ([(TR, "        mask_data = SegmentationService._nifti_native_to_internal(stored_data, True)\n",
                                              "        mask_data = SegmentationService._nifti_native_to_internal(stored_data, False)\n")],
                                            "the record's dimensions (image_shape) computed from the mask read in the "
                                            "legacy axis order"),
    "L1_loader_transposes_v2_with_legacy_order": ([(SEG, "        return np.transpose(nifti_data, (2, 0, 1) if oriented_v2 else (2, 1, 0))\n",
                                                    "        return np.transpose(nifti_data, (2, 1, 0))\n")],
                                                  "the load side ignores the marker (v2 file read with the legacy transpose)"),
    "T1_lstai_reference_not_passed": ([ref_dropped(
        "                reference_mri_path=flair_path,  # RC-031: LST-AI segments FLAIR space\n")],
        "LST-AI call site passes no reference MRI (its run must now be refused)"),
    "T2_flames_reference_not_passed": ([ref_dropped(
        "                reference_mri_path=flair_path,  # RC-031: FLAMeS segments FLAIR space\n")],
        "FLAMeS call site passes no reference MRI (its run must now be refused)"),
    "T3_synthseg_reference_not_passed": ([ref_dropped(
        "                reference_mri_path=input_path,  # RC-031: orient by affine\n            )\n\n"
        "            # Store volumes CSV if available\n")],
        "SynthSeg call site passes no reference MRI (its run must now be refused)"),
    "T4_mindglide_lesion_reference_not_passed": ([ref_dropped(
        "                reference_mri_path=input_path,  # RC-031: orient by affine\n            )\n\n"
        "            # Store brain structure mask separately if available\n")],
        "mindGlide lesion-mask call site passes no reference MRI (its run must now be refused)"),
    "T5_mindglide_structure_reference_not_passed": ([ref_dropped(
        "                    reference_mri_path=input_path,  # RC-031: orient by affine\n")],
        "mindGlide structure-mask call site passes no reference MRI (its run must now be refused)"),
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
    files = sorted({e[0] for edits, _w in M.values() for e in edits})
    raw = {p: open(p, "rb").read() for p in files}
    text = {p: b.decode("utf-8").replace("\r\n", "\n") for p, b in raw.items()}
    eol = {p: "\r\n" if b"\r\n" in b else "\n" for p, b in raw.items()}
    for name, (edits, _w) in M.items():
        for path, anchor, _r in edits:
            c = text[path].count(anchor)
            assert c == 1, f"{name}: anchor occurs {c}x in {path}, expected 1"
    res = {"executed": datetime.datetime.now().isoformat(timespec="seconds"),
           "method": "one mutation at a time; each anchor asserted to occur exactly once",
           "hash_basis": "sha256 of the UTF-8 text with LF line endings",
           "source_sha256": {p: hashlib.sha256(text[p].encode("utf-8")).hexdigest() for p in files},
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
