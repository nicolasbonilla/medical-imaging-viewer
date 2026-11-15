"""D5 two-tool consensus (PREREG §3): keep a lesion of the primary arm only if another independent arm also marks it.

Pure numpy/scipy, no app import, no network. The registered order is:
1. overlap on the scan's native FLAIR grid, both masks resampled there as in paper 1's lesion-wise evaluation;
2. keep the agreed components of the primary arm;
3. warp to MNI with paper 1's transform (resampled value >= 0.5);
4. paper 1's lesion rule;
5. the app's DIS rule.

Steps 1–2 are here. Steps 3–5 reuse paper 1's frozen functions in the record builder.

- `agreed(primary, partners)`: an 18-connected component of `primary` is agreed when it shares at least 1 voxel with a
  component of at least `k - 1` partner masks. The primary rule has k = 2 and one partner (FLAMeS-ens with LST-AI).
- `split(primary, partners, k)`: returns (agreed_mask, single_tool_mask, n_agreed, n_single).
"""
from typing import Sequence, Tuple

import numpy as np
from scipy import ndimage

# 18-connectivity, as the app (RC-030) and paper 1 use
STRUCT_18 = ndimage.generate_binary_structure(3, 2)


def _binary(m: np.ndarray) -> np.ndarray:
    return np.asarray(m) > 0


def split(primary: np.ndarray, partners: Sequence[np.ndarray], k: int = 2
          ) -> Tuple[np.ndarray, np.ndarray, int, int]:
    """Split the primary arm's lesions into agreed and single-tool ones.

    A component is agreed when at least k - 1 partner masks overlap it by at least 1 voxel. All masks must be on the
    same grid, which the caller guarantees by resampling as paper 1 does."""
    p = _binary(primary)
    parts = [_binary(q) for q in partners]
    if any(q.shape != p.shape for q in parts):
        raise ValueError("all masks must be on the same grid (resample first, as paper 1's lesion-wise evaluation)")
    if k < 2 or k - 1 > len(parts):
        raise ValueError(f"k = {k} needs at least {k - 1} partner masks")
    lab, n = ndimage.label(p, structure=STRUCT_18)
    if n == 0:
        z = np.zeros_like(p)
        return z, z.copy(), 0, 0
    votes = np.zeros(n + 1, dtype=np.int32)
    for q in parts:
        hit = np.unique(lab[q & p])
        votes[hit[hit > 0]] += 1
    keep = votes >= (k - 1)
    keep[0] = False
    agreed_mask = keep[lab]
    single_mask = p & ~agreed_mask
    n_agreed = int(keep[1:].sum())
    return agreed_mask, single_mask, n_agreed, n - n_agreed


def agreed(primary: np.ndarray, partners: Sequence[np.ndarray], k: int = 2) -> np.ndarray:
    return split(primary, partners, k)[0]
