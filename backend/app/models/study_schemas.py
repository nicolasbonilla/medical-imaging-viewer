"""
Pydantic Schemas for Imaging Studies.

Defines request/response models for study management following HL7 FHIR ImagingStudy.

@module models.study_schemas
"""

from typing import Optional, List, Dict
from uuid import UUID
from datetime import datetime, date
from enum import Enum
from pydantic import BaseModel, Field, field_validator


class Modality(str, Enum):
    """
    Imaging modality codes (DICOM standard).
    """
    CT = "CT"           # Computed Tomography
    MR = "MR"           # Magnetic Resonance
    US = "US"           # Ultrasound
    XR = "XR"           # X-Ray/Radiography
    CR = "CR"           # Computed Radiography
    DX = "DX"           # Digital Radiography
    MG = "MG"           # Mammography
    NM = "NM"           # Nuclear Medicine
    PT = "PT"           # PET
    RF = "RF"           # Fluoroscopy
    OT = "OT"           # Other


class StudyStatus(str, Enum):
    """
    Status of the imaging study.
    """
    REGISTERED = "registered"       # Study registered but not started
    AVAILABLE = "available"         # Images available
    CANCELLED = "cancelled"         # Study cancelled
    ENTERED_IN_ERROR = "entered-in-error"


class SeriesStatus(str, Enum):
    """
    Status of the imaging series.
    """
    UPLOADING = "uploading"         # Files being uploaded
    PROCESSING = "processing"       # Files being processed
    AVAILABLE = "available"         # Ready for viewing
    ERROR = "error"                 # Processing error


# =============================================================================
# Study Schemas
# =============================================================================

class StudyCreate(BaseModel):
    """
    Schema for creating a new imaging study.
    """
    patient_id: UUID = Field(..., description="Patient UUID")
    modality: Modality = Field(..., description="Primary imaging modality")
    study_date: datetime = Field(..., description="Date and time of the study")
    study_description: Optional[str] = Field(None, max_length=500, description="Study description")
    body_site: Optional[str] = Field(None, max_length=100, description="Body site imaged")
    laterality: Optional[str] = Field(None, max_length=20, description="Left, Right, Both, etc.")
    reason_for_study: Optional[str] = Field(None, max_length=500, description="Reason for study/clinical indication")
    referring_physician_name: Optional[str] = Field(None, max_length=200, description="Referring physician name")
    referring_physician_id: Optional[str] = Field(None, max_length=50, description="Referring physician ID")
    performing_physician_name: Optional[str] = Field(None, max_length=200, description="Performing physician/technologist")
    institution_name: Optional[str] = Field(None, max_length=200, description="Institution where study was performed")

    @field_validator('study_date')
    @classmethod
    def study_date_not_future(cls, v: datetime) -> datetime:
        """Study date cannot be in the future."""
        if v > datetime.now():
            raise ValueError("Study date cannot be in the future")
        return v


class StudyUpdate(BaseModel):
    """
    Schema for updating an imaging study.
    """
    study_description: Optional[str] = Field(None, max_length=500)
    body_site: Optional[str] = Field(None, max_length=100)
    laterality: Optional[str] = Field(None, max_length=20)
    reason_for_study: Optional[str] = Field(None, max_length=500)
    referring_physician_name: Optional[str] = Field(None, max_length=200)
    referring_physician_id: Optional[str] = Field(None, max_length=50)
    performing_physician_name: Optional[str] = Field(None, max_length=200)
    institution_name: Optional[str] = Field(None, max_length=200)
    status: Optional[StudyStatus] = None
    clinical_notes: Optional[str] = None


class StudyResponse(BaseModel):
    """
    Schema for study response.
    """
    id: UUID
    patient_id: UUID
    accession_number: str
    study_instance_uid: str
    status: StudyStatus
    modality: Modality
    study_date: datetime
    study_description: Optional[str] = None
    body_site: Optional[str] = None
    laterality: Optional[str] = None
    reason_for_study: Optional[str] = None
    referring_physician_name: Optional[str] = None
    referring_physician_id: Optional[str] = None
    performing_physician_name: Optional[str] = None
    institution_name: Optional[str] = None
    gcs_bucket: Optional[str] = None
    gcs_prefix: Optional[str] = None
    clinical_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Computed fields
    series_count: Optional[int] = None
    instance_count: Optional[int] = None
    total_size_bytes: Optional[int] = None

    model_config = {"from_attributes": True}


class StudySummary(BaseModel):
    """
    Schema for study list items (minimal data).
    """
    id: UUID
    patient_id: UUID
    accession_number: str
    modality: Modality
    study_date: datetime
    study_description: Optional[str] = None
    body_site: Optional[str] = None
    status: StudyStatus
    series_count: Optional[int] = None
    instance_count: Optional[int] = None
    total_size_bytes: Optional[int] = None

    model_config = {"from_attributes": True}


class StudySearch(BaseModel):
    """
    Schema for searching studies.
    """
    patient_id: Optional[UUID] = None
    modality: Optional[Modality] = None
    status: Optional[StudyStatus] = None
    study_date_from: Optional[date] = None
    study_date_to: Optional[date] = None
    body_site: Optional[str] = None
    referring_physician: Optional[str] = None
    accession_number: Optional[str] = None
    query: Optional[str] = Field(None, description="Full-text search")

    # Pagination
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    sort_by: str = Field("study_date", description="Sort field")
    sort_order: str = Field("desc", pattern="^(asc|desc)$")


# =============================================================================
# Series Schemas
# =============================================================================

