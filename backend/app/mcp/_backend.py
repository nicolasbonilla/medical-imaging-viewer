"""
Read-only backend client shared by every MCP (assistant) server — CAPA-008.

The MCP servers let an AI assistant (Claude Desktop / Claude Code) call the backend on behalf
of the clinician who runs it. CAPA-008 found that the assistant could write clinical records
(CVS/PRL readings feeding the McDonald summary, region classifications, PACS imports) and that
each server had its own unrestricted HTTP client. This module is now the ONLY way a server
reaches the backend:

- GET requests are allowed (reads).
- POST is allowed only for the routes in ``COMPUTE_ONLY_POST_PATHS``: they compute a result
  and return it without storing or changing any record. Any other path raises
  ``AssistantWriteRefused`` before a request is sent.

Credential: ``API_SERVICE_TOKEN`` must be the access token of the clinician operating the
assistant — never a shared, service or administrator account. The backend applies that
user's own object-level authorization (RC-029) on every route the assistant can reach, so the
assistant sees no more than that clinician may see. STDIO transport only (see run_all.py): an
HTTP transport would expose that token to any local process or web page able to reach the port.

@module mcp._backend
"""

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Optional

from app.agent_platform.capability import (ASSISTANT_CLIENT, CAPABILITY_HEADER, CLIENT_HEADER, ScopeRefused,
                                           ScopeRequired, current_capability)

# Routes that only compute and return, AND either authorize every object they reference
# (RC-029) or reference none. Each was checked to store nothing (CAPA-008 §2):
# - compare / longitudinal compare: authorize_mask_specs, return metrics, store nothing;
# - /ai/report/generate: authorizes the segmentation it drafts for (CAPA-014, RC-065; RC-029), returns
#   text, keeps no copy; it reads (never writes) that segmentation to re-derive the DIS state and the
#   lesion table on the server (PRB-003, RC-070).
# Deliberately NOT listed: /ai/segment/*, /ai/anomaly/detect and /ai/volumetry/* take a
# file or segmentation id WITHOUT object-level authorization (CAPA-008 finding 8, CAPA-007
# PA-7.2), and volumetry rests on unsourced normative data (CAPA-005).
COMPUTE_ONLY_POST_PATHS = frozenset({
    "/segmentation/compare",
    "/segmentation/longitudinal/compare",
    "/ai/report/generate",
})


# Sixth review of PR #79 (S2): routes that call a PAID model. Never reached by an agent: the call would bypass the
# agent's cost ledger (RC-112; the assistant's caps are 0.0 USD). Refused here AND by the backend's agent guard.
PAID_MODEL_POST_PATHS = frozenset({"/ai/report/generate"})

# Sixth review (C3): the ONE list of the assistant's read routes (paths under /api/v1). The backend's agent guard
# (app/security/agent_scope.py AGENT_ROUTES) is built from these and COMPUTE_ONLY_POST_PATHS minus the paid ones.
AGENT_GET_ROUTES = (
    r"/segmentation/[^/]+",                                       # a segmentation record, and /segmentation/list
    r"/segmentation/[^/]+/(?:dis-assessment|lesion-analysis)",
    r"/imaging/(?:metadata|process)/.+",
    r"/imaging/(?:slice|matplotlib-2d)/.+/[0-9]+",
)
AGENT_SCOPE_PATH = "/agent-scope"          # issues the study session's pass (backend: issue_for_studies)
ASSISTANT_AGENT = "ms-clinical-assistant"
SESSION_MAX_SECONDS = 3600

# Sixth review (S1): this process's study session — the pass the backend issued for the studies the physician
# opened. Kept in memory only, never returned to the model, never written to disk; it expires with the pass.
_SESSION: dict = {}


class AssistantWriteRefused(PermissionError):
    """The assistant tried to call a backend route that is not on the compute-only list."""


