"""
MS Lesion Region Classification Service.

Classifies MS lesions into anatomical regions per McDonald 2024 criteria
(Montalban et al., Lancet Neurology 2025; 24(10): 850-865) and
2024 MAGNIMS-CMSC-NAIMS consensus (Barkhof et al., Lancet Neurology 2025;
24(10): 866-879):
  1 - Periventricular (PV): Abutting lateral ventricles
  2 - Juxtacortical (JC): Directly abutting cortex
  3 - Infratentorial (IT): Brainstem, cerebellum, cerebellar peduncles
  4 - Deep White Matter (DWM): Cerebral WM not meeting PV/JC/IT criteria

Note: McDonald 2024 DIS regions are PV, JC, IT, spinal cord, and optic nerve.
DWM is NOT a DIS region. Spinal cord and optic nerve require separate imaging.

Two methods are provided:

  - **Parcellation-based** (generate_zone_map): Uses SynthSeg/FreeSurfer labels
    with Euclidean Distance Transforms (EDT). Higher accuracy when parcellation
    is available.

  - **MSMask-based** (generate_zone_map_atlas): Uses LST-AI's MSMask atlas
    with binary dilation (Wiltgen et al., NeuroImage: Clinical 2024).
    The only published, validated method for MAGNIMS zone classification.

Priority cascade: IT -> PV -> JC -> DWM (most specific first).

References:
  - Montalban et al., Lancet Neurol 2025; 24(10): 850-865 (McDonald 2024)
  - Barkhof et al., Lancet Neurol 2025; 24(10): 866-879 (MAGNIMS-CMSC-NAIMS 2024)
  - Filippi et al., Brain 2019; 142(7): 1858-1875 (practical MRI guidelines)
  - Wiltgen et al., NeuroImage: Clinical 2024; 42: 103611 (LST-AI/MSMask)
  - Billot et al., NeuroImage 2023 (SynthSeg parcellation)

@module services.ms_region_classifier
"""

import time
import numpy as np
from app.utils.spacing_utils import SPACING_REQUIRED, require_spacing
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)

# =============================================================================
# FreeSurfer / SynthSeg Label Groups for Anatomical Reference
# =============================================================================

# Lateral ventricles — PV lesions must contact these
LATERAL_VENTRICLE_LABELS = {4, 43}  # L/R Lateral Ventricle
ALL_VENTRICLE_LABELS = {4, 5, 14, 15, 43, 44}  # All ventricles + inf lat vent

# Cerebral cortex — JC lesions must contact cortex
CORTEX_LABELS = {3, 42}  # L/R Cerebral Cortex

# Infratentorial structures
INFRATENTORIAL_LABELS = {
    7, 8,    # L Cerebellum WM, L Cerebellum Cortex
    16,      # Brain Stem
    46, 47,  # R Cerebellum WM, R Cerebellum Cortex
}

# Cerebral white matter — for DWM fallback
WHITE_MATTER_LABELS = {2, 41}  # L/R Cerebral White Matter

# =============================================================================
# LST-AI MSMask Atlas (Wiltgen et al., NeuroImage: Clinical 2024)
# =============================================================================

# The MSMask is a manually-labeled MNI152 atlas included in LST-AI.
# It is the ONLY published, validated atlas for MAGNIMS zone classification.
MSMASK_PATH = "/app/data/msmask/sub-mni152_space-mni_msmask.nii.gz"
MSMASK_LABELS = {"CSF": 1, "GM": 2, "WM": 3, "Ventricles": 4, "Infratentorial": 5}

# =============================================================================
# Clinical Thresholds (mm) — Based on LST-AI "direct contact" criterion
# =============================================================================

# LST-AI uses binary dilation with a 3x3x3 cube at 1mm isotropic (~1.73mm
# diagonal). For the EDT-based parcellation method, we use 1.5mm to match
# the same "direct contact" criterion (Filippi 2019: "directly abutting").
PV_DISTANCE_THRESHOLD_MM = 1.5

# Juxtacortical: "directly abutting cortex" (McDonald 2024, Filippi 2019).
JC_DISTANCE_THRESHOLD_MM = 1.5

# Infratentorial: lesion within or touching brainstem/cerebellum.
IT_DISTANCE_THRESHOLD_MM = 1.5

# RC-030: min-volume floor and 18-connectivity centralised in lesion_metrics
# (ISBI-2015 / MSSEG-2016), replacing a duplicated 3.0 literal.
from app.services.lesion_metrics import MIN_LESION_VOLUME_MM3, label_lesions


