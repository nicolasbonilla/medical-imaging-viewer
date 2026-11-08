"""Paper 1 healthy-control arm — the definitions REUSED from paper A (PREREG-healthy-controls.md section 4).

Copied verbatim (same text, so the reuse is checkable) from branch research/paper-a-v0.3, commit 413f5b5:
  research/paper_a/v03_candidates.py   THRESHOLD, MIN_VOL_MM3, STRUCT, load()
  research/paper_a/v03c_controls.py    _cand_voxels() (here: cand_voxels), class AppDIS (the app's DIS path)
  research/paper_a/v03_metrics.py      clopper_pearson()
The paper A modules are not imported directly because v03_data.py refuses to import without the paper A
patient data folder; research/paper_1/tests/test_hc_core.py imports them (with a stub data folder) and
checks that the copies are identical in source text and in output.

Pure functions; no cloud calls. The app modules are imported read-only by AppDIS (offline environment).
"""
import os
import sys

import nibabel as nib
import numpy as np
from scipy import ndimage as ndi
from scipy.stats import beta, binom

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

THRESHOLD, MIN_VOL_MM3 = 0.5, 3.0                       # v03_candidates.py
STRUCT = ndi.generate_binary_structure(3, 2)            # 18-connectivity


def load(path):
    return np.asarray(nib.load(path).get_fdata(dtype=np.float32))


def cand_voxels(prob, vox):
    """Same labelling as v03_candidates.candidates: flat voxel indices of each kept component,
    in the same order as its outputs."""
    lab, n = ndi.label(prob >= THRESHOLD, structure=STRUCT)
    counts = np.bincount(lab.ravel(), minlength=n + 1)
    ids = [i for i in range(1, n + 1) if counts[i] * vox >= MIN_VOL_MM3 - 1e-9]
    if not ids:
        return []
    objs = ndi.find_objects(lab)
    out = []
    for i in ids:
        sl = objs[i - 1]
        sub = lab[sl] == i
        idx = np.nonzero(sub)
        full = tuple(idx[d] + sl[d].start for d in range(3))
        out.append(np.ravel_multi_index(full, lab.shape).astype(np.int64))
    return out


def clopper_pearson(x, n, conf=0.95):
    if n == 0:
        return [None, None]
    a = 1 - conf
    lo = 0.0 if x == 0 else float(beta.ppf(a / 2, x, n - x + 1))
    hi = 1.0 if x == n else float(beta.ppf(1 - a / 2, x + 1, n - x))
    return [lo, hi]


def mcnemar_exact(a, b):
    """a = arm, b = reference (paired boolean arrays). Exact two-sided McNemar on the discordant pairs:
    p = min(1, 2 P[Bin(n10 + n01, 1/2) <= min(n10, n01)]); p = 1 when there is no discordant pair.
    Same formula as v03c_controls.mcnemar_exact (keys renamed from ens_only / f0_only)."""
    a, b = np.asarray(a, bool), np.asarray(b, bool)
    n10 = int((a & ~b).sum())
    n01 = int((~a & b).sum())
    k = n10 + n01
    p = 1.0 if k == 0 else min(1.0, 2 * binom.cdf(min(n10, n01), k, 0.5))
    return {"arm_only": n10, "reference_only": n01, "p_two_sided": float(p)}


# ------------------------------------------------------------------ S3 app DIS
class AppDIS:
    def __init__(self, gimg):
        sys.path.insert(0, os.path.join(ROOT, "backend"))
        from app.services import lesion_analysis_service as las     # read-only use of app code
        from app.services import ms_region_classifier as rc
        self.rc, self.las = rc, las
        if not rc.looks_mni(gimg.affine, gimg.shape[:3]):
            raise RuntimeError("grid not MNI-like: the app would refuse (NotMNISpaceError)")
        zooms = [float(z) for z in gimg.header.get_zooms()[:3]]
        self.spacing = (zooms[2], zooms[0], zooms[1])                   # app internal (D, H, W) = (k, a0, a1)
        zr = rc.generate_zone_map_atlas(gimg, self.spacing)
        self.zone = np.ascontiguousarray(np.transpose(np.asarray(zr["zone_mask"]), (2, 0, 1)))
        self.shape = tuple(gimg.shape[:3])
        self.affine = gimg.affine.copy()

    def run(self, voxel_lists):
        """voxel_lists: flat NIfTI indices of each lesion of the set. Returns (dis dict, classified NIfTI)."""
        if not voxel_lists:
            return {"dis_met_brain": False, "regions": {}, "any_dis_region": False}, None
        m = np.zeros(int(np.prod(self.shape)), np.uint8)
        for v in voxel_lists:
            m[v] = 1
        m = np.transpose(m.reshape(self.shape), (2, 0, 1)).copy()
        cl = self.rc.classify_from_zone_mask(m, self.zone, self.spacing)
        dis = self.las.compute_dis_criteria(cl["classified_mask"], voxel_spacing=self.spacing)
        pres = {k: bool(v["present"]) for k, v in dis["region_details"].items()}
        return ({"dis_met_brain": bool(dis["dis_met_brain"]), "regions": pres, "any_dis_region": any(pres.values())},
                np.transpose(cl["classified_mask"], (1, 2, 0)))


def holm(pvals):
    """Holm step-down adjusted p-values (same order as the input; None -> treated as p = 1)."""
    p = np.array([1.0 if v is None else float(v) for v in pvals])
    order = np.argsort(p, kind="stable")
    m = p.size
    adj = np.empty(m)
    run = 0.0
    for r, i in enumerate(order):
        run = max(run, min(1.0, (m - r) * p[i]))
        adj[i] = run
    return adj.tolist()
