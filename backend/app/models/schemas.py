from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class ImageFormat(str, Enum):
    """Supported image formats."""
    DICOM = "dicom"
    NIFTI = "nifti"
    NRRD = "nrrd"


class ImageOrientation(str, Enum):
    """Image orientation planes."""
    AXIAL = "axial"
    SAGITTAL = "sagittal"
    CORONAL = "coronal"


class DriveFileInfo(BaseModel):
    """Google Drive file information."""
    id: str
    name: str
    mimeType: str
    size: Optional[int] = None
    modifiedTime: Optional[datetime] = None
    webViewLink: Optional[str] = None
    thumbnailLink: Optional[str] = None


class ImageMetadata(BaseModel):
    """Medical image metadata."""
    patient_id: Optional[str] = None
    patient_name: Optional[str] = None
    study_date: Optional[str] = None
    study_description: Optional[str] = None
    series_description: Optional[str] = None
    modality: Optional[str] = None
    manufacturer: Optional[str] = None
    institution_name: Optional[str] = None

    # Image properties
    rows: Optional[int] = None
    columns: Optional[int] = None
    slices: Optional[int] = None
    pixel_spacing: Optional[List[float]] = None
    slice_thickness: Optional[float] = None

    # Window/Level
    window_center: Optional[float] = None
    window_width: Optional[float] = None

    # Additional metadata
    extra_fields: Optional[Dict[str, Any]] = None


class ImageSlice(BaseModel):
    """Single image slice data."""
    slice_index: int
    image_data: str  # Base64 encoded
    format: ImageFormat
    width: int
    height: int
    window_center: Optional[float] = None
    window_width: Optional[float] = None


class ImageSeriesResponse(BaseModel):
    """Complete image series response."""
    id: str
    name: str
    format: ImageFormat
    metadata: ImageMetadata
    total_slices: int
    slices: Optional[List[ImageSlice]] = None


class WindowLevelRequest(BaseModel):
    """Request to adjust window/level."""
    window_center: float = Field(..., description="Window center value")
    window_width: float = Field(..., gt=0, description="Window width value")
    slice_index: int = Field(..., ge=0, description="Slice index")


class MeasurementType(str, Enum):
    """Types of measurements."""
    DISTANCE = "distance"
    ANGLE = "angle"
    AREA = "area"
    VOLUME = "volume"


class Point3D(BaseModel):
    """3D point coordinates."""
    x: float
    y: float
    z: float


class Measurement(BaseModel):
    """Measurement data."""
    type: MeasurementType
    points: List[Point3D]
    value: float
    unit: str
    label: Optional[str] = None


class VolumeRenderRequest(BaseModel):
    """Request for 3D volume rendering."""
    orientation: ImageOrientation = ImageOrientation.AXIAL
    slice_range: Optional[tuple[int, int]] = None
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    color_map: str = "gray"


class HealthCheck(BaseModel):
    """Health check response."""
    status: str
    version: str
    timestamp: datetime


class ErrorResponse(BaseModel):
    """Error response."""
    detail: str
    error_code: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# Segmentation Models

class LabelInfo(BaseModel):
    """Label information for segmentation."""
    id: int = Field(..., ge=0, description="Label ID (0 = background)")
    name: str = Field(..., description="Label name (e.g., 'Lesion Type 1')")
    color: str = Field(..., description="Hex color code (e.g., '#FF0000')")
    opacity: float = Field(default=0.5, ge=0.0, le=1.0, description="Overlay opacity")
    visible: bool = Field(default=True, description="Whether label is visible")


class SegmentationMetadata(BaseModel):
    """Metadata for a segmentation."""
    file_id: str = Field(..., description="Associated image file ID")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    modified_at: datetime = Field(default_factory=datetime.utcnow)
    labels: List[LabelInfo] = Field(default_factory=list, description="Label definitions")
    description: Optional[str] = None


class PaintStroke(BaseModel):
    """Single paint stroke data."""
    slice_index: int = Field(..., ge=0, description="Slice index")
    label_id: int = Field(..., ge=0, description="Label ID to paint")
    x: int = Field(..., ge=0, description="X coordinate")
    y: int = Field(..., ge=0, description="Y coordinate")
    brush_size: int = Field(default=1, ge=1, description="Brush radius in pixels")
    erase: bool = Field(default=False, description="Erase mode (set to background)")


class SegmentationMask(BaseModel):
    """Segmentation mask for a single slice."""
    slice_index: int
    mask_data: str  # Base64 encoded PNG or numpy array
    labels_present: List[int] = Field(default_factory=list, description="Label IDs present in this slice")


class SegmentationResponse(BaseModel):
    """Complete segmentation response."""
    segmentation_id: str
    file_id: str
    metadata: SegmentationMetadata
    total_slices: int
    masks: Optional[List[SegmentationMask]] = None


class OverlayImageRequest(BaseModel):
    """Request to generate overlay image."""
    file_id: str
    segmentation_id: str
    slice_index: int
    window_center: Optional[float] = None
    window_width: Optional[float] = None
    colormap: str = Field(default="gray")
    show_labels: Optional[List[int]] = Field(default=None, description="Label IDs to show (None = all)")


class ImageShape(BaseModel):
    """Image dimensions."""
    rows: int = Field(..., ge=1, description="Image height")
    columns: int = Field(..., ge=1, description="Image width")
    slices: int = Field(..., ge=1, description="Number of slices")


class CreateSegmentationRequest(BaseModel):
    """Request to create new segmentation."""
    file_id: str
    image_shape: ImageShape = Field(..., description="Image dimensions (rows, columns, slices)")
    description: Optional[str] = None
    labels: List[LabelInfo] = Field(
        default_factory=lambda: [
            LabelInfo(id=0, name="Background", color="#000000", opacity=0.0, visible=False),
            LabelInfo(id=1, name="Lesion", color="#FF0000", opacity=0.5, visible=True)
        ]
    )
