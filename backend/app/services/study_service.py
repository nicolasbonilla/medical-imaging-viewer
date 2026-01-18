"""
Study Service Implementation.

Manages imaging studies, series, and instances with GCS storage integration.

@module services.study_service
"""

import uuid
import hashlib
import logging
from typing import Optional, List, Tuple
from uuid import UUID
from datetime import datetime, timedelta

from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.interfaces.study_interface import IStudyService
from app.core.interfaces.storage_interface import IStorageService
from app.core.exceptions import NotFoundException, ValidationException, ConflictException
from app.core.config import get_settings
from app.models.database import (
    ImagingStudy, ImagingSeries, ImagingInstance, Patient,
    StudyStatus as DBStudyStatus, SeriesStatus as DBSeriesStatus, Modality as DBModality
)
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


class StudyService(IStudyService):
    """
    Imaging study service with GCS storage integration.
    """

    def __init__(self, db: AsyncSession, storage_service: IStorageService):
        """
        Initialize study service.

        Args:
            db: Async database session
            storage_service: GCS storage service
        """
        self.db = db
        self.storage = storage_service
        self._upload_sessions: dict = {}  # In-memory upload session tracking

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _generate_uid(self) -> str:
        """Generate a DICOM-compliant UID."""
        # Use OID root for organization + UUID
        # Format: 2.25.{uuid as integer}
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
        # Preserve file extension
        ext = filename.rsplit('.', 1)[-1] if '.' in filename else ''
        ext_suffix = f".{ext}" if ext else ''
        return f"{series_path}/{instance_id}{ext_suffix}"

    def _study_to_response(
        self,
        study: ImagingStudy,
        series_count: Optional[int] = None,
        instance_count: Optional[int] = None,
        total_size: Optional[int] = None
    ) -> StudyResponse:
        """Convert Study model to StudyResponse."""
        return StudyResponse(
            id=study.id,
            patient_id=study.patient_id,
            accession_number=study.accession_number,
            study_instance_uid=study.study_instance_uid,
            status=StudyStatus(study.status.value),
            modality=Modality(study.modality.value),
            study_date=study.study_date,
            study_description=study.study_description,
            body_site=study.body_site,
            laterality=study.laterality,
            reason_for_study=study.reason_for_study,
            referring_physician_name=study.referring_physician_name,
            referring_physician_id=study.referring_physician_id,
            performing_physician_name=study.performing_physician_name,
            institution_name=study.institution_name,
            gcs_bucket=study.gcs_bucket,
            gcs_prefix=study.gcs_prefix,
            clinical_notes=study.clinical_notes,
            created_at=study.created_at,
            updated_at=study.updated_at,
            series_count=series_count,
            instance_count=instance_count,
            total_size_bytes=total_size
        )

    def _study_to_summary(self, study: ImagingStudy) -> StudySummary:
        """Convert Study model to StudySummary."""
        return StudySummary(
            id=study.id,
            patient_id=study.patient_id,
            accession_number=study.accession_number,
            modality=Modality(study.modality.value),
            study_date=study.study_date,
            study_description=study.study_description,
            body_site=study.body_site,
            status=StudyStatus(study.status.value)
        )

    def _series_to_response(
        self,
        series: ImagingSeries,
        instance_count: Optional[int] = None,
        total_size: Optional[int] = None
    ) -> SeriesResponse:
        """Convert Series model to SeriesResponse."""
        return SeriesResponse(
            id=series.id,
            study_id=series.study_id,
            series_instance_uid=series.series_instance_uid,
            series_number=series.series_number,
            modality=Modality(series.modality.value),
            series_description=series.series_description,
            body_part_examined=series.body_part_examined,
            status=SeriesStatus(series.status.value),
            gcs_path=series.gcs_path,
            created_at=series.created_at,
            instance_count=instance_count,
            total_size_bytes=total_size
        )

    def _instance_to_response(self, instance: ImagingInstance) -> InstanceResponse:
        """Convert Instance model to InstanceResponse."""
        return InstanceResponse(
            id=instance.id,
            series_id=instance.series_id,
            sop_instance_uid=instance.sop_instance_uid,
            sop_class_uid=instance.sop_class_uid,
            instance_number=instance.instance_number,
            gcs_object_name=instance.gcs_object_name,
            original_filename=instance.original_filename,
            file_size_bytes=instance.file_size_bytes,
            content_type=instance.content_type,
            checksum_sha256=instance.checksum_sha256,
            rows=instance.rows,
            columns=instance.columns,
            bits_allocated=instance.bits_allocated,
            pixel_spacing=instance.pixel_spacing,
            slice_thickness=instance.slice_thickness,
            slice_location=instance.slice_location,
            window_center=instance.window_center,
            window_width=instance.window_width,
            dicom_metadata=instance.dicom_metadata,
            created_at=instance.created_at
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
        patient_result = await self.db.execute(
            select(Patient.id).where(Patient.id == data.patient_id)
        )
        if not patient_result.scalar_one_or_none():
            raise NotFoundException(
                message="Patient not found",
                error_code="PATIENT_NOT_FOUND",
                details={"patient_id": str(data.patient_id)}
            )

        # Generate UIDs and accession number
        study_uid = self._generate_uid()
        accession = self._generate_accession_number()
        study_id = uuid.uuid4()

        # Build GCS prefix
        gcs_prefix = self._build_gcs_prefix(data.patient_id, study_id)

        # Create study
        study = ImagingStudy(
            id=study_id,
            patient_id=data.patient_id,
            accession_number=accession,
            study_instance_uid=study_uid,
            status=DBStudyStatus.REGISTERED,
            modality=DBModality(data.modality.value),
            study_date=data.study_date,
            study_description=data.study_description,
            body_site=data.body_site,
            laterality=data.laterality,
            reason_for_study=data.reason_for_study,
            referring_physician_name=data.referring_physician_name,
            referring_physician_id=data.referring_physician_id,
            performing_physician_name=data.performing_physician_name,
            institution_name=data.institution_name,
            gcs_bucket=settings.GCS_BUCKET_NAME,
            gcs_prefix=gcs_prefix,
            created_by=created_by
        )

        self.db.add(study)
        await self.db.flush()
        await self.db.refresh(study)

        logger.info(
            "Study created",
            extra={
                "study_id": str(study.id),
                "accession": accession,
                "patient_id": str(data.patient_id),
                "modality": data.modality.value
            }
        )

        return self._study_to_response(study, series_count=0, instance_count=0, total_size=0)

    async def get_study(
        self,
        study_id: UUID,
        include_stats: bool = False
    ) -> StudyResponse:
        """Get a study by ID."""
        result = await self.db.execute(
            select(ImagingStudy).where(ImagingStudy.id == study_id)
        )
        study = result.scalar_one_or_none()

        if not study:
            raise NotFoundException(
                message="Study not found",
                error_code="STUDY_NOT_FOUND",
                details={"study_id": str(study_id)}
            )

        series_count = None
        instance_count = None
        total_size = None

        if include_stats:
            # Get series count
            series_result = await self.db.execute(
                select(func.count(ImagingSeries.id))
                .where(ImagingSeries.study_id == study_id)
            )
            series_count = series_result.scalar() or 0

            # Get instance count and total size
            instance_result = await self.db.execute(
                select(
                    func.count(ImagingInstance.id),
                    func.coalesce(func.sum(ImagingInstance.file_size_bytes), 0)
                )
                .join(ImagingSeries)
                .where(ImagingSeries.study_id == study_id)
            )
            row = instance_result.one()
            instance_count = row[0] or 0
            total_size = row[1] or 0

        return self._study_to_response(study, series_count, instance_count, total_size)

    async def get_study_by_accession(
        self,
        accession_number: str
    ) -> Optional[StudyResponse]:
        """Get a study by accession number."""
        result = await self.db.execute(
            select(ImagingStudy).where(ImagingStudy.accession_number == accession_number)
        )
        study = result.scalar_one_or_none()

        if not study:
            return None

        return self._study_to_response(study)

    async def update_study(
        self,
        study_id: UUID,
        data: StudyUpdate,
        updated_by: Optional[UUID] = None
    ) -> StudyResponse:
        """Update a study."""
        result = await self.db.execute(
            select(ImagingStudy).where(ImagingStudy.id == study_id)
        )
        study = result.scalar_one_or_none()

        if not study:
            raise NotFoundException(
                message="Study not found",
                error_code="STUDY_NOT_FOUND",
                details={"study_id": str(study_id)}
            )

        # Update fields
        update_data = data.model_dump(exclude_unset=True)

        # Handle status enum conversion
        if 'status' in update_data and update_data['status']:
            update_data['status'] = DBStudyStatus(update_data['status'].value)

        for field, value in update_data.items():
            setattr(study, field, value)

        study.updated_by = updated_by

        await self.db.flush()
        await self.db.refresh(study)

        logger.info(
            "Study updated",
            extra={
                "study_id": str(study_id),
                "updated_fields": list(update_data.keys())
            }
        )

        return self._study_to_response(study)

    async def delete_study(
        self,
        study_id: UUID,
        deleted_by: Optional[UUID] = None,
        hard_delete: bool = False
    ) -> bool:
        """Delete or cancel a study."""
        result = await self.db.execute(
            select(ImagingStudy).where(ImagingStudy.id == study_id)
        )
        study = result.scalar_one_or_none()

        if not study:
            raise NotFoundException(
                message="Study not found",
                error_code="STUDY_NOT_FOUND",
                details={"study_id": str(study_id)}
            )

        if hard_delete:
            # Delete from GCS
            if study.gcs_prefix:
                await self.storage.delete_prefix(study.gcs_prefix)

            # Delete all instances, series, then study
            await self.db.execute(
                ImagingInstance.__table__.delete().where(
                    ImagingInstance.series_id.in_(
                        select(ImagingSeries.id).where(ImagingSeries.study_id == study_id)
                    )
                )
            )
            await self.db.execute(
                ImagingSeries.__table__.delete().where(ImagingSeries.study_id == study_id)
            )
            await self.db.delete(study)
        else:
            # Soft delete - mark as cancelled
            study.status = DBStudyStatus.CANCELLED
            study.updated_by = deleted_by

        await self.db.flush()

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
        query = select(ImagingStudy)
        count_query = select(func.count(ImagingStudy.id))

        conditions = []

        if search.patient_id:
            conditions.append(ImagingStudy.patient_id == search.patient_id)

        if search.modality:
            conditions.append(ImagingStudy.modality == DBModality(search.modality.value))

        if search.status:
            conditions.append(ImagingStudy.status == DBStudyStatus(search.status.value))

        if search.study_date_from:
            conditions.append(ImagingStudy.study_date >= search.study_date_from)

        if search.study_date_to:
            conditions.append(ImagingStudy.study_date <= search.study_date_to)

        if search.body_site:
            conditions.append(ImagingStudy.body_site.ilike(f"%{search.body_site}%"))

        if search.referring_physician:
            conditions.append(
                ImagingStudy.referring_physician_name.ilike(f"%{search.referring_physician}%")
            )

        if search.accession_number:
            conditions.append(ImagingStudy.accession_number == search.accession_number)

        if search.query:
            search_term = f"%{search.query}%"
            conditions.append(
                or_(
                    ImagingStudy.accession_number.ilike(search_term),
                    ImagingStudy.study_description.ilike(search_term),
                    ImagingStudy.body_site.ilike(search_term)
                )
            )

        if conditions:
            query = query.where(and_(*conditions))
            count_query = count_query.where(and_(*conditions))

        # Get total
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply sorting
        sort_column = getattr(ImagingStudy, search.sort_by, ImagingStudy.study_date)
        if search.sort_order == "desc":
            sort_column = sort_column.desc()
        query = query.order_by(sort_column)

        # Apply pagination
        offset = (search.page - 1) * search.page_size
        query = query.offset(offset).limit(search.page_size)

        result = await self.db.execute(query)
        studies = result.scalars().all()

        return [self._study_to_summary(s) for s in studies], total

    async def list_patient_studies(
        self,
        patient_id: UUID,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[StudySummary], int]:
        """List all studies for a patient."""
        query = select(ImagingStudy).where(ImagingStudy.patient_id == patient_id)
        count_query = select(func.count(ImagingStudy.id)).where(
            ImagingStudy.patient_id == patient_id
        )

        # Get total
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.order_by(ImagingStudy.study_date.desc())
        query = query.offset(offset).limit(page_size)

        result = await self.db.execute(query)
        studies = result.scalars().all()

        return [self._study_to_summary(s) for s in studies], total

    # =========================================================================
    # Series Operations
    # =========================================================================

    async def create_series(
        self,
        data: SeriesCreate
    ) -> SeriesResponse:
        """Create a new series within a study."""
        # Get study
        study_result = await self.db.execute(
            select(ImagingStudy).where(ImagingStudy.id == data.study_id)
        )
        study = study_result.scalar_one_or_none()

        if not study:
            raise NotFoundException(
                message="Study not found",
                error_code="STUDY_NOT_FOUND",
                details={"study_id": str(data.study_id)}
            )

        # Check if series number already exists
        existing = await self.db.execute(
            select(ImagingSeries).where(
                ImagingSeries.study_id == data.study_id,
                ImagingSeries.series_number == data.series_number
            )
        )
        if existing.scalar_one_or_none():
            raise ConflictException(
                message=f"Series number {data.series_number} already exists in study",
                error_code="SERIES_NUMBER_EXISTS",
                details={"series_number": data.series_number}
            )

        series_id = uuid.uuid4()
        series_uid = self._generate_uid()
        gcs_path = self._build_series_path(study.gcs_prefix, series_id)

        series = ImagingSeries(
            id=series_id,
            study_id=data.study_id,
            series_instance_uid=series_uid,
            series_number=data.series_number,
            modality=DBModality(data.modality.value),
            series_description=data.series_description,
            body_part_examined=data.body_part_examined,
            status=DBSeriesStatus.UPLOADING,
            gcs_path=gcs_path
        )

        self.db.add(series)
        await self.db.flush()
        await self.db.refresh(series)

        logger.info(
            "Series created",
            extra={
                "series_id": str(series.id),
                "study_id": str(data.study_id),
                "series_number": data.series_number
            }
        )

        return self._series_to_response(series, instance_count=0, total_size=0)

    async def get_series(
        self,
        series_id: UUID
    ) -> SeriesResponse:
        """Get a series by ID."""
        result = await self.db.execute(
            select(ImagingSeries).where(ImagingSeries.id == series_id)
        )
        series = result.scalar_one_or_none()

        if not series:
            raise NotFoundException(
                message="Series not found",
                error_code="SERIES_NOT_FOUND",
                details={"series_id": str(series_id)}
            )

        # Get instance stats
        instance_result = await self.db.execute(
            select(
                func.count(ImagingInstance.id),
                func.coalesce(func.sum(ImagingInstance.file_size_bytes), 0)
            ).where(ImagingInstance.series_id == series_id)
        )
        row = instance_result.one()

        return self._series_to_response(series, instance_count=row[0], total_size=row[1])

    async def list_study_series(
        self,
        study_id: UUID
    ) -> List[SeriesResponse]:
        """List all series in a study."""
        result = await self.db.execute(
            select(ImagingSeries)
            .where(ImagingSeries.study_id == study_id)
            .order_by(ImagingSeries.series_number)
        )
        series_list = result.scalars().all()

        return [self._series_to_response(s) for s in series_list]

    async def delete_series(
        self,
        series_id: UUID
    ) -> bool:
        """Delete a series and all its instances from GCS."""
        result = await self.db.execute(
            select(ImagingSeries).where(ImagingSeries.id == series_id)
        )
        series = result.scalar_one_or_none()

        if not series:
            raise NotFoundException(
                message="Series not found",
                error_code="SERIES_NOT_FOUND",
                details={"series_id": str(series_id)}
            )

        # Delete from GCS
        if series.gcs_path:
            await self.storage.delete_prefix(series.gcs_path)

        # Delete instances then series
        await self.db.execute(
            ImagingInstance.__table__.delete().where(ImagingInstance.series_id == series_id)
        )
        await self.db.delete(series)
        await self.db.flush()

        logger.info("Series deleted", extra={"series_id": str(series_id)})

        return True

    # =========================================================================
    # Instance Operations
    # =========================================================================

    async def register_instance(
        self,
        data: InstanceCreate
    ) -> InstanceResponse:
        """Register a new instance in the database."""
        # Verify series exists
        series_result = await self.db.execute(
            select(ImagingSeries).where(ImagingSeries.id == data.series_id)
        )
        series = series_result.scalar_one_or_none()

        if not series:
            raise NotFoundException(
                message="Series not found",
                error_code="SERIES_NOT_FOUND",
                details={"series_id": str(data.series_id)}
            )

        instance_id = uuid.uuid4()
        gcs_object_name = self._build_instance_path(
            series.gcs_path, instance_id, data.original_filename
        )

        instance = ImagingInstance(
            id=instance_id,
            series_id=data.series_id,
            sop_instance_uid=data.sop_instance_uid,
            sop_class_uid=data.sop_class_uid,
            instance_number=data.instance_number,
            gcs_object_name=gcs_object_name,
            original_filename=data.original_filename,
            file_size_bytes=data.file_size_bytes,
            content_type=data.content_type,
            checksum_sha256=data.checksum_sha256
        )

        self.db.add(instance)
        await self.db.flush()
        await self.db.refresh(instance)

        return self._instance_to_response(instance)

    async def get_instance(
        self,
        instance_id: UUID
    ) -> InstanceResponse:
        """Get an instance by ID."""
        result = await self.db.execute(
            select(ImagingInstance).where(ImagingInstance.id == instance_id)
        )
        instance = result.scalar_one_or_none()

        if not instance:
            raise NotFoundException(
                message="Instance not found",
                error_code="INSTANCE_NOT_FOUND",
                details={"instance_id": str(instance_id)}
            )

        return self._instance_to_response(instance)

    async def list_series_instances(
        self,
        series_id: UUID
    ) -> List[InstanceResponse]:
        """List all instances in a series."""
        result = await self.db.execute(
            select(ImagingInstance)
            .where(ImagingInstance.series_id == series_id)
            .order_by(ImagingInstance.instance_number)
        )
        instances = result.scalars().all()

        return [self._instance_to_response(i) for i in instances]

    async def delete_instance(
        self,
        instance_id: UUID
    ) -> bool:
        """Delete an instance from database and GCS."""
        result = await self.db.execute(
            select(ImagingInstance).where(ImagingInstance.id == instance_id)
        )
        instance = result.scalar_one_or_none()

        if not instance:
            raise NotFoundException(
                message="Instance not found",
                error_code="INSTANCE_NOT_FOUND",
                details={"instance_id": str(instance_id)}
            )

        # Delete from GCS
        await self.storage.delete_file(instance.gcs_object_name)

        # Delete from DB
        await self.db.delete(instance)
        await self.db.flush()

        logger.info("Instance deleted", extra={"instance_id": str(instance_id)})

        return True

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
        study_result = await self.db.execute(
            select(ImagingStudy).where(ImagingStudy.id == request.study_id)
        )
        study = study_result.scalar_one_or_none()

        if not study:
            raise NotFoundException(
                message="Study not found",
                error_code="STUDY_NOT_FOUND",
                details={"study_id": str(request.study_id)}
            )

        # Find or create series
        series_result = await self.db.execute(
            select(ImagingSeries).where(
                ImagingSeries.study_id == request.study_id,
                ImagingSeries.series_number == request.series_number
            )
        )
        series = series_result.scalar_one_or_none()

        if not series:
            # Create new series
            series_data = SeriesCreate(
                study_id=request.study_id,
                series_number=request.series_number,
                modality=Modality(study.modality.value)
            )
            series_response = await self.create_series(series_data)
            series_id = series_response.id
            gcs_path = series_response.gcs_path
        else:
            series_id = series.id
            gcs_path = series.gcs_path

        # Generate instance ID and GCS path
        instance_id = uuid.uuid4()
        gcs_object_name = self._build_instance_path(gcs_path, instance_id, request.filename)

        # Generate signed URL for upload
        signed_url = await self.storage.generate_signed_upload_url(
            object_name=gcs_object_name,
            content_type=request.content_type,
            expiration_minutes=settings.GCS_SIGNED_URL_EXPIRATION_MINUTES
        )

        # Create upload session
        upload_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(minutes=settings.GCS_SIGNED_URL_EXPIRATION_MINUTES)

        self._upload_sessions[upload_id] = {
            "study_id": request.study_id,
            "series_id": series_id,
            "instance_id": instance_id,
            "gcs_object_name": gcs_object_name,
            "filename": request.filename,
            "content_type": request.content_type,
            "file_size_bytes": request.file_size_bytes,
            "expected_checksum": request.checksum_sha256,
            "user_id": user_id,
            "expires_at": expires_at
        }

        logger.info(
            "Upload initialized",
            extra={
                "upload_id": upload_id,
                "study_id": str(request.study_id),
                "filename": request.filename
            }
        )

        return UploadInitResponse(
            upload_id=upload_id,
            signed_url=signed_url.url,
            expires_at=expires_at,
            gcs_object_name=gcs_object_name
        )

    async def complete_upload(
        self,
        request: UploadCompleteRequest,
        user_id: Optional[UUID] = None
    ) -> UploadCompleteResponse:
        """Complete an upload and register the instance."""
        # Get upload session
        session = self._upload_sessions.get(request.upload_id)
        if not session:
            raise ValidationException(
                message="Upload session not found or expired",
                error_code="UPLOAD_SESSION_NOT_FOUND"
            )

        # Check expiration
        if datetime.utcnow() > session["expires_at"]:
            del self._upload_sessions[request.upload_id]
            raise ValidationException(
                message="Upload session expired",
                error_code="UPLOAD_SESSION_EXPIRED"
            )

        # Verify file exists in GCS
        exists = await self.storage.file_exists(session["gcs_object_name"])
        if not exists:
            raise ValidationException(
                message="File not found in storage",
                error_code="FILE_NOT_UPLOADED"
            )

        # Verify checksum if provided during init
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

        # Create instance record
        instance_data = InstanceCreate(
            series_id=session["series_id"],
            sop_instance_uid=sop_instance_uid,
            original_filename=session["filename"],
            file_size_bytes=session["file_size_bytes"],
            content_type=session["content_type"],
            checksum_sha256=request.checksum_sha256
        )

        instance = await self.register_instance(instance_data)

        # Update instance with correct GCS object name
        await self.db.execute(
            ImagingInstance.__table__.update()
            .where(ImagingInstance.id == instance.id)
            .values(gcs_object_name=session["gcs_object_name"])
        )

        # Update series status to available
        await self.db.execute(
            ImagingSeries.__table__.update()
            .where(ImagingSeries.id == session["series_id"])
            .values(status=DBSeriesStatus.AVAILABLE)
        )

        # Update study status to available
        await self.db.execute(
            ImagingStudy.__table__.update()
            .where(ImagingStudy.id == session["study_id"])
            .values(status=DBStudyStatus.AVAILABLE)
        )

        await self.db.flush()

        # Clean up session
        del self._upload_sessions[request.upload_id]

        logger.info(
            "Upload completed",
            extra={
                "upload_id": request.upload_id,
                "instance_id": str(instance.id),
                "study_id": str(session["study_id"])
            }
        )

        return UploadCompleteResponse(
            instance_id=instance.id,
            series_id=session["series_id"],
            study_id=session["study_id"],
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
        # Get all instances in study
        result = await self.db.execute(
            select(ImagingInstance)
            .join(ImagingSeries)
            .where(ImagingSeries.study_id == study_id)
            .order_by(ImagingSeries.series_number, ImagingInstance.instance_number)
        )
        instances = result.scalars().all()

        urls = []
        for instance in instances:
            signed_url = await self.storage.generate_signed_download_url(
                object_name=instance.gcs_object_name,
                expiration_minutes=expiration_minutes,
                filename=instance.original_filename
            )
            urls.append({
                "instance_id": str(instance.id),
                "url": signed_url.url,
                "filename": instance.original_filename,
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
        # This would integrate with pydicom
        # For now, return empty dict - to be implemented
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
        result = await self.db.execute(
            select(ImagingInstance).where(ImagingInstance.id == instance_id)
        )
        instance = result.scalar_one_or_none()

        if not instance:
            raise NotFoundException(
                message="Instance not found",
                error_code="INSTANCE_NOT_FOUND",
                details={"instance_id": str(instance_id)}
            )

        # Update metadata fields
        if metadata.get('rows'):
            instance.rows = metadata['rows']
        if metadata.get('columns'):
            instance.columns = metadata['columns']
        if metadata.get('bits_allocated'):
            instance.bits_allocated = metadata['bits_allocated']
        if metadata.get('pixel_spacing'):
            instance.pixel_spacing = metadata['pixel_spacing']
        if metadata.get('slice_thickness'):
            instance.slice_thickness = metadata['slice_thickness']
        if metadata.get('slice_location'):
            instance.slice_location = metadata['slice_location']
        if metadata.get('window_center'):
            instance.window_center = metadata['window_center']
        if metadata.get('window_width'):
            instance.window_width = metadata['window_width']

        instance.dicom_metadata = metadata

        await self.db.flush()
        await self.db.refresh(instance)

        return self._instance_to_response(instance)
