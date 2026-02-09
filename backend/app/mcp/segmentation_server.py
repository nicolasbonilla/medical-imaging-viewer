"""
Brain Segmentation MCP Server.

Provides tools for Claude Desktop / Claude Code to interact with
AI-powered brain segmentation:
- Automatic brain structure segmentation (SynthSeg)
- Interactive click-based segmentation
- Brain volumetry (per-structure volumes)
- Longitudinal volume comparison
- Anomaly detection

@module mcp.segmentation_server
"""

from fastmcp import FastMCP
from typing import Optional, List

mcp = FastMCP(
    "brain-segmentation-mcp",
    description="MCP server for AI brain segmentation — auto segment, volumetry, anomaly detection",
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
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.get(url, params=params, headers=_get_headers())
        response.raise_for_status()
        return response.json()


async def _api_post(path: str, json_data: Optional[dict] = None) -> dict:
    """Make an authenticated POST request to the backend."""
    import httpx
    url = f"{_get_api_base()}/api/v1{path}"
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url, json=json_data, headers=_get_headers())
        response.raise_for_status()
        return response.json()


# =============================================================================
# Tools — AI Segmentation
# =============================================================================

@mcp.tool()
async def segment_brain_auto(file_id: str, model: str = "synthseg") -> dict:
    """
    Automatically segment brain structures from an MRI scan.

    Uses SynthSeg to identify 30+ brain structures including hippocampus,
    ventricles, cortex, thalamus, caudate, putamen, brain stem, etc.

    The result is a labeled 3D mask compatible with the viewer's
    segmentation overlay system.

    Args:
        file_id: The GCS file path of the brain MRI
        model: AI model to use ('synthseg' for brain structures)
    """
    return await _api_post("/ai/segment/auto", {
        "file_id": file_id,
        "model": model,
    })


@mcp.tool()
async def segment_interactive(
    file_id: str,
    click_points: list,
    model: str = "sam_med3d",
) -> dict:
    """
    Run interactive segmentation from click points.

    The user provides positive (include) and negative (exclude) click points,
    and the AI generates a 3D segmentation mask.

    Args:
        file_id: The GCS file path of the brain MRI
        click_points: List of dicts with keys: x, y, z, label ('positive'/'negative')
        model: AI model ('sam_med3d' or 'nninteractive')
    """
    return await _api_post("/ai/segment/interactive", {
        "file_id": file_id,
        "click_points": click_points,
        "model": model,
    })


@mcp.tool()
async def get_task_status(task_id: str) -> dict:
    """
    Check the status of an async AI segmentation task.

    Returns task status (pending, processing, completed, failed),
    progress percentage, and result when complete.

    Args:
        task_id: The task ID returned by segment_brain_auto or segment_interactive
    """
    return await _api_get(f"/ai/segment/{task_id}/status")


@mcp.tool()
async def detect_anomalies(
    file_id: str,
    sensitivity: str = "medium",
) -> dict:
    """
    Detect brain anomalies (tumors, lesions, hemorrhages, infarcts, atrophy).

    Returns a list of detected anomalies with type, location, confidence,
    and volume. Also generates a probability heatmap stored as a
    fractional segmentation overlay.

    Args:
        file_id: The GCS file path of the brain MRI
        sensitivity: Detection sensitivity — 'low', 'medium', or 'high'
    """
    return await _api_post("/ai/anomaly/detect", {
        "file_id": file_id,
        "sensitivity": sensitivity,
    })


# =============================================================================
# Tools — Volumetry
# =============================================================================

@mcp.tool()
async def compute_brain_volumes(
    segmentation_id: str,
    voxel_spacing: list = [1.0, 1.0, 1.0],
    patient_age: Optional[int] = None,
    patient_sex: Optional[str] = None,
) -> dict:
    """
    Compute per-structure brain volumes from a segmentation mask.

    Returns volume in mm3 and mL for each brain structure,
    with normative percentile comparison when patient demographics
    are provided. Flags abnormal structures (atrophy or enlargement).

    Runs on CPU — no GPU required.

    Args:
        segmentation_id: ID of the segmentation to measure
        voxel_spacing: Voxel dimensions in mm [z, y, x] (default [1,1,1])
        patient_age: Patient age in years (enables normative comparison)
        patient_sex: Patient sex ('M' or 'F', enables normative comparison)
    """
    return await _api_post("/ai/volumetry/compute", {
        "segmentation_id": segmentation_id,
        "voxel_spacing": voxel_spacing,
        "patient_age": patient_age,
        "patient_sex": patient_sex,
    })


