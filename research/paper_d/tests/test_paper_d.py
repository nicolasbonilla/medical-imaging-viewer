"""Tests for the paper-D research code (not the device). Run with the backend venv from the repo root:

    backend/venv/Scripts/python.exe -m pytest research/paper_d/tests -q

They prove that (1) the vectorised grid code reproduces the device's own Class C functions exactly
(zone map, region counts, DIS) and (2) the LST-AI rule is a faithful port of annotate.py, and they
pin the anatomical facts about the MSMask atlas that paper D reports (third ventricle inside label 4,
fourth ventricle inside label 5, thalamus labelled WM). No outcome on real patients is computed here.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest
from scipy import ndimage as ndi

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "backend"))
logging.disable(logging.CRITICAL)

from research.paper_d import atlas as A  # noqa: E402
from research.paper_d import rules as RL  # noqa: E402
from research.paper_d.common import DEVICE_MSMASK, MSMASK_SHA256, sha256  # noqa: E402
from research.paper_d import run_grid as RG  # noqa: E402

FSL_SHAPE = (182, 218, 182)
FSL_AFFINE = np.array([[-1.0, 0, 0, 90], [0, 1, 0, -126], [0, 0, 1, -72], [0, 0, 0, 1]])


@pytest.fixture(scope="module")
def atlas():
    labels, aff = A.load_labels(DEVICE_MSMASK)
    split, info = A.split_third_ventricle(labels, aff)
    return labels, aff, split, info


@pytest.fixture(scope="module")
def g0_maps():
    return RG.atlas_maps(None, FSL_SHAPE, FSL_AFFINE, Path("."), levels=("G0",))


def world_to_vox(xyz, aff=FSL_AFFINE):
    return tuple(np.round(np.linalg.inv(aff) @ np.r_[xyz, 1]).astype(int)[:3])


def test_atlas_is_the_lstai_release_file():
    assert sha256(DEVICE_MSMASK) == MSMASK_SHA256


def test_third_ventricle_is_inside_label4_and_fourth_inside_label5(atlas):
    labels, aff, split, info = atlas
    assert np.array_equal((split == A.VENT) | (split == A.THIRD_VENT), labels == A.VENT)
    third = np.argwhere(split == A.THIRD_VENT)
    xyz = (aff[:3, :3] @ third.T).T + aff[:3, 3]
    assert np.abs(xyz[:, 0]).max() <= 12              # a midline structure
    assert 1000 < info["third_ventricle_voxels"] < 5000  # 1-5 mL on the template
    # fourth ventricle (midline, y -40..-50, z -25..-35) carries label 5, not 4 or 1
    for y in (-42, -46):
        for z in (-28, -32):
            assert labels[world_to_vox((0, y, z), aff)] == A.INFRA
    # thalamus (x +-10, y -18, z +6) is labelled WM (3) in MSMask
    assert labels[world_to_vox((10, -18, 6), aff)] == A.WM
    assert labels[world_to_vox((-10, -18, 6), aff)] == A.WM


def test_zone_map_mirror_equals_device(g0_maps):
    from app.services.ms_region_classifier import generate_zone_map_atlas
    img = nib.Nifti1Image(np.zeros(FSL_SHAPE, np.uint8), FSL_AFFINE)
    dev = generate_zone_map_atlas(img, (1.0, 1.0, 1.0))["zone_mask"]
    assert np.array_equal(dev, g0_maps["G0"]["zone"]["APP"])


def _random_lesions(seed, n=40):
    """Blobs in the brain (MSMask label > 0), some touching ventricles / cortex / posterior fossa."""
    rng = np.random.default_rng(seed)
    labels, aff = A.load_labels(DEVICE_MSMASK)
    lab_fsl = A.resample_nearest(labels, aff, FSL_SHAPE, FSL_AFFINE)
    cand = np.argwhere(lab_fsl > 1)
    mask = np.zeros(FSL_SHAPE, bool)
    for c in cand[rng.choice(len(cand), n, replace=False)]:
        r = rng.integers(0, 3, size=3)
        sl = tuple(slice(max(ci - ri, 0), ci + ri + 1) for ci, ri in zip(c, r))
        mask[sl] = True
    # a few 1-2 voxel specks (below the 3 mm^3 floor)
    for c in cand[rng.choice(len(cand), 8, replace=False)]:
        mask[tuple(c)] = True
    return mask


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_grid_counts_and_dis_equal_device(seed, g0_maps):
    from app.services.ms_region_classifier import generate_zone_map_atlas
    mask = _random_lesions(seed)
    img = nib.Nifti1Image(mask.astype(np.uint8), FSL_AFFINE)
    zdev = np.transpose(generate_zone_map_atlas(img, (1.0, 1.0, 1.0))["zone_mask"], (2, 0, 1))
    dev_counts, dev_dis = RG.device_check(img, mask, zdev)
    rows, _ = RG.evaluate_mask(mask, None, g0_maps, keep_lesions=False)
    mine = [r for r in rows if r[0] == "G0" and r[1] == "APP" and r[2] == "v3"][0]
    assert list(mine[3:7]) == dev_counts
    assert mine[9] == dev_dis


def _annotate_py_port(seg, msmask):
    """Literal port of LST-AI v1.2.0 annotate.py (lesion loop), returning LST-AI output codes
    (1 PV, 2 JC, 3 subcortical, 4 IT)."""
    from skimage.measure import label
    from skimage.morphology import binary_dilation
    seg = seg.astype(float).copy()
    seg[seg > 0] = 1
    seg_label = label(seg, connectivity=3)
    for lesion_ctr in range(1, seg_label.max() + 1):
        temp_mask = np.zeros(seg.shape)
        temp_mask[seg_label == lesion_ctr] = 1
        temp_mask_dil = binary_dilation(temp_mask, footprint=np.ones((3, 3, 3))).astype(np.uint8)
        if 4 in msmask[temp_mask_dil == 1]:
            seg[temp_mask == 1] = 1
        elif 2 in msmask[temp_mask_dil == 1]:
            seg[temp_mask == 1] = 2
        elif 5 in msmask[temp_mask_dil == 1]:
            seg[temp_mask == 1] = 4
        else:
            seg[temp_mask == 1] = 3
    return seg.astype(np.uint8), seg_label


@pytest.mark.parametrize("seed", [11, 12])
def test_lstai_rule_equals_annotate_py(seed):
    pytest.importorskip("skimage")
    rng = np.random.default_rng(seed)
    labels, aff = A.load_labels(DEVICE_MSMASK)
    # a 60^3 crop around the third ventricle / thalami / midbrain, where every label meets
    c = world_to_vox((0, -20, 0), aff)
    crop = labels[c[0] - 30:c[0] + 30, c[1] - 30:c[1] + 30, c[2] - 30:c[2] + 30].astype(np.int16)
    seg = ndi.binary_dilation(rng.random(crop.shape) < 0.002, iterations=1)
    expected, seg_label = _annotate_py_port(seg, crop)
    lab26, n26 = RL.label(seg, 26)
    reg = RL.regions_lstai(lab26, n26, RL.lstai_touch_masks(crop))
    to_lst = {RL.PV: 1, RL.JC: 2, RL.DWM: 3, RL.IT: 4}
    mine = np.zeros(crop.shape, np.uint8)
    for i in range(n26):
        mine[lab26 == i + 1] = to_lst[int(reg[i])]
    assert n26 == seg_label.max()
    assert np.array_equal(mine, expected)


def _closest(cond, target_xyz, aff):
    c = np.argwhere(cond)
    xyz = (aff[:3, :3] @ c.T).T + aff[:3, 3]
    return xyz[np.argmin(np.linalg.norm(xyz - np.asarray(target_xyz), axis=1))]


def _single_voxel_regions(xyz, g0_maps):
    mask = np.zeros(FSL_SHAPE, bool)
    mask[world_to_vox(xyz)] = True
    rows, _ = RG.evaluate_mask(mask, None, g0_maps, keep_lesions=False)
    out = {}
    for G, R, M, pv, jc, it, dwm, *_ in rows:
        if G == "G0" and M == "none":
            out[R] = ("PV", "JC", "IT", "DWM")[int(np.argmax([pv, jc, it, dwm]))]
    return out


def test_lesion_abutting_only_the_third_ventricle_is_pv_unless_lateral_only(atlas, g0_maps):
    labels, aff, split, _ = atlas
    d = lambda m: ndi.binary_dilation(m, structure=np.ones((3, 3, 3), bool))  # noqa: E731
    cond = (split == A.WM) & d(split == A.THIRD_VENT) & ~d(split == A.VENT) & ~d(split == A.GM) & ~d(split == A.INFRA)
    xyz = _closest(cond, (6, -18, 6), aff)            # thalamus next to the third ventricle
    reg = _single_voxel_regions(xyz, g0_maps)
    assert reg["APP"] == "PV" and reg["LSTAI"] == "PV"        # as shipped
    assert reg["APP-LV"] == "DWM" and reg["LSTAI-LV"] == "DWM"  # Filippi 2019: lateral ventricles only


def test_brainstem_lesion_touching_third_ventricle_is_pv_for_lstai_but_it_for_device(atlas, g0_maps):
    labels, aff, split, _ = atlas
    d = lambda m: ndi.binary_dilation(m, structure=np.ones((3, 3, 3), bool))  # noqa: E731
    cond = (split == A.INFRA) & d(split == A.THIRD_VENT) & ~d(split == A.VENT) & ~d(split == A.GM)
    xyz = _closest(cond, (0, -22, -8), aff)           # midbrain, next to the third ventricle / aqueduct
    reg = _single_voxel_regions(xyz, g0_maps)
    assert reg["APP"] == "IT"                          # device: IT has priority
    assert reg["LSTAI"] == "PV"                        # LST-AI: PV > JC > IT
    assert reg["LSTAI-LV"] == "IT"


def test_min_size_rules():
    mask = np.zeros((20, 20, 20), bool)
    mask[1, 1, 1] = True                               # 1 mm^3, long axis 1
    mask[5, 5, 5:8] = True                             # 3 mm^3, long axis 3
    mask[10:13, 10:13, 10:12] = True                   # 18 mm^3
    lab, n = RL.label(mask, 18)
    f = RL.lesion_features(lab, n)
    assert sorted(f["volume_mm3"].tolist()) == [1, 3, 18]
    assert RL.keep_by_min_size(f, "none").sum() == 3
    assert RL.keep_by_min_size(f, "v3").sum() == 2
    assert RL.keep_by_min_size(f, "v14").sum() == 1
    assert RL.keep_by_min_size(f, "la3").sum() == 2


def test_contact_and_majority_rules():
    zc = np.array([[5, 1, 0, 0, 9],   # touches PV, mostly DWM -> contact PV, majority DWM
                   [0, 2, 0, 1, 0],   # touches IT and PV -> IT both ways (tie broken IT first)
                   [7, 0, 0, 0, 0],   # in no zone -> DWM
                   [0, 0, 3, 0, 1]])  # JC
    assert RL.regions_contact(zc).tolist() == [RL.PV, RL.IT, RL.DWM, RL.JC]
    assert RL.regions_majority(zc).tolist() == [RL.DWM, RL.PV, RL.DWM, RL.JC]


def test_dis_rule():
    assert RL.dis_brain([1, 1, 0, 9])
    assert not RL.dis_brain([5, 0, 0, 9])
    assert RL.dis_brain([0, 1, 1, 0])
    assert not RL.dis_brain([2, 1, 0, 0], pv_min=3)
    assert RL.dis_brain([3, 1, 0, 0], pv_min=3)


def test_threshold_on_stored_codes():
    k = np.array([101, 102, 127, 128, 152, 153], dtype=np.uint8)
    assert RG.binarise("F0", k, 0.4).tolist() == [False, True, True, True, True, True]
    assert RG.binarise("F0", k, 0.5).tolist() == [False, False, False, True, True, True]
    assert RG.binarise("F0", k, 0.6).tolist() == [False, False, False, False, False, True]
    s = np.array([5 * 127, 5 * 128], dtype=np.uint16)
    assert RG.binarise("FENS", s, 0.5).tolist() == [False, True]


def test_perturbation_is_small_and_seeded():
    P1 = A.perturbation_matrix(A.case_seed("x"))
    assert np.allclose(P1, A.perturbation_matrix(A.case_seed("x")))
    pts = np.array([[0, -18, 18, 1], [60, -18, 18, 1], [0, 60, 18, 1], [0, -18, 75, 1]]).T
    disp = np.linalg.norm((P1 @ pts - pts)[:3], axis=0)
    assert disp.max() < 2 * np.sqrt(3) + 0.02 * 80 + np.deg2rad(2) * 80 + 1e-6


def test_lstai_order_variants_on_synthetic_labels():
    """A lesion touching GM (2) and infratentorial (5): JC under the v1 code order, IT under the
    order stated in the LST-AI paper / v2. Touching label 4 wins in both."""
    shape = (12, 12, 12)
    labels = np.full(shape, 3, np.int16)
    labels[:, :, :4] = 2            # GM slab
    labels[:, :, 8:] = 5            # infratentorial slab
    labels[0:2] = 4                 # ventricle slab
    maps = {"G0": {"zone": {k: A.device_zone_map(labels) for k in ("APP", "APP-LV", "APP-3MM", "APP-MAJ")},
                   "touch": {"LSTAI": RL.lstai_touch_masks(labels), "LSTAI-LV": RL.lstai_touch_masks(labels)},
                   "touch_third": np.zeros(shape, bool), "touch_lateral": np.zeros(shape, bool)}}
    mask = np.zeros(shape, bool)
    mask[6, 6, 4:8] = True          # spans from the GM edge to the infratentorial edge
    mask[2, 6, 6] = True            # touches the ventricle slab
    rows, _ = RG.evaluate_mask(mask, None, maps, keep_lesions=False)
    got = {r[1]: r[3:7] for r in rows if r[2] == "none"}
    assert tuple(got["LSTAI"]) == (1, 1, 0, 0)       # PV + JC
    assert tuple(got["LSTAI-ORD2"]) == (1, 0, 1, 0)  # PV + IT
