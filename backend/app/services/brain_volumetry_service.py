"""
Brain Volumetry Service.

Computes volumetric measurements of brain structures from segmentation masks.
Runs on CPU using numpy/scipy (no GPU required).

Features:
- Per-structure volume calculation (mm3 and mL)
- Comparison against normative data by age/sex
- Atrophy detection (hippocampal, ventricular enlargement)
- Longitudinal comparison across timepoints

@module services.brain_volumetry_service
"""

import time
import numpy as np
from typing import Optional, List, Dict, Tuple

from app.core.logging import get_logger
from app.core.interfaces.ai_interface import (
    BrainStructureVolume,
    VolumetryResult,
    VolumetryComparisonResult,
)

logger = get_logger(__name__)


# =============================================================================
# Normative Brain Structure Volumes (mL) by Age Group
# Source: FreeSurfer reference data (aggregated from large cohort studies)
# =============================================================================

# Format: {label_id: {age_group: (mean_ml, std_ml)}}
# Age groups: "20-40", "40-60", "60-80", "80+"
NORMATIVE_VOLUMES: Dict[int, Dict[str, Tuple[float, float]]] = {
    # Left Hippocampus
    17: {
        "20-40": (4.2, 0.5),
        "40-60": (3.9, 0.5),
        "60-80": (3.5, 0.6),
        "80+":   (3.0, 0.7),
    },
    # Right Hippocampus
    53: {
        "20-40": (4.3, 0.5),
        "40-60": (4.0, 0.5),
        "60-80": (3.6, 0.6),
        "80+":   (3.1, 0.7),
    },
    # Left Lateral Ventricle (increases with age/atrophy)
    4: {
        "20-40": (7.5, 3.5),
        "40-60": (10.0, 5.0),
        "60-80": (15.0, 8.0),
        "80+":   (22.0, 12.0),
    },
    # Right Lateral Ventricle
    43: {
        "20-40": (7.0, 3.5),
        "40-60": (9.5, 5.0),
        "60-80": (14.5, 8.0),
        "80+":   (21.0, 12.0),
    },
    # Left Thalamus
    10: {
        "20-40": (8.0, 0.8),
        "40-60": (7.5, 0.9),
        "60-80": (6.8, 1.0),
        "80+":   (6.0, 1.2),
    },
    # Right Thalamus
    49: {
        "20-40": (7.8, 0.8),
        "40-60": (7.3, 0.9),
        "60-80": (6.6, 1.0),
        "80+":   (5.8, 1.2),
    },
    # Left Caudate
    11: {
        "20-40": (3.8, 0.5),
        "40-60": (3.5, 0.5),
        "60-80": (3.1, 0.6),
        "80+":   (2.7, 0.6),
    },
    # Right Caudate
    50: {
        "20-40": (3.9, 0.5),
        "40-60": (3.6, 0.5),
        "60-80": (3.2, 0.6),
        "80+":   (2.8, 0.6),
    },
    # Left Putamen
    12: {
        "20-40": (5.5, 0.6),
        "40-60": (5.0, 0.7),
        "60-80": (4.5, 0.7),
        "80+":   (3.9, 0.8),
    },
    # Right Putamen
    51: {
        "20-40": (5.4, 0.6),
        "40-60": (4.9, 0.7),
        "60-80": (4.4, 0.7),
        "80+":   (3.8, 0.8),
    },
    # Brain Stem
    16: {
        "20-40": (22.0, 2.5),
        "40-60": (21.0, 2.5),
        "60-80": (20.0, 3.0),
        "80+":   (18.5, 3.5),
    },
}

