"""PRB-002: the backend test suite must never reach a real Google Cloud service.

Before the fix, a developer machine with gcloud application-default credentials made
SecureUserStorage build a real Firestore client for project brain-mri-476110, and every local
test run wrote test accounts into the production auth_users collection. These tests check each
layer of the guard in backend/tests/conftest.py, and the end result: the user store, the
segmentation service and the storage service all fail to get a real client.
"""
import os
from pathlib import Path

import pytest

OFFLINE_PROJECT_ID = "mstool-offline-tests"  # backend/tests/conftest.py


NO_CLOUD_DIR = Path(__file__).resolve().parents[1] / ".no-cloud"


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
    assert "brain-mri" not in os.environ["GOOGLE_CLOUD_PROJECT"]
    assert "GCLOUD_PROJECT" not in os.environ


def test_google_auth_default_refuses(monkeypatch):
    import google.auth
    import google.auth._default
    from google.auth.exceptions import DefaultCredentialsError

    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    for fn in (google.auth.default, google.auth._default.default):
        assert getattr(fn, "prb002_guard", False), fn
        with pytest.raises(DefaultCredentialsError):
            fn()


def test_remote_emulator_host_is_not_trusted(monkeypatch):
    """Only a LOCAL emulator gets anonymous credentials; any other host is refused."""
    import google.auth
    from google.auth.exceptions import DefaultCredentialsError

    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "firestore.googleapis.com:443")
    with pytest.raises(DefaultCredentialsError):
        google.auth.default()


def test_firestore_client_cannot_be_built(monkeypatch):
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    from app.core.firebase import get_firestore_client

    with pytest.raises(Exception):
        get_firestore_client()


def test_user_store_uses_local_backend(tmp_path, monkeypatch):
    """The store that wrote to production now falls back to its encrypted local backend."""
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
