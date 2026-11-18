"""Paper 1 addendum 2, analysis 3 (PREREG-addendum-2026-11-age-faithful-deterministic.md section 5): a clinically
faithful automated dissemination-in-space rule, computed in each person's own image space (no registration).

Definitions (fixed in the protocol before any output was computed):
  lesion       an 18-connected component of the binary map (map >= 0.5) on the image's own voxel grid, kept when its
               largest extent F >= 3 mm. F = the maximum Euclidean distance in mm (world coordinates from the image
               affine) between the CENTRES of any two of its voxels (3-D maximum Feret diameter of the voxel-centre
               set; a single voxel has F = 0). Sensitivity: F_corner = the same over the 8 corners of every voxel (the
               full extent of the voxelised lesion; an upper bound). No volume criterion.
  anatomy      SynthSeg 2.0 (robust) labels of the same FLAIR, resampled to the lesion grid by nearest neighbour in
               world coordinates: lateral ventricles {4, 5, 43, 44}; cerebral cortex {3, 42}; infratentorial
               {7, 8, 16, 46, 47} (cerebellar white matter and cortex, brainstem).
  contact      the lesion dilated by one voxel with the 3 x 3 x 3 (26-neighbour) element contains >= 1 voxel of the
               structure (overlap counts).
  region       one per lesion, priority IT > PV > JC (the app's convention): IT when >= 50 % of its voxels carry an
               infratentorial label; else PV when in contact with a lateral ventricle; else JC when in contact with
               the cerebral cortex; else "other".
  rule         met when qualifying lesions occupy >= 2 of PV, JC, IT; variant: PV needs >= 3 PV lesions.
Pure functions (numpy, scipy.ndimage); no cloud calls, no app code.
"""
import numpy as np
from scipy import ndimage as ndi

STRUCT18 = ndi.generate_binary_structure(3, 2)
CUBE26 = np.ones((3, 3, 3), bool)
VENTRICLES = (4, 5, 43, 44)
CORTEX = (3, 42)
INFRATENTORIAL = (7, 8, 16, 46, 47)
MIN_AXIS_MM = 3.0
TOL = 1e-6
REGIONS = ("PV", "JC", "IT")
_CORNERS = np.array([[i, j, k] for i in (-0.5, 0.5) for j in (-0.5, 0.5) for k in (-0.5, 0.5)])


def _max_pairwise_at_least(pts, thr):
    """True when some pair of points is >= thr apart (exact; chunked)."""
    n = len(pts)
    if n < 2:
        return False
    for s in range(0, n, 512):
        d = pts[s:s + 512, None, :] - pts[None, :, :]
        if float((d * d).sum(-1).max()) >= (thr - TOL) ** 2:
            return True
    return False


def long_axis_at_least(ijk, affine, thr=MIN_AXIS_MM, corners=False):
    """Is the 3-D maximum Feret diameter of a voxel set >= thr mm?  ijk: (N, 3) voxel indices.
    Shortcuts are exact: F >= the largest axis-aligned extent of the points, and F <= the bounding-box diagonal."""
    p = np.asarray(ijk, float)
    if corners:
        p = np.unique((p[:, None, :] + _CORNERS[None]).reshape(-1, 3), axis=0)
    pts = p @ np.asarray(affine, float)[:3, :3].T + np.asarray(affine, float)[:3, 3]
    if len(pts) < 2:
        return False
    ext = pts.max(0) - pts.min(0)
    if float(ext.max()) >= thr - TOL:
        return True
    if float(np.sqrt((ext * ext).sum())) < thr - TOL:
        return False
    return _max_pairwise_at_least(pts, thr)


def labels_on_grid(lab_data, lab_affine, shape, affine):
    """Nearest-neighbour resampling of a label volume onto another grid (world coordinates), slice by slice."""
    lab = np.asarray(lab_data)
    if lab.ndim == 4:
        lab = lab[..., 0]
    lab = np.rint(lab).astype(np.int32)
    M = np.linalg.inv(np.asarray(lab_affine, float)) @ np.asarray(affine, float)
    out = np.zeros(tuple(shape[:3]), np.int16)
    ii, jj = np.meshgrid(np.arange(shape[0]), np.arange(shape[1]), indexing="ij")
    for k in range(shape[2]):
        vox = np.stack([ii.ravel(), jj.ravel(), np.full(ii.size, k), np.ones(ii.size)])
        src = M @ vox
        out[:, :, k] = ndi.map_coordinates(lab, src[:3], order=0, mode="constant", cval=0).reshape(ii.shape)
    return out


def classify_lesions(mask, affine, anat):
    """mask: binary array on the lesion grid; anat: int labels on the same grid.
    Returns a list of dicts {voxels, axis_ok, axis_ok_corner, region} for every 18-connected component."""
    lab, n = ndi.label(np.asarray(mask, bool), structure=STRUCT18)
    if n == 0:
        return []
    objs = ndi.find_objects(lab)
    shp = lab.shape
    vent = np.isin(anat, VENTRICLES)
    ctx = np.isin(anat, CORTEX)
    inf = np.isin(anat, INFRATENTORIAL)
    out = []
    for i, sl in enumerate(objs, 1):
        big = tuple(slice(max(0, s.start - 1), min(shp[d], s.stop + 1)) for d, s in enumerate(sl))
        sub = lab[big] == i
        idx = np.argwhere(sub) + np.array([b.start for b in big])
        nvox = int(sub.sum())
        if float(inf[big][sub].sum()) >= 0.5 * nvox:
            region = "IT"
        else:
            dil = ndi.binary_dilation(sub, structure=CUBE26)
            region = "PV" if vent[big][dil].any() else ("JC" if ctx[big][dil].any() else "other")
        ok = bool(long_axis_at_least(idx, affine))
        # the corner set contains every centre's extreme, so F_corner >= F: compute it only when F < 3 mm
        out.append({"voxels": nvox, "axis_ok": ok,
                    "axis_ok_corner": ok or bool(long_axis_at_least(idx, affine, corners=True)), "region": region})
    return out


def rule(lesions, key="axis_ok", pv_min=1):
    """(met, counts) from classified lesions: >= 2 of PV, JC, IT with >= 1 qualifying lesion (PV >= pv_min)."""
    cnt = {r: 0 for r in REGIONS + ("other",)}
    for les in lesions:
        if les[key]:
            cnt[les["region"]] += 1
    met = sum(1 for r in REGIONS if cnt[r] >= (pv_min if r == "PV" else 1)) >= 2
    return bool(met), cnt


def evaluate_mask(mask, affine, anat):
    """Everything analysis 3 records for one binary mask: rule (primary), PV >= 3 variant, corner-Feret
    sensitivity, region counts, and the number of components before / after the size criterion."""
    les = classify_lesions(mask, affine, anat)
    met, cnt = rule(les)
    met3, _ = rule(les, pv_min=3)
    metc, cntc = rule(les, key="axis_ok_corner")
    return {"n_components": len(les), "n_lesions": sum(x["axis_ok"] for x in les),
            "n_lesions_corner": sum(x["axis_ok_corner"] for x in les), "rule": met, "rule_pv3": met3,
            "rule_corner": metc, "regions": cnt, "regions_corner": cntc}
