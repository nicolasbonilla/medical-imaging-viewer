#!/usr/bin/env python3
"""Paper A manuscript — every figure is drawn from the committed result records, nothing else.

Inputs (read-only):
  docs/research/records/2026-10-21_paper_a_v03_results.json       pre-registered v0.3 results
  docs/research/records/2026-10-21_paper_a_v03_posthoc.json       post-hoc explanations (labelled)
  docs/research/records/2026-10-24_paper_a_v03c_controls.json     healthy-control addendum
  docs/research/records/2026-10-31_paper_a_manuscript_posthoc.json manuscript-stage post hoc

Outputs: figN_*.png (300 dpi) and figN_*.pdf next to this script, plus figures_manifest.json
(SHA-256 of every input record and output file).

Colour: categorical slots blue #2a78d6, orange #eb6834, aqua #1baf7a (validated all-pairs for
colour-vision deficiency with the dataviz validator, light surface); status of a cell
(holds / inconclusive / violated) uses the fixed status steps and ALWAYS a distinct marker shape
and a legend, so no meaning is carried by colour alone.

    python docs/research/paper/manuscript/figures/make_figures.py
"""
import hashlib
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt                     # noqa: E402
from matplotlib.lines import Line2D                  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", ".."))
REC = os.path.join(ROOT, "docs", "research", "records")
F_RES = os.path.join(REC, "2026-10-21_paper_a_v03_results.json")
F_PH = os.path.join(REC, "2026-10-21_paper_a_v03_posthoc.json")
F_CTL = os.path.join(REC, "2026-10-24_paper_a_v03c_controls.json")
F_MPH = os.path.join(REC, "2026-10-31_paper_a_manuscript_posthoc.json")

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
GOOD, WARN, CRIT = "#0ca30c", "#fab219", "#d03b3b"
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#ffffff"
CLASS_STYLE = {"holds": dict(marker="o", color=GOOD, label="holds (no violation detected; upper bound within margin)"),
               "inconclusive": dict(marker="D", color=WARN, label="inconclusive"),
               "violated": dict(marker="s", color=CRIT, label="violated (lower bound above nominal)")}
SITE_LABEL = {"mslesseg": "MSLesSeg", "openms": "Ljubljana-10", "ms3seg": "MS3SEG", "muslim": "Muslim", "pedims": "PediMS"}

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 8.5, "axes.edgecolor": INK2, "axes.labelcolor": INK,
    "xtick.color": INK2, "ytick.color": INK2, "axes.titlesize": 9.5, "axes.titleweight": "bold",
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.6, "axes.axisbelow": True, "legend.frameon": False, "savefig.facecolor": SURF,
    "figure.facecolor": SURF, "lines.linewidth": 2.0, "pdf.fonttype": 42})

OUTPUTS = []


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(fig, name):
    for ext in ("png", "pdf"):
        p = os.path.join(HERE, f"{name}.{ext}")
        fig.savefig(p, dpi=300, bbox_inches="tight")
        OUTPUTS.append(p)
    plt.close(fig)


def sha(p):
    """SHA-256; text records are hashed with LF line endings so the value equals the committed blob's."""
    h = hashlib.sha256()
    with open(p, "rb") as f:
        data = f.read()
    h.update(data.replace(b"\r\n", b"\n") if p.endswith(".json") else data)
    return h.hexdigest()


