"""
Patient Service Implementation using Firebase Firestore.

Manages patient demographics, medical history, and related operations
following HL7 FHIR standards with Firestore backend.

@module services.patient_service_firestore
"""

from typing import Optional, List, Tuple
from uuid import UUID, uuid4
from datetime import date, datetime
import logging

from google.cloud.firestore_v1 import FieldFilter

from app.core.firebase import (
    get_firestore_client,
    Collections,
    get_document,
    create_document,
    update_document,
    delete_document,
    query_collection,
    count_collection
)
from app.core.interfaces.patient_interface import IPatientService
from app.core.exceptions import NotFoundException, ConflictException, ValidationException
from app.models.patient_schemas import (
    PatientCreate,
    PatientUpdate,
    PatientSearch,
    PatientResponse,
    PatientSummary,
    MedicalHistoryCreate,
    MedicalHistoryResponse,
    PatientStatus,
    Gender
)

logger = logging.getLogger(__name__)


def _calculate_age(birth_date: date) -> int:
    """Calculate age from birth date."""
    today = date.today()
    age = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        age -= 1
    return age


def _build_full_name(
    given_name: str,
    family_name: str,
    middle_name: Optional[str] = None,
    name_prefix: Optional[str] = None,
    name_suffix: Optional[str] = None
) -> str:
    """Build full name from components."""
    parts = []
    if name_prefix:
        parts.append(name_prefix)
    parts.append(given_name)
    if middle_name:
        parts.append(middle_name)
    parts.append(family_name)
    if name_suffix:
        parts.append(name_suffix)
    return " ".join(parts)


