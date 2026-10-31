"""Paper F manuscript figures - generated ONLY from the stored, pre-registered results (no images, no cloud).

Inputs : ../results/comparisons.json, ../results/summary.json
Outputs: figures/fig{1..4}_*.pdf (vector) and .png (300 dpi)

    python -I research/paper_f/manuscript/make_figures.py

Colour: Okabe-Ito hues (colour-blind safe; validated with the dataviz palette checker - all checks pass,
contrast relieved by direct labels and markers). Every tool also has its own marker shape, so identity
never rests on colour alone. FLAMeS (the reference) is neutral ink.
"""
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(os.path.dirname(HERE), "results")
OUT = os.path.join(HERE, "figures")
os.makedirs(OUT, exist_ok=True)

COMP = json.load(open(os.path.join(RES, "comparisons.json"), encoding="utf-8"))
SUMM = json.load(open(os.path.join(RES, "summary.json"), encoding="utf-8"))

INK, MUTED, GRID = "#1f1f1f", "#6b6b6b", "#d9d9d9"
STYLE = {  # fixed order, never cycled
    "flames":        {"name": "FLAMeS (5-fold ensemble)", "short": "FLAMeS",       "c": "#222222", "m": "o"},
    "mindglide":     {"name": "MindGlide",                "short": "MindGlide",    "c": "#0072B2", "m": "s"},
    "mindglide-raw": {"name": "MindGlide, raw input",     "short": "MindGlide raw", "c": "#56B4E9", "m": "D"},
    "wmhsynthseg":   {"name": "WMH-SynthSeg",             "short": "WMH-SynthSeg", "c": "#E69F00", "m": "^"},
    "samseg":        {"name": "SAMSEG (tier C)",          "short": "SAMSEG",       "c": "#D55E00", "m": "v"},
    "lstai":         {"name": "LST-AI",                   "short": "LST-AI",       "c": "#CC79A7", "m": "P"},
}
COHORT = {"mslesseg": "MSLesSeg (1 mm)", "openms": "Ljubljana (1 mm)", "ms3seg": "MS3SEG (6.0–8.1 mm)",
          "muslim": "Muslim et al. (4.9–8.3 mm)", "pedims": "PediMS (3.9 mm)"}
MM = 1 / 25.4

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 7.5, "axes.titlesize": 8, "axes.labelsize": 7.5,
    "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7, "axes.edgecolor": MUTED,
    "axes.linewidth": 0.6, "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK,
    "ytick.labelcolor": INK, "axes.labelcolor": INK, "text.color": INK, "axes.spines.top": False,
    "axes.spines.right": False, "pdf.fonttype": 42, "svg.fonttype": "none", "savefig.dpi": 300,
})


def save(fig, name):
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(OUT, f"{name}.{ext}"), bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", name)


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
    return f"{p:.3f}" if p < 0.995 else "1.00"


