"""
API routes for segmentation operations (v2).

Hierarchical endpoints with full Patient → Study → Series → Segmentation support.
Multi-expert workflow with status tracking.

@module api.routes.segmentation_v2
"""

from fastapi import APIRouter, HTTPException, status, Query, Body, Depends, Path
from fastapi.responses import Response
from typing import List, Optional
from uuid import UUID
from datetime import datetime
import base64

from app.core.logging import get_logger
from app.security.auth import get_current_user
from app.models.segmentation_schemas import (
    SegmentationCreate,
    SegmentationUpdate,
    SegmentationStatusUpdate,
    SegmentationResponse,
    SegmentationSummary,
    SegmentationListResponse,
    SegmentationSearch,
    SegmentationStatistics,
    PaintStroke,
    PaintStrokeBatch,
    LabelInfo,
    OverlaySettings,
    ExportRequest,
    ExportResponse,
)
from app.services.segmentation_service_firestore import SegmentationServiceFirestore
from app.core.container import get_segmentation_service_v2
from app.core.config import get_settings

settings = get_settings()
router = APIRouter(tags=["segmentation-v2"])
logger = get_logger(__name__)


# =============================================================================
# Hierarchical Endpoints - Series Level
# =============================================================================

@router.post(
    "/patients/{patient_id}/studies/{study_id}/series/{series_id}/segmentations",
    response_model=SegmentationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create segmentation for a series"
)
async def create_segmentation(
    patient_id: UUID = Path(..., description="Patient UUID"),
    study_id: UUID = Path(..., description="Study UUID"),
    series_id: UUID = Path(..., description="Series UUID"),
    request: SegmentationCreate = Body(...),
    current_user: dict = Depends(get_current_user),
    segmentation_service: SegmentationServiceFirestore = Depends(get_segmentation_service_v2)
):
    """
    Create a new segmentation for an imaging series.

    The segmentation will be linked to the series and inherit patient/study context.
    Initial status will be DRAFT until the first paint stroke.
    """
    try:
        # Override series_id from path if different
        if request.series_id != series_id:
            request.series_id = series_id

        # TODO: Get image shape from series metadata
        # For now, use a default or require it in the request
        image_shape = (256, 256, 155)  # Default, should come from series

        segmentation = await segmentation_service.create_segmentation(
            patient_id=str(patient_id),
            study_id=str(study_id),
            series_id=str(series_id),
            data=request,
            user_id=current_user.get("username", "unknown"),
            user_name=current_user.get("full_name", current_user.get("username", "Unknown")),
            image_shape=image_shape,
        )

        logger.info(
            "Created segmentation",
            extra={
                "segmentation_id": str(segmentation.id),
                "series_id": str(series_id),
                "created_by": current_user.get("username"),
            }
        )

        return segmentation

    except Exception as e:
        logger.error(f"Failed to create segmentation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create segmentation: {str(e)}"
        )


@router.get(
    "/patients/{patient_id}/studies/{study_id}/series/{series_id}/segmentations",
    response_model=SegmentationListResponse,
    summary="List segmentations for a series"
)
async def list_series_segmentations(
    patient_id: UUID = Path(..., description="Patient UUID"),
    study_id: UUID = Path(..., description="Study UUID"),
    series_id: UUID = Path(..., description="Series UUID"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    created_by: Optional[str] = Query(None, description="Filter by creator username"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    segmentation_service: SegmentationServiceFirestore = Depends(get_segmentation_service_v2)
):
    """
    List all segmentations for a specific series.

    Supports filtering by status and creator.
    Returns minimal summary data for fast loading.
    """
    from app.models.segmentation_schemas import SegmentationStatus

    search = SegmentationSearch(
        series_id=series_id,
        status=SegmentationStatus(status_filter) if status_filter else None,
        created_by=created_by,
        page=page,
        page_size=page_size,
    )

    return await segmentation_service.list_segmentations(
        patient_id=str(patient_id),
        study_id=str(study_id),
        series_id=str(series_id),
        search=search,
    )


# =============================================================================
# Hierarchical Endpoints - Study Level
# =============================================================================

@router.get(
    "/patients/{patient_id}/studies/{study_id}/segmentations",
    response_model=SegmentationListResponse,
    summary="List all segmentations for a study"
)
async def list_study_segmentations(
    patient_id: UUID = Path(..., description="Patient UUID"),
    study_id: UUID = Path(..., description="Study UUID"),
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    segmentation_service: SegmentationServiceFirestore = Depends(get_segmentation_service_v2)
):
    """
    List all segmentations across all series in a study.

    Useful for getting an overview of all segmentation work on a study.
    """
    from app.models.segmentation_schemas import SegmentationStatus

    search = SegmentationSearch(
        study_id=study_id,
        status=SegmentationStatus(status_filter) if status_filter else None,
        page=page,
        page_size=page_size,
    )

    return await segmentation_service.list_segmentations(
        patient_id=str(patient_id),
        study_id=str(study_id),
        search=search,
    )


# =============================================================================
# Hierarchical Endpoints - Patient Level
# =============================================================================

@router.get(
    "/patients/{patient_id}/segmentations",
    response_model=SegmentationListResponse,
    summary="List all segmentations for a patient"
)
async def list_patient_segmentations(
    patient_id: UUID = Path(..., description="Patient UUID"),
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    segmentation_service: SegmentationServiceFirestore = Depends(get_segmentation_service_v2)
):
    """
    List all segmentations across all studies for a patient.

    Provides a complete view of all segmentation work for a patient.
    """
    from app.models.segmentation_schemas import SegmentationStatus

    search = SegmentationSearch(
        patient_id=patient_id,
        status=SegmentationStatus(status_filter) if status_filter else None,
        page=page,
        page_size=page_size,
    )

    return await segmentation_service.list_segmentations(
        patient_id=str(patient_id),
        search=search,
    )


# =============================================================================
# Direct Segmentation Endpoints
# =============================================================================

@router.get(
    "/segmentations/{segmentation_id}",
    response_model=SegmentationResponse,
    summary="Get segmentation by ID"
)
async def get_segmentation(
    segmentation_id: UUID = Path(..., description="Segmentation UUID"),
    segmentation_service: SegmentationServiceFirestore = Depends(get_segmentation_service_v2)
):
    """
    Get full segmentation details by ID.

    Returns complete metadata including labels, status, and authorship.
    """
    result = await segmentation_service.get_segmentation(str(segmentation_id))

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Segmentation {segmentation_id} not found"
        )

    return result


@router.patch(
    "/segmentations/{segmentation_id}",
    response_model=SegmentationResponse,
    summary="Update segmentation metadata"
)
async def update_segmentation(
    segmentation_id: UUID = Path(..., description="Segmentation UUID"),
    update: SegmentationUpdate = Body(...),
    current_user: dict = Depends(get_current_user),
    segmentation_service: SegmentationServiceFirestore = Depends(get_segmentation_service_v2)
):
    """
    Update segmentation name or description.

    Does not affect labels or mask data.
    """
    # TODO: Implement update_segmentation in service
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Segmentation update not yet implemented"
    )


