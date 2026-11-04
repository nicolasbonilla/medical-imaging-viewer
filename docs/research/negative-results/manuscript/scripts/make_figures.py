#!/usr/bin/env python3
"""Make every manuscript figure from ``../data/extracted_results.json`` (written by extract_results.py).

No number is computed here except what is drawn: point estimates and confidence intervals are taken
from the records as stored (Figure 2 also draws the per-scan values those means are made of, and asserts
that they reproduce the stored means). Style: the MSTool-AI house style (``../figures/mstool_figstyle.py``
and ``mstool.mplstyle``): Arial, final size 180 mm, white ground, thin axes, notes in the captions.
Colour: muted, colour-blind-safe house palette (checked for deuteranopia, protanopia and tritanopia); FLAMeS
ensemble dark grey and fold 0 mid grey as in every MSTool-AI paper, LST-AI mauve, every series with its own
marker. Output: ``../figures/fig*.pdf`` (vector, TrueType embedded) and ``.png`` (600 dpi).
"""
from __future__ import annotations

import json
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data" / "extracted_results.json"
FIG = HERE.parent / "figures"
sys.path.insert(0, str(FIG))
import mstool_figstyle as fs  # noqa: E402

fs.use()
import matplotlib.dates as mdates  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402


def fmt(x: float, nd: int = 3, sign: bool = False) -> str:
    """Round half-up on the stored decimal value (as the text reports it), with a real minus sign."""
    return fs.fnum(x, nd, sign=sign, half_up=True)


ARM = {  # arm -> (short, long label, colour, marker)
    "R": ("R", "Original FLAMeS fold 0", fs.FLAMES_FOLD0, "o"),
    "E": ("E", "Original 5-fold ensemble (context)", fs.FLAMES, "^"),
    "A": ("A", "Fine-tuned + thick-slice augmentation", fs.PRIMARY, "s"),
    "B": ("B", "Fine-tuned, no augmentation (control)", fs.OCHRE, "D"),
}
ARMS = ("R", "E", "A", "B")


def save(fig, name: str) -> None:
    fs.save(fig, str(FIG / name))


def arm_key(fig, x_mm: float, y_mm: float, arms=ARMS, col_w: float = 64.0, row_h: float = 3.7) -> None:
    """Two-column key of the four arms (R, E | A, B)."""
    for i, a in enumerate(arms):
        c, r = divmod(i, 2)
        x, y = x_mm + c * col_w, y_mm + r * row_h
        short, lab, col, mk = ARM[a]
        fig.lines.append(Line2D([fs.fx(fig, x + 1.4)], [fs.fy(fig, y)], transform=fig.transFigure, marker=mk,
                                color=col, mec="white", mew=0.5, ms=4.8, ls="none"))
        fs.text_mm(fig, x + 3.4, y, f"{short}  {lab}", va="center", fontsize=7)


# ---------------------------------------------------------------------------- figure 1
def _forest(fig, top, rows, x_ax, w_ax, xlim, ticks, ticklabels, refs, xlabel, nd, signed, row_mm, label_rows=True):
    """rows: (code, label, indent, point, (lo, hi) or None, colour, marker). Returns the table end (mm)."""
    n = len(rows)
    ax = fs.axes(fig, x_ax, top, w_ax, n * row_mm)
    ax.set_ylim(n - 0.5, -0.5)
    ymm = lambda i: top + (i + 0.5) * row_mm  # noqa: E731
    for x, ls in refs:
        fs.ref_vline(ax, x, color=fs.AXIS if ls == "-" else fs.INK2, lw=0.5, ls=ls)
    cells = []
    for i, (code, lab, ind, pt, ci, col, mk) in enumerate(rows):
        if ci is not None:
            ax.plot(ci, [i, i], color=col, lw=fs.LW_CI, zorder=2)
        ax.plot(pt, i, marker=mk, color=col, ms=4.6, mec="white", mew=0.5, ls="none", zorder=3)
        if label_rows:
            if code:
                fs.text_mm(fig, 0, ymm(i), code, va="center", fontsize=7, fontweight="bold")
            fs.text_mm(fig, 7.0 + 2.0 * ind, ymm(i), lab, va="center", fontsize=7)
        cells.append((pt, ci))
    ax.set_xlim(*xlim)
    ax.set_xticks(ticks)
    ax.set_xticklabels(ticklabels)
    ax.set_yticks([])
    fs.despine(ax, left=False)
    ax.set_xlabel(xlabel)
    neg = any(v < 0 for _, ci in cells if ci for v in ci)
    sep = " to " if neg else "–"
    txt = []
    for pt, ci in cells:
        if ci is None:
            txt.append([fmt(pt, nd, signed), "", "", ""])
        else:
            txt.append([fmt(pt, nd, signed), "(" + fmt(ci[0], nd, signed), sep.strip(), fmt(ci[1], nd, signed) + ")"])
    cols = [[c for c in col if c] or [""] for col in zip(*txt)]
    anchors, end = fs.table_layout(fig, x_ax + w_ax + 2.5, cols, "ddcd",
                                   [1.2, 0.9 if neg else 0.12, 0.9 if neg else 0.12, 0])
    for i, row in enumerate(txt):
        fs.table_row(fig, anchors, "ddcd", ymm(i), row)
    return ax, end


