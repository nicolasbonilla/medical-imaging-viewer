"""Negative controls for RC-029 on the analysis routes (CAPA-007, HAZ-010) — reproducible evidence.

Each mutation removes one authorization sub-control from the real source, one at a time; the
script asserts the mutated text occurs exactly once (the sabotage really was applied), runs the
bound test file, records the failing test names and restores the originals.

Run from the repository root:
    backend/venv/Scripts/python scripts/safety/rc029_negative_controls.py
Output: docs/iec62304/records/risk_verification/RC-029_analysis_negative_controls_2026-10-17.json
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
OUT = "docs/iec62304/records/risk_verification/RC-029_analysis_negative_controls_2026-10-17.json"
ANA = "backend/app/api/routes/segmentation_analysis.py"
RA = "backend/app/security/resource_access.py"
FILES = (ANA, RA)
TEST = "tests/unit/test_rc029_analysis_routes_authorization.py"

DEP = ("    # CAPA-007 RC-029: object-level authorization (404 if not the caller's patient).\n"
       "    _authorized=Depends(require_segmentation_access),\n")


def nth_dep_removed(n):
    """Remove the n-th (0-based) occurrence of the path dependency."""
    def apply(text):
        idx = -1
        for _ in range(n + 1):
            idx = text.index(DEP, idx + 1)
        return text[:idx] + text[idx + len(DEP):]
    return apply


BODY = "        await authorize_mask_specs(mask_specs, current_user)   # CAPA-007 RC-029\n"
TPS = "        await authorize_mask_specs([tp1_spec, tp2_spec], current_user)   # CAPA-007 RC-029\n"


def nth_removed(line, n):
    def apply(text):
        idx = -1
        for _ in range(n + 1):
            idx = text.index(line, idx + 1)
        return text[:idx] + text[idx + len(line):]
    return apply


GCS_NEW = ("                from app.core.container import get_study_service\n"
           "                instance = await get_study_service().get_instance(mask_id)\n"
           "                gcs_path = instance.gcs_object_name\n")
GCS_OLD = ("                gcs_path = spec.get(\"gcs_path\")\n"
           "                if not gcs_path:\n"
           "                    from app.core.container import get_study_service\n"
           "                    instance = await get_study_service().get_instance(mask_id)\n"
           "                    gcs_path = instance.gcs_object_name\n")

M = {  # name: (file, expected occurrences of the anchor, transform, what it restores)
    "P1_lesion_analysis_unprotected": (ANA, DEP, 4, nth_dep_removed(0), "lesion-analysis without object-level authorization"),
    "P2_dis_assessment_unprotected": (ANA, DEP, 4, nth_dep_removed(1), "dis-assessment without object-level authorization"),
    "P3_lesion_annotations_unprotected": (ANA, DEP, 4, nth_dep_removed(2), "lesion-annotations (a write) without object-level authorization"),
    "P4_export_dicom_seg_unprotected": (ANA, DEP, 4, nth_dep_removed(3), "export/dicom-seg without object-level authorization"),
    "B1_compare_unprotected": (ANA, BODY, 2, nth_removed(BODY, 0), "compare without authorization of its masks"),
    "B2_agreement_map_unprotected": (ANA, BODY, 2, nth_removed(BODY, 1), "agreement-map without authorization of its masks"),
    "B3_longitudinal_compare_unprotected": (ANA, TPS, 2, nth_removed(TPS, 0), "longitudinal/compare without authorization"),
    "B4_longitudinal_sel_unprotected": (ANA, TPS, 2, nth_removed(TPS, 1), "longitudinal/sel without authorization"),
    "G1_client_gcs_path_trusted": (ANA, GCS_NEW, 1, lambda t: t.replace(GCS_NEW, GCS_OLD, 1), "compare trusts a client gcs_path again"),
    "H1_helper_allows_everything": (RA, "    if not isinstance(specs, (list, tuple)) or not specs:\n", 1,
                                    lambda t: t.replace("    if not isinstance(specs, (list, tuple)) or not specs:\n",
                                                        "    return None\n    if not isinstance(specs, (list, tuple)) or not specs:\n", 1),
                                    "authorize_mask_specs authorizes nothing"),
    "H2_unknown_type_accepted": (RA, '            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown mask type: {kind}")\n', 1,
                                 lambda t: t.replace('            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown mask type: {kind}")\n',
                                                     "            continue\n", 1),
                                 "authorize_mask_specs skips an unknown mask type"),
}


def run():
    env = dict(os.environ)
    r = subprocess.run([PY, "-m", "pytest", TEST, "-q", "-p", "no:cacheprovider"], cwd="backend",
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    f = re.search(r"(\d+) failed", r.stdout)
    p = re.search(r"(\d+) passed", r.stdout)
    return {"failed": int(f.group(1)) if f else 0, "passed": int(p.group(1)) if p else 0,
            "failing_tests": re.findall(r"FAILED \S+::(\S+)", r.stdout)}


def main():
    orig = {p: open(p, encoding="utf-8").read() for p in FILES}
    for name, (path, anchor, n, _t, _w) in M.items():
        c = orig[path].count(anchor)
        assert c == n, f"{name}: anchor occurs {c}x in {path}, expected {n}"
    res = {"executed": datetime.datetime.now().isoformat(timespec="seconds"),
           "method": "one mutation at a time; each anchor asserted to occur the expected number of times",
           "hash_basis": "sha256 of the UTF-8 text as read by Python (universal newlines, LF)",
           "source_sha256": {p: hashlib.sha256(orig[p].encode("utf-8")).hexdigest() for p in FILES},
           "test_sha256": hashlib.sha256(open(os.path.join("backend", TEST), encoding="utf-8").read().encode("utf-8")).hexdigest(),
           "mutations": {}}
    try:
        for name, (path, _a, _n, transform, what) in M.items():
            mutated = transform(orig[path])
            assert mutated != orig[path], name
            open(path, "w", encoding="utf-8").write(mutated)
            out = run()
            out.update({"restores": what, "applied": True})
            res["mutations"][name] = out
            open(path, "w", encoding="utf-8").write(orig[path])
            print(f"{name:40s} {out['failed']} failed / {out['passed']} passed", flush=True)
    finally:
        for p, t in orig.items():
            open(p, "w", encoding="utf-8").write(t)
    res["restored"] = run()
    res["undetected"] = sorted(n for n, v in res["mutations"].items() if v["failed"] == 0)
    json.dump(res, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("restored", res["restored"]["passed"], "passed /", res["restored"]["failed"], "failed | undetected:", res["undetected"])
    return 1 if res["undetected"] or res["restored"]["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