@router.patch(
    "/segmentations/{segmentation_id}/status",
    response_model=SegmentationResponse,
    summary="Update segmentation status"
)
async def update_segmentation_status(
    segmentation_id: UUID = Path(..., description="Segmentation UUID"),
    update: SegmentationStatusUpdate = Body(...),
    current_user: dict = Depends(get_current_user),
    segmentation_service: SegmentationServiceFirestore = Depends(get_segmentation_service_v2)
):
    """
    Update segmentation workflow status.

    Status transitions:
    - DRAFT → IN_PROGRESS (automatic on first paint)
    - IN_PROGRESS → PENDING_REVIEW (manual)
    - PENDING_REVIEW → REVIEWED / IN_PROGRESS (reviewer)
    - REVIEWED → APPROVED (supervisor)
    """
    return await segmentation_service.update_status(
        segmentation_id=str(segmentation_id),
        update=update,
        user_id=current_user.get("username", "unknown"),
        user_name=current_user.get("full_name", current_user.get("username", "Unknown")),
    )


@router.delete(
    "/segmentations/{segmentation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete segmentation"
)
async def delete_segmentation(
    segmentation_id: UUID = Path(..., description="Segmentation UUID"),
    current_user: dict = Depends(get_current_user),
    segmentation_service: SegmentationServiceFirestore = Depends(get_segmentation_service_v2)
):
    """
    Delete a segmentation permanently.

    Removes metadata from Firestore and masks from GCS.
    Requires appropriate permissions.
    """
    success = await segmentation_service.delete_segmentation(str(segmentation_id))

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Segmentation {segmentation_id} not found"
        )

    logger.info(
        "Deleted segmentation",
        extra={
            "segmentation_id": str(segmentation_id),
            "deleted_by": current_user.get("username"),
        }
    )


# =============================================================================
# Paint/Edit Endpoints
# =============================================================================

@router.post(
    "/segmentations/{segmentation_id}/paint",
    summary="Apply paint stroke"
)
async def apply_paint_stroke(
    segmentation_id: UUID = Path(..., description="Segmentation UUID"),
    stroke: PaintStroke = Body(...),
    segmentation_service: SegmentationServiceFirestore = Depends(get_segmentation_service_v2)
):
    """
    Apply a single paint stroke to the segmentation mask.

    The stroke specifies position, brush size, and label to paint.
    Erase mode sets voxels to label 0 (background).
    """
    try:
        success = await segmentation_service.apply_paint_stroke(
            segmentation_id=str(segmentation_id),
            stroke=stroke,
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to apply paint stroke"
            )

        return {"success": True}

    except Exception as e:
        logger.error(f"Paint stroke failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/segmentations/{segmentation_id}/paint/batch",
    summary="Apply batch of paint strokes"
)
async def apply_paint_strokes_batch(
    segmentation_id: UUID = Path(..., description="Segmentation UUID"),
    batch: PaintStrokeBatch = Body(...),
    segmentation_service: SegmentationServiceFirestore = Depends(get_segmentation_service_v2)
):
    """
    Apply multiple paint strokes in a single request.

    More efficient than individual stroke requests.
    """
    try:
        for stroke in batch.strokes:
            await segmentation_service.apply_paint_stroke(
                segmentation_id=str(segmentation_id),
                stroke=stroke,
            )

        return {"success": True, "strokes_applied": len(batch.strokes)}

    except Exception as e:
        logger.error(f"Batch paint failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/segmentations/{segmentation_id}/save",
    summary="Save segmentation to persistent storage"
)
async def save_segmentation(
    segmentation_id: UUID = Path(..., description="Segmentation UUID"),
    segmentation_service: SegmentationServiceFirestore = Depends(get_segmentation_service_v2)
):
    """
    Save segmentation to persistent storage (GCS).

    Saves all dirty slices and updates metadata in Firestore.
    """
    success = await segmentation_service.save_segmentation(str(segmentation_id))

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save segmentation"
        )

    return {"success": True, "message": "Segmentation saved"}


