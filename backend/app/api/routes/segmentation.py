"""
API routes for segmentation operations.
"""

from fastapi import APIRouter, HTTPException, status, Query, Body, Depends, Request
from fastapi.responses import Response
from typing import List, Optional
from datetime import datetime
import numpy as np

import struct

from app.core.logging import get_logger
from app.models.schemas import (
    LabelInfo,
    PaintStroke,
    SegmentationResponse,
    CreateSegmentationRequest,
    ErrorResponse
)
from app.core.interfaces.imaging_interface import IImagingService
from app.core.interfaces.storage_interface import IStorageService
from app.core.container import get_segmentation_service, get_imaging_service, get_storage_service
from app.services.segmentation_service import SegmentationService
from app.services.segmentation_comparison_service import (
    compare_two_masks,
    compute_agreement_map,
    compute_per_slice_dice,
)
from app.services.lesion_analysis_service import (
    analyze_lesions,
    compute_dis_criteria,
    MAGNIMS_REGIONS,
)
from app.services.ms_region_classifier import (
    classify_lesions_with_parcellation,
    classify_lesions_geometric,
    generate_zone_map,
    generate_zone_map_atlas,
)
from app.services.longitudinal_tracking_service import compare_timepoints
from app.core.config import get_settings
from app.utils import load_nifti_from_bytes

settings = get_settings()

router = APIRouter(prefix="/segmentation", tags=["segmentation"])
logger = get_logger(__name__)


@router.post("/create", response_model=SegmentationResponse)
async def create_segmentation(
    request: CreateSegmentationRequest,
    segmentation_service: SegmentationService = Depends(get_segmentation_service)
):
    """
    Create a new segmentation for an image file.

    Uses dependency injection to get SegmentationService instance.
    Custom exceptions will be caught by global exception handler.
    """
    try:
        # Use image shape from request (provided by frontend)
        image_shape = (
            request.image_shape.rows,
            request.image_shape.columns,
            request.image_shape.slices
        )

        logger.info(
            "Creating segmentation",
            extra={
                "file_id": request.file_id,
                "shape": image_shape,
                "num_labels": len(request.labels)
            }
        )

        # Detect source format from file extension
        source_format = "nifti"  # Default
        if request.file_id.lower().endswith('.dcm'):
            source_format = "dicom"
        elif request.file_id.lower().endswith(('.nii', '.nii.gz')):
            source_format = "nifti"

        logger.debug(
            "Detected source format",
            extra={
                "file_id": request.file_id,
                "source_format": source_format
            }
        )

        # Create segmentation
        segmentation = segmentation_service.create_segmentation(
            file_id=request.file_id,
            image_shape=image_shape,
            labels=request.labels,
            description=request.description,
            source_format=source_format
        )

        return segmentation

    except Exception as e:
        logger.error(
            "Failed to create segmentation",
            extra={
                "file_id": request.file_id,
                "error": str(e),
                "error_type": type(e).__name__
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create segmentation: {str(e)}"
        )


@router.get("/list", response_model=List[SegmentationResponse])
async def list_segmentations(
    file_id: Optional[str] = Query(None),
    file_ids: Optional[str] = Query(None, description="Comma-separated list of file_ids to query across multiple images"),
    segmentation_service: SegmentationService = Depends(get_segmentation_service)
):
    """
    List all segmentations, optionally filtered by file_id or file_ids.

    - file_id: Filter by a single file_id
    - file_ids: Filter by multiple file_ids (comma-separated), useful for study-level queries

    Uses dependency injection to get SegmentationService instance.
    Custom exceptions will be caught by global exception handler.
    """
    try:
        if file_ids:
            ids_list = [fid.strip() for fid in file_ids.split(",") if fid.strip()]
            if ids_list:
                return segmentation_service.list_segmentations(file_ids=ids_list)
        return segmentation_service.list_segmentations(file_id=file_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list segmentations: {str(e)}"
        )


@router.get("/{segmentation_id}", response_model=SegmentationResponse)
async def get_segmentation(
    segmentation_id: str,
    segmentation_service: SegmentationService = Depends(get_segmentation_service)
):
    """
    Get segmentation metadata and information.

    Uses dependency injection to get SegmentationService instance.
    Custom exceptions will be caught by global exception handler.
    """
    try:
        metadata = await segmentation_service.get_metadata(segmentation_id)
        if metadata is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Segmentation {segmentation_id} not found"
            )

        # Get image shape from cache
        if segmentation_id in segmentation_service.segmentations_cache:
            seg_data = segmentation_service.segmentations_cache[segmentation_id]
            total_slices = seg_data["masks_3d"].shape[0]  # Using D,H,W convention
        else:
            total_slices = 0

        return SegmentationResponse(
            segmentation_id=segmentation_id,
            file_id=metadata.file_id,
            metadata=metadata,
            total_slices=total_slices,
            masks=None
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get segmentation: {str(e)}"
        )


@router.post("/{segmentation_id}/paint")
async def apply_paint_stroke(
    segmentation_id: str,
    stroke: PaintStroke = Body(...),
    segmentation_service: SegmentationService = Depends(get_segmentation_service)
):
    """
    Apply a paint stroke to the segmentation.

    Uses dependency injection to get SegmentationService instance.
    Custom exceptions will be caught by global exception handler.
    """
    try:
        logger.debug(
            "Received paint stroke",
            extra={
                "segmentation_id": segmentation_id,
                "slice_index": stroke.slice_index,
                "position": {"x": stroke.x, "y": stroke.y},
                "brush_size": stroke.brush_size,
                "label_id": stroke.label_id,
                "erase_mode": stroke.erase
            }
        )

        success = await segmentation_service.apply_paint_stroke(segmentation_id, stroke)
        if not success:
            logger.warning(
                "Paint stroke failed",
                extra={"segmentation_id": segmentation_id}
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to apply paint stroke"
            )

        logger.info(
            "Paint stroke applied successfully",
            extra={"segmentation_id": segmentation_id, "slice_index": stroke.slice_index}
        )
        return {"success": True, "message": "Paint stroke applied successfully"}

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to apply paint stroke: {str(e)}"
        )


