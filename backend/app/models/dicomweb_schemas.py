"""
DICOMweb Integration Schemas.

Pydantic models for PACS connection management, QIDO-RS search,
WADO-RS retrieval, and import job tracking.

@module models.dicomweb_schemas
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


# ============================================================================
# PACS Connection
# ============================================================================

class PACSConnectionCreate(BaseModel):
    """Configuration for a remote DICOMweb PACS endpoint."""
    name: str = Field(min_length=1, max_length=100, description="Display name")
    base_url: str = Field(min_length=8, description="DICOMweb base URL (e.g. https://pacs.hospital.org/dicom-web)")
    auth_type: Literal["none", "basic", "bearer"] = "none"
    username: Optional[str] = None
    password: Optional[str] = None
    bearer_token: Optional[str] = None
    verify_ssl: bool = True


class PACSConnectionResponse(BaseModel):
    """PACS connection with credentials redacted."""
    id: str
    name: str
    base_url: str
    auth_type: str
    username: Optional[str] = None
    password: str = "***"
    verify_ssl: bool = True
    created_at: str
    last_tested: Optional[str] = None
    is_reachable: Optional[bool] = None


# ============================================================================
# QIDO-RS Search
# ============================================================================

class StudySearchRequest(BaseModel):
    """Query parameters for QIDO-RS study search."""
    connection_id: str
    patient_name: Optional[str] = None
    patient_id: Optional[str] = None
    study_date: Optional[str] = None  # DICOM date range: YYYYMMDD or YYYYMMDD-YYYYMMDD
    modality: Optional[str] = None
    accession_number: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=200)


class StudySearchResult(BaseModel):
    """Single study result from QIDO-RS."""
    study_instance_uid: str
    patient_name: Optional[str] = None
    patient_id: Optional[str] = None
    study_date: Optional[str] = None
    study_description: Optional[str] = None
    modality: Optional[str] = None
    accession_number: Optional[str] = None
    number_of_series: Optional[int] = None
    number_of_instances: Optional[int] = None


class SeriesSearchResult(BaseModel):
    """Single series result from QIDO-RS."""
    series_instance_uid: str
    series_number: Optional[int] = None
    modality: Optional[str] = None
    series_description: Optional[str] = None
    body_part_examined: Optional[str] = None
    number_of_instances: Optional[int] = None


# ============================================================================
# Import Job
# ============================================================================

class ImportRequest(BaseModel):
    """Request to import a DICOM series from PACS into MSTool-AI."""
    connection_id: str
    study_instance_uid: str
    series_instance_uid: str
    patient_id: str  # Target patient UUID in MSTool-AI
    study_description: Optional[str] = None


class ImportJobStatus(BaseModel):
    """Status of a DICOMweb import job."""
    job_id: str
    status: Literal["pending", "downloading", "converting", "uploading", "registering", "completed", "failed"] = "pending"
    progress_percent: int = 0
    error_message: Optional[str] = None
    instances_downloaded: int = 0
    instances_total: Optional[int] = None
    study_id: Optional[str] = None
    series_id: Optional[str] = None
    instance_id: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
