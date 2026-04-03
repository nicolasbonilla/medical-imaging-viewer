"""
DICOMweb Bridge Service.

Provides QIDO-RS search and WADO-RS retrieval from external PACS systems,
with automatic DICOM-to-NIfTI conversion and GCS storage.

Acts as an import bridge: DICOMweb → DICOM → NIfTI → GCS → existing pipeline.

@module services.dicomweb_service
"""

import asyncio
import io
import uuid
import tempfile
import os
from typing import Optional
from datetime import datetime

import httpx
import numpy as np
import pydicom
from pydicom.uid import ExplicitVRLittleEndian
import nibabel as nib

from app.core.logging import get_logger
from app.core.config import get_settings

logger = get_logger(__name__)
settings = get_settings()

# DICOM tag constants (hex → keyword mapping for QIDO-RS JSON)
STUDY_TAGS = {
    "0020000D": "study_instance_uid",    # StudyInstanceUID
    "00100010": "patient_name",          # PatientName
    "00100020": "patient_id",            # PatientID
    "00080020": "study_date",            # StudyDate
    "00081030": "study_description",     # StudyDescription
    "00080060": "modality",              # ModalitiesInStudy
    "00080050": "accession_number",      # AccessionNumber
    "00201206": "number_of_series",      # NumberOfStudyRelatedSeries
    "00201208": "number_of_instances",   # NumberOfStudyRelatedInstances
}

SERIES_TAGS = {
    "0020000E": "series_instance_uid",   # SeriesInstanceUID
    "00200011": "series_number",         # SeriesNumber
    "00080060": "modality",              # Modality
    "0008103E": "series_description",    # SeriesDescription
    "00180015": "body_part_examined",    # BodyPartExamined
    "00201209": "number_of_instances",   # NumberOfSeriesRelatedInstances
}


def _extract_dicom_value(tag_data: dict) -> Optional[str]:
    """Extract value from DICOM JSON format {vr, Value: [...]}."""
    if not tag_data:
        return None
    value = tag_data.get("Value")
    if not value or len(value) == 0:
        return None
    v = value[0]
    if isinstance(v, dict):
        # PersonName: {"Alphabetic": "DOE^JOHN"}
        return v.get("Alphabetic", str(v))
    return str(v)


def _parse_qido_results(results: list[dict], tag_map: dict) -> list[dict]:
    """Parse QIDO-RS JSON array into flat dicts."""
    parsed = []
    for item in results:
        row = {}
        for tag_hex, field_name in tag_map.items():
            tag_upper = tag_hex.upper()
            tag_data = item.get(tag_upper) or item.get(tag_hex)
            row[field_name] = _extract_dicom_value(tag_data)
        parsed.append(row)
    return parsed