@router.get("/{segmentation_id}/slice/{slice_index}/mask")
async def get_slice_mask(
    segmentation_id: str,
    slice_index: int,
    segmentation_service: SegmentationService = Depends(get_segmentation_service)
):
    """
    Get the segmentation mask for a specific slice as base64 encoded image.

    Uses dependency injection to get SegmentationService instance.
    Custom exceptions will be caught by global exception handler.
    """
    try:
        mask = await segmentation_service.get_slice_mask(segmentation_id, slice_index)
        if mask is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Mask not found for slice {slice_index}"
            )

        # Convert mask to base64 image
        mask_base64 = segmentation_service._array_to_base64(mask)

        return {"slice_index": slice_index, "mask_data": mask_base64}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get slice mask: {str(e)}"
        )


@router.get("/{segmentation_id}/slice/{slice_index}/overlay")
async def get_overlay_image(
    segmentation_id: str,
    slice_index: int,
    window_center: Optional[float] = Query(None),
    window_width: Optional[float] = Query(None),
    colormap: str = Query("gray"),
    show_labels: Optional[str] = Query(None, description="Comma-separated label IDs"),
    t: Optional[int] = Query(None, description="Cache buster"),
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    imaging_service: IImagingService = Depends(get_imaging_service),
    storage_service: IStorageService = Depends(get_storage_service)
):
    """
    Get overlay image with segmentation on top of base image.
    Returns PNG image directly (not JSON).

    Uses dependency injection to get all required service instances.
    Custom exceptions will be caught by global exception handler.
    """
    from fastapi.responses import Response
    import base64
    import io

    try:
        # Get segmentation metadata
        metadata = await segmentation_service.get_metadata(segmentation_id)
        if metadata is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Segmentation {segmentation_id} not found"
            )

        # Get base image using storage and imaging services
        file_data = await storage_service.download_file(settings.GCS_BUCKET_NAME, metadata.file_id)
        filename = metadata.file_id.split('/')[-1] if metadata.file_id else "unknown"

        # Process image to get slice
        result = imaging_service.process_image(
            file_data=file_data,
            filename=filename,
            slice_range=(slice_index, slice_index + 1)
        )

        # Get base image from slice
        if result.slices and len(result.slices) > 0:
            # Decode base64 image - for now, we'll need to reprocess
            # This is a workaround until we have better caching
            from app.services.imaging_service import ImageFormat
            img_format = imaging_service.detect_format(file_data, filename)

            if img_format == ImageFormat.DICOM:
                pixel_array, _ = imaging_service.load_dicom(file_data)
            elif img_format == ImageFormat.NIFTI:
                pixel_array, _ = imaging_service.load_nifti(file_data)
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unsupported format: {img_format}"
                )

            # Ensure 3D
            if len(pixel_array.shape) == 2:
                pixel_array = pixel_array[:, :, np.newaxis]

            # Get slice
            base_image = pixel_array[:, :, slice_index]
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Slice {slice_index} not found"
            )

        # Apply window/level if specified
        if window_center is not None and window_width is not None:
            base_image = imaging_service.apply_window_level(
                base_image, window_center, window_width
            )

        # Parse show_labels
        label_ids = None
        if show_labels:
            label_ids = [int(x.strip()) for x in show_labels.split(",")]

        # Generate overlay (returns base64 string with data:image/png;base64, prefix)
        overlay_base64 = await segmentation_service.generate_overlay_image(
            base_image=base_image,
            segmentation_id=segmentation_id,
            slice_index=slice_index,
            show_labels=label_ids
        )

        # Extract base64 data (remove data:image/png;base64, prefix)
        if overlay_base64.startswith('data:image/png;base64,'):
            overlay_base64 = overlay_base64[len('data:image/png;base64,'):]

        # Decode base64 to bytes
        image_bytes = base64.b64decode(overlay_base64)

        # Return PNG image directly
        return Response(
            content=image_bytes,
            media_type="image/png",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate overlay image: {str(e)}"
        )


@router.get("/{segmentation_id}/slice/{slice_index}/segmentation-only")
async def get_segmentation_only(
    segmentation_id: str,
    slice_index: int,
    t: Optional[int] = Query(None, description="Cache buster"),
    segmentation_service: SegmentationService = Depends(get_segmentation_service)
):
    """
    Get ONLY the segmentation mask as a transparent PNG overlay.
    Does not include the base MRI image.

    Uses dependency injection to get SegmentationService instance.
    Custom exceptions will be caught by global exception handler.
    """
    from fastapi.responses import Response
    import base64

    try:
        # Generate just the segmentation overlay
        seg_overlay_base64 = await segmentation_service.generate_segmentation_overlay(
            segmentation_id=segmentation_id,
            slice_index=slice_index
        )

        # Extract base64 data
        if seg_overlay_base64.startswith('data:image/png;base64,'):
            seg_overlay_base64 = seg_overlay_base64[len('data:image/png;base64,'):]

        # Decode to bytes
        image_bytes = base64.b64decode(seg_overlay_base64)

        # Return PNG directly
        return Response(
            content=image_bytes,
            media_type="image/png",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate segmentation overlay: {str(e)}"
        )


