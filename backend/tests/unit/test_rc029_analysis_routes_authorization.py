"""RC-029 (HAZ-010) — object-level authorization on EVERY mounted segmentation route (CAPA-007).

RC-029 was verified on 2026-07-19 by a test that read segmentation.py only. The C3 refactor
(2026-07-10) had already moved ten routes into segmentation_regions.py and
segmentation_analysis.py; those checked authentication only. Eight are live analysis routes:
lesion-analysis, dis-assessment, lesion-annotations (a write), export/dicom-seg, compare,
agreement-map, longitudinal/compare and longitudinal/sel. compare also used a client-supplied
"gcs_path" as the storage key (RC-027 class).

These tests enumerate the routes the APP actually mounts, so a route moved into a new file can
no longer escape (CAPA-006 PA-6.2, authorization half):
- every /segmentation route with {segmentation_id} depends on require_segmentation_access;
- every other /segmentation route is in a classified list and its handler calls the scope
  authorization that fits its input;
- a caller without access to the patient gets 404 from each of the eight analysis routes;
- a client "gcs_path" is never used as a storage key.

Negative controls: scripts/safety/rc029_negative_controls.py; record
docs/iec62304/records/risk_verification/RC-029_analysis_negative_controls_2026-10-17.json.
"""
import inspect
from datetime import datetime

import numpy as np
import nibabel as nib
import pytest

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.main import app
from app.core.container import get_segmentation_service, get_storage_service
from app.security import get_current_active_user
from app.security.models import User, UserRole
from app.security.patient_access import CareTeamAssignment
import app.security.resource_access as resource_access
from app.security.resource_access import require_segmentation_access

PATIENT = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"
FILE_ID = f"patients/{PATIENT}/studies/s/series/x/image.nii.gz"

# Every /segmentation route WITHOUT {segmentation_id} must be classified here, with the
# authorization call its handler must make. A new unclassified route fails the build.
SCOPED_ROUTES = {
    ("POST", "/api/v1/segmentation/create"): "require_imaging_access",
    ("GET", "/api/v1/segmentation/list"): "authorize_file_scope",
    ("POST", "/api/v1/segmentation/generate-zone-map"): "authorize_file_scope",
    ("POST", "/api/v1/segmentation/compare"): "authorize_mask_specs",
    ("POST", "/api/v1/segmentation/agreement-map"): "authorize_mask_specs",
    ("POST", "/api/v1/segmentation/longitudinal/compare"): "authorize_mask_specs",
    ("POST", "/api/v1/segmentation/longitudinal/sel"): "authorize_mask_specs",
    ("POST", "/api/v1/segmentation/longitudinal/review"): "authorize_mask_specs",   # CAPA-013 RC-060
}


def _dependency_calls(dependant, acc=None):
    acc = set() if acc is None else acc
    for d in dependant.dependencies:
        acc.add(d.call)
        _dependency_calls(d, acc)
    return acc


def _segmentation_routes():
    return [r for r in app.routes if isinstance(r, APIRoute) and r.path.startswith("/api/v1/segmentation")]


# ----------------------------------------------------------------------------- structural
@pytest.mark.unit
def test_rc029_every_segmentation_object_route_requires_object_access():
    routes = [r for r in _segmentation_routes() if "{segmentation_id}" in r.path]
    assert len(routes) >= 17
    missing = [f"{sorted(r.methods)} {r.path}" for r in routes
               if require_segmentation_access not in _dependency_calls(r.dependant)]
    assert not missing, f"segmentation routes without object-level authorization: {missing}"


@pytest.mark.unit
def test_rc029_every_other_segmentation_route_is_classified_and_authorizes_its_scope():
    unclassified, not_calling = [], []
    for r in _segmentation_routes():
        if "{segmentation_id}" in r.path:
            continue
        for method in r.methods:
            key = (method, r.path)
            if key not in SCOPED_ROUTES:
                unclassified.append(key)
                continue
            source = inspect.getsource(r.endpoint)
            if f"{SCOPED_ROUTES[key]}(" not in source:
                not_calling.append((key, SCOPED_ROUTES[key]))
    assert not unclassified, f"new segmentation routes with no classified authorization: {unclassified}"
    assert not not_calling, f"routes that do not call their scope authorization: {not_calling}"


# ----------------------------------------------------------------------------- behavioural
class _Meta:
    def __init__(self, file_id=FILE_ID):
        self.file_id = file_id


class _SegSvc:
    async def get_metadata(self, sid):
        return _Meta()


class _Patients:
    async def get_patient(self, pid):
        return type("P", (), {"created_by": "someone-else"})()


class _CareTeam:
    def __init__(self, entitlements=()):
        self._e = list(entitlements)

    def list_entitlements_for_user(self, user_id):
        return [e for e in self._e if e.user_id == user_id]


def _user(role=UserRole.RADIOLOGIST, uid="u-2"):
    now = datetime.utcnow()
    return User(id=uid, username="clinician", email="clinician@example.com", full_name="Clinician",
                role=role, is_active=True, is_locked=False, email_verified=True,
                created_at=now, updated_at=now)


