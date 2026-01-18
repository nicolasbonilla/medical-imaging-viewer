"""
Document Pydantic Schemas.

Models for clinical document management with versioning.

@module models.document_schemas
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from uuid import UUID
from datetime import date, datetime
from enum import Enum


class DocumentCategory(str, Enum):
    """Document category types (HL7 FHIR DocumentReference)."""
    LAB_RESULT = "lab-result"
    PRESCRIPTION = "prescription"
    CLINICAL_NOTE = "clinical-note"
    DISCHARGE_SUMMARY = "discharge-summary"
    RADIOLOGY_REPORT = "radiology-report"
    CONSENT_FORM = "consent-form"
    REFERRAL = "referral"
    OPERATIVE_NOTE = "operative-note"
    PATHOLOGY_REPORT = "pathology-report"
    IMAGING_REPORT = "imaging-report"
    PROGRESS_NOTE = "progress-note"
    CONSULTATION = "consultation"
    OTHER = "other"


class DocumentStatus(str, Enum):
    """Document status (HL7 FHIR)."""
    CURRENT = "current"
    SUPERSEDED = "superseded"
    ENTERED_IN_ERROR = "entered-in-error"


# =============================================================================
# Document Base Schemas
# =============================================================================

class DocumentBase(BaseModel):
    """Base document fields."""
    title: str = Field(..., min_length=1, max_length=255, description="Document title")
    description: Optional[str] = Field(None, max_length=2000, description="Document description")
    category: DocumentCategory = Field(..., description="Document category")
    document_date: date = Field(..., description="Date the document was created/authored")


class DocumentCreate(DocumentBase):
    """Schema for creating a new document."""
    patient_id: UUID = Field(..., description="Patient this document belongs to")
    study_id: Optional[UUID] = Field(None, description="Optional linked imaging study")
    author_name: Optional[str] = Field(None, max_length=255, description="Document author")

    @field_validator('document_date')
    @classmethod
    def document_date_not_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError('Document date cannot be in the future')
        return v


class DocumentUpdate(BaseModel):
    """Schema for updating document metadata."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    category: Optional[DocumentCategory] = None
    document_date: Optional[date] = None
    status: Optional[DocumentStatus] = None
    author_name: Optional[str] = Field(None, max_length=255)

    @field_validator('document_date')
    @classmethod
    def document_date_not_future(cls, v: Optional[date]) -> Optional[date]:
        if v is not None and v > date.today():
            raise ValueError('Document date cannot be in the future')
        return v


class DocumentResponse(DocumentBase):
    """Response schema for a document."""
    id: UUID
    patient_id: UUID
    study_id: Optional[UUID] = None
    status: DocumentStatus
    version: int = Field(..., description="Document version number")
    original_filename: str = Field(..., description="Original uploaded filename")
    content_type: str = Field(..., description="MIME type")
    file_size_bytes: int = Field(..., ge=0, description="File size in bytes")
    checksum_sha256: str = Field(..., description="SHA-256 checksum")
    gcs_object_name: str = Field(..., description="GCS object path")
    author_name: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    created_by: Optional[UUID] = None

    model_config = {"from_attributes": True}


class DocumentSummary(BaseModel):
    """Summary schema for document listings."""
    id: UUID
    patient_id: UUID
    title: str
    category: DocumentCategory
    document_date: date
    status: DocumentStatus
    version: int
    content_type: str
    file_size_bytes: int
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    """Paginated list of documents."""
    items: List[DocumentSummary]
    total: int
    page: int
    page_size: int
    total_pages: int


# =============================================================================
# Document Version Schemas
# =============================================================================

class DocumentVersionResponse(BaseModel):
    """Response schema for a document version."""
    id: UUID
    document_id: UUID
    version: int
    original_filename: str
    content_type: str
    file_size_bytes: int
    checksum_sha256: str
    gcs_object_name: str
    created_at: datetime
    created_by: Optional[UUID] = None
    change_summary: Optional[str] = None

    model_config = {"from_attributes": True}


class DocumentVersionCreate(BaseModel):
    """Schema for creating a new document version."""
    change_summary: Optional[str] = Field(
        None,
        max_length=500,
        description="Description of changes in this version"
    )


# =============================================================================
# Upload Schemas
# =============================================================================

