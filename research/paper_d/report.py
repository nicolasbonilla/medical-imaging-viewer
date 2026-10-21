"""Render the paper-D results JSON as markdown tables (pasted into RESULTS.md; research code).

    python research/paper_d/report.py docs/research/paper-d/records/results_v1.json > summary.md
"""
from __future__ import annotations

import json
import sys


def ci(d, pct=True):
    if d is None:
        return "n/a"
    f = (lambda v: f"{100 * v:.1f} %") if pct else (lambda v: f"{v:.3f}")
    return f"{f(d['est'])} ({f(d['lo'])} – {f(d['hi'])})"


def core_table(c, title):
    p1, p2, p2e = c["P1"], c["P2_automated"], c["P2_expert"]
    rows = [
        ("Scans / patients", f"{c['n_scans']} / {c['n_patients']}"),
        ("Reference: brain DIS met", ci(c["reference_dis_met"])),
        ("P1 device automated default — flip vs reference", ci(p1["device_default_flip"])),
        ("P1 LST-AI as shipped — flip vs reference", ci(p1["lstai_as_shipped_flip"])),
        ("P1 mean flip over the automated grid", ci(p1["grid_mean_flip"])),
        ("P1 scans flipped by ≥ 1 automated pipeline", ci(p1["any_flip"])),
        ("P1 per-pipeline flip rate: min / median / max",
         f"{100 * p1['per_pipeline_flip']['min']:.1f} / {100 * p1['per_pipeline_flip']['median']:.1f} / "
         f"{100 * p1['per_pipeline_flip']['max']:.1f} %"),
        ("P2 automated grid: not unanimous", ci(p2["not_unanimous"])),
        ("P2 automated grid: contested (10–90 %)", ci(p2["contested"])),
        ("P2 automated grid: pairwise disagreement", ci(p2["pairwise"])),
        ("P2 expert grid: not unanimous", ci(p2e["not_unanimous"])),
        ("P2 expert grid: contested", ci(p2e["contested"])),
        ("P2 expert grid: pairwise disagreement", ci(p2e["pairwise"])),
        ("Expert grid: mean flip vs reference", ci(c["expert_grid_flip_vs_ref_mean"])),
    ]
    out = [f"#### {title}", "", "| Outcome | Estimate (95 % CI) |", "|---|---|"]
    out += [f"| {a} | {b} |" for a, b in rows]
    d = p1["device_default_direction"]
    out += ["", f"Device default disagreements: reference met → pipeline not met **{d['ref_met_pipeline_not']}**, "
                f"reference not met → pipeline met **{d['ref_not_pipeline_met']}**."]
    return "\n".join(out)


def main(path):
    r = json.load(open(path))
    print(f"Device agreement: {r['device_agreement']}\n")
    print(core_table(r["primary"], "Primary (clean set)"))
    print("\n#### S1 drivers (pairs differing only in the factor)\n\n| Factor | Disagreement (95 % CI) | groups |\n|---|---|---|")
    s1 = r["S1_drivers"]
    for k in s1["_ranking"]:
        print(f"| {k} | {ci(s1[k]['disagreement'])} | {s1[k]['n_groups']} |")
    t = s1["_top_minus_second"]
    print(f"\nTop minus second ({t['top']} − {t['second']}): {ci(t)}\n")
    print("Expert grid factors:\n\n| Factor | Disagreement |\n|---|---|")
    for k, v in s1["_expert_grid"].items():
        print(f"| {k} | {ci(v['disagreement'])} |")
    print("\nOne factor at a time from the device default:\n\n| Change | Flip vs default | Flip vs reference |\n|---|---|---|")
    for k, v in s1["_ofat_from_default"].items():
        print(f"| {k} | {ci(v['flip_vs_default'])} | {ci(v['flip_vs_reference'])} |")
    print("\nOne factor at a time from the reference (expert mask):\n\n| Change | Flip vs reference |\n|---|---|")
    for k, v in s1["_ofat_from_reference"].items():
        print(f"| {k} | {ci(v)} |")
    print("\n#### S2 regions\n\n| Region | presence flip (grid mean) | presence flip (default) | ICC(A,1) default vs ref | "
          "bias (default − ref) | LoA | ref median [IQR] | within-scan IQR / range (median) |\n|---|---|---|---|---|---|---|---|")
    for k, v in r["S2_regions"].items():
        ba = v["bland_altman_default_minus_ref"]
        m = v["ref_median_iqr"]
        print(f"| {k} | {ci(v['presence_flip_grid_mean'])} | {ci(v['presence_flip_default'])} | "
              f"{ci(v['icc_a1_default_vs_ref'], pct=False)} | {ci(ba['bias'], pct=False)} | {ba['loa']} | "
              f"{m[0]:.0f} [{m[1]:.0f}–{m[2]:.0f}] | {v['within_scan_iqr_median']:.1f} / {v['within_scan_range_median']:.1f} |")
    print("\n#### S3 strata\n")
    for name, groups in r["S3_strata"].items():
        if name == "lesion_count_tertile_cuts":
            print(f"Tertile cuts (expert lesions ≥ 3 mm³): {groups}\n")
            continue
        print(f"{name}\n\n| Stratum | scans / patients | ref met | default flip | grid mean flip | not unanimous | contested | expert-grid not unanimous |\n|---|---|---|---|---|---|---|---|")
        for g, v in groups.items():
            print(f"| {g} | {v['n_scans']} / {v['n_patients']} | {100 * v['reference_dis_met']:.0f} % | {ci(v['device_default_flip'])} | "
                  f"{ci(v['grid_mean_flip'])} | {ci(v['not_unanimous'])} | {ci(v['contested'])} | {ci(v['expert_grid_not_unanimous'])} |")
        print()
    print("#### S4 ventricles\n")
    for G, v in r["S4_ventricles"].items():
        print(f"**{G}**\n")
        for k, x in v.items():
            if k == "scans_with_a_changed_lesion":
                x = ci(x)
            print(f"- {k}: {x}")
        print()
    print("#### S5 indicator\n")
    for name, v in r["S5_indicator"].items():
        if name == "n_variants":
            print(f"variants: {v}\n")
            continue
        for oname, m in v.items():
            print(f"**{name} → {oname}**: flagged {ci(m['flagged'])}; P(outcome | flag) {ci(m['p_outcome_if_flagged'])}; "
                  f"P(outcome | no flag) {ci(m['p_outcome_if_not_flagged'])}; RD {ci(m.get('risk_difference'))}; "
                  f"sens {ci(m['sensitivity'])}; spec {ci(m['specificity'])}; counts {m['counts']}\n")
    print("#### S6 sensitivity\n")
    for k, v in r["S6_sensitivity"].items():
        if k == "e_g1_qc":
            print(f"G1 QC: {json.dumps({a: b for a, b in v.items() if a != 'restricted'})}\n")
            if "restricted" in v:
                print(core_table(v["restricted"], "G1 QC-restricted"))
            continue
        print(core_table(v, k))
        print()
    print("#### Criteria\n")
    for k, v in r["criteria"].items():
        print(f"- {k}: {v}")


if __name__ == "__main__":
    main(sys.argv[1])