@router.post("/{segmentation_id}/save")
async def save_segmentation(
    segmentation_id: str,
    segmentation_service: SegmentationService = Depends(get_segmentation_service)
):
    """
    Save segmentation to persistent storage (Firestore + GCS).

    This endpoint should be called:
    - When the user explicitly clicks "Save"
    - When changing slices (to persist paint strokes)
    - Before closing the viewer

    Uses dependency injection to get SegmentationService instance.
    """
    try:
        # Use the async save method
        success = await segmentation_service.save_segmentation_async(segmentation_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Segmentation {segmentation_id} not found or nothing to save"
            )

        # Get info about saved segmentation
        seg_data = segmentation_service.segmentations_cache.get(segmentation_id)

        if seg_data:
            source_format = seg_data.get("source_format", "nifti")
            masks_3d = seg_data.get("masks_3d")
            # Count non-zero voxels
            annotated_voxels = int(np.sum(masks_3d > 0)) if masks_3d is not None else 0
            message = f"Segmentation saved to cloud storage ({annotated_voxels} annotated voxels)"
        else:
            message = "Segmentation saved"

        logger.info(
            "Segmentation saved via API",
            extra={"segmentation_id": segmentation_id}
        )

        return {
            "success": True,
            "segmentation_id": segmentation_id,
            "message": message
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to save segmentation",
            extra={"segmentation_id": segmentation_id, "error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save segmentation: {str(e)}"
        )


@router.delete("/{segmentation_id}")
async def delete_segmentation(
    segmentation_id: str,
    segmentation_service: SegmentationService = Depends(get_segmentation_service)
):
    """
    Delete a segmentation.

    Uses dependency injection to get SegmentationService instance.
    Custom exceptions will be caught by global exception handler.
    """
    try:
        success = segmentation_service.delete_segmentation(segmentation_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Segmentation {segmentation_id} not found"
            )

        return {"success": True, "message": "Segmentation deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete segmentation: {str(e)}"
        )


@router.put("/{segmentation_id}/labels")
async def update_labels(
    segmentation_id: str,
    labels: List[LabelInfo] = Body(...),
    segmentation_service: SegmentationService = Depends(get_segmentation_service)
):
    """
    Update label definitions for a segmentation.

    Uses dependency injection to get SegmentationService instance.
    Custom exceptions will be caught by global exception handler.
    """
    try:
        metadata = await segmentation_service.get_metadata(segmentation_id)
        if metadata is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Segmentation {segmentation_id} not found"
            )

        # Update labels
        metadata.labels = labels
        metadata.modified_at = datetime.utcnow()

        # Save changes
        segmentation_service._save_segmentation(segmentation_id)

        return {"success": True, "message": "Labels updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update labels: {str(e)}"
        )


@router.get("/{segmentation_id}/nifti")
async def get_segmentation_nifti(
    segmentation_id: str,
    segmentation_service: SegmentationService = Depends(get_segmentation_service)
):
    """
    Serve the segmentation as a raw NIfTI file (.nii.gz) for WebGL-based viewers.

    This endpoint returns the segmentation mask as a NIfTI file with the exact same
    affine, header, and dimensions as the original MRI image, making it compatible
    with ITK-SNAP and NiiVue for overlay visualization.

    The NIfTI file is served directly from GCS storage where it was saved during
    the last save operation.
    """
    try:
        # Get the segmentation NIfTI from GCS
        nifti_data = segmentation_service.get_segmentation_nifti(segmentation_id)

        if nifti_data is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Segmentation NIfTI file not found for {segmentation_id}"
            )

        logger.info("Serving segmentation NIfTI file", extra={
            "segmentation_id": segmentation_id,
            "size_bytes": len(nifti_data)
        })

        return Response(
            content=nifti_data,
            media_type="application/gzip",
            headers={
                "Content-Disposition": f'inline; filename="{segmentation_id}_segmentation.nii.gz"',
                "Content-Length": str(len(nifti_data)),
                "Cache-Control": "no-cache",  # Segmentation can change, don't cache
                "Access-Control-Expose-Headers": "Content-Disposition, Content-Length"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error serving segmentation NIfTI", extra={
            "segmentation_id": segmentation_id,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get segmentation NIfTI: {str(e)}"
        )


# =============================================================================
# ITK-SNAP STYLE ARCHITECTURE: Binary mask endpoints for local-first editing
# =============================================================================
# These endpoints enable the frontend to:
# 1. Download the entire 3D mask once at startup
# 2. Edit locally in memory (instant, no network)
# 3. Upload the complete mask only when user clicks "Save"
# =============================================================================

@router.get("/{segmentation_id}/mask/binary")
async def get_binary_mask(
    segmentation_id: str,
    segmentation_service: SegmentationService = Depends(get_segmentation_service)
):
    """
    Download the complete 3D segmentation mask as raw binary data.

    ITK-SNAP Architecture: The frontend loads this ONCE at startup,
    stores it in memory, and all painting happens locally without
    any network calls. This is how professional segmentation tools work.

    Returns:
        Raw binary data (Uint8Array) with header containing dimensions.
        Format: [depth:4bytes][height:4bytes][width:4bytes][mask_data:D*H*W bytes]
    """
    try:
        # Load segmentation if not in cache
        if segmentation_id not in segmentation_service.segmentations_cache:
            if not segmentation_service._load_segmentation(segmentation_id):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Segmentation {segmentation_id} not found"
                )

        seg_data = segmentation_service.segmentations_cache[segmentation_id]
        masks_3d = seg_data["masks_3d"]  # numpy array (D, H, W), dtype=uint8

        # Get dimensions
        depth, height, width = masks_3d.shape

        # Create binary buffer with header
        # Header: 12 bytes (3 x uint32 for dimensions)
        # Data: D * H * W bytes
        import struct
        header = struct.pack('<III', depth, height, width)  # Little-endian uint32
        mask_bytes = masks_3d.tobytes()

        binary_data = header + mask_bytes

        logger.info("Serving binary mask", extra={
            "segmentation_id": segmentation_id,
            "shape": (depth, height, width),
            "size_bytes": len(binary_data)
        })

        return Response(
            content=binary_data,
            media_type="application/octet-stream",
            headers={
                "Content-Length": str(len(binary_data)),
                "X-Mask-Depth": str(depth),
                "X-Mask-Height": str(height),
                "X-Mask-Width": str(width),
                "Cache-Control": "no-cache",
                "Access-Control-Expose-Headers": "X-Mask-Depth, X-Mask-Height, X-Mask-Width, Content-Length"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error serving binary mask", extra={
            "segmentation_id": segmentation_id,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get binary mask: {str(e)}"
        )


@router.put("/{segmentation_id}/mask/binary")
async def upload_binary_mask(
    segmentation_id: str,
    request: Request,
    segmentation_service: SegmentationService = Depends(get_segmentation_service)
):
    """
    Upload the complete 3D segmentation mask from the frontend.

    ITK-SNAP Architecture: This is called ONLY when the user clicks "Save".
    All painting happens locally in the frontend - no network calls per stroke.

    Expects:
        Raw binary data (Uint8Array) with header containing dimensions.
        Format: [depth:4bytes][height:4bytes][width:4bytes][mask_data:D*H*W bytes]

    Returns:
        Success confirmation with voxel count
    """
    try:
        # Read raw binary data
        body = await request.body()

        if len(body) < 12:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid binary data: too short for header"
            )

        # Parse header
        import struct
        depth, height, width = struct.unpack('<III', body[:12])
        mask_bytes = body[12:]

        expected_size = depth * height * width
        if len(mask_bytes) != expected_size:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid mask size: expected {expected_size}, got {len(mask_bytes)}"
            )

        # Convert to numpy array
        masks_3d = np.frombuffer(mask_bytes, dtype=np.uint8).reshape((depth, height, width))

        # Load existing segmentation to get metadata
        if segmentation_id not in segmentation_service.segmentations_cache:
            if not segmentation_service._load_segmentation(segmentation_id):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Segmentation {segmentation_id} not found"
                )

        # Update the mask in cache
        seg_data = segmentation_service.segmentations_cache[segmentation_id]
        seg_data["masks_3d"] = masks_3d
        seg_data["metadata"].modified_at = datetime.utcnow()

        # Save to GCS (this is the ONLY time we save during editing)
        segmentation_service._save_segmentation(segmentation_id)

        # Count annotated voxels
        annotated_voxels = int(np.sum(masks_3d > 0))

        logger.info("Binary mask uploaded and saved", extra={
            "segmentation_id": segmentation_id,
            "shape": (depth, height, width),
            "annotated_voxels": annotated_voxels
        })

        return {
            "success": True,
            "segmentation_id": segmentation_id,
            "shape": {"depth": depth, "height": height, "width": width},
            "annotated_voxels": annotated_voxels,
            "message": f"Mask saved successfully ({annotated_voxels} annotated voxels)"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error uploading binary mask", extra={
            "segmentation_id": segmentation_id,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload binary mask: {str(e)}"
        )


