"""Paper 1 addendum: one HELPER VM that takes the LAST remaining LST-AI items of mimics-v1 and the LAST remaining SAMSEG
items of mimics-v3, so the three VMs (quota 12 vCPU) finish together (owner request 2026-11-14: "se demora demasiado").

The main VMs re-check the bucket every 5 cases (LST-AI, SAMSEG), so items the helper finishes are skipped by them; the
helper takes the items the main VMs would reach LAST, so overlap is at most one batch. No new outcome, no new arm: the
same tools, inputs and plan format; the preparation is already in the bucket (prep markers), so the plan has no prep.

    python research/paper_1/mimics/launch_helper.py [--lstai 166] [--samseg 25] [--hours 12] [--dry-run]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import launch_mimics as L  # noqa: E402


def remaining_in_order(plan, tool, have):
    out = []
    for st in plan["steps"]:
        if tool in st["tools"]:
            for i in st["inputs"]:
                name = (f"lstai/cohort/{i}_lstai_prob.nii.gz" if tool == "lstai" else f"toolbench/cohort/{i}_{tool}_seg.nii.gz")
                if tool == "lstai" and i.startswith("mslesseg_P49_T2"):
                    continue
                if name not in have:
                    out.append(i)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lstai", type=int, default=166)
    ap.add_argument("--samseg", type=int, default=25)
    ap.add_argument("--hours", type=int, default=12)
    ap.add_argument("--name", default="mimics-h1")
    ap.add_argument("--disk", type=int, default=108)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    have, plans = L.listing(), L.plans_in_bucket()
    lst = remaining_in_order(plans["mimics-v1"], "lstai", have)
    sam = remaining_in_order(plans["mimics-v3"], "samseg", have)
    take_l, take_s = lst[-a.lstai:] if a.lstai else [], sam[-a.samseg:] if a.samseg else []
    plan = {"prep": [], "steps": [s for s in ({"tools": ["lstai"], "inputs": take_l}, {"tools": ["samseg"], "inputs": take_s})
                                  if s["inputs"]],
            "idle_wait_h": 1}
    print(f"remaining: lstai {len(lst)}, samseg {len(sam)}; helper takes lstai {len(take_l)}, samseg {len(take_s)}")
    # 2026-11-14: the regional SSD quota is 250 GB and the two running VMs hold 140 GB, so the helper gets 108 GB on a
    # standard 4-vCPU machine (FreeSurfer 41.2 GB + LST-AI 30.2 GB docker use, from the pilot), like mimics-v3.
    L.VM[a.name] = ("c2d-standard-4", a.disk, 8, "lstai fs", "v3")
    if a.dry_run:
        print("dry run: plan not uploaded, no VM")
        return
    L.launch(a.name, L.upload_plan(a.name, plan), a.hours,
             "Paper 1 addendum: helper taking the last LST-AI items of mimics-v1 and the last SAMSEG items of mimics-v3 "
             "(same tools and inputs; owner request 2026-11-14)", False)


if __name__ == "__main__":
    main()
