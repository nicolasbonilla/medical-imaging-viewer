"""MNI-compatibility guard for MAGNIMS region stratification (adversarial Finding F1).

The MSMask atlas is MNI152; applying it to native/oblique clinical data would mint
CONFIDENTLY WRONG per-region (PV/JC/IT/DWM) counts. _looks_mni fails such inputs
closed so region stratification is only computed on plausibly-MNI data.
"""
import math

import numpy as np

from app.api.routes.segmentation_analysis import _looks_mni


def test_accepts_mni152_1mm():
    aff = np.array([[-1, 0, 0, 90], [0, 1, 0, -126], [0, 0, 1, -72], [0, 0, 0, 1]], float)
    assert _looks_mni(aff, (182, 218, 182)) is True


def test_accepts_mni152_2mm():
    # 2 mm MNI (91x109x91) — same ~181x217x181 mm FOV, axis-aligned.
    aff = np.array([[-2, 0, 0, 90], [0, 2, 0, -126], [0, 0, 2, -72], [0, 0, 0, 1]], float)
    assert _looks_mni(aff, (91, 109, 91)) is True


def test_rejects_oblique_native_scan():
    # a 10-degree in-plane tilt (native acquisition) must be rejected.
    c, s = math.cos(math.radians(10)), math.sin(math.radians(10))
    aff = np.array([[c, -s, 0, 90], [s, c, 0, -126], [0, 0, 1, -72], [0, 0, 0, 1]], float)
    assert _looks_mni(aff, (182, 218, 182)) is False


def test_rejects_wrong_fov():
    # 1 mm iso but a small (64 mm) FOV — not the MNI brain box.
    assert _looks_mni(np.eye(4), (64, 64, 64)) is False


def test_rejects_degenerate_affine():
    assert _looks_mni(np.zeros((4, 4)), (182, 218, 182)) is False
