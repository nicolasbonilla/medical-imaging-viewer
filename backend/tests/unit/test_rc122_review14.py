"""Fourteenth review of PR #81. NEW RULE: every failing-first test fails through the REAL lowest layer's failure modes —
here the real AuditLogger and durable sink (K1), the real route and its single-use store (K2, K3, K5), the real routes'
post-gate steps (K6), the real record builder (K7), the real gather (K8), the real registry (K9) and a store that
answers queries (K10). K1 the route's record counts only once the durable store holds it; K2 a lost answer is replayed,
never re-evaluated; K3 no run permission without an established version; K5 the store off the event loop; K6 one
outcome record on every path; K7 a closed registry of audit reasons; K8 the visit check before any read; K9 one details
filter; K10 one read strategy for the acquisition record. DRAFT, PENDING owner approval."""
import asyncio
import copy
import inspect
import json
import re
from concurrent.futures import Future
from pathlib import Path

import numpy as np
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app.api.routes.clinical_tools as ct
import app.api.routes.segmentation_analysis as sa
from app.agent_platform import registry as R
from app.core.container import get_segmentation_service, get_storage_service
from app.core.logging import audit as A
from app.core.logging import audit_middleware as M
from app.core.logging import audit_sink as S
from app.main import app
from app.services import longitudinal_candidate_safety as lcs
from app.services import quality_gate as qg
from tests.unit.test_rc122_quality_gate_wiring import (  # noqa: F401 — fixtures
    FILE, PAIR, REGISTRY, URL, _Storage, compare, single,
)

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[3]
QG_URL = "/api/v1/clinical/quality-gate"


def _approved(audit):
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    data["agents"]["quality-gate"]["approval"]["status"] = "approved"          # IN MEMORY, for the test only
    return R.AgentRegistry(data, switches=R.InMemoryKillSwitches({"quality-gate": True}), audit=audit)


class _Versioned(_Storage):
    """A stored file whose version is known (size, checksum, creation time)."""

    async def get_file_metadata(self, bucket, path):
        from app.core.interfaces.storage_interface import StorageObject
        return StorageObject(bucket=bucket, name=path, size=len(self.data), content_type="application/octet-stream",
                             checksum_sha256="v1", created_at="2026-11-13")


@pytest.fixture
def versioned(single):
    client, state = single
    data = app.dependency_overrides[get_storage_service]().data
    app.dependency_overrides[get_storage_service] = lambda: _Versioned(data)
    return client, state


# ============================================================================= K1: the REAL logger and sink
_ROUTE_ONLY = lambda source: source == "explicit"          # noqa: E731 — the route's own record, never the middleware's


def _inject(point, monkeypatch, sink):
    """Make the route's OWN audit record fail at one real failure point of the layer below emit_audit."""
    if point == "integrity":
        real = A.AuditEvent.verify_integrity
        monkeypatch.setattr(A.AuditEvent, "verify_integrity", lambda self: False if _ROUTE_ONLY(self.source) else real(self))
    elif point == "build":
        real = A.build_audit_record

        def build(event):
            if _ROUTE_ONLY(event.source):
                raise ValueError("record build failed")
            return real(event)
        monkeypatch.setattr(A, "build_audit_record", build)
    elif point == "stdout":
        real = A.AuditLogger._write_stdout

        def write(record, event):
            if _ROUTE_ONLY(record.get("source")):
                raise OSError("stdout closed")
            return real(record, event)
        monkeypatch.setattr(A.AuditLogger, "_write_stdout", staticmethod(write))
    else:
        real = sink.submit

        def submit(record):
            if not _ROUTE_ONLY(record.get("source")):
                return real(record)
            if point == "durable_raises":
                raise RuntimeError("durable store unreachable")
            if point == "durable_none":
                return None                                     # no durable write was made (backend off)
            fut = Future()
            if point == "durable_false":
                fut.set_result(False)                           # given up / dropped: not persisted
            return fut                                          # durable_pending: still retrying, never persisted
        monkeypatch.setattr(sink, "submit", submit)


