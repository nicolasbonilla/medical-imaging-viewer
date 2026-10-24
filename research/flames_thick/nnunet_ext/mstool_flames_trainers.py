"""Entry module for nnU-Net's external-trainer lookup (nnUNet_extTrainer points to this folder).

nnU-Net imports every module in this folder while searching a trainer class by name, so this folder
must contain only this file. The classes live in the importable package `flames_thick`.
"""
from flames_thick.trainer import nnUNetTrainerFLAMeSFT, nnUNetTrainerFLAMeSThick  # noqa: F401
