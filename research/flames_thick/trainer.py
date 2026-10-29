"""nnU-Net v2 trainers for FLAMeS-thick (PROTOCOL.md §5).

  nnUNetTrainerFLAMeSFT     arm B: fine-tune FLAMeS fold 0 with nnU-Net's default augmentation only
  nnUNetTrainerFLAMeSThick  arm A: the same + on-the-fly thick-slice simulation (thick_slice.py)

Both: strict load of ALL FLAMeS weights (segmentation heads included; nnU-Net's -pretrained_weights
would re-initialise them), refusal to train from random weights, LR 1e-3 with 5-epoch warm-up then
poly decay, checkpoint every FT_SAVE_EVERY epochs with callbacks (cloud upload) and an epoch-end hook
for the cost guard. Schedule knobs come from FT_* environment variables so the pilot can shorten them;
the defaults are the pre-registered values. nnU-Net finds these classes through nnUNet_extTrainer
(research/flames_thick/nnunet_ext), with `flames_thick` importable (PYTHONPATH).
"""
import glob
import hashlib
import os
import time

import torch
from batchgenerators.utilities.file_and_folder_operations import join, load_pickle
from batchgeneratorsv2.transforms.spatial.spatial import SpatialTransform
from batchgeneratorsv2.transforms.utils.compose import ComposeTransforms
from batchgeneratorsv2.transforms.utils.pseudo2d import Convert2DTo3DTransform
from torch._dynamo import OptimizedModule

from nnunetv2.training.nnUNetTrainer.nnUNetTrainer import nnUNetTrainer

from flames_thick import thick_slice as ts
from flames_thick.transforms import ThickSliceTransform

PREREGISTERED_SCHEDULE = {"FT_EPOCHS": 300, "FT_ITERS": 250, "FT_VAL_ITERS": 50, "FT_SAVE_EVERY": 5,
                          "FT_INITIAL_LR": 1e-3, "FT_WARMUP_EPOCHS": 5}


def _env(name, cast):
    v = os.environ.get(name, "").strip()
    return cast(v) if v else cast(PREREGISTERED_SCHEDULE[name])


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


class BudgetStop(Exception):
    """Raised at an epoch end (after a resumable checkpoint is written) when a guard says stop."""


class WarmupPolyLR:
    """Stateless per-epoch LR: linear warm-up lr*(e+1)/w for e < w, then poly(0.9) to 0 at max_epochs.

    Same interface as nnU-Net's PolyLRScheduler (step(current_step)) so resuming at any epoch gives
    exactly the LR of an uninterrupted run.
    """

    def __init__(self, optimizer, initial_lr, max_epochs, warmup_epochs, exponent=0.9):
        self.optimizer, self.initial_lr = optimizer, initial_lr
        self.max_epochs, self.warmup, self.exponent = max_epochs, warmup_epochs, exponent

    def lr_at(self, epoch):
        if epoch < self.warmup:
            return self.initial_lr * (epoch + 1) / self.warmup
        span = max(1, self.max_epochs - self.warmup)
        frac = min(1.0, (epoch - self.warmup) / span)
        return self.initial_lr * (1.0 - frac) ** self.exponent

    def step(self, current_step=None):
        lr = self.lr_at(int(current_step or 0))
        for g in self.optimizer.param_groups:
            g["lr"] = lr

    def state_dict(self):
        return {}

    def load_state_dict(self, state):
        pass


