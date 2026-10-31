#!/usr/bin/env python3
"""Check every number of the manuscript against the committed records and write NUMBERS_CHECK.md.

For each claim, the stored value(s) are read from ``../data/extracted_results.json`` (built from pinned
commits by extract_results.py), rounded half-up exactly as the text reports them, rendered with the
manuscript's typography (Unicode minus, thousands commas), and the rendered string must occur in
manuscript.md (whitespace-normalised). A claim FAILS if either the rendering differs or the string is
absent. Numbers that are not in a machine-readable record (protocol facts, dataset descriptors) are
listed in a second table with their source file and section, checked by reading.

Exit code 1 if any automatic check fails.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
DATA = BASE / "data" / "extracted_results.json"
MS = BASE / "manuscript.md"
OUT = BASE / "NUMBERS_CHECK.md"
MINUS = "−"


# ------------------------------------------------------------------ formatting
def f(x, nd=3, signed=False):
    q = Decimal(repr(float(x))).quantize(Decimal(1).scaleb(-nd), rounding=ROUND_HALF_UP)
    s = f"{q:f}"
    if s.startswith("-"):
        s = s[1:] if q == 0 else MINUS + s[1:]
    elif signed:
        s = "+" + s
    return s


def i(x):
    return f"{int(x):,}"


def pct(x, nd=0):
    return f(float(x) * 100, nd)


def ci(v, nd=3, signed=False):
    """[point, [lo, hi]] -> 'p [lo, hi]'."""
    return f"{f(v[0], nd, signed)} [{f(v[1][0], nd, signed)}, {f(v[1][1], nd, signed)}]"


def aci(rec, nd=3):
    """{'auroc', 'ci95'} -> 'a [lo, hi]'."""
    a = rec.get("auroc", rec.get("auroc_foldwise_mean"))
    return f"{f(a, nd)} [{f(rec['ci95'][0], nd)}, {f(rec['ci95'][1], nd)}]"


def dci(rec, key, nd=3):
    """delta with its CI from a record that stores key and key_ci95."""
    return f"{f(rec[key], nd, True)} [{f(rec[key + '_ci95'][0], nd, True)}, {f(rec[key + '_ci95'][1], nd, True)}]"


def utc(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")


def main() -> int:
    d = json.loads(DATA.read_text(encoding="utf-8"))
    text = re.sub(r"\s+", " ", MS.read_text(encoding="utf-8").replace("*", ""))  # emphasis markers ignored
    ft, v3, v31, v32, comp, pre = d["flames_thick"], d["v3"], d["v31"], d["v32"], d["compute"], d["preregistration"]
    s1 = ft["S1_size"]

    def sens(band, arm, b):
        return next(x["sens"] for x in s1[f"{band}|{arm}"]["bins"] if x["bin"] == b)

    S2 = ft["S2_by_site"]
    ext_p1 = v31["posthoc_P1_mean5"]
    h1 = v32["H1"]
    h3 = v32["H3"]
    k2 = v32["K2"]
    k3 = v32["K3"]
    dc = v31["derived_external_candidate_counts"]
    push = {e["event"].split(" (")[0]: e["utc"] for e in d["public_push_evidence"]}
    kag = {k["run_id"]: k for k in comp["kaggle_sessions"]}

    F = "flames_thick_results.json"
    V3, V3P = "lesion_detector_v3_evaluation.json", "lesion_detector_v3_posthoc_checks.json"
    V31, V31P = "lesion_detector_v31_evaluation.json", "lesion_detector_v31_posthoc_checks.json"
    V32, LED = "lesion_detector_v32_evaluation.json", "compute_ledger.csv / kaggle_runs.csv"

    # (id, what, rendered string that must appear, source file, key)
    C = []

    def add(cid, what, rendered, src, key):
        C.append((cid, what, rendered, src, key))

    # ---------------- Study 1
    add("S1-n", "evaluation scans", f"All {ft['n_scans']} scans", F, "n_scans")
    add("S1-n2", "thick scans / patients", f"{ft['H1']['n']} scans, {ft['H1']['patients']} patients", F, "H1.n, H1.patients")
    add("S1-H1", "H1 delta F1 A-R", ci(ft["H1"]["delta_f1"], 3, True), F, "H1.delta_f1")
    add("S1-H1fp", "H1 false-lesion ratio", ci(ft["H1"]["fp_ratio"], 3), F, "H1.fp_ratio")
    add("S1-H1f1", "H1 mean F1", f"(A {f(ft['H1']['mean_f1']['A'])} vs R {f(ft['H1']['mean_f1']['R'])})", F, "H1.mean_f1")
    add("S1-H1fpn", "H1 false lesions/scan", f"({f(ft['H1']['mean_fp']['A'], 2)} vs {f(ft['H1']['mean_fp']['R'], 2)} per scan)", F, "H1.mean_fp")
    for site, lab in [("ms3seg", "MS3SEG"), ("muslim", "Muslim"), ("pedims", "PediMS")]:
        add(f"S1-site-{site}", f"H1 delta F1 {lab}", f"{ci(ft['H1_by_site'][site]['delta_f1'], 3, True)} for {lab}", F,
            f"H1_by_site.{site}.delta_f1")
    r = [f(ft["H1_by_site"][s]["fp_ratio"][0]) for s in ("ms3seg", "muslim", "pedims")]
    add("S1-site-fp", "per-site false-lesion ratio", f"{r[0]}, {r[1]} and {r[2]}", F, "H1_by_site.*.fp_ratio")
    add("S1-S6s", "S6 strict matching", f"Strict matching gave {ci(ft['S6_strict']['delta_f1'], 3, True)}", F, "S6_strict.delta_f1")
    add("S1-S6p9", "S6 without PediMS P9", ci(ft["S6_without_pedims_P9"]["delta_f1"], 3, True), F, "S6_without_pedims_P9.delta_f1")
    h2 = ft["H2"]
    add("S1-H2", "H2 pooled dDice / dF1", f"{ci(h2['delta_dice'], 3, True)} / {ci(h2['delta_f1'], 3, True)}", F, "H2.delta_dice, H2.delta_f1")
    add("S1-H2lj", "H2 Ljubljana guard rail", f"{f(h2['ljubljana_delta_dice'], 3, True)} / {f(h2['ljubljana_delta_f1'], 3, True)}", F,
        "H2.ljubljana_delta_dice/f1")
    add("S1-H2lj-abs", "abstract: Ljubljana Dice drop", f"Dice fell by {f(-h2['ljubljana_delta_dice'])}", F, "H2.ljubljana_delta_dice")
    add("S1-H3", "H3 A-B delta F1", ci(ft["S3_A_vs_B"]["delta_f1"], 3, True), F, "S3_A_vs_B.delta_f1")
    add("S1-H3fp", "H3 A/B false-lesion ratio", ci(ft["S3_A_vs_B"]["fp_ratio"], 3), F, "S3_A_vs_B.fp_ratio")
    add("S1-BR", "B vs R delta F1", ci(ft["B_vs_R_thick"]["delta_f1"], 3, True), F, "B_vs_R_thick.delta_f1")
    add("S1-BRfp", "B vs R false-lesion ratio", ci(ft["B_vs_R_thick"]["fp_ratio"], 3), F, "B_vs_R_thick.fp_ratio")
    add("S1-S4", "S4 A vs E delta F1", ci(ft["S4_A_vs_E"]["delta_f1"], 3, True), F, "S4_A_vs_E.delta_f1")
    add("S1-S4fp", "S4 A/E false-lesion ratio", ci(ft["S4_A_vs_E"]["fp_ratio"], 3), F, "S4_A_vs_E.fp_ratio")
    add("S1-BA", "B vs A mean F1", f"B's F1 was {f(ft['S3_A_vs_B']['mean_f1']['B'])} against A's {f(ft['S3_A_vs_B']['mean_f1']['A'])}", F,
        "S3_A_vs_B.mean_f1")
    add("S1-BAfp", "B vs A false lesions", f"({f(ft['S3_A_vs_B']['mean_fp']['B'], 2)} against {f(ft['S3_A_vs_B']['mean_fp']['A'], 2)} per scan)",
        F, "S3_A_vs_B.mean_fp")
    add("S1-S1small", "S1 14-50 mm3 detection, B3/B4",
        f"{f(sens('B3','A','[14,50)'),2)} against {f(sens('B3','R','[14,50)'),2)} for R at 4.5–6.5 mm, and "
        f"{f(sens('B4','A','[14,50)'),2)} against {f(sens('B4','R','[14,50)'),2)} above 6.5 mm", F, "S1_size.B3|A, B3|R, B4|A, B4|R [14,50)")
    add("S1-S1large", "S1 >=500 mm3 detection, B3/B4",
        f"{f(sens('B3','A','>=500'),2)} against {f(sens('B3','R','>=500'),2)}, and {f(sens('B4','A','>=500'),2)} against "
        f"{f(sens('B4','R','>=500'),2)}", F, "S1_size.B3/B4 >=500")
    ok50 = all(s1[f"{b}|{a}"]["min_size_50"] == "[50,150)" for b in ("B3", "B4") for a in "RAEB")
    add("S1-S1-50", "50 % size [50,150) for every arm in B3, B4", "stayed at 50–150 mm³ for every arm" if ok50 else "<mismatch>",
        F, "S1_size.B3|*, B4|*.min_size_50")
    add("S1-S1tiny", "S1 3-14 mm3 detection at B1",
        f"from {f(sens('B1','R','[3,14)'),2)} (R) to {f(sens('B1','B','[3,14)'),2)} (B) and {f(sens('B1','A','[3,14)'),2)} (A)", F,
        "S1_size.B1|R/B/A [3,14)")
    add("S1-S2msl", "S2 MSLesSeg test F1",
        f"from {f(S2['mslesseg']['R']['f1'],2)} (R) to {f(S2['mslesseg']['A']['f1'],2)} (A) and {f(S2['mslesseg']['B']['f1'],2)} (B)", F,
        "S2_by_site.mslesseg.*.f1")
    add("S1-S2mslfp", "S2 MSLesSeg test false lesions",
        f"from {f(S2['mslesseg']['R']['fp'],2)} to {f(S2['mslesseg']['A']['fp'],2)} and {f(S2['mslesseg']['B']['fp'],2)} per scan", F,
        "S2_by_site.mslesseg.*.fp")
    s5 = ft["S5_mslesseg_by_native_thickness"]
    add("S1-S5", "S5 4-5 mm vs <=3 mm",
        f"for the {s5['4-5mm']['n']} acquired at 4–5 mm (ΔF1 {f(s5['4-5mm']['delta_f1_mean'],3,True)}, ΔDice "
        f"{f(s5['4-5mm']['delta_dice_mean'],3,True)}) compared with the {s5['<=3mm']['n']} acquired at ≤ 3 mm "
        f"({f(s5['<=3mm']['delta_f1_mean'],3,True)}, {f(s5['<=3mm']['delta_dice_mean'],3,True)})", F, "S5_mslesseg_by_native_thickness")
    lj = S2["openms"]
    add("S1-S2lj", "S2 Ljubljana sensitivity and precision",
        f"{f(lj['R']['sens'],2)} for R, {f(lj['B']['sens'],2)} for B and {f(lj['A']['sens'],2)} for A, with precision "
        f"{f(lj['R']['prec'],2)}, {f(lj['B']['prec'],2)} and {f(lj['A']['prec'],2)}", F, "S2_by_site.openms.*.sens/prec")
    add("S1-intro19", "false lesions cut by 19 % (1 - ratio)", f"by {pct(1 - ft['H1']['fp_ratio'][0])} %", F, "1 - H1.fp_ratio[0] (derived)")
    add("S1-S4b", "S4 point estimate in text", f"(S4: ΔF1 {f(ft['S4_A_vs_E']['delta_f1'][0],3,True)})", F, "S4_A_vs_E.delta_f1[0]")

    # ---------------- compute
    add("CMP-kag", "Kaggle study session hours", f"{f(comp['kaggle_quota_hours_study'],1)} h of session time", LED, "kaggle_runs full-s1..s3")
    mod = d["flames_thick_models"]
    add("S1-S7", "whole-scan validation Dice on the 15 monitoring scans",
        f"whole-scan validation Dice was {f(mod['flames-thick-a']['internal_validation_dice'])} (A) and "
        f"{f(mod['flames-thick-b']['internal_validation_dice'])} (B)", "kaggle/models.json", "models.*.internal_validation_final.dice_mean_15_scans")
    add("CMP-kag2", "Kaggle smoke + pilot hours", f"{f(comp['kaggle_quota_hours_all'] - comp['kaggle_quota_hours_study'],2)} h of smoke and pilot",
        LED, "kaggle_runs smoke+pilot (derived)")
    add("CMP-evalh", "evaluation VM-hours", f"{f(comp['flames_thick_eval_vm_hours'],2)} VM-hours", LED, "flames-thick-eval-*")
    add("CMP-evalc", "evaluation cost", f"{f(comp['flames_thick_eval_cost_usd_list'],2)} USD at list price", LED, "flames-thick-eval-*")
    add("CMP-shh", "shared upstream VM-hours", f"{f(comp['shared_upstream_vm_hours'],2)} VM-hours", LED, "shared upstream runs")
    add("CMP-shc", "shared upstream cost", f"{f(comp['shared_upstream_cost_usd_list'],2)} USD at list price", LED, "shared upstream runs")
    add("CMP-tot", "research project total", f"{f(comp['research_project_total_cost_usd_list'],2)} USD", LED, "all mstool-research rows")
    add("CMP-rt", "Study 2 evaluation runtimes",
        f"v3 {f(v3['runtime_s']/60,0)} min, v3.1 {f(v31['runtime_s']/60,1)} min, v3.2 {f(v32['runtime_s']/60,1)} min", "records", "runtime_s")
    add("CMP-abs", "abstract: Study 1 evaluation cost", f"{f(comp['flames_thick_eval_cost_usd_list'],2)} USD (list price)", LED, "flames-thick-eval-*")

    # ---------------- v3
    g = v3["reproduction_gate"]
    add("V3-gate", "v3 reproduction gate",
        f"{i(g['M']['candidates'])} candidates ({i(g['M']['false_lenient'])} false) in MSLesSeg, {i(g['L10']['candidates'])} "
        f"({i(g['L10']['false_lenient'])}) in Ljubljana-10 and {i(g['C']['candidates'])} in {g['C']['scans']} controls", V3, "reproduction_gate")
    p = v3["primary_pooled_loco"]
    add("V3-n", "v3 pooled candidates", f"{i(p['_n']['candidates'])} candidates from {p['_n']['patients']} patients", V3, "primary_pooled_loco._n")
    add("V3-prim", "v3 V3-LR vs raw",
        f"{aci(p['V3-LR'])} for V3-LR against {aci(p['RAW'])} for raw probability, a difference of {dci(p['V3-LR'], 'delta_vs_RAW')}",
        V3, "primary_pooled_loco")
    add("V3-abs", "abstract: v3 delta", f"(ΔAUROC {dci(p['V3-LR'], 'delta_vs_RAW')})", V3, "primary_pooled_loco.V3-LR")
    w = v3["S1_within_cohort"]["M"]
    add("V3-withinM", "within MSLesSeg",
        f"{f(w['V3-LR']['auroc'])} against {f(w['RAW']['auroc'])}, {dci(w['V3-LR'], 'delta_vs_RAW')}", V3, "S1_within_cohort.M")
    a = v3["S2_loco_per_direction"]["A_M_to_L10"]
    add("V3-dirA", "direction A M->L10",
        f"{f(a['V3-LR']['auroc'])} against {f(a['RAW']['auroc'])}, {dci(a['V3-LR'], 'delta_vs_RAW')}", V3, "S2_loco_per_direction.A_M_to_L10")
    add("V3-refA", "direction A refits below raw",
        f"{int(round(v3['posthoc_P2_direction_A_refits']['frac_refits_below_raw'] * 50))} of {v3['posthoc_P2_direction_A_refits']['n_refits']} refits below",
        V3P, "P2_direction_A_refit_variance")
    add("V3-refB", "direction B refits below raw", f"{pct(v3['A5_small_n']['direction_B_refit_variance']['frac_refits_below_raw'])} % of refits",
        V3, "A5_small_n.direction_B_refit_variance")
    pp = v3["posthoc_P1_same_model"]["pooled"]
    add("V3-P1", "new families vs v2 features, same LR",
        f"{f(pp['delta'],3,True)} [{f(pp['delta_ci95'][0],3,True)}, {f(pp['delta_ci95'][1],3,True)}]", V3P, "P1_v3_minus_v2_same_model.pooled")
    a3 = v3["A3_site_identity_auroc"]
    add("V3-A3", "cohort identity, all v3 features", f"AUROC {f(a3['V3_all'],2)}", V3, "A3_site_identity_auroc.V3_all")
    add("V3-A3b", "cohort identity, FLAIR boundary", f"FLAIR boundary family alone reached {f(a3['F4_flair_boundary'],2)}", V3,
        "A3_site_identity_auroc.F4_flair_boundary")
    add("V3-S5", "controls, raw probability", aci(v3["S5_controls_auroc"]["RAW"]), V3, "S5_controls.auroc_L10true_vs_control.RAW")
    add("V3-v2", "v2 as shipped under clean protocol", f"(0.639 against 0.624)" if f(p["V2-shipped"]["auroc"]) == "0.639" else "<mismatch>",
        V3, "primary_pooled_loco.V2-shipped.auroc (0.624 = August record, manual)")
    bl = v3["base_rates"]
    add("V3-frag", "fragment share of FALSE, in-sample vs clean Ljubljana",
        f"{pct(bl['Ltr']['fragment_false_share'])} % of the false candidates are fragments of real lesions, against "
        f"{pct(bl['L10']['fragment_false_share'])} %",
        V3, "base_rates.Ltr/L10.fragment_false_share")

    # ---------------- v3.1
    pe = v31["primary_pooled_external"]
    add("V31-n", "external candidates", f"{i(pe['_n']['candidates'])} fold-0 candidates, {pe['_n']['patients']} patients", V31,
        "primary_pooled_external._n")
    add("V31-prim", "GR-LR vs raw fold-0",
        f"{aci(pe['GR-LR'])} for GR-LR against {aci(pe['RAW'])} for raw fold-0 probability, a difference of {dci(pe['GR-LR'], 'delta_vs_RAW')}",
        V31, "primary_pooled_external")
    add("V31-abs", "abstract: 0.721 -> 0.832", f"AUROC {f(pe['RAW']['auroc'])} → {f(pe['GR-LR']['auroc'])}", V31, "primary_pooled_external")
    add("V31-intro", "intro: 0.72 -> 0.83", f"from {f(pe['RAW']['auroc'],2)} to {f(pe['GR-LR']['auroc'],2)}", V31, "primary_pooled_external")
    ps = v31["S_per_site_external"]
    add("V31-sites", "per-site delta vs raw",
        f"{dci(ps['ms3seg']['GR-LR'], 'delta_vs_RAW')} for MS3SEG, {dci(ps['muslim']['GR-LR'], 'delta_vs_RAW')} for Muslim and "
        f"{dci(ps['pedims']['GR-LR'], 'delta_vs_RAW')} for PediMS", V31, "S_per_site_external.*.GR-LR.delta_vs_RAW")
    add("V31-ens", "ensemble mean on fold-0 candidates", aci(pe["ENS-RAW"]), V31, "primary_pooled_external.ENS-RAW")
    cr = v31["criteria"]
    add("V31-H2", "H2 GR-LR vs ensemble", f"by {f(cr['H2_delta_vs_ENS_RAW'],3,True)} [{f(cr['H2_ci95'][0],3,True)}, {f(cr['H2_ci95'][1],3,True)}]",
        V31, "criteria.H2")
    add("V31-H3", "H3 fold disagreement adds",
        f"added {f(cr['H3_delta_vs_GR_noENS'],3,True)} [{f(cr['H3_ci95'][0],3,True)}, {f(cr['H3_ci95'][1],3,True)}]", V31, "criteria.H3")
    b5 = v31["B5_refit_variance_external"]
    add("V31-B5", "refit variance", f"{f(b5['auroc_mean'])} [{f(b5['p2.5_p97.5'][0])}, {f(b5['p2.5_p97.5'][1])}], none below raw"
        if b5["frac_refits_below_raw"] == 0 else "<mismatch>", V31, "B5_refit_variance_external")
    h4 = v31["H4_site_signature_M_vs_L10"]["site_identity_auroc"]
    add("V31-H4", "cohort identity F8 vs FLAIR",
        f"AUROC {f(h4['F8_fold_disagreement'])}, against {f(h4['F1_flair_contrast'])}–{f(h4['F4_flair_boundary'])} for the FLAIR families",
        V31, "H4_site_signature_M_vs_L10.site_identity_auroc")
    h4b = v31["H4b_site_signature_M_vs_new_sites"]
    add("V31-H4b", "cohort identity F8, MS3SEG and Muslim",
        f"MS3SEG ({f(h4b['ms3seg']['site_identity_auroc']['F8_fold_disagreement'])}) and Muslim "
        f"({f(h4b['muslim']['site_identity_auroc']['F8_fold_disagreement'])})", V31, "H4b_site_signature_M_vs_new_sites")
    pm = ext_p1["pooled_external"]
    add("V31-ph1", "post hoc: ensemble mean on ensemble candidates", f"reaches {aci(pm['RAW'])}", V31P, "P1_mean5_candidates.pooled_external.RAW")
    add("V31-ph2", "post hoc: GR-LR on ensemble candidates",
        f"GR-LR then reaches {aci(pm['GR-LR'])}, a gain of only {dci(pm['GR-LR'], 'delta_vs_RAW')}", V31P, "P1_mean5_candidates.pooled_external.GR-LR")
    add("V31-ph3", "post hoc: fold disagreement adds to GR", f"contributes {f(pm['GR-LR']['delta_vs_GR-noENS-LR'],3,True)} over",
        V31P, "P1_mean5_candidates.pooled_external.GR-LR.delta_vs_GR-noENS-LR")
    add("V31-cand", "ensemble candidates: net change in false and true counts",
        f"{i(dc['false_removed'])} fewer false candidates ({i(dc['mean5_false'])} vs {i(dc['fold0_false'])}; "
        f"{MINUS}{pct(dc['false_removed_share'],1)} %) and {i(dc['true_removed'])} fewer true ones ({i(dc['mean5_true'])} vs "
        f"{i(dc['fold0_true'])}; {MINUS}{pct(dc['true_removed_share'],1)} %)", V31P, "P2_candidates_fold0_vs_mean5 (derived net counts)")
    add("V31-cand2", "Lesson 3 restatement", f"yields {pct(dc['false_removed_share'],1)} % fewer false candidates and "
        f"{pct(dc['true_removed_share'],1)} % fewer true ones", V31P, "P2 (derived)")
    sep = v31["H4_site_signature_M_vs_L10"]["paired_separability_differences"]["F9_lstai_agreement_minus_F1_flair_contrast"]
    add("V31-H4f9", "H4 not met for LST-AI agreement",
        f"LST-AI agreement gave {f(h4['F9_lstai_agreement'])}, not reliably below FLAIR contrast (separability difference "
        f"{f(sep['delta'],3,True)} [{f(sep['ci95'][0],3,True)}, {f(sep['ci95'][1],3,True)}])", V31,
        "H4_site_signature_M_vs_L10 (F9; paired_separability_differences)")
    ped = h4b["pedims"]["site_identity_auroc"].values()
    add("V31-H4bped", "PediMS identifiable by every family", f"(pooled cohort-identity AUROC {f(min(ped),2)}–{f(max(ped),2)})", V31,
        "H4b_site_signature_M_vs_new_sites.pedims (min-max)")
    add("V31-F8fw", "fold-wise F8 probe between MS cohorts (v3.2)", f"cohorts gave {f(k2['Mfalse_vs_L10false_reference']['foldwise']['F8']['auroc_foldwise_mean'])}",
        V32, "K2.Mfalse_vs_L10false_reference._foldwise_D1.F8")
    b6 = v31["B6_contamination"]["L10"]["GR-LR"]
    m2l = ext_p1["M_to_L10"]["GR-LR"]
    add("V31-L10", "Ljubljana-10: learned vs ensemble",
        f"{dci(b6, 'delta_vs_ENS-RAW')} with fold-0 candidates and {dci(m2l, 'delta_vs_RAW')} with ensemble candidates", V31 + " / " + V31P,
        "B6_contamination.L10.GR-LR; P1_mean5_candidates.M_to_L10.GR-LR")

    # ---------------- v3.2
    de = v32["descriptives"]["C"]
    add("V32-C", "control candidates", f"{de['candidates']} candidates in {de['scans_with_any']} of the {de['scans']} controls, "
        f"{f(de['per_scan_mean'],2)} per scan", V32, "descriptives.C")
    add("V32-H1", "H1 GR+C-LR vs ensemble",
        f"{aci(h1['GR+C-LR'])} for GR+C-LR and {aci(h1['ENS-RAW'])} for the ensemble mean, a difference of {dci(h1['GR+C-LR'], 'delta_vs_ENS-RAW')}",
        V32, "H1_primary_ms_true_vs_controls")
    add("V32-abs", "abstract: v3.2 delta", f"criterion ({dci(h1['GR+C-LR'], 'delta_vs_ENS-RAW')})", V32, "H1.GR+C-LR")
    e, g2, gl = h3["ENS-RAW"], h3["GR+C-LR"], h3["GR-LR"]
    add("V32-H3", "H3 false candidates per healthy scan",
        f"left {f(e['false_per_control_scan'],2)} [{f(e['fps_ci95'][0],2)}, {f(e['fps_ci95'][1],2)}] false candidates per healthy scan and "
        f"GR+C-LR left {f(g2['false_per_control_scan'],2)} [{f(g2['fps_ci95'][0],2)}, {f(g2['fps_ci95'][1],2)}] (difference "
        f"{f(g2['fps_minus_ENS-RAW'],2,True)} [{f(g2['fps_minus_ENS-RAW_ci95'][0],2,True)}, {f(g2['fps_minus_ENS-RAW_ci95'][1],2,True)}]",
        V32, "H3_false_per_control_at_90pct_sensitivity")
    add("V32-H3gr", "v3.1 detector on healthy scans",
        f"{f(gl['false_per_control_scan'],2)} [{f(gl['fps_ci95'][0],2)}, {f(gl['fps_ci95'][1],2)}] false candidates per scan, "
        f"{f(gl['fps_minus_ENS-RAW'],2,True)} [{f(gl['fps_minus_ENS-RAW_ci95'][0],2,True)}, {f(gl['fps_minus_ENS-RAW_ci95'][1],2,True)}]",
        V32, "H3.GR-LR")
    add("V32-H3b", "Lesson 3 restatement", f"({f(gl['false_per_control_scan'],2)} against {f(e['false_per_control_scan'],2)} false candidates per scan)",
        V32, "H3")
    h4p = v32["H4_external_pooled"]
    add("V32-H4", "H4 external non-inferiority",
        f"AUROC {f(h4p['GR+C-LR']['auroc'])} against {f(h4p['GR-LR']['auroc'])}, difference {dci(h4p['GR+C-LR'], 'delta_vs_GR-LR')}",
        V32, "H4_external_pooled")
    fw = k2["MSfalse_vs_C"]["foldwise"]
    add("V32-K2", "K2 cohort identity, MS false vs controls", f"fold-wise AUROC {aci(fw['GR'])}", V32, "K2_cohort_identity_probe.MSfalse_vs_C._foldwise_D1.GR")
    add("V32-K2abs", "abstract: K2", f"(AUROC {f(fw['GR']['auroc_foldwise_mean'])})", V32, "K2 foldwise GR")
    add("V32-K2ref", "K2 reference between MS cohorts", aci(k2["Mfalse_vs_L10false_reference"]["foldwise"]["GR"]), V32,
        "K2.Mfalse_vs_L10false_reference._foldwise_D1.GR")
    add("V32-K2geo", "K2 geometry dose",
        f"MSLesSeg (affine-scaled to MNI, like the template) gave {f(k2['Mfalse_vs_C']['foldwise']['GR']['auroc_foldwise_mean'])}, and Ljubljana "
        f"(rigidly placed, native size) gave {f(k2['L10false_vs_C']['foldwise']['GR']['auroc_foldwise_mean'])}", V32, "K2.Mfalse_vs_C / L10false_vs_C foldwise GR")
    add("V32-K2f8", "K2 fold disagreement", f"recognisable ({aci(fw['F8'])})", V32, "K2 foldwise F8")
    add("V32-Conly", "controls-only model on primary", f"scored {f(h1['GR-Conly-LR']['auroc'])} on the primary endpoint", V32, "H1.GR-Conly-LR")
    ho = k3["held_out_1mm_ms"]
    add("V32-K3", "K3 transfer",
        f"scored {f(ho['GR-Conly-LR']['auroc'])} against {f(ho['ENS-RAW']['auroc'])} for the ensemble, a difference of "
        f"{f(k3['transfer_delta_vs_ENS_RAW'],3,True)} [{f(k3['transfer_ci95'][0],3,True)}, {f(k3['transfer_ci95'][1],3,True)}]",
        V32, "K3_transfer.held_out_1mm_ms; transfer_delta_vs_ENS_RAW")
    add("V32-K3abs", "abstract: K3", f"(ΔAUROC {f(k3['transfer_delta_vs_ENS_RAW'],3,True)} against the ensemble mean)", V32,
        "K3_transfer.transfer_delta_vs_ENS_RAW")
    add("V32-K10", "fold-wise H1", f"The fold-wise version gave {dci(v32['K10']['GR+C-LR'], 'delta_vs_ENS-RAW')}", V32, "K10_H1_foldwise_D1.GR+C-LR")
    add("V32-H2", "key secondary H2 (vs MS-trained detector)", f"was met ({dci(h1['GR+C-LR'], 'delta_vs_GR-LR')} over the MS-trained detector)",
        V32, "H1.GR+C-LR.delta_vs_GR-LR")
    s2g = v32["S2_1mm"]["ms_only_true_vs_ms_false"]
    add("V32-S2", "training with controls costs nothing within 1-mm MS", f"cost nothing either ({dci(s2g['GR+C-LR'], 'delta_vs_ENS-RAW')}",
        V32, "S2_1mm.ms_only_true_vs_ms_false.GR+C-LR")
    add("V32-S2dis", "fold disagreement on MS false candidates",
        f"({f(s2g['DIS-RAW']['auroc'])} against {f(s2g['ENS-RAW']['auroc'])}, {dci(s2g['DIS-RAW'], 'delta_vs_ENS-RAW')})", V32,
        "S2_1mm.ms_only_true_vs_ms_false.DIS-RAW")
    k8 = v32["K8"]
    add("V32-K8", "blindness split",
        f"(ensemble {f(k8['august30']['ENS-RAW']['auroc'])}, GR+C-LR {f(k8['august30']['GR+C-LR']['auroc'])}) and on the 70 others "
        f"({f(k8['new70']['ENS-RAW']['auroc'])}, {f(k8['new70']['GR+C-LR']['auroc'])})", V32, "K8_blindness_split")
    sc = v32["S_CAL"]
    kept = [sc[f"{m}|alpha=0.1"]["ms_1mm_sensitivity"] for m in ("ENS-RAW", "GR-LR", "GR+C-LR")]
    flagged = {sc[f"{m}|alpha=0.1"]["held_out_controls_flagged"] for m in ("ENS-RAW", "GR-LR", "GR+C-LR")}
    add("V32-SCAL", "healthy-calibrated threshold at alpha 0.1",
        (f"({flagged.pop()} of 100 held-out controls flagged at α = 0.1), but it kept only {pct(min(kept))}–{pct(max(kept))} % of real 1-mm "
         f"lesions visible") if len(flagged) == 1 else "<mismatch>", V32, "S_CAL_healthy_calibrated_threshold (alpha 0.1)")
    add("V32-K3l", "Lesson 1 restatement", f"scored {f(h1['GR-Conly-LR']['auroc'])} where the shortcut was available and "
        f"{f(ho['GR-Conly-LR']['auroc'])} where it was not", V32, "H1.GR-Conly-LR; K3.held_out_1mm_ms.GR-Conly-LR")
    kb = k3["K3b_cohort_probe_on_H1_endpoint"]["K3b-cohort-probe"]
    add("V32-K3b", "K3b cohort probe on primary",
        f"{aci(kb)} on the primary endpoint. That equals GR+C-LR (difference {dci(kb, 'delta_vs_GR+C-LR')})", V32, "K3_transfer.K3b_cohort_probe_on_H1_endpoint")
    add("V32-K3bl", "Lesson 1 restatement", f"({f(kb['auroc'])} against {f(h1['GR+C-LR']['auroc'])})", V32, "K3b; H1.GR+C-LR")
    add("V32-K4", "K4 without volume", f"({dci(h1['GR+C-noVOL-LR'], 'delta_vs_ENS-RAW')})", V32, "H1.GR+C-noVOL-LR")
    add("V32-DIS", "fold disagreement alone, primary endpoint", f"{aci(h1['DIS-RAW'])}, {dci(h1['DIS-RAW'], 'delta_vs_ENS-RAW')}", V32, "H1.DIS-RAW")
    add("V32-K5", "shuffle null mean", f"mean {f(v32['K5']['mean'])}", V32, "K5_shuffle_null.mean")
    add("V32-gate", "models clearing +0.05 but confounded",
        f"gradient boosting ({f(h1['GR+C-GB']['delta_vs_ENS-RAW'],3,True)}), LST-AI with controls ({f(h1['GRL+C-LR']['delta_vs_ENS-RAW'],3,True)}) "
        f"and the controls-only model ({f(h1['GR-Conly-LR']['delta_vs_ENS-RAW'],3,True)})", V32, "H1.GR+C-GB, GRL+C-LR, GR-Conly-LR")
    k6 = v32["K6_independent_check"]
    add("V32-K6", "separately written re-implementation passed", "A separately written re-implementation reproduced the candidates exactly"
        if k6.get("passed", k6.get("K6_passed", True)) else "<mismatch>", "lesion_detector_v32_independent_check.json", "passed")

    # ---------------- pre-registration record
    for key, lab in [("flames_thick", "Study 1"), ("detector_v3", "v3"), ("detector_v31", "v3.1"), ("detector_v32", "v3.2")]:
        rec = pre[key]
        add(f"PR-{key}", f"{lab}: protocol commit, time, SHA-256, results commit",
            f"`{rec['preregistration']['commit'][:7]}` ({utc(rec['preregistration']['committer_date'])}) | "
            f"`{rec['protocol_sha256_at_preregistration'][:16]}` | `{rec['results']['commit'][:7]}` ({utc(rec['results']['committer_date'])})",
            "git history", f"{rec['protocol_path']} @ {rec['preregistration']['commit'][:7]}")
        add(f"PRfull-{key}", f"{lab}: full hashes (Appendix A)",
            f"`{rec['preregistration']['commit']}` | `{rec['protocol_sha256_at_preregistration']}` | `{rec['results']['commit']}`",
            "git history", "Appendix A")
        if not rec["protocol_is_ancestor_of_results"]:
            add(f"PRanc-{key}", "protocol commit is ancestor of results", "<not an ancestor>", "git history", "merge-base")
    t_pr56 = datetime.fromisoformat(push["PR #56 opened"].replace("Z", "+00:00"))
    add("PR-pub56", "Study 1 protocol public", f"{utc(push['PR #56 opened'])} (PR #56)", "GitHub API (recorded in extract_results.py)", "PR #56 createdAt")
    add("PR-pub55", "v3/v3.1 first public", f"{utc(push['PR #55 opened'])} (PR #55)", "GitHub API", "PR #55 createdAt")
    a1, s1t = push["push 73e9651"], kag["kaggle-full-s1"]["start_utc"]
    dt = (datetime.fromisoformat(s1t.replace("Z", "+00:00")) - datetime.fromisoformat(a1.replace("Z", "+00:00"))).total_seconds()
    add("PR-am1", "amendment 1 pushed before full-s1",
        f"(`73e9651`) was pushed at {a1[11:19]}, {int(dt)} s before the first full training session started at {s1t[11:19]}", "GitHub API; kaggle_runs.csv",
        "push 73e9651; kaggle-full-s1.start_utc")
    a2, s2t = push["push aba9a54"], kag["kaggle-full-s2"]["start_utc"]
    add("PR-am2", "amendment 2 pushed before full-s2", f"(`aba9a54`) was pushed at {a2[11:19]}, before the second session at {s2t[11:19]}"
        if a2 < s2t else "<mismatch>", "GitHub API; kaggle_runs.csv", "push aba9a54; kaggle-full-s2.start_utc")
    first_kaggle = min(k["start_utc"] for k in comp["kaggle_sessions"])
    hrs = (datetime.fromisoformat(first_kaggle.replace("Z", "+00:00")) - t_pr56).total_seconds() / 3600
    add("PR-11h", "protocol public before first Kaggle session", "public about 11 hours before the first Kaggle session"
        if 10.5 <= hrs < 11.5 else f"<{hrs:.2f} h>", "GitHub API; kaggle_runs.csv", f"{hrs:.2f} h (rounded to 'about 11')")
    p32, r32 = push["push 3c24977"], push["push 90797a9"]
    mins = (datetime.fromisoformat(r32.replace("Z", "+00:00")) - datetime.fromisoformat(p32.replace("Z", "+00:00"))).total_seconds() / 60
    add("PR-37", "v3.2 protocol pushed before results", f"{f(mins,0)} min before the results push", "GitHub API", "push 3c24977 -> 90797a9")

    # ---------------- run checks
    rows, fails = [], 0
    for cid, what, rendered, src, key in C:
        ok = "<" not in rendered and re.sub(r"\s+", " ", rendered) in text
        fails += not ok
        rows.append(f"| {cid} | {what} | {rendered.replace('|', '¦')} | {src} | `{key}` | {'PASS' if ok else '**FAIL**'} |")
    prov = d["provenance"]
    plines = [f"| {n} | `{p['commit'][:7]}` | `{p['path']}` | `{p['sha256']}` |" for n, p in prov.items()]

    md = OUT_HEADER.format(n=len(C), ok=len(C) - fails, fail=fails, when=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    md += "\n".join(["| id | claim | text that must appear in manuscript.md | source | key | status |", "|---|---|---|---|---|---|"] + rows)
    md += "\n\n## 2. Source files (pinned commits, SHA-256 of the blob read)\n\n| name | commit | path | SHA-256 |\n|---|---|---|---|\n"
    md += "\n".join(plines) + "\n"
    md += MANUAL + REFS
    OUT.write_text(md, encoding="utf-8")
    print(f"{len(C)} automatic checks: {len(C) - fails} PASS, {fails} FAIL -> {OUT.name}")
    for r in rows:
        if "FAIL" in r:
            print("  " + r)
    return 1 if fails else 0


OUT_HEADER = """# NUMBERS_CHECK — every number in `manuscript.md`, traced to its record

