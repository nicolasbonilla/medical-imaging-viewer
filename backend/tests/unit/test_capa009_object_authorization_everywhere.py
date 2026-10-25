"""CAPA-009 (HAZ-010, RC-036) — object-level authorization on EVERY mounted route.

Findings these tests bind (docs/iec62304/records/capa/CAPA-009_*.md):
- `require_patient_access` was a plain `def` returning a coroutine. FastAPI runs a plain-def
  dependency in a thread pool and never awaits what it returns, so the patient check never
  executed: every caller with the role permission reached every patient record. RC-026 had
  been "verified" by a test that read source text, never by a request.
- ~35 routes took a patient, study, instance, document, version, segmentation, file, task,
  upload or import reference and authorized nothing: signed download links for any study,
  instance or document; any expert mask; any patient's study list; FHIR Patient/ImagingStudy;
  lookup by MRN (enumerable); study/document creation and uploads into any patient; PACS
  import into any patient; AI and clinical-tool jobs on any image; anyone's job status.
- PACS connections (create, delete, "test" = the server calls any URL) were open to any user.
- `/segmentation/{id}/nifti?ref_file_id=` used a raw client storage path as a bucket key, and
  `/imaging/matplotlib-2d?segmentation_id=` drew any patient's mask onto an authorized image.

The tests (1) classify every mounted route that references an object and check that its
mechanism is still wired — a new, unclassified route fails the build; (2) send real requests
as a radiologist with no care-team entitlement and expect 404 (403 for administrator-only
routes) before any data service is touched; (3) show that an entitled caller passes;
(4) check that no dependency can silently skip itself again.
Negative controls: scripts/safety/capa009_negative_controls.py.
"""
import ast
import inspect
import re
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.main import app
from app.core import container
from app.security import get_current_active_user
from app.security.models import User, UserRole
from app.security.patient_access import CareTeamAssignment
from app.security.ownership import InitiatorRegistry, initiators
import app.security.resource_access as ra
import app.security.patient_access_dependency as pad

ROOT = Path(__file__).resolve().parents[2]
PATIENT = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"
OBJ = "33333333-3333-3333-3333-333333333333"
STUDY = "44444444-4444-4444-4444-444444444444"
SERIES = "55555555-5555-5555-5555-555555555555"
# Must satisfy the RC-027 grammar (every segment a UUID), or every file route would answer
# 404 for a malformed path and these tests would pass for the wrong reason.
FILE = f"patients/{PATIENT}/studies/{STUDY}/series/{SERIES}/image.nii.gz"
OTHER_FILE = f"patients/{OTHER}/studies/{STUDY}/series/{SERIES}/image.nii.gz"

DEPS = ["require_segmentation_access", "require_study_access", "require_series_access",
        "require_instance_access", "require_document_access", "require_patient_access",
        "require_version_access", "require_study_list_scope", "require_document_list_scope"]
CALLS = ["require_imaging_access", "authorize_file_scope", "authorize_mask_specs",
         "authorize_patient_id", "authorize_study_id", "authorize_document_id", "authorize_segmentation_id",
         "_authorized_inputs", "_authorized_image_request"]

