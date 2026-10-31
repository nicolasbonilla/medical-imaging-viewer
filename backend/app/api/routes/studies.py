"""
Studies API Routes.

REST API endpoints for managing imaging studies, series, and instances.

@module api.routes.studies
"""

from typing import Optional
from uuid import UUID
import struct

import numpy as np
from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File
from fastapi.responses import Response

from app.core.logging import get_logger
from app.core.config import get_settings
from app.security import get_current_active_user, require_permission
from app.security.resource_access import (
    require_study_access, require_series_access, require_instance_access,
    require_study_list_scope, authorize_patient_id, authorize_study_id,
)
from app.security.patient_access_dependency import require_patient_access
from app.security.ownership import initiators
from app.security.models import User, Permission, UserRole
from app.core.container import get_study_service, get_storage_service
from app.core.interfaces.study_interface import IStudyService
from app.core.interfaces.storage_interface import IStorageService
from app.utils import load_nifti_from_bytes
from app.models.study_schemas import (
    StudyCreate,
    StudyUpdate,
    StudyResponse,
    StudySummary,
    StudySearch,
    StudyListResponse,
    SeriesCreate,
    SeriesResponse,
    InstanceUpdate,
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


def _may_change_study_status(user: User) -> bool:
    """Review of PR #70, M2: cancelling or restoring a study needs PATIENT_UPDATE (radiologist, administrator)."""
    from app.security.rbac import RBACManager
    return RBACManager.has_permission(user.role, Permission.PATIENT_UPDATE)
logger = get_logger(__name__)
settings = get_settings()


# =============================================================================
# Study Endpoints (using Firestore via DI Container)
# =============================================================================

@router.post("", response_model=StudyResponse, status_code=201)
async def create_study(
    data: StudyCreate,
    study_service: IStudyService = Depends(get_study_service),
    current_user: User = Depends(get_current_active_user)
):
    """
    Create a new imaging study for a patient the caller may access.

    CAPA-009 (RC-036): the patient in the body is authorized first (404 otherwise).
    """
    await authorize_patient_id(data.patient_id, current_user)
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
    study_service: IStudyService = Depends(get_study_service),
    current_user: User = Depends(get_current_active_user),
    # CAPA-002 CA-2.1 RC-028 - object-level authorization.
    _authorized=Depends(require_study_list_scope),
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
    study_service: IStudyService = Depends(get_study_service),
    current_user: User = Depends(get_current_active_user),
    # CAPA-002 CA-2.1 RC-028 - object-level authorization.
    _authorized=Depends(require_study_access),
):
    """
    Get a study by ID.

    Requires STUDY_VIEW permission.
    """
    return await study_service.get_study(study_id, include_stats=include_stats)