Generated by `scripts/check_numbers.py` on {when}. Re-run after any edit:
`python scripts/extract_results.py && python scripts/check_numbers.py`.

**Result: {ok} of {n} automatic checks PASS, {fail} FAIL.**

How it works: each value is read from `data/extracted_results.json`, which `extract_results.py`
builds with `git show <pinned commit>:<path>` (section 2 lists the commits and the SHA-256 of every
file read). The value is rounded half-up as printed, typeset like the text (Unicode minus, thousands
commas), and the whole phrase must occur in `manuscript.md` after whitespace is normalised. A
mismatch in any digit, sign or CI bound is a FAIL. The `|` character inside a phrase is shown as `¦`.

## 1. Automatic checks

"""

MANUAL = """
## 3. Numbers checked by reading (not in a machine-readable record)

| Number in the text | Source (branch / commit : file, section) |
|---|---|
| FLAMeS trained on 668 scans; fingerprint has no case with spacing ≥ 3 mm or an axis < 40 voxels | `90797a9` : `docs/research/lesion-detector-v3/PROTOCOL-v3.1.md` §2 |
| MSLesSeg: 0 of 115 fingerprint matches with FLAMeS training | `b19293c` : `docs/research/flames-thick/PROTOCOL.md` §4; `PROTOCOL.md` (detector) §3 |
| MSLesSeg-train 93 scans, P1–P53; test P54–P75; native thickness 2–5 mm; 8 of 93 training scans at 4–5 mm | `b19293c` : `PROTOCOL.md` §4 and §7 |
| Fine-tuning on 78 scans, internal monitoring split of 15 scans (11 patients) | `b19293c` : `PROTOCOL.md` §14 (early-look entry: "78 training / 15 internal-validation scans") |
| Ljubljana images rigidly placed, not size-normalised (brain ≈ 1.18–1.37 L vs MSLesSeg ≈ 1.84–1.95 L; text rounds to 1.2–1.4 and 1.8–2.0), N4-corrected and winsorised | `90797a9` : detector `PROTOCOL.md` §2 |
| Comparators not blind: Paper A v0.3 results (`2fa812d`, 2026-10-21 03:08 UTC) before the FLAMeS-thick protocol (03:57 UTC); Paper A healthy-control results (`413f5b5`, 2026-10-24 15:03 UTC) before the v3.2 protocol (16:26 UTC); v3.2 honesty statement | git history; `PROTOCOL-v3.2.md` §2; `PROTOCOL-v3.1.md` §1; detector `PROTOCOL.md` §1 |
| Results push of `b19293c` (2026-10-23 10:10 UTC) known only from the local reflog | `extract_results.py` (author_side flag); no GitHub event returned |
| Repository public when queried (2026-10-31) | `data/github_timing_evidence_2026-10-31.json` |
| Slice spacing MS3SEG 6.0–8.1 mm, Muslim 4.86–8.3 mm, PediMS 3.9 mm; 51 axial Muslim scans; PediMS 28 scans / 9 children | `b19293c` : `PROTOCOL.md` §7; `docs/research/cohorts-extra.md` §1 |
| Thick range "3.9–8.3 mm" in the abstract | same (PediMS 3.9 mm to Muslim 8.3 mm) |
| Ljubljana-10 = patients 16–20, 26–30; other 20 Ljubljana scans in FLAMeS training | `90797a9` : detector `PROTOCOL.md` §3 |
| LST-AI trained on 491 in-house scans | `90797a9` : `PROTOCOL-v3.1.md` §2 |
| Fine-tuning schedule (300 epochs × 250 iterations, batch 2, LR 1e-3, 5-epoch warm-up, momentum 0.99), simulation parameters (p = 2/3, 3–8 mm, axial 0.8, gap 0–0.5 T, nearest 0.7) | `b19293c` : `PROTOCOL.md` §5.2–§5.3 |
| Thickness bands B1 ≤ 1.5 mm, B2 1.5–4.5, B3 4.5–6.5, B4 > 6.5 mm; lesion size bins 3–14–50–150–500 mm³ | `b19293c` : `PROTOCOL.md` §8 |
| Internal validation 15 scans of 11 patients; unchanged FLAMeS 0.689 | `b19293c` : `PROTOCOL.md` §14; `RESULTS.md` S7 |
| Internal pseudo-Dice ranges A 0.799–0.846, B 0.807–0.856 | `b19293c` : `docs/research/flames-thick/RESULTS.md` S7 table |
| 68 s per case-model; 0 errors; inputs and masks identical to reference runs | `b19293c` : `RESULTS.md` §1 |
| FLAMeS fold-0 checkpoint SHA-256 `4fc7db24…df861` | `b19293c` : `PROTOCOL.md` §3 |
| Bootstrap B = 10,000 (seed 20261021) and 2,000 draws for S1 | `b19293c` : `PROTOCOL.md` §9; `RESULTS.md` §3 |
| Study 2: B = 2,000, seed 20261017; LR C = 0.1; GB depth 3, 300 iterations | `90797a9` : detector `PROTOCOL.md` §6–§7 |
| v2 honest leave-one-site-out AUROC 0.624 | `90797a9` : detector `PROTOCOL.md` §1 |
| D4 dry-run bias 0.31 | `90797a9` : detector `PROTOCOL.md` §11 D4 |
| v3.2 D1 dry-run values 0.470 / 0.440 / 0.419 vs 0.502 / 0.492 / 0.498 | `90797a9` : `PROTOCOL-v3.2.md` §11 D1 |
| 42 v3 features = 9 v2 + 5 new families; GR = 14 features | `90797a9` : detector `PROTOCOL.md` §5; `PROTOCOL-v3.1.md` §4 (also `feature_sets_sizes` in the extracted JSON) |
| 2 × T4, 4 vCPU per Kaggle session; ≤ 12 h sessions, soft pause at 11 h | `b19293c` : `RUNBOOK.md` §10; `PROTOCOL.md` §14 |
| Claude Opus 5.5 recorded as co-author trailer on every study commit | `git log --format=%(trailers)` on both branches |
| MELBA "no article processing charge" (checked 2026-10-17) | local notes `research_notes/Plan de publicaciones de MSTool AI/venues_bars_fit.md` (untracked) |