# Every mounted route that references an object, with the mechanism that authorizes it.
# A route added without an entry, or losing its mechanism, fails the build.
ROUTE_AUTH = {
    ("POST", "/ai/anomaly/detect"): "call:_authorized_image_request",
    ("POST", "/ai/segment/auto"): "call:_authorized_image_request",
    ("POST", "/ai/segment/interactive"): "call:_authorized_image_request",
    ("GET", "/ai/segment/{task_id}/status"): "initiator",
    ("POST", "/ai/volumetry/compare"): "call:authorize_patient_id",
    ("POST", "/ai/report/generate"): "call:authorize_segmentation_id",   # CAPA-014 (RC-065)
    ("POST", "/ai/volumetry/compute"): "call:authorize_mask_specs",
    ("GET", "/auth/audit-logs"): "admin",   # CAPA-015 RC-067: administrators only (was AUDIT_VIEW, incl. radiologists)
    ("DELETE", "/auth/users/{user_id}"): "perm",
    ("GET", "/auth/users/{user_id}"): "perm",
    ("PATCH", "/auth/users/{user_id}"): "perm",
    ("DELETE", "/auth/webauthn/credentials/{credential_id}"): "self",
    ("POST", "/clinical/flames/segment"): "call:_authorized_inputs",
    ("POST", "/clinical/lst-ai/segment"): "call:_authorized_inputs",
    ("POST", "/clinical/synthseg/parcellate"): "call:_authorized_inputs",
    ("GET", "/clinical/task/{task_id}"): "initiator",
    ("GET", "/clinical/task/{task_id}/result"): "initiator",
    ("POST", "/conformal/select"): "call:require_imaging_access",
    ("POST", "/conformal/status-mask"): "call:require_imaging_access",
    ("DELETE", "/dicomweb/connections/{connection_id}"): "admin",
    ("POST", "/dicomweb/connections/{connection_id}/test"): "admin",
    ("POST", "/dicomweb/import"): "call:authorize_patient_id",
    ("GET", "/dicomweb/import/{job_id}"): "initiator",
    ("GET", "/documents"): "dep:require_document_list_scope",
    ("GET", "/documents/patient/{patient_id}"): "dep:require_patient_access",
    ("GET", "/documents/patient/{patient_id}/download-urls"): "dep:require_patient_access",
    ("GET", "/documents/study/{study_id}"): "dep:require_study_access",
    ("POST", "/documents/upload/complete"): "initiator",
    ("POST", "/documents/upload/init"): "call:authorize_patient_id",
    ("POST", "/documents/versions/upload/complete"): "initiator",
    ("POST", "/documents/versions/upload/init"): "call:authorize_document_id",
    ("GET", "/documents/versions/{version_id}"): "dep:require_version_access",
    ("DELETE", "/documents/{document_id}"): "dep:require_document_access",
    ("GET", "/documents/{document_id}"): "dep:require_document_access",
    ("PATCH", "/documents/{document_id}"): "dep:require_document_access",
    ("GET", "/documents/{document_id}/download-url"): "dep:require_document_access",
    ("GET", "/documents/{document_id}/versions"): "dep:require_document_access",
    ("GET", "/fhir/ImagingStudy/{study_id}"): "call:authorize_study_id",
    ("GET", "/fhir/Patient/{patient_id}"): "call:authorize_patient_id",
    ("GET", "/imaging/matplotlib-2d/{file_id:path}/{slice_index}"): "call:require_imaging_access",
    ("GET", "/imaging/metadata/{file_id:path}"): "call:require_imaging_access",
    ("GET", "/imaging/nifti/{file_id:path}"): "call:require_imaging_access",
    ("GET", "/imaging/process/{file_id:path}"): "call:require_imaging_access",
    ("GET", "/imaging/slice/{file_id:path}/{slice_index}"): "call:require_imaging_access",
    ("GET", "/imaging/volume/{file_id:path}"): "call:require_imaging_access",
    ("GET", "/imaging/voxel-3d/{file_id:path}"): "call:require_imaging_access",
    ("POST", "/imaging/window-level/{file_id:path}"): "call:require_imaging_access",
    ("GET", "/patients/by-mrn/{mrn}"): "call:authorize_patient_id",
    ("PATCH", "/patients/history/{history_id}"): "dep:require_patient_access",   # dead route, see below
    ("DELETE", "/patients/{patient_id}"): "dep:require_patient_access",
    ("GET", "/patients/{patient_id}"): "dep:require_patient_access",
    ("PUT", "/patients/{patient_id}"): "dep:require_patient_access",
    ("GET", "/patients/{patient_id}/care-team"): "dep:require_patient_access",
    ("POST", "/patients/{patient_id}/care-team"): "dep:require_patient_access",
    ("DELETE", "/patients/{patient_id}/care-team/{assignment_id}"): "dep:require_patient_access",
    ("GET", "/patients/{patient_id}/history"): "dep:require_patient_access",
    ("POST", "/patients/{patient_id}/history"): "dep:require_patient_access",
    ("POST", "/segmentation/agreement-map"): "call:authorize_mask_specs",
    ("POST", "/segmentation/compare"): "call:authorize_mask_specs",
    ("POST", "/segmentation/create"): "call:require_imaging_access",
    ("POST", "/segmentation/generate-zone-map"): "call:authorize_file_scope",
    ("GET", "/segmentation/list"): "call:authorize_file_scope",
    ("POST", "/segmentation/longitudinal/compare"): "call:authorize_mask_specs",
    ("POST", "/segmentation/longitudinal/sel"): "call:authorize_mask_specs",
    ("POST", "/segmentation/longitudinal/review"): "call:authorize_mask_specs",   # CAPA-013 RC-060
    ("DELETE", "/segmentation/{segmentation_id}"): "dep:require_segmentation_access",
    ("GET", "/segmentation/{segmentation_id}"): "dep:require_segmentation_access",
    # CP-FLAMES-BROWSER-001 (RC-047): confirm the review of an AI draft
    ("POST", "/segmentation/{segmentation_id}/ai-review/confirm"): "dep:require_segmentation_access",
    ("POST", "/segmentation/{segmentation_id}/classify-regions"): "dep:require_segmentation_access",
    ("GET", "/segmentation/{segmentation_id}/dis-assessment"): "dep:require_segmentation_access",
    ("GET", "/segmentation/{segmentation_id}/export/dicom-seg"): "dep:require_segmentation_access",
    ("GET", "/segmentation/{segmentation_id}/info"): "dep:require_segmentation_access",
    ("PUT", "/segmentation/{segmentation_id}/labels"): "dep:require_segmentation_access",
    ("GET", "/segmentation/{segmentation_id}/lesion-analysis"): "dep:require_segmentation_access",
    ("POST", "/segmentation/{segmentation_id}/lesion-annotations"): "dep:require_segmentation_access",
    ("GET", "/segmentation/{segmentation_id}/mask/binary"): "dep:require_segmentation_access",
    ("PUT", "/segmentation/{segmentation_id}/mask/binary"): "dep:require_segmentation_access",
    ("GET", "/segmentation/{segmentation_id}/nifti"): "dep:require_segmentation_access",
    ("POST", "/segmentation/{segmentation_id}/paint"): "dep:require_segmentation_access",
    ("POST", "/segmentation/{segmentation_id}/save"): "dep:require_segmentation_access",
    ("GET", "/segmentation/{segmentation_id}/slice/{slice_index}/mask"): "dep:require_segmentation_access",
    ("GET", "/segmentation/{segmentation_id}/slice/{slice_index}/overlay"): "dep:require_segmentation_access",
    ("GET", "/segmentation/{segmentation_id}/slice/{slice_index}/segmentation-only"): "dep:require_segmentation_access",
    ("GET", "/studies"): "dep:require_study_list_scope",
    ("POST", "/studies"): "call:authorize_patient_id",
    ("GET", "/studies/accession/{accession_number}"): "call:authorize_study_id",
    ("DELETE", "/studies/instances/{instance_id}"): "dep:require_instance_access",
    ("GET", "/studies/instances/{instance_id}"): "dep:require_instance_access",
    ("PATCH", "/studies/instances/{instance_id}"): "dep:require_instance_access",
    ("GET", "/studies/instances/{instance_id}/download-url"): "dep:require_instance_access",
    ("GET", "/studies/instances/{instance_id}/mask-data"): "dep:require_instance_access",
    ("GET", "/studies/patient/{patient_id}"): "dep:require_patient_access",
    ("DELETE", "/studies/series/{series_id}"): "dep:require_series_access",
    ("GET", "/studies/series/{series_id}"): "dep:require_series_access",
    ("GET", "/studies/series/{series_id}/instances"): "dep:require_series_access",
    ("POST", "/studies/upload/complete"): "initiator",
    ("POST", "/studies/upload/init"): "call:authorize_study_id",
    ("DELETE", "/studies/{study_id}"): "dep:require_study_access",
    ("GET", "/studies/{study_id}"): "dep:require_study_access",
    ("PUT", "/studies/{study_id}"): "dep:require_study_access",
    ("GET", "/studies/{study_id}/download-urls"): "dep:require_study_access",
    ("GET", "/studies/{study_id}/series"): "dep:require_study_access",
    ("POST", "/studies/{study_id}/series"): "dep:require_study_access",
    ("GET", "/ws/connections/{connection_id}"): "admin",
}