@pytest.fixture
def real_audit(versioned, monkeypatch):
    client, _ = versioned
    monkeypatch.setattr(qg, "_REGISTRY", _approved(R.default_audit_sink))
    sink = S.DurableAuditSink(None, backend="memory")
    previous = S.set_durable_audit_sink(sink)
    monkeypatch.setattr(M, "_CONFIRM_WAIT_S", 0.2, raising=False)
    A.reset_audit_budget()
    yield client, sink
    S.set_durable_audit_sink(previous)


def _rows(sink, endpoint):
    return [r for r in sink.memory_records if r.get("endpoint") == endpoint]


@pytest.mark.parametrize("point", ["integrity", "build", "stdout", "durable_raises", "durable_none", "durable_false",
                                   "durable_pending"])
def test_rc126_k1_a_route_record_that_is_not_durable_never_silences_the_middleware(real_audit, monkeypatch, point):
    client, sink = real_audit
    _inject(point, monkeypatch, sink)
    assert client.post(QG_URL, json={"file_id": FILE}).status_code == 200
    rows = _rows(sink, QG_URL)
    assert [r["source"] for r in rows] == ["middleware"], (point, rows)


def test_rc126_k1_a_durable_route_record_is_the_one_record(real_audit):
    client, sink = real_audit
    assert client.post(QG_URL, json={"file_id": FILE}).status_code == 200
    assert [r["source"] for r in _rows(sink, QG_URL)] == ["explicit"]


@pytest.mark.parametrize("point", ["durable_none", "durable_false", "durable_pending", "integrity"])
def test_rc126_k1_platform_wide_an_auth_route_s_unconfirmed_record_never_silences_the_middleware(monkeypatch, point):
    """The same assumption on /auth (the middleware skipped its record whenever the route had LOGGED one)."""
    from app.security import refresh_tokens as rt
    sink = S.DurableAuditSink(None, backend="memory")
    previous = S.set_durable_audit_sink(sink)
    monkeypatch.setattr(M, "_CONFIRM_WAIT_S", 0.2, raising=False)
    app.dependency_overrides[rt.get_refresh_token_store] = lambda: rt.RefreshTokenStore(repo=rt.MemoryRefreshRepo())
    A.reset_audit_budget()
    try:
        _inject(point, monkeypatch, sink)
        r = TestClient(app, base_url="https://testserver").post("/api/v1/auth/logout")
        assert r.status_code == 204
        assert [x["source"] for x in _rows(sink, "/api/v1/auth/logout")] == ["middleware"], sink.memory_records
    finally:
        app.dependency_overrides.pop(rt.get_refresh_token_store, None)
        S.set_durable_audit_sink(previous)


# ============================================================================= K2: a lost answer is replayed
def _run_token(client):
    run = client.post(QG_URL, json={"file_id": FILE, "physician_confirmed_flair": True}).json()
    assert run["ai_may_run"] is True and isinstance(run.get("run_token"), str), run
    return run["run_token"]


def _final(token, skull="stripped"):
    return {"file_id": FILE, "physician_confirmed_flair": True, "skull": skull, "run_token": token}


def test_rc126_k2_a_lost_final_answer_is_replayed_identically_and_audited_as_a_replay(versioned, monkeypatch):
    client, _ = versioned
    events = []
    monkeypatch.setattr(qg, "_REGISTRY", _approved(events.append))
    token = _run_token(client)
    events.clear()
    first = client.post(QG_URL, json=_final(token)).json()          # the server answered; the browser never got it
    again = client.post(QG_URL, json=_final(token)).json()          # "Check again" with the same request
    assert first["ai_output_allowed"] is True, first
    assert again["ai_output_allowed"] is True and again["decision"] == first["decision"], again
    assert again["trace_id"] == first["trace_id"], "the stored decision is replayed, never re-evaluated"
    releases = [e for e in events if e["event"] == "agent.run"]
    assert len(releases) == 1, "one release record for one run"
    assert any(e["event"] == "agent.consultation" and "replay" in e["code"] for e in events), "a replay is audited"


def test_rc126_k2_a_withheld_first_answer_is_never_replayed_as_more_permissive(versioned, monkeypatch):
    client, _ = versioned
    monkeypatch.setattr(qg, "_REGISTRY", _approved(lambda e: None))
    token = _run_token(client)
    first = client.post(QG_URL, json=_final(token, "unknown")).json()
    again = client.post(QG_URL, json=_final(token, "unknown")).json()
    assert first["ai_output_allowed"] is False and again["ai_output_allowed"] is False
    assert again["decision"] == first["decision"] and again["codes"] == first["codes"]


