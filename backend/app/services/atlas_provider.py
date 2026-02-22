"""
MNI152 Atlas Provider Service.

Provides cached, pre-processed anatomical atlas masks for MAGNIMS zone
classification. Uses Harvard-Oxford atlases via nilearn with lazy loading
and in-memory caching.

Atlas masks are loaded on first use, resampled to match the target image
dimensions (nearest-neighbor to preserve integer labels), and cached
for all subsequent requests.

IMPORTANT: This module assumes the input images are registered to the
MNI-ICBM152 template (same space as Harvard-Oxford atlases). For the
ISBI 2015 MS dataset, all preprocessed images are rigidly registered
to MNI-ICBM152 at 1mm isotropic (181x217x181).

@module services.atlas_provider
"""

import time
import threading
import numpy as np
from typing import Optional, Dict, Tuple
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)

# Atlas data directory — baked into Docker image at build time.
# Falls back to nilearn default (~/.nilearn_data) if not pre-baked.
ATLAS_DATA_DIR = "/app/data/nilearn_data"

# =============================================================================
# Harvard-Oxford Subcortical Atlas — Voxel Value Mapping
# =============================================================================
# nilearn prepends "Background" at index 0, so FSL XML indices are +1.
# Source: nilearn.datasets.fetch_atlas_harvard_oxford('sub-maxprob-thr25-1mm')

HO_SUB_LEFT_CEREBRAL_WM = 1
HO_SUB_LEFT_CEREBRAL_CORTEX = 2
HO_SUB_LEFT_LATERAL_VENTRICLE = 3
HO_SUB_LEFT_THALAMUS = 4
HO_SUB_LEFT_CAUDATE = 5
HO_SUB_LEFT_PUTAMEN = 6
HO_SUB_LEFT_PALLIDUM = 7
HO_SUB_BRAIN_STEM = 8
HO_SUB_LEFT_HIPPOCAMPUS = 9
HO_SUB_LEFT_AMYGDALA = 10
HO_SUB_LEFT_ACCUMBENS = 11
HO_SUB_RIGHT_CEREBRAL_WM = 12
HO_SUB_RIGHT_CEREBRAL_CORTEX = 13
HO_SUB_RIGHT_LATERAL_VENTRICLE = 14
HO_SUB_RIGHT_THALAMUS = 15
HO_SUB_RIGHT_CAUDATE = 16
HO_SUB_RIGHT_PUTAMEN = 17
HO_SUB_RIGHT_PALLIDUM = 18
HO_SUB_RIGHT_HIPPOCAMPUS = 19
HO_SUB_RIGHT_AMYGDALA = 20
HO_SUB_RIGHT_ACCUMBENS = 21

# =============================================================================
# Label Sets for MAGNIMS Zone Classification
# =============================================================================

VENTRICLE_LABELS = {HO_SUB_LEFT_LATERAL_VENTRICLE, HO_SUB_RIGHT_LATERAL_VENTRICLE}
CORTEX_LABELS_SUB = {HO_SUB_LEFT_CEREBRAL_CORTEX, HO_SUB_RIGHT_CEREBRAL_CORTEX}
BRAINSTEM_LABELS = {HO_SUB_BRAIN_STEM}
CEREBRAL_WM_LABELS = {HO_SUB_LEFT_CEREBRAL_WM, HO_SUB_RIGHT_CEREBRAL_WM}

# All supratentorial structure labels (everything that is NOT cerebellum)
SUPRATENTORIAL_LABELS = (
    CEREBRAL_WM_LABELS | CORTEX_LABELS_SUB | VENTRICLE_LABELS |
    {HO_SUB_LEFT_THALAMUS, HO_SUB_LEFT_CAUDATE, HO_SUB_LEFT_PUTAMEN,
     HO_SUB_LEFT_PALLIDUM, HO_SUB_LEFT_HIPPOCAMPUS, HO_SUB_LEFT_AMYGDALA,
     HO_SUB_LEFT_ACCUMBENS,
     HO_SUB_RIGHT_THALAMUS, HO_SUB_RIGHT_CAUDATE, HO_SUB_RIGHT_PUTAMEN,
     HO_SUB_RIGHT_PALLIDUM, HO_SUB_RIGHT_HIPPOCAMPUS, HO_SUB_RIGHT_AMYGDALA,
     HO_SUB_RIGHT_ACCUMBENS}
)


