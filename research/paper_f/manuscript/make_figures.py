"""Paper F manuscript figures - generated ONLY from the stored, pre-registered results (no images, no cloud).

Inputs : ../results/comparisons.json, ../results/summary.json, ../results/per_scan.csv.gz (Figure 4a dots)
Outputs: figures/fig{1..4}_*.pdf (vector, Arial embedded as TrueType) and .png (600 dpi), drawn at their
         final journal size (180 mm wide) in the MSTool-AI house style (figures/mstool_figstyle.py).

    python research/paper_f/manuscript/make_figures.py

Colour: the house palette (muted, colour-blind safe; checked for deuteranopia, protanopia and tritanopia
by figures/mstool_figstyle.py). Every tool keeps one fixed hue and its own marker shape in every paper;
FLAMeS, the reference, is always dark grey. All explanatory notes are in the manuscript captions.
"""
import csv
import gzip
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "figures")
sys.path.insert(0, OUT)
import mstool_figstyle as fs  # noqa: E402

fs.use()
import matplotlib.colors as mcolors  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

RES = os.path.join(os.path.dirname(HERE), "results")
COMP = json.load(open(os.path.join(RES, "comparisons.json"), encoding="utf-8"))
SUMM = json.load(open(os.path.join(RES, "summary.json"), encoding="utf-8"))

ORDER = ("flames", "mindglide", "mindglide-raw", "wmhsynthseg", "samseg", "lstai")
STYLE = {k: fs.TOOLS[k] for k in ORDER}
NAME = {"flames": "FLAMeS", "mindglide": "MindGlide", "mindglide-raw": "MindGlide, raw input",
        "wmhsynthseg": "WMH-SynthSeg", "samseg": "SAMSEG", "lstai": "LST-AI"}
SHORT = {"flames": "FLAMeS", "mindglide": "MindGlide", "mindglide-raw": "MindGlide\nraw input",
         "wmhsynthseg": "WMH-\nSynthSeg", "samseg": "SAMSEG", "lstai": "LST-AI"}
COHORT = {"mslesseg": ("MSLesSeg", "1 mm"), "openms": ("Ljubljana", "1 mm"), "ms3seg": ("MS3SEG", "6.0–8.1 mm"),
          "muslim": ("Muslim et al.", "4.9–8.3 mm"), "pedims": ("PediMS", "3.9 mm")}


def tint(c, k):
    """Mix a colour with white (k = share of white)."""
    r, g, b = mcolors.to_rgb(c)
    return mcolors.to_hex((r + (1 - r) * k, g + (1 - g) * k, b + (1 - b) * k))


def save(fig, name):
    fs.save(fig, os.path.join(OUT, name))


def find(family, **kw):
    for r in COMP[family]:
        if all(r.get(k) == v for k, v in kw.items()):
            return r
    raise KeyError((family, kw))


def pfmt(p, family_size):
    """Bootstrap p of 0 = no replicate on the other side of zero (resolution 2/10,000);
    after Holm over m tests the honest bound is m x 0.0002."""
    if p is None:
        return "not run"
    if p == 0.0:
        return "< 0.002" if family_size <= 6 else "< 0.003"
    # two significant figures, as in the manuscript (Monte Carlo SE of a bootstrap p near 0.45 is ~0.008)
    return f"{p:.2g}" if p < 0.995 else "1.0"