@pytest.fixture
def stranger_client(monkeypatch):
    """A RADIOLOGIST with no care-team entitlement for the patient. No datastore is touched."""
    monkeypatch.setattr(resource_access, "_segmentation_service", lambda: _SegSvc())
    monkeypatch.setattr(resource_access, "_patient_service", lambda: _Patients())
    monkeypatch.setattr(resource_access, "_care_team_service", lambda: _CareTeam())

    class _NeverLoaded:          # the route must refuse BEFORE touching the segmentation
        def __getattr__(self, name):
            raise AssertionError(f"segmentation service used before authorization: {name}")

    class _NeverDownloaded:
        async def download_file(self, *a, **k):
            raise AssertionError("storage read before authorization")

    app.dependency_overrides[get_current_active_user] = lambda: _user()
    app.dependency_overrides[get_segmentation_service] = lambda: _NeverLoaded()
    app.dependency_overrides[get_storage_service] = lambda: _NeverDownloaded()
    yield TestClient(app)
    for dep in (get_current_active_user, get_segmentation_service, get_storage_service):
        app.dependency_overrides.pop(dep, None)


TWO = [{"type": "segmentation", "id": "s1"}, {"type": "segmentation", "id": "s2"}]
EIGHT_ROUTES = [
    ("get", "/api/v1/segmentation/s1/lesion-analysis", None),
    ("get", "/api/v1/segmentation/s1/dis-assessment", None),
    ("post", "/api/v1/segmentation/s1/lesion-annotations", {"annotations": []}),
    ("get", "/api/v1/segmentation/s1/export/dicom-seg", None),
    ("post", "/api/v1/segmentation/compare", {"masks": TWO}),
    ("post", "/api/v1/segmentation/agreement-map", {"masks": TWO}),
    ("post", "/api/v1/segmentation/longitudinal/compare", {"tp1": TWO[0], "tp2": TWO[1]}),
    ("post", "/api/v1/segmentation/longitudinal/sel", {"tp1": TWO[0], "tp2": TWO[1]}),
]


@pytest.mark.unit
@pytest.mark.parametrize("method,path,body", EIGHT_ROUTES, ids=[p.rsplit("/", 1)[-1] for _, p, _ in EIGHT_ROUTES])
def test_rc029_analysis_route_refuses_a_caller_without_access(stranger_client, method, path, body):
    r = getattr(stranger_client, method)(path, json=body) if body is not None else getattr(stranger_client, method)(path)
    assert r.status_code == 404, f"{path}: {r.status_code} {r.text[:200]}"


# ----------------------------------------------------------------------------- the helper
@pytest.mark.unit
@pytest.mark.asyncio
async def test_rc029_mask_specs_helper_allows_entitled_and_refuses_the_rest(monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setattr(resource_access, "_segmentation_service", lambda: _SegSvc())
    monkeypatch.setattr(resource_access, "_patient_service", lambda: _Patients())
    entitled = CareTeamAssignment(patient_id=PATIENT, user_id="u-2", role_in_care="attending", revoked_at=None)
    monkeypatch.setattr(resource_access, "_care_team_service", lambda: _CareTeam([entitled]))
    await resource_access.authorize_mask_specs(TWO, _user())                      # entitled: no error
    for bad, code in [([], 400), (["s1"], 400), ([{"type": "pdf", "id": "x"}], 400)]:
        with pytest.raises(HTTPException) as e:
            await resource_access.authorize_mask_specs(bad, _user())
        assert e.value.status_code == code
    monkeypatch.setattr(resource_access, "_care_team_service", lambda: _CareTeam())
    with pytest.raises(HTTPException) as e:
        await resource_access.authorize_mask_specs(TWO, _user())                  # not entitled
    assert e.value.status_code == 404


@pytest.mark.unit
def test_rc029_compare_ignores_a_client_storage_path(monkeypatch):
    """compare used a client "gcs_path" as the storage key: any object could be read."""
    import app.api.routes.segmentation_analysis as analysis_routes
    import app.core.container as container

    async def _authorized(specs, user):
        return None

    monkeypatch.setattr(analysis_routes, "authorize_mask_specs", _authorized)
    own_path = f"patients/{PATIENT}/studies/s/series/x/mask.nii.gz"
    foreign_path = f"patients/{OTHER}/studies/s/series/y/image.nii.gz"

    class _Studies:
        async def get_instance(self, instance_id):
            return type("Instance", (), {"gcs_object_name": own_path})()

    monkeypatch.setattr(container, "get_study_service", lambda: _Studies())
    requested = []

    class _Storage:
        async def download_file(self, bucket, key):
            requested.append(key)
            img = nib.Nifti1Image(np.zeros((8, 8, 4), np.uint8), np.eye(4))
            return img.to_bytes()

    app.dependency_overrides[get_current_active_user] = lambda: _user(UserRole.ADMIN, "admin-1")
    app.dependency_overrides[get_storage_service] = lambda: _Storage()
    try:
        TestClient(app).post("/api/v1/segmentation/compare", json={"masks": [
            {"type": "instance", "id": "i1", "gcs_path": foreign_path},
            {"type": "instance", "id": "i2", "gcs_path": foreign_path}]})
    finally:
        for dep in (get_current_active_user, get_storage_service):
            app.dependency_overrides.pop(dep, None)
    assert foreign_path not in requested and requested == [own_path, own_path]