# Direct identifiers removed from every response before the assistant sees it: whatever the
# assistant reads is sent to its model provider (CAPA-008 finding 7). Keys are compared
# case-insensitively and without underscores, so "patient_name" and DICOM "PatientName" match.
# Free text (descriptions, notes) is NOT scrubbed: it must not contain identifiers.
IDENTIFIER_KEYS = frozenset({
    "patientid", "patientname", "patientbirthdate", "patientaddress", "otherpatientids",
    "institutionname", "institutionaddress", "accessionnumber", "referringphysicianname",
    "studydate", "seriesdate", "acquisitiondate", "contentdate", "extrafields",
})


def drop_direct_identifiers(value):
    """Return a copy of a JSON-like value without the IDENTIFIER_KEYS fields, at any depth."""
    if isinstance(value, dict):
        return {k: drop_direct_identifiers(v) for k, v in value.items()
                if str(k).replace("_", "").lower() not in IDENTIFIER_KEYS}
    if isinstance(value, list):
        return [drop_direct_identifiers(v) for v in value]
    return value


# CAPA-013 (RC-060, HAZ-007): the assistant never receives an activity or dissemination-in-time
# flag computed from unconfirmed longitudinal candidates (the backend no longer sends them; this
# also covers an older backend). A radiologist's confirmation travels as
# `reader_confirmed_activity`, which is kept.
UNCONFIRMED_ACTIVITY_KEYS = frozenset({
    "activity_candidate", "dit_candidate", "new_clinically_significant_count", "enlarging_count",
})


def drop_unconfirmed_activity_flags(value):
    """Return a copy of a JSON-like value without the UNCONFIRMED_ACTIVITY_KEYS fields, at any depth."""
    if isinstance(value, dict):
        return {k: drop_unconfirmed_activity_flags(v) for k, v in value.items()
                if k not in UNCONFIRMED_ACTIVITY_KEYS}
    if isinstance(value, list):
        return [drop_unconfirmed_activity_flags(v) for v in value]
    return value


def assistant_view(value):
    """What any AI assistant or agent may receive from the backend: the value without direct identifiers
    (CAPA-008) and without activity flags computed from unconfirmed candidates (CAPA-013, RC-060). The ONE
    rule shared by this MCP client and the agent platform (app/agent_platform/untrusted.py; second review of
    PR #79, finding 1). Sixth review, E3: one pass, one copy."""
    return _view(value)


def _view(value):
    if isinstance(value, dict):
        return {k: _view(v) for k, v in value.items()
                if str(k).replace("_", "").lower() not in IDENTIFIER_KEYS and k not in UNCONFIRMED_ACTIVITY_KEYS}
    if isinstance(value, list):
        return [_view(v) for v in value]
    return value


def _api_base() -> str:
    return os.environ.get("API_BASE_URL", "http://localhost:8000")


