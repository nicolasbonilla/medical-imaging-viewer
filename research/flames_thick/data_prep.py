"""Training data for FLAMeS-thick: MSLesSeg TRAIN only, FLAMeS plans, patient-grouped split.

PROTOCOL.md §4: only MSLesSeg train patients P1-P53 may ever be written into the training dataset.
`assert_trainable` is called for every case before any file is written; it rejects the held-out
evaluation sites (MS3SEG, Muslim, PediMS, every Ljubljana scan incl. the clean 16-20/26-30), the
MSLesSeg test patients P54-P75 and anything else.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import zipfile

import numpy as np

DATASET_ID = 501
DATASET_NAME = "Dataset501_MSLesSegFT"
FLAMES_DATASET = "Dataset004_WML"
FLAMES_MODEL = "nnUNetTrainer_8000epochs__nnUNetPlans__3d_fullres"
FLAMES_FOLD0_SHA256 = "4fc7db24e7c1541b59023df2a2f498a964eb629fe38f4eaec763297dd3fdf861"
MSLESSEG_ZIP_BYTES = 1473284755          # Figshare file 52771814 "MSLesSeg Dataset.zip"
TRAIN_PATIENTS = range(1, 54)            # P1..P53 (official train split)
SPLIT_SEED, N_SPLITS = 12345, 5

_TRAIN_MEMBER = re.compile(r"(?:^|/)train/P(\d+)/T(\d+)/P\1_T\2_(FLAIR|MASK)\.nii\.gz$")
_TRAIN_CASE = re.compile(r"^mslesseg_P(\d+)_T(\d+)$")
FORBIDDEN_PREFIXES = ("ms3seg_", "muslim_", "pedims_", "openms_", "sub-", "sibbms_")


class ForbiddenTrainingCase(ValueError):
    pass


def assert_trainable(case_id):
    """Raise unless `case_id` is an MSLesSeg TRAIN scan (mslesseg_P{1..53}_T{k})."""
    if case_id.startswith(FORBIDDEN_PREFIXES):
        raise ForbiddenTrainingCase(f"{case_id}: held-out evaluation / control data, never trainable")
    m = _TRAIN_CASE.match(case_id)
    if not m:
        raise ForbiddenTrainingCase(f"{case_id}: not an MSLesSeg train scan id (mslesseg_P<n>_T<k>)")
    if int(m.group(1)) not in TRAIN_PATIENTS:
        raise ForbiddenTrainingCase(f"{case_id}: MSLesSeg patient P{m.group(1)} is in the TEST split")
    return case_id


def patient_of(case_id):
    return re.match(r"^(mslesseg_P\d+)_T\d+$", case_id).group(1)


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def train_members(names):
    """{case_id: {"flair": member, "mask": member}} for complete MSLesSeg train scans in a zip listing."""
    out = {}
    for n in names:
        m = _TRAIN_MEMBER.search(n)
        if m:
            cid = f"mslesseg_P{int(m.group(1))}_T{int(m.group(2))}"
            out.setdefault(cid, {})["flair" if m.group(3) == "FLAIR" else "mask"] = n
    return {c: v for c, v in sorted(out.items()) if "flair" in v and "mask" in v}


def build_raw_dataset(zip_path, raw_root, case_ids=None, dataset_name=DATASET_NAME):
    """Write nnUNet_raw/<dataset>/{imagesTr,labelsTr,dataset.json}. Returns a per-case manifest."""
    import nibabel as nib
    with zipfile.ZipFile(zip_path) as zf:
        members = train_members(zf.namelist())
        ids = sorted(members) if not case_ids else list(case_ids)
        for c in ids:                                   # guard BEFORE any file is written
            assert_trainable(c)
            if c not in members:
                raise KeyError(f"{c} not found in {os.path.basename(zip_path)}")
        root = os.path.join(raw_root, dataset_name)
        if os.path.isdir(root):
            shutil.rmtree(root)
        os.makedirs(os.path.join(root, "imagesTr"))
        os.makedirs(os.path.join(root, "labelsTr"))
        manifest = {}
        for c in ids:
            img_out = os.path.join(root, "imagesTr", f"{c}_0000.nii.gz")
            with zf.open(members[c]["flair"]) as src, open(img_out, "wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 22)
            tmp_mask = os.path.join(root, f"_{c}_mask.nii.gz")
            with zf.open(members[c]["mask"]) as src, open(tmp_mask, "wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 22)
            fl, mk = nib.load(img_out), nib.load(tmp_mask)
            if fl.shape[:3] != mk.shape[:3] or not np.allclose(fl.affine, mk.affine, atol=1e-4):
                raise ValueError(f"{c}: mask grid differs from FLAIR grid")
            lab = (np.asarray(mk.dataobj, np.float32) > 0.5).astype(np.uint8)
            hdr = fl.header.copy()                       # the FLAIR's exact geometry for the label
            hdr.set_data_dtype(np.uint8)
            hdr.set_slope_inter(1, 0)
            lab_out = os.path.join(root, "labelsTr", f"{c}.nii.gz")
            nib.save(nib.Nifti1Image(lab, fl.affine, hdr), lab_out)
            manifest[c] = {"flair_member": members[c]["flair"], "mask_member": members[c]["mask"],
                           "flair_sha256": sha256_file(img_out), "mask_sha256": sha256_file(tmp_mask),
                           "shape": [int(s) for s in fl.shape[:3]],
                           "zooms": [float(z) for z in fl.header.get_zooms()[:3]],
                           "lesion_voxels": int(lab.sum())}
            os.remove(tmp_mask)
    ds = {"channel_names": {"0": "FLAIR"}, "labels": {"background": 0, "Lesion": 1},
          "numTraining": len(ids), "file_ending": ".nii.gz", "overwrite_image_reader_writer": "SimpleITKIO",
          "name": dataset_name,
          "description": "MSLesSeg TRAIN split only (P1-P53), FLAIR + binarised expert mask, for "
                         "fine-tuning FLAMeS fold 0 (MSTool-AI research, PROTOCOL docs/research/flames-thick)",
          "licence": "MSLesSeg CC BY 4.0, Figshare 10.6084/m9.figshare.27919209.v1 (Guarnera et al., Sci Data 2025)"}
    with open(os.path.join(raw_root, dataset_name, "dataset.json"), "w") as f:
        json.dump(ds, f, indent=1)
    return manifest


def patient_grouped_splits(case_ids, n_splits=N_SPLITS, seed=SPLIT_SEED):
    """nnU-Net splits_final.json content: patients permuted with RandomState(seed), np.array_split."""
    for c in case_ids:
        assert_trainable(c)
    patients = sorted({patient_of(c) for c in case_ids}, key=lambda p: int(p.split("_P")[1]))
    k = max(2, min(n_splits, len(patients)))
    if len(patients) < 2:
        raise ValueError("need at least two patients for a train/validation split")
    perm = np.random.RandomState(seed).permutation(len(patients))
    groups = [[patients[i] for i in g] for g in np.array_split(perm, k)]
    splits = []
    for g in groups:
        val_p = set(g)
        splits.append({"train": sorted(c for c in case_ids if patient_of(c) not in val_p),
                       "val": sorted(c for c in case_ids if patient_of(c) in val_p)})
    return splits


def place_flames_plans(flames_model_dir, preprocessed_root):
    """FLAMeS plans/dataset.json as the 'source dataset' Dataset004_WML for plan transfer."""
    dst = os.path.join(preprocessed_root, FLAMES_DATASET)
    os.makedirs(dst, exist_ok=True)
    shutil.copyfile(os.path.join(flames_model_dir, "plans.json"), os.path.join(dst, "nnUNetPlans.json"))
    shutil.copyfile(os.path.join(flames_model_dir, "dataset.json"), os.path.join(dst, "dataset.json"))
    return dst


def run(cmd, log=print):
    log("$ " + " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed ({r.returncode}):\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
    return r.stdout


def prepare_nnunet(flames_model_dir, case_ids, n_proc=8, log=print):
    """Fingerprint -> FLAMeS plans transferred -> preprocess 3d_fullres -> patient-grouped splits.

    Uses nnUNet_raw / nnUNet_preprocessed from the environment. Returns the split list.
    """
    pre = os.environ["nnUNet_preprocessed"]
    run(["nnUNetv2_extract_fingerprint", "-d", str(DATASET_ID), "-np", str(n_proc),
         "--verify_dataset_integrity"], log)
    place_flames_plans(flames_model_dir, pre)
    run(["nnUNetv2_move_plans_between_datasets", "-s", "4", "-t", str(DATASET_ID),
         "-sp", "nnUNetPlans", "-tp", "nnUNetPlans"], log)
    plans = json.load(open(os.path.join(pre, DATASET_NAME, "nnUNetPlans.json")))
    src = json.load(open(os.path.join(flames_model_dir, "plans.json")))
    if plans["configurations"]["3d_fullres"] != src["configurations"]["3d_fullres"] \
            or plans["transpose_forward"] != src["transpose_forward"]:
        raise RuntimeError("transferred plans differ from FLAMeS plans")
    # nnU-Net's planner normally copies dataset.json next to the plans; we skip planning on purpose
    shutil.copyfile(os.path.join(os.environ["nnUNet_raw"], DATASET_NAME, "dataset.json"),
                    os.path.join(pre, DATASET_NAME, "dataset.json"))
    run(["nnUNetv2_preprocess", "-d", str(DATASET_ID), "-plans_name", "nnUNetPlans", "-c", "3d_fullres",
         "-np", str(n_proc)], log)
    splits = patient_grouped_splits(case_ids)
    with open(os.path.join(pre, DATASET_NAME, "splits_final.json"), "w") as f:
        json.dump(splits, f, indent=1)
    return splits
