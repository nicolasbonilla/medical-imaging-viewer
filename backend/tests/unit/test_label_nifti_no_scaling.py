"""Audit P-4.1: a persisted label mask must store class IDs VERBATIM, never
intensity-scaled — even when the source MRI header carries a non-unit scl_slope.

_save_masks_to_gcs reuses the original MRI's header for perfect spatial
alignment. That header can carry scl_slope != 1. Label masks are categorical, so
any scaling on write/read would corrupt them. set_data_dtype(uint8) already makes
nibabel recompute scaling for the integer output, and the service now ALSO resets
slope/inter explicitly. This test drives the REAL _save_masks_to_gcs through a
fake GCS bucket and asserts the round-tripped labels are intact and the persisted
header applies no scaling.
"""
import io
import tempfile
import os
from types import SimpleNamespace

import numpy as np
import nibabel as nib
import pytest

from app.services.segmentation_service import SegmentationService

ORIGINAL_NAME = "patients/p/img.nii.gz"


def _source_mri_bytes(shape, slope, inter):
    """A source MRI NIfTI whose header carries a non-unit intensity scale."""
    img = nib.Nifti1Image(np.zeros(shape, dtype=np.int16), np.diag([0.9, 0.9, 3.0, 1.0]))
    img.header.set_slope_inter(slope, inter)
    with tempfile.NamedTemporaryFile(suffix=".nii.gz", delete=False) as t:
        p = t.name
    nib.save(img, p)
    with open(p, "rb") as f:
        data = f.read()
    os.unlink(p)
    return data


class _FakeBlob:
    def __init__(self, bucket, name):
        self.bucket, self.name = bucket, name
        self.generation = None

    def exists(self):
        return self.name == self.bucket.original_name

    def download_to_file(self, buf):
        buf.write(self.bucket.original_bytes)

    # Accept the A-2 if_generation_match kwarg (and any future upload kwargs);
    # this fake does not enforce preconditions, so writes always succeed.
    def upload_from_file(self, buf, content_type=None, if_generation_match=None, **kwargs):
        self.bucket.uploaded[self.name] = buf.read()
        self.generation = 1

    def reload(self):
        pass


class _FakeBucket:
    def __init__(self, original_name, original_bytes):
        self.original_name = original_name
        self.original_bytes = original_bytes
        self.uploaded = {}

    def blob(self, name):
        return _FakeBlob(self, name)


def _service_with_source(tmp_path, source_bytes, native_shape, file_id=ORIGINAL_NAME):
    svc = SegmentationService(storage_path=str(tmp_path), cache_service=None)
    svc._gcs_bucket = _FakeBucket(file_id, source_bytes)  # bypass lazy GCS client
    return svc


@pytest.mark.parametrize("slope,inter", [(2.0, 0.0), (0.5, 3.0), (10.0, 0.0)])
def test_labels_verbatim_despite_inherited_slope(tmp_path, slope, inter):
    # internal (k,a0,a1); native (a0,a1,k) is what lands on disk.
    internal = np.zeros((4, 5, 6), dtype=np.uint8)
    internal[0] = 1
    internal[1] = 2
    internal[2] = 200          # a large label — adversarial for scaling/truncation
    native_shape = (5, 6, 4)
    src = _source_mri_bytes(native_shape, slope, inter)

    svc = _service_with_source(tmp_path, src, native_shape)
    sid = "seg-labels-1"
    svc.segmentations_cache[sid] = {"metadata": SimpleNamespace(file_id=ORIGINAL_NAME)}

    svc._save_masks_to_gcs(sid, internal)

    out_bytes = svc._gcs_bucket.uploaded[f"segmentations/{sid}/masks.nii.gz"]
    with tempfile.NamedTemporaryFile(suffix=".nii.gz", delete=False) as t:
        p = t.name
    with open(p, "wb") as f:
        f.write(out_bytes)
    loaded = nib.load(p)
    fdata = np.rint(loaded.get_fdata()).astype(int)
    out_slope, out_inter = loaded.header.get_slope_inter()
    os.unlink(p)

    # Labels preserved exactly.
    assert set(fdata.flatten().tolist()) == {0, 1, 2, 200}
    # Persisted header applies no scaling (1/0, or None which nibabel reads as 1).
    assert (out_slope in (None, 1.0)) and (out_inter in (None, 0.0))