class SeriesCreate(BaseModel):
    """
    Schema for creating a new series.
    """
    study_id: UUID = Field(..., description="Parent study UUID")
    series_number: int = Field(..., ge=1, description="Series number within study")
    modality: Modality = Field(..., description="Series modality")
    series_description: Optional[str] = Field(None, max_length=200)
    body_part_examined: Optional[str] = Field(None, max_length=100)


class SeriesResponse(BaseModel):
    """
    Schema for series response.
    """
    id: UUID
    study_id: UUID
    series_instance_uid: str
    series_number: int
    modality: Modality
    series_description: Optional[str] = None
    body_part_examined: Optional[str] = None
    status: SeriesStatus
    gcs_path: Optional[str] = None
    created_at: datetime

    # Computed
    instance_count: Optional[int] = None
    total_size_bytes: Optional[int] = None

    model_config = {"from_attributes": True}


class SeriesSummary(BaseModel):
    """
    Minimal series info for lists.
    """
    id: UUID
    series_number: int
    modality: Modality
    series_description: Optional[str] = None
    instance_count: Optional[int] = None

    model_config = {"from_attributes": True}


# =============================================================================
# Instance Schemas
# =============================================================================

class InstanceCreate(BaseModel):
    """
    Schema for registering a new instance.
    """
    series_id: UUID = Field(..., description="Parent series UUID")
    sop_instance_uid: str = Field(..., max_length=128, description="DICOM SOP Instance UID")
    sop_class_uid: Optional[str] = Field(None, max_length=128, description="DICOM SOP Class UID")
    instance_number: Optional[int] = Field(None, ge=1, description="Instance number")
    original_filename: str = Field(..., max_length=255, description="Original uploaded filename")
    file_size_bytes: int = Field(..., ge=0, description="File size in bytes")
    content_type: str = Field(..., max_length=100, description="MIME type")
    checksum_sha256: str = Field(..., min_length=64, max_length=64, description="SHA-256 checksum")


class InstanceResponse(BaseModel):
    """
    Schema for instance response.
    """
    id: UUID
    series_id: UUID
    sop_instance_uid: str
    sop_class_uid: Optional[str] = None
    instance_number: Optional[int] = None
    gcs_object_name: str
    original_filename: str
    file_size_bytes: int
    content_type: str
    checksum_sha256: str
    rows: Optional[int] = None
    columns: Optional[int] = None
    bits_allocated: Optional[int] = None
    pixel_spacing: Optional[str] = None
    slice_thickness: Optional[float] = None
    slice_location: Optional[float] = None
    window_center: Optional[float] = None
    window_width: Optional[float] = None
    dicom_metadata: Optional[dict] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class InstanceSummary(BaseModel):
    """
    Minimal instance info.
    """
    id: UUID
    instance_number: Optional[int] = None
    original_filename: str
    file_size_bytes: int

    model_config = {"from_attributes": True}


# =============================================================================
# Upload Schemas
# =============================================================================

class UploadInitRequest(BaseModel):
    """
    Request to initialize a file upload.
    """
    study_id: UUID = Field(..., description="Study to upload to")
    series_number: int = Field(1, ge=1, description="Series number (creates new if doesn't exist)")
    filename: str = Field(..., max_length=255, description="Original filename")
    content_type: str = Field(..., max_length=100, description="MIME type")
    file_size_bytes: int = Field(..., ge=1, description="File size in bytes")
    checksum_sha256: Optional[str] = Field(None, min_length=64, max_length=64, description="Optional pre-computed checksum")


class UploadInitResponse(BaseModel):
    """
    Response with signed URL for upload.
    """
    upload_id: str = Field(..., description="Upload session ID")
    signed_url: str = Field(..., description="Signed URL for uploading")
    expires_at: datetime = Field(..., description="URL expiration time")
    gcs_object_name: str = Field(..., description="Target GCS object path")
    series_id: Optional[UUID] = Field(None, description="Created series UUID")
    headers: Dict[str, str] = Field(default_factory=dict, description="Headers to send with upload request")


class UploadCompleteRequest(BaseModel):
    """
    Request to confirm upload completion.
    """
    upload_id: str = Field(..., description="Upload session ID from init")
    checksum_sha256: str = Field(..., min_length=64, max_length=64, description="SHA-256 checksum of uploaded file")


class UploadCompleteResponse(BaseModel):
    """
    Response after successful upload completion.
    """
    instance_id: UUID = Field(..., description="Created instance UUID")
    series_id: UUID = Field(..., description="Series UUID")
    study_id: UUID = Field(..., description="Study UUID")
    gcs_object_name: str
    file_size_bytes: int


class BulkUploadProgress(BaseModel):
    """
    Progress tracking for bulk uploads.
    """
    total_files: int
    uploaded_files: int
    failed_files: int
    current_file: Optional[str] = None
    bytes_uploaded: int
    total_bytes: int
    percent_complete: float


# =============================================================================
# Download Schemas
# =============================================================================

class DownloadUrlRequest(BaseModel):
    """
    Request for a signed download URL.
    """
    instance_ids: Optional[List[UUID]] = Field(None, description="Specific instances to download")
    series_id: Optional[UUID] = Field(None, description="Download entire series")
    study_id: Optional[UUID] = Field(None, description="Download entire study (ZIP)")
    expiration_minutes: int = Field(60, ge=5, le=1440, description="URL expiration in minutes")


class DownloadUrlResponse(BaseModel):
    """
    Response with signed download URL(s).
    """
    urls: List[dict] = Field(..., description="List of {instance_id, url, filename, expires_at}")
    expires_at: datetime


# =============================================================================
# Study List Response
# =============================================================================

class StudyListResponse(BaseModel):
    """
    Paginated study list response.
    """
    items: List[StudySummary]
    total: int
    page: int
    page_size: int
    pages: int
