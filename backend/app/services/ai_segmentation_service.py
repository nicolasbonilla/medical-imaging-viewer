"""
AI Segmentation Service for Brain MRI.

Provides AI-powered brain segmentation using Vertex AI endpoints:
- Interactive segmentation (SAM-Med3D / nnInteractive)
- Automatic brain structure segmentation (SynthSeg)
- Brain anomaly detection

Results are stored in the same format as manual segmentations
(Uint8Array masks with 12-byte header binary protocol) for seamless
integration with the existing frontend.

@module services.ai_segmentation_service
"""

import uuid
import time
import asyncio
import numpy as np
from typing import Optional, List, Dict, Any
from datetime import datetime

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.exceptions import SegmentationException, NotFoundException, ValidationException
from app.core.interfaces.ai_interface import (
    IAISegmentationService,
    AIModelType,
    AITaskStatus,
    InteractiveSegmentRequest,
    AutoSegmentRequest,
    AnomalyDetectionRequest,
    AITaskResult,
    AnomalyDetectionResult,
    BrainAnomaly,
)

logger = get_logger(__name__)
settings = get_settings()


# Brain structure labels for SynthSeg (FreeSurfer convention)
SYNTHSEG_LABELS = {
    0: ("Background", "#000000"),
    2: ("Left Cerebral White Matter", "#F5F5DC"),
    3: ("Left Cerebral Cortex", "#CD853F"),
    4: ("Left Lateral Ventricle", "#4169E1"),
    5: ("Left Inf Lat Ventricle", "#6495ED"),
    7: ("Left Cerebellum White Matter", "#F0E68C"),
    8: ("Left Cerebellum Cortex", "#BDB76B"),
    10: ("Left Thalamus", "#2E8B57"),
    11: ("Left Caudate", "#00CED1"),
    12: ("Left Putamen", "#FF69B4"),
    13: ("Left Pallidum", "#FF1493"),
    14: ("3rd Ventricle", "#1E90FF"),
    15: ("4th Ventricle", "#00BFFF"),
    16: ("Brain Stem", "#8B4513"),
    17: ("Left Hippocampus", "#FFD700"),
    18: ("Left Amygdala", "#FF8C00"),
    24: ("CSF", "#87CEEB"),
    26: ("Left Accumbens", "#DA70D6"),
    28: ("Left VentralDC", "#9370DB"),
    41: ("Right Cerebral White Matter", "#FFFACD"),
    42: ("Right Cerebral Cortex", "#DEB887"),
    43: ("Right Lateral Ventricle", "#6495ED"),
    44: ("Right Inf Lat Ventricle", "#87CEFA"),
    46: ("Right Cerebellum White Matter", "#EEE8AA"),
    47: ("Right Cerebellum Cortex", "#D2B48C"),
    49: ("Right Thalamus", "#3CB371"),
    50: ("Right Caudate", "#48D1CC"),
    51: ("Right Putamen", "#FF69B4"),
    52: ("Right Pallidum", "#FF1493"),
    53: ("Right Hippocampus", "#FFD700"),
    54: ("Right Amygdala", "#FF8C00"),
    58: ("Right Accumbens", "#DA70D6"),
    60: ("Right VentralDC", "#9370DB"),
}


