"""PRB-002: the backend test suite must never reach a real external service.

Before the fix, a developer machine with gcloud application-default credentials made
SecureUserStorage build a real Firestore client for project brain-mri-476110, and every local
test run wrote test accounts into the production auth_users collection. These tests check each
layer of the guard in backend/tests/conftest.py, that it is installed before any app module is
imported, and the end result: the start-up user store, the Firestore client, the segmentation
service and the storage service all fail to get a real client, also with the Firestore emulator
variable that CI sets without running an emulator, and no Python socket leaves the loopback.
"""
import os
import socket
import sys
import time
from pathlib import Path

import pytest

OFFLINE_PROJECT_ID = "mstool-offline-tests"  # backend/tests/conftest.py
NO_CLOUD_DIR = Path(__file__).resolve().parents[1] / ".no-cloud"
CI_EMULATOR_HOST = "localhost:8081"  # .github/workflows/ci.yml sets it; no emulator runs there


def _conftest():
    for module in list(sys.modules.values()):
        if hasattr(module, "PRB002_APP_IMPORTED_BEFORE_GUARD"):
            return module
    raise AssertionError("backend/tests/conftest.py did not install the PRB-002 guard")


def test_guard_installed_before_any_app_import():
    """The production writes came from the user store created while conftest imported app.main."""
    assert _conftest().PRB002_APP_IMPORTED_BEFORE_GUARD == []


def test_credentials_file_points_nowhere():
    """Forced by conftest (not inherited from the developer's environment) and absent."""
    path = Path(os.environ["GOOGLE_APPLICATION_CREDENTIALS"])
    assert path.resolve() == NO_CLOUD_DIR / "no-credentials.json", path
    assert not path.exists(), path


def test_gcloud_config_dir_holds_no_credentials():
    config = Path(os.environ["CLOUDSDK_CONFIG"])
    assert config.resolve() == NO_CLOUD_DIR / "gcloud", config
    assert not (config / "application_default_credentials.json").exists()


def test_project_is_not_a_real_project():
    assert os.environ["GOOGLE_CLOUD_PROJECT"] == OFFLINE_PROJECT_ID
    assert "GCLOUD_PROJECT" not in os.environ


def test_other_service_keys_and_endpoints_removed():
    removed = _conftest().PRB002_REMOVED_VARIABLES
    assert "ANTHROPIC_API_KEY" in removed and "FLAMES_ENDPOINT" in removed
    assert [name for name in removed if name in os.environ] == []


@pytest.mark.parametrize("emulator_host", [None, CI_EMULATOR_HOST])
def test_google_auth_default_refuses(monkeypatch, emulator_host):
    """Always: also with the emulator variable (CI sets it without an emulator)."""
    import google.auth
    import google.auth._default
    from google.auth.exceptions import DefaultCredentialsError

    if emulator_host:
        monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", emulator_host)
    else:
        monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    for fn in (google.auth.default, google.auth._default.default):
        assert getattr(fn, "prb002_guard", False), fn
        with pytest.raises(DefaultCredentialsError):
            fn()


def test_emulator_variable_does_not_unlock_storage(monkeypatch):
    """With CI's emulator variable a GCS client must still fail at once (no anonymous client,
    no retry loop towards storage.googleapis.com)."""
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", CI_EMULATOR_HOST)
    from google.cloud import storage
    from app.core.exceptions import StorageException
    from app.services.storage_service import GCSStorageService

    started = time.monotonic()
    with pytest.raises(Exception):
        storage.Client()
    with pytest.raises(StorageException):
        GCSStorageService()._get_client()
    assert time.monotonic() - started < 10


def test_outbound_connections_refused():
    with pytest.raises(OSError, match="PRB-002"):
        socket.create_connection(("192.0.2.1", 443), timeout=2)  # TEST-NET-1, never routed


def test_loopback_connections_still_work():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    try:
        client = socket.create_connection(server.getsockname(), timeout=2)
        client.close()
    finally:
        server.close()


def test_firestore_client_cannot_be_built(monkeypatch):
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    from app.core.firebase import get_firestore_client

    with pytest.raises(Exception):
        get_firestore_client()


def test_startup_user_store_is_local():
    """The singleton the app created at import (used by AuthService) is the object that wrote to
    production; it must be on its local backend."""
    from app.security.user_storage import get_user_storage

    assert get_user_storage()._db is None
    from app.api.routes import auth as auth_routes
    assert auth_routes.auth_service._storage._db is None


def test_new_user_store_uses_local_backend(tmp_path, monkeypatch):
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    from app.security.user_storage import SecureUserStorage

    store = SecureUserStorage(storage_dir=tmp_path / "users")
    assert store._db is None


def test_segmentation_service_cannot_reach_cloud(tmp_path, monkeypatch):
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    from app.services.segmentation_service import SegmentationService

    svc = SegmentationService(storage_path=str(tmp_path), cache_service=None)
    with pytest.raises(Exception):
        svc.db
    with pytest.raises(Exception):
        svc.gcs_client


def test_storage_service_cannot_reach_cloud(monkeypatch):
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    from app.core.exceptions import StorageException
    from app.services.storage_service import GCSStorageService

    assert os.environ["GCS_CREDENTIALS_FILE"] == ""
    with pytest.raises(StorageException):
        GCSStorageService()._get_client()