# Routes that reference an identifier but read or change no patient object — each justified.
EXEMPT = {
    ("POST", "/auth/login"): "authentication; the id is a captcha challenge",
    ("GET", "/dicomweb/connections/{connection_id}"): "PACS connection configuration, credentials masked; no patient data",
    ("POST", "/dicomweb/search/series"): "queries the external PACS through an administrator-configured connection",
    ("POST", "/dicomweb/search/studies"): "queries the external PACS; patient_id is the PACS PatientID filter",
    ("GET", "/fhir/DiagnosticReport/{report_id}"): "builds a template from the identifiers; reads no stored object",
}

# PATCH /patients/history/{history_id} depends on require_patient_access but has no
# {patient_id} in its path, so it always fails validation (422), and its service raises
# NotImplementedError. A dead route, recorded in CAPA-009 (finding 6); never a leak.
DEAD_ROUTES = {("PATCH", "/patients/history/{history_id}")}


def _deps(dependant, acc=None):
    acc = set() if acc is None else acc
    for d in dependant.dependencies:
        acc.add(getattr(d.call, "__name__", str(d.call)))
        _deps(d, acc)
    return acc


def _object_refs(route):
    refs = [p for p in re.findall(r"\{([^}:]+)", route.path) if p != "slice_index"]
    refs += [q.name for q in route.dependant.query_params if q.name.endswith("_id")]
    for b in route.dependant.body_params:
        t = getattr(b, "type_", None) or b.field_info.annotation
        if hasattr(t, "model_fields"):
            refs += [f for f in t.model_fields
                     if f.endswith("_id") or f in ("file_id", "masks", "tp1", "tp2", "timepoints")]
    raw_body = any(p.annotation.__name__ == "Request" for p in inspect.signature(route.endpoint).parameters.values()
                   if isinstance(p.annotation, type))
    if raw_body and not route.path.startswith("/api/v1/auth"):
        refs.append("<raw request body>")
    return refs


