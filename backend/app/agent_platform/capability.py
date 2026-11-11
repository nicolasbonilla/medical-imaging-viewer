"""
The run's study-scoped capability, as the tool layer sees it — RC-121 (HAZ-021), REQ-AGT-008.

DRAFT, PENDING owner approval. Fifth review of PR #79 (structural finding): the run scope is enforced at the
SOURCE. For an agent whose tools reach the backend (``requires_backend_scope`` in agents.json), the backend
issues a short-lived capability for the run's patient and studies (``app.security.agent_scope``, after its own
CAPA-009 authorization of each study). The runtime holds it in ``RunScope.capability`` and makes it current
around every tool call; the backend client (``app.mcp._backend``) sends it in ``CAPABILITY_HEADER`` with every
request; the backend then refuses any object outside the capability in the same object-level checks that
already protect every route (404, as for an object the clinician may not see). The model never sees the
capability, and a tool cannot widen it: it is signed by the backend and bound to the clinician.

The id walk of ``untrusted.py`` (RC-114) stays as a second, defence-in-depth layer.

Standard library only (the platform has no third-party dependency).

@module agent_platform.capability
"""

from __future__ import annotations

import contextlib
import contextvars
from typing import Iterator, Optional

CAPABILITY_HEADER = "X-MSTool-Agent-Scope"
# Sixth review of PR #79 (S1): EVERY request the assistant's backend client sends carries this marker, whatever
# the session state, so the backend can refuse an assistant request that has no valid scope (it never depends
# on the client volunteering the scope header).
CLIENT_HEADER = "X-MSTool-Client"
ASSISTANT_CLIENT = "mcp-assistant"


class ScopeRefused(PermissionError):
    """The backend (or the client, before sending) refused a request outside the run's study scope. The runtime
    audits it as a DENIAL (``code``), never as the tool's own failure (sixth review, C1)."""

    code = "out_of_scope_resource"

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class ToolNotAllowed(ScopeRefused):
    """A route the assistant may not call (a write, a paid model, a non-assistant read): a denial, tool not allowed
    (eighth review, F5)."""

    code = "tool_not_allowed_for_agent"


class ScopeRequired(ScopeRefused):
    """No study session / capability: the assistant reaches nothing (sixth review, S1)."""

    code = "backend_scope_missing"

_CURRENT: "contextvars.ContextVar[Optional[str]]" = contextvars.ContextVar("mstool_agent_capability", default=None)


def current_capability() -> Optional[str]:
    """The capability of the run whose tool is executing now, or None outside a tool call."""
    return _CURRENT.get()


@contextlib.contextmanager
def capability_context(token: Optional[str]) -> Iterator[None]:
    """Make ``token`` current for the enclosed tool call (worker threads started inside inherit it)."""
    reset = _CURRENT.set(token if isinstance(token, str) and token else None)
    try:
        yield
    finally:
        _CURRENT.reset(reset)
