"""
DICOMweb Integration API Routes.

Provides PACS connection management, QIDO-RS study/series search,
and WADO-RS import with automatic DICOM-to-NIfTI conversion.

@module api.routes.dicomweb
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional

from app.security import get_current_active_user
from app.security.models import User
from app.core.logging import get_logger
from app.models.dicomweb_schemas import (
    PACSConnectionCreate, PACSConnectionResponse,
    StudySearchRequest, StudySearchResult,
    SeriesSearchResult,
    ImportRequest, ImportJobStatus,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/dicomweb", tags=["DICOMweb"])


def _get_dicomweb_service():
    """Lazy-initialize DICOMweb service."""
    if not hasattr(_get_dicomweb_service, '_instance'):
        from app.services.dicomweb_service import DICOMwebService
        from app.core.firebase import get_firestore_client
        from app.core.container import get_storage_service
        try:
            db = get_firestore_client()
        except Exception:
            db = None
        try:
            storage = get_storage_service()
        except Exception:
            storage = None
        _get_dicomweb_service._instance = DICOMwebService(db=db, storage_service=storage)
    return _get_dicomweb_service._instance


# ============================================================================
# PACS Connection Management
# ============================================================================

@router.post("/connections", response_model=PACSConnectionResponse)
async def create_connection(data: PACSConnectionCreate, current_user: User = Depends(get_current_active_user)):
    """Save a new PACS DICOMweb connection."""
    svc = _get_dicomweb_service()
    conn = await svc.save_connection(data.model_dump())
    conn["password"] = "***"
    return conn


@router.get("/connections")
async def list_connections(current_user: User = Depends(get_current_active_user)):
    """List all configured PACS connections."""
    svc = _get_dicomweb_service()
    conns = await svc.list_connections()
    for c in conns:
        c["password"] = "***"
        if c.get("bearer_token"):
            c["bearer_token"] = "***"
    return conns


@router.get("/connections/{connection_id}")
async def get_connection(connection_id: str, current_user: User = Depends(get_current_active_user)):
    """Get a single PACS connection (credentials redacted)."""
    svc = _get_dicomweb_service()
    conn = await svc.get_connection(connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    conn["password"] = "***"
    if conn.get("bearer_token"):
        conn["bearer_token"] = "***"
    return conn


@router.delete("/connections/{connection_id}")
async def delete_connection(connection_id: str, current_user: User = Depends(get_current_active_user)):
    """Delete a PACS connection."""
    svc = _get_dicomweb_service()
    await svc.delete_connection(connection_id)
    return {"status": "deleted"}


@router.post("/connections/{connection_id}/test")
async def test_connection(connection_id: str, current_user: User = Depends(get_current_active_user)):
    """Test PACS connectivity."""
    svc = _get_dicomweb_service()
    result = await svc.test_connection(connection_id)
    return result


# ============================================================================
# QIDO-RS Search
# ============================================================================

@router.post("/search/studies")
async def search_studies(request: StudySearchRequest, current_user: User = Depends(get_current_active_user)):
    """Search studies on a remote PACS via QIDO-RS."""
    svc = _get_dicomweb_service()
    try:
        results = await svc.search_studies(
            connection_id=request.connection_id,
            params=request.model_dump(exclude={"connection_id"}),
        )
        return results
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("QIDO-RS study search failed", extra={"error": str(e)})
        raise HTTPException(status_code=502, detail=f"PACS search failed: {str(e)}")


@router.post("/search/series")
async def search_series(connection_id: str, study_instance_uid: str, current_user: User = Depends(get_current_active_user)):
    """Search series within a study on a remote PACS via QIDO-RS."""
    svc = _get_dicomweb_service()
    try:
        results = await svc.search_series(connection_id, study_instance_uid)
        return results
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("QIDO-RS series search failed", extra={"error": str(e)})
        raise HTTPException(status_code=502, detail=f"PACS search failed: {str(e)}")


# ============================================================================
# WADO-RS Import
# ============================================================================

@router.post("/import")
async def start_import(request: ImportRequest, current_user: User = Depends(get_current_active_user)):
    """Start importing a DICOM series from PACS (async with job tracking)."""
    svc = _get_dicomweb_service()
    try:
        job_id = await svc.start_import(
            connection_id=request.connection_id,
            study_uid=request.study_instance_uid,
            series_uid=request.series_instance_uid,
            patient_id=request.patient_id,
            study_description=request.study_description,
        )
        return {"job_id": job_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("DICOMweb import start failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/import/{job_id}")
async def get_import_status(job_id: str, current_user: User = Depends(get_current_active_user)):
    """Poll import job status."""
    svc = _get_dicomweb_service()
    status = svc.get_import_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Import job not found")
    return status


@router.get("/imports")
async def list_imports(current_user: User = Depends(get_current_active_user)):
    """List all import jobs."""
    svc = _get_dicomweb_service()
    return list(svc._import_jobs.values())