def _mechanism(route):
    deps = _deps(route.dependant)
    src = inspect.getsource(route.endpoint)
    for name in DEPS:
        if name in deps:
            return "dep:" + name
    if "role_checker" in deps:
        return "admin"
    if "permission_checker" in deps and route.path.startswith("/api/v1/auth/"):
        return "perm"
    if "initiators.authorize(" in src:
        return "initiator"
    for name in CALLS:
        if name + "(" in src:
            return "call:" + name
    if "current_user.id" in src and "webauthn" in route.path:
        return "self"
    return None


def _routes():
    out = {}
    for r in app.routes:
        if isinstance(r, APIRoute) and r.path.startswith("/api/v1") and _object_refs(r):
            for m in r.methods:
                out[(m, r.path[len("/api/v1"):])] = r
    return out


# ----------------------------------------------------------------------------- structure
@pytest.mark.unit
def test_rc036_every_object_route_is_classified_and_keeps_its_mechanism():
    routes = _routes()
    unclassified = sorted(k for k in routes if k not in ROUTE_AUTH and k not in EXEMPT)
    assert not unclassified, f"routes referencing objects with no classified authorization: {unclassified}"
    wrong = {k: (ROUTE_AUTH[k], _mechanism(routes[k])) for k in ROUTE_AUTH
             if k in routes and _mechanism(routes[k]) != ROUTE_AUTH[k]}
    assert not wrong, f"routes whose authorization changed or disappeared: {wrong}"
    missing = sorted(k for k in list(ROUTE_AUTH) + list(EXEMPT) if k not in routes)
    assert not missing, f"classified routes no longer mounted (update the table): {missing}"


