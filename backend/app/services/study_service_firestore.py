"""
Study Service Implementation using Firebase Firestore.

Manages imaging studies, series, and instances with GCS storage integration.
Migrated from PostgreSQL to Firestore for cost optimization.

@module services.study_service_firestore
"""

import uuid
import logging
from typing import Optional, List, Tuple
from uuid import UUID
from datetime import datetime, timedelta, date

from google.cloud.firestore_v1 import FieldFilter

from app.core.firebase import (
    get_firestore_client,
    Collections,
)
from app.core.interfaces.study_interface import IStudyService
from app.core.interfaces.storage_interface import IStorageService
from app.core.exceptions import NotFoundException, ValidationException, ConflictException
from app.core.config import get_settings
from app.models.study_schemas import (
    StudyCreate, StudyUpdate, StudyResponse, StudySummary, StudySearch,
    SeriesCreate, SeriesResponse,
    InstanceCreate, InstanceResponse,
    UploadInitRequest, UploadInitResponse,
    UploadCompleteRequest, UploadCompleteResponse,
    StudyStatus, SeriesStatus, Modality
)

logger = logging.getLogger(__name__)
settings = get_settings()


class StudyServiceFirestore(IStudyService):
    """
    Imaging study service with Firestore backend and GCS storage integration.
    """

    def __init__(self, storage_service: Optional[IStorageService] = None):
        """
        Initialize study service.

        Args:
            storage_service: GCS storage service (optional)
        """
        self.db = get_firestore_client()
        self.storage = storage_service
        # Upload sessions stored in Firestore for Cloud Run compatibility
        # Collection: upload_sessions

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _generate_uid(self) -> str:
        """Generate a DICOM-compliant UID."""
        uid_uuid = uuid.uuid4()
        uid_int = int(uid_uuid.hex, 16)
        return f"2.25.{uid_int}"

    def _generate_accession_number(self) -> str:
        """Generate a unique accession number."""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        random_part = uuid.uuid4().hex[:6].upper()
        return f"ACC-{timestamp}-{random_part}"

    def _build_gcs_prefix(self, patient_id: UUID, study_id: UUID) -> str:
        """Build GCS path prefix for a study."""
        return f"patients/{patient_id}/studies/{study_id}"

    def _build_series_path(self, study_prefix: str, series_id: UUID) -> str:
        """Build GCS path for a series."""
        return f"{study_prefix}/series/{series_id}"

    def _build_instance_path(self, series_path: str, instance_id: UUID, filename: str) -> str:
        """Build GCS object name for an instance."""
        ext = filename.rsplit('.', 1)[-1] if '.' in filename else ''
        ext_suffix = f".{ext}" if ext else ''
        return f"{series_path}/{instance_id}{ext_suffix}"

    def _doc_to_response(
        self,
        doc_data: dict,
        series_count: Optional[int] = None,
        instance_count: Optional[int] = None,
        total_size: Optional[int] = None
    ) -> StudyResponse:
        """Convert Firestore document to StudyResponse."""
        # Handle date conversions
        study_date = doc_data.get("study_date")
        if isinstance(study_date, str):
            study_date = datetime.fromisoformat(study_date)

        created_at = doc_data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        updated_at = doc_data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)

        return StudyResponse(
            id=UUID(doc_data["id"]),
            patient_id=UUID(doc_data["patient_id"]),
            accession_number=doc_data["accession_number"],
            study_instance_uid=doc_data["study_instance_uid"],
            status=StudyStatus(doc_data.get("status", "registered")),
            modality=Modality(doc_data["modality"]),
            study_date=study_date,
            study_description=doc_data.get("study_description"),
            body_site=doc_data.get("body_site"),
            laterality=doc_data.get("laterality"),
            reason_for_study=doc_data.get("reason_for_study"),
            referring_physician_name=doc_data.get("referring_physician_name"),
            referring_physician_id=doc_data.get("referring_physician_id"),
            performing_physician_name=doc_data.get("performing_physician_name"),
            institution_name=doc_data.get("institution_name"),
            gcs_bucket=doc_data.get("gcs_bucket"),
            gcs_prefix=doc_data.get("gcs_prefix"),
            clinical_notes=doc_data.get("clinical_notes"),
            created_at=created_at,
            updated_at=updated_at,
            series_count=series_count,
            instance_count=instance_count,
            total_size_bytes=total_size
        )

    def _doc_to_summary(
        self,
        doc_data: dict,
        series_count: Optional[int] = None,
        instance_count: Optional[int] = None,
        total_size_bytes: Optional[int] = None
    ) -> StudySummary:
        """Convert Firestore document to StudySummary."""
        study_date = doc_data.get("study_date")
        if isinstance(study_date, str):
            study_date = datetime.fromisoformat(study_date)

        return StudySummary(
            id=UUID(doc_data["id"]),
            patient_id=UUID(doc_data["patient_id"]),
            accession_number=doc_data["accession_number"],
            modality=Modality(doc_data["modality"]),
            study_date=study_date,
            study_description=doc_data.get("study_description"),
            body_site=doc_data.get("body_site"),
            status=StudyStatus(doc_data.get("status", "registered")),
            series_count=series_count,
            instance_count=instance_count,
            total_size_bytes=total_size_bytes
        )

    def _series_to_response(
        self,
        doc_data: dict,
        instance_count: Optional[int] = None,
        total_size: Optional[int] = None
    ) -> SeriesResponse:
        """Convert Firestore document to SeriesResponse."""
        created_at = doc_data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        return SeriesResponse(
            id=UUID(doc_data["id"]),
            study_id=UUID(doc_data["study_id"]),
            series_instance_uid=doc_data["series_instance_uid"],
            series_number=doc_data["series_number"],
            modality=Modality(doc_data["modality"]),
            series_description=doc_data.get("series_description"),
            body_part_examined=doc_data.get("body_part_examined"),
            status=SeriesStatus(doc_data.get("status", "uploading")),
            gcs_path=doc_data.get("gcs_path"),
            created_at=created_at,
            instance_count=instance_count,
            total_size_bytes=total_size
        )

    def _instance_to_response(self, doc_data: dict) -> InstanceResponse:
        """Convert Firestore document to InstanceResponse."""
        created_at = doc_data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        return InstanceResponse(
            id=UUID(doc_data["id"]),
            series_id=UUID(doc_data["series_id"]),
            sop_instance_uid=doc_data["sop_instance_uid"],
            sop_class_uid=doc_data.get("sop_class_uid"),
            instance_number=doc_data.get("instance_number"),
            gcs_object_name=doc_data.get("gcs_object_name", ""),
            original_filename=doc_data["original_filename"],
            file_size_bytes=doc_data.get("file_size_bytes", 0),
            content_type=doc_data.get("content_type", "application/octet-stream"),
            checksum_sha256=doc_data.get("checksum_sha256", ""),
            rows=doc_data.get("rows"),
            columns=doc_data.get("columns"),
            bits_allocated=doc_data.get("bits_allocated"),
            pixel_spacing=doc_data.get("pixel_spacing"),
            slice_thickness=doc_data.get("slice_thickness"),
            slice_location=doc_data.get("slice_location"),
            window_center=doc_data.get("window_center"),
            window_width=doc_data.get("window_width"),
            dicom_metadata=doc_data.get("dicom_metadata"),
            created_at=created_at
        )

    # =========================================================================
    # Study Operations
    # =========================================================================

    async def create_study(
        self,
        data: StudyCreate,
        created_by: Optional[UUID] = None
    ) -> StudyResponse:
        """Create a new imaging study."""
        # Verify patient exists
        patient_doc = self.db.collection(Collections.PATIENTS).document(str(data.patient_id)).get()
        if not patient_doc.exists:
            raise NotFoundException(
                message="Patient not found",
                error_code="PATIENT_NOT_FOUND",
                details={"patient_id": str(data.patient_id)}
            )

        # Generate UIDs and accession number
        study_uid = self._generate_uid()
        accession = self._generate_accession_number()
        study_id = str(uuid.uuid4())
        now = datetime.utcnow()

        # Build GCS prefix
        gcs_prefix = self._build_gcs_prefix(data.patient_id, UUID(study_id))

        # Build document data
        study_data = {
            "id": study_id,
            "patient_id": str(data.patient_id),
            "accession_number": accession,
            "study_instance_uid": study_uid,
            "status": StudyStatus.REGISTERED.value,
            "modality": data.modality.value,
            "study_date": data.study_date.isoformat() if data.study_date else None,
            "study_description": data.study_description,
            "body_site": data.body_site,
            "laterality": data.laterality,
            "reason_for_study": data.reason_for_study,
            "referring_physician_name": data.referring_physician_name,
            "referring_physician_id": data.referring_physician_id,
            "performing_physician_name": data.performing_physician_name,
            "institution_name": data.institution_name,
            "gcs_bucket": getattr(settings, 'GCS_BUCKET_NAME', None),
            "gcs_prefix": gcs_prefix,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "created_by": str(created_by) if created_by else None
        }

        # Create document
        self.db.collection(Collections.STUDIES).document(study_id).set(study_data)

        logger.info(
            "Study created",
            extra={
                "study_id": study_id,
                "accession": accession,
                "patient_id": str(data.patient_id),
                "modality": data.modality.value
            }
        )

        return self._doc_to_response(study_data, series_count=0, instance_count=0, total_size=0)

    async def get_study(
        self,
        study_id: UUID,
        include_stats: bool = False
    ) -> StudyResponse:
        """Get a study by ID."""
        doc = self.db.collection(Collections.STUDIES).document(str(study_id)).get()

        if not doc.exists:
            raise NotFoundException(
                message="Study not found",
                error_code="STUDY_NOT_FOUND",
                details={"study_id": str(study_id)}
            )

        doc_data = doc.to_dict()
        doc_data["id"] = doc.id

        series_count = None
        instance_count = None
        total_size = None

        if include_stats:
            # Count series for this study
            series_docs = self.db.collection(Collections.STUDIES).document(str(study_id)).collection("series").count().get()
            series_count = series_docs[0][0].value if series_docs else 0

            # Count instances and sum sizes
            instance_count = 0
            total_size = 0
            series_stream = self.db.collection(Collections.STUDIES).document(str(study_id)).collection("series").stream()
            for series_doc in series_stream:
                instances = series_doc.reference.collection("instances").stream()
                for inst in instances:
                    instance_count += 1
                    inst_data = inst.to_dict()
                    total_size += inst_data.get("file_size_bytes", 0)

        return self._doc_to_response(doc_data, series_count, instance_count, total_size)

    async def get_study_by_accession(
        self,
        accession_number: str
    ) -> Optional[StudyResponse]:
        """Get a study by accession number."""
        docs = self.db.collection(Collections.STUDIES).where(
            filter=FieldFilter("accession_number", "==", accession_number)
        ).limit(1).get()

        doc_list = list(docs)
        if not doc_list:
            return None

        doc = doc_list[0]
        doc_data = doc.to_dict()
        doc_data["id"] = doc.id

        return self._doc_to_response(doc_data)

    async def update_study(
        self,
        study_id: UUID,
        data: StudyUpdate,
        updated_by: Optional[UUID] = None
    ) -> StudyResponse:
        """Update a study."""
        doc_ref = self.db.collection(Collections.STUDIES).document(str(study_id))
        doc = doc_ref.get()

        if not doc.exists:
            raise NotFoundException(
                message="Study not found",
                error_code="STUDY_NOT_FOUND",
                details={"study_id": str(study_id)}
            )

        # Build update data
        update_data = data.model_dump(exclude_unset=True)

        # Handle status enum
        if 'status' in update_data and update_data['status']:
            update_data['status'] = update_data['status'].value

        update_data["updated_at"] = datetime.utcnow().isoformat()
        update_data["updated_by"] = str(updated_by) if updated_by else None

        # Update document
        doc_ref.update(update_data)

        logger.info(
            "Study updated",
            extra={
                "study_id": str(study_id),
                "updated_fields": list(update_data.keys())
            }
        )

        # Get updated document
        updated_doc = doc_ref.get()
        doc_data = updated_doc.to_dict()
        doc_data["id"] = updated_doc.id

        return self._doc_to_response(doc_data)

    async def delete_study(
        self,
        study_id: UUID,
        deleted_by: Optional[UUID] = None,
        hard_delete: bool = False
    ) -> bool:
        """Delete or cancel a study."""
        doc_ref = self.db.collection(Collections.STUDIES).document(str(study_id))
        doc = doc_ref.get()

        if not doc.exists:
            raise NotFoundException(
                message="Study not found",
                error_code="STUDY_NOT_FOUND",
                details={"study_id": str(study_id)}
            )

        doc_data = doc.to_dict()

        if hard_delete:
            # Delete from GCS if storage service available
            if self.storage and doc_data.get("gcs_prefix"):
                await self.storage.delete_prefix(doc_data["gcs_prefix"])

            # Delete all series and instances (subcollections)
            series_stream = doc_ref.collection("series").stream()
            for series_doc in series_stream:
                # Delete instances in series
                instances = series_doc.reference.collection("instances").stream()
                for inst in instances:
                    inst.reference.delete()
                series_doc.reference.delete()

            # Delete the study document
            doc_ref.delete()
        else:
            # Soft delete - mark as cancelled
            doc_ref.update({
                "status": StudyStatus.CANCELLED.value,
                "updated_at": datetime.utcnow().isoformat(),
                "updated_by": str(deleted_by) if deleted_by else None
            })

        logger.info(
            "Study deleted",
            extra={
                "study_id": str(study_id),
                "hard_delete": hard_delete
            }
        )

        return True

    async def search_studies(
        self,
        search: StudySearch
    ) -> Tuple[List[StudySummary], int]:
        """Search studies with filters and pagination."""
        query = self.db.collection(Collections.STUDIES)

        # Build filters
        if search.patient_id:
            query = query.where(filter=FieldFilter("patient_id", "==", str(search.patient_id)))

        if search.modality:
            query = query.where(filter=FieldFilter("modality", "==", search.modality.value))

        if search.status:
            query = query.where(filter=FieldFilter("status", "==", search.status.value))

        if search.accession_number:
            query = query.where(filter=FieldFilter("accession_number", "==", search.accession_number))

        # Get total count
        count_result = query.count().get()
        total = count_result[0][0].value if count_result else 0

        # Apply ordering
        if search.sort_by == "study_date":
            direction = "DESCENDING" if search.sort_order == "desc" else "ASCENDING"
            query = query.order_by("study_date", direction=direction)
        else:
            query = query.order_by("created_at", direction="DESCENDING")

        # Apply pagination
        offset = (search.page - 1) * search.page_size
        if offset > 0:
            query = query.limit(search.page_size + offset)
            docs = list(query.stream())
            docs = docs[offset:offset + search.page_size]
        else:
            query = query.limit(search.page_size)
            docs = list(query.stream())

        results = []
        for doc in docs:
            doc_data = doc.to_dict()
            doc_data["id"] = doc.id

            # Calculate stats for this study
            series_count = 0
            instance_count = 0
            total_size = 0

            series_stream = doc.reference.collection("series").stream()
            for series_doc in series_stream:
                series_count += 1
                instances = series_doc.reference.collection("instances").stream()
                for inst in instances:
                    instance_count += 1
                    inst_data = inst.to_dict()
                    total_size += inst_data.get("file_size_bytes", 0)

            results.append(self._doc_to_summary(
                doc_data,
                series_count=series_count,
                instance_count=instance_count,
                total_size_bytes=total_size
            ))

        return results, total

    async def list_patient_studies(
        self,
        patient_id: UUID,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[StudySummary], int]:
        """List all studies for a patient."""
        query = self.db.collection(Collections.STUDIES).where(
            filter=FieldFilter("patient_id", "==", str(patient_id))
        )

        # Get total count
        count_result = query.count().get()
        total = count_result[0][0].value if count_result else 0

        # Apply ordering and pagination
        query = query.order_by("study_date", direction="DESCENDING")

        offset = (page - 1) * page_size
        if offset > 0:
            query = query.limit(page_size + offset)
            docs = list(query.stream())
            docs = docs[offset:offset + page_size]
        else:
            query = query.limit(page_size)
            docs = list(query.stream())

        results = []
        for doc in docs:
            doc_data = doc.to_dict()
            doc_data["id"] = doc.id

            # Calculate stats for this study
            series_count = 0
            instance_count = 0
            total_size = 0

            series_stream = doc.reference.collection("series").stream()
            for series_doc in series_stream:
                series_count += 1
                instances = series_doc.reference.collection("instances").stream()
                for inst in instances:
                    instance_count += 1
                    inst_data = inst.to_dict()
                    total_size += inst_data.get("file_size_bytes", 0)

            results.append(self._doc_to_summary(
                doc_data,
                series_count=series_count,
                instance_count=instance_count,
                total_size_bytes=total_size
            ))

        return results, total

    # =========================================================================
    # Series Operations
    # =========================================================================

    async def create_series(
        self,
        data: SeriesCreate
    ) -> SeriesResponse:
        """Create a new series within a study."""
        # Get study
        study_doc = self.db.collection(Collections.STUDIES).document(str(data.study_id)).get()

        if not study_doc.exists:
            raise NotFoundException(
                message="Study not found",
                error_code="STUDY_NOT_FOUND",
                details={"study_id": str(data.study_id)}
            )

        study_data = study_doc.to_dict()

        # Check if series number already exists
        existing = self.db.collection(Collections.STUDIES).document(str(data.study_id)).collection("series").where(
            filter=FieldFilter("series_number", "==", data.series_number)
        ).limit(1).get()

        if list(existing):
            raise ConflictException(
                message=f"Series number {data.series_number} already exists in study",
                error_code="SERIES_NUMBER_EXISTS",
                details={"series_number": data.series_number}
            )

        series_id = str(uuid.uuid4())
        series_uid = self._generate_uid()
        gcs_path = self._build_series_path(study_data.get("gcs_prefix", ""), UUID(series_id))
        now = datetime.utcnow()

        series_data = {
            "id": series_id,
            "study_id": str(data.study_id),
            "series_instance_uid": series_uid,
            "series_number": data.series_number,
            "modality": data.modality.value,
            "series_description": data.series_description,
            "body_part_examined": data.body_part_examined,
            "status": SeriesStatus.UPLOADING.value,
            "gcs_path": gcs_path,
            "created_at": now.isoformat()
        }

        # Create series in subcollection
        self.db.collection(Collections.STUDIES).document(str(data.study_id)).collection("series").document(series_id).set(series_data)

        logger.info(
            "Series created",
            extra={
                "series_id": series_id,
                "study_id": str(data.study_id),
                "series_number": data.series_number
            }
        )

        return self._series_to_response(series_data, instance_count=0, total_size=0)

    async def get_series(
        self,
        series_id: UUID
    ) -> SeriesResponse:
        """Get a series by ID."""
        # Need to search across all studies for this series
        studies = self.db.collection(Collections.STUDIES).stream()

        for study_doc in studies:
            series_doc = study_doc.reference.collection("series").document(str(series_id)).get()
            if series_doc.exists:
                doc_data = series_doc.to_dict()
                doc_data["id"] = series_doc.id

                # Get instance stats
                instances = series_doc.reference.collection("instances").stream()
                instance_count = 0
                total_size = 0
                for inst in instances:
                    instance_count += 1
                    inst_data = inst.to_dict()
                    total_size += inst_data.get("file_size_bytes", 0)

                return self._series_to_response(doc_data, instance_count, total_size)

        raise NotFoundException(
            message="Series not found",
            error_code="SERIES_NOT_FOUND",
            details={"series_id": str(series_id)}
        )

    async def list_study_series(
        self,
        study_id: UUID
    ) -> List[SeriesResponse]:
        """List all series in a study."""
        series_docs = self.db.collection(Collections.STUDIES).document(str(study_id)).collection("series").order_by("series_number").stream()

        results = []
        for doc in series_docs:
            doc_data = doc.to_dict()
            doc_data["id"] = doc.id
            results.append(self._series_to_response(doc_data))

        return results

    async def delete_series(
        self,
        series_id: UUID
    ) -> bool:
        """Delete a series and all its instances from GCS."""
        # Find the series
        studies = self.db.collection(Collections.STUDIES).stream()

        for study_doc in studies:
            series_ref = study_doc.reference.collection("series").document(str(series_id))
            series_doc = series_ref.get()

            if series_doc.exists:
                doc_data = series_doc.to_dict()

                # Delete from GCS if available
                if self.storage and doc_data.get("gcs_path"):
                    await self.storage.delete_prefix(doc_data["gcs_path"])

                # Delete instances
                instances = series_ref.collection("instances").stream()
                for inst in instances:
                    inst.reference.delete()

                # Delete series
                series_ref.delete()

                logger.info("Series deleted", extra={"series_id": str(series_id)})
                return True

        raise NotFoundException(
            message="Series not found",
            error_code="SERIES_NOT_FOUND",
            details={"series_id": str(series_id)}
        )

    # =========================================================================
    # Instance Operations
    # =========================================================================

    async def register_instance(
        self,
        data: InstanceCreate
    ) -> InstanceResponse:
        """Register a new instance in the database."""
        # Find series
        studies = self.db.collection(Collections.STUDIES).stream()

        for study_doc in studies:
            series_ref = study_doc.reference.collection("series").document(str(data.series_id))
            series_doc = series_ref.get()

            if series_doc.exists:
                series_data = series_doc.to_dict()
                instance_id = str(uuid.uuid4())
                gcs_object_name = self._build_instance_path(
                    series_data.get("gcs_path", ""), UUID(instance_id), data.original_filename
                )
                now = datetime.utcnow()

                instance_data = {
                    "id": instance_id,
                    "series_id": str(data.series_id),
                    "sop_instance_uid": data.sop_instance_uid,
                    "sop_class_uid": data.sop_class_uid,
                    "instance_number": data.instance_number,
                    "gcs_object_name": gcs_object_name,
                    "original_filename": data.original_filename,
                    "file_size_bytes": data.file_size_bytes,
                    "content_type": data.content_type,
                    "checksum_sha256": data.checksum_sha256,
                    "created_at": now.isoformat()
                }

                # Create instance in subcollection
                series_ref.collection("instances").document(instance_id).set(instance_data)

                return self._instance_to_response(instance_data)

        raise NotFoundException(
            message="Series not found",
            error_code="SERIES_NOT_FOUND",
            details={"series_id": str(data.series_id)}
        )

    async def get_instance(
        self,
        instance_id: UUID
    ) -> InstanceResponse:
        """Get an instance by ID."""
        # Search across all studies and series
        studies = self.db.collection(Collections.STUDIES).stream()

        for study_doc in studies:
            series_stream = study_doc.reference.collection("series").stream()
            for series_doc in series_stream:
                instance_doc = series_doc.reference.collection("instances").document(str(instance_id)).get()
                if instance_doc.exists:
                    doc_data = instance_doc.to_dict()
                    doc_data["id"] = instance_doc.id
                    return self._instance_to_response(doc_data)

        raise NotFoundException(
            message="Instance not found",
            error_code="INSTANCE_NOT_FOUND",
            details={"instance_id": str(instance_id)}
        )

    async def list_series_instances(
        self,
        series_id: UUID
    ) -> List[InstanceResponse]:
        """List all instances in a series."""
        # Find series
        studies = self.db.collection(Collections.STUDIES).stream()

        for study_doc in studies:
            series_ref = study_doc.reference.collection("series").document(str(series_id))
            series_doc = series_ref.get()

            if series_doc.exists:
                instances = series_ref.collection("instances").order_by("instance_number").stream()
                results = []
                for inst in instances:
                    doc_data = inst.to_dict()
                    doc_data["id"] = inst.id
                    results.append(self._instance_to_response(doc_data))
                return results

        return []

    async def delete_instance(
        self,
        instance_id: UUID
    ) -> bool:
        """Delete an instance from database and GCS."""
        # Search for instance
        studies = self.db.collection(Collections.STUDIES).stream()

        for study_doc in studies:
            series_stream = study_doc.reference.collection("series").stream()
            for series_doc in series_stream:
                instance_ref = series_doc.reference.collection("instances").document(str(instance_id))
                instance_doc = instance_ref.get()

                if instance_doc.exists:
                    doc_data = instance_doc.to_dict()

                    # Delete from GCS
                    if self.storage and doc_data.get("gcs_object_name"):
                        await self.storage.delete_file(doc_data["gcs_object_name"])

                    # Delete from DB
                    instance_ref.delete()

                    logger.info("Instance deleted", extra={"instance_id": str(instance_id)})
                    return True

        raise NotFoundException(
            message="Instance not found",
            error_code="INSTANCE_NOT_FOUND",
            details={"instance_id": str(instance_id)}
        )

    # =========================================================================
    # Upload Operations
    # =========================================================================

    async def init_upload(
        self,
        request: UploadInitRequest,
        user_id: Optional[UUID] = None
    ) -> UploadInitResponse:
        """Initialize a file upload to GCS."""
        # Get study
        study_doc = self.db.collection(Collections.STUDIES).document(str(request.study_id)).get()

        if not study_doc.exists:
            raise NotFoundException(
                message="Study not found",
                error_code="STUDY_NOT_FOUND",
                details={"study_id": str(request.study_id)}
            )

        study_data = study_doc.to_dict()

        # Find or create series
        series_query = self.db.collection(Collections.STUDIES).document(str(request.study_id)).collection("series").where(
            filter=FieldFilter("series_number", "==", request.series_number)
        ).limit(1).get()

        series_list = list(series_query)

        if not series_list:
            # Create new series
            series_data = SeriesCreate(
                study_id=request.study_id,
                series_number=request.series_number,
                modality=Modality(study_data["modality"])
            )
            series_response = await self.create_series(series_data)
            series_id = series_response.id
            gcs_path = series_response.gcs_path
        else:
            series_doc = series_list[0]
            series_data = series_doc.to_dict()
            series_id = UUID(series_data["id"])
            gcs_path = series_data.get("gcs_path", "")

        # Generate instance ID and GCS path
        instance_id = uuid.uuid4()
        gcs_object_name = self._build_instance_path(gcs_path, instance_id, request.filename)

        # Generate signed URL for upload (if storage service available)
        signed_url = ""
        if self.storage:
            url_response = await self.storage.generate_signed_upload_url(
                object_name=gcs_object_name,
                content_type=request.content_type,
                expiration_minutes=getattr(settings, 'GCS_SIGNED_URL_EXPIRATION_MINUTES', 60)
            )
            signed_url = url_response.url

        # Create upload session in Firestore (for Cloud Run multi-instance compatibility)
        upload_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(minutes=getattr(settings, 'GCS_SIGNED_URL_EXPIRATION_MINUTES', 60))

        session_data = {
            "upload_id": upload_id,
            "study_id": str(request.study_id),
            "series_id": str(series_id),
            "instance_id": str(instance_id),
            "gcs_object_name": gcs_object_name,
            "filename": request.filename,
            "content_type": request.content_type,
            "file_size_bytes": request.file_size_bytes,
            "expected_checksum": request.checksum_sha256,
            "user_id": str(user_id) if user_id else None,
            "expires_at": expires_at.isoformat(),
            "created_at": datetime.utcnow().isoformat()
        }

        # Store session in Firestore
        self.db.collection(Collections.UPLOAD_SESSIONS).document(upload_id).set(session_data)

        logger.info(
            "Upload initialized",
            extra={
                "upload_id": upload_id,
                "study_id": str(request.study_id),
                "file_name": request.filename
            }
        )

        # Headers for upload (Content-Type is required for GCS signed URLs)
        upload_headers = {"Content-Type": request.content_type}

        return UploadInitResponse(
            upload_id=upload_id,
            signed_url=signed_url,
            expires_at=expires_at,
            gcs_object_name=gcs_object_name,
            series_id=series_id,
            headers=upload_headers
        )

    async def complete_upload(
        self,
        request: UploadCompleteRequest,
        user_id: Optional[UUID] = None
    ) -> UploadCompleteResponse:
        """Complete an upload and register the instance."""
        # Get upload session from Firestore
        session_doc = self.db.collection(Collections.UPLOAD_SESSIONS).document(request.upload_id).get()
        if not session_doc.exists:
            raise ValidationException(
                message="Upload session not found or expired",
                error_code="UPLOAD_SESSION_NOT_FOUND"
            )

        session = session_doc.to_dict()

        # Check expiration
        expires_at = session["expires_at"]
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)

        if datetime.utcnow() > expires_at:
            # Delete expired session
            self.db.collection(Collections.UPLOAD_SESSIONS).document(request.upload_id).delete()
            raise ValidationException(
                message="Upload session expired",
                error_code="UPLOAD_SESSION_EXPIRED"
            )

        # Verify file exists in GCS (if storage available)
        if self.storage:
            exists = await self.storage.file_exists(session["gcs_object_name"])
            if not exists:
                raise ValidationException(
                    message="File not found in storage",
                    error_code="FILE_NOT_UPLOADED"
                )

        # Verify checksum
        if session["expected_checksum"] and session["expected_checksum"] != request.checksum_sha256:
            raise ValidationException(
                message="Checksum mismatch",
                error_code="CHECKSUM_MISMATCH",
                details={
                    "expected": session["expected_checksum"],
                    "received": request.checksum_sha256
                }
            )

        # Generate DICOM UID for instance
        sop_instance_uid = self._generate_uid()

        # Parse UUIDs from session (stored as strings in Firestore)
        series_id = UUID(session["series_id"])
        study_id = UUID(session["study_id"])
        instance_id = UUID(session["instance_id"])  # Use the instance_id from init_upload
        gcs_object_name = session["gcs_object_name"]  # Use the GCS path from init_upload
        now = datetime.utcnow()

        # Create instance record directly with the correct GCS path from init_upload
        instance_data = {
            "id": str(instance_id),
            "series_id": str(series_id),
            "sop_instance_uid": sop_instance_uid,
            "sop_class_uid": None,
            "instance_number": None,
            "gcs_object_name": gcs_object_name,  # Use path from session, not regenerated
            "original_filename": session["filename"],
            "file_size_bytes": session["file_size_bytes"],
            "content_type": session["content_type"],
            "checksum_sha256": request.checksum_sha256,
            "created_at": now.isoformat()
        }

        # Find series and create instance
        study_doc_ref = self.db.collection(Collections.STUDIES).document(str(study_id))
        series_ref = study_doc_ref.collection("series").document(str(series_id))
        series_ref.collection("instances").document(str(instance_id)).set(instance_data)

        instance = self._instance_to_response(instance_data)

        # Update series status to available
        series_ref.update({"status": SeriesStatus.AVAILABLE.value})

        # Update study status to available
        self.db.collection(Collections.STUDIES).document(str(study_id)).update({
            "status": StudyStatus.AVAILABLE.value
        })

        # Clean up session from Firestore
        self.db.collection(Collections.UPLOAD_SESSIONS).document(request.upload_id).delete()

        logger.info(
            "Upload completed",
            extra={
                "upload_id": request.upload_id,
                "instance_id": str(instance.id),
                "study_id": str(study_id)
            }
        )

        return UploadCompleteResponse(
            instance_id=instance.id,
            series_id=series_id,
            study_id=study_id,
            gcs_object_name=session["gcs_object_name"],
            file_size_bytes=session["file_size_bytes"]
        )

    async def get_download_url(
        self,
        instance_id: UUID,
        expiration_minutes: int = 60
    ) -> str:
        """Get a signed download URL for an instance."""
        instance = await self.get_instance(instance_id)

        if not self.storage:
            return ""

        signed_url = await self.storage.generate_signed_download_url(
            object_name=instance.gcs_object_name,
            expiration_minutes=expiration_minutes,
            filename=instance.original_filename
        )

        return signed_url.url

    async def get_study_download_urls(
        self,
        study_id: UUID,
        expiration_minutes: int = 60
    ) -> List[dict]:
        """Get download URLs for all instances in a study."""
        urls = []

        # Get all series in study
        series_docs = self.db.collection(Collections.STUDIES).document(str(study_id)).collection("series").stream()

        for series_doc in series_docs:
            instances = series_doc.reference.collection("instances").order_by("instance_number").stream()

            for inst in instances:
                inst_data = inst.to_dict()

                if self.storage and inst_data.get("gcs_object_name"):
                    signed_url = await self.storage.generate_signed_download_url(
                        object_name=inst_data["gcs_object_name"],
                        expiration_minutes=expiration_minutes,
                        filename=inst_data.get("original_filename", "unknown")
                    )
                    urls.append({
                        "instance_id": inst.id,
                        "url": signed_url.url,
                        "filename": inst_data.get("original_filename"),
                        "expires_at": signed_url.expires_at.isoformat()
                    })

        return urls

    # =========================================================================
    # DICOM Metadata
    # =========================================================================

    async def extract_dicom_metadata(
        self,
        file_data: bytes,
        filename: str
    ) -> dict:
        """Extract metadata from a DICOM file."""
        try:
            import pydicom
            from io import BytesIO

            ds = pydicom.dcmread(BytesIO(file_data))

            metadata = {
                "patient_name": str(ds.PatientName) if hasattr(ds, 'PatientName') else None,
                "patient_id": str(ds.PatientID) if hasattr(ds, 'PatientID') else None,
                "study_date": str(ds.StudyDate) if hasattr(ds, 'StudyDate') else None,
                "modality": str(ds.Modality) if hasattr(ds, 'Modality') else None,
                "rows": int(ds.Rows) if hasattr(ds, 'Rows') else None,
                "columns": int(ds.Columns) if hasattr(ds, 'Columns') else None,
                "bits_allocated": int(ds.BitsAllocated) if hasattr(ds, 'BitsAllocated') else None,
                "pixel_spacing": str(ds.PixelSpacing) if hasattr(ds, 'PixelSpacing') else None,
                "slice_thickness": float(ds.SliceThickness) if hasattr(ds, 'SliceThickness') else None,
                "slice_location": float(ds.SliceLocation) if hasattr(ds, 'SliceLocation') else None,
                "window_center": float(ds.WindowCenter) if hasattr(ds, 'WindowCenter') else None,
                "window_width": float(ds.WindowWidth) if hasattr(ds, 'WindowWidth') else None,
            }

            return metadata
        except Exception as e:
            logger.warning(f"Failed to extract DICOM metadata: {e}")
            return {}

    async def update_instance_metadata(
        self,
        instance_id: UUID,
        metadata: dict
    ) -> InstanceResponse:
        """Update instance with extracted DICOM metadata."""
        # Search for instance
        studies = self.db.collection(Collections.STUDIES).stream()

        for study_doc in studies:
            series_stream = study_doc.reference.collection("series").stream()
            for series_doc in series_stream:
                instance_ref = series_doc.reference.collection("instances").document(str(instance_id))
                instance_doc = instance_ref.get()

                if instance_doc.exists:
                    update_data = {}

                    if metadata.get('rows'):
                        update_data['rows'] = metadata['rows']
                    if metadata.get('columns'):
                        update_data['columns'] = metadata['columns']
                    if metadata.get('bits_allocated'):
                        update_data['bits_allocated'] = metadata['bits_allocated']
                    if metadata.get('pixel_spacing'):
                        update_data['pixel_spacing'] = metadata['pixel_spacing']
                    if metadata.get('slice_thickness'):
                        update_data['slice_thickness'] = metadata['slice_thickness']
                    if metadata.get('slice_location'):
                        update_data['slice_location'] = metadata['slice_location']
                    if metadata.get('window_center'):
                        update_data['window_center'] = metadata['window_center']
                    if metadata.get('window_width'):
                        update_data['window_width'] = metadata['window_width']

                    update_data['dicom_metadata'] = metadata

                    instance_ref.update(update_data)

                    # Get updated document
                    updated_doc = instance_ref.get()
                    doc_data = updated_doc.to_dict()
                    doc_data["id"] = updated_doc.id

                    return self._instance_to_response(doc_data)

        raise NotFoundException(
            message="Instance not found",
            error_code="INSTANCE_NOT_FOUND",
            details={"instance_id": str(instance_id)}
        )
