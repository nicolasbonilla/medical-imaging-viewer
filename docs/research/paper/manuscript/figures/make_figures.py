#!/usr/bin/env python3
"""Paper A manuscript — every figure is drawn from the committed result records, nothing else.

Inputs (read-only):
  docs/research/records/2026-10-21_paper_a_v03_results.json       pre-registered v0.3 results
  docs/research/records/2026-10-21_paper_a_v03_posthoc.json       post-hoc explanations (labelled)
  docs/research/records/2026-10-24_paper_a_v03c_controls.json     healthy-control addendum
  docs/research/records/2026-10-31_paper_a_manuscript_posthoc.json manuscript-stage post hoc

Outputs: figN_*.pdf (vector, Arial embedded as TrueType) and figN_*.png (600 dpi) next to this script, drawn at
their final size (180 mm, double column) in the MSTool-AI house style (mstool_figstyle.py, mstool.mplstyle),
plus figures_manifest.json (SHA-256 of every input record and output file).

Colour: the house palette (muted, colour-blind safe; checked for deuteranopia, protanopia and tritanopia).
The status of a cell uses the house met / not-met pair (holds teal, inconclusive grey, violated brick) and
ALWAYS a distinct marker shape, so no meaning is carried by colour alone. FLAMeS ensemble = dark grey, fold 0 =
mid grey, as in every MSTool-AI paper. Explanatory notes live in the manuscript captions, not in the figures.

    python docs/research/paper/manuscript/figures/make_figures.py
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mstool_figstyle as fs  # noqa: E402

fs.use()
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", ".."))
REC = os.path.join(ROOT, "docs", "research", "records")
F_RES = os.path.join(REC, "2026-10-31_paper_a_v03_results_fullprec.json")
F_PH = os.path.join(REC, "2026-10-31_paper_a_v03_posthoc_fullprec.json")
F_CTL = os.path.join(REC, "2026-10-24_paper_a_v03c_controls.json")
F_MPH = os.path.join(REC, "2026-10-31_paper_a_manuscript_posthoc_fullprec.json")

CLASS_STYLE = {"holds": dict(marker="o", color=fs.TEAL, label="Holds"),
               "inconclusive": dict(marker="D", color=fs.GREY_MID, label="Inconclusive"),
               "violated": dict(marker="s", color=fs.BRICK, label="Violated")}
SITE_LABEL = {"mslesseg": "MSLesSeg", "openms": "Ljubljana-10", "ms3seg": "MS3SEG", "muslim": "Muslim", "pedims": "PediMS"}
ENS, F0 = fs.FLAMES, fs.FLAMES_FOLD0

OUTPUTS = []


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(fig, name):
    OUTPUTS.extend(fs.save(fig, os.path.join(HERE, name)))


def sha(p):
    """SHA-256; text records are hashed with LF line endings so the value equals the committed blob's."""
    h = hashlib.sha256()
    with open(p, "rb") as f:
        data = f.read()
    h.update(data.replace(b"\r\n", b"\n") if p.endswith(".json") else data)
    return h.hexdigest()


def status_key(fig, x_mm, y_mm, hollow_label=None, gap=4.0, above_label=None):
    """One-line key for the cell status (and, optionally, the hollow marker and the 'holds, estimate above
    nominal' marker: the holds marker with a dark edge)."""
    x = x_mm
    items = [(v["marker"], v["color"], v["label"], True, False) for v in CLASS_STYLE.values()]
    if above_label:
        items.append((CLASS_STYLE["holds"]["marker"], CLASS_STYLE["holds"]["color"], above_label, True, True))
    if hollow_label:
        items.append(("o", fs.INK2, hollow_label, False, False))
    for mk, col, lab, filled, dark in items:
        fig.lines.append(Line2D([fs.fx(fig, x + 1.4)], [fs.fy(fig, y_mm)], transform=fig.transFigure, marker=mk,
                                ms=4.4, mew=(1.0 if dark else 0.6) if filled else 0.8, ls="none", mfc=col if filled else "white",
                                mec=(fs.INK if dark else "white") if filled else col))
        t = fs.text_mm(fig, x + 3.4, y_mm, lab, va="center", fontsize=7)
        x += 3.4 + fs.text_width_mm(fig, lab) + gap
    return x


