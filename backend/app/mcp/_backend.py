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

import os
import posixpath
import re
import time
import uuid
from typing import Optional

from app.agent_platform.capability import (ASSISTANT_CLIENT, CAPABILITY_HEADER, CLIENT_HEADER, ScopeRefused,
                                           ScopeRequired, ToolNotAllowed, current_capability)

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
})


# Sixth review (C3): the ONE list of the assistant's read routes (paths under /api/v1). The backend's agent guard
# (app/security/agent_scope.py AGENT_ROUTES) is built from these and COMPUTE_ONLY_POST_PATHS minus the paid ones.
# Seventh review (R6): every path parameter has a STRICT shape — a segmentation id, or a storage path of the RC-027
# grammar — so nothing like "../" or an encoded slash can ride in it; and the path must already be normalised.
_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_SEGMENTATION_ID = r"[A-Za-z0-9_-]{1,128}"
_FILE_ID = rf"patients/{_UUID}/studies/{_UUID}/series/{_UUID}/[A-Za-z0-9][A-Za-z0-9._-]{{0,254}}"   # = RC-027
AGENT_GET_ROUTES = (
    rf"/segmentation/{_SEGMENTATION_ID}",                          # a segmentation record, and /segmentation/list
    rf"/segmentation/{_SEGMENTATION_ID}/(?:dis-assessment|lesion-analysis)",
    rf"/imaging/(?:metadata|process)/{_FILE_ID}",
    rf"/imaging/(?:slice|matplotlib-2d)/{_FILE_ID}/[0-9]+",
)
AGENT_SCOPE_PATH = "/agent-scope"          # issues the study session's pass (backend: issue_for_studies)
SESSION_MAX_SECONDS = 3600

# Sixth review (S1): this process's study session — the pass the backend issued for the studies the physician
# opened. Kept in memory only, never returned to the model, never written to disk; it expires with the pass.
_SESSION: dict = {}


class AssistantWriteRefused(ToolNotAllowed):
    """The assistant tried to call a backend route that is not on the compute-only list. Seventh review (R7): a
    REFUSAL, audited as a denial (tool not allowed), never as the tool's failure."""


# Direct identifiers removed from every response before the assistant sees it (by assistant_view, the ONE
# implementation): whatever the
# assistant reads is sent to its model provider (CAPA-008 finding 7). Keys are compared
# case-insensitively and without underscores, so "patient_name" and DICOM "PatientName" match.
# Free text (descriptions, notes) is NOT scrubbed: it must not contain identifiers.
IDENTIFIER_KEYS = frozenset({
    "patientid", "patientname", "patientbirthdate", "patientaddress", "otherpatientids",
    "institutionname", "institutionaddress", "accessionnumber", "referringphysicianname",
    "studydate", "seriesdate", "acquisitiondate", "contentdate", "extrafields",
})


# CAPA-013 (RC-060, HAZ-007): the assistant never receives an activity or dissemination-in-time
# flag computed from unconfirmed longitudinal candidates (the backend no longer sends them; this
# also covers an older backend). A radiologist's confirmation travels as
# `reader_confirmed_activity`, which is kept.
UNCONFIRMED_ACTIVITY_KEYS = frozenset({
    "activity_candidate", "dit_candidate", "new_clinically_significant_count", "enlarging_count",
})


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


def path_is_clean(path: str) -> bool:
    """Seventh review (R6): no dot segment, encoded character, backslash or empty segment, and already normalised."""
    return (isinstance(path, str) and path.startswith("/") and "%" not in path and "\\" not in path
            and not any(seg in ("..", ".", "") for seg in path[1:].split("/"))      # F10: ".." as a SEGMENT only
            and posixpath.normpath(path) == path)


def get_route_allowed(path: str) -> bool:
    return path_is_clean(path) and any(re.fullmatch(rx, path) for rx in AGENT_GET_ROUTES)


def _require_pass(capability: Optional[str]) -> None:
    """Seventh review (R5): the assistant ALWAYS needs a pass — there is no mode without one (the backend never
    serves an assistant request without a scope either)."""
    if capability is None:
        raise ScopeRequired("No study session is open: call open_study_session (or open_imaging_session); the "
                            "physician chooses and confirms the study in the client.")


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
    if not path_is_clean(path):
        raise ScopeRefused("the request path is not clean (dot segment, encoded character or backslash)")
    if method == "POST":
        check_compute_only(path)            # a paid-model route is not compute-only (eighth review, F8)
    elif not get_route_allowed(path):
        raise ToolNotAllowed(f"GET {path} is not one of the assistant's routes")      # F5
    capability = _active_pass()
    _require_pass(capability)
    return _headers(capability)


