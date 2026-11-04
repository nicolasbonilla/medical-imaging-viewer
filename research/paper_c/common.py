"""Paper C — data locations, lesion components and the two ground-truth rules (no analysis here).

Research code, not the medical device. Read-only use of the app's longitudinal functions.

Inputs (local, read-only, never committed; all public data):
  open_ms_data LONGITUDINAL (Lesjak et al., Neuroinformatics 2016; CC-BY):
    data/external/open_ms_longitudinal/longitudinal/coregistered/patientNN/
        study1_FLAIR.nii.gz, study2_FLAIR.nii.gz  co-registered (common space), N4-corrected 2D FLAIR
        brainmask.nii.gz                          brain mask (common space)
        gt.nii.gz                                 expert white-matter lesion CHANGE mask (one label)
  MSLesSeg (Rondinella et al., Sci Data 2025; CC-BY-4.0), patients with >= 2 timepoints:
    data/external/mslesseg/MSLesSeg Dataset/train/Pnn/Tk/Pnn_Tk_{FLAIR,MASK}.nii.gz  (MNI 1 mm)
    data/cohorts/cloud-2026-10/flames/mslesseg_Pnn_Tk_f{0..4}_prob.nii.gz          FLAMeS folds
    data/external/mslesseg/MSLesSeg Dataset/info_dataset/*.csv                      acquisition table
The data folder is looked up in $PAPER_C_DATA_ROOT, then <repo>/data, then the main checkout of a
git worktree (<repo>/../../../data).
"""
import csv
import glob
import math
import os
import re
import sys

import nibabel as nib
import numpy as np
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
RECORDS = os.path.join(ROOT, "docs", "research", "records")
BACKEND = os.path.join(ROOT, "backend")

STRUCT18 = ndimage.generate_binary_structure(3, 2)     # 18-connectivity (app RC-030 convention)
DETECT_MM3 = 3.0                                         # MSSEG noise floor (app lesion_metrics)
CLIN_MM3 = (4.0 / 3.0) * math.pi * 1.5 ** 3              # 3-mm-diameter sphere = 14.137 mm3 (app)
ENLARGE_REL = 1.5                                        # truth rule: >= 50 % growth ...
ENLARGE_ABS_MM3 = CLIN_MM3                               # ... and >= 14.14 mm3 of new tissue


def _data_root():
    cands = [os.environ.get("PAPER_C_DATA_ROOT", ""), os.path.join(ROOT, "data"),
             os.path.abspath(os.path.join(ROOT, "..", "..", "..", "data"))]
    for c in cands:
        if c and os.path.isdir(os.path.join(c, "cohorts", "cloud-2026-10")):
            return c
    raise FileNotFoundError("data/cohorts/cloud-2026-10 not found; set PAPER_C_DATA_ROOT")


DATA = _data_root()
OMS_LONG = os.path.join(DATA, "external", "open_ms_longitudinal", "longitudinal", "coregistered")
MSL = os.path.join(DATA, "external", "mslesseg", "MSLesSeg Dataset")
FLAMES = os.path.join(DATA, "cohorts", "cloud-2026-10", "flames")
OMS_LONG_FLAMES = os.path.join(DATA, "cohorts", "openms-longitudinal-flames")  # cloud job output


def app_longitudinal():
    """The app's own longitudinal functions (read-only import from backend/)."""
    if BACKEND not in sys.path:
        sys.path.insert(0, BACKEND)
    from app.services import longitudinal_tracking_service as lts   # noqa: E402
    from app.services import longitudinal_subtraction as lsub       # noqa: E402
    return lts, lsub


# ----------------------------------------------------------------------------- components
def voxel_volume(img):
    return float(np.prod(img.header.get_zooms()[:3]))


def components(mask, voxvol, min_mm3=0.0):
    """18-connected components of a boolean mask -> (label array, list of dicts)."""
    lab, n = ndimage.label(mask, structure=STRUCT18)
    out = []
    if n == 0:
        return lab, out
    counts = np.bincount(lab.ravel(), minlength=n + 1)
    slices = ndimage.find_objects(lab)
    for i in range(1, n + 1):
        vol = counts[i] * voxvol
        if vol < min_mm3:
            continue
        out.append({"id": i, "slice": slices[i - 1], "voxels": int(counts[i]), "volume_mm3": float(vol)})
    return lab, out


def comp_mask(lab, comp):
    """Full-size boolean mask of one component (bounding-box local work, full-size result)."""
    m = np.zeros(lab.shape, dtype=bool)
    sl = comp["slice"]
    m[sl] = lab[sl] == comp["id"]
    return m


