"""Imaging routes must preserve intended HTTP status codes, not remask as 500.

Regression guard for the production incident where every original image surfaced
as HTTP 500. Root chain: an unsupported storage-ref (or an unauthorised patient)
makes `require_imaging_access` raise HTTPException(404); the route's broad
`except Exception: raise HTTPException(500, ...)` then re-wrapped that 404 as a
500 — hiding the real status from the client and making the outage read as a
server crash instead of a 404.

The fix adds `except (HTTPException, AppException): raise` before the broad
catch, so the global exception handlers format intended codes correctly and only
genuinely unexpected errors become 500. These tests call the handler coroutine
directly with the authorization step monkeypatched to each failure mode.
"""
import pytest
from fastapi import HTTPException

from app.api.routes import imaging
from app.core.exceptions import NotFoundException, ImageProcessingException


async def _run_process(**overrides):
    """Invoke process_image with dummy dependencies (auth raises before they're used)."""
    kwargs = dict(
        file_id="patients/p/studies/s/series/se/x.gz",
        start_slice=None, end_slice=None, max_slices=50,
        storage_service=object(), imaging_service=object(), current_user=object(),
    )
    kwargs.update(overrides)
    return await imaging.process_image(**kwargs)


@pytest.mark.asyncio
async def test_httpexception_propagates_with_its_status(monkeypatch):
    async def raise_404(file_id, user):
        raise HTTPException(status_code=404, detail="Imaging object not found")
    monkeypatch.setattr(imaging, "require_imaging_access", raise_404)

    with pytest.raises(HTTPException) as exc:
        await _run_process()
    assert exc.value.status_code == 404, "a 404 must NOT be remasked as 500"


@pytest.mark.asyncio
async def test_appexception_propagates_for_global_handler(monkeypatch):
    # An AppException carries its own status_code and is formatted by the global
    # handler — the route must not swallow it into a 500.
    async def raise_app(file_id, user):
        raise NotFoundException("nope")  # status_code=404
    monkeypatch.setattr(imaging, "require_imaging_access", raise_app)

    with pytest.raises(NotFoundException):
        await _run_process()


@pytest.mark.asyncio
async def test_image_processing_exception_propagates(monkeypatch):
    async def raise_ipe(file_id, user):
        raise ImageProcessingException("bad NIfTI")  # AppException, 500 — but formatted by global handler
    monkeypatch.setattr(imaging, "require_imaging_access", raise_ipe)

    with pytest.raises(ImageProcessingException):
        await _run_process()


@pytest.mark.asyncio
async def test_unexpected_error_still_becomes_500(monkeypatch):
    # Genuinely unexpected errors MUST still be contained as a 500 (defensive).
    async def raise_generic(file_id, user):
        raise ValueError("boom")
    monkeypatch.setattr(imaging, "require_imaging_access", raise_generic)

    with pytest.raises(HTTPException) as exc:
        await _run_process()
    assert exc.value.status_code == 500