# Structure names for volumetry output
STRUCTURE_NAMES: Dict[int, str] = {
    2: "Left Cerebral White Matter",
    3: "Left Cerebral Cortex",
    4: "Left Lateral Ventricle",
    5: "Left Inf Lat Ventricle",
    7: "Left Cerebellum White Matter",
    8: "Left Cerebellum Cortex",
    10: "Left Thalamus",
    11: "Left Caudate",
    12: "Left Putamen",
    13: "Left Pallidum",
    14: "3rd Ventricle",
    15: "4th Ventricle",
    16: "Brain Stem",
    17: "Left Hippocampus",
    18: "Left Amygdala",
    24: "CSF",
    26: "Left Accumbens",
    28: "Left VentralDC",
    41: "Right Cerebral White Matter",
    42: "Right Cerebral Cortex",
    43: "Right Lateral Ventricle",
    44: "Right Inf Lat Ventricle",
    46: "Right Cerebellum White Matter",
    47: "Right Cerebellum Cortex",
    49: "Right Thalamus",
    50: "Right Caudate",
    51: "Right Putamen",
    52: "Right Pallidum",
    53: "Right Hippocampus",
    54: "Right Amygdala",
    58: "Right Accumbens",
    60: "Right VentralDC",
}

# Ventricular label IDs (enlarge with atrophy)
VENTRICULAR_LABELS = {4, 43, 5, 44, 14, 15}

# Structures that decrease with atrophy
ATROPHY_SENSITIVE_LABELS = {17, 53, 10, 49, 11, 50, 12, 51}


