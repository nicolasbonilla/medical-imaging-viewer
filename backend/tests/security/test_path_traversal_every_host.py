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
def test_safe_relative_paths_accepted_and_returned_identically_on_every_host(host, payload):
    # The returned path must not depend on the host either (no separator rewriting on Windows).
    assert v.PathTraversalValidator.validate(payload) == payload


@pytest.mark.parametrize("payload", ["../Juan_Perez_MRN123.dcm", "C:\\Juan_Perez_MRN123.dcm"])
def test_refusal_audit_event_carries_no_raw_value(monkeypatch, payload):
    """A file name can carry patient identifiers: the audit event must not contain it (RMF open item, PRB-020)."""
    recorder = types.SimpleNamespace(calls=[])
    monkeypatch.setattr(v, "audit_logger",
                        types.SimpleNamespace(log_security_event=lambda **kw: recorder.calls.append(kw)))
    with pytest.raises(v.PathTraversalDetected):
        v.PathTraversalValidator.validate(payload)
    assert recorder.calls, "the refusal was not audited"
    assert "Juan_Perez" not in repr(recorder.calls)