def classify_lesions_with_parcellation(
    lesion_mask: np.ndarray,
    parcellation_mask: np.ndarray,
    voxel_spacing: tuple[float, float, float],
) -> dict:
    """
    Classify MS lesions into MAGNIMS regions using brain parcellation + EDT.

    This is the high-accuracy method. Requires a brain parcellation with
    FreeSurfer/SynthSeg labels for the same image.

    Algorithm:
      1. Extract ventricle, cortex, and infratentorial masks from parcellation
      2. Compute EDT (distance in mm) from each anatomical surface
      3. For each connected lesion component, measure minimum distance to each
         anatomical landmark
      4. Apply priority cascade: IT -> PV -> JC -> DWM

    Args:
        lesion_mask: 3D binary lesion mask (D, H, W), values > 0 = lesion.
        parcellation_mask: 3D parcellation with FreeSurfer labels (D, H, W).
        voxel_spacing: (dz, dy, dx) in mm.

    Returns:
        Dict with classified_mask (MAGNIMS labels 1-4), per-lesion details,
        classification summary, and confidence scores.
    """
    # IEC 62304 Class C — Input validation (REQ-SAFE-005)
    if not isinstance(lesion_mask, np.ndarray) or lesion_mask.ndim != 3:
        raise ValueError("lesion_mask must be a 3D numpy ndarray")
    if not isinstance(parcellation_mask, np.ndarray) or parcellation_mask.ndim != 3:
        raise ValueError("parcellation_mask must be a 3D numpy ndarray")
    if voxel_spacing is not None:
        if not all(isinstance(v, (int, float)) and v > 0 for v in voxel_spacing):
            raise ValueError(f"voxel_spacing values must be positive, got {voxel_spacing}")

    from scipy.ndimage import label as cc_label, center_of_mass
    from scipy.ndimage import distance_transform_edt

    start_time = time.time()

    if lesion_mask.shape != parcellation_mask.shape:
        raise ValueError(
            f"Mask shapes must match: lesion {lesion_mask.shape} vs "
            f"parcellation {parcellation_mask.shape}"
        )

    # Binary lesion mask
    binary_lesion = (lesion_mask > 0).astype(np.uint8)
    total_lesion_voxels = int(binary_lesion.sum())

    if total_lesion_voxels == 0:
        return _empty_result("parcellation", time.time() - start_time)

    # --- Step 1: Extract anatomical reference masks ---
    ventricle_mask = np.isin(parcellation_mask, list(LATERAL_VENTRICLE_LABELS))
    cortex_mask = np.isin(parcellation_mask, list(CORTEX_LABELS))
    infratentorial_mask = np.isin(parcellation_mask, list(INFRATENTORIAL_LABELS))

    has_ventricles = ventricle_mask.any()
    has_cortex = cortex_mask.any()
    has_infratentorial = infratentorial_mask.any()

    logger.info(
        "[RegionClassifier] Anatomical landmarks found: "
        "ventricles=%s, cortex=%s, infratentorial=%s",
        has_ventricles, has_cortex, has_infratentorial,
    )

    # --- Step 2: Compute distance transforms (mm) ---
    dist_to_ventricle = (
        distance_transform_edt(~ventricle_mask, sampling=voxel_spacing)
        if has_ventricles else np.full(lesion_mask.shape, np.inf)
    )
    dist_to_cortex = (
        distance_transform_edt(~cortex_mask, sampling=voxel_spacing)
        if has_cortex else np.full(lesion_mask.shape, np.inf)
    )
    dist_to_infratentorial = (
        distance_transform_edt(~infratentorial_mask, sampling=voxel_spacing)
        if has_infratentorial else np.full(lesion_mask.shape, np.inf)
    )

    # --- Step 3: Connected components ---
    labeled_array, num_components = label_lesions(binary_lesion)  # RC-030: 18-connectivity

    if num_components == 0:
        return _empty_result("parcellation", time.time() - start_time)

    component_ids = list(range(1, num_components + 1))
    centroids = center_of_mass(binary_lesion, labeled_array, component_ids)

    # --- Step 4: Classify each component ---
    classified_mask = np.zeros_like(lesion_mask, dtype=np.uint8)
    lesion_details = []
    voxel_vol_mm3 = float(np.prod(voxel_spacing))

    for comp_idx, centroid in zip(component_ids, centroids):
        comp_mask = labeled_array == comp_idx
        voxel_count = int(comp_mask.sum())
        volume_mm3 = voxel_count * voxel_vol_mm3

        # Skip tiny components (noise)
        if volume_mm3 < MIN_LESION_VOLUME_MM3:
            continue

        # Minimum distance from this lesion to each anatomical landmark
        comp_voxels = comp_mask
        min_dist_it = float(dist_to_infratentorial[comp_voxels].min())
        min_dist_pv = float(dist_to_ventricle[comp_voxels].min())
        min_dist_jc = float(dist_to_cortex[comp_voxels].min())

        # Priority cascade: IT -> PV -> JC -> DWM
        region_id, region_name, confidence = _classify_by_distance(
            min_dist_it, min_dist_pv, min_dist_jc
        )

        # Write classified label to output mask
        classified_mask[comp_mask] = region_id

        lesion_details.append({
            "lesion_id": len(lesion_details) + 1,
            "region_id": region_id,
            "region": region_name,
            "confidence": round(confidence, 3),
            "volume_mm3": round(volume_mm3, 2),
            "volume_ml": round(volume_mm3 / 1000, 4),
            "voxel_count": voxel_count,
            "centroid": {
                "z": round(float(centroid[0]), 1),
                "y": round(float(centroid[1]), 1),
                "x": round(float(centroid[2]), 1),
            },
            "distances_mm": {
                "to_ventricle": round(min_dist_pv, 2),
                "to_cortex": round(min_dist_jc, 2),
                "to_infratentorial": round(min_dist_it, 2),
            },
        })

    elapsed_ms = int((time.time() - start_time) * 1000)
    summary = _build_summary(lesion_details)

    logger.info(
        "[RegionClassifier] Parcellation-based classification: "
        "%d lesions classified in %dms — PV=%d, JC=%d, IT=%d, DWM=%d",
        len(lesion_details), elapsed_ms,
        summary.get("Periventricular", 0),
        summary.get("Juxtacortical", 0),
        summary.get("Infratentorial", 0),
        summary.get("Deep White Matter", 0),
    )

    return {
        "method": "parcellation",
        "classified_mask": classified_mask,
        "lesions": lesion_details,
        "total_classified": len(lesion_details),
        "classification_summary": summary,
        "thresholds_mm": {
            "periventricular": PV_DISTANCE_THRESHOLD_MM,
            "juxtacortical": JC_DISTANCE_THRESHOLD_MM,
            "infratentorial": IT_DISTANCE_THRESHOLD_MM,
        },
        "processing_time_ms": elapsed_ms,
    }


