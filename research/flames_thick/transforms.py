"""batchgeneratorsv2 wrapper of the thick-slice simulator (used inside nnU-Net's training pipeline).

nnU-Net 2.8 applies transforms per sample to torch tensors: image (C, X, Y, Z) float32, segmentation
(C, X, Y, Z) int16. This transform changes the image only; `_apply_to_segmentation` returns the
segmentation object unchanged, and the image parameters are drawn without looking at it.
"""
import numpy as np
import torch
from batchgeneratorsv2.transforms.base.basic_transform import BasicTransform

from flames_thick import thick_slice as ts


class ThickSliceTransform(BasicTransform):
    def __init__(self, axis_map, spacing_by_axis, cfg=None):
        super().__init__()
        self.axis_map = {k: int(v) for k, v in axis_map.items()}
        self.spacing_by_axis = [float(s) for s in spacing_by_axis]
        self.cfg = dict(ts.PREREGISTERED if cfg is None else cfg)

    def get_parameters(self, **data_dict) -> dict:
        # np.random (global, per data-augmentation worker) like the other batchgeneratorsv2 transforms
        return ts.sample_params(np.random, self.axis_map, self.spacing_by_axis, self.cfg)

    def _apply_to_image(self, img: torch.Tensor, **params) -> torch.Tensor:
        if not params.get("apply"):
            return img
        out = ts.apply_params(img.numpy(), params)
        return torch.from_numpy(np.ascontiguousarray(out, dtype=np.float32))

    def _apply_to_segmentation(self, segmentation: torch.Tensor, **params) -> torch.Tensor:
        return segmentation                      # labels stay the thin expert mask (PROTOCOL §5.3)

    def _apply_to_regr_target(self, regression_target, **params):
        return regression_target
