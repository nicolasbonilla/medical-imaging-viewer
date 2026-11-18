"""Paper 1 addendum 2: the clinically faithful rule (faithful_rule.py) and the frozen addendum-2 sets, on tiny
synthetic arrays. No cloud call, no image data.

    python -m pytest research/paper_1/tests/test_faithful_rule.py -q
"""
import json
import os
import sys
from collections import Counter

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "mimics"))
import faithful_rule as FR  # noqa: E402
import freeze_addendum2_sets as F2  # noqa: E402

ISO = np.eye(4)
THICK = np.diag([0.5, 0.5, 3.0, 1.0])


def test_feret_centres_and_corners():
    one = np.array([[5, 5, 5]])
    assert not FR.long_axis_at_least(one, ISO)                       # a single voxel: F = 0
    assert not FR.long_axis_at_least(one, ISO, corners=True)         # corners: sqrt(3) mm
    three = np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0]])
    four = np.vstack([three, [[3, 0, 0]]])
    assert not FR.long_axis_at_least(three, ISO)                     # centres 2 mm apart
    assert FR.long_axis_at_least(three, ISO, corners=True)           # 3 mm extent
    assert FR.long_axis_at_least(four, ISO)                          # centres 3 mm apart
    diag = np.array([[0, 0, 0], [1, 1, 1], [2, 2, 2]])               # 2 * sqrt(3) = 3.46 mm, extents 2 mm
    assert FR.long_axis_at_least(diag, ISO)
    assert FR.long_axis_at_least(np.array([[0, 0, 0], [0, 0, 1]]), THICK)      # two thick slices: 3 mm
    assert FR.long_axis_at_least(np.array([[0, 0, 0]]), THICK, corners=True)   # one 3-mm voxel, corner extent 3
    assert not FR.long_axis_at_least(np.array([[0, 0, 0], [1, 1, 0]]), THICK)  # in-plane 0.71 mm


def test_labels_on_grid_nearest_neighbour():
    lab = np.zeros((10, 10, 10), np.int16)
    lab[2:4, 2:4, 2:4] = 4
    out = FR.labels_on_grid(lab, ISO, (10, 10, 10), ISO)
    assert np.array_equal(out, lab)
    coarse = np.diag([2.0, 2.0, 2.0, 1.0])                           # a 2-mm grid over the same world space
    out2 = FR.labels_on_grid(lab, ISO, (5, 5, 5), coarse)
    assert out2[1, 1, 1] == 4 and out2[0, 0, 0] == 0


def _anat():
    a = np.zeros((30, 30, 30), np.int16)
    a[10:14, 10:14, 10:14] = 4              # a "ventricle"
    a[:, :, 25:] = 3                         # "cortex" (top)
    a[:, :, :3] = 16                         # "brainstem" (bottom)
    return a


def test_regions_and_rule():
    anat = _anat()
    m = np.zeros_like(anat, bool)
    m[14:18, 11, 11] = True                  # touches the ventricle face, 3 mm long -> PV
    m[5:9, 5, 23] = True                     # 1 voxel below cortex (z 24 neighbour of 25? no: 23 -> 24 gap)
    m[20:24, 20, 24] = True                  # touches cortex at z = 25 -> JC
    m[20:24, 5, 1] = True                    # inside the brainstem -> IT
    les = FR.classify_lesions(m, ISO, anat)
    regs = Counter(x["region"] for x in les if x["axis_ok"])
    assert regs == {"PV": 1, "JC": 1, "IT": 1, "other": 1}
    met, cnt = FR.rule(les)
    assert met and cnt["PV"] == 1
    assert FR.rule(les, pv_min=3)[0]          # PV no longer counts (1 < 3), but JC + IT still give 2 regions
    m[20:24, 5, 1] = False
    assert not FR.rule(FR.classify_lesions(m, ISO, anat), pv_min=3)[0]   # without IT: JC alone
    small = np.zeros_like(m)
    small[14:16, 11, 11] = True              # PV but only 1 mm between centres
    small[20:22, 20, 24] = True              # JC, 1 mm
    r = FR.evaluate_mask(small, ISO, anat)
    assert r["n_components"] == 2 and r["n_lesions"] == 0 and not r["rule"]
    assert r["n_lesions_corner"] == 0                                # 2-mm corner extent < 3 mm
    assert r["rule_corner"] is False


def test_priority_it_over_pv():
    anat = _anat()
    anat[10:14, 10:14, 3:6] = 16             # brainstem next to a ventricle-labelled voxel
    anat[10, 10, 6] = 4
    m = np.zeros_like(anat, bool)
    m[10:14, 10, 3:6] = True
    les = FR.classify_lesions(m, ISO, anat)
    assert [x["region"] for x in les] == ["IT"]


def test_addendum2_sample_is_reproducible():
    sets = json.load(open(os.path.join(HERE, "..", "mimics", "analysis_sets.json")))
    frozen = json.load(open(os.path.join(HERE, "..", "mimics", "analysis_sets_addendum2.json")))
    ids, rank = F2.young_sample(sets["B_dlbs"])
    assert ids == frozen["B2_sample"]["ids"]
    assert Counter(rank[i]["decade"] for i in ids) == {20: 25, 30: 25, 40: 25}
    assert all(sets["B_dlbs"][i]["set"] == "B2" and 21 <= sets["B_dlbs"][i]["age_mri_w1"] <= 49 for i in ids)
    assert not set(ids) & set(sets["B1_sample"]["ids"])
    assert set(frozen["pilot"]["B2_tools"]) <= set(ids)