def fig1(d):
    ft = d["flames_thick"]
    A, B, CTX = fs.PRIMARY, fs.OCHRE, fs.INK2

    def r(code, lab, ind, key, col, mk, field="delta_f1"):
        v = ft[key][field]
        return (code, lab, ind, v[0], tuple(v[1]), col, mk)

    def site(lab, s, field):
        v = ft["H1_by_site"][s][field]
        return ("", lab, 1, v[0], tuple(v[1]), A, "s")

    spec = [("H1", "A vs R, pooled thick sites (179 scans)", 0, "H1", A, "s"),
            ("", "MS3SEG (100)", 1, ("ms3seg",), A, "s"),
            ("", "Muslim (51)", 1, ("muslim",), A, "s"),
            ("", "PediMS (28 scans, 9 children)", 1, ("pedims",), A, "s"),
            ("S6", "A vs R, strict matching (IoU ≥ 0.10)", 0, "S6_strict", A, "s"),
            ("S6", "A vs R, without PediMS P9", 0, "S6_without_pedims_P9", A, "s"),
            ("", "B vs R (fine-tuning, no augmentation)", 0, "B_vs_R_thick", B, "D"),
            ("H3", "A vs B (augmentation effect)", 0, "S3_A_vs_B", CTX, "o"),
            ("S4", "A vs E (5-fold ensemble)", 0, "S4_A_vs_E", CTX, "^")]
    f1_rows, fp_rows = [], []
    for code, lab, ind, key, col, mk in spec:
        if isinstance(key, tuple):
            f1_rows.append(site(lab, key[0], "delta_f1"))
            v = ft["H1_by_site"][key[0]]["fp_ratio"]
        else:
            f1_rows.append(r(code, lab, ind, key, col, mk))
            v = ft[key]["fp_ratio"]
        fp_rows.append((code, lab, ind, v[0], tuple(v[1]), col, mk))
    h2 = ft["H2"]
    h2_rows = [("H2", "Pooled 1-mm sites, Δ Dice (32 scans)", 0, h2["delta_dice"][0], tuple(h2["delta_dice"][1]), A, "s"),
               ("", "Pooled 1-mm sites, ΔF1", 0, h2["delta_f1"][0], tuple(h2["delta_f1"][1]), A, "s"),
               ("", "Ljubljana-10 only, Δ Dice (point)", 0, h2["ljubljana_delta_dice"], None, A, "s"),
               ("", "Ljubljana-10 only, ΔF1 (point)", 0, h2["ljubljana_delta_f1"], None, A, "s")]

    row_mm, top = 4.3, 7.5
    top_c = top + len(f1_rows) * row_mm + 21.0
    fig = fs.figure(fs.DOUBLE, top_c + len(h2_rows) * row_mm + 11.0)
    fs.panel_label(fig, "a", 0, 0.4)
    ax1, end1 = _forest(fig, top, f1_rows, 57.0, 27.0, (-0.06, 0.08), [-0.05, 0, 0.05],
                        [fmt(-0.05, 2), "0", fmt(0.05, 2, True)], [(0, "-"), (0.03, (0, (3, 2)))],
                        "ΔF1, A − R (thick sites)", 3, True, row_mm)
    ax1.annotate("SESOI", (0.03, -0.5), xytext=(0, 1.5), textcoords="offset points", ha="center", va="bottom",
                 fontsize=6.5, color=fs.INK2, annotation_clip=False)
    fs.text_mm(fig, 86.5, top - 2.8, "Δ (95% CI)", va="center", fontsize=6.5, color=fs.INK2)
    fs.panel_label(fig, "b", end1 + 3.0, 0.4)
    ax2, end2 = _forest(fig, top, fp_rows, end1 + 6.5, 22.0, (0.5, 1.25), [0.6, 0.8, 1.0, 1.2],
                        ["0.6", "0.8", "1.0", "1.2"], [(1.0, "-"), (1.10, (0, (3, 2)))],
                        "False-lesion ratio", 2, False, row_mm, label_rows=False)
    ax2.annotate("margin", (1.10, -0.5), xytext=(0, 1.5), textcoords="offset points", ha="center", va="bottom",
                 fontsize=6.5, color=fs.INK2, annotation_clip=False)
    fs.text_mm(fig, end1 + 6.5 + 22.0 + 2.5, top - 2.8, "Ratio (95% CI)", va="center", fontsize=6.5, color=fs.INK2)
    fs.panel_label(fig, "c", 0, top_c - 7.0)
    ax3, _ = _forest(fig, top_c, h2_rows, 57.0, 70.0, (-0.25, 0.08), [-0.25, -0.2, -0.15, -0.1, -0.05, 0, 0.05],
                     [fmt(v, 2, v > 0) if v else "0" for v in (-0.25, -0.2, -0.15, -0.1, -0.05, 0, 0.05)],
                     [(0, "-"), (-0.02, (0, (3, 2))), (-0.03, (0, (1, 1.5)))], "Difference, A − R (~1-mm sites)", 3, True,
                     row_mm)
    ax3.annotate("−0.03 F1", (-0.03, -0.5), xytext=(-1.5, 1.5), textcoords="offset points", ha="right", va="bottom",
                 fontsize=6.5, color=fs.INK2, annotation_clip=False)
    ax3.annotate("−0.02 Dice", (-0.02, -0.5), xytext=(1.5, 1.5), textcoords="offset points", ha="left", va="bottom",
                 fontsize=6.5, color=fs.INK2, annotation_clip=False)
    save(fig, "fig1_flames_thick_primary")


