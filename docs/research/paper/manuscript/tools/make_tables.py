#!/usr/bin/env python3
"""Paper A manuscript — generate every results table from the committed records and write it
into manuscript.md between markers  <!-- BEGIN TABLE tX -->  and  <!-- END TABLE tX -->.

Revision 2 (2026-11-04): reads the FULL-PRECISION records (`*_fullprec.json`, `*_revision*.json`) and
rounds once, half up, at printing — the first version rounded already-rounded record values and
produced eight off-by-0.001 slips. Exact Clopper–Pearson intervals for the controls are recomputed
from the stored counts.

Idempotent: re-running replaces the table bodies only. `--check` regenerates the tables and fails if
manuscript.md differs (used by check_numbers.py). Numbers are never typed by hand into a table.

    python docs/research/paper/manuscript/tools/make_tables.py [--check]
"""
import json
import os
import re
import sys
from decimal import ROUND_HALF_UP, Decimal

from scipy.stats import beta

HERE = os.path.dirname(os.path.abspath(__file__))
MS_DIR = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(MS_DIR, "..", "..", "..", ".."))
REC = os.path.join(ROOT, "docs", "research", "records")
MANUSCRIPT = os.path.join(MS_DIR, "manuscript.md")


def load(name):
    with open(os.path.join(REC, name), encoding="utf-8") as fh:
        return json.load(fh)


RES = load("2026-10-31_paper_a_v03_results_fullprec.json")
PH = load("2026-10-31_paper_a_v03_posthoc_fullprec.json")
MPH = load("2026-10-31_paper_a_manuscript_posthoc_fullprec.json")
NAT = load("2026-10-31_paper_a_v03_mslesseg_native_fullprec.json")
REV = load("2026-10-31_paper_a_revision.json")
REVX = load("2026-10-31_paper_a_revision_extra.json")
CTL = load("2026-10-24_paper_a_v03c_controls.json")

SITE = {"mslesseg": "MSLesSeg", "openms": "Ljubljana-10", "ms3seg": "MS3SEG", "muslim": "Muslim", "pedims": "PediMS"}
SITES = ("mslesseg", "openms", "ms3seg", "muslim", "pedims")
CLS = {"holds": "holds", "inconclusive": "inconclusive", "violated": "**violated**", "not estimable": "not estimable"}


def r(x, k=3):
    """Round half up, once, from the full-precision value."""
    q = Decimal(1).scaleb(-k)
    return str(Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP))


def f(x, k=3):
    return "—" if x is None else r(x, k)


def sg(x, k=3):
    return ("+" if x >= 0 else "") + f(x, k)


def ci(c, k=3):
    return "—" if c is None else f"[{r(c[0], k)}, {r(c[1], k)}]"


def pc(x, k=0):
    return "—" if x is None else f(100 * x, k)


def classify(c, nominal, margin=0.05):
    if c is None:
        return "—"
    if c[0] > nominal:
        return "violated"
    return "holds" if c[1] <= nominal + margin else "inconclusive"


def cp(x, n, conf=0.95):
    a = (1 - conf) / 2
    lo = 0.0 if x == 0 else beta.ppf(a, x, n - x + 1)
    hi = 1.0 if x == n else beta.ppf(1 - a, x + 1, n - x)
    return [float(lo), float(hi)]


def lab_design(d, s):
    return ("1-mm grid → " if d == "D3" else "leave-one-site-out · ") + SITE[s] + (" †" if s == "openms" else "")


ORDER = [("D3", "ms3seg"), ("D3", "muslim"), ("D3", "pedims"), ("D2", "mslesseg"), ("D2", "openms"),
         ("D2", "ms3seg"), ("D2", "muslim"), ("D2", "pedims")]