class AISegmentationService(IAISegmentationService):
    """
    AI segmentation service using Vertex AI endpoints for inference.

    The service acts as a proxy between the FastAPI backend and Vertex AI.
    Heavy model inference runs on GPU-equipped Vertex AI endpoints,
    while this service handles request packaging, result processing,
    and integration with the existing segmentation storage.
    """

    def __init__(self, cache_service=None):
        self.cache_service = cache_service
        self._tasks: Dict[str, AITaskResult] = {}
        self._vertex_client = None
        logger.info("[AISegmentation] Service initialized")

    def _get_vertex_client(self):
        """Lazy-load Vertex AI client."""
        if self._vertex_client is None:
            if not settings.VERTEX_AI_PROJECT_ID:
                logger.warning("[AISegmentation] Vertex AI not configured (VERTEX_AI_PROJECT_ID empty)")
                return None
            try:
                from google.cloud import aiplatform
                aiplatform.init(
                    project=settings.VERTEX_AI_PROJECT_ID,
                    location=settings.VERTEX_AI_REGION,
                )
                self._vertex_client = aiplatform
                logger.info("[AISegmentation] Vertex AI client initialized")
            except Exception as e:
                logger.error(f"[AISegmentation] Failed to init Vertex AI: {e}")
                return None
        return self._vertex_client

    def _is_vertex_configured(self, endpoint_setting: str) -> bool:
        """Check if a specific Vertex AI endpoint is configured."""
        return bool(settings.VERTEX_AI_PROJECT_ID and endpoint_setting)

    async def segment_interactive(
        self,
        request: InteractiveSegmentRequest,
    ) -> AITaskResult:
        """Run interactive segmentation from click points."""
        task_id = str(uuid.uuid4())
        start_time = time.time()

        # Validate endpoint configuration
        if not self._is_vertex_configured(settings.VERTEX_AI_ENDPOINT_INTERACTIVE):
            # Return a graceful error — the feature is not yet deployed
            return AITaskResult(
                task_id=task_id,
                status=AITaskStatus.FAILED,
                error="Interactive segmentation model not configured. "
                      "Set VERTEX_AI_ENDPOINT_INTERACTIVE to enable this feature.",
            )

        # Create pending task
        self._tasks[task_id] = AITaskResult(
            task_id=task_id,
            status=AITaskStatus.PROCESSING,
            progress=10.0,
        )

        try:
            # Package request for Vertex AI
            client = self._get_vertex_client()
            if client is None:
                raise SegmentationException("Vertex AI client not available")

            endpoint = client.Endpoint(settings.VERTEX_AI_ENDPOINT_INTERACTIVE)

            # Prepare inference input
            instances = [{
                "file_id": request.file_id,
                "click_points": [
                    {"x": p.x, "y": p.y, "z": p.z, "label": p.label}
                    for p in request.click_points
                ],
                "model": request.model.value,
                "current_mask_id": request.current_mask_id,
            }]

            self._tasks[task_id].progress = 30.0

            # Send prediction request
            response = endpoint.predict(instances=instances)

            self._tasks[task_id].progress = 80.0

            # Process response — expects segmentation_id of the created mask
            prediction = response.predictions[0]
            segmentation_id = prediction.get("segmentation_id")

            elapsed_ms = int((time.time() - start_time) * 1000)

            result = AITaskResult(
                task_id=task_id,
                status=AITaskStatus.COMPLETED,
                progress=100.0,
                segmentation_id=segmentation_id,
                processing_time_ms=elapsed_ms,
            )
            self._tasks[task_id] = result
            logger.info(f"[AISegmentation] Interactive segmentation completed in {elapsed_ms}ms")
            return result

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            result = AITaskResult(
                task_id=task_id,
                status=AITaskStatus.FAILED,
                error=str(e),
                processing_time_ms=elapsed_ms,
            )
            self._tasks[task_id] = result
            logger.error(f"[AISegmentation] Interactive segmentation failed: {e}")
            return result

    async def segment_auto(
        self,
        request: AutoSegmentRequest,
    ) -> AITaskResult:
        """Run automatic brain structure segmentation."""
        task_id = str(uuid.uuid4())
        start_time = time.time()

        if not self._is_vertex_configured(settings.VERTEX_AI_ENDPOINT_AUTO):
            return AITaskResult(
                task_id=task_id,
                status=AITaskStatus.FAILED,
                error="Auto segmentation model not configured. "
                      "Set VERTEX_AI_ENDPOINT_AUTO to enable this feature.",
            )

        self._tasks[task_id] = AITaskResult(
            task_id=task_id,
            status=AITaskStatus.PROCESSING,
            progress=10.0,
        )

        try:
            client = self._get_vertex_client()
            if client is None:
                raise SegmentationException("Vertex AI client not available")

            endpoint = client.Endpoint(settings.VERTEX_AI_ENDPOINT_AUTO)

            instances = [{
                "file_id": request.file_id,
                "model": request.model.value,
            }]

            self._tasks[task_id].progress = 30.0

            response = endpoint.predict(instances=instances)

            self._tasks[task_id].progress = 80.0

            prediction = response.predictions[0]
            segmentation_id = prediction.get("segmentation_id")

            elapsed_ms = int((time.time() - start_time) * 1000)

            result = AITaskResult(
                task_id=task_id,
                status=AITaskStatus.COMPLETED,
                progress=100.0,
                segmentation_id=segmentation_id,
                processing_time_ms=elapsed_ms,
            )
            self._tasks[task_id] = result
            logger.info(f"[AISegmentation] Auto segmentation completed in {elapsed_ms}ms")
            return result

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            result = AITaskResult(
                task_id=task_id,
                status=AITaskStatus.FAILED,
                error=str(e),
                processing_time_ms=elapsed_ms,
            )
            self._tasks[task_id] = result
            logger.error(f"[AISegmentation] Auto segmentation failed: {e}")
            return result

    async def detect_anomalies(
        self,
        request: AnomalyDetectionRequest,
    ) -> AnomalyDetectionResult:
        """Detect brain anomalies."""
        start_time = time.time()

        if not self._is_vertex_configured(settings.VERTEX_AI_ENDPOINT_ANOMALY):
            return AnomalyDetectionResult(
                anomalies=[],
                overall_confidence=0.0,
                processing_time_ms=0,
            )

        try:
            client = self._get_vertex_client()
            if client is None:
                raise SegmentationException("Vertex AI client not available")

            endpoint = client.Endpoint(settings.VERTEX_AI_ENDPOINT_ANOMALY)

            instances = [{
                "file_id": request.file_id,
                "sensitivity": request.sensitivity,
            }]

            response = endpoint.predict(instances=instances)
            prediction = response.predictions[0]

            anomalies = [
                BrainAnomaly(**a) for a in prediction.get("anomalies", [])
            ]

            elapsed_ms = int((time.time() - start_time) * 1000)

            result = AnomalyDetectionResult(
                anomalies=anomalies,
                heatmap_segmentation_id=prediction.get("heatmap_segmentation_id"),
                overall_confidence=prediction.get("overall_confidence", 0.0),
                processing_time_ms=elapsed_ms,
            )

            logger.info(
                f"[AISegmentation] Anomaly detection completed: "
                f"{len(anomalies)} anomalies found in {elapsed_ms}ms"
            )
            return result

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(f"[AISegmentation] Anomaly detection failed: {e}")
            return AnomalyDetectionResult(
                anomalies=[],
                overall_confidence=0.0,
                processing_time_ms=elapsed_ms,
            )

    async def get_task_status(self, task_id: str) -> AITaskResult:
        """Get the status of an async AI inference task."""
        if task_id in self._tasks:
            return self._tasks[task_id]

        return AITaskResult(
            task_id=task_id,
            status=AITaskStatus.FAILED,
            error="Task not found",
        )

    async def list_available_models(self) -> List[Dict[str, Any]]:
        """List available AI models and their configuration status."""
        models = [
            {
                "id": "sam_med3d",
                "name": "SAM-Med3D",
                "type": "interactive",
                "description": "Interactive 3D segmentation from click points. "
                               "Click on a brain structure to segment it in 3D.",
                "prompt_types": ["point"],
                "configured": self._is_vertex_configured(
                    settings.VERTEX_AI_ENDPOINT_INTERACTIVE
                ),
            },
            {
                "id": "nninteractive",
                "name": "nnInteractive",
                "type": "interactive",
                "description": "Interactive segmentation with points, scribbles, "
                               "bounding boxes, and lasso prompts.",
                "prompt_types": ["point", "scribble", "bbox", "lasso"],
                "configured": self._is_vertex_configured(
                    settings.VERTEX_AI_ENDPOINT_INTERACTIVE
                ),
            },
            {
                "id": "synthseg",
                "name": "SynthSeg",
                "type": "auto",
                "description": "Automatic segmentation of 30+ brain structures "
                               "(hippocampus, ventricles, cortex, thalamus, etc.).",
                "structures_count": len(SYNTHSEG_LABELS),
                "configured": self._is_vertex_configured(
                    settings.VERTEX_AI_ENDPOINT_AUTO
                ),
            },
        ]

        return models

    @staticmethod
    def get_synthseg_labels() -> Dict[int, tuple]:
        """Get the SynthSeg brain structure label mapping."""
        return SYNTHSEG_LABELS