# ---------------------------------------------------------------------------- figure 2
def fig2(d):
    ft = d["flames_thick"]
    s2, ps = ft["S2_by_site"], ft["per_scan"]
    sites = [("ms3seg", "MS3SEG", "6.0–8.1 mm"), ("muslim", "Muslim", "4.9–8.3 mm"), ("pedims", "PediMS", "3.9 mm"),
             ("openms", "Ljubljana-10", "3D, ~1 mm"), ("mslesseg", "MSLesSeg test", "in-domain for A, B")]
    metrics = [("f1", "Lesion-wise F1", (0, 1), [0, 0.5, 1.0], ["0", "0.5", "1.0"]),
               ("fp", "False lesions per scan", (0, 62), [0, 20, 40, 60], ["0", "20", "40", "60"]),
               ("dice", "Voxel Dice", (0, 1), [0, 0.5, 1.0], ["0", "0.5", "1.0"]),
               ("sens", "Lesion sensitivity", (0, 1), [0, 0.5, 1.0], ["0", "0.5", "1.0"])]
    # the dots are the scans the stored means are made of: assert it
    per = {s: [r for r in ps if r["site"] == s] for s, _, _ in sites}
    for s, _, _ in sites:
        for a in ARMS:
            for m, *_ in metrics:
                v = [r[a][m] for r in per[s]]
                assert abs(statistics.mean(v) - s2[s][a][m]) < 1e-9, (s, a, m)
    sub_mm, gap_units, top = 2.7, 1.1, 11.5
    ys, y = {}, 0.0
    for k, (s, _, _) in enumerate(sites):
        if k == 3:
            y += 0.9                                             # extra air between thick and ~1-mm sites
        ys[s] = [y + j for j in range(4)]
        y += 4 + gap_units
    n_units = y - gap_units
    plot_h = (n_units + 0.4) * sub_mm
    fig = fs.figure(fs.DOUBLE, top + plot_h + 10.5)
    ymm = lambda v: top + (v + 0.7) * sub_mm  # noqa: E731
    for s, name, sub in sites:
        fs.text_mm(fig, 0, ymm(ys[s][1]), name, va="center", fontsize=7)
        fs.text_mm(fig, 0, ymm(ys[s][2]) + 0.4, sub, va="center", fontsize=6.5, color=fs.INK2)
        for a, yy in zip(ARMS, ys[s]):
            fs.text_mm(fig, 27.5, ymm(yy), a, ha="center", va="center", fontsize=6, color=fs.INK2)
    x0, w, gx = 31.0, 33.0, 4.6
    for k, (m, lab, xlim, ticks, tl) in enumerate(metrics):
        ax = fs.axes(fig, x0 + k * (w + gx), top, w, plot_h)
        ax.set_ylim(n_units - 0.3, -0.7)
        for si, (s, _, _) in enumerate(sites):
            for ai, (a, yy) in enumerate(zip(ARMS, ys[s])):
                short, _, col, mk = ARM[a]
                v = [r[a][m] for r in per[s]]
                ax.scatter(v, yy + fs.jitter(len(v), 0.62, phase=0.29 * si + 0.13 * ai), s=1.1, color=col, alpha=0.32,
                           lw=0, zorder=1, rasterized=True)
                ax.plot(s2[s][a][m], yy, marker=mk, color=col, ms=4.4, mec="white", mew=0.6, ls="none", zorder=3)
        pad = 0.025 * (xlim[1] - xlim[0])
        ax.set_xlim(xlim[0] - pad, xlim[1] + pad)
        ax.spines["bottom"].set_bounds(*xlim)
        ax.set_xticks(ticks)
        ax.set_xticklabels(tl)
        ax.set_yticks([])
        fs.despine(ax, left=False)
        ax.set_xlabel(lab)
    arm_key(fig, 31.0, 1.8)
    save(fig, "fig2_flames_thick_per_site")