# ----------------------------------------------------------------------------- Figure 1: forest plot
def fig1():
    rows = [
        ("> 3 mm · primary family", None),
        ("MindGlide", ("primary", "mindglide", "thick")),
        ("WMH-SynthSeg", ("primary", "wmhsynthseg", "thick")),
        ("SAMSEG (tier C)", ("primary", "samseg", "thick")),
        ("> 3 mm · raw-input arm (§7.6)", None),
        ("MindGlide, raw input", ("secondary_raw_arm", "mindglide-raw", "thick")),
        ("1 mm · secondary family", None),
        ("MindGlide", ("secondary", "mindglide", "iso")),
        ("WMH-SynthSeg", ("secondary", "wmhsynthseg", "iso")),
        ("LST-AI", ("secondary", "lstai", "iso")),
    ]
    # rows: 1 unit each, plus 0.45 unit of air above every group header after the first
    ys, y = [], 0.0
    for i, (_, key) in enumerate(rows):
        if key is None and i > 0:
            y += 0.45
        ys.append(y)
        y += 1.0
    n_units, row_mm, top = y, 4.1, 8.0
    plot_h = n_units * row_mm
    fig = fs.figure(fs.DOUBLE, top + plot_h + 11.0)
    ymm = lambda yy: top + (yy + 0.5) * row_mm  # noqa: E731  (row centre, mm from top)
    head_mm = top - 2.6

    data = {}
    for (label, key), yy in zip(rows, ys):
        if key is None:
            continue
        fam, tool, band = key
        data[yy] = {o: find(fam, tool=tool, vs="flames", outcome=o, band=band) for o in ("f1", "false_lesions")}
        data[yy]["tool"] = tool

    # row labels and sample sizes
    X_N = 37.5
    fs.text_mm(fig, X_N, head_mm, "Scans / patients", ha="right", va="center", fontsize=6.5, color=fs.INK2)
    for (label, key), yy in zip(rows, ys):
        if key is None:
            fs.text_mm(fig, 0, ymm(yy), label, va="center", fontsize=7, fontweight="bold")
            continue
        s = data[yy]["f1"]
        fs.text_mm(fig, 2.0, ymm(yy), label, va="center", fontsize=7)
        fs.text_mm(fig, X_N, ymm(yy), f"{s['n_scans']} / {s['n_clusters']}", ha="right", va="center", fontsize=7,
                   color=fs.INK2)

    panels = (dict(outcome="f1", x=41.0, w=31.0, margin=0.05, xlim=(-0.46, 0.08), ticks=(-0.4, -0.2, 0.0), dec=2,
                   xlabel="ΔF1 (tool − FLAMeS)", head="ΔF1 (95% CI)", letter="a"),
              dict(outcome="false_lesions", x=116.5, w=27.0, margin=1.0, xlim=(-7.0, 5.5), ticks=(-6, -3, 0, 3),
                   dec=1, xlabel="Δ false lesions per scan", head="Δ (95% CI)", letter="b"))
    fs.panel_label(fig, "a", 0, 0.4)
    for P in panels:
        if P["letter"] == "b":
            fs.panel_label(fig, "b", P["x"] - 3.5, 0.4)
        ax = fs.axes(fig, P["x"], top, P["w"], plot_h)
        ax.set_ylim(n_units - 0.5, -0.5)
        fs.band_v(ax, -P["margin"], P["margin"])
        fs.ref_vline(ax, 0, color=fs.AXIS, lw=0.5)
        ax.set_xlim(*P["xlim"])
        ax.set_xticks(P["ticks"])
        ax.set_xticklabels([fs.fnum(t, 1 if P["dec"] == 2 else 0) if t != 0 else "0" for t in P["ticks"]])
        ax.set_yticks([])
        fs.despine(ax, left=False)
        ax.set_xlabel(P["xlabel"])
        cells = []
        for yy, d in data.items():
            r, st = d[P["outcome"]], STYLE[d["tool"]]
            ax.plot(r["ci95"], [yy, yy], color=st["color"], lw=fs.LW_CI, zorder=2)
            ax.plot(r["ci90"], [yy, yy], color=tint(st["color"], 0.4), lw=fs.LW_CI_THICK, zorder=2)
            ax.plot(r["estimate"], yy, marker=st["marker"], color=st["color"], mec="white", mew=0.5, ms=4.6,
                    zorder=3, ls="none")
            cells.append((yy, r))
        # typeset table: estimate (95% CI) and Holm-adjusted p, decimal-aligned; 'to' because bounds are negative
        sep = " to " if any(v < 0 for _, r in cells for v in r["ci95"]) else "–"
        rows_txt = [fs.ci_cells(r["estimate"], *r["ci95"], nd=P["dec"], sep=sep)
                    + [pfmt(r["p_holm_registered_family"], r.get("registered_family_size", 6))] for _, r in cells]
        cols = [list(c) for c in zip(*rows_txt)]
        kinds = "ddcdd"   # estimate | (lower | to | upper) | p
        x0 = P["x"] + P["w"] + 2.5
        anchors, x_end = fs.table_layout(fig, x0, cols, kinds, [1.3, 0.9, 0.9, 2.4, 0])
        for (yy, _), cells_ in zip(cells, rows_txt):
            fs.table_row(fig, anchors, kinds, ymm(yy), cells_)
        fs.text_mm(fig, x0, head_mm, P["head"], va="center", fontsize=6.5, color=fs.INK2)
        fs.text_mm(fig, x_end, head_mm, r"$p_{\mathrm{Holm}}$", ha="right", va="center", fontsize=6.5,
                   color=fs.INK2)
    save(fig, "fig1_forest_vs_flames")


