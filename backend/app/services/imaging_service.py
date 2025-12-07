import io
import base64
import tempfile
import os
import hashlib
import numpy as np
from typing import Optional, List, Tuple
from datetime import timedelta
import pydicom
import nibabel as nib
from PIL import Image
import SimpleITK as sitk

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.exceptions import ImageProcessingException, ValidationException
from app.core.interfaces.imaging_interface import IImagingService
from app.core.interfaces.cache_interface import ICacheService
from app.models.schemas import (
    ImageMetadata,
    ImageSlice,
    ImageFormat,
    ImageSeriesResponse,
    ImageOrientation
)

# Import shared utilities
from app.utils import (
    normalize_to_uint8,
    array_to_base64,
    load_nifti_from_bytes,
    extract_nifti_metadata
)

logger = get_logger(__name__)


class ImagingService(IImagingService):
    """Service for processing medical images."""

    def __init__(self, cache_service: Optional[ICacheService] = None):
        self.cache = cache_service
        self.settings = get_settings()

    def _generate_file_hash(self, file_data: bytes) -> str:
        """Generate a hash for file data to use in cache keys."""
        return hashlib.md5(file_data).hexdigest()

    def detect_format(self, file_data: bytes, filename: str) -> ImageFormat:
        """Detect the format of the medical image."""
        if filename.endswith('.dcm'):
            return ImageFormat.DICOM
        elif filename.endswith('.nii') or filename.endswith('.nii.gz'):
            return ImageFormat.NIFTI
        else:
            # Try to detect by content
            try:
                pydicom.dcmread(io.BytesIO(file_data))
                return ImageFormat.DICOM
            except:
                try:
                    nib.load(io.BytesIO(file_data))
                    return ImageFormat.NIFTI
                except:
                    raise ValidationException(
                        message="Unsupported image format - file must be DICOM or NIfTI",
                        error_code="UNSUPPORTED_IMAGE_FORMAT",
                        details={"filename": filename}
                    )

    def load_dicom(self, file_data: bytes) -> Tuple[np.ndarray, ImageMetadata]:
        """Load DICOM file and extract metadata."""
        try:
            ds = pydicom.dcmread(io.BytesIO(file_data))

            # Get pixel array
            pixel_array = ds.pixel_array

            # Normalize to 8-bit if needed
            if pixel_array.dtype != np.uint8:
                pixel_array = normalize_to_uint8(pixel_array)

            # Extract metadata
            metadata = ImageMetadata(
                patient_id=str(ds.get('PatientID', '')),
                patient_name=str(ds.get('PatientName', '')),
                study_date=str(ds.get('StudyDate', '')),
                study_description=str(ds.get('StudyDescription', '')),
                series_description=str(ds.get('SeriesDescription', '')),
                modality=str(ds.get('Modality', '')),
                manufacturer=str(ds.get('Manufacturer', '')),
                institution_name=str(ds.get('InstitutionName', '')),
                rows=int(ds.get('Rows', 0)),
                columns=int(ds.get('Columns', 0)),
                slices=1,
                pixel_spacing=[float(x) for x in ds.get('PixelSpacing', [1.0, 1.0])],
                slice_thickness=float(ds.get('SliceThickness', 1.0)),
                window_center=float(ds.get('WindowCenter', 0)) if 'WindowCenter' in ds else None,
                window_width=float(ds.get('WindowWidth', 0)) if 'WindowWidth' in ds else None
            )

            return pixel_array, metadata

        except ImageProcessingException:
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            raise ImageProcessingException(
                message="Failed to load DICOM file",
                error_code="DICOM_LOAD_ERROR",
                status_code=500,
                details={
                    "original_error": str(e),
                    "error_type": type(e).__name__
                }
            )

    def load_nifti(self, file_data: bytes) -> Tuple[np.ndarray, ImageMetadata]:
        """Load NIfTI file and extract metadata using utility functions."""
        try:
            # Load using utility function (includes temp file handling)
            img, data = load_nifti_from_bytes(file_data, normalize=True)

            # Extract metadata
            header = img.header
            pixdim = header.get_zooms()

            metadata = ImageMetadata(
                rows=data.shape[0] if len(data.shape) > 0 else 0,
                columns=data.shape[1] if len(data.shape) > 1 else 0,
                slices=data.shape[2] if len(data.shape) > 2 else 1,
                pixel_spacing=[float(pixdim[0]), float(pixdim[1])] if len(pixdim) > 1 else [1.0, 1.0],
                slice_thickness=float(pixdim[2]) if len(pixdim) > 2 else 1.0,
                modality="MRI"
            )

            return data, metadata

        except ImageProcessingException:
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            raise ImageProcessingException(
                message="Failed to load NIfTI file",
                error_code="NIFTI_LOAD_ERROR",
                status_code=500,
                details={
                    "original_error": str(e),
                    "error_type": type(e).__name__
                }
            )

    async def process_image(
        self,
        file_data: bytes,
        filename: str,
        slice_range: Optional[Tuple[int, int]] = None
    ) -> ImageSeriesResponse:
        """Process medical image file with caching."""
        # Generate cache key
        file_hash = self._generate_file_hash(file_data)
        slice_range_str = f"{slice_range[0]}-{slice_range[1]}" if slice_range else "all"
        cache_key = f"imaging:processed:{file_hash}:{slice_range_str}"

        # Try cache first
        if self.cache:
            cached_response = await self.cache.get(cache_key)
            if cached_response:
                logger.debug(
                    "Cache hit for processed image",
                    extra={"file_name": filename, "cache_key": cache_key}
                )
                # Reconstruct ImageSeriesResponse from cached dict
                return ImageSeriesResponse(**cached_response)

        # Detect format
        img_format = self.detect_format(file_data, filename)

        # Load image based on format
        if img_format == ImageFormat.DICOM:
            pixel_array, metadata = self.load_dicom(file_data)
            # DICOM is usually 2D
            if len(pixel_array.shape) == 2:
                pixel_array = np.expand_dims(pixel_array, axis=2)
        elif img_format == ImageFormat.NIFTI:
            pixel_array, metadata = self.load_nifti(file_data)
        else:
            raise ValidationException(
                message="Unsupported image format",
                error_code="UNSUPPORTED_IMAGE_FORMAT",
                details={"format": str(img_format)}
            )

        # Ensure 3D array
        if len(pixel_array.shape) == 2:
            pixel_array = np.expand_dims(pixel_array, axis=2)

        total_slices = pixel_array.shape[2]
        metadata.slices = total_slices

        # Determine slice range
        if slice_range:
            start_slice, end_slice = slice_range
            start_slice = max(0, start_slice)
            end_slice = min(total_slices, end_slice)
        else:
            # By default, return all slices (can be memory intensive)
            start_slice = 0
            end_slice = total_slices

        # Generate slices
        slices = []
        for i in range(start_slice, end_slice):
            slice_data = pixel_array[:, :, i]
            image_b64 = array_to_base64(slice_data, mode='L', include_data_url_prefix=False)

            slices.append(ImageSlice(
                slice_index=i,
                image_data=image_b64,
                format=img_format,
                width=slice_data.shape[1],
                height=slice_data.shape[0],
                window_center=metadata.window_center,
                window_width=metadata.window_width
            ))

        response = ImageSeriesResponse(
            id=filename,
            name=filename,
            format=img_format,
            metadata=metadata,
            total_slices=total_slices,
            slices=slices
        )

        # Store in cache
        if self.cache:
            await self.cache.set(
                cache_key,
                response.model_dump(),
                ttl=timedelta(seconds=self.settings.CACHE_IMAGES_TTL)
            )
            logger.debug(
                "Cached processed image",
                extra={"file_name": filename, "slices_count": len(slices), "cache_key": cache_key}
            )

        return response

    def apply_window_level(
        self,
        pixel_array: np.ndarray,
        window_center: float,
        window_width: float
    ) -> np.ndarray:
        """Apply window/level adjustment to pixel array."""
        img_min = window_center - window_width // 2
        img_max = window_center + window_width // 2

        windowed = np.clip(pixel_array, img_min, img_max)
        windowed = ((windowed - img_min) / (img_max - img_min) * 255.0).astype(np.uint8)

        return windowed

    async def get_slice_with_window(
        self,
        file_data: bytes,
        filename: str,
        slice_index: int,
        window_center: Optional[float] = None,
        window_width: Optional[float] = None
    ) -> ImageSlice:
        """Get a specific slice with window/level adjustment with caching."""
        # Generate cache key
        file_hash = self._generate_file_hash(file_data)
        wc_str = f"{window_center:.1f}" if window_center is not None else "auto"
        ww_str = f"{window_width:.1f}" if window_width is not None else "auto"
        cache_key = f"imaging:slice:{file_hash}:{slice_index}:wc{wc_str}:ww{ww_str}"

        # Try cache first
        if self.cache:
            cached_slice = await self.cache.get(cache_key)
            if cached_slice:
                logger.debug(
                    "Cache hit for image slice",
                    extra={"file_name": filename, "slice_index": slice_index, "cache_key": cache_key}
                )
                return ImageSlice(**cached_slice)

        img_format = self.detect_format(file_data, filename)

        if img_format == ImageFormat.DICOM:
            pixel_array, metadata = self.load_dicom(file_data)
        elif img_format == ImageFormat.NIFTI:
            pixel_array, metadata = self.load_nifti(file_data)
        else:
            raise ValidationException(
                message="Unsupported image format for slice range extraction",
                error_code="UNSUPPORTED_IMAGE_FORMAT",
                details={"format": str(img_format)}
            )

        # Ensure 3D
        if len(pixel_array.shape) == 2:
            pixel_array = np.expand_dims(pixel_array, axis=2)

        # Get slice
        slice_data = pixel_array[:, :, slice_index]

        # Apply window/level if specified
        if window_center is not None and window_width is not None:
            slice_data = self.apply_window_level(slice_data, window_center, window_width)

        image_b64 = array_to_base64(slice_data, mode='L', include_data_url_prefix=False)

        slice_result = ImageSlice(
            slice_index=slice_index,
            image_data=image_b64,
            format=img_format,
            width=slice_data.shape[1],
            height=slice_data.shape[0],
            window_center=window_center or metadata.window_center,
            window_width=window_width or metadata.window_width
        )

        # Store in cache
        if self.cache:
            await self.cache.set(
                cache_key,
                slice_result.model_dump(),
                ttl=timedelta(seconds=self.settings.CACHE_IMAGES_TTL)
            )
            logger.debug(
                "Cached image slice",
                extra={"file_name": filename, "slice_index": slice_index, "cache_key": cache_key}
            )

        return slice_result

    def generate_3d_volume(
        self,
        file_data: bytes,
        filename: str,
        orientation: ImageOrientation = ImageOrientation.AXIAL
    ) -> dict:
        """Generate 3D volume data for rendering."""
        img_format = self.detect_format(file_data, filename)

        if img_format == ImageFormat.DICOM:
            pixel_array, metadata = self.load_dicom(file_data)
        elif img_format == ImageFormat.NIFTI:
            pixel_array, metadata = self.load_nifti(file_data)
        else:
            raise ValueError("Unsupported format")

        # Reorient based on requested orientation
        if orientation == ImageOrientation.SAGITTAL:
            pixel_array = np.transpose(pixel_array, (2, 1, 0))
        elif orientation == ImageOrientation.CORONAL:
            pixel_array = np.transpose(pixel_array, (0, 2, 1))

        # Convert to list for JSON serialization
        volume_data = pixel_array.tolist()

        return {
            "volume": volume_data,
            "shape": pixel_array.shape,
            "orientation": orientation,
            "metadata": metadata.dict()
        }

    def generate_3d_voxel_visualization(
        self,
        file_data: bytes,
        filename: str,
        slice_range: tuple = None,
        angle: int = 320
    ) -> str:
        """OPTIMIZED matplotlib 3D voxel visualization - renders in <15 seconds."""
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d import Axes3D
        from matplotlib import cm
        from skimage.transform import resize

        # Load the image data
        img_format = self.detect_format(file_data, filename)

        if img_format == ImageFormat.DICOM:
            pixel_array, metadata = self.load_dicom(file_data)
        elif img_format == ImageFormat.NIFTI:
            pixel_array, metadata = self.load_nifti(file_data)
        else:
            raise ValueError("Unsupported format")

        # Use center portion of volume
        depth = pixel_array.shape[0]
        start_idx = depth // 4
        end_idx = 3 * depth // 4
        pixel_array = pixel_array[start_idx:end_idx, :, :]

        # OPTIMIZATION 1: Resize to 20x20x20 for fast rendering (~8k voxels)
        pixel_array = resize(pixel_array, (20, 20, 20), mode='constant', anti_aliasing=True)

        # Normalize
        arr_min = np.min(pixel_array)
        arr_max = np.max(pixel_array)
        if arr_max > arr_min:
            pixel_array = (pixel_array - arr_min) / (arr_max - arr_min)

        # OPTIMIZATION 2: NO explode - keeps voxel count low
        # Create face colors with transparency (like your original code)
        facecolors = cm.gray(pixel_array)
        facecolors[:, :, :, -1] = pixel_array  # Alpha channel

        # OPTIMIZATION 3: Only render voxels with meaningful values
        filled = pixel_array > 0.15  # Threshold to show only brain tissue

        # Create voxel coordinates
        x, y, z = np.indices(np.array(filled.shape) + 1)

        # Create figure
        fig = plt.figure(figsize=(10, 10))
        ax = fig.add_subplot(111, projection='3d')

        # Set view angle
        ax.view_init(30, angle)

        # OPTIMIZATION 4: Plot voxels - with reduced count this is fast
        ax.voxels(x, y, z, filled, facecolors=facecolors, edgecolors=None)

        # Remove axes for clean look
        ax.set_axis_off()
        
        # Set limits
        ax.set_xlim(0, 20)
        ax.set_ylim(0, 20)
        ax.set_zlim(0, 20)

        # Convert to base64
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', bbox_inches='tight', dpi=150, facecolor='black')
        plt.close(fig)
        buffer.seek(0)
        img_b64 = base64.b64encode(buffer.read()).decode('utf-8')

        return f"data:image/png;base64,{img_b64}"

    def get_slice_2d(
        self,
        file_data: bytes,
        filename: str,
        slice_index: int,
        orientation: ImageOrientation = ImageOrientation.AXIAL,
        window_center: Optional[float] = None,
        window_width: Optional[float] = None
    ) -> ImageSlice:
        """Get a single 2D slice from a medical image - sync version of get_slice_with_window."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(
            self.get_slice_with_window(file_data, filename, slice_index, window_center, window_width)
        )

    async def visualize_with_matplotlib_2d(
        self,
        file_data: bytes,
        filename: str,
        slice_index: int,
        x_min: Optional[int] = None,
        x_max: Optional[int] = None,
        y_min: Optional[int] = None,
        y_max: Optional[int] = None,
        colormap: str = 'gray',
        minimal: bool = False,
        segmentation_data: Optional[bytes] = None,
        segmentation_id: Optional[str] = None,
        window_center: Optional[float] = None,
        window_width: Optional[float] = None
    ) -> bytes:
        """Generate a matplotlib visualization of a 2D slice - returns bytes instead of str."""
        result = await self.generate_2d_matplotlib_slice(
            file_data=file_data,
            filename=filename,
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
        # Convert data URL string to bytes
        if isinstance(result, dict):
            # If result has bbox, return just the image
            data_url = result['image']
        else:
            data_url = result

        # Extract base64 part and decode to bytes
        if data_url.startswith('data:image/png;base64,'):
            b64_data = data_url.replace('data:image/png;base64,', '')
            return base64.b64decode(b64_data)
        return b''

    async def generate_2d_matplotlib_slice(
        self,
        file_data: bytes,
        filename: str,
        slice_index: int,
        window_center: Optional[float] = None,
        window_width: Optional[float] = None,
        colormap: str = 'gray',
        x_min: Optional[int] = None,
        x_max: Optional[int] = None,
        y_min: Optional[int] = None,
        y_max: Optional[int] = None,
        minimal: bool = False,
        segmentation_id: Optional[str] = None
    ) -> str:
        """Generate a 2D slice visualization using matplotlib with axis limits support.

        Args:
            minimal: If True, renders only the image data without axes, labels, grid, or colorbar.
                    Perfect for segmentation overlay where voxel coordinates must match exactly.
            segmentation_id: If provided, overlay the segmentation on the image using matplotlib.
        """
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        # Load the image data
        img_format = self.detect_format(file_data, filename)

        if img_format == ImageFormat.DICOM:
            pixel_array, metadata = self.load_dicom(file_data)
        elif img_format == ImageFormat.NIFTI:
            pixel_array, metadata = self.load_nifti(file_data)
        else:
            raise ValidationException(
                message="Unsupported image format for slice range extraction",
                error_code="UNSUPPORTED_IMAGE_FORMAT",
                details={"format": str(img_format)}
            )

        # Ensure 3D
        if len(pixel_array.shape) == 2:
            pixel_array = np.expand_dims(pixel_array, axis=2)

        # Get slice
        slice_data = pixel_array[:, :, slice_index]

        # Get image dimensions
        img_height, img_width = slice_data.shape

        # Store original data for colorbar
        original_min = np.min(slice_data)
        original_max = np.max(slice_data)

        # Apply window/level if specified
        if window_center is not None and window_width is not None:
            slice_data = self.apply_window_level(slice_data, window_center, window_width)
            vmin, vmax = 0, 255
        else:
            # Keep original values - do NOT modify voxel intensities
            vmin, vmax = original_min, original_max

        # If minimal mode, render only the image data without any decorations
        # This ensures perfect voxel coordinate alignment for segmentation overlay
        if minimal:
            # Apply cropping if specified
            if x_min is not None or x_max is not None or y_min is not None or y_max is not None:
                x_start = max(0, x_min if x_min is not None else 0)
                x_end = min(img_width, x_max if x_max is not None else img_width)
                y_start = max(0, y_min if y_min is not None else 0)
                y_end = min(img_height, y_max if y_max is not None else img_height)
                slice_data = slice_data[y_start:y_end, x_start:x_end]

            # Get dimensions of the data to render
            data_height, data_width = slice_data.shape
            logger.debug("Original voxel dimensions: {data_width}x{data_height}")

            # Calculate figure size to match data dimensions exactly
            # Use high DPI for crisp rendering
            dpi = 100
            figsize = (data_width / dpi, data_height / dpi)
            logger.debug("Figure size: {figsize}, DPI: {dpi}")

            # Create figure with no frame
            fig = plt.figure(figsize=figsize, dpi=dpi, frameon=False)

            # Add axes that fill the entire figure [left, bottom, width, height]
            ax = fig.add_axes([0, 0, 1, 1])
            ax.axis('off')  # Turn off all axes decorations

            # Render image data only with 'none' interpolation for exact pixel mapping
            ax.imshow(slice_data, cmap=colormap, interpolation='none',
                     vmin=vmin, vmax=vmax, aspect='equal', origin='upper')

            # Overlay segmentation if provided
            if segmentation_id:
                from app.services.segmentation_service import segmentation_service
                from matplotlib.colors import ListedColormap
                try:
                    logger.debug("Overlaying segmentation {segmentation_id} on slice {slice_index}")
                    # Get segmentation data for this slice
                    seg_slice = await segmentation_service.get_slice_mask(segmentation_id, slice_index)

                    if seg_slice is not None:
                        logger.debug("Seg slice shape: {seg_slice.shape}, has data: {np.any(seg_slice > 0)}, unique values: {np.unique(seg_slice)}")
                        if np.any(seg_slice > 0):
                            # Apply same cropping to segmentation
                            if x_min is not None or x_max is not None or y_min is not None or y_max is not None:
                                seg_slice = seg_slice[y_start:y_end, x_start:x_end]

                            # Create a masked array where 0 values are transparent
                            seg_masked = np.ma.masked_where(seg_slice == 0, seg_slice)

                            # Create red colormap for segmentation (same as standard mode)
                            red_cmap = ListedColormap(['red'])
                            # Overlay segmentation with transparency
                            ax.imshow(seg_masked, cmap=red_cmap, interpolation='none',
                                     alpha=0.5, aspect='equal', origin='upper', vmin=0, vmax=1)
                            logger.debug("Successfully overlayed segmentation")
                        else:
                            logger.debug("Segmentation slice is empty")
                    else:
                        logger.debug("No segmentation data found for slice {slice_index}")
                except Exception as e:
                    logger.warning(
                        "Could not overlay segmentation on matplotlib image",
                        extra={"segmentation_id": segmentation_id, "slice_index": slice_index, "error": str(e)}
                    )

            # Save without any padding - output image will be exactly data_width x data_height pixels
            buffer = io.BytesIO()
            # Use bbox_inches=None to avoid any automatic cropping/padding
            plt.savefig(buffer, format='png', dpi=dpi, bbox_inches=None,
                       pad_inches=0, facecolor='black')
            plt.close(fig)
            buffer.seek(0)
            img_b64 = base64.b64encode(buffer.read()).decode('utf-8')

            return {"image": f"data:image/png;base64,{img_b64}"}

        # Crop the image if limits are specified
        if x_min is not None or x_max is not None or y_min is not None or y_max is not None:
            # Default to full range if not specified
            x_start = max(0, x_min if x_min is not None else 0)
            x_end = min(img_width, x_max if x_max is not None else img_width)
            y_start = max(0, y_min if y_min is not None else 0)
            y_end = min(img_height, y_max if y_max is not None else img_height)

            # Crop to show only these voxels
            cropped_slice = slice_data[y_start:y_end, x_start:x_end]

            # Calculate figure size based on cropped dimensions to maintain aspect ratio
            crop_width = x_end - x_start
            crop_height = y_end - y_start
            aspect_ratio = crop_width / crop_height if crop_height > 0 else 1

            # Use larger base size for better voxel visibility
            if aspect_ratio > 1:
                figsize = (14, 14 / aspect_ratio)
            else:
                figsize = (14 * aspect_ratio, 14)

            fig = plt.figure(figsize=figsize, facecolor='black')
            # Create axes that fill most of the figure (leave space for colorbar on right)
            ax = fig.add_axes([0, 0, 0.85, 1])  # [left, bottom, width, height] in figure coordinates
            ax.set_facecolor('black')

            # Display cropped region with 'equal' aspect to preserve voxel squares
            im = ax.imshow(cropped_slice, cmap=colormap, interpolation='none', vmin=vmin, vmax=vmax,
                          extent=[x_start, x_end, y_end, y_start], origin='upper', aspect='equal')

            # Set axis limits to exactly match the cropped region
            ax.set_xlim(x_start, x_end)
            ax.set_ylim(y_end, y_start)

            # Overlay segmentation if provided (for cropped view)
            if segmentation_id:
                from app.services.segmentation_service import segmentation_service
                from matplotlib.colors import ListedColormap
                try:
                    logger.debug("Overlaying segmentation {segmentation_id} on slice {slice_index} (cropped)")
                    seg_slice = await segmentation_service.get_slice_mask(segmentation_id, slice_index)

                    if seg_slice is not None and np.any(seg_slice > 0):
                        # Crop segmentation to match image crop
                        seg_cropped = seg_slice[y_start:y_end, x_start:x_end]
                        if np.any(seg_cropped > 0):
                            seg_masked = np.ma.masked_where(seg_cropped == 0, seg_cropped)
                            # Create red colormap for segmentation (same as standard mode)
                            red_cmap = ListedColormap(['red'])
                            ax.imshow(seg_masked, cmap=red_cmap, interpolation='none',
                                     alpha=0.5, extent=[x_start, x_end, y_end, y_start],
                                     origin='upper', aspect='equal', vmin=0, vmax=1)
                            logger.debug("Successfully overlayed segmentation (cropped)")
                except Exception as e:
                    logger.debug("Warning: Could not overlay segmentation: {e}")

            # Enable axes with white labels and ticks
            ax.set_xlabel('X (pixels)', color='white', fontsize=10)
            ax.set_ylabel('Y (pixels)', color='white', fontsize=10)
            ax.tick_params(colors='white', labelsize=8, direction='out', length=4, width=1)

            # Show grid lines
            ax.grid(True, color='white', alpha=0.3, linewidth=0.5, linestyle='--')

            # Style spines (axis borders)
            for spine in ax.spines.values():
                spine.set_edgecolor('white')
                spine.set_linewidth(1)
        else:
            # Show full image with figsize calculated to match voxel dimensions
            # Use same DPI as minimal mode for consistency
            dpi = 100
            # Calculate figure size to maintain 1:1 voxel-to-pixel ratio
            # Leave extra space for axes, labels, and colorbar
            fig_width = (img_width + 100) / dpi  # Add 100px for colorbar and margins
            fig_height = (img_height + 80) / dpi  # Add 80px for title and labels

            fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=dpi, facecolor='black')
            im = ax.imshow(slice_data, cmap=colormap, interpolation='none', vmin=vmin, vmax=vmax,
                          extent=[0, img_width, img_height, 0], origin='upper', aspect='equal')

            # Overlay segmentation if provided (for full view)
            if segmentation_id:
                from app.services.segmentation_service import segmentation_service
                from matplotlib.colors import ListedColormap
                try:
                    logger.debug("Overlaying segmentation {segmentation_id} on slice {slice_index} (full)")
                    seg_slice = await segmentation_service.get_slice_mask(segmentation_id, slice_index)

                    if seg_slice is not None and np.any(seg_slice > 0):
                        seg_masked = np.ma.masked_where(seg_slice == 0, seg_slice)
                        # Create red colormap for segmentation (same as standard mode)
                        red_cmap = ListedColormap(['red'])
                        ax.imshow(seg_masked, cmap=red_cmap, interpolation='none',
                                 alpha=0.5, extent=[0, img_width, img_height, 0],
                                 origin='upper', aspect='auto', vmin=0, vmax=1)
                        logger.debug("Successfully overlayed segmentation (full)")
                except Exception as e:
                    logger.debug("Warning: Could not overlay segmentation: {e}")

            # Enable axes with white labels for full image
            ax.set_xlabel('X (pixels)', color='white', fontsize=12)
            ax.set_ylabel('Y (pixels)', color='white', fontsize=12)
            ax.set_title(f'Slice {slice_index}', color='white', fontsize=14, pad=10)
            ax.tick_params(colors='white', labelsize=10, direction='out', length=4, width=1)

            # Show grid lines
            ax.grid(True, color='white', alpha=0.3, linewidth=0.5, linestyle='--')

            # Style spines (axis borders)
            for spine in ax.spines.values():
                spine.set_edgecolor('white')
                spine.set_linewidth(1)

        # Add colorbar with voxel intensity scale
        if x_min is not None or x_max is not None or y_min is not None or y_max is not None:
            # For cropped image with custom axes positioning, create colorbar manually
            cbar_ax = fig.add_axes([0.87, 0.1, 0.03, 0.8])  # [left, bottom, width, height]
            cbar = plt.colorbar(im, cax=cbar_ax)
            cbar.set_label('Voxel Intensity', color='white', fontsize=12)
            cbar.ax.tick_params(colors='white', labelsize=10)
            
        else:
            # For full image, use standard colorbar
            cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
            cbar.set_label('Voxel Intensity', color='white', fontsize=12)
            cbar.ax.tick_params(colors='white', labelsize=10)
           
            plt.tight_layout()

        # Get the bounding box of the axes in figure coordinates (0-1) BEFORE savefig
        # This tells us where the actual image data sits within the full figure
        bbox = ax.get_position()
        logger.debug("Axes position (fig coords): x0={bbox.x0}, y0={bbox.y0}, width={bbox.width}, height={bbox.height}")

        # Get figure size and DPI BEFORE savefig
        fig_width_inch = fig.get_figwidth()
        fig_height_inch = fig.get_figheight()
        fig_dpi = fig.get_dpi()

        # Convert to base64
        buffer = io.BytesIO()
        # Use the same DPI as the figure was created with
        plt.savefig(buffer, format='png', bbox_inches='tight', dpi=fig_dpi, facecolor='black')

        # Note: bbox_inches='tight' can change the final image size
        # We calculate bbox based on the original figure dimensions and axes position
        fig_width_px = fig_width_inch * fig_dpi
        fig_height_px = fig_height_inch * fig_dpi

        plt.close(fig)
        buffer.seek(0)
        img_b64 = base64.b64encode(buffer.read()).decode('utf-8')

        # Calculate the actual pixel position of the image within the figure
        # bbox is in figure coordinates (0-1), convert to pixels
        # Matplotlib uses bottom-left origin, CSS uses top-left, so we convert y
        left_px = bbox.x0 * fig_width_px
        bottom_px = bbox.y0 * fig_height_px
        width_px = bbox.width * fig_width_px
        height_px = bbox.height * fig_height_px

        # Convert bottom to top (CSS coordinate system)
        top_px = fig_height_px - (bottom_px + height_px)

        image_bbox = {
            'left': left_px,
            'top': top_px,  # CSS top coordinate
            'width': width_px,
            'height': height_px,
            'figure_width': fig_width_px,
            'figure_height': fig_height_px
        }

        logger.debug("Image bbox (pixels): left={left_px:.1f}, top={top_px:.1f}, width={width_px:.1f}, height={height_px:.1f}")
        logger.debug("Figure size (pixels): {fig_width_px:.1f}x{fig_height_px:.1f}")

        return {
            'image': f"data:image/png;base64,{img_b64}",
            'bbox': image_bbox
        }
