#!/usr/bin/env python3
"""Make every manuscript figure from ``../data/extracted_results.json`` (written by extract_results.py).

No number is computed here except what is drawn: point estimates and confidence intervals are taken
from the records as stored. Colours: Okabe-Ito subset (#0072B2, #D55E00, #009E73, #CC79A7), checked
with a CVD validator; every series also has its own marker shape and a text label, so identity never
depends on colour alone. Output: ``../figures/fig*.png`` (300 dpi) and ``.pdf`` (vector).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.ticker  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

def fmt(x: float, nd: int = 3, sign: bool = False) -> str:
    """Round half-up on the stored decimal value (as the text reports it), not on the binary float."""
    q = Decimal(repr(x)).quantize(Decimal(1).scaleb(-nd), rounding=ROUND_HALF_UP)
    out = f"{q:f}"
    if out.startswith("-") and q == 0:
        out = out[1:]
    return ("+" + out) if (sign and not out.startswith("-")) else out


HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data" / "extracted_results.json"
FIG = HERE.parent / "figures"

BLUE, VERM, GREEN, PURPLE = "#0072B2", "#D55E00", "#009E73", "#CC79A7"
INK, MUTED, GRID = "#222222", "#666666", "#DDDDDD"
ARM_STYLE = {  # arm -> (label, colour, marker)
    "R": ("R: original FLAMeS fold 0", BLUE, "o"),
    "A": ("A: fine-tuned + thick-slice augmentation", VERM, "s"),
    "B": ("B: fine-tuned, no augmentation (control)", GREEN, "D"),
    "E": ("E: original 5-fold ensemble (context)", PURPLE, "^"),
}

plt.rcParams.update({
    "font.size": 8, "axes.titlesize": 8.5, "axes.labelsize": 8, "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5, "legend.fontsize": 7.5, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
    "xtick.color": MUTED, "ytick.color": INK, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "savefig.bbox": "tight", "savefig.dpi": 300, "pdf.fonttype": 42,
})


def save(fig, name: str) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(FIG / f"{name}.{ext}", metadata={"CreationDate": None} if ext == "pdf" else None)
    plt.close(fig)
    print("wrote", FIG / f"{name}.png")


def forest(ax, rows, ref_lines, xlabel, title, xlim=None):
    """rows: list of (label, point, (lo, hi) or None, colour, marker)."""
    n = len(rows)
    for i, (lab, pt, ci, col, mk) in enumerate(rows):
        y = n - 1 - i
        if ci is not None:
            ax.plot(ci, [y, y], color=col, lw=1.6, solid_capstyle="round")
        ax.plot(pt, y, marker=mk, color=col, ms=6.5, mec="white", mew=0.8, ls="none", zorder=3)
        txt = fmt(pt, 3, True) if ci is None else f"{fmt(pt, 3, True)} [{fmt(ci[0], 3, True)}, {fmt(ci[1], 3, True)}]"
        if "ratio" in xlabel:
            txt = fmt(pt, 2) if ci is None else f"{fmt(pt, 2)} [{fmt(ci[0], 2)}, {fmt(ci[1], 2)}]"
        ax.annotate(txt, (1.0, y), xycoords=("axes fraction", "data"), xytext=(4, 0),
                    textcoords="offset points", va="center", ha="left", fontsize=6.8, color=INK)
    for x, style, lab, ha in ref_lines:
        ax.axvline(x, color=MUTED, lw=0.9, ls=style, zorder=1)
        ax.annotate(lab, (x, n - 0.35), xytext=({"left": 2, "right": -2, "center": 0}[ha], 0),
                    textcoords="offset points", fontsize=6.5, color=MUTED, ha=ha, va="bottom")
    ax.set_yticks(range(n))
    ax.set_yticklabels([r[0] for r in rows][::-1])
    ax.set_ylim(-0.6, n + 0.2)
    ax.set_xlabel(xlabel)
    ax.set_title(title, loc="left", fontweight="bold")
    ax.grid(axis="y", visible=False)
    if xlim:
        ax.set_xlim(*xlim)


# ---------------------------------------------------------------------------- figure 1
def fig1(d):
    ft = d["flames_thick"]

    def r(lab, key, col, mk, field="delta_f1"):
        v = ft[key][field]
        return (lab, v[0], tuple(v[1]), col, mk)

    def site(lab, s, field):
        v = ft["H1_by_site"][s][field]
        return (lab, v[0], tuple(v[1]), VERM, "s")

    f1_rows = [
        r("H1  A vs R, pooled thick sites (179 scans)", "H1", VERM, "s"),
        site("   MS3SEG (100)", "ms3seg", "delta_f1"),
        site("   Muslim (51)", "muslim", "delta_f1"),
        site("   PediMS (28 scans, 9 children)", "pedims", "delta_f1"),
        r("S6  A vs R, strict matching IoU >= 0.10", "S6_strict", VERM, "s"),
        r("S6  A vs R, without PediMS P9", "S6_without_pedims_P9", VERM, "s"),
        r("B vs R (fine-tuning, no augmentation)", "B_vs_R_thick", GREEN, "D"),
        r("H3  A vs B (augmentation effect)", "S3_A_vs_B", MUTED, "o"),
        r("S4  A vs E (5-fold ensemble)", "S4_A_vs_E", PURPLE, "^"),
    ]
    fp_keys = ["H1", ("ms3seg",), ("muslim",), ("pedims",), "S6_strict", "S6_without_pedims_P9",
               "B_vs_R_thick", "S3_A_vs_B", "S4_A_vs_E"]
    fp_rows = []
    for (lab, _, _, col, mk), k in zip(f1_rows, fp_keys):
        v = ft["H1_by_site"][k[0]]["fp_ratio"] if isinstance(k, tuple) else ft[k]["fp_ratio"]
        fp_rows.append((lab, v[0], tuple(v[1]), col, mk))

    h2 = ft["H2"]
    h2_rows = [
        ("pooled 1-mm sites, delta Dice (32 scans)", h2["delta_dice"][0], tuple(h2["delta_dice"][1]), VERM, "s"),
        ("pooled 1-mm sites, delta F1", h2["delta_f1"][0], tuple(h2["delta_f1"][1]), VERM, "s"),
        ("Ljubljana-10 only, delta Dice (point)", h2["ljubljana_delta_dice"], None, VERM, "s"),
        ("Ljubljana-10 only, delta F1 (point)", h2["ljubljana_delta_f1"], None, VERM, "s"),
    ]

    fig = plt.figure(figsize=(7.4, 6.4))
    gs = fig.add_gridspec(2, 2, height_ratios=[9, 4.2], width_ratios=[1, 1], hspace=0.55, wspace=1.05)
    ax1 = fig.add_subplot(gs[0, 0])
    forest(ax1, f1_rows, [(0, "-", "0", "right"), (0.03, "--", "+0.03 SESOI", "left")],
           "difference in mean per-scan lesion-wise F1", "a  Lesion-wise F1, thick-slice sites", (-0.06, 0.08))
    ax1.xaxis.set_major_locator(matplotlib.ticker.MultipleLocator(0.05))
    ax2 = fig.add_subplot(gs[0, 1])
    forest(ax2, fp_rows, [(1.0, "-", "1", "right"), (1.10, "--", "1.10 margin", "left")],
           "ratio of mean false lesions per scan", "b  False lesions, thick-slice sites", (0.5, 1.25))
    ax2.set_yticklabels([""] * len(fp_rows))
    ax3 = fig.add_subplot(gs[1, :])
    forest(ax3, h2_rows, [(0, "-", "", "left"), (-0.02, "--", "-0.02 Dice", "left"), (-0.03, ":", "-0.03 F1", "right")],
           "difference A - R", "c  H2: non-inferiority at ~1 mm (A vs R)", (-0.25, 0.08))
    fig.text(0.0, -0.02, "Points: estimates; bars: paired patient-bootstrap 95 % CI (B = 10 000). "
             "SESOI = pre-registered smallest effect of interest. Source: 2026-10-23_flames_thick_results.json.",
             fontsize=6.5, color=MUTED)
    save(fig, "fig1_flames_thick_primary")


# ---------------------------------------------------------------------------- figure 2
def fig2(d):
    s2 = d["flames_thick"]["S2_by_site"]
    sites = [("ms3seg", "MS3SEG\n(6.0-8.1 mm)"), ("muslim", "Muslim\n(4.9-8.3 mm)"),
             ("pedims", "PediMS\n(3.9 mm)"), ("openms", "Ljubljana-10\n(3D, ~1 mm)"),
             ("mslesseg", "MSLesSeg test\n(in-domain for A, B)")]
    metrics = [("f1", "lesion-wise F1"), ("fp", "false lesions per scan"), ("dice", "voxel Dice"),
               ("sens", "lesion sensitivity")]
    fig, axes = plt.subplots(1, 4, figsize=(7.4, 3.0), sharey=True)
    offs = {"R": -0.24, "E": -0.08, "A": 0.08, "B": 0.24}
    for ax, (m, mlab) in zip(axes, metrics):
        for j, (s, _) in enumerate(sites):
            y = len(sites) - 1 - j
            for arm in ("R", "E", "A", "B"):
                lab, col, mk = ARM_STYLE[arm]
                ax.plot(s2[s][arm][m], y + offs[arm], marker=mk, color=col, ms=5.5, mec="white", mew=0.6,
                        ls="none", label=lab if (j == 0 and m == "f1") else None)
        ax.set_title(mlab, loc="left")
        ax.grid(axis="y", visible=False)
    axes[0].set_yticks(range(len(sites)))
    axes[0].set_yticklabels([s[1] for s in sites][::-1])
    for ax in axes:
        ax.axhline(1.5, color=GRID, lw=0.8)
    fig.legend(loc="lower center", ncol=2, frameon=False, bbox_to_anchor=(0.5, -0.12))
    fig.text(0.0, -0.17, "Means over scans (point estimates; the pre-registered code does not bootstrap S2). "
             "Below the line: ~1-mm sites (H2). Source: S2_by_site, 2026-10-23_flames_thick_results.json.",
             fontsize=6.5, color=MUTED)
    save(fig, "fig2_flames_thick_per_site")


# ---------------------------------------------------------------------------- figure 3
def fig3(d):
    s1 = d["flames_thick"]["S1_size"]
    bands = [("B1", "B1  slice spacing <= 1.5 mm\nLjubljana-10 + MSLesSeg test (32 scans)"),
             ("B2", "B2  1.5-4.5 mm\nPediMS (28 scans)"),
             ("B3", "B3  4.5-6.5 mm\nMuslim 45 + MS3SEG 31 scans"),
             ("B4", "B4  > 6.5 mm\nMS3SEG 69 + Muslim 6 scans")]
    bins = ["[3,14)", "[14,50)", "[50,150)", "[150,500)", ">=500"]
    offs = {"R": -0.24, "E": -0.08, "A": 0.08, "B": 0.24}
    fig, axes2 = plt.subplots(2, 2, figsize=(7.0, 5.4), sharey=True, gridspec_kw={"hspace": 0.55, "wspace": 0.12})
    axes = axes2.ravel()
    for ax, (b, title) in zip(axes, bands):
        for arm in ("R", "E", "A", "B"):
            lab, col, mk = ARM_STYLE[arm]
            rec = {x["bin"]: x for x in s1[f"{b}|{arm}"]["bins"]}
            xs = [i + offs[arm] for i in range(len(bins))]
            ys = [rec[k]["sens"] for k in bins]
            lo = [rec[k]["sens"] - rec[k]["ci"][0] for k in bins]
            hi = [rec[k]["ci"][1] - rec[k]["sens"] for k in bins]
            ax.errorbar(xs, ys, yerr=[lo, hi], fmt=mk, color=col, ms=4.2, mec="white", mew=0.5, elinewidth=1.0,
                        capsize=0, label=lab if b == "B1" else None)
        for h in (0.5, 0.8):
            ax.axhline(h, color=MUTED, lw=0.8, ls="--")
        ax.set_xticks(range(len(bins)))
        ax.set_xticklabels(["3-14", "14-50", "50-150", "150-500", ">=500"])
        ax.set_title(title, loc="left", fontsize=7.6, fontweight="bold")
        ax.set_xlabel("expert lesion volume (mm³)")
        ax.set_ylim(0, 1.02)
        ax.grid(axis="x", visible=False)
    axes[0].set_ylabel("detection sensitivity")
    axes[2].set_ylabel("detection sensitivity")
    fig.legend(loc="lower center", ncol=2, frameon=False, bbox_to_anchor=(0.5, -0.06))
    fig.text(0.0, -0.09, "Pooled expert lesions per band; bars: patient-bootstrap 95 % CI (2 000 draws, as coded before "
             "any map existed). Dashed: 50 % and 80 %. Source: S1_size, 2026-10-23_flames_thick_results.json.",
             fontsize=6.5, color=MUTED)
    save(fig, "fig3_flames_thick_size")


# ---------------------------------------------------------------------------- figure 4
def fig4(d):
    v3, v31, v32 = d["v3"], d["v31"], d["v32"]
    NOTRAIN, LEARN, PROBE = BLUE, VERM, PURPLE

    def a(rec, key):
        x = rec[key]
        return x["auroc"], tuple(x["ci95"])

    p = v3["primary_pooled_loco"]
    rows_v3 = [("raw fold-0 probability", *a(p, "RAW"), NOTRAIN, "o", True),
               ("V3-LR (primary)", *a(p, "V3-LR"), LEARN, "s", True),
               ("V3-GB", *a(p, "V3-GB"), LEARN, "s", True),
               ("V2 as shipped (earlier version)", *a(p, "V2-shipped"), LEARN, "s", True)]
    pe, pm = v31["primary_pooled_external"], v31["posthoc_P1_mean5"]["pooled_external"]
    rows_v31 = [("raw fold-0 probability", *a(pe, "RAW"), NOTRAIN, "o", True),
                ("5-fold ensemble mean", *a(pe, "ENS-RAW"), NOTRAIN, "o", True),
                ("GR-LR (primary)", *a(pe, "GR-LR"), LEARN, "s", True),
                ("post hoc, ensemble candidates: ensemble mean", *a(pm, "RAW"), NOTRAIN, "o", False),
                ("post hoc, ensemble candidates: GR-LR", *a(pm, "GR-LR"), LEARN, "s", False)]
    h1 = v32["H1"]
    k3b = v32["K3"]["K3b_cohort_probe_on_H1_endpoint"]["K3b-cohort-probe"]
    rows_v32 = [("5-fold ensemble mean", *a(h1, "ENS-RAW"), NOTRAIN, "o", True),
                ("fold disagreement (no training)", *a(h1, "DIS-RAW"), NOTRAIN, "o", True),
                ("GR-LR (v3.1 detector)", *a(h1, "GR-LR"), LEARN, "s", True),
                ("GR+C-LR (primary, trained with controls)", *a(h1, "GR+C-LR"), LEARN, "s", True),
                ("cohort probe (never saw a true lesion)", k3b["auroc"], tuple(k3b["ci95"]), PROBE, "D", True),
                ("controls-only negatives (GR-Conly-LR)", *a(h1, "GR-Conly-LR"), PROBE, "D", True)]
    k3 = v32["K3"]["held_out_1mm_ms"]["GR-Conly-LR"]
    k3e = v32["K3"]["held_out_1mm_ms"]["ENS-RAW"]

    fig, axes = plt.subplots(3, 1, figsize=(6.6, 7.0),
                             gridspec_kw={"height_ratios": [4, 5, 6.6], "hspace": 0.75})
    titles = [f"a  v3: pooled leave-one-cohort-out, MSLesSeg <-> Ljubljana-10 "
              f"({v3['primary_pooled_loco']['_n']['candidates']} candidates)",
              f"b  v3.1: three unseen thick-slice sites "
              f"({pe['_n']['candidates']} fold-0 / {pm['_n']['candidates']} ensemble candidates)",
              f"c  v3.2: real 1-mm MS lesions vs healthy-control false candidates "
              f"({h1['_n']['true']} vs {h1['_n']['false']})"]
    for ax, rows, title in zip(axes, [rows_v3, rows_v31, rows_v32], titles):
        n = len(rows)
        for i, (lab, pt, ci, col, mk, filled) in enumerate(rows):
            y = n - 1 - i
            ax.plot(ci, [y, y], color=col, lw=1.6)
            ax.plot(pt, y, marker=mk, color=col, ms=6.5, ls="none", zorder=3,
                    mfc=col if filled else "white", mec=col if not filled else "white", mew=1.2 if not filled else 0.8)
            ax.annotate(f"{fmt(pt)} [{fmt(ci[0])}, {fmt(ci[1])}]", (1.0, y), xycoords=("axes fraction", "data"),
                        xytext=(4, 0), textcoords="offset points", va="center", fontsize=6.8, color=INK)
        ax.set_yticks(range(n))
        ax.set_yticklabels([r[0] for r in rows][::-1])
        ax.set_xlim(0.6, 0.95)
        ax.set_ylim(-0.6, n - 0.4)
        ax.set_title(title, loc="left", fontweight="bold", fontsize=7.6)
        ax.grid(axis="y", visible=False)
        ax.set_xlabel("lesion-level AUROC (95 % CI)")
    axes[2].annotate(f"K3 transfer test: the controls-only model ranks held-out MS true vs MS false candidates at "
                     f"{fmt(k3['auroc'], 2)} (ensemble mean {fmt(k3e['auroc'], 2)})", (0.0, -0.42), xycoords="axes fraction",
                     fontsize=6.6, color=PURPLE)
    from matplotlib.lines import Line2D
    handles = [Line2D([], [], color=NOTRAIN, marker="o", ls="none", label="no training (probability / ensemble)"),
               Line2D([], [], color=LEARN, marker="s", ls="none", label="learned detector"),
               Line2D([], [], color=PROBE, marker="D", ls="none", label="confound probe / controls-only model"),
               Line2D([], [], color=MUTED, marker="o", mfc="white", ls="none", label="post hoc (not pre-registered)")]
    fig.legend(handles=handles, loc="lower center", ncol=2, frameon=False, bbox_to_anchor=(0.45, -0.06))
    fig.text(0.0, -0.09, "Patient-clustered bootstrap 95 % CI (B = 2 000). Sources: lesion_detector_v3 / v31 / v32 "
             "evaluation and post-hoc records (2026-10-17, -21, -24).", fontsize=6.5, color=MUTED)
    save(fig, "fig4_detector_auroc")


# ---------------------------------------------------------------------------- figure 5
def fig5(d):
    a3 = d["v3"]["A3_site_identity_auroc"]
    h4 = d["v31"]["H4_site_signature_M_vs_L10"]["site_identity_auroc"]
    k2 = d["v32"]["K2"]
    FL, DIS, PRB, LST, ALL = VERM, BLUE, GREEN, PURPLE, INK

    rows_a = [("all 42 v3 features", a3["V3_all"], ALL, "o"),
              ("FLAIR boundary", a3["F4_flair_boundary"], FL, "s"),
              ("FLAIR texture", a3["F3_texture"], FL, "s"),
              ("FLAIR contrast", a3["F1_contrast"], FL, "s"),
              ("probability-map boundary", a3["F4_prob_boundary"], PRB, "D"),
              ("location proxies", a3["F6_location"], PRB, "D"),
              ("persistence", a3["F5_persistence"], PRB, "D"),
              ("raw mean probability", a3["RAW(prob_mean)"], PRB, "D")]
    rows_b = [("FLAIR boundary", h4["F4_flair_boundary"], FL, "s"),
              ("FLAIR texture", h4["F3_flair_texture"], FL, "s"),
              ("FLAIR contrast", h4["F1_flair_contrast"], FL, "s"),
              ("probability + size (GR without F8)", h4["GR-noENS"], PRB, "D"),
              ("LST-AI agreement (F9)", h4["F9_lstai_agreement"], LST, "^"),
              ("fold disagreement (F8)", h4["F8_fold_disagreement"], DIS, "o")]
    fw = k2["MSfalse_vs_C"]["foldwise"]
    ref = k2["Mfalse_vs_L10false_reference"]["foldwise"]
    fam = [("GR", "grid-robust set (GR)", ALL, "o"), ("F8", "fold disagreement (F8)", DIS, "o"),
           ("GR-noENS", "probability + size", PRB, "D"), ("LST", "LST-AI agreement", LST, "^"),
           ("VOL", "volume alone", PRB, "D"), ("PROB", "mean probability alone", PRB, "D")]

    fig, axes = plt.subplots(3, 1, figsize=(5.6, 8.2), gridspec_kw={"height_ratios": [8, 6, 6.6], "hspace": 0.62})
    for ax, rows, title in [(axes[0], rows_a, "a  v3: MSLesSeg vs Ljubljana-10 (all candidates)"),
                            (axes[1], rows_b, "b  v3.1: MSLesSeg vs Ljubljana-10 (all candidates)")]:
        n = len(rows)
        for i, (lab, v, col, mk) in enumerate(rows):
            y = n - 1 - i
            ax.plot([0.5, v], [y, y], color=col, lw=1.4)
            ax.plot(v, y, marker=mk, color=col, ms=6, mec="white", mew=0.7, ls="none", zorder=3)
            ax.annotate(fmt(v, 2), (v, y), xytext=(4 if v >= 0.5 else -4, 0), textcoords="offset points",
                        ha="left" if v >= 0.5 else "right", va="center", fontsize=6.6, color=INK)
        ax.set_yticks(range(n))
        ax.set_yticklabels([r[0] for r in rows][::-1])
        ax.set_xlim(0.15, 1.05)
        ax.set_ylim(-0.6, n - 0.4)
        ax.set_title(title, loc="left", fontweight="bold", fontsize=7.6)
        ax.axvline(0.5, color=MUTED, lw=0.9)
        ax.axvline(0.7, color=MUTED, lw=0.9, ls="--")
        ax.grid(axis="y", visible=False)
        ax.set_xlabel("cohort-identity AUROC")
    ax = axes[2]
    n = len(fam)
    for i, (k, lab, col, mk) in enumerate(fam):
        y = n - 1 - i
        v, ci = fw[k]["auroc_foldwise_mean"], fw[k]["ci95"]
        ax.plot(ci, [y + 0.13] * 2, color=col, lw=1.5)
        ax.plot(v, y + 0.13, marker=mk, color=col, ms=6, mec="white", mew=0.7, ls="none", zorder=3)
        ax.annotate(fmt(v, 2), (ci[1], y + 0.13), xytext=(3, 0), textcoords="offset points", va="center",
                    fontsize=6.4, color=INK)
        rv, rci = ref[k]["auroc_foldwise_mean"], ref[k]["ci95"]
        ax.plot(rci, [y - 0.17] * 2, color=MUTED, lw=1.2)
        ax.plot(rv, y - 0.17, marker=mk, color="white", mec=MUTED, mew=1.1, ms=5.2, ls="none", zorder=3)
    ax.set_yticks(range(n))
    ax.set_yticklabels([f[1] for f in fam][::-1])
    ax.set_xlim(0.15, 1.05)
    ax.set_ylim(-0.6, n - 0.4)
    ax.axvline(0.5, color=MUTED, lw=0.9)
    ax.axvline(0.7, color=MUTED, lw=0.9, ls="--")
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("cohort-identity AUROC (fold-wise, 95 % CI)")
    ax.set_title("c  v3.2, false candidates only. Filled: MS patients vs healthy controls;\n"
                 "    hollow: MSLesSeg vs Ljubljana-10 (reference)",
                 loc="left", fontweight="bold", fontsize=7.6)
    fig.text(0.0, 0.0, "0.5 = cohort not recognisable; dashed 0.70 = v3.2 pre-registered reading threshold (reference\n"
             "only in a-b). Pooled out-of-fold values (a-b) are biased downward for weak signals (v3 D4,\n"
             "v3.2 D1), so values near or below 0.5 understate separability; panel c is fold-wise.",
             fontsize=6.5, color=MUTED)
    save(fig, "fig5_site_signature")


# ---------------------------------------------------------------------------- figure 6
def _t(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def fig6(d):
    pre, oth, comp = d["preregistration"], d["other_commits"], d["compute"]
    push = {e["event"].split(" (")[0]: _t(e["utc"]) for e in d["public_push_evidence"]}

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.4, 4.6), gridspec_kw={"height_ratios": [3.2, 3], "hspace": 0.7})
    # --- a: FLAMeS-thick
    lanes = {"commits (author time)": 3, "public on GitHub": 2, "Kaggle sessions\n(smoke, pilot, full)": 1,
             "evaluation VMs": 0}
    ax1.scatter([_t(pre["flames_thick"]["preregistration"]["committer_date"])], [3], marker="D", color=BLUE, s=36, zorder=3)
    ax1.annotate("protocol", (_t(pre["flames_thick"]["preregistration"]["committer_date"]), 3), xytext=(0, 6),
                 textcoords="offset points", ha="center", fontsize=6.4)
    for key, lab, ha in [("ft_amendment_kaggle_pilot", "amend. 1 ", "right"),
                         ("ft_amendment_early_look", " amend. 2", "left"), ("ft_training_done", "models", "center")]:
        t = _t(oth[key]["committer_date"])
        ax1.scatter([t], [3], marker="|", color=INK, s=80, zorder=3)
        ax1.annotate(lab, (t, 3), xytext=(0, 6), textcoords="offset points", ha=ha, fontsize=6.0)
    t_res = _t(pre["flames_thick"]["results"]["committer_date"])
    ax1.scatter([t_res], [3], marker="*", color=VERM, s=70, zorder=3)
    ax1.annotate("results", (t_res, 3), xytext=(0, 6), textcoords="offset points", ha="center", fontsize=6.4)
    for ev, lab in [("PR #56 opened", "protocol public"), ("push 73e9651", ""), ("push aba9a54", "")]:
        t = push[ev]
        ax1.scatter([t], [2], marker="o", color=BLUE, s=22, zorder=3)
        if lab:
            ax1.annotate(lab, (t, 2), xytext=(0, 6), textcoords="offset points", ha="center", fontsize=6.2)
    t = push["push b19293c"]  # local reflog only (author-side); no GitHub event was returned for it
    ax1.scatter([t], [2], marker="o", facecolors="white", edgecolors=VERM, s=26, zorder=3, linewidths=1.1)
    ax1.annotate("results pushed\n(local log only)", (t, 2), xytext=(0, 6), textcoords="offset points",
                 ha="center", fontsize=6.0)
    for k in comp["kaggle_sessions"]:
        ax1.plot([_t(k["start_utc"]), _t(k["end_utc"])], [1, 1], color=GREEN, lw=6, solid_capstyle="butt")
    for k in comp["flames_thick_eval_runs"]:
        ax1.plot([_t(k["start_utc"]), _t(k["end_utc"])], [0, 0], color=PURPLE, lw=6, solid_capstyle="butt")
    ax1.set_yticks(list(lanes.values()))
    ax1.set_yticklabels(list(lanes.keys()))
    ax1.set_ylim(-0.6, 3.8)
    ax1.set_xlim(datetime(2026, 10, 21, 0, tzinfo=timezone.utc), datetime(2026, 10, 23, 14, tzinfo=timezone.utc))
    ax1.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 12], tz=timezone.utc))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%d Oct %H:%M", tz=timezone.utc))
    ax1.set_title("a  FLAMeS-thick (UTC): protocol public before any Kaggle session; amendments pushed before "
                  "each study training session", loc="left", fontweight="bold", fontsize=7.4)
    ax1.grid(axis="y", visible=False)
    # --- b: detector stages
    stages = [("v3", "detector_v3", "PR #55 opened"), ("v3.1", "detector_v31", "PR #55 opened"),
              ("v3.2", "detector_v32", "push 3c24977")]
    for i, (lab, key, ev) in enumerate(stages):
        y = 2 - i
        tp = _t(pre[key]["preregistration"]["committer_date"])
        tr = _t(pre[key]["results"]["committer_date"])
        ax2.scatter([tp], [y], marker="D", color=BLUE, s=34, zorder=3)
        ax2.scatter([tr], [y], marker="*", color=VERM, s=70, zorder=3)
        tpub = push[ev]
        ax2.scatter([tpub], [y], marker="o", facecolors="white", edgecolors=INK, s=40, zorder=4, linewidths=1.1)
        fmt = "%d Oct %H:%M"
        note = (f"protocol {tp:{fmt}}  ->  results {tr:{fmt}}  ->  first public {tpub:{fmt}}"
                + ("  (protocol and results together)" if key != "detector_v32" else
                   f"; results public {push['push 90797a9']:%H:%M}"))
        ax2.annotate(note, (0.01, y), xycoords=("axes fraction", "data"), xytext=(0, 9),
                     textcoords="offset points", ha="left", fontsize=6.2, color=INK)
    ax2.set_yticks([2, 1, 0])
    ax2.set_yticklabels(["detector v3", "detector v3.1", "detector v3.2"])
    ax2.set_ylim(-0.7, 2.7)
    ax2.set_xlim(datetime(2026, 10, 17, 0, tzinfo=timezone.utc), datetime(2026, 10, 25, 0, tzinfo=timezone.utc))
    ax2.xaxis.set_major_locator(mdates.DayLocator(tz=timezone.utc))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%d Oct", tz=timezone.utc))
    ax2.grid(axis="y", visible=False)
    ax2.set_title("b  detector stages: protocol commit, results commit, first public appearance",
                  loc="left", fontweight="bold", fontsize=7.4)
    from matplotlib.lines import Line2D
    handles = [Line2D([], [], marker="D", color=BLUE, ls="none", label="protocol commit"),
               Line2D([], [], marker="*", color=VERM, ms=9, ls="none", label="results commit"),
               Line2D([], [], marker="o", mfc="white", mec=INK, ls="none", label="first public on GitHub"),
               Line2D([], [], color=GREEN, lw=5, label="Kaggle 2 x T4 session"),
               Line2D([], [], color=PURPLE, lw=5, label="cloud CPU evaluation")]
    fig.legend(handles=handles, loc="lower center", ncol=5, frameon=False, bbox_to_anchor=(0.5, -0.06), fontsize=6.6)
    fig.text(0.0, -0.1, "Commit times are author-controlled; GitHub push and pull-request times are third-party "
             "timestamps (queried 2026-10-31). Sources: git history; compute ledger c8b4239.", fontsize=6.5, color=MUTED)
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
