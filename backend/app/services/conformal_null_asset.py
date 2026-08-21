"""Frozen CALM-MS calibration-null asset loader + validated presets + the
enforced exchangeability invariant.

The conformal endpoint's statistical guarantee is valid ONLY when a request's
probability map comes from the SAME base model (FLAMeS) on the SAME MNI grid as
the calibration null. The adversarial Class C review was unanimous: this must be
an ENFORCED, FAIL-CLOSED refusal — not a comment, not a soft warning. This module
owns that invariant.

Design (per the review):
  * Load the versioned, provenance-stamped null asset ONCE (module singleton).
    Refuse to serve if it is missing or empty (never silently return a void
    guarantee).
  * Expose ONLY a small set of VALIDATED PRESETS (enum), each mapping to a FROZEN
    (alpha, threshold) operating point. The candidate-extraction threshold is part
    of the frozen point — it is NOT a user parameter. Raw alpha/threshold are
    rejected at the API layer, never accepted.
  * `assert_compatible(grid_shape, voxel_spacing)` raises ProvenanceMismatch unless
    the incoming map matches the null's stamped grid exactly.

v1 uses the raw pooled-probability null; the learned scorer is deferred to v2.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

import numpy as np

# Validated operating points. High-sensitivity is the LOCKED default: in MS the
# costly error is a MISS, and this is an ADDITIVE second-reader overlay (it never
# deletes candidates), so a permissive FDR budget is the safe default.
PRESETS: dict[str, float] = {
    "high_sensitivity": 0.30,   # LOCKED DEFAULT
    "balanced": 0.20,
    "high_precision": 0.10,
}
DEFAULT_PRESET = "high_sensitivity"

# The null is valid ONLY for this base model. A null stamped with any other model
# must be refused at load — the guarantee is model-specific (exchangeability).
EXPECTED_BASE_MODEL = "FLAMeS"
# A near-degenerate null (few distinct values / ~zero spread) maps every test score
# to p ~ 1/(n+1) and selects everything, silently INVERTING the FDR control. Refuse.
MIN_NULL_DISTINCT = 20
MIN_NULL_STD = 1e-3

_ASSET_PATH = os.path.join(os.path.dirname(__file__), "assets", "calm_ms_null_flames_v2.npz")


class ConformalAssetError(RuntimeError):
    """The null asset is missing/empty/corrupt — the endpoint must fail closed."""


class ProvenanceMismatch(ValueError):
    """The request's probability map does not match the null's provenance/grid.

    The FDR guarantee would be void; the endpoint must REFUSE (4xx), not warn."""


@dataclass
class NullAsset:
    null_scores: np.ndarray
    provenance: dict
    ood_reference: np.ndarray | None = None   # (n_cases, n_features) calibration OOD envelope

    @property
    def threshold(self) -> float:
        return float(self.provenance["threshold"])

    @property
    def min_volume_mm3(self) -> float:
        return float(self.provenance["min_volume_mm3"])

    @property
    def score_pooling(self) -> str:
        return str(self.provenance.get("score_pooling", "mean"))

    @property
    def voxel_spacing(self) -> tuple[float, float, float]:
        return tuple(float(x) for x in self.provenance["voxel_spacing"])  # type: ignore[return-value]

    @property
    def grid_shape(self) -> tuple[int, int, int]:
        return tuple(int(x) for x in self.provenance["grid_shape"])  # type: ignore[return-value]

    def assert_compatible(self, grid_shape, voxel_spacing, tol: float = 1e-3) -> None:
        """Fail closed unless the incoming map is on the null's exact grid/spacing.

        This is THE exchangeability enforcement: same base model is asserted by the
        caller (the prob map must be FLAMeS-derived), and same space/grid is checked
        here. Any mismatch voids the guarantee, so we refuse."""
        want_shape = self.grid_shape
        got_shape = tuple(int(x) for x in grid_shape)
        # Validate lengths first: zip() would silently truncate a short spacing tuple
        # and skip the missing axis (adversarial finding).
        if len(got_shape) != 3 or len(tuple(voxel_spacing)) != 3 or len(want_shape) != 3:
            raise ProvenanceMismatch("grid and voxel_spacing must both be length 3")
        if got_shape != want_shape:
            raise ProvenanceMismatch(
                f"probability map grid {got_shape} != calibration grid {want_shape}; "
                f"the FDR guarantee is valid only on the {self.provenance['preprocessing_space']} grid")
        want_sp = self.voxel_spacing
        got_sp = tuple(float(x) for x in voxel_spacing)
        if any(abs(a - b) > tol for a, b in zip(got_sp, want_sp)):
            raise ProvenanceMismatch(
                f"voxel spacing {got_sp} != calibration spacing {want_sp}")


_asset: NullAsset | None = None


def load_null_asset(path: str = _ASSET_PATH) -> NullAsset:
    """Load + validate the frozen null asset. Raises ConformalAssetError (fail
    closed) if missing/empty/corrupt — the endpoint turns this into a clear 5xx/503
    rather than a silent void guarantee."""
    if not os.path.exists(path):
        raise ConformalAssetError(f"CALM-MS null asset not found: {path}")
    try:
        data = np.load(path, allow_pickle=False)
        null = np.asarray(data["null_scores"], dtype=float)
        provenance = json.loads(str(data["provenance"]))
        ood_reference = np.asarray(data["ood_reference"], dtype=float) if "ood_reference" in data else None
    except Exception as e:  # noqa: BLE001
        raise ConformalAssetError(f"CALM-MS null asset unreadable: {e}") from e
    if null.size == 0:
        raise ConformalAssetError("CALM-MS null asset is empty — refusing to serve a void guarantee")
    for k in ("threshold", "min_volume_mm3", "voxel_spacing", "grid_shape", "base_model"):
        if k not in provenance:
            raise ConformalAssetError(f"CALM-MS null asset missing provenance field '{k}'")
    if provenance.get("base_model") != EXPECTED_BASE_MODEL:
        raise ConformalAssetError(
            f"CALM-MS null base_model {provenance.get('base_model')!r} != expected {EXPECTED_BASE_MODEL!r}")
    # Contamination gate (fail closed): a null whose cohorts overlap the base model's
    # TRAINING data yields in-sample false-candidate scores that are NOT exchangeable
    # with held-out cases (the exact defect the v2 decontamination fixed). Refuse to
    # serve any null not explicitly stamped base_model_independent=true. This makes a
    # contaminated rebuild structurally un-shippable rather than trusted by convention.
    if provenance.get("base_model_independent") is not True:
        raise ConformalAssetError(
            "CALM-MS null is not stamped base_model_independent=true — its cohorts may "
            "overlap the base model's training set (non-exchangeable false-candidate "
            "scores); refusing to serve a potentially contaminated guarantee")
    if np.unique(null).size < MIN_NULL_DISTINCT or float(np.std(null)) < MIN_NULL_STD:
        raise ConformalAssetError(
            "CALM-MS null is degenerate (too few distinct values / near-zero spread) — "
            "it cannot produce calibrated p-values; refusing to serve")
    return NullAsset(null_scores=null, provenance=provenance, ood_reference=ood_reference)


def get_null_asset() -> NullAsset:
    """Module-singleton accessor (loads once). Fail-closed on any asset problem."""
    global _asset
    if _asset is None:
        _asset = load_null_asset()
    return _asset


def resolve_preset(preset: str) -> tuple[float, float]:
    """(alpha, threshold) for a validated preset. Raises KeyError for anything else
    — raw alpha/threshold are never accepted."""
    if preset not in PRESETS:
        raise KeyError(preset)
    return PRESETS[preset], get_null_asset().threshold