**Rounding note.** The detector records store 4 decimals; the manuscript rounds them half-up to 3. In
one place this differs from the source report: v3.1 PediMS ΔAUROC is stored as 0.1275 and printed in
`RESULTS-v3.1.md` as +0.127; the manuscript prints +0.128 (half-up of the stored value). The CI and
every other value agree with the source reports.
"""

REFS = """
## 4. Reference verification (offline, 2026-10-31)

No web access was used for this manuscript. Each entry of `references.bib` was checked against the
best local evidence. "Local [V]" means a web-verified note written on 2026-10-17 in
`research_notes/` (untracked) or a repository document that quotes the live record. "Memory" means
the details come from bibliographic knowledge of a well-known work; those fields are flagged
`CHECK ONLINE` in the `.bib` file where any doubt remains. **Before submission, resolve every DOI
online once.**

| key | evidence | status |
|---|---|---|
| dereskewicz2025flames | DOI, journal, vol. 35(5), e70085, PubMed 40937688 in local [V] notes | title from memory: CHECK ONLINE |
| larosa2025flamesweights | Zenodo DOI, version and licence in `PROTOCOL.md` §5.1/§12 (live record checked 2026-10-21) | verified locally |
| isensee2021nnunet | memory (very widely cited) | confident |
| isensee2024revisited | title, venue and arXiv id in local [V] notes | co-authors: CHECK ONLINE |
| isensee2019hdbet | memory | confident |
| wiltgen2024lstai | full citation and DOI in local [V] notes | verified locally |
| goebl2025mindglide | title, journal, volume, article, DOI in local [V] notes | verified locally (middle authors abbreviated) |
| billot2023synthseg | memory | confident |
| guarnera2025mslesseg | title, journal, article 920, DOI, first seven authors in local notes | verified locally |
| mslesseg2025data | Figshare DOI, file id, md5 in `PROTOCOL.md` §4 | verified locally |
| lesjak2018ljubljana | title, journal, year in `data/registry.yaml` and Paper A draft | co-authors, pages, DOI: CHECK ONLINE |
| bawil2026ms3seg, muslim2022baghdad, popa2025pedims | `docs/research/cohorts-extra.md` §2 (live records checked 2026-10-17) | verified locally |
| tuchinov2025sibbms | medRxiv DOI and licence statement in Paper A draft | journal version: CHECK ONLINE |
| commowick2018msseg | memory | CHECK ONLINE |
| carass2017isbi | memory | confident |
| malinin2022shifts2 | arXiv id in local [V] notes | verified locally |
| lakshminarayanan2017ensembles, nair2020uncertainty, jin2023selection, benjamini1995fdr | memory | confident |
| zech2018pneumonia, degrave2021shortcuts, geirhos2020shortcut, glocker2019scanner | memory | confident |
| fortin2018combat | memory | middle authors abbreviated; confident on title/venue |
| varoquaux2022failures, kapoor2023leakage, maierhein2024metrics | memory | confident |
| nosek2018preregistration, lakens2017equivalence, fanelli2012negative, efron1993bootstrap, hanley1982auc, wong2011color | memory | confident |
"""

if __name__ == "__main__":
    sys.exit(main())
