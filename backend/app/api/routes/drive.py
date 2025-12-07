from fastapi import APIRouter, Query, Depends
from typing import List, Optional

from app.models.schemas import DriveFileInfo
from app.core.interfaces.drive_interface import IDriveService
from app.core.container import get_drive_service

router = APIRouter(prefix="/drive", tags=["Google Drive"])


@router.get("/auth")
async def authenticate_drive(
    drive_service: IDriveService = Depends(get_drive_service)
):
    """
    Authenticate with Google Drive.

    Uses dependency injection to get DriveService instance.
    Custom exceptions will be caught by global exception handler.
    """
    success = drive_service.authenticate()
    return {"status": "authenticated" if success else "failed"}


@router.get("/folders", response_model=List[DriveFileInfo])
async def list_folders(
    parent_id: Optional[str] = Query(None, description="Parent folder ID"),
    drive_service: IDriveService = Depends(get_drive_service)
):
    """
    List all folders in Google Drive.

    Uses dependency injection to get DriveService instance.
    Custom exceptions will be caught by global exception handler.
    """
    folders = drive_service.list_folders(parent_folder_id=parent_id)
    return folders


@router.get("/files", response_model=List[DriveFileInfo])
async def list_files(
    folder_id: Optional[str] = Query(None, description="Folder ID to list files from"),
    page_size: int = Query(100, ge=1, le=1000, description="Number of files to return"),
    drive_service: IDriveService = Depends(get_drive_service)
):
    """
    List medical imaging files from Google Drive.

    Uses dependency injection to get DriveService instance.
    Custom exceptions will be caught by global exception handler.
    """
    files = await drive_service.list_files(folder_id=folder_id, page_size=page_size)
    return files


@router.get("/files/{file_id}/metadata", response_model=DriveFileInfo)
async def get_file_metadata(
    file_id: str,
    drive_service: IDriveService = Depends(get_drive_service)
):
    """
    Get metadata for a specific file.

    Uses dependency injection to get DriveService instance.
    Custom exceptions will be caught by global exception handler.
    """
    metadata = await drive_service.get_file_metadata(file_id)
    return metadata


@router.get("/files/{file_id}/download")
async def download_file(
    file_id: str,
    drive_service: IDriveService = Depends(get_drive_service)
):
    """
    Download a file from Google Drive.

    Uses dependency injection to get DriveService instance.
    Custom exceptions will be caught by global exception handler.
    """
    file_data = await drive_service.download_file(file_id)
    return {"file_id": file_id, "size": len(file_data), "status": "downloaded"}
