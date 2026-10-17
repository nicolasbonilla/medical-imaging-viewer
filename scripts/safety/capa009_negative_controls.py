"""Negative controls for CAPA-009 / RC-036 (HAZ-010) — reproducible evidence.

Each mutation removes ONE authorization sub-control CAPA-009 added (or re-introduces the
never-awaited dependency), in the real source, one at a time; the script asserts every anchor
occurs exactly once (the sabotage really was applied), runs the bound tests, records the
failing test names and restores the exact original bytes.

Run from the repository root:
    backend/venv/Scripts/python scripts/safety/capa009_negative_controls.py
Output: docs/iec62304/records/risk_verification/CAPA-009_negative_controls_2026-10-17.json
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
OUT = "docs/iec62304/records/risk_verification/CAPA-009_negative_controls_2026-10-17.json"
TESTS = ["tests/unit/test_capa009_object_authorization_everywhere.py"]

R = "backend/app/api/routes/"
PAD = "backend/app/security/patient_access_dependency.py"
OWN = "backend/app/security/ownership.py"
STU, DOC, FHIR, PAT = R + "studies.py", R + "documents.py", R + "fhir.py", R + "patients.py"
AI, CLIN, DICOM, WS = R + "ai_segmentation.py", R + "clinical_tools.py", R + "dicomweb.py", R + "websocket.py"
IMG, SEG = R + "imaging.py", R + "segmentation.py"


def drop(path, line):
    return (path, line, "")


M = {  # name: ([(file, anchor, replacement), ...], what it re-introduces)
    "P1_patient_check_never_awaited": ([
        (PAD, "async def require_patient_access(", "def require_patient_access("),
        (PAD, "    return await _run_authorization(patient_id, current_user)", "    return _run_authorization(patient_id, current_user)"),
    ], "the RC-026 defect: the patient dependency returns a coroutine that is never awaited"),
    "S1_instance_download_url_open": ([drop(STU, "    _authorized=Depends(require_instance_access),   # CAPA-009 (RC-036)\n")],
                                      "signed download link for any instance"),
    "S2_study_download_urls_open": ([drop(STU, "    _authorized=Depends(require_study_access),   # CAPA-009 (RC-036)\n")],
                                    "signed download links for any study"),
    "S3_patient_study_list_open": ([drop(STU, "    _authorized=Depends(require_patient_access),   # CAPA-009 (RC-036)\n")],
                                   "any patient's study list"),
    "S4_expert_mask_open": ([drop(STU, "    # CAPA-009 (RC-036): expert masks are patient data.\n    _authorized=Depends(require_instance_access),\n")],
                            "any expert mask"),
    "S5_create_study_any_patient": ([drop(STU, "    await authorize_patient_id(data.patient_id, current_user)\n")],
                                    "a study created for any patient"),
    "S6_accession_lookup_open": ([drop(STU, "    await authorize_study_id(getattr(study, \"id\", None), current_user)\n")],
                                 "lookup of any study by accession number"),
    "S7_upload_into_any_study": ([drop(STU, "    await authorize_study_id(request.study_id, current_user)\n")],
                                 "an upload into any study"),
    "S8_complete_anyones_upload": ([drop(STU, "    initiators.authorize(\"study-upload\", request.upload_id, current_user, \"Upload\")   # CAPA-009\n")],
                                   "completion of someone else's upload"),
    "D1_study_documents_open": ([drop(DOC, "    _authorized=Depends(require_study_access),   # CAPA-009 (RC-036)\n")],
                                "documents of any study"),
    "D2_version_open": ([drop(DOC, "    _authorized=Depends(require_version_access),   # CAPA-009 (RC-036)\n")],
                        "any document version"),
    "D3_document_download_open": ([drop(DOC, "    _authorized=Depends(require_document_access),   # CAPA-009 (RC-036)\n")],
                                  "signed download link for any document"),
    "D4_patient_document_links_open": ([drop(DOC, "    _authorized=Depends(require_patient_access),   # CAPA-009 (RC-036)\n")],
                                       "signed download links for any patient's documents"),
    "D5_document_upload_any_patient": ([drop(DOC, "    await authorize_patient_id(request.patient_id, current_user)\n")],
                                       "a document uploaded into any patient"),
    "D6_version_upload_any_document": ([drop(DOC, "    await authorize_document_id(request.document_id, current_user)   # CAPA-009 (RC-036)\n")],
                                       "a new version of any document"),
    "D7_complete_anyones_document_upload": ([drop(DOC, "    initiators.authorize(\"document-upload\", request.upload_id, current_user, \"Upload\")   # CAPA-009\n")],
                                            "completion of someone else's document upload"),
    "F1_fhir_patient_open": ([drop(FHIR, "    await authorize_patient_id(patient_id, current_user)   # CAPA-009 (RC-036): 404 unless entitled\n")],
                             "any patient as a FHIR resource"),
    "F2_fhir_study_open": ([drop(FHIR, "    await authorize_study_id(study_id, current_user)   # CAPA-009 (RC-036): 404 unless entitled\n")],
                           "any study as a FHIR resource"),
    "M1_mrn_enumeration": ([drop(PAT, "    await authorize_patient_id(getattr(patient, \"id\", None), current_user)\n")],
                           "enumeration of patients by MRN"),
    "A1_ai_on_any_image": ([(AI, "    request = await _authorized_image_request(request, current_user)   # CAPA-009\n    logger.info(\n        f\"[AI] Auto segmentation",
                             "    logger.info(\n        f\"[AI] Auto segmentation")],
                           "AI segmentation of any image"),
    "A2_volumetry_any_segmentation": ([drop(AI, "    await authorize_mask_specs([{\"type\": \"segmentation\", \"id\": request.segmentation_id}], current_user)\n")],
                                      "volumetry of any segmentation"),
    "A3_volumetry_compare_any_patient": ([drop(AI, "    await authorize_patient_id(request.patient_id, current_user)   # CAPA-009 (RC-036)\n")],
                                         "volumetry comparison for any patient"),
    "A4_anyones_ai_task": ([drop(AI, "    initiators.authorize(\"ai-task\", task_id, current_user, \"Task\")   # CAPA-009\n")],
                           "polling of someone else's AI task"),
    "T1_tool_on_any_image": ([(CLIN, "    (flair_path,) = await _authorized_inputs(\n        [request.flair_file_id], request.patient_id, request.study_id, current_user)\n",
                               "    flair_path = request.flair_file_id\n")],
                             "a clinical tool run on any image"),
    "T2_anyones_tool_task": ([(CLIN, "    \"\"\"\n    initiators.authorize(\"clinical-task\", task_id, current_user, \"Task\")   # CAPA-009\n    task = await tool_runner.get_task_status(task_id)\n    return task",
                               "    \"\"\"\n    task = await tool_runner.get_task_status(task_id)\n    return task")],
                             "polling of someone else's clinical-tool task"),
    "W1_pacs_import_any_patient": ([drop(DICOM, "    await authorize_patient_id(request.patient_id, current_user)\n")],
                                   "a PACS import into any patient"),
    "W2_anyones_import_job": ([drop(DICOM, "    initiators.authorize(\"pacs-import\", job_id, current_user, \"Import job\")   # CAPA-009\n")],
                              "status of someone else's import job"),
    "W3_any_user_tests_any_url": ([(DICOM, "async def test_connection(connection_id: str, current_user: User = _admin):",
                                    "async def test_connection(connection_id: str, current_user: User = Depends(get_current_active_user)):")],
                                  "any user makes the server call a URL"),
    "W4_websocket_stats_open": ([(WS, "    current_user=Depends(require_role(UserRole.ADMIN)),\n", "    current_user=Depends(get_current_active_user),\n")],
                                "another user's connection statistics"),
    "O1_overlay_any_segmentation": ([drop(IMG, "            await authorize_mask_specs([{\"type\": \"segmentation\", \"id\": segmentation_id}], current_user)\n")],
                                    "another patient's mask drawn onto an authorized image"),
    "O2_raw_reference_path": ([(SEG, "            _ref = await require_imaging_access(ref_file_id, current_user)\n            ref_blob = segmentation_service.gcs_bucket.blob(_ref.object_path)",
                                "            ref_blob = segmentation_service.gcs_bucket.blob(ref_file_id)")],
                              "a raw client storage path used as a bucket key"),
    "R1_registry_allows_everyone": ([(OWN, "        if user.role == UserRole.ADMIN:\n            return\n        if handle and",
                                      "        return\n        if handle and")],
                                    "the initiator registry authorizes everyone"),
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
            print(f"{name:40s} {out['failed']} failed / {out['errors']} errors / {out['passed']} passed", flush=True)
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