# ---------------------------------------------------------------------------- figure 3
def fig3(d):
    s1 = d["flames_thick"]["S1_size"]
    bands = [("B1", "B1  slice spacing ≤ 1.5 mm", "32 scans"), ("B2", "B2  1.5–4.5 mm", "28 scans"),
             ("B3", "B3  4.5–6.5 mm", "76 scans"), ("B4", "B4  > 6.5 mm", "75 scans")]
    bins = ["[3,14)", "[14,50)", "[50,150)", "[150,500)", ">=500"]
    offs = {"R": -0.24, "E": -0.08, "A": 0.08, "B": 0.24}
    fig = fs.figure(fs.DOUBLE, 107)
    L, T, PW, PH, GX, GY = 14.0, 16.0, 77.0, 34.0, 12.0, 15.0
    for k, (b, title, n) in enumerate(bands):
        r_, c_ = divmod(k, 2)
        x0, y0 = L + c_ * (PW + GX), T + r_ * (PH + GY)
        ax = fs.axes(fig, x0, y0, PW, PH)
        fs.panel_label(fig, "abcd"[k], x0 - (13.5 if c_ == 0 else 6.0), y0 - 5.0)
        fs.facet_label(ax, title, fontweight="bold")
        fs.facet_label(ax, n, x=1.0, ha="right", color=fs.INK2)
        for h in (0.5, 0.8):
            fs.ref_hline(ax, h, color=fs.GRID, lw=0.6, zorder=0)
        for a in ARMS:
            short, lab, col, mk = ARM[a]
            rec = {x["bin"]: x for x in s1[f"{b}|{a}"]["bins"]}
            for i, kb in enumerate(bins):
                xx = i + offs[a]
                ax.plot([xx, xx], rec[kb]["ci"], color=col, lw=fs.LW_CI, zorder=2)
                ax.plot(xx, rec[kb]["sens"], marker=mk, color=col, ms=3.9, mec="white", mew=0.45, ls="none", zorder=3)
        ax.set_xticks(range(len(bins)))
        ax.set_xticklabels(["3–14", "14–50", "50–150", "150–500", "≥500"])
        ax.tick_params(axis="x", length=0)
        ax.set_xlim(-0.5, len(bins) - 0.5)
        ax.set_ylim(0, 1.02)
        ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
        ax.set_yticklabels(["0", "0.2", "0.4", "0.6", "0.8", "1.0"] if c_ == 0 else [])
        if r_ == 1:
            ax.set_xlabel("Expert lesion volume (mm³)")
        if c_ == 0:
            ax.set_ylabel("Detection sensitivity")
    arm_key(fig, 14.0, 1.8)
    save(fig, "fig3_flames_thick_size")


