"""S1 (fifteenth review of PR #81; RC-126; DRAFT, PENDING owner approval): a MODEL-BASED test of the WHOLE server
lifecycle of a run token, through the real route (POST /api/v1/clinical/quality-gate), with a failure injected at EVERY
external call: the store's read, write and (ambiguous) commit, the audit write, the evaluation, and a lost response.

Each generated sequence obtains one run token, then plays: the identical final consultation (delivered or its response
LOST), a DIFFERENT one with the same token (another skull report: another request digest), the claim's lease expiring,
a store read / write / ambiguous-commit failure on the next call, an audit-write failure, an evaluation fault.
Properties, checked on every response and at the end of each sequence:
  PS1  at most one CLINICAL_AI_RUN (agent.run) record per token;
  PS2  every delivered decision for the identical request equals the FIRST decision the store kept for the token;
  PS3  never "in progress" (429 gate_run_in_progress) unless a live claim exists;
  PS4  a replay is never more permissive than the first stored decision;
  PS5  fail closed: a request during which a store call failed releases nothing and records no AI run;
  PS6  a request whose digest differs from the one the token was claimed with is always rejected.
QG_SERVER_MODEL_RUNS sets the number of sequences (default 2000)."""
import json
import os
import random
from concurrent.futures import Future

import pytest
from fastapi.testclient import TestClient

from app.agent_platform import registry as R
from app.core.container import get_storage_service
from app.main import app
from app.services import quality_gate as qg
from tests.unit.test_rc122_quality_gate_wiring import FILE, REGISTRY, _Storage, single  # noqa: F401 — fixtures

pytestmark = pytest.mark.unit
URL = "/api/v1/clinical/quality-gate"
RUNS = int(os.environ.get("QG_SERVER_MODEL_RUNS", "2000"))
NEW = hasattr(qg, "RunLedger")                 # the fifteenth review's one-document ledger
ACTIONS = [("final", 4), ("final_lost", 3), ("final_other", 2), ("lease", 2), ("fail_read", 1), ("fail_write", 1),
           ("ambiguous_write", 1), ("fail_audit", 1), ("eval_fault", 1), ("consult_raises", 1)]


class _Unavailable(Exception):
    """A store call that did not go through (as google.api_core's ServiceUnavailable)."""


class _World:
    def __init__(self, rng):
        self.rng, self.now = rng, 1_800_000_000.0
        self.fault = None              # (read | write | ambiguous, calls of that kind to let through first)
        self.failed = False            # a store call failed during the current request
        self.audit_fail = False
        self.eval_fault = False
        self.consult_raises = False
        self.events = []
        self.violations = {}

    def violate(self, prop, why):
        self.violations.setdefault(prop, why)

    def store_call(self, kind, apply=None):
        """One external call of the store: ``kind`` read or write; ``apply`` performs a write."""
        hit = self.fault is not None and (self.fault[0] == kind or (self.fault[0] == "ambiguous" and kind == "write"))
        if hit and self.fault[1] > 0:
            self.fault = (self.fault[0], self.fault[1] - 1)
        elif hit:
            ambiguous, self.fault = self.fault[0] == "ambiguous", None
            self.failed = True
            if ambiguous and apply is not None:
                apply()                # the write happened, the caller is told it did not
            raise _Unavailable(f"store {kind} failed")
        return apply() if apply is not None else None


class _FakeFirestore:
    """The durable store of the code before the fifteenth review (create / get / update), with the World's faults."""

    def __init__(self, world):
        self.world, self.docs = world, {}

    def collection(self, name):
        return self

    def document(self, doc_id):
        fs = self

        class _Snap:
            def __init__(self, data):
                self.exists, self._d = data is not None, data

            def to_dict(self):
                return dict(self._d) if self._d is not None else None

        class _Ref:
            def create(self, data):
                from google.api_core.exceptions import AlreadyExists

                def apply():
                    if doc_id in fs.docs:
                        raise AlreadyExists("exists")
                    fs.docs[doc_id] = dict(data)
                fs.world.store_call("write", apply)

            def get(self):
                fs.world.store_call("read")
                return _Snap(fs.docs.get(doc_id))

            def update(self, data, option=None):
                fs.world.store_call("write", lambda: fs.docs[doc_id].update(data))
        return _Ref()


