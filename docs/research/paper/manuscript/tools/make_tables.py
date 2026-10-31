#!/usr/bin/env python3
"""Paper A manuscript — generate every results table from the committed records and write it
into manuscript.md between markers  <!-- BEGIN TABLE tX -->  and  <!-- END TABLE tX -->.

Idempotent: re-running replaces the table bodies only. `--check` regenerates the tables and fails
if manuscript.md differs (used by check_numbers.py). Numbers are never typed by hand into a table.

    python docs/research/paper/manuscript/tools/make_tables.py [--check]
"""
import json
import os
import re
import sys
from decimal import ROUND_HALF_UP, Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
MS_DIR = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(MS_DIR, "..", "..", "..", ".."))
REC = os.path.join(ROOT, "docs", "research", "records")
MANUSCRIPT = os.path.join(MS_DIR, "manuscript.md")


def load(name):
    with open(os.path.join(REC, name), encoding="utf-8") as f:
        return json.load(f)


RES = load("2026-10-21_paper_a_v03_results.json")
PH = load("2026-10-21_paper_a_v03_posthoc.json")
CTL = load("2026-10-24_paper_a_v03c_controls.json")
MPH = load("2026-10-31_paper_a_manuscript_posthoc.json")
NAT = load("2026-10-21_paper_a_v03_mslesseg_native.json")

SITE = {"mslesseg": "MSLesSeg", "openms": "Ljubljana-10", "ms3seg": "MS3SEG", "muslim": "Muslim", "pedims": "PediMS"}
CLS = {"holds": "holds", "inconclusive": "inconclusive", "violated": "**violated**"}


def r(x, k=3):
    """Round half up from the stored decimal representation (records hold 4-decimal values)."""
    q = Decimal(1).scaleb(-k)
    return str(Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP))


def f(x, k=3):
    return "—" if x is None else r(x, k)


def sg(x, k=3):
    return ("+" if x >= 0 else "") + f(x, k)


def ci(c, k=3):
    return "—" if c is None else f"[{r(c[0], k)}, {r(c[1], k)}]"


def classify(c, nominal, margin=0.05):
    if c is None:
        return "—"
    if c[0] > nominal:
        return "violated"
    return "holds" if c[1] <= nominal + margin else "inconclusive"


def t_cohorts():
    meta = {"mslesseg": ("Italy (Catania); 8 scanner models, 1.5/3 T", "2D/3D, native 2–5 mm (43 at 2–2.3, 52 at 3, 15 at 4–5, 5 unknown)", "MNI 1 mm (delivered)"),
            "openms": ("Slovenia (Ljubljana); Siemens 3 T", "3D, 0.47 × 0.47 × 0.8 mm", "MNI 1 mm (delivered)"),
            "ms3seg": ("Iran; Toshiba 1.5 T", "2D, slice spacing 6.0–8.1 mm (median 7.2)", "native"),
            "muslim": ("Iraq (Baghdad), ~20 centres; 1.5 T", "2D, 4.86–8.3 mm (median 6.0); in-plane pixel size estimated", "native"),
            "pedims": ("one centre; Siemens Skyra 3 T; 9 children", "2D, 0.75 × 0.75 × 3.9 mm", "native")}
    rows = ["| cohort | origin, scanner | scans / patients | native FLAIR geometry | grid analysed | detectable expert lesions | candidates (false) | candidate AUROC, 5-fold mean [95 % CI] | AUROC, single folds (range) |",
            "|---|---|---|---|---|---:|---|---|---|"]
    for s in ("mslesseg", "openms", "ms3seg", "muslim", "pedims"):
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
    order = [("D3", "ms3seg"), ("D3", "muslim"), ("D3", "pedims"), ("D2", "mslesseg"), ("D2", "openms"),
             ("D2", "ms3seg"), ("D2", "muslim"), ("D2", "pedims")]
    rows = ["| design · test site | P1, α = 0.1 (FDR) | P1, α = 0.2 (FDR) | P2, γ = 0.1 (FDX vs δ = 0.1) | P2, γ = 0.2 (FDX vs δ = 0.1) |",
            "|---|---|---|---|---|"]
    for d, s in order:
        lab = ("1-mm grid → " if d == "D3" else "leave-one-site-out · ") + SITE[s] + (" †" if s == "openms" else "")
        out = []
        for p, t in (("P1", 0.1), ("P1", 0.2), ("P2", 0.1), ("P2", 0.2)):
            c = cells[(d, s, p, t)]
            k = 3 if p == "P1" else 2
            ab = " (abst.)" if c["uninformative_abstention"] else ""
            star = "*" if (c["class"] == "holds" and c["estimate"] > c["nominal"]) else ""
            out.append(f"{f(c['estimate'], k)} {ci(c['ci95'], k)} {CLS[c['class']]}{star}{ab}; sens. {f(c['sens_e2e'])}; n = {c['n_sel']}")
        rows.append(f"| {lab} | " + " | ".join(out) + " |")
    return "\n".join(rows)


