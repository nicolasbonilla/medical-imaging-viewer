"""
Pydantic Schemas for Medical Image Segmentation.

ITK-SNAP style segmentation with multi-expert support.
Compliant with DICOM SEG and HL7 FHIR ImagingStudy standards.

@module models.segmentation_schemas
"""

from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, field_validator
import re


class SegmentationStatus(str, Enum):
    """
    Lifecycle status of a segmentation.
    Supports multi-expert review workflow.
    """
    DRAFT = "draft"                    # Created, no annotations yet
    IN_PROGRESS = "in_progress"        # Active work
    PENDING_REVIEW = "pending_review"  # Waiting for review
    REVIEWED = "reviewed"              # Reviewed by another expert
    APPROVED = "approved"              # Approved for clinical use
    ARCHIVED = "archived"              # Archived (not active)


class SegmentationType(str, Enum):
    """
    Segmentation type according to DICOM SEG standard.
    """
    BINARY = "binary"          # One label per segment (0 or 1)
    LABELMAP = "labelmap"      # Multiple labels (ITK-SNAP style, 0-255)
    FRACTIONAL = "fractional"  # Probability values (AI predictions)


# =============================================================================
# Label Schemas (ITK-SNAP Style)
# =============================================================================

class LabelInfo(BaseModel):
    """
    Label definition for segmentation (ITK-SNAP style).

    Labels are integers 0-255 where:
    - 0 = Background/Clear (always transparent)
    - 1-255 = User-defined labels
    """
    id: int = Field(..., ge=0, le=255, description="Label ID (0=background)")
    name: str = Field(..., min_length=1, max_length=100, description="Label name")
    color: str = Field(..., description="Hex color code (#RRGGBB)")
    opacity: float = Field(default=0.5, ge=0.0, le=1.0, description="Overlay opacity")
    visible: bool = Field(default=True, description="Whether label is visible in overlay")
    description: Optional[str] = Field(None, max_length=500, description="Label description")

    # Clinical metadata (optional)
    snomed_code: Optional[str] = Field(None, max_length=50, description="SNOMED-CT code")
    finding_site: Optional[str] = Field(None, max_length=100, description="Anatomical location")

    @field_validator('color')
    @classmethod
    def validate_color(cls, v: str) -> str:
        """Validate hex color format."""
        if not re.match(r'^#[0-9A-Fa-f]{6}$', v):
            raise ValueError('Color must be hex format: #RRGGBB')
        return v.upper()


