"""
Document Service Implementation.

Manages clinical documents with versioning and GCS storage.

@module services.document_service
"""

import uuid
import secrets
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload

from app.core.interfaces.document_interface import IDocumentService
from app.core.interfaces.storage_interface import IStorageService
from app.core.logging import get_logger
from app.core.exceptions import NotFoundException, ValidationException
from app.models.database import Document, DocumentVersion
from app.models.document_schemas import (
    DocumentCreate,
    DocumentUpdate,
    DocumentResponse,
    DocumentSummary,
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
    DocumentStatus,
)

logger = get_logger(__name__)


class DocumentService(IDocumentService):
    """
    Document service implementation.

    Handles document management with versioning and GCS integration.
    """

    def __init__(self, db: AsyncSession, storage_service: IStorageService):
        """
        Initialize document service.

        Args:
            db: Async database session
            storage_service: GCS storage service
        """
        self.db = db
        self.storage = storage_service
        self._upload_sessions: Dict[str, Dict[str, Any]] = {}

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _generate_upload_id(self) -> str:
        """Generate unique upload session ID."""
        return secrets.token_urlsafe(32)

    def _build_gcs_path(self, patient_id: UUID, document_id: UUID, version: int, filename: str) -> str:
        """
        Build GCS object path for a document version.

        Structure: patients/{patient_id}/documents/{document_id}/v{version}/{filename}
        """
        return f"patients/{patient_id}/documents/{document_id}/v{version}/{filename}"

    def _to_response(self, doc: Document) -> DocumentResponse:
        """Convert Document ORM to response schema."""
        return DocumentResponse(
            id=doc.id,
            patient_id=doc.patient_id,
            study_id=doc.study_id,
            title=doc.title,
            description=doc.description,
            category=doc.category,
            document_date=doc.document_date,
            status=doc.status,
            version=doc.version,
            original_filename=doc.original_filename,
            content_type=doc.content_type,
            file_size_bytes=doc.file_size_bytes,
            checksum_sha256=doc.checksum_sha256,
            gcs_object_name=doc.gcs_object_name,
            author_name=doc.author_name,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            created_by=doc.created_by,
        )

    def _to_summary(self, doc: Document) -> DocumentSummary:
        """Convert Document ORM to summary schema."""
        return DocumentSummary(
            id=doc.id,
            patient_id=doc.patient_id,
            title=doc.title,
            category=doc.category,
            document_date=doc.document_date,
            status=doc.status,
            version=doc.version,
            content_type=doc.content_type,
            file_size_bytes=doc.file_size_bytes,
            created_at=doc.created_at,
        )

    def _to_version_response(self, version: DocumentVersion) -> DocumentVersionResponse:
        """Convert DocumentVersion ORM to response schema."""
        return DocumentVersionResponse(
            id=version.id,
            document_id=version.document_id,
            version=version.version,
            original_filename=version.original_filename,
            content_type=version.content_type,
            file_size_bytes=version.file_size_bytes,
            checksum_sha256=version.checksum_sha256,
            gcs_object_name=version.gcs_object_name,
            created_at=version.created_at,
            created_by=version.created_by,
            change_summary=version.change_summary,
        )

    # =========================================================================
    # Document CRUD Operations
    # =========================================================================

    async def create_document(
        self,
        data: DocumentCreate,
        filename: str,
        content_type: str,
        file_size_bytes: int,
        checksum_sha256: str,
        gcs_object_name: str,
        created_by: Optional[UUID] = None
    ) -> DocumentResponse:
        """Create a new document record."""
        doc = Document(
            id=uuid.uuid4(),
            patient_id=data.patient_id,
            study_id=data.study_id,
            title=data.title,
            description=data.description,
            category=data.category,
            document_date=data.document_date,
            status=DocumentStatus.CURRENT,
            version=1,
            original_filename=filename,
            content_type=content_type,
            file_size_bytes=file_size_bytes,
            checksum_sha256=checksum_sha256,
            gcs_object_name=gcs_object_name,
            author_name=data.author_name,
            created_at=datetime.utcnow(),
            created_by=created_by,
        )

        self.db.add(doc)

        # Create initial version record
        version = DocumentVersion(
            id=uuid.uuid4(),
            document_id=doc.id,
            version=1,
            original_filename=filename,
            content_type=content_type,
            file_size_bytes=file_size_bytes,
            checksum_sha256=checksum_sha256,
            gcs_object_name=gcs_object_name,
            created_at=datetime.utcnow(),
            created_by=created_by,
        )
        self.db.add(version)

        await self.db.commit()
        await self.db.refresh(doc)

        logger.info(
            "Document created",
            extra={"document_id": str(doc.id), "patient_id": str(data.patient_id)}
        )

        return self._to_response(doc)

    async def get_document(self, document_id: UUID) -> DocumentResponse:
        """Get a document by ID."""
        result = await self.db.execute(
            select(Document).where(Document.id == document_id)
        )
        doc = result.scalar_one_or_none()

        if not doc:
            raise NotFoundException(f"Document {document_id} not found")

        return self._to_response(doc)

    async def update_document(
        self,
        document_id: UUID,
        data: DocumentUpdate,
        updated_by: Optional[UUID] = None
    ) -> DocumentResponse:
        """Update document metadata."""
        result = await self.db.execute(
            select(Document).where(Document.id == document_id)
        )
        doc = result.scalar_one_or_none()

        if not doc:
            raise NotFoundException(f"Document {document_id} not found")

        # Update fields
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(doc, field, value)

        doc.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(doc)

        logger.info("Document updated", extra={"document_id": str(document_id)})

        return self._to_response(doc)

    async def delete_document(
        self,
        document_id: UUID,
        deleted_by: Optional[UUID] = None,
        hard_delete: bool = False
    ) -> bool:
        """Delete a document."""
        result = await self.db.execute(
            select(Document).where(Document.id == document_id)
        )
        doc = result.scalar_one_or_none()

        if not doc:
            raise NotFoundException(f"Document {document_id} not found")

        if hard_delete:
            # Delete all versions from GCS
            versions = await self.db.execute(
                select(DocumentVersion).where(DocumentVersion.document_id == document_id)
            )
            for version in versions.scalars().all():
                try:
                    await self.storage.delete(version.gcs_object_name)
                except Exception as e:
                    logger.warning(f"Failed to delete GCS object: {e}")

            # Delete version records
            await self.db.execute(
                DocumentVersion.__table__.delete().where(
                    DocumentVersion.document_id == document_id
                )
            )

            # Delete document
            await self.db.delete(doc)
        else:
            # Soft delete - mark as entered-in-error
            doc.status = DocumentStatus.ENTERED_IN_ERROR
            doc.updated_at = datetime.utcnow()

        await self.db.commit()

        logger.info(
            "Document deleted",
            extra={"document_id": str(document_id), "hard_delete": hard_delete}
        )

        return True

    async def search_documents(
        self,
        search: DocumentSearch
    ) -> Tuple[List[DocumentSummary], int]:
        """Search documents with filters and pagination."""
        query = select(Document).where(
            Document.status != DocumentStatus.ENTERED_IN_ERROR
        )

        # Apply filters
        if search.patient_id:
            query = query.where(Document.patient_id == search.patient_id)

        if search.study_id:
            query = query.where(Document.study_id == search.study_id)

        if search.category:
            query = query.where(Document.category == search.category)

        if search.status:
            query = query.where(Document.status == search.status)

        if search.date_from:
            query = query.where(Document.document_date >= search.date_from)

        if search.date_to:
            query = query.where(Document.document_date <= search.date_to)

        if search.query:
            search_term = f"%{search.query}%"
            query = query.where(
                or_(
                    Document.title.ilike(search_term),
                    Document.description.ilike(search_term)
                )
            )

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0

        # Apply pagination
        offset = (search.page - 1) * search.page_size
        query = query.order_by(Document.created_at.desc())
        query = query.offset(offset).limit(search.page_size)

        result = await self.db.execute(query)
        documents = result.scalars().all()

        return [self._to_summary(doc) for doc in documents], total

    async def list_patient_documents(
        self,
        patient_id: UUID,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[DocumentSummary], int]:
        """List all documents for a patient."""
        search = DocumentSearch(
            patient_id=patient_id,
            page=page,
            page_size=page_size
        )
        return await self.search_documents(search)

    async def list_study_documents(
        self,
        study_id: UUID,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[DocumentSummary], int]:
        """List all documents linked to a study."""
        search = DocumentSearch(
            study_id=study_id,
            page=page,
            page_size=page_size
        )
        return await self.search_documents(search)

    # =========================================================================
    # Version Operations
    # =========================================================================

    async def create_version(
        self,
        document_id: UUID,
        filename: str,
        content_type: str,
        file_size_bytes: int,
        checksum_sha256: str,
        gcs_object_name: str,
        change_summary: Optional[str] = None,
        created_by: Optional[UUID] = None
    ) -> DocumentVersionResponse:
        """Create a new version of a document."""
        # Get document
        result = await self.db.execute(
            select(Document).where(Document.id == document_id)
        )
        doc = result.scalar_one_or_none()

        if not doc:
            raise NotFoundException(f"Document {document_id} not found")

        # Mark current version as superseded
        doc.status = DocumentStatus.SUPERSEDED

        # Increment version
        new_version_num = doc.version + 1

        # Create new version record
        version = DocumentVersion(
            id=uuid.uuid4(),
            document_id=document_id,
            version=new_version_num,
            original_filename=filename,
            content_type=content_type,
            file_size_bytes=file_size_bytes,
            checksum_sha256=checksum_sha256,
            gcs_object_name=gcs_object_name,
            created_at=datetime.utcnow(),
            created_by=created_by,
            change_summary=change_summary,
        )
        self.db.add(version)

        # Update document with new version info
        doc.version = new_version_num
        doc.original_filename = filename
        doc.content_type = content_type
        doc.file_size_bytes = file_size_bytes
        doc.checksum_sha256 = checksum_sha256
        doc.gcs_object_name = gcs_object_name
        doc.status = DocumentStatus.CURRENT
        doc.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(version)

        logger.info(
            "Document version created",
            extra={"document_id": str(document_id), "version": new_version_num}
        )

        return self._to_version_response(version)

    async def get_version(self, version_id: UUID) -> DocumentVersionResponse:
        """Get a specific version by ID."""
        result = await self.db.execute(
            select(DocumentVersion).where(DocumentVersion.id == version_id)
        )
        version = result.scalar_one_or_none()

        if not version:
            raise NotFoundException(f"Version {version_id} not found")

        return self._to_version_response(version)

    async def list_versions(self, document_id: UUID) -> List[DocumentVersionResponse]:
        """List all versions of a document."""
        result = await self.db.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version.desc())
        )
        versions = result.scalars().all()

        return [self._to_version_response(v) for v in versions]

    async def get_latest_version(self, document_id: UUID) -> DocumentVersionResponse:
        """Get the latest version of a document."""
        result = await self.db.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version.desc())
            .limit(1)
        )
        version = result.scalar_one_or_none()

        if not version:
            raise NotFoundException(f"No versions found for document {document_id}")

        return self._to_version_response(version)

    # =========================================================================
    # Upload Operations
    # =========================================================================

    async def init_upload(
        self,
        request: DocumentUploadInit,
        user_id: Optional[UUID] = None
    ) -> DocumentUploadInitResponse:
        """Initialize a new document upload."""
        # Create document ID upfront
        document_id = uuid.uuid4()

        # Build GCS path
        gcs_object_name = self._build_gcs_path(
            request.patient_id,
            document_id,
            1,  # First version
            request.filename
        )

        # Generate signed upload URL
        expires_at = datetime.utcnow() + timedelta(hours=1)
        signed_url = await self.storage.generate_signed_upload_url(
            object_name=gcs_object_name,
            content_type=request.content_type,
            expires_at=expires_at,
            size_bytes=request.file_size_bytes,
        )

        # Store upload session
        upload_id = self._generate_upload_id()
        self._upload_sessions[upload_id] = {
            "document_id": document_id,
            "patient_id": request.patient_id,
            "study_id": request.study_id,
            "title": request.title,
            "description": request.description,
            "category": request.category,
            "document_date": request.document_date,
            "author_name": request.author_name,
            "filename": request.filename,
            "content_type": request.content_type,
            "file_size_bytes": request.file_size_bytes,
            "gcs_object_name": gcs_object_name,
            "user_id": user_id,
            "created_at": datetime.utcnow(),
        }

        logger.info(
            "Document upload initialized",
            extra={"upload_id": upload_id, "document_id": str(document_id)}
        )

        return DocumentUploadInitResponse(
            upload_id=upload_id,
            signed_url=signed_url.url,
            expires_at=expires_at,
            headers=signed_url.headers or {},
            document_id=document_id,
            gcs_object_name=gcs_object_name,
        )

    async def complete_upload(
        self,
        request: DocumentUploadComplete,
        user_id: Optional[UUID] = None
    ) -> DocumentUploadCompleteResponse:
        """Complete an upload and finalize the document."""
        session = self._upload_sessions.get(request.upload_id)
        if not session:
            raise ValidationException(f"Upload session {request.upload_id} not found or expired")

        # Verify file exists in GCS
        exists = await self.storage.exists(session["gcs_object_name"])
        if not exists:
            raise ValidationException("File not found in storage")

        # Create document record
        doc_create = DocumentCreate(
            patient_id=session["patient_id"],
            study_id=session["study_id"],
            title=session["title"],
            description=session["description"],
            category=session["category"],
            document_date=session["document_date"],
            author_name=session["author_name"],
        )

        # Use document ID from session
        doc = Document(
            id=session["document_id"],
            patient_id=session["patient_id"],
            study_id=session["study_id"],
            title=session["title"],
            description=session["description"],
            category=session["category"],
            document_date=session["document_date"],
            status=DocumentStatus.CURRENT,
            version=1,
            original_filename=session["filename"],
            content_type=session["content_type"],
            file_size_bytes=session["file_size_bytes"],
            checksum_sha256=request.checksum_sha256,
            gcs_object_name=session["gcs_object_name"],
            author_name=session["author_name"],
            created_at=datetime.utcnow(),
            created_by=session.get("user_id") or user_id,
        )

        self.db.add(doc)

        # Create version record
        version = DocumentVersion(
            id=uuid.uuid4(),
            document_id=doc.id,
            version=1,
            original_filename=session["filename"],
            content_type=session["content_type"],
            file_size_bytes=session["file_size_bytes"],
            checksum_sha256=request.checksum_sha256,
            gcs_object_name=session["gcs_object_name"],
            created_at=datetime.utcnow(),
            created_by=session.get("user_id") or user_id,
        )
        self.db.add(version)

        await self.db.commit()
        await self.db.refresh(doc)

        # Cleanup session
        del self._upload_sessions[request.upload_id]

        logger.info(
            "Document upload completed",
            extra={"document_id": str(doc.id), "upload_id": request.upload_id}
        )

        return DocumentUploadCompleteResponse(
            document=self._to_response(doc),
            is_new_version=False,
            version_count=1,
        )

    async def init_version_upload(
        self,
        request: VersionUploadInit,
        user_id: Optional[UUID] = None
    ) -> VersionUploadInitResponse:
        """Initialize upload for a new version."""
        # Get existing document
        result = await self.db.execute(
            select(Document).where(Document.id == request.document_id)
        )
        doc = result.scalar_one_or_none()

        if not doc:
            raise NotFoundException(f"Document {request.document_id} not found")

        new_version = doc.version + 1

        # Build GCS path for new version
        gcs_object_name = self._build_gcs_path(
            doc.patient_id,
            doc.id,
            new_version,
            request.filename
        )

        # Generate signed upload URL
        expires_at = datetime.utcnow() + timedelta(hours=1)
        signed_url = await self.storage.generate_signed_upload_url(
            object_name=gcs_object_name,
            content_type=request.content_type,
            expires_at=expires_at,
            size_bytes=request.file_size_bytes,
        )

        # Store upload session
        upload_id = self._generate_upload_id()
        self._upload_sessions[upload_id] = {
            "type": "version",
            "document_id": doc.id,
            "patient_id": doc.patient_id,
            "new_version": new_version,
            "filename": request.filename,
            "content_type": request.content_type,
            "file_size_bytes": request.file_size_bytes,
            "gcs_object_name": gcs_object_name,
            "change_summary": request.change_summary,
            "user_id": user_id,
            "created_at": datetime.utcnow(),
        }

        logger.info(
            "Version upload initialized",
            extra={
                "upload_id": upload_id,
                "document_id": str(doc.id),
                "new_version": new_version
            }
        )

        return VersionUploadInitResponse(
            upload_id=upload_id,
            signed_url=signed_url.url,
            expires_at=expires_at,
            headers=signed_url.headers or {},
            new_version=new_version,
            gcs_object_name=gcs_object_name,
        )

    async def complete_version_upload(
        self,
        request: VersionUploadComplete,
        user_id: Optional[UUID] = None
    ) -> VersionUploadCompleteResponse:
        """Complete a version upload."""
        session = self._upload_sessions.get(request.upload_id)
        if not session or session.get("type") != "version":
            raise ValidationException(f"Version upload session {request.upload_id} not found")

        # Verify file exists
        exists = await self.storage.exists(session["gcs_object_name"])
        if not exists:
            raise ValidationException("File not found in storage")

        # Create new version
        version_response = await self.create_version(
            document_id=session["document_id"],
            filename=session["filename"],
            content_type=session["content_type"],
            file_size_bytes=session["file_size_bytes"],
            checksum_sha256=request.checksum_sha256,
            gcs_object_name=session["gcs_object_name"],
            change_summary=session.get("change_summary"),
            created_by=session.get("user_id") or user_id,
        )

        # Get updated document
        doc_response = await self.get_document(session["document_id"])

        # Cleanup session
        del self._upload_sessions[request.upload_id]

        logger.info(
            "Version upload completed",
            extra={
                "document_id": str(session["document_id"]),
                "version": version_response.version
            }
        )

        return VersionUploadCompleteResponse(
            document=doc_response,
            version=version_response,
        )

    # =========================================================================
    # Download Operations
    # =========================================================================

    async def get_download_url(
        self,
        document_id: UUID,
        version: Optional[int] = None,
        expiration_minutes: int = 60
    ) -> DocumentDownloadUrl:
        """Get a signed download URL for a document."""
        if version:
            # Get specific version
            result = await self.db.execute(
                select(DocumentVersion).where(
                    and_(
                        DocumentVersion.document_id == document_id,
                        DocumentVersion.version == version
                    )
                )
            )
            ver = result.scalar_one_or_none()

            if not ver:
                raise NotFoundException(f"Version {version} not found for document {document_id}")

            gcs_path = ver.gcs_object_name
            filename = ver.original_filename
            content_type = ver.content_type
            ver_num = ver.version
        else:
            # Get latest from document
            result = await self.db.execute(
                select(Document).where(Document.id == document_id)
            )
            doc = result.scalar_one_or_none()

            if not doc:
                raise NotFoundException(f"Document {document_id} not found")

            gcs_path = doc.gcs_object_name
            filename = doc.original_filename
            content_type = doc.content_type
            ver_num = doc.version

        # Generate signed URL
        expires_at = datetime.utcnow() + timedelta(minutes=expiration_minutes)
        signed_url = await self.storage.generate_signed_download_url(
            object_name=gcs_path,
            expires_at=expires_at,
            content_disposition=f'attachment; filename="{filename}"',
        )

        return DocumentDownloadUrl(
            document_id=document_id,
            version=ver_num,
            url=signed_url.url,
            filename=filename,
            content_type=content_type,
            expires_at=expires_at,
        )

    async def get_patient_documents_urls(
        self,
        patient_id: UUID,
        expiration_minutes: int = 60
    ) -> List[DocumentDownloadUrl]:
        """Get download URLs for all patient documents."""
        result = await self.db.execute(
            select(Document).where(
                and_(
                    Document.patient_id == patient_id,
                    Document.status == DocumentStatus.CURRENT
                )
            )
        )
        documents = result.scalars().all()

        urls = []
        for doc in documents:
            url = await self.get_download_url(doc.id, expiration_minutes=expiration_minutes)
            urls.append(url)

        return urls