def test_rc126_k2_another_request_with_the_same_token_is_refused(versioned, monkeypatch):
    client, _ = versioned
    monkeypatch.setattr(qg, "_REGISTRY", _approved(lambda e: None))
    token = _run_token(client)
    assert client.post(QG_URL, json=_final(token)).json()["ai_output_allowed"] is True
    other = client.post(QG_URL, json=_final(token, "unknown")).json()
    assert other["ai_output_allowed"] is False and "run_not_confirmed" in other["codes"]


def test_rc126_k2_a_failed_evaluation_does_not_burn_the_token(versioned, monkeypatch):
    client, _ = versioned
    monkeypatch.setattr(qg, "_REGISTRY", _approved(lambda e: None))
    token = _run_token(client)
    real, calls = qg.consult_quality_gate, []

    def flaky(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("evaluation interrupted")
        return real(*a, **k)

    monkeypatch.setattr(qg, "consult_quality_gate", flaky)
    lost = TestClient(app, raise_server_exceptions=False).post(QG_URL, json=_final(token))
    assert lost.status_code == 500
    again = TestClient(app).post(QG_URL, json=_final(token))
    if again.status_code == 429:                                     # the claim's lease: retry after the wait
        monkeypatch.setattr(qg, "_now", (lambda t: (lambda: t + qg.RUN_CLAIM_LEASE_S + 1))(qg._now()))
        again = TestClient(app).post(QG_URL, json=_final(token))
    assert again.json()["ai_output_allowed"] is True, again.json()


def test_rc126_k2_an_unavailable_store_fails_closed(versioned, monkeypatch):
    client, _ = versioned
    monkeypatch.setattr(qg, "_REGISTRY", _approved(lambda e: None))
    token = _run_token(client)

    class _Down:
        def __getattr__(self, name):
            def fail(*a, **k):
                from app.security.agent_scope import AgentScopeError
                raise AgentScopeError("ticket store unavailable")
            return fail

    monkeypatch.setattr(qg, "_run_token_store", lambda: _Down())
    final = client.post(QG_URL, json=_final(token)).json()
    assert final["ai_output_allowed"] is False and "run_not_confirmed" in final["codes"]


def test_rc126_k2_the_card_model_s_fake_server_replays_as_the_real_server_does(monkeypatch):
    import importlib.util
    monkeypatch.setenv("QUALITY_GATE_RUN_TOKEN_STORE", "memory")
    monkeypatch.setenv("QUALITY_GATE_TOKEN_SECRET", "card-model-fixture")
    monkeypatch.setattr(qg, "_RUN_TOKEN_MEMORY", None)
    spec = importlib.util.spec_from_file_location("card_model_fixture", ROOT / "scripts/safety/quality_gate_card_model_fixture.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    shipped = json.loads((ROOT / "frontend/src/config/qualityGate.card_model.v1.json").read_text(encoding="utf-8"))
    assert shipped["run_token"] == gen.run_token_semantics(), "the model's fake server no longer replays as the server does"
    assert shipped["decisions"] == gen.decisions()


# ============================================================================= K3: no silent dead end
class _Bare:
    """A storage that can only download (no metadata method at all)."""

    def __init__(self, data):
        self.data = data

    async def download_file(self, bucket, path):
        return self.data


class _NoVersion(_Bare):
    async def get_file_metadata(self, bucket, path):
        raise OSError("metadata unavailable")


class _NullVersion(_Bare):
    async def get_file_metadata(self, bucket, path):
        return None


@pytest.mark.parametrize("storage", [_NoVersion, _NullVersion, _Bare, _Versioned])
def test_rc126_k3_a_run_permission_always_names_the_file_version(single, monkeypatch, storage):
    client, _ = single
    monkeypatch.setattr(qg, "_REGISTRY", _approved(lambda e: None))
    data = app.dependency_overrides[get_storage_service]().data
    app.dependency_overrides[get_storage_service] = lambda: storage(data)
    body = client.post(QG_URL, json={"file_id": FILE, "physician_confirmed_flair": True}).json()
    version = body["subject"]["version"]
    if "run_token" in body or body["ai_may_run"] is True:
        assert isinstance(version, str) and version, body
    else:
        assert "version_not_established" in body["codes"], body


def test_rc127_k3_version_not_established_is_a_registered_code_with_a_message():
    policy = json.loads((ROOT / "backend/app/services/quality_gate_policy.json").read_text(encoding="utf-8"))
    reasons = json.loads((ROOT / "backend/app/services/quality_gate_reasons.json").read_text(encoding="utf-8"))
    assert policy["codes"].get("version_not_established") == "abstain"
    assert set(reasons["reasons"]["version_not_established"]) >= {"en", "es", "de"}
    for loc in ("en", "es", "de"):
        texts = json.loads((ROOT / f"frontend/src/i18n/locales/{loc}.json").read_text(encoding="utf-8"))["qualityGate"]
        assert texts["codes"]["version_not_established"]["message"] and texts["check"]["version"]


# ============================================================================= K5: the store off the event loop
class _LoopWatchingStore:
    """Wraps the code's own memory store; records whether each blocking call ran on the event loop's thread."""

    def __init__(self, inner):
        self.inner, self.on_loop = inner, []

    def __getattr__(self, name):
        target = getattr(self.inner, name)

        def call(*a, **k):
            try:
                asyncio.get_running_loop()
                self.on_loop.append(True)
            except RuntimeError:
                self.on_loop.append(False)
            return target(*a, **k)
        return call


def test_rc126_k5_the_single_use_store_is_never_called_on_the_event_loop(versioned, monkeypatch):
    from app.security.agent_scope import MemoryTicketStore
    client, _ = versioned
    monkeypatch.setattr(qg, "_REGISTRY", _approved(lambda e: None))
    token = _run_token(client)
    watch = _LoopWatchingStore(qg.RunLedger(qg.MemoryDocs()) if hasattr(qg, "RunLedger") else MemoryTicketStore())
    monkeypatch.setattr(qg, "_run_token_store", lambda: watch)
    client.post(QG_URL, json=_final(token))
    assert watch.on_loop and not any(watch.on_loop), ("a blocking store call ran on the event loop", watch.on_loop)


# ============================================================================= K6: one outcome record on every path
def _outcomes(events):
    return [e for e in events if str(e.get("code", "")).startswith(("quality_gate.released", "quality_gate.withheld"))]


def _seg():
    return app.dependency_overrides[get_segmentation_service]()


def _after(n, mp, owner, name, exc=RuntimeError("post-gate step failed")):
    """``owner.name`` behaves as itself for its first ``n`` calls (the gate's own use), then raises."""
    real, calls = getattr(owner, name), []

    def fault(*a, **k):
        calls.append(1)
        if len(calls) > n:
            raise exc
        return real(*a, **k)
    mp.setattr(owner, name, fault)


COMPARE_FAULTS = {
    "mask_missing": lambda mp: mp.setattr(_seg(), "get_mask", lambda sid: None),
    "grid_mismatch": lambda mp: mp.setattr(sa, "_require_comparable_grid",
                                           lambda a, b: (_ for _ in ()).throw(HTTPException(status_code=422, detail="grid"))),
    "comparison_fails": lambda mp: _after(0, mp, sa, "compare_timepoints"),
    "presentation_fails": lambda mp: mp.setattr(qg, "present_gated_comparison",
                                                lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))),
    "evidence_read_fails": lambda mp: _after(0, mp, lcs, "load_false_candidate_evidence", MemoryError()),
}
SEL_FAULTS = {
    "intensities_missing": lambda mp: None,               # the fixture's source images give no intensities: 422
    "mask_missing": lambda mp: mp.setattr(_seg(), "get_mask", lambda sid: None),
    "grid_mismatch": lambda mp: mp.setattr(sa, "_require_comparable_grid",
                                           lambda a, b: (_ for _ in ()).throw(HTTPException(status_code=422, detail="grid"))),
    "detection_fails": lambda mp: (mp.setattr(sa, "_load_source_intensity", _intensities),
                                   mp.setattr("app.services.sel_detection_service.detect_sels",
                                              lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))),
}


