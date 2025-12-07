from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional
import asyncio

from app.core.logging import get_logger
from app.core.config import get_settings
from app.models.schemas import (
    ImageSeriesResponse,
    ImageSlice,
    WindowLevelRequest,
    ImageOrientation
)
from app.core.interfaces.drive_interface import IDriveService
from app.core.interfaces.imaging_interface import IImagingService
from app.core.container import get_drive_service, get_imaging_service, get_prefetch_service
from app.services.prefetch_service import PrefetchService

router = APIRouter(prefix="/imaging", tags=["Medical Imaging"])
logger = get_logger(__name__)
settings = get_settings()


@router.get("/process/{file_id}", response_model=ImageSeriesResponse)
async def process_image(
    file_id: str,
    start_slice: Optional[int] = Query(None, ge=0, description="Start slice index"),
    end_slice: Optional[int] = Query(None, ge=0, description="End slice index"),
    max_slices: int = Query(50, ge=1, le=500, description="Maximum slices to return"),
    drive_service: IDriveService = Depends(get_drive_service),
    imaging_service: IImagingService = Depends(get_imaging_service)
):
    """
    Process a medical image file from Google Drive.
    Returns image metadata and slice data.

    Uses dependency injection to get DriveService and ImagingService instances.
    Custom exceptions will be caught by global exception handler.
    """
    try:
        # Download file from Drive
        file_metadata = await drive_service.get_file_metadata(file_id)
        file_data = await drive_service.download_file(file_id)

        # Determine slice range
        slice_range = None
        if start_slice is not None and end_slice is not None:
            slice_range = (start_slice, end_slice)
        elif start_slice is not None:
            slice_range = (start_slice, start_slice + max_slices)
        elif end_slice is not None:
            slice_range = (max(0, end_slice - max_slices), end_slice)
        else:
            # Return first max_slices slices
            slice_range = (0, max_slices)

        # Process image
        result = await imaging_service.process_image(
            file_data=file_data,
            filename=file_metadata['name'],
            slice_range=slice_range
        )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing image: {str(e)}")


@router.post("/window-level/{file_id}", response_model=ImageSlice)
async def apply_window_level(
    file_id: str,
    request: WindowLevelRequest,
    drive_service: IDriveService = Depends(get_drive_service),
    imaging_service: IImagingService = Depends(get_imaging_service)
):
    """
    Apply window/level adjustment to a specific slice.

    Uses dependency injection to get DriveService and ImagingService instances.
    Custom exceptions will be caught by global exception handler.
    """
    try:
        # Download file
        file_metadata = await drive_service.get_file_metadata(file_id)
        file_data = await drive_service.download_file(file_id)

        # Get slice with windowing
        result = imaging_service.get_slice_with_window(
            file_data=file_data,
            filename=file_metadata['name'],
            slice_index=request.slice_index,
            window_center=request.window_center,
            window_width=request.window_width
        )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error applying window/level: {str(e)}")


@router.get("/slice/{file_id}/{slice_index}", response_model=ImageSlice)
async def get_slice(
    file_id: str,
    slice_index: int,
    window_center: Optional[float] = Query(None, description="Window center"),
    window_width: Optional[float] = Query(None, description="Window width"),
    direction: str = Query("forward", description="Navigation direction: 'forward' or 'backward'"),
    drive_service: IDriveService = Depends(get_drive_service),
    imaging_service: IImagingService = Depends(get_imaging_service),
    prefetch_service: PrefetchService = Depends(get_prefetch_service)
):
    """
    Get a specific slice from an image file.

    Uses dependency injection to get DriveService and ImagingService instances.
    Custom exceptions will be caught by global exception handler.

    FASE 1 Optimization: Intelligent prefetching enabled.
    When a slice is requested, the next N slices are prefetched in the background
    to improve cache hit rate from 80% to 95%.
    """
    try:
        # Download file
        file_metadata = await drive_service.get_file_metadata(file_id)
        file_data = await drive_service.download_file(file_id)

        # Get slice
        result = imaging_service.get_slice_with_window(
            file_data=file_data,
            filename=file_metadata['name'],
            slice_index=slice_index,
            window_center=window_center,
            window_width=window_width
        )

        # FASE 1: Intelligent Prefetching (fire-and-forget)
        # Prefetch next N slices in background based on navigation direction
        if settings.ENABLE_PREFETCHING:
            # Get total slices from metadata
            img_format = imaging_service.detect_format(file_data, file_metadata['name'])
            if img_format.value == "dicom":
                _, metadata = imaging_service.load_dicom(file_data)
            elif img_format.value == "nifti":
                _, metadata = imaging_service.load_nifti(file_data)
            else:
                metadata = {}

            total_slices = metadata.get('slices', 0)

            # Fire-and-forget prefetching (don't await)
            asyncio.create_task(
                prefetch_service.prefetch_slices(
                    file_id=file_id,
                    current_slice=slice_index,
                    total_slices=total_slices,
                    direction=direction
                )
            )

            logger.debug(
                "Prefetching triggered",
                extra={
                    "file_id": file_id,
                    "current_slice": slice_index,
                    "total_slices": total_slices,
                    "direction": direction
                }
            )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting slice: {str(e)}")


