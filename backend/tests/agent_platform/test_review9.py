"""Light verification of PR #79 (round 9) — failing-first tests. DRAFT, PENDING owner approval.

T1 (security, RC-121): one physician confirmation authorises exactly ONE pass — the preview's ticket is single-use
(a jti consumed atomically: Firestore create-if-absent across instances; an in-process store for tests); a second
redemption is refused and audited once as a replay. T2 the preview states the time left to confirm and the session
length, each with its meaning. T3 one helper for the request checks of a session.
"""
import ast
import asyncio
import inspect

import pytest
from fastapi import HTTPException

from tests.agent_platform.test_review5 import S1, USER, _Backend, _scope_module, scope_key  # noqa: F401
from tests.agent_platform.test_review6 import assistant  # noqa: F401
from tests.agent_platform.test_review7 import Human


# ================================================================== T1: single-use ticket
def test_rc121_review9_a_confirmation_authorises_exactly_one_pass(scope_key, monkeypatch):
    import app.core.logging.audit as audit
    S = _scope_module()
    _Backend().install(monkeypatch)
    emitted = []
    monkeypatch.setattr(audit, "emit_audit", lambda *a, **k: emitted.append(k.get("reason")))
    preview = asyncio.run(S.preview_studies([S1], USER))
    first = asyncio.run(S.issue_from_pending(preview["pending"], USER, run_id="run-a"))
    assert S.verify_scope_token(first).study_ids == frozenset({S1})
    with pytest.raises(HTTPException) as e:
        asyncio.run(S.issue_from_pending(preview["pending"], USER, run_id="run-b"))
    assert e.value.status_code == 409
    assert [r for r in emitted if r and "replay" in r] == ["agent.scope:ticket_replay"]


def test_rc121_review9_the_shared_store_consumes_atomically_and_fails_closed(scope_key):
    from google.api_core.exceptions import AlreadyExists
    S = _scope_module()

    class Doc:
        def __init__(self, docs, key):
            self.docs, self.key = docs, key

        def create(self, data):
            if self.key in self.docs:
                raise AlreadyExists("exists")
            self.docs[self.key] = data

    class Client:
        def __init__(self):
            self.docs = {}

        def collection(self, name):
            return type("C", (), {"document": lambda _self, key: Doc(self.docs, (name, key))})()
    store = S.FirestoreTicketStore(client=Client())
    assert store.consume("jti-1", 2 ** 40) is True and store.consume("jti-1", 2 ** 40) is False

    class Down:
        def collection(self, name):
            raise RuntimeError("datastore unreachable")
    with pytest.raises(S.AgentScopeError):
        S.FirestoreTicketStore(client=Down()).consume("jti-2", 2 ** 40)


def test_rc121_review9_the_store_is_shared_unless_explicitly_in_process(monkeypatch):
    S = _scope_module()
    monkeypatch.delenv("AGENT_SCOPE_TICKET_STORE", raising=False)
    assert isinstance(S.ticket_store(), S.FirestoreTicketStore)
    monkeypatch.setenv("AGENT_SCOPE_TICKET_STORE", "memory")
    assert isinstance(S.ticket_store(), S.MemoryTicketStore)


# ================================================================== T2: both times, each with its meaning
def test_rc121_review9_the_preview_states_both_times(assistant):
    server, _backend, _app, _paid = assistant
    S = _scope_module()
    preview = asyncio.run(S.preview_studies([S1], USER))
    assert preview["confirm_within_seconds"] == S.PENDING_TTL_SECONDS == 300
    assert preview["session_seconds"] == S.DEFAULT_TTL_SECONDS == 900 and "expires_in" not in preview
    human = Human(("accept", S1), ("accept", None))
    asyncio.run(server.open_study_session(human))
    assert "within 5 minutes" in human.asked[1] and "15 minutes" in human.asked[1]


# ================================================================== T3: one helper
def test_rc121_review9_one_helper_for_the_request_checks():
    S = _scope_module()
    for fn in (S.preview_studies, S._authorize_studies):
        src = inspect.getsource(fn)
        assert "_requested_studies(" in src and "scope_active()" not in src and "_canon(s) for s" not in src, fn
    assert ast.parse(inspect.getsource(S._requested_studies))