class PatientServiceFirestore(IPatientService):
    """
    Patient service implementation with Firestore backend.
    """

    def __init__(self):
        """Initialize patient service with Firestore."""
        self.db = get_firestore_client()
        self.collection = Collections.PATIENTS

    def _doc_to_response(
        self,
        doc_data: dict,
        study_count: Optional[int] = None,
        document_count: Optional[int] = None
    ) -> PatientResponse:
        """Convert Firestore document to PatientResponse."""
        # Handle date conversions
        birth_date = doc_data.get("birth_date")
        if isinstance(birth_date, str):
            birth_date = date.fromisoformat(birth_date)
        elif hasattr(birth_date, 'date'):
            birth_date = birth_date.date()

        created_at = doc_data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        updated_at = doc_data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)

        deceased_date = doc_data.get("deceased_date")
        if isinstance(deceased_date, str):
            deceased_date = date.fromisoformat(deceased_date)

        # Calculate age
        age = _calculate_age(birth_date) if birth_date else None

        # Build full name
        full_name = _build_full_name(
            doc_data.get("given_name", ""),
            doc_data.get("family_name", ""),
            doc_data.get("middle_name"),
            doc_data.get("name_prefix"),
            doc_data.get("name_suffix")
        )

        return PatientResponse(
            id=UUID(doc_data["id"]),
            mrn=doc_data["mrn"],
            given_name=doc_data["given_name"],
            middle_name=doc_data.get("middle_name"),
            family_name=doc_data["family_name"],
            name_prefix=doc_data.get("name_prefix"),
            name_suffix=doc_data.get("name_suffix"),
            full_name=full_name,
            birth_date=birth_date,
            gender=Gender(doc_data["gender"]),
            age=age,
            phone_home=doc_data.get("phone_home"),
            phone_mobile=doc_data.get("phone_mobile"),
            phone_work=doc_data.get("phone_work"),
            email=doc_data.get("email"),
            address_line1=doc_data.get("address_line1"),
            address_line2=doc_data.get("address_line2"),
            city=doc_data.get("city"),
            state=doc_data.get("state"),
            postal_code=doc_data.get("postal_code"),
            country=doc_data.get("country"),
            emergency_contact_name=doc_data.get("emergency_contact_name"),
            emergency_contact_phone=doc_data.get("emergency_contact_phone"),
            emergency_contact_relationship=doc_data.get("emergency_contact_relationship"),
            insurance_provider=doc_data.get("insurance_provider"),
            insurance_policy_number=doc_data.get("insurance_policy_number"),
            status=PatientStatus(doc_data.get("status", "active")),
            deceased_date=deceased_date,
            created_at=created_at,
            updated_at=updated_at,
            study_count=study_count,
            document_count=document_count
        )

    def _doc_to_summary(self, doc_data: dict) -> PatientSummary:
        """Convert Firestore document to PatientSummary."""
        birth_date = doc_data.get("birth_date")
        if isinstance(birth_date, str):
            birth_date = date.fromisoformat(birth_date)
        elif hasattr(birth_date, 'date'):
            birth_date = birth_date.date()

        full_name = _build_full_name(
            doc_data.get("given_name", ""),
            doc_data.get("family_name", ""),
            doc_data.get("middle_name"),
            doc_data.get("name_prefix"),
            doc_data.get("name_suffix")
        )

        return PatientSummary(
            id=UUID(doc_data["id"]),
            mrn=doc_data["mrn"],
            full_name=full_name,
            birth_date=birth_date,
            gender=Gender(doc_data["gender"]),
            status=PatientStatus(doc_data.get("status", "active"))
        )

    async def create_patient(
        self,
        data: PatientCreate,
        created_by: Optional[UUID] = None
    ) -> PatientResponse:
        """Create a new patient record."""
        # Check if MRN already exists
        existing = self.db.collection(self.collection).where(
            filter=FieldFilter("mrn", "==", data.mrn.upper())
        ).limit(1).get()

        if list(existing):
            raise ConflictException(
                message=f"Patient with MRN '{data.mrn}' already exists",
                error_code="PATIENT_MRN_EXISTS",
                details={"mrn": data.mrn}
            )

        # Generate new patient ID
        patient_id = str(uuid4())
        now = datetime.utcnow()

        # Build document data
        patient_data = {
            "id": patient_id,
            "mrn": data.mrn.upper(),
            "given_name": data.given_name,
            "middle_name": data.middle_name,
            "family_name": data.family_name,
            "name_prefix": data.name_prefix,
            "name_suffix": data.name_suffix,
            "birth_date": data.birth_date.isoformat() if data.birth_date else None,
            "gender": data.gender.value if hasattr(data.gender, 'value') else data.gender,
            "phone_home": data.phone_home,
            "phone_mobile": data.phone_mobile,
            "phone_work": data.phone_work,
            "email": data.email,
            "address_line1": data.address_line1,
            "address_line2": data.address_line2,
            "city": data.city,
            "state": data.state,
            "postal_code": data.postal_code,
            "country": data.country,
            "emergency_contact_name": data.emergency_contact_name,
            "emergency_contact_phone": data.emergency_contact_phone,
            "emergency_contact_relationship": data.emergency_contact_relationship,
            "insurance_provider": data.insurance_provider,
            "insurance_policy_number": data.insurance_policy_number,
            "status": "active",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "created_by": str(created_by) if created_by else None
        }

        # Create document
        self.db.collection(self.collection).document(patient_id).set(patient_data)

        logger.info(
            "Patient created",
            extra={
                "patient_id": patient_id,
                "mrn": data.mrn,
                "created_by": str(created_by) if created_by else None
            }
        )

        return self._doc_to_response(patient_data, study_count=0, document_count=0)

    async def get_patient(
        self,
        patient_id: UUID,
        include_stats: bool = False
    ) -> PatientResponse:
        """Get a patient by ID."""
        doc_ref = self.db.collection(self.collection).document(str(patient_id))
        doc = doc_ref.get()

        if not doc.exists:
            raise NotFoundException(
                message="Patient not found",
                error_code="PATIENT_NOT_FOUND",
                details={"patient_id": str(patient_id)}
            )

        doc_data = doc.to_dict()
        doc_data["id"] = doc.id

        study_count = None
        document_count = None

        if include_stats:
            # Count studies for this patient
            studies = self.db.collection(Collections.STUDIES).where(
                filter=FieldFilter("patient_id", "==", str(patient_id))
            ).count().get()
            study_count = studies[0][0].value if studies else 0

            # Count documents for this patient
            docs = self.db.collection(Collections.DOCUMENTS).where(
                filter=FieldFilter("patient_id", "==", str(patient_id))
            ).count().get()
            document_count = docs[0][0].value if docs else 0

        return self._doc_to_response(doc_data, study_count, document_count)

    async def get_patient_by_mrn(self, mrn: str) -> Optional[PatientResponse]:
        """Get a patient by MRN."""
        docs = self.db.collection(self.collection).where(
            filter=FieldFilter("mrn", "==", mrn.upper())
        ).limit(1).get()

        doc_list = list(docs)
        if not doc_list:
            return None

        doc = doc_list[0]
        doc_data = doc.to_dict()
        doc_data["id"] = doc.id

        return self._doc_to_response(doc_data)

    async def update_patient(
        self,
        patient_id: UUID,
        data: PatientUpdate,
        updated_by: Optional[UUID] = None
    ) -> PatientResponse:
        """Update a patient record."""
        doc_ref = self.db.collection(self.collection).document(str(patient_id))
        doc = doc_ref.get()

        if not doc.exists:
            raise NotFoundException(
                message="Patient not found",
                error_code="PATIENT_NOT_FOUND",
                details={"patient_id": str(patient_id)}
            )

        # Build update data
        update_data = data.model_dump(exclude_unset=True)

        # Convert date fields to ISO strings
        for date_field in ["birth_date", "deceased_date"]:
            if date_field in update_data and update_data[date_field]:
                update_data[date_field] = update_data[date_field].isoformat()

        # Convert enum fields
        if "gender" in update_data and hasattr(update_data["gender"], 'value'):
            update_data["gender"] = update_data["gender"].value
        if "status" in update_data and hasattr(update_data["status"], 'value'):
            update_data["status"] = update_data["status"].value

        update_data["updated_at"] = datetime.utcnow().isoformat()
        update_data["updated_by"] = str(updated_by) if updated_by else None

        # Update document
        doc_ref.update(update_data)

        logger.info(
            "Patient updated",
            extra={
                "patient_id": str(patient_id),
                "updated_fields": list(update_data.keys()),
                "updated_by": str(updated_by) if updated_by else None
            }
        )

        # Get updated document
        updated_doc = doc_ref.get()
        doc_data = updated_doc.to_dict()
        doc_data["id"] = updated_doc.id

        return self._doc_to_response(doc_data)

    async def delete_patient(
        self,
        patient_id: UUID,
        deleted_by: Optional[UUID] = None
    ) -> bool:
        """Soft delete a patient (set status to inactive)."""
        doc_ref = self.db.collection(self.collection).document(str(patient_id))
        doc = doc_ref.get()

        if not doc.exists:
            raise NotFoundException(
                message="Patient not found",
                error_code="PATIENT_NOT_FOUND",
                details={"patient_id": str(patient_id)}
            )

        # Soft delete - just update status
        doc_ref.update({
            "status": "inactive",
            "updated_at": datetime.utcnow().isoformat(),
            "updated_by": str(deleted_by) if deleted_by else None
        })

        logger.info(
            "Patient deactivated",
            extra={
                "patient_id": str(patient_id),
                "deleted_by": str(deleted_by) if deleted_by else None
            }
        )

        return True

    async def search_patients(
        self,
        search: PatientSearch
    ) -> Tuple[List[PatientSummary], int]:
        """Search patients with filters and pagination."""
        query = self.db.collection(self.collection)

        # Build filters
        if search.mrn:
            query = query.where(filter=FieldFilter("mrn", "==", search.mrn.upper()))

        if search.family_name:
            # Firestore doesn't support LIKE, use range query for prefix matching
            query = query.where(filter=FieldFilter("family_name", ">=", search.family_name))
            query = query.where(filter=FieldFilter("family_name", "<=", search.family_name + "\uf8ff"))

        if search.gender:
            gender_value = search.gender.value if hasattr(search.gender, 'value') else search.gender
            query = query.where(filter=FieldFilter("gender", "==", gender_value))

        if search.status:
            status_value = search.status.value if hasattr(search.status, 'value') else search.status
            query = query.where(filter=FieldFilter("status", "==", status_value))

        # Get total count first
        count_result = query.count().get()
        total = count_result[0][0].value if count_result else 0

        # Apply ordering - default to family_name ascending
        if search.sort_by == "created_at":
            direction = "DESCENDING" if search.sort_order == "desc" else "ASCENDING"
            query = query.order_by("created_at", direction=direction)
        else:
            direction = "DESCENDING" if search.sort_order == "desc" else "ASCENDING"
            query = query.order_by("family_name", direction=direction)

        # Apply pagination
        offset = (search.page - 1) * search.page_size
        if offset > 0:
            # Firestore pagination with offset (not efficient for large offsets)
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
            results.append(self._doc_to_summary(doc_data))

        return results, total

    async def list_patients(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None
    ) -> Tuple[List[PatientSummary], int]:
        """List all patients with pagination."""
        query = self.db.collection(self.collection)

        if status:
            query = query.where(filter=FieldFilter("status", "==", status))

        # Get total count
        count_result = query.count().get()
        total = count_result[0][0].value if count_result else 0

        # Apply ordering
        query = query.order_by("family_name").order_by("given_name")

        # Apply pagination
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
            results.append(self._doc_to_summary(doc_data))

        return results, total

    # Medical History methods would go here (simplified for now)

    async def add_medical_history(
        self,
        patient_id: UUID,
        data: MedicalHistoryCreate,
        recorded_by: Optional[str] = None
    ) -> MedicalHistoryResponse:
        """Add a medical history entry for a patient."""
        # Verify patient exists
        doc = self.db.collection(self.collection).document(str(patient_id)).get()
        if not doc.exists:
            raise NotFoundException(
                message="Patient not found",
                error_code="PATIENT_NOT_FOUND",
                details={"patient_id": str(patient_id)}
            )

        # Create medical history in subcollection
        history_id = str(uuid4())
        now = datetime.utcnow()

        history_data = {
            "id": history_id,
            "patient_id": str(patient_id),
            "condition_name": data.condition_name,
            "condition_code": data.condition_code,
            "condition_system": data.condition_system,
            "is_active": data.is_active,
            "onset_date": data.onset_date.isoformat() if data.onset_date else None,
            "resolution_date": data.resolution_date.isoformat() if data.resolution_date else None,
            "severity": data.severity,
            "notes": data.notes,
            "recorded_by": recorded_by,
            "recorded_at": now.isoformat()
        }

        # Store in subcollection
        self.db.collection(self.collection).document(str(patient_id)).collection(
            "medical_history"
        ).document(history_id).set(history_data)

        logger.info(
            "Medical history added",
            extra={
                "patient_id": str(patient_id),
                "history_id": history_id,
                "condition": data.condition_name
            }
        )

        return MedicalHistoryResponse(
            id=UUID(history_id),
            patient_id=patient_id,
            condition_name=data.condition_name,
            condition_code=data.condition_code,
            condition_system=data.condition_system,
            is_active=data.is_active,
            onset_date=data.onset_date,
            resolution_date=data.resolution_date,
            severity=data.severity,
            notes=data.notes,
            recorded_by=recorded_by,
            recorded_at=now
        )

    async def get_medical_history(
        self,
        patient_id: UUID,
        active_only: bool = False
    ) -> List[MedicalHistoryResponse]:
        """Get medical history for a patient."""
        # Verify patient exists
        doc = self.db.collection(self.collection).document(str(patient_id)).get()
        if not doc.exists:
            raise NotFoundException(
                message="Patient not found",
                error_code="PATIENT_NOT_FOUND",
                details={"patient_id": str(patient_id)}
            )

        query = self.db.collection(self.collection).document(str(patient_id)).collection(
            "medical_history"
        )

        if active_only:
            query = query.where(filter=FieldFilter("is_active", "==", True))

        query = query.order_by("recorded_at", direction="DESCENDING")
        docs = query.stream()

        results = []
        for doc in docs:
            data = doc.to_dict()
            results.append(MedicalHistoryResponse(
                id=UUID(data["id"]),
                patient_id=patient_id,
                condition_name=data["condition_name"],
                condition_code=data.get("condition_code"),
                condition_system=data.get("condition_system"),
                is_active=data.get("is_active", True),
                onset_date=date.fromisoformat(data["onset_date"]) if data.get("onset_date") else None,
                resolution_date=date.fromisoformat(data["resolution_date"]) if data.get("resolution_date") else None,
                severity=data.get("severity"),
                notes=data.get("notes"),
                recorded_by=data.get("recorded_by"),
                recorded_at=datetime.fromisoformat(data["recorded_at"]) if data.get("recorded_at") else None
            ))

        return results

    async def update_medical_history(
        self,
        history_id: UUID,
        is_active: bool,
        resolution_date: Optional[str] = None
    ) -> MedicalHistoryResponse:
        """Update a medical history entry."""
        # This requires knowing the patient_id to access subcollection
        # For simplicity, we'll search across all patients (not efficient for large datasets)
        raise NotImplementedError(
            "Medical history update requires patient context. "
            "Use patient-scoped update endpoint instead."
        )
