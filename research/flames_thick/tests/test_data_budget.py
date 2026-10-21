"""Training-data guard, raw dataset assembly, patient-grouped split, cost guard (no torch needed)."""
import json
import os
import sys
import zipfile

import nibabel as nib
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from flames_thick import budget, data_prep as dp  # noqa: E402

LAS = np.diag([-1.0, 1.0, 1.0, 1.0])
LAS[:3, 3] = [90, -126, -72]


# ------------------------------------------------------------------ guard
@pytest.mark.parametrize("cid", ["mslesseg_P1_T1", "mslesseg_P53_T4", "mslesseg_P12_T3"])
def test_train_ids_are_trainable(cid):
    assert dp.assert_trainable(cid) == cid


@pytest.mark.parametrize("cid", [
    "mslesseg_P54", "mslesseg_P75", "mslesseg_P54_T1", "mslesseg_P60_T1",          # MSLesSeg test split
    "openms_patient16", "openms_patient30", "openms_patient01",                     # every Ljubljana scan
    "ms3seg_001", "muslim_01", "pedims_P1_T1", "sub-001", "sibbms_sub-001",         # held-out sites / controls
    "mslesseg_P0_T1", "P1_T1", "mslesseg_P1", "", "mslesseg_P1_T1_x"])
def test_heldout_and_malformed_ids_are_rejected(cid):
    with pytest.raises(dp.ForbiddenTrainingCase):
        dp.assert_trainable(cid)


def test_clean_ljubljana_patients_explicitly_forbidden():
    for n in (16, 17, 18, 19, 20, 26, 27, 28, 29, 30):
        with pytest.raises(dp.ForbiddenTrainingCase):
            dp.assert_trainable(f"openms_patient{n:02d}")


# ------------------------------------------------------------------ zip -> nnU-Net raw
def _nii_bytes(tmp_path, name, data, affine=LAS, dtype=np.float32):
    p = tmp_path / name
    img = nib.Nifti1Image(np.asarray(data, dtype), affine)
    img.set_data_dtype(dtype)
    nib.save(img, str(p))
    return p.read_bytes()


def make_mslesseg_zip(tmp_path):
    rng = np.random.default_rng(0)
    z = tmp_path / "MSLesSeg Dataset.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for p, tps in ((1, (1, 2)), (2, (1,)), (3, (1,)), (53, (1,))):
            for t in tps:
                fl = rng.random((12, 14, 10)) * 100 + 1
                mk = np.zeros((12, 14, 10))
                mk[4:7, 5:8, 3:5] = 1.0
                zf.writestr(f"MSLesSeg Dataset/train/P{p}/T{t}/P{p}_T{t}_FLAIR.nii.gz", _nii_bytes(tmp_path, "f.nii.gz", fl))
                zf.writestr(f"MSLesSeg Dataset/train/P{p}/T{t}/P{p}_T{t}_MASK.nii.gz", _nii_bytes(tmp_path, "m.nii.gz", mk))
                zf.writestr(f"MSLesSeg Dataset/train/P{p}/T{t}/P{p}_T{t}_T1.nii.gz", b"not used")
        zf.writestr("MSLesSeg Dataset/train/P9/T1/P9_T1_FLAIR.nii.gz", b"incomplete: no mask")
        for p in (54, 60):                                       # test split (different layout)
            zf.writestr(f"MSLesSeg Dataset/test/P{p}/P{p}_FLAIR.nii.gz", _nii_bytes(tmp_path, "f.nii.gz", np.ones((12, 14, 10))))
            zf.writestr(f"MSLesSeg Dataset/test/P{p}/P{p}_MASK.nii.gz", _nii_bytes(tmp_path, "m.nii.gz", np.zeros((12, 14, 10))))
    return str(z)


def test_train_members_only_complete_train_scans(tmp_path):
    z = make_mslesseg_zip(tmp_path)
    m = dp.train_members(zipfile.ZipFile(z).namelist())
    assert sorted(m) == ["mslesseg_P1_T1", "mslesseg_P1_T2", "mslesseg_P2_T1", "mslesseg_P3_T1", "mslesseg_P53_T1"]
    assert all("/train/" in v["flair"] and "/train/" in v["mask"] for v in m.values())