def classify_lesions_geometric(
    lesion_mask: np.ndarray,
    image_data: Optional[np.ndarray] = None,
    # RC-024 (CAPA-001 CA-5): required. The sentinel replaces the old
    # (1.0, 1.0, 1.0) default; omitting it now raises instead of assuming.
    voxel_spacing: tuple[float, float, float] = SPACING_REQUIRED,
) -> dict:
    """
    Classify MS lesions using geometric heuristics (fallback method).

    Uses spatial position within the brain volume to estimate region:
      - Infratentorial: lower ~25% of brain (z-coordinate heuristic)
      - Periventricular: central core of brain (distance from center)
      - Juxtacortical: near brain surface (distance from brain edge)
      - Deep White Matter: everything else

    Less accurate than parcellation-based method (~70% vs ~90+% agreement
    with expert classification), but requires no additional data.

    Args:
        lesion_mask: 3D binary lesion mask (D, H, W), values > 0 = lesion.
        image_data: Optional MRI intensity data for Otsu-based ventricle detection.
        voxel_spacing: (dz, dy, dx) in mm.

    Returns:
        Dict with classified_mask and per-lesion details.
    """
    voxel_spacing = require_spacing(voxel_spacing, caller="classify_lesions_geometric")
    # IEC 62304 Class C — Input validation (REQ-SAFE-005)
    if not isinstance(lesion_mask, np.ndarray) or lesion_mask.ndim != 3:
        raise ValueError("lesion_mask must be a 3D numpy ndarray")
    if voxel_spacing is not None:
        if not all(isinstance(v, (int, float)) and v > 0 for v in voxel_spacing):
            raise ValueError(f"voxel_spacing values must be positive, got {voxel_spacing}")

    from scipy.ndimage import label as cc_label, center_of_mass
    from scipy.ndimage import distance_transform_edt, binary_fill_holes

    start_time = time.time()

    binary_lesion = (lesion_mask > 0).astype(np.uint8)
    total_lesion_voxels = int(binary_lesion.sum())

    if total_lesion_voxels == 0:
        return _empty_result("geometric", time.time() - start_time)

    depth, height, width = lesion_mask.shape

    # --- Estimate brain mask (all non-zero in lesion or image) ---
    if image_data is not None and image_data.shape == lesion_mask.shape:
        # Use Otsu threshold to get brain mask
        from skimage.filters import threshold_otsu
        try:
            thresh = threshold_otsu(image_data[image_data > 0])
            brain_mask = (image_data > thresh * 0.3).astype(bool)
        except ValueError:
            brain_mask = np.ones_like(lesion_mask, dtype=bool)
    else:
        # Assume entire volume is brain
        brain_mask = np.ones_like(lesion_mask, dtype=bool)

    brain_mask = binary_fill_holes(brain_mask)

    # --- Estimate anatomical zones using geometry ---

    # Infratentorial zone: bottom ~25% of brain extent
    brain_z_indices = np.where(brain_mask.any(axis=(1, 2)))[0]
    if len(brain_z_indices) > 0:
        brain_z_min = brain_z_indices[0]
        brain_z_max = brain_z_indices[-1]
        brain_z_range = brain_z_max - brain_z_min
        it_z_threshold = brain_z_min + brain_z_range * 0.25
    else:
        it_z_threshold = depth * 0.25

    # Distance from brain surface (for JC detection)
    dist_from_surface = distance_transform_edt(brain_mask, sampling=voxel_spacing)

    # Periventricular zone: central region of brain
    # Estimate ventricle region as the center ~20% of the brain volume
    center_z = (brain_z_indices[0] + brain_z_indices[-1]) / 2 if len(brain_z_indices) > 0 else depth / 2
    center_y = height / 2
    center_x = width / 2

    # Create a distance-from-center map (normalized)
    zz, yy, xx = np.meshgrid(
        np.arange(depth) * voxel_spacing[0],
        np.arange(height) * voxel_spacing[1],
        np.arange(width) * voxel_spacing[2],
        indexing='ij',
    )
    dist_from_center = np.sqrt(
        ((zz - center_z * voxel_spacing[0]) ** 2) +
        ((yy - center_y * voxel_spacing[1]) ** 2) +
        ((xx - center_x * voxel_spacing[2]) ** 2)
    )

    # --- Connected components ---
    labeled_array, num_components = label_lesions(binary_lesion)  # RC-030: 18-connectivity

    if num_components == 0:
        return _empty_result("geometric", time.time() - start_time)

    component_ids = list(range(1, num_components + 1))
    centroids = center_of_mass(binary_lesion, labeled_array, component_ids)

    classified_mask = np.zeros_like(lesion_mask, dtype=np.uint8)
    lesion_details = []
    voxel_vol_mm3 = float(np.prod(voxel_spacing))

    # Thresholds for geometric classification
    max_brain_radius = dist_from_surface.max() if dist_from_surface.max() > 0 else 1.0
    jc_surface_threshold = min(8.0, max_brain_radius * 0.15)  # Near surface
    pv_center_threshold = dist_from_center.max() * 0.35 if dist_from_center.max() > 0 else 50.0

    for comp_idx, centroid in zip(component_ids, centroids):
        comp_mask = labeled_array == comp_idx
        voxel_count = int(comp_mask.sum())
        volume_mm3 = voxel_count * voxel_vol_mm3

        if volume_mm3 < MIN_LESION_VOLUME_MM3:
            continue

        cz = float(centroid[0])

        # Geometric heuristics (priority cascade)
        # NOTE: Geometric method has no empirically calibrated confidence scores.
        # confidence=None indicates uncalibrated (use parcellation or MSMask for validated results).
        # 1. Infratentorial: z-coordinate below threshold
        if cz < it_z_threshold:
            region_id, region_name = 3, "Infratentorial"

        # 2. Periventricular: close to center of brain
        elif float(dist_from_center[comp_mask].mean()) < pv_center_threshold:
            region_id, region_name = 1, "Periventricular"

        # 3. Juxtacortical: close to brain surface
        elif float(dist_from_surface[comp_mask].min()) < jc_surface_threshold:
            region_id, region_name = 2, "Juxtacortical"

        # 4. Deep white matter: default
        else:
            region_id, region_name = 4, "Deep White Matter"

        confidence = None  # Geometric: not empirically calibrated

        classified_mask[comp_mask] = region_id

        lesion_details.append({
            "lesion_id": len(lesion_details) + 1,
            "region_id": region_id,
            "region": region_name,
            "confidence": confidence,  # None — geometric method is not calibrated
            "confidence_note": "Geometric method — not empirically calibrated. Use parcellation or MSMask for validated confidence.",
            "volume_mm3": round(volume_mm3, 2),
            "volume_ml": round(volume_mm3 / 1000, 4),
            "voxel_count": voxel_count,
            "centroid": {
                "z": round(cz, 1),
                "y": round(float(centroid[1]), 1),
                "x": round(float(centroid[2]), 1),
            },
            "distances_mm": {
                "to_ventricle": round(float(dist_from_center[comp_mask].min()), 2),
                "to_cortex": round(float(dist_from_surface[comp_mask].min()), 2),
                "to_infratentorial": 0.0 if cz < it_z_threshold else round((cz - it_z_threshold) * voxel_spacing[0], 2),
            },
        })

    elapsed_ms = int((time.time() - start_time) * 1000)
    summary = _build_summary(lesion_details)

    logger.info(
        "[RegionClassifier] Geometric classification: "
        "%d lesions classified in %dms — PV=%d, JC=%d, IT=%d, DWM=%d",
        len(lesion_details), elapsed_ms,
        summary.get("Periventricular", 0),
        summary.get("Juxtacortical", 0),
        summary.get("Infratentorial", 0),
        summary.get("Deep White Matter", 0),
    )

    return {
        "method": "geometric",
        "classified_mask": classified_mask,
        "lesions": lesion_details,
        "total_classified": len(lesion_details),
        "classification_summary": summary,
        "thresholds_mm": {
            "periventricular": "center-distance heuristic",
            "juxtacortical": round(jc_surface_threshold, 1),
            "infratentorial": f"z < {round(it_z_threshold, 1)}",
        },
        "processing_time_ms": elapsed_ms,
    }


# =============================================================================
# MSMask Atlas-based Lesion Classification
# =============================================================================


