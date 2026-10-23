"""Markdown tables of every pre-registered FLAMeS-thick number, straight from the analysis record.

    python research/flames_thick/results_tables.py docs/research/records/<date>_flames_thick_results.json \
        [--training docs/research/flames-thick/kaggle/runs] > tables.md

Used to write docs/research/flames-thick/RESULTS.md without hand-copying numbers. Read-only.
"""
import argparse
import glob
import json
import os
import statistics


def d(x):
    p, (lo, hi) = x
    return f"{p:+.3f} [{lo:+.3f}, {hi:+.3f}]"


def r3(x):
    p, (lo, hi) = x
    return f"{p:.3f} [{lo:.3f}, {hi:.3f}]"


def comp_rows(res, keys):
    out = ["| comparison (thick sites) | scans / patients | mean F1 | ΔF1 [95 % CI] | mean false lesions / scan | FP ratio [95 % CI] |",
           "|---|---|---|---|---|---|"]
    for label, k in keys:
        v = res[k]
        a, b = list(v["mean_f1"])
        out.append(f"| {label} | {v['n']} / {v['patients']} | {a} {v['mean_f1'][a]:.3f} vs {b} {v['mean_f1'][b]:.3f} | "
                   f"{d(v['delta_f1'])} | {a} {v['mean_fp'][a]:.2f} vs {b} {v['mean_fp'][b]:.2f} | {r3(v['fp_ratio'])} |")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("record")
    ap.add_argument("--training")
    a = ap.parse_args(argv)
    res = json.load(open(a.record))
    L = [f"Evaluation set: {res['n_scans']} scans {res['counts']}.", ""]
    L.append("### H1 and its sensitivity analyses (A vs R unless stated)")
    L += comp_rows(res, [("H1 primary: A vs R, lenient IoU > 0", "H1"),
                         ("S6 strict matching IoU ≥ 0.10", "S6_strict"),
                         ("S6 without PediMS P9 (Baló)", "S6_without_pedims_P9"),
                         ("S3 / H3: A vs B (augmentation effect)", "S3_A_vs_B"),
                         ("S4: A vs E (5-fold ensemble)", "S4_A_vs_E"),
                         ("context: B vs R (fine-tuning without thickening)", "B_vs_R_thick")])
    L += ["", "Script verdict strings: H1 " + res["H1"]["verdict"] + "; S6 strict " + res["S6_strict"]["verdict"]
          + "; S6 without P9 " + res["S6_without_pedims_P9"]["verdict"] + ". (The script applies the H1 rule to every row; "
          "only H1 has a pre-registered verdict; S3 is read with its own rule: effect shown if the ΔF1 CI lower bound > 0.)", ""]
    L.append("### H1 per thick site (A vs R)")
    L += ["| site | scans / patients | mean F1 A vs R | ΔF1 [95 % CI] | false lesions A vs R | FP ratio [95 % CI] |", "|---|---|---|---|---|---|"]
    for s, v in res["H1_by_site"].items():
        L.append(f"| {s} | {v['n']} / {v['patients']} | {v['mean_f1']['A']:.3f} vs {v['mean_f1']['R']:.3f} | {d(v['delta_f1'])} | "
                 f"{v['mean_fp']['A']:.2f} vs {v['mean_fp']['R']:.2f} | {r3(v['fp_ratio'])} |")
    h = res["H2"]
    L += ["", "### H2 (~1 mm non-inferiority, A vs R)",
          "| quantity | estimate [95 % CI] | margin | met? |", "|---|---|---|---|",
          f"| pooled ΔDice ({h['n']} scans) | {d(h['delta_dice'])} | CI lower > −0.02 | {'yes' if h['delta_dice'][1][0] > -0.02 else 'no'} |",
          f"| pooled ΔF1 | {d(h['delta_f1'])} | CI lower > −0.03 | {'yes' if h['delta_f1'][1][0] > -0.03 else 'no'} |",
          f"| Ljubljana clean-10 ΔDice (point) | {h['ljubljana_delta_dice']:+.3f} | ≥ −0.02 | {'yes' if h['ljubljana_delta_dice'] >= -0.02 else 'no'} |",
          f"| Ljubljana clean-10 ΔF1 (point) | {h['ljubljana_delta_f1']:+.3f} | ≥ −0.03 | {'yes' if h['ljubljana_delta_f1'] >= -0.03 else 'no'} |",
          f"", f"Verdict string: {h['verdict']}.", ""]
    L.append("### S1 detection by lesion size (pooled lesions, patient-bootstrap 95 % CI)")
    L += ["| band | arm | [3,14) | [14,50) | [50,150) | [150,500) | ≥ 500 mm³ | 50 % from | 80 % from |", "|---|---|---|---|---|---|---|---|---|"]
    f = lambda v: "–" if v is None else f"{v:.2f}"
    for k, v in res["S1_size"].items():
        band, arm = k.split("|")
        cells = [f"{f(b['sens'])} [{f(b['ci'][0])}–{f(b['ci'][1])}] (n {b['n']})" for b in v["bins"]]
        L.append(f"| {band} | {arm} | " + " | ".join(cells) + f" | {v['min_size_50'] or 'never'} | {v['min_size_80'] or 'never'} |")
    L += ["", "Bands by slice spacing: B1 ≤ 1.5 mm (Ljubljana, MSLesSeg test), B2 1.5–4.5 (PediMS), B3 4.5–6.5, B4 > 6.5 (MS3SEG, Muslim).", ""]
    L.append("### S2 per site (means over scans)")
    L += ["| site | arm | lesion F1 | false lesions / scan | Dice | lesion sensitivity | lesion precision |", "|---|---|---|---|---|---|---|"]
    for s, arms in res["S2_by_site"].items():
        for arm, m in arms.items():
            L.append(f"| {s} | {arm} | {f(m['f1'])} | {f(m['fp'])} | {f(m['dice'])} | {f(m['sens'])} | {f(m['prec'])} |")
    if res.get("S5_mslesseg_by_native_thickness"):
        L += ["", "### S5 MSLesSeg test by native FLAIR slice thickness (A − R, means)", "| native thickness | scans | ΔF1 | ΔDice |", "|---|---|---|---|"]
        for k, v in res["S5_mslesseg_by_native_thickness"].items():
            L.append(f"| {k} | {v['n']} | {v['delta_f1_mean']:+.3f} | {v['delta_dice_mean']:+.3f} |")
    if a.training:
        L += ["", "### S7 internal-validation pseudo-Dice per epoch (thin, in-domain; forgetting check)",
              "| run | epochs | first | min | median | max | last | nnU-Net final validation Dice (15 scans) |", "|---|---|---|---|---|---|---|---|"]
        for p in sorted(glob.glob(os.path.join(a.training, "*.manifest.json"))):
            m = json.load(open(p))
            pdice = [e["pseudo_dice"][0] for e in m["epochs"]]
            fin = os.path.join(os.path.dirname(p), "..", "models.json")
            final = json.load(open(fin))["models"][m["run_id"]]["internal_validation_final"]["dice_mean_15_scans"] if os.path.exists(fin) else None
            L.append(f"| {m['run_id']} ({m['arm']}) | {len(pdice)} | {pdice[0]:.3f} | {min(pdice):.3f} | {statistics.median(pdice):.3f} | "
                     f"{max(pdice):.3f} | {pdice[-1]:.3f} | {final} |")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
