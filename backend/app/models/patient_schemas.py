"""
Pydantic schemas for Patient management.

HL7 FHIR-aligned schemas for patient demographics and contact information.

@module models.patient_schemas
"""

import uuid
from datetime import date, datetime
from typing import Optional, List
from enum import Enum

from pydantic import BaseModel, Field, EmailStr, field_validator, model_validator
import re


class Gender(str, Enum):
    """HL7 FHIR Administrative Gender."""
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    UNKNOWN = "unknown"


class PatientStatus(str, Enum):
    """Patient record status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    DECEASED = "deceased"


# ============================================================================
# REQUEST SCHEMAS
# ============================================================================

class PatientCreate(BaseModel):
    """
    Schema for creating a new patient.

    All required fields for patient registration following HL7 FHIR.
    """
    # Medical Record Number (unique identifier)
    mrn: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Medical Record Number (unique within institution)"
    )

    # Name (HL7 FHIR HumanName)
    given_name: str = Field(..., min_length=1, max_length=100, description="First name")
    middle_name: Optional[str] = Field(None, max_length=100, description="Middle name")
    family_name: str = Field(..., min_length=1, max_length=100, description="Last name/surname")
    name_prefix: Optional[str] = Field(None, max_length=20, description="Title (Dr., Mr., etc.)")
    name_suffix: Optional[str] = Field(None, max_length=20, description="Suffix (Jr., III, etc.)")

    # Demographics
    birth_date: date = Field(..., description="Date of birth")
    gender: Gender = Field(..., description="Administrative gender")

    # Contact - Telecom
    phone_home: Optional[str] = Field(None, max_length=20, description="Home phone")
    phone_mobile: str = Field(..., max_length=20, description="Mobile phone (required for notifications)")
    phone_work: Optional[str] = Field(None, max_length=20, description="Work phone")
    email: Optional[EmailStr] = Field(None, description="Email address")

    # Address
    address_line1: Optional[str] = Field(None, max_length=255, description="Street address line 1")
    address_line2: Optional[str] = Field(None, max_length=255, description="Street address line 2")
    city: Optional[str] = Field(None, max_length=100, description="City")
    state: Optional[str] = Field(None, max_length=100, description="State/Province/Department")
    postal_code: Optional[str] = Field(None, max_length=20, description="Postal/ZIP code")
    country: str = Field(default="COL", max_length=3, description="ISO 3166-1 alpha-3 country code")

    # Emergency Contact
    emergency_contact_name: Optional[str] = Field(None, max_length=200, description="Emergency contact name")
    emergency_contact_phone: Optional[str] = Field(None, max_length=20, description="Emergency contact phone")
    emergency_contact_relationship: Optional[str] = Field(None, max_length=50, description="Relationship to patient")

    # Insurance
    insurance_provider: Optional[str] = Field(None, max_length=200, description="Insurance company name")
    insurance_policy_number: Optional[str] = Field(None, max_length=100, description="Policy number")

    @field_validator('mrn')
    @classmethod
    def validate_mrn(cls, v: str) -> str:
        """Validate MRN format (alphanumeric with hyphens)."""
        if not re.match(r'^[A-Za-z0-9\-]+$', v):
            raise ValueError('MRN must contain only letters, numbers, and hyphens')
        return v.upper()

    @field_validator('phone_mobile', 'phone_home', 'phone_work', 'emergency_contact_phone')
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        """Validate phone number format."""
        if v is None:
            return v
        # Remove common formatting characters
        cleaned = re.sub(r'[\s\-\(\)\.]', '', v)
        if not re.match(r'^\+?[0-9]{7,15}$', cleaned):
            raise ValueError('Invalid phone number format')
        return v

    @field_validator('birth_date')
    @classmethod
    def validate_birth_date(cls, v: date) -> date:
        """Validate birth date is not in the future."""
        if v > date.today():
            raise ValueError('Birth date cannot be in the future')
        return v

    @field_validator('country')
    @classmethod
    def validate_country(cls, v: str) -> str:
        """Validate country code is uppercase."""
        return v.upper()

    model_config = {
        "json_schema_extra": {
            "example": {
                "mrn": "MRN-2025-001",
                "given_name": "Juan",
                "family_name": "Perez",
                "birth_date": "1985-03-15",
                "gender": "male",
                "phone_mobile": "+57 300 123 4567",
                "email": "juan.perez@email.com",
                "city": "Bogota",
                "state": "Cundinamarca",
                "country": "COL"
            }
        }
    }


class PatientUpdate(BaseModel):
    """
    Schema for updating a patient (partial update).

    All fields are optional - only provided fields will be updated.
    """
    given_name: Optional[str] = Field(None, min_length=1, max_length=100)
    middle_name: Optional[str] = Field(None, max_length=100)
    family_name: Optional[str] = Field(None, min_length=1, max_length=100)
    name_prefix: Optional[str] = Field(None, max_length=20)
    name_suffix: Optional[str] = Field(None, max_length=20)

    birth_date: Optional[date] = None
    gender: Optional[Gender] = None

    phone_home: Optional[str] = Field(None, max_length=20)
    phone_mobile: Optional[str] = Field(None, max_length=20)
    phone_work: Optional[str] = Field(None, max_length=20)
    email: Optional[EmailStr] = None

    address_line1: Optional[str] = Field(None, max_length=255)
    address_line2: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    country: Optional[str] = Field(None, max_length=3)

    emergency_contact_name: Optional[str] = Field(None, max_length=200)
    emergency_contact_phone: Optional[str] = Field(None, max_length=20)
    emergency_contact_relationship: Optional[str] = Field(None, max_length=50)

    insurance_provider: Optional[str] = Field(None, max_length=200)
    insurance_policy_number: Optional[str] = Field(None, max_length=100)

    status: Optional[PatientStatus] = None
    deceased_date: Optional[date] = None

    @model_validator(mode='after')
    def validate_deceased(self):
        """Validate deceased status and date."""
        if self.status == PatientStatus.DECEASED and self.deceased_date is None:
            raise ValueError('Deceased date is required when status is deceased')
        if self.deceased_date is not None and self.deceased_date > date.today():
            raise ValueError('Deceased date cannot be in the future')
        return self


class PatientSearch(BaseModel):
    """
    Schema for patient search parameters.
    """
    query: Optional[str] = Field(None, min_length=2, description="Search term (name, MRN, email)")
    mrn: Optional[str] = Field(None, description="Exact MRN match")
    family_name: Optional[str] = Field(None, description="Last name (partial match)")
    given_name: Optional[str] = Field(None, description="First name (partial match)")
    birth_date: Optional[date] = Field(None, description="Exact birth date")
    gender: Optional[Gender] = Field(None, description="Gender filter")
    status: Optional[PatientStatus] = Field(None, description="Status filter")
    city: Optional[str] = Field(None, description="City filter")

    # Pagination
    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")

    # Sorting
    sort_by: str = Field(default="family_name", description="Sort field")
    sort_order: str = Field(default="asc", pattern="^(asc|desc)$", description="Sort order")


# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class PatientResponse(BaseModel):
    """
    Full patient response schema.
    """
    id: uuid.UUID
    mrn: str

    # Name
    given_name: str
    middle_name: Optional[str] = None
    family_name: str
    name_prefix: Optional[str] = None
    name_suffix: Optional[str] = None
    full_name: str  # Computed field

    # Demographics
    birth_date: date
    gender: Gender
    age: int  # Computed field

    # Contact
    phone_home: Optional[str] = None
    phone_mobile: str
    phone_work: Optional[str] = None
    email: Optional[str] = None

    # Address
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: str

    # Emergency Contact
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_relationship: Optional[str] = None

    # Insurance
    insurance_provider: Optional[str] = None
    insurance_policy_number: Optional[str] = None

    # Status
    status: PatientStatus
    deceased_date: Optional[date] = None

    # Audit
    created_at: datetime
    updated_at: datetime

    # Statistics (optional, populated on detail requests)
    study_count: Optional[int] = None
    document_count: Optional[int] = None

    model_config = {
        "from_attributes": True
    }


class PatientSummary(BaseModel):
    """
    Minimal patient summary for lists and references.
    """
    id: uuid.UUID
    mrn: str
    full_name: str
    birth_date: date
    gender: Gender
    status: PatientStatus
    study_count: Optional[int] = None
    document_count: Optional[int] = None

    model_config = {
        "from_attributes": True
    }


class PatientListResponse(BaseModel):
    """
    Paginated list of patients.
    """
    items: List[PatientSummary]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============================================================================
# MEDICAL HISTORY SCHEMAS
# ============================================================================

class MedicalHistoryCreate(BaseModel):
    """Schema for adding medical history entry."""
    condition_name: str = Field(..., min_length=1, max_length=255)
    condition_code: Optional[str] = Field(None, max_length=50, description="ICD-10 or SNOMED CT code")
    condition_system: Optional[str] = Field(
        default="http://snomed.info/sct",
        max_length=100,
        description="Coding system URI"
    )
    is_active: bool = Field(default=True)
    onset_date: Optional[date] = None
    resolution_date: Optional[date] = None
    severity: Optional[str] = Field(None, pattern="^(mild|moderate|severe)$")
    notes: Optional[str] = None

    @model_validator(mode='after')
    def validate_dates(self):
        """Validate onset and resolution dates."""
        if self.onset_date and self.resolution_date:
            if self.resolution_date < self.onset_date:
                raise ValueError('Resolution date cannot be before onset date')
        return self


class MedicalHistoryResponse(BaseModel):
    """Medical history entry response."""
    id: uuid.UUID
    patient_id: uuid.UUID
    condition_name: str
    condition_code: Optional[str] = None
    condition_system: Optional[str] = None
    is_active: bool
    onset_date: Optional[date] = None
    resolution_date: Optional[date] = None
    severity: Optional[str] = None
    notes: Optional[str] = None
    recorded_by: Optional[str] = None
    recorded_at: datetime

    model_config = {
        "from_attributes": True
    }
