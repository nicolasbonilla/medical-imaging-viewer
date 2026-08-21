"""
Interface for AI Segmentation and Analysis Services.

Defines the contract for AI-powered brain MRI operations including
interactive segmentation, automatic brain structure segmentation,
anomaly detection, volumetry, and report generation.

@module core.interfaces.ai_interface
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum
from pydantic import BaseModel, Field


# =============================================================================
# AI Request/Response Models
# =============================================================================

class AIModelType(str, Enum):
    """Available AI models for brain segmentation."""
    SAM_MED3D = "sam_med3d"
    NNINTERACTIVE = "nninteractive"
    SYNTHSEG = "synthseg"


class AITaskStatus(str, Enum):
    """Status of an async AI inference task."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ClickPoint3D(BaseModel):
    """A 3D click point for interactive segmentation."""
    x: int = Field(..., ge=0, description="X coordinate (column)")
    y: int = Field(..., ge=0, description="Y coordinate (row)")
    z: int = Field(..., ge=0, description="Z coordinate (slice index)")
    label: str = Field(default="positive", pattern="^(positive|negative)$")


class InteractiveSegmentRequest(BaseModel):
    """Request for interactive AI segmentation."""
    file_id: str = Field(..., description="GCS file ID of the brain MRI")
    click_points: List[ClickPoint3D] = Field(..., min_length=1, max_length=50)
    model: AIModelType = Field(default=AIModelType.SAM_MED3D)
    current_mask_id: Optional[str] = Field(None, description="Existing segmentation to refine")


class AutoSegmentRequest(BaseModel):
    """Request for automatic brain structure segmentation."""
    file_id: str = Field(..., description="GCS file ID of the brain MRI")
    model: AIModelType = Field(default=AIModelType.SYNTHSEG)


class AnomalyDetectionRequest(BaseModel):
    """Request for brain anomaly detection."""
    file_id: str = Field(..., description="GCS file ID of the brain MRI")
    sensitivity: str = Field(default="medium", pattern="^(low|medium|high)$")


class BrainAnomaly(BaseModel):
    """A detected MS lesion or brain anomaly."""
    type: str = Field(..., description="Anomaly type: ms_lesion, active_lesion, chronic_lesion, black_hole")
    location: str = Field(..., description="Anatomical location description")
    confidence: float = Field(..., ge=0.0, le=1.0)
    volume_mm3: Optional[float] = None
    gadolinium_enhancement: Optional[bool] = Field(None, description="Whether lesion shows gadolinium enhancement")
    bounding_box: Optional[Dict[str, int]] = Field(
        None, description="3D bounding box: x_min, y_min, z_min, x_max, y_max, z_max"
    )


class AITaskResult(BaseModel):
    """Result of an async AI inference task."""
    task_id: str
    status: AITaskStatus
    progress: float = Field(default=0.0, ge=0.0, le=100.0)
    segmentation_id: Optional[str] = None
    error: Optional[str] = None
    processing_time_ms: Optional[int] = None


class AnomalyDetectionResult(BaseModel):
    """Result of brain anomaly detection."""
    anomalies: List[BrainAnomaly] = Field(default_factory=list)
    heatmap_segmentation_id: Optional[str] = None
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    processing_time_ms: Optional[int] = None


class BrainStructureVolume(BaseModel):
    """Volume measurement for a single brain structure."""
    label_id: int
    structure_name: str
    volume_mm3: float
    volume_ml: float
    normative_percentile: Optional[float] = Field(None, ge=0.0, le=100.0)
    is_abnormal: bool = False
    abnormality_type: Optional[str] = None  # 'atrophy' or 'enlargement'


class VolumetryResult(BaseModel):
    """Result of brain volumetry computation."""
    segmentation_id: str
    structures: List[BrainStructureVolume]
    total_brain_volume_ml: Optional[float] = None
    intracranial_volume_ml: Optional[float] = None
    # Brain Parenchymal Fraction = brain parenchyma / intracranial volume.
    # The head-size-normalized atrophy metric standard in MS (SIENAX, icobrain,
    # NeuroQuant). Dimensionless (0..1); ~0.80-0.85 in healthy adults, declining
    # with atrophy. Enables cross-patient/cross-scanner comparability that raw
    # brain volume (confounded by head size) cannot provide.
    brain_parenchymal_fraction: Optional[float] = Field(None, ge=0.0, le=1.0)
    processing_time_ms: Optional[int] = None
    # Honesty (audit #6): the normative percentiles + abnormality flags are AGE-based only.
    # patient_sex is accepted by the API but NOT yet used (NORMATIVE_VOLUMES is single-sex),
    # so a sex-adjusted claim would be false. Consumers must NOT present these as sex-adjusted.
    normative_sex_stratified: bool = False