def _view(docs, key):
    """The token's state in the store, whatever the ledger: (claimed digest, claimed_at, decided answer or None)."""
    if NEW:
        doc = docs.peek(key)
        if doc is None:
            return None, None, None
        return doc.get("request_digest"), doc.get("claimed_at"), doc.get("decision") if doc.get("state") == "decided" else None
    claim, decided = docs.get(key), docs.get(f"{key}-decision")
    return ((claim or {}).get("digest"), (claim or {}).get("claimed_at"),
            json.loads(decided["answer"]) if decided else None)


def _approved(audit):
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    data["agents"]["quality-gate"]["approval"]["status"] = "approved"          # IN MEMORY, for the test only
    return R.AgentRegistry(data, switches=R.InMemoryKillSwitches({"quality-gate": True}), audit=audit)


class _Versioned(_Storage):
    async def get_file_metadata(self, bucket, path):
        from app.core.interfaces.storage_interface import StorageObject
        return StorageObject(bucket=bucket, name=path, size=len(self.data), content_type="application/octet-stream",
                             checksum_sha256="v1", created_at="2026-11-13")


def _play(client, final_client, monkeypatch, seed):
    rng = random.Random(seed)
    world = _World(rng)

    def sink(event):
        if world.audit_fail:
            world.audit_fail = False
            raise OSError("audit write failed")
        world.events.append(event)

    monkeypatch.setattr(qg, "_REGISTRY", _approved(sink))
    monkeypatch.setattr(qg, "_now", lambda: world.now)
    real_evaluate = qg.evaluate

    def evaluate(*a, **k):
        if world.eval_fault:
            world.eval_fault = False
            raise RuntimeError("evaluation fault")
        return real_evaluate(*a, **k)
    monkeypatch.setattr(qg, "evaluate", evaluate)
    for name in ("run_quality_gate", "consult_quality_gate"):     # the call the route evaluates the gate with
        if hasattr(qg, name):
            def raising(*a, _real=getattr(qg, name), **k):
                if world.consult_raises:
                    world.consult_raises = False
                    raise RuntimeError("the evaluation was interrupted")
                return _real(*a, **k)
            monkeypatch.setattr(qg, name, raising)
    if NEW:
        docs = qg.MemoryDocs(faults=lambda kind, apply=None: world.store_call(kind, apply))
        store = qg.RunLedger(docs)
    else:
        fake = _FakeFirestore(world)
        docs, store = fake.docs, qg.FirestoreRunLedger(client=fake)
    monkeypatch.setattr(qg, "_run_token_store", lambda: store)

    run = client.post(URL, json={"file_id": FILE, "physician_confirmed_flair": True}).json()
    token = run["run_token"]
    payload = qg.verify_token(token, "run")
    key = f"run-{payload['nonce']}"
    digest = {sk: qg._final_digest(user_id=payload["user"], file_id=payload["file"], version=payload["version"],
                                   attested=True, skull=sk) for sk in ("stripped", "unknown")}
    first, delivered = None, []
    for _ in range(rng.randint(4, 12)):
        action = rng.choices([a for a, _ in ACTIONS], weights=[w for _, w in ACTIONS])[0]
        if action == "lease":
            world.now += qg.RUN_CLAIM_LEASE_S + 1
            continue
        if action in ("fail_read", "fail_write", "ambiguous_write"):
            world.fault = ({"fail_read": "read", "fail_write": "write", "ambiguous_write": "ambiguous"}[action],
                           rng.randint(0, 2))
            continue
        if action == "fail_audit":
            world.audit_fail = True
            continue
        if action == "eval_fault":
            world.eval_fault = True
            continue
        if action == "consult_raises":
            world.consult_raises = True
            continue
        skull = "unknown" if action == "final_other" else "stripped"
        before_claim = _view(docs, key)[0]
        world.failed, n_events = False, len(world.events)
        r = final_client.post(URL, json={"file_id": FILE, "physician_confirmed_flair": True, "skull": skull,
                                         "run_token": token})
        runs_now = [e for e in world.events[n_events:] if e.get("event") == "agent.run"]
        claimed, claimed_at, stored = _view(docs, key)
        if stored is not None and first is None:
            first = stored
        elif stored is not None and (stored.get("trace_id"), stored.get("decision")) != (first.get("trace_id"), first.get("decision")):
            world.violate("PS2", f"seed {seed}: the store's first decision for the token changed")
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        in_progress = r.status_code == 429 and (body.get("error") or {}).get("details", {}).get("code") == "gate_run_in_progress"
        released = r.status_code == 200 and body.get("ai_output_allowed") is True
        if len([e for e in world.events if e.get("event") == "agent.run"]) > 1:
            world.violate("PS1", f"seed {seed}: a second CLINICAL_AI_RUN for one token")
        if in_progress and not (claimed is not None and stored is None and claimed_at
                                and world.now - float(claimed_at) < qg.RUN_CLAIM_LEASE_S):
            world.violate("PS3", f"seed {seed}: 'in progress' with no live claim")
        if world.failed and (released or runs_now):
            world.violate("PS5", f"seed {seed}: a store call failed, yet the request released an output or recorded an AI run")
        own = digest[skull]
        if before_claim is not None and before_claim != own and released:
            world.violate("PS6", f"seed {seed}: a request with another digest than the token's claim was released")
        if r.status_code == 200 and body.get("replayed") is True and first is not None \
                and body.get("ai_output_allowed") is True and first.get("ai_output_allowed") is not True:
            world.violate("PS4", f"seed {seed}: a replay more permissive than the first stored decision")
        decision = r.status_code == 200 and not any(str(c).startswith("gate_") for c in body.get("codes", []))
        if action != "final_lost" and decision and claimed == own and not world.failed:
            delivered.append(body)
    for body in delivered:                       # PS2 over the whole sequence, against the store's FIRST decision
        if first is None or (body.get("trace_id"), body.get("decision"), body.get("ai_output_allowed")) != \
                (first.get("trace_id"), first.get("decision"), first.get("ai_output_allowed")):
            world.violate("PS2", f"seed {seed}: a delivered decision differs from the store's first decision (or none is kept)")
            break
    return world.violations