class DICOMwebService:
    """Bridge service for DICOMweb PACS integration."""

    def __init__(self, db=None, storage_service=None):
        self.db = db
        self.storage_service = storage_service
        self._import_jobs: dict[str, dict] = {}  # In-memory job tracking

    # ─── PACS Connection CRUD ───

    def _connections_ref(self):
        return self.db.collection("pacs_connections")

    async def save_connection(self, data: dict) -> dict:
        conn_id = str(uuid.uuid4())
        doc = {
            "id": conn_id,
            "name": data["name"],
            "base_url": data["base_url"].rstrip("/"),
            "auth_type": data.get("auth_type", "none"),
            "username": data.get("username"),
            "password": data.get("password"),
            "bearer_token": data.get("bearer_token"),
            "verify_ssl": data.get("verify_ssl", True),
            "created_at": datetime.utcnow().isoformat(),
            "last_tested": None,
            "is_reachable": None,
        }
        self._connections_ref().document(conn_id).set(doc)
        return doc

    async def list_connections(self) -> list[dict]:
        docs = self._connections_ref().stream()
        return [d.to_dict() for d in docs]

    async def get_connection(self, connection_id: str) -> Optional[dict]:
        doc = self._connections_ref().document(connection_id).get()
        return doc.to_dict() if doc.exists else None

    async def delete_connection(self, connection_id: str) -> bool:
        self._connections_ref().document(connection_id).delete()
        return True

    def _get_http_client(self, conn: dict) -> httpx.AsyncClient:
        """Build authenticated httpx client for a PACS connection."""
        headers = {"Accept": "application/dicom+json"}
        auth = None

        if conn.get("auth_type") == "basic" and conn.get("username"):
            auth = httpx.BasicAuth(conn["username"], conn.get("password", ""))
        elif conn.get("auth_type") == "bearer" and conn.get("bearer_token"):
            headers["Authorization"] = f"Bearer {conn['bearer_token']}"

        return httpx.AsyncClient(
            base_url=conn["base_url"],
            headers=headers,
            auth=auth,
            verify=conn.get("verify_ssl", True),
            timeout=httpx.Timeout(60.0, connect=10.0),
        )

    # ─── QIDO-RS Search ───

    async def test_connection(self, connection_id: str) -> dict:
        """Test PACS connectivity via a minimal QIDO-RS query."""
        conn = await self.get_connection(connection_id)
        if not conn:
            return {"success": False, "message": "Connection not found"}

        try:
            async with self._get_http_client(conn) as client:
                resp = await client.get("/studies", params={"limit": 1})
                resp.raise_for_status()

            # Update status
            self._connections_ref().document(connection_id).update({
                "last_tested": datetime.utcnow().isoformat(),
                "is_reachable": True,
            })
            return {"success": True, "message": "Connection successful"}
        except Exception as e:
            self._connections_ref().document(connection_id).update({
                "last_tested": datetime.utcnow().isoformat(),
                "is_reachable": False,
            })
            return {"success": False, "message": str(e)}

    async def search_studies(self, connection_id: str, params: dict) -> list[dict]:
        """QIDO-RS study-level search."""
        conn = await self.get_connection(connection_id)
        if not conn:
            raise ValueError("Connection not found")

        query = {}
        if params.get("patient_name"):
            query["PatientName"] = f"*{params['patient_name']}*"
        if params.get("patient_id"):
            query["PatientID"] = params["patient_id"]
        if params.get("study_date"):
            query["StudyDate"] = params["study_date"]
        if params.get("modality"):
            query["ModalitiesInStudy"] = params["modality"]
        if params.get("accession_number"):
            query["AccessionNumber"] = params["accession_number"]
        query["limit"] = params.get("limit", 50)
        query["includefield"] = "all"

        async with self._get_http_client(conn) as client:
            resp = await client.get("/studies", params=query)
            resp.raise_for_status()
            results = resp.json()

        return _parse_qido_results(results, STUDY_TAGS)

    async def search_series(self, connection_id: str, study_uid: str) -> list[dict]:
        """QIDO-RS series-level search within a study."""
        conn = await self.get_connection(connection_id)
        if not conn:
            raise ValueError("Connection not found")

        async with self._get_http_client(conn) as client:
            resp = await client.get(
                f"/studies/{study_uid}/series",
                params={"includefield": "all"}
            )
            resp.raise_for_status()
            results = resp.json()

        return _parse_qido_results(results, SERIES_TAGS)

    # ─── WADO-RS Import ───

    async def start_import(
        self,
        connection_id: str,
        study_uid: str,
        series_uid: str,
        patient_id: str,
        study_description: Optional[str] = None,
    ) -> str:
        """Start async import of a DICOM series from PACS."""
        job_id = str(uuid.uuid4())
        self._import_jobs[job_id] = {
            "job_id": job_id,
            "status": "pending",
            "progress_percent": 0,
            "error_message": None,
            "instances_downloaded": 0,
            "instances_total": None,
            "study_id": None,
            "series_id": None,
            "instance_id": None,
            "created_at": datetime.utcnow().isoformat(),
            "completed_at": None,
        }

        # Launch background task
        asyncio.create_task(self._run_import(
            job_id, connection_id, study_uid, series_uid, patient_id, study_description
        ))

        return job_id

    def get_import_status(self, job_id: str) -> Optional[dict]:
        return self._import_jobs.get(job_id)

    async def _run_import(
        self,
        job_id: str,
        connection_id: str,
        study_uid: str,
        series_uid: str,
        patient_id: str,
        study_description: Optional[str],
    ):
        """Background: download DICOM series, convert to NIfTI, store in GCS."""
        job = self._import_jobs[job_id]
        try:
            conn = await self.get_connection(connection_id)
            if not conn:
                raise ValueError("PACS connection not found")

            # Step 1: Download DICOM instances via WADO-RS
            job["status"] = "downloading"
            job["progress_percent"] = 10

            async with self._get_http_client(conn) as client:
                # Request multipart DICOM
                headers = {"Accept": "multipart/related; type=\"application/dicom\""}
                resp = await client.get(
                    f"/studies/{study_uid}/series/{series_uid}",
                    headers=headers,
                    timeout=httpx.Timeout(300.0, connect=10.0),
                )
                resp.raise_for_status()

            # Parse multipart response to extract DICOM instances
            datasets = self._parse_multipart_dicom(resp)
            job["instances_total"] = len(datasets)
            job["instances_downloaded"] = len(datasets)
            job["progress_percent"] = 40

            if len(datasets) == 0:
                raise ValueError("No DICOM instances received from PACS")

            logger.info(f"Downloaded {len(datasets)} DICOM instances", extra={
                "study_uid": study_uid, "series_uid": series_uid
            })

            # Step 2: Convert to NIfTI
            job["status"] = "converting"
            job["progress_percent"] = 50

            nifti_bytes = self._convert_dicom_to_nifti(datasets)
            job["progress_percent"] = 70

            # Step 3: Upload NIfTI to GCS
            job["status"] = "uploading"

            new_study_id = str(uuid.uuid4())
            new_series_id = str(uuid.uuid4())
            new_instance_id = str(uuid.uuid4())

            gcs_path = f"patients/{patient_id}/studies/{new_study_id}/series/{new_series_id}/{new_instance_id}.nii.gz"

            bucket_name = settings.GCS_BUCKET_NAME
            blob = self.storage_service.gcs_bucket.blob(gcs_path) if hasattr(self.storage_service, 'gcs_bucket') else None
            if blob:
                blob.upload_from_string(nifti_bytes, content_type="application/gzip")
            job["progress_percent"] = 85

            # Step 4: Register in Firestore
            job["status"] = "registering"

            ds0 = datasets[0]
            desc = study_description or getattr(ds0, 'StudyDescription', 'PACS Import')
            modality = getattr(ds0, 'Modality', 'MR')
            study_date = getattr(ds0, 'StudyDate', '')

            # Create study document
            study_doc = {
                "id": new_study_id,
                "patient_id": patient_id,
                "modality": modality,
                "study_date": study_date,
                "study_description": desc,
                "accession_number": getattr(ds0, 'AccessionNumber', ''),
                "status": "available",
                "source": "dicomweb_import",
                "dicom_study_uid": study_uid,
                "created_at": datetime.utcnow().isoformat(),
            }
            self.db.collection("studies").document(new_study_id).set(study_doc)

            # Create series document
            series_doc = {
                "id": new_series_id,
                "study_id": new_study_id,
                "series_number": getattr(ds0, 'SeriesNumber', 1),
                "modality": modality,
                "series_description": getattr(ds0, 'SeriesDescription', ''),
                "body_part_examined": getattr(ds0, 'BodyPartExamined', 'BRAIN'),
                "created_at": datetime.utcnow().isoformat(),
            }
            self.db.collection("studies").document(new_study_id).collection("series").document(new_series_id).set(series_doc)

            # Create instance document
            original_filename = f"{series_uid}.nii.gz"
            instance_doc = {
                "id": new_instance_id,
                "series_id": new_series_id,
                "sop_instance_uid": str(uuid.uuid4()),
                "gcs_object_name": gcs_path,
                "original_filename": original_filename,
                "content_type": "application/x-nifti-compressed",
                "file_size_bytes": len(nifti_bytes),
                "dicom_series_uid": series_uid,
                "dicom_study_uid": study_uid,
                "source": "dicomweb_import",
                "created_at": datetime.utcnow().isoformat(),
            }
            self.db.collection("studies").document(new_study_id).collection("series").document(new_series_id).collection("instances").document(new_instance_id).set(instance_doc)

            job["status"] = "completed"
            job["progress_percent"] = 100
            job["study_id"] = new_study_id
            job["series_id"] = new_series_id
            job["instance_id"] = new_instance_id
            job["completed_at"] = datetime.utcnow().isoformat()

            logger.info("DICOMweb import completed", extra={
                "job_id": job_id,
                "study_id": new_study_id,
                "gcs_path": gcs_path,
            })

        except Exception as e:
            job["status"] = "failed"
            job["error_message"] = str(e)
            job["completed_at"] = datetime.utcnow().isoformat()
            logger.error("DICOMweb import failed", extra={
                "job_id": job_id, "error": str(e)
            })

    def _parse_multipart_dicom(self, response: httpx.Response) -> list[pydicom.Dataset]:
        """Parse multipart DICOM response into pydicom Datasets."""
        content_type = response.headers.get("content-type", "")
        datasets = []

        if "multipart" in content_type:
            # Extract boundary
            boundary = None
            for part in content_type.split(";"):
                part = part.strip()
                if part.startswith("boundary="):
                    boundary = part.split("=", 1)[1].strip('"')
                    break

            if boundary:
                parts = response.content.split(f"--{boundary}".encode())
                for part in parts:
                    # Skip empty parts and closing boundary
                    if len(part) < 100 or part.strip() == b"--":
                        continue
                    # Find the double newline separating headers from body
                    sep_idx = part.find(b"\r\n\r\n")
                    if sep_idx == -1:
                        sep_idx = part.find(b"\n\n")
                    if sep_idx == -1:
                        continue
                    dicom_bytes = part[sep_idx + 4:] if b"\r\n\r\n" in part[:sep_idx + 4] else part[sep_idx + 2:]
                    try:
                        ds = pydicom.dcmread(io.BytesIO(dicom_bytes))
                        datasets.append(ds)
                    except Exception:
                        continue
        else:
            # Single DICOM instance
            try:
                ds = pydicom.dcmread(io.BytesIO(response.content))
                datasets.append(ds)
            except Exception:
                pass

        return datasets

    def _convert_dicom_to_nifti(self, datasets: list[pydicom.Dataset]) -> bytes:
        """Convert sorted DICOM instances to NIfTI .nii.gz bytes."""
        # Sort instances by InstanceNumber or SliceLocation
        datasets = self._sort_instances(datasets)

        # Check for multi-frame
        if len(datasets) == 1 and hasattr(datasets[0], 'NumberOfFrames') and int(datasets[0].NumberOfFrames) > 1:
            volume = datasets[0].pixel_array.astype(np.float32)
        else:
            # Stack single-frame instances
            slices = []
            for ds in datasets:
                arr = ds.pixel_array.astype(np.float32)
                # Apply rescale
                slope = float(getattr(ds, 'RescaleSlope', 1))
                intercept = float(getattr(ds, 'RescaleIntercept', 0))
                if slope != 1 or intercept != 0:
                    arr = arr * slope + intercept
                slices.append(arr)
            volume = np.stack(slices, axis=-1)  # (rows, cols, slices)

        # Build affine matrix
        affine = self._build_affine(datasets)

        # Create NIfTI
        nifti_img = nib.Nifti1Image(volume, affine)

        # Serialize to .nii.gz
        with tempfile.NamedTemporaryFile(suffix='.nii.gz', delete=False) as tmp:
            tmp_path = tmp.name
        try:
            nib.save(nifti_img, tmp_path)
            with open(tmp_path, 'rb') as f:
                return f.read()
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def _sort_instances(self, datasets: list[pydicom.Dataset]) -> list[pydicom.Dataset]:
        """Sort DICOM instances by spatial position."""
        def sort_key(ds):
            # Primary: InstanceNumber
            inst_num = getattr(ds, 'InstanceNumber', None)
            if inst_num is not None:
                return (0, int(inst_num))
            # Fallback: SliceLocation
            loc = getattr(ds, 'SliceLocation', None)
            if loc is not None:
                return (1, float(loc))
            # Fallback: ImagePositionPatient Z
            ipp = getattr(ds, 'ImagePositionPatient', None)
            if ipp:
                return (2, float(ipp[2]))
            return (3, 0)

        return sorted(datasets, key=sort_key)

    def _build_affine(self, datasets: list[pydicom.Dataset]) -> np.ndarray:
        """Build 4x4 NIfTI affine from DICOM spatial tags."""
        ds0 = datasets[0]

        # Get orientation and position
        iop = getattr(ds0, 'ImageOrientationPatient', None)
        ipp = getattr(ds0, 'ImagePositionPatient', None)
        ps = getattr(ds0, 'PixelSpacing', None)

        if not iop or not ipp or not ps:
            # No spatial info — use identity
            logger.warning("Missing DICOM spatial tags, using identity affine")
            return np.eye(4)

        iop = np.array([float(x) for x in iop])
        ipp0 = np.array([float(x) for x in ipp])
        ps = np.array([float(x) for x in ps])

        row_cosine = iop[:3]
        col_cosine = iop[3:]

        # Compute slice direction
        if len(datasets) > 1:
            ipp1 = np.array([float(x) for x in datasets[1].ImagePositionPatient])
            slice_vec = ipp1 - ipp0
            slice_spacing = np.linalg.norm(slice_vec)
            if slice_spacing > 0:
                slice_cosine = slice_vec / slice_spacing
            else:
                slice_cosine = np.cross(row_cosine, col_cosine)
                slice_spacing = float(getattr(ds0, 'SliceThickness', 1.0))
        else:
            slice_cosine = np.cross(row_cosine, col_cosine)
            slice_spacing = float(getattr(ds0, 'SliceThickness', 1.0))

        # Build affine
        affine = np.eye(4)
        affine[:3, 0] = row_cosine * ps[1]        # column direction
        affine[:3, 1] = col_cosine * ps[0]        # row direction
        affine[:3, 2] = slice_cosine * slice_spacing
        affine[:3, 3] = ipp0

        return affine
