"""Paper 1 addendum: compute plan, budget projection and budget rule — AMENDMENT 1
(docs/research/paper-1/PREREG-mimics-thickness.md section 15; version 1.0 of this file, section 9, is in git).

Spot VMs only; hard cap 45 USD for the whole addendum (list price of what runs). Work (amendment 1):
  A   WMH 2017: 170 x (HD-BET, FLAMeS 5 folds, LST-AI, MindGlide, SAMSEG) + WMH-SynthSeg on the 110 test subjects
  B1  DLBS: stratified sample of 100 (or 75 after reduction iii) x (2 HD-BET, FLAMeS, LST-AI, MindGlide, WMH, SAMSEG)
  C1  MS 1 mm (145; LST-AI 144) x {3, 5, 7} mm (or {3, 7}) for FLAMeS, LST-AI, MindGlide, WMH-SynthSeg;
      SAMSEG on the pre-listed 50-scan subset at 1 mm and at each simulated thickness
  C2  SibBMS (100) x 7 mm, every tool
Reductions if the post-pilot HIGH projection exceeds the cap, in this order: (i) drop C2; (ii) C1 at {3, 7} mm;
(iii) DLBS sample 75. If nothing fits: stop (owner decision).

Layout (quotas: 4 external addresses, 250 GB SSD, C2D 32 vCPUs): two "nn" VMs (c2d-standard-4, 50 GB: HD-BET prep,
FLAMeS, LST-AI, MindGlide) and two "fs" VMs (c2d-highmem-4 75 GB: WMH-SynthSeg then SAMSEG; c2d-standard-4 75 GB:
SAMSEG), balanced on projected hours. Spot list prices read from the Cloud Billing catalog on 2026-11-09
(us-central1, boot disk included): c2d-standard-4 + 50 GB 0.09003 USD/h, + 75 GB 0.09346; c2d-highmem-4 + 75 GB
0.12248, + 130 GB 0.13002 (pilot).

    python research/paper_1/mimics/plan_mimics.py                             # ledger medians (before the pilot)
    python research/paper_1/mimics/plan_mimics.py --pilot-json p.json --spent-usd 0.6   # the rule after the pilot
p.json: mean seconds per step measured in the pilot, keys hdbet flames5 lstai mindglide wmhsynthseg samseg
(DLBS-specific keys hdbet_dlbs, samseg_dlbs, ... override for block B when present).
"""
import argparse
import json
import math

CAP_USD = 45.0
SAFETY = 1.25
SETUP_H = 0.35                         # per VM: environment, weights, images (pilot measures it)
RATE = {"nn": 0.09003, "fs_hm": 0.12248, "fs_std": 0.09346, "pilot": 0.13002}
FIXED_USD = {"data mirror (done)": 0.0093, "registration + evaluation VM (Spot)": 0.6}
# Ledger medians (n2d, 4 vCPU), used until the pilot replaces them.
LEDGER_SECONDS = {"hdbet": 139.0, "flames5": 5 * 68.5, "lstai": 120.0, "mindglide": 84.0,
                  "wmhsynthseg": 216.0, "samseg": 552.0}
NN_STEPS = ("hdbet", "flames5", "lstai", "mindglide")
FS_STEPS = ("wmhsynthseg", "samseg")


def work(c1_thick=(3, 5, 7), dlbs_n=100, with_c2=True):
    """{block: {step: n}} for a plan variant."""
    k = len(c1_thick)
    w = {"A": {"hdbet": 170, "flames5": 170, "lstai": 170, "mindglide": 170, "samseg": 170, "wmhsynthseg": 110},
         "B1": {"hdbet": 2 * dlbs_n, "flames5": dlbs_n, "lstai": dlbs_n, "mindglide": dlbs_n, "samseg": dlbs_n,
                "wmhsynthseg": dlbs_n},
         "C1": {"flames5": 145 * k, "lstai": 144 * k, "mindglide": 145 * k, "wmhsynthseg": 145 * k,
                "samseg": 50 * (k + 1)}}
    if with_c2:
        w["C2"] = {"flames5": 100, "lstai": 100, "mindglide": 100, "wmhsynthseg": 100, "samseg": 100}
    return w


def seconds_for(block, step, sec):
    key = {"B1": f"{step}_dlbs", "A": f"{step}_wmh"}.get(block)
    return float(sec.get(key, sec[step])) if key else float(sec[step])