def nominal_marks(ax, y, nominal, h=0.36):
    """Pre-registered margin (nominal to nominal + 0.05) as a light band and the nominal level as a tick."""
    ax.add_patch(Rectangle((nominal, y - h), 0.05, 2 * h, color=fs.BAND, lw=0, zorder=0))
    ax.plot([nominal, nominal], [y - h, y + h], color=fs.REFLINE, lw=0.6, zorder=1)


def cell_marker(ax, x, y, cls, filled=True, ms=4.6, above=False):
    """above: a 'holds' cell whose point estimate exceeds the nominal level (dark edge; revision 2)."""
    st = CLASS_STYLE[cls]
    dark = above and filled
    ax.plot(x, y, marker=st["marker"], ls="none", ms=ms, zorder=4, mew=(1.0 if dark else 0.6) if filled else 0.9,
            mfc=st["color"] if filled else "white", mec=(fs.INK if dark else "white") if filled else st["color"])


# --------------------------------------------------------------------------- Figure 1
def fig1_primary(res):
    """Forest plot of the 32 pre-registered primary cells (ensemble arm)."""
    groups = [("1-mm grid → thick slices (D3)", [("D3", "ms3seg"), ("D3", "muslim"), ("D3", "pedims")]),
              ("Leave one site out (D2)", [("D2", "mslesseg"), ("D2", "openms"), ("D2", "ms3seg"), ("D2", "muslim"),
                                          ("D2", "pedims")])]
    cells = {(c["design"], c["site"], c["procedure"], c["target"]): c for c in res["primary"]}
    rows, y = [], 0.0
    for gi, (head, sites) in enumerate(groups):
        if gi:
            y += 0.5
        rows.append(("head", head, y))
        y += 1.0
        for si, (d, s) in enumerate(sites):
            if si:
                y += 0.35
            for t in (0.1, 0.2):
                rows.append(("cell", (d, s, t), y))
                y += 1.0
    n_units, row_mm, top = y, 3.55, 9.5
    plot_h = n_units * row_mm
    fig = fs.figure(fs.DOUBLE, top + plot_h + 13.0)
    ylim = (n_units - 0.5, -0.5)
    ymm = lambda v: top + (v + 0.5) * row_mm  # noqa: E731
    fs.panel_label(fig, "a", 0, 0.4)
    fs.text_mm(fig, 33.5, top - 2.8, "α or γ", ha="center", va="center", fontsize=6.5, color=fs.INK2)
    for kind, val, yy in rows:
        if kind == "head":
            fs.text_mm(fig, 0, ymm(yy), val, va="center", fontsize=7, fontweight="bold")
            continue
        d, s, t = val
        if t == 0.1:
            lab = SITE_LABEL[s] + (" †" if s == "openms" else "")
            fs.text_mm(fig, 2.0, ymm(yy + 0.5), lab, va="center", fontsize=7)
        fs.text_mm(fig, 33.5, ymm(yy), f"{t}", ha="center", va="center", fontsize=7, color=fs.INK2)
    specs = (("P1", 40.0, 62.0, (-0.01, 0.30), (0, 0.1, 0.2, 0.3), "Realised FDR (mean per-scan FDP)",
              "P1, conformal BH"),
             ("P2", 112.0, 66.0, (-0.01, 0.55), (0, 0.1, 0.2, 0.3, 0.4, 0.5), "Realised FDX (share of scans with FDP > γ)",
              "P2, CALM-FDX threshold"))
    for proc, x0, w, xlim, ticks, xlabel, facet in specs:
        ax = fs.axes(fig, x0, top, w, plot_h)
        ax.set_ylim(*ylim)
        if proc == "P2":
            fs.panel_label(fig, "b", x0 - 5.0, 0.4)
        fs.facet_label(ax, facet, color=fs.INK2, pad_pt=6)
        for kind, val, yy in rows:
            if kind != "cell":
                continue
            d, s, t = val
            c = cells[(d, s, proc, t)]
            nominal_marks(ax, yy, c["nominal"])
            lo, hi = c["ci95"]
            ax.plot([lo, hi], [yy, yy], color=fs.INK, lw=fs.LW_CI, zorder=3)
            cell_marker(ax, c["estimate"], yy, c["class"], filled=not c["uninformative_abstention"],
                        above=c["class"] == "holds" and c["estimate"] > c["nominal"])
        ax.set_xlim(*xlim)
        ax.set_xticks(ticks)
        ax.set_xticklabels(["0" if v == 0 else f"{v:g}" for v in ticks])
        ax.set_yticks([])
        fs.despine(ax, left=False)
        ax.set_xlabel(xlabel)
    status_key(fig, 0.0, top + plot_h + 10.6, hollow_label="Passes only by abstention", above_label="Holds, estimate > nominal")
    save(fig, "fig1_primary_cells")


