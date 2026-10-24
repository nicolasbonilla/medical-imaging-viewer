"""Transform inside nnU-Net's pipeline, label safety, LR schedule, trainer guards (needs torch + nnunetv2).

Skipped when torch / nnunetv2 / batchgeneratorsv2 are not installed (the pinned job environment has them).
"""
import json
import os
import sys

import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("nnunetv2")
pytest.importorskip("batchgeneratorsv2")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from flames_thick import thick_slice as ts  # noqa: E402
from flames_thick.transforms import ThickSliceTransform  # noqa: E402

PLANS = json.load(open(os.path.join(HERE, "fixtures", "flames_plans.json")))
AXES = {"sagittal": 0, "axial": 1, "coronal": 2}
SPACING = PLANS["configurations"]["3d_fullres"]["spacing"]
PATCH = tuple(PLANS["configurations"]["3d_fullres"]["patch_size"])


def sample(seed=0, shape=PATCH):
    g = torch.Generator().manual_seed(seed)
    img = torch.randn((1,) + shape, generator=g)
    seg = (torch.rand((1,) + shape, generator=g) > 0.97).to(torch.int16)
    return img, seg


def test_transform_never_touches_the_label_and_ignores_it():
    t = ThickSliceTransform(AXES, SPACING, dict(ts.PREREGISTERED, p_apply=1.0))
    img, seg = sample(1)
    seg_other = torch.zeros_like(seg)
    np.random.seed(7)
    out1 = t(image=img.clone(), segmentation=seg)
    np.random.seed(7)
    out2 = t(image=img.clone(), segmentation=seg_other)
    assert out1["segmentation"] is seg and torch.equal(out1["segmentation"], sample(1)[1])
    assert torch.equal(out1["image"], out2["image"])            # image does not depend on the label
    assert out1["image"].dtype == torch.float32 and out1["image"].shape == img.shape
    assert not torch.allclose(out1["image"], img)


def test_transform_application_rate_is_two_thirds():
    t = ThickSliceTransform(AXES, SPACING)
    np.random.seed(0)
    small = torch.randn(1, 20, 24, 28)
    n_changed = 0
    for _ in range(600):
        out = t(image=small.clone(), segmentation=torch.zeros(1, 20, 24, 28, dtype=torch.int16))["image"]
        n_changed += int(not torch.equal(out, small))
    assert abs(n_changed / 600 - 2 / 3) < 0.06


def test_inserted_right_after_spatial_transform_and_full_pipeline_runs():
    from batchgeneratorsv2.transforms.spatial.spatial import SpatialTransform
    from nnunetv2.training.nnUNetTrainer.nnUNetTrainer import nnUNetTrainer
    from flames_thick.trainer import insert_after_spatial
    base = nnUNetTrainer.get_training_transforms(
        PATCH, (-0.5236, 0.5236), [[1, 1, 1], [0.5, 0.5, 0.5], [0.25, 0.25, 0.25]], (0, 1, 2), False,
        use_mask_for_norm=[True], is_cascaded=False, foreground_labels=[1], regions=None, ignore_label=None)
    thick = ThickSliceTransform(AXES, SPACING, dict(ts.PREREGISTERED, p_apply=1.0))
    comp = insert_after_spatial(base, thick)
    kinds = [type(x).__name__ for x in comp.transforms]
    i = kinds.index("SpatialTransform")
    assert kinds[i + 1] == "ThickSliceTransform" and kinds.count("ThickSliceTransform") == 1
    assert len(kinds) == len(base.transforms) + 1
    assert isinstance(comp.transforms[i], SpatialTransform)
    big = tuple(int(s * 1.2) for s in PATCH)
    img, seg = sample(3, big)
    out = comp(image=img, segmentation=seg)
    assert tuple(out["image"].shape) == (1,) + PATCH
    assert isinstance(out["segmentation"], list) and tuple(out["segmentation"][0].shape) == (1,) + PATCH


def test_warmup_poly_lr():
    from flames_thick.trainer import WarmupPolyLR
    opt = torch.optim.SGD([torch.nn.Parameter(torch.zeros(1))], lr=1.0)
    s = WarmupPolyLR(opt, 1e-3, 300, 5)
    assert np.isclose(s.lr_at(0), 2e-4) and np.isclose(s.lr_at(4), 1e-3) and np.isclose(s.lr_at(5), 1e-3)
    assert s.lr_at(150) < 1e-3 and s.lr_at(299) < 2e-5 and s.lr_at(300) == 0.0
    lrs = [s.lr_at(e) for e in range(5, 300)]
    assert all(a >= b for a, b in zip(lrs, lrs[1:]))           # monotone after warm-up
    s.step(10)
    assert np.isclose(opt.param_groups[0]["lr"], s.lr_at(10))  # stateless: resume gives the same LR


def test_preregistered_schedule_defaults(monkeypatch):
    from flames_thick import trainer as tr
    for k in tr.PREREGISTERED_SCHEDULE:
        monkeypatch.delenv(k, raising=False)
    assert tr._env("FT_EPOCHS", int) == 300 and tr._env("FT_ITERS", int) == 250
    assert tr._env("FT_INITIAL_LR", float) == 1e-3 and tr._env("FT_SAVE_EVERY", int) == 5
    monkeypatch.setenv("FT_EPOCHS", "4")
    assert tr._env("FT_EPOCHS", int) == 4


def test_trainers_are_found_by_nnunet_external_lookup(monkeypatch):
    monkeypatch.setenv("nnUNet_extTrainer", os.path.join(os.path.dirname(HERE), "nnunet_ext"))
    import importlib
    import nnunetv2.paths
    importlib.reload(nnunetv2.paths)
    import nnunetv2.utilities.find_objects as fo
    importlib.reload(fo)
    a = fo.recursive_find_trainer_class_by_name("nnUNetTrainerFLAMeSThick")
    b = fo.recursive_find_trainer_class_by_name("nnUNetTrainerFLAMeSFT")
    assert a.THICK is True and b.THICK is False and issubclass(a, b)
