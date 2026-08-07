"""
API routes for segmentation operations.
"""

from fastapi import APIRouter, HTTPException, status, Query, Body, Depends, Request
from fastapi.responses import Response
from typing import List, Optional
from datetime import datetime
import numpy as np

import struct

from app.security import get_current_active_user
from app.security.models import User
# CAPA-002 CA-2.1 (RC-029): object-level authorization for segmentations.
from app.security.resource_access import (
    require_segmentation_access,
    authorize_file_scope,
)
from app.security.patient_access_dependency import require_imaging_access
from app.core.container import get_patient_service as _seg_patient_service
from app.core.logging import get_logger


def _seg_care_team_service():
    from app.services.care_team_service import CareTeamService
    return CareTeamService()
from app.models.schemas import (
    LabelInfo,
    PaintStroke,
    SegmentationResponse,
    CreateSegmentationRequest,
)
from app.core.interfaces.imaging_interface import IImagingService
from app.core.interfaces.storage_interface import IStorageService
from app.core.container import get_segmentation_service, get_imaging_service, get_storage_service
from app.services.segmentation_service import SegmentationService
from app.core.config import get_settings

settings = get_settings()

router = APIRouter(prefix="/segmentation", tags=["segmentation"])
logger = get_logger(__name__)


@router.post("/create", response_model=SegmentationResponse)
async def create_segmentation(
    request: CreateSegmentationRequest,
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    current_user: User = Depends(get_current_active_user)
):
    """
    Create a new segmentation for an image file.

    Uses dependency injection to get SegmentationService instance.
    Custom exceptions will be caught by global exception handler.
    """
    try:
        # CAPA-002 CA-2.1 RC-029: a caller may only create a segmentation on an
        # image they can access. Authorizes request.file_id (parse + patient).
        await require_imaging_access(request.file_id, current_user)
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
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    current_user: User = Depends(get_current_active_user)
):
    """
    List all segmentations, optionally filtered by file_id or file_ids.

    - file_id: Filter by a single file_id
    - file_ids: Filter by multiple file_ids (comma-separated), useful for study-level queries

    Uses dependency injection to get SegmentationService instance.
    Custom exceptions will be caught by global exception handler.
    """
    try:
        ids_list = [fid.strip() for fid in file_ids.split(",") if fid.strip()] if file_ids else []
        # CAPA-002 CA-2.1 RC-029: authorize the file_id scope before listing.
        # An unscoped listing across all patients is the bulk form of the defect.
        scope = ids_list if ids_list else ([file_id] if file_id else [])
        await authorize_file_scope(
            file_ids=scope, user=current_user,
            patient_service=_seg_patient_service(),
            care_team_service=_seg_care_team_service(),
        )
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
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    current_user: User = Depends(get_current_active_user),
    # CAPA-002 CA-2.1 RC-029 - object-level authorization.
    _authorized=Depends(require_segmentation_access),
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

        # Get image shape from the cached entry (metadata was already fetched above)
        seg_data = segmentation_service.get_cached(segmentation_id)
        total_slices = seg_data["masks_3d"].shape[0] if seg_data else 0  # D,H,W convention

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
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    current_user: User = Depends(get_current_active_user),
    # CAPA-002 CA-2.1 RC-029 - object-level authorization.
    _authorized=Depends(require_segmentation_access),
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
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    current_user: User = Depends(get_current_active_user),
    # CAPA-002 CA-2.1 RC-029 - object-level authorization.
    _authorized=Depends(require_segmentation_access),
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
        mask_base64 = segmentation_service.array_to_base64(mask)

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
    storage_service: IStorageService = Depends(get_storage_service),
    current_user: User = Depends(get_current_active_user),
    # CAPA-002 CA-2.1 RC-029 - object-level authorization.
    _authorized=Depends(require_segmentation_access),
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
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    current_user: User = Depends(get_current_active_user),
    # CAPA-002 CA-2.1 RC-029 - object-level authorization.
    _authorized=Depends(require_segmentation_access),
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
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    current_user: User = Depends(get_current_active_user),
    # CAPA-002 CA-2.1 RC-029 - object-level authorization.
    _authorized=Depends(require_segmentation_access),
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
        seg_data = segmentation_service.get_cached(segmentation_id)

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
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    current_user: User = Depends(get_current_active_user),
    # CAPA-002 CA-2.1 RC-029 - object-level authorization.
    _authorized=Depends(require_segmentation_access),
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
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    current_user: User = Depends(get_current_active_user),
    # CAPA-002 CA-2.1 RC-029 - object-level authorization.
    _authorized=Depends(require_segmentation_access),
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
        segmentation_service.persist(segmentation_id)

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
    ref_file_id: Optional[str] = None,
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    storage_service: IStorageService = Depends(get_storage_service),
    current_user: User = Depends(get_current_active_user),
    # CAPA-002 CA-2.1 RC-029 - object-level authorization.
    _authorized=Depends(require_segmentation_access),
):
    """
    Serve the segmentation as a raw NIfTI file (.nii.gz) for WebGL-based viewers.

    If ref_file_id is provided, regenerates the NIfTI using the reference MRI's affine matrix,
    ensuring the overlay aligns perfectly with the displayed brain image regardless of how
    the segmentation was originally saved.
    """
    try:
        nifti_data = None

        if ref_file_id:
            import nibabel as nib
            import tempfile, os

            # Load the EXISTING segmentation NIfTI from GCS (not internal mask)
            existing_bytes = segmentation_service.get_segmentation_nifti(segmentation_id)
            if not existing_bytes:
                raise HTTPException(status_code=404, detail=f"Segmentation NIfTI not found for {segmentation_id}")

            # Load reference MRI NIfTI
            ref_blob = segmentation_service.gcs_bucket.blob(ref_file_id)
            if not ref_blob.exists():
                # Fallback: serve original NIfTI as-is
                nifti_data = existing_bytes
            else:
                # Load reference MRI
                ref_buffer = io.BytesIO()
                ref_blob.download_to_file(ref_buffer)
                ref_buffer.seek(0)
                with tempfile.NamedTemporaryFile(suffix='.nii.gz', delete=False) as rtmp:
                    rtmp.write(ref_buffer.read())
                    ref_tmp_path = rtmp.name
                ref_img = nib.load(ref_tmp_path)

                # Load existing segmentation NIfTI
                with tempfile.NamedTemporaryFile(suffix='.nii.gz', delete=False) as stmp:
                    stmp.write(existing_bytes)
                    seg_tmp_path = stmp.name
                seg_img = nib.load(seg_tmp_path)
                seg_data = seg_img.get_fdata()

                ref_shape = ref_img.shape[:3]
                seg_shape = seg_data.shape[:3]

                logger.info("Aligning segmentation to reference", extra={
                    "seg_shape": str(seg_shape),
                    "ref_shape": str(ref_shape),
                    "seg_affine_diag": str(np.diag(seg_img.affine)[:3].tolist()),
                    "ref_affine_diag": str(np.diag(ref_img.affine)[:3].tolist()),
                })

                # RC-031: reorient by the header marker, not a shape-permutation
                # guess. v2 masks are MRI-native; legacy masks are the in-plane
                # transpose. This is deterministic even on square (a0==a1) data,
                # where the greedy permutation could not detect the swap and left
                # legacy overlays mirrored.
                seg_v2 = segmentation_service._header_has_v2_marker(seg_img.header)
                oriented = segmentation_service._seg_native_to_reference_order(seg_data, seg_v2)

                if tuple(oriented.shape[:3]) == tuple(ref_shape):
                    result_data = oriented.astype(np.uint8)
                    logger.info("Aligned segmentation to reference", extra={
                        "rc031_v2": seg_v2,
                        "result_shape": str(result_data.shape),
                    })
                else:
                    # Dimensional mismatch (e.g. different resolution) — serve original
                    logger.warning("Cannot align: incompatible shapes", extra={
                        "seg_shape": str(seg_shape),
                        "ref_shape": str(ref_shape),
                        "rc031_v2": seg_v2,
                    })
                    os.unlink(ref_tmp_path)
                    os.unlink(seg_tmp_path)
                    nifti_data = existing_bytes
                    result_data = None

                if result_data is not None:
                    # Save with reference affine AND full header
                    aligned_img = nib.Nifti1Image(result_data, ref_img.affine, ref_img.header)
                    with tempfile.NamedTemporaryFile(suffix='.nii.gz', delete=False) as otmp:
                        out_path = otmp.name
                    nib.save(aligned_img, out_path)
                    with open(out_path, 'rb') as f:
                        nifti_data = f.read()
                    os.unlink(out_path)
                    logger.info("Generated aligned NIfTI", extra={
                        "size_bytes": len(nifti_data),
                        "shape": str(result_data.shape),
                    })

                os.unlink(ref_tmp_path)
                os.unlink(seg_tmp_path)
        else:
            # Get the segmentation NIfTI from GCS (original orientation)
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
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    current_user: User = Depends(get_current_active_user),
    # CAPA-002 CA-2.1 RC-029 - object-level authorization.
    _authorized=Depends(require_segmentation_access),
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
        # Load segmentation (from cache or durable storage)
        seg_data = segmentation_service.get_loaded(segmentation_id)
        if seg_data is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Segmentation {segmentation_id} not found"
            )
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
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    current_user: User = Depends(get_current_active_user),
    # CAPA-002 CA-2.1 RC-029 - object-level authorization.
    _authorized=Depends(require_segmentation_access),
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
        seg_data = segmentation_service.get_loaded(segmentation_id)
        if seg_data is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Segmentation {segmentation_id} not found"
            )

        # Update the mask in cache
        seg_data["masks_3d"] = masks_3d
        seg_data["metadata"].modified_at = datetime.utcnow()

        # Save to GCS (this is the ONLY time we save during editing)
        segmentation_service.persist(segmentation_id)

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
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    current_user: User = Depends(get_current_active_user),
    # CAPA-002 CA-2.1 RC-029 - object-level authorization.
    _authorized=Depends(require_segmentation_access),
):
    """
    Get segmentation metadata and dimensions without downloading the full mask.

    Useful for the frontend to know the mask dimensions before downloading.
    """
    try:
        # Load segmentation (from cache or durable storage)
        seg_data = segmentation_service.get_loaded(segmentation_id)
        if seg_data is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Segmentation {segmentation_id} not found"
            )
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
