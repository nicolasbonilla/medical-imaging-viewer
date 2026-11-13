"""Thirteenth review of PR #81: the run-token lifecycle (M2), the decision token bound to the clinician (M3), the audit
marker set only after the record was written (A1), no audit reason ever lost (A2), one place for the SEL abstention,
the attestation type and its validator; and the server decisions the browser card's model-based test plays (M1).
DRAFT, PENDING owner approval."""
import importlib.util
import inspect
import json
import logging
import re
from pathlib import Path

import pytest
from fastapi import HTTPException

import app.api.routes.segmentation_analysis as sa
from app.agent_platform import registry as R
from app.services import quality_gate as qg
from tests.unit.test_rc122_quality_gate_wiring import FILE, URL, _registry, single  # noqa: F401 — fixtures

ROOT = Path(__file__).resolve().parents[3]
F, V, U = "patients/p/studies/s/series/x/f.nii.gz", "10:v1:2026-11-12", "id-dr_rev"


@pytest.fixture
def memory_tokens(monkeypatch):
    monkeypatch.setenv("QUALITY_GATE_RUN_TOKEN_STORE", "memory")
    monkeypatch.setattr(qg, "_RUN_TOKEN_MEMORY", None, raising=False)


# ----------------------------------------------------------------------------- M1: the fake server's decisions
def test_rc126_m1_the_card_model_plays_the_server_s_own_decisions():
    spec = importlib.util.spec_from_file_location("card_model_fixture", ROOT / "scripts/safety/quality_gate_card_model_fixture.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    shipped = json.loads((ROOT / "frontend/src/config/qualityGate.card_model.v1.json").read_text(encoding="utf-8"))
    assert shipped["decisions"] == gen.decisions(), "the card model's fake server no longer answers with the server's rule"


# ----------------------------------------------------------------------------- M2
def test_rc126_m2_a_token_is_issued_only_by_a_run_consultation_that_allows_the_run(single, monkeypatch, memory_tokens):
    client, _ = single
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    assert "run_token" not in client.post(URL, json={"file_id": FILE}).json()                     # abstains: no run
    run = client.post(URL, json={"file_id": FILE, "physician_confirmed_flair": True}).json()
    assert run["ai_may_run"] is True and isinstance(run.get("run_token"), str)
    assert "run_token" not in client.post(URL, json={"file_id": FILE, "physician_confirmed_flair": True,
                                                     "skull": "stripped"}).json()                # a final one: none


def _claim(token, **wrong):
    return qg.claim_final(token, **{"file_id": F, "version": V, "user_id": U, "attested": False, "skull": "stripped", **wrong})


def test_rc126_m2_spendable_once_before_expiry_by_the_same_user_for_the_same_file_and_version(monkeypatch, memory_tokens):
    """M2, as amended by K2 (fourteenth review): one claim per token — the identical request replays its decision,
    another request is refused."""
    token = qg.run_token(F, V, U, False)
    for wrong in ({"file_id": F + "x"}, {"version": "11:v2:x"}, {"user_id": "id-other"}, {"attested": True}):
        assert _claim(token, **wrong).status == "invalid"
    late = qg.run_token(F, V, U, False)
    monkeypatch.setattr(qg, "_now", lambda: 10 ** 11)
    assert _claim(late).status == "invalid"                                          # expired
    monkeypatch.undo()
    monkeypatch.setenv("QUALITY_GATE_RUN_TOKEN_STORE", "memory")
    first = _claim(token)
    assert first.status == "fresh"
    qg.settle_final(first, {"decision": "proceed", "trace_id": "t1"})
    again = _claim(token)
    assert again.status == "replay" and again.answer == {"decision": "proceed", "trace_id": "t1"}
    assert _claim(token, skull="unknown").status == "conflict"                       # once, for one request


def test_rc126_m2_an_unexpired_token_is_never_forgotten_and_a_full_store_fails_closed(monkeypatch, memory_tokens, caplog):
    monkeypatch.setattr(qg, "RUN_TOKENS_SPENT_MAX", 3)
    first = qg.run_token(F, V, U, False)
    assert _claim(first).status == "fresh"
    for _ in range(2):
        assert _claim(qg.run_token(F, V, U, False)).status == "fresh"
    with caplog.at_level(logging.WARNING):
        assert _claim(qg.run_token(F, V, U, False)).status == "unavailable"
    assert any("run token" in r.getMessage().lower() for r in caplog.records), "a refused release is logged"
    assert _claim(first, skull="unknown").status == "conflict", "an unexpired token was forgotten"


class _AlreadyExistsStore:
    """A durable store as Firestore's: one document per token, read and written inside a transaction (fifteenth review,
    S1); the transaction runner is a plain call here (offline — the SDK's runs it in the service)."""

    def __init__(self):
        self.docs = {}

    def collection(self, name):
        return self

    def transaction(self):
        return self

    def set(self, ref, data):
        self.docs[ref.doc_id] = dict(data)

    def document(self, doc_id):
        store = self

        class _Snap:
            def __init__(self, data):
                self.exists, self._data = data is not None, data

            def to_dict(self):
                return dict(self._data) if self._data is not None else None

        class _Doc:
            def __init__(self):
                self.doc_id = doc_id

            def get(self, transaction=None):
                return _Snap(store.docs.get(doc_id))
        return _Doc()


def test_rc126_m2_a_replay_after_a_reload_is_rejected_while_the_token_is_unexpired(monkeypatch):
    """After a restart the durable ledger still knows the token: the identical request gets the SAME decision back
    (K2), another request is refused — never a second fresh run."""
    durable = _AlreadyExistsStore()
    monkeypatch.delenv("QUALITY_GATE_RUN_TOKEN_STORE", raising=False)
    import app.core.firebase as fb
    from google.cloud import firestore
    monkeypatch.setattr(fb, "get_firestore_client", lambda *a, **k: durable)
    monkeypatch.setattr(firestore, "transactional", lambda fn: (lambda tx: fn(tx)))
    token = qg.run_token(F, V, U, False)
    first = _claim(token)
    assert first.status == "fresh"
    qg.settle_final(first, {"decision": "proceed", "trace_id": "t1"})
    spec = importlib.util.spec_from_file_location("quality_gate_reloaded", qg.__file__)
    fresh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fresh)                                  # the module state reloaded (a restart)
    args = {"file_id": F, "version": V, "user_id": U, "attested": False}
    again = fresh.claim_final(token, **args, skull="stripped")
    assert again.status == "replay" and again.answer == {"decision": "proceed", "trace_id": "t1"}
    assert fresh.claim_final(token, **args, skull="unknown").status == "conflict"


