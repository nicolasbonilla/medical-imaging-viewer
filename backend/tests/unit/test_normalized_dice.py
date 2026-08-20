"""nDSC (normalised Dice) — Raina et al. 2023, the Shifts load-corrected Dice.

Plain DSC is biased by lesion LOAD (fraction of lesion voxels): a high-load scan gets an
inflated DSC for the same relative error. nDSC rescales false positives to a reference load
r=0.001 so scores are comparable across patients. These tests lock in the exact formula from
the reference implementation (github.com/NataliiaMolch/nDSC), especially the DEFINING property:
nDSC equals plain DSC exactly when the scan's lesion load == r.
"""
import numpy as np

from app.services.segmentation_comparison_service import (
    compute_normalized_dice,
    compute_dice,
)


def test_perfect_match_is_one():
    ref = np.zeros((20, 20, 20), np.uint8)
    ref[5:10, 5:10, 5:10] = 1
    assert compute_normalized_dice(ref.copy(), ref) == 1.0


def test_both_empty_is_one_empty_ref_with_pred_is_zero():
    z = np.zeros((16, 16, 16), np.uint8)
    assert compute_normalized_dice(z, z) == 1.0
    pred = z.copy(); pred[2:4, 2:4, 2:4] = 1
    assert compute_normalized_dice(pred, z) == 0.0  # FP only, no ref → 0


def test_equals_plain_dice_at_reference_load():
    """DEFINING property: when the scan's lesion load == r (0.001), scaling=1 → nDSC == DSC."""
    N = 100  # 100^3 = 1e6 voxels
    ref = np.zeros((N, N, N), np.uint8)
    ref[0:10, 0:10, 0:10] = 1                 # 1000 lesion voxels → load = 1000/1e6 = 0.001 = r
    pred = ref.copy()
    pred[50:52, 50:55, 50:60] = 1             # add ~... false positives elsewhere
    ndsc = compute_normalized_dice(pred, ref)
    dice = compute_dice(pred, ref)
    assert abs(ndsc - dice) < 1e-6


def test_corrects_inflated_dice_on_high_load_scan():
    """On a HIGH-load scan, plain DSC is inflated (FP contribution is small vs many TP);
    nDSC scales the FP up and corrects the score DOWN — the bias fix."""
    N = 100
    ref = np.zeros((N, N, N), np.uint8)
    ref[0:50, 0:50, 0:40] = 1                 # 100,000 lesion voxels → load 0.1 >> r
    pred = ref.copy()
    pred[90:91, 0:40, 0:25] = 1               # 1000 false-positive voxels
    dice = compute_dice(pred, ref)
    ndsc = compute_normalized_dice(pred, ref)
    assert dice > 0.98                        # DSC looks great on the heavy-load scan
    assert ndsc < dice - 0.2                  # nDSC corrects it substantially downward


def test_low_load_scan_penalises_fp_less_than_dice():
    """On a LOW-load scan (load < r), nDSC scales FP DOWN → nDSC >= DSC."""
    N = 100
    ref = np.zeros((N, N, N), np.uint8)
    ref[0:3, 0:3, 0:3] = 1                     # 27 voxels → load 2.7e-5 << r
    pred = ref.copy()
    pred[50:51, 0:10, 0:10] = 1                # 100 FP voxels
    assert compute_normalized_dice(pred, ref) >= compute_dice(pred, ref)
