"""
MS Lesion Region Classification Service.

Classifies MS lesions into MAGNIMS/McDonald 2024 anatomical regions:
  1 - Periventricular (PV): Direct contact with lateral ventricles
  2 - Juxtacortical (JC): Touching cortex / involving U-fibers
  3 - Infratentorial (IT): Brainstem, cerebellum, cerebellar peduncles
  4 - Deep White Matter (DWM): Cerebral WM not meeting PV/JC/IT criteria

Two methods are provided:

  - **Parcellation-based** (generate_zone_map): Uses SynthSeg/FreeSurfer labels
    with Euclidean Distance Transforms (EDT). Higher accuracy when parcellation
    is available.

  - **Atlas-based** (generate_zone_map_atlas): Uses Harvard-Oxford atlas with
    single-voxel binary dilation, following the LST-AI methodology (Wiltgen
    et al., NeuroImage: Clinical 2024). Fallback when no parcellation exists.

Priority cascade: IT -> PV -> JC -> DWM (most specific first).

References:
  - Filippi et al., Brain 2019; 142(7): 1858-1875 (MAGNIMS practical guidelines)
  - Thompson et al., Lancet Neurology 2018; 17: 162-173 (McDonald 2017 criteria)
  - Wiltgen et al., NeuroImage: Clinical 2024 (LST-AI zone classification)
  - Billot et al., NeuroImage 2023 (SynthSeg parcellation)

@module services.ms_region_classifier
"""

import time
import numpy as np
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
# Clinical Thresholds (mm) — Based on MAGNIMS guidelines
# =============================================================================

# Periventricular: "directly abutting the lateral ventricle" (Filippi 2019).
# We use <=3mm to account for partial volume effects at typical 1mm isotropic.
PV_DISTANCE_THRESHOLD_MM = 3.0

# Juxtacortical: "touching the cortex with no intervening white matter"
# (Thompson 2018). In practice <=4mm accounts for cortical ribbon thickness.
JC_DISTANCE_THRESHOLD_MM = 4.0

# Infratentorial: lesion within or touching brainstem/cerebellum.
IT_DISTANCE_THRESHOLD_MM = 3.0

# Minimum lesion volume (mm3) to classify — ignore very small noise components
MIN_LESION_VOLUME_MM3 = 3.0  # ~3 voxels at 1mm isotropic