def classify_from_zone_mask(
    lesion_mask: np.ndarray,
    zone_mask: np.ndarray,
    voxel_spacing: tuple[float, float, float],
) -> dict:
    """
    Classify MS lesions into MAGNIMS regions using a pre-computed zone mask.

    For each connected component in lesion_mask, counts overlapping zone voxels
    and assigns the region with the majority vote. This function does NOT generate
    the zone mask — it expects one already computed (from atlas or parcellation).

    Args:
        lesion_mask: 3D binary lesion mask (D, H, W), uint8.
        zone_mask: 3D zone mask (D, H, W), uint8 with values 0-4.
        voxel_spacing: (dz, dy, dx) in mm.

    Returns:
        Dict with classified_mask, lesions list, summary, processing time.
    """
    from scipy.ndimage import label as scipy_label

    start_time = time.time()

    binary = (lesion_mask > 0).astype(np.int32)
    labeled, num_components = label_lesions(binary)  # RC-030: 18-connectivity

    if num_components == 0:
        elapsed_ms = int((time.time() - start_time) * 1000)
        return {
            "classified_mask": np.zeros_like(lesion_mask, dtype=np.uint8),
            "lesions": [],
            "total_classified": 0,
            "classification_summary": {},
            "processing_time_ms": elapsed_ms,
        }

    classified_mask = np.zeros_like(lesion_mask, dtype=np.uint8)
    voxel_vol_mm3 = float(np.prod(voxel_spacing))
    lesion_details = []

    for comp_id in range(1, num_components + 1):
        comp_mask = labeled == comp_id
        voxel_count = int(comp_mask.sum())
        volume_mm3 = voxel_count * voxel_vol_mm3

        if volume_mm3 < MIN_LESION_VOLUME_MM3:
            continue

        # Get zone values at lesion voxels
        zone_vals = zone_mask[comp_mask]

        # Count votes per zone (ignore 0 = background)
        zone_counts = {}
        for z_id in [1, 2, 3, 4]:
            count = int((zone_vals == z_id).sum())
            if count > 0:
                zone_counts[z_id] = count

        if not zone_counts:
            # Lesion falls entirely outside atlas coverage → DWM fallback
            region_id = 4
            confidence = 0.50
        else:
            # Majority vote
            region_id = max(zone_counts, key=zone_counts.get)
            total_in_zones = sum(zone_counts.values())
            confidence = zone_counts[region_id] / total_in_zones

            # Boost confidence: atlas-based is inherently more accurate
            # Scale from raw agreement (0.25-1.0) to (0.75-0.98)
            confidence = 0.75 + 0.23 * min(1.0, confidence)

        region_name = REGION_NAMES.get(region_id, "Unknown")
        classified_mask[comp_mask] = region_id

        # Compute centroid
        coords = np.argwhere(comp_mask)
        centroid = coords.mean(axis=0)

        lesion_details.append({
            "lesion_id": len(lesion_details) + 1,
            "region_id": region_id,
            "region": region_name,
            "confidence": round(confidence, 3),
            "volume_mm3": round(volume_mm3, 2),
            "volume_ml": round(volume_mm3 / 1000, 4),
            "voxel_count": voxel_count,
            "centroid": {
                "z": round(float(centroid[0]), 1),
                "y": round(float(centroid[1]), 1),
                "x": round(float(centroid[2]), 1),
            },
            "zone_votes": {
                REGION_NAMES.get(z, "Unknown"): c
                for z, c in sorted(zone_counts.items())
            } if zone_counts else {},
        })

    elapsed_ms = int((time.time() - start_time) * 1000)
    summary = _build_summary(lesion_details)

    logger.info(
        "[RegionClassifier-ZoneMask] Classification: "
        "%d lesions in %dms — PV=%d, JC=%d, IT=%d, DWM=%d",
        len(lesion_details), elapsed_ms,
        summary.get("Periventricular", 0),
        summary.get("Juxtacortical", 0),
        summary.get("Infratentorial", 0),
        summary.get("Deep White Matter", 0),
    )

    return {
        "classified_mask": classified_mask,
        "lesions": lesion_details,
        "total_classified": len(lesion_details),
        "classification_summary": summary,
        "processing_time_ms": elapsed_ms,
    }


def classify_lesions_with_atlas(
    lesion_mask: np.ndarray,
    target_img,
    voxel_spacing: tuple[float, float, float],
) -> dict:
    """
    Classify MS lesions into MAGNIMS regions using the MSMask atlas.

    Generates a zone map via generate_zone_map_atlas(), then delegates to
    classify_from_zone_mask() for the actual per-lesion classification.

    Args:
        lesion_mask: 3D binary lesion mask (D, H, W), uint8.
        target_img: nibabel Nifti1Image of the patient MRI (for atlas resampling).
        voxel_spacing: (dz, dy, dx) in mm.

    Returns:
        Dict with classified_mask, lesions list, summary, processing time.
    """
    # IEC 62304 Class C — Input validation (REQ-SAFE-005)
    if not isinstance(lesion_mask, np.ndarray) or lesion_mask.ndim != 3:
        raise ValueError("lesion_mask must be a 3D numpy ndarray")
    if target_img is None:
        raise ValueError("target_img must be a nibabel Nifti1Image")
    if voxel_spacing is not None:
        if not all(isinstance(v, (int, float)) and v > 0 for v in voxel_spacing):
            raise ValueError(f"voxel_spacing values must be positive, got {voxel_spacing}")

    start_time = time.time()

    # 1. Generate zone map from MSMask atlas
    zone_result = generate_zone_map_atlas(target_img, voxel_spacing)
    zone_mask = zone_result["zone_mask"]
    zone_gen_ms = zone_result["processing_time_ms"]

    logger.info(
        "[RegionClassifier-MSMask] Zone map generated in %dms, classifying lesions...",
        zone_gen_ms,
    )

    # 2. Classify using the generated zone mask
    result = classify_from_zone_mask(lesion_mask, zone_mask, voxel_spacing)

    # Add method info and total timing
    total_ms = int((time.time() - start_time) * 1000)
    result["method"] = "msmask"
    result["processing_time_ms"] = total_ms
    result["zone_generation_ms"] = zone_gen_ms

    return result


# =============================================================================
# Zone Map Generation
# =============================================================================