# --------------------------------------------------------------------------- Figure 1
def fig1_primary(res):
    """Forest plot of the 32 pre-registered primary cells (ensemble arm)."""
    order = [("D3", "ms3seg"), ("D3", "muslim"), ("D3", "pedims"), ("D2", "mslesseg"), ("D2", "openms"),
             ("D2", "ms3seg"), ("D2", "muslim"), ("D2", "pedims")]
    cells = {(c["design"], c["site"], c["procedure"], c["target"]): c for c in res["primary"]}
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 5.0), sharey=True)
    ylabels, ys = [], []
    for panel, (proc, ax) in enumerate(zip(("P1", "P2"), axes)):
        y = 0
        for d, s in order:
            for t in (0.1, 0.2):
                c = cells[(d, s, proc, t)]
                nominal = c["nominal"]
                lo, hi = c["ci95"]
                st = CLASS_STYLE[c["class"]]
                ax.plot([nominal, nominal + 0.05], [y, y], color=GRID, lw=6, solid_capstyle="butt", zorder=1)
                ax.plot([nominal, nominal], [y - 0.42, y + 0.42], color=INK2, lw=0.9, zorder=2)
                ax.plot([lo, hi], [y, y], color=INK, lw=1.2, zorder=3)
                filled = not c["uninformative_abstention"]
                ax.plot([c["estimate"]], [y], marker=st["marker"], ms=6.5, mec=INK, mew=0.7,
                        mfc=st["color"] if filled else SURF, ls="none", zorder=4)
                if panel == 0:
                    lab = ("1-mm grid → " if d == "D3" else "Leave-one-site-out · ") + SITE_LABEL[s]
                    if s == "openms":
                        lab += " †"
                    ylabels.append(f"{lab}  (α | γ = {t})")
                    ys.append(y)
                y += 1
            y += 0.45
        ax.set_xlim(-0.01, 0.55 if proc == "P2" else 0.30)
        ax.set_xlabel("realised FDR (mean per-scan FDP)" if proc == "P1" else "realised FDX (share of scans with FDP > γ)")
        ax.set_title("P1 · conformal BH (target: FDR ≤ α)" if proc == "P1" else "P2 · CALM-FDX threshold (target: P(FDP > γ) ≤ 0.1)",
                     loc="left")
        ax.grid(axis="y", visible=False)
    axes[0].set_yticks(ys)
    axes[0].set_yticklabels(ylabels, fontsize=7.2)
    axes[0].invert_yaxis()
    handles = [Line2D([], [], marker=v["marker"], color="none", mfc=v["color"], mec=INK, ms=6.5, label=v["label"])
               for v in CLASS_STYLE.values()]
    handles += [Line2D([], [], marker="o", color="none", mfc=SURF, mec=INK, ms=6.5,
                       label="hollow = passes only by abstention (< 10 selections or sensitivity < 0.05)"),
                Line2D([], [], color=INK2, lw=0.9, label="nominal level"),
                Line2D([], [], color=GRID, lw=6, label="pre-registered margin (nominal + 0.05)")]
    fig.legend(handles=handles, loc="lower center", ncol=2, bbox_to_anchor=(0.5, -0.16), fontsize=7.2)
    fig.text(0.0, -0.19, "† Ljubljana is a FLAMeS training site: its 10 patients were never trained on, but the site was. "
                         "95 % patient-cluster bootstrap intervals (P2: union with exact Clopper–Pearson).",
             fontsize=6.8, color=INK2)
    save(fig, "fig1_primary_cells")