def _headers(capability: Optional[str] = None) -> dict:
    token = os.environ.get("API_SERVICE_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    headers[CLIENT_HEADER] = ASSISTANT_CLIENT              # always: the backend refuses an unscoped assistant request
    if capability:                                         # RC-121: the run's / the session's pass
        headers[CAPABILITY_HEADER] = capability
    return headers


def get_route_allowed(path: str) -> bool:
    return any(re.fullmatch(rx, path) for rx in AGENT_GET_ROUTES)


def _requires_scope() -> bool:
    """The registry says whether the assistant needs a study scope; an unreadable registry means yes (fail closed)."""
    try:
        from app.agent_platform.registry import DEFAULT_REGISTRY_PATH
        data = json.loads(Path(DEFAULT_REGISTRY_PATH).read_text(encoding="utf-8"))
        return data["agents"][ASSISTANT_AGENT].get("requires_backend_scope") is not False
    except Exception:  # noqa: BLE001
        return True


def _active_pass() -> Optional[str]:
    """The platform run's capability, else this process's study session while it lasts."""
    capability = current_capability()
    if capability:
        return capability
    token = _SESSION.get("token")
    if token and time.monotonic() < _SESSION.get("expires_at", 0):
        return token
    return None


def _prepare(method: str, path: str) -> dict:
    """Sixth review of PR #79 (S1, S2, C3): refuse locally — before anything is sent — a paid model route, a route
    that is not one of the assistant's, and any request without a study session when the registry requires one."""
    if method == "POST":
        if path in PAID_MODEL_POST_PATHS:
            raise ScopeRefused(f"POST {path} calls a paid model; an agent never calls it (RC-112)")
        check_compute_only(path)
    elif not get_route_allowed(path):
        raise ScopeRefused(f"GET {path} is not one of the assistant's routes")
    capability = _active_pass()
    if capability is None and _requires_scope():
        raise ScopeRequired("No study session is open: call open_study_session (or open_imaging_session) with the "
                            "study the physician is reviewing first.")
    return _headers(capability)


def _result(response):
    """A refusal by the backend (403, or the 404 it gives for an object outside the scope or not visible) is a
    ScopeRefused — a denial, never the tool's failure (C1). Sixth review E3: inside a platform run the runtime
    applies ``assistant_view`` once (validate_tool_result); elsewhere it is applied here."""
    status_code = getattr(response, "status_code", 200)
    if status_code in (403, 404):
        raise ScopeRefused(f"refused or not found by the backend ({status_code})", status=status_code)
    response.raise_for_status()
    data = response.json()
    return data if current_capability() else assistant_view(data)


async def open_session(study_ids) -> dict:
    """Open this process's study session (S1): the backend authorizes each study for the clinician (CAPA-009) and
    issues a pass for ONE patient and these studies (at most 1 h). The pass is kept here; only its status is
    returned, so it never reaches the model."""
    if not isinstance(study_ids, list) or not 0 < len(study_ids) <= 20 \
            or not all(isinstance(s, str) and s for s in study_ids):
        raise ValueError("study_ids: a list of 1 to 20 study ids")
    async with _client(30.0) as client:
        response = await client.post(f"{_api_base()}/api/v1{AGENT_SCOPE_PATH}",
                                     json={"study_ids": study_ids, "run_id": f"mcp-{uuid.uuid4().hex}"},
                                     headers=_headers(None))
    if response.status_code in (403, 404):
        raise ScopeRefused(f"the study session was refused ({response.status_code})", status=response.status_code)
    response.raise_for_status()
    data = response.json()
    ttl = max(0, min(int(data.get("expires_in", 0)), SESSION_MAX_SECONDS))
    _SESSION.clear()
    _SESSION.update(token=str(data["token"]), expires_at=time.monotonic() + max(0, ttl - 5))
    return {"session": "open", "studies": len(set(study_ids)), "expires_in_seconds": ttl,
            "note": "Only these studies of one patient can be read until the session ends."}


# Tests only: an in-process transport (httpx.ASGITransport) instead of the network.
_TRANSPORT = None


def _client(timeout: float):
    import httpx
    kwargs = {"timeout": timeout}
    if _TRANSPORT is not None:
        kwargs["transport"] = _TRANSPORT
    return httpx.AsyncClient(**kwargs)


def check_compute_only(path: str) -> None:
    """Refuse any POST path that is not on the compute-only list (no request is sent)."""
    if path not in COMPUTE_ONLY_POST_PATHS:
        raise AssistantWriteRefused(
            f"The assistant is read-only: POST {path} is not a compute-only route (CAPA-008)."
        )


async def api_get(path: str, params: Optional[dict] = None, timeout: float = 60.0) -> dict:
    """Authenticated GET as the operating clinician, inside the study session; direct identifiers are removed."""
    headers = _prepare("GET", path)
    async with _client(timeout) as client:
        response = await client.get(f"{_api_base()}/api/v1{path}", params=params, headers=headers)
    return _result(response)


async def api_post_compute(path: str, json_data: Optional[dict] = None, timeout: float = 120.0) -> dict:
    """Authenticated POST to a compute-only route; any other route is refused before sending."""
    headers = _prepare("POST", path)
    async with _client(timeout) as client:
        response = await client.post(f"{_api_base()}/api/v1{path}", json=json_data, headers=headers)
    return _result(response)
