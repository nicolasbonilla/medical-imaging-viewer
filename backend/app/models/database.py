"""
SQLAlchemy ORM Models for EHR System.

HL7 FHIR-aligned data models for:
- Patient demographics and contact information
- Imaging studies (DICOM/NIfTI)
- Clinical documents (PDF, Word, images)
- Medical history tracking

@module models.database
"""

import uuid
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from enum import Enum as PyEnum

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text, Date, DateTime,
    ForeignKey, Enum, JSON, LargeBinary, BigInteger, Index, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


# ============================================================================
# ENUMS (HL7 FHIR aligned)
# ============================================================================

class Gender(str, PyEnum):
    """HL7 FHIR Administrative Gender (http://hl7.org/fhir/administrative-gender)."""
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    UNKNOWN = "unknown"


class PatientStatus(str, PyEnum):
    """Patient record status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    DECEASED = "deceased"


class StudyStatus(str, PyEnum):
    """HL7 FHIR ImagingStudy status (http://hl7.org/fhir/imagingstudy-status)."""
    REGISTERED = "registered"
    AVAILABLE = "available"
    CANCELLED = "cancelled"
    ENTERED_IN_ERROR = "entered-in-error"


class Modality(str, PyEnum):
    """DICOM Modality codes (subset)."""
    CT = "CT"           # Computed Tomography
    MR = "MR"           # Magnetic Resonance
    US = "US"           # Ultrasound
    XR = "XR"           # X-Ray Radiography
    MG = "MG"           # Mammography
    NM = "NM"           # Nuclear Medicine
    PT = "PT"           # PET
    CR = "CR"           # Computed Radiography
    DX = "DX"           # Digital Radiography
    OT = "OT"           # Other


class DocumentCategory(str, PyEnum):
    """HL7 FHIR Document Reference category."""
    LAB_RESULT = "lab-result"
    PRESCRIPTION = "prescription"
    CLINICAL_NOTE = "clinical-note"
    DISCHARGE_SUMMARY = "discharge-summary"
    RADIOLOGY_REPORT = "radiology-report"
    CONSENT_FORM = "consent-form"
    REFERRAL = "referral"
    OPERATIVE_NOTE = "operative-note"
    PATHOLOGY_REPORT = "pathology-report"
    OTHER = "other"


class DocumentStatus(str, PyEnum):
    """Document lifecycle status."""
    CURRENT = "current"
    SUPERSEDED = "superseded"
    ENTERED_IN_ERROR = "entered-in-error"


class SeriesStatus(str, PyEnum):
    """Series status within a study."""
    REGISTERED = "registered"
    AVAILABLE = "available"
    CANCELLED = "cancelled"


# ============================================================================
# PATIENT MODEL (HL7 FHIR Patient Resource)
# ============================================================================

class Patient(Base):
    """
    Patient demographics following HL7 FHIR Patient resource.

    References:
    - http://hl7.org/fhir/patient.html
    - ISO 27001 A.8.2.3 (Handling of assets)
    """
    __tablename__ = "patients"

    # Primary Key (UUID for HIPAA compliance - no sequential IDs)
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    # Medical Record Number (MRN) - unique identifier within institution
    mrn: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True
    )

    # HL7 FHIR HumanName
    given_name: Mapped[str] = mapped_column(String(100), nullable=False)
    middle_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    family_name: Mapped[str] = mapped_column(String(100), nullable=False)
    name_prefix: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # Dr., Mr., etc.
    name_suffix: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # Jr., III, etc.

    # Demographics
    birth_date: Mapped[date] = mapped_column(Date, nullable=False)
    gender: Mapped[Gender] = mapped_column(Enum(Gender), nullable=False)

    # Contact - Telecom (HL7 FHIR ContactPoint)
    phone_home: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    phone_mobile: Mapped[str] = mapped_column(String(20), nullable=False)  # Required for notifications
    phone_work: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)

    # Address (HL7 FHIR Address)
    address_line1: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    address_line2: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    country: Mapped[str] = mapped_column(String(3), nullable=False, default="COL")  # ISO 3166-1 alpha-3

    # Emergency Contact
    emergency_contact_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    emergency_contact_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    emergency_contact_relationship: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Insurance/Payer (simplified)
    insurance_provider: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    insurance_policy_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Status and Audit
    status: Mapped[PatientStatus] = mapped_column(
        Enum(PatientStatus),
        nullable=False,
        default=PatientStatus.ACTIVE
    )
    deceased_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Audit fields (ISO 27001 A.12.4.1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Relationships
    studies: Mapped[List["ImagingStudy"]] = relationship(
        "ImagingStudy",
        back_populates="patient",
        cascade="all, delete-orphan"
    )
    documents: Mapped[List["Document"]] = relationship(
        "Document",
        back_populates="patient",
        cascade="all, delete-orphan"
    )
    medical_history: Mapped[List["MedicalHistory"]] = relationship(
        "MedicalHistory",
        back_populates="patient",
        cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index('ix_patients_name', 'family_name', 'given_name'),
        Index('ix_patients_birth_date', 'birth_date'),
        Index('ix_patients_status', 'status'),
    )

    @property
    def full_name(self) -> str:
        """Return full name formatted."""
        parts = []
        if self.name_prefix:
            parts.append(self.name_prefix)
        parts.append(self.given_name)
        if self.middle_name:
            parts.append(self.middle_name)
        parts.append(self.family_name)
        if self.name_suffix:
            parts.append(self.name_suffix)
        return " ".join(parts)

    @property
    def age(self) -> int:
        """Calculate current age."""
        today = date.today()
        return today.year - self.birth_date.year - (
            (today.month, today.day) < (self.birth_date.month, self.birth_date.day)
        )


# ============================================================================
# IMAGING STUDY MODEL (HL7 FHIR ImagingStudy Resource)
# ============================================================================

class ImagingStudy(Base):
    """
    Imaging study following HL7 FHIR ImagingStudy resource.
    Represents a DICOM study or NIfTI acquisition session.

    References:
    - http://hl7.org/fhir/imagingstudy.html
    """
    __tablename__ = "imaging_studies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    # Patient reference
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # DICOM Study Instance UID (unique across systems)
    study_instance_uid: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
        index=True
    )

    # Accession Number (institution-specific study ID)
    accession_number: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True
    )

    # Study details
    status: Mapped[StudyStatus] = mapped_column(
        Enum(StudyStatus),
        nullable=False,
        default=StudyStatus.REGISTERED
    )
    modality: Mapped[Modality] = mapped_column(Enum(Modality), nullable=False)
    body_site: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # SNOMED CT code

    # Dates
    study_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Description
    study_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reason_for_study: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Referring physician
    referring_physician_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    referring_physician_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Performing physician/technologist
    performing_physician_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Institution
    institution_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # GCS Storage location
    gcs_bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    gcs_prefix: Mapped[str] = mapped_column(String(1024), nullable=False)  # patients/{patient_id}/studies/{study_id}/

    # Statistics
    number_of_series: Mapped[int] = mapped_column(Integer, default=0)
    number_of_instances: Mapped[int] = mapped_column(Integer, default=0)
    total_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)

    # DICOM metadata (stored as JSON for flexibility)
    dicom_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Relationships
    patient: Mapped["Patient"] = relationship("Patient", back_populates="studies")
    series: Mapped[List["ImagingSeries"]] = relationship(
        "ImagingSeries",
        back_populates="study",
        cascade="all, delete-orphan"
    )
    documents: Mapped[List["Document"]] = relationship(
        "Document",
        back_populates="study"
    )

    __table_args__ = (
        Index('ix_studies_patient_date', 'patient_id', 'study_date'),
        Index('ix_studies_modality', 'modality'),
    )