# --------------------------------------------------------------------------- Figure 2
def fig2_mechanism(res, ph):
    """Why the per-scan threshold fails on thick slices (post hoc explanation)."""
    sites = ["mslesseg", "openms", "ms3seg", "muslim", "pedims"]
    above = [ph[f"ens|{s}"]["scans_with_false_candidate_above_1mm_P2_threshold"] for s in sites]
    cells = {(c["design"], c["site"], c["procedure"], c["target"]): c for c in res["primary"]}
    fdx = [None, None] + [cells[("D3", s, "P2", 0.1)]["estimate"] for s in sites[2:]]
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.2), gridspec_kw={"width_ratios": [1.3, 1]})
    ax = axes[0]
    x = range(len(sites))
    w = 0.38
    ax.bar([i - w / 2 for i in x], above, width=w - 0.03, color=BLUE, label="scans with a false candidate scoring above 0.965 [post hoc]")
    ax.bar([i + w / 2 for i in x[2:]], fdx[2:], width=w - 0.03, color=ORANGE, label="realised FDX, 1-mm → thick, γ = 0.1 (pre-registered)")
    ax.axhline(0.1, color=INK2, lw=0.9)
    ax.text(4.55, 0.105, "δ = 0.1", fontsize=7, color=INK2, ha="right", va="bottom")
    for i, v in enumerate(above):
        ax.text(i - w / 2, v + 0.006, f"{v:.2f}", ha="center", fontsize=6.0, color=INK)
    for i in range(2, 5):
        ax.text(i + w / 2, fdx[i] + 0.006, f"{fdx[i]:.2f}", ha="center", fontsize=6.0, color=INK)
    ax.set_xticks(list(x))
    ax.set_xticklabels([SITE_LABEL[s].replace("-", "\n") for s in sites], fontsize=7.0)
    ax.set_ylabel("share of scans")
    ax.set_ylim(0, 0.36)
    ax.set_title("A  The 1-mm threshold (0.965) is exceeded by\n    false candidates on thick-slice scans", loc="left")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), fontsize=6.6)
    ax.grid(axis="x", visible=False)
    ax2 = axes[1]
    f0 = [ph[f"f0|{s}"]["false_candidates_score_ge_0.95"] for s in sites]
    en = [ph[f"ens|{s}"]["false_candidates_score_ge_0.95"] for s in sites]
    for i, (a, b) in enumerate(zip(f0, en)):
        ax2.plot([a, b], [i, i], color=GRID, lw=3, zorder=1)
    ax2.plot(f0, list(x), "s", color=ORANGE, ms=7, mec=INK, mew=0.6, ls="none", label="fold 0 alone", zorder=3)
    ax2.plot(en, list(x), "o", color=BLUE, ms=7, mec=INK, mew=0.6, ls="none", label="5-fold ensemble", zorder=3)
    ax2.set_yticks(list(x))
    ax2.set_yticklabels([SITE_LABEL[s] for s in sites], fontsize=7.5)
    ax2.invert_yaxis()
    ax2.set_xlim(0, 0.36)
    ax2.set_xlabel("share of false candidates scoring ≥ 0.95")
    ax2.set_title("B  Averaging folds removes over-confident\n    false candidates [post hoc]", loc="left")
    ax2.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2, fontsize=7)
    ax2.grid(axis="y", visible=False)
    fig.tight_layout()
    save(fig, "fig2_threshold_mechanism")


# --------------------------------------------------------------------------- Figure 3
def fig3_size(res):
    """Raw detection by lesion volume and thickness band (D2, ensemble)."""
    sb = res["thickness"]["size_bins"]
    bands = [("B1", "≤ 1.5 mm grid (125 scans; 110 natively 2–5 mm)", BLUE, "o", "-"),
             ("B2", "3.9 mm (PediMS, 28 scans / 9 children)", AQUA, "^", "-"),
             ("B3", "4.5–6.5 mm (Muslim 45, MS3SEG 31)", ORANGE, "s", "-"),
             ("B4", "> 6.5 mm (MS3SEG 69, Muslim 6)", INK2, "D", "--")]
    xt = ["3–14", "14–50", "50–150", "150–500", "≥ 500"]
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.0), sharey=True)
    for ax, key, title in ((axes[0], "sens_raw", "A  Raw segmentation (no selection)"),
                           (axes[1], "sens_selected", "B  After P1 selection (α = 0.2, LOSO)")):
        for b, lab, col, mk, ls in bands:
            r = sb[f"{b}|D2|P1|0.2"]
            ax.plot(range(5), r[key], ls=ls, marker=mk, color=col, ms=6, mec=INK, mew=0.5, label=lab)
        ax.axhline(0.8, color=INK2, lw=0.8, ls=":")
        ax.axhline(0.5, color=INK2, lw=0.8, ls=":")
        ax.text(4.25, 0.81, "0.8", fontsize=6.8, color=INK2)
        ax.text(4.25, 0.51, "0.5", fontsize=6.8, color=INK2)
        ax.set_xticks(range(5))
        ax.set_xticklabels(xt, fontsize=7.2)
        ax.set_xlabel("expert-lesion volume (mm³)")
        ax.set_title(title, loc="left")
        ax.set_ylim(0, 1.0)
        ax.grid(axis="x", visible=False)
    axes[0].set_ylabel("share of expert lesions found")
    h3, l3 = axes[0].get_legend_handles_labels()
    fig.legend(h3, l3, loc="lower center", ncol=2, bbox_to_anchor=(0.5, -0.1), fontsize=6.8)
    fig.text(0.0, -0.14, "Bands are confounded with site, scanner, population and annotation protocol; they describe these cohorts, "
                         "not a controlled thickness effect.", fontsize=6.8, color=INK2)
    fig.tight_layout()
    save(fig, "fig3_detection_by_size_and_band")


