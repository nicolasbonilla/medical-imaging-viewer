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
from typing import Optional

# Routes that only compute and return, AND either authorize every object they reference
# (RC-029) or reference none. Each was checked to store nothing (CAPA-008 §2):
# - compare / longitudinal compare: authorize_mask_specs, return metrics, store nothing;
# - /ai/report/generate: references no stored object, returns text, keeps no copy.
# Deliberately NOT listed: /ai/segment/*, /ai/anomaly/detect and /ai/volumetry/* take a
# file or segmentation id WITHOUT object-level authorization (CAPA-008 finding 8, CAPA-007
# PA-7.2), and volumetry rests on unsourced normative data (CAPA-005).
COMPUTE_ONLY_POST_PATHS = frozenset({
    "/segmentation/compare",
    "/segmentation/longitudinal/compare",
    "/ai/report/generate",
})


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


def _api_base() -> str:
    return os.environ.get("API_BASE_URL", "http://localhost:8000")


def _headers() -> dict:
    token = os.environ.get("API_SERVICE_TOKEN", "")
    return {"Authorization": f"Bearer {token}"} if token else {}


def check_compute_only(path: str) -> None:
    """Refuse any POST path that is not on the compute-only list (no request is sent)."""
    if path not in COMPUTE_ONLY_POST_PATHS:
        raise AssistantWriteRefused(
            f"The assistant is read-only: POST {path} is not a compute-only route (CAPA-008)."
        )


async def api_get(path: str, params: Optional[dict] = None, timeout: float = 60.0) -> dict:
    """Authenticated GET as the operating clinician; direct identifiers are removed."""
    import httpx
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(f"{_api_base()}/api/v1{path}", params=params, headers=_headers())
        response.raise_for_status()
        return drop_direct_identifiers(response.json())


async def api_post_compute(path: str, json_data: Optional[dict] = None, timeout: float = 120.0) -> dict:
    """Authenticated POST to a compute-only route; any other route is refused before sending."""
    check_compute_only(path)
    import httpx
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(f"{_api_base()}/api/v1{path}", json=json_data, headers=_headers())
        response.raise_for_status()
        return drop_direct_identifiers(response.json())