async def _intensities(file_id, storage_service, context):
    return np.ones((12, 24, 24), np.float32), (1.0, 1.0, 1.0), None


@pytest.mark.parametrize("route, fault", [("compare", f) for f in COMPARE_FAULTS] + [("sel", f) for f in SEL_FAULTS]
                         + [("compare", None)])
def test_rc126_k6_every_allowed_pair_leaves_exactly_one_outcome_record(compare, monkeypatch, route, fault):
    client, _, _ = compare
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", True)
    events = []
    monkeypatch.setattr(qg, "_REGISTRY", _approved(events.append))
    (COMPARE_FAULTS if route == "compare" else SEL_FAULTS).get(fault, lambda mp: None)(monkeypatch)
    r = TestClient(app, raise_server_exceptions=False).post(f"/api/v1/segmentation/longitudinal/{route}", json=PAIR)
    gate = [e for e in events if e["event"] == "agent.consultation" and str(e["code"]).startswith("quality_gate.proceed")]
    assert gate, ("the gate did not allow the pair", events)
    outcomes = _outcomes(events)
    assert len(outcomes) == 1, (route, fault, r.status_code, outcomes)
    if r.status_code >= 400:
        assert outcomes[0]["code"].startswith("quality_gate.withheld."), outcomes


# ============================================================================= K7: a closed registry of reasons
PII_LIKE = ["jane.doe@hospital.org", "patient_12345_flair.nii.gz", "C:\\Users\\drsmith\\scan.dcm",
            "/data/patients/MRN-889911/t1.nii", "MRN889911", "1.2.840.113619.2.55.3.604688", "Juan Perez Gomez",
            "Patient John Smith has new lesions", "agent.run:jane.doe@hospital.org", "agent.consultation:patient_12345",
            "quality_gate.withheld.patient_12345", "x" * 80, "agent.run:" + "lesion_" * 12]
