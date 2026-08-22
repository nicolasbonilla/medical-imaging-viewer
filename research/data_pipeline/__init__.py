"""research.data_pipeline — public multi-site MS MRI ingestion for CALM-MS.

A reproducible, documented pipeline that turns PUBLIC MS lesion datasets into the
repo's common cohort format so they can (a) train a base lesion segmenter and
(b) calibrate / externally-validate the CALM-MS conformal FDR layer across many
scanners and sites.

Modules
-------
- ``common``            shared target-format definitions + path bootstrapping.
- ``download``          fetch OPEN datasets (idempotent, resumable, checksummed);
                        print exact manual steps for credential-gated ones.
- ``preprocess``        common skull-strip / bias / register / normalize entry
                        point that REUSES the repo's nifti + registration utils.
- ``to_calm_calibration`` emit the CALM-MS calibration format (per-candidate
                        score/features + TP/FP labels + site) from a base
                        segmenter's outputs + expert masks.

This package NEVER imports or mutates ``app/`` runtime code; it only *reads* the
repo's frozen, side-effect-free service functions (candidate extraction, feature
matrix, conformal p-values) so training/inference and this offline tooling can
never diverge.
"""
