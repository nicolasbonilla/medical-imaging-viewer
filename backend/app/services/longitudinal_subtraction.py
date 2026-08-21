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
    territory). Both volumes are z-scored first so the difference reflects relative
    signal change, not scanner scaling. Returns None if either volume can't be
    normalized (caller then skips subtraction confirmation).
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
    min_signal_sd: float = DEFAULT_MIN_SIGNAL_SD,
) -> dict:
    """Annotate each status=='new' change with its mean subtraction signal and an
    advisory `subtraction_confirmed` flag.

    For each new candidate, the mean normalized subtraction is measured WITHIN its
    lesion component (in registered TP2 space). A genuine new lesion is brighter on
    follow-up → positive signal; an artifact is ≈0/negative. Returns a summary dict
    {new_total, new_subtraction_confirmed, min_signal_sd}. Mutates `changes` in place.
    """
    from app.services.lesion_metrics import label_lesions

    labeled, _ = label_lesions(registered_tp2_bin > 0)
    dz, dy, dx = labeled.shape
    new_total = 0
    confirmed = 0

    for ch in changes:
        if ch.get("status") != "new":
            continue
        new_total += 1
        cz = int(round(ch.get("centroid_z", -1)))
        cy = int(round(ch.get("centroid_y", -1)))
        cx = int(round(ch.get("centroid_x", -1)))
        if not (0 <= cz < dz and 0 <= cy < dy and 0 <= cx < dx):
            ch["subtraction_signal"] = None
            ch["subtraction_confirmed"] = None
            continue
        lbl = int(labeled[cz, cy, cx])
        if lbl == 0:
            # Centroid rounded off the component (e.g. concave lesion) — sample a
            # small cube around it rather than dropping the measurement.
            z0, z1 = max(0, cz - 1), min(dz, cz + 2)
            y0, y1 = max(0, cy - 1), min(dy, cy + 2)
            x0, x1 = max(0, cx - 1), min(dx, cx + 2)
            region = np.zeros_like(labeled, dtype=bool)
            region[z0:z1, y0:y1, x0:x1] = True
        else:
            region = labeled == lbl
        if not region.any():
            ch["subtraction_signal"] = None
            ch["subtraction_confirmed"] = None
            continue
        sig = float(np.asarray(subtraction)[region].mean())
        ch["subtraction_signal"] = round(sig, 3)
        ch["subtraction_confirmed"] = bool(sig >= min_signal_sd)
        if ch["subtraction_confirmed"]:
            confirmed += 1

    return {
        "new_total": new_total,
        "new_subtraction_confirmed": confirmed,
        "min_signal_sd": min_signal_sd,
    }