PII_FRAGMENTS = ["jane", "12345", "drsmith", "889911", "604688", "Perez", "Smith", "xxxxxxxx", "lesion_lesion"]


def _record(reason):
    return A.build_audit_record(A.AuditEvent(event_type=A.AuditEventType.CLINICAL_AI_RUN, severity=A.AuditSeverity.LOW,
                                             outcome=A.AuditOutcome.SUCCESS, reason=reason, source="explicit"))


@pytest.mark.parametrize("reason", PII_LIKE)
def test_rc126_k7_no_pii_like_reason_ever_persists(reason):
    record = _record(reason)
    dump = json.dumps(record)
    assert record.get("reason") == "reason_unregistered", record.get("reason")
    assert "full_reason" not in record.get("details", {})
    assert not [f for f in PII_FRAGMENTS if f in dump], dump


def test_rc126_k7_every_valid_long_composition_persists_in_full():
    for whole in ("agent.consultation:quality_gate.withheld.http_422:run_not_confirmed:version_not_established",
                  "agent.run:quality_gate.proceed_with_warnings.attested:sequence_confirmed_by_physician:thickness_at_least",
                  "agent.consultation:quality_gate.abstain:skull_pending:sequence_missing:gate_rate_limited"):
        record = _record(whole)
        assert len(whole) > 64 and record["details"]["full_reason"] == whole, record
        assert re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", record["reason"]) and record["reason"].startswith(whole.split(":")[0])
    for short in ("agent.run:agent_not_approved", "unknown_session", "agent.scope:ticket_replay"):
        assert _record(short)["reason"] == short


def test_rc126_k7_every_literal_audit_reason_of_the_platform_is_registered():
    pattern = re.compile(r"""(?:\breason\s*=\s*|["']reason["']\s*:\s*|audit_failure\(\s*)["']([A-Za-z0-9_.:-]+)["']""")
    files = [ROOT / "backend/app/api/routes/auth.py", ROOT / "backend/app/api/routes/authentication.py",
             ROOT / "backend/app/security/auth.py", ROOT / "backend/app/security/agent_scope.py"]
    literal = {m for f in files for m in pattern.findall(f.read_text(encoding="utf-8"))}
    assert literal, "no literal reasons found"
    unregistered = sorted(r for r in literal if _record(r)["reason"] != r)
    assert unregistered == [], unregistered