@router.get("/{segmentation_id}/info")
async def get_segmentation_info(
    segmentation_id: str,
    segmentation_service: SegmentationService = Depends(get_segmentation_service)
):
    """
    Get segmentation metadata and dimensions without downloading the full mask.

    Useful for the frontend to know the mask dimensions before downloading.
    """
    try:
        # Load segmentation if not in cache
        if segmentation_id not in segmentation_service.segmentations_cache:
            if not segmentation_service._load_segmentation(segmentation_id):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Segmentation {segmentation_id} not found"
                )

        seg_data = segmentation_service.segmentations_cache[segmentation_id]
        masks_3d = seg_data["masks_3d"]
        metadata = seg_data["metadata"]

        depth, height, width = masks_3d.shape
        annotated_voxels = int(np.sum(masks_3d > 0))

        return {
            "segmentation_id": segmentation_id,
            "file_id": metadata.file_id,
            "shape": {"depth": depth, "height": height, "width": width},
            "total_voxels": depth * height * width,
            "annotated_voxels": annotated_voxels,
            "labels": [label.dict() for label in metadata.labels],
            "created_at": metadata.created_at.isoformat(),
            "modified_at": metadata.modified_at.isoformat(),
            "description": metadata.description
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting segmentation info", extra={
            "segmentation_id": segmentation_id,
            "error": str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get segmentation info: {str(e)}"
        )


# =============================================================================
# Comparison Endpoints
# =============================================================================

@router.post("/compare")
async def compare_masks(
    request: Request,
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    storage_service: IStorageService = Depends(get_storage_service),
):
    """
    Compare 2+ segmentation/expert masks.

    Request body:
    {
      "masks": [
        {"type": "segmentation", "id": "<segmentation_id>", "label": "My Seg"},
        {"type": "instance", "id": "<instance_id>", "label": "Expert 1"}
      ]
    }

    For type "segmentation": loads from segmentation cache/storage.
    For type "instance": loads NIfTI from GCS and converts to binary mask.

    Returns pairwise comparison metrics (Dice, Hausdorff, volume diff).
    """
    from app.core.container import get_study_service
    study_service = get_study_service()

    try:
        body = await request.json()
        mask_specs = body.get("masks", [])

        if len(mask_specs) < 2:
            raise HTTPException(status_code=400, detail="At least 2 masks required")

        # Load all masks
        loaded_masks = []
        for spec in mask_specs:
            mask_type = spec.get("type")
            mask_id = spec.get("id")
            label = spec.get("label", mask_id)

            if mask_type == "segmentation":
                # Load from segmentation cache
                if mask_id not in segmentation_service.segmentations_cache:
                    if not segmentation_service._load_segmentation(mask_id):
                        raise HTTPException(status_code=404, detail=f"Segmentation {mask_id} not found")
                mask_3d = segmentation_service.segmentations_cache[mask_id]["masks_3d"]
                loaded_masks.append({"mask": (mask_3d > 0).astype(np.uint8), "label": label})

            elif mask_type == "instance":
                # Load NIfTI from instance
                instance = await study_service.get_instance(mask_id)
                file_data = await storage_service.download_file(
                    settings.GCS_BUCKET_NAME, instance.gcs_object_name
                )
                _, data = load_nifti_from_bytes(file_data, normalize=False)
                mask = (data > 0).astype(np.uint8)
                if mask.ndim == 3:
                    mask = np.transpose(mask, (2, 1, 0))  # NIfTI (W,H,D) -> (D,H,W)
                loaded_masks.append({"mask": mask, "label": label})
            else:
                raise HTTPException(status_code=400, detail=f"Unknown mask type: {mask_type}")

        # Compute pairwise metrics
        comparisons = []
        for i in range(len(loaded_masks)):
            for j in range(i + 1, len(loaded_masks)):
                result = compare_two_masks(
                    loaded_masks[i]["mask"],
                    loaded_masks[j]["mask"],
                    loaded_masks[i]["label"],
                    loaded_masks[j]["label"],
                )
                comparisons.append(result)

        return {"comparisons": comparisons, "mask_count": len(loaded_masks)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error comparing masks", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Comparison failed: {str(e)}")


