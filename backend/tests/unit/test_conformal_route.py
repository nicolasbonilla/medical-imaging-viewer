"""Integration seams for POST /api/v1/conformal/select (REQ-FUNC-CALM-001).

Exercises the fail-closed HTTP mapping the adversarial Class C review demanded:
feature-dark 404, provenance 409, bad-preset/bad-prob 422, and the additive,
hazard-free 200 payload. Skips cleanly if the null asset isn't built.
"""
from datetime import datetime

import numpy as np
import nibabel as nib
import pytest

try:
    from app.main import app
    from app.core.container import get_storage_service
    from app.security import get_current_active_user
    from app.security.models import User, UserRole
    from app.services.conformal_null_asset import get_null_asset, ConformalAssetError
    from fastapi.testclient import TestClient
    _GRID = get_null_asset().grid_shape
    _AVAILABLE = True
except (Exception, ConformalAssetError):  # asset missing or app not importable
    _AVAILABLE = False

pytestmark = pytest.mark.skipif(not _AVAILABLE, reason="app/null-asset not available")


def _admin():
    now = datetime.utcnow()
    return User(id="admin-1", username="admin", email="a@e.com", full_name="A",
                role=UserRole.ADMIN, is_active=True, is_locked=False,
                email_verified=True, created_at=now, updated_at=now)


def _ball(shape, c, r):
    zz, yy, xx = np.ogrid[:shape[0], :shape[1], :shape[2]]
    return (zz - c[0]) ** 2 + (yy - c[1]) ** 2 + (xx - c[2]) ** 2 <= r ** 2


def _prob_bytes(shape, blobs=((60, 90, 90, 0.95), (90, 130, 100, 0.7)), spacing=(1.0, 1.0, 1.0)):
    p = np.full(shape, 0.02, dtype=np.float32)
    for z, y, x, v in blobs:
        if z < shape[0] and y < shape[1] and x < shape[2]:
            p[_ball(shape, (z, y, x), 3)] = v
    img = nib.Nifti1Image(p, np.eye(4)); img.header.set_zooms(spacing)
    return img.to_bytes()


class _Storage:
    def __init__(self, data): self._data = data
    async def download_file(self, bucket, file_id): return self._data


class _Settings:
    CALM_MS_RESEARCH_ENABLED = True
    GCS_BUCKET_NAME = "test-bucket"


def _client(monkeypatch, prob_bytes, enabled=True):
    async def _noop_auth(file_id, current_user): return None
    monkeypatch.setattr("app.api.routes.conformal.require_imaging_access", _noop_auth)
    st = _Settings(); st.CALM_MS_RESEARCH_ENABLED = enabled
    monkeypatch.setattr("app.api.routes.conformal.get_settings", lambda: st)
    app.dependency_overrides[get_current_active_user] = _admin
    app.dependency_overrides[get_storage_service] = lambda: _Storage(prob_bytes)
    return TestClient(app)


def _cleanup():
    for dep in (get_current_active_user, get_storage_service):
        app.dependency_overrides.pop(dep, None)


def test_feature_dark_returns_404(monkeypatch):
    c = _client(monkeypatch, _prob_bytes(_GRID), enabled=False)
    try:
        r = c.post("/api/v1/conformal/select", json={"prob_file_id": "x", "preset": "balanced"})
        assert r.status_code == 404
    finally:
        _cleanup()


def test_select_200_additive_and_hazard_free(monkeypatch):
    c = _client(monkeypatch, _prob_bytes(_GRID))
    try:
        r = c.post("/api/v1/conformal/select", json={"prob_file_id": "patients/p/studies/s/x", "preset": "high_sensitivity"})
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        b = r.json()
        assert b["preset"] == "high_sensitivity" and b["fdr_target"] == 0.30
        assert "population-level" in b["guarantee_scope"].lower()
        assert b["n_candidates"] >= 1
        assert "realized" not in r.text.lower()                 # no per-scan realized FDR
        for les in b["lesions"]:
            assert "confidence" not in les                      # no per-lesion probability
            assert les["review_priority"] in ("high", "medium", "low")
    finally:
        _cleanup()


def test_provenance_mismatch_returns_409(monkeypatch):
    c = _client(monkeypatch, _prob_bytes((100, 100, 100)))        # wrong grid
    try:
        r = c.post("/api/v1/conformal/select", json={"prob_file_id": "x", "preset": "balanced"})
        assert r.status_code == 409, f"{r.status_code}: {r.text[:200]}"
        assert "exchangeability" in r.text.lower()
    finally:
        _cleanup()


def test_unknown_preset_returns_422(monkeypatch):
    c = _client(monkeypatch, _prob_bytes(_GRID))
    try:
        r = c.post("/api/v1/conformal/select", json={"prob_file_id": "x", "preset": "ultra"})
        assert r.status_code == 422
    finally:
        _cleanup()


def test_out_of_range_prob_returns_422(monkeypatch):
    p = np.full(_GRID, 0.02, dtype=np.float32); p[0, 0, 0] = 7.0
    img = nib.Nifti1Image(p, np.eye(4)); img.header.set_zooms((1.0, 1.0, 1.0))
    c = _client(monkeypatch, img.to_bytes())
    try:
        r = c.post("/api/v1/conformal/select", json={"prob_file_id": "x", "preset": "balanced"})
        assert r.status_code == 422
    finally:
        _cleanup()
