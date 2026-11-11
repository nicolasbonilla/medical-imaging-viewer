"""CAPA-003 CA-3.2 / REQ-SEC-016: the path validator refuses absolute paths of BOTH path families on every host.

The server runs on Linux (Cloud Run), where ``os.path`` is ``posixpath``: a Windows drive path
(``C:\\Windows\\...``), a UNC path (``\\\\server\\share``) or a device path (``\\\\?\\C:\\...``) was not seen as
absolute, so ``TestPathTraversalProtection`` failed on every GitHub run since the suite started executing
(non-blocking step, CAPA-003) while passing on the developer's Windows laptop. These tests pin the validator to
both path families whatever the host is, by swapping the ``os`` module the validator sees.
"""
import ntpath
import posixpath
import types

import pytest

from app.core.security import validators as v

HOSTS = [pytest.param(posixpath, id="linux-host"), pytest.param(ntpath, id="windows-host")]

ABSOLUTE = [
    "/etc/passwd",
    "C:\\Windows\\System32\\config\\sam",
    "c:/windows/win.ini",
    "\\\\?\\C:\\Windows\\System32",
    "\\\\server\\share\\scan.dcm",
    "C:drive-relative.dcm",
    "\\rooted.dcm",
]

SAFE = [
    "patient_001/scan.dcm",
    "studies/2024/study_001.nii.gz",
    "uploads/image.jpg",
    "reports/final_report.pdf",
]


@pytest.fixture
def host(monkeypatch, request):
    """Make the validator module see the given path family as its ``os.path``."""
    monkeypatch.setattr(v, "os", types.SimpleNamespace(path=request.param))
    return request.param


@pytest.mark.parametrize("host", HOSTS, indirect=True)
@pytest.mark.parametrize("payload", ABSOLUTE)
def test_absolute_paths_refused_on_every_host(host, payload):
    with pytest.raises(v.PathTraversalDetected):
        v.PathTraversalValidator.validate(payload)


@pytest.mark.parametrize("host", HOSTS, indirect=True)
@pytest.mark.parametrize("payload", SAFE)
def test_safe_relative_paths_still_accepted_on_every_host(host, payload):
    assert v.PathTraversalValidator.validate(payload)
