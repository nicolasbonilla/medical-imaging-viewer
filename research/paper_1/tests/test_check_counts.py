"""Paper 1 gate G2: the independent breadth-first recount agrees with scipy's 18-connected labelling.

    python -m pytest research/paper_1/tests -q
"""
import os
import sys

import numpy as np
from scipy import ndimage as ndi

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import check_counts as C  # noqa: E402


def test_bfs_matches_scipy_18_connectivity():
    rng = np.random.default_rng(11)
    for _ in range(5):
        fg = rng.random((14, 12, 10)) > 0.8
        lab, n = ndi.label(fg, structure=ndi.generate_binary_structure(3, 2))
        sizes = sorted(np.bincount(lab.ravel())[1:].tolist())
        assert sorted(C.bfs_components(fg)) == sizes


def test_volume_floor():
    fg = np.zeros((5, 5, 5), bool)
    fg[0, 0, 0] = fg[0, 0, 1] = True             # 2 voxels
    fg[3, 3, 3] = fg[3, 4, 4] = fg[4, 4, 4] = True   # edge + face chain: 3 voxels
    assert C.count(fg, 1.0) == (1, 3.0)
    assert C.count(fg, 1.5) == (2, 7.5)
