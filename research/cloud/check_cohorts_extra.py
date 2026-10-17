#!/usr/bin/env python3
"""Local sanity check of research/cloud/cohorts_extra.py on ONE case per cohort.

For each cohort: fetch one case (minimal download), then check that FLAIR and lesion mask share
shape and affine, that the mask is binary and non-empty, that the voxel sizes and orientation are
plausible and that lesions are brighter than their surroundings (a misaligned mask is not). Saves
a PNG overlay per cohort and ``summary.json`` into --outdir for a human to eyeball.

    python research/cloud/check_cohorts_extra.py --workdir /tmp/cx --outdir docs/research/records/cohorts_extra_check
    (add --hdbet to also run HD-BET on the cases that need skull stripping; add --cleanup to delete --workdir)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import nibabel as nib  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cohorts_extra as cx  # noqa: E402

RED = ListedColormap(["red"])
DEFAULT_IDS = {"ms3seg": ["001"], "muslim": ["1"], "pedims": ["P1_T1"]}


def check_case(case, hdbet_brain=None) -> dict:
    cid, fp, mp, strip = case
    fi, mi = nib.load(fp), nib.load(mp)
    f = fi.get_fdata(dtype=np.float32)
    m_raw = np.asarray(mi.dataobj)
    m = m_raw > 0
    zooms = [float(z) for z in fi.header.get_zooms()[:3]]
    codes = "".join(nib.aff2axcodes(fi.affine))
    r = {
        "case_id": cid, "flair": os.path.basename(fp), "mask": os.path.basename(mp), "needs_skull_strip": strip,
        "shape": list(fi.shape), "zooms_mm": [round(z, 4) for z in zooms], "axcodes": codes,
        "same_shape": fi.shape == mi.shape,
        "same_affine": bool(np.array_equal(fi.affine, mi.affine)),
        "mask_binary": bool(set(np.unique(m_raw).tolist()) <= {0, 1}),
        "mask_dtype": str(m_raw.dtype),
        "lesion_voxels": int(m.sum()),
        "lesion_ml": round(float(m.sum()) * float(np.prod(zooms)) / 1000.0, 3),
    }
    thick_axis = int(np.argmax(zooms))
    r["inplane_zooms_plausible"] = all(0.25 <= zooms[a] <= 1.3 for a in range(3) if a != thick_axis)
    r["slice_spacing_plausible"] = 0.4 <= zooms[thick_axis] <= 10.0
    # lesion vs. surrounding in-plane ring (hyperintense if aligned)
    r.update({k: v for k, v in cx._qc(f, m, zooms, thick_axis).items() if k.startswith("lesion_to_ring")})
    # orientation plausibility in LAS (axial acquisitions): head/brain longer antero-posteriorly
    # (axis1) than left-right (axis0)
    if codes == "LAS" and thick_axis == 2:
        ext = cx._head_extents(f, 2)
        r["extent_lr_mm"] = round(ext[0][0] * zooms[0], 1)
        r["extent_ap_mm"] = round(ext[1][0] * zooms[1], 1)
        r["ap_longer_than_lr"] = r["extent_ap_mm"] > r["extent_lr_mm"]
    if hdbet_brain:
        b = nib.load(hdbet_brain)
        bm = np.asarray(b.dataobj) != 0
        r["hdbet_same_affine"] = bool(np.allclose(b.affine, fi.affine, atol=1e-5))
        r["hdbet_brain_fraction"] = round(float(bm.mean()), 4)
        r["hdbet_lesion_outside_brain_frac"] = round(float((m & ~bm).sum()) / max(1, int(m.sum())), 4)
    r["pass"] = bool(r["same_shape"] and r["same_affine"] and r["mask_binary"] and r["lesion_voxels"] > 0
                     and r["inplane_zooms_plausible"] and r["slice_spacing_plausible"]
                     and (r.get("lesion_to_ring_median_ratio") or 0) > 1.0 and r.get("ap_longer_than_lr", True))
    return r


def overlay_png(case, out_png, title, hdbet_brain=None):
    cid, fp, mp, _ = case
    fi = nib.load(fp)
    f = fi.get_fdata(dtype=np.float32)
    m = np.asarray(nib.load(mp).dataobj) > 0
    zx, zy, zz = [float(z) for z in fi.header.get_zooms()[:3]]
    b = (np.asarray(nib.load(hdbet_brain).dataobj) != 0) if hdbet_brain else None
    ks = np.argsort(m.sum(axis=(0, 1)))[::-1][:5]
    ks = sorted(int(k) for k in ks if m[:, :, k].any()) or [f.shape[2] // 2]
    pos = f[f > 0]
    lo, hi = (np.percentile(pos, [1, 99.5]) if pos.size else (0, 1))
    ncol = len(ks) + 1
    fig, axs = plt.subplots(2, ncol, figsize=(3.0 * ncol, 6.4))
    for j, k in enumerate(ks):
        for row in range(2):
            ax = axs[row, j]
            ax.imshow(f[:, :, k].T, cmap="gray", origin="lower", vmin=lo, vmax=hi, aspect=zy / zx)
            if row == 1:
                ov = np.ma.masked_where(~m[:, :, k].T, m[:, :, k].T)
                ax.imshow(ov, cmap=RED, origin="lower", alpha=0.55, aspect=zy / zx, vmin=0, vmax=1)
                if b is not None:
                    ax.contour(b[:, :, k].T.astype(float), levels=[0.5], colors="c", linewidths=0.6, origin="lower")
            ax.set_title(f"axial k={k}" + (" + lesion" if row else ""), fontsize=8)
            ax.set_xticks([])
            ax.set_yticks([])
    # coronal reformat through the lesion-richest coronal plane (superior up), true aspect
    j = int(np.argmax(m.sum(axis=(0, 2)))) if m.any() else f.shape[1] // 2
    for row in range(2):
        ax = axs[row, -1]
        ax.imshow(f[:, j, :].T, cmap="gray", origin="lower", vmin=lo, vmax=hi, aspect=zz / zx)
        if row == 1:
            ov = np.ma.masked_where(~m[:, j, :].T, m[:, j, :].T)
            ax.imshow(ov, cmap=RED, origin="lower", alpha=0.55, aspect=zz / zx, vmin=0, vmax=1)
        ax.set_title(f"coronal reformat y={j}", fontsize=8)
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle(f"{title}\n{cid}  shape={fi.shape}  voxel={zx:.3f}x{zy:.3f}x{zz:.2f} mm  "
                 f"{''.join(nib.aff2axcodes(fi.affine))} (display: patient left on the right = radiological, "
                 f"anterior up; red = lesion mask" + ("; cyan = HD-BET brain" if b is not None else "") + ")",
                 fontsize=9)
    plt.tight_layout()
    plt.savefig(out_png, dpi=80)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--cohorts", nargs="*", default=["ms3seg", "muslim", "pedims"])
    ap.add_argument("--hdbet", action="store_true", help="also run HD-BET on cases that need skull stripping")
    ap.add_argument("--cleanup", action="store_true", help="delete --workdir at the end")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    titles = {"ms3seg": "MS3SEG (Toshiba 1.5T, Tabriz) - native FLAIR with skull, abWMH lesion mask",
              "muslim": "Muslim et al. 2022 (Baghdad 1.5T) - reoriented to LAS, in-plane spacing ESTIMATED",
              "pedims": "PediMS (Siemens Skyra 3T, pediatric) - SynthStrip brain FLAIR, consensus mask"}
    summary = []
    for name in a.cohorts:
        cases = cx.FETCHERS[name](a.workdir, ids=DEFAULT_IDS[name])
        if not cases:
            summary.append({"cohort": name, "error": "no case fetched"})
            continue
        case = cases[0]
        brain = None
        if a.hdbet and case[3]:
            done = cx.hdbet_strip({case[0]: case[1]}, os.path.join(a.workdir, "hdbet"), gts={case[0]: case[2]})
            brain = done.get(case[0])
        r = check_case(case, brain)
        r["cohort"] = name
        summary.append(r)
        overlay_png(case, os.path.join(a.outdir, f"{name}_{case[0]}.png"), titles[name], brain)
        print(json.dumps(r))
    with open(os.path.join(a.outdir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    if a.cleanup:
        shutil.rmtree(a.workdir, ignore_errors=True)
    ok = all(s.get("pass") for s in summary)
    print("ALL PASS" if ok else "SOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
