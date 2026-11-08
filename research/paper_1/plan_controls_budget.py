"""Paper 1 budget rule (PREREG-healthy-controls.md section 8) from the pilot timings — runtime only, never accuracy.

    python research/paper_1/plan_controls_budget.py --pilot-manifest <toolbench-ctl-pilot.json> \
        --pilot-cost <toolbench-ctl-pilot.txt> [--cap 10]

m_t = pilot mean seconds per control for tool t (manifest field "seconds", case-tool wall time).
VM A (n2d-highmem-4): WMH-SynthSeg then MindGlide on the controls not yet done; VMs B (n2d-standard-4) and
C (n2-standard-4): SAMSEG, half each. projected = pilot actual + sum_VM rate x (0.25 h + scans x m x 1.25 / 3600).
Tier A (all 100) if projected <= cap; else tier B (SAMSEG on the 50 odd-numbered controls); else SAMSEG not run.
Guards (the in-VM wall-clock stop): max-hours per VM = ceil(f x projected hours, which already carry the 1.25
safety factor), with the largest f in 1.5, 1.45, ..., 1.0 such that pilot + sum_VM rate x max-hours <= cap
(PREREG section 8: even if every VM ran to its guard, the total stays within the cap). If even f = 1.0 does
not fit, the next tier is tried.
"""
import argparse
import json
import math
import re

RATES = {"A": 0.24029, "B": 0.17994, "C": 0.20519}       # USD/h list price with the planned disks (90/80/80 GB)
SETUP_H = 0.25
SAFETY = 1.25
ALL = [f"sub-{i:03d}" for i in range(1, 101)]
ODD = [f"sub-{i:03d}" for i in range(1, 101, 2)]


def pilot_means(manifest):
    by = {}
    for c in manifest["cases"]:
        by.setdefault(c["tool"], []).append(float(c["seconds"]))
    return {t: sum(v) / len(v) for t, v in by.items()}, sorted({c["case"] for c in manifest["cases"]})


def plan(means, pilot_usd, done, cap=10.0, rates=RATES):
    todo_all = [c for c in ALL if c not in done]
    out = {"pilot_usd": round(pilot_usd, 4), "m_seconds": {t: round(v, 1) for t, v in means.items()}, "cap_usd": cap}
    for tier, sam in (("A", ALL), ("B", ODD), ("no SAMSEG", [])):
        sam_todo = [c for c in sam if c not in done]
        half = (len(sam_todo) + 1) // 2
        blocks = {"A": {"tools": ["wmhsynthseg", "mindglide"], "cases": todo_all},
                  "B": {"tools": ["samseg"], "cases": sam_todo[:half]},
                  "C": {"tools": ["samseg"], "cases": sam_todo[half:]}}
        hours = {}
        for vm, b in blocks.items():
            if not b["cases"]:
                continue
            per = sum(means[t] for t in b["tools"])
            hours[vm] = SETUP_H + len(b["cases"]) * per * SAFETY / 3600.0
        proj = pilot_usd + sum(rates[vm] * h for vm, h in hours.items())
        if proj > cap:
            continue
        for f in [round(1.5 - 0.05 * i, 2) for i in range(11)]:             # 1.5 ... 1.0
            mh = {vm: math.ceil(f * h) for vm, h in hours.items()}
            worst = pilot_usd + sum(rates[vm] * mh[vm] for vm in mh)
            if worst <= cap:
                out.update({"tier": tier, "projected_usd": round(proj, 3),
                            "projected_hours": {k: round(v, 2) for k, v in hours.items()},
                            "max_hours": mh, "guard_factor": f, "worst_case_usd_at_guards": round(worst, 3),
                            "worst_case_within_cap": True,
                            "blocks": {vm: {"tools": b["tools"], "n": len(b["cases"]), "cases": b["cases"]}
                                       for vm, b in blocks.items() if b["cases"]}})
                return out
    out.update({"tier": "none fits", "projected_usd": None})
    return out


def pilot_cost(text):
    m = re.search(r"cost_usd_compute_estimate=([0-9.]+)", text)
    return float(m.group(1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot-manifest", required=True)
    ap.add_argument("--pilot-cost", required=True)
    ap.add_argument("--cap", type=float, default=10.0)
    a = ap.parse_args()
    means, done = pilot_means(json.load(open(a.pilot_manifest)))
    p = plan(means, pilot_cost(open(a.pilot_cost).read()), done, a.cap)
    print(json.dumps({k: v for k, v in p.items() if k != "blocks"}, indent=1))
    for vm, b in p.get("blocks", {}).items():
        print(vm, b["tools"], b["n"], " ".join(b["cases"]))


if __name__ == "__main__":
    main()