class ImagingSeries(Base):
    """
    Imaging series - group of related instances within a study.
    Corresponds to DICOM Series.
    """
    __tablename__ = "imaging_series"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("imaging_studies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # DICOM Series Instance UID
    series_instance_uid: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False
    )

    series_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    series_description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    modality: Mapped[Modality] = mapped_column(Enum(Modality), nullable=False)

    # Series date/time
    series_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # GCS path for this series
    gcs_path: Mapped[str] = mapped_column(String(1024), nullable=False)

    # Instance count
    number_of_instances: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    study: Mapped["ImagingStudy"] = relationship("ImagingStudy", back_populates="series")
    instances: Mapped[List["ImagingInstance"]] = relationship(
        "ImagingInstance",
        back_populates="series",
        cascade="all, delete-orphan"
    )


class ImagingInstance(Base):
    """
    Single image instance (DICOM file or NIfTI slice).
    Corresponds to DICOM SOP Instance.
    """
    __tablename__ = "imaging_instances"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    series_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("imaging_series.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # DICOM SOP Instance UID
    sop_instance_uid: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False
    )
    sop_class_uid: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Instance number (for ordering)
    instance_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # GCS storage
    gcs_object_name: Mapped[str] = mapped_column(String(1024), nullable=False)

    # File info
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Integrity verification (ISO 27001 A.10.1.1)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    # Upload tracking
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    # Relationships
    series: Mapped["ImagingSeries"] = relationship("ImagingSeries", back_populates="instances")

    __table_args__ = (
        Index('ix_instances_series_number', 'series_id', 'instance_number'),
    )


