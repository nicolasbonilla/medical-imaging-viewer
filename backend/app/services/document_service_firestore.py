"""
Document Service Implementation using Firebase Firestore.

Manages clinical documents with versioning and GCS storage.
Migrated from PostgreSQL to Firestore for cost optimization.

@module services.document_service_firestore
"""

import uuid
import secrets
import logging
from datetime import datetime, timedelta, date
from typing import Optional, List, Tuple, Dict, Any
from uuid import UUID

from google.cloud.firestore_v1 import FieldFilter

from app.core.firebase import (
    get_firestore_client,
    Collections,
)
from app.core.interfaces.document_interface import IDocumentService
from app.core.interfaces.storage_interface import IStorageService
from app.core.exceptions import NotFoundException, ValidationException
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
    DocumentCategory,
)

logger = logging.getLogger(__name__)


class DocumentServiceFirestore(IDocumentService):
    """
    Document service implementation with Firestore backend.

    Handles document management with versioning and GCS integration.
    """

    def __init__(self, storage_service: Optional[IStorageService] = None):
        """
        Initialize document service.

        Args:
            storage_service: GCS storage service (optional)
        """
        self.db = get_firestore_client()
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

    def _doc_to_response(self, doc_data: dict) -> DocumentResponse:
        """Convert Firestore document to DocumentResponse."""
        # Handle date conversions
        document_date = doc_data.get("document_date")
        if isinstance(document_date, str):
            document_date = date.fromisoformat(document_date)

        created_at = doc_data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        updated_at = doc_data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)

        created_by = doc_data.get("created_by")
        if created_by and isinstance(created_by, str):
            created_by = UUID(created_by)

        study_id = doc_data.get("study_id")
        if study_id and isinstance(study_id, str):
            study_id = UUID(study_id)

        return DocumentResponse(
            id=UUID(doc_data["id"]),
            patient_id=UUID(doc_data["patient_id"]),
            study_id=study_id,
            title=doc_data["title"],
            description=doc_data.get("description"),
            category=DocumentCategory(doc_data["category"]),
            document_date=document_date,
            status=DocumentStatus(doc_data.get("status", "current")),
            version=doc_data.get("version", 1),
            original_filename=doc_data["original_filename"],
            content_type=doc_data["content_type"],
            file_size_bytes=doc_data.get("file_size_bytes", 0),
            checksum_sha256=doc_data.get("checksum_sha256", ""),
            gcs_object_name=doc_data.get("gcs_object_name", ""),
            author_name=doc_data.get("author_name"),
            created_at=created_at,
            updated_at=updated_at,
            created_by=created_by
        )

    def _doc_to_summary(self, doc_data: dict) -> DocumentSummary:
        """Convert Firestore document to DocumentSummary."""
        document_date = doc_data.get("document_date")
        if isinstance(document_date, str):
            document_date = date.fromisoformat(document_date)

        created_at = doc_data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        return DocumentSummary(
            id=UUID(doc_data["id"]),
            patient_id=UUID(doc_data["patient_id"]),
            title=doc_data["title"],
            category=DocumentCategory(doc_data["category"]),
            document_date=document_date,
            status=DocumentStatus(doc_data.get("status", "current")),
            version=doc_data.get("version", 1),
            content_type=doc_data["content_type"],
            file_size_bytes=doc_data.get("file_size_bytes", 0),
            created_at=created_at
        )

    def _version_to_response(self, doc_data: dict) -> DocumentVersionResponse:
        """Convert Firestore document to DocumentVersionResponse."""
        created_at = doc_data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        created_by = doc_data.get("created_by")
        if created_by and isinstance(created_by, str):
            created_by = UUID(created_by)

        return DocumentVersionResponse(
            id=UUID(doc_data["id"]),
            document_id=UUID(doc_data["document_id"]),
            version=doc_data["version"],
            original_filename=doc_data["original_filename"],
            content_type=doc_data["content_type"],
            file_size_bytes=doc_data.get("file_size_bytes", 0),
            checksum_sha256=doc_data.get("checksum_sha256", ""),
            gcs_object_name=doc_data.get("gcs_object_name", ""),
            created_at=created_at,
            created_by=created_by,
            change_summary=doc_data.get("change_summary")
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
        document_id = str(uuid.uuid4())
        now = datetime.utcnow()

        doc_data = {
            "id": document_id,
            "patient_id": str(data.patient_id),
            "study_id": str(data.study_id) if data.study_id else None,
            "title": data.title,
            "description": data.description,
            "category": data.category.value,
            "document_date": data.document_date.isoformat() if data.document_date else None,
            "status": DocumentStatus.CURRENT.value,
            "version": 1,
            "original_filename": filename,
            "content_type": content_type,
            "file_size_bytes": file_size_bytes,
            "checksum_sha256": checksum_sha256,
            "gcs_object_name": gcs_object_name,
            "author_name": data.author_name,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "created_by": str(created_by) if created_by else None
        }

        # Create document
        self.db.collection(Collections.DOCUMENTS).document(document_id).set(doc_data)

        # Create initial version record in subcollection
        version_id = str(uuid.uuid4())
        version_data = {
            "id": version_id,
            "document_id": document_id,
            "version": 1,
            "original_filename": filename,
            "content_type": content_type,
            "file_size_bytes": file_size_bytes,
            "checksum_sha256": checksum_sha256,
            "gcs_object_name": gcs_object_name,
            "created_at": now.isoformat(),
            "created_by": str(created_by) if created_by else None
        }
        self.db.collection(Collections.DOCUMENTS).document(document_id).collection("versions").document(version_id).set(version_data)

        logger.info(
            "Document created",
            extra={"document_id": document_id, "patient_id": str(data.patient_id)}
        )

        return self._doc_to_response(doc_data)

    async def get_document(self, document_id: UUID) -> DocumentResponse:
        """Get a document by ID."""
        doc = self.db.collection(Collections.DOCUMENTS).document(str(document_id)).get()

        if not doc.exists:
            raise NotFoundException(f"Document {document_id} not found")

        doc_data = doc.to_dict()
        doc_data["id"] = doc.id

        return self._doc_to_response(doc_data)

    async def update_document(
        self,
        document_id: UUID,
        data: DocumentUpdate,
        updated_by: Optional[UUID] = None
    ) -> DocumentResponse:
        """Update document metadata."""
        doc_ref = self.db.collection(Collections.DOCUMENTS).document(str(document_id))
        doc = doc_ref.get()

        if not doc.exists:
            raise NotFoundException(f"Document {document_id} not found")

        # Build update data
        update_data = data.model_dump(exclude_unset=True)

        # Handle enum conversions
        if "category" in update_data and update_data["category"]:
            update_data["category"] = update_data["category"].value
        if "status" in update_data and update_data["status"]:
            update_data["status"] = update_data["status"].value
        if "document_date" in update_data and update_data["document_date"]:
            update_data["document_date"] = update_data["document_date"].isoformat()

        update_data["updated_at"] = datetime.utcnow().isoformat()

        # Update document
        doc_ref.update(update_data)

        logger.info("Document updated", extra={"document_id": str(document_id)})

        # Get updated document
        updated_doc = doc_ref.get()
        doc_data = updated_doc.to_dict()
        doc_data["id"] = updated_doc.id

        return self._doc_to_response(doc_data)

    async def delete_document(
        self,
        document_id: UUID,
        deleted_by: Optional[UUID] = None,
        hard_delete: bool = False
    ) -> bool:
        """Delete a document."""
        doc_ref = self.db.collection(Collections.DOCUMENTS).document(str(document_id))
        doc = doc_ref.get()

        if not doc.exists:
            raise NotFoundException(f"Document {document_id} not found")

        if hard_delete:
            # Delete all versions from GCS
            versions = doc_ref.collection("versions").stream()
            for version in versions:
                version_data = version.to_dict()
                if self.storage and version_data.get("gcs_object_name"):
                    try:
                        await self.storage.delete_file(version_data["gcs_object_name"])
                    except Exception as e:
                        logger.warning(f"Failed to delete GCS object: {e}")
                version.reference.delete()

            # Delete document
            doc_ref.delete()
        else:
            # Soft delete - mark as entered-in-error
            doc_ref.update({
                "status": DocumentStatus.ENTERED_IN_ERROR.value,
                "updated_at": datetime.utcnow().isoformat()
            })

        logger.info(
            "Document deleted",
            extra={"document_id": str(document_id), "hard_delete": hard_delete}
        )

        return True

    async def search_documents(
        self,
        search: DocumentSearch
    ) -> Tuple[List[DocumentSummary], int]:
        """Search documents with filters and pagination.

        Note: To avoid complex composite index requirements with inequality filters,
        we filter out 'entered-in-error' documents in memory rather than in the query.
        This is efficient because entered-in-error documents are rare (soft deletes).
        """
        query = self.db.collection(Collections.DOCUMENTS)

        # Apply filters (but NOT the status != filter to avoid complex index)
        if search.patient_id:
            query = query.where(filter=FieldFilter("patient_id", "==", str(search.patient_id)))

        if search.study_id:
            query = query.where(filter=FieldFilter("study_id", "==", str(search.study_id)))

        if search.category:
            query = query.where(filter=FieldFilter("category", "==", search.category.value))

        if search.status:
            # If specific status requested, filter for it
            query = query.where(filter=FieldFilter("status", "==", search.status.value))

        # Apply ordering
        query = query.order_by("created_at", direction="DESCENDING")

        # Fetch more than needed to account for filtered-out documents
        fetch_limit = (search.page * search.page_size) + 50
        docs = list(query.limit(fetch_limit).stream())

        # Filter out entered-in-error documents in memory (unless specific status was requested)
        if not search.status:
            docs = [
                doc for doc in docs
                if doc.to_dict().get("status") != DocumentStatus.ENTERED_IN_ERROR.value
            ]

        # Calculate total from filtered results
        total = len(docs)

        # Apply pagination
        offset = (search.page - 1) * search.page_size
        docs = docs[offset:offset + search.page_size]

        results = []
        for doc in docs:
            doc_data = doc.to_dict()
            doc_data["id"] = doc.id
            results.append(self._doc_to_summary(doc_data))

        return results, total

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
        doc_ref = self.db.collection(Collections.DOCUMENTS).document(str(document_id))
        doc = doc_ref.get()

        if not doc.exists:
            raise NotFoundException(f"Document {document_id} not found")

        doc_data = doc.to_dict()

        # Mark current as superseded and increment version
        new_version_num = doc_data.get("version", 1) + 1
        now = datetime.utcnow()

        # Create new version record
        version_id = str(uuid.uuid4())
        version_data = {
            "id": version_id,
            "document_id": str(document_id),
            "version": new_version_num,
            "original_filename": filename,
            "content_type": content_type,
            "file_size_bytes": file_size_bytes,
            "checksum_sha256": checksum_sha256,
            "gcs_object_name": gcs_object_name,
            "created_at": now.isoformat(),
            "created_by": str(created_by) if created_by else None,
            "change_summary": change_summary
        }
        doc_ref.collection("versions").document(version_id).set(version_data)

        # Update document with new version info
        doc_ref.update({
            "version": new_version_num,
            "original_filename": filename,
            "content_type": content_type,
            "file_size_bytes": file_size_bytes,
            "checksum_sha256": checksum_sha256,
            "gcs_object_name": gcs_object_name,
            "status": DocumentStatus.CURRENT.value,
            "updated_at": now.isoformat()
        })

        logger.info(
            "Document version created",
            extra={"document_id": str(document_id), "version": new_version_num}
        )

        return self._version_to_response(version_data)

    async def get_version(self, version_id: UUID) -> DocumentVersionResponse:
        """Get a specific version by ID."""
        # Search across all documents for this version
        docs = self.db.collection(Collections.DOCUMENTS).stream()

        for doc in docs:
            version_doc = doc.reference.collection("versions").document(str(version_id)).get()
            if version_doc.exists:
                doc_data = version_doc.to_dict()
                doc_data["id"] = version_doc.id
                return self._version_to_response(doc_data)

        raise NotFoundException(f"Version {version_id} not found")

    async def list_versions(self, document_id: UUID) -> List[DocumentVersionResponse]:
        """List all versions of a document."""
        versions = self.db.collection(Collections.DOCUMENTS).document(str(document_id)).collection("versions").order_by("version", direction="DESCENDING").stream()

        results = []
        for v in versions:
            doc_data = v.to_dict()
            doc_data["id"] = v.id
            results.append(self._version_to_response(doc_data))

        return results

    async def get_latest_version(self, document_id: UUID) -> DocumentVersionResponse:
        """Get the latest version of a document."""
        versions = self.db.collection(Collections.DOCUMENTS).document(str(document_id)).collection("versions").order_by("version", direction="DESCENDING").limit(1).get()

        version_list = list(versions)
        if not version_list:
            raise NotFoundException(f"No versions found for document {document_id}")

        doc_data = version_list[0].to_dict()
        doc_data["id"] = version_list[0].id
        return self._version_to_response(doc_data)

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
        signed_url = ""
        headers = {}

        if self.storage:
            url_response = await self.storage.generate_signed_upload_url(
                object_name=gcs_object_name,
                content_type=request.content_type,
                expiration_minutes=60
            )
            signed_url = url_response.url
            headers = getattr(url_response, 'headers', {}) or {}

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
            signed_url=signed_url,
            expires_at=expires_at,
            headers=headers,
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
        if self.storage:
            exists = await self.storage.file_exists(session["gcs_object_name"])
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

        document_id = str(session["document_id"])
        now = datetime.utcnow()

        doc_data = {
            "id": document_id,
            "patient_id": str(session["patient_id"]),
            "study_id": str(session["study_id"]) if session["study_id"] else None,
            "title": session["title"],
            "description": session["description"],
            "category": session["category"].value if hasattr(session["category"], 'value') else session["category"],
            "document_date": session["document_date"].isoformat() if session["document_date"] else None,
            "status": DocumentStatus.CURRENT.value,
            "version": 1,
            "original_filename": session["filename"],
            "content_type": session["content_type"],
            "file_size_bytes": session["file_size_bytes"],
            "checksum_sha256": request.checksum_sha256,
            "gcs_object_name": session["gcs_object_name"],
            "author_name": session["author_name"],
            "created_at": now.isoformat(),
            "created_by": str(session.get("user_id") or user_id) if (session.get("user_id") or user_id) else None
        }

        # Create document
        self.db.collection(Collections.DOCUMENTS).document(document_id).set(doc_data)

        # Create version record
        version_id = str(uuid.uuid4())
        version_data = {
            "id": version_id,
            "document_id": document_id,
            "version": 1,
            "original_filename": session["filename"],
            "content_type": session["content_type"],
            "file_size_bytes": session["file_size_bytes"],
            "checksum_sha256": request.checksum_sha256,
            "gcs_object_name": session["gcs_object_name"],
            "created_at": now.isoformat(),
            "created_by": str(session.get("user_id") or user_id) if (session.get("user_id") or user_id) else None
        }
        self.db.collection(Collections.DOCUMENTS).document(document_id).collection("versions").document(version_id).set(version_data)

        # Cleanup session
        del self._upload_sessions[request.upload_id]

        logger.info(
            "Document upload completed",
            extra={"document_id": document_id, "upload_id": request.upload_id}
        )

        return DocumentUploadCompleteResponse(
            document=self._doc_to_response(doc_data),
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
        doc = self.db.collection(Collections.DOCUMENTS).document(str(request.document_id)).get()

        if not doc.exists:
            raise NotFoundException(f"Document {request.document_id} not found")

        doc_data = doc.to_dict()
        new_version = doc_data.get("version", 1) + 1

        # Build GCS path for new version
        gcs_object_name = self._build_gcs_path(
            UUID(doc_data["patient_id"]),
            request.document_id,
            new_version,
            request.filename
        )

        # Generate signed upload URL
        expires_at = datetime.utcnow() + timedelta(hours=1)
        signed_url = ""
        headers = {}

        if self.storage:
            url_response = await self.storage.generate_signed_upload_url(
                object_name=gcs_object_name,
                content_type=request.content_type,
                expiration_minutes=60
            )
            signed_url = url_response.url
            headers = getattr(url_response, 'headers', {}) or {}

        # Store upload session
        upload_id = self._generate_upload_id()
        self._upload_sessions[upload_id] = {
            "type": "version",
            "document_id": request.document_id,
            "patient_id": UUID(doc_data["patient_id"]),
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
                "document_id": str(request.document_id),
                "new_version": new_version
            }
        )

        return VersionUploadInitResponse(
            upload_id=upload_id,
            signed_url=signed_url,
            expires_at=expires_at,
            headers=headers,
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
        if self.storage:
            exists = await self.storage.file_exists(session["gcs_object_name"])
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
            versions = self.db.collection(Collections.DOCUMENTS).document(str(document_id)).collection("versions").where(
                filter=FieldFilter("version", "==", version)
            ).limit(1).get()

            version_list = list(versions)
            if not version_list:
                raise NotFoundException(f"Version {version} not found for document {document_id}")

            ver_data = version_list[0].to_dict()
            gcs_path = ver_data.get("gcs_object_name", "")
            filename = ver_data.get("original_filename", "")
            content_type = ver_data.get("content_type", "application/octet-stream")
            ver_num = ver_data.get("version", 1)
        else:
            # Get latest from document
            doc = self.db.collection(Collections.DOCUMENTS).document(str(document_id)).get()

            if not doc.exists:
                raise NotFoundException(f"Document {document_id} not found")

            doc_data = doc.to_dict()
            gcs_path = doc_data.get("gcs_object_name", "")
            filename = doc_data.get("original_filename", "")
            content_type = doc_data.get("content_type", "application/octet-stream")
            ver_num = doc_data.get("version", 1)

        # Generate signed URL
        expires_at = datetime.utcnow() + timedelta(minutes=expiration_minutes)
        url = ""

        if self.storage and gcs_path:
            signed_url = await self.storage.generate_signed_download_url(
                object_name=gcs_path,
                expiration_minutes=expiration_minutes,
                filename=filename
            )
            url = signed_url.url

        return DocumentDownloadUrl(
            document_id=document_id,
            version=ver_num,
            url=url,
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
        docs = self.db.collection(Collections.DOCUMENTS).where(
            filter=FieldFilter("patient_id", "==", str(patient_id))
        ).where(
            filter=FieldFilter("status", "==", DocumentStatus.CURRENT.value)
        ).stream()

        urls = []
        for doc in docs:
            doc_data = doc.to_dict()
            url = await self.get_download_url(
                UUID(doc_data["id"]),
                expiration_minutes=expiration_minutes
            )
            urls.append(url)

        return urls
