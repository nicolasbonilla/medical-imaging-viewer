"""Skull removal for the in-browser AI (REQ-FUNC-115, RC-101). Access is covered by the RC-036 table and its DENIED row."""
import gzip

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core import container
from app.core.config import get_settings
from app.main import app
from app.api.routes import clinical_tools
from app.security import get_current_active_user
from app.security.models import User, UserRole
from app.services import tool_runner_service as runner_module
from app.services.tool_runner_service import ToolRunnerService
from datetime import datetime

FILE = "patients/p/flair.nii.gz"


def _user():
    now = datetime.utcnow()
    return User(id="r-1", username="rad", email="r@e.com", full_name="R", role=UserRole.RADIOLOGIST, is_active=True,
                is_locked=False, email_verified=True, created_at=now, updated_at=now)


class FakeRunner:
    def __init__(self, available=True, error=None):
        self.available, self.error, self.asked = available, error, []

    def is_skull_strip_available(self):
        return self.available

    async def skull_strip(self, path):
        self.asked.append(path)
        if self.error:
            raise self.error
        return b"brain"


@pytest.fixture
def client(monkeypatch):
    async def authorized(file_ids, patient_id, study_id, user):
        return [f"checked/{f}" for f in file_ids]
    monkeypatch.setattr(clinical_tools, "_authorized_inputs", authorized)
    app.dependency_overrides[get_current_active_user] = _user

    def make(runner):
        app.dependency_overrides[container.get_tool_runner_service] = lambda: runner
        return TestClient(app)
    yield make
    app.dependency_overrides.clear()


def post(client):
    return client.post("/api/v1/clinical/skull-strip", json={"file_id": FILE})


def test_off_by_default():
    settings = get_settings()
    assert settings.SKULL_STRIP_ENABLED is False and settings.SKULL_STRIP_ENDPOINT == ""


def test_the_brain_comes_back_from_the_authorized_path_and_is_not_cached(client):
    runner = FakeRunner()
    r = post(client(runner))
    assert r.status_code == 200 and r.content == b"brain"
    assert runner.asked == [f"checked/{FILE}"]
    assert r.headers["cache-control"] == "no-store"


def test_no_worker_means_503_and_nothing_is_read(client):
    runner = FakeRunner(available=False)
    assert post(client(runner)).status_code == 503
    assert runner.asked == []


def test_a_worker_failure_is_a_clear_refusal(client):
    assert post(client(FakeRunner(error=RuntimeError("worker down")))).status_code == 502


class FakeStorage:
    def __init__(self, data):
        self.data = data

    async def download(self, path):
        return self.data


@pytest.mark.parametrize("stored,sent", [(b"\x1f\x8bgz", b"\x1f\x8bgz"), (b"plain", None)])
def test_the_image_travels_compressed_and_only_in_the_request(monkeypatch, stored, sent):
    seen = {}

    def answer(request):
        seen["url"], seen["body"] = str(request.url), request.content
        return httpx.Response(200, content=b"brain")
    real = httpx.AsyncClient
    monkeypatch.setattr(runner_module.httpx, "AsyncClient", lambda **k: real(transport=httpx.MockTransport(answer), **k))
    monkeypatch.setattr(runner_module.settings, "SKULL_STRIP_ENDPOINT", "https://worker")
    service = ToolRunnerService(FakeStorage(stored))

    async def no_auth(_):
        return {}
    monkeypatch.setattr(service, "_worker_auth_headers", no_auth)
    import asyncio
    assert asyncio.run(service.skull_strip(FILE)) == b"brain"
    assert seen["url"] == "https://worker/strip"
    assert seen["body"] == sent if sent else gzip.decompress(seen["body"]) == stored


def test_a_worker_error_is_not_taken_for_an_image(monkeypatch):
    real = httpx.AsyncClient
    monkeypatch.setattr(runner_module.httpx, "AsyncClient",
                        lambda **k: real(transport=httpx.MockTransport(lambda r: httpx.Response(422)), **k))
    monkeypatch.setattr(runner_module.settings, "SKULL_STRIP_ENDPOINT", "https://worker")
    service = ToolRunnerService(FakeStorage(b"\x1f\x8bgz"))

    async def no_auth(_):
        return {}
    monkeypatch.setattr(service, "_worker_auth_headers", no_auth)
    import asyncio
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(service.skull_strip(FILE))