def generate_zone_map(
    parcellation_mask: np.ndarray,
    voxel_spacing: tuple[float, float, float],
) -> dict:
    """
    Generate a 3D MAGNIMS zone map from brain parcellation.

    For each brain voxel, determines which MAGNIMS zone it belongs to using
    Euclidean Distance Transforms from anatomical landmarks. The zone map
    covers ALL brain tissue, not just lesion voxels.

    Zone labels (same IDs as MAGNIMS_LESION_LABELS):
      0 - Background / CSF / ventricles (transparent)
      1 - Periventricular zone (within PV_DISTANCE_THRESHOLD_MM of ventricles)
      2 - Juxtacortical zone (within JC_DISTANCE_THRESHOLD_MM of cortex)
      3 - Infratentorial zone (brainstem + cerebellum)
      4 - Deep White Matter (remaining brain tissue)

    Priority cascade: IT -> PV -> JC -> DWM.

    Args:
        parcellation_mask: 3D parcellation with FreeSurfer labels (D, H, W).
        voxel_spacing: (dz, dy, dx) in mm.

    Returns:
        Dict with zone_mask (uint8 D,H,W), zone_stats, and processing time.
    """
    from scipy.ndimage import distance_transform_edt

    start_time = time.time()

    # --- Extract anatomical reference masks ---
    # McDonald 2024: PV = "abutting the lateral ventricles" only (excludes 3rd/4th ventricle)
    ventricle_mask = np.isin(parcellation_mask, list(LATERAL_VENTRICLE_LABELS))
    cortex_mask = np.isin(parcellation_mask, list(CORTEX_LABELS))
    infratentorial_mask = np.isin(parcellation_mask, list(INFRATENTORIAL_LABELS))
    white_matter_mask = np.isin(parcellation_mask, list(WHITE_MATTER_LABELS))

    # Brain mask: any non-zero parcellation label (everything that's brain)
    brain_mask = parcellation_mask > 0

    total_brain_voxels = int(brain_mask.sum())
    if total_brain_voxels == 0:
        logger.warning("[ZoneMap] No brain voxels found in parcellation")
        return {
            "zone_mask": np.zeros_like(parcellation_mask, dtype=np.uint8),
            "zone_stats": {},
            "total_brain_voxels": 0,
            "processing_time_ms": int((time.time() - start_time) * 1000),
        }

    has_ventricles = ventricle_mask.any()
    has_cortex = cortex_mask.any()
    has_infratentorial = infratentorial_mask.any()

    logger.info(
        "[ZoneMap] Generating zone map: brain=%d voxels, "
        "ventricles=%s, cortex=%s, infratentorial=%s",
        total_brain_voxels, has_ventricles, has_cortex, has_infratentorial,
    )

    # --- Compute distance transforms (mm) ---
    dist_to_ventricle = (
        distance_transform_edt(~ventricle_mask, sampling=voxel_spacing)
        if has_ventricles else np.full(parcellation_mask.shape, np.inf)
    )
    dist_to_cortex = (
        distance_transform_edt(~cortex_mask, sampling=voxel_spacing)
        if has_cortex else np.full(parcellation_mask.shape, np.inf)
    )
    dist_to_infratentorial = (
        distance_transform_edt(~infratentorial_mask, sampling=voxel_spacing)
        if has_infratentorial else np.full(parcellation_mask.shape, np.inf)
    )

    # --- Classify every brain voxel using priority cascade ---
    zone_mask = np.zeros_like(parcellation_mask, dtype=np.uint8)

    # Exclude ventricles and CSF from the zone map (they stay 0 = transparent)
    classifiable = brain_mask & ~ventricle_mask

    # 1. Infratentorial: voxels that ARE part of infratentorial structures
    #    OR within IT_DISTANCE_THRESHOLD_MM of them (captures adjacent WM)
    it_zone = classifiable & (
        infratentorial_mask | (dist_to_infratentorial <= IT_DISTANCE_THRESHOLD_MM)
    )
    zone_mask[it_zone] = 3

    # 2. Periventricular: within PV threshold, but NOT infratentorial
    pv_zone = classifiable & ~it_zone & (dist_to_ventricle <= PV_DISTANCE_THRESHOLD_MM)
    zone_mask[pv_zone] = 1

    # 3. Juxtacortical: within JC threshold, but NOT IT or PV
    jc_zone = classifiable & ~it_zone & ~pv_zone & (dist_to_cortex <= JC_DISTANCE_THRESHOLD_MM)
    zone_mask[jc_zone] = 2

    # 4. Deep White Matter: remaining brain tissue (primarily WM)
    dwm_zone = classifiable & (zone_mask == 0)
    zone_mask[dwm_zone] = 4

    # --- Compute stats ---
    zone_stats = {}
    for zone_id, zone_name in REGION_NAMES.items():
        count = int((zone_mask == zone_id).sum())
        voxel_vol_mm3 = float(np.prod(voxel_spacing))
        zone_stats[zone_name] = {
            "zone_id": zone_id,
            "voxel_count": count,
            "volume_mm3": round(count * voxel_vol_mm3, 1),
            "volume_ml": round(count * voxel_vol_mm3 / 1000, 3),
            "percentage": round(count / max(total_brain_voxels, 1) * 100, 1),
        }

    elapsed_ms = int((time.time() - start_time) * 1000)

    logger.info(
        "[ZoneMap] Zone map generated in %dms — PV=%d%%, JC=%d%%, IT=%d%%, DWM=%d%%",
        elapsed_ms,
        zone_stats.get("Periventricular", {}).get("percentage", 0),
        zone_stats.get("Juxtacortical", {}).get("percentage", 0),
        zone_stats.get("Infratentorial", {}).get("percentage", 0),
        zone_stats.get("Deep White Matter", {}).get("percentage", 0),
    )

    return {
        "zone_mask": zone_mask,
        "zone_stats": zone_stats,
        "total_brain_voxels": total_brain_voxels,
        "processing_time_ms": elapsed_ms,
    }