# --------------------------------------------------------------------------- Figure 2
def fig2_mechanism(res, ph):
    """Why the per-scan threshold fails on thick slices (post hoc explanation)."""
    sites = ["mslesseg", "openms", "ms3seg", "muslim", "pedims"]
    above = [ph[f"ens|{s}"]["scans_with_false_candidate_above_1mm_P2_threshold"] for s in sites]
    cells = {(c["design"], c["site"], c["procedure"], c["target"]): c for c in res["primary"]}
    fdx = [None, None] + [cells[("D3", s, "P2", 0.1)]["estimate"] for s in sites[2:]]
    fig = fs.figure(fs.DOUBLE, 62)
    T, PH = 9.0, 40.0
    # ---- a: share of scans above the 1-mm threshold (post hoc) next to the realised FDX (pre-registered)
    ax = fs.axes(fig, 12.0, T, 84.0, PH)
    fs.panel_label(fig, "a", 0, 0.4)
    x = list(range(len(sites)))
    w = 0.36
    C_ABOVE, C_FDX = fs.GREY_MID, fs.PRIMARY
    ax.bar([i - w / 2 for i in x], above, width=w - 0.04, color=C_ABOVE, lw=0, zorder=2)
    ax.bar([i + w / 2 for i in x[2:]], fdx[2:], width=w - 0.04, color=C_FDX, lw=0, zorder=2)
    fs.ref_hline(ax, 0.1, color=fs.INK, lw=0.5, ls=(0, (3, 2)), zorder=3)
    ax.annotate("δ = 0.1", (4.62, 0.1), xytext=(0, 2), textcoords="offset points", ha="right", va="bottom",
                fontsize=6.5, color=fs.INK2)
    for i, v in enumerate(above):
        ax.annotate(f"{v:.2f}", (i - w / 2, v), xytext=(0, 1.5), textcoords="offset points", ha="center",
                    va="bottom", fontsize=6.5, color=fs.INK2)
    for i in range(2, 5):
        ax.annotate(f"{fdx[i]:.2f}", (i + w / 2, fdx[i]), xytext=(0, 1.5), textcoords="offset points", ha="center",
                    va="bottom", fontsize=6.5, color=fs.INK2)
    ax.set_xticks(x)
    ax.set_xticklabels([SITE_LABEL[s] for s in sites])
    ax.tick_params(axis="x", length=0)
    ax.set_xlim(-0.6, 4.65)
    ax.set_ylabel("Share of scans")
    ax.set_ylim(0, 0.34)
    ax.set_yticks([0, 0.1, 0.2, 0.3])
    ax.set_yticklabels(["0", "0.1", "0.2", "0.3"])
    for k, (col, lab) in enumerate(((C_ABOVE, "Scans with a false candidate above 0.965 (post hoc)"),
                                    (C_FDX, "Realised FDX, 1-mm → thick, γ = 0.1 (pre-registered)"))):
        ym = 1.6 + k * 3.6
        fig.patches.append(Rectangle((fs.fx(fig, 14.0), fs.fy(fig, ym + 1.1)), 2.4 / fs.DOUBLE, 2.2 / fig._mm[1],
                                     transform=fig.transFigure, color=col, lw=0))
        fs.text_mm(fig, 17.6, ym, lab, va="center", fontsize=7)
    # ---- b: fold 0 vs 5-fold ensemble, share of false candidates scoring >= 0.95 (post hoc)
    bx = fs.axes(fig, 126.0, T, 50.0, PH)
    fs.panel_label(fig, "b", 106.0, 0.4)
    f0 = [ph[f"f0|{s}"]["false_candidates_score_ge_0.95"] for s in sites]
    en = [ph[f"ens|{s}"]["false_candidates_score_ge_0.95"] for s in sites]
    for i, (a, b) in enumerate(zip(f0, en)):
        bx.plot([a, b], [i, i], color=fs.GREY_LIGHT, lw=1.6, zorder=1, solid_capstyle="round")
    bx.plot(f0, x, "s", color=F0, ms=4.6, mec="white", mew=0.5, ls="none", zorder=3)
    bx.plot(en, x, "o", color=ENS, ms=4.8, mec="white", mew=0.5, ls="none", zorder=3)
    bx.annotate("Fold 0", (f0[0], 0), xytext=(0, 5), textcoords="offset points", ha="center", va="bottom",
                fontsize=6.5, color=fs.INK2)
    bx.annotate("5-fold ensemble", (en[0], 0), xytext=(-2, 5), textcoords="offset points", ha="left", va="bottom",
                fontsize=6.5, color=fs.INK2)
    bx.set_yticks(x)
    bx.set_yticklabels([SITE_LABEL[s] for s in sites])
    bx.tick_params(axis="y", length=0)
    bx.spines["left"].set_visible(False)
    bx.set_ylim(len(sites) - 0.5, -0.9)
    bx.set_xlim(0, 0.36)
    bx.set_xticks([0, 0.1, 0.2, 0.3])
    bx.set_xticklabels(["0", "0.1", "0.2", "0.3"])
    bx.set_xlabel("False candidates scoring ≥ 0.95")
    save(fig, "fig2_threshold_mechanism")


