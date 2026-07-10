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
from app.core.logging import get_logger
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
from app.services.segmentation_comparison_service import (
    compare_two_masks,
    compute_agreement_map,
)
from app.services.lesion_analysis_service import (
    analyze_lesions,
    compute_dis_criteria,
    MAGNIMS_REGIONS,
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
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    current_user: User = Depends(get_current_active_user)
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
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    current_user: User = Depends(get_current_active_user)
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
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    current_user: User = Depends(get_current_active_user)
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
    current_user: User = Depends(get_current_active_user)
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
    storage_service: IStorageService = Depends(get_storage_service),
    current_user: User = Depends(get_current_active_user)
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
    current_user: User = Depends(get_current_active_user)
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
    current_user: User = Depends(get_current_active_user)
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
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    current_user: User = Depends(get_current_active_user)
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
    current_user: User = Depends(get_current_active_user)
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
    ref_file_id: Optional[str] = None,
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    storage_service: IStorageService = Depends(get_storage_service),
    current_user: User = Depends(get_current_active_user),
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

                if seg_shape == ref_shape:
                    # Same shape — just apply reference affine + header
                    result_data = seg_data.astype(np.uint8)
                elif sorted(seg_shape) == sorted(ref_shape):
                    # Same dimensions but different axis order — find permutation
                    perm = []
                    used = [False] * 3
                    for t_dim in ref_shape:
                        for i, s_dim in enumerate(seg_shape):
                            if s_dim == t_dim and not used[i]:
                                perm.append(i)
                                used[i] = True
                                break
                    result_data = np.transpose(seg_data, perm).astype(np.uint8)
                    logger.info("Permuted segmentation axes", extra={
                        "permutation": str(perm),
                        "result_shape": str(result_data.shape),
                    })
                else:
                    # Incompatible shapes — serve original
                    logger.warning("Cannot align: incompatible shapes")
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
    current_user: User = Depends(get_current_active_user)
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
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    current_user: User = Depends(get_current_active_user)
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
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    current_user: User = Depends(get_current_active_user)
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
    current_user: User = Depends(get_current_active_user),
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
                # Load NIfTI from instance — prefer gcs_path (fast) over instance lookup (slow)
                gcs_path = spec.get("gcs_path")
                if not gcs_path:
                    instance = await study_service.get_instance(mask_id)
                    gcs_path = instance.gcs_object_name
                file_data = await storage_service.download_file(
                    settings.GCS_BUCKET_NAME, gcs_path
                )
                _, data = load_nifti_from_bytes(file_data, normalize=False)
                mask = (data > 0).astype(np.uint8)
                if mask.ndim == 3:
                    mask = np.transpose(mask, (2, 1, 0))  # NIfTI (W,H,D) -> (D,H,W)
                loaded_masks.append({"mask": mask, "label": label})
            else:
                raise HTTPException(status_code=400, detail=f"Unknown mask type: {mask_type}")

        # Compute pairwise metrics (skip pairs with shape mismatch)
        comparisons = []
        for i in range(len(loaded_masks)):
            for j in range(i + 1, len(loaded_masks)):
                if loaded_masks[i]["mask"].shape != loaded_masks[j]["mask"].shape:
                    logger.warning(
                        "Shape mismatch in comparison, skipping pair",
                        extra={
                            "label_a": loaded_masks[i]["label"],
                            "label_b": loaded_masks[j]["label"],
                            "shape_a": str(loaded_masks[i]["mask"].shape),
                            "shape_b": str(loaded_masks[j]["mask"].shape),
                        }
                    )
                    comparisons.append({
                        "label_a": loaded_masks[i]["label"],
                        "label_b": loaded_masks[j]["label"],
                        "dice": 0.0,
                        "hausdorff_mm": None,
                        "volume": {
                            "volume_a_mm3": 0,
                            "volume_b_mm3": 0,
                            "diff_percent": 0,
                        },
                        "per_slice_dice": [],
                        "error": f"Shape mismatch: {loaded_masks[i]['mask'].shape} vs {loaded_masks[j]['mask'].shape}",
                    })
                    continue
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
    current_user: User = Depends(get_current_active_user),
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
    current_user: User = Depends(get_current_active_user),
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

        # Stale check — return cached result if mask hasn't changed
        cached = metadata.analysis_data or {}
        mask_mod = metadata.modified_at.isoformat()
        if cached.get("analysis_mask_modified_at") == mask_mod and "lesion_analysis" in cached:
            logger.info("Returning cached lesion analysis for %s", segmentation_id)
            result = dict(cached["lesion_analysis"])
            result["segmentation_id"] = segmentation_id
            return result

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

        # Persist analysis result in metadata
        metadata.analysis_data = {
            **cached,
            "lesion_analysis": result,
            "analysis_mask_modified_at": mask_mod,
        }
        segmentation_service._save_segmentation(segmentation_id)

        logger.info("Lesion analysis completed and cached", extra={
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
    current_user: User = Depends(get_current_active_user),
):
    """
    Evaluate McDonald 2024 DIS (Dissemination in Space) criteria.

    McDonald 2024 (Montalban et al., 2025): DIS requires ≥2 of 5 regions
    (PV, JC, IT, spinal cord, optic nerve). Brain MRI evaluates 3 of 5.
    """
    try:
        if segmentation_id not in segmentation_service.segmentations_cache:
            if not segmentation_service._load_segmentation(segmentation_id):
                raise HTTPException(status_code=404, detail=f"Segmentation {segmentation_id} not found")

        seg_data = segmentation_service.segmentations_cache[segmentation_id]
        masks_3d = seg_data["masks_3d"]
        metadata = seg_data["metadata"]

        # Stale check — return cached result if mask hasn't changed
        cached = metadata.analysis_data or {}
        mask_mod = metadata.modified_at.isoformat()
        if cached.get("analysis_mask_modified_at") == mask_mod and "dis_assessment" in cached:
            logger.info("Returning cached DIS assessment for %s", segmentation_id)
            result = dict(cached["dis_assessment"])
            result["segmentation_id"] = segmentation_id
            return result

        # Build label map
        label_map = {}
        for lbl in metadata.labels:
            if hasattr(lbl, 'id') and hasattr(lbl, 'name'):
                label_map[lbl.id] = lbl.name
            elif isinstance(lbl, dict):
                label_map[lbl.get("id", 0)] = lbl.get("name", f"Label {lbl.get('id', 0)}")

        if not label_map or all(lid == 0 for lid in label_map):
            label_map = MAGNIMS_REGIONS

        # Get voxel spacing for minimum volume filter
        voxel_spacing = (1.0, 1.0, 1.0)
        if hasattr(metadata, 'extra_fields') and metadata.extra_fields:
            ps = metadata.extra_fields.get('pixel_spacing')
            st = metadata.extra_fields.get('slice_thickness')
            if ps and len(ps) >= 2:
                voxel_spacing = (float(st or 1.0), float(ps[0]), float(ps[1]))

        result = compute_dis_criteria(masks_3d, label_map, voxel_spacing)
        result["segmentation_id"] = segmentation_id

        # Persist DIS result in metadata
        metadata.analysis_data = {
            **cached,
            "dis_assessment": result,
            "analysis_mask_modified_at": mask_mod,
        }
        segmentation_service._save_segmentation(segmentation_id)

        logger.info("DIS assessment completed and cached", extra={
            "segmentation_id": segmentation_id,
            "dis_met_brain": result.get("dis_met_brain", False),
            "brain_regions_with_lesions": result.get("brain_regions_with_lesions", 0),
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
# Longitudinal Tracking Endpoints
# =============================================================================

@router.post("/longitudinal/compare")
async def compare_longitudinal(
    request: Request,
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    storage_service: IStorageService = Depends(get_storage_service),
    current_user: User = Depends(get_current_active_user),
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

        logger.info("Longitudinal masks loaded", extra={
            "tp1_shape": str(mask_tp1.shape),
            "tp2_shape": str(mask_tp2.shape),
            "tp1_nonzero": int(np.count_nonzero(mask_tp1)),
            "tp2_nonzero": int(np.count_nonzero(mask_tp2)),
        })

        # Normalize orientation: if shapes differ but sorted dims match, transpose TP2 to match TP1
        if mask_tp1.shape != mask_tp2.shape:
            sorted1 = sorted(mask_tp1.shape)
            sorted2 = sorted(mask_tp2.shape)
            if sorted1 == sorted2:
                # Find the permutation that maps TP2 shape to TP1 shape
                target = mask_tp1.shape
                source = mask_tp2.shape
                perm = []
                used = [False] * len(source)
                for t in target:
                    for i, s in enumerate(source):
                        if s == t and not used[i]:
                            perm.append(i)
                            used[i] = True
                            break
                mask_tp2 = np.transpose(mask_tp2, perm)
                logger.info("Transposed TP2 mask to match TP1", extra={
                    "original_shape": str(source),
                    "new_shape": str(mask_tp2.shape),
                    "permutation": str(perm),
                })
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Mask dimensions incompatible: TP1={mask_tp1.shape} vs TP2={mask_tp2.shape}"
                )

        # Binarize masks (labels > 0 → 1) for comparison
        mask_tp1_bin = (mask_tp1 > 0).astype(np.uint8)
        mask_tp2_bin = (mask_tp2 > 0).astype(np.uint8)

        result = compare_timepoints(mask_tp1_bin, mask_tp2_bin)

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


# =============================================================================
# CVS / PRL Lesion Annotations (McDonald 2024 Biomarkers)
# =============================================================================

@router.post("/{segmentation_id}/lesion-annotations")
async def annotate_lesions(
    segmentation_id: str,
    body: dict,
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    current_user: User = Depends(get_current_active_user),
):
    """
    Save CVS/PRL annotations for individual lesions (McDonald 2024 biomarkers).

    McDonald 2024 (Montalban et al., Lancet Neurology 2025) incorporates
    Central Vein Sign (CVS) and Paramagnetic Rim Lesions (PRL) as diagnostic
    biomarkers. CVS Select-6: >=6 CVS+ lesions. PRL: >=1 positive.

    Body: { annotations: [{ lesion_id, cvs_status, prl_status, notes }] }
    """
    try:
        if segmentation_id not in segmentation_service.segmentations_cache:
            if not segmentation_service._load_segmentation(segmentation_id):
                raise HTTPException(status_code=404, detail=f"Segmentation {segmentation_id} not found")

        seg_data = segmentation_service.segmentations_cache[segmentation_id]
        metadata = seg_data["metadata"]

        annotations = body.get("annotations", [])
        if not annotations:
            raise HTTPException(status_code=400, detail="No annotations provided")

        from datetime import datetime

        # Merge annotations with existing ones
        existing = (metadata.analysis_data or {}).get("lesion_annotations", [])
        existing_map = {a.get("lesion_id"): a for a in existing if isinstance(a, dict)}

        for ann in annotations:
            lesion_id = ann.get("lesion_id")
            if lesion_id is None:
                continue
            existing_map[lesion_id] = {
                "lesion_id": lesion_id,
                "cvs_status": ann.get("cvs_status"),
                "prl_status": ann.get("prl_status"),
                "annotated_by": ann.get("annotated_by", "manual"),
                "annotated_at": datetime.utcnow().isoformat(),
                "notes": ann.get("notes"),
            }

        merged_annotations = list(existing_map.values())

        # Compute CVS summary (McDonald 2024 Select-6 and 40% rule)
        cvs_evaluated = [a for a in merged_annotations if a.get("cvs_status") in ("positive", "negative")]
        cvs_positive = sum(1 for a in cvs_evaluated if a.get("cvs_status") == "positive")
        total_cvs_evaluated = len(cvs_evaluated)
        cvs_summary = {
            "total_evaluated": total_cvs_evaluated,
            "cvs_positive": cvs_positive,
            "cvs_negative": total_cvs_evaluated - cvs_positive,
            "meets_select6": cvs_positive >= 6,
            "meets_40pct": (cvs_positive / total_cvs_evaluated >= 0.4) if total_cvs_evaluated > 0 else False,
        }

        # Compute PRL summary (McDonald 2024: >=1 PRL)
        prl_evaluated = [a for a in merged_annotations if a.get("prl_status") in ("positive", "negative")]
        prl_positive = sum(1 for a in prl_evaluated if a.get("prl_status") == "positive")
        prl_summary = {
            "total_evaluated": len(prl_evaluated),
            "prl_positive": prl_positive,
            "meets_criteria": prl_positive >= 1,
        }

        # Persist in analysis_data
        metadata.analysis_data = {
            **(metadata.analysis_data or {}),
            "lesion_annotations": merged_annotations,
            "cvs_summary": cvs_summary,
            "prl_summary": prl_summary,
        }
        segmentation_service._save_segmentation(segmentation_id)

        logger.info("Lesion annotations saved", extra={
            "segmentation_id": segmentation_id,
            "annotations_count": len(merged_annotations),
            "cvs_positive": cvs_positive,
            "prl_positive": prl_positive,
        })

        return {
            "segmentation_id": segmentation_id,
            "annotations_count": len(merged_annotations),
            "cvs_summary": cvs_summary,
            "prl_summary": prl_summary,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Lesion annotation failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Lesion annotation failed: {str(e)}")


# =============================================================================
# DICOM-SEG Export
# =============================================================================

@router.get("/{segmentation_id}/export/dicom-seg")
async def export_dicom_seg(
    segmentation_id: str,
    segmentation_service: SegmentationService = Depends(get_segmentation_service),
    current_user: User = Depends(get_current_active_user),
):
    """
    Export a segmentation as a DICOM Segmentation (DICOM-SEG) object.

    Returns a binary DICOM file (.dcm) suitable for PACS archival.
    The file uses SOP Class 1.2.840.10008.5.1.4.1.1.66.4 (Segmentation Storage)
    with BINARY segmentation type and per-label segment entries.
    """
    from app.utils.dicom_utils import create_dicom_seg, save_dicom
    import tempfile

    try:
        # Load mask
        if segmentation_id not in segmentation_service.segmentations_cache:
            if not segmentation_service._load_segmentation(segmentation_id):
                raise HTTPException(status_code=404, detail=f"Segmentation {segmentation_id} not found")

        cache_entry = segmentation_service.segmentations_cache[segmentation_id]
        mask_3d = cache_entry["masks_3d"]
        metadata = cache_entry["metadata"]

        # Extract label info
        labels = []
        if hasattr(metadata, 'labels') and metadata.labels:
            labels = [{"id": l.id, "name": l.name, "color": l.color} for l in metadata.labels]
        else:
            # Fallback: detect unique labels
            unique_labels = np.unique(mask_3d)
            labels = [{"id": int(v), "name": f"Label {v}", "color": "#FF0000"} for v in unique_labels if v > 0]

        if not labels:
            raise HTTPException(status_code=400, detail="Segmentation has no labels")

        # Create DICOM-SEG
        description = getattr(metadata, 'description', '') or 'Segmentation'
        ds = create_dicom_seg(
            mask_3d=mask_3d,
            labels=labels,
            study_description=description,
            series_description=description,
        )

        # Serialize to bytes
        with tempfile.NamedTemporaryFile(suffix='.dcm', delete=False) as tmp:
            tmp_path = tmp.name
        save_dicom(ds, tmp_path)
        with open(tmp_path, 'rb') as f:
            dicom_bytes = f.read()
        import os
        os.unlink(tmp_path)

        logger.info("DICOM-SEG export generated", extra={
            "segmentation_id": segmentation_id,
            "labels_count": len(labels),
            "size_bytes": len(dicom_bytes),
        })

        return Response(
            content=dicom_bytes,
            media_type="application/dicom",
            headers={
                "Content-Disposition": f'attachment; filename="{segmentation_id}_seg.dcm"',
                "Content-Length": str(len(dicom_bytes)),
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("DICOM-SEG export failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"DICOM-SEG export failed: {str(e)}")
