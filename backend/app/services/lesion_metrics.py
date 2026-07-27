"""Shared lesion connected-component conventions — IEC 62304 Class C.

Risk control RC-030 for HAZ-005 (incorrect lesion count / region classification).

WHY THIS MODULE EXISTS
----------------------
Lesion count and dissemination-in-space (DIS, "a region is present if it has a
qualifying lesion") depend on TWO conventions that were previously implicit and
duplicated across three services:

  1. The neighbourhood CONNECTIVITY used to split a binary mask into discrete
     lesions. Every call site used `scipy.ndimage.label(binary)` with no
     `structure` argument, which defaults to `generate_binary_structure(3, 1)` =
     **6-connectivity** (faces only). That is NOT the convention the field's two
     reference evaluation protocols use.

  2. The minimum lesion VOLUME below which a component is treated as noise. This
     was a `MIN_LESION_VOLUME_MM3 = 3.0` literal DUPLICATED in
     lesion_analysis_service.py and ms_region_classifier.py, justified by a
     comment ("~3 voxels at 1mm isotropic") that is coincidental and misleading.

Both conventions change reported clinical numbers (lesion count, and whether a
region "counts" toward DIS), so they are centralised here, documented against
primary sources, and bound to a test.

CONNECTIVITY — 18-connected (the challenge-evaluation standard)
--------------------------------------------------------------
The two canonical MS lesion-segmentation challenges both define a discrete lesion
as an **18-connected component**:

  - ISBI-2015 (Carass et al., NeuroImage 2017): "We define the list of lesions,
    LR, as the 18-connected components of MR." (used for lesion TPR/FPR)
    https://pmc.ncbi.nlm.nih.gov/articles/PMC5344762/
  - MSSEG-2016 (Commowick et al., Sci Rep 2018): "We first compute the connected
    components of G and A (with a 18-connectivity kernel)" for detection scoring.
    https://www.nature.com/articles/s41598-018-31911-7

18-connectivity = faces + edges (a lesion whose voxels touch only along a cube
EDGE is one lesion, not two). scipy's default 6-connectivity would split such a
lesion, over-counting relative to the challenge standard. We therefore set the
structuring element explicitly to `generate_binary_structure(3, 2)`
(connectivity rank 2 = 18-neighbourhood).

HONEST SCOPE OF THIS CHOICE (do not overstate it):
  - This is the challenge-EVALUATION standard, NOT a clinical consensus.
    MAGNIMS/OFSEP do not prescribe a connectivity. It is the strongest
    engineering-defensible standard available and is unanimous across the two
    reference challenges.
  - Connected-component labelling at ANY connectivity CANNOT separate confluent
    lesions, so lesion COUNT is inherently less reliable than lesion VOLUME/load
    (volume correlates rho ~0.92-0.97 with manual reference vs ~0.83-0.94 for
    count; ConfLUNet, Dumont et al. 2025, and the consensus/ensemble literature).
    Downstream reporting must weight count with that uncertainty.

MINIMUM LESION VOLUME — 3.0 mm3 (MSSEG-2016 evaluation floor)
------------------------------------------------------------
The ONLY genuinely citable 3 mm3 figure is MSSEG-2016's detection-evaluation
gate: after 18-connected labelling it "remove[s] all lesions that are smaller in
size than 3 mm3" before counting, applied in mm3 (so it is voxel-size/resolution
agnostic). We keep 3.0 mm3 on that basis.

⚠️ It is NOT the "3 mm" diagnostic criterion. The widely-cited clinical "3 mm"
MS lesion threshold is a DIAMETER (~14 mm3 for a sphere), a different and larger
quantity. The old "~3 voxels at 1 mm isotropic" justification was coincidental
and conflatable; it is removed. No clinical consensus prescribes a mm3 count
floor, so this value is deliberately the evaluation-standard noise floor, not a
diagnostic threshold.

Verified by: backend/tests/unit/test_rc030_lesion_metrics.py (tests named
test_rc030_*). Reverting connectivity to 6 or dropping the shared floor MUST
turn CI red.
"""
from typing import Tuple

import numpy as np


# Minimum lesion volume treated as signal (mm3). MSSEG-2016 evaluation floor.
# NOT the 3 mm-diameter diagnostic criterion (~14 mm3). See module docstring.
MIN_LESION_VOLUME_MM3: float = 3.0


def lesion_structuring_element() -> np.ndarray:
    """The 18-connected structuring element for discrete-lesion labelling.

    Built lazily (not at import) so the module imports without SciPy present;
    the analysis services already gate on a SciPy import and degrade with an
    explicit error, and this keeps that behaviour.

    connectivity rank 2 on a rank-3 array = 18-neighbourhood (faces + edges),
    matching ISBI-2015 and MSSEG-2016. See module docstring.
    """
    from scipy.ndimage import generate_binary_structure

    return generate_binary_structure(3, 2)


def label_lesions(binary_mask: np.ndarray) -> Tuple[np.ndarray, int]:
    """Label discrete lesions in a 3D binary mask with 18-connectivity.

    Drop-in replacement for `scipy.ndimage.label(binary_mask)` that pins the
    connectivity to the challenge-evaluation standard instead of scipy's
    6-connected default.

    Returns (labelled_array, num_components), exactly like scipy's label().
    """
    from scipy.ndimage import label as _scipy_label

    return _scipy_label(binary_mask, structure=lesion_structuring_element())


def meets_min_volume(voxel_count: int, voxel_volume_mm3: float) -> bool:
    """True if a component's physical volume reaches the MSSEG-2016 noise floor.

    Uses volume (voxel_count * voxel_volume_mm3), never a raw voxel count, so the
    floor is resolution-independent — the whole point of expressing it in mm3.
    """
    return voxel_count * voxel_volume_mm3 >= MIN_LESION_VOLUME_MM3