# --------------------------------------------------------------------------- Figure 3
def fig3_size(res):
    """Raw detection by lesion volume and thickness band (D2, ensemble)."""
    sb = res["thickness"]["size_bins"]
    bands = [("B1", "≤ 1.5 mm", fs.ORDINAL4[0], "o"), ("B2", "3.9 mm", fs.ORDINAL4[1], "^"),
             ("B3", "4.5–6.5 mm", fs.ORDINAL4[2], "s"), ("B4", "> 6.5 mm", fs.ORDINAL4[3], "D")]
    xt = ["3–14", "14–50", "50–150", "150–500", "≥500"]
    fig = fs.figure(fs.DOUBLE, 60)
    T, PH, PW = 6.0, 41.0, 62.0
    for p, (key, letter, facet) in enumerate((("sens_raw", "a", "Raw segmentation"),
                                              ("sens_selected", "b", "After P1 selection (α = 0.2, leave one site out)"))):
        x0 = 12.0 + p * (PW + 22.0)
        ax = fs.axes(fig, x0, T, PW, PH)
        fs.panel_label(fig, letter, x0 - (12.0 if p == 0 else 4.5), 0.4)
        fs.facet_label(ax, facet, color=fs.INK2)
        for yref in (0.5, 0.8):
            fs.ref_hline(ax, yref, color=fs.GRID, lw=0.6, zorder=0)
        ends = []
        for b, lab, col, mk in bands:
            r = sb[f"{b}|D2|P1|0.2"]
            ax.plot(range(5), r[key], color=col, lw=fs.LW_DATA, zorder=2)
            ax.plot(range(5), r[key], marker=mk, color=col, ms=4.2, mec="white", mew=0.5, ls="none", zorder=3)
            ends.append((r[key][-1], lab, col))
        yl = fs.spread([e for e, _, _ in ends], 0.075, lo=0.03, hi=0.98)
        for (e, lab, col), yy in zip(ends, yl):
            ax.annotate(lab, (4, e), xytext=(4.32, yy), textcoords="data", ha="left", va="center", fontsize=7,
                        color=fs.INK, arrowprops=dict(arrowstyle="-", lw=0.4, color=fs.GREY_MID, shrinkA=0.5,
                                                      shrinkB=3.0) if abs(yy - e) > 0.02 else None)
        ax.set_xticks(range(5))
        ax.set_xticklabels(xt)
        ax.set_xlim(-0.3, 4.3)
        ax.spines["bottom"].set_bounds(-0.3, 4.3)
        ax.set_xlabel("Expert-lesion volume (mm³)")
        ax.set_ylim(0, 1.0)
        ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
        ax.set_yticklabels(["0", "0.2", "0.4", "0.6", "0.8", "1.0"] if p == 0 else [])
        if p == 0:
            ax.set_ylabel("Expert lesions found")
    save(fig, "fig3_detection_by_size_and_band")