class nnUNetTrainerFLAMeSFT(nnUNetTrainer):
    THICK = False

    def __init__(self, plans: dict, configuration: str, fold: int, dataset_json: dict,
                 device: torch.device = torch.device("cuda")):
        super().__init__(plans, configuration, fold, dataset_json, device)
        self.num_epochs = _env("FT_EPOCHS", int)
        self.num_iterations_per_epoch = _env("FT_ITERS", int)
        self.num_val_iterations_per_epoch = _env("FT_VAL_ITERS", int)
        self.save_every = _env("FT_SAVE_EVERY", int)
        self.initial_lr = _env("FT_INITIAL_LR", float)
        self.warmup_epochs = _env("FT_WARMUP_EPOCHS", int)
        self.init_source = None            # set by load_flames_init() or load_checkpoint()
        self.checkpoint_callbacks = []     # fn(path) after a checkpoint file is written
        self.epoch_end_callbacks = []      # fn(trainer, finished_epoch) -> None or a stop reason
        self.epoch_records = []            # [{"epoch", "seconds", "lr", "train_loss", "val_loss", "pseudo_dice"}]
        self.thick_info = None
        # Local CPU plumbing tests only: a laptop cannot back-propagate FLAMeS's 112x128x160 patch in RAM.
        # Never allowed on a GPU (the real runs keep FLAMeS's plans untouched).
        tp = os.environ.get("FT_LOCAL_TEST_PATCH", "").strip()
        if tp:
            if self.device.type != "cpu":
                raise RuntimeError("FT_LOCAL_TEST_PATCH is for local CPU tests only")
            self.configuration_manager.configuration["patch_size"] = [int(x) for x in tp.split(",")]
            self.print_to_log_file(f"LOCAL TEST: patch size overridden to {self.configuration_manager.patch_size}")

    # ------------------------------------------------------------------ weights
    def _bare_network(self):
        mod = self.network.module if self.is_ddp else self.network
        return mod._orig_mod if isinstance(mod, OptimizedModule) else mod

    def load_flames_init(self, checkpoint_path, expected_sha256=None):
        """Load every FLAMeS weight (strict). Optimiser, epoch and logs start fresh."""
        if expected_sha256:
            got = sha256(checkpoint_path)
            if got != expected_sha256:
                raise RuntimeError(f"FLAMeS checkpoint SHA-256 {got} != expected {expected_sha256}")
        if not self.was_initialized:
            self.initialize()
        ckpt = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        sd = {}
        for k, v in ckpt["network_weights"].items():
            k = k.replace("_orig_mod.", "")
            sd[k[7:] if k.startswith("module.") else k] = v
        self._bare_network().load_state_dict(sd, strict=True)
        self.init_source = {"kind": "flames", "path": os.path.basename(checkpoint_path),
                            "trainer_name": ckpt.get("trainer_name"), "n_tensors": len(sd),
                            "sha256": expected_sha256}
        self.print_to_log_file(f"FLAMeS init loaded strictly: {self.init_source}")

    def load_checkpoint(self, filename_or_checkpoint):
        super().load_checkpoint(filename_or_checkpoint)
        self.init_source = {"kind": "checkpoint", "resumed_at_epoch": int(self.current_epoch)}
        self.print_to_log_file(f"resumed from checkpoint at epoch {self.current_epoch}")

    # ------------------------------------------------------------------ optimiser
    def configure_optimizers(self):
        optimizer = torch.optim.SGD(self.network.parameters(), self.initial_lr, weight_decay=self.weight_decay,
                                    momentum=0.99, nesterov=True)
        return optimizer, WarmupPolyLR(optimizer, self.initial_lr, self.num_epochs, self.warmup_epochs)

    # ------------------------------------------------------------------ training loop hooks
    def on_train_start(self):
        if self.init_source is None:
            raise RuntimeError("refusing to train from random weights: call load_flames_init() or "
                               "load_checkpoint() first (PROTOCOL §5.1)")
        super().on_train_start()

    def save_checkpoint(self, filename: str) -> None:
        if os.path.basename(filename) == "checkpoint_best.pth":
            return                                   # never used (PROTOCOL §5.2: final, no selection)
        super().save_checkpoint(filename)
        if self.local_rank == 0 and not self.disable_checkpointing and os.path.isfile(filename):
            if os.path.basename(filename) == "checkpoint_latest.pth":
                self._latest_saved_for_epoch = self.current_epoch
            for cb in self.checkpoint_callbacks:
                cb(filename)

    def perform_actual_validation(self, save_probabilities: bool = False):
        if os.environ.get("FT_LOCAL_TEST_PATCH", "").strip():
            self.inference_allowed_mirroring_axes = None   # local CPU plumbing test only: no 8x mirroring
        super().perform_actual_validation(save_probabilities)

    # per-phase wall time (the pilot extrapolates the 250-iteration epoch from these)
    def on_train_epoch_start(self):
        self._t_train0 = time.monotonic()
        super().on_train_epoch_start()

    def on_validation_epoch_start(self):
        self._t_train1 = time.monotonic()
        super().on_validation_epoch_start()

    def on_validation_epoch_end(self, val_outputs):
        super().on_validation_epoch_end(val_outputs)
        self._t_val1 = time.monotonic()

    def _save_resume_checkpoint(self):
        """checkpoint_latest for the epoch that just ended (on_epoch_end already incremented the counter)."""
        self.current_epoch -= 1
        self.save_checkpoint(join(self.output_folder, "checkpoint_latest.pth"))
        self.current_epoch += 1

    def on_epoch_end(self):
        # The record is built BEFORE nnU-Net's on_epoch_end, which writes the periodic checkpoint: the
        # upload callback then ships epochs.json including this epoch (a resume must not lose it).
        finished = self.current_epoch
        lg = self.logger
        rec = {"epoch": finished}
        try:
            rec["seconds"] = round(time.time() - lg.get_value("epoch_start_timestamps", step=-1), 2)
            rec["lr"] = float(self.optimizer.param_groups[0]["lr"])
            rec["train_loss"] = float(lg.get_value("train_losses", step=-1))
            rec["val_loss"] = float(lg.get_value("val_losses", step=-1))
            rec["pseudo_dice"] = [float(x) for x in lg.get_value("dice_per_class_or_region", step=-1)]
            rec["train_seconds"] = round(self._t_train1 - self._t_train0, 2)
            rec["val_seconds"] = round(self._t_val1 - self._t_train1, 2)
            rec["iters"], rec["val_iters"] = self.num_iterations_per_epoch, self.num_val_iterations_per_epoch
        except Exception as exc:                     # logging must never stop training
            rec["log_error"] = repr(exc)[:200]
        self.epoch_records.append(rec)
        super().on_epoch_end()                       # may save checkpoint_latest; increments current_epoch
        if finished >= self.num_epochs - 1:
            return                                   # last epoch: on_train_end writes checkpoint_final
        for cb in self.epoch_end_callbacks:
            reason = cb(self, finished)
            if reason:
                if getattr(self, "_latest_saved_for_epoch", None) != finished:
                    self._save_resume_checkpoint()
                self.print_to_log_file(f"STOP after epoch {finished}: {reason}")
                raise BudgetStop(reason)

    # ------------------------------------------------------------------ augmentation
    def get_training_transforms(self, patch_size, rotation_for_DA, deep_supervision_scales, mirror_axes,
                                do_dummy_2d_data_aug, use_mask_for_norm=None, is_cascaded=False,
                                foreground_labels=None, regions=None, ignore_label=None):
        tr = nnUNetTrainer.get_training_transforms(
            patch_size, rotation_for_DA, deep_supervision_scales, mirror_axes, do_dummy_2d_data_aug,
            use_mask_for_norm=use_mask_for_norm, is_cascaded=is_cascaded, foreground_labels=foreground_labels,
            regions=regions, ignore_label=ignore_label)
        if not self.THICK:
            return tr
        axis_map, info = self.thick_axis_map()
        spacing = [float(s) for s in self.configuration_manager.spacing]
        thick = ThickSliceTransform(axis_map, spacing)
        self.thick_info = {**info, "axis_map": axis_map, "spacing_by_patch_axis": spacing,
                           "config": {k: (list(v) if isinstance(v, tuple) else v) for k, v in thick.cfg.items()}}
        self.print_to_log_file(f"thick-slice augmentation: {self.thick_info}")
        return insert_after_spatial(tr, thick)

    def thick_axis_map(self):
        """Anatomical -> patch axes, from the direction cosines of every preprocessed training case."""
        pkls = sorted(glob.glob(join(self.preprocessed_dataset_folder, "*.pkl")))
        if not pkls:
            raise RuntimeError(f"no preprocessed cases in {self.preprocessed_dataset_folder}")
        tf = self.plans_manager.transpose_forward
        maps = {}
        for p in pkls:
            d = load_pickle(p)["sitk_stuff"]["direction"]
            maps.setdefault(tuple(sorted(ts.anatomical_axes(d, tf).items())), []).append(os.path.basename(p))
        if len(maps) != 1:
            raise RuntimeError(f"training cases do not share one orientation: {list(maps)}")
        (key, cases), = maps.items()
        return dict(key), {"n_cases_checked": len(cases), "transpose_forward": list(tf)}


class nnUNetTrainerFLAMeSThick(nnUNetTrainerFLAMeSFT):
    THICK = True


def insert_after_spatial(compose: ComposeTransforms, transform):
    """Insert `transform` right after nnU-Net's SpatialTransform (and Convert2DTo3D if present)."""
    items = list(compose.transforms)
    idx = [i for i, t in enumerate(items) if isinstance(t, SpatialTransform)]
    if len(idx) != 1:
        raise RuntimeError(f"expected exactly one SpatialTransform, found {len(idx)}")
    pos = idx[0] + 1
    if pos < len(items) and isinstance(items[pos], Convert2DTo3DTransform):
        pos += 1
    items.insert(pos, transform)
    return ComposeTransforms(items)