class AtlasProvider:
    """
    Singleton provider for MNI152-space anatomical atlas masks.

    Thread-safe, lazy-loaded. Atlas NIfTI images are loaded once from disk
    (pre-baked in Docker or downloaded by nilearn on first use), then
    resampled to match target image dimensions and cached per-shape.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._raw_sub_img = None       # Harvard-Oxford subcortical NIfTI
        self._raw_cort_img = None      # Harvard-Oxford cortical NIfTI
        self._brain_mask_img = None    # MNI152 brain mask NIfTI
        self._resampled_cache: Dict[Tuple, Dict[str, np.ndarray]] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Load raw atlas NIfTI images (thread-safe, idempotent)."""
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._load_atlases()
            self._loaded = True

    def _load_atlases(self) -> None:
        """Download/load Harvard-Oxford atlases and MNI152 brain mask."""
        import nibabel as nib
        from nilearn import datasets

        start = time.time()

        data_dir = ATLAS_DATA_DIR if Path(ATLAS_DATA_DIR).exists() else None
        if data_dir:
            logger.info("[AtlasProvider] Using pre-baked atlas data from %s", data_dir)
        else:
            logger.info("[AtlasProvider] No pre-baked data, nilearn will download atlases")

        logger.info("[AtlasProvider] Loading Harvard-Oxford subcortical atlas (1mm)...")
        sub_atlas = datasets.fetch_atlas_harvard_oxford(
            'sub-maxprob-thr25-1mm', data_dir=data_dir
        )
        # nilearn >= 0.11 returns Nifti1Image directly; older versions return path
        self._raw_sub_img = (
            sub_atlas.maps if isinstance(sub_atlas.maps, nib.spatialimages.SpatialImage)
            else nib.load(sub_atlas.maps)
        )

        logger.info("[AtlasProvider] Loading Harvard-Oxford cortical atlas (1mm)...")
        cort_atlas = datasets.fetch_atlas_harvard_oxford(
            'cort-maxprob-thr25-1mm', data_dir=data_dir
        )
        self._raw_cort_img = (
            cort_atlas.maps if isinstance(cort_atlas.maps, nib.spatialimages.SpatialImage)
            else nib.load(cort_atlas.maps)
        )

        logger.info("[AtlasProvider] Loading MNI152 brain mask (1mm)...")
        self._brain_mask_img = datasets.load_mni152_brain_mask(resolution=1)

        elapsed = int((time.time() - start) * 1000)
        logger.info(
            "[AtlasProvider] Atlases loaded in %dms — sub=%s, cort=%s, brain=%s",
            elapsed,
            self._raw_sub_img.shape,
            self._raw_cort_img.shape,
            self._brain_mask_img.shape,
        )

    def get_masks_for_shape(self, target_img) -> Dict[str, np.ndarray]:
        """
        Get resampled binary masks for MAGNIMS zone classification.

        Args:
            target_img: nibabel Nifti1Image — only affine + shape are used
                        for resampling the atlas to match the patient image.

        Returns:
            Dict with keys:
              - 'ventricle': bool array, lateral ventricle voxels
              - 'cortex': bool array, cortical gray matter
              - 'brainstem': bool array, brainstem
              - 'cerebellum': bool array, cerebellum (inferred)
              - 'infratentorial': bool array, brainstem OR cerebellum
              - 'brain': bool array, any brain tissue
              - 'cerebral_wm': bool array, cerebral white matter

            All arrays match the shape of target_img.
        """
        self._ensure_loaded()

        target_shape = tuple(target_img.shape[:3])

        if target_shape in self._resampled_cache:
            return self._resampled_cache[target_shape]

        with self._lock:
            # Double-check after acquiring lock
            if target_shape in self._resampled_cache:
                return self._resampled_cache[target_shape]
            masks = self._compute_masks(target_img)
            self._resampled_cache[target_shape] = masks
            return masks

    def _compute_masks(self, target_img) -> Dict[str, np.ndarray]:
        """Resample atlases to target image and extract binary masks."""
        from nilearn.image import resample_to_img

        start = time.time()

        # Log affines for diagnostics (helps debug resampling misalignment)
        logger.info(
            "[AtlasProvider] Target affine origin: %s, shape: %s",
            target_img.affine[:3, 3].tolist(),
            target_img.shape[:3],
        )
        logger.info(
            "[AtlasProvider] Atlas affine origin: %s, shape: %s",
            self._raw_sub_img.affine[:3, 3].tolist(),
            self._raw_sub_img.shape[:3],
        )

        # Resample subcortical atlas to patient image (nearest = preserve labels)
        sub_resampled = resample_to_img(
            self._raw_sub_img, target_img, interpolation='nearest'
        )
        sub_data = np.asarray(sub_resampled.dataobj, dtype=np.int16)

        # Resample cortical atlas
        cort_resampled = resample_to_img(
            self._raw_cort_img, target_img, interpolation='nearest'
        )
        cort_data = np.asarray(cort_resampled.dataobj, dtype=np.int16)

        # Resample brain mask
        brain_resampled = resample_to_img(
            self._brain_mask_img, target_img, interpolation='nearest'
        )
        brain_data = np.asarray(brain_resampled.dataobj) > 0

        # --- Extract individual masks ---

        # Ventricles: lateral ventricles from subcortical atlas
        ventricle = np.isin(sub_data, list(VENTRICLE_LABELS))

        # Cortex: union of subcortical cortex labels + all cortical atlas regions
        cortex_from_sub = np.isin(sub_data, list(CORTEX_LABELS_SUB))
        cortex_from_cort = cort_data > 0  # All non-zero = cortical regions
        cortex = cortex_from_sub | cortex_from_cort

        # Brainstem: directly from subcortical atlas
        brainstem = np.isin(sub_data, list(BRAINSTEM_LABELS))

        # Cerebral white matter
        cerebral_wm = np.isin(sub_data, list(CEREBRAL_WM_LABELS))

        # --- Infer cerebellum ---
        # Strategy: brain voxels that are NOT any supratentorial structure
        # AND NOT brainstem AND lie at or below the brainstem z-range.
        # This works because Harvard-Oxford labels all supratentorial structures,
        # so the "leftover" brain tissue in the posterior fossa = cerebellum.
        supratentorial = np.isin(sub_data, list(SUPRATENTORIAL_LABELS))
        unlabeled_brain = brain_data & ~supratentorial & ~brainstem

        brainstem_z_indices = np.where(brainstem.any(axis=(1, 2)))[0]
        if len(brainstem_z_indices) > 0:
            # Include brain tissue below the top of the brainstem
            brainstem_top_z = int(brainstem_z_indices[-1])
            z_grid = np.broadcast_to(
                np.arange(sub_data.shape[0])[:, None, None],
                sub_data.shape,
            )
            cerebellum = unlabeled_brain & (z_grid <= brainstem_top_z)
        else:
            logger.warning("[AtlasProvider] No brainstem found in atlas — cerebellum will be empty")
            cerebellum = np.zeros_like(brain_data, dtype=bool)

        infratentorial = brainstem | cerebellum

        elapsed = int((time.time() - start) * 1000)
        logger.info(
            "[AtlasProvider] Masks computed for shape %s in %dms — "
            "ventricle=%d, cortex=%d, brainstem=%d, cerebellum=%d, brain=%d",
            target_img.shape[:3], elapsed,
            int(ventricle.sum()), int(cortex.sum()),
            int(brainstem.sum()), int(cerebellum.sum()), int(brain_data.sum()),
        )

        return {
            'ventricle': ventricle,
            'cortex': cortex,
            'brainstem': brainstem,
            'cerebellum': cerebellum,
            'infratentorial': infratentorial,
            'brain': brain_data,
            'cerebral_wm': cerebral_wm,
        }


# =============================================================================
# Module-level Singleton
# =============================================================================

_provider: Optional[AtlasProvider] = None
_provider_lock = threading.Lock()


def get_atlas_provider() -> AtlasProvider:
    """Get or create the singleton AtlasProvider instance."""
    global _provider
    if _provider is None:
        with _provider_lock:
            if _provider is None:
                _provider = AtlasProvider()
    return _provider
