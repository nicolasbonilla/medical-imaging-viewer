"""Fifteenth review of PR #81 — failing-first through the REAL lower layers, and LESS mechanism. S2 the audit
confirmation (the real middleware, logger and durable sink on every route class and sink state); S3 RC-062's input read
exactly as on the base, also when the store fails (G26); S5 Retry-After from the real limiter; S6 one details filter,
one NIfTI header reader. (S1, the run-token lifecycle: test_rc126_run_token_model.py.) DRAFT, PENDING owner approval."""
import asyncio
import gzip
import inspect
import json
import math
import time as _time
from concurrent.futures import Future
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from app.agent_platform import registry as R
from app.core.logging import audit as A
from app.core.logging import audit_middleware as M
from app.core.logging import audit_sink as S
from app.services import longitudinal_candidate_safety as lcs
from app.services import quality_gate as qg

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[3]


# ============================================================================= S2: the audit confirmation
class _AuditStore:
    """The durable audit store (Firestore's create()) as the sink sees it: fast, slow, or failing."""

    def __init__(self, mode):
        self.mode, self.docs = mode, {}

    def collection(self, name):
        return self

    def document(self, doc_id):
        store = self

        class _Doc:
            def create(self, data):
                if store.mode == "slow":
                    _time.sleep(1.0)
                if store.mode == "failing":
                    raise OSError("store unavailable")
                store.docs[doc_id] = data
        return _Doc()


def _mini_app():
    """The real AuditMiddleware in front of one route of each class, each writing its records the way the app does."""
    mini = FastAPI()
    mini.add_middleware(M.AuditMiddleware)

    def explicit(request):
        A.emit_audit(A.AuditEventType.CLINICAL_AI_RUN, A.AuditOutcome.SUCCESS, request=request, user_id="id-dr",
                     reason="agent.run:ok")

    def through_the_platform(request):
        with R.audit_actor(R.AuditActor(user_id="id-dr", request=request)):
            R.default_audit_sink({"event": "agent.consultation", "code": "quality_gate.abstain", "outcome": "success"})

    @mini.post("/api/v1/auth/logout")
    async def auth(request: Request):
        A.emit_audit(A.AuditEventType.AUTH_LOGOUT, A.AuditOutcome.FAILURE, request=request, reason="no_session")
        return Response(status_code=204)

    @mini.post("/api/v1/clinical/quality-gate")
    async def gate(request: Request):
        through_the_platform(request)
        return {}

    @mini.post("/api/v1/segmentation/longitudinal/compare")
    async def compare(request: Request):
        through_the_platform(request)
        return {}

    @mini.post("/api/v1/agent/mcp/call")
    async def agent(request: Request):
        explicit(request)
        return {}

    @mini.post("/api/v1/plain")
    async def plain(request: Request):
        return {}
    return mini


CLASSES = {"auth": "/api/v1/auth/logout", "gate": "/api/v1/clinical/quality-gate",
           "gate_consulting": "/api/v1/segmentation/longitudinal/compare", "agent": "/api/v1/agent/mcp/call",
           "plain": "/api/v1/plain"}
COVERED = {"auth", "gate"}          # the routes whose own record silences the middleware


