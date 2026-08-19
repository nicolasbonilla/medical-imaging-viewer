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

    def is_flames_available(self) -> bool:
        """Check if the FLAMeS GPU worker is configured."""
        return bool(settings.FLAMES_ENABLED and settings.FLAMES_ENDPOINT)

    def is_tool_available(self, tool: str) -> bool:
        """Check if a clinical tool is available by ID."""
        checkers = {
            "lst-ai": self.is_lstai_available,
            "synthseg": self.is_synthseg_available,
            "mindglide": self.is_mindglide_available,
            "flames": self.is_flames_available,
        }
        return checkers.get(tool, lambda: False)()

    async def check_sidecar_health(self, tool: str) -> bool:
        """Ping a sidecar's /health endpoint."""
        endpoints = {
            "lst-ai": settings.LSTAI_ENDPOINT,
            "synthseg": settings.SYNTHSEG_ENDPOINT,
            "mindglide": settings.MINDGLIDE_ENDPOINT,
            "flames": settings.FLAMES_ENDPOINT,
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
                id="flames",
                name="FLAMeS",
                version="1.0.0",
                available=self.is_flames_available(),
                description=(
                    "SOTA single-FLAIR MS lesion segmentation. nnU-Net v2 ensemble "
                    "(Dataset004_WML) externally validated to Dice 0.74 / F1 0.78, "
                    "outperforming SAMSEG, LST-LPA and LST-AI. Needs only FLAIR — the "
                    "modality essentially always acquired in MS — so it degrades "
                    "gracefully when a T1 is unavailable. Runs on a scale-to-zero GPU."
                ),
                citation=(
                    "Ballerini A, et al. FLAMeS: a robust deep learning model for "
                    "automated multiple sclerosis lesion segmentation. "
                    "J Neuroimaging 2025 (medRxiv 2025.05.19.25327707). Weights CC-BY-4.0, "
                    "Zenodo 17955359."
                ),
                license="CC-BY-4.0 (weights); permissive",
                fda_status="research_only",
                required_inputs=["FLAIR"],
            ),
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
                reference_mri_path=flair_path,  # RC-031: LST-AI segments FLAIR space
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

    async def run_flames(
        self,
        flair_file_id: str,
        patient_id: Optional[str] = None,
        study_id: Optional[str] = None,
    ) -> str:
        """
        Submit a FLAMeS single-FLAIR MS-lesion segmentation task.

        Unlike the Docker-sidecar tools (which share a volume), FLAMeS runs as a
        separate Cloud Run GPU service, so the contract is GCS-URI based: the main
        service tells the worker the FLAIR's gs:// URI and a staging output URI, the
        worker does GPU inference + skull-strip and writes the mask back to GCS. The
        mask is then oriented (RC-031) and stored via the same canonical path as the
        other tools, so the viewer loads it identically.

        Returns:
            task_id for status polling
        """
        task_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        if not self.is_flames_available():
            self._tasks[task_id] = ToolTask(
                task_id=task_id,
                tool="flames",
                status=ToolTaskStatus.FAILED,
                error=(
                    "FLAMeS is not configured. Deploy the flames-worker GPU service "
                    "and set FLAMES_ENABLED=true and FLAMES_ENDPOINT to its URL."
                ),
                validation_source="flames-v1.0",
                created_at=now,
            )
            return task_id

        self._tasks[task_id] = ToolTask(
            task_id=task_id,
            tool="flames",
            status=ToolTaskStatus.PENDING,
            progress=0.0,
            validation_source="flames-v1.0",
            created_at=now,
        )

        asyncio.create_task(
            self._execute_flames(task_id, flair_file_id, patient_id, study_id)
        )

        return task_id

    async def _execute_flames(
        self,
        task_id: str,
        flair_file_id: str,
        patient_id: Optional[str],
        study_id: Optional[str],
    ):
        """Background execution of FLAMeS segmentation over the GCS-URI contract."""
        import tempfile

        start_time = time.time()
        task = self._tasks[task_id]
        bucket = settings.GCS_BUCKET_NAME
        input_uri = f"gs://{bucket}/{flair_file_id}"
        # Staging URI the worker writes to; we re-store it at the canonical
        # segmentations/{id}/masks.nii.gz path after RC-031 orientation.
        output_uri = f"gs://{bucket}/clinical-tools/flames/{task_id}/mask.nii.gz"
        work_dir = Path(tempfile.mkdtemp(prefix=f"flames_{task_id}_"))

        try:
            # Phase 1: dispatch GPU inference (worker pulls FLAIR from GCS itself)
            task.status = ToolTaskStatus.PROCESSING
            task.progress = 20.0

            async with httpx.AsyncClient(
                timeout=httpx.Timeout(settings.FLAMES_TIMEOUT_SECONDS, connect=10.0)
            ) as client:
                headers = await self._worker_auth_headers(settings.FLAMES_ENDPOINT)
                resp = await client.post(
                    f"{settings.FLAMES_ENDPOINT}/segment",
                    headers=headers,
                    json={
                        "input_gcs_uri": input_uri,
                        "output_gcs_uri": output_uri,
                        "skull_strip": True,
                        "threshold": settings.FLAMES_THRESHOLD,
                    },
                )
                resp.raise_for_status()
                result = resp.json()

            task.progress = 80.0

            # Phase 2: pull the mask + reference FLAIR back for RC-031 orientation
            # and canonical storage (the worker wrote to a staging URI, not the
            # viewer-loadable path — orientation is applied here, not on the GPU).
            task.status = ToolTaskStatus.STORING
            task.progress = 85.0

            mask_path = work_dir / "flames_mask.nii.gz"
            mask_path.write_bytes(await self._storage.download(
                f"clinical-tools/flames/{task_id}/mask.nii.gz"
            ))
            flair_path = work_dir / "flair.nii.gz"
            flair_path.write_bytes(await self._storage.download(flair_file_id))

            seg_id = await self._store_nifti_as_segmentation(
                mask_path=mask_path,
                file_id=flair_file_id,
                description="FLAMeS automated MS lesion segmentation (single-FLAIR SOTA)",
                validation_source="flames-v1.0",
                patient_id=patient_id,
                study_id=study_id,
                reference_mri_path=flair_path,  # RC-031: FLAMeS segments FLAIR space
            )

            elapsed_ms = int((time.time() - start_time) * 1000)
            task.status = ToolTaskStatus.COMPLETED
            task.progress = 100.0
            task.segmentation_id = seg_id
            task.processing_time_ms = elapsed_ms
            logger.info(
                f"[ToolRunner] FLAMeS completed in {elapsed_ms}ms "
                f"({result.get('lesion_voxels', '?')} lesion voxels)",
                extra={"task_id": task_id, "segmentation_id": seg_id},
            )

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            task.status = ToolTaskStatus.FAILED
            task.error = str(e)
            task.processing_time_ms = elapsed_ms
            logger.error(f"[ToolRunner] FLAMeS failed: {e}", extra={"task_id": task_id})

        finally:
            self._cleanup_work_dir(work_dir)

    async def _worker_auth_headers(self, audience: str) -> dict:
        """Mint an ID token so the main service can call a private ('--no-allow-
        unauthenticated') Cloud Run worker. On Cloud Run the metadata server issues
        an identity token for the service account, scoped to the worker's URL as the
        audience. Fails open to no auth (local/dev, or a worker that allows
        unauthenticated) so this never blocks a legitimately public endpoint."""
        try:
            import google.auth.transport.requests
            import google.oauth2.id_token

            def _mint():
                req = google.auth.transport.requests.Request()
                return google.oauth2.id_token.fetch_id_token(req, audience)

            token = await asyncio.get_event_loop().run_in_executor(None, _mint)
            return {"Authorization": f"Bearer {token}"} if token else {}
        except Exception as e:  # noqa: BLE001 — auth is best-effort here
            logger.debug(f"[ToolRunner] No ID token for worker call ({e}); calling unauthenticated")
            return {}

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
                reference_mri_path=input_path,  # RC-031: orient by affine
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
                reference_mri_path=input_path,  # RC-031: orient by affine
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
                    reference_mri_path=input_path,  # RC-031: orient by affine
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

    def _orient_mask_to_display(
        self,
        mask_native: np.ndarray,
        source_affine: np.ndarray,
        reference_mri_path: Optional[Path],
    ) -> np.ndarray:
        """RC-031 (risk control for HAZ-006): bring a clinical-tool mask into the
        app's DISPLAY convention (k, a0, a1) — the one painted masks
        (segmentation_service.py:157) and the viewer's MSMask branch
        (segmentation_regions.py:566-574, transpose (2,0,1)) use.

        The legacy path applied a blind np.transpose(mask,(2,1,0)) -> (k, a1, a0),
        which is the in-plane TRANSPOSE of the display convention. That mirrored
        parcellation overlays and — because classify_lesions_with_parcellation
        (ms_region_classifier.py:138) only guards on equal SHAPE — silently
        mis-assigned MAGNIMS regions (and DIS) on square 256x256 data, where the
        two conventions share a shape. Proven in
        test_rc031_ingest_order_characterization.py.

        This aligns by the AFFINES instead of a fixed transpose: reorient the mask
        onto the reference MRI's voxel grid (correct for any source orientation —
        the property five prior fixed-transpose attempts lacked), then apply the
        (2,0,1) display transpose.

        Fails SAFE: if the reference MRI or a determinate affine is unavailable it
        falls back to the legacy (2,1,0), so behaviour never regresses below the
        current baseline.
        """
        import nibabel as nib
        from app.utils.nifti_utils import reorient_array_to_reference

        DISPLAY_TRANSPOSE = (2, 0, 1)
        LEGACY_TRANSPOSE = (2, 1, 0)
        try:
            if reference_mri_path is not None and Path(reference_mri_path).exists():
                ref_img = nib.load(str(reference_mri_path))
                aligned = reorient_array_to_reference(
                    mask_native, source_affine, ref_img.affine
                )
                return np.transpose(aligned, DISPLAY_TRANSPOSE)
            logger.warning(
                "[RC-031] No reference MRI for orientation (%s); using legacy "
                "(2,1,0) transpose — overlay/classification may be in-plane "
                "transposed on this mask.",
                reference_mri_path,
            )
        except Exception as e:  # noqa: BLE001 — fail safe, never block ingest
            logger.warning(
                "[RC-031] Affine reorientation failed (%s); using legacy "
                "(2,1,0) transpose.", e,
            )
        return np.transpose(mask_native, LEGACY_TRANSPOSE)

    async def _store_nifti_as_segmentation(
        self,
        mask_path: Path,
        file_id: str,
        description: str,
        validation_source: str,
        patient_id: Optional[str] = None,
        study_id: Optional[str] = None,
        types_path: Optional[Path] = None,
        reference_mri_path: Optional[Path] = None,
    ) -> str:
        """
        Read a NIfTI mask from disk and store it as a segmentation.

        Converts the NIfTI to the app's binary protocol format:
        12-byte header (uint32 depth, height, width) + uint8 voxel data.
        Uploads to GCS and creates Firestore metadata.

        reference_mri_path: the MRI the tool ran on. Used to orient the mask into
        the app's display convention by affine (RC-031); if omitted, falls back
        to the legacy fixed transpose.
        """
        import nibabel as nib

        # Read primary mask (keep its affine for RC-031 affine-based orientation)
        img = nib.load(str(mask_path))
        mask_data = np.asarray(img.dataobj).astype(np.uint8)
        source_affine = img.affine

        # If types mask exists (LST-AI MAGNIMS zones), use it instead
        if types_path is not None and types_path.exists():
            types_img = nib.load(str(types_path))
            mask_data = np.asarray(types_img.dataobj).astype(np.uint8)
            source_affine = types_img.affine

        # Ensure 3D
        if mask_data.ndim == 4:
            mask_data = mask_data[:, :, :, 0]

        # RC-031: orient into the app's display convention by AFFINE, not a blind
        # transpose (fails safe to the legacy (2,1,0) when no reference MRI).
        mask_data = self._orient_mask_to_display(
            mask_data, source_affine, reference_mri_path
        )

        depth, height, width = mask_data.shape

        # Silent-failure visibility (finding #7): a sidecar can complete its HTTP
        # call yet write an all-zeros mask (model didn't run, wrong contrast,
        # resampled off-grid). Stored as-is, that is INDISTINGUISHABLE from a
        # genuine negative result — "0 lesions" reads as a clean scan when the
        # tool actually produced nothing. We do NOT reject an empty mask (a
        # healthy brain legitimately has zero LESION voxels), but we record the
        # annotated-voxel count in metadata and log a warning so the emptiness is
        # visible to downstream consumers and to ops, never silent.
        annotated_voxels = int((mask_data > 0).sum())
        if annotated_voxels == 0:
            logger.warning(
                "[ToolRunner] Stored an ALL-ZERO clinical-tool mask — "
                "verify this is a true negative and not a sidecar failure",
                extra={
                    "validation_source": validation_source,
                    "file_id": file_id,
                    "shape": [depth, height, width],
                },
            )

        # Store as NIfTI at the CANONICAL path the viewer actually loads. The previous
        # code wrote the app's raw .bin protocol to `segmentations/clinical-tools/{id}/
        # mask.bin`, but `_load_masks_from_gcs` only reads `segmentations/{id}/masks.nii.gz`
        # (or .npz) — so an auto-segmentation appeared in the Firestore list but 404'd in
        # the viewer. Match `_save_masks_to_gcs`: uint8 NIfTI with the source affine, the
        # RC-031 v2 orient marker, and slope/inter reset so labels are verbatim.
        import nibabel as nib
        import tempfile as _tempfile
        affine = source_affine if source_affine is not None else np.eye(4)
        nifti_img = nib.Nifti1Image(mask_data.astype(np.uint8), affine)
        nifti_img.header.set_data_dtype(np.uint8)
        nifti_img.header.set_slope_inter(1.0, 0.0)
        nifti_img.header["descrip"] = b"RC031-ORIENT-V2"   # matches segmentation_service._RC031_ORIENT_MARKER
        with _tempfile.NamedTemporaryFile(suffix=".nii.gz", delete=False) as _tmp:
            _tmp_path = _tmp.name
        try:
            nib.save(nifti_img, _tmp_path)
            with open(_tmp_path, "rb") as _f:
                binary_data = _f.read()
        finally:
            try:
                os.unlink(_tmp_path)
            except OSError:
                pass

        # Generate segmentation ID and GCS path (canonical — viewer-loadable)
        seg_id = str(uuid.uuid4())
        gcs_path = f"segmentations/{seg_id}/masks.nii.gz"

        # Upload to GCS
        if self._storage is not None:
            await self._storage.upload(
                object_name=gcs_path,
                file_data=binary_data,
                content_type="application/gzip",
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
                "annotated_voxels": annotated_voxels,
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
                file_data=csv_data,
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
            "flames-v1.0": (
                "Ballerini A, et al. FLAMeS: a robust deep learning model for "
                "automated multiple sclerosis lesion segmentation. J Neuroimaging "
                "2025 (medRxiv 2025.05.19.25327707). nnU-Net v2, Dataset004_WML; "
                "weights CC-BY-4.0, Zenodo 17955359."
            ),
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
