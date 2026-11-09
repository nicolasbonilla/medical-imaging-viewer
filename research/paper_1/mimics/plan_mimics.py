"""Paper 1 addendum (docs/research/paper-1/PREREG-mimics-thickness.md, section 9): compute plan, budget
projection and budget tiers for the MS-mimic (WMH 2017), second-healthy-cohort (DLBS) and controlled-
thickness (MS 1 mm + SibBMS) runs. LAUNCH SKELETON: it prints the plan and the projected spend; it does
not create any VM. The launch itself (one self-deleting VM per block, research/cloud/launch_vm.py, same
safety layers as paper F and the healthy arm) is enabled only after the pilot (section 9.3) and after the
driver extensions of section 11 step 2 exist; until then `--launch` refuses.

    python research/paper_1/mimics/plan_mimics.py                      # projection from the ledger timings
    python research/paper_1/mimics/plan_mimics.py --pilot-json p.json  # projection from pilot timings (rule 9.4)

Per-scan seconds (4 vCPU) are the medians measured in the compute ledger (docs/research/compute-ledger/):
HD-BET 139 s (flames-extra-a/b preparation, TTA on), FLAMeS 68.5 s per fold (flames-full-*, flames-extra-*),
LST-AI 120 s (lstai-ctl 100.5 s on n2-standard-4, lstai-pilot 141.6 s on n2d-standard-4), MindGlide 84 s
(toolbench-mindglide-*), WMH-SynthSeg 216 s (toolbench-wmh; n2d-highmem-4), SAMSEG 552 s (toolbench-ctl-samseg-a).
List prices (Cloud Billing catalog, 2026-11-09, us-central1, standard, boot disk included):
n2d-standard-4 + 80 GB 0.17994 USD/h, n2d-highmem-4 + 90 GB 0.24029, n2-standard-4 + 80 GB 0.20519;
Spot: 0.10084 / 0.13357 / 0.12747.
"""
import argparse
import json

RATE = {"n2d-standard-4": 0.17994, "n2d-highmem-4": 0.24029, "n2-standard-4": 0.20519}
RATE_SPOT = {"n2d-standard-4": 0.10084, "n2d-highmem-4": 0.13357, "n2-standard-4": 0.12747}
SECONDS = {"hdbet": 139.0, "flames5": 5 * 68.5, "lstai": 120.0, "mindglide": 84.0, "wmhsynthseg": 216.0, "samseg": 552.0}
MACHINE = {"hdbet": "n2d-standard-4", "flames5": "n2d-standard-4", "lstai": "n2d-standard-4",
           "mindglide": "n2d-standard-4", "wmhsynthseg": "n2d-highmem-4", "samseg": "n2d-standard-4"}
TOOLS = ("flames5", "lstai", "mindglide", "wmhsynthseg", "samseg")
SAFETY = 1.25                    # runtime safety factor (as the healthy arm's budget rule)
SETUP_H = 0.25                   # image pulls + environment per VM
CAP_USD = 110.0                  # hard cap of this addendum (section 9), pilots and evaluation VMs included
FIXED_USD = {"pilots (3 blocks)": 1.5, "registration + evaluation VMs": 2.0, "data mirror (done)": 0.10}

# Blocks in priority order (section 9.4): scans per step. HD-BET only where the input is not skull-stripped.
BLOCKS = {
    "A  WMH 2017 (170, native 3 mm)": {"hdbet": 170, **{t: 170 for t in TOOLS}},
    "B1 DLBS >= 50 y (275, native 2.5 mm)": {"hdbet": 2 * 275, **{t: 275 for t in TOOLS}},     # FLAIR + T1 for LST-AI
    "C1 MS 1 mm x {3,5,7} mm (145 x 3) + SAMSEG at 1 mm (145)": {**{t: 3 * 145 for t in TOOLS},
                                                                   "lstai": 3 * 144, "samseg": 4 * 145},
    "C2 SibBMS x {3,5,7} mm (100 x 3)": {t: 3 * 100 for t in TOOLS},
    "B2 DLBS < 50 y (105, lifespan extension)": {"hdbet": 2 * 105, **{t: 105 for t in TOOLS}},
}
# Pre-registered reductions (section 9.4), applied in this order until the projection fits the cap.
REDUCTIONS = [
    ("drop B2 (lifespan extension)", {"B2 DLBS < 50 y (105, lifespan extension)": None}),
    ("C2 at 7 mm only", {"C2 SibBMS x {3,5,7} mm (100 x 3)": {t: 100 for t in TOOLS}}),
    ("Spot provisioning for all blocks (resumable drivers; outputs unchanged)", "spot"),
]