@router.post("/agreement-map")
async def get_agreement_map(
    request: Request,
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    storage_service: IStorageService = Depends(get_storage_service),
):
    """
    Compute voxel-wise agreement map across N masks.

    Returns binary data: [depth:4][height:4][width:4][mask_count:4][agreement_data:D*H*W bytes]
    Each voxel value = number of masks that agree (0 to N).
    """
    from app.core.container import get_study_service
    study_service = get_study_service()

    try:
        body = await request.json()
        mask_specs = body.get("masks", [])

        if len(mask_specs) < 2:
            raise HTTPException(status_code=400, detail="At least 2 masks required")

        loaded_masks = []
        for spec in mask_specs:
            mask_type = spec.get("type")
            mask_id = spec.get("id")

            if mask_type == "segmentation":
                if mask_id not in segmentation_service.segmentations_cache:
                    if not segmentation_service._load_segmentation(mask_id):
                        raise HTTPException(status_code=404, detail=f"Segmentation {mask_id} not found")
                mask_3d = segmentation_service.segmentations_cache[mask_id]["masks_3d"]
                loaded_masks.append((mask_3d > 0).astype(np.uint8))

            elif mask_type == "instance":
                instance = await study_service.get_instance(mask_id)
                file_data = await storage_service.download_file(
                    settings.GCS_BUCKET_NAME, instance.gcs_object_name
                )
                _, data = load_nifti_from_bytes(file_data, normalize=False)
                mask = (data > 0).astype(np.uint8)
                if mask.ndim == 3:
                    mask = np.transpose(mask, (2, 1, 0))
                loaded_masks.append(mask)

        agreement = compute_agreement_map(loaded_masks)
        depth, height, width = agreement.shape

        header = struct.pack('<IIII', depth, height, width, len(loaded_masks))
        binary_data = header + agreement.tobytes()

        return Response(
            content=binary_data,
            media_type="application/octet-stream",
            headers={
                "Content-Length": str(len(binary_data)),
                "X-Mask-Count": str(len(loaded_masks)),
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error computing agreement map", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Agreement map failed: {str(e)}")


# =============================================================================
# Lesion Analysis Endpoints
# =============================================================================

@router.get("/{segmentation_id}/lesion-analysis")
async def get_lesion_analysis(
    segmentation_id: str,
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
):
    """
    Analyze lesions in a segmentation using connected components.

    Returns per-lesion statistics (volume, centroid, bounding box),
    region summary, total burden, and size distribution.
    """
    try:
        # Load segmentation
        if segmentation_id not in segmentation_service.segmentations_cache:
            if not segmentation_service._load_segmentation(segmentation_id):
                raise HTTPException(status_code=404, detail=f"Segmentation {segmentation_id} not found")

        seg_data = segmentation_service.segmentations_cache[segmentation_id]
        masks_3d = seg_data["masks_3d"]
        metadata = seg_data["metadata"]

        # Build label map from metadata
        label_map = {}
        for lbl in metadata.labels:
            if hasattr(lbl, 'id') and hasattr(lbl, 'name'):
                label_map[lbl.id] = lbl.name
            elif isinstance(lbl, dict):
                label_map[lbl.get("id", 0)] = lbl.get("name", f"Label {lbl.get('id', 0)}")

        # Use MAGNIMS defaults if no custom labels
        if not label_map or all(lid == 0 for lid in label_map):
            label_map = MAGNIMS_REGIONS

        # Get voxel spacing from metadata if available
        voxel_spacing = (1.0, 1.0, 1.0)
        if hasattr(metadata, 'extra_fields') and metadata.extra_fields:
            ps = metadata.extra_fields.get('pixel_spacing')
            st = metadata.extra_fields.get('slice_thickness')
            if ps and len(ps) >= 2:
                voxel_spacing = (float(st or 1.0), float(ps[0]), float(ps[1]))

        result = analyze_lesions(masks_3d, voxel_spacing, label_map)
        result["segmentation_id"] = segmentation_id

        logger.info("Lesion analysis completed", extra={
            "segmentation_id": segmentation_id,
            "lesion_count": result["total_count"],
            "total_burden_ml": result["total_burden_ml"],
        })

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error analyzing lesions", extra={
            "segmentation_id": segmentation_id,
            "error": str(e),
        })
        raise HTTPException(status_code=500, detail=f"Lesion analysis failed: {str(e)}")


@router.get("/{segmentation_id}/dis-assessment")
async def get_dis_assessment(
    segmentation_id: str,
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
):
    """
    Evaluate McDonald 2024 DIS (Dissemination in Space) criteria.

    Checks if lesions are present in ≥2 of 4 characteristic MAGNIMS regions.
    """
    try:
        if segmentation_id not in segmentation_service.segmentations_cache:
            if not segmentation_service._load_segmentation(segmentation_id):
                raise HTTPException(status_code=404, detail=f"Segmentation {segmentation_id} not found")

        seg_data = segmentation_service.segmentations_cache[segmentation_id]
        masks_3d = seg_data["masks_3d"]
        metadata = seg_data["metadata"]

        # Build label map
        label_map = {}
        for lbl in metadata.labels:
            if hasattr(lbl, 'id') and hasattr(lbl, 'name'):
                label_map[lbl.id] = lbl.name
            elif isinstance(lbl, dict):
                label_map[lbl.get("id", 0)] = lbl.get("name", f"Label {lbl.get('id', 0)}")

        if not label_map or all(lid == 0 for lid in label_map):
            label_map = MAGNIMS_REGIONS

        result = compute_dis_criteria(masks_3d, label_map)
        result["segmentation_id"] = segmentation_id

        logger.info("DIS assessment completed", extra={
            "segmentation_id": segmentation_id,
            "dis_met": result["dis_met"],
            "regions_with_lesions": result["regions_with_lesions"],
        })

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error computing DIS assessment", extra={
            "segmentation_id": segmentation_id,
            "error": str(e),
        })
        raise HTTPException(status_code=500, detail=f"DIS assessment failed: {str(e)}")