# ============================================================================
# DOCUMENT MODEL (HL7 FHIR DocumentReference Resource)
# ============================================================================

class Document(Base):
    """
    Clinical document following HL7 FHIR DocumentReference resource.
    Supports PDF, Word, and image documents with versioning.

    References:
    - http://hl7.org/fhir/documentreference.html
    """
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    # Patient reference (required)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Optional study reference (for radiology reports, etc.)
    study_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("imaging_studies.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # Document metadata
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[DocumentCategory] = mapped_column(
        Enum(DocumentCategory),
        nullable=False,
        index=True
    )

    # Document date (when the document was created/signed, not upload date)
    document_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Status and versioning
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus),
        nullable=False,
        default=DocumentStatus.CURRENT
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Link to previous version (for version chain)
    supersedes_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True
    )

    # GCS storage
    gcs_bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    gcs_object_name: Mapped[str] = mapped_column(String(1024), nullable=False)

    # File info
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Integrity (ISO 27001 A.10.1.1)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    # Author (practitioner who created/signed the document)
    author_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    author_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Relationships
    patient: Mapped["Patient"] = relationship("Patient", back_populates="documents")
    study: Mapped[Optional["ImagingStudy"]] = relationship("ImagingStudy", back_populates="documents")
    supersedes: Mapped[Optional["Document"]] = relationship(
        "Document",
        remote_side=[id],
        foreign_keys=[supersedes_id]
    )

    __table_args__ = (
        Index('ix_documents_patient_category', 'patient_id', 'category'),
        Index('ix_documents_date', 'document_date'),
        CheckConstraint('version >= 1', name='ck_document_version_positive'),
    )

    # Relationship to versions
    versions: Mapped[List["DocumentVersion"]] = relationship(
        "DocumentVersion",
        back_populates="document",
        order_by="DocumentVersion.version.desc()"
    )


# ============================================================================
# DOCUMENT VERSION MODEL
# ============================================================================

class DocumentVersion(Base):
    """
    Document version history for tracking changes.
    Each new version of a document creates a new record here.
    """
    __tablename__ = "document_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    # Reference to parent document
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Version number (1, 2, 3, ...)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    # File information (at time of this version)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    # GCS location for this version
    gcs_object_name: Mapped[str] = mapped_column(String(500), nullable=False)

    # Change summary (optional)
    change_summary: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Relationship
    document: Mapped["Document"] = relationship("Document", back_populates="versions")

    __table_args__ = (
        Index('ix_document_versions_doc_version', 'document_id', 'version'),
        CheckConstraint('version >= 1', name='ck_version_positive'),
    )


# ============================================================================
# MEDICAL HISTORY MODEL (HL7 FHIR Condition Resource)
# ============================================================================

class MedicalHistory(Base):
    """
    Patient medical history/conditions following HL7 FHIR Condition resource.

    References:
    - http://hl7.org/fhir/condition.html
    """
    __tablename__ = "medical_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Condition details
    condition_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # SNOMED CT or ICD-10 code (optional but recommended)
    condition_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    condition_system: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        default="http://snomed.info/sct"
    )

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Dates
    onset_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    resolution_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Severity (mild, moderate, severe)
    severity: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Recorded by
    recorded_by: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    # Relationships
    patient: Mapped["Patient"] = relationship("Patient", back_populates="medical_history")

    __table_args__ = (
        Index('ix_medical_history_patient_active', 'patient_id', 'is_active'),
    )


# ============================================================================
# AUDIT LOG MODEL (ISO 27001 A.12.4.1)
# ============================================================================

class AuditLog(Base):
    """
    Audit trail for all data access and modifications.
    Implements ISO 27001 A.12.4.1 (Event logging).
    """
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    # Timestamp
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )

    # User who performed the action
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Action details
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # CREATE, READ, UPDATE, DELETE
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # Patient, Study, Document
    resource_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Request details
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)  # IPv6 max length
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Additional context
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    # Success/failure
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index('ix_audit_user_time', 'user_id', 'timestamp'),
        Index('ix_audit_resource', 'resource_type', 'resource_id'),
    )
