"""Lesion-detector v3 — per-candidate feature families (pre-registered in
docs/research/lesion-detector-v3/PROTOCOL.md §5).

Every function here works WITHOUT ground truth: inputs are the base model's probability map, the
candidate labelling, and (optionally) co-registered images / extra probability maps. Ground truth
only ever produces labels, in build_features.py. A unit test pins that no public function in this
module accepts a GT argument.

Families (NEW in v3 unless stated):
  v2 (carried, NOT new) ... prob moments + morphology + MNI location, from the shipped
                            app.services.calm_ms_lesion_features module
  F1 FLAIR contrast vs NAWM shell (per-scan robust z)
  F2 T1 contrast (exploratory)
  F3 FLAIR texture
  F4 boundary sharpness (FLAIR + probability map)
  F5 multi-threshold persistence (probability map only)
  F6 scale-normalised, MNI-free location proxies (depth / ventricle / CSF contact)
  F7 scan context (exploratory)
  F8 ensemble disagreement across FLAMeS folds      (placeholder: needs per-fold maps)
  F9 independent-model agreement with LST-AI        (placeholder: needs LST-AI maps)

Conventions: arrays are (X, Y, Z) NIfTI voxel order at 1 mm isotropic spacing (the cohorts used are
1 mm; spacing is asserted by the caller). 18-connectivity everywhere a component is formed.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage as ndi
from scipy import stats

CONN18 = ndi.generate_binary_structure(3, 2)
CSF_Z = -2.0            # CSF-like threshold on the per-scan robust z (FLAIR suppresses fluid)
SHELL_P_MAX = 0.1       # shell voxels must have base-model probability below this
SHELL_MIN_VOX = 10
REF_P_MAX = 0.05        # reference tissue for the per-scan z: brain voxels with P < 0.05
SD_FLOOR = 0.25
MARGIN = 8              # crop margin (D6 dilation + 1 for central differences + slack)

F1 = ("fl_z_mean", "fl_z_median", "fl_shell_z_mean", "fl_shell_z_std", "fl_contrast", "fl_cnr",
      "fl_frac_hyper", "fl_shell_valid_frac")
F2 = ("t1_contrast", "t1_frac_hypo")
F3 = ("fl_tex_std", "fl_tex_iqr", "fl_tex_skew", "fl_tex_kurt", "fl_tex_entropy", "fl_tex_grad_interior")
F4_FLAIR = ("fl_grad_boundary", "fl_grad_ratio", "fl_edge_step")
F4_PROB = ("pm_grad_boundary", "pm_ring1_mean", "pm_ring3_mean")
F5 = ("ps_surv_075", "ps_surv_090", "ps_nsplit_075", "ps_nsplit_090", "ps_log_merge_025",
      "ps_log_merge_010", "ps_nmerge_025")
F6 = ("loc_depth_min_rel", "loc_depth_mean_rel", "loc_dvent_min_rel", "loc_csf_contact",
      "loc_outside_contact", "loc_log_rel_volume")
F7 = ("ctx_log_ncand", "ctx_log_totvol", "ctx_rank_prob")
F8 = ("ens_mean", "ens_std", "ens_frac_detect", "ens_voxvar_mean", "ens_mi")
F9 = ("lst_mean", "lst_max", "lst_frac_ge05", "lst_detect", "lst_local_dice")

FAMILIES = {"F1": F1, "F2": F2, "F3": F3, "F4_FLAIR": F4_FLAIR, "F4_PROB": F4_PROB, "F5": F5,
            "F6": F6, "F7": F7, "F8": F8, "F9": F9}
NEW_FEATURE_NAMES = F1 + F2 + F3 + F4_FLAIR + F4_PROB + F5 + F6 + F7 + F8 + F9


# ------------------------------------------------------------------ per-scan context
def brain_mask(flair: np.ndarray) -> np.ndarray:
    """Largest 6-connected component of fill_holes(FLAIR > 0) (skull-stripped inputs)."""
    b = ndi.binary_fill_holes(flair > 0)
    lab, n = ndi.label(b)
    if n == 0:
        raise ValueError("empty brain mask")
    sizes = np.bincount(lab.ravel())
    sizes[0] = 0
    return lab == int(np.argmax(sizes))


def robust_z(img: np.ndarray, ref: np.ndarray) -> np.ndarray:
    """(img - median(img[ref])) / (1.4826 MAD(img[ref])) as float32."""
    v = img[ref].astype(np.float64)
    if v.size < 1000:
        raise ValueError("too few reference voxels for the per-scan z-score")
    med = float(np.median(v))
    mad = 1.4826 * float(np.median(np.abs(v - med)))
    if not mad > 0:
        raise ValueError("degenerate reference intensity spread")
    return ((img - med) / mad).astype(np.float32)


class ScanContext:
    """Image-derived, GT-free per-scan quantities shared by all candidates of one scan."""

    def __init__(self, prob: np.ndarray, flair: np.ndarray | None = None, t1: np.ndarray | None = None):
        self.prob = prob
        self.has_flair = flair is not None
        self.has_t1 = t1 is not None and flair is not None
        # multi-threshold components of the probability map (F5)
        self.lab025, _ = ndi.label(prob >= 0.25, structure=CONN18)
        self.lab010, _ = ndi.label(prob >= 0.10, structure=CONN18)
        self.size025 = np.bincount(self.lab025.ravel())
        self.size010 = np.bincount(self.lab010.ravel())
        if not self.has_flair:
            return
        if flair.shape != prob.shape:
            raise ValueError(f"FLAIR grid {flair.shape} != prob grid {prob.shape}")
        self.brain = brain_mask(flair)
        ref = self.brain & (prob < REF_P_MAX)
        self.z = robust_z(flair, ref)
        self.csf = self.brain & (self.z < CSF_Z)
        depth = ndi.distance_transform_edt(self.brain).astype(np.float32)
        self.depth = depth
        self.dmax = float(depth.max())
        self.brain_vox = int(self.brain.sum())
        self.r_b = float((3.0 * self.brain_vox / (4.0 * np.pi)) ** (1.0 / 3.0))
        deep_csf = self.csf & (depth >= 0.25 * self.dmax)
        lab, n = ndi.label(deep_csf, structure=CONN18)
        if n:
            sizes = np.bincount(lab.ravel())
            sizes[0] = 0
            keep = np.nonzero(sizes >= 0.25 * sizes.max())[0]
            vent = np.isin(lab, keep)
            self.vent_vox = int(vent.sum())
            self.dvent = ndi.distance_transform_edt(~vent).astype(np.float32)
        else:
            self.vent_vox = 0
            self.dvent = None
        self.t1_status = "absent"
        if self.has_t1:
            if t1.shape != prob.shape:
                raise ValueError(f"T1 grid {t1.shape} != prob grid {prob.shape}")
            # T1 feeds only the EXPLORATORY family F2: a broken T1 (e.g. MSLesSeg P49_T2 ships an
            # almost empty T1) disables F2 for that scan instead of aborting (PROTOCOL §11 D3).
            coverage = float((t1[self.brain] != 0).mean())
            try:
                if coverage < 0.5:
                    raise ValueError("T1 covers < 50 % of the FLAIR brain mask")
                self.zt1 = robust_z(t1, ref)
                self.t1_status = "ok"
            except ValueError as e:
                self.has_t1 = False
                self.t1_status = f"disabled: {e} (coverage {coverage:.3f})"

    def summary(self) -> dict:
        out = {"has_flair": self.has_flair, "has_t1": self.has_t1, "t1_status": self.t1_status}
        if self.has_flair:
            out.update({"brain_vox": self.brain_vox, "dmax_mm": round(self.dmax, 2),
                        "r_b_mm": round(self.r_b, 2), "ventricle_proxy_vox": self.vent_vox,
                        "csf_frac": round(float(self.csf.sum()) / self.brain_vox, 4)})
        return out


# ------------------------------------------------------------------ helpers
def _crop(sl, shape, margin=MARGIN):
    return tuple(slice(max(s.start - margin, 0), min(s.stop + margin, n)) for s, n in zip(sl, shape))


def _mean(a):
    return float(a.mean()) if a.size else np.nan


def _grad_mag(vol):
    g = np.gradient(vol.astype(np.float32))
    return np.sqrt(g[0] ** 2 + g[1] ** 2 + g[2] ** 2)


def _hist_entropy(v, width=0.5):
    if v.size == 0:
        return np.nan
    lo, hi = np.floor(v.min() / width) * width, np.ceil(v.max() / width) * width + width
    h, _ = np.histogram(v, bins=np.arange(lo, hi + 1e-9, width))
    p = h[h > 0] / v.size
    return float(-(p * np.log(p)).sum())


def _bin_entropy(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return -(p * np.log(p) + (1 - p) * np.log(1 - p))


# ------------------------------------------------------------------ main entry
def candidate_features_v3(prob, labeled, cands, ctx: ScanContext,
                          fold_maps=None, lstai=None) -> dict:
    """Dict name -> float array (len(cands)) for every NEW family whose inputs are available.

    prob: base-model probability map; labeled/cands: from extract_lesion_candidates on `prob`;
    ctx: ScanContext of the same scan; fold_maps: optional list of K >= 2 per-fold probability maps
    (F8); lstai: optional LST-AI probability map on the same grid (F9). No ground truth.
    """
    n = len(cands)
    objs = ndi.find_objects(labeled)
    out = {k: np.full(n, np.nan) for k in F4_PROB + F5 + F7}
    if ctx.has_flair:
        for k in F1 + F3 + F4_FLAIR + F6:
            out[k] = np.full(n, np.nan)
    if ctx.has_t1:
        for k in F2:
            out[k] = np.full(n, np.nan)
    if fold_maps is not None:
        if len(fold_maps) < 2:
            raise ValueError("ensemble features need >= 2 fold maps")
        for fm in fold_maps:
            if fm.shape != prob.shape:
                raise ValueError("fold map grid mismatch")
        for k in F8:
            out[k] = np.full(n, np.nan)
    if lstai is not None:
        if lstai.shape != prob.shape:
            raise ValueError("LST-AI map grid mismatch")
        lst_lab, _ = ndi.label(lstai >= 0.5, structure=CONN18)
        lst_size = np.bincount(lst_lab.ravel())
        for k in F9:
            out[k] = np.full(n, np.nan)

    # F5 merge bookkeeping: 0.25-component of every candidate
    comp025 = []
    for c in cands:
        sl = objs[c.label - 1]
        m = labeled[sl] == c.label
        comp025.append(int(ctx.lab025[sl][m][0]))
    comp025 = np.asarray(comp025)

    vols = np.array([c.n_voxels for c in cands], float)
    pm = np.array([c.score for c in cands], float)
    ranks = stats.rankdata(pm) if n else np.zeros(0)

    for i, c in enumerate(cands):
        sl = _crop(objs[c.label - 1], prob.shape)
        C = labeled[sl] == c.label
        P = prob[sl]
        nC = int(C.sum())
        # rings (18-connected dilation steps)
        D = [C]
        for _ in range(6):
            D.append(ndi.binary_dilation(D[-1], structure=CONN18))
        ring1 = D[1] & ~C
        ring2 = D[2] & ~C
        ring3 = D[3] & ~D[1]
        inner = C & ~ndi.binary_erosion(C)
        interior = ndi.binary_erosion(C)
        band = inner | ring1

        # ---- F4 (probability map) + F5
        gp = _grad_mag(P)
        out["pm_grad_boundary"][i] = _mean(gp[band])
        out["pm_ring1_mean"][i] = _mean(P[ring1])
        out["pm_ring3_mean"][i] = _mean(P[ring3])
        pc = P[C]
        for t, key_s, key_n in ((0.75, "ps_surv_075", "ps_nsplit_075"), (0.90, "ps_surv_090", "ps_nsplit_090")):
            out[key_s][i] = float((pc >= t).mean())
            out[key_n][i] = float(ndi.label(C & (P >= t), structure=CONN18)[1])
        out["ps_log_merge_025"][i] = float(np.log(ctx.size025[comp025[i]] / nC))
        c010 = int(ctx.lab010[sl][C][0])
        out["ps_log_merge_010"][i] = float(np.log(ctx.size010[c010] / nC))
        out["ps_nmerge_025"][i] = float((comp025 == comp025[i]).sum() - 1)

        # ---- F7 scan context (exploratory)
        out["ctx_log_ncand"][i] = float(np.log1p(n))
        out["ctx_log_totvol"][i] = float(np.log1p(vols.sum()))
        out["ctx_rank_prob"][i] = float((ranks[i] - 1) / (n - 1)) if n > 1 else 0.5

        if ctx.has_flair:
            B = ctx.brain[sl]
            Z = ctx.z[sl]
            CSF = ctx.csf[sl]
            zc = Z[C]
            # ---- F1 contrast vs NAWM shell
            geo = D[4] & ~D[1]
            shell = geo & B & (P < SHELL_P_MAX) & ~CSF
            if shell.sum() < SHELL_MIN_VOX:
                geo = D[6] & ~D[1]
                shell = geo & B & (P < SHELL_P_MAX) & ~CSF
            out["fl_z_mean"][i] = float(zc.mean())
            out["fl_z_median"][i] = float(np.median(zc))
            out["fl_shell_valid_frac"][i] = float(shell.sum() / max(int(geo.sum()), 1))
            if shell.sum() >= SHELL_MIN_VOX:
                zs = Z[shell]
                smu, ssd = float(zs.mean()), float(zs.std())
                out["fl_shell_z_mean"][i] = smu
                out["fl_shell_z_std"][i] = ssd
                out["fl_contrast"][i] = float(zc.mean()) - smu
                out["fl_cnr"][i] = (float(zc.mean()) - smu) / max(ssd, SD_FLOOR)
                out["fl_frac_hyper"][i] = float((zc > smu + 2.0 * max(ssd, SD_FLOOR)).mean())
                if ctx.has_t1:
                    T = ctx.zt1[sl]
                    ts = T[shell]
                    tmu, tsd = float(ts.mean()), float(ts.std())
                    out["t1_contrast"][i] = float(T[C].mean()) - tmu
                    out["t1_frac_hypo"][i] = float((T[C] < tmu - 2.0 * max(tsd, SD_FLOOR)).mean())
            # ---- F3 texture
            out["fl_tex_std"][i] = float(zc.std())
            q75, q25 = np.percentile(zc, [75, 25])
            out["fl_tex_iqr"][i] = float(q75 - q25)
            if nC >= 3 and zc.std() > 0:
                out["fl_tex_skew"][i] = float(stats.skew(zc))
                out["fl_tex_kurt"][i] = float(stats.kurtosis(zc))
            out["fl_tex_entropy"][i] = _hist_entropy(zc)
            gz = _grad_mag(Z)
            gint = _mean(gz[interior]) if interior.any() else np.nan
            out["fl_tex_grad_interior"][i] = gint
            # ---- F4 FLAIR boundary
            bandB = band & B
            gb = _mean(gz[bandB])
            out["fl_grad_boundary"][i] = gb
            out["fl_grad_ratio"][i] = gb / (gint + 0.1) if np.isfinite(gint) else np.nan
            r1B = ring1 & B
            out["fl_edge_step"][i] = (_mean(Z[inner]) - _mean(Z[r1B])) if r1B.any() else np.nan
            # ---- F6 location proxies
            dep = ctx.depth[sl][C]
            out["loc_depth_min_rel"][i] = float(dep.min()) / ctx.dmax
            out["loc_depth_mean_rel"][i] = float(dep.mean()) / ctx.dmax
            if ctx.dvent is not None:
                out["loc_dvent_min_rel"][i] = float(ctx.dvent[sl][C].min()) / ctx.r_b
            r2B = ring2 & B
            out["loc_csf_contact"][i] = float(CSF[r2B].mean()) if r2B.any() else np.nan
            out["loc_outside_contact"][i] = float((~B[ring2]).mean()) if ring2.any() else np.nan
            out["loc_log_rel_volume"][i] = float(np.log(nC / ctx.brain_vox))

        # ---- F8 ensemble disagreement (placeholder family)
        if fold_maps is not None:
            stack = np.stack([fm[sl][C] for fm in fold_maps]).astype(np.float64)   # K x nC
            means = stack.mean(axis=1)
            out["ens_mean"][i] = float(means.mean())
            out["ens_std"][i] = float(means.std())
            out["ens_frac_detect"][i] = float(((stack >= 0.5).mean(axis=1) >= 0.5).mean())
            out["ens_voxvar_mean"][i] = float(stack.var(axis=0).mean())
            pbar = stack.mean(axis=0)
            out["ens_mi"][i] = float((_bin_entropy(pbar) - _bin_entropy(stack).mean(axis=0)).mean())

        # ---- F9 LST-AI agreement (placeholder family)
        if lstai is not None:
            q = lstai[sl][C]
            out["lst_mean"][i] = float(q.mean())
            out["lst_max"][i] = float(q.max())
            out["lst_frac_ge05"][i] = float((q >= 0.5).mean())
            ids = np.unique(lst_lab[sl][C])
            ids = [int(k) for k in ids if k > 0 and lst_size[k] >= 3]
            out["lst_detect"][i] = 1.0 if ids else 0.0
            if ids:
                u = int(sum(lst_size[k] for k in ids))
                inter = int(np.isin(lst_lab[sl][C], ids).sum())
                out["lst_local_dice"][i] = 2.0 * inter / (nC + u)
            else:
                out["lst_local_dice"][i] = 0.0
    return out