def t_baselines(design="D3"):
    sites = ("ms3seg", "muslim", "pedims") if design == "D3" else ("mslesseg", "openms", "ms3seg", "muslim", "pedims")
    procs = [("P1", "P1 conformal BH (pre-registered, primary)"),
             ("SUB", "one false candidate per calibration patient + BH [post hoc]"),
             ("LR", "hierarchical conformal e-values + e-BH [post hoc]"),
             ("B2", "B2 conformal risk control, per-scan FDP loss (pre-registered)"),
             ("B3", "B3 Learn-then-Test, per-scan FDP loss, δ = 0.1 (pre-registered)"),
             ("B1", "B1 precision-matched threshold, no guarantee (pre-registered)")]
    head = "| procedure | α | " + " | ".join(SITE[s] for s in sites) + " |"
    rows = [head, "|---|---|" + "---|" * len(sites)]
    for p, lab in procs:
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
                cells.append(f"{f(est)} {ci(c)} {CLS[cl]}; sens. {f(sens)}")
            rows.append(f"| {lab} | {a} | " + " | ".join(cells) + " |")
    return "\n".join(rows)


def t_bands():
    bb = RES["thickness"]["D2|by_band"]
    lab = {"B1": "≤ 1.5 mm grid (native: 10 at 0.8 mm, 110 at 2–5 mm, 5 unknown) — MSLesSeg, Ljubljana-10",
           "B2": "(1.5, 4.5] mm: 3.9 mm — PediMS", "B3": "(4.5, 6.5] mm — Muslim 45, MS3SEG 31",
           "B4": "> 6.5 mm — MS3SEG 69, Muslim 6"}
    rows = ["| band (slice spacing) · sites | scans / patients | P1 α = 0.1: FDR · sens. | P1 α = 0.2: FDR [95 % CI] | scans with FDP > 0.1 (α = 0.2) | P1 α = 0.2: sens. [95 % CI] | false / true selected lesions per scan (α = 0.2) | P2 γ = 0.1: FDX [95 % CI] · sens. |",
            "|---|---|---|---|---:|---|---|---|"]
    for b in ("B1", "B2", "B3", "B4"):
        p1a, p1, p2 = bb["P1|0.1"][b], bb["P1|0.2"][b], bb["P2|0.1"][b]
        rows.append(f"| {lab[b]} | {p1['scans']} / {p1['patients']} | {f(p1a['mean_fdp'])} · {f(p1a['sens_e2e'])} | "
                    f"{f(p1['mean_fdp'])} {ci(p1['mean_fdp_ci'])} | {f(p1['fdp_gt_0.1']['frac'] * 100, 0)} % | "
                    f"{f(p1['sens_e2e'])} {ci(p1['sens_e2e_ci'])} | {f(p1['false_per_scan'], 2)} / {f(p1['true_per_scan'], 1)} | "
                    f"{f(p2['fdp_gt_0.1']['frac'])} {ci([min(p2['fdp_gt_0.1']['ci_boot'][0], p2['fdp_gt_0.1']['ci_exact_scans'][0]), max(p2['fdp_gt_0.1']['ci_boot'][1], p2['fdp_gt_0.1']['ci_exact_scans'][1])])} · {f(p2['sens_e2e'])} |")
    return "\n".join(rows)