@router.get("/accession/{accession_number}", response_model=StudyResponse)
async def get_study_by_accession(
    accession_number: str,
    study_service: IStudyService = Depends(get_study_service),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get a study by accession number.

    Requires STUDY_VIEW permission.
    """
    study = await study_service.get_study_by_accession(accession_number)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    # CAPA-009 (RC-036): a lookup by accession number must not bypass the patient check.
    await authorize_study_id(getattr(study, "id", None), current_user)
    return study


@router.put("/{study_id}", response_model=StudyResponse)
async def update_study(
    study_id: UUID,
    data: StudyUpdate,
    study_service: IStudyService = Depends(get_study_service),
    current_user: User = Depends(get_current_active_user),
    # CAPA-002 CA-2.1 RC-028 - object-level authorization.
    _authorized=Depends(require_study_access),
):
    """
    Update a study.

    A status change (cancel or restore) needs PATIENT_UPDATE (radiologist, administrator), like cancelling through
    DELETE (review of PR #70, M2): otherwise a read-only user could hide a study from everyone with a PUT. Other
    fields need object access only, as before. (The docstring named a STUDY_UPDATE permission that does not exist.)
    """
    if data.status is not None and not _may_change_study_status(current_user):
        raise HTTPException(status_code=403, detail="Changing a study's status requires the patient:update permission")
    return await study_service.update_study(study_id, data)


@router.delete("/{study_id}")
async def delete_study(
    study_id: UUID,
    hard_delete: bool = Query(False, description="Permanently delete files from storage"),
    study_service: IStudyService = Depends(get_study_service),
    # Review of PR #70, M2: cancelling hides the study from every user (PRB-025), so it needs a write permission.
    current_user: User = Depends(require_permission(Permission.PATIENT_UPDATE)),
    # CAPA-002 CA-2.1 RC-028 - object-level authorization.
    _authorized=Depends(require_study_access),
):
    """
    Delete or cancel a study.

    Requires PATIENT_UPDATE (radiologist, administrator) — review of PR #70, M2. The route had no role check and its
    docstring named a STUDY_DELETE permission that does not exist; since PRB-025 a cancelled study is no longer listed
    or counted for anyone, so a read-only user could hide a prior scan from a longitudinal comparison.

    If hard_delete is False, the study is marked as cancelled: it is kept as a record but no longer listed or
    counted (PRB-025). If hard_delete is True, all files are deleted from storage.

    hard_delete is administrator-only (PRB-025): this docstring said so, but the route did not check it, so
    any user with access to the patient could erase a study's images permanently.
    """
    if hard_delete and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Permanent deletion of a study is restricted to administrators")
    await study_service.delete_study(study_id, deleted_by=current_user.id, hard_delete=hard_delete)
    return {"message": "Study deleted successfully"}


# =============================================================================
# Series Endpoints
# =============================================================================

@router.post("/{study_id}/series", response_model=SeriesResponse, status_code=201)
async def create_series(
    study_id: UUID,
    data: SeriesCreate,
    study_service: IStudyService = Depends(get_study_service),
    current_user: User = Depends(get_current_active_user),
    # CAPA-002 CA-2.1 RC-028 - object-level authorization.
    _authorized=Depends(require_study_access),
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
    study_service: IStudyService = Depends(get_study_service),
    current_user: User = Depends(get_current_active_user),
    # CAPA-002 CA-2.1 RC-028 - object-level authorization.
    _authorized=Depends(require_study_access),
):
    """
    List all series in a study.

    Requires STUDY_VIEW permission.
    """
    return await study_service.list_study_series(study_id)


@router.get("/series/{series_id}", response_model=SeriesResponse)
async def get_series(
    series_id: UUID,
    study_service: IStudyService = Depends(get_study_service),
    current_user: User = Depends(get_current_active_user),
    # CAPA-002 CA-2.1 RC-028 - object-level authorization.
    _authorized=Depends(require_series_access),
):
    """
    Get a series by ID.

    Requires STUDY_VIEW permission.
    """
    return await study_service.get_series(series_id)


@router.delete("/series/{series_id}")
async def delete_series(
    series_id: UUID,
    study_service: IStudyService = Depends(get_study_service),
    # Review of PR #70, M1: erases the series' files from storage permanently → IMAGE_DELETE (administrator only).
    current_user: User = Depends(require_permission(Permission.IMAGE_DELETE)),
    # CAPA-002 CA-2.1 RC-028 - object-level authorization.
    _authorized=Depends(require_series_access),
):
    """
    Delete a series and all its instances, and their files in storage (permanent).

    Requires IMAGE_DELETE (administrator only) — review of PR #70, M1. The route checked only object access and its
    docstring named a STUDY_DELETE permission that does not exist: any care-team member, a viewer included, could
    erase a series.
    """
    await study_service.delete_series(series_id)
    return {"message": "Series deleted successfully"}


# =============================================================================
# Instance Endpoints
# =============================================================================

@router.get("/series/{series_id}/instances", response_model=list[InstanceResponse])
async def list_instances(
    series_id: UUID,
    study_service: IStudyService = Depends(get_study_service),
    current_user: User = Depends(get_current_active_user),
    # CAPA-002 CA-2.1 RC-028 - object-level authorization.
    _authorized=Depends(require_series_access),
):
    """
    List all instances in a series.

    Requires STUDY_VIEW permission.
    """
    return await study_service.list_series_instances(series_id)


@router.get("/instances/{instance_id}", response_model=InstanceResponse)
async def get_instance(
    instance_id: UUID,
    study_service: IStudyService = Depends(get_study_service),
    current_user: User = Depends(get_current_active_user),
    # CAPA-002 CA-2.1 RC-028 - object-level authorization.
    _authorized=Depends(require_instance_access),
):
    """
    Get an instance by ID.

    Requires STUDY_VIEW permission.
    """
    return await study_service.get_instance(instance_id)


@router.patch("/instances/{instance_id}", response_model=InstanceResponse)
async def update_instance(
    instance_id: UUID,
    data: InstanceUpdate,
    study_service: IStudyService = Depends(get_study_service),
    current_user: User = Depends(get_current_active_user),
    # CAPA-002 CA-2.1 RC-028 - object-level authorization.
    _authorized=Depends(require_instance_access),
):
    """
    Update an instance (e.g. rename original_filename).

    Requires STUDY_UPDATE permission.
    """
    return await study_service.update_instance(instance_id, data)


@router.delete("/instances/{instance_id}")
async def delete_instance(
    instance_id: UUID,
    study_service: IStudyService = Depends(get_study_service),
    # Review of PR #70, M1: erases the image file from storage permanently → IMAGE_DELETE (administrator only).
    current_user: User = Depends(require_permission(Permission.IMAGE_DELETE)),
    # CAPA-002 CA-2.1 RC-028 - object-level authorization.
    _authorized=Depends(require_instance_access),
):
    """
    Delete an instance and its file in storage (permanent).

    Requires IMAGE_DELETE (administrator only) — review of PR #70, M1 (see delete_series).
    """
    await study_service.delete_instance(instance_id)
    return {"message": "Instance deleted successfully"}


# =============================================================================
# Instance Mask Endpoint (for expert annotation NIfTI overlays)
# =============================================================================

@router.get("/instances/{instance_id}/mask-data")
async def get_instance_mask_data(
    instance_id: UUID,
    study_service: IStudyService = Depends(get_study_service),
    storage_service: IStorageService = Depends(get_storage_service),
    current_user: User = Depends(get_current_active_user),
    # CAPA-009 (RC-036): expert masks are patient data.
    _authorized=Depends(require_instance_access),
):
    """
    Download a NIfTI instance as binary mask data.

    Used for loading expert annotation masks as overlays.
    Returns the same binary format as segmentation masks:
    [depth:4bytes][height:4bytes][width:4bytes][mask_data:D*H*W bytes]
    """
    try:
        instance = await study_service.get_instance(instance_id)
        gcs_path = instance.gcs_object_name

        file_data = await storage_service.download_file(
            settings.GCS_BUCKET_NAME, gcs_path
        )

        img, data = load_nifti_from_bytes(file_data, normalize=False)

        # Ensure uint8 binary mask (0 or 1)
        mask = (data > 0).astype(np.uint8)

        # Transpose from NIfTI (W,H,D) to viewer convention (D,H,W)
        if mask.ndim == 3:
            mask = np.transpose(mask, (2, 1, 0))

        depth, height, width = mask.shape
        header = struct.pack('<III', depth, height, width)
        binary_data = header + mask.tobytes()

        return Response(
            content=binary_data,
            media_type="application/octet-stream",
            headers={
                "Content-Length": str(len(binary_data)),
                "X-Mask-Depth": str(depth),
                "X-Mask-Height": str(height),
                "X-Mask-Width": str(width),
                "Cache-Control": "public, max-age=3600",
                "Access-Control-Expose-Headers": "X-Mask-Depth, X-Mask-Height, X-Mask-Width, Content-Length"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error loading instance mask data", extra={
            "instance_id": str(instance_id),
            "error": str(e)
        })
        raise HTTPException(status_code=500, detail=f"Failed to load mask data: {str(e)}")


# =============================================================================
# Upload Endpoints
# =============================================================================

@router.post("/upload/init", response_model=UploadInitResponse)
async def init_upload(
    request: UploadInitRequest,
    study_service: IStudyService = Depends(get_study_service),
    current_user: User = Depends(get_current_active_user)
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
    # CAPA-009 (RC-036): upload only into a study of a patient the caller may access, and
    # remember who started the upload so only they can complete it.
    await authorize_study_id(request.study_id, current_user)
    result = await study_service.init_upload(request)
    initiators.record("study-upload", getattr(result, "upload_id", None), current_user)
    return result


@router.post("/upload/complete", response_model=UploadCompleteResponse)
async def complete_upload(
    request: UploadCompleteRequest,
    study_service: IStudyService = Depends(get_study_service),
    current_user: User = Depends(get_current_active_user)
):
    """
    Complete a file upload.

    Verifies the upload, extracts metadata, and creates the instance record.

    Requires STUDY_UPLOAD permission.
    """
    initiators.authorize("study-upload", request.upload_id, current_user, "Upload")   # CAPA-009
    return await study_service.complete_upload(request)


# =============================================================================
# Download Endpoints
# =============================================================================

@router.get("/instances/{instance_id}/download-url")
async def get_instance_download_url(
    instance_id: UUID,
    expiration_minutes: int = Query(60, ge=5, le=1440, description="URL expiration in minutes"),
    study_service: IStudyService = Depends(get_study_service),
    current_user: User = Depends(get_current_active_user),
    _authorized=Depends(require_instance_access),   # CAPA-009 (RC-036)
):
    """
    Get a signed download URL for an instance of a patient the caller may access.
    """
    url = await study_service.get_download_url(instance_id, expiration_minutes)
    return {"url": url}


@router.get("/{study_id}/download-urls", response_model=DownloadUrlResponse)
async def get_study_download_urls(
    study_id: UUID,
    expiration_minutes: int = Query(60, ge=5, le=1440, description="URL expiration in minutes"),
    study_service: IStudyService = Depends(get_study_service),
    current_user: User = Depends(get_current_active_user),
    _authorized=Depends(require_study_access),   # CAPA-009 (RC-036)
):
    """
    Get download URLs for all instances in a study of a patient the caller may access.
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
    study_service: IStudyService = Depends(get_study_service),
    current_user: User = Depends(get_current_active_user),
    _authorized=Depends(require_patient_access),   # CAPA-009 (RC-036)
):
    """
    List all studies of a patient the caller may access.
    """
    studies, total = await study_service.list_patient_studies(patient_id, page, page_size)

    return StudyListResponse(
        items=studies,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size
    )