class VolumetryComparisonResult(BaseModel):
    """Result of longitudinal volumetry comparison."""
    patient_id: str
    timepoints: List[Dict[str, Any]]  # [{study_id, date, volumes}]
    changes: List[Dict[str, Any]]  # [{structure, change_percent, annualized_change_percent, trend}]
    # Elapsed years between first and last timepoint (from ISO dates), used to
    # annualize atrophy. None when dates are missing/unparseable, in which case
    # annualized rates are also None (raw change is still reported).
    interval_years: Optional[float] = None


# =============================================================================
# Validated Clinical Tool Models
# =============================================================================

class ToolTaskStatus(str, Enum):
    """Status of an async clinical tool task."""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    STORING = "storing"
    COMPLETED = "completed"
    FAILED = "failed"


class ToolTask(BaseModel):
    """Result/status of a validated clinical tool task (LST-AI, SynthSeg)."""
    task_id: str
    tool: str = Field(..., description="Tool identifier: 'lst-ai' or 'synthseg'")
    status: ToolTaskStatus
    progress: float = Field(default=0.0, ge=0.0, le=100.0)
    segmentation_id: Optional[str] = None
    error: Optional[str] = None
    processing_time_ms: Optional[int] = None
    validation_source: str = Field(default="custom", description="Tool version string, e.g. 'lst-ai-v1.0.3'")
    created_at: str = Field(..., description="ISO 8601 timestamp")


class LSTAISegmentRequest(BaseModel):
    """Request for LST-AI lesion segmentation (requires T1 + FLAIR)."""
    t1_file_id: str = Field(..., description="GCS file ID for T1-weighted MRI")
    flair_file_id: str = Field(..., description="GCS file ID for FLAIR MRI")
    patient_id: Optional[str] = None
    study_id: Optional[str] = None


class SynthSegRequest(BaseModel):
    """Request for SynthSeg brain parcellation."""
    file_id: str = Field(..., description="GCS file ID for brain MRI (any contrast)")
    patient_id: Optional[str] = None
    study_id: Optional[str] = None


class FLAMeSSegmentRequest(BaseModel):
    """Request for FLAMeS MS-lesion segmentation (single FLAIR)."""
    flair_file_id: str = Field(..., description="GCS file ID for FLAIR MRI")
    patient_id: Optional[str] = None
    study_id: Optional[str] = None


class ClinicalToolInfo(BaseModel):
    """Information about a validated clinical tool."""
    id: str
    name: str
    version: str
    available: bool
    description: str
    citation: str
    license: str
    fda_status: str = Field(default="research_only", description="'research_only' or '510k_cleared'")
    required_inputs: List[str] = Field(default_factory=list, description="Required input types, e.g. ['T1w', 'FLAIR']")


# =============================================================================
# AI Service Interface
# =============================================================================

class IAISegmentationService(ABC):
    """
    Abstract interface for AI-powered brain segmentation and analysis.

    All methods return results compatible with the existing segmentation
    infrastructure (Uint8Array masks, binary protocol, Firestore metadata).
    """

    @abstractmethod
    async def segment_interactive(
        self,
        request: InteractiveSegmentRequest,
    ) -> AITaskResult:
        """
        Run interactive segmentation from user click points.

        The user clicks on a 2D slice and the AI generates a 3D mask
        of the indicated brain structure. Uses SAM-Med3D or nnInteractive.

        Returns:
            AITaskResult with task_id for polling, or completed result
        """
        pass

    @abstractmethod
    async def segment_auto(
        self,
        request: AutoSegmentRequest,
    ) -> AITaskResult:
        """
        Run automatic brain structure segmentation (SynthSeg).

        Segments 30+ brain structures from any MRI contrast:
        hippocampus, ventricles, cortex, white matter, thalamus, etc.

        Returns:
            AITaskResult with task_id for polling
        """
        pass

    @abstractmethod
    async def detect_anomalies(
        self,
        request: AnomalyDetectionRequest,
    ) -> AnomalyDetectionResult:
        """
        Detect brain anomalies (tumors, lesions, hemorrhages, infarcts).

        Returns a probability heatmap stored as a fractional segmentation
        and a list of detected anomalies with bounding boxes.
        """
        pass

    @abstractmethod
    async def get_task_status(
        self,
        task_id: str,
    ) -> AITaskResult:
        """
        Get the status of an async AI inference task.
        """
        pass

    @abstractmethod
    async def list_available_models(self) -> List[Dict[str, Any]]:
        """
        List available AI models and their configuration status.

        Returns:
            List of model info dicts with name, type, status, description
        """
        pass