# ----------------------------------------------------------------------------- truth rules
def truth_from_two_masks(mask_a, mask_b, voxvol):
    """APPROXIMATE new/enlarging truth from two per-timepoint lesion masks on one grid (MSLesSeg).

    Components of B (18-conn, >= 3 mm3):
      new        : no voxel within 1 voxel (18-dilation) of A;
      enlarging  : touches the 18-dilation of A, and its volume >= 1.5 x the summed volume of the
                   A components it touches AND it adds >= 14.14 mm3;
      persistent : otherwise.
    Change region: whole component (new), component minus A (enlarging).
    Active pair  : >= 1 new component >= 14.14 mm3 (3 mm diameter) or >= 1 enlarging component.
    This is NOT an expert change annotation: per-timepoint masks were drawn per scan, so annotation
    differences between timepoints create spurious 'new' lesions (and can hide real ones)."""
    A = mask_a > 0
    B = mask_b > 0
    a_dil = ndimage.binary_dilation(A, structure=STRUCT18)
    lab_a, comps_a = components(A, voxvol)
    vol_a = {c["id"]: c["volume_mm3"] for c in comps_a}
    lab_b, comps_b = components(B, voxvol, DETECT_MM3)
    region = np.zeros(A.shape, dtype=bool)
    lesion_map = np.zeros(A.shape, dtype=np.int32)      # countable truth lesions (sensitivity)
    items = []
    for c in comps_b:
        sl = c["slice"]
        cm = lab_b[sl] == c["id"]
        if not (cm & a_dil[sl]).any():
            kind = "new"
            region[sl] |= cm
            if c["volume_mm3"] >= CLIN_MM3:
                lesion_map[sl][cm] = int(lesion_map.max()) + 1   # contiguous ids 1..L
        else:
            # A components touching the component or its 1-voxel shell
            shell = ndimage.binary_dilation(np.pad(cm, 1), structure=STRUCT18)[1:-1, 1:-1, 1:-1]
            touched = np.unique(lab_a[sl][shell & A[sl]])
            touched = touched[touched > 0]
            va = float(sum(vol_a.get(int(t), 0.0) for t in touched))
            growth = c["volume_mm3"] - va
            if c["volume_mm3"] >= ENLARGE_REL * va and growth >= ENLARGE_ABS_MM3:
                kind = "enlarging"
                region[sl] |= cm & ~A[sl]
                lesion_map[sl][cm & ~A[sl]] = int(lesion_map.max()) + 1   # contiguous ids 1..L
            else:
                kind = "persistent"
        items.append({"kind": kind, "volume_mm3": round(c["volume_mm3"], 2)})
    n_new_clin = sum(1 for it in items if it["kind"] == "new" and it["volume_mm3"] >= CLIN_MM3)
    n_new_any = sum(1 for it in items if it["kind"] == "new")
    n_enl = sum(1 for it in items if it["kind"] == "enlarging")
    return {"items": items, "n_new_clinical": n_new_clin, "n_new_detectable": n_new_any,
            "n_enlarging": n_enl, "active": bool(n_new_clin + n_enl >= 1),
            "active_lenient": bool(n_new_any + n_enl >= 1)}, region, lesion_map


def truth_from_change_mask(gt, sub, domain, voxvol):
    """EXPERT change truth (open_ms longitudinal). gt has one label for 'lesion change'; the
    direction is not encoded. Each 18-component >= 3 mm3 is classified by the sign of the mean
    normalised subtraction (follow-up - baseline) inside it (over the brain domain):
    positive = new/enlarging, non-positive = shrinking/resolving.
    Active patient: >= 1 positive component >= 14.14 mm3."""
    lab, comps = components(gt > 0, voxvol, DETECT_MM3)
    region_any = np.zeros(gt.shape, dtype=bool)
    region_pos = np.zeros(gt.shape, dtype=bool)
    lesion_map = np.zeros(gt.shape, dtype=np.int32)      # positive components >= 14.14 mm3
    items = []
    for c in comps:
        sl = c["slice"]
        cm = lab[sl] == c["id"]
        vals = sub[sl][cm & domain[sl]]
        mean_d = float(vals.mean()) if vals.size else float("nan")
        pos = bool(vals.size and mean_d > 0)
        region_any[sl] |= cm
        if pos:
            region_pos[sl] |= cm
            if c["volume_mm3"] >= CLIN_MM3:
                lesion_map[sl][cm] = int(lesion_map.max()) + 1   # contiguous ids 1..L
        items.append({"volume_mm3": round(c["volume_mm3"], 2), "mean_sub": round(mean_d, 3), "positive": pos})
    n_pos_clin = sum(1 for it in items if it["positive"] and it["volume_mm3"] >= CLIN_MM3)
    return {"items": items, "n_components": len(items), "n_positive": sum(it["positive"] for it in items),
            "n_positive_clinical": n_pos_clin, "active": bool(n_pos_clin >= 1)}, region_any, region_pos, lesion_map


