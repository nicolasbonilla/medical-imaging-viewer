from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
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


class AcquisitionGeometry(BaseModel):
    """Slice thickness / spacing of the ORIGINAL acquisition, as far as the file shows it.

    REQ-FUNC-099 / REQ-SAFE-034, risk control RC-054 (CP-SLICE-THICKNESS-001 — DRAFT,
    PENDING owner approval). Produced by app.services.acquisition_geometry, never by a
    default. Three states:

    - ``native``: read from the acquisition metadata of an ORIGINAL DICOM image
      (with the spacing between slices, or a 3D acquisition). ``effective_mm`` is
      max(SliceThickness, SpacingBetweenSlices).
    - ``at_least``: only a lower bound (> 1.5 mm) is known — the stored grid of a
      NIfTI, or a derived DICOM. The acquisition may have been thicker still.
    - ``not_determinable``: nothing reliable (``reason`` says why). A fine grid without
      acquisition metadata is NOT evidence of a thin acquisition: a 2-5 mm FLAIR
      resampled to 1 mm looks exactly like it (Paper A v0.3, MSLesSeg).

    ``ImageMetadata.slice_thickness`` is unrelated legacy display data (it defaults to
    1.0 mm for a DICOM without the tag) and must never be used for this purpose.
    """
    state: str  # "native" | "at_least" | "not_determinable"
    effective_mm: Optional[float] = None
    source: str = "none"  # "dicom_header" | "nifti_grid" | "none"
    reason: Optional[str] = None
    slice_thickness_mm: Optional[float] = None
    spacing_between_slices_mm: Optional[float] = None
    grid_spacing_mm: Optional[List[float]] = None
    mr_acquisition_type: Optional[str] = None
    image_type: Optional[List[str]] = None
    method_version: str = "acq-geometry/1"


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

    # Anatomical orientation — risk control RC-023 for HAZ-006 (CAPA-004 CA-4.2).
    #
    # Three-letter axis code, e.g. "RAS" or "LAS", naming the direction of
    # INCREASING index along each axis. This is what a viewport needs in order to
    # label left from right.
    #
    # "UNKNOWN" means the affine does not determine an orientation. It is a
    # distinct, meaningful value and MUST NOT be coerced to a default: the client
    # is required to warn the user rather than draw a laterality label it cannot
    # justify. A plausible-looking wrong L/R marker is more dangerous than none,
    # because it turns an obvious absence into a confident error.
    anatomical_orientation: Optional[str] = None

    # Slice thickness of the original acquisition with its source and state
    # (RC-054, CP-SLICE-THICKNESS-001 — DRAFT). None only for responses produced
    # before this field existed; the client treats None as "not determinable".
    acquisition_geometry: Optional[AcquisitionGeometry] = None

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


class LesionAnnotation(BaseModel):
    """Per-lesion CVS and PRL readings recorded by a clinician.

    Central vein sign (CVS) and paramagnetic rim lesions (PRL) are read on
    susceptibility-sensitive MRI. McDonald 2024 (Montalban et al., Lancet Neurology 2025)
    uses them as supportive evidence in specific situations only (CAPA-008).
    """
    lesion_id: int = Field(..., description="Lesion ID from classification results")
    cvs_status: Optional[str] = Field(
        None, description="CVS status: 'positive', 'negative', 'indeterminate'"
    )
    prl_status: Optional[str] = Field(
        None, description="PRL status: 'positive', 'negative', 'indeterminate'"
    )
    annotated_by: Optional[str] = Field(
        None, description="ID of the authenticated user who recorded the reading (set by the server)"
    )
    annotated_at: Optional[datetime] = None
    notes: Optional[str] = None


class AIProvenance(BaseModel):
    """Provenance of an AI-produced segmentation draft (in-browser FLAMeS, CP-FLAMES-BROWSER-001).

    REQ-SAFE-030 / RC-047: an AI draft is stored only with this record so it can never be
    mistaken for manual work. ``review_status`` is forced to "unreviewed" on creation (whatever
    the client sends) and only the confirm-review route can set it to "confirmed".
    """
    kind: Literal["ai_draft"] = "ai_draft"
    model_name: str = Field(..., min_length=1, max_length=100)
    model_version: str = Field(..., min_length=1, max_length=200)
    model_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    fold: int = Field(..., ge=0, le=4)
    source_checkpoint_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    pipeline_version: str = Field(..., min_length=1, max_length=100)
    runtime: str = Field(..., min_length=1, max_length=200)
    generated_at: str = Field(..., min_length=1, max_length=40)
    lesion_count: int = Field(..., ge=0)
    annotated_voxels: int = Field(..., ge=0)
    review_status: Literal["unreviewed", "confirmed"] = "unreviewed"
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    # RC-047: a confirmation is bound to the exact mask that was reviewed (SHA-256 of the stored
    # (depth, height, width) uint8 mask). Any later mask change resets the review (server-side).
    reviewed_mask_sha256: Optional[str] = Field(None, pattern=r"^[0-9a-f]{64}$")
    # RC-049: positive evidence that the input was a FLAIR — the file header said so ("header"),
    # or the clinician explicitly confirmed the sequence before the run ("clinician", recorded with
    # the authenticated user by the server).
    sequence_evidence: Literal["header", "clinician"]
    sequence_confirmed_by: Optional[str] = None