@pytest.fixture
def server(single, monkeypatch):
    client, _ = single
    data = app.dependency_overrides[get_storage_service]().data
    app.dependency_overrides[get_storage_service] = lambda: _Versioned(data)
    monkeypatch.setattr(qg, "rate_limit", lambda user_id: None)       # the model sends many consultations
    return client, TestClient(app, raise_server_exceptions=False)


@pytest.mark.timeout(1500)                       # 2 000 lifecycles: several minutes on a laptop, about two in CI
def test_rc126_s1_ps1_ps6_hold_over_the_generated_lifecycles(server, monkeypatch):
    counts = {p: 0 for p in ("PS1", "PS2", "PS3", "PS4", "PS5", "PS6")}
    examples = {}
    for i in range(RUNS):
        with monkeypatch.context() as mp:
            for prop, why in _play(*server, mp, 20261115 + i).items():
                counts[prop] += 1
                examples.setdefault(prop, why)
    report = json.dumps({"sequences": RUNS, "counts": counts, "examples": examples})
    print("S1 server model:", report)
    assert counts == {p: 0 for p in counts}, report


def test_rc126_s1_a_decision_not_stored_fails_closed_and_is_retryable_at_once(server, monkeypatch):
    """The store refuses the settlement of the first decision: the answer is the gate unavailable, no AI-run record;
    the identical retry is a fresh claim AT ONCE (no 'in progress'), released, recorded once."""
    if not NEW:
        pytest.fail("the code has no one-document ledger (fifteenth review, S1)")
    client, final_client = server
    events = []
    monkeypatch.setattr(qg, "_REGISTRY", _approved(events.append))
    writes = {"n": 0}

    def faults(kind, apply=None):
        if kind == "write":
            writes["n"] += 1
            if writes["n"] == 2:                    # the claim's write goes through; the settlement's does not
                raise _Unavailable("settle failed")
        return apply() if apply is not None else None

    monkeypatch.setattr(qg, "_run_token_store", (lambda st: (lambda: st))(qg.RunLedger(qg.MemoryDocs(faults=faults))))
    token = client.post(URL, json={"file_id": FILE, "physician_confirmed_flair": True}).json()["run_token"]
    body = {"file_id": FILE, "physician_confirmed_flair": True, "skull": "stripped", "run_token": token}
    first = final_client.post(URL, json=body).json()
    assert first["ai_output_allowed"] is False and first["codes"] == ["gate_unavailable"], first
    assert not [e for e in events if e.get("event") == "agent.run"], "no AI-run record for a decision not stored"
    again = final_client.post(URL, json=body)
    assert again.status_code == 200 and again.json()["ai_output_allowed"] is True, again.text
    assert len([e for e in events if e.get("event") == "agent.run"]) == 1
