"""strip_file on small synthetic images, with the SynthStrip run replaced by a stub that writes the mask (review M10, m2, m3)."""
import subprocess
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

import server


def stub(mask_value):
    def run(cmd, **kwargs):
        source, mask_path = Path(cmd[cmd.index("-i") + 1]), Path(cmd[cmd.index("-m") + 1])
        img = nib.load(source)
        shape = img.shape[:3]
        mask = np.zeros(shape, np.uint8)
        if mask_value:
            mask[2:-2, 2:-2, 1:-1] = 1
        nib.save(nib.Nifti1Image(mask, img.affine), mask_path)
        return subprocess.CompletedProcess(cmd, 0)
    return run


def write(tmp_path, data, affine=None):
    path = tmp_path / "flair.nii.gz"
    nib.save(nib.Nifti1Image(data, affine if affine is not None else np.diag([0.9, 0.9, 5.5, 1])), path)
    return path


def test_same_grid_and_exact_zero_outside(tmp_path, monkeypatch):
    monkeypatch.setattr(server.subprocess, "run", stub(True))
    data = np.full((12, 10, 6), 7.0, np.float32)
    data[0, 0, 0] = np.nan
    out = nib.load(server.strip_file(write(tmp_path, data), tmp_path))
    brain = out.get_fdata()
    assert out.shape == (12, 10, 6) and np.allclose(out.affine, np.diag([0.9, 0.9, 5.5, 1]))
    assert not np.isnan(brain).any() and brain[0, 0, 0] == 0 and brain[5, 5, 3] == 7


def test_a_3d_image_stored_as_one_volume_is_kept_3d(tmp_path, monkeypatch):
    monkeypatch.setattr(server.subprocess, "run", stub(True))
    out = nib.load(server.strip_file(write(tmp_path, np.ones((8, 8, 8, 1), np.float32)), tmp_path))
    assert out.shape == (8, 8, 8)


def test_an_empty_mask_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(server.subprocess, "run", stub(False))
    with pytest.raises(ValueError):
        server.strip_file(write(tmp_path, np.ones((8, 8, 8), np.float32)), tmp_path)


def test_a_real_4d_series_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(server.subprocess, "run", stub(True))
    with pytest.raises(ValueError):
        server.strip_file(write(tmp_path, np.ones((8, 8, 8, 3), np.float32)), tmp_path)
