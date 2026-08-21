"""Longitudinal FLAIR subtraction imaging for new-lesion confirmation.

Intensity subtraction of a co-registered follow-up minus baseline FLAIR is the
most clinically-validated longitudinal reading aid: it raises new-lesion detection
sensitivity ~35-80% and inter-rater agreement markedly over side-by-side scrolling
(AJNR 2023; FLAIR-subtraction ICC ~0.91). Here it is used to CONFIRM new-lesion
CANDIDATES: a candidate that is a genuine new lesion shows a strong positive
subtraction signal (follow-up brighter), whereas a candidate born of segmentation
noise or residual misregistration shows little/none — a false-positive filter.

Class C framing: this NEVER upgrades a candidate to a finding. It annotates each
new candidate with an advisory `subtraction_confirmed` flag; registration_verified
and the candidate firewall are untouched. Requires the co-registered intensities
(subtraction on un-registered volumes is dominated by pose, not disease).

@module services.longitudinal_subtraction
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from app.core.logging import get_logger

logger = get_logger(__name__)

# A new candidate whose mean normalized subtraction (follow-up − baseline, in SD
# units) reaches this is "subtraction-confirmed". 0.5 SD is a deliberately modest,
# advisory bar — the goal is to FLAG obvious artifacts (signal ≈ 0 / negative), not
# to gate detection. Never presented as a diagnostic threshold.
DEFAULT_MIN_SIGNAL_SD = 0.5


def normalize_intensity(img: np.ndarray, brain_mask: Optional[np.ndarray] = None) -> Optional[np.ndarray]:
    """Z-score an intensity volume within the brain (or nonzero voxels), so two
    timepoints acquired with different scaling/offset are comparable. Returns None
    when the volume is uninformative (too few voxels / no contrast)."""
    img = np.asarray(img, dtype=np.float32)
    if brain_mask is not None and np.count_nonzero(brain_mask) >= 10:
        vals = img[brain_mask > 0]
    else:
        vals = img[img != 0]
    if vals.size < 10:
        return None
    mu = float(vals.mean())
    sd = float(vals.std())
    if sd <= 1e-6:
        return None
    return (img - mu) / sd


def subtraction_map(
    fixed_img: np.ndarray,
    registered_moving_img: np.ndarray,
    brain_mask: Optional[np.ndarray] = None,
) -> Optional[np.ndarray]:
    """Normalized subtraction (follow-up − baseline) on CO-REGISTERED FLAIR.

    Positive voxels = signal that appeared/brightened at follow-up (new-lesion
    territory). Both volumes are z-scored WITHIN THE BRAIN DOMAIN (adversarial
    Finding 2: z-scoring over the whole nonzero FOV mixes skull/scalp and the
    resample zero-pad rim, injecting a global offset that drifts the confirmation
    threshold). Returns None if either volume can't be normalized.
    """
    nf = normalize_intensity(fixed_img, brain_mask)
    nm = normalize_intensity(registered_moving_img, brain_mask)
    if nf is None or nm is None:
        return None
    return nm - nf


def confirm_new_candidates(
    changes: list,
    registered_tp2_bin: np.ndarray,
    subtraction: np.ndarray,
    brain_domain: Optional[np.ndarray] = None,
    min_signal_sd: float = DEFAULT_MIN_SIGNAL_SD,
) -> dict:
    """Annotate each status=='new' change with an advisory `subtraction_confirmed`.

    Adversarial-hardened (Findings 1/3):
      * Each new candidate is matched to its lesion component by CENTROID PROXIMITY
        (not a rounded-voxel lookup, which could land on an adjacent lesion).
      * A candidate whose component TOUCHES THE BRAIN-DOMAIN BOUNDARY (brain/FOV
        edge, resample zero-pad rim) is WITHHELD (subtraction_confirmed=None,
        subtraction_note="border") — this is exactly where a linear-interpolation
        edge would falsely "confirm" a misregistration phantom.
      * The mean subtraction is measured over component ∩ brain_domain only.

    Returns {new_total, new_subtraction_confirmed, new_withheld, min_signal_sd};
    mutates `changes` in place. A verdict is never a diagnosis — advisory only.
    """
    from scipy.ndimage import center_of_mass, binary_erosion
    from app.services.lesion_metrics import label_lesions

    labeled, n = label_lesions(registered_tp2_bin > 0)
    dz, dy, dx = labeled.shape
    sub = np.asarray(subtraction)

    if brain_domain is not None:
        domain = np.asarray(brain_domain) > 0
    else:
        domain = np.ones(labeled.shape, dtype=bool)
    # "Interior" of the valid domain: a component reaching outside the eroded domain
    # is touching the brain/FOV boundary and is not trustworthy for subtraction.
    interior = binary_erosion(domain, iterations=1) if domain.any() else domain

    # Component centroids (for proximity matching) computed once.
    comp_ids = list(range(1, n + 1))
    comp_centroids = center_of_mass(labeled > 0, labeled, comp_ids) if n > 0 else []
    cc = {cid: c for cid, c in zip(comp_ids, comp_centroids)}

    new_total = 0
    confirmed = 0
    withheld = 0

    for ch in changes:
        if ch.get("status") != "new":
            continue
        new_total += 1
        target = (ch.get("centroid_z"), ch.get("centroid_y"), ch.get("centroid_x"))
        if any(t is None for t in target):
            ch["subtraction_signal"] = None
            ch["subtraction_confirmed"] = None
            ch["subtraction_note"] = "no-centroid"
            withheld += 1
            continue

        # Match to the nearest component centroid (should be near-exact: the change
        # centroids ARE component centroids of the same 18-conn labeling).
        best_lbl, best_d = 0, None
        for cid, c in cc.items():
            d = (c[0] - target[0]) ** 2 + (c[1] - target[1]) ** 2 + (c[2] - target[2]) ** 2
            if best_d is None or d < best_d:
                best_d, best_lbl = d, cid
        if best_lbl == 0 or best_d is None or best_d > 4.0:  # >2 voxels off → no match
            ch["subtraction_signal"] = None
            ch["subtraction_confirmed"] = None
            ch["subtraction_note"] = "unmatched"
            withheld += 1
            continue

        region = labeled == best_lbl
        # Finding 1: reject candidates at the brain/FOV boundary (misreg-rim artifacts).
        if not region[interior].any() or (region & ~interior).any():
            ch["subtraction_signal"] = None
            ch["subtraction_confirmed"] = None
            ch["subtraction_note"] = "border"
            withheld += 1
            continue

        region_in = region & domain
        if not region_in.any():
            ch["subtraction_signal"] = None
            ch["subtraction_confirmed"] = None
            ch["subtraction_note"] = "outside-domain"
            withheld += 1
            continue

        sig = float(sub[region_in].mean())
        ch["subtraction_signal"] = round(sig, 3)
        ch["subtraction_confirmed"] = bool(sig >= min_signal_sd)
        ch["subtraction_note"] = "assessed"
        if ch["subtraction_confirmed"]:
            confirmed += 1

    return {
        "new_total": new_total,
        "new_subtraction_confirmed": confirmed,
        "new_withheld": withheld,
        "min_signal_sd": min_signal_sd,
    }
