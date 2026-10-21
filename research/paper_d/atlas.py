"""MSMask atlas handling for paper D (research code, not the device).

The MSMask atlas (LST-AI; labels 1 CSF, 2 GM, 3 WM, 4 Ventricles, 5 Infratentorial) sits on the
ICBM 2009c 1 mm grid (193 x 229 x 193, origin -96/-132/-78). Inspection (protocol §4) shows that
label 4 is ONE connected structure holding the lateral ventricles AND the third ventricle, that the
fourth ventricle lies inside label 5, and that the thalami are labelled 3 (WM). This module

  * splits label 4 into lateral ventricles and third ventricle (label 6) — `split_third_ventricle`;
  * mirrors, line for line, the device's zone-map construction (ms_region_classifier.
    generate_zone_map_atlas, steps 2-4) so variants of it can be built — `device_zone_map`;
  * resamples atlas-space maps onto a scan grid by nearest neighbour in world coordinates, as the
    device does through nilearn — `resample_nearest`;
  * builds the pre-specified small residual misregistration (level G2) — `perturbation_matrix`.

Only numpy / scipy / nibabel are used so the registration venv (picsl_greedy) can import it.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage as ndi

CSF, GM, WM, VENT, INFRA, THIRD_VENT = 1, 2, 3, 4, 5, 6
CUBE = np.ones((3, 3, 3), dtype=bool)


def load_labels(path):
    import nibabel as nib
    img = nib.load(str(path))
    return np.asarray(img.dataobj).astype(np.int16), img.affine.copy()


def split_third_ventricle(labels: np.ndarray, affine: np.ndarray) -> tuple[np.ndarray, dict]:
    """Return a copy of `labels` where the third-ventricle part of label 4 is relabelled 6.

    Pre-specified method (protocol §5.4): erode label 4 once with the 6-neighbourhood, which cuts
    the narrow interventricular foramina; the eroded component that is midline and narrow (centroid
    |x| < 2 mm, centroid z < 20 mm, > 200 voxels, every voxel within |x| <= 10 mm) is the
    third-ventricle seed, every other eroded component is a
    lateral-ventricle seed; each label-4 voxel then takes the class of its nearest seed voxel
    (Euclidean). An approximation of the anatomy, reported as such.
    """
    v = labels == VENT
    eroded = ndi.binary_erosion(v, structure=ndi.generate_binary_structure(3, 1))
    comp, n = ndi.label(eroded, structure=ndi.generate_binary_structure(3, 1))
    if n == 0:
        raise ValueError("label 4 vanished after one erosion")
    idx = np.arange(1, n + 1)
    centroids_vox = np.array(ndi.center_of_mass(eroded, comp, idx))
    centroids_mm = (affine[:3, :3] @ centroids_vox.T).T + affine[:3, 3]
    sizes = ndi.sum(eroded, comp, idx)
    objs = ndi.find_objects(comp)
    half_width = []
    for sl in objs:   # world |x| extent of each component's bounding box
        corners = np.array([[sl[0].start, sl[1].start, sl[2].start], [sl[0].stop - 1, sl[1].stop - 1, sl[2].stop - 1]])
        xs = (affine[:3, :3] @ corners.T).T[:, 0] + affine[0, 3]
        half_width.append(float(np.abs(xs).max()))
    third = [i for i, c, s, hw in zip(idx, centroids_mm, sizes, half_width)
             if abs(c[0]) < 2.0 and c[2] < 20.0 and s > 200 and hw <= 10.0]
    lateral_ids = [i for i in idx if i not in third]
    if len(third) != 1:
        raise ValueError(f"expected one midline third-ventricle seed, found {len(third)}")
    seeds = np.zeros(labels.shape, dtype=np.int8)
    seeds[np.isin(comp, lateral_ids)] = 1
    seeds[comp == third[0]] = 2
    _, inds = ndi.distance_transform_edt(seeds == 0, return_indices=True)
    nearest = seeds[tuple(inds)]
    out = labels.copy()
    out[v & (nearest == 2)] = THIRD_VENT
    third_mask = out == THIRD_VENT
    coords_mm = (affine[:3, :3] @ np.argwhere(third_mask).T).T + affine[:3, 3]
    info = {
        "label4_voxels": int(v.sum()),
        "third_ventricle_voxels": int(third_mask.sum()),
        "lateral_ventricle_voxels": int((out == VENT).sum()),
        "third_ventricle_bbox_mm": {
            "x": [float(coords_mm[:, 0].min()), float(coords_mm[:, 0].max())],
            "y": [float(coords_mm[:, 1].min()), float(coords_mm[:, 1].max())],
            "z": [float(coords_mm[:, 2].min()), float(coords_mm[:, 2].max())],
        },
        "eroded_components": int(n),
    }
    return out, info


def ventricle_variant(split_labels: np.ndarray, ventricles: str) -> np.ndarray:
    """MSMask label map with the original 5 labels. 'all' = original (third ventricle stays a
    ventricle, as shipped); 'lateral' = third ventricle relabelled CSF (Filippi 2019: the
    periventricular region abuts the LATERAL ventricles)."""
    out = split_labels.copy()
    if ventricles == "all":
        out[out == THIRD_VENT] = VENT
    elif ventricles == "lateral":
        out[out == THIRD_VENT] = CSF
    else:
        raise ValueError(ventricles)
    return out


def device_zone_map(labels: np.ndarray, mode: str = "contact",
                    d_pv: float = 3.0, d_jc: float = 4.0, d_it: float = 3.0) -> np.ndarray:
    """Zone map (0 none, 1 PV, 2 JC, 3 IT, 4 DWM) built exactly as the device builds it from the
    MSMask labels (ms_region_classifier.generate_zone_map_atlas, steps 2-4), on whatever 1 mm grid
    `labels` is on.

    mode='contact'  : the device (3x3x3 dilation of ventricles, cortex and infratentorial).
    mode='distance' : the 3 / 4 / 3 mm thresholds that the device's IFU stated until CAPA-006
                      (Euclidean distance <= d mm on the 1 mm grid instead of the 3x3x3 dilation).
    """
    ventricles = labels == VENT
    cortex = labels == GM
    wm = labels == WM
    infratentorial = labels == INFRA
    if mode == "contact":
        ventricles_d = ndi.binary_dilation(ventricles, structure=CUBE)
        cortex_d = ndi.binary_dilation(cortex, structure=CUBE)
        infra_d = ndi.binary_dilation(infratentorial, structure=CUBE)
    elif mode == "distance":
        ventricles_d = ndi.distance_transform_edt(~ventricles) <= d_pv
        cortex_d = ndi.distance_transform_edt(~cortex) <= d_jc
        infra_d = ndi.distance_transform_edt(~infratentorial) <= d_it
    else:
        raise ValueError(mode)
    zone = np.zeros(labels.shape, dtype=np.uint8)
    zone[wm] = 4
    zone[infratentorial] = 3
    zone[infra_d & wm] = 3
    zone[cortex_d & wm & (zone != 3)] = 2
    zone[ventricles_d & wm & (zone != 3)] = 1
    return zone


def resample_nearest(src: np.ndarray, src_affine: np.ndarray, target_shape, target_affine,
                     cval: int = 0) -> np.ndarray:
    """Nearest-neighbour resampling of an atlas-space map onto a target grid, world coordinates
    (what the device does with nilearn.image.resample_to_img(interpolation='nearest'))."""
    vox_map = np.linalg.inv(src_affine) @ np.asarray(target_affine, dtype=float)
    out = ndi.affine_transform(src, vox_map[:3, :3], offset=vox_map[:3, 3],
                               output_shape=tuple(target_shape[:3]), order=0, mode="constant",
                               cval=cval, prefilter=False)
    return out.astype(src.dtype, copy=False)


# Residual misregistration level G2 (protocol §5.5): one seeded random rigid + isotropic-scale
# perturbation per scan, rotation <= 2 deg about a random axis, scale within +-2 %, translation
# within +-2 mm per axis, about the MNI brain centre.
G2_MAX_ROT_DEG, G2_MAX_SCALE, G2_MAX_SHIFT_MM = 2.0, 0.02, 2.0
MNI_BRAIN_CENTRE = np.array([0.0, -18.0, 18.0])


def perturbation_matrix(seed: int) -> np.ndarray:
    from scipy.spatial.transform import Rotation
    rng = np.random.default_rng(seed)
    axis = rng.normal(size=3)
    axis /= np.linalg.norm(axis)
    R = Rotation.from_rotvec(np.deg2rad(rng.uniform(-G2_MAX_ROT_DEG, G2_MAX_ROT_DEG)) * axis).as_matrix()
    s = 1.0 + rng.uniform(-G2_MAX_SCALE, G2_MAX_SCALE)
    t = rng.uniform(-G2_MAX_SHIFT_MM, G2_MAX_SHIFT_MM, size=3)
    P = np.eye(4)
    P[:3, :3] = R * s
    P[:3, 3] = MNI_BRAIN_CENTRE + t - (R * s) @ MNI_BRAIN_CENTRE
    return P


def case_seed(case: str, base: int = 20261021) -> int:
    import zlib
    return (base + zlib.crc32(case.encode())) % (2 ** 32)