def block_cost(work, spot=False, seconds=SECONDS):
    rates = RATE_SPOT if spot else RATE
    hours = {}
    for step, n in work.items():
        m = MACHINE[step]
        hours[m] = hours.get(m, 0.0) + n * seconds[step] / 3600.0
    usd = sum(rates[m] * (h * SAFETY + SETUP_H) for m, h in hours.items())
    usd_central = sum(rates[m] * (h + SETUP_H) for m, h in hours.items())
    return {"vm_hours": round(sum(hours.values()), 1), "cpu_hours": round(4 * sum(hours.values()), 1),
            "usd_central": round(usd_central, 2), "usd_high": round(usd, 2), "by_machine_h": {k: round(v, 1) for k, v in hours.items()}}


def projection(blocks, spot=False, seconds=SECONDS):
    rows = {name: block_cost(w, spot, seconds) for name, w in blocks.items()}
    fixed = sum(FIXED_USD.values())
    return rows, {"vm_hours": round(sum(r["vm_hours"] for r in rows.values()), 1),
                  "cpu_hours": round(sum(r["cpu_hours"] for r in rows.values()), 1),
                  "usd_central": round(sum(r["usd_central"] for r in rows.values()) + fixed, 2),
                  "usd_high": round(sum(r["usd_high"] for r in rows.values()) + fixed, 2)}


def apply_rule(seconds=SECONDS):
    """Section 9.4: the largest plan (fewest reductions) whose HIGH projection is <= CAP_USD."""
    blocks, spot, applied = dict(BLOCKS), False, []
    rows, tot = projection(blocks, spot, seconds)
    if tot["usd_high"] <= CAP_USD:
        return {"tier": "A (everything)", "applied": applied, "rows": rows, "total": tot}
    for label, change in REDUCTIONS:
        if change == "spot":
            spot = True
        else:
            for k, v in change.items():
                if v is None:
                    blocks.pop(k, None)
                else:
                    blocks[k] = v
        applied.append(label)
        rows, tot = projection(blocks, spot, seconds)
        if tot["usd_high"] <= CAP_USD:
            return {"tier": f"reduced ({len(applied)} step(s))", "applied": applied, "rows": rows, "total": tot}
    return {"tier": "none fits: stop, owner decision (section 9.5)", "applied": applied, "rows": rows, "total": tot}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot-json", help="per-step mean seconds measured in the pilot, e.g. {\"samseg\": 560}")
    ap.add_argument("--launch", action="store_true")
    a = ap.parse_args()
    sec = dict(SECONDS)
    if a.pilot_json:
        sec.update({k: float(v) for k, v in json.load(open(a.pilot_json)).items() if k in sec})
    full_rows, full_tot = projection(BLOCKS, False, sec)
    print("Full plan, standard VMs (central = measured seconds; high = x1.25 + 0.25 h set-up per machine type):")
    for name, r in full_rows.items():
        print(f"  {name:62s} {r['vm_hours']:7.1f} VM-h {r['cpu_hours']:8.1f} CPU-h  {r['usd_central']:6.2f} - {r['usd_high']:6.2f} USD")
    print(f"  {'fixed: ' + ', '.join(FIXED_USD):62s} {'':26s} {sum(FIXED_USD.values()):6.2f} USD")
    print(f"  TOTAL {full_tot['vm_hours']} VM-h, {full_tot['cpu_hours']} CPU-h, {full_tot['usd_central']} - {full_tot['usd_high']} USD")
    _, spot_tot = projection(BLOCKS, True, sec)
    print(f"  (same plan on Spot VMs: {spot_tot['usd_central']} - {spot_tot['usd_high']} USD)")
    plan = apply_rule(sec)
    print(json.dumps({"budget_rule": plan["tier"], "reductions": plan["applied"], "projected": plan["total"],
                      "cap_usd": CAP_USD}, indent=1))
    if a.launch:
        raise SystemExit("launch disabled until the pilot passed and the driver extensions exist (PREREG section 11)")


if __name__ == "__main__":
    main()