# --------------------------------------------------------------------------- Figure 4
def fig4_ensemble(res):
    """5-fold ensemble vs fold 0, same scans and expert lesions (P1, alpha = 0.2)."""
    q = res["q3"]["paired_ens_minus_f0"]
    rows = [("D3|ALL", "1-mm → thick, all thick sites"), ("D3|ms3seg", "1-mm → MS3SEG"), ("D3|muslim", "1-mm → Muslim"),
            ("D3|pedims", "1-mm → PediMS"), ("D2|ALL", "Leave one site out, all"), ("D1|ALL", "Within site, all"),
            ("D4|ALL", "Pooled 5-fold, all")]
    row_mm, top = 4.6, 8.0
    n = len(rows)
    plot_h = n * row_mm
    fig = fs.figure(fs.DOUBLE, top + plot_h + 11.0)
    ymm = lambda i: top + (i + 0.5) * row_mm  # noqa: E731
    for i, (_, lab) in enumerate(rows):
        fs.text_mm(fig, 0, ymm(i), lab, va="center", fontsize=7)
    fs.panel_label(fig, "a", 0, 0.4)
    specs = (("mean_fdp", 39.0, 31.0, (0, 0.42), (0, 0.1, 0.2, 0.3, 0.4), "Realised FDR (α = 0.2)", "a"),
             ("sens_e2e", 112.0, 38.0, (0, 0.7), (0, 0.2, 0.4, 0.6), "End-to-end lesion sensitivity", "b"))
    for metric, x0, w, xlim, ticks, xlabel, letter in specs:
        ax = fs.axes(fig, x0, top, w, plot_h)
        if letter == "b":
            fs.panel_label(fig, "b", x0 - 4.0, 0.4)
        ax.set_ylim(n - 0.5, -0.5)
        if metric == "mean_fdp":
            fs.ref_vline(ax, 0.2, color=fs.INK, lw=0.5, ls=(0, (3, 2)))
        cells = []
        for i, (k, _) in enumerate(rows):
            r = q[f"{k}|P1|0.2"][metric]
            ax.plot([r["b"], r["a"]], [i, i], color=fs.GREY_LIGHT, lw=1.6, zorder=1, solid_capstyle="round")
            ax.plot(r["b"], i, "s", color=F0, ms=4.4, mec="white", mew=0.5, zorder=3)
            ax.plot(r["a"], i, "o", color=ENS, ms=4.6, mec="white", mew=0.5, zorder=3)
            cells.append(r)
        r0 = cells[0]
        left, right = sorted(((r0["b"], "Fold 0"), (r0["a"], "Ensemble")))
        ax.annotate(left[1], (left[0], 0), xytext=(2, 4.5), textcoords="offset points", ha="right", va="bottom",
                    fontsize=6.5, color=fs.INK2, bbox=dict(fc="white", ec="none", pad=0.4), zorder=5)
        ax.annotate(right[1], (right[0], 0), xytext=(-2, 4.5), textcoords="offset points", ha="left", va="bottom",
                    fontsize=6.5, color=fs.INK2, bbox=dict(fc="white", ec="none", pad=0.4), zorder=5)
        ax.set_xlim(*xlim)
        ax.set_xticks(ticks)
        ax.set_xticklabels(["0" if v == 0 else f"{v:g}" for v in ticks])
        ax.set_yticks([])
        fs.despine(ax, left=False)
        ax.set_xlabel(xlabel)
        # paired difference (ensemble − fold 0) with 95% CI, decimal-aligned
        all_pos = all(v >= 0 for r in cells for v in r["ci95"])
        sep = "–" if all_pos else " to "
        txt = [[fs.fnum(r["diff"], 3, sign=True), "(" + fs.fnum(r["ci95"][0], 3, sign=not all_pos), sep.strip(),
                fs.fnum(r["ci95"][1], 3, sign=not all_pos) + ")"] for r in cells]
        tx0 = x0 + w + 2.5
        anchors, _ = fs.table_layout(fig, tx0, [list(c) for c in zip(*txt)], "ddcd",
                                     [1.2, 0.12 if all_pos else 0.9, 0.12 if all_pos else 0.9, 0])
        for i, row in enumerate(txt):
            fs.table_row(fig, anchors, "ddcd", ymm(i), row)
        fs.text_mm(fig, tx0, top - 2.6, "Δ (95% CI)", va="center", fontsize=6.5, color=fs.INK2)
    save(fig, "fig4_ensemble_vs_fold0")