@pytest.mark.parametrize("sink_state", ["healthy", "slow", "failing", "off"])
@pytest.mark.parametrize("outcome", ["logged", "not_logged"])
@pytest.mark.parametrize("route", sorted(CLASSES))
def test_rc126_s2_the_unconfirmed_tag_is_exactly_true_and_no_request_is_left_without_a_record(monkeypatch, route,
                                                                                             outcome, sink_state):
    sink = (S.DurableAuditSink(None, backend="off") if sink_state == "off" else
            S.DurableAuditSink((lambda st: (lambda: st))(_AuditStore(sink_state)), backend="firestore",
                               base_backoff_s=0.01, max_backoff_s=0.02, max_attempts=3))
    previous = S.set_durable_audit_sink(sink)
    logged = []
    real_stdout = A.AuditLogger._write_stdout
    monkeypatch.setattr(A.AuditLogger, "_write_stdout",
                        staticmethod(lambda record, event: (logged.append(record), real_stdout(record, event))[1]))
    if outcome == "not_logged":
        real = A.AuditEvent.verify_integrity
        monkeypatch.setattr(A.AuditEvent, "verify_integrity", lambda self: False if self.source == "explicit" else real(self))
    A.reset_audit_budget()
    try:
        client = TestClient(_mini_app(), base_url="https://testserver")
        t0 = _time.monotonic()
        client.post(CLASSES[route], json={})
        elapsed = _time.monotonic() - t0
    finally:
        S.set_durable_audit_sink(previous)
    rows = [r for r in logged if r.get("endpoint") == CLASSES[route]]
    mine = [r for r in rows if r.get("source") == "middleware"]
    explicit = [r for r in rows if r.get("source") == "explicit"]
    assert rows, "a request left no record at all"
    route_wrote = route != "plain" and outcome == "logged"
    durable_in_time = sink_state == "healthy"
    tagged = any((r.get("details") or {}).get("route_record") == "unconfirmed" for r in mine)
    expect_tag = (route in COVERED and sink_state != "off"
                  and (outcome == "not_logged" or not durable_in_time))
    assert tagged is expect_tag, (route, outcome, sink_state, rows)
    if sink_state == "off":                  # no durable backend: exactly the base — the route's record or the middleware's
        base = (1 if route in COVERED else (2 if route_wrote else 1))
        assert len(rows) == base, (route, outcome, rows)
    if route in COVERED and route_wrote and (durable_in_time or sink_state == "off"):
        assert mine == [] and len(explicit) == 1, "a durable route record is the one record"
    budget = getattr(M, "_WAIT_BUDGET_S", M._FLUSH_WAIT_S)
    assert elapsed <= budget + 0.6, f"the request waited {elapsed:.2f} s (budget {budget:.2f} s)"


def test_rc126_s2_one_import_of_asyncio_in_the_middleware():
    assert inspect.getsource(M).count("\nimport asyncio\n") == 1


# ============================================================================= S3: RC-062's input as on the base (G26)
def _base_read_source_acquisition(file_id, study_service=None):
    """The base branch's read, VERBATIM (5ee06b7), the reference of G26."""
    m = lcs._FILE_ID_RE.fullmatch(str(file_id or ""))
    if not m:
        return None
    try:
        if study_service is None:
            from app.core.container import get_study_service
            study_service = get_study_service()
        db = getattr(study_service, "db", None)
        if db is None:
            return None
        instances = (db.collection("studies").document(m.group(1))
                     .collection("series").document(m.group(2)).collection("instances"))
        for doc in instances.stream():
            data = doc.to_dict() or {}
            if data.get("gcs_object_name") == file_id:
                acq = data.get("acquisition")
                return acq if isinstance(acq, dict) else None
    except Exception:  # noqa: BLE001
        pass
    return None


FID = "patients/p/studies/st/series/se/f.nii.gz"
DOCS = [{"gcs_object_name": "patients/p/studies/st/series/se/other.nii.gz", "acquisition": {"manufacturer": "GE"}},
        {"gcs_object_name": FID, "acquisition": {"manufacturer": "SIEMENS"}}]


class _Store:
    """A study store with the failure modes of Firestore's query and scan."""

    def __init__(self, mode):
        self.mode = mode

    def collection(self, name):
        return self

    def document(self, name):
        return self

    def where(self, *a, **k):
        from google.api_core.exceptions import FailedPrecondition, PermissionDenied
        if self.mode == "query_raises":
            raise RuntimeError("query failed")
        if self.mode == "missing_index":
            raise FailedPrecondition("The query requires an index")
        if self.mode == "permission":
            raise PermissionDenied("missing permission")
        return self

    def limit(self, n):
        return self

    def stream(self):
        from google.api_core.exceptions import PermissionDenied
        if self.mode == "scan_permission":
            raise PermissionDenied("missing permission")
        return iter([type("D", (), {"to_dict": lambda self, d=d: dict(d)})() for d in DOCS])


@pytest.mark.parametrize("enforced", [False, True])
@pytest.mark.parametrize("mode", ["ok", "query_raises", "missing_index", "permission", "scan_permission"])
def test_rc123_g26_s3_rc062_s_input_is_the_base_read_also_when_the_store_fails(monkeypatch, enforced, mode):
    from app.services import quality_gate as _qg  # noqa: F401 — the flag is read through the settings
    monkeypatch.setattr(lcs, "logger", lcs.logger)
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "QUALITY_GATE_ENFORCED", enforced)
    service = type("Svc", (), {"db": _Store(mode)})()
    for fid in (FID, "patients/p/studies/st/series/se/missing.nii.gz", "not a file id"):
        assert lcs.read_source_acquisition(fid, service) == _base_read_source_acquisition(fid, service), (mode, fid)
    no_db = type("Svc", (), {"db": None})()
    assert lcs.read_source_acquisition(FID, no_db) == _base_read_source_acquisition(FID, no_db)


