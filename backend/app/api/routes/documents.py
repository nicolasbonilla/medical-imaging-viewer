"""
Documents API Routes.

Endpoints for clinical document management with versioning.

@module api.routes.documents
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from uuid import UUID
import math

from app.core.logging import get_logger
from app.core.exceptions import NotFoundException, ValidationException
from app.core.interfaces.document_interface import IDocumentService
from app.core.container import get_document_service
from app.core.config import get_settings
from app.models.document_schemas import (
    DocumentCreate,
    DocumentUpdate,
    DocumentResponse,
    DocumentSummary,
    DocumentListResponse,
    DocumentSearch,
    DocumentVersionResponse,
    DocumentUploadInit,
    DocumentUploadInitResponse,
    DocumentUploadComplete,
    DocumentUploadCompleteResponse,
    VersionUploadInit,
    VersionUploadInitResponse,
    VersionUploadComplete,
    VersionUploadCompleteResponse,
    DocumentDownloadUrl,
    DocumentCategory,
    DocumentStatus,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/documents", tags=["Documents"])

settings = get_settings()


# =============================================================================
# Document CRUD Endpoints (using Firestore via DI Container)
# =============================================================================

@router.get("", response_model=DocumentListResponse)
async def list_documents(
    patient_id: Optional[UUID] = Query(None, description="Filter by patient"),
    study_id: Optional[UUID] = Query(None, description="Filter by study"),
    category: Optional[DocumentCategory] = Query(None, description="Filter by category"),
    status: Optional[DocumentStatus] = Query(None, description="Filter by status"),
    query: Optional[str] = Query(None, description="Search in title/description"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    document_service: IDocumentService = Depends(get_document_service),
):
    """
    List documents with optional filters and pagination.
    """
    search = DocumentSearch(
        patient_id=patient_id,
        study_id=study_id,
        category=category,
        status=status,
        query=query,
        page=page,
        page_size=page_size,
    )

    documents, total = await document_service.search_documents(search)

    return DocumentListResponse(
        items=documents,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 1,
    )


@router.get("/patient/{patient_id}", response_model=DocumentListResponse)
async def list_patient_documents(
    patient_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    document_service: IDocumentService = Depends(get_document_service),
):
    """
    List all documents for a specific patient.
    """
    documents, total = await document_service.list_patient_documents(
        patient_id, page, page_size
    )

    return DocumentListResponse(
        items=documents,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 1,
    )


@router.get("/study/{study_id}", response_model=DocumentListResponse)
async def list_study_documents(
    study_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    document_service: IDocumentService = Depends(get_document_service),
):
    """
    List all documents linked to a specific study.
    """
    documents, total = await document_service.list_study_documents(
        study_id, page, page_size
    )

    return DocumentListResponse(
        items=documents,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 1,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    document_service: IDocumentService = Depends(get_document_service),
):
    """
    Get a document by ID.
    """
    try:
        return await document_service.get_document(document_id)
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: UUID,
    data: DocumentUpdate,
    document_service: IDocumentService = Depends(get_document_service),
):
    """
    Update document metadata.
    """
    try:
        return await document_service.update_document(document_id, data)
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{document_id}")
async def delete_document(
    document_id: UUID,
    hard_delete: bool = Query(False, description="Permanently delete from storage"),
    document_service: IDocumentService = Depends(get_document_service),
):
    """
    Delete a document. By default, marks as entered-in-error.
    Use hard_delete=true to permanently remove from storage.
    """
    try:
        await document_service.delete_document(document_id, hard_delete=hard_delete)
        return {"status": "deleted", "document_id": str(document_id)}
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


# =============================================================================
# Version Endpoints
# =============================================================================

@router.get("/{document_id}/versions", response_model=List[DocumentVersionResponse])
async def list_document_versions(
    document_id: UUID,
    document_service: IDocumentService = Depends(get_document_service),
):
    """
    List all versions of a document.
    """
    return await document_service.list_versions(document_id)


@router.get("/versions/{version_id}", response_model=DocumentVersionResponse)
async def get_version(
    version_id: UUID,
    document_service: IDocumentService = Depends(get_document_service),
):
    """
    Get a specific version by ID.
    """
    try:
        return await document_service.get_version(version_id)
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


# =============================================================================
# Upload Endpoints
# =============================================================================

@router.post("/upload/init", response_model=DocumentUploadInitResponse)
async def init_upload(
    request: DocumentUploadInit,
    document_service: IDocumentService = Depends(get_document_service),
):
    """
    Initialize a new document upload.

    Returns a signed URL for direct upload to Google Cloud Storage.
    After uploading to the signed URL, call /upload/complete to finalize.
    """
    try:
        return await document_service.init_upload(request)
    except ValidationException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/upload/complete", response_model=DocumentUploadCompleteResponse)
async def complete_upload(
    request: DocumentUploadComplete,
    document_service: IDocumentService = Depends(get_document_service),
):
    """
    Complete a document upload.

    Verifies the checksum and creates the document record.
    """
    try:
        return await document_service.complete_upload(request)
    except ValidationException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/versions/upload/init", response_model=VersionUploadInitResponse)
async def init_version_upload(
    request: VersionUploadInit,
    document_service: IDocumentService = Depends(get_document_service),
):
    """
    Initialize upload for a new document version.

    Returns a signed URL for uploading the new version.
    """
    try:
        return await document_service.init_version_upload(request)
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/versions/upload/complete", response_model=VersionUploadCompleteResponse)
async def complete_version_upload(
    request: VersionUploadComplete,
    document_service: IDocumentService = Depends(get_document_service),
):
    """
    Complete a version upload.

    Creates the new version and updates the document.
    """
    try:
        return await document_service.complete_version_upload(request)
    except ValidationException as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# Download Endpoints
# =============================================================================

@router.get("/{document_id}/download-url", response_model=DocumentDownloadUrl)
async def get_download_url(
    document_id: UUID,
    version: Optional[int] = Query(None, description="Specific version (default: latest)"),
    expiration_minutes: int = Query(60, ge=1, le=1440),
    document_service: IDocumentService = Depends(get_document_service),
):
    """
    Get a signed download URL for a document.

    Optionally specify a version number to download a specific version.
    """
    try:
        return await document_service.get_download_url(
            document_id,
            version=version,
            expiration_minutes=expiration_minutes,
        )
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/patient/{patient_id}/download-urls", response_model=List[DocumentDownloadUrl])
async def get_patient_download_urls(
    patient_id: UUID,
    expiration_minutes: int = Query(60, ge=1, le=1440),
    document_service: IDocumentService = Depends(get_document_service),
):
    """
    Get download URLs for all documents of a patient.
    """
    return await document_service.get_patient_documents_urls(
        patient_id, expiration_minutes=expiration_minutes
    )