# ------------------------------------------------------------------ main-text tables
def t_cohorts():
    meta = {"mslesseg": ("Italy (Catania); 8 scanner models, 1.5/3 T", "2D/3D; slice thickness 2–5 mm (43 at 2–2.3, 52 at 3, 15 at 4–5, 5 unknown)", "MNI 1 mm (delivered resampled)"),
            "openms": ("Slovenia (Ljubljana); Siemens 3 T", "3D; 0.47 × 0.47 × 0.8 mm", "MNI 1 mm (delivered)"),
            "ms3seg": ("Iran; one Toshiba 1.5 T scanner", "2D; thickness 4.7–6.9 mm + gap 0.7–2.1 mm (spacing 6.0–8.1, median 7.2)", "native"),
            "muslim": ("Iraq, ~20 centres (most patients from Baghdad); 1.5 T", "2D; thickness 3–6 mm, spacing 4.86–8.3 mm (median 6.0); in-plane pixel size estimated", "native"),
            "pedims": ("one centre; Siemens Skyra 3 T; 9 children", "2D; spacing 3.9 mm (0.75 × 0.75 mm in-plane)", "native")}
    rows = ["| cohort | origin, scanner | scans / patients | native FLAIR geometry | grid analysed | detectable expert lesions | candidates (false) | candidate AUROC, 5-fold mean [95 % CI] | AUROC, single folds on their own candidates (range) |",
            "|---|---|---|---|---|---:|---|---|---|"]
    for s in SITES:
        d = RES["descriptive"][f"ens|{s}"]
        a = RES["q3"]["auroc"]
        folds = [a[f"f{k}|{s}"]["auroc"] for k in range(5)]
        o, g, grid = meta[s]
        rows.append(f"| {SITE[s]} | {o} | {d['scans']} / {d['patients']} | {g} | {grid} | {d['gt_detectable']} | "
                    f"{d['candidates']} ({d['false']}) | {f(a[f'ens_mean|{s}']['auroc'])} {ci(a[f'ens_mean|{s}']['ci95'])} | "
                    f"{f(min(folds))}–{f(max(folds))} |")
    raw = CTL["raw_candidates"]
    rows.append(f"| SibBMS healthy controls | Siberia (Russia), one site | 100 / 100 | not verified; images registered to an MNI-type 1-mm template | template 1 mm | 0 | "
                f"{raw['ens']['candidates_total']} ({raw['ens']['candidates_total']}); fold 0: {raw['f0']['candidates_total']} | — | — |")
    return "\n".join(rows)


def t_primary():
    cells = {(c["design"], c["site"], c["procedure"], c["target"]): c for c in RES["primary"]}
    rows = ["| design · test site | P1, α = 0.1 (FDR) | P1, α = 0.2 (FDR) | P2, γ = 0.1 (FDX vs δ = 0.1) | P2, γ = 0.2 (FDX vs δ = 0.1) |",
            "|---|---|---|---|---|"]
    for d, s in ORDER:
        out = []
        for p, t in (("P1", 0.1), ("P1", 0.2), ("P2", 0.1), ("P2", 0.2)):
            c = cells[(d, s, p, t)]
            k = 3 if p == "P1" else 2
            ab = " (abst.)" if c["uninformative_abstention"] else ""
            star = "*" if (c["class"] == "holds" and c["estimate"] > c["nominal"]) else ""
            out.append(f"{f(c['estimate'], k)} {ci(c['ci95'], k)} {CLS[c['class']]}{star}{ab}; sens. {f(c['sens_e2e'])}; n = {c['n_sel']}")
        rows.append(f"| {lab_design(d, s)} | " + " | ".join(out) + " |")
    return "\n".join(rows)


def revised_class(est_ci, ucb_hb, nominal, degenerate):
    if degenerate:
        return "not estimable"
    if est_ci[0] > nominal:
        return "violated"
    return "holds" if ucb_hb <= nominal + 0.05 else "inconclusive"


