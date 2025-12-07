"""
API routes for segmentation operations.
"""

from fastapi import APIRouter, HTTPException, status, Query, Body, Depends
from typing import List, Optional
from datetime import datetime
import numpy as np

from app.core.logging import get_logger
from app.models.schemas import (
    LabelInfo,
    PaintStroke,
    SegmentationResponse,
    CreateSegmentationRequest,
    ErrorResponse
)
from app.core.interfaces.segmentation_interface import ISegmentationService
from app.core.interfaces.imaging_interface import IImagingService
from app.core.interfaces.drive_interface import IDriveService
from app.core.container import get_segmentation_service, get_imaging_service, get_drive_service

router = APIRouter(prefix="/segmentation", tags=["segmentation"])
logger = get_logger(__name__)


@router.post("/create", response_model=SegmentationResponse)
async def create_segmentation(
    request: CreateSegmentationRequest,
    segmentation_service: ISegmentationService = Depends(get_segmentation_service)
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
    segmentation_service: ISegmentationService = Depends(get_segmentation_service)
):
    """
    List all segmentations, optionally filtered by file_id.

    Uses dependency injection to get SegmentationService instance.
    Custom exceptions will be caught by global exception handler.
    """
    try:
        return segmentation_service.list_segmentations(file_id=file_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list segmentations: {str(e)}"
        )


@router.get("/{segmentation_id}", response_model=SegmentationResponse)
async def get_segmentation(
    segmentation_id: str,
    segmentation_service: ISegmentationService = Depends(get_segmentation_service)
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
    segmentation_service: ISegmentationService = Depends(get_segmentation_service)
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
    segmentation_service: ISegmentationService = Depends(get_segmentation_service)
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
    segmentation_service: ISegmentationService = Depends(get_segmentation_service),
    imaging_service: IImagingService = Depends(get_imaging_service),
    drive_service: IDriveService = Depends(get_drive_service)
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

        # Get base image using imaging service
        file_metadata_obj = drive_service.get_file_metadata(metadata.file_id)
        file_data = drive_service.download_file(metadata.file_id)

        # Process image to get slice
        result = imaging_service.process_image(
            file_data=file_data,
            filename=file_metadata_obj.name,
            slice_range=(slice_index, slice_index + 1)
        )

        # Get base image from slice
        if result.slices and len(result.slices) > 0:
            # Decode base64 image - for now, we'll need to reprocess
            # This is a workaround until we have better caching
            from app.services.imaging_service import ImageFormat
            img_format = imaging_service.detect_format(file_data, file_metadata_obj.name)

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
    segmentation_service: ISegmentationService = Depends(get_segmentation_service)
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
    segmentation_service: ISegmentationService = Depends(get_segmentation_service)
):
    """
    Save segmentation to disk (NIfTI or DICOM based on source format).

    Uses dependency injection to get SegmentationService instance.
    Custom exceptions will be caught by global exception handler.
    """
    try:
        segmentation_service._save_segmentation(segmentation_id)

        # Get output path based on format
        from pathlib import Path
        seg_data = segmentation_service.segmentations_cache.get(segmentation_id)

        if seg_data:
            source_format = seg_data.get("source_format", "nifti")
            if source_format == "nifti":
                output_path = Path(segmentation_service.storage_path) / f"{segmentation_id}_seg.nii.gz"
                message = "Segmentation saved as NIfTI file"
            else:
                output_path = Path(segmentation_service.storage_path) / "dicom" / segmentation_id
                message = "Segmentation saved as DICOM series"
        else:
            output_path = "Unknown"
            message = "Segmentation saved"

        return {
            "success": True,
            "output_path": str(output_path),
            "dicom_directory": str(output_path),  # Keep for compatibility
            "message": message
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save segmentation: {str(e)}"
        )


@router.delete("/{segmentation_id}")
async def delete_segmentation(
    segmentation_id: str,
    segmentation_service: ISegmentationService = Depends(get_segmentation_service)
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
    segmentation_service: ISegmentationService = Depends(get_segmentation_service)
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