def classify_lesions_with_parcellation(
    lesion_mask: np.ndarray,
    parcellation_mask: np.ndarray,
    voxel_spacing: tuple[float, float, float] = (1.0, 1.0, 1.0),
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
    labeled_array, num_components = cc_label(binary_lesion)

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
    voxel_spacing: tuple[float, float, float] = (1.0, 1.0, 1.0),
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
    labeled_array, num_components = cc_label(binary_lesion)

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
        # 1. Infratentorial: z-coordinate below threshold
        if cz < it_z_threshold:
            region_id, region_name, confidence = 3, "Infratentorial", 0.75

        # 2. Periventricular: close to center of brain
        elif float(dist_from_center[comp_mask].mean()) < pv_center_threshold:
            region_id, region_name, confidence = 1, "Periventricular", 0.60

        # 3. Juxtacortical: close to brain surface
        elif float(dist_from_surface[comp_mask].min()) < jc_surface_threshold:
            region_id, region_name, confidence = 2, "Juxtacortical", 0.55

        # 4. Deep white matter: default
        else:
            region_id, region_name, confidence = 4, "Deep White Matter", 0.50

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
# Zone Map Generation
# =============================================================================


def generate_zone_map(
    parcellation_mask: np.ndarray,
    voxel_spacing: tuple[float, float, float] = (1.0, 1.0, 1.0),
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
    ventricle_mask = np.isin(parcellation_mask, list(ALL_VENTRICLE_LABELS))
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
    voxel_spacing: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> dict:
    """
    Generate a 3D MAGNIMS zone map using Harvard-Oxford atlas.

    Implements the LST-AI methodology (Wiltgen et al., NeuroImage: Clinical
    2024) adapted from per-lesion classification to pre-computed zone map:

    1. Load Harvard-Oxford subcortical + cortical atlases at 1mm MNI resolution
    2. Extract anatomical masks: ventricles, cortex (combined), WM, brainstem
    3. Infer infratentorial region via MNI z-coordinate (z < -30mm)
    4. Single-voxel binary dilation (3x3x3 cube) of ventricles and cortex to
       implement MAGNIMS "abutting" criterion (Filippi et al., Brain 2019)
    5. Resample zone map to patient image grid via corrected affine

    Priority cascade: IT > PV > JC > DWM. For zone maps, IT has absolute
    priority as lateral ventricles do not exist in the infratentorial region,
    making the cascade equivalent to LST-AI's PV > JC > IT > SC.

    Harvard-Oxford subcortical maxprob-thr0-1mm labels (nilearn 1-based):
      1/12 = L/R Cerebral White Matter
      2/13 = L/R Cerebral Cortex
      3/14 = L/R Lateral Ventricle
      8    = Brain-Stem

    Harvard-Oxford cortical maxprob-thr0-1mm: 48 cortical parcellation
    regions (all labels > 0), combined with subcortical cortex labels for
    complete cortical surface coverage.

    Args:
        target_img: nibabel Nifti1Image of the patient MRI in MNI space.
            Used for shape and affine to determine the output grid.
        voxel_spacing: Unused (kept for API compatibility). Atlas is 1mm
            isotropic.

    Returns:
        Dict with zone_mask (uint8 in NIfTI native order i,j,k), zone_stats,
        total_brain_voxels, processing_time_ms, method='atlas'.

    References:
        Wiltgen et al. (2024). LST-AI: A deep learning ensemble for accurate
        MS lesion segmentation. NeuroImage: Clinical, 42, 103611.

        Filippi et al. (2019). Assessment of lesions on MRI in MS: practical
        guidelines. Brain, 142(7), 1858-1875.
    """
    import nibabel as nib
    from scipy.ndimage import binary_dilation
    from nilearn import datasets
    from pathlib import Path

    start_time = time.time()

    # ── 1. Load atlases at NATIVE resolution (no resampling of masks) ──
    data_dir = "/app/data/nilearn_data"
    data_dir = data_dir if Path(data_dir).exists() else None

    # Subcortical atlas: ventricles, WM, cortex (grey matter), brainstem
    # thr25 = 25% probability threshold (FSL default for clinical applications)
    atlas = datasets.fetch_atlas_harvard_oxford(
        'sub-maxprob-thr25-1mm', data_dir=data_dir
    )
    atlas_img = (
        atlas.maps if isinstance(atlas.maps, nib.spatialimages.SpatialImage)
        else nib.load(atlas.maps)
    )
    atlas_data = np.asarray(atlas_img.dataobj, dtype=np.int16)

    # Cortical atlas: 48 cortical regions for more complete cortex coverage
    # thr25 excludes low-probability voxels that may extend into white matter
    cort_atlas = datasets.fetch_atlas_harvard_oxford(
        'cort-maxprob-thr25-1mm', data_dir=data_dir
    )
    cort_img = (
        cort_atlas.maps if isinstance(cort_atlas.maps, nib.spatialimages.SpatialImage)
        else nib.load(cort_atlas.maps)
    )
    cort_data = np.asarray(cort_img.dataobj, dtype=np.int16)

    target_shape = target_img.shape[:3]

    logger.info(
        "[ZoneMap-Atlas] Atlas: shape=%s, affine_diag=%s, origin=%s",
        atlas_data.shape,
        np.diag(atlas_img.affine[:3, :3]).tolist(),
        atlas_img.affine[:3, 3].tolist(),
    )
    logger.info(
        "[ZoneMap-Atlas] Target: shape=%s, affine_diag=%s, origin=%s",
        target_shape,
        np.diag(target_img.affine[:3, :3]).tolist(),
        target_img.affine[:3, 3].tolist(),
    )

    # ── 2. Extract masks at NATIVE atlas resolution ──
    ventricle = (atlas_data == 3) | (atlas_data == 14)     # L/R Lat Ventricle
    cortex_sub = (atlas_data == 2) | (atlas_data == 13)    # L/R Cerebral Cortex (subcortical)
    cortex_cort = cort_data > 0                             # All 48 cortical regions
    cortex = cortex_sub | cortex_cort                       # Combined cortex mask
    wm = (atlas_data == 1) | (atlas_data == 12)             # L/R Cerebral WM
    brainstem = (atlas_data == 8)                            # Brain-Stem
    brain = (atlas_data > 0) | cortex_cort                  # Any labeled tissue

    # ── 3. Infer infratentorial region via MNI z-coordinate ──
    # Tentorium cerebelli is approximately at z = -30mm in MNI space.
    # Everything below (brainstem + cerebellum) = infratentorial.
    affine = atlas_img.affine
    k_indices = np.arange(atlas_data.shape[2])
    # MNI z for each k-slice: z = affine[2,2]*k + affine[2,3]
    mni_z_per_slice = affine[2, 2] * k_indices + affine[2, 3]
    z_volume = np.broadcast_to(
        mni_z_per_slice[np.newaxis, np.newaxis, :], atlas_data.shape
    )
    infratentorial = brainstem | (brain & (z_volume < -30))

    logger.info(
        "[ZoneMap-Atlas] Masks at native res: brain=%d, ventricle=%d, "
        "cortex=%d (sub=%d, cort=%d), wm=%d, brainstem=%d, infratentorial=%d",
        int(brain.sum()), int(ventricle.sum()), int(cortex.sum()),
        int(cortex_sub.sum()), int(cortex_cort.sum()),
        int(wm.sum()), int(brainstem.sum()), int(infratentorial.sum()),
    )

    # ── 4. Build zone map using binary dilation (LST-AI methodology) ──
    # LST-AI (Wiltgen et al. 2024) uses single-voxel binary dilation with a
    # 3x3x3 cube footprint to implement the MAGNIMS "abutting" criterion.
    # At 1mm isotropic MNI resolution this captures structures within ~1.73mm
    # (cube diagonal), matching the clinical definition of "direct contact."
    struct = np.ones((3, 3, 3), dtype=bool)
    ventricle_dilated = binary_dilation(ventricle, structure=struct)
    cortex_dilated = binary_dilation(cortex, structure=struct)

    zone_map = np.zeros(atlas_data.shape, dtype=np.uint8)

    # Assign ALL white matter voxels as DWM (default)
    zone_map[wm] = 4

    # IT: WM in infratentorial region + brainstem (overrides DWM)
    # Only classify WM tissue (where MS lesions occur) + brainstem grey matter.
    # Cerebellar cortex stays as background (0) for clean overlay rendering.
    zone_map[(infratentorial & wm) | brainstem] = 3

    # JC: WM voxels abutting cortex (overrides DWM, not IT)
    jc_mask = cortex_dilated & wm & (zone_map != 3)
    zone_map[jc_mask] = 2

    # PV: WM voxels abutting lateral ventricles (overrides JC/DWM, not IT)
    pv_mask = ventricle_dilated & wm & (zone_map != 3)
    zone_map[pv_mask] = 1

    # ── 5. Map zone map to patient image grid ──
    # The patient NIfTI may have a wrong affine (e.g., origin [0,0,0] in ISBI
    # 2015 datasets that are registered to MNI but lack correct sform/qform).
    # We compute a CORRECTED affine from the atlas's MNI extent and the
    # patient's axis directions (sign of diagonal), guaranteeing alignment.
    from nilearn.image import resample_to_img

    # Derive corrected affine from atlas extent + patient axis directions
    atlas_diag = np.diag(atlas_img.affine[:3, :3])       # e.g., [1, 1, 1]
    atlas_origin = atlas_img.affine[:3, 3]                 # e.g., [-91, -126, -72]
    atlas_end = atlas_origin + atlas_diag * (np.array(atlas_img.shape[:3]) - 1)
    # atlas_end = [90, 91, 109]

    target_diag = np.diag(target_img.affine[:3, :3])       # e.g., [-1, -1, 1]

    # For each axis, voxel[0] maps to:
    #   high end of MNI range if stride < 0 (axis is flipped)
    #   low end of MNI range if stride >= 0
    corrected_origin = np.zeros(3)
    for ax in range(3):
        lo = min(atlas_origin[ax], atlas_end[ax])
        hi = max(atlas_origin[ax], atlas_end[ax])
        corrected_origin[ax] = hi if target_diag[ax] < 0 else lo

    corrected_affine = np.eye(4)
    corrected_affine[:3, :3] = np.diag(target_diag)
    corrected_affine[:3, 3] = corrected_origin

    logger.info(
        "[ZoneMap-Atlas] Corrected affine: diag=%s, origin=%s (patient original: %s)",
        target_diag.tolist(), corrected_origin.tolist(),
        target_img.affine[:3, 3].tolist(),
    )

    # Resample zone map from atlas space to corrected patient space
    zone_nifti = nib.Nifti1Image(zone_map.astype(np.float32), atlas_img.affine)
    target_ref = nib.Nifti1Image(
        np.zeros(target_shape, dtype=np.uint8), corrected_affine
    )
    zone_resampled = resample_to_img(
        zone_nifti, target_ref, interpolation='nearest'
    )
    zone_final = np.asarray(zone_resampled.dataobj, dtype=np.uint8)

    # Log zone data distribution for verification
    zone_nz = np.argwhere(zone_final > 0)
    if len(zone_nz) > 0:
        zone_com = zone_nz.mean(axis=0)
        zone_bb_min = zone_nz.min(axis=0)
        zone_bb_max = zone_nz.max(axis=0)
        logger.info(
            "[ZoneMap-Atlas] Zone data: com=%s, bbox=[%s..%s], shape=%s",
            [round(c, 1) for c in zone_com],
            zone_bb_min.tolist(), zone_bb_max.tolist(),
            zone_final.shape,
        )

    # ── 6. Compute zone statistics ──
    total_classified = int((zone_final > 0).sum())
    zone_stats = {}
    for zone_id, zone_name in REGION_NAMES.items():
        count = int((zone_final == zone_id).sum())
        zone_stats[zone_name] = {
            "zone_id": zone_id,
            "voxel_count": count,
            "volume_mm3": round(count * 1.0, 1),  # 1mm isotropic
            "volume_ml": round(count / 1000, 3),
            "percentage": round(count / max(total_classified, 1) * 100, 1),
        }

    elapsed_ms = int((time.time() - start_time) * 1000)

    logger.info(
        "[ZoneMap-Atlas] Generated in %dms — PV=%.1f%%, JC=%.1f%%, IT=%.1f%%, DWM=%.1f%%, total=%d",
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
        "method": "atlas",
    }


def generate_zone_map_geometric(
    image_data: np.ndarray,
    voxel_spacing: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> dict:
    """
    DEPRECATED: Use generate_zone_map_atlas() instead.

    Generate MAGNIMS zone map using intensity-based anatomy detection.
    This method produces inaccurate results because it relies on heuristic
    ventricle/cortex detection from image intensities.

    Steps:
      1. Brain extraction: Otsu threshold + morphological skull stripping
      2. Ventricle detection: dark CSF regions in the brain interior
      3. PV zone: EDT from detected ventricles, <= 3mm (MAGNIMS threshold)
      4. JC zone: EDT from brain surface (cortex), <= 4mm
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