# =============================================================================
# Region Classification Endpoint (SynthSeg + EDT / Geometric)
# =============================================================================

@router.post("/{segmentation_id}/classify-regions")
async def classify_regions(
    segmentation_id: str,
    request: Request,
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    storage_service: IStorageService = Depends(get_storage_service),
):
    """
    Auto-classify lesions into MAGNIMS regions (PV, JC, IT, DWM).

    Uses brain parcellation (SynthSeg/FreeSurfer labels) + Euclidean Distance
    Transform for high-accuracy classification (~90%+ agreement with expert
    neuroradiologists). Falls back to geometric heuristics when no parcellation
    is available.

    Request body:
    {
      "parcellation_id": "<optional segmentation_id with FreeSurfer labels>",
      "method": "auto" | "parcellation" | "geometric"
    }

    - method "auto" (default): tries parcellation first, falls back to geometric
    - method "parcellation": requires parcellation_id
    - method "geometric": uses spatial heuristics only

    The segmentation mask is reclassified IN-PLACE (label values changed from
    binary 1 to MAGNIMS labels 1-4) and saved. The frontend should re-download
    the binary mask after this call.
    """
    try:
        body = await request.json()
        parcellation_id = body.get("parcellation_id")
        method = body.get("method", "auto")

        # Load the lesion segmentation
        if segmentation_id not in segmentation_service.segmentations_cache:
            if not segmentation_service._load_segmentation(segmentation_id):
                raise HTTPException(
                    status_code=404,
                    detail=f"Segmentation {segmentation_id} not found",
                )

        seg_data = segmentation_service.segmentations_cache[segmentation_id]
        lesion_mask = seg_data["masks_3d"]  # (D, H, W), uint8
        metadata = seg_data["metadata"]

        # Get voxel spacing
        voxel_spacing = (1.0, 1.0, 1.0)
        if hasattr(metadata, 'extra_fields') and metadata.extra_fields:
            ps = metadata.extra_fields.get('pixel_spacing')
            st = metadata.extra_fields.get('slice_thickness')
            if ps and len(ps) >= 2:
                voxel_spacing = (float(st or 1.0), float(ps[0]), float(ps[1]))

        result = None

        # --- Try parcellation-based classification ---
        if method in ("auto", "parcellation") and parcellation_id:
            try:
                # Load parcellation mask
                if parcellation_id not in segmentation_service.segmentations_cache:
                    if not segmentation_service._load_segmentation(parcellation_id):
                        if method == "parcellation":
                            raise HTTPException(
                                status_code=404,
                                detail=f"Parcellation {parcellation_id} not found",
                            )
                        logger.warning(
                            "[ClassifyRegions] Parcellation %s not found, falling back to geometric",
                            parcellation_id,
                        )

                if parcellation_id in segmentation_service.segmentations_cache:
                    parc_data = segmentation_service.segmentations_cache[parcellation_id]
                    parcellation_mask = parc_data["masks_3d"]

                    result = classify_lesions_with_parcellation(
                        lesion_mask, parcellation_mask, voxel_spacing
                    )
                    logger.info(
                        "[ClassifyRegions] Parcellation-based classification succeeded",
                        extra={"segmentation_id": segmentation_id},
                    )
            except HTTPException:
                raise
            except Exception as e:
                if method == "parcellation":
                    raise
                logger.warning(
                    "[ClassifyRegions] Parcellation classification failed: %s. Falling back.",
                    str(e),
                )

        # --- Try parcellation from instance (expert mask as NIfTI) ---
        if result is None and method in ("auto", "parcellation") and not parcellation_id:
            # Check if there is another segmentation for the same file that
            # looks like a parcellation (has FreeSurfer-range labels)
            file_id = metadata.file_id
            all_segs = segmentation_service.list_segmentations(file_id=file_id)
            for candidate in all_segs:
                if candidate.segmentation_id == segmentation_id:
                    continue
                # Load candidate and check for FreeSurfer labels
                try:
                    cand_id = candidate.segmentation_id
                    if cand_id not in segmentation_service.segmentations_cache:
                        segmentation_service._load_segmentation(cand_id)
                    if cand_id in segmentation_service.segmentations_cache:
                        cand_mask = segmentation_service.segmentations_cache[cand_id]["masks_3d"]
                        unique_vals = set(int(v) for v in np.unique(cand_mask) if v > 0)
                        # FreeSurfer labels include values like 2,3,4,7,8,10...
                        freesurfer_check = unique_vals & {2, 3, 4, 7, 8, 10, 16, 41, 42, 43}
                        if len(freesurfer_check) >= 3:
                            logger.info(
                                "[ClassifyRegions] Found parcellation candidate: %s",
                                cand_id,
                            )
                            result = classify_lesions_with_parcellation(
                                lesion_mask, cand_mask, voxel_spacing
                            )
                            break
                except Exception:
                    continue

        # --- Fallback to geometric ---
        if result is None:
            if method == "parcellation":
                raise HTTPException(
                    status_code=400,
                    detail="Parcellation method requested but no parcellation available. "
                           "Run AI Brain Parcellation (SynthSeg) first.",
                )
            result = classify_lesions_geometric(
                lesion_mask, image_data=None, voxel_spacing=voxel_spacing
            )

        # --- Update the segmentation mask in place ---
        classified_mask = result.get("classified_mask")
        if classified_mask is not None:
            seg_data["masks_3d"] = classified_mask

            # Update labels to MAGNIMS
            from app.models.schemas import LabelInfo as SchemaLabelInfo
            magnims_labels = [
                SchemaLabelInfo(id=0, name="Background", color="#000000", opacity=0.0, visible=False),
                SchemaLabelInfo(id=1, name="Periventricular", color="#FF0000", opacity=0.6, visible=True),
                SchemaLabelInfo(id=2, name="Juxtacortical", color="#00CC00", opacity=0.6, visible=True),
                SchemaLabelInfo(id=3, name="Infratentorial", color="#0066FF", opacity=0.6, visible=True),
                SchemaLabelInfo(id=4, name="Deep White Matter", color="#FFD700", opacity=0.6, visible=True),
                SchemaLabelInfo(id=5, name="Active (Gd+)", color="#FF00FF", opacity=0.6, visible=True),
                SchemaLabelInfo(id=6, name="Black Hole (T1)", color="#9932CC", opacity=0.5, visible=True),
            ]
            metadata.labels = magnims_labels
            metadata.modified_at = datetime.utcnow()

            # Save to GCS
            segmentation_service._save_segmentation(segmentation_id)

        # Remove numpy array from response (not JSON serializable)
        response_data = {k: v for k, v in result.items() if k != "classified_mask"}
        response_data["segmentation_id"] = segmentation_id
        response_data["mask_updated"] = classified_mask is not None
        response_data["labels_updated"] = classified_mask is not None

        logger.info(
            "[ClassifyRegions] Region classification completed",
            extra={
                "segmentation_id": segmentation_id,
                "method": result["method"],
                "total_classified": result["total_classified"],
                "processing_time_ms": result["processing_time_ms"],
            },
        )

        return response_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "[ClassifyRegions] Classification failed",
            extra={"segmentation_id": segmentation_id, "error": str(e)},
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Region classification failed: {str(e)}",
        )


