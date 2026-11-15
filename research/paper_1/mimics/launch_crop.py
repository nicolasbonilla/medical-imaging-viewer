"""Paper 1 addendum: the pre-registered memory fallback for WMH-SynthSeg (PREREG-mimics-thickness.md section 10:
"a WMH-SynthSeg out-of-memory stop is re-run with `--crop`, flagged").

The 10 WMH 2017 Amsterdam GE 1.5 T subjects (wmh_ams-ge1t5_150..159) stopped with exit 137 (killed: out of memory) in
every mimics-v2 attempt (r1-r5, c2d-highmem-4, 32 GB + 16 GB swap). This launches ONE VM, mimics-c1 (same machine,
image, inputs and tool as mimics-v2), that runs WMH-SynthSeg on those subjects only, with `--crop`. The driver
records "crop": true in the run metadata, so the outputs are flagged. No other tool, input or arm changes. The
preparation is already in the bucket, so the plan has no prep step.

    python research/paper_1/mimics/launch_crop.py [--hours 6] [--dry-run]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import launch_mimics as L  # noqa: E402


def missing_wmhsynthseg(have):
    out = []
    for st in L.plans_in_bucket()["mimics-v2"]["steps"]:
        if "wmhsynthseg" in st["tools"]:
            out += [i for i in st["inputs"] if f"toolbench/cohort/{i}_wmhsynthseg_seg.nii.gz" not in have]
    return sorted(set(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=6)
    ap.add_argument("--name", default="mimics-c1")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    ids = missing_wmhsynthseg(L.listing())
    print(f"WMH-SynthSeg items still missing: {len(ids)} {ids}")
    if not ids:
        return
    if any(not i.startswith("wmh_ams-ge1t5_") for i in ids):
        raise SystemExit("unexpected missing items: the fallback is registered for the out-of-memory stops only")
    plan = {"prep": [], "steps": [{"tools": ["wmhsynthseg"], "inputs": ids, "wmh_crop": True}], "idle_wait_h": 1}
    L.VM[a.name] = L.VM["mimics-v2"]          # same machine type, disk, swap, needs and price key as mimics-v2
    if a.dry_run:
        print("dry run: nothing uploaded, no VM", L.VM[a.name])
        return
    print(L.upload_code())                   # the VM runs mimics_vm.py from the bucket: it must carry the wmh_crop step
    L.launch(a.name, L.upload_plan(a.name, plan), a.hours,
             "Paper 1 addendum: pre-registered --crop re-run of the 10 WMH-SynthSeg out-of-memory stops (PREREG section 10)",
             False)


if __name__ == "__main__":
    main()
