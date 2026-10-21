"""LOCAL ONLY (no cloud calls): apply the pre-stated run tiers of PROTOCOL.md section 4.4 to the
timings MEASURED by the pilot. Runtime only — accuracy is never read here.

    python research/paper_f/plan_budget.py --pilot-manifest <D>/toolbench-pilot.json --spent-usd 5.21

--spent-usd = pilot + wave 1 at list price (compute ledger) when wave 1 is finished; before that, leave it
out and the wave-1 cost is projected from the pilot medians. Prints the SAMSEG tier, the case list per
VM and the --max-hours each VM needs (projected hours x 1.25 safety, rounded up).
"""
import argparse
import json
import math
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
BUDGET_USD = 15.0
SAFETY = 1.25
CPU_RULE_MIN = 15.0
# List USD/h incl. boot disk (RUNBOOK.md section 2); launch_vm.py re-reads the catalog at launch.
RATE = {"n2d-highmem-4/150": 0.24851, "n2d-standard-4/150": 0.18953, "n2-standard-4/150": 0.21478,
        "n2d-standard-4/100": 0.18268, "n2-standard-4/100": 0.20794, "n2-highmem-4/150": 0.28258}
SETUP_H = {"fs": 0.25, "mindglide": 0.12}                      # expected setup per VM (RUNBOOK.md section 5)


def tier_c_ids(expected):
    """Fixed now: all PediMS + all Muslim + MS3SEG odd ids (129 scans)."""
    return sorted(c for c, v in expected.items()
                  if v["cohort"] in ("pedims", "muslim") or (v["cohort"] == "ms3seg" and int(c.split("_")[1]) % 2 == 1))


def pilot_minutes(manifest, expected):
    """{tool: {"thick": median min, "iso": median min, "peak_gb": max, "swap_gb": max, "timeouts": n}}."""
    out = {}
    for rec in manifest.get("cases", []):
        t = out.setdefault(rec["tool"], {"thick": [], "iso": [], "peak_gb": 0.0, "swap_gb": 0.0, "timeouts": 0})
        t[expected[rec["case"]]["band"]].append(rec["seconds"] / 60.0)
        t["peak_gb"] = max(t["peak_gb"], rec.get("peak_mem_used_gb") or 0.0)
        t["swap_gb"] = max(t["swap_gb"], rec.get("peak_swap_used_gb") or 0.0)
    for err in manifest.get("errors", []):
        t = out.setdefault(err["tool"], {"thick": [], "iso": [], "peak_gb": 0.0, "swap_gb": 0.0, "timeouts": 0})
        t["timeouts"] += int("exceeded" in err.get("error", ""))
    for t in out.values():
        for band in ("thick", "iso"):
            t[band] = statistics.median(t[band]) if t[band] else None
    return out


def vm_plan(n_scans, minutes, rate, vms, setup_h):
    """Even split across `vms`; hours and cost with the safety factor; max-hours per VM (ceil + 1)."""
    per_vm = math.ceil(n_scans / vms)
    hours = per_vm * minutes * SAFETY / 60.0 + setup_h
    return {"vms": vms, "scans_per_vm": per_vm, "hours_per_vm": round(hours, 2),
            "max_hours": int(math.ceil(hours)) + 1, "usd": round(vms * hours * rate, 2)}


