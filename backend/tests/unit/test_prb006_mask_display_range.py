"""PRB-006 — a stored lesion mask must not carry the MRI's display range.

`_save_masks_to_gcs` writes the mask NIfTI with a copy of the source MRI's header (for an exact
spatial match in other viewers). That copy kept the MRI's `cal_min`/`cal_max` — its display window,
e.g. -15.5 / 189.2. A viewer that honours the header (niivue in this app's 3D and GPU views,
MRIcroGL, FSLeyes) then maps the mask's 0 (background) to a visible colour and its labels (1, 2, …)
to the bottom of the colour scale: the whole volume tinted, the lesions nearly invisible.

Required: the stored header's display range is the mask's own — 0 (background, transparent) to its
highest label (at least 1) — while the spatial header (affine, voxel sizes), the RC-031 voxel-order
marker and the verbatim labels (P-4.1) are unchanged.

Drives the REAL `_save_masks_to_gcs` through a fake bucket (no cloud access; PRB-002).
"""
import os
import tempfile
from types import SimpleNamespace

import nibabel as nib
import numpy as np
import pytest

from app.services.segmentation_service import SegmentationService

ORIGINAL = "patients/p/studies/s/series/se/flair.nii.gz"
NATIVE = (5, 6, 4)  # MRI-native (a0, a1, k)
AFFINE = np.array([[-1.0, 0, 0, 90], [0, 1.2, 0, -126], [0, 0, 3.0, -72], [0, 0, 0, 1]])


def _mri_bytes(cal_min, cal_max):
    img = nib.Nifti1Image(np.zeros(NATIVE, dtype=np.int16), AFFINE)
    img.header["cal_min"] = cal_min
    img.header["cal_max"] = cal_max
    with tempfile.NamedTemporaryFile(suffix=".nii.gz", delete=False) as t:
        p = t.name
    nib.save(img, p)
    with open(p, "rb") as f:
        data = f.read()
    os.unlink(p)
    return data


class _Blob:
    def __init__(self, bucket, name):
        self.bucket, self.name, self.generation = bucket, name, None

    def exists(self):
        return self.name == ORIGINAL and self.bucket.original is not None

    def download_to_file(self, buf):
        buf.write(self.bucket.original)

    def upload_from_file(self, buf, content_type=None, if_generation_match=None, **kwargs):
        self.bucket.uploaded[self.name] = buf.read()
        self.generation = 1

    def reload(self):
        pass


class _Bucket:
    def __init__(self, original):
        self.original, self.uploaded = original, {}

    def blob(self, name):
        return _Blob(self, name)


def _stored_header(tmp_path, internal, cal_min=-15.5, cal_max=189.2, original_present=True):
    svc = SegmentationService(storage_path=str(tmp_path), cache_service=None)
    svc._gcs_bucket = _Bucket(_mri_bytes(cal_min, cal_max) if original_present else None)
    sid = "seg-prb006"
    svc.segmentations_cache[sid] = {"metadata": SimpleNamespace(file_id=ORIGINAL)}
    svc._save_masks_to_gcs(sid, internal)
    raw = svc._gcs_bucket.uploaded[f"segmentations/{sid}/masks.nii.gz"]
    with tempfile.NamedTemporaryFile(suffix=".nii.gz", delete=False) as t:
        p = t.name
    with open(p, "wb") as f:
        f.write(raw)
    img = nib.load(p)
    hdr, data, affine = img.header.copy(), np.asarray(img.dataobj).copy(), img.affine.copy()
    del img
    os.unlink(p)
    return hdr, data, affine


def _internal(*labels):
    m = np.zeros((NATIVE[2], NATIVE[0], NATIVE[1]), dtype=np.uint8)  # internal (k, a0, a1)
    for n, label in enumerate(labels):
        m[n % NATIVE[2], 1 + n % 3, 2] = label
    return m


@pytest.mark.parametrize("cal_min,cal_max", [(-15.5, 189.2), (100.0, 900.0), (0.0, 255.0)])
def test_rc074_stored_binary_mask_display_range_is_zero_to_one(tmp_path, cal_min, cal_max):
    hdr, data, _ = _stored_header(tmp_path, _internal(1, 1), cal_min, cal_max)
    assert float(hdr["cal_min"]) == 0.0
    assert float(hdr["cal_max"]) == 1.0
    assert set(np.unique(data).tolist()) == {0, 1}


def test_rc074_stored_label_mask_display_range_is_zero_to_its_highest_label(tmp_path):
    hdr, data, _ = _stored_header(tmp_path, _internal(1, 4, 6))
    assert float(hdr["cal_min"]) == 0.0
    assert float(hdr["cal_max"]) == 6.0
    assert set(np.unique(data).tolist()) == {0, 1, 4, 6}


def test_rc074_empty_mask_display_range_is_zero_to_one(tmp_path):
    hdr, _, _ = _stored_header(tmp_path, _internal())
    assert (float(hdr["cal_min"]), float(hdr["cal_max"])) == (0.0, 1.0)


def test_rc074_mask_stored_without_the_mri_header_has_its_own_display_range(tmp_path):
    """The fallback path (source MRI not readable): a generic header, same display-range rule."""
    hdr, data, _ = _stored_header(tmp_path, _internal(1, 3), original_present=False)
    assert (float(hdr["cal_min"]), float(hdr["cal_max"])) == (0.0, 3.0)
    assert b"RC031-ORIENT-V2" in bytes(np.asarray(hdr["descrip"]).tobytes())


def test_rc074_spatial_header_and_rc031_marker_are_still_the_mri_s(tmp_path):
    """Guard: the fix touches the display range only (passes on the base too)."""
    hdr, data, affine = _stored_header(tmp_path, _internal(1))
    assert np.allclose(affine, AFFINE, atol=1e-4)
    assert data.shape == NATIVE
    assert b"RC031-ORIENT-V2" in bytes(np.asarray(hdr["descrip"]).tobytes())
    assert np.allclose(hdr.get_zooms()[:3], (1.0, 1.2, 3.0), atol=1e-5)