# --------------------------------------------------------------------------- Figure 4
def fig4_ensemble(res):
    """5-fold ensemble vs fold 0, same scans and expert lesions (P1, alpha = 0.2)."""
    q = res["q3"]["paired_ens_minus_f0"]
    rows = [("D3|ALL", "1-mm → thick, all thick sites"), ("D3|ms3seg", "1-mm → MS3SEG"), ("D3|muslim", "1-mm → Muslim"),
            ("D3|pedims", "1-mm → PediMS"), ("D2|ALL", "leave-one-site-out, all"), ("D1|ALL", "within-site, all"),
            ("D4|ALL", "pooled 5-fold, all")]
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.9), sharey=True)
    for ax, metric, xl, title in ((axes[0], "mean_fdp", "realised FDR (α = 0.2)", "A  Validity"),
                                  (axes[1], "sens_e2e", "end-to-end lesion sensitivity", "B  Power")):
        for i, (k, lab) in enumerate(rows):
            r = q[f"{k}|P1|0.2"][metric]
            ax.plot([r["b"], r["a"]], [i, i], color=GRID, lw=3, zorder=1)
            ax.plot(r["b"], i, "s", color=ORANGE, ms=7, mec=INK, mew=0.6, zorder=3)
            ax.plot(r["a"], i, "o", color=BLUE, ms=7, mec=INK, mew=0.6, zorder=3)
            ax.text(0.245 if metric == "mean_fdp" else 0.43, i,
                    f"Δ {r['diff']:+.3f} [{r['ci95'][0]:+.3f}, {r['ci95'][1]:+.3f}]", va="center", fontsize=6.0, color=INK2)
        if metric == "mean_fdp":
            ax.axvline(0.2, color=INK2, lw=0.9)
            ax.set_xlim(0, 0.42)
        else:
            ax.set_xlim(0, 0.70)
        ax.set_xlabel(xl)
        ax.set_title(title, loc="left")
        ax.grid(axis="y", visible=False)
    axes[0].set_yticks(range(len(rows)))
    axes[0].set_yticklabels([r[1] for r in rows], fontsize=7.3)
    axes[0].invert_yaxis()
    h = [Line2D([], [], marker="o", color="none", mfc=BLUE, mec=INK, ms=7, label="5-fold ensemble"),
         Line2D([], [], marker="s", color="none", mfc=ORANGE, mec=INK, ms=7, label="fold 0 alone (v0.2 pipeline)")]
    fig.legend(handles=h, loc="lower center", ncol=2, bbox_to_anchor=(0.55, -0.08), fontsize=7.2)
    fig.tight_layout()
    save(fig, "fig4_ensemble_vs_fold0")