# --------------------------------------------------------------------------- Figure 5
def fig5_recal(res):
    """Recalibration curve with k local patients (D5, 200 draws)."""
    series = [("site_only", "P1", 0.2, fs.PRIMARY, "o", True, "P1, site only (α = 0.2)"),
              ("augmented", "P1", 0.1, fs.PRIMARY, "o", False, "P1, 1-mm pool + k (α = 0.1)"),
              ("site_only", "P2", 0.1, fs.OCHRE_DARK, "s", True, "P2, site only (γ = 0.1)"),
              ("augmented", "P2", 0.1, fs.OCHRE_DARK, "s", False, "P2, 1-mm pool + k (γ = 0.1)")]
    fig = fs.figure(fs.DOUBLE, 100)
    L, T, PW, PH, GX, GY = 14.0, 11.5, 78.0, 35.0, 10.0, 10.5
    letters = {(0, 0): "a", (0, 1): "b", (1, 0): "c", (1, 1): "d"}
    for col, site in enumerate(("ms3seg", "muslim")):
        cells = res["q4"][site]["cells"]
        ks = res["q4"][site]["k_grid"]
        for row in (0, 1):
            x0, y0 = L + col * (PW + GX), T + row * (PH + GY)
            ax = fs.axes(fig, x0, y0, PW, PH)
            fs.panel_label(fig, letters[(row, col)], x0 - 12.5 if col == 0 else x0 - 5.0, y0 - 4.0)
            if row == 0:
                fs.facet_label(ax, SITE_LABEL[site], fontweight="bold")
                for yref in (0.1, 0.2):
                    fs.ref_hline(ax, yref, color=fs.REFLINE, lw=0.5, ls=(0, (2, 2)))
            for mode, proc, t, c, mk, filled, lab in series:
                xs, ys = [], []
                for k in ks:
                    r = cells.get(f"{mode}|{proc}|{t}|k={k}")
                    if r is None:
                        continue
                    if proc == "P2" and mode == "site_only" and r["n_sel_mean"] == 0:
                        continue  # abstains by construction (k < 9)
                    xs.append(k)
                    ys.append(r["realised_mean"] if row == 0 else r["sens_e2e_mean"])
                ax.plot(xs, ys, color=c, lw=fs.LW_DATA, ls="-" if filled else (0, (3, 1.6)), zorder=2)
                ax.plot(xs, ys, marker=mk, ls="none", ms=4.2, zorder=3, mew=0.5 if filled else 0.9, color=c,
                        mfc=c if filled else "white", mec="white" if filled else c)
            ax.set_xscale("log")
            ax.set_xticks(ks)
            ax.set_xticklabels([str(k) for k in ks] if row == 1 else [])
            ax.minorticks_off()
            ax.set_xlim(0.85, 47)
            ax.set_ylim(0, 0.3)
            ax.set_yticks([0, 0.1, 0.2, 0.3])
            ax.set_yticklabels(["0", "0.1", "0.2", "0.3"] if col == 0 else [])
            if row == 1:
                ax.set_xlabel("Local calibration patients, k")
            if col == 0:
                ax.set_ylabel("Realised FDR or FDX" if row == 0 else "End-to-end sensitivity")
    # key: one line across the top
    x = L
    for mode, proc, t, c, mk, filled, lab in series:
        y = 2.2
        fig.lines.append(Line2D([fs.fx(fig, x), fs.fx(fig, x + 6.0)], [fs.fy(fig, y)] * 2, transform=fig.transFigure,
                                color=c, lw=fs.LW_DATA, ls="-" if filled else (0, (3, 1.6))))
        fig.lines.append(Line2D([fs.fx(fig, x + 3.0)], [fs.fy(fig, y)], transform=fig.transFigure, marker=mk, ls="none",
                                ms=4.2, mew=0.5 if filled else 0.9, color=c, mfc=c if filled else "white",
                                mec="white" if filled else c))
        fs.text_mm(fig, x + 7.6, y, lab, va="center", fontsize=7)
        x += 7.6 + fs.text_width_mm(fig, lab) + 6.0
    save(fig, "fig5_recalibration_curve")