# ----------------------------------------------------------------------------- Figure 1: forest plot
def fig1():
    rows = [
        ("Thick slices (> 3 mm): primary family", None),
        ("MindGlide", ("primary", "mindglide", "thick")),
        ("WMH-SynthSeg", ("primary", "wmhsynthseg", "thick")),
        ("SAMSEG (tier C)", ("primary", "samseg", "thick")),
        ("Thick slices: raw-input arm (7.6)", None),
        ("MindGlide, raw input", ("secondary_raw_arm", "mindglide-raw", "thick")),
        ("1 mm isotropic: secondary family", None),
        ("MindGlide", ("secondary", "mindglide", "iso")),
        ("WMH-SynthSeg", ("secondary", "wmhsynthseg", "iso")),
        ("LST-AI", ("secondary", "lstai", "iso")),
    ]
    fig, axs = plt.subplots(1, 4, figsize=(183 * MM, 88 * MM), sharey=True,
                            gridspec_kw={"wspace": 0.03, "width_ratios": [0.9, 1.2, 0.9, 1.1]})
    panels = (("f1", "Δ lesion-wise F1\n(tool − FLAMeS)", 0.05, (-0.46, 0.08), 2),
              ("false_lesions", "Δ false lesions per scan\n(tool − FLAMeS)", 1.0, (-7.0, 5.5), 1))
    n = len(rows)
    for (ax, tx), (outcome, xlabel, margin, xlim, dec) in zip(((axs[0], axs[1]), (axs[2], axs[3])), panels):
        ax.axvspan(-margin, margin, color="#ececec", zorder=0, lw=0)
        ax.axvline(0, color=MUTED, lw=0.7, zorder=1)
        tx.axis("off")
        tx.set_xlim(0, 1)
        tx.text(0.03, n - 0.35, "Δ [95% CI]", fontsize=6.1, color=MUTED, va="center", fontweight="bold")
        tx.text(0.97, n - 0.35, "p$_{Holm}$", fontsize=6.1, color=MUTED, va="center", ha="right", fontweight="bold")
        for i, (label, key) in enumerate(rows):
            y = n - 1 - i
            if key is None:
                continue
            fam, tool, band = key
            r = find(fam, tool=tool, vs="flames", outcome=outcome, band=band)
            st = STYLE[tool]
            ax.plot(r["ci95"], [y, y], color=st["c"], lw=1.0, solid_capstyle="round", zorder=2)
            ax.plot(r["ci90"], [y, y], color=st["c"], lw=3.2, solid_capstyle="round", alpha=0.5, zorder=2)
            ax.plot(r["estimate"], y, marker=st["m"], color=st["c"], mec="white", mew=0.6, ms=6.5, zorder=3)
            f = "{:+." + str(dec) + "f}"
            txt = (f.format(r["estimate"]) + " [" + f.format(r["ci95"][0]) + ", " + f.format(r["ci95"][1]) + "]")
            tx.text(0.03, y, txt.replace("-", "−"), fontsize=6.1, va="center")
            tx.text(0.97, y, pfmt(r["p_holm_registered_family"], r.get("registered_family_size", 6)),
                    fontsize=6.1, va="center", ha="right")
        ax.set_xlim(*xlim)
        ax.set_xlabel(xlabel)
        ax.grid(axis="x", color=GRID, lw=0.4)
        ax.set_axisbelow(True)
        ax.tick_params(axis="y", length=0)
        ax.spines["left"].set_visible(False)
    labels = []
    for label, key in reversed(rows):
        if key is None:
            labels.append(label)
        else:
            fam, tool, band = key
            s = find(fam, tool=tool, vs="flames", outcome="f1", band=band)
            labels.append(f"{label}  ({s['n_scans']} / {s['n_clusters']})")
    axs[0].set_yticks(range(n))
    axs[0].set_yticklabels(labels)
    for t, (label, key) in zip(axs[0].get_yticklabels(), reversed(rows)):
        if key is None:
            t.set_fontweight("bold")
            t.set_color(MUTED)
    axs[0].set_ylim(-0.7, n + 0.1)
    axs[0].text(-0.02, 1.0, "A", transform=axs[0].transAxes, fontsize=10, fontweight="bold", va="bottom", ha="right")
    axs[2].text(-0.02, 1.0, "B", transform=axs[2].transAxes, fontsize=10, fontweight="bold", va="bottom", ha="right")
    fig.text(0.01, -0.06, "Rows: comparison (scans / patients). Shaded: pre-registered equivalence margin (±0.05 F1; "
             "±1 false lesion per scan). Thin line: 95% CI; thick line: 90% CI (equivalence criterion).\n"
             "Patient-cluster bootstrap stratified by cohort, 10,000 replicates; Holm over the registered family size "
             "(tests not run count as p = 1). '< 0.002' / '< 0.003': no replicate crossed zero.",
             fontsize=6.0, color=MUTED, ha="left", va="top")
    save(fig, "fig1_forest_vs_flames")


