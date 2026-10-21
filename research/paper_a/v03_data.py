"""Paper A v0.3 — data locations and cohort metadata (no analysis here).

Inputs (local, read-only, never committed):
  data/cohorts/cloud-2026-10/flames/{case}_f{k}_prob.nii.gz   FLAMeS fold k (k = 0..4), no TTA,
                                                              uint8 on disk + NIfTI scl_slope; nibabel
                                                              get_fdata() returns the probability
  data/cohorts/cloud-2026-10/flames/{case}_gt.nii.gz          expert lesion mask, same grid
  data/cohorts/cloud-2026-10/lstai/{case}_lstai_prob[_m1|_m2|_m3].nii.gz   LST-AI v1.2.0
  data/cohorts/sibbms-controls-flames/sub-NNN_{prob,gt}.nii.gz 30 healthy controls, FLAMeS fold 0
                                                              (August run, float32)
The data folder is looked up in $PAPER_A_DATA_ROOT, then <repo>/data/cohorts, then the main
checkout of a git worktree (<repo>/../../../data/cohorts).
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
RECORDS = os.path.join(ROOT, "docs", "research", "records")


def _data_root():
    cands = [os.environ.get("PAPER_A_DATA_ROOT", ""), os.path.join(ROOT, "data", "cohorts"),
             os.path.abspath(os.path.join(ROOT, "..", "..", "..", "data", "cohorts"))]
    for c in cands:
        if c and os.path.isdir(os.path.join(c, "cloud-2026-10")):
            return c
    raise FileNotFoundError("data/cohorts/cloud-2026-10 not found; set PAPER_A_DATA_ROOT")


DATA_ROOT = _data_root()
CLOUD = os.path.join(DATA_ROOT, "cloud-2026-10")
CONTROLS_DIR = os.path.join(DATA_ROOT, "sibbms-controls-flames")
OLD_DIRS = {"mslesseg": os.path.join(DATA_ROOT, "mslesseg-flames"),
            "openms": os.path.join(DATA_ROOT, "openms-flames")}

# Ljubljana (open_ms_data) patients that NO FLAMeS fold trained on (v0.2 forensic records,
# docs/research/records/2026-10-17_flames_fold_membership.json -> never_trained_any_fold).
OPENMS_CLEAN = (16, 17, 18, 19, 20, 26, 27, 28, 29, 30)

# Site acquisition class, fixed from the dataset descriptions (docs/research/cohorts-extra.md on
# branch research/cloud-compute-ledger; data/registry.yaml), NOT from the analysis data.
SITE_INFO = {
    "mslesseg": {"label": "MSLesSeg (Catania; 8 scanner models in its acquisition table)", "acq": "1mm",
                 "note": "delivered co-registered to MNI 1 mm; NATIVE FLAIR slices 2-5 mm per the "
                         "release's patient_scanners_info_FLAIR.csv (corrected 2026-10-21, protocol "
                         "entry 9; 'acq' = grid as delivered)"},
    "openms": {"label": "Ljubljana open_ms_data (3 T Siemens), FLAMeS-clean 10", "acq": "1mm",
               "note": "3D FLAIR 0.47 x 0.47 x 0.8 mm native, MNI 1 mm here"},
    "ms3seg": {"label": "MS3SEG (Iran, Toshiba 1.5 T)", "acq": "2d_thick",
               "note": "2D FLAIR 0.898 mm in-plane, 6.0-8.1 mm slice spacing; HD-BET"},
    "muslim": {"label": "Muslim 2022 (Baghdad, ~20 centres, 1.5 T)", "acq": "2d_thick",
               "note": "2D FLAIR 4.86-8.3 mm slices; in-plane pixel size ESTIMATED; HD-BET"},
    "pedims": {"label": "PediMS (Siemens Skyra 3 T, children)", "acq": "2d_thick",
               "note": "2D FLAIR 0.75 x 0.75 x 3.9 mm; SynthStrip (distributed stripped)"},
}
SITES = tuple(SITE_INFO)
ONE_MM_SITES = ("mslesseg", "openms")
THICK_SITES = ("ms3seg", "muslim", "pedims")


def case_cohort(case):
    return case.split("_", 1)[0]


def patient_of(case):
    """Patient identifier (the resampling / splitting unit)."""
    coh = case_cohort(case)
    if coh == "mslesseg":
        return "mslesseg_" + re.match(r"mslesseg_(P\d+)", case).group(1)
    if coh == "pedims":
        return "pedims_" + re.match(r"pedims_(P\d+)", case).group(1)
    return case                                        # single-timepoint cohorts


def openms_number(case):
    m = re.match(r"openms_patient(\d+)$", case)
    return int(m.group(1)) if m else None


def openms_clean_ids():
    return [f"openms_patient{n:02d}" for n in OPENMS_CLEAN]


def flames_clean(case):
    """True if the scan may be used to EVALUATE FLAMeS (not FLAMeS training data)."""
    if case_cohort(case) == "openms":
        return openms_number(case) in OPENMS_CLEAN
    return True