# ---------------------------------------------------------------------------- figure 4
def fig4(d):
    v3, v31, v32 = d["v3"], d["v31"], d["v32"]
    LEARN, PROBE = fs.PRIMARY, fs.OCHRE

    def a(rec, key):
        x = rec[key]
        return x["auroc"], tuple(x["ci95"])

    p = v3["primary_pooled_loco"]
    rows_v3 = [("Raw fold-0 probability", *a(p, "RAW"), fs.FLAMES_FOLD0, "o", True),
               ("V3-LR (primary)", *a(p, "V3-LR"), LEARN, "s", True),
               ("V3-GB", *a(p, "V3-GB"), LEARN, "s", True),
               ("V2 as shipped (earlier version)", *a(p, "V2-shipped"), LEARN, "s", True)]
    pe, pm = v31["primary_pooled_external"], v31["posthoc_P1_mean5"]["pooled_external"]
    rows_v31 = [("Raw fold-0 probability", *a(pe, "RAW"), fs.FLAMES_FOLD0, "o", True),
                ("5-fold ensemble mean", *a(pe, "ENS-RAW"), fs.FLAMES, "o", True),
                ("GR-LR (primary)", *a(pe, "GR-LR"), LEARN, "s", True),
                ("Ensemble candidates: ensemble mean (post hoc)", *a(pm, "RAW"), fs.FLAMES, "o", False),
                ("Ensemble candidates: GR-LR (post hoc)", *a(pm, "GR-LR"), LEARN, "s", False)]
    h1 = v32["H1"]
    k3b = v32["K3"]["K3b_cohort_probe_on_H1_endpoint"]["K3b-cohort-probe"]
    rows_v32 = [("5-fold ensemble mean", *a(h1, "ENS-RAW"), fs.FLAMES, "o", True),
                ("Fold disagreement (no training)", *a(h1, "DIS-RAW"), fs.FLAMES, "o", True),
                ("GR-LR (v3.1 detector)", *a(h1, "GR-LR"), LEARN, "s", True),
                ("GR+C-LR (primary, trained with controls)", *a(h1, "GR+C-LR"), LEARN, "s", True),
                ("Cohort probe (never saw a true lesion)", k3b["auroc"], tuple(k3b["ci95"]), PROBE, "D", True),
                ("Controls-only negatives (GR-Conly-LR)", *a(h1, "GR-Conly-LR"), PROBE, "D", True)]
    blocks = [("a", "v3 · pooled leave-one-cohort-out, MSLesSeg ↔ Ljubljana-10", rows_v3),
              ("b", "v3.1 · three unseen thick-slice sites", rows_v31),
              ("c", "v3.2 · 1-mm MS lesions vs healthy-control false candidates", rows_v32)]
    row_mm, head_mm, gap_mm = 4.2, 7.5, 4.0
    total = sum(len(r) for _, _, r in blocks) * row_mm + len(blocks) * head_mm + (len(blocks) - 1) * gap_mm
    fig = fs.figure(fs.DOUBLE, total + 11.5)
    X_AX, W_AX = 62.0, 72.0
    y = 0.0
    axes = []
    for bi, (letter, head, rows) in enumerate(blocks):
        fs.panel_label(fig, letter, 0, y + 0.4)
        fs.text_mm(fig, X_AX, y + 3.9, head, va="center", fontsize=7, color=fs.INK2)
        top = y + head_mm
        n = len(rows)
        ax = fs.axes(fig, X_AX, top, W_AX, n * row_mm)
        ax.set_ylim(n - 0.5, -0.5)
        ymm = lambda i, t=top: t + (i + 0.5) * row_mm  # noqa: E731
        txt = []
        for i, (lab, pt, ci, col, mk, filled) in enumerate(rows):
            ax.plot(ci, [i, i], color=col, lw=fs.LW_CI, zorder=2)
            ax.plot(pt, i, marker=mk, ls="none", zorder=3, ms=4.6, color=col, mfc=col if filled else "white",
                    mec="white" if filled else col, mew=0.5 if filled else 0.9)
            fs.text_mm(fig, 3.0, ymm(i), lab, va="center", fontsize=7)
            txt.append([fmt(pt), "(" + fmt(ci[0]), "–", fmt(ci[1]) + ")"])
        anchors, _ = fs.table_layout(fig, X_AX + W_AX + 3.0, [list(c) for c in zip(*txt)], "ddcd",
                                     [1.2, 0.12, 0.12, 0])
        for i, row in enumerate(txt):
            fs.table_row(fig, anchors, "ddcd", ymm(i), row)
        if bi == 0:
            fs.text_mm(fig, X_AX + W_AX + 3.0, y + 3.9, "AUROC (95% CI)", va="center", fontsize=6.5, color=fs.INK2)
        ax.set_xlim(0.6, 0.95)
        ax.set_xticks([0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95])
        last = bi == len(blocks) - 1
        ax.set_xticklabels(["0.60", "", "0.70", "", "0.80", "", "0.90", ""] if last else [])
        ax.set_yticks([])
        fs.despine(ax, left=False)
        if last:
            ax.set_xlabel("Lesion-level AUROC")
        axes.append(ax)
        y = top + n * row_mm + gap_mm
    save(fig, "fig4_detector_auroc")