@pytest.mark.unit
def test_rc036_path_dependencies_match_the_path():
    """A require_X_access dependency reads {X_id} from the path; on a path without it the
    route can never authorize anything (it fails validation instead)."""
    needs = {"require_patient_access": "{patient_id}", "require_study_access": "{study_id}",
             "require_series_access": "{series_id}", "require_instance_access": "{instance_id}",
             "require_document_access": "{document_id}", "require_version_access": "{version_id}",
             "require_segmentation_access": "{segmentation_id}"}
    bad = []
    for key, route in _routes().items():
        for dep, param in needs.items():
            if dep in _deps(route.dependant) and param not in route.path and key not in DEAD_ROUTES:
                bad.append((key, dep))
    assert not bad, bad


@pytest.mark.unit
def test_rc036_no_dependency_can_silently_skip_itself():
    """The root cause of the RC-026 failure: a plain `def` dependency that RETURNS a coroutine.
    FastAPI never awaits it. Every authorization callable is now `async def`, and no plain-def
    function used in Depends(...) anywhere in app/ returns a call to an async function."""
    assert inspect.iscoroutinefunction(pad.require_patient_access)
    assert inspect.iscoroutinefunction(pad.require_imaging_access)
    for name in DEPS:
        fn = getattr(ra, name, None) or getattr(pad, name)
        assert inspect.iscoroutinefunction(fn), name
    defs, depends = {}, set()
    for f in (ROOT / "app").rglob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defs.setdefault(n.name, []).append(n)
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "Depends" and n.args \
                    and isinstance(n.args[0], ast.Name):
                depends.add(n.args[0].id)
    async_names = {k for k, v in defs.items() if any(isinstance(x, ast.AsyncFunctionDef) for x in v)}
    offenders = []
    for name in depends:
        for node in defs.get(name, []):
            if isinstance(node, ast.FunctionDef):
                for r in ast.walk(node):
                    if isinstance(r, ast.Return) and isinstance(r.value, ast.Call):
                        callee = getattr(r.value.func, "id", getattr(r.value.func, "attr", ""))
                        if callee in async_names:
                            offenders.append((name, callee))
    assert not offenders, f"plain-def dependencies returning a coroutine (never awaited): {offenders}"


# ----------------------------------------------------------------------------- behaviour
def _user(uid="stranger-1", role=UserRole.RADIOLOGIST):
    now = datetime.utcnow()
    return User(id=uid, username="stranger", email="stranger@example.com", full_name="Stranger",
                role=role, is_active=True, is_locked=False, email_verified=True,
                created_at=now, updated_at=now)


class _Never:
    """A data service the route must not reach before authorization."""
    def __init__(self, name):
        self._name = name

    def __getattr__(self, attr):
        raise AssertionError(f"{self._name}.{attr} used before authorization")


class _Patients:
    async def get_patient(self, pid, **kw):
        return type("P", (), {"created_by": "someone-else", "id": pid})()

    async def get_patient_by_mrn(self, mrn):
        return type("P", (), {"created_by": "someone-else", "id": PATIENT})()


class _CareTeam:
    def __init__(self, entitled=()):
        self._e = [CareTeamAssignment(patient_id=p, user_id="stranger-1", role_in_care="attending",
                                      revoked_at=None) for p in entitled]

    def list_entitlements_for_user(self, uid):
        return [e for e in self._e if e.user_id == uid]


class _Docs:
    async def get_version(self, vid):
        return type("V", (), {"document_id": OBJ})()