def projection(w, sec, spent=0.0):
    nn_h = sum(n * seconds_for(b, s, sec) for b, steps in w.items() for s, n in steps.items() if s in NN_STEPS) / 3600
    wmh_h = sum(n * seconds_for(b, "wmhsynthseg", sec) for b, steps in w.items() for s, n in steps.items()
                if s == "wmhsynthseg") / 3600
    sam_h = sum(n * seconds_for(b, "samseg", sec) for b, steps in w.items() for s, n in steps.items()
                if s == "samseg") / 3600

    def cost(f):
        nn = 2 * (f * nn_h / 2 + SETUP_H) * RATE["nn"]
        fs_tot = f * (wmh_h + sam_h)
        fsa = max(f * wmh_h, fs_tot / 2)                      # fs-a: WMH-SynthSeg, then SAMSEG up to balance
        fsb = fs_tot - fsa
        return nn + (fsa + SETUP_H) * RATE["fs_hm"] + (fsb + SETUP_H) * RATE["fs_std"]
    fixed = sum(FIXED_USD.values())
    central = cost(1.0) + fixed + spent
    high = cost(SAFETY) + fixed + spent
    fs_tot = wmh_h + sam_h
    return {"vm_hours": round(nn_h + wmh_h + sam_h + 4 * SETUP_H, 1), "cpu_hours": round(4 * (nn_h + wmh_h + sam_h), 1),
            "hours": {"nn_total": round(nn_h, 1), "wmhsynthseg": round(wmh_h, 1), "samseg": round(sam_h, 1)},
            "wall_clock_h_high": round(max(SAFETY * nn_h / 2, SAFETY * max(wmh_h, fs_tot / 2)) + SETUP_H, 1),
            "usd_central": round(central, 2), "usd_high": round(high, 2)}


VARIANTS = [
    ("full amendment-1 plan", {}),
    ("(i) drop C2", {"with_c2": False}),
    ("(i) + (ii) C1 at {3, 7} mm", {"with_c2": False, "c1_thick": (3, 7)}),
    ("(i) + (ii) + (iii) DLBS 75", {"with_c2": False, "c1_thick": (3, 7), "dlbs_n": 75}),
]


def apply_rule(sec, spent=0.0):
    rows = []
    for label, kw in VARIANTS:
        p = projection(work(**kw), sec, spent)
        rows.append({"variant": label, **p})
        if p["usd_high"] <= CAP_USD:
            return {"selected": label, "kwargs": kw, "projection": p, "considered": rows}
    return {"selected": None, "reason": "nothing fits the cap: stop, owner decision", "considered": rows}


def guards(sel_kwargs, sec, spent):
    """max-hours per VM so that every VM running to its guard still keeps total spend <= CAP_USD."""
    p = projection(work(**sel_kwargs), sec, spent)
    left = CAP_USD - spent - sum(FIXED_USD.values())
    nn_h = p["hours"]["nn_total"] / 2
    fs_tot = p["hours"]["wmhsynthseg"] + p["hours"]["samseg"]
    fsa_h = max(p["hours"]["wmhsynthseg"], fs_tot / 2)
    fsb_h = fs_tot - fsa_h
    base = {"nn-a": (nn_h, RATE["nn"]), "nn-b": (nn_h, RATE["nn"]), "fs-a": (fsa_h, RATE["fs_hm"]),
            "fs-b": (fsb_h, RATE["fs_std"])}
    for f in (1.6, 1.5, 1.4, 1.3, 1.25, 1.2, 1.1, 1.0):
        g = {k: math.ceil(h * f + SETUP_H) for k, (h, _) in base.items()}
        worst = sum(g[k] * r for k, (_, r) in base.items())
        if worst <= left:
            return {"factor": f, "max_hours": g, "worst_case_usd": round(worst + spent + sum(FIXED_USD.values()), 2)}
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot-json")
    ap.add_argument("--spent-usd", type=float, default=0.0, help="pilot + prep already spent (ledger)")
    a = ap.parse_args()
    sec = dict(LEDGER_SECONDS)
    if a.pilot_json:
        sec.update({k: float(v) for k, v in json.load(open(a.pilot_json)).items()})
    print(f"seconds per step: {json.dumps(sec)}")
    for label, kw in VARIANTS:
        p = projection(work(**kw), sec, a.spent_usd)
        print(f"  {label:34s} {p['vm_hours']:6.1f} VM-h {p['cpu_hours']:7.1f} CPU-h  {p['usd_central']:6.2f} - "
              f"{p['usd_high']:6.2f} USD  (wall clock <= {p['wall_clock_h_high']} h)")
    rule = apply_rule(sec, a.spent_usd)
    out = {"budget_rule": rule.get("selected") or rule["reason"], "cap_usd": CAP_USD}
    if rule.get("selected"):
        out["projection"] = rule["projection"]
        out["guards"] = guards(rule["kwargs"], sec, a.spent_usd)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