# ---------------------------------------------------------------------------- figure 5
def fig5(d):
    a3 = d["v3"]["A3_site_identity_auroc"]
    h4 = d["v31"]["H4_site_signature_M_vs_L10"]["site_identity_auroc"]
    k2 = d["v32"]["K2"]
    ALL = (fs.BLUE_DARK, "o")      # combined feature sets
    FL = (fs.OCHRE, "s")           # FLAIR image features
    PRB = (fs.PRIMARY, "D")        # probability map / size
    DIS = (fs.FLAMES, "v")         # fold disagreement (from the FLAMeS ensemble)
    LST = (fs.MAUVE, "P")          # LST-AI agreement (the LST-AI hue of every MSTool-AI paper)
    rows_a = [("All 42 v3 features", a3["V3_all"], *ALL),
              ("FLAIR boundary", a3["F4_flair_boundary"], *FL),
              ("FLAIR texture", a3["F3_texture"], *FL),
              ("FLAIR contrast", a3["F1_contrast"], *FL),
              ("Probability-map boundary", a3["F4_prob_boundary"], *PRB),
              ("Location proxies", a3["F6_location"], *PRB),
              ("Persistence", a3["F5_persistence"], *PRB),
              ("Raw mean probability", a3["RAW(prob_mean)"], *PRB)]
    rows_b = [("FLAIR boundary", h4["F4_flair_boundary"], *FL),
              ("FLAIR texture", h4["F3_flair_texture"], *FL),
              ("FLAIR contrast", h4["F1_flair_contrast"], *FL),
              ("Probability + size (GR without F8)", h4["GR-noENS"], *PRB),
              ("LST-AI agreement (F9)", h4["F9_lstai_agreement"], *LST),
              ("Fold disagreement (F8)", h4["F8_fold_disagreement"], *DIS)]
    fw = k2["MSfalse_vs_C"]["foldwise"]
    ref = k2["Mfalse_vs_L10false_reference"]["foldwise"]
    fam = [("GR", "Grid-robust set (GR)", *ALL), ("F8", "Fold disagreement (F8)", *DIS),
           ("GR-noENS", "Probability + size", *PRB), ("LST", "LST-AI agreement", *LST),
           ("VOL", "Volume alone", *PRB), ("PROB", "Mean probability alone", *PRB)]
    row_a, row_c, head_mm, gap_mm = 4.0, 5.6, 6.5, 5.0
    head_c = 10.0
    h_a, h_b, h_c = len(rows_a) * row_a, len(rows_b) * row_a, len(fam) * row_c
    total = h_a + h_b + h_c + 2 * head_mm + head_c + 2 * gap_mm
    fig = fs.figure(fs.ONE_HALF, total + 11.5)
    X_AX, W_AX = 46.0, 76.0
    xlim, ticks = (0.15, 1.05), [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]

    def frame(ax, last, ylab_rows, top, rh):
        ax.set_xlim(*xlim)
        fs.ref_vline(ax, 0.5, color=fs.AXIS, lw=0.5)
        fs.ref_vline(ax, 0.7, color=fs.INK2, lw=0.5, ls=(0, (3, 2)))
        ax.set_xticks(ticks)
        ax.set_xticklabels([f"{t:.1f}" for t in ticks] if last else [])
        ax.set_yticks([])
        fs.despine(ax, left=False)
        for i, lab in enumerate(ylab_rows):
            fs.text_mm(fig, 2.5, top + (i + 0.5) * rh, lab, va="center", fontsize=7)

    y = 0.0
    for letter, head, rows in (("a", "v3 · MSLesSeg vs Ljubljana-10, all candidates", rows_a),
                               ("b", "v3.1 · MSLesSeg vs Ljubljana-10, all candidates", rows_b)):
        fs.panel_label(fig, letter, 0, y + 0.4)
        fs.text_mm(fig, X_AX, y + 3.6, head, va="center", fontsize=7, color=fs.INK2)
        top = y + head_mm
        n = len(rows)
        ax = fs.axes(fig, X_AX, top, W_AX, n * row_a)
        ax.set_ylim(n - 0.5, -0.5)
        for i, (lab, v, col, mk) in enumerate(rows):
            ax.plot([0.5, v], [i, i], color=col, lw=1.1, zorder=2, solid_capstyle="butt")
            ax.plot(v, i, marker=mk, color=col, ms=4.6, mec="white", mew=0.5, ls="none", zorder=3)
            ax.annotate(fmt(v, 2), (v, i), xytext=(4.5 if v >= 0.5 else -4.5, 0), textcoords="offset points",
                        ha="left" if v >= 0.5 else "right", va="center", fontsize=6.5, color=fs.INK,
                        bbox=dict(fc="white", ec="none", pad=0.6), zorder=4)
        frame(ax, False, [r[0] for r in rows], top, row_a)
        y = top + n * row_a + gap_mm
    fs.panel_label(fig, "c", 0, y + 0.4)
    fs.text_mm(fig, X_AX, y + 3.6, "v3.2 · false candidates only", va="center", fontsize=7, color=fs.INK2)
    top = y + head_c
    n = len(fam)
    ax = fs.axes(fig, X_AX, top, W_AX, h_c)
    ax.set_ylim(n - 0.5, -0.5)
    for i, (k, lab, col, mk) in enumerate(fam):
        v, ci = fw[k]["auroc_foldwise_mean"], fw[k]["ci95"]
        ax.plot(ci, [i - 0.15] * 2, color=col, lw=fs.LW_CI, zorder=2)
        ax.plot(v, i - 0.15, marker=mk, color=col, ms=4.6, mec="white", mew=0.5, ls="none", zorder=3)
        ax.annotate(fmt(v, 2), (ci[1], i - 0.15), xytext=(3.5, 0), textcoords="offset points", va="center",
                    fontsize=6.5, color=fs.INK, bbox=dict(fc="white", ec="none", pad=0.6), zorder=4)
        rv, rci = ref[k]["auroc_foldwise_mean"], ref[k]["ci95"]
        ax.plot(rci, [i + 0.2] * 2, color=fs.GREY_MID, lw=fs.LW_CI, zorder=2)
        ax.plot(rv, i + 0.2, marker=mk, color=fs.GREY_MID, mfc="white", mec=fs.GREY_MID, mew=0.9, ms=4.0, ls="none",
                zorder=3)
    frame(ax, True, [f[1] for f in fam], top, row_c)
    ax.set_xlabel("Cohort-identity AUROC")
    # key for the two comparisons of panel c
    ky = top - 1.2
    for x, filled, lab in ((X_AX + 33.0, True, "MS patients vs healthy controls"),
                           (X_AX + 33.0, False, "MSLesSeg vs Ljubljana-10 (reference)")):
        yk = ky - (4.6 if filled else 1.2)
        col = fs.INK if filled else fs.GREY_MID
        fig.lines.append(Line2D([fs.fx(fig, x)], [fs.fy(fig, yk)], transform=fig.transFigure, marker="o", ls="none",
                                ms=4.0, color=col, mfc=col if filled else "white", mec=col if filled else col,
                                mew=0.5 if filled else 0.9))
        fs.text_mm(fig, x + 2.2, yk, lab, va="center", fontsize=6.5, color=fs.INK2)
    save(fig, "fig5_site_signature")