# ----------------------------------------------------------------------------- Figure 2: FP vs sensitivity
def fig2():
    order = ("ms3seg", "muslim", "pedims", "mslesseg", "openms")
    per = {(r["cohort"], r["tool"]): r for r in SUMM["per_cohort"]}
    fig = fs.figure(fs.DOUBLE, 101)
    L, T, PW, PH, GX, GY = 13.0, 5.5, 49.0, 38.0, 9.5, 11.5
    axs = []
    for i, c in enumerate(order):
        row, col = divmod(i, 3)
        ax = fs.axes(fig, L + col * (PW + GX), T + row * (PH + GY), PW, PH)
        axs.append(ax)
        for tool in ORDER:
            r = per.get((c, tool))
            if r is None:
                continue
            st = STYLE[tool]
            x, y = r["recall"], r["false_lesions"]
            ax.plot(x["ci95"], [y["estimate"]] * 2, color=st["color"], lw=fs.LW_CI, zorder=2)
            ax.plot([x["estimate"]] * 2, y["ci95"], color=st["color"], lw=fs.LW_CI, zorder=2)
            ax.plot(x["estimate"], y["estimate"], marker=st["marker"], color=st["color"], mec="white", mew=0.5,
                    ms=4.8, ls="none", zorder=3)
        name, mm = COHORT[c]
        fs.facet_label(ax, f"{name}", fontweight="bold")
        fs.facet_label(ax, f"{mm}", x=1.0, ha="right", color=fs.INK2)
        ax.set_xlim(0.1, 0.92)
        ax.set_ylim(0, 11.5)
        ax.set_xticks([0.2, 0.4, 0.6, 0.8])
        ax.set_yticks([0, 5, 10])
        if row == 1 or col == 2:
            ax.set_xlabel("Lesion-wise sensitivity")
        if col == 0:
            ax.set_ylabel("False lesions per scan")
        else:
            ax.set_yticklabels([])
    # key, in the free sixth position
    kx, ky = L + 2 * (PW + GX) + 2.0, T + (PH + GY) + 7.0
    for i, tool in enumerate(ORDER):
        st = STYLE[tool]
        y = ky + i * 5.0
        fig.lines.append(Line2D([fs.fx(fig, kx + 1.6)], [fs.fy(fig, y)], transform=fig.transFigure,
                                marker=st["marker"], color=st["color"], mec="white", mew=0.5, ms=5.2, ls="none"))
        fs.text_mm(fig, kx + 5.0, y, NAME[tool] + (" (5-fold ensemble)" if tool == "flames" else ""),
                   va="center", fontsize=7)
    save(fig, "fig2_false_lesions_vs_sensitivity")


# ----------------------------------------------------------------------------- Figure 3: small lesions
def fig3():
    bins = ("14-50", "50-200", "200-1000", ">=1000")
    blabel = ("14–50", "50–200", "200–1000", "≥1000")
    sb = {(r["band"], r["tool"], r["bin"]): r for r in SUMM["size_bins"]}
    fig = fs.figure(fs.DOUBLE, 61)
    L, T, PW, PH, GX = 12.0, 5.0, 79.0, 44.0, 10.0
    for p, (band, letter, head) in enumerate((("iso", "a", "1 mm isotropic"), ("thick", "b", "Thick slices (> 3 mm)"))):
        x0 = L + p * (PW + GX)
        ax = fs.axes(fig, x0, T, PW, PH)
        fs.panel_label(fig, letter, x0 - (11.5 if p == 0 else 4.0), 0.4)
        fs.facet_label(ax, head, x=0.62, ha="center", color=fs.INK2)
        tools = [t for t in ORDER if (band, t, bins[0]) in sb]
        k = len(tools)
        first = []
        for j, tool in enumerate(tools):
            st = STYLE[tool]
            dx = (j - (k - 1) / 2) * 0.075
            xs = [i + dx for i in range(len(bins))]
            est = [sb[(band, tool, b)]["estimate"] for b in bins]
            for xx, b in zip(xs, bins):
                ax.plot([xx, xx], sb[(band, tool, b)]["ci95"], color=st["color"], lw=fs.LW_CI, zorder=2)
            ax.plot(xs, est, color=st["color"], lw=fs.LW_DATA, zorder=2)
            ax.plot(xs, est, marker=st["marker"], color=st["color"], mec="white", mew=0.5, ms=4.4, ls="none", zorder=3)
            first.append((est[0], tool, xs[0]))
        # direct labels, inside the plot to the left of the smallest-lesion bin, spread so they never touch
        ylab = fs.spread([e for e, _, _ in first], 0.075, lo=0.03, hi=0.97)
        for (e, tool, x0_), yl in zip(first, ylab):
            ax.annotate(NAME[tool].replace(", raw input", " raw"), (x0_, e), xytext=(-0.42, yl), textcoords="data",
                        ha="right", va="center", fontsize=7, color=fs.INK,
                        arrowprops=dict(arrowstyle="-", lw=0.4, color=fs.GREY_MID, shrinkA=1.0, shrinkB=2.6))
        ax.set_xticks(range(len(bins)))
        ax.set_xticklabels(blabel)
        ax.set_xlim(-1.75, len(bins) - 0.6)
        ax.spines["bottom"].set_bounds(-0.3, len(bins) - 0.6)
        ax.set_ylim(0, 1.0)
        ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
        ax.set_yticklabels(["0", "0.25", "0.50", "0.75", "1.00"] if p == 0 else [])
        ax.set_xlabel("Expert lesion volume (mm³)")
        ax.xaxis.set_label_coords(((-0.3 + len(bins) - 0.6) / 2 + 1.75) / (len(bins) - 0.6 + 1.75), -0.15)
        if p == 0:
            ax.set_ylabel("Expert lesions detected")
    save(fig, "fig3_detection_by_lesion_size")