# --------------------------------------------------------------------------- Figure 5
def fig5_recal(res):
    """Recalibration curve with k local patients (D5, 200 draws)."""
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 4.6), sharex=True)
    for col, site in enumerate(("ms3seg", "muslim")):
        cells = res["q4"][site]["cells"]
        ks = res["q4"][site]["k_grid"]
        series = [("site_only", "P1", 0.2, BLUE, "o", "-", "P1 α = 0.2, site only (FDR)"),
                  ("augmented", "P1", 0.1, AQUA, "^", "-", "P1 α = 0.1, 1-mm pool + k (FDR)"),
                  ("site_only", "P2", 0.1, ORANGE, "s", "-", "P2 γ = 0.1, site only (FDX)"),
                  ("augmented", "P2", 0.1, INK2, "D", "--", "P2 γ = 0.1, 1-mm pool + k (FDX)")]
        top, bot = axes[0][col], axes[1][col]
        for mode, proc, t, c, mk, ls, lab in series:
            xs, ys, ss = [], [], []
            for k in ks:
                r = cells.get(f"{mode}|{proc}|{t}|k={k}")
                if r is None:
                    continue
                if proc == "P2" and mode == "site_only" and r["n_sel_mean"] == 0:
                    continue  # abstains by construction (k < 9)
                xs.append(k)
                ys.append(r["realised_mean"])
                ss.append(r["sens_e2e_mean"])
            top.plot(xs, ys, ls=ls, marker=mk, color=c, ms=5.5, mec=INK, mew=0.5, label=lab)
            bot.plot(xs, ss, ls=ls, marker=mk, color=c, ms=5.5, mec=INK, mew=0.5, label=lab)
        top.axhline(0.1, color=INK2, lw=0.8, ls=":")
        top.axhline(0.2, color=INK2, lw=0.8, ls=":")
        top.set_title(f"{'A' if col == 0 else 'B'}  {SITE_LABEL[site]}: realised error", loc="left")
        bot.set_title(f"{'C' if col == 0 else 'D'}  {SITE_LABEL[site]}: end-to-end sensitivity", loc="left")
        top.set_ylim(0, 0.3)
        bot.set_ylim(0, 0.45)
        bot.set_xscale("log")
        bot.set_xticks(ks)
        bot.set_xticklabels([str(k) for k in ks])
        bot.set_xlabel("local calibration patients k")
        top.grid(axis="x", visible=False)
        bot.grid(axis="x", visible=False)
    axes[0][0].set_ylabel("realised FDR / FDX\n(mean of 200 draws)")
    axes[1][0].set_ylabel("sensitivity")
    h, l = axes[0][0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=2, bbox_to_anchor=(0.5, -0.07), fontsize=7.2)
    fig.text(0.0, -0.1, "P2 site-only abstains by construction for k < 9 (δ = 0.1) and is drawn from k = 10.",
             fontsize=6.8, color=INK2)
    fig.tight_layout()
    save(fig, "fig5_recalibration_curve")


# --------------------------------------------------------------------------- Figure 6
def fig6_controls(ctl):
    """Healthy controls with >= 1 reported lesion (100 SibBMS controls)."""
    op = ctl["operating_points"]
    rows = [("ens|1-mm sites|P1|0.1", "ensemble · 1-mm pool · P1 α = 0.1 (primary)", 0.1),
            ("ens|1-mm sites|P1|0.2", "ensemble · 1-mm pool · P1 α = 0.2 (primary)", 0.2),
            ("ens|1-mm sites|P2|0.1", "ensemble · 1-mm pool · P2 (primary)", 0.1),
            ("ens|all five patient sites|P1|0.1", "ensemble · all-site pool · P1 α = 0.1", 0.1),
            ("ens|all five patient sites|P1|0.2", "ensemble · all-site pool · P1 α = 0.2", 0.2),
            ("ens|1-mm sites|B3|0.2", "ensemble · 1-mm pool · LTT (B3) α = 0.2", 0.2),
            ("f0|1-mm sites|P1|0.1", "fold 0 · 1-mm pool · P1 α = 0.1", 0.1),
            ("f0|1-mm sites|P1|0.2", "fold 0 · 1-mm pool · P1 α = 0.2", 0.2),
            ("f0|1-mm sites|P2|0.1", "fold 0 · 1-mm pool · P2", 0.1)]
    fig, ax = plt.subplots(figsize=(7.2, 3.3))
    for i, (k, lab, nom) in enumerate(rows):
        r = op[f"{k}|all100"]
        lo, hi = r["ci95_exact"]
        st = CLASS_STYLE[r["class"]]
        ax.plot([nom, nom + 0.05], [i, i], color=GRID, lw=6, solid_capstyle="butt", zorder=1)
        ax.plot([nom, nom], [i - 0.4, i + 0.4], color=INK2, lw=0.9, zorder=2)
        ax.plot([lo, hi], [i, i], color=INK, lw=1.2, zorder=3)
        ax.plot(r["rate"], i, marker=st["marker"], color="none", mfc=st["color"], mec=INK, ms=6.5, zorder=4)
        ax.text(hi + 0.01, i, f"{r['scans_with_any']}/100", va="center", fontsize=6.8, color=INK2)
    raw = ctl["raw_candidates"]["ens"]
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[1] for r in rows], fontsize=7.2)
    ax.invert_yaxis()
    ax.set_xlim(0, 0.9)
    ax.set_xlabel("healthy controls with ≥ 1 reported lesion (exact 95 % CI)")
    ax.set_title(f"Healthy brains: on a lesion-free scan the FDR promise reads P(≥ 1 reported lesion) ≤ α  "
                 f"(no selection: {raw['scans_with_any_candidate']}/100)", loc="left", fontsize=8.5)
    ax.grid(axis="y", visible=False)
    handles = [Line2D([], [], marker=v["marker"], color="none", mfc=v["color"], mec=INK, ms=6.5, label=v["label"].split(" (")[0])
               for v in CLASS_STYLE.values()]
    ax.legend(handles=handles, loc="upper right", fontsize=7)
    fig.tight_layout()
    save(fig, "fig6_healthy_controls")