# ----------------------------------------------------------------------------- Figure 2: FP vs sensitivity
def fig2():
    order = ("ms3seg", "muslim", "pedims", "mslesseg", "openms")
    fig, axs = plt.subplots(2, 3, figsize=(183 * MM, 118 * MM), sharex=True, sharey=True,
                            gridspec_kw={"hspace": 0.32, "wspace": 0.10})
    flat = axs.ravel()
    per = {(r["cohort"], r["tool"]): r for r in SUMM["per_cohort"]}
    for ax, c in zip(flat, order):
        for tool in STYLE:
            r = per.get((c, tool))
            if r is None:
                continue
            st = STYLE[tool]
            x, y = r["recall"], r["false_lesions"]
            ax.errorbar(x["estimate"], y["estimate"],
                        xerr=[[x["estimate"] - x["ci95"][0]], [x["ci95"][1] - x["estimate"]]],
                        yerr=[[y["estimate"] - y["ci95"][0]], [y["ci95"][1] - y["estimate"]]],
                        fmt=st["m"], color=st["c"], mec="white", mew=0.6, ms=6, elinewidth=0.8, capsize=0, zorder=3)
        ax.set_title(f"{COHORT[c]}", loc="left", fontsize=7.5)
        ax.grid(color=GRID, lw=0.4)
        ax.set_axisbelow(True)
        ax.set_xlim(0.1, 0.92)
        ax.set_ylim(0, 11.5)
    for ax in axs[1, :2]:
        ax.set_xlabel("Lesion-wise sensitivity (recall)")
    axs[0, 2].tick_params(labelbottom=True)
    axs[0, 2].set_xlabel("Lesion-wise sensitivity (recall)")
    for ax in axs[:, 0]:
        ax.set_ylabel("False lesions per scan")
    leg = flat[5]
    leg.axis("off")
    handles = [Line2D([0], [0], marker=STYLE[t]["m"], color=STYLE[t]["c"], mec="white", ls="none", ms=7,
                      label=STYLE[t]["name"]) for t in STYLE]
    leg.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.0, 1.04), frameon=False, title="Tool",
               title_fontsize=7.5, alignment="left")
    leg.text(0.03, 0.0, "Better = lower right.\nError bars: 95% patient-cluster bootstrap CI.\n"
             "Ljubljana: FLAMeS on the 10 scans not in its\ntraining; other tools on all 30.\n"
             "MS3SEG: SAMSEG on the 50 odd-id scans (tier C).", transform=leg.transAxes, fontsize=6.2,
             color=MUTED, va="bottom")
    save(fig, "fig2_false_lesions_vs_sensitivity")


# ----------------------------------------------------------------------------- Figure 3: small lesions
def fig3():
    bins = ("14-50", "50-200", "200-1000", ">=1000")
    blabel = ("14–50", "50–200", "200–1000", "≥ 1000")
    fig, axs = plt.subplots(1, 2, figsize=(183 * MM, 72 * MM), sharey=True, gridspec_kw={"wspace": 0.08})
    sb = {(r["band"], r["tool"], r["bin"]): r for r in SUMM["size_bins"]}
    for ax, band, title in zip(axs, ("iso", "thick"), ("1 mm isotropic band", "Thick-slice band (> 3 mm)")):
        tools = [t for t in STYLE if (band, t, bins[0]) in sb]
        k = len(tools)
        for j, tool in enumerate(tools):
            st = STYLE[tool]
            dx = (j - (k - 1) / 2) * 0.09
            xs = [i + dx for i in range(len(bins))]
            est = [sb[(band, tool, b)]["estimate"] for b in bins]
            lo = [sb[(band, tool, b)]["estimate"] - sb[(band, tool, b)]["ci95"][0] for b in bins]
            hi = [sb[(band, tool, b)]["ci95"][1] - sb[(band, tool, b)]["estimate"] for b in bins]
            ax.plot(xs, est, color=st["c"], lw=1.2, zorder=2)
            ax.errorbar(xs, est, yerr=[lo, hi], fmt=st["m"], color=st["c"], mec="white", mew=0.5, ms=5,
                        elinewidth=0.7, capsize=0, zorder=3, label=st["name"])
        ax.set_xticks(range(len(bins)))
        ax.set_xticklabels(blabel)
        ax.set_xlabel("Expert lesion volume (mm³)")
        ax.set_title(title, loc="left")
        ax.set_ylim(0, 1.03)
        ax.grid(axis="y", color=GRID, lw=0.4)
        ax.set_axisbelow(True)
    axs[0].set_ylabel("Proportion of expert lesions detected")
    handles = [Line2D([0], [0], marker=STYLE[t]["m"], color=STYLE[t]["c"], mec="white", ms=6, lw=1.2,
                      label=STYLE[t]["name"]) for t in STYLE]
    fig.legend(handles=handles, loc="lower center", ncol=6, frameon=False, fontsize=6.5,
               bbox_to_anchor=(0.5, -0.1), handletextpad=0.4, columnspacing=1.2)
    save(fig, "fig3_detection_by_lesion_size")


# ----------------------------------------------------------------------------- Figure 4: degradation
NUDGE = {"mindglide": 0.013, "mindglide-raw": -0.013}


