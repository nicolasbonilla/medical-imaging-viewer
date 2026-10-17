"""Negative controls for RC-032 (HAZ-005) and CAPA-006 PA-6.1 — reproducible evidence.

Each mutation re-introduces one defect (or removes one sub-control) in the real source, one at a
time. The script asserts that the mutated text occurs exactly once (so the sabotage really was
applied), runs the bound test file, records the failing test names, and restores the originals.
A control whose removal no test detects is reported as such (redundancies are stated, not hidden).

Run from the repository root (needs backend/venv and frontend/node_modules):
    backend/venv/Scripts/python scripts/safety/rc032_negative_controls.py
Output: docs/iec62304/records/risk_verification/RC-032_negative_controls_2026-09-28.json

NEVER run this while anything else edits the files it mutates: it snapshots them and restores the
snapshot at the end (CAPA-006 lesson).
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
OUT = "docs/iec62304/records/risk_verification/RC-032_negative_controls_2026-09-28.json"

SVC = "backend/app/services/ms_region_classifier.py"
RTE = "backend/app/api/routes/segmentation_regions.py"
ANA = "backend/app/api/routes/segmentation_analysis.py"
MCP = "backend/app/mcp/ms_clinical_server.py"
IFU = "docs/mdr/IFU-001_Instructions_For_Use.md"
README = "README.md"
DASH = "frontend/src/components/LesionDashboard.tsx"
EN = "frontend/src/i18n/locales/en.json"
FILES = (SVC, RTE, ANA, MCP, IFU, README, DASH, EN)

T_RC = "tests/unit/test_rc032_region_atlas_guard.py"
T_LAB = "tests/unit/test_capa006_labelling_bound_to_code.py"
T_FE = "src/components/LesionDashboard.rc032.test.ts"

ZM_GATE = ("            if not looks_mni(img.affine, img.shape, img.header):\n"
           "                # HAZ-005 / RC-032: never generate (or persist) an atlas zone map off-MNI.\n")
ZM_GATE_OFF = ("            if False:\n"
               "                # HAZ-005 / RC-032: never generate (or persist) an atlas zone map off-MNI.\n")
SVC_GATE = "    if not looks_mni(target_img.affine, target_img.shape):\n"
CLS_GATE = "                if not looks_mni(src_img.affine, src_img.shape, src_img.header):\n"
REUSE = ('                result = classify_lesions_with_atlas(\n'
         '                    lesion_mask, src_img, voxel_spacing\n'
         '                )\n')
REUSE_MUT = ('                _zid = (metadata.analysis_data or {}).get("zone_map_seg_id")\n'
             '                _ze = segmentation_service.get_loaded(_zid) if _zid else None\n'
             '                result = (__import__("app.services.ms_region_classifier", fromlist=["x"]).classify_from_zone_mask(\n'
             '                    lesion_mask, _ze["masks_3d"], voxel_spacing) if _ze is not None else classify_lesions_with_atlas(\n'
             '                    lesion_mask, src_img, voxel_spacing\n'
             '                ))\n')
DELETE_LOOP = ("        for _ex in segmentation_service.list_segmentations(file_id=file_id):\n"
               "            _ee = segmentation_service.get_loaded(_ex.segmentation_id)\n"
               "            if _ee is not None and getattr(_ee.get(\"metadata\"), \"description\", \"\") == \"MAGNIMS Zone Map\":\n"
               "                segmentation_service.delete_segmentation(_ex.segmentation_id)\n")

M = {  # name: (test target, [(file, old, new), ...], what the mutation restores)
    # ---- MNI gate (service, classify route, zone-map route, longitudinal route)
    "A_service_gate_off": (T_RC, [(SVC, SVC_GATE, "    if False:\n")],
        "generate_zone_map_atlas no longer refuses non-MNI grids"),
    "B_classify_source_gate_off": (T_RC, [(RTE, CLS_GATE, "                if False:\n")],
        "classify-regions no longer checks the source image (covered by the service gate)"),
    "AB_service_and_classify_gates_off": (T_RC, [(SVC, SVC_GATE, "    if False:\n"), (RTE, CLS_GATE, "                if False:\n")],
        "both MNI gates on the classify path removed"),
    "B2_zonemap_route_gate_off": (T_RC, [(RTE, ZM_GATE, ZM_GATE_OFF)],
        "generate-zone-map route pre-check removed (covered by the service gate)"),
    "F_zonemap_route_gate_and_mapping_off": (T_RC, [(RTE, ZM_GATE, ZM_GATE_OFF),
        (RTE, "            except NotMNISpaceError as e:\n                # HAZ-005 / RC-032: never persist an atlas zone map for a non-MNI image.\n",
              "            except KeyboardInterrupt as e:\n                # HAZ-005 / RC-032: never persist an atlas zone map for a non-MNI image.\n")],
        "generate-zone-map: route pre-check AND NotMNISpaceError->422 mapping removed"),
    "L1_gate_no_isotropy": (T_RC, [(SVC, "        if not np.all(vox > 1e-3) or vox.max() / vox.min() > MNI_ISOTROPY_TOLERANCE:\n", "        if not np.all(vox > 1e-3):\n")],
        "gate without the isotropy condition"),
    "L2_gate_no_fov": (T_RC, [(SVC, "        if np.any(np.abs(extent - MNI_REFERENCE_FOV_MM) / MNI_REFERENCE_FOV_MM >= MNI_FOV_TOLERANCE):\n", "        if False:\n")],
        "gate without the per-axis field-of-view condition"),
    "L3_gate_no_centre": (T_RC, [(SVC, "        if np.linalg.norm(centre - MNI_REFERENCE_CENTRE_MM) > MNI_CENTRE_TOLERANCE_MM:\n", "        if False:\n")],
        "gate without the grid-centre condition"),
    "L4_gate_no_header": (T_RC, [(SVC, '                if int(header["sform_code"]) == 0 and int(header["qform_code"]) == 0:\n', "                if False:\n")],
        "gate without the spatial-transform (xform code) condition"),
    "L5_gate_column_max_instead_of_diagonal": (T_RC, [(SVC, "        if any(abs(Rn[c, c]) < 0.999 for c in range(3)):\n", "        if any(np.abs(Rn[:, c]).max() < 0.999 for c in range(3)):\n")],
        "gate accepts permuted axes (redundant with the per-axis FOV condition)"),
    "Z_longitudinal_own_gate": (T_RC, [(ANA, "from app.services.ms_region_classifier import looks_mni as _looks_mni  # noqa: E402\n",
                                        "def _looks_mni(affine, shape):\n    return True\n")],
        "the longitudinal compare route uses its own (accept-all) gate"),
    # ---- spacing / outage
    "C_spacing_from_seg_metadata": (T_RC, [(RTE, '        voxel_spacing = await _voxel_spacing_from_source_image(\n            metadata.file_id, storage_service, context=f"segmentation {segmentation_id}"\n        )\n',
                                            '        voxel_spacing = __import__("app.utils", fromlist=["x"]).resolve_voxel_spacing(metadata, context="x")\n')],
        "classify-regions reads spacing from SegmentationMetadata (the outage)"),
    "E_zonemap_undefined_names": (T_RC, [(RTE, '            file_id, storage_service, context=f"image {file_id}"\n',
                                          '            metadata.file_id, storage_service, context=f"segmentation {segmentation_id}"\n')],
        "generate-zone-map spacing reads undefined metadata/segmentation_id"),
    # ---- axis order / persistence
    "D_atlas_transpose_off": (T_RC, [(SVC, "    zone_mask = np.transpose(zone_mask, (2, 0, 1))\n    if zone_mask.shape != lesion_mask.shape:\n", "    zone_mask = zone_mask\n    if False:\n")],
        "classify_lesions_with_atlas: no transpose, no shape check"),
    "P_zone_mask_shape_check_off": (T_RC, [(SVC, "    if np.shape(zone_mask) != np.shape(lesion_mask):\n", "    if False:\n")],
        "classify_from_zone_mask shape check removed"),
    "M_persisted_zone_map_reused": (T_RC, [(RTE, REUSE, REUSE_MUT)],
        "classify-regions reuses a persisted zone map again"),
    "N_raw_gcs_overwrite": (T_RC, [(RTE, "        segmentation_service.persist(new_seg_id)\n\n        # CAPA-006: no raw GCS overwrite here.",
                                    "        segmentation_service.persist(new_seg_id)\n        segmentation_service.gcs_bucket.blob(f\"segmentations/{new_seg_id}/masks.nii.gz\").upload_from_string(b\"x\")\n\n        # CAPA-006: no raw GCS overwrite here.")],
        "generate-zone-map overwrites the blob directly again"),
    "O_delete_before_validation": (T_RC, [(RTE, "        # --- Find parcellation ---\n", DELETE_LOOP + "        # --- Find parcellation ---\n")],
        "generate-zone-map deletes existing zone maps before validating"),
    "W_delete_before_persist": (T_RC, [(RTE, "        # Save to GCS (metadata + masks via standard pipeline)\n",
        "        for _ex in segmentation_service.list_segmentations(file_id=file_id):\n            if _ex.segmentation_id != new_seg_id:\n                segmentation_service.delete_segmentation(_ex.segmentation_id)\n        # Save to GCS (metadata + masks via standard pipeline)\n")],
        "generate-zone-map deletes old zone maps before the new one is persisted"),
    # ---- parcellation identity
    "G_old_parcellation_autodetect": (T_RC, [(RTE, "                        if np.shape(cand_mask) == np.shape(lesion_mask) and looks_like_freesurfer_parcellation(\n",
        "                        if len(set(int(v) for v in np.unique(cand_mask)) & {2, 3, 4, 7, 8, 10, 16, 41, 42, 43}) >= 3 or looks_like_freesurfer_parcellation(\n")],
        "classify-regions auto-detects a parcellation with the old label test"),
    "H_classify_explicit_parcellation_unchecked": (T_RC, [(RTE, "                    if not looks_like_freesurfer_parcellation(\n", "                    if False and not looks_like_freesurfer_parcellation(\n")],
        "classify-regions accepts any explicit parcellation_id (identity)"),
    "H2_zonemap_explicit_parcellation_unchecked": (T_RC, [(RTE, "\n            if not looks_like_freesurfer_parcellation(\n", "\n            if False and not looks_like_freesurfer_parcellation(\n")],
        "generate-zone-map accepts any explicit parcellation_id (identity)"),
    "Q_same_image_check_off": (T_RC, [(RTE, "                    if (getattr(parc_meta, \"file_id\", None) != metadata.file_id\n", "                    if False and (getattr(parc_meta, \"file_id\", None) != metadata.file_id\n")],
        "classify-regions accepts a parcellation of another image"),
    "Q2_zonemap_same_image_check_off": (T_RC, [(RTE, "            if getattr(parc_meta, \"file_id\", None) != file_id:\n", "            if False:\n")],
        "generate-zone-map accepts a parcellation of another image"),
    "R_required_labels_weakened": (T_RC, [(SVC, "    if not FREESURFER_REQUIRED_LABELS <= labels:\n", "    if not (labels & FREESURFER_REQUIRED_LABELS):\n")],
        "parcellation identity needs only one landmark label"),
    "S_foreground_size_off": (T_RC, [(SVC, "    if foreground_ml is not None and foreground_ml < MIN_PARCELLATION_FOREGROUND_ML:\n", "    if False:\n")],
        "parcellation identity without the brain-sized volume condition"),
    # ---- geometric preconditions
    "I_native_order_image": (T_RC, [(RTE, "                image_data = prepare_geometric_image(geo_affine, geo_native, lesion_mask.shape)\n", "                image_data = geo_native\n")],
        "geometric path receives the native-order image again"),
    "J_no_orientation_check": (T_RC, [(SVC, '    if codes[2] != "S":\n', "    if False:\n")],
        "geometric slice-axis orientation not checked"),
    "T_tilt_cap_off": (T_RC, [(SVC, '    if codes[2] == "S" and tilt_deg > GEOMETRIC_MAX_SLICE_TILT_DEG:\n', "    if False:\n")],
        "geometric path accepts a strongly tilted slice axis"),
    "K_silent_whole_volume_fallback": (T_RC, [
        (SVC, "    if image_data is not None and image_data.shape != lesion_mask.shape:\n        raise ValueError(\n", "    if False:\n        raise ValueError(\n"),
        (SVC, "    if image_data is not None:\n        # Use Otsu threshold to get brain mask\n", "    if image_data is not None and image_data.shape == lesion_mask.shape:\n        # Use Otsu threshold to get brain mask\n")],
        "geometric classifier silently drops a mismatched image"),
    # ---- faults vs refusals
    "U_atlas_fault_silent": (T_RC, [(RTE, '                atlas_error = f"Atlas classification failed ({type(e).__name__})"\n', "                atlas_error = None\n")],
        "an atlas fault degrades silently to geometric again"),
    "V_geometric_fault_swallowed": (T_RC, [(RTE, '                geometric_error = f"Geometric classification failed ({type(e).__name__})"\n', "                geometric_error = None\n")],
        "a geometric fault is swallowed (400/422 instead of 500)"),
    # ---- authorization (RC-029, HAZ-010)
    "X_classify_authz_off": (T_RC, [(RTE, "    _authorized=Depends(require_segmentation_access),\n", "")],
        "classify-regions without object-level authorization"),
    "Y_zonemap_authz_off": (T_RC, [(RTE, "        await authorize_file_scope(\n            file_ids=[file_id],", "        if False: await authorize_file_scope(\n            file_ids=[file_id],")],
        "generate-zone-map without image authorization"),
    # ---- labelling bound to code (CAPA-006 PA-6.1)
    "LAB1_ifu_restates_3_4_3mm": (T_LAB, [(IFU, "**Output (per lesion)**", "PV \u2264 3 mm, JC \u2264 4 mm, IT \u2264 3 mm.\n\n**Output (per lesion)**")],
        "IFU restates the withdrawn thresholds"),
    "LAB2_readme_two_tier": (T_LAB, [(README, "### 3.3 MAGNIMS Region Classification\n", "### 3.3 MAGNIMS Region Classification\n\nTwo-tier classification: parcellation then geometric fallback.\n")],
        "README describes a two-tier cascade"),
    "LAB3_constant_changes": (T_LAB, [(SVC, "PV_DISTANCE_THRESHOLD_MM = 1.5", "PV_DISTANCE_THRESHOLD_MM = 2.0")],
        "code constant changes without the IFU"),
    "LAB4_accuracy_claim_in_code": (T_LAB, [(RTE, '    - method "geometric": uses spatial heuristics only\n', '    - method "geometric": uses spatial heuristics only (~70% accuracy)\n')],
        "an unmeasured accuracy figure reappears in a Class C docstring"),
    "LAB5_validation_claim_in_ifu": (T_LAB, [(IFU, "**Output (per lesion)**", "MAGNIMS classification validated against expert annotations.\n\n**Output (per lesion)**")],
        "an unevidenced validation claim reappears in the IFU"),
    "LAB6_accuracy_claim_for_assistant": (T_LAB, [(MCP, "    Read the MAGNIMS region classification STORED for a lesion segmentation.\n", "    Read the MAGNIMS region classification STORED for a lesion segmentation (~90% accuracy).\n")],
        "an unmeasured accuracy figure reappears in the text the clinical assistant reads"),
    # ---- user interface
    "FE1_atlas_alert_removed": (T_FE, [(DASH, "{classification.atlas_unavailable_reason && (", "{false && (")],
        "UI no longer shows why the atlas was not used"),
    "FE2_geometric_warning_removed": (T_FE, [(DASH, "classification.method === 'geometric' && !classification.atlas_unavailable_reason && !classification.atlas_error && (", "false && (")],
        "UI no longer warns on geometric regions"),
    "FE3_best_restored": (T_FE, [(EN, '"methodAuto": "Auto"', '"methodAuto": "Auto (best)"')],
        "UI calls the automatic method 'best' again"),
    "FE4_atlas_fault_alert_removed": (T_FE, [(DASH, "{classification.atlas_error && (", "{false && (")],
        "UI no longer shows an atlas fault"),
    "FE5_least_accurate_restored": (T_FE, [(EN, '"geometricWarning": "Geometric heuristics: coordinate rules', '"geometricWarning": "Geometric heuristics: the least accurate method; coordinate rules')],
        "UI claims an unmeasured comparative accuracy again"),
}
EXPECTED_UNDETECTED = {
    "B_classify_source_gate_off": "covered by the service gate (generate_zone_map_atlas); detected together in AB",
    "B2_zonemap_route_gate_off": "covered by the service gate; detected together with the 422 mapping in F",
    "L5_gate_column_max_instead_of_diagonal": "a permuted affine has a zero diagonal, so the per-axis FOV condition already rejects it",
}


def run(target):
    if target == T_FE:
        out = os.path.join(os.environ.get("TEMP", ROOT), "rc032_vitest.json")
        subprocess.run(f"npx vitest run {T_FE} --pool=threads --reporter=json --outputFile={out}", cwd="frontend",
                       shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
        d = json.load(open(out, encoding="utf-8"))
        res = [a for f in d["testResults"] for a in f["assertionResults"]]
        failed = [a["title"] for a in res if a["status"] == "failed"]
        return {"failed": len(failed), "passed": sum(a["status"] == "passed" for a in res), "failing_tests": failed}
    r = subprocess.run([PY, "-m", "pytest", target, "-q", "-p", "no:cacheprovider"], cwd="backend",
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    f = re.search(r"(\d+) failed", r.stdout)
    p = re.search(r"(\d+) passed", r.stdout)
    return {"failed": int(f.group(1)) if f else 0, "passed": int(p.group(1)) if p else 0,
            "failing_tests": re.findall(r"FAILED \S+::(\S+)", r.stdout)}


def main():
    orig = {p: open(p, encoding="utf-8").read() for p in FILES}
    for name, (_t, edits, _w) in M.items():          # dry run: every anchor exactly once
        for path, old, _new in edits:
            n = orig[path].count(old)
            assert n == 1, f"{name}: anchor occurs {n}x in {path}: {old[:70]!r}"
    res = {"executed": datetime.datetime.now().isoformat(timespec="seconds"),
           "method": "one mutation at a time; each target string asserted to occur exactly once before replacement",
           "hash_basis": "sha256 of the UTF-8 text as read by Python (universal newlines, LF); a raw CRLF working-tree hash differs",
           "source_sha256": {p: hashlib.sha256(orig[p].encode("utf-8")).hexdigest() for p in FILES},
           "test_sha256": {t: hashlib.sha256(open(os.path.join("backend" if t != T_FE else "frontend", t), encoding="utf-8").read().encode("utf-8")).hexdigest()
                           for t in (T_RC, T_LAB, T_FE)},
           "expected_undetected": EXPECTED_UNDETECTED, "mutations": {}}
    try:
        for name, (target, edits, what) in M.items():
            cur = dict(orig)
            for path, old, new in edits:
                cur[path] = cur[path].replace(old, new)
            for p in FILES:
                if cur[p] != orig[p]:
                    open(p, "w", encoding="utf-8").write(cur[p])
            out = run(target)
            out.update({"restores": what, "test_file": target, "applied": True})
            res["mutations"][name] = out
            for p in FILES:
                if cur[p] != orig[p]:
                    open(p, "w", encoding="utf-8").write(orig[p])
            print(f"{name:45s} {out['failed']} failed / {out['passed']} passed", flush=True)
    finally:
        for p, t in orig.items():
            open(p, "w", encoding="utf-8").write(t)
    res["restored"] = {t: run(t) for t in (T_RC, T_LAB, T_FE)}
    undetected = sorted(n for n, v in res["mutations"].items() if v["failed"] == 0)
    res["undetected"] = undetected
    res["unexpected_undetected"] = sorted(set(undetected) - set(EXPECTED_UNDETECTED))
    json.dump(res, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("restored", {k: (v["passed"], v["failed"]) for k, v in res["restored"].items()})
    print("undetected:", undetected, "| unexpected:", res["unexpected_undetected"])
    return 1 if res["unexpected_undetected"] or any(v["failed"] for v in res["restored"].values()) else 0


if __name__ == "__main__":
    sys.exit(main())