# --------------------------------------------------------------------------- Figure 6
def fig6_controls(ctl):
    """Healthy controls with >= 1 reported lesion (100 SibBMS controls)."""
    op = ctl["operating_points"]
    rows = [("ens|1-mm sites|P1|0.1", ("Ensemble", "1-mm sites", "P1, α = 0.1", "primary"), 0.1),
            ("ens|1-mm sites|P1|0.2", ("Ensemble", "1-mm sites", "P1, α = 0.2", "primary"), 0.2),
            ("ens|1-mm sites|P2|0.1", ("Ensemble", "1-mm sites", "P2", "primary"), 0.1),
            ("ens|all five patient sites|P1|0.1", ("Ensemble", "All five sites", "P1, α = 0.1", ""), 0.1),
            ("ens|all five patient sites|P1|0.2", ("Ensemble", "All five sites", "P1, α = 0.2", ""), 0.2),
            ("ens|1-mm sites|B3|0.2", ("Ensemble", "1-mm sites", "LTT (B3), α = 0.2", ""), 0.2),
            ("f0|1-mm sites|P1|0.1", ("Fold 0", "1-mm sites", "P1, α = 0.1", ""), 0.1),
            ("f0|1-mm sites|P1|0.2", ("Fold 0", "1-mm sites", "P1, α = 0.2", ""), 0.2),
            ("f0|1-mm sites|P2|0.1", ("Fold 0", "1-mm sites", "P2", ""), 0.1)]
    row_mm, top = 4.3, 8.0
    n = len(rows)
    plot_h = n * row_mm + 0.35 * row_mm
    fig = fs.figure(fs.DOUBLE, top + plot_h + 13.0)
    ys = [i + (0.35 if i >= 6 else 0) for i in range(n)]
    ymm = lambda v: top + (v + 0.5) * row_mm  # noqa: E731
    cols = [(0, "Arm"), (14.0, "Calibration pool"), (35.0, "Procedure"), (60.0, "")]
    for x, head in cols:
        if head:
            fs.text_mm(fig, x, top - 2.6, head, va="center", fontsize=6.5, color=fs.INK2)
    for (k, labs, nom), yy in zip(rows, ys):
        for (x, _), s in zip(cols, labs):
            fs.text_mm(fig, x, ymm(yy), s, va="center", fontsize=7, color=fs.INK2 if s == "primary" else fs.INK)
    ax = fs.axes(fig, 74.0, top, 84.0, plot_h)
    ax.set_ylim(ys[-1] + 0.5, -0.5)
    cnt = []
    for (k, labs, nom), yy in zip(rows, ys):
        r = op[f"{k}|all100"]
        lo, hi = r["ci95_exact"]
        nominal_marks(ax, yy, nom, h=0.38)
        ax.plot([lo, hi], [yy, yy], color=fs.INK, lw=fs.LW_CI, zorder=3)
        cell_marker(ax, r["rate"], yy, r["class"])
        cnt.append((yy, f"{r['scans_with_any']}/100"))
    ax.set_xlim(0, 0.9)
    ax.set_xticks([0, 0.2, 0.4, 0.6, 0.8])
    ax.set_xticklabels(["0", "0.2", "0.4", "0.6", "0.8"])
    ax.set_yticks([])
    fs.despine(ax, left=False)
    ax.set_xlabel("Healthy controls with ≥ 1 reported lesion (exact 95% CI)")
    anchors, _ = fs.table_layout(fig, 162.0, [[c for _, c in cnt]], "r", [0])
    fs.text_mm(fig, anchors[0], top - 2.6, "Controls", ha="right", va="center", fontsize=6.5, color=fs.INK2)
    for yy, c in cnt:
        fs.text_mm(fig, anchors[0], ymm(yy), c, ha="right", va="center", fontsize=7)
    status_key(fig, 0.0, top + plot_h + 10.6)
    save(fig, "fig6_healthy_controls")


