"""Shared definitions for the public-dataset pipeline + the CALM-MS target format.

Two jobs:

1. **Path bootstrapping** — make the repo's frozen backend service functions
   importable from anywhere (``ensure_backend_on_path``) so this offline tooling
   consumes the *exact* candidate-extraction / feature / conformal code that the
   product runs. Training-inference divergence is a Class C hazard; sharing one
   source of truth is the mitigation.

2. **The two target formats** this pipeline produces, matched to what the repo
   already expects:

   * The **cohort record** (``StandardizedCase``) — the on-disk per-case layout
     that ``scripts/calm-ms/run_lstai_cohort.py`` and ``run_conformal_experiment.py``
     consume: a ``cohort.csv`` with ``case,t1_path,flair_path,expert_path`` plus,
     once a base segmenter has run, ``{case}_prob.nii.gz`` + ``{case}_gt.nii.gz``.

   * The **CALM-MS calibration record** — the per-candidate table the conformal
     layer calibrates on: ``score`` (or the full ``FEATURE_NAMES`` feature
     vector), a ``is_false`` TP/FP label, and a ``site`` tag for site-conditional
     (Mondrian) nulls. See ``to_calm_calibration``.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Optional, Tuple

import yaml

# ---------------------------------------------------------------------------
# Repo layout
# ---------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]                    # research/data_pipeline -> repo root
BACKEND = REPO_ROOT / "backend"
DATASETS_YAML = HERE / "datasets.yaml"


def ensure_backend_on_path() -> None:
    """Put ``<repo>/backend`` on ``sys.path`` so ``import app.services...`` works.

    Idempotent. Mirrors the ``sys.path.insert`` prologue every script under
    ``scripts/calm-ms/`` uses, so this package reuses the same frozen functions.
    """
    b = str(BACKEND)
    if b not in sys.path:
        sys.path.insert(0, b)


def load_manifest(path: os.PathLike | str = DATASETS_YAML) -> dict:
    """Parse ``datasets.yaml`` into a plain dict. Raises if the file is missing."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"dataset manifest not found: {p}")
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def iter_datasets(manifest: dict):
    """Yield ``(name, entry)`` for each dataset in a loaded manifest."""
    for name, entry in (manifest.get("datasets") or {}).items():
        yield name, entry


# ---------------------------------------------------------------------------
# Target format 1 — the standardized cohort record
# ---------------------------------------------------------------------------
# Canonical sequence keys used across the pipeline (lower-case, hyphenated).
SEQ_T1 = "t1"
SEQ_T1GD = "t1gd"
SEQ_T2 = "t2"
SEQ_PD = "pd"
SEQ_FLAIR = "flair"
KNOWN_SEQUENCES = (SEQ_T1, SEQ_T1GD, SEQ_T2, SEQ_PD, SEQ_FLAIR)

# Coordinate spaces we tag records with.
SPACE_NATIVE = "native"
SPACE_MNI_1MM = "MNI_1mm"


@dataclass
class StandardizedCase:
    """One preprocessed case in the common format.

    Attributes
    ----------
    case_id:      pipeline-local id, e.g. ``"mslesseg_P01_T1"``.
    dataset:      manifest key the case came from, e.g. ``"mslesseg"``.
    site:         scanner/site tag used as the CALM-MS Mondrian stratum.
    images:       sequence-key -> absolute NIfTI path (skull-stripped/registered).
    lesion_mask:  absolute path to the binary expert mask, or ``None`` if unlabeled.
    space:        ``"native"`` or ``"MNI_1mm"``.
    spacing:      voxel size in mm (z, y, x).
    edss:         optional Expanded Disability Status Scale score, if the dataset
                  ships it (only the Baghdad/Mendeley cohort does, publicly).
    meta:         free-form provenance (rater count, field strength, ...).
    """

    case_id: str
    dataset: str
    site: str
    images: Dict[str, str]
    lesion_mask: Optional[str] = None
    space: str = SPACE_NATIVE
    spacing: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    edss: Optional[float] = None
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["spacing"] = list(self.spacing)
        return d

    def cohort_row(self) -> dict:
        """A row for ``cohort.csv`` (the schema the LST-AI runner consumes).

        Emits ``case,t1_path,flair_path,expert_path`` plus the extra columns this
        pipeline adds (``dataset,site,edss``) which downstream tools may ignore.
        """
        return {
            "case": self.case_id,
            "t1_path": self.images.get(SEQ_T1, ""),
            "flair_path": self.images.get(SEQ_FLAIR, ""),
            "expert_path": self.lesion_mask or "",
            "dataset": self.dataset,
            "site": self.site,
            "edss": "" if self.edss is None else self.edss,
        }


COHORT_CSV_FIELDS = ["case", "t1_path", "flair_path", "expert_path",
                     "dataset", "site", "edss"]


# ---------------------------------------------------------------------------
# Target format 2 — the CALM-MS per-candidate calibration record
# ---------------------------------------------------------------------------
# Columns of the calibration table emitted by ``to_calm_calibration``. The
# conformal layer needs, at minimum, (score, is_false, site); the feature columns
# (FEATURE_NAMES, filled in at emit time) let a learned scorer be retrained.
CALIB_BASE_FIELDS = ["dataset", "case", "site", "candidate_label",
                     "score", "is_false", "n_voxels", "volume_mm3", "edss"]


def calib_feature_fields():
    """The FEATURE_NAMES columns, resolved from the frozen backend module.

    Kept as a function (not a module constant) so importing ``common`` never
    forces the backend import — callers that only need cohort helpers stay light.
    """
    ensure_backend_on_path()
    from app.services.calm_ms_lesion_features import FEATURE_NAMES
    return list(FEATURE_NAMES)
