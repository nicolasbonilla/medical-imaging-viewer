"""Initial EHR schema with Patient, Study, Document, and Audit models.

Revision ID: 001
Revises:
Create Date: 2025-01-04 00:00:00.000000

HL7 FHIR-aligned database schema for Medical Imaging EHR System.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum types
    op.execute("CREATE TYPE gender AS ENUM ('male', 'female', 'other', 'unknown')")
    op.execute("CREATE TYPE patientstatus AS ENUM ('active', 'inactive', 'deceased')")
    op.execute("CREATE TYPE studystatus AS ENUM ('registered', 'available', 'cancelled', 'entered-in-error')")
    op.execute("CREATE TYPE modality AS ENUM ('CT', 'MR', 'US', 'XR', 'MG', 'NM', 'PT', 'CR', 'DX', 'OT')")
    op.execute("CREATE TYPE documentcategory AS ENUM ('lab-result', 'prescription', 'clinical-note', 'discharge-summary', 'radiology-report', 'consent-form', 'referral', 'operative-note', 'pathology-report', 'other')")
    op.execute("CREATE TYPE documentstatus AS ENUM ('current', 'superseded', 'entered-in-error')")

    # Create patients table
    op.create_table(
        'patients',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('mrn', sa.String(50), nullable=False),
        sa.Column('given_name', sa.String(100), nullable=False),
        sa.Column('middle_name', sa.String(100), nullable=True),
        sa.Column('family_name', sa.String(100), nullable=False),
        sa.Column('name_prefix', sa.String(20), nullable=True),
        sa.Column('name_suffix', sa.String(20), nullable=True),
        sa.Column('birth_date', sa.Date(), nullable=False),
        sa.Column('gender', postgresql.ENUM('male', 'female', 'other', 'unknown', name='gender', create_type=False), nullable=False),
        sa.Column('phone_home', sa.String(20), nullable=True),
        sa.Column('phone_mobile', sa.String(20), nullable=False),
        sa.Column('phone_work', sa.String(20), nullable=True),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('address_line1', sa.String(255), nullable=True),
        sa.Column('address_line2', sa.String(255), nullable=True),
        sa.Column('city', sa.String(100), nullable=True),
        sa.Column('state', sa.String(100), nullable=True),
        sa.Column('postal_code', sa.String(20), nullable=True),
        sa.Column('country', sa.String(3), nullable=False, server_default='COL'),
        sa.Column('emergency_contact_name', sa.String(200), nullable=True),
        sa.Column('emergency_contact_phone', sa.String(20), nullable=True),
        sa.Column('emergency_contact_relationship', sa.String(50), nullable=True),
        sa.Column('insurance_provider', sa.String(200), nullable=True),
        sa.Column('insurance_policy_number', sa.String(100), nullable=True),
        sa.Column('status', postgresql.ENUM('active', 'inactive', 'deceased', name='patientstatus', create_type=False), nullable=False, server_default='active'),
        sa.Column('deceased_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Patient indexes
    op.create_index('ix_patients_mrn', 'patients', ['mrn'], unique=True)
    op.create_index('ix_patients_email', 'patients', ['email'], unique=False)
    op.create_index('ix_patients_name', 'patients', ['family_name', 'given_name'], unique=False)
    op.create_index('ix_patients_birth_date', 'patients', ['birth_date'], unique=False)
    op.create_index('ix_patients_status', 'patients', ['status'], unique=False)

    # Create imaging_studies table
    op.create_table(
        'imaging_studies',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('patient_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('study_instance_uid', sa.String(128), nullable=False),
        sa.Column('accession_number', sa.String(64), nullable=True),
        sa.Column('status', postgresql.ENUM('registered', 'available', 'cancelled', 'entered-in-error', name='studystatus', create_type=False), nullable=False, server_default='registered'),
        sa.Column('modality', postgresql.ENUM('CT', 'MR', 'US', 'XR', 'MG', 'NM', 'PT', 'CR', 'DX', 'OT', name='modality', create_type=False), nullable=False),
        sa.Column('body_site', sa.String(100), nullable=True),
        sa.Column('study_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('study_description', sa.Text(), nullable=True),
        sa.Column('reason_for_study', sa.Text(), nullable=True),
        sa.Column('referring_physician_name', sa.String(200), nullable=True),
        sa.Column('referring_physician_id', sa.String(50), nullable=True),
        sa.Column('performing_physician_name', sa.String(200), nullable=True),
        sa.Column('institution_name', sa.String(200), nullable=True),
        sa.Column('gcs_bucket', sa.String(255), nullable=False),
        sa.Column('gcs_prefix', sa.String(1024), nullable=False),
        sa.Column('number_of_series', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('number_of_instances', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_size_bytes', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('dicom_metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Study indexes
    op.create_index('ix_studies_patient_id', 'imaging_studies', ['patient_id'], unique=False)
    op.create_index('ix_studies_study_instance_uid', 'imaging_studies', ['study_instance_uid'], unique=True)
    op.create_index('ix_studies_accession_number', 'imaging_studies', ['accession_number'], unique=False)
    op.create_index('ix_studies_patient_date', 'imaging_studies', ['patient_id', 'study_date'], unique=False)
    op.create_index('ix_studies_modality', 'imaging_studies', ['modality'], unique=False)

    # Create imaging_series table
    op.create_table(
        'imaging_series',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('study_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('series_instance_uid', sa.String(128), nullable=False),
        sa.Column('series_number', sa.Integer(), nullable=True),
        sa.Column('series_description', sa.String(255), nullable=True),
        sa.Column('modality', postgresql.ENUM('CT', 'MR', 'US', 'XR', 'MG', 'NM', 'PT', 'CR', 'DX', 'OT', name='modality', create_type=False), nullable=False),
        sa.Column('series_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('gcs_path', sa.String(1024), nullable=False),
        sa.Column('number_of_instances', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['study_id'], ['imaging_studies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Series indexes
    op.create_index('ix_series_study_id', 'imaging_series', ['study_id'], unique=False)
    op.create_index('ix_series_series_instance_uid', 'imaging_series', ['series_instance_uid'], unique=True)

    # Create imaging_instances table
    op.create_table(
        'imaging_instances',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('series_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('sop_instance_uid', sa.String(128), nullable=False),
        sa.Column('sop_class_uid', sa.String(128), nullable=True),
        sa.Column('instance_number', sa.Integer(), nullable=True),
        sa.Column('gcs_object_name', sa.String(1024), nullable=False),
        sa.Column('original_filename', sa.String(255), nullable=False),
        sa.Column('content_type', sa.String(100), nullable=False),
        sa.Column('file_size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('checksum_sha256', sa.String(64), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['series_id'], ['imaging_series.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Instance indexes
    op.create_index('ix_instances_series_id', 'imaging_instances', ['series_id'], unique=False)
    op.create_index('ix_instances_sop_instance_uid', 'imaging_instances', ['sop_instance_uid'], unique=True)
    op.create_index('ix_instances_series_number', 'imaging_instances', ['series_id', 'instance_number'], unique=False)

    # Create documents table
    op.create_table(
        'documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('patient_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('study_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', postgresql.ENUM('lab-result', 'prescription', 'clinical-note', 'discharge-summary', 'radiology-report', 'consent-form', 'referral', 'operative-note', 'pathology-report', 'other', name='documentcategory', create_type=False), nullable=False),
        sa.Column('document_date', sa.Date(), nullable=False),
        sa.Column('status', postgresql.ENUM('current', 'superseded', 'entered-in-error', name='documentstatus', create_type=False), nullable=False, server_default='current'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('supersedes_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('gcs_bucket', sa.String(255), nullable=False),
        sa.Column('gcs_object_name', sa.String(1024), nullable=False),
        sa.Column('original_filename', sa.String(255), nullable=False),
        sa.Column('content_type', sa.String(100), nullable=False),
        sa.Column('file_size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('checksum_sha256', sa.String(64), nullable=False),
        sa.Column('author_name', sa.String(200), nullable=True),
        sa.Column('author_id', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['study_id'], ['imaging_studies.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['supersedes_id'], ['documents.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('version >= 1', name='ck_document_version_positive')
    )

    # Document indexes
    op.create_index('ix_documents_patient_id', 'documents', ['patient_id'], unique=False)
    op.create_index('ix_documents_study_id', 'documents', ['study_id'], unique=False)
    op.create_index('ix_documents_patient_category', 'documents', ['patient_id', 'category'], unique=False)
    op.create_index('ix_documents_date', 'documents', ['document_date'], unique=False)

    # Create medical_history table
    op.create_table(
        'medical_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('patient_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('condition_name', sa.String(255), nullable=False),
        sa.Column('condition_code', sa.String(50), nullable=True),
        sa.Column('condition_system', sa.String(100), nullable=True, server_default='http://snomed.info/sct'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('onset_date', sa.Date(), nullable=True),
        sa.Column('resolution_date', sa.Date(), nullable=True),
        sa.Column('severity', sa.String(50), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('recorded_by', sa.String(200), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Medical history indexes
    op.create_index('ix_medical_history_patient_id', 'medical_history', ['patient_id'], unique=False)
    op.create_index('ix_medical_history_patient_active', 'medical_history', ['patient_id', 'is_active'], unique=False)

    # Create audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('username', sa.String(100), nullable=True),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('resource_type', sa.String(50), nullable=False),
        sa.Column('resource_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(500), nullable=True),
        sa.Column('details', postgresql.JSONB(), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Audit log indexes
    op.create_index('ix_audit_timestamp', 'audit_logs', ['timestamp'], unique=False)
    op.create_index('ix_audit_action', 'audit_logs', ['action'], unique=False)
    op.create_index('ix_audit_resource', 'audit_logs', ['resource_type', 'resource_id'], unique=False)
    op.create_index('ix_audit_user_time', 'audit_logs', ['user_id', 'timestamp'], unique=False)


def downgrade() -> None:
    # Drop tables in reverse order (respecting foreign keys)
    op.drop_table('audit_logs')
    op.drop_table('medical_history')
    op.drop_table('documents')
    op.drop_table('imaging_instances')
    op.drop_table('imaging_series')
    op.drop_table('imaging_studies')
    op.drop_table('patients')

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS documentstatus")
    op.execute("DROP TYPE IF EXISTS documentcategory")
    op.execute("DROP TYPE IF EXISTS modality")
    op.execute("DROP TYPE IF EXISTS studystatus")
    op.execute("DROP TYPE IF EXISTS patientstatus")
    op.execute("DROP TYPE IF EXISTS gender")