# =============================================================================
# MAGNIMS Zone Map Generation
# =============================================================================


@router.post("/generate-zone-map")
async def generate_zone_map_endpoint(
    request: Request,
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    storage_service: IStorageService = Depends(get_storage_service),
):
    """
    Generate a MAGNIMS zone map for a brain MRI.

    Creates a new segmentation where every brain voxel is classified into one of
    the four MAGNIMS regions (Periventricular, Juxtacortical, Infratentorial,
    Deep White Matter).

    Method selection:
    - If a brain parcellation (SynthSeg) exists: uses EDT from anatomical landmarks (~90% accuracy)
    - Fallback: loads MRI image, computes brain mask via Otsu thresholding, uses geometric heuristics (~70%)

    Request body:
    {
      "file_id": "<image file_id>",
      "parcellation_id": "<optional segmentation_id with FreeSurfer labels>"
    }
    """
    try:
        body = await request.json()
        file_id = body.get("file_id")
        parcellation_id = body.get("parcellation_id")

        if not file_id:
            raise HTTPException(
                status_code=400,
                detail="file_id is required",
            )

        # --- Delete existing zone maps for this file (prevent duplicates) ---
        all_existing = segmentation_service.list_segmentations(file_id=file_id)
        for existing in all_existing:
            eid = existing.segmentation_id
            try:
                if eid not in segmentation_service.segmentations_cache:
                    segmentation_service._load_segmentation(eid)
                if eid in segmentation_service.segmentations_cache:
                    emeta = segmentation_service.segmentations_cache[eid].get("metadata")
                    if emeta and getattr(emeta, 'description', '') == "MAGNIMS Zone Map":
                        logger.info("[ZoneMap] Deleting old zone map: %s", eid)
                        segmentation_service.delete_segmentation(eid)
            except Exception:
                pass

        # --- Find parcellation ---
        parcellation_mask = None
        parc_source = None

        # Explicit parcellation_id
        if parcellation_id:
            if parcellation_id not in segmentation_service.segmentations_cache:
                if not segmentation_service._load_segmentation(parcellation_id):
                    raise HTTPException(
                        status_code=404,
                        detail=f"Parcellation {parcellation_id} not found",
                    )
            parc_data = segmentation_service.segmentations_cache[parcellation_id]
            parcellation_mask = parc_data["masks_3d"]
            parc_source = parcellation_id
        else:
            # Auto-detect parcellation for this file
            all_segs = segmentation_service.list_segmentations(file_id=file_id)
            for candidate in all_segs:
                cand_id = candidate.segmentation_id
                try:
                    if cand_id not in segmentation_service.segmentations_cache:
                        segmentation_service._load_segmentation(cand_id)
                    if cand_id in segmentation_service.segmentations_cache:
                        # Skip zone map segmentations (labels 1-4 overlap with FreeSurfer)
                        cand_meta = segmentation_service.segmentations_cache[cand_id].get("metadata")
                        if cand_meta and getattr(cand_meta, 'description', '') == "MAGNIMS Zone Map":
                            continue
                        cand_mask = segmentation_service.segmentations_cache[cand_id]["masks_3d"]
                        unique_vals = set(int(v) for v in np.unique(cand_mask) if v > 0)
                        # FreeSurfer parcellations have hemispheric labels (41-43)
                        # and brainstem (16). Zone maps only have labels 1-4.
                        # Require at least one high label to distinguish.
                        freesurfer_check = unique_vals & {2, 3, 4, 7, 8, 10, 16, 41, 42, 43}
                        has_high_labels = bool(unique_vals & {16, 41, 42, 43})
                        if len(freesurfer_check) >= 3 and has_high_labels:
                            parcellation_mask = cand_mask
                            parc_source = cand_id
                            break
                except Exception:
                    continue

        # Get voxel spacing from metadata if available
        voxel_spacing = (1.0, 1.0, 1.0)
        if parc_source and parc_source in segmentation_service.segmentations_cache:
            meta = segmentation_service.segmentations_cache[parc_source].get("metadata")
            if meta and hasattr(meta, 'extra_fields') and meta.extra_fields:
                ps = meta.extra_fields.get('pixel_spacing')
                st = meta.extra_fields.get('slice_thickness')
                if ps and len(ps) >= 2:
                    voxel_spacing = (float(st or 1.0), float(ps[0]), float(ps[1]))

        # --- Generate zone map ---
        if parcellation_mask is not None:
            # Preferred method: parcellation-based (high accuracy)
            logger.info("[ZoneMap] Using parcellation-based method (source=%s)", parc_source)
            result = generate_zone_map(parcellation_mask, voxel_spacing)
        else:
            # Atlas-based method: Harvard-Oxford atlas resampled to patient image
            logger.info("[ZoneMap] No parcellation found, using atlas method for file=%s", file_id)
            file_data = await storage_service.download_file(settings.GCS_BUCKET_NAME, file_id)
            img, data = load_nifti_from_bytes(file_data, normalize=False)
            # Create in-memory NIfTI (the temp file from load_nifti_from_bytes is
            # already deleted, so img.dataobj is a dead file proxy; we need a new
            # image backed by the in-memory data array for resample_to_img to work)
            import nibabel as nib
            target_img = nib.Nifti1Image(data, img.affine, img.header)
            result = generate_zone_map_atlas(target_img, voxel_spacing)
            # Transpose zone_mask from NIfTI native (i,j,k) to display-compatible
            # internal format (k,i,j) using transpose (2,0,1).
            #
            # Why (2,0,1) instead of the usual (2,1,0)?
            # The MRI display pipeline (imaging_service) does NOT transpose — it
            # serves slices as raw NIfTI[:,:,k], shape (i,j). The frontend renders
            # each slice with imageWidth=columns=j and imageHeight=rows=i.
            # To overlay correctly, the zone map must have the same per-slice layout:
            #   internal[k, i, j] = nifti[i, j, k]  →  transpose (2, 0, 1)
            # The standard (2,1,0) would give internal[k, j, i], swapping the axes.
            zone_mask_raw = result["zone_mask"]
            if zone_mask_raw.ndim == 3:
                result["zone_mask"] = np.transpose(zone_mask_raw, (2, 0, 1))

        zone_mask = result["zone_mask"]

        if zone_mask is None or int(zone_mask.sum()) == 0:
            raise HTTPException(
                status_code=400,
                detail="Failed to generate zone map: no brain voxels detected.",
            )

        # --- Create segmentation with zone mask ---
        from app.models.schemas import LabelInfo as SchemaLabelInfo

        depth, height, width = zone_mask.shape
        magnims_labels = [
            SchemaLabelInfo(id=0, name="Background", color="#000000", opacity=0.0, visible=False),
            SchemaLabelInfo(id=1, name="Periventricular", color="#FF0000", opacity=0.6, visible=True),
            SchemaLabelInfo(id=2, name="Juxtacortical", color="#00CC00", opacity=0.6, visible=True),
            SchemaLabelInfo(id=3, name="Infratentorial", color="#0066FF", opacity=0.6, visible=True),
            SchemaLabelInfo(id=4, name="Deep White Matter", color="#FFD700", opacity=0.6, visible=True),
        ]

        # create_segmentation expects: file_id: str, image_shape: (H, W, D) tuple
        seg_response = segmentation_service.create_segmentation(
            file_id=file_id,
            image_shape=(height, width, depth),
            labels=magnims_labels,
            description="MAGNIMS Zone Map",
        )
        new_seg_id = seg_response.segmentation_id

        # Write the zone mask into the cache
        if new_seg_id in segmentation_service.segmentations_cache:
            segmentation_service.segmentations_cache[new_seg_id]["masks_3d"] = zone_mask.astype(np.uint8)

        # Save to GCS
        segmentation_service._save_segmentation(new_seg_id)

        logger.info(
            "[ZoneMap] Zone map segmentation created",
            extra={
                "segmentation_id": new_seg_id,
                "file_id": file_id,
                "processing_time_ms": result["processing_time_ms"],
            },
        )

        return {
            "segmentation_id": new_seg_id,
            "file_id": file_id,
            "zone_stats": result["zone_stats"],
            "total_brain_voxels": result["total_brain_voxels"],
            "processing_time_ms": result["processing_time_ms"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "[ZoneMap] Zone map generation failed",
            extra={"error": str(e)},
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Zone map generation failed: {str(e)}",
        )


# =============================================================================
# Longitudinal Tracking Endpoints
# =============================================================================

@router.post("/longitudinal/compare")
async def compare_longitudinal(
    request: Request,
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    storage_service: IStorageService = Depends(get_storage_service),
):
    """
    Compare lesion masks from two timepoints.

    Request body:
    {
      "tp1": {"type": "segmentation"|"instance", "id": "<id>"},
      "tp2": {"type": "segmentation"|"instance", "id": "<id>"}
    }

    Returns lesion-by-lesion changes (new, resolved, enlarged, shrunk, stable),
    total burden delta, and summary counts.
    """
    from app.core.container import get_study_service
    study_service = get_study_service()

    try:
        body = await request.json()
        tp1_spec = body.get("tp1")
        tp2_spec = body.get("tp2")

        if not tp1_spec or not tp2_spec:
            raise HTTPException(status_code=400, detail="Both tp1 and tp2 are required")

        async def load_mask(spec):
            mask_type = spec.get("type")
            mask_id = spec.get("id")

            if mask_type == "segmentation":
                if mask_id not in segmentation_service.segmentations_cache:
                    if not segmentation_service._load_segmentation(mask_id):
                        raise HTTPException(status_code=404, detail=f"Segmentation {mask_id} not found")
                return segmentation_service.segmentations_cache[mask_id]["masks_3d"]

            elif mask_type == "instance":
                instance = await study_service.get_instance(mask_id)
                file_data = await storage_service.download_file(
                    settings.GCS_BUCKET_NAME, instance.gcs_object_name
                )
                _, data = load_nifti_from_bytes(file_data, normalize=False)
                mask = (data > 0).astype(np.uint8)
                if mask.ndim == 3:
                    mask = np.transpose(mask, (2, 1, 0))
                return mask
            else:
                raise HTTPException(status_code=400, detail=f"Unknown mask type: {mask_type}")

        mask_tp1 = await load_mask(tp1_spec)
        mask_tp2 = await load_mask(tp2_spec)

        result = compare_timepoints(mask_tp1, mask_tp2)

        logger.info("Longitudinal comparison completed", extra={
            "new": result["status_counts"]["new"],
            "resolved": result["status_counts"]["resolved"],
            "enlarged": result["status_counts"]["enlarged"],
        })

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Longitudinal comparison failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Longitudinal comparison failed: {str(e)}")