def _result(response):
    """A refusal by the backend (403, or the 404 it gives for an object outside the scope or not visible) is a
    ScopeRefused — a denial, never the tool's failure (C1). Seventh review (R3, R4): the shared rule is applied HERE,
    at the source, ALWAYS — inside a platform run too; the platform then only checks the viewed result."""
    status_code = getattr(response, "status_code", 200)
    if status_code in (403, 404):
        raise ScopeRefused(f"refused or not found by the backend ({status_code})", status=status_code)
    response.raise_for_status()
    data = response.json()
    return assistant_view(data)


NO_ELICITATION = ("This client cannot ask the physician to choose and confirm the study (MCP elicitation); no "
                  "study session is opened. Use a client that supports elicitation.")
ASK_STUDY = ("MSTool assistant — which study are you reviewing? Paste the study id from the MSTool web app (for a "
             "two-timepoint comparison, the current and the prior study of the SAME patient, separated by a comma).")


async def _scope_request(body: dict) -> dict:
    async with _client(30.0) as client:
        response = await client.post(f"{_api_base()}/api/v1{AGENT_SCOPE_PATH}", json=body, headers=_headers(None))
    status_code = getattr(response, "status_code", 200)
    if status_code in (403, 404):
        raise ScopeRefused(f"the study session was refused ({status_code})", status=status_code)
    if status_code in (400, 422):                                             # eighth review, F4
        raise ScopeRequired(f"No session was opened: the backend refused the request ({status_code}); check the "
                            f"study id in the MSTool web app.")
    response.raise_for_status()
    return response.json()


def _confirmation_text(preview: dict, session_minutes: int, confirm_minutes: int) -> str:
    """Written by the SERVER from the backend's answer, never by the model (seventh review, R1)."""
    studies = "; ".join(f"study {s.get('study_ref', '?')} of {s.get('date') or 'unknown date'}"
                        f" ({s['series'] if s.get('series') is not None else 'unknown number of'} series)"
                        for s in preview.get("studies", []))
    return (f"Open the MSTool assistant for patient {preview.get('patient_ref', '?')} — {studies}? Confirm within "
            f"{confirm_minutes} minutes. The session then lasts {session_minutes} minutes, and the assistant reads only "
            f"{'this study' if len(preview.get('studies', [])) == 1 else 'these studies'} of this patient. Confirm "
            f"only if this is the patient you are reviewing.")


async def open_session(ctx) -> dict:
    """Seventh review of PR #79 (R1): the HUMAN chooses the scope. The server asks the physician through the client
    (MCP elicitation) which study to open, has the backend authorize it (CAPA-009) and describe it, and asks the
    physician to confirm a text written by the server (patient reference, study date, series). Only then is the pass
    issued and kept in this process (≤ 1 h, never returned to the model). The model supplies nothing and sees only
    the session's status. A client without elicitation, a decline or a cancel opens nothing (fail closed); any new
    request first closes the current session, so a patient switch always needs a fresh confirmation (and the backend
    audits it)."""
    _SESSION.clear()
    elicit = getattr(ctx, "elicit", None)
    if elicit is None:
        raise ScopeRequired(NO_ELICITATION)
    try:
        entry = await elicit(ASK_STUDY, response_type=str)
    except Exception:  # noqa: BLE001 — a client that does not implement elicitation
        raise ScopeRequired(NO_ELICITATION)
    data = getattr(entry, "data", None)
    if getattr(entry, "action", None) != "accept" or not isinstance(data, str):
        raise ScopeRequired("The physician chose no study: no study session.")
    ids = [x.strip() for x in data.replace(";", ",").split(",") if x.strip()]
    if not ids:
        raise ScopeRequired("The physician chose no study: no study session.")
    if len(ids) > 20:                                                         # eighth review, F4: never truncated
        raise ScopeRequired(f"No session was opened: at most 20 studies ({len(ids)} were given).")
    run_id = f"mcp-{uuid.uuid4().hex}"
    preview = await _scope_request({"study_ids": ids, "run_id": run_id, "preview": True})
    session_minutes = max(1, int(preview.get("session_seconds", 900)) // 60)              # round 9 (T2)
    confirm_minutes = max(1, int(preview.get("confirm_within_seconds", 300)) // 60)
    try:
        answer = await elicit(_confirmation_text(preview, session_minutes, confirm_minutes), response_type=None)
    except Exception:  # noqa: BLE001
        raise ScopeRequired(NO_ELICITATION)
    if getattr(answer, "action", None) != "accept":
        raise ScopeRequired("The physician did not confirm the study: no study session.")
    issued = await _scope_request({"pending": preview["pending"], "run_id": run_id})    # F6: no second authorization
    ttl = max(0, min(int(issued.get("expires_in", 0)), SESSION_MAX_SECONDS))
    _SESSION.update(token=str(issued["token"]), expires_at=time.monotonic() + max(0, ttl - 5),
                    patient_ref=preview.get("patient_ref"))
    return {"session": "open", "studies": len(preview.get("studies", [])), "expires_in_seconds": ttl,
            "note": "The physician confirmed the study; only it can be read until the session ends."}


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