def _wire(monkeypatch, entitled=(), seg_owner=PATIENT, user=None):
    async def owner(*a, **k):
        return PATIENT

    async def seg(*a, **k):
        return seg_owner

    for name in ("resolve_study_patient_id", "resolve_series_patient_id",
                 "resolve_instance_patient_id", "resolve_document_patient_id"):
        monkeypatch.setattr(ra, name, owner)
    monkeypatch.setattr(ra, "resolve_segmentation_patient_id", seg)
    monkeypatch.setattr(ra, "_patient_service", lambda: _Patients())
    monkeypatch.setattr(ra, "_care_team_service", lambda: _CareTeam(entitled))
    monkeypatch.setattr(ra, "_document_service", lambda: _Docs())
    monkeypatch.setattr(ra, "_study_service", lambda: _Never("study_service(resolver)"))
    monkeypatch.setattr(ra, "_segmentation_service", lambda: _Never("segmentation_service(resolver)"))
    monkeypatch.setattr(pad, "_get_patient_service", lambda: _Patients())
    monkeypatch.setattr(pad, "_get_care_team_service", lambda: _CareTeam(entitled))
    import app.api.routes.ai_segmentation as ai_routes
    import app.api.routes.patients as patient_routes
    overrides = {
        patient_routes.get_care_team_service: lambda: _Never("care_team_service"),
        get_current_active_user: lambda: user or _user(),
        container.get_study_service: lambda: _Never("study_service"),
        container.get_document_service: lambda: _Never("document_service"),
        container.get_storage_service: lambda: _Never("storage_service"),
        container.get_segmentation_service: lambda: _Never("segmentation_service"),
        container.get_tool_runner_service: lambda: _Never("tool_runner"),
        container.get_patient_service: lambda: _Patients(),
        ai_routes.get_ai_service: lambda: _Never("ai_service"),
        ai_routes.get_volumetry_service: lambda: _Never("volumetry_service"),
    }
    app.dependency_overrides.update(overrides)
    return list(overrides)


@pytest.fixture
def stranger(monkeypatch):
    keys = _wire(monkeypatch)
    initiators.clear()
    yield TestClient(app, raise_server_exceptions=False)
    for k in keys:
        app.dependency_overrides.pop(k, None)
    initiators.clear()


CHECKSUM = "0" * 64
DENIED = [  # (method, path, json) -> 404 for a caller without access, before any data service
    ("get", f"/patients/{PATIENT}", None),
    ("get", f"/patients/{PATIENT}/care-team", None),
    ("get", f"/patients/{PATIENT}/history", None),
    ("get", "/patients/by-mrn/MRN-0001", None),
    ("get", f"/studies/instances/{OBJ}/download-url", None),
    ("get", f"/studies/instances/{OBJ}/mask-data", None),
    ("get", f"/studies/{OBJ}/download-urls", None),
    ("get", f"/studies/patient/{PATIENT}", None),
    ("post", "/studies", {"patient_id": PATIENT, "modality": "MR", "study_date": "2026-01-01T00:00:00"}),
    ("post", "/studies/upload/init", {"study_id": OBJ, "filename": "a.nii.gz",
                                      "content_type": "application/gzip", "file_size_bytes": 10}),
    ("post", "/studies/upload/complete", {"upload_id": "u-1", "checksum_sha256": CHECKSUM}),
    ("get", f"/documents/patient/{PATIENT}", None),
    ("get", f"/documents/patient/{PATIENT}/download-urls", None),
    ("get", f"/documents/study/{OBJ}", None),
    ("get", f"/documents/{OBJ}/download-url", None),
    ("get", f"/documents/versions/{OBJ}", None),
    ("post", "/documents/upload/init", {"patient_id": PATIENT, "title": "t", "category": "clinical-note",
                                        "document_date": "2026-01-01", "filename": "a.pdf",
                                        "content_type": "application/pdf", "file_size_bytes": 10}),
    ("post", "/documents/upload/complete", {"upload_id": "u-1", "checksum_sha256": CHECKSUM}),
    ("post", "/documents/versions/upload/init", {"document_id": OBJ, "filename": "a.pdf",
                                                 "content_type": "application/pdf", "file_size_bytes": 10}),
    ("post", "/documents/versions/upload/complete", {"upload_id": "u-1", "checksum_sha256": CHECKSUM}),
    ("get", f"/fhir/Patient/{PATIENT}", None),
    ("get", f"/fhir/ImagingStudy/{OBJ}", None),
    ("post", "/ai/segment/auto", {"file_id": FILE}),
    ("post", "/ai/anomaly/detect", {"file_id": FILE}),
    ("post", "/ai/volumetry/compute", {"segmentation_id": "s1"}),
    ("post", "/ai/volumetry/compare", {"patient_id": PATIENT, "timepoints": [{}, {}]}),
    ("post", "/ai/report/generate", {"segmentation_id": "s1",                       # CAPA-014
                                     "findings": {"lesion_analysis": {"total_count": 1}}}),
    ("get", "/ai/segment/t-1/status", None),
    ("post", "/clinical/flames/segment", {"flair_file_id": FILE}),
    ("post", "/clinical/synthseg/parcellate", {"file_id": FILE}),
    ("get", "/clinical/task/t-1", None),
    ("get", "/clinical/task/t-1/result", None),
    ("post", "/dicomweb/import", {"connection_id": "c", "study_instance_uid": "1", "series_instance_uid": "2",
                                  "patient_id": PATIENT}),
    ("get", "/dicomweb/import/j-1", None),
    ("post", f"/segmentation/{OBJ}/ai-review/confirm", None),  # CP-FLAMES-BROWSER-001 (RC-047)
]
ADMIN_ONLY = [
    ("post", "/dicomweb/connections", {"name": "x", "url": "http://169.254.169.254/"}),
    ("delete", "/dicomweb/connections/c-1", None),
    ("post", "/dicomweb/connections/c-1/test", None),
    ("get", "/ws/connections/c-1", None),
]