def t_primary_bounds():
    """Table 4b: what a reader sees (selection rates), and bounds that survive few patients / re-drawn calibration."""
    rows = ["| design · test site | cell | estimate (empty = 0) | scans selecting | FDR among selecting scans | scans with FDP > 0.1 | one-sided 95 % bound: bootstrap, calibration fixed | two-level bootstrap: mean [95 % CI]; one-sided bound (MC SE) | Hoeffding–Bentkus bound over patients | revised class [post hoc] |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for d, s in ORDER:
        for p, t in (("P1", 0.1), ("P1", 0.2), ("P2", 0.1), ("P2", 0.2)):
            c = REV["cells"][f"{d}|{s}|{p}|{t}"]
            tl = c["two_level"]
            if p == "P1":
                est, ucb, hb = c["realised_fdr"], c["realised_fdr_ucb95_boot"], c["realised_fdr_ucb95_hb_patients"]
                ci2 = c["realised_fdr_ci95"]
                nominal = t
            else:
                est, ucb, hb = c["exceedance_estimate"], c["exceedance_ucb95_boot"], c["exceedance_ucb95_hb_patients"]
                pre = [x for x in RES["primary"] if x["design"] == d and x["site"] == s and x["procedure"] == p and x["target"] == t][0]
                ci2 = pre["ci95"]                      # pre-registered: bootstrap ∪ exact Clopper–Pearson
                nominal = 0.1
            degenerate = c["bootstrap_degenerate"] if p == "P1" else ci2[0] == ci2[1]
            rc = revised_class(ci2, hb, nominal, degenerate)
            lowp = " · low power" if c["low_power_flag_revised"] else ""
            rows.append(f"| {lab_design(d, s)} | {p} {'α' if p == 'P1' else 'γ'} = {t} | {f(est)} | {c['scans_selecting']}/{c['scans']} | "
                        f"{f(c['fdr_among_selecting'])} | {pc(c['share_fdp_gt_0.1'])} % | {f(ucb)} | {f(tl['mean'])} {ci(tl['ci95'])}; {f(tl['ucb95'])} ({f(tl['mc_se_ucb95'])}) | "
                        f"{f(hb)} | {CLS[rc]}{lowp} |")
    return "\n".join(rows)


BASE_PROCS = [("P1", "P1 conformal BH (pre-registered, primary)"),
              ("SUB", "one false candidate per calibration patient (first scan) + BH [post hoc]"),
              ("LR", "hierarchical conformal e-values + e-BH [post hoc]"),
              ("B2", "B2 conformal risk control, per-scan FDP loss (pre-registered)"),
              ("B3", "B3 Learn-then-Test, per-scan FDP loss, δ = 0.1 (pre-registered)"),
              ("B1", "B1 precision-matched threshold, no guarantee (pre-registered)")]


def t_baselines(design="D3"):
    sites = ("ms3seg", "muslim", "pedims") if design == "D3" else SITES
    rows = ["| procedure | α | " + " | ".join(SITE[s] for s in sites) + " |", "|---|---|" + "---|" * len(sites)]
    for p, lab in BASE_PROCS:
        for a in (0.1, 0.2):
            cells = []
            for s in sites:
                if p in ("P1", "B1", "B2", "B3"):
                    v = RES["designs"][f"ens|{design}"][f"{p}|{a}"][s]
                    est, c, sens, n = v["mean_fdp"], v["mean_fdp_ci"], v["sens_e2e"], v["n_sel"]
                elif p == "SUB":
                    v = MPH["B_baselines"][f"SUB|{design}|{s}|{a}"]
                    est, c, sens, n = v["estimate"], v["ci95"], v["sens_e2e"], v["n_sel_mean"]
                else:
                    v = MPH["B_baselines"][f"LRhier|{design}|{s}|{a}"]
                    est, c, sens, n = v["estimate"], v["ci95"], v["sens_e2e"], v["n_sel"]
                if p == "LR" and n == 0:
                    cells.append("no selection (sens. 0)")
                    continue
                cl = classify(c, a)
                if c[0] == c[1]:
                    cl = "not estimable"
                cells.append(f"{f(est)} {ci(c)} {CLS[cl]}; sens. {f(sens)}")
            rows.append(f"| {lab} | {a} | " + " | ".join(cells) + " |")
    return "\n".join(rows)


def t_bands():
    bb = RES["thickness"]["D2|by_band"]
    lab = {"B1": "G1 · 1-mm grid (MSLesSeg resampled from 2–5 mm; Ljubljana-10 3D 0.8 mm)",
           "B2": "G2 · PediMS (children, 3 T, spacing 3.9 mm)", "B3": "G3 · spacing 4.5–6.5 mm (Muslim 45, MS3SEG 31)",
           "B4": "G4 · spacing > 6.5 mm (MS3SEG 69 — one Toshiba scanner — and Muslim 6)"}
    rows = ["| cohort–acquisition group (pre-registered band) | scans / patients | P1 α = 0.1: FDR · sens. | P1 α = 0.2: FDR [95 % CI] | scans with FDP > 0.1 (α = 0.2) | P1 α = 0.2: sens. [95 % CI] | false / true selected lesions per scan (α = 0.2) | P2 γ = 0.1: FDX [95 % CI] · sens. |",
            "|---|---|---|---|---:|---|---|---|"]
    for b in ("B1", "B2", "B3", "B4"):
        p1a, p1, p2 = bb["P1|0.1"][b], bb["P1|0.2"][b], bb["P2|0.1"][b]
        g = p2["fdp_gt_0.1"]
        rows.append(f"| {lab[b]} | {p1['scans']} / {p1['patients']} | {f(p1a['mean_fdp'])} · {f(p1a['sens_e2e'])} | "
                    f"{f(p1['mean_fdp'])} {ci(p1['mean_fdp_ci'])} | {pc(p1['fdp_gt_0.1']['frac'])} % | "
                    f"{f(p1['sens_e2e'])} {ci(p1['sens_e2e_ci'])} | {f(p1['false_per_scan'], 2)} / {f(p1['true_per_scan'], 1)} | "
                    f"{f(g['frac'])} {ci([min(g['ci_boot'][0], g['ci_exact_scans'][0]), max(g['ci_boot'][1], g['ci_exact_scans'][1])])} · {f(p2['sens_e2e'])} |")
    return "\n".join(rows)


def t_sizes():
    sb = RES["thickness"]["size_bins"]
    lab = {"mslesseg": "MSLesSeg · 1-mm grid, resampled from 2–5 mm", "openms": "Ljubljana-10 · 3D, 0.8 mm",
           "pedims": "PediMS · 2D, spacing 3.9 mm (children)", "muslim": "Muslim · 2D, spacing 4.86–8.3 mm",
           "ms3seg": "MS3SEG · 2D, spacing 6.0–8.1 mm (one scanner)"}
    rows = ["| cohort · acquisition | lesions per bin (3–14 / 14–50 / 50–150 / 150–500 / ≥ 500 mm³) | raw sensitivity per bin | sensitivity at P1 α = 0.2 (leave-one-site-out) | raw ≥ 0.8 from | raw ≥ 0.5 from |",
            "|---|---|---|---|---|---|"]

    def mr(v):
        return "not reached" if v[0] is None else f"{v[0]:g} mm³"
    for s in ("mslesseg", "openms", "pedims", "muslim", "ms3seg"):
        rr = sb[f"site:{s}|D2|P1|0.2"]
        rows.append(f"| {lab[s]} | {' / '.join(str(n) for n in rr['n_lesions'])} | {' / '.join(f(x, 2) for x in rr['sens_raw'])} | "
                    f"{' / '.join(f(x, 2) for x in rr['sens_selected'])} | {mr(rr['min_reliable_raw_0.8'])} | {mr(rr['min_reliable_raw_0.5'])} |")
    for g in ("2-2.3 mm", "3 mm", "4-5 mm"):
        rr = NAT[f"group|{g}"]
        rows.append(f"| *within MSLesSeg, native {g.replace('-', '–')} [post hoc]* | {' / '.join(str(n) for n in rr['lesions_by_size_bin'])} | "
                    f"{' / '.join(f(x, 2) for x in rr['raw_sensitivity_by_size_bin'])} | — | — | — |")
    return "\n".join(rows)


def t_ensemble():
    q = RES["q3"]["paired_ens_minus_f0"]
    rows = ["| design · test set | α | realised FDR: ensemble / fold 0 | Δ FDR [95 % CI] | sensitivity: ensemble / fold 0 | Δ sensitivity [95 % CI] |",
            "|---|---|---|---|---|---|"]
    lab = {"D3|ALL": "1-mm → thick, all thick sites", "D3|ms3seg": "1-mm → MS3SEG", "D3|muslim": "1-mm → Muslim",
           "D3|pedims": "1-mm → PediMS", "D2|ALL": "leave-one-site-out, all sites", "D1|ALL": "within-site, all sites",
           "D4|ALL": "pooled 5-fold, all sites"}
    for a in (0.2, 0.1):
        for k in lab:
            rr = q.get(f"{k}|P1|{a}")
            if rr is None:
                continue
            m, s = rr["mean_fdp"], rr["sens_e2e"]
            rows.append(f"| {lab[k]} | {a} | {f(m['a'])} / {f(m['b'])} | {sg(m['diff'])} {ci(m['ci95'])} | {f(s['a'])} / {f(s['b'])} | {sg(s['diff'])} {ci(s['ci95'])} |")
    return "\n".join(rows)


def t_recal():
    rows = ["| site · procedure · mode | k = 3 | k = 10 | k = 40 | k* | 2000-draw re-estimate at k = 10 [post hoc]: mean (MC SE); sens. (MC SE) |",
            "|---|---|---|---|---|---|"]
    spec = [("ms3seg", "site_only", "P1", 0.2), ("ms3seg", "augmented", "P1", 0.1), ("ms3seg", "site_only", "P2", 0.1),
            ("ms3seg", "augmented", "P2", 0.1), ("muslim", "site_only", "P1", 0.2), ("muslim", "augmented", "P1", 0.1),
            ("muslim", "site_only", "P2", 0.1), ("muslim", "augmented", "P2", 0.1)]
    for site, mode, p, t in spec:
        c = RES["q4"][site]["cells"]
        ks = RES["q4"][site]["k_star"][f"{mode}|{p}|{t}"]["k_star"]
        mc = REV["d5_mc"][site][f"{mode}|{p}|{t}|k=10"]
        out = []
        for k in (3, 10, 40):
            rr = c[f"{mode}|{p}|{t}|k={k}"]
            if p == "P2" and mode == "site_only" and rr["n_sel_mean"] == 0:
                out.append("abstains (k < 9)")
            else:
                metric = "FDR" if p == "P1" else "FDX"
                out.append(f"{metric} {f(rr['realised_mean'])} ({pc(rr['share_draws_above_nominal'])} % of draws > nominal); sens. {f(rr['sens_e2e_mean'])}")
        mlab = "site patients only" if mode == "site_only" else "1-mm pool + k site patients"
        tl = f"α = {t}" if p == "P1" else f"γ = {t}"
        rows.append(f"| {SITE[site]} · {p} {tl} · {mlab} | " + " | ".join(out) + f" | {ks if ks is not None else 'none'} | "
                    f"{f(mc['realised_mean'])} ({f(mc['realised_mc_se'], 4)}); {f(mc['sens_mean'])} ({f(mc['sens_mc_se'], 4)}) |")
    return "\n".join(rows)


def t_controls():
    op = CTL["operating_points"]
    pools = [("1-mm sites", "ensemble · 1-mm-grid patient sites (primary)"), ("MSLesSeg only", "ensemble · MSLesSeg only"),
             ("all five patient sites", "ensemble · all five patient sites"), ("thick-slice sites", "ensemble · thick-slice sites")]
    rows = ["| arm · calibration pool | P1 α = 0.1 | P1 α = 0.2 | P2 γ = 0.1 (= 0.2) | B2 CRC α = 0.1 / 0.2 | B3 LTT α = 0.1 / 0.2 |",
            "|---|---|---|---|---|---|"]

    def cell(k, bold=False):
        rr = op[f"{k}|all100"]
        c = cp(rr["scans_with_any"], rr["n"])
        s = f"{rr['scans_with_any']} [{pc(c[0], 1)}, {pc(c[1], 1)}] {CLS[rr['class']]}"
        return f"**{s}**" if bold else s

    def short(k):
        rr = op[f"{k}|all100"]
        return f"{rr['scans_with_any']} {CLS[rr['class']]}"
    for arm in ("ens", "f0"):
        for pk, lab in pools:
            if arm == "f0":
                lab = lab.replace("ensemble", "fold 0").replace(" (primary)", "")
            prim = arm == "ens" and pk == "1-mm sites"
            rows.append(f"| {lab} | {cell(f'{arm}|{pk}|P1|0.1', prim)} | {cell(f'{arm}|{pk}|P1|0.2', prim)} | {cell(f'{arm}|{pk}|P2|0.1', prim)} | "
                        f"{short(f'{arm}|{pk}|B2|0.1')} / {short(f'{arm}|{pk}|B2|0.2')} | {short(f'{arm}|{pk}|B3|0.1')} / {short(f'{arm}|{pk}|B3|0.2')} |")
        k = f"{arm}|own-null floor (leave-one-control-out)"
        r1, r2 = op[f"{k}|P1|0.1|all100"], op[f"{k}|P1|0.2|all100"]
        c1, c2 = cp(r1["scans_with_any"], r1["n"]), cp(r2["scans_with_any"], r2["n"])
        name = "ensemble" if arm == "ens" else "fold 0"
        rows.append(f"| {name} · own null (leave-one-control-out; exchangeable by construction) | {r1['scans_with_any']} [{pc(c1[0], 1)}, {pc(c1[1], 1)}] | "
                    f"{r2['scans_with_any']} [{pc(c2[0], 1)}, {pc(c2[1], 1)}] | — | — | — |")
    return "\n".join(rows)


# ------------------------------------------------------------------ appendix tables
def t_within():
    rows = ["| site | P1 α = 0.1: FDR · sens. | P1 α = 0.2: FDR · sens. | P2 γ = 0.1: FDX · sens. |", "|---|---|---|---|"]
    for s in SITES:
        a, b, c = (RES["designs"]["ens|D1"][p][s] for p in ("P1|0.1", "P1|0.2", "P2|0.1"))
        p2 = "abstains (8 calibration patients < 9)" if c["n_sel"] == 0 else f"{f(c['fdp_gt_0.1']['frac'])} · {f(c['sens_e2e'])}"
        rows.append(f"| {SITE[s]} | {f(a['mean_fdp'])} · {f(a['sens_e2e'])} | {f(b['mean_fdp'])} · {f(b['sens_e2e'])} | {p2} |")
    return "\n".join(rows)


def t_noLj():
    A = MPH["A_site_seen_sensitivity"]
    rows = ["| design · test site | cell | pre-registered pools (with Ljubljana-10) | Ljubljana removed from every pool [post hoc] |", "|---|---|---|---|"]
    for key, c in A.items():
        d, s, p, t = key.split("|")
        pr = c.get("preregistered_with_Ljubljana")
        if pr is None:
            continue
        k = 3 if p == "P1" else 2
        pre = [x for x in RES["primary"] if x["design"] == d.split("-")[0] and x["site"] == s and x["procedure"] == p and x["target"] == float(t)][0]
        rows.append(f"| {('1-mm grid → ' if d.startswith('D3') else 'leave-one-site-out · ') + SITE[s]} | {p} {'α' if p == 'P1' else 'γ'} = {t} | "
                    f"{f(pre['estimate'], k)} {ci(pre['ci95'], k)} {CLS[pre['class']]}; sens. {f(pre['sens_e2e'])} | "
                    f"{f(c['estimate'], k)} {ci(c['ci95'], k)} {CLS[c['class']]}; sens. {f(c['sens_e2e'])} |")
    return "\n".join(rows)


def t_d3_quantities():
    rows = ["| site | procedure | α | realised FDR (empty = 0) | scans selecting | FDR among selecting scans | micro-FDR | scans with FDP > 0.1 | sens. | Hoeffding–Bentkus bound |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for s in ("ms3seg", "muslim", "pedims"):
        for p in ("P1", "B2", "B3", "B1"):
            for a in (0.1, 0.2):
                c = REV["cells"][f"D3|{s}|{p}|{a}"]
                rows.append(f"| {SITE[s]} | {p} | {a} | {f(c['realised_fdr'])} | {c['scans_selecting']}/{c['scans']} | {f(c['fdr_among_selecting'])} | "
                            f"{f(c['micro_fdr'])} | {pc(c['share_fdp_gt_0.1'])} % | {f(c['sens_e2e'])} | {f(c['realised_fdr_ucb95_hb_patients'])} |")
    return "\n".join(rows)


def t_frontier_summary():
    F = REV["frontier_d3"]
    rows = ["| site | realised FDR at matched sensitivity | P1 | SUB | B2 | B3 | B1 |", "|---|---|---|---|---|---|---|"]
    for s in ("ms3seg", "muslim", "pedims"):
        for tgt in (0.2, 0.3):
            rows.append(f"| {SITE[s]} | sensitivity {tgt} | " + " | ".join(f(F[f"{s}|{p}|fdr_at_sens_{tgt}"]) if F[f"{s}|{p}|fdr_at_sens_{tgt}"] is not None else "not reached"
                                                                          for p in ("P1", "SUB", "B2", "B3", "B1")) + " |")
    return "\n".join(rows)


def t_frontier_grid():
    F = REV["frontier_d3"]
    grid = (0.05, 0.1, 0.15, 0.2, 0.25, 0.3)
    rows = ["| site · procedure | " + " | ".join(f"α = {a}" for a in grid) + " |", "|---|" + "---|" * len(grid)]
    for s in ("ms3seg", "muslim", "pedims"):
        for p in ("P1", "SUB", "B2", "B3", "B1"):
            rows.append(f"| {SITE[s]} · {p} | " + " | ".join(
                f"{f(F[f'{s}|{p}|{a}']['realised_fdr'])} {ci(F[f'{s}|{p}|{a}']['realised_fdr_ci95'])} / {f(F[f'{s}|{p}|{a}']['sens_e2e'])}" for a in grid) + " |")
    return "\n".join(rows)


def t_simulation():
    S = REV["simulation"]["scenarios"]
    rows = ["| scan-level ICC ρ | shift of test false scores (SD) | α | realised FDR (MC SE) | α · mean per-scan π0 | scans with FDP > 0.1 | FDR among selecting scans |",
            "|---|---|---|---|---|---|---|"]
    for rho in ("0.0", "0.03", "0.1", "0.2"):
        for sh in ("0.0", "0.15", "0.3"):
            for a in ("0.1", "0.2"):
                v = S[f"rho={rho}|shift={sh}"][a]
                rows.append(f"| {rho} | {sh} | {a} | {f(v['fdr']['mean'])} ({f(v['fdr']['mc_se'], 4)}) | {f(v['pi0']['mean'])} | {pc(v['exc']['mean'])} % | {f(v['fdr_sel']['mean'])} |")
    return "\n".join(rows)


def t_mc():
    rows = ["| quantity | 200 draws (pre-registered / manuscript v1) | 2000 draws [post hoc]: mean | MC SE (2000) | MC SE a 200-draw mean would have |",
            "|---|---|---|---|---|"]
    for site in ("ms3seg", "muslim"):
        for key, lab in (("site_only|P2|0.1|k=10", "P2 γ = 0.1, site only, k = 10"), ("site_only|P1|0.2|k=10", "P1 α = 0.2, site only, k = 10"),
                         ("augmented|P1|0.1|k=10", "P1 α = 0.1, 1-mm pool + 10"), ("augmented|P2|0.1|k=10", "P2 γ = 0.1, 1-mm pool + 10")):
            pre = RES["q4"][site]["cells"][key]
            mc = REV["d5_mc"][site][key]
            rows.append(f"| {SITE[site]} · {lab} · realised | {f(pre['realised_mean'])} | {f(mc['realised_mean'])} | {f(mc['realised_mc_se'], 4)} | {f(mc['mc_se_if_200_draws']['realised'], 4)} |")
            rows.append(f"| {SITE[site]} · {lab} · sensitivity | {f(pre['sens_e2e_mean'])} | {f(mc['sens_mean'])} | {f(mc['sens_mc_se'], 4)} | {f(mc['mc_se_if_200_draws']['sens'], 4)} |")
    for s in ("ms3seg", "muslim", "pedims"):
        for a in (0.1, 0.2):
            pre = MPH["B_baselines"][f"SUB|D3|{s}|{a}"]
            mc = REV["sub_mc"][f"{s}|{a}"]
            rows.append(f"| SUB · {SITE[s]} · α = {a} · realised FDR | {f(pre['estimate'])} | {f(mc['realised_mean'])} | {f(mc['realised_mc_se'], 4)} | {f(mc['mc_se_if_200_draws'], 4)} |")
    return "\n".join(rows)


def t_paired_auroc():
    rows = ["| site | AUROC, 5-fold mean | AUROC of each fold's mean on the same (ensemble) candidates | ensemble − fold 0 [95 % CI] | ensemble − best single fold |",
            "|---|---|---|---|---|"]
    for s in SITES:
        v = REV["paired_auroc"][s]
        rows.append(f"| {SITE[s]} | {f(v['auroc_ensemble_mean'])} | {' / '.join(f(x) for x in v['auroc_fold_mean_on_ensemble_candidates'])} | "
                    f"{sg(v['diff_ens_minus_fold0'])} {ci(v['diff_ens_minus_fold0_ci95'])} | {sg(v['diff_ens_minus_best_fold'])} |")
    return "\n".join(rows)


def t_sensitivity_analyses():
    S = RES["sensitivity"]
    rows = ["| design · test site | cell | primary (lenient IoU > 0) | strict matching (IoU ≥ 0.10) | consensus score S_cons | PediMS without patient P9 |",
            "|---|---|---|---|---|---|"]
    for d, s in ORDER:
        for p, t in (("P1", 0.1), ("P1", 0.2), ("P2", 0.1), ("P2", 0.2)):
            k = 3 if p == "P1" else 2
            pre = [x for x in RES["primary"] if x["design"] == d and x["site"] == s and x["procedure"] == p and x["target"] == t][0]
            out = [f"{f(pre['estimate'], k)} {CLS[pre['class']]}; sens. {f(pre['sens_e2e'])}"]
            for tag in ("strict_IoU0.10", "consensus_score", "pedims_without_P9"):
                v = S.get(f"{tag}|{d}|{s}|{p}|{t}")
                out.append("—" if v is None else f"{f(v['estimate'], k)} {ci(v['ci95'], k)} {CLS[v['class']]}; sens. {f(v['sens_e2e'])}")
            rows.append(f"| {lab_design(d, s)} | {p} {'α' if p == 'P1' else 'γ'} = {t} | " + " | ".join(out) + " |")
    return "\n".join(rows)


def t_alpha03():
    rows = ["| design · test site | P1 α = 0.3: realised FDR [95 % CI] → class; sens. |", "|---|---|"]
    for d, s in ORDER:
        v = RES["designs"][f"ens|{d}"]["P1|0.3"][s]
        rows.append(f"| {lab_design(d, s)} | {f(v['mean_fdp'])} {ci(v['mean_fdp_ci'])} {CLS[classify(v['mean_fdp_ci'], 0.3)]}; sens. {f(v['sens_e2e'])} |")
    return "\n".join(rows)


def t_sizes_p2():
    sb = RES["thickness"]["size_bins"]
    lab = {"B1": "G1 · 1-mm grid", "B2": "G2 · PediMS", "B3": "G3 · spacing 4.5–6.5 mm", "B4": "G4 · spacing > 6.5 mm"}
    rows = ["| group | sensitivity at P2 γ = 0.2 by lesion bin (3–14 / 14–50 / 50–150 / 150–500 / ≥ 500 mm³), leave-one-site-out |", "|---|---|"]
    for b in ("B1", "B2", "B3", "B4"):
        rr = sb[f"{b}|D2|P2|0.2"]
        rows.append(f"| {lab[b]} | {' / '.join(f(x, 2) for x in rr['sens_selected'])} |")
    return "\n".join(rows)


def t_d5_small():
    rows = ["| site · procedure · mode | k = 1 | k = 2 | k = 3 | k = 5 |", "|---|---|---|---|---|"]
    for site in ("pedims", "openms"):
        c = RES["q4"][site]["cells"]
        for mode, p, t in (("site_only", "P1", 0.1), ("site_only", "P1", 0.2), ("augmented", "P1", 0.1), ("augmented", "P2", 0.1)):
            out = []
            for k in (1, 2, 3, 5):
                rr = c.get(f"{mode}|{p}|{t}|k={k}")
                if rr is None:
                    out.append("—")
                elif p == "P2" and mode == "site_only" and rr["n_sel_mean"] == 0:
                    out.append("abstains")
                else:
                    out.append(f"{'FDR' if p == 'P1' else 'FDX'} {f(rr['realised_mean'])}; sens. {f(rr['sens_e2e_mean'])}")
            rows.append(f"| {SITE[site]} · {p} {'α' if p == 'P1' else 'γ'} = {t} · {'site only' if mode == 'site_only' else '1-mm pool + k'} | " + " | ".join(out) + " |")
    return "\n".join(rows)


def t_ratio():
    rows = ["| site | α | realised FDR, 1-mm calibration (D3) | realised FDR, within site (D1, pre-registered split) | ratio [95 % CI, patient-paired bootstrap] | D1 over 20 other fold splits: min–max | ratio over those splits: min–max |",
            "|---|---|---|---|---|---|---|"]
    for k, v in REV["ratio_d3_over_d1"].items():
        s, a = k.split("|")
        rows.append(f"| {SITE[s]} | {a} | {f(v['d3_fdr'])} | {f(v['d1_fdr_preregistered_split'])} | {f(v['ratio'], 2)} {ci(v['ratio_ci95_paired_bootstrap'], 2)} | "
                    f"{f(v['d1_fdr_other_splits']['min'])}–{f(v['d1_fdr_other_splits']['max'])} | {f(v['ratio_other_splits']['min'], 2)}–{f(v['ratio_other_splits']['max'], 2)} |")
    return "\n".join(rows)


TABLES = {"t1": t_cohorts, "t4": t_primary, "t4b": t_primary_bounds, "t5": t_baselines, "t6": t_bands, "t7": t_sizes,
          "t8": t_ensemble, "t9": t_recal, "t10": t_controls, "tA1": t_within, "tA2": lambda: t_baselines("D2"),
          "tA3": t_noLj, "tA4": t_d3_quantities, "tA5": t_frontier_summary, "tA6": t_frontier_grid, "tA7": t_simulation,
          "tA8": t_mc, "tA9": t_paired_auroc, "tA10": t_sensitivity_analyses, "tA11": t_alpha03, "tA12": t_sizes_p2,
          "tA13": t_d5_small, "tA14": t_ratio}


def render(text):
    for key, fn in TABLES.items():
        pat = re.compile(rf"(<!-- BEGIN TABLE {key} -->\n)(.*?)(<!-- END TABLE {key} -->)", re.S)
        if not pat.search(text):
            raise SystemExit(f"marker for table {key} missing in manuscript.md")
        text = pat.sub(lambda m: m.group(1) + fn() + "\n" + m.group(3), text)
    return text


def main():
    with open(MANUSCRIPT, encoding="utf-8") as fh:
        old = fh.read()
    new = render(old)
    if "--check" in sys.argv:
        if new != old:
            raise SystemExit("TABLES OUT OF DATE: run make_tables.py")
        print("tables up to date")
        return
    with open(MANUSCRIPT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(new)
    print("tables written:", ", ".join(TABLES))


if __name__ == "__main__":
    main()