# ----------------------------------------------------------------------------- Figure 4: degradation
def per_scan_f1():
    """Per-scan lesion-wise F1 behind Figure 4a: the scans of the per-band summary (primary variant, run ok;
    FLAMeS without the 20 Ljubljana scans it was trained on). Counts are asserted against summary.json."""
    out = {}
    with gzip.open(os.path.join(RES, "per_scan.csv.gz"), "rt", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["variant"] != "primary" or r["status"] != "ok" or r["contaminated"] or r["f1"] == "":
                continue
            out.setdefault((r["band"], r["tool"]), []).append(float(r["f1"]))
    for pb in SUMM["per_band"]:
        if pb["band"] in ("iso", "thick"):
            assert len(out[(pb["band"], pb["tool"])]) == pb["f1"]["n_scans"], (pb["band"], pb["tool"])
    return out


def _pair_marker(ax, x, y, st, filled):
    ax.plot(x, y, marker=st["marker"], ms=5.0, mew=0.6 if filled else 0.9, ls="none", zorder=4, color=st["color"],
            mfc=st["color"] if filled else "white", mec="white" if filled else st["color"])


def fig4():
    pb = {(r["band"], r["tool"]): r for r in SUMM["per_band"]}
    dots = per_scan_f1()
    deg = {r["tool"]: r for r in COMP["secondary"] if "contrast" in r}
    # rows: each tool has a 1 mm sub-row (open marker) and a > 3 mm sub-row (filled marker)
    gap = 0.75
    rows, y = {}, 0.0
    for tool in ORDER:
        rows[tool] = (y, y + 1.0)
        y += 2.0 + gap
    ylim = (y - gap - 0.5, -0.5)
    unit_mm, top = 3.0, 7.0
    plot_h = (ylim[0] - ylim[1]) * unit_mm
    fig = fs.figure(fs.DOUBLE, top + plot_h + 10.5)

    def ymm(v):
        return top + (v - ylim[1]) * unit_mm

    for tool in ORDER:
        y1, y2 = rows[tool]
        have = [yy for b, yy in (("iso", y1), ("thick", y2)) if (b, tool) in pb]
        fs.text_mm(fig, 0, ymm(sum(have) / len(have)), NAME[tool], va="center", fontsize=7)
        for b, yy in (("iso", y1), ("thick", y2)):
            if (b, tool) in pb:
                fs.text_mm(fig, 33.0, ymm(yy), "1 mm" if b == "iso" else "> 3 mm", ha="right", va="center",
                           fontsize=6.5, color=fs.INK2)
    # ---- a: per-scan F1 (dots), cohort-weighted mean with 95% CI
    ax = fs.axes(fig, 36.0, top, 62.0, plot_h)
    fs.panel_label(fig, "a", 0, 0.4)
    ax.set_ylim(*ylim)
    for i, tool in enumerate(ORDER):
        st = STYLE[tool]
        pts = []
        for b, yy in (("iso", rows[tool][0]), ("thick", rows[tool][1])):
            if (b, tool) not in pb:
                continue
            v = dots[(b, tool)]
            ax.scatter(v, yy + fs.jitter(len(v), 0.62, phase=0.37 * i + (0.5 if b == "thick" else 0)), s=1.4,
                       color=st["color"], alpha=0.3, lw=0, zorder=1, rasterized=True)
            r = pb[(b, tool)]["f1"]
            pts.append((r["estimate"], yy))
            ax.plot(r["ci95"], [yy, yy], color=fs.INK, lw=fs.LW_CI, zorder=3)
            _pair_marker(ax, r["estimate"], yy, st, b == "thick")
        if len(pts) == 2:
            ax.plot([p[0] for p in pts], [p[1] for p in pts], color=fs.INK, lw=0.6, zorder=2)
    ax.set_xlim(0, 1)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xticklabels(["0", "0.25", "0.50", "0.75", "1.00"])
    ax.set_yticks([])
    fs.despine(ax, left=False)
    ax.set_xlabel("Lesion-wise F1")
    # ---- b: paired difference from FLAMeS in each band; the slope is the degradation contrast
    bx = fs.axes(fig, 107.0, top, 36.0, plot_h)
    fs.panel_label(fig, "b", 102.0, 0.4)
    bx.set_ylim(*ylim)
    fs.ref_vline(bx, 0, color=fs.AXIS, lw=0.5)
    bx.annotate("reference", (0, sum(rows["flames"]) / 2), xytext=(-3, 0), textcoords="offset points", ha="right",
                va="center", fontsize=6.5, color=fs.INK2)
    for tool in ORDER[1:]:
        st = STYLE[tool]
        pts = []
        for b, fam, yy in (("iso", "secondary", rows[tool][0]), ("thick", "primary", rows[tool][1])):
            f = "secondary_raw_arm" if tool == "mindglide-raw" else fam
            try:
                r = find(f, tool=tool, vs="flames", outcome="f1", band=b)
            except KeyError:
                continue
            if r.get("estimate") is None:
                continue
            pts.append((r["estimate"], yy))
            bx.plot(r["ci95"], [yy, yy], color=fs.INK, lw=fs.LW_CI, zorder=3)
            _pair_marker(bx, r["estimate"], yy, st, b == "thick")
        if len(pts) == 2:
            bx.plot([p[0] for p in pts], [p[1] for p in pts], color=fs.INK, lw=0.6, zorder=2)
    bx.set_xlim(-0.5, 0.03)
    bx.set_xticks([-0.4, -0.2, 0])
    bx.set_xticklabels([fs.fnum(-0.4, 1), fs.fnum(-0.2, 1), "0"])
    bx.set_yticks([])
    fs.despine(bx, left=False)
    bx.set_xlabel("ΔF1 vs FLAMeS (paired)")
    # ---- degradation contrast (Δ > 3 mm − Δ 1 mm): registered secondary tests, typeset beside each tool
    x0 = 148.0
    fs.text_mm(fig, x0, top - 2.6, "Contrast (95% CI)", va="center", fontsize=6.5, color=fs.INK2)
    con = [t for t in ("mindglide", "wmhsynthseg") if deg[t]["estimate"] is not None]
    sep = " to " if any(v < 0 for t in con for v in deg[t]["ci95"]) else "–"
    cells = [fs.ci_cells(deg[t]["estimate"], *deg[t]["ci95"], nd=3, sep=sep) for t in con]
    anchors, _ = fs.table_layout(fig, x0, [list(c) for c in zip(*cells)], "ddcd", [1.2, 0.8, 0.8, 0])
    for t, c in zip(con, cells):
        y1, y2 = rows[t]
        fs.table_row(fig, anchors, "ddcd", ymm(y1), c)
        fs.text_mm(fig, x0, ymm(y2), r"$p_{\mathrm{Holm}}$ " + pfmt(deg[t]["p_holm_registered_family"], 11),
                   va="center", fontsize=6.5, color=fs.INK2)
    if deg["samseg"]["estimate"] is None:
        fs.text_mm(fig, x0, ymm(sum(rows["samseg"]) / 2), "not run", va="center", fontsize=6.5, color=fs.INK2)
    save(fig, "fig4_degradation_1mm_to_thick")


if __name__ == "__main__":
    fig1()
    fig2()
    fig3()
    fig4()