@mcp.tool()
async def compare_brain_volumes(
    patient_id: str,
    timepoints: list,
) -> dict:
    """
    Compare brain volumes across multiple timepoints for longitudinal tracking.

    Detects atrophy progression, treatment response, or disease monitoring.
    Each timepoint must include study_id, date, and per-structure volumes.

    Args:
        patient_id: The patient ID
        timepoints: List of dicts with keys: study_id, date, structures
                    (structures = list of {label_id, volume_ml})
    """
    return await _api_post("/ai/volumetry/compare", {
        "patient_id": patient_id,
        "timepoints": timepoints,
    })


@mcp.tool()
async def list_ai_models() -> list:
    """
    List available AI models and their configuration status.

    Returns model names, types, and whether they are properly
    configured on the server (Vertex AI endpoints).
    """
    return await _api_get("/ai/models")


@mcp.tool()
async def get_brain_structure_labels() -> dict:
    """
    Get the complete mapping of SynthSeg brain structure labels.

    Returns label IDs, structure names, and colors for all 33
    FreeSurfer brain structures used in automatic segmentation.
    """
    return await _api_get("/ai/labels/synthseg")


# =============================================================================
# Prompts — Workflow Templates
# =============================================================================

@mcp.prompt()
async def brain_tumor_analysis(file_id: str) -> str:
    """
    Complete workflow for brain tumor analysis.

    Guides through: auto-segmentation → anomaly detection → volumetry → report.
    """
    return f"""Analyze this brain MRI for tumor evaluation.

Steps:
1. First, get the image metadata: get_image_metadata(file_id="{file_id}")
2. Run automatic brain segmentation: segment_brain_auto(file_id="{file_id}")
3. Run anomaly detection: detect_anomalies(file_id="{file_id}", sensitivity="high")
4. If segmentation succeeds, compute brain volumes with patient demographics
5. Generate a tumor-focused report with the findings

Focus on:
- Tumor location, size, and enhancement pattern
- Mass effect and midline shift
- Edema extent
- RANO criteria if follow-up study
"""


@mcp.prompt()
async def dementia_assessment(file_id: str, patient_age: int = 70) -> str:
    """
    Complete workflow for dementia/Alzheimer's assessment.

    Guides through: segmentation → volumetry with normative comparison → report.
    """
    return f"""Assess this brain MRI for cognitive decline / dementia.

Steps:
1. Get image metadata: get_image_metadata(file_id="{file_id}")
2. Run brain structure segmentation: segment_brain_auto(file_id="{file_id}")
3. Compute volumetry with age: compute_brain_volumes(segmentation_id=<from step 2>, patient_age={patient_age})
4. Generate a dementia assessment report

Focus on:
- Hippocampal volumes (bilateral comparison)
- Ventricular enlargement (especially temporal horns)
- Cortical atrophy pattern (GCA score)
- White matter hyperintensities (Fazekas score)
- Pattern analysis: Alzheimer's vs vascular vs frontotemporal vs Lewy body
"""


@mcp.prompt()
async def stroke_evaluation(file_id: str) -> str:
    """
    Complete workflow for acute stroke evaluation.

    Guides through: anomaly detection → segmentation → report.
    """
    return f"""Evaluate this brain MRI for acute stroke.

Steps:
1. Get image metadata: get_image_metadata(file_id="{file_id}")
2. Run anomaly detection with high sensitivity: detect_anomalies(file_id="{file_id}", sensitivity="high")
3. Run brain segmentation: segment_brain_auto(file_id="{file_id}")
4. Generate a stroke protocol report

Focus on:
- DWI restriction pattern and location
- Vascular territory (ACA, MCA, PCA, vertebrobasilar)
- ASPECTS score if MCA territory
- Hemorrhagic transformation
- Mass effect
"""