class BrainVolumetryService:
    """
    Computes brain structure volumes from segmentation masks.

    Runs entirely on CPU — suitable for Cloud Run (2CPU/2GB).
    Uses numpy for voxel counting and volume calculation.
    """

    def __init__(self):
        logger.info("[BrainVolumetry] Service initialized")

    def _get_age_group(self, age: int) -> str:
        """Map patient age to normative age group."""
        if age < 40:
            return "20-40"
        elif age < 60:
            return "40-60"
        elif age < 80:
            return "60-80"
        else:
            return "80+"

    def _compute_percentile(
        self,
        volume_ml: float,
        label_id: int,
        age_group: str,
    ) -> Optional[float]:
        """
        Compute approximate percentile of a volume vs normative data.

        Uses z-score with normal distribution approximation.
        """
        if label_id not in NORMATIVE_VOLUMES:
            return None
        if age_group not in NORMATIVE_VOLUMES[label_id]:
            return None

        mean, std = NORMATIVE_VOLUMES[label_id][age_group]
        if std == 0:
            return 50.0

        z_score = (volume_ml - mean) / std

        # Approximate CDF with error function
        from math import erf, sqrt
        percentile = 50.0 * (1.0 + erf(z_score / sqrt(2.0)))
        return round(max(0.0, min(100.0, percentile)), 1)

    def compute_volumes(
        self,
        mask: np.ndarray,
        voxel_spacing: Tuple[float, float, float],
        segmentation_id: str,
        patient_age: Optional[int] = None,
        patient_sex: Optional[str] = None,
    ) -> VolumetryResult:
        """
        Compute volumes for all brain structures in a segmentation mask.

        Args:
            mask: 3D numpy array (depth, height, width) with integer labels
            voxel_spacing: (z_spacing, y_spacing, x_spacing) in mm
            segmentation_id: ID of the segmentation
            patient_age: Patient age for normative comparison
            patient_sex: Patient sex ('M' or 'F')

        Returns:
            VolumetryResult with per-structure volumes
        """
        start_time = time.time()

        # Voxel volume in mm3
        voxel_volume_mm3 = float(np.prod(voxel_spacing))

        # Find all unique labels in the mask
        unique_labels = np.unique(mask)

        age_group = self._get_age_group(patient_age) if patient_age else None

        structures: List[BrainStructureVolume] = []
        total_brain_voxels = 0
        intracranial_voxels = 0

        for label_id in unique_labels:
            label_id = int(label_id)
            if label_id == 0:
                continue

            # Count voxels for this label
            voxel_count = int(np.sum(mask == label_id))
            volume_mm3 = voxel_count * voxel_volume_mm3
            volume_ml = volume_mm3 / 1000.0

            # Determine structure name
            structure_name = STRUCTURE_NAMES.get(label_id, f"Structure {label_id}")

            # Compute normative percentile if age available
            percentile = None
            if age_group:
                percentile = self._compute_percentile(volume_ml, label_id, age_group)

            # Detect abnormality
            is_abnormal = False
            abnormality_type = None
            if percentile is not None:
                if label_id in VENTRICULAR_LABELS:
                    # Ventricles: abnormal if enlarged (> 90th percentile)
                    if percentile > 90.0:
                        is_abnormal = True
                        abnormality_type = "enlargement"
                elif label_id in ATROPHY_SENSITIVE_LABELS:
                    # Parenchymal structures: abnormal if atrophied (< 10th percentile)
                    if percentile < 10.0:
                        is_abnormal = True
                        abnormality_type = "atrophy"

            structures.append(BrainStructureVolume(
                label_id=label_id,
                structure_name=structure_name,
                volume_mm3=round(volume_mm3, 2),
                volume_ml=round(volume_ml, 3),
                normative_percentile=percentile,
                is_abnormal=is_abnormal,
                abnormality_type=abnormality_type,
            ))

            # Accumulate totals (all non-background is intracranial)
            intracranial_voxels += voxel_count
            if label_id not in VENTRICULAR_LABELS and label_id != 24:  # Exclude ventricles/CSF for brain volume
                total_brain_voxels += voxel_count

        total_brain_ml = round((total_brain_voxels * voxel_volume_mm3) / 1000.0, 2)
        intracranial_ml = round((intracranial_voxels * voxel_volume_mm3) / 1000.0, 2)

        elapsed_ms = int((time.time() - start_time) * 1000)

        logger.info(
            f"[BrainVolumetry] Computed volumes for {len(structures)} structures "
            f"in {elapsed_ms}ms. Total brain: {total_brain_ml}mL, ICV: {intracranial_ml}mL"
        )

        return VolumetryResult(
            segmentation_id=segmentation_id,
            structures=structures,
            total_brain_volume_ml=total_brain_ml,
            intracranial_volume_ml=intracranial_ml,
            processing_time_ms=elapsed_ms,
        )

    def compare_timepoints(
        self,
        patient_id: str,
        timepoints: List[Dict],
    ) -> VolumetryComparisonResult:
        """
        Compare brain volumes across multiple timepoints.

        Each timepoint should contain:
        - study_id: str
        - date: str (ISO format)
        - volumes: VolumetryResult

        Returns comparison with change percentages and trends.
        """
        if len(timepoints) < 2:
            return VolumetryComparisonResult(
                patient_id=patient_id,
                timepoints=timepoints,
                changes=[],
            )

        # Sort by date
        sorted_tp = sorted(timepoints, key=lambda t: t.get("date", ""))

        # Compare last vs first timepoint
        first = sorted_tp[0]
        last = sorted_tp[-1]

        changes = []

        first_vols = {s["label_id"]: s["volume_ml"] for s in first.get("structures", [])}
        last_vols = {s["label_id"]: s["volume_ml"] for s in last.get("structures", [])}

        for label_id in set(first_vols.keys()) & set(last_vols.keys()):
            vol_first = first_vols[label_id]
            vol_last = last_vols[label_id]

            if vol_first == 0:
                continue

            change_pct = round(((vol_last - vol_first) / vol_first) * 100.0, 2)

            # Determine trend
            if abs(change_pct) < 2.0:
                trend = "stable"
            elif change_pct > 0:
                trend = "increasing"
            else:
                trend = "decreasing"

            structure_name = STRUCTURE_NAMES.get(label_id, f"Structure {label_id}")

            changes.append({
                "label_id": label_id,
                "structure": structure_name,
                "volume_first_ml": vol_first,
                "volume_last_ml": vol_last,
                "change_percent": change_pct,
                "trend": trend,
            })

        logger.info(
            f"[BrainVolumetry] Longitudinal comparison: {len(sorted_tp)} timepoints, "
            f"{len(changes)} structures compared"
        )

        return VolumetryComparisonResult(
            patient_id=patient_id,
            timepoints=[{
                "study_id": tp.get("study_id"),
                "date": tp.get("date"),
            } for tp in sorted_tp],
            changes=changes,
        )
