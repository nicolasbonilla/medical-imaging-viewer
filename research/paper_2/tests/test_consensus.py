"""Tests of the D5 consensus (PREREG §3), on synthetic masks."""
import numpy as np
import pytest

from research.paper_2.consensus import split


def blob(shape, at, size=3):
    m = np.zeros(shape, dtype=np.uint8)
    z, y, x = at
    m[z:z + size, y:y + size, x:x + size] = 1
    return m


S = (30, 30, 30)


def test_overlap_of_one_voxel_is_enough():
    a = blob(S, (2, 2, 2)) | blob(S, (20, 20, 20))
    b = np.zeros(S, dtype=np.uint8)
    b[4, 4, 4] = 1                                   # touches the first blob only, by one voxel
    ag, single, na, ns = split(a, [b])
    assert (na, ns) == (1, 1)
    assert ag[3, 3, 3] and not ag[21, 21, 21] and single[21, 21, 21]


def test_whole_component_is_kept_not_just_the_overlap():
    a = blob(S, (2, 2, 2), size=5)
    b = np.zeros(S, dtype=np.uint8)
    b[2, 2, 2] = 1
    ag, _, na, _ = split(a, [b])
    assert na == 1 and ag.sum() == a.sum()


def test_18_connectivity_joins_edge_neighbours_not_corner_ones():
    a = np.zeros(S, dtype=np.uint8)
    a[5, 5, 5] = a[5, 6, 6] = 1                      # edge neighbours: one component under 18-connectivity
    a[10, 10, 10] = a[11, 11, 11] = 1                # corner neighbours only: two components
    b = np.zeros(S, dtype=np.uint8)
    b[5, 5, 5] = b[10, 10, 10] = 1
    _, _, na, ns = split(a, [b])
    assert (na, ns) == (2, 1)


def test_k3_needs_two_partners():
    a = blob(S, (2, 2, 2))
    b = blob(S, (2, 2, 2))
    c = np.zeros(S, dtype=np.uint8)
    assert split(a, [b, c], k=3)[2] == 0
    assert split(a, [b, b], k=3)[2] == 1
    with pytest.raises(ValueError):
        split(a, [b], k=3)


def test_grid_mismatch_and_empty():
    with pytest.raises(ValueError):
        split(np.zeros(S), [np.zeros((10, 10, 10))])
    ag, single, na, ns = split(np.zeros(S), [np.zeros(S)])
    assert (na, ns) == (0, 0) and not ag.any() and not single.any()


def test_partner_lesions_alone_are_never_added():
    a = np.zeros(S, dtype=np.uint8)
    b = blob(S, (10, 10, 10))
    ag, single, na, ns = split(a, [b])
    assert not ag.any() and (na, ns) == (0, 0)