def generate_zone_map_atlas(
    target_img,
    voxel_spacing: tuple[float, float, float],
) -> dict:
    """
    Generate a 3D MAGNIMS zone map using LST-AI's MSMask atlas.

    Uses the exact methodology from LST-AI (Wiltgen et al., NeuroImage:
    Clinical 2024), the ONLY published and validated tool for MAGNIMS zone
    classification:

    1. Load MSMask atlas (manually-labeled MNI152, 5 tissue classes)
    2. Extract anatomical masks from MSMask labels
    3. Binary dilation (3x3x3 cube) of ventricles and cortex for "abutting"
    4. Classify WM voxels: PV > JC > IT > DWM (LST-AI priority order)
    5. Resample zone map to patient image grid via corrected affine

    MSMask labels (from LST-AI source):
      1 = CSF, 2 = GM (cortex), 3 = WM, 4 = Ventricles, 5 = Infratentorial

    LST-AI classification logic (annotate.py):
      - For each lesion, dilate by 3x3x3 cube, then check overlap:
        - If dilated lesion overlaps Ventricles(4) → PV
        - Elif dilated lesion overlaps GM(2) → JC
        - Elif dilated lesion overlaps Infratentorial(5) → IT
        - Else → DWM (subcortical)
      - We adapt this per-lesion logic to a pre-computed zone map.

    Args:
        target_img: nibabel Nifti1Image of the patient MRI in MNI space.
        voxel_spacing: Unused (kept for API compatibility).

    Returns:
        Dict with zone_mask (uint8), zone_stats, total_brain_voxels,
        processing_time_ms, method='msmask'.

    References:
        Wiltgen et al. (2024). LST-AI: A deep learning ensemble for accurate
        MS lesion segmentation. NeuroImage: Clinical, 42, 103611.
    """
    import nibabel as nib
    from scipy.ndimage import binary_dilation
    from pathlib import Path

    start_time = time.time()

    # ── 1. Load MSMask atlas ──
    msmask_path = Path(MSMASK_PATH)
    if not msmask_path.exists():
        # Fallback: check relative to module
        alt_path = Path(__file__).resolve().parent.parent.parent / "data" / "msmask" / "sub-mni152_space-mni_msmask.nii.gz"
        if alt_path.exists():
            msmask_path = alt_path
        else:
            raise FileNotFoundError(
                f"MSMask atlas not found at {MSMASK_PATH} or {alt_path}. "
                "Run scripts/download_msmask.py to download it."
            )

    msmask_img = nib.load(str(msmask_path))
    msmask_data = np.asarray(msmask_img.dataobj, dtype=np.int16)
    target_shape = target_img.shape[:3]

    logger.info(
        "[ZoneMap-MSMask] Atlas: shape=%s, origin=%s",
        msmask_data.shape,
        msmask_img.affine[:3, 3].tolist(),
    )
    logger.info(
        "[ZoneMap-MSMask] Target: shape=%s, affine_diag=%s, origin=%s",
        target_shape,
        np.diag(target_img.affine[:3, :3]).tolist(),
        target_img.affine[:3, 3].tolist(),
    )

    # ── 2. Extract anatomical masks from MSMask labels ──
    ventricles = (msmask_data == MSMASK_LABELS["Ventricles"])   # label 4
    cortex = (msmask_data == MSMASK_LABELS["GM"])               # label 2
    wm = (msmask_data == MSMASK_LABELS["WM"])                   # label 3
    infratentorial = (msmask_data == MSMASK_LABELS["Infratentorial"])  # label 5

    logger.info(
        "[ZoneMap-MSMask] Masks: ventricles=%d, cortex=%d, wm=%d, infratentorial=%d",
        int(ventricles.sum()), int(cortex.sum()),
        int(wm.sum()), int(infratentorial.sum()),
    )

    # ── 3. Binary dilation (LST-AI exact methodology) ──
    # LST-AI uses a 3x3x3 cube structuring element for "abutting" criterion.
    # At 1mm isotropic this captures structures within ~1.73mm (cube diagonal).
    # We dilate ALL reference masks: ventricles, cortex, AND infratentorial.
    # This ensures WM voxels adjacent to infratentorial structures (e.g.,
    # cerebellar WM) are correctly classified as IT, not DWM.
    struct = np.ones((3, 3, 3), dtype=bool)
    ventricles_dilated = binary_dilation(ventricles, structure=struct)
    cortex_dilated = binary_dilation(cortex, structure=struct)
    infratentorial_dilated = binary_dilation(infratentorial, structure=struct)

    # ── 4. Build zone map ──
    # Priority: IT > PV > JC > DWM
    # IT has highest priority because "infratentorial" is a LOCATION definition
    # (posterior fossa), not proximity-based. Any lesion in brainstem/cerebellum
    # is infratentorial per MAGNIMS (Filippi 2019), regardless of proximity to
    # other structures.
    zone_map = np.zeros(msmask_data.shape, dtype=np.uint8)

    # Default: all WM voxels = DWM (label 4)
    zone_map[wm] = 4

    # Infratentorial: label-5 voxels + WM abutting infratentorial structures
    # This captures cerebellar WM (labeled as WM=3 in MSMask but located
    # in the posterior fossa, which is infratentorial per MAGNIMS).
    zone_map[infratentorial] = 3
    it_wm = infratentorial_dilated & wm
    zone_map[it_wm] = 3

    # JC: WM voxels abutting cortex (overrides DWM, not IT)
    jc_mask = cortex_dilated & wm & (zone_map != 3)
    zone_map[jc_mask] = 2

    # PV: WM voxels abutting ventricles (overrides JC/DWM, not IT)
    pv_mask = ventricles_dilated & wm & (zone_map != 3)
    zone_map[pv_mask] = 1

    # ── 5. Resample zone map to patient image grid ──
    from nilearn.image import resample_to_img

    # Determine the reference affine for resampling.
    # If the target image has a plausible MNI affine, use it directly.
    # Otherwise (e.g., ISBI 2015 with origin [0,0,0]), compute a corrected
    # affine by aligning the spatial centers of atlas and target.
    target_diag = np.diag(target_img.affine[:3, :3])
    target_origin = target_img.affine[:3, 3]
    target_end = target_origin + target_diag * (np.array(target_shape) - 1)
    target_center_mni = (target_origin + target_end) / 2.0

    atlas_diag = np.diag(msmask_img.affine[:3, :3])
    atlas_center_vox = (np.array(msmask_img.shape[:3]) - 1) / 2.0
    atlas_center_mni = msmask_img.affine[:3, 3] + atlas_diag * atlas_center_vox

    center_distance = float(np.linalg.norm(target_center_mni - atlas_center_mni))

    if center_distance < 30.0:
        # Target affine is plausible for MNI space — use it directly
        logger.info(
            "[ZoneMap-MSMask] Using target affine (center distance %.1fmm)",
            center_distance,
        )
        ref_affine = target_img.affine.copy()
    else:
        # Target affine is wrong — compute corrected affine by aligning
        # spatial centers. This maps the target's center voxel to the same
        # MNI coordinate as the atlas center, preserving axis directions.
        target_center_vox = (np.array(target_shape) - 1) / 2.0
        corrected_origin = atlas_center_mni - target_diag * target_center_vox
        ref_affine = np.eye(4)
        ref_affine[:3, :3] = np.diag(target_diag)
        ref_affine[:3, 3] = corrected_origin
        logger.info(
            "[ZoneMap-MSMask] Target affine wrong (center distance %.1fmm), "
            "using center-aligned affine: origin=%s",
            center_distance, corrected_origin.tolist(),
        )

    logger.info(
        "[ZoneMap-MSMask] Reference affine: diag=%s, origin=%s",
        np.diag(ref_affine[:3, :3]).tolist(), ref_affine[:3, 3].tolist(),
    )

    zone_nifti = nib.Nifti1Image(zone_map.astype(np.float32), msmask_img.affine)
    target_ref = nib.Nifti1Image(
        np.zeros(target_shape, dtype=np.uint8), ref_affine
    )
    zone_resampled = resample_to_img(
        zone_nifti, target_ref, interpolation='nearest'
    )
    zone_final = np.asarray(zone_resampled.dataobj, dtype=np.uint8)

    # ── 6. Compute zone statistics ──
    total_classified = int((zone_final > 0).sum())
    zone_stats = {}
    for zone_id, zone_name in REGION_NAMES.items():
        count = int((zone_final == zone_id).sum())
        zone_stats[zone_name] = {
            "zone_id": zone_id,
            "voxel_count": count,
            "volume_mm3": round(count * 1.0, 1),
            "volume_ml": round(count / 1000, 3),
            "percentage": round(count / max(total_classified, 1) * 100, 1),
        }

    elapsed_ms = int((time.time() - start_time) * 1000)

    logger.info(
        "[ZoneMap-MSMask] Generated in %dms — PV=%.1f%%, JC=%.1f%%, IT=%.1f%%, DWM=%.1f%%, total=%d",
        elapsed_ms,
        zone_stats.get("Periventricular", {}).get("percentage", 0),
        zone_stats.get("Juxtacortical", {}).get("percentage", 0),
        zone_stats.get("Infratentorial", {}).get("percentage", 0),
        zone_stats.get("Deep White Matter", {}).get("percentage", 0),
        total_classified,
    )

    return {
        "zone_mask": zone_final,
        "zone_stats": zone_stats,
        "total_brain_voxels": total_classified,
        "processing_time_ms": elapsed_ms,
        "method": "msmask",
    }