def fig4():
    pb = {(r["band"], r["tool"]): r for r in SUMM["per_band"]}
    fig, axs = plt.subplots(1, 2, figsize=(183 * MM, 76 * MM), gridspec_kw={"wspace": 0.32})
    ax = axs[0]
    xs = {"iso": 0, "thick": 1}
    for tool in STYLE:
        st = STYLE[tool]
        pts = [(xs[b], pb[(b, tool)]["f1"]) for b in ("iso", "thick") if (b, tool) in pb]
        if len(pts) == 2:
            ax.plot([p[0] for p in pts], [p[1]["estimate"] for p in pts], color=st["c"], lw=1.2, zorder=2)
        for x, r in pts:
            ax.errorbar(x, r["estimate"], yerr=[[r["estimate"] - r["ci95"][0]], [r["ci95"][1] - r["estimate"]]],
                        fmt=st["m"], color=st["c"], mec="white", mew=0.5, ms=6, elinewidth=0.8, capsize=0, zorder=3)
        last = pts[-1]
        ha = "left" if last[0] == 1 else "right"
        ax.text(1.07 if last[0] == 1 else -0.07, last[1]["estimate"] + NUDGE.get(tool, 0.0), st["short"],
                ha=ha, va="center", fontsize=6.5, color=INK)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["1 mm\n(MSLesSeg,\nLjubljana)", "> 3 mm\n(MS3SEG, Muslim,\nPediMS)"])
    ax.set_xlim(-0.55, 1.55)
    ax.set_ylim(0.25, 0.85)
    ax.set_ylabel("Lesion-wise F1 (cohort-weighted mean)")
    ax.grid(axis="y", color=GRID, lw=0.4)
    ax.set_axisbelow(True)
    ax.set_title("A  Absolute lesion-wise F1 by band", loc="left", fontweight="bold")
    # adjust overlapping labels: nudge manually where needed
    ax = axs[1]
    ax.axhline(0, color=MUTED, lw=0.7)
    for tool in ("mindglide", "wmhsynthseg", "lstai", "samseg", "mindglide-raw"):
        st = STYLE[tool]
        pts = []
        for b, fam in (("iso", "secondary"), ("thick", "primary")):
            f = "secondary_raw_arm" if tool == "mindglide-raw" else fam
            try:
                r = find(f, tool=tool, vs="flames", outcome="f1", band=b)
            except KeyError:
                continue
            if r.get("estimate") is None:
                continue
            pts.append((xs[b], r))
        if len(pts) == 2:
            ax.plot([p[0] for p in pts], [p[1]["estimate"] for p in pts], color=st["c"], lw=1.2, zorder=2)
        for x, r in pts:
            ax.errorbar(x, r["estimate"], yerr=[[r["estimate"] - r["ci95"][0]], [r["ci95"][1] - r["estimate"]]],
                        fmt=st["m"], color=st["c"], mec="white", mew=0.5, ms=6, elinewidth=0.8, capsize=0, zorder=3)
        last = pts[-1]
        ax.text(1.07 if last[0] == 1 else -0.07, last[1]["estimate"] + NUDGE.get(tool, 0.0) * 1.6, st["short"],
                ha="left" if last[0] == 1 else "right", va="center", fontsize=6.5)
    deg = {r["tool"]: r for r in COMP["secondary"] if "contrast" in r}
    lines = []
    for tool in ("mindglide", "wmhsynthseg"):
        r = deg[tool]
        lines.append(f"{STYLE[tool]['short']}: {r['estimate']:+.3f} [{r['ci95'][0]:+.3f}, {r['ci95'][1]:+.3f}], "
                     .replace("-", "−") + f"p$_{{Holm}}$ {pfmt(r['p_holm_registered_family'], 11)}")
    ax.text(0.02, 0.03, "Degradation contrast (Δ thick − Δ 1 mm):\n" + "\n".join(lines) +
            "\nSAMSEG: not run (tier C is thick-only)", transform=ax.transAxes, fontsize=6.2, va="bottom", color=INK)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["1 mm", "> 3 mm"])
    ax.set_xlim(-0.55, 1.55)
    ax.set_ylim(-0.62, 0.05)
    ax.set_ylabel("Δ lesion-wise F1 vs FLAMeS (paired)")
    ax.grid(axis="y", color=GRID, lw=0.4)
    ax.set_axisbelow(True)
    ax.set_title("B  Paired difference from FLAMeS", loc="left", fontweight="bold")
    save(fig, "fig4_degradation_1mm_to_thick")


if __name__ == "__main__":
    fig1()
    fig2()
    fig3()
    fig4()
