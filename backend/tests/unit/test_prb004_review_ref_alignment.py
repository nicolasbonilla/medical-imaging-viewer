"""PRB-004 review (M1) — `GET /segmentation/{id}/nifti?ref_file_id=` serves a mask the viewers can place.

The 3D view and the W/L GPU view now request the mask aligned to the image they show. On `main` that path
raised NameError (`io` was imported only inside another function, CAPA-006 PA-6.4), and when it worked it
copied the MRI's header: the RC-031 voxel-order marker was dropped and the MRI display window copied (PRB-006),
and it stamped the reference affine onto ANY mask of the same shape — also one stored with the identity
fallback or on another scanner grid, i.e. a fabricated alignment.

Required:
- a mask stored on the reference image's grid (same voxel-to-scanner transform within 0.001), legacy (in-plane
  transpose, no marker) or v2, is served in the image's voxel order, under the image's affine, with the RC-031
  marker and its own display range (0 .. highest label);
- a mask whose stored transform is not the reference's (identity fallback, another grid) is served unchanged
  (the viewers then refuse it with a notice) — never stamped with the reference affine.

Route driven through the real FastAPI app; storage and authorization replaced; no cloud access (PRB-002).
"""
import gzip
import io
import tempfile
import os
from types import SimpleNamespace

import nibabel as nib
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core import container
from app.security import get_current_active_user
from app.security.resource_access import require_segmentation_access
import app.api.routes.segmentation as seg_routes
from app.services.segmentation_service import SegmentationService

MARKER = b"RC031-ORIENT-V2"
REF_PATH = "patients/p/studies/s/series/se/flair.nii.gz"
A0, A1, K = 5, 7, 3          # non-square in-plane: a transpose changes the shape
SQ = 6                       # square in-plane: a transpose keeps the shape
AFFINE = np.array([[-1.0, 0, 0, 90], [0, 1.2, 0, -126], [0, 0, 3.0, -72], [0, 0, 0, 1]])


def _nifti_bytes(data, affine, cal=None, descrip=None):
    img = nib.Nifti1Image(data, affine)
    if cal:
        img.header["cal_min"], img.header["cal_max"] = cal
    if descrip is not None:
        img.header["descrip"] = descrip
    with tempfile.NamedTemporaryFile(suffix=".nii.gz", delete=False) as t:
        p = t.name
    nib.save(img, p)
    with open(p, "rb") as f:
        out = f.read()
    os.unlink(p)
    return out


def _load(raw):
    with tempfile.NamedTemporaryFile(suffix=".nii.gz", delete=False) as t:
        t.write(raw)
        p = t.name
    img = nib.load(p)
    data, affine, hdr = np.asarray(img.dataobj).copy(), img.affine.copy(), img.header.copy()
    del img
    os.unlink(p)
    return data, affine, hdr


class _Blob:
    def __init__(self, data):
        self._data = data

    def exists(self):
        return self._data is not None

    def download_to_file(self, buf):
        buf.write(self._data)


class _Svc(SegmentationService):
    def __init__(self, stored, ref):  # noqa: D401 - no cloud clients
        self._stored, self._ref = stored, ref

    def get_segmentation_nifti(self, sid):
        return self._stored

    @property
    def gcs_bucket(self):
        return SimpleNamespace(blob=lambda path: _Blob(self._ref if path == REF_PATH else None))


@pytest.fixture
def serve(monkeypatch):
    async def authorized_ref(file_id, user):
        return SimpleNamespace(object_path=file_id)

    monkeypatch.setattr(seg_routes, "require_imaging_access", authorized_ref)
    keys = [get_current_active_user, require_segmentation_access, container.get_segmentation_service,
            container.get_storage_service]

    def run(stored, ref):
        app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(id="u1", username="dr")
        app.dependency_overrides[require_segmentation_access] = lambda: None
        app.dependency_overrides[container.get_segmentation_service] = lambda: _Svc(stored, ref)
        app.dependency_overrides[container.get_storage_service] = lambda: None
        client = TestClient(app, raise_server_exceptions=False)
        return client.get("/api/v1/segmentation/seg-1/nifti", params={"ref_file_id": REF_PATH})

    yield run
    for k in keys:
        app.dependency_overrides.pop(k, None)


def _reference(shape):
    return _nifti_bytes(np.zeros(shape, dtype=np.int16), AFFINE, cal=(-15.5, 189.2))


def test_rc073_legacy_mask_on_the_reference_grid_is_served_in_image_order_with_marker_and_own_range(serve):
    native = np.zeros((A0, A1, K), dtype=np.uint8)
    native[1, 5, 2] = 1
    native[3, 0, 1] = 4
    legacy = np.ascontiguousarray(np.transpose(native, (1, 0, 2)))   # how pre-RC-031 saves stored it
    r = serve(_nifti_bytes(legacy, AFFINE, descrip=b""), _reference((A0, A1, K)))
    assert r.status_code == 200, r.text
    data, affine, hdr = _load(r.content)
    assert data.shape == (A0, A1, K) and np.array_equal(data, native)
    assert np.allclose(affine, AFFINE, atol=1e-4)
    assert MARKER in bytes(np.asarray(hdr["descrip"]).tobytes())
    assert (float(hdr["cal_min"]), float(hdr["cal_max"])) == (0.0, 4.0)


def test_rc073_legacy_square_mask_is_un_transposed(serve):
    native = np.zeros((SQ, SQ, K), dtype=np.uint8)
    native[1, 4, 0] = 1
    legacy = np.ascontiguousarray(np.transpose(native, (1, 0, 2)))
    r = serve(_nifti_bytes(legacy, AFFINE, descrip=b""), _reference((SQ, SQ, K)))
    assert r.status_code == 200, r.text
    data, _, hdr = _load(r.content)
    assert np.array_equal(data, native)
    assert MARKER in bytes(np.asarray(hdr["descrip"]).tobytes())


def test_rc073_v2_mask_on_the_reference_grid_keeps_its_order_and_gets_its_own_range(serve):
    native = np.zeros((A0, A1, K), dtype=np.uint8)
    native[2, 3, 1] = 1
    r = serve(_nifti_bytes(native, AFFINE, cal=(-15.5, 189.2), descrip=MARKER), _reference((A0, A1, K)))
    assert r.status_code == 200, r.text
    data, affine, hdr = _load(r.content)
    assert np.array_equal(data, native)
    assert (float(hdr["cal_min"]), float(hdr["cal_max"])) == (0.0, 1.0)
    assert MARKER in bytes(np.asarray(hdr["descrip"]).tobytes())


def test_rc073_identity_fallback_mask_is_not_stamped_with_the_reference_affine(serve):
    native = np.zeros((A0, A1, K), dtype=np.uint8)
    native[2, 3, 1] = 1
    r = serve(_nifti_bytes(native, np.eye(4), descrip=MARKER), _reference((A0, A1, K)))
    assert r.status_code == 200, r.text
    _, affine, _ = _load(r.content)
    assert np.allclose(affine, np.eye(4)), "a mask of unknown position must not be presented as aligned"


def test_rc073_mask_on_another_scanner_grid_is_served_unchanged(serve):
    other = AFFINE.copy()
    other[0, 3] += 0.5          # half a voxel elsewhere
    native = np.zeros((A0, A1, K), dtype=np.uint8)
    native[2, 3, 1] = 1
    r = serve(_nifti_bytes(native, other, descrip=MARKER), _reference((A0, A1, K)))
    assert r.status_code == 200, r.text
    _, affine, _ = _load(r.content)
    assert np.allclose(affine, other, atol=1e-4)
