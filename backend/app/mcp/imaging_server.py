"""
Brain Imaging MCP Server.

Provides tools for Claude Desktop / Claude Code to interact with
the medical imaging viewer backend:
- Search brain studies by patient or date
- Get study and image metadata
- Get slice images as base64
- Patient imaging history

@module mcp.imaging_server
"""

from fastmcp import FastMCP
from typing import Optional

mcp = FastMCP(
    "brain-imaging-mcp",
    description="MCP server for brain MRI imaging — search studies, view slices, get metadata",
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
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=json_data, headers=_get_headers())
        response.raise_for_status()
        return response.json()


# =============================================================================
# Tools
# =============================================================================

@mcp.tool()
async def get_image_metadata(file_id: str) -> dict:
    """
    Get detailed metadata for a brain MRI image.

    Returns DICOM/NIfTI metadata including patient info, study date,
    modality, dimensions, pixel spacing, and slice count.

    Args:
        file_id: The GCS file path or ID of the image
    """
    return await _api_get(f"/imaging/metadata/{file_id}")


@mcp.tool()
async def get_slice_image(
    file_id: str,
    slice_index: int,
    window_center: Optional[float] = None,
    window_width: Optional[float] = None,
    direction: str = "axial",
) -> dict:
    """
    Get a single slice from a brain MRI as a base64-encoded PNG image.

    Args:
        file_id: The GCS file path or ID of the image
        slice_index: Zero-based slice index
        window_center: Optional window center for contrast adjustment
        window_width: Optional window width for contrast adjustment
        direction: Slice direction — 'axial', 'sagittal', or 'coronal'
    """
    params = {"direction": direction}
    if window_center is not None:
        params["window_center"] = str(window_center)
    if window_width is not None:
        params["window_width"] = str(window_width)
    return await _api_get(f"/imaging/slice/{file_id}/{slice_index}", params=params)


@mcp.tool()
async def process_image(
    file_id: str,
    max_slices: int = 10,
) -> dict:
    """
    Process a brain MRI file and return metadata with a sample of slices.

    Use this to get an overview of an image file. Returns metadata
    plus the first N slices as base64-encoded PNGs.

    Args:
        file_id: The GCS file path or ID of the image
        max_slices: Maximum number of slices to return (default 10)
    """
    return await _api_get(
        f"/imaging/process/{file_id}",
        params={"max_slices": str(max_slices)},
    )


@mcp.tool()
async def list_segmentations(file_id: str) -> list:
    """
    List all segmentations available for a brain MRI image.

    Returns segmentation IDs, descriptions, labels, and timestamps.

    Args:
        file_id: The GCS file path or ID of the image
    """
    return await _api_get("/segmentation/list", params={"file_id": file_id})


@mcp.tool()
async def get_matplotlib_visualization(
    file_id: str,
    slice_index: int,
    colormap: str = "gray",
    window_center: Optional[float] = None,
    window_width: Optional[float] = None,
) -> dict:
    """
    Get a matplotlib-rendered visualization of a brain MRI slice.

    Returns a publication-quality image with axes and colorbar.

    Args:
        file_id: The GCS file path or ID of the image
        slice_index: Zero-based slice index
        colormap: Matplotlib colormap name (gray, viridis, hot, etc.)
        window_center: Optional window center for contrast
        window_width: Optional window width for contrast
    """
    params = {"colormap": colormap}
    if window_center is not None:
        params["window_center"] = str(window_center)
    if window_width is not None:
        params["window_width"] = str(window_width)
    return await _api_get(
        f"/imaging/matplotlib-2d/{file_id}/{slice_index}",
        params=params,
    )


# =============================================================================
# Resources
# =============================================================================

@mcp.resource("brain-atlas://structures")
async def get_brain_atlas() -> str:
    """
    Atlas of brain structures with FreeSurfer/SynthSeg label IDs,
    names, and typical colors for overlay rendering.
    """
    result = await _api_get("/ai/labels/synthseg")
    labels = result.get("labels", [])
    lines = ["# Brain Structure Atlas (SynthSeg/FreeSurfer)", ""]
    lines.append(f"Total structures: {result.get('count', len(labels))}")
    lines.append("")
    lines.append("| ID | Structure | Color |")
    lines.append("|---|---|---|")
    for label in labels:
        lines.append(f"| {label['id']} | {label['name']} | {label['color']} |")
    return "\n".join(lines)


@mcp.resource("imaging://supported-formats")
async def get_supported_formats() -> str:
    """Supported medical imaging file formats and their capabilities."""
    return """# Supported Medical Imaging Formats

## NIfTI (.nii, .nii.gz)
- 3D volumetric brain MRI data
- Full segmentation support
- AI segmentation compatible
- Multi-orientation viewing (axial, sagittal, coronal)

## DICOM (.dcm)
- Standard medical imaging format
- Rich metadata (patient, study, series)
- Window/level presets for brain viewing
- Multi-frame support

## Viewing Capabilities
- 2D slice viewer with scroll navigation
- Matplotlib rendering with colormaps (gray, viridis, hot, jet, etc.)
- Window/level adjustment
- Zoom/pan
- Segmentation overlay
"""
