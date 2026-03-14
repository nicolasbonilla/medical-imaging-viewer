"""
Clinical Tool Runner Service.

Orchestrates calls to validated clinical neuroimaging tool containers
(LST-AI, SynthSeg, mindGlide) running as Docker sidecars. Manages async task
lifecycle, NIfTI I/O on shared volumes, and result conversion to the
application's segmentation storage format.

References:
    - LST-AI: Wiltgen et al., NeuroImage: Clinical 2024, 42, 103611
    - SynthSeg: Billot et al., 2023 (FreeSurfer 7.4+)
    - mindGlide: MS-PINPOINT, Nature Communications 2025

@module services.tool_runner_service
"""

import uuid
import time
import os
import asyncio
from pathlib import Path
from typing import Dict, Optional, Tuple
from datetime import datetime, timezone

import numpy as np
import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.exceptions import SegmentationException, NotFoundException
from app.core.interfaces.ai_interface import (
    ToolTask,
    ToolTaskStatus,
    ClinicalToolInfo,
)

logger = get_logger(__name__)
settings = get_settings()


class ToolRunnerService:
    """
    Orchestrates validated clinical tool containers (LST-AI, SynthSeg, mindGlide).

    Architecture:
        1. Downloads NIfTI from GCS to a shared Docker volume
        2. Sends HTTP request to sidecar container with file paths
        3. Polls sidecar for completion
        4. Reads output NIfTI mask from shared volume
        5. Converts to app's segmentation format and stores in GCS/Firestore
    """

    def __init__(self, storage_service=None):
        self._tasks: Dict[str, ToolTask] = {}
        self._storage = storage_service
        self._shared_volume = Path(settings.CLINICAL_TOOLS_SHARED_VOLUME)
        logger.info("[ToolRunner] Service initialized")

    def _ensure_shared_volume(self):
        """Create shared volume directory if it doesn't exist."""
        self._shared_volume.mkdir(parents=True, exist_ok=True)

    def is_lstai_available(self) -> bool:
        """Check if LST-AI sidecar is configured."""
        return bool(settings.LSTAI_ENABLED and settings.LSTAI_ENDPOINT)

    def is_synthseg_available(self) -> bool:
        """Check if SynthSeg sidecar is configured."""
        return bool(settings.SYNTHSEG_ENABLED and settings.SYNTHSEG_ENDPOINT)

    def is_mindglide_available(self) -> bool:
        """Check if mindGlide sidecar is configured."""
        return bool(settings.MINDGLIDE_ENABLED and settings.MINDGLIDE_ENDPOINT)

    def is_tool_available(self, tool: str) -> bool:
        """Check if a clinical tool is available by ID."""
        checkers = {
            "lst-ai": self.is_lstai_available,
            "synthseg": self.is_synthseg_available,
            "mindglide": self.is_mindglide_available,
        }
        return checkers.get(tool, lambda: False)()

    async def check_sidecar_health(self, tool: str) -> bool:
        """Ping a sidecar's /health endpoint."""
        endpoints = {
            "lst-ai": settings.LSTAI_ENDPOINT,
            "synthseg": settings.SYNTHSEG_ENDPOINT,
            "mindglide": settings.MINDGLIDE_ENDPOINT,
        }
        endpoint = endpoints.get(tool, "")
        if not endpoint:
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{endpoint}/health")
                return resp.status_code == 200
        except Exception:
            return False

    def list_tools(self) -> list:
        """List available clinical tools with metadata."""
        tools = [
            ClinicalToolInfo(
                id="lst-ai",
                name="LST-AI",
                version="1.0.3",
                available=self.is_lstai_available(),
                description=(
                    "Lesion Segmentation Tool - AI. Automated MS lesion segmentation "
                    "using a 3x 3D U-Net ensemble with test-time augmentation. "
                    "Includes native MAGNIMS 2021 zone classification (PV, JC, IT, DWM)."
                ),
                citation="Wiltgen T, et al. LST-AI: a deep learning ensemble for accurate MS lesion segmentation. NeuroImage: Clinical 2024;42:103611.",
                license="Open-source research",
                fda_status="research_only",
                required_inputs=["T1w", "FLAIR"],
            ),
            ClinicalToolInfo(
                id="synthseg",
                name="SynthSeg",
                version="2.0",
                available=self.is_synthseg_available(),
                description=(
                    "Contrast-agnostic brain parcellation of 30+ structures "
                    "(hippocampus, ventricles, cortex, thalamus, etc.). "
                    "Works on any MRI contrast. Part of FreeSurfer 7.4+."
                ),
                citation="Billot B, et al. SynthSeg: Segmentation of brain MRI scans of any contrast and resolution without retraining. Medical Image Analysis 2023;83:102789.",
                license="FreeSurfer License (research free, commercial license required)",
                fda_status="research_only",
                required_inputs=["Any MRI"],
            ),
            ClinicalToolInfo(
                id="mindglide",
                name="mindGlide (MS-PINPOINT)",
                version="1.0.0",
                available=self.is_mindglide_available(),
                description=(
                    "SOTA MS lesion + brain structure segmentation using DynUNet (MONAI), "
                    "trained on 23,000+ scans. 60% better than SAMSEG, 20% better than "
                    "WMH-SynthSeg. Segments 20 brain structures + lesions."
                ),
                citation=(
                    "MS-PINPOINT. mindGlide: SOTA open-source MS segmentation. "
                    "Nature Communications 2025."
                ),
                license="Open-source research",
                fda_status="research_only",
                required_inputs=["Any MRI (contrast-agnostic)"],
            ),
        ]
        return [t.model_dump() for t in tools]

    async def run_lstai(
        self,
        t1_file_id: str,
        flair_file_id: str,
        patient_id: Optional[str] = None,
        study_id: Optional[str] = None,
    ) -> str:
        """
        Submit an LST-AI lesion segmentation task.

        Downloads T1 and FLAIR NIfTI files from GCS to the shared volume,
        then sends a request to the LST-AI sidecar container.

        Returns:
            task_id for status polling
        """
        task_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        if not self.is_lstai_available():
            self._tasks[task_id] = ToolTask(
                task_id=task_id,
                tool="lst-ai",
                status=ToolTaskStatus.FAILED,
                error=(
                    "LST-AI is not configured. Set LSTAI_ENABLED=true and "
                    "LSTAI_ENDPOINT to the sidecar URL to enable this feature."
                ),
                validation_source="lst-ai-v1.0.3",
                created_at=now,
            )
            return task_id

        self._tasks[task_id] = ToolTask(
            task_id=task_id,
            tool="lst-ai",
            status=ToolTaskStatus.PENDING,
            progress=0.0,
            validation_source="lst-ai-v1.0.3",
            created_at=now,
        )

        # Run in background
        asyncio.create_task(
            self._execute_lstai(task_id, t1_file_id, flair_file_id, patient_id, study_id)
        )

        return task_id

    async def _execute_lstai(
        self,
        task_id: str,
        t1_file_id: str,
        flair_file_id: str,
        patient_id: Optional[str],
        study_id: Optional[str],
    ):
        """Background execution of LST-AI segmentation."""
        start_time = time.time()
        task = self._tasks[task_id]
        work_dir = self._shared_volume / task_id

        try:
            # Phase 1: Download NIfTI files from GCS
            task.status = ToolTaskStatus.DOWNLOADING
            task.progress = 5.0

            self._ensure_shared_volume()
            work_dir.mkdir(parents=True, exist_ok=True)

            t1_path = await self._download_to_shared(t1_file_id, work_dir, "t1.nii.gz")
            task.progress = 15.0

            flair_path = await self._download_to_shared(flair_file_id, work_dir, "flair.nii.gz")
            task.progress = 25.0

            # Phase 2: Call LST-AI sidecar
            task.status = ToolTaskStatus.PROCESSING
            task.progress = 30.0

            output_dir = work_dir / "output"
            output_dir.mkdir(exist_ok=True)

            async with httpx.AsyncClient(
                timeout=httpx.Timeout(settings.LSTAI_TIMEOUT_SECONDS, connect=10.0)
            ) as client:
                resp = await client.post(
                    f"{settings.LSTAI_ENDPOINT}/segment",
                    json={
                        "t1_path": str(t1_path),
                        "flair_path": str(flair_path),
                        "output_dir": str(output_dir),
                    },
                )
                resp.raise_for_status()
                result = resp.json()

            task.progress = 80.0

            # Phase 3: Read output and store as segmentation
            task.status = ToolTaskStatus.STORING
            task.progress = 85.0

            lesion_mask_path = output_dir / result.get("lesion_mask", "lesion_mask.nii.gz")
            lesion_types_path = output_dir / result.get("lesion_types", "lesion_types.nii.gz")

            seg_id = await self._store_nifti_as_segmentation(
                mask_path=lesion_mask_path,
                types_path=lesion_types_path if lesion_types_path.exists() else None,
                file_id=flair_file_id,
                description="LST-AI automated MS lesion segmentation",
                validation_source="lst-ai-v1.0.3",
                patient_id=patient_id,
                study_id=study_id,
            )

            elapsed_ms = int((time.time() - start_time) * 1000)

            task.status = ToolTaskStatus.COMPLETED
            task.progress = 100.0
            task.segmentation_id = seg_id
            task.processing_time_ms = elapsed_ms

            logger.info(
                f"[ToolRunner] LST-AI completed in {elapsed_ms}ms",
                extra={"task_id": task_id, "segmentation_id": seg_id},
            )

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            task.status = ToolTaskStatus.FAILED
            task.error = str(e)
            task.processing_time_ms = elapsed_ms
            logger.error(f"[ToolRunner] LST-AI failed: {e}", extra={"task_id": task_id})

        finally:
            # Cleanup working directory
            self._cleanup_work_dir(work_dir)

    async def run_synthseg(
        self,
        file_id: str,
        patient_id: Optional[str] = None,
        study_id: Optional[str] = None,
    ) -> str:
        """
        Submit a SynthSeg brain parcellation task.

        Returns:
            task_id for status polling
        """
        task_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        if not self.is_synthseg_available():
            self._tasks[task_id] = ToolTask(
                task_id=task_id,
                tool="synthseg",
                status=ToolTaskStatus.FAILED,
                error=(
                    "SynthSeg is not configured. Set SYNTHSEG_ENABLED=true and "
                    "SYNTHSEG_ENDPOINT to the sidecar URL to enable this feature."
                ),
                validation_source="synthseg-v2.0",
                created_at=now,
            )
            return task_id

        self._tasks[task_id] = ToolTask(
            task_id=task_id,
            tool="synthseg",
            status=ToolTaskStatus.PENDING,
            progress=0.0,
            validation_source="synthseg-v2.0",
            created_at=now,
        )

        asyncio.create_task(
            self._execute_synthseg(task_id, file_id, patient_id, study_id)
        )

        return task_id

    async def _execute_synthseg(
        self,
        task_id: str,
        file_id: str,
        patient_id: Optional[str],
        study_id: Optional[str],
    ):
        """Background execution of SynthSeg parcellation."""
        start_time = time.time()
        task = self._tasks[task_id]
        work_dir = self._shared_volume / task_id

        try:
            # Phase 1: Download NIfTI from GCS
            task.status = ToolTaskStatus.DOWNLOADING
            task.progress = 10.0

            self._ensure_shared_volume()
            work_dir.mkdir(parents=True, exist_ok=True)

            input_path = await self._download_to_shared(file_id, work_dir, "input.nii.gz")
            task.progress = 25.0

            # Phase 2: Call SynthSeg sidecar
            task.status = ToolTaskStatus.PROCESSING
            task.progress = 30.0

            output_dir = work_dir / "output"
            output_dir.mkdir(exist_ok=True)

            async with httpx.AsyncClient(
                timeout=httpx.Timeout(settings.SYNTHSEG_TIMEOUT_SECONDS, connect=10.0)
            ) as client:
                resp = await client.post(
                    f"{settings.SYNTHSEG_ENDPOINT}/parcellate",
                    json={
                        "input_path": str(input_path),
                        "output_dir": str(output_dir),
                    },
                )
                resp.raise_for_status()
                result = resp.json()

            task.progress = 80.0

            # Phase 3: Store result
            task.status = ToolTaskStatus.STORING
            task.progress = 85.0

            parcellation_path = output_dir / result.get("parcellation", "synthseg.nii.gz")

            seg_id = await self._store_nifti_as_segmentation(
                mask_path=parcellation_path,
                file_id=file_id,
                description="SynthSeg brain parcellation (30+ structures)",
                validation_source="synthseg-v2.0",
                patient_id=patient_id,
                study_id=study_id,
            )

            # Store volumes CSV if available
            volumes_csv = output_dir / result.get("volumes", "volumes.csv")
            if volumes_csv.exists():
                await self._store_volumes_csv(seg_id, volumes_csv)

            elapsed_ms = int((time.time() - start_time) * 1000)

            task.status = ToolTaskStatus.COMPLETED
            task.progress = 100.0
            task.segmentation_id = seg_id
            task.processing_time_ms = elapsed_ms

            logger.info(
                f"[ToolRunner] SynthSeg completed in {elapsed_ms}ms",
                extra={"task_id": task_id, "segmentation_id": seg_id},
            )

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            task.status = ToolTaskStatus.FAILED
            task.error = str(e)
            task.processing_time_ms = elapsed_ms
            logger.error(f"[ToolRunner] SynthSeg failed: {e}", extra={"task_id": task_id})

        finally:
            self._cleanup_work_dir(work_dir)

    async def run_mindglide(
        self,
        file_id: str,
        patient_id: Optional[str] = None,
        study_id: Optional[str] = None,
    ) -> str:
        """
        Submit a mindGlide MS lesion + brain structure segmentation task.

        Reference: MS-PINPOINT, Nature Communications 2025.

        Returns:
            task_id for status polling
        """
        task_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        if not self.is_mindglide_available():
            self._tasks[task_id] = ToolTask(
                task_id=task_id,
                tool="mindglide",
                status=ToolTaskStatus.FAILED,
                error=(
                    "mindGlide is not configured. Set MINDGLIDE_ENABLED=true and "
                    "MINDGLIDE_ENDPOINT to the sidecar URL to enable this feature."
                ),
                validation_source="mindglide-v1.0",
                created_at=now,
            )
            return task_id

        self._tasks[task_id] = ToolTask(
            task_id=task_id,
            tool="mindglide",
            status=ToolTaskStatus.PENDING,
            progress=0.0,
            validation_source="mindglide-v1.0",
            created_at=now,
        )

        asyncio.create_task(
            self._execute_mindglide(task_id, file_id, patient_id, study_id)
        )

        return task_id

    async def _execute_mindglide(
        self,
        task_id: str,
        file_id: str,
        patient_id: Optional[str],
        study_id: Optional[str],
    ):
        """Background execution of mindGlide segmentation."""
        start_time = time.time()
        task = self._tasks[task_id]
        work_dir = self._shared_volume / task_id

        try:
            # Phase 1: Download NIfTI from GCS
            task.status = ToolTaskStatus.DOWNLOADING
            task.progress = 10.0

            self._ensure_shared_volume()
            work_dir.mkdir(parents=True, exist_ok=True)

            input_path = await self._download_to_shared(file_id, work_dir, "input.nii.gz")
            task.progress = 25.0

            # Phase 2: Call mindGlide sidecar
            task.status = ToolTaskStatus.PROCESSING
            task.progress = 30.0

            output_dir = work_dir / "output"
            output_dir.mkdir(exist_ok=True)

            async with httpx.AsyncClient(
                timeout=httpx.Timeout(settings.MINDGLIDE_TIMEOUT_SECONDS, connect=10.0)
            ) as client:
                resp = await client.post(
                    f"{settings.MINDGLIDE_ENDPOINT}/segment",
                    json={
                        "input_path": str(input_path),
                        "output_dir": str(output_dir),
                    },
                )
                resp.raise_for_status()
                result = resp.json()

            task.progress = 80.0

            # Phase 3: Store lesion mask as segmentation
            task.status = ToolTaskStatus.STORING
            task.progress = 85.0

            lesion_mask_path = output_dir / result.get("lesion_mask", "lesion_mask.nii.gz")

            seg_id = await self._store_nifti_as_segmentation(
                mask_path=lesion_mask_path,
                file_id=file_id,
                description="mindGlide MS lesion + structure segmentation (Nature Comms 2025)",
                validation_source="mindglide-v1.0",
                patient_id=patient_id,
                study_id=study_id,
            )

            # Store brain structure mask separately if available
            structure_mask_path = output_dir / result.get("structure_mask", "structure_mask.nii.gz")
            if structure_mask_path.exists():
                await self._store_nifti_as_segmentation(
                    mask_path=structure_mask_path,
                    file_id=file_id,
                    description="mindGlide brain structure parcellation",
                    validation_source="mindglide-v1.0-structures",
                    patient_id=patient_id,
                    study_id=study_id,
                )

            elapsed_ms = int((time.time() - start_time) * 1000)

            task.status = ToolTaskStatus.COMPLETED
            task.progress = 100.0
            task.segmentation_id = seg_id
            task.processing_time_ms = elapsed_ms

            logger.info(
                f"[ToolRunner] mindGlide completed in {elapsed_ms}ms",
                extra={"task_id": task_id, "segmentation_id": seg_id},
            )

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            task.status = ToolTaskStatus.FAILED
            task.error = str(e)
            task.processing_time_ms = elapsed_ms
            logger.error(f"[ToolRunner] mindGlide failed: {e}", extra={"task_id": task_id})

        finally:
            self._cleanup_work_dir(work_dir)

    async def get_task_status(self, task_id: str) -> ToolTask:
        """Get the status of an async clinical tool task."""
        if task_id in self._tasks:
            return self._tasks[task_id]

        return ToolTask(
            task_id=task_id,
            tool="unknown",
            status=ToolTaskStatus.FAILED,
            error="Task not found",
            validation_source="unknown",
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    # =========================================================================
    # Private helpers
    # =========================================================================

    async def _download_to_shared(
        self, file_id: str, work_dir: Path, filename: str
    ) -> Path:
        """Download a GCS file to the shared volume work directory."""
        if self._storage is None:
            raise SegmentationException(
                message="Storage service not available",
                error_code="TOOL_RUNNER_NO_STORAGE",
            )

        file_data = await self._storage.download(file_id)
        output_path = work_dir / filename
        output_path.write_bytes(file_data)

        logger.debug(
            f"[ToolRunner] Downloaded {file_id} to {output_path} ({len(file_data)} bytes)"
        )
        return output_path

    async def _store_nifti_as_segmentation(
        self,
        mask_path: Path,
        file_id: str,
        description: str,
        validation_source: str,
        patient_id: Optional[str] = None,
        study_id: Optional[str] = None,
        types_path: Optional[Path] = None,
    ) -> str:
        """
        Read a NIfTI mask from disk and store it as a segmentation.

        Converts the NIfTI to the app's binary protocol format:
        12-byte header (uint32 depth, height, width) + uint8 voxel data.
        Uploads to GCS and creates Firestore metadata.
        """
        import nibabel as nib

        # Read primary mask
        img = nib.load(str(mask_path))
        mask_data = np.asarray(img.dataobj).astype(np.uint8)

        # If types mask exists (LST-AI MAGNIMS zones), use it instead
        if types_path is not None and types_path.exists():
            types_img = nib.load(str(types_path))
            mask_data = np.asarray(types_img.dataobj).astype(np.uint8)

        # Ensure 3D
        if mask_data.ndim == 4:
            mask_data = mask_data[:, :, :, 0]

        # NIfTI convention: (x, y, z) → app convention: (depth, height, width) = (z, y, x)
        # Transpose to match the app's (slices, rows, columns) format
        mask_data = np.transpose(mask_data, (2, 1, 0))

        depth, height, width = mask_data.shape

        # Build 12-byte header + uint8 data (app's binary protocol)
        import struct
        header = struct.pack('<III', depth, height, width)
        binary_data = header + mask_data.tobytes()

        # Generate segmentation ID and GCS path
        seg_id = str(uuid.uuid4())
        gcs_path = f"segmentations/clinical-tools/{seg_id}/mask.bin"

        # Upload to GCS
        if self._storage is not None:
            await self._storage.upload(
                object_name=gcs_path,
                data=binary_data,
                content_type="application/octet-stream",
            )

        # Store metadata in Firestore
        try:
            from app.core.firebase import get_firestore_client
            db = get_firestore_client()

            doc_data = {
                "id": seg_id,
                "file_id": file_id,
                "patient_id": patient_id,
                "study_id": study_id,
                "name": description,
                "description": description,
                "segmentation_type": "automatic",
                "status": "completed",
                "image_shape": [height, width, depth],
                "gcs_path": gcs_path,
                "validation_source": validation_source,
                "validation_citation": self._get_citation(validation_source),
                "created_at": datetime.now(timezone.utc),
                "modified_at": datetime.now(timezone.utc),
                "created_by": "system",
                "created_by_name": validation_source,
            }

            # Store in flat segmentation collection for easy lookup
            db.collection("segmentations").document(seg_id).set(doc_data)

            logger.info(
                f"[ToolRunner] Stored segmentation {seg_id}",
                extra={"validation_source": validation_source, "shape": [depth, height, width]},
            )

        except Exception as e:
            logger.error(f"[ToolRunner] Failed to store Firestore metadata: {e}")

        return seg_id

    async def _store_volumes_csv(self, seg_id: str, csv_path: Path):
        """Store SynthSeg volumes CSV alongside the segmentation in GCS."""
        if self._storage is None:
            return
        try:
            csv_data = csv_path.read_bytes()
            gcs_path = f"segmentations/clinical-tools/{seg_id}/volumes.csv"
            await self._storage.upload(
                object_name=gcs_path,
                data=csv_data,
                content_type="text/csv",
            )
        except Exception as e:
            logger.error(f"[ToolRunner] Failed to store volumes CSV: {e}")

    def _cleanup_work_dir(self, work_dir: Path):
        """Remove temporary working directory."""
        try:
            import shutil
            if work_dir.exists():
                shutil.rmtree(work_dir)
        except Exception as e:
            logger.warning(f"[ToolRunner] Failed to cleanup {work_dir}: {e}")

    @staticmethod
    def _get_citation(validation_source: str) -> str:
        """Get the academic citation for a validation source."""
        citations = {
            "lst-ai-v1.0.3": (
                "Wiltgen T, McGinnis J, Schlaeger S, et al. "
                "LST-AI: a deep learning ensemble for accurate MS lesion segmentation. "
                "NeuroImage: Clinical 2024;42:103611."
            ),
            "synthseg-v2.0": (
                "Billot B, Greve DN, Puonti O, et al. "
                "SynthSeg: Segmentation of brain MRI scans of any contrast "
                "and resolution without retraining. "
                "Medical Image Analysis 2023;83:102789."
            ),
            "mindglide-v1.0": (
                "MS-PINPOINT. mindGlide: SOTA open-source MS lesion and brain "
                "structure segmentation. Nature Communications 2025."
            ),
        }
        return citations.get(validation_source, "")