# ============================================================================= S5: Retry-After from the real limiter
@pytest.mark.parametrize("remaining", [0.05, 0.5, 0.99, 1.0, 1.3, 1.7, 2.5, 30.2, 59.0, 59.95])
def test_rc126_s5_retry_after_is_at_least_the_real_remaining_time_and_never_inflated(monkeypatch, remaining):
    from app.core.security import rate_limiter as RL
    clock = {"t": 1_000_000.0}
    monkeypatch.setattr(RL, "time", type("T", (), {"time": staticmethod(lambda: clock["t"])})())
    monkeypatch.setattr(qg, "_LIMITER", None)
    uid = f"id-retry-{remaining}"
    for _ in range(qg.RATE_LIMIT_PER_MINUTE):
        assert qg.rate_limit(uid) is None
    clock["t"] += 60 - remaining                                       # the window resets in `remaining` seconds
    wait = qg.rate_limit(uid)
    assert wait is not None and 1 <= wait <= 60, wait
    assert wait >= remaining, f"Retry-After {wait} s while {remaining} s remain"
    assert wait <= max(1, math.ceil(remaining)), f"Retry-After {wait} s while only {remaining} s remain"


# ============================================================================= S6: one details filter
def test_rc126_s6_the_raw_details_are_filtered_once_by_the_record_builder():
    details = {"causes": [f"code_{i}" for i in range(25)], "decision": "abstain", "mode": "single with spaces",
               "not_a_detail_key": "x", "released": False}
    events = []
    data = json.loads((ROOT / "backend/app/agent_platform/agents.json").read_text(encoding="utf-8"))
    reg = R.AgentRegistry(data, switches=R.InMemoryKillSwitches({"quality-gate": True}), audit=events.append)
    reg.audit("success", "quality_gate.abstain", event="agent.consultation", agent_id="quality-gate", details=details)
    assert events[0]["details"] == details, "the registry passes the details through unfiltered"
    record = A.build_audit_record(A.AuditEvent(event_type=A.AuditEventType.QUALITY_GATE_CONSULTATION,
                                               severity=A.AuditSeverity.LOW, outcome=A.AuditOutcome.SUCCESS,
                                               details=events[0]["details"], source="explicit"))
    assert record.get("details", {}) == A._safe_details(details), "the record builder filters once"
    assert "_safe_details" not in inspect.getsource(R) and "_plain_details" not in inspect.getsource(R)


# ============================================================================= S6: one NIfTI header reader
def _nifti(kind, endian, gz, extension):
    arr = np.zeros((7, 5, 3), np.float32)
    affine = np.array([[0.9, 0, 0, -10], [0, 1.1, 0, 5], [0, 0, 3.0, 2], [0, 0, 0, 1]])
    header = (nib.Nifti2Header if kind == 2 else nib.Nifti1Header)(endianness=endian)
    img = (nib.Nifti2Image if kind == 2 else nib.Nifti1Image)(arr, affine, header=header)
    if extension:
        img.header.extensions.append(nib.nifti1.Nifti1Extension("comment", b"x" * 3000))
    raw = img.to_bytes()
    return gzip.compress(raw) if gz else raw


@pytest.mark.parametrize("kind", [1, 2])
@pytest.mark.parametrize("endian", ["<", ">"])
@pytest.mark.parametrize("gz", [False, True])
@pytest.mark.parametrize("extension", [False, True])
def test_rc122_s6_both_nifti_header_readers_agree(kind, endian, gz, extension):
    from app.services.segmentation_service import SegmentationService
    raw = _nifti(kind, endian, gz, extension)
    shape, affine, _hdr = SegmentationService.nifti_header_grid(raw)
    img = qg._nifti_header_image(raw)
    assert shape == tuple(int(d) for d in img.shape[:3]) == (7, 5, 3)
    assert np.allclose(affine, img.affine)
    assert qg.sniff_format(raw) == "nifti"


def test_rc122_s6_the_gate_has_no_nifti_reader_of_its_own():
    assert not hasattr(qg, "_nifti_prefix") and not hasattr(qg, "_nifti_sizeof_hdr")