# --------------------------------------------------------------------------- Figure 7
def fig7_baselines(res, mph):
    """Validity vs power of every procedure, 1-mm -> thick (D3), per site and alpha."""
    procs = [("P1", "P1, conformal BH", fs.PRIMARY, "o"),
             ("SUB", "One candidate per patient + BH (post hoc)", fs.BLUE_LIGHT, "^"),
             ("B2", "B2, conformal risk control", fs.OCHRE, "s"),
             ("B3", "B3, Learn-then-Test", fs.OCHRE_DARK, "D"),
             ("B1", "B1, precision-matched (no guarantee)", fs.FLAMES, "X"),
             ("LR", "Hierarchical e-values (post hoc)", fs.GREY_MID, "v")]
    fig = fs.figure(fs.DOUBLE, 103)
    L, T, PW, PH, GX, GY = 13.0, 15.5, 49.0, 34.0, 8.0, 12.0
    letters = iter("abcdef")
    for r_i, a in enumerate((0.1, 0.2)):
        for c_i, site in enumerate(("ms3seg", "muslim", "pedims")):
            x0, y0 = L + c_i * (PW + GX), T + r_i * (PH + GY)
            ax = fs.axes(fig, x0, y0, PW, PH)
            fs.panel_label(fig, next(letters), x0 - (13.0 if c_i == 0 else 5.5), y0 - 4.6)
            fs.facet_label(ax, f"{SITE_LABEL[site]}", fontweight="bold")
            fs.facet_label(ax, f"α = {a}", x=1.0, ha="right", color=fs.INK2)
            fs.band_v(ax, a, a + 0.05)
            fs.ref_vline(ax, a, color=fs.INK, lw=0.5, ls=(0, (3, 2)))
            for p, lab, col, mk in procs:
                if p in ("P1", "B1", "B2", "B3"):
                    v = res["designs"]["ens|D3"][f"{p}|{a}"][site]
                    est, ci, sens = v["mean_fdp"], v["mean_fdp_ci"], v["sens_e2e"]
                elif p == "SUB":
                    v = mph["B_baselines"][f"SUB|D3|{site}|{a}"]
                    est, ci, sens = v["estimate"], v["ci95"], v["sens_e2e"]
                else:
                    v = mph["B_baselines"][f"LRhier|D3|{site}|{a}"]
                    est, ci, sens = v["estimate"], v["ci95"], v["sens_e2e"]
                ax.plot(ci, [sens, sens], color=col, lw=fs.LW_CI, zorder=2)
                ax.plot(est, sens, marker=mk, color=col, mec="white", mew=0.5, ms=4.8 if mk != "X" else 5.2,
                        ls="none", zorder=3)
            ax.set_xlim(-0.01, 0.32)
            ax.set_xticks([0, 0.1, 0.2, 0.3])
            ax.set_xticklabels(["0", "0.1", "0.2", "0.3"])
            ax.set_ylim(-0.03, 0.68)
            ax.set_yticks([0, 0.2, 0.4, 0.6])
            ax.set_yticklabels(["0", "0.2", "0.4", "0.6"] if c_i == 0 else [])
            if c_i == 0:
                ax.set_ylabel("End-to-end sensitivity")
            if r_i == 1:
                ax.set_xlabel("Realised FDR (95% CI)")
    # key: two rows of three, above the panels
    for i, (p, lab, col, mk) in enumerate(procs):
        c, r = divmod(i, 2)
        x, y = L + c * 57.0, 2.0 + r * 4.2
        fig.lines.append(Line2D([fs.fx(fig, x + 1.4)], [fs.fy(fig, y)], transform=fig.transFigure, marker=mk,
                                color=col, mec="white", mew=0.5, ms=5.0, ls="none"))
        fs.text_mm(fig, x + 3.6, y, lab, va="center", fontsize=7)
    save(fig, "fig7_baselines_validity_power")


def main():
    res, ph, ctl, mph = load(F_RES), load(F_PH), load(F_CTL), load(F_MPH)
    fig1_primary(res)
    fig2_mechanism(res, ph)
    fig3_size(res)
    fig4_ensemble(res)
    fig5_recal(res)
    fig6_controls(ctl)
    fig7_baselines(res, mph)
    man = {"inputs": {os.path.relpath(p, ROOT).replace(os.sep, "/"): sha(p) for p in (F_RES, F_PH, F_CTL, F_MPH)},
           "outputs": {os.path.basename(p): sha(p) for p in OUTPUTS if p.endswith(".png")},
           "style": "MSTool-AI house style (mstool_figstyle.py + mstool.mplstyle): Arial, 180 mm, PDF TrueType + 600 dpi PNG",
           "palette": {"ensemble/fold0": [fs.FLAMES, fs.FLAMES_FOLD0], "accents": [fs.PRIMARY, fs.SECONDARY],
                       "status": [fs.TEAL, fs.GREY_MID, fs.BRICK], "ordinal": list(fs.ORDINAL4),
                       "validator": "mstool_figstyle.cvd_report: Machado 2009 deutan/protan/tritan, CIEDE2000 >= 12, ALL PASS"}}
    with open(os.path.join(HERE, "figures_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, indent=1)
    print("wrote", len(OUTPUTS), "files")


if __name__ == "__main__":
    main()