def test_build_raw_dataset_writes_only_train_with_binary_labels_on_flair_grid(tmp_path):
    z = make_mslesseg_zip(tmp_path)
    raw = tmp_path / "raw"
    man = dp.build_raw_dataset(z, str(raw))
    root = raw / dp.DATASET_NAME
    imgs = sorted(os.listdir(root / "imagesTr"))
    labs = sorted(os.listdir(root / "labelsTr"))
    assert imgs == [f"{c}_0000.nii.gz" for c in sorted(man)] and labs == [f"{c}.nii.gz" for c in sorted(man)]
    assert not any("P54" in f or "P60" in f for f in imgs + labs)
    for c in man:
        fl = nib.load(str(root / "imagesTr" / f"{c}_0000.nii.gz"))
        lb = nib.load(str(root / "labelsTr" / f"{c}.nii.gz"))
        assert lb.get_data_dtype() == np.uint8 and set(np.unique(np.asarray(lb.dataobj))) <= {0, 1}
        assert lb.shape == fl.shape and np.allclose(lb.affine, fl.affine)
        assert np.allclose(lb.header.get_qform(), fl.header.get_qform())
        assert man[c]["lesion_voxels"] == 18
    ds = json.load(open(root / "dataset.json"))
    assert ds["numTraining"] == 5 and ds["channel_names"] == {"0": "FLAIR"} and ds["labels"]["Lesion"] == 1


def test_build_raw_dataset_refuses_a_test_case_before_writing(tmp_path):
    z = make_mslesseg_zip(tmp_path)
    with pytest.raises(dp.ForbiddenTrainingCase):
        dp.build_raw_dataset(z, str(tmp_path / "raw"), ["mslesseg_P1_T1", "mslesseg_P54"])
    assert not (tmp_path / "raw").exists()


def test_patient_grouped_split_has_no_patient_in_both_sides():
    ids = [f"mslesseg_P{p}_T{t}" for p in range(1, 54) for t in (1, 2) if p % 3 or t == 1]
    splits = dp.patient_grouped_splits(ids)
    assert len(splits) == 5
    allval = []
    for s in splits:
        tp = {dp.patient_of(c) for c in s["train"]}
        vp = {dp.patient_of(c) for c in s["val"]}
        assert not tp & vp and sorted(s["train"] + s["val"]) == sorted(ids)
        allval += s["val"]
    assert sorted(allval) == sorted(ids)                         # every scan validated exactly once
    assert 10 <= len({dp.patient_of(c) for c in splits[0]["val"]}) <= 11
    assert dp.patient_grouped_splits(ids) == splits             # deterministic


def test_two_patient_pilot_split():
    s = dp.patient_grouped_splits(["mslesseg_P1_T1", "mslesseg_P2_T1"])
    assert len(s) == 2 and len(s[0]["train"]) == 1 and len(s[0]["val"]) == 1


# ------------------------------------------------------------------ cost guard
def att(start, hb=None, end=None, live=False):
    return {"start_utc": start, "heartbeat_utc": hb, "end_utc": end, "live": live}


def test_billed_seconds_sum_over_attempts_with_overhead():
    now = budget.parse("2026-11-01T12:00:00Z")
    a = [att("2026-11-01T08:00:00Z", hb="2026-11-01T09:00:00Z"),            # preempted: last heartbeat
         att("2026-11-01T09:30:00Z", end="2026-11-01T10:00:00Z"),           # ended
         att("2026-11-01T11:00:00Z", live=True)]                            # this one
    assert budget.billed_seconds(a, now, overhead_s=300) == 3600 + 1800 + 3600 + 3 * 300
    assert budget.billed_seconds([att("2026-11-01T11:00:00Z")], now, 0) == 0     # dead before 1st beat


def test_decide_stops_before_exceeding_cost_or_hours():
    now = budget.parse("2026-11-01T12:00:00Z")
    a = [att("2026-11-01T00:00:00Z", live=True)]                              # 12 h so far
    # 12 h * 0.43 * 1.15 = 5.93 USD; one more 250-s epoch + 10-min reserve stays under 8 USD
    assert budget.decide(a, now, 0.43, 8.0, 36, 250) is None
    assert budget.decide(a, now, 0.43, 6.0, 36, 250).startswith("max_cost")
    assert budget.decide(a, now, 0.43, 100.0, 12.1, 250).startswith("max_hours")
    s = budget.summary(a, now, 0.43)
    assert s["cost_usd_guard_estimate"] > s["cost_usd_list_estimate"] > 0
