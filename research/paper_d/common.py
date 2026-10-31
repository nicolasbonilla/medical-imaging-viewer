"""Paths, cohort enumeration and contamination flags for paper D (research code, not the device).

Data are PUBLIC and local (git-ignored): data/cohorts/cloud-2026-10/{flames,lstai}/ and the raw
releases in data/external/{mslesseg,open_ms_data}/. No data of the device's users is read.

The data root is resolved from --data-root, else the PAPER_D_DATA_ROOT environment variable, else
<repo>/data. A git worktree has no data/cohorts of its own, so pass the main checkout's data/.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
DEVICE_MSMASK = BACKEND_DIR / "data" / "msmask" / "sub-mni152_space-mni_msmask.nii.gz"

# SHA-256 of the atlas files (LST-AI v1.1.0 release lst_data.zip; identical to the LST-AI v1.2.0
# docker image recorded in data/cohorts/cloud-2026-10/manifests/lstai-full-a.json).
MSMASK_SHA256 = "2ad50b1433a040a4d5b58ac064f984211b466f83081fc5d344ff13eff56cdd0f"
ATLAS_T1_SHA256 = "d4104bbda56ad46c898135c805b394856993aea239b942f3a705136cd2b4476b"

# FLAMeS training data include the Ljubljana 3D MS DB (Lesjak 2018) EXCEPT these patients
# (protocol §3). MSLesSeg was not in FLAMeS training. LST-AI was trained on neither.
LJUBLJANA_FLAMES_CLEAN = set(range(16, 21)) | set(range(26, 31))

# Pre-specified exclusion (protocol §3): the public MSLesSeg release ships a blank T1 for this
# scan (0.097 % non-zero voxels), so LST-AI skipped it and no deformable registration exists.
EXCLUDED_SCANS = {"mslesseg_P49_T2": "blank T1 in the public release (no LST-AI map, no G1 warp)"}

FLAMES_FOLDS = (0, 1, 2, 3, 4)
LSTAI_MODELS = (1, 2, 3)


def data_root(cli_value: Optional[str] = None) -> Path:
    root = cli_value or os.environ.get("PAPER_D_DATA_ROOT") or str(REPO_ROOT / "data")
    p = Path(root)
    if not (p / "cohorts" / "cloud-2026-10").is_dir():
        raise FileNotFoundError(
            f"{p}/cohorts/cloud-2026-10 not found; pass --data-root pointing at the main checkout's data/")
    return p


def cache_dir(root: Path) -> Path:
    d = root / "cache" / "paper-d"
    d.mkdir(parents=True, exist_ok=True)
    return d


def experiments_dir(root: Path) -> Path:
    d = root / "experiments" / "paper-d"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass(frozen=True)
class Scan:
    case: str                 # e.g. mslesseg_P10_T1, mslesseg_P54, openms_patient16
    dataset: str              # mslesseg | ljubljana
    patient: str              # cluster id for the bootstrap
    flames_in_sample: bool    # True = FLAMeS saw this patient in training (contaminated)
    gt: str
    flames: tuple             # fold 0..4 probability maps
    lstai_ens: Optional[str]
    lstai_models: tuple       # m1..m3
    t1: Optional[str]

    def as_dict(self):
        return asdict(self)


def _mslesseg_t1(ext: Path, case: str) -> Path:
    m = re.fullmatch(r"mslesseg_(P\d+)_(T\d+)", case)
    base = ext / "mslesseg" / "MSLesSeg Dataset"
    if m:
        p, t = m.groups()
        return base / "train" / p / t / f"{p}_{t}_T1.nii.gz"
    p = case.split("_", 1)[1]
    return base / "test" / p / f"{p}_T1.nii.gz"


def enumerate_scans(root: Path, include_contaminated: bool = True) -> list[Scan]:
    """All MNI-space scans (MSLesSeg + Ljubljana) with every input present, minus EXCLUDED_SCANS."""
    fl = root / "cohorts" / "cloud-2026-10" / "flames"
    ls = root / "cohorts" / "cloud-2026-10" / "lstai"
    ext = root / "external"
    scans: list[Scan] = []
    for gt in sorted(fl.glob("*_gt.nii.gz")):
        case = gt.name[: -len("_gt.nii.gz")]
        if case.startswith("mslesseg_"):
            dataset = "mslesseg"
            patient = "mslesseg_" + case.split("_")[1]
            in_sample = False
            t1 = _mslesseg_t1(ext, case)
        elif case.startswith("openms_patient"):
            dataset = "ljubljana"
            patient = case
            pid = int(case[len("openms_patient"):])
            in_sample = pid not in LJUBLJANA_FLAMES_CLEAN
            t1 = (ext / "open_ms_data" / "cross_sectional" / "MNI" / f"patient{pid:02d}" /
                  "T1_N4_noneck_reduced_winsor_regtoFLAIR_brain_N4_regtoMNI.nii.gz")
        else:
            continue  # native-space cohorts (MS3SEG, MUSLIM, PediMS): out of scope (protocol §3)
        if case in EXCLUDED_SCANS:
            continue
        if in_sample and not include_contaminated:
            continue
        folds = tuple(str(fl / f"{case}_f{k}_prob.nii.gz") for k in FLAMES_FOLDS)
        lens = ls / f"{case}_lstai_prob.nii.gz"
        lmods = tuple(str(ls / f"{case}_lstai_prob_m{k}.nii.gz") for k in LSTAI_MODELS)
        missing = [p for p in (*folds, str(lens), *lmods, str(t1)) if not Path(p).exists()]
        if missing:
            raise FileNotFoundError(f"{case}: missing inputs {missing}")
        scans.append(Scan(case, dataset, patient, in_sample, str(gt), folds, str(lens), lmods, str(t1)))
    return scans


def sha256(path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