# =============================================================================
# Overlay/Visualization Endpoints
# =============================================================================

@router.get(
    "/segmentations/{segmentation_id}/slices/{slice_index}/overlay",
    response_class=Response,
    summary="Get slice overlay as PNG"
)
async def get_slice_overlay(
    segmentation_id: UUID = Path(..., description="Segmentation UUID"),
    slice_index: int = Path(..., ge=0, description="Slice index"),
    labels: Optional[str] = Query(None, description="Comma-separated label IDs to show"),
    t: Optional[int] = Query(None, description="Cache buster timestamp"),
    segmentation_service: SegmentationServiceFirestore = Depends(get_segmentation_service_v2)
):
    """
    Get segmentation overlay for a slice as transparent PNG.

    Returns RGBA PNG with only the segmentation mask (no base image).
    Use CSS to overlay on top of the base medical image.
    """
    try:
        # Parse visible labels
        visible_labels = None
        if labels:
            visible_labels = [int(x.strip()) for x in labels.split(",")]

        overlay_base64 = await segmentation_service.get_slice_overlay(
            segmentation_id=str(segmentation_id),
            slice_index=slice_index,
            visible_labels=visible_labels,
        )

        # Extract base64 data
        if overlay_base64.startswith('data:image/png;base64,'):
            overlay_base64 = overlay_base64[len('data:image/png;base64,'):]

        image_bytes = base64.b64decode(overlay_base64)

        return Response(
            content=image_bytes,
            media_type="image/png",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )

    except Exception as e:
        logger.error(f"Failed to get overlay: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# =============================================================================
# Labels Endpoints
# =============================================================================

@router.put(
    "/segmentations/{segmentation_id}/labels",
    summary="Update label definitions"
)
async def update_labels(
    segmentation_id: UUID = Path(..., description="Segmentation UUID"),
    labels: List[LabelInfo] = Body(...),
    current_user: dict = Depends(get_current_user),
    segmentation_service: SegmentationServiceFirestore = Depends(get_segmentation_service_v2)
):
    """
    Update label definitions for a segmentation.

    Can add, modify, or remove labels.
    Does not affect existing mask data.
    """
    # TODO: Implement label update in service
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Label update not yet implemented"
    )


@router.post(
    "/segmentations/{segmentation_id}/labels",
    status_code=status.HTTP_201_CREATED,
    summary="Add new label"
)
async def add_label(
    segmentation_id: UUID = Path(..., description="Segmentation UUID"),
    label: LabelInfo = Body(...),
    current_user: dict = Depends(get_current_user),
    segmentation_service: SegmentationServiceFirestore = Depends(get_segmentation_service_v2)
):
    """
    Add a new label to the segmentation.

    Label ID must be unique within the segmentation.
    """
    # TODO: Implement add label in service
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Add label not yet implemented"
    )


# =============================================================================
# Statistics Endpoints
# =============================================================================

@router.get(
    "/segmentations/{segmentation_id}/statistics",
    response_model=SegmentationStatistics,
    summary="Get segmentation statistics"
)
async def get_statistics(
    segmentation_id: UUID = Path(..., description="Segmentation UUID"),
    segmentation_service: SegmentationServiceFirestore = Depends(get_segmentation_service_v2)
):
    """
    Calculate and return statistics for a segmentation.

    Includes voxel counts and percentages per label.
    """
    return await segmentation_service.get_statistics(str(segmentation_id))


# =============================================================================
# Export Endpoints
# =============================================================================

@router.post(
    "/segmentations/{segmentation_id}/export",
    response_model=ExportResponse,
    summary="Export segmentation"
)
async def export_segmentation(
    segmentation_id: UUID = Path(..., description="Segmentation UUID"),
    request: ExportRequest = Body(...),
    current_user: dict = Depends(get_current_user),
    segmentation_service: SegmentationServiceFirestore = Depends(get_segmentation_service_v2)
):
    """
    Export segmentation to specified format.

    Supported formats: nifti, dicom_seg, nrrd
    Returns a signed URL for download.
    """
    # TODO: Implement export in service
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Export not yet implemented"
    )