# ----------------------------------------------------------------------------- M3
def test_rc127_m3_a_colleague_s_report_never_uses_another_clinician_s_decision(monkeypatch):
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", True)
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    visit = {"sequence": "FLAIR", "physician_confirmed_flair": False, "skull": "stripped", "scanner": None,
             "thickness": {"state": "native", "effective_mm": 1.0}}
    gate = qg.run_quality_gate({"mode": "comparison", "visits": [visit, dict(visit)], "rc062_withholds": False},
                               study_key="s", releases_output=False)
    pair = {"tp1": {"id": "s1", "source": None, "version": None}, "tp2": {"id": "s2", "source": None, "version": None}}
    lng = {"pair": pair, "quality_gate": {**gate, "token": qg.decision_token(gate, pair, "id-dr_rev")}}
    assert qg.report_account(lng, user_id="id-dr_rev")["established"] is True
    assert qg.report_account(lng, user_id="id-colleague")["established"] is False


# ----------------------------------------------------------------------------- A1
def test_rc126_a1_the_route_s_marker_is_set_only_after_its_record_was_written(single, monkeypatch, memory_tokens):
    from app.core.logging import audit as A
    client, _ = single
    data = json.loads((ROOT / "backend/app/agent_platform/agents.json").read_text(encoding="utf-8"))
    data["agents"]["quality-gate"]["approval"]["status"] = "approved"     # IN MEMORY, for the test only
    monkeypatch.setattr(qg, "_REGISTRY", R.AgentRegistry(data, switches=R.InMemoryKillSwitches({"quality-gate": True}),
                                                         audit=R.default_audit_sink))
    written = []

    def flaky(self, event, durable=True):
        if event.source == "explicit":
            raise RuntimeError("audit sink down")                        # the route's own record fails
        written.append(event)

    monkeypatch.setattr(A.AuditLogger, "log_event", flaky)
    assert client.post(URL, json={"file_id": FILE}).status_code == 200
    assert len(written) == 1 and written[0].source == "middleware", "the request left no audit record"


# ----------------------------------------------------------------------------- A2
def test_rc126_a2_no_audit_reason_is_ever_lost(monkeypatch):
    from app.core.logging import audit as A
    built = []
    monkeypatch.setattr(A.AuditLogger, "log_event", lambda self, event, durable=True: built.append(A.build_audit_record(event)))
    # K7 (fourteenth review): a long reason persists in full only as a composition of REGISTERED codes
    code = "quality_gate.withheld.http_422:run_not_confirmed:version_not_established:sequence_confirmed_by_physician"
    for prefix in sorted(R.AUDIT_EVENT_TYPES):
        built.clear()
        R.default_audit_sink({"event": prefix, "code": code, "outcome": "success", "agent_id": "quality-gate"})
        (record,) = built
        reason = record.get("reason")
        assert isinstance(reason, str) and len(reason) <= 64 and reason.startswith(prefix + ":"), (prefix, reason)
        assert re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", reason)
        assert record.get("details", {}).get("full_reason") == f"{prefix}:{code}", record.get("details")
    built.clear()
    R.default_audit_sink({"event": "agent.run", "code": "agent_not_approved", "outcome": "denied"})
    assert built[0]["reason"] == "agent.run:agent_not_approved"                                   # a short one, as it is


# ----------------------------------------------------------------------------- one place
def test_rc123_one_sel_abstention_response():
    assert hasattr(qg, "abstained_sel")
    assert '"sels": []' not in inspect.getsource(sa.detect_slowly_expanding_lesions)


def test_rc123_one_attestation_validator_on_the_server():
    from pydantic import BaseModel
    assert issubclass(qg.PairAttestation, BaseModel)
    assert "PairAttestation" in inspect.getsource(sa._attestation)
    for bad in ({"tp1": "true"}, {"tp1": 1}, ["tp1"], {"tp3": True}):
        with pytest.raises(HTTPException) as e:
            sa._attestation({"quality_gate_attestation": bad})
        assert e.value.status_code == 400 and e.value.detail == "quality_gate_attestation must map tp1/tp2 to true or false"
    assert sa._attestation({"quality_gate_attestation": {"tp1": True}}) == (True, False)


def test_rc127_one_attestation_type_in_the_browser():
    src = ROOT / "frontend/src"
    files = [p for p in src.rglob("*.ts*") if ".test." not in p.name]
    shapes = [(p.name, n) for p in files for n in [p.read_text(encoding="utf-8").count("tp1: boolean; tp2: boolean")] if n]
    assert shapes == [("gate.ts", 1)], shapes
