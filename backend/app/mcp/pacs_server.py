"""
PACS Connectivity MCP Server.

Provides tools for Claude Desktop / Claude Code to query and retrieve
DICOM studies from PACS via DICOM C-FIND/C-MOVE or dicom-mcp bridge.

References:
    - dicom-mcp: https://github.com/ChristianHinge/dicom-mcp

@module mcp.pacs_server
"""

from fastmcp import FastMCP
from typing import Optional

mcp = FastMCP(
    "pacs-connectivity-mcp",
    description=(
        "MCP server for PACS connectivity — query patients, retrieve DICOM studies, "
        "and import series into the medical imaging viewer."
    ),
)


def _get_api_base() -> str:
    """Get the backend API base URL."""
    import os
    return os.environ.get("API_BASE_URL", "http://localhost:8000")


def _get_headers() -> dict:
    """Get auth headers for internal API calls."""
    import os
    token = os.environ.get("API_SERVICE_TOKEN", "")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


async def _api_get(path: str, params: Optional[dict] = None) -> dict:
    """Make an authenticated GET request to the backend."""
    import httpx
    url = f"{_get_api_base()}/api/v1{path}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, params=params, headers=_get_headers())
        response.raise_for_status()
        return response.json()


async def _api_post(path: str, json_data: Optional[dict] = None) -> dict:
    """Make an authenticated POST request to the backend."""
    import httpx
    url = f"{_get_api_base()}/api/v1{path}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=json_data, headers=_get_headers())
        response.raise_for_status()
        return response.json()


# =============================================================================
# Tools
# =============================================================================


@mcp.tool()
async def query_patients(
    name: str = "",
    mrn: str = "",
) -> dict:
    """
    Search for patients in PACS by name or MRN (Medical Record Number).

    Args:
        name: Patient name (partial match, case-insensitive)
        mrn: Medical Record Number (exact match)

    Returns:
        List of matching patients with demographics
    """
    params = {}
    if name:
        params["name"] = name
    if mrn:
        params["mrn"] = mrn

    try:
        return await _api_get("/pacs/patients", params=params)
    except Exception as e:
        return {
            "error": str(e),
            "note": (
                "PACS connectivity requires PACS_HOST, PACS_PORT, and "
                "PACS_AE_TITLE to be configured in the backend."
            ),
        }


@mcp.tool()
async def query_studies(
    patient_id: str,
    modality: str = "MR",
    date_range: str = "",
) -> dict:
    """
    List imaging studies for a patient from PACS.

    Args:
        patient_id: Patient ID from PACS
        modality: DICOM modality filter (default: MR for brain MRI)
        date_range: Optional date range (e.g., '20240101-20241231')

    Returns:
        List of studies with UIDs, dates, descriptions
    """
    params = {"patient_id": patient_id, "modality": modality}
    if date_range:
        params["date_range"] = date_range

    try:
        return await _api_get("/pacs/studies", params=params)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def query_series(
    study_uid: str,
) -> dict:
    """
    List all series within a DICOM study.

    Args:
        study_uid: DICOM Study Instance UID

    Returns:
        List of series with UIDs, descriptions, modality, number of instances
    """
    try:
        return await _api_get(f"/pacs/studies/{study_uid}/series")
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def retrieve_series(
    study_uid: str,
    series_uid: str,
) -> dict:
    """
    Retrieve a DICOM series from PACS to local storage via C-MOVE.

    This operation may take time depending on the series size and network.

    Args:
        study_uid: DICOM Study Instance UID
        series_uid: DICOM Series Instance UID

    Returns:
        Local path to retrieved DICOM files and metadata
    """
    try:
        return await _api_post("/pacs/retrieve", json_data={
            "study_uid": study_uid,
            "series_uid": series_uid,
        })
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def import_dicom_to_viewer(
    series_path: str,
    patient_id: Optional[str] = None,
) -> dict:
    """
    Convert retrieved DICOM series to NIfTI and import into the viewer.

    Takes a local directory of DICOM files, converts to NIfTI using dcm2niix,
    and uploads to the viewer's storage backend.

    Args:
        series_path: Local path to the DICOM series directory
        patient_id: Optional patient ID to associate with the import

    Returns:
        File ID and metadata for the imported NIfTI file
    """
    try:
        return await _api_post("/pacs/import", json_data={
            "series_path": series_path,
            "patient_id": patient_id,
        })
    except Exception as e:
        return {"error": str(e)}