def _call(client, method, path, body):
    fn = getattr(client, method)
    return fn("/api/v1" + path, json=body) if body is not None else fn("/api/v1" + path)


@pytest.mark.unit
@pytest.mark.parametrize("method,path,body", DENIED, ids=[f"{m} {p}" for m, p, _ in DENIED])
def test_rc036_a_caller_without_access_gets_404_before_any_data_is_touched(stranger, method, path, body):
    r = _call(stranger, method, path, body)
    assert r.status_code == 404, f"{method.upper()} {path}: {r.status_code} {r.text[:300]}"


@pytest.mark.unit
@pytest.mark.parametrize("method,path,body", ADMIN_ONLY, ids=[f"{m} {p}" for m, p, _ in ADMIN_ONLY])
def test_rc036_administrator_only_routes_refuse_other_roles(stranger, method, path, body):
    r = _call(stranger, method, path, body)
    assert r.status_code == 403, f"{method.upper()} {path}: {r.status_code} {r.text[:300]}"


@pytest.mark.unit
def test_rc036_an_entitled_caller_passes_the_same_checks(monkeypatch):
    """Positive control: the 404s above come from the authorization, not from the fakes."""
    keys = _wire(monkeypatch, entitled=[PATIENT])
    calls = []

    class _Studies:
        async def get_download_url(self, instance_id, minutes):
            calls.append("download-url")
            return "https://signed.example/instance"

    class _PatientsData(_Patients):
        async def get_patient(self, pid, **kw):
            calls.append("patient")
            return await super().get_patient(pid, **kw)

    app.dependency_overrides[container.get_study_service] = lambda: _Studies()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get(f"/api/v1/studies/instances/{OBJ}/download-url")
        assert r.status_code == 200 and r.json()["url"].startswith("https://"), r.text
        assert calls == ["download-url"]
        r = client.get(f"/api/v1/patients/{PATIENT}")
        assert r.status_code != 404, r.text      # authorization passed; the fake record is incomplete
    finally:
        for k in keys:
            app.dependency_overrides.pop(k, None)


@pytest.mark.unit
def test_rc036_an_overlay_or_reference_from_another_patient_is_refused(monkeypatch):
    """Authorized on the image, not on the second object: the overlay segmentation (imaging)
    and the reference image (segmentation NIfTI) must be authorized too."""
    keys = _wire(monkeypatch, entitled=[PATIENT], seg_owner=OTHER)
    try:
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get(f"/api/v1/imaging/matplotlib-2d/{FILE}/0", params={"segmentation_id": "s-other"})
        assert r.status_code == 404, r.text
    finally:
        for k in keys:
            app.dependency_overrides.pop(k, None)
    keys = _wire(monkeypatch, entitled=[PATIENT], seg_owner=PATIENT)

    class _SegData:
        def get_segmentation_nifti(self, sid):
            return b"not-read-before-authorization"

        @property
        def gcs_bucket(self):
            raise AssertionError("bucket read before the reference image was authorized")

    app.dependency_overrides[container.get_segmentation_service] = lambda: _SegData()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/api/v1/segmentation/s-1/nifti", params={"ref_file_id": OTHER_FILE})
        assert r.status_code == 404, r.text
    finally:
        for k in keys:
            app.dependency_overrides.pop(k, None)


