"""
HL7 FHIR Integration Routes.

Generates FHIR resources for interoperability with hospital EHR systems:
- ImagingStudy: Links DICOM study metadata to FHIR
- DiagnosticReport: Wraps AI-generated reports as FHIR resources
- Patient: Maps internal patient records to FHIR

@module api.routes.fhir
"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends

from app.security import get_current_active_user
from app.security.models import User
from app.core.logging import get_logger
from app.core.config import get_settings

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(prefix="/fhir", tags=["FHIR"])


def _fhir_datetime(dt_str: Optional[str]) -> Optional[str]:
    """Convert internal datetime string to FHIR instant format."""
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%dT%H:%M:%S+00:00')
    except (ValueError, AttributeError):
        return dt_str


@router.get("/ImagingStudy/{study_id}")
async def get_imaging_study(study_id: str, current_user: User = Depends(get_current_active_user)):
    """
    Generate a FHIR R4 ImagingStudy resource from a study.

    Returns a JSON FHIR resource conforming to:
    https://www.hl7.org/fhir/imagingstudy.html
    """
    from app.core.firebase import get_firestore_client

    try:
        db = get_firestore_client()
        study_doc = db.collection("studies").document(study_id).get()

        if not study_doc.exists:
            raise HTTPException(status_code=404, detail="Study not found")

        study = study_doc.to_dict()

        # Fetch series
        series_docs = db.collection("studies").document(study_id).collection("series").stream()
        series_list = [s.to_dict() for s in series_docs]

        # Build FHIR ImagingStudy
        fhir_study = {
            "resourceType": "ImagingStudy",
            "id": study_id,
            "status": "available",
            "subject": {
                "reference": f"Patient/{study.get('patient_id', '')}",
            },
            "started": _fhir_datetime(study.get("study_date") or study.get("created_at")),
            "description": study.get("study_description", ""),
            "modality": [
                {
                    "system": "http://dicom.nema.org/resources/ontology/DCM",
                    "code": study.get("modality", "MR"),
                }
            ],
            "numberOfSeries": len(series_list),
            "numberOfInstances": sum(s.get("instance_count", 0) for s in series_list),
            "series": [],
        }

        # Add DICOM Study UID if available (from DICOMweb import)
        if study.get("dicom_study_uid"):
            fhir_study["identifier"] = [
                {
                    "system": "urn:dicom:uid",
                    "value": f"urn:oid:{study['dicom_study_uid']}",
                }
            ]

        for series in series_list:
            fhir_series = {
                "uid": series.get("dicom_series_uid") or series.get("id", ""),
                "number": series.get("series_number", 1),
                "modality": {
                    "system": "http://dicom.nema.org/resources/ontology/DCM",
                    "code": series.get("modality", "MR"),
                },
                "description": series.get("series_description", ""),
                "bodysite": {
                    "system": "http://snomed.info/sct",
                    "code": "12738006",
                    "display": "Brain structure",
                } if series.get("body_part_examined", "").upper() == "BRAIN" else None,
            }
            # Remove None values
            fhir_series = {k: v for k, v in fhir_series.items() if v is not None}
            fhir_study["series"].append(fhir_series)

        return fhir_study

    except HTTPException:
        raise
    except Exception as e:
        logger.error("FHIR ImagingStudy generation failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/DiagnosticReport/{report_id}")
async def get_diagnostic_report(
    report_id: str,
    study_id: Optional[str] = None,
    patient_id: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
):
    """
    Generate a FHIR R4 DiagnosticReport resource.

    Wraps AI-generated clinical reports as FHIR-compliant resources
    conforming to: https://www.hl7.org/fhir/diagnosticreport.html
    """
    # Build FHIR DiagnosticReport
    report = {
        "resourceType": "DiagnosticReport",
        "id": report_id,
        "status": "final",
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/v2-0074",
                        "code": "RAD",
                        "display": "Radiology",
                    }
                ]
            }
        ],
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": "18748-4",
                    "display": "Diagnostic imaging study",
                }
            ],
            "text": "MS Brain MRI Analysis Report",
        },
        "issued": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S+00:00'),
        "performer": [
            {
                "display": "MSTool-AI (AI-Assisted)",
            }
        ],
        "conclusion": "AI-generated report — requires physician review before clinical action.",
    }

    if patient_id:
        report["subject"] = {"reference": f"Patient/{patient_id}"}

    if study_id:
        report["imagingStudy"] = [{"reference": f"ImagingStudy/{study_id}"}]

    return report


@router.get("/Patient/{patient_id}")
async def get_patient(patient_id: str, current_user: User = Depends(get_current_active_user)):
    """
    Generate a FHIR R4 Patient resource from internal patient record.

    Conforming to: https://www.hl7.org/fhir/patient.html
    """
    from app.core.firebase import get_firestore_client

    try:
        db = get_firestore_client()

        # Search in patients collection
        patients = db.collection("patients").where("id", "==", patient_id).limit(1).stream()
        patient_doc = None
        for doc in patients:
            patient_doc = doc.to_dict()
            break

        if not patient_doc:
            # Try direct document access
            doc = db.collection("patients").document(patient_id).get()
            if doc.exists:
                patient_doc = doc.to_dict()

        if not patient_doc:
            raise HTTPException(status_code=404, detail="Patient not found")

        full_name = patient_doc.get("full_name", "")
        name_parts = full_name.split() if full_name else [""]

        fhir_patient = {
            "resourceType": "Patient",
            "id": patient_id,
            "active": patient_doc.get("status", "active") == "active",
            "name": [
                {
                    "use": "official",
                    "family": name_parts[-1] if name_parts else "",
                    "given": name_parts[:-1] if len(name_parts) > 1 else [],
                    "text": full_name,
                }
            ],
            "gender": _map_gender(patient_doc.get("gender")),
            "birthDate": patient_doc.get("date_of_birth", ""),
        }

        # MRN identifier
        mrn = patient_doc.get("mrn")
        if mrn:
            fhir_patient["identifier"] = [
                {
                    "use": "official",
                    "type": {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/v2-0203",
                                "code": "MR",
                                "display": "Medical Record Number",
                            }
                        ]
                    },
                    "value": mrn,
                }
            ]

        # Contact info
        telecom = []
        phone = patient_doc.get("phone") or patient_doc.get("mobile_phone")
        if phone:
            telecom.append({"system": "phone", "value": phone, "use": "mobile"})
        email = patient_doc.get("email")
        if email:
            telecom.append({"system": "email", "value": email})
        if telecom:
            fhir_patient["telecom"] = telecom

        # Address
        address_str = patient_doc.get("address")
        if address_str:
            fhir_patient["address"] = [{"text": address_str, "use": "home"}]

        return fhir_patient

    except HTTPException:
        raise
    except Exception as e:
        logger.error("FHIR Patient generation failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=str(e))


def _map_gender(gender: Optional[str]) -> str:
    """Map internal gender to FHIR AdministrativeGender."""
    if not gender:
        return "unknown"
    g = gender.lower()
    if g in ("female", "f"):
        return "female"
    if g in ("male", "m"):
        return "male"
    if g in ("other", "o"):
        return "other"
    return "unknown"