# ============================================================================= K8: the visit check before any read
class _ReadCounter(_Storage):
    def __init__(self, data):
        super().__init__(data)
        self.reads = 0

    async def download_file(self, bucket, path):
        self.reads += 1
        return self.data

    async def get_file_metadata(self, bucket, path):
        self.reads += 1
        return None


def test_rc123_k8_a_same_visit_pair_starts_no_read(compare, monkeypatch):
    client, _, (f1, f2) = compare
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", True)
    monkeypatch.setattr(qg, "_REGISTRY", _approved(lambda e: None))
    monkeypatch.setattr(sa, "_source_visit", lambda fid: {"study_id": "st-same", "study_date": "2024-01-10"})
    counter = _ReadCounter(b"")
    app.dependency_overrides[get_storage_service] = lambda: counter
    records = []
    monkeypatch.setattr(qg, "stored_records", lambda *a, **k: records.append(a) or (None, None))
    r = client.post("/api/v1/segmentation/longitudinal/compare", json=PAIR)
    assert r.status_code == 400
    assert counter.reads == 0 and records == [], "a read was started for a pair refused by the visit check"


# ============================================================================= K9: one details filter
def test_rc126_k9_the_registry_and_the_record_use_one_details_filter():
    details = {"causes": [f"code_{i}" for i in range(25)], "warnings": ["thickness_at_least"], "decision": "abstain",
               "mode": "single with spaces", "released": False, "withheld_by": "x" * 40, "not_a_detail_key": "kept?",
               "attested_visits": ["tp1"], "skull_report": "client_reported:stripped"}
    events = []
    reg = _approved(events.append)
    reg.audit("success", "quality_gate.abstain", event="agent.consultation", agent_id="quality-gate", details=details)
    # fifteenth review (S6) supersedes K9's second filter: the details pass through, the record's builder filters ONCE
    assert events[0]["details"] == details
    assert "_plain_details" not in inspect.getsource(R) and "_safe_details" not in inspect.getsource(R)


# ============================================================================= K10: one read strategy
class _Instances:
    def __init__(self, docs, queryable=True):
        self.docs, self.queries, self.scans = docs, 0, 0
        if not queryable:
            self.where = None

    def where(self, *a, **k):                     # noqa: F811 — the queryable store
        store = self

        class _Q:
            def limit(self, n):
                return self

            def stream(self):
                store.queries += 1
                field = k["filter"].field_path if "filter" in k else a[0]
                value = k["filter"].value if "filter" in k else a[2]
                hits = [d for d in store.docs if d.to_dict().get(field.split(".")[-1]) == value]
                return iter(hits[:1])
        return _Q()

    def stream(self):
        self.scans += 1
        return iter(self.docs)


class _Doc:
    def __init__(self, data):
        self._d = data

    def to_dict(self):
        return dict(self._d)


@pytest.mark.parametrize("queryable", [True, False])
def test_rc123_g26_k10_rc062_s_input_is_the_same_with_the_gate_on_and_off(monkeypatch, queryable):
    file_id = "patients/p/studies/s/series/x/f.nii.gz"
    docs = [_Doc({"gcs_object_name": "patients/p/studies/s/series/x/other.nii.gz", "acquisition": {"manufacturer": "GE"}}),
            _Doc({"gcs_object_name": file_id, "acquisition": {"manufacturer": "SIEMENS"}})]
    seen = {}
    for enforced in (False, True):
        instances = _Instances(list(docs), queryable)

        class _Series:
            def collection(self, name):
                return instances
        monkeypatch.setattr(lcs, "source_refs", lambda fid, svc=None: (None, _Series()))
        monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", enforced)
        seen[enforced] = (lcs.read_source_acquisition(file_id), instances.queries, instances.scans)
    assert seen[True][0] == seen[False][0] == {"manufacturer": "SIEMENS"}
    assert seen[True][1:] == seen[False][1:], ("one read strategy whatever the flag", seen)
    # fifteenth review (S3): K10 withdrawn — the ONE strategy is the base read, the scan, whatever the store answers
    assert seen[False][1:] == (0, 1), "the base read: a scan of the series' instances"
