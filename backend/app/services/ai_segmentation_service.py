"""
AI Segmentation Service for Brain MRI.

Delegates to validated clinical tools (LST-AI, SynthSeg) via ToolRunnerService
when available, with graceful degradation when tools are not configured.

The Vertex AI proxy code has been removed as those endpoints were never deployed.

@module services.ai_segmentation_service
"""

import uuid
from typing import List, Dict, Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.interfaces.ai_interface import (
    IAISegmentationService,
    AIModelType,
    AITaskStatus,
    InteractiveSegmentRequest,
    AutoSegmentRequest,
    AnomalyDetectionRequest,
    AITaskResult,
    AnomalyDetectionResult,
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
    AI segmentation service.

    Delegates to ToolRunnerService for SynthSeg brain parcellation.
    Interactive segmentation is not yet available (future nnInteractive integration).
    """

    def __init__(self, cache_service=None):
        self.cache_service = cache_service
        self._tasks: Dict[str, AITaskResult] = {}
        logger.info("[AISegmentation] Service initialized")

    async def segment_interactive(
        self,
        request: InteractiveSegmentRequest,
    ) -> AITaskResult:
        """Interactive segmentation is not yet available."""
        return AITaskResult(
            task_id=str(uuid.uuid4()),
            status=AITaskStatus.FAILED,
            error=(
                "Interactive segmentation is not yet available. "
                "Use the Clinical Tools panel to run LST-AI or SynthSeg instead."
            ),
        )

    async def segment_auto(
        self,
        request: AutoSegmentRequest,
    ) -> AITaskResult:
        """
        Auto brain parcellation.

        Delegates to SynthSeg via ToolRunnerService when available.
        Returns informative error when SynthSeg is not configured.
        """
        # Try to get ToolRunnerService
        try:
            from app.core.container import get_tool_runner_service
            tool_runner = get_tool_runner_service()

            if tool_runner.is_synthseg_available():
                task_id = await tool_runner.run_synthseg(request.file_id)
                task = await tool_runner.get_task_status(task_id)
                return AITaskResult(
                    task_id=task.task_id,
                    status=AITaskStatus.PROCESSING,
                    progress=task.progress,
                )
        except Exception as e:
            logger.warning(f"[AISegmentation] ToolRunnerService not available: {e}")

        return AITaskResult(
            task_id=str(uuid.uuid4()),
            status=AITaskStatus.FAILED,
            error=(
                "SynthSeg is not configured. Use the Clinical Tools panel "
                "(POST /api/v1/clinical/synthseg/parcellate) to run brain parcellation."
            ),
        )

    async def detect_anomalies(
        self,
        request: AnomalyDetectionRequest,
    ) -> AnomalyDetectionResult:
        """Anomaly detection is not yet available."""
        return AnomalyDetectionResult(
            anomalies=[],
            overall_confidence=0.0,
            processing_time_ms=0,
        )

    async def get_task_status(self, task_id: str) -> AITaskResult:
        """Get the status of an async AI inference task."""
        # Check local tasks first
        if task_id in self._tasks:
            return self._tasks[task_id]

        # Try ToolRunnerService
        try:
            from app.core.container import get_tool_runner_service
            tool_runner = get_tool_runner_service()
            tool_task = await tool_runner.get_task_status(task_id)
            if tool_task.status.value != "failed" or tool_task.error != "Task not found":
                return AITaskResult(
                    task_id=tool_task.task_id,
                    status=AITaskStatus(tool_task.status.value)
                    if tool_task.status.value in [s.value for s in AITaskStatus]
                    else AITaskStatus.PROCESSING,
                    progress=tool_task.progress,
                    segmentation_id=tool_task.segmentation_id,
                    error=tool_task.error,
                    processing_time_ms=tool_task.processing_time_ms,
                )
        except Exception:
            pass

        return AITaskResult(
            task_id=task_id,
            status=AITaskStatus.FAILED,
            error="Task not found",
        )

    async def list_available_models(self) -> List[Dict[str, Any]]:
        """List available AI models and their configuration status."""
        # Check tool availability via ToolRunnerService
        synthseg_available = False
        mindglide_available = False
        try:
            from app.core.container import get_tool_runner_service
            tool_runner = get_tool_runner_service()
            synthseg_available = tool_runner.is_synthseg_available()
            mindglide_available = tool_runner.is_mindglide_available()
        except Exception:
            pass

        models = [
            {
                "id": "synthseg",
                "name": "SynthSeg",
                "type": "auto",
                "description": "Automatic segmentation of 30+ brain structures "
                               "(hippocampus, ventricles, cortex, thalamus, etc.).",
                "structures_count": len(SYNTHSEG_LABELS),
                "configured": synthseg_available,
                "validation_source": "synthseg-v2.0",
            },
            {
                "id": "lst-ai",
                "name": "LST-AI",
                "type": "auto",
                "description": "MS lesion segmentation with MAGNIMS zone classification.",
                "configured": False,  # LST-AI uses dedicated /clinical endpoints
                "note": "Use /api/v1/clinical/lst-ai/segment endpoint",
            },
            {
                "id": "mindglide",
                "name": "mindGlide (MS-PINPOINT)",
                "type": "auto",
                "description": (
                    "SOTA MS lesion + brain structure segmentation (Nature Comms 2025). "
                    "DynUNet (MONAI), trained on 23,000+ scans. 20 brain structures + lesions."
                ),
                "structures_count": 20,
                "configured": mindglide_available,
                "validation_source": "mindglide-v1.0",
            },
        ]

        return models

    @staticmethod
    def get_synthseg_labels() -> Dict[int, tuple]:
        """Get the SynthSeg brain structure label mapping."""
        return SYNTHSEG_LABELS