# ---------------------------------------------------------------------------- figure 6
def _t(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def fig6(d):
    pre, oth, comp = d["preregistration"], d["other_commits"], d["compute"]
    push = {e["event"].split(" (")[0]: _t(e["utc"]) for e in d["public_push_evidence"]}
    PROT, RES, PUB = fs.PRIMARY, fs.OCHRE_DARK, fs.INK
    fig = fs.figure(fs.DOUBLE, 92)
    # ---- a: FLAMeS-thick, UTC, four lanes
    ax = fs.axes(fig, 36.0, 9.0, 140.0, 36.0)
    fs.panel_label(fig, "a", 0, 0.4)
    fs.text_mm(fig, 36.0, 3.2, "Study 1, FLAMeS-thick (UTC)", va="center", fontsize=7, color=fs.INK2)
    lanes = {"Commits (author time)": 3, "Public on GitHub": 2, "Kaggle sessions": 1, "Evaluation VMs": 0}
    t_pre = _t(pre["flames_thick"]["preregistration"]["committer_date"])
    ax.plot(t_pre, 3, marker="D", color=PROT, ms=4.6, mec="white", mew=0.5, ls="none", zorder=3)
    ax.annotate("protocol", (t_pre, 3), xytext=(0, 5), textcoords="offset points", ha="center", va="bottom",
                fontsize=6.5)
    for key, lab, ha, dx in [("ft_amendment_kaggle_pilot", "amend. 1", "right", -1.5),
                             ("ft_amendment_early_look", "amend. 2", "left", 1.5),
                             ("ft_training_done", "models", "center", 0)]:
        t = _t(oth[key]["committer_date"])
        ax.plot(t, 3, marker="|", color=fs.INK, ms=6.5, mew=1.0, ls="none", zorder=3)
        ax.annotate(lab, (t, 3), xytext=(dx, 5), textcoords="offset points", ha=ha, va="bottom", fontsize=6.5)
    t_res = _t(pre["flames_thick"]["results"]["committer_date"])
    ax.plot(t_res, 3, marker="s", color=RES, ms=4.6, mec="white", mew=0.5, ls="none", zorder=3)
    ax.annotate("results", (t_res, 3), xytext=(0, 5), textcoords="offset points", ha="center", va="bottom",
                fontsize=6.5)
    for ev, lab in [("PR #56 opened", "protocol public"), ("push 73e9651", ""), ("push aba9a54", "")]:
        t = push[ev]
        ax.plot(t, 2, marker="o", color=PUB, ms=4.2, mfc="white", mew=0.9, ls="none", zorder=3)
        if lab:
            ax.annotate(lab, (t, 2), xytext=(0, 5), textcoords="offset points", ha="center", va="bottom", fontsize=6.5)
    t = push["push b19293c"]  # local reflog only (author-side); no GitHub event was returned for it
    ax.plot(t, 2, marker="o", color=fs.GREY_MID, ms=4.2, mfc="white", mew=0.9, ls="none", zorder=3)
    ax.annotate("results pushed (local log only)", (t, 2), xytext=(4, 5), textcoords="offset points", ha="right",
                va="bottom", fontsize=6.5, color=fs.INK2)
    for k in comp["kaggle_sessions"]:
        ax.plot([_t(k["start_utc"]), _t(k["end_utc"])], [1, 1], color=fs.FLAMES, lw=5.0, solid_capstyle="butt")
    for k in comp["flames_thick_eval_runs"]:
        ax.plot([_t(k["start_utc"]), _t(k["end_utc"])], [0, 0], color=fs.GREY_MID, lw=5.0, solid_capstyle="butt")
    ax.set_yticks(list(lanes.values()))
    ax.set_yticklabels(list(lanes.keys()))
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.set_ylim(-0.6, 3.75)
    t0, t1 = datetime(2026, 10, 21, 0, tzinfo=timezone.utc), datetime(2026, 10, 23, 14, tzinfo=timezone.utc)
    ax.set_xlim(t0, t1)
    ax.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 6, 12, 18], tz=timezone.utc))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=timezone.utc))
    for day in (21, 22, 23):
        noon = datetime(2026, 10, day, 12, tzinfo=timezone.utc)
        ax.annotate(f"{day} October", (mdates.date2num(noon), 0), xycoords=("data", "axes fraction"), xytext=(0, -15),
                    textcoords="offset points", ha="center", va="top", fontsize=7, annotation_clip=False)
    for day in (22, 23):
        fs.ref_vline(ax, datetime(2026, 10, day, 0, tzinfo=timezone.utc), color=fs.GRID, lw=0.6, zorder=0)
    # ---- b: detector stages: markers on a day axis, times typeset at right
    stages = [("v3", "detector_v3", "PR #55 opened"), ("v3.1", "detector_v31", "PR #55 opened"),
              ("v3.2", "detector_v32", "push 3c24977")]
    top_b = 65.0
    bx = fs.axes(fig, 36.0, top_b, 68.0, 15.0)
    fs.panel_label(fig, "b", 0, top_b - 7.0)
    fs.text_mm(fig, 36.0, top_b - 4.3, "Study 2, detector stages (UTC)", va="center", fontsize=7, color=fs.INK2)
    rows = []
    for i, (lab, key, ev) in enumerate(stages):
        tp = _t(pre[key]["preregistration"]["committer_date"])
        tr = _t(pre[key]["results"]["committer_date"])
        tpub = push[ev]
        bx.plot(tp, i, marker="D", color=PROT, ms=4.6, mec="white", mew=0.5, ls="none", zorder=3)
        bx.plot(tr, i, marker="s", color=RES, ms=4.4, mec="white", mew=0.5, ls="none", zorder=4)
        bx.plot(tpub, i, marker="o", color=PUB, ms=5.4, mfc="none", mew=0.9, ls="none", zorder=5)
        bx.plot([tp, tpub], [i, i], color=fs.GREY_LIGHT, lw=0.8, zorder=1)
        f = "%d Oct %H:%M"
        pub = f"{tpub:{f}}" + (f"; results {push['push 90797a9']:%H:%M}" if key == "detector_v32" else "")
        rows.append((f"Detector {lab}", f"{tp:{f}}", f"{tr:{f}}", pub))
    bx.set_ylim(2.6, -0.6)
    bx.set_yticks(range(len(stages)))
    bx.set_yticklabels([r[0] for r in rows])
    bx.tick_params(axis="y", length=0)
    bx.spines["left"].set_visible(False)
    bx.set_xlim(datetime(2026, 10, 17, 0, tzinfo=timezone.utc), datetime(2026, 10, 25, 0, tzinfo=timezone.utc))
    bx.xaxis.set_major_locator(mdates.DayLocator(tz=timezone.utc))
    bx.xaxis.set_major_formatter(mdates.DateFormatter("%d", tz=timezone.utc))
    bx.set_xlabel("October 2026")
    heads = [("Protocol", PROT, "D"), ("Results", RES, "s"), ("First public", PUB, "o")]
    xs = [109.0, 128.5, 148.0]
    for (h, col, mk), x in zip(heads, xs):
        fig.lines.append(Line2D([fs.fx(fig, x + 1.2)], [fs.fy(fig, top_b - 4.3)], transform=fig.transFigure, marker=mk,
                                color=col, ms=4.4, mec="white" if mk != "o" else col, mew=0.5 if mk != "o" else 0.9,
                                mfc=col if mk != "o" else "none", ls="none"))
        fs.text_mm(fig, x + 3.2, top_b - 4.3, h, va="center", fontsize=6.5, color=fs.INK2)
    for i, r in enumerate(rows):
        ym = top_b + (i + 0.6) * (15.0 / 3.2)
        for x, s in zip(xs, r[1:]):
            fs.text_mm(fig, x, ym, s, va="center", fontsize=7)
    # legend for the lane symbols of panel a is the same as panel b's column heads
    save(fig, "fig6_preregistration_timeline")


def main():
    d = json.loads(DATA.read_text(encoding="utf-8"))
    fig1(d)
    fig2(d)
    fig3(d)
    fig4(d)
    fig5(d)
    fig6(d)


if __name__ == "__main__":
    main()