@pytest.mark.unit
def test_rc036_tool_inputs_must_belong_to_one_patient_and_match_the_ids(monkeypatch):
    keys = _wire(monkeypatch, entitled=[PATIENT, OTHER])
    try:
        client = TestClient(app, raise_server_exceptions=False)
        r = client.post("/api/v1/clinical/lst-ai/segment", json={"t1_file_id": FILE, "flair_file_id": OTHER_FILE})
        assert r.status_code == 400, r.text
        r = client.post("/api/v1/clinical/flames/segment", json={"flair_file_id": FILE, "patient_id": OTHER})
        assert r.status_code == 400, r.text
    finally:
        for k in keys:
            app.dependency_overrides.pop(k, None)


# ----------------------------------------------------------------------------- the registry
@pytest.mark.unit
def test_rc036_initiator_registry_allows_the_initiator_and_admins_only():
    from fastapi import HTTPException
    reg = InitiatorRegistry(ttl_seconds=3600)
    owner, other, admin = _user("u-owner"), _user("u-other"), _user("u-admin", UserRole.ADMIN)
    reg.record("task", "t-1", owner)
    reg.authorize("task", "t-1", owner)
    reg.authorize("task", "t-1", admin)
    reg.authorize("task", "t-unknown", admin)
    for user, handle in ((other, "t-1"), (owner, "t-unknown"), (owner, None)):
        with pytest.raises(HTTPException) as e:
            reg.authorize("task", handle, user)
        assert e.value.status_code == 404
    expired = InitiatorRegistry(ttl_seconds=-1)
    expired.record("task", "t-1", owner)
    with pytest.raises(HTTPException):
        expired.authorize("task", "t-1", owner)


@pytest.mark.unit
def test_rc036_file_paths_used_by_these_tests_are_valid_storage_references():
    from app.security.storage_access import parse_patient_storage_ref
    assert str(parse_patient_storage_ref(FILE).patient_id) == PATIENT
    assert str(parse_patient_storage_ref(OTHER_FILE).patient_id) == OTHER


@pytest.mark.unit
def test_rc036_an_entitled_caller_reaches_the_ai_service_with_the_authorized_path(monkeypatch):
    """Positive control for the file routes: the image check passes and the service receives
    the parsed path, not the raw client string."""
    from fastapi import HTTPException
    import app.api.routes.ai_segmentation as ai_routes
    keys = _wire(monkeypatch, entitled=[PATIENT])
    received = []

    class _Ai:
        async def segment_auto(self, request):
            received.append(request.file_id)
            raise HTTPException(status_code=418, detail="reached")

    app.dependency_overrides[ai_routes.get_ai_service] = lambda: _Ai()
    try:
        r = TestClient(app, raise_server_exceptions=False).post("/api/v1/ai/segment/auto", json={"file_id": FILE})
        assert r.status_code == 418, r.text
        assert received == [FILE]
    finally:
        for k in keys:
            app.dependency_overrides.pop(k, None)


@pytest.mark.unit
def test_rc036_a_lookup_by_accession_number_does_not_bypass_the_patient_check(monkeypatch):
    """The lookup necessarily runs first; the found study must then be authorized."""
    keys = _wire(monkeypatch)

    class _Studies:
        async def get_study_by_accession(self, accession):
            return type("S", (), {"id": OBJ, "patient_id": PATIENT})()

    app.dependency_overrides[container.get_study_service] = lambda: _Studies()
    try:
        r = TestClient(app, raise_server_exceptions=False).get("/api/v1/studies/accession/ACC-0001")
        assert r.status_code == 404, r.text
    finally:
        for k in keys:
            app.dependency_overrides.pop(k, None)