class ClinicianReview(BaseModel):
    """A radiologist's confirmation that a segmentation's lesions AND their MAGNIMS regions were checked, for
    dissemination in space (PRB-003, RC-071, REQ-SAFE-039).

    Any segmentation needs it before DIS is evaluated (RC-070): drawn in the application, produced by a server
    tool, uploaded from another program, or an AI draft (which also needs its own review, RC-047). It is
    offered only after the region classification, set only by `POST /segmentation/{id}/review/confirm`
    (radiologists; the authenticated user recorded; the first confirmer is kept), and bound to the SHA-256 of
    the exact stored mask (same digest as RC-047) AND of the label scheme (id -> name); a later change of either
    removes it (`SegmentationService.enforce_review_binding`), with an entry in `clinician_review_history`.

    Second review of PR #68: a region a radiologist changed by hand after the classification is a correction he
    acknowledges in the confirmation (`region_corrections`, bound by `reviewed_region_corrections_sha256`; N1).
    `reviewed_by` / `reviewed_by_id` are returned only to radiologists and administrators; other roles and the
    AI assistant see the role and the time (N5) — the route always records them.
    """
    reviewed_by: Optional[str] = Field(None, max_length=200)
    reviewed_by_id: Optional[str] = Field(None, max_length=200)
    reviewed_by_role: Optional[str] = Field(None, max_length=40)
    reviewed_at: str = Field(..., min_length=1, max_length=40)
    reviewed_mask_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    reviewed_labels_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    reviewed_region_corrections_sha256: Optional[str] = Field(None, pattern=r"^[0-9a-f]{64}$")
    region_correction_count: int = Field(0, ge=0)
    region_corrections: List[Dict[str, Any]] = Field(default_factory=list, max_length=100)
    # PRB-028 (RC-090): on a classification by the geometric fallback, the lesions whose region the radiologist checked
    # one by one (bound by their digest; None: no such lesion, or a confirmation recorded before this rule).
    reviewed_geometric_regions_sha256: Optional[str] = Field(None, pattern=r"^[0-9a-f]{64}$")
    geometric_region_count: int = Field(0, ge=0)
    geometric_regions: List[Dict[str, Any]] = Field(default_factory=list, max_length=100)


class ClinicianReviewEvent(BaseModel):
    """One entry of the append-only history of DIS confirmations (PRB-003, RC-071; review of PR #68, finding 5).

    `confirmed` and `confirmation_repeated` carry the authenticated user; `voided` is written by the service's
    single save point when the mask or the label scheme changed (the save itself is in the audit log)."""
    event: Literal["confirmed", "confirmation_repeated", "voided"]
    by: Optional[str] = Field(None, max_length=200)
    by_id: Optional[str] = Field(None, max_length=200)
    at: str = Field(..., min_length=1, max_length=40)
    mask_sha256: Optional[str] = Field(None, pattern=r"^[0-9a-f]{64}$")
    labels_sha256: Optional[str] = Field(None, pattern=r"^[0-9a-f]{64}$")
    reason: Optional[Literal["mask_changed", "labels_changed"]] = None
    previous_reviewer: Optional[str] = Field(None, max_length=200)
    region_correction_count: Optional[int] = Field(None, ge=0)


class SegmentationMetadata(BaseModel):
    """Metadata for a segmentation."""
    file_id: str = Field(..., description="Associated image file ID")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    modified_at: datetime = Field(default_factory=datetime.utcnow)
    labels: List[LabelInfo] = Field(default_factory=list, description="Label definitions")
    description: Optional[str] = None
    validation_source: Optional[str] = Field(
        None,
        description="Origin tool: 'manual', 'lst-ai-v1.0.3', 'synthseg-v2.0', 'custom-edt'"
    )
    analysis_data: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "Cached MAGNIMS analysis results (McDonald 2024). Keys: "
            "'lesion_analysis', 'dis_assessment', 'classification', "
            "'zone_map_seg_id', 'analysis_mask_modified_at', "
            "'lesion_annotations', 'cvs_summary', 'prl_summary'."
        )
    )
    segmentation_type: Optional[str] = Field(
        None,
        description="'automatic' for algorithm output (server tools, in-browser AI draft); absent for manual work",
    )
    ai_provenance: Optional[AIProvenance] = Field(
        None,
        description="AI draft provenance (REQ-SAFE-030). Absent on manual segmentations.",
    )
    clinician_review: Optional[ClinicianReview] = Field(
        None,
        description=("Radiologist's confirmation of the lesions and their MAGNIMS regions for DIS, bound to the "
                     "stored mask and label scheme (REQ-SAFE-039, RC-071). Set only by the review/confirm route."),
    )
    clinician_review_history: List[ClinicianReviewEvent] = Field(
        default_factory=list,
        description=("History of DIS confirmations and voidings (RC-071), the most recent 50 kept (every event is "
                     "also in the server log). Written by the server only; returned to radiologists and "
                     "administrators only (second review of PR #68, N5)."),
    )
    created_by: Optional[str] = Field(
        None,
        description=(
            "Username of the authenticated user who created the segmentation, set by the server at creation "
            "(PRB-026); never taken from the request. Absent on segmentations created before it was recorded "
            "and on ones written by tools or scripts — the viewer then says 'Author not recorded'."
        ),
    )


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
    # PRB-003 (second review of PR #68, N5): for a role that does not see the DIS confirmation history, its length.
    clinician_review_history_count: Optional[int] = None


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
    ai_provenance: Optional[AIProvenance] = Field(
        None,
        description="Only for an AI draft explicitly saved by the clinician; stored as 'unreviewed'.",
    )
    labels: List[LabelInfo] = Field(
        default_factory=lambda: [
            LabelInfo(id=0, name="Background", color="#000000", opacity=0.0, visible=False),
            LabelInfo(id=1, name="Lesion", color="#FF0000", opacity=0.5, visible=True)
        ]
    )
