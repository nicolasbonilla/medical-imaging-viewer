"""PRB-032: every AuditEventType member the application references exists, and a detection is audited and raised.

The input validators referenced four AuditEventType members that never existed (SECURITY_INJECTION_ATTEMPT,
SECURITY_XSS_ATTEMPT, SECURITY_PATH_TRAVERSAL, SECURITY_INVALID_INPUT). Every detection raised AttributeError at
argument evaluation, before its audit event and before its *Detected exception. The security tests hid this by
replacing the enum with a MagicMock. The input-validation middleware is bypassed for every path today (a known,
recorded RMF open item), so production behaviour was not affected; the defect would have surfaced on re-enabling it.
"""
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core.logging.audit import AuditEventType
from app.core.security import validators as v
from app.core.security.validation_middleware import InputValidationMiddleware

APP = Path(__file__).resolve().parents[2] / "app"


def test_every_referenced_audit_event_type_exists():
    referenced = {}
    for path in APP.rglob("*.py"):
        for name in re.findall(r"AuditEventType\.([A-Z][A-Z0-9_]+)", path.read_text(encoding="utf-8")):
            referenced.setdefault(name, path.relative_to(APP).as_posix())
    assert referenced, "no reference found: the check would pass vacuously"
    missing = {n: f for n, f in referenced.items() if not hasattr(AuditEventType, n)}
    assert not missing, f"AuditEventType members referenced but not defined: {missing}"


@pytest.mark.parametrize(
    "check, payload, exc, event",
    [
        (v.SQLValidator.validate, "1' OR '1'='1", v.SQLInjectionDetected, AuditEventType.SECURITY_INJECTION_ATTEMPT),
        (v.XSSValidator.validate, "<script>alert(1)</script>", v.XSSDetected, AuditEventType.SECURITY_XSS_ATTEMPT),
        (v.PathTraversalValidator.validate, "../../etc/passwd", v.PathTraversalDetected,
         AuditEventType.SECURITY_PATH_TRAVERSAL),
        (v.PathTraversalValidator.validate, "C:\\Windows\\win.ini", v.PathTraversalDetected,
         AuditEventType.SECURITY_PATH_TRAVERSAL),
    ],
    ids=["sql", "xss", "relative-traversal", "windows-absolute"],
)
def test_detection_is_audited_then_raised_with_the_real_enum(monkeypatch, check, payload, exc, event):
    recorder = MagicMock()
    monkeypatch.setattr(v, "audit_logger", recorder)
    with pytest.raises(exc):
        check(payload)
    assert recorder.log_security_event.call_args.kwargs["event_type"] is event


def test_input_validation_middleware_is_still_bypassed_for_every_path():
    """Pins the recorded state (RMF open item 'Input-validation middleware', PRB-020): every path is bypassed.

    If this fails, someone re-enabled the middleware. The RMF precondition must be met first: the SQL/XSS/command
    validators must stop writing the typed value to the audit log (passwords containing a listed keyword would be
    logged), and a false-positive check on real queries (for example a surname with an apostrophe) is needed.
    """
    mw = InputValidationMiddleware(app=MagicMock())
    for path in ("/api/v1/patients", "/api/v1/auth/login", "/api/v1/imaging/upload"):
        assert mw._should_bypass(path), f"{path} is validated: check the RMF precondition before re-enabling"