class LabelUpdate(BaseModel):
    """Schema for updating a label."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    color: Optional[str] = None
    opacity: Optional[float] = Field(None, ge=0.0, le=1.0)
    visible: Optional[bool] = None
    description: Optional[str] = Field(None, max_length=500)
    snomed_code: Optional[str] = Field(None, max_length=50)
    finding_site: Optional[str] = Field(None, max_length=100)

    @field_validator('color')
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not re.match(r'^#[0-9A-Fa-f]{6}$', v):
            raise ValueError('Color must be hex format: #RRGGBB')
        return v.upper()


# =============================================================================
# Segmentation Request Schemas
# =============================================================================

class SegmentationCreate(BaseModel):
    """
    Request to create a new segmentation.
    Must be associated with a series.
    """
    series_id: UUID = Field(..., description="Series to segment")
    name: str = Field(..., min_length=1, max_length=200, description="Descriptive name")
    description: Optional[str] = Field(None, max_length=1000, description="Detailed description")
    segmentation_type: SegmentationType = Field(
        default=SegmentationType.LABELMAP,
        description="Segmentation type (labelmap recommended)"
    )
    labels: List[LabelInfo] = Field(
        default_factory=lambda: [
            LabelInfo(id=0, name="Background", color="#000000", opacity=0.0, visible=False),
            LabelInfo(id=1, name="Lesion", color="#FF0000", opacity=0.5, visible=True)
        ],
        description="Label definitions"
    )

    @field_validator('labels')
    @classmethod
    def validate_labels(cls, v: List[LabelInfo]) -> List[LabelInfo]:
        """Ensure background label (id=0) exists."""
        if not any(label.id == 0 for label in v):
            v.insert(0, LabelInfo(
                id=0, name="Background", color="#000000", opacity=0.0, visible=False
            ))
        return v


class SegmentationUpdate(BaseModel):
    """
    Request to update segmentation metadata.
    """
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)


class SegmentationStatusUpdate(BaseModel):
    """
    Request to update segmentation status.
    """
    status: SegmentationStatus = Field(..., description="New status")
    notes: Optional[str] = Field(None, max_length=500, description="Status change notes")


class PaintStroke(BaseModel):
    """
    Single paint stroke data for segmentation editing.
    """
    slice_index: int = Field(..., ge=0, description="Slice index")
    label_id: int = Field(..., ge=0, le=255, description="Label ID to paint")
    x: int = Field(..., ge=0, description="X coordinate (column)")
    y: int = Field(..., ge=0, description="Y coordinate (row)")
    brush_size: int = Field(default=1, ge=1, le=50, description="Brush size in voxels")
    erase: bool = Field(default=False, description="Erase mode (set to label 0)")


class PaintStrokeBatch(BaseModel):
    """
    Batch of paint strokes for efficient transmission.
    """
    strokes: List[PaintStroke] = Field(..., min_length=1, max_length=1000)


# =============================================================================
# Segmentation Response Schemas
# =============================================================================

class SegmentationResponse(BaseModel):
    """
    Full segmentation response with all metadata.
    """
    id: UUID

    # Hierarchical relationships
    patient_id: UUID
    study_id: UUID
    series_id: UUID

    # For backward compatibility
    file_id: Optional[str] = None

    # Metadata
    name: str
    description: Optional[str] = None
    segmentation_type: SegmentationType

    # Status and progress
    status: SegmentationStatus
    progress_percentage: int = Field(ge=0, le=100)
    slices_annotated: int = Field(ge=0)
    total_slices: int = Field(ge=1)

    # Authorship
    created_by: str  # username
    created_by_name: Optional[str] = None  # full name
    reviewed_by: Optional[str] = None
    reviewed_by_name: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None

    # Labels
    labels: List[LabelInfo]

    # Storage
    gcs_path: Optional[str] = None

    # Timestamps
    created_at: datetime
    modified_at: datetime

    model_config = {"from_attributes": True}


class SegmentationSummary(BaseModel):
    """
    Minimal segmentation info for lists (fast loading).
    """
    id: UUID
    name: str
    status: SegmentationStatus
    progress_percentage: int
    slices_annotated: int
    total_slices: int
    created_by: str
    created_by_name: Optional[str] = None
    created_at: datetime
    modified_at: datetime
    label_count: int

    # For visual indicator
    primary_label_color: str = Field(
        default="#FF0000",
        description="Color of the primary non-background label"
    )

    model_config = {"from_attributes": True}


class SegmentationListResponse(BaseModel):
    """
    Paginated list of segmentations.
    """
    items: List[SegmentationSummary]
    total: int
    page: int = 1
    page_size: int = 20
    has_more: bool = False


# =============================================================================
# Overlay and Export Schemas
# =============================================================================

class OverlaySettings(BaseModel):
    """
    Settings for segmentation overlay rendering.
    """
    mode: str = Field(
        default="overlay",
        pattern="^(overlay|outline|checkerboard|side_by_side)$"
    )
    global_opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    visible_labels: Optional[List[int]] = Field(
        default=None,
        description="Label IDs to show (None = all visible)"
    )
    outline_thickness: int = Field(default=2, ge=1, le=5)
    outline_only: bool = Field(default=False)


class OverlayRequest(BaseModel):
    """
    Request for overlay image generation.
    """
    slice_index: int = Field(..., ge=0)
    settings: Optional[OverlaySettings] = None
    format: str = Field(default="png", pattern="^(png|jpeg|webp)$")


class ExportRequest(BaseModel):
    """
    Request to export segmentation.
    """
    format: str = Field(
        ...,
        pattern="^(nifti|dicom_seg|nrrd)$",
        description="Export format"
    )
    include_metadata: bool = Field(default=True)
    compress: bool = Field(default=True)


class ExportResponse(BaseModel):
    """
    Response with export download information.
    """
    download_url: str
    filename: str
    format: str
    size_bytes: int
    expires_at: datetime


# =============================================================================
# Statistics and Comparison Schemas
# =============================================================================

class LabelStatistics(BaseModel):
    """
    Statistics for a single label.
    """
    label_id: int
    label_name: str
    voxel_count: int
    volume_mm3: Optional[float] = None  # Requires voxel spacing
    percentage: float = Field(ge=0.0, le=100.0)
    slices_present: int


class SegmentationStatistics(BaseModel):
    """
    Complete statistics for a segmentation.
    """
    segmentation_id: UUID
    total_voxels: int
    annotated_voxels: int
    image_shape: List[int]  # [depth, height, width]
    voxel_spacing: Optional[List[float]] = None  # [dz, dy, dx] in mm
    label_statistics: List[LabelStatistics]
    computed_at: datetime


class SegmentationComparisonRequest(BaseModel):
    """
    Request to compare multiple segmentations.
    """
    segmentation_ids: List[UUID] = Field(
        ...,
        min_length=2,
        max_length=5,
        description="Segmentation IDs to compare"
    )
    metrics: List[str] = Field(
        default=["dice", "hausdorff", "volume_difference"],
        description="Metrics to compute"
    )


class ComparisonMetrics(BaseModel):
    """
    Comparison metrics between two segmentations.
    """
    segmentation_a: UUID
    segmentation_b: UUID
    dice_coefficient: float = Field(ge=0.0, le=1.0)
    hausdorff_distance: Optional[float] = None  # in mm or voxels
    volume_difference_percent: float
    voxel_agreement_percent: float


class SegmentationComparisonResponse(BaseModel):
    """
    Response with comparison results.
    """
    segmentation_ids: List[UUID]
    pairwise_metrics: List[ComparisonMetrics]
    consensus_labels: Optional[Dict[int, float]] = Field(
        default=None,
        description="Agreement percentage per label"
    )
    computed_at: datetime


# =============================================================================
# Search and Filter Schemas
# =============================================================================

class SegmentationSearch(BaseModel):
    """
    Search parameters for segmentations.
    """
    # Hierarchy filters
    patient_id: Optional[UUID] = None
    study_id: Optional[UUID] = None
    series_id: Optional[UUID] = None

    # Status filter
    status: Optional[SegmentationStatus] = None
    status_in: Optional[List[SegmentationStatus]] = None

    # Author filter
    created_by: Optional[str] = None
    reviewed_by: Optional[str] = None

    # Date filters
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    modified_after: Optional[datetime] = None

    # Full-text search
    query: Optional[str] = Field(None, min_length=2, max_length=100)

    # Pagination
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    # Sorting
    sort_by: str = Field(default="modified_at")
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")


# =============================================================================
# Audit Schemas
# =============================================================================

class SegmentationAuditAction(str, Enum):
    """
    Audit action types for segmentation operations.
    """
    CREATED = "created"
    PAINT_STROKE = "paint_stroke"
    LABEL_ADDED = "label_added"
    LABEL_MODIFIED = "label_modified"
    LABEL_REMOVED = "label_removed"
    STATUS_CHANGED = "status_changed"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    EXPORTED = "exported"
    DELETED = "deleted"


class SegmentationAuditLog(BaseModel):
    """
    Audit log entry for segmentation operations.
    """
    id: UUID
    timestamp: datetime
    user_id: str
    username: str
    action: SegmentationAuditAction
    segmentation_id: UUID
    details: Dict[str, Any] = Field(default_factory=dict)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    model_config = {"from_attributes": True}