def t_sizes():
    sb = RES["thickness"]["size_bins"]
    lab = {"B1": "≤ 1.5 mm grid", "B2": "3.9 mm", "B3": "4.5–6.5 mm", "B4": "> 6.5 mm"}
    rows = ["| band | lesions per bin (3–14 / 14–50 / 50–150 / 150–500 / ≥ 500 mm³) | raw sensitivity per bin | sensitivity at P1 α = 0.2 (leave-one-site-out) | raw ≥ 0.8 from | raw ≥ 0.5 from |",
            "|---|---|---|---|---|---|"]

    def mr(v):
        return "not reached" if v[0] is None else f"{v[0]:g} mm³"
    for b in ("B1", "B2", "B3", "B4"):
        rr = sb[f"{b}|D2|P1|0.2"]
        rows.append(f"| {lab[b]} | {' / '.join(str(n) for n in rr['n_lesions'])} | {' / '.join(f(x, 2) for x in rr['sens_raw'])} | "
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
            r = q.get(f"{k}|P1|{a}")
            if r is None:
                continue
            m, s = r["mean_fdp"], r["sens_e2e"]
            rows.append(f"| {lab[k]} | {a} | {f(m['a'])} / {f(m['b'])} | {sg(m['diff'])} {ci(m['ci95'])} | {f(s['a'])} / {f(s['b'])} | {sg(s['diff'])} {ci(s['ci95'])} |")
    return "\n".join(rows)


def t_recal():
    rows = ["| site · procedure · mode | k = 3 | k = 10 | k = 40 | k* |", "|---|---|---|---|---|"]
    spec = [("ms3seg", "site_only", "P1", 0.2), ("ms3seg", "augmented", "P1", 0.1), ("ms3seg", "site_only", "P2", 0.1),
            ("ms3seg", "augmented", "P2", 0.1), ("muslim", "site_only", "P1", 0.2), ("muslim", "augmented", "P1", 0.1),
            ("muslim", "site_only", "P2", 0.1), ("muslim", "augmented", "P2", 0.1)]
    for site, mode, p, t in spec:
        c = RES["q4"][site]["cells"]
        ks = RES["q4"][site]["k_star"][f"{mode}|{p}|{t}"]["k_star"]
        out = []
        for k in (3, 10, 40):
            r = c[f"{mode}|{p}|{t}|k={k}"]
            if p == "P2" and mode == "site_only" and r["n_sel_mean"] == 0:
                out.append("abstains (k < 9)")
            else:
                metric = "FDR" if p == "P1" else "FDX"
                out.append(f"{metric} {f(r['realised_mean'])} ({f(r['share_draws_above_nominal'] * 100, 0)} % of draws > nominal); sens. {f(r['sens_e2e_mean'])}")
        mlab = "site patients only" if mode == "site_only" else "1-mm pool + k site patients"
        tl = f"α = {t}" if p == "P1" else f"γ = {t}"
        rows.append(f"| {SITE[site]} · {p} {tl} · {mlab} | " + " | ".join(out) + f" | {ks if ks is not None else 'none'} |")
    return "\n".join(rows)


def t_controls():
    op = CTL["operating_points"]
    pools = [("1-mm sites", "ensemble · 1-mm-grid patient sites (primary)"), ("MSLesSeg only", "ensemble · MSLesSeg only"),
             ("all five patient sites", "ensemble · all five patient sites"), ("thick-slice sites", "ensemble · thick-slice sites")]
    rows = ["| arm · calibration pool | P1 α = 0.1 | P1 α = 0.2 | P2 γ = 0.1 (= 0.2) | B2 CRC α = 0.1 / 0.2 | B3 LTT α = 0.1 / 0.2 |",
            "|---|---|---|---|---|---|"]

    def cell(k, bold=False):
        r = op[f"{k}|all100"]
        s = f"{r['scans_with_any']} [{f(r['ci95_exact'][0] * 100, 1)}, {f(r['ci95_exact'][1] * 100, 1)}] {CLS[r['class']]}"
        return f"**{s}**" if bold else s

    def short(k):
        r = op[f"{k}|all100"]
        return f"{r['scans_with_any']} {CLS[r['class']]}"
    for arm in ("ens", "f0"):
        for pk, lab in pools:
            if arm == "f0":
                lab = lab.replace("ensemble", "fold 0").replace(" (primary)", "")
            prim = arm == "ens" and pk == "1-mm sites"
            rows.append(f"| {lab} | {cell(f'{arm}|{pk}|P1|0.1', prim)} | {cell(f'{arm}|{pk}|P1|0.2', prim)} | {cell(f'{arm}|{pk}|P2|0.1', prim)} | "
                        f"{short(f'{arm}|{pk}|B2|0.1')} / {short(f'{arm}|{pk}|B2|0.2')} | {short(f'{arm}|{pk}|B3|0.1')} / {short(f'{arm}|{pk}|B3|0.2')} |")
        k = f"{arm}|own-null floor (leave-one-control-out)"
        r1, r2 = op[f"{k}|P1|0.1|all100"], op[f"{k}|P1|0.2|all100"]
        name = "ensemble" if arm == "ens" else "fold 0"
        rows.append(f"| {name} · own null (leave-one-control-out; exchangeable by construction) | {r1['scans_with_any']} [{f(r1['ci95_exact'][0] * 100, 1)}, {f(r1['ci95_exact'][1] * 100, 1)}] | "
                    f"{r2['scans_with_any']} [{f(r2['ci95_exact'][0] * 100, 1)}, {f(r2['ci95_exact'][1] * 100, 1)}] | — | — | — |")
    return "\n".join(rows)


def t_within():
    rows = ["| site | P1 α = 0.1: FDR · sens. | P1 α = 0.2: FDR · sens. | P2 γ = 0.1: FDX · sens. |", "|---|---|---|---|"]
    for s in ("mslesseg", "openms", "ms3seg", "muslim", "pedims"):
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
        lab = ("1-mm grid → " if d.startswith("D3") else "leave-one-site-out · ") + SITE[s]
        rows.append(f"| {lab} | {p} {'α' if p == 'P1' else 'γ'} = {t} | {f(pr['estimate'], k)} {ci(pr['ci95'], k)} {CLS[pr['class']]}; sens. {f(pr['sens_e2e'])} | "
                    f"{f(c['estimate'], k)} {ci(c['ci95'], k)} {CLS[c['class']]}; sens. {f(c['sens_e2e'])} |")
    return "\n".join(rows)


TABLES = {"t1": t_cohorts, "t4": t_primary, "t5": t_baselines, "t6": t_bands, "t7": t_sizes, "t8": t_ensemble,
          "t9": t_recal, "t10": t_controls, "tA1": t_within, "tA2": lambda: t_baselines("D2"), "tA3": t_noLj}


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