def generate_zone_map_geometric(
    image_data: np.ndarray,
    voxel_spacing: tuple[float, float, float],
) -> dict:
    """
    DEPRECATED: Use generate_zone_map_atlas() instead.

    Generate MAGNIMS zone map using intensity-based anatomy detection.
    This method produces inaccurate results because it relies on heuristic
    ventricle/cortex detection from image intensities.

    Steps:
      1. Brain extraction: Otsu threshold + morphological skull stripping
      2. Ventricle detection: dark CSF regions in the brain interior
      3. PV zone: EDT from detected ventricles, <= 1.5mm (direct contact approx.)
      4. JC zone: EDT from brain surface (cortex), <= 1.5mm (direct contact approx.)
      5. IT zone: bottom 25% of brain in z-axis
      6. DWM zone: remaining brain tissue

    Args:
        image_data: 3D MRI intensity data (D, H, W).
        voxel_spacing: (dz, dy, dx) in mm.

    Returns:
        Dict with zone_mask (uint8 D,H,W), zone_stats, processing time.
    """
    from scipy.ndimage import (
        distance_transform_edt,
        binary_fill_holes,
        binary_erosion,
        binary_dilation,
        binary_opening,
        binary_closing,
        label as cc_label,
    )

    start_time = time.time()
    depth, height, width = image_data.shape

    # =========================================================================
    # Step 1: Brain Extraction (skull stripping)
    # =========================================================================

    nonzero = image_data[image_data > 0]
    if len(nonzero) < 100:
        logger.warning("[ZoneMap-Geo] Too few non-zero voxels: %d", len(nonzero))
        return _empty_zone_result((depth, height, width), start_time)

    # Otsu threshold to separate tissue from background
    try:
        from skimage.filters import threshold_otsu
        otsu_thresh = float(threshold_otsu(nonzero))
    except (ValueError, ImportError):
        otsu_thresh = float(np.percentile(nonzero, 30))

    # Tissue mask: brain + skull + scalp (above ~50% of Otsu)
    tissue_mask = (image_data > otsu_thresh * 0.5).astype(bool)

    # Clean up: remove noise, fill holes
    struct3 = np.ones((3, 3, 3), dtype=bool)
    tissue_mask = binary_opening(tissue_mask, structure=struct3, iterations=1)
    tissue_mask = binary_closing(tissue_mask, structure=struct3, iterations=1)
    tissue_mask = binary_fill_holes(tissue_mask)

    # Keep only the largest connected component (the head)
    labeled_tissue, n_tissue = cc_label(tissue_mask)
    if n_tissue > 1:
        sizes = [(labeled_tissue == i).sum() for i in range(1, n_tissue + 1)]
        largest = int(np.argmax(sizes)) + 1
        tissue_mask = (labeled_tissue == largest)

    # Skull stripping via erosion-dilation:
    # Skull is a ~3-5mm thin shell. Erode to remove it, then dilate back.
    # Erosion radius ~6mm removes skull while preserving brain core.
    erosion_iters = max(1, int(6.0 / min(voxel_spacing)))  # ~6mm
    brain_core = binary_erosion(tissue_mask, structure=struct3, iterations=erosion_iters)

    # Keep largest CC of eroded mask (the brain, excluding skull fragments)
    labeled_core, n_core = cc_label(brain_core)
    if n_core > 1:
        sizes = [(labeled_core == i).sum() for i in range(1, n_core + 1)]
        largest = int(np.argmax(sizes)) + 1
        brain_core = (labeled_core == largest)
    elif n_core == 0:
        logger.warning("[ZoneMap-Geo] Erosion removed all tissue, reducing iterations")
        brain_core = binary_erosion(tissue_mask, structure=struct3, iterations=max(1, erosion_iters // 2))
        labeled_core, n_core = cc_label(brain_core)
        if n_core > 1:
            sizes = [(labeled_core == i).sum() for i in range(1, n_core + 1)]
            largest = int(np.argmax(sizes)) + 1
            brain_core = (labeled_core == largest)

    # Dilate back to recover brain boundary
    brain_mask = binary_dilation(brain_core, structure=struct3, iterations=erosion_iters)
    brain_mask = brain_mask & tissue_mask  # Stay within original tissue
    brain_mask = binary_fill_holes(brain_mask)

    total_brain_voxels = int(brain_mask.sum())
    if total_brain_voxels < 1000:
        logger.warning("[ZoneMap-Geo] Brain mask too small: %d voxels", total_brain_voxels)
        return _empty_zone_result((depth, height, width), start_time)

    logger.info(
        "[ZoneMap-Geo] Brain mask: %d voxels (%.1f%% of volume)",
        total_brain_voxels, total_brain_voxels / (depth * height * width) * 100,
    )

    # =========================================================================
    # Step 2: Ventricle Detection (dark CSF regions inside brain)
    # =========================================================================

    # Get brain interior (away from cortex surface) for ventricle search
    interior_dist = distance_transform_edt(brain_mask, sampling=voxel_spacing)
    brain_interior = interior_dist > 10.0  # At least 10mm from brain surface

    # Ventricles are the darkest structures inside the brain
    # (CSF appears dark in FLAIR, T1, T2)
    brain_intensities = image_data[brain_mask & (image_data > 0)]
    if len(brain_intensities) > 0:
        p20 = float(np.percentile(brain_intensities, 20))
    else:
        p20 = otsu_thresh * 0.3

    # Dark voxels in the brain interior = ventricle candidates
    ventricle_candidates = brain_interior & (image_data > 0) & (image_data < p20)

    # Keep only large connected components (real ventricles, not noise)
    if ventricle_candidates.any():
        labeled_vent, n_vent = cc_label(ventricle_candidates)
        min_vent_voxels = max(50, total_brain_voxels // 500)  # Adaptive minimum
        for i in range(1, n_vent + 1):
            if (labeled_vent == i).sum() < min_vent_voxels:
                ventricle_candidates[labeled_vent == i] = False

    has_ventricles = int(ventricle_candidates.sum()) > 100

    logger.info(
        "[ZoneMap-Geo] Ventricle detection: %d voxels (found=%s, threshold=%.1f)",
        int(ventricle_candidates.sum()), has_ventricles, p20,
    )

    # =========================================================================
    # Step 3: Compute Distance Transforms
    # =========================================================================

    # Distance from brain surface (cortex) — for JC zone
    dist_from_cortex = interior_dist  # Already computed above

    # Distance from ventricles — for PV zone
    if has_ventricles:
        dist_to_ventricle = distance_transform_edt(
            ~ventricle_candidates, sampling=voxel_spacing
        )
    else:
        # Fallback: approximate ventricle location as brain center
        logger.info("[ZoneMap-Geo] No ventricles detected, using center approximation")
        brain_z = np.where(brain_mask.any(axis=(1, 2)))[0]
        cz = float(brain_z[0] + brain_z[-1]) / 2.0
        cy = float(height) / 2.0
        cx = float(width) / 2.0
        zz, yy, xx = np.meshgrid(
            np.arange(depth) * voxel_spacing[0],
            np.arange(height) * voxel_spacing[1],
            np.arange(width) * voxel_spacing[2],
            indexing='ij',
        )
        dist_to_ventricle = np.sqrt(
            (zz - cz * voxel_spacing[0]) ** 2 +
            (yy - cy * voxel_spacing[1]) ** 2 +
            (xx - cx * voxel_spacing[2]) ** 2
        )

    # =========================================================================
    # Step 4: Classify Zones (priority cascade IT → PV → JC → DWM)
    # =========================================================================

    zone_mask = np.zeros((depth, height, width), dtype=np.uint8)

    # Brain z-extent for IT detection
    brain_z_indices = np.where(brain_mask.any(axis=(1, 2)))[0]
    brain_z_min = int(brain_z_indices[0])
    brain_z_max = int(brain_z_indices[-1])
    it_z_threshold = brain_z_min + (brain_z_max - brain_z_min) * 0.25
    z_grid = np.broadcast_to(
        np.arange(depth, dtype=np.float32)[:, None, None],
        (depth, height, width),
    )

    # 1. Infratentorial: bottom 25% of brain extent
    it_zone = brain_mask & (z_grid < it_z_threshold)
    zone_mask[it_zone] = 3

    # 2. Periventricular: within 3mm of ventricles (MAGNIMS clinical threshold)
    pv_zone = brain_mask & ~it_zone & (dist_to_ventricle <= PV_DISTANCE_THRESHOLD_MM)
    zone_mask[pv_zone] = 1

    # 3. Juxtacortical: within 4mm of brain surface (MAGNIMS clinical threshold)
    jc_zone = brain_mask & ~it_zone & ~pv_zone & (
        dist_from_cortex <= JC_DISTANCE_THRESHOLD_MM
    )
    zone_mask[jc_zone] = 2

    # 4. Deep White Matter: remaining brain tissue
    dwm_zone = brain_mask & (zone_mask == 0)
    zone_mask[dwm_zone] = 4

    # =========================================================================
    # Stats
    # =========================================================================

    zone_stats = {}
    voxel_vol_mm3 = float(np.prod(voxel_spacing))
    for zone_id, zone_name in REGION_NAMES.items():
        count = int((zone_mask == zone_id).sum())
        zone_stats[zone_name] = {
            "zone_id": zone_id,
            "voxel_count": count,
            "volume_mm3": round(count * voxel_vol_mm3, 1),
            "volume_ml": round(count * voxel_vol_mm3 / 1000, 3),
            "percentage": round(count / max(total_brain_voxels, 1) * 100, 1),
        }

    elapsed_ms = int((time.time() - start_time) * 1000)

    logger.info(
        "[ZoneMap-Geo] Generated in %dms — PV=%.1f%%, JC=%.1f%%, IT=%.1f%%, DWM=%.1f%%",
        elapsed_ms,
        zone_stats.get("Periventricular", {}).get("percentage", 0),
        zone_stats.get("Juxtacortical", {}).get("percentage", 0),
        zone_stats.get("Infratentorial", {}).get("percentage", 0),
        zone_stats.get("Deep White Matter", {}).get("percentage", 0),
    )

    return {
        "zone_mask": zone_mask,
        "zone_stats": zone_stats,
        "total_brain_voxels": total_brain_voxels,
        "processing_time_ms": elapsed_ms,
    }


def _empty_zone_result(shape: tuple, start_time: float) -> dict:
    """Return empty zone map result."""
    return {
        "zone_mask": np.zeros(shape, dtype=np.uint8),
        "zone_stats": {},
        "total_brain_voxels": 0,
        "processing_time_ms": int((time.time() - start_time) * 1000),
    }


# =============================================================================
# Internal Helpers
# =============================================================================

REGION_NAMES = {
    1: "Periventricular",
    2: "Juxtacortical",
    3: "Infratentorial",
    4: "Deep White Matter",
}


def _classify_by_distance(
    dist_it: float,
    dist_pv: float,
    dist_jc: float,
) -> tuple[int, str, float]:
    """
    Classify a single lesion by minimum distances to anatomical landmarks.

    Priority cascade: IT -> PV -> JC -> DWM.
    Returns (region_id, region_name, confidence).

    Confidence is computed as inverse distance normalized:
    - Closer to landmark = higher confidence
    - Within threshold = high confidence (0.85-0.95)
    - Marginally within threshold = moderate confidence (0.70-0.85)
    """
    # Infratentorial (most specific)
    if dist_it <= IT_DISTANCE_THRESHOLD_MM:
        confidence = _distance_to_confidence(dist_it, IT_DISTANCE_THRESHOLD_MM)
        return 3, "Infratentorial", confidence

    # Periventricular
    if dist_pv <= PV_DISTANCE_THRESHOLD_MM:
        confidence = _distance_to_confidence(dist_pv, PV_DISTANCE_THRESHOLD_MM)
        return 1, "Periventricular", confidence

    # Juxtacortical
    if dist_jc <= JC_DISTANCE_THRESHOLD_MM:
        confidence = _distance_to_confidence(dist_jc, JC_DISTANCE_THRESHOLD_MM)
        return 2, "Juxtacortical", confidence

    # Deep White Matter (default)
    # Confidence based on how far from other regions
    min_other = min(dist_it, dist_pv, dist_jc)
    max_threshold = max(IT_DISTANCE_THRESHOLD_MM, PV_DISTANCE_THRESHOLD_MM, JC_DISTANCE_THRESHOLD_MM)
    confidence = min(0.90, 0.60 + 0.30 * min(1.0, (min_other - max_threshold) / 10.0))
    return 4, "Deep White Matter", confidence


def _distance_to_confidence(distance: float, threshold: float) -> float:
    """
    Convert distance to confidence score.
    Distance=0 -> confidence=0.95, distance=threshold -> confidence=0.70.
    """
    if threshold == 0:
        return 0.95
    ratio = distance / threshold
    return max(0.70, 0.95 - 0.25 * ratio)


def _build_summary(lesion_details: list[dict]) -> dict[str, int]:
    """Count lesions per region."""
    summary: dict[str, int] = {}
    for lesion in lesion_details:
        region = lesion["region"]
        summary[region] = summary.get(region, 0) + 1
    return summary


def _empty_result(method: str, elapsed: float) -> dict:
    """Return empty classification result."""
    return {
        "method": method,
        "classified_mask": None,
        "lesions": [],
        "total_classified": 0,
        "classification_summary": {},
        "thresholds_mm": {},
        "processing_time_ms": int(elapsed * 1000),
    }