# ----------------------------------------------------------------------------- datasets
def oms_long_patients():
    return [f"patient{i:02d}" for i in range(1, 21)]


def load_oms_long(pid):
    d = os.path.join(OMS_LONG, pid)
    f1 = nib.load(os.path.join(d, "study1_FLAIR.nii.gz"))
    f2 = nib.load(os.path.join(d, "study2_FLAIR.nii.gz"))
    bm = nib.load(os.path.join(d, "brainmask.nii.gz"))
    gt = nib.load(os.path.join(d, "gt.nii.gz"))
    for x in (f2, bm, gt):
        if x.shape[:3] != f1.shape[:3] or np.abs(x.affine - f1.affine).max() > 1e-3:
            raise ValueError(f"{pid}: grid mismatch")
    return {"flair_a": np.asarray(f1.dataobj, dtype=np.float32), "flair_b": np.asarray(f2.dataobj, dtype=np.float32),
            "brain": np.asarray(bm.dataobj) > 0, "gt": np.asarray(gt.dataobj) > 0,
            "voxvol": voxel_volume(f1), "zooms": tuple(float(z) for z in f1.header.get_zooms()[:3]),
            "affine": f1.affine, "paths": {"flair_a": f1.get_filename(), "flair_b": f2.get_filename(),
                                            "brain": bm.get_filename(), "gt": gt.get_filename()}}


def mslesseg_timepoints():
    """{patient: [timepoints...]} for MSLesSeg train patients with FLAIR+MASK and all 5 FLAMeS folds."""
    out = {}
    for pdir in sorted(glob.glob(os.path.join(MSL, "train", "P*")), key=lambda p: int(os.path.basename(p)[1:])):
        p = os.path.basename(pdir)
        tps = []
        for tdir in sorted(glob.glob(os.path.join(pdir, "T*"))):
            t = os.path.basename(tdir)
            ok = all(os.path.exists(os.path.join(tdir, f"{p}_{t}_{s}.nii.gz")) for s in ("FLAIR", "MASK"))
            ok &= all(os.path.exists(os.path.join(FLAMES, f"mslesseg_{p}_{t}_f{k}_prob.nii.gz")) for k in range(5))
            if ok:
                tps.append(t)
        if tps:
            out[p] = sorted(tps, key=lambda t: int(t[1:]))
    return out


def mslesseg_pairs(first_only=False):
    pairs = []
    for p, tps in mslesseg_timepoints().items():
        for i in range(len(tps) - 1):
            pairs.append((p, tps[i], tps[i + 1]))
            if first_only:
                break
    return pairs


def load_mslesseg_tp(p, t, with_prob=True):
    d = os.path.join(MSL, "train", p, t)
    fl = nib.load(os.path.join(d, f"{p}_{t}_FLAIR.nii.gz"))
    mk = nib.load(os.path.join(d, f"{p}_{t}_MASK.nii.gz"))
    out = {"flair": np.asarray(fl.dataobj, dtype=np.float32), "mask": np.asarray(mk.dataobj) > 0,
           "voxvol": voxel_volume(fl), "affine": fl.affine, "shape": fl.shape[:3]}
    if with_prob:
        acc = np.zeros(fl.shape[:3], dtype=np.float32)       # running mean (memory-light)
        for k in range(5):
            pi = nib.load(os.path.join(FLAMES, f"mslesseg_{p}_{t}_f{k}_prob.nii.gz"))
            if pi.shape[:3] != fl.shape[:3] or np.abs(pi.affine - fl.affine).max() > 1e-3:
                raise ValueError(f"{p}_{t} fold {k}: grid mismatch with FLAIR")
            acc += pi.get_fdata(dtype=np.float32)
        out["prob"] = acc / 5.0
    return out


def mslesseg_acquisition():
    """{(patient, timepoint): {scanner, manufacturer, slice_mm}} from the release's FLAIR table."""
    path = os.path.join(MSL, "info_dataset", "patient_scanners_info", "patient_scanners_info_FLAIR.csv")
    out = {}
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f, delimiter=";"):
            out[(row["Patient"], row["Timepoint"])] = {
                "manufacturer": row["MANUFACTURER"], "scanner": row["SCANNER"],
                "slice_mm": row["SliceThickness[mm]"], "pixel": row["PixelSpacing"]}
    return out


def mslesseg_ages():
    """{(patient, timepoint): age in years} from clinical_data.csv (interval = age difference)."""
    path = os.path.join(MSL, "info_dataset", "clinical_data.csv")
    out = {}
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f, delimiter=";"):
            try:
                out[(row["Patient"], row["Timepoint"])] = float(row["Age"].replace(",", "."))
            except (ValueError, KeyError, AttributeError):
                pass
    return out


def patient_key(case):
    m = re.match(r"(P\d+)", case)
    return m.group(1) if m else case
