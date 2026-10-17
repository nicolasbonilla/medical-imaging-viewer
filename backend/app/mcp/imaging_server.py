"""
Brain Imaging MCP Server (read-only).

Lets an AI assistant (Claude Desktop / Claude Code) read images the operating clinician may
access:
- image metadata (direct identifiers removed)
- single slices and a sample of slices as base64 PNG
- the segmentations of an image

CAPA-008: every backend call goes through ``app.mcp._backend`` (GET only here), which removes
direct identifiers (patient name/ID, institution, dates, extra DICOM fields) before the
assistant — and therefore its model provider — sees a response. Free text such as series
descriptions is passed through and must not contain identifiers.

@module mcp.imaging_server
"""

from typing import Optional

from fastmcp import FastMCP
from app.mcp._backend import api_get

mcp = FastMCP(
    "brain-imaging-mcp",
    description="Read-only brain MRI access for the assistant — metadata without identifiers, "
                "slices, segmentation list",
)


# =============================================================================
# Tools (read-only)
# =============================================================================

@mcp.tool()
async def get_image_metadata(file_id: str) -> dict:
    """
    Get technical metadata for a brain MRI image: modality, manufacturer, dimensions, pixel
    spacing, slice thickness, anatomical orientation, window/level.

    Direct identifiers (patient name/ID, institution, dates, extra DICOM fields) are removed.

    Args:
        file_id: The storage path or ID of the image
    """
    return await api_get(f"/imaging/metadata/{file_id}")


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
        file_id: The storage path or ID of the image
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
    return await api_get(f"/imaging/slice/{file_id}/{slice_index}", params=params)


@mcp.tool()
async def process_image(file_id: str, max_slices: int = 10) -> dict:
    """
    Overview of a brain MRI file: technical metadata (identifiers removed) plus the first
    N slices as base64-encoded PNGs.

    Args:
        file_id: The storage path or ID of the image
        max_slices: Maximum number of slices to return (default 10)
    """
    return await api_get(f"/imaging/process/{file_id}", params={"max_slices": str(max_slices)})


@mcp.tool()
async def list_segmentations(file_id: str) -> list:
    """
    List the segmentations available for a brain MRI image (IDs, descriptions, labels,
    timestamps).

    Args:
        file_id: The storage path or ID of the image
    """
    return await api_get("/segmentation/list", params={"file_id": file_id})


@mcp.tool()
async def get_matplotlib_visualization(
    file_id: str,
    slice_index: int,
    colormap: str = "gray",
    window_center: Optional[float] = None,
    window_width: Optional[float] = None,
) -> dict:
    """
    Get a matplotlib-rendered view of a brain MRI slice (axes and colorbar).

    Args:
        file_id: The storage path or ID of the image
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
    return await api_get(f"/imaging/matplotlib-2d/{file_id}/{slice_index}", params=params)


# =============================================================================
# Resources
# =============================================================================

@mcp.resource("imaging://supported-formats")
async def get_supported_formats() -> str:
    """Supported medical imaging file formats and viewing capabilities."""
    return """# Supported Medical Imaging Formats

## NIfTI (.nii, .nii.gz)
- 3D volumetric brain MRI data
- Segmentation support
- Multi-orientation viewing (axial, sagittal, coronal)

## DICOM (.dcm)
- Standard medical imaging format
- Window/level presets for brain viewing
- Multi-frame support

## Viewing capabilities
- 2D slice viewer with scroll navigation
- Matplotlib rendering with colormaps (gray, viridis, hot, jet, etc.)
- Window/level adjustment
- Segmentation overlay
"""
