"""Paper 1 full run: apply the budget rule to the pilot and launch the three self-deleting VMs
(PREREG-healthy-controls.md section 8). Project mstool-research only (launch_vm.py uses the isolated
gcloud configuration and --project=mstool-research on every command).

    python research/paper_1/launch_full_run.py --pilot-manifest <toolbench-ctl-pilot.json> \
        --pilot-cost <toolbench-ctl-pilot.txt> [--dry-run]

VM A n2d-highmem-4 (90 GB): WMH-SynthSeg then MindGlide; VM B n2d-standard-4 (80 GB) and VM C n2-standard-4
(80 GB): SAMSEG, half each. 90 + 80 + 80 = 250 GB = the regional SSD quota; 3 of 4 external addresses.
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import plan_controls_budget as P  # noqa: E402

VMS = {"A": ("toolbench-ctl-wmh-mg", "n2d-highmem-4", 90,
             "Paper 1 healthy controls: WMH-SynthSeg then MindGlide on the {n} SibBMS controls not done in the pilot"),
       "B": ("toolbench-ctl-samseg-a", "n2d-standard-4", 80, "Paper 1 healthy controls: SAMSEG lesions, block 1 ({n} controls)"),
       "C": ("toolbench-ctl-samseg-b", "n2-standard-4", 80, "Paper 1 healthy controls: SAMSEG lesions, block 2 ({n} controls)")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot-manifest", required=True)
    ap.add_argument("--pilot-cost", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    means, done = P.pilot_means(json.load(open(a.pilot_manifest)))
    plan = P.plan(means, P.pilot_cost(open(a.pilot_cost).read()), done)
    print(json.dumps({k: v for k, v in plan.items() if k != "blocks"}, indent=1), flush=True)
    if plan.get("tier") in (None, "none fits") or not plan.get("worst_case_within_cap"):
        raise SystemExit("budget rule: no launch (see PREREG section 8)")
    for vm, b in plan["blocks"].items():
        name, mtype, disk, purpose = VMS[vm]
        mh = int(plan["max_hours"][vm])
        cmd = [sys.executable, os.path.join(ROOT, "research", "cloud", "launch_vm.py"), "--name", name,
               "--machine-type", mtype, "--disk-gb", str(disk), "--startup", os.path.join(ROOT, "research", "cloud", "vm_toolbench.sh"),
               "--paper", "1", "--max-hours", str(mh), "--purpose", purpose.format(n=b["n"]),
               "--meta", f"tools={' '.join(b['tools'])}", "datasets=sibbms", f"cases={' '.join(b['cases'])}",
               "expected=controls_inputs.json", "code-prefix=toolbench/code-paper1"]
        print(f"{vm}: {name} {mtype} {disk} GB max-hours {mh} tools {b['tools']} n {b['n']}", flush=True)
        if not a.dry_run:
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
            print(r.stdout.strip(), r.stderr.strip()[-1500:], flush=True)
            if r.returncode != 0:
                raise SystemExit(f"launch of {name} failed; the other VMs keep running (each deletes itself)")


if __name__ == "__main__":
    main()