@router.get("/volume/{file_id}")
async def get_3d_volume(
    file_id: str,
    orientation: ImageOrientation = Query(ImageOrientation.AXIAL, description="Volume orientation"),
    drive_service: IDriveService = Depends(get_drive_service),
    imaging_service: IImagingService = Depends(get_imaging_service)
):
    """
    Get 3D volume data for rendering.
    Warning: This can be memory intensive for large volumes.

    Uses dependency injection to get DriveService and ImagingService instances.
    Custom exceptions will be caught by global exception handler.
    """
    try:
        # Download file
        file_metadata = await drive_service.get_file_metadata(file_id)
        file_data = await drive_service.download_file(file_id)

        # Generate 3D volume
        result = imaging_service.generate_3d_volume(
            file_data=file_data,
            filename=file_metadata['name'],
            orientation=orientation
        )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating 3D volume: {str(e)}")


@router.get("/metadata/{file_id}")
async def get_image_metadata(
    file_id: str,
    drive_service: IDriveService = Depends(get_drive_service),
    imaging_service: IImagingService = Depends(get_imaging_service)
):
    """
    Get only metadata from an image file without loading pixel data.

    Uses dependency injection to get DriveService and ImagingService instances.
    Custom exceptions will be caught by global exception handler.
    """
    try:
        # Download file
        file_metadata = await drive_service.get_file_metadata(file_id)
        file_data = await drive_service.download_file(file_id)

        # Detect format and load metadata only
        img_format = imaging_service.detect_format(file_data, file_metadata['name'])

        if img_format.value == "dicom":
            _, metadata = imaging_service.load_dicom(file_data)
        elif img_format.value == "nifti":
            _, metadata = imaging_service.load_nifti(file_data)
        else:
            raise ValueError("Unsupported format")

        return {
            "format": img_format,
            "metadata": metadata,
            "file_info": file_metadata
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting metadata: {str(e)}")


@router.get("/voxel-3d/{file_id}")
async def get_voxel_3d_visualization(
    file_id: str,
    start_slice: Optional[int] = Query(None, ge=0, description="Start slice index"),
    end_slice: Optional[int] = Query(None, ge=0, description="End slice index"),
    angle: int = Query(320, ge=0, le=360, description="Viewing angle"),
    drive_service: IDriveService = Depends(get_drive_service),
    imaging_service: IImagingService = Depends(get_imaging_service)
):
    """
    Generate a 3D voxel visualization using matplotlib.
    Returns a base64 encoded PNG image.

    Uses dependency injection to get DriveService and ImagingService instances.
    Custom exceptions will be caught by global exception handler.
    """
    try:
        # Download file
        file_metadata = await drive_service.get_file_metadata(file_id)
        file_data = await drive_service.download_file(file_id)

        # Determine slice range
        slice_range = None
        if start_slice is not None and end_slice is not None:
            slice_range = (start_slice, end_slice)

        # Generate 3D voxel visualization
        img_b64 = imaging_service.generate_3d_voxel_visualization(
            file_data=file_data,
            filename=file_metadata['name'],
            slice_range=slice_range,
            angle=angle
        )

        return {"image": img_b64}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating 3D visualization: {str(e)}")


@router.get("/matplotlib-2d/{file_id}/{slice_index}")
async def get_matplotlib_2d_slice(
    file_id: str,
    slice_index: int,
    window_center: Optional[float] = Query(None, description="Window center for contrast adjustment"),
    window_width: Optional[float] = Query(None, description="Window width for contrast adjustment"),
    colormap: str = Query('gray', description="Matplotlib colormap (gray, viridis, hot, cool, bone, etc.)"),
    x_min: Optional[int] = Query(None, ge=0, description="X-axis lower limit (pixels)"),
    x_max: Optional[int] = Query(None, ge=0, description="X-axis upper limit (pixels)"),
    y_min: Optional[int] = Query(None, ge=0, description="Y-axis lower limit (pixels)"),
    y_max: Optional[int] = Query(None, ge=0, description="Y-axis upper limit (pixels)"),
    minimal: bool = Query(False, description="If True, renders only image data without axes/labels/colorbar for segmentation overlay"),
    segmentation_id: Optional[str] = Query(None, description="If provided, overlay segmentation on the matplotlib image"),
    drive_service: IDriveService = Depends(get_drive_service),
    imaging_service: IImagingService = Depends(get_imaging_service)
):
    """
    Generate a 2D slice visualization using matplotlib with colormap and axis limits support.
    Returns a base64 encoded PNG image.

    When minimal=True, the output image contains only the pixel data without any decorative elements,
    ensuring perfect voxel coordinate alignment for segmentation overlay.

    When segmentation_id is provided, the segmentation will be overlaid on the image using matplotlib,
    ensuring perfect voxel coordinate alignment.

    Uses dependency injection to get DriveService and ImagingService instances.
    Custom exceptions will be caught by global exception handler.
    """
    try:
        # Log received parameters
        logger.debug(
            "Matplotlib 2D visualization request",
            extra={
                "file_id": file_id,
                "slice_index": slice_index,
                "x_min": x_min,
                "x_max": x_max,
                "y_min": y_min,
                "y_max": y_max,
                "colormap": colormap,
                "minimal": minimal,
                "segmentation_id": segmentation_id,
                "window_center": window_center,
                "window_width": window_width
            }
        )

        # Download file
        file_metadata = await drive_service.get_file_metadata(file_id)
        file_data = await drive_service.download_file(file_id)

        # Generate 2D matplotlib visualization
        result = await imaging_service.generate_2d_matplotlib_slice(
            file_data=file_data,
            filename=file_metadata['name'],
            slice_index=slice_index,
            window_center=window_center,
            window_width=window_width,
            colormap=colormap,
            x_min=x_min,
            x_max=x_max,
            y_min=y_min,
            y_max=y_max,
            minimal=minimal,
            segmentation_id=segmentation_id
        )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating 2D matplotlib visualization: {str(e)}")