def decide(manifest, expected, spent_usd=None, pilot_usd=0.5):
    m = pilot_minutes(manifest, expected)
    n_all = len(expected)
    thick = [c for c, v in expected.items() if v["band"] == "thick"]
    iso = [c for c, v in expected.items() if v["band"] == "iso"]
    plan = {"pilot_minutes": m, "dropped_cpu_rule": []}
    for tool in ("wmhsynthseg", "mindglide"):
        mins = [x for x in (m.get(tool, {}).get("thick"), m.get(tool, {}).get("iso")) if x is not None]
        if not mins or max(mins) > CPU_RULE_MIN:
            plan["dropped_cpu_rule"].append(tool)
    wave1 = {}
    if "wmhsynthseg" not in plan["dropped_cpu_rule"]:
        mins = max(x for x in (m["wmhsynthseg"]["thick"], m["wmhsynthseg"]["iso"]) if x is not None)
        wave1["wmhsynthseg"] = vm_plan(n_all, mins, RATE["n2d-highmem-4/150"], 1, SETUP_H["fs"])
    if "mindglide" not in plan["dropped_cpu_rule"]:
        mins = max(x for x in (m["mindglide"]["thick"], m["mindglide"]["iso"]) if x is not None)
        wave1["mindglide"] = vm_plan(n_all, mins, (RATE["n2d-standard-4/100"] + RATE["n2-standard-4/100"]) / 2, 2,
                                     SETUP_H["mindglide"])
    plan["wave1"] = wave1
    spent = spent_usd if spent_usd is not None else pilot_usd + sum(v["usd"] for v in wave1.values())
    plan["spent_or_projected_before_samseg_usd"] = round(spent, 2)
    s = m.get("samseg", {})
    peak = s.get("peak_gb", 0.0) + s.get("swap_gb", 0.0)
    high = peak >= 14.0
    rate = ((2 * RATE["n2d-highmem-4/150"] + RATE["n2-highmem-4/150"]) / 3 if high
            else (2 * RATE["n2d-standard-4/150"] + RATE["n2-standard-4/150"]) / 3)
    plan["samseg_machines"] = ("2 x n2d-highmem-4 + 1 x n2-highmem-4" if high else
                               "2 x n2d-standard-4 + 1 x n2-standard-4") + " (150 GB disk)"
    if s.get("thick") is None or s["thick"] > CPU_RULE_MIN:
        plan["samseg_tier"] = "dropped: CPU rule (median thick-slice scan > 15 min or not measured)"
        return plan
    tiers = []
    if s.get("iso") is not None and s["iso"] <= CPU_RULE_MIN:
        tiers.append(("A", sorted(expected), None))
    tiers += [("B", sorted(thick), None), ("C", tier_c_ids(expected), None)]
    for name, ids, _ in tiers:
        n_thick = sum(expected[c]["band"] == "thick" for c in ids)
        n_iso = len(ids) - n_thick
        minutes = (n_thick * s["thick"] + n_iso * (s.get("iso") or 0.0)) / len(ids)
        p = vm_plan(len(ids), minutes, rate, 3, SETUP_H["fs"])
        if spent + p["usd"] <= BUDGET_USD:
            plan.update(samseg_tier=name, samseg_ids=ids, samseg=p, projected_total_usd=round(spent + p["usd"], 2))
            return plan
    plan["samseg_tier"] = "dropped: budget (no tier fits under 15 USD)"
    return plan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot-manifest", required=True)
    ap.add_argument("--expected", default=os.path.join(HERE, "flames_inputs.json"))
    ap.add_argument("--spent-usd", type=float)
    ap.add_argument("--pilot-usd", type=float, default=0.5)
    ap.add_argument("--ids-out", help="prefix: writes <prefix>_1.txt .. _3.txt, the SAMSEG case ids of each VM "
                                      "(one line, space separated) for --meta cases=...")
    a = ap.parse_args()
    plan = decide(json.load(open(a.pilot_manifest)), json.load(open(a.expected)), a.spent_usd, a.pilot_usd)
    ids = plan.pop("samseg_ids", None)
    print(json.dumps(plan, indent=1))
    if ids and a.ids_out:
        for k, part in enumerate(split_even(ids, plan["samseg"]["vms"]), start=1):
            open(f"{a.ids_out}_{k}.txt", "w").write(" ".join(part))
            print(f"VM {k}: {len(part)} SAMSEG ids -> {a.ids_out}_{k}.txt")


def split_even(ids, k):
    """Deterministic split into k consecutive chunks whose sizes differ by at most one."""
    n, out, start = len(ids), [], 0
    for i in range(k):
        size = n // k + (1 if i < n % k else 0)
        out.append(ids[start:start + size])
        start += size
    return out


if __name__ == "__main__":
    main()
