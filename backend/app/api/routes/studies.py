"""
Studies API Routes.

REST API endpoints for managing imaging studies, series, and instances.

@module api.routes.studies
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File

from app.core.logging import get_logger
from app.core.config import get_settings
from app.core.container import get_study_service
from app.core.interfaces.study_interface import IStudyService
from app.models.study_schemas import (
    StudyCreate,
    StudyUpdate,
    StudyResponse,
    StudySummary,
    StudySearch,
    StudyListResponse,
    SeriesCreate,
    SeriesResponse,
    InstanceResponse,
    UploadInitRequest,
    UploadInitResponse,
    UploadCompleteRequest,
    UploadCompleteResponse,
    DownloadUrlResponse,
    Modality,
    StudyStatus
)

router = APIRouter(prefix="/studies", tags=["Imaging Studies"])
logger = get_logger(__name__)
settings = get_settings()


# =============================================================================
# Study Endpoints (using Firestore via DI Container)
# =============================================================================

@router.post("", response_model=StudyResponse, status_code=201)
async def create_study(
    data: StudyCreate,
    study_service: IStudyService = Depends(get_study_service)
):
    """
    Create a new imaging study.

    Requires STUDY_CREATE permission.
    """
    return await study_service.create_study(data)


@router.get("", response_model=StudyListResponse)
async def list_studies(
    patient_id: Optional[UUID] = Query(None, description="Filter by patient ID"),
    modality: Optional[Modality] = Query(None, description="Filter by modality"),
    status: Optional[StudyStatus] = Query(None, description="Filter by status"),
    query: Optional[str] = Query(None, description="Full-text search"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("study_date", description="Sort field"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort order"),
    study_service: IStudyService = Depends(get_study_service)
):
    """
    List and search studies.

    Requires STUDY_VIEW permission.
    """
    search = StudySearch(
        patient_id=patient_id,
        modality=modality,
        status=status,
        query=query,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order
    )

    studies, total = await study_service.search_studies(search)

    return StudyListResponse(
        items=studies,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size
    )


@router.get("/{study_id}", response_model=StudyResponse)
async def get_study(
    study_id: UUID,
    include_stats: bool = Query(True, description="Include series/instance counts"),
    study_service: IStudyService = Depends(get_study_service)
):
    """
    Get a study by ID.

    Requires STUDY_VIEW permission.
    """
    return await study_service.get_study(study_id, include_stats=include_stats)


@router.get("/accession/{accession_number}", response_model=StudyResponse)
async def get_study_by_accession(
    accession_number: str,
    study_service: IStudyService = Depends(get_study_service)
):
    """
    Get a study by accession number.

    Requires STUDY_VIEW permission.
    """
    study = await study_service.get_study_by_accession(accession_number)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    return study


@router.put("/{study_id}", response_model=StudyResponse)
async def update_study(
    study_id: UUID,
    data: StudyUpdate,
    study_service: IStudyService = Depends(get_study_service)
):
    """
    Update a study.

    Requires STUDY_UPDATE permission.
    """
    return await study_service.update_study(study_id, data)


@router.delete("/{study_id}")
async def delete_study(
    study_id: UUID,
    hard_delete: bool = Query(False, description="Permanently delete files from storage"),
    study_service: IStudyService = Depends(get_study_service)
):
    """
    Delete or cancel a study.

    If hard_delete is False, the study is marked as cancelled.
    If hard_delete is True, all files are deleted from storage.

    Requires STUDY_DELETE permission (ADMIN only for hard_delete).
    """
    await study_service.delete_study(study_id, hard_delete=hard_delete)
    return {"message": "Study deleted successfully"}


# =============================================================================
# Series Endpoints
# =============================================================================

@router.post("/{study_id}/series", response_model=SeriesResponse, status_code=201)
async def create_series(
    study_id: UUID,
    data: SeriesCreate,
    study_service: IStudyService = Depends(get_study_service)
):
    """
    Create a new series within a study.

    Requires STUDY_UPLOAD permission.
    """
    # Ensure study_id matches
    if data.study_id != study_id:
        raise HTTPException(status_code=400, detail="Study ID mismatch")

    return await study_service.create_series(data)


@router.get("/{study_id}/series", response_model=list[SeriesResponse])
async def list_series(
    study_id: UUID,
    study_service: IStudyService = Depends(get_study_service)
):
    """
    List all series in a study.

    Requires STUDY_VIEW permission.
    """
    return await study_service.list_study_series(study_id)


@router.get("/series/{series_id}", response_model=SeriesResponse)
async def get_series(
    series_id: UUID,
    study_service: IStudyService = Depends(get_study_service)
):
    """
    Get a series by ID.

    Requires STUDY_VIEW permission.
    """
    return await study_service.get_series(series_id)


@router.delete("/series/{series_id}")
async def delete_series(
    series_id: UUID,
    study_service: IStudyService = Depends(get_study_service)
):
    """
    Delete a series and all its instances.

    Requires STUDY_DELETE permission.
    """
    await study_service.delete_series(series_id)
    return {"message": "Series deleted successfully"}


# =============================================================================
# Instance Endpoints
# =============================================================================

@router.get("/series/{series_id}/instances", response_model=list[InstanceResponse])
async def list_instances(
    series_id: UUID,
    study_service: IStudyService = Depends(get_study_service)
):
    """
    List all instances in a series.

    Requires STUDY_VIEW permission.
    """
    return await study_service.list_series_instances(series_id)


@router.get("/instances/{instance_id}", response_model=InstanceResponse)
async def get_instance(
    instance_id: UUID,
    study_service: IStudyService = Depends(get_study_service)
):
    """
    Get an instance by ID.

    Requires STUDY_VIEW permission.
    """
    return await study_service.get_instance(instance_id)


@router.delete("/instances/{instance_id}")
async def delete_instance(
    instance_id: UUID,
    study_service: IStudyService = Depends(get_study_service)
):
    """
    Delete an instance.

    Requires STUDY_DELETE permission.
    """
    await study_service.delete_instance(instance_id)
    return {"message": "Instance deleted successfully"}


# =============================================================================
# Upload Endpoints
# =============================================================================

@router.post("/upload/init", response_model=UploadInitResponse)
async def init_upload(
    request: UploadInitRequest,
    study_service: IStudyService = Depends(get_study_service)
):
    """
    Initialize a file upload.

    Returns a signed URL for direct upload to Google Cloud Storage.
    The client should:
    1. Call this endpoint to get a signed URL
    2. PUT the file directly to the signed URL
    3. Call /upload/complete to finalize

    Requires STUDY_UPLOAD permission.
    """
    return await study_service.init_upload(request)


@router.post("/upload/complete", response_model=UploadCompleteResponse)
async def complete_upload(
    request: UploadCompleteRequest,
    study_service: IStudyService = Depends(get_study_service)
):
    """
    Complete a file upload.

    Verifies the upload, extracts metadata, and creates the instance record.

    Requires STUDY_UPLOAD permission.
    """
    return await study_service.complete_upload(request)


# =============================================================================
# Download Endpoints
# =============================================================================

@router.get("/instances/{instance_id}/download-url")
async def get_instance_download_url(
    instance_id: UUID,
    expiration_minutes: int = Query(60, ge=5, le=1440, description="URL expiration in minutes"),
    study_service: IStudyService = Depends(get_study_service)
):
    """
    Get a signed download URL for an instance.

    Requires STUDY_VIEW permission.
    """
    url = await study_service.get_download_url(instance_id, expiration_minutes)
    return {"url": url}


@router.get("/{study_id}/download-urls", response_model=DownloadUrlResponse)
async def get_study_download_urls(
    study_id: UUID,
    expiration_minutes: int = Query(60, ge=5, le=1440, description="URL expiration in minutes"),
    study_service: IStudyService = Depends(get_study_service)
):
    """
    Get download URLs for all instances in a study.

    Requires STUDY_VIEW permission.
    """
    from datetime import datetime, timedelta

    urls = await study_service.get_study_download_urls(study_id, expiration_minutes)

    return DownloadUrlResponse(
        urls=urls,
        expires_at=datetime.utcnow() + timedelta(minutes=expiration_minutes)
    )


# =============================================================================
# Patient Studies
# =============================================================================

@router.get("/patient/{patient_id}", response_model=StudyListResponse)
async def list_patient_studies(
    patient_id: UUID,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    study_service: IStudyService = Depends(get_study_service)
):
    """
    List all studies for a patient.

    Requires STUDY_VIEW permission.
    """
    studies, total = await study_service.list_patient_studies(patient_id, page, page_size)

    return StudyListResponse(
        items=studies,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size
    )