# --------------------------------------------------------------------------- Figure 7
def fig7_baselines(res, mph):
    """Validity vs power of every procedure, 1-mm -> thick (D3), per site and alpha."""
    procs = [("P1", "P1 conformal BH", BLUE, "o"), ("SUB", "one candidate per patient + BH [post hoc]", BLUE, "^"),
             ("B2", "B2 conformal risk control", ORANGE, "s"), ("B3", "B3 Learn-then-Test", ORANGE, "D"),
             ("B1", "B1 precision-matched (no guarantee)", INK2, "X"), ("LR", "hierarchical e-values [post hoc]", AQUA, "v")]
    fig, axes = plt.subplots(2, 3, figsize=(7.2, 4.4), sharex="row", sharey=True)
    for r_i, a in enumerate((0.1, 0.2)):
        for c_i, site in enumerate(("ms3seg", "muslim", "pedims")):
            ax = axes[r_i][c_i]
            ax.axvspan(a, a + 0.05, color=GRID, zorder=0)
            ax.axvline(a, color=INK2, lw=0.9)
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
                ax.plot(ci, [sens, sens], color=col, lw=1.1, zorder=2)
                ax.plot(est, sens, marker=mk, color="none", mfc=col, mec=INK, mew=0.6, ms=6.5, zorder=3, label=lab)
            ax.set_title(f"{SITE_LABEL[site]} · α = {a}", loc="left")
            ax.set_xlim(-0.01, 0.32)
            if c_i == 0:
                ax.set_ylabel("end-to-end sensitivity")
            if r_i == 1:
                ax.set_xlabel("realised FDR [95 % CI]")
    h, l = axes[0][0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.08), fontsize=6.8)
    fig.text(0.0, -0.11, "Calibration on the 1-mm-grid sites, test on each thick-slice site (D3). Hierarchical e-values selected "
                         "nothing in every D3 cell (sensitivity 0). Grey band: nominal α to α + 0.05.",
             fontsize=6.8, color=INK2)
    fig.tight_layout()
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
           "palette": {"categorical": [BLUE, ORANGE, AQUA], "status": [GOOD, WARN, CRIT],
                       "validator": "dataviz validate_palette.js --pairs all --mode light: ALL CHECKS PASS (aqua contrast WARN -> legends + markers)"}}
    with open(os.path.join(HERE, "figures_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, indent=1)
    print("wrote", len(OUTPUTS), "files")


if __name__ == "__main__":
    main()