class DocumentUploadInit(BaseModel):
    """Request to initialize document upload."""
    patient_id: UUID = Field(..., description="Patient this document belongs to")
    study_id: Optional[UUID] = Field(None, description="Optional linked study")
    title: str = Field(..., min_length=1, max_length=255, description="Document title")
    category: DocumentCategory = Field(..., description="Document category")
    document_date: date = Field(..., description="Document date")
    filename: str = Field(..., min_length=1, max_length=255, description="Original filename")
    content_type: str = Field(..., description="MIME type")
    file_size_bytes: int = Field(..., gt=0, description="File size in bytes")
    description: Optional[str] = Field(None, max_length=2000)
    author_name: Optional[str] = Field(None, max_length=255)

    @field_validator('content_type')
    @classmethod
    def validate_content_type(cls, v: str) -> str:
        allowed_types = [
            'application/pdf',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'image/jpeg',
            'image/png',
            'image/tiff',
            'text/plain',
            'text/html',
            'application/rtf',
        ]
        if v not in allowed_types:
            raise ValueError(f'Content type {v} not allowed. Allowed: {allowed_types}')
        return v

    @field_validator('document_date')
    @classmethod
    def document_date_not_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError('Document date cannot be in the future')
        return v


class DocumentUploadInitResponse(BaseModel):
    """Response for document upload initialization."""
    upload_id: str = Field(..., description="Unique upload session ID")
    signed_url: str = Field(..., description="GCS signed upload URL")
    expires_at: datetime = Field(..., description="URL expiration time")
    headers: dict = Field(default_factory=dict, description="Required upload headers")
    document_id: UUID = Field(..., description="Pre-created document ID")
    gcs_object_name: str = Field(..., description="GCS object path")


class DocumentUploadComplete(BaseModel):
    """Request to complete document upload."""
    upload_id: str = Field(..., description="Upload session ID from init")
    checksum_sha256: str = Field(..., min_length=64, max_length=64, description="SHA-256 checksum")


class DocumentUploadCompleteResponse(BaseModel):
    """Response for completed document upload."""
    document: DocumentResponse
    is_new_version: bool = False
    version_count: int = 1


# =============================================================================
# Version Upload Schemas
# =============================================================================

class VersionUploadInit(BaseModel):
    """Request to initialize a new version upload."""
    document_id: UUID = Field(..., description="Existing document ID")
    filename: str = Field(..., min_length=1, max_length=255, description="New version filename")
    content_type: str = Field(..., description="MIME type")
    file_size_bytes: int = Field(..., gt=0, description="File size in bytes")
    change_summary: Optional[str] = Field(None, max_length=500, description="Version change notes")

    @field_validator('content_type')
    @classmethod
    def validate_content_type(cls, v: str) -> str:
        allowed_types = [
            'application/pdf',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'image/jpeg',
            'image/png',
            'image/tiff',
            'text/plain',
            'text/html',
            'application/rtf',
        ]
        if v not in allowed_types:
            raise ValueError(f'Content type {v} not allowed. Allowed: {allowed_types}')
        return v


class VersionUploadInitResponse(BaseModel):
    """Response for version upload initialization."""
    upload_id: str = Field(..., description="Upload session ID")
    signed_url: str = Field(..., description="GCS signed upload URL")
    expires_at: datetime = Field(..., description="URL expiration time")
    headers: dict = Field(default_factory=dict)
    new_version: int = Field(..., description="Version number that will be created")
    gcs_object_name: str = Field(..., description="GCS object path")


class VersionUploadComplete(BaseModel):
    """Request to complete version upload."""
    upload_id: str = Field(..., description="Upload session ID")
    checksum_sha256: str = Field(..., min_length=64, max_length=64)


class VersionUploadCompleteResponse(BaseModel):
    """Response for completed version upload."""
    document: DocumentResponse
    version: DocumentVersionResponse


# =============================================================================
# Search Schemas
# =============================================================================

class DocumentSearch(BaseModel):
    """Search parameters for documents."""
    patient_id: Optional[UUID] = None
    study_id: Optional[UUID] = None
    category: Optional[DocumentCategory] = None
    status: Optional[DocumentStatus] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    query: Optional[str] = Field(None, max_length=255, description="Search in title/description")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


# =============================================================================
# Download Schemas
# =============================================================================

class DocumentDownloadUrl(BaseModel):
    """Response with signed download URL."""
    document_id: UUID
    version: int
    url: str
    filename: str
    content_type: str
    expires_at: datetime
