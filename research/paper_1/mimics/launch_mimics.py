"""Paper 1 addendum, amendment 1 (PREREG-mimics-thickness.md section 15): pilot, full runs, status, G3 check.
Project mstool-research only: every gcloud call carries --project=mstool-research and the isolated configuration
CLOUDSDK_CONFIG=C:/Users/Nicolas/.gcloud-mstool (launch_vm.py sets it too). Spot VMs, self-deleting.

    python research/paper_1/mimics/launch_mimics.py pilot [--dry-run]
    python research/paper_1/mimics/launch_mimics.py check <scratch dir> --inputs wmh_utrecht_1 sub-178 ...
    python research/paper_1/mimics/launch_mimics.py full --pilot-json p.json --spent-usd X [--dry-run]
    python research/paper_1/mimics/launch_mimics.py status
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import plan_mimics as PM  # noqa: E402

os.environ["CLOUDSDK_CONFIG"] = r"C:\Users\Nicolas\.gcloud-mstool"
PROJECT = "mstool-research"
BK = "gs://mstool-research-data"
SETS = os.path.join(HERE, "analysis_sets.json")
CODE = [os.path.join(HERE, f) for f in ("mimics_vm.py", "mimics_prep.py", "simulate_thick.py", "thick_slice.py",
                                        "analysis_sets.json")] + \
       [os.path.join(ROOT, "research", "cloud", f) for f in ("flames_ensemble_driver.py", "lstai_driver.py",
                                                            "toolbench_driver.py", "job_common.py")] + \
       [os.path.join(ROOT, "research", "paper_f", "flames_inputs.json"), os.path.join(ROOT, "research", "paper_1", "controls_inputs.json")]
SHUTDOWN = ('#!/bin/bash\nMD=http://metadata/computeMetadata/v1/instance\n'
            'P=$(curl -sf -H "Metadata-Flavor: Google" $MD/preempted)\nN=$(curl -sf -H "Metadata-Flavor: Google" $MD/name)\n'
            'echo "$N preempted=$P $(date -u +%Y-%m-%dT%H:%M:%SZ)" | '
            'gcloud storage cp - gs://mstool-research-data/mimics/interruptions/$N-$(date -u +%s).txt --quiet\n')
TOOLS_NN = ["flames", "lstai", "mindglide"]
VM = {  # name: (machine type, disk GB, swap GB, needs, rate key)
    "mimics-pilot": ("c2d-highmem-4", 130, 16, "hdbet flames lstai mindglide fs cdata", "pilot"),
    "mimics-nn-a": ("c2d-standard-4", 50, 8, "hdbet flames lstai mindglide", "nn"),
    "mimics-nn-b": ("c2d-standard-4", 50, 8, "hdbet flames lstai mindglide", "nn"),
    "mimics-fs-a": ("c2d-highmem-4", 75, 16, "fs", "fs_hm"),
    "mimics-fs-b": ("c2d-standard-4", 75, 8, "fs", "fs_std"),
}


def sh(cmd, check=True):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"FAILED: {cmd}\n{r.stderr[-1500:]}")
    return r.stdout


def gs(args):
    return sh(f"gcloud storage {args} --project={PROJECT}")


def sets():
    return json.load(open(SETS))


def c_ids(s, thick=(3, 5, 7), with_c2=True):
    ms = sorted(s["C1_ms_iso"])
    c1 = [f"{c}_th{t}" for c in ms for t in thick]
    sam = [f"{c}_th{t}" for c in s["C1_samseg_subset"]["ids"] for t in (1,) + tuple(thick)]
    c2 = [f"{c}_th7" for c in s["C2_sibbms"]] if with_c2 else []
    return c1, sam, c2


def prep_c_items(s):
    """The pilot simulates EVERY C input (3, 5 and 7 mm; 7 mm for C2) so they are frozen before any tool runs."""
    c1_all = [f"{c}_th{t}" for c in sorted(s["C1_ms_iso"]) for t in (3, 5, 7)] + \
             [f"{c}_th1" for c in s["C1_samseg_subset"]["ids"]]
    return [{"kind": "simulate", "block": "C1", "cases": sorted(s["C1_ms_iso"]), "thicknesses": [3, 5, 7],
             "one_mm": s["C1_samseg_subset"]["ids"], "finalize": c1_all},
            {"kind": "simulate", "block": "C2", "cases": list(s["C2_sibbms"]), "thicknesses": [7],
             "finalize": [f"{c}_th7" for c in s["C2_sibbms"]]}]


def pilot_plan(s):
    p = s["pilot"]
    inputs = p["A_wmh2017"] + p["B_dlbs"] + p["C1_ms"] + p["C2_sibbms"]
    return {"prep": prep_c_items(s) + [{"kind": "hdbet", "block": "A", "cohort": "wmh2017", "ids": p["A_wmh2017"]},
                                       {"kind": "hdbet", "block": "B", "cohort": "dlbs", "ids": p["B_dlbs"]}],
            "steps": [{"tools": TOOLS_NN + ["wmhsynthseg", "samseg"], "inputs": inputs}], "idle_wait_h": 1}


def split_balanced(items, hours_fixed, sec):
    """Assign items (id, seconds) alternately to the lighter of two machines with fixed hours already booked."""
    load = list(hours_fixed)
    out = ([], [])
    for iid, s in items:
        k = 0 if load[0] <= load[1] else 1
        out[k].append(iid)
        load[k] += s / 3600.0
    return out, load


def full_plans(s, kw, sec):
    thick = tuple(kw.get("c1_thick", (3, 5, 7)))
    with_c2 = kw.get("with_c2", True)
    b_ids = s["B1_sample"]["reduced_75"]["ids"] if kw.get("dlbs_n") == 75 else s["B1_sample"]["ids"]
    a_ids = sorted(s["A_wmh2017"])
    a_test = [i for i in a_ids if s["A_wmh2017"][i]["split"] == "test"]
    c1, sam_c1, c2 = c_ids(s, thick, with_c2)
    nn_s = lambda blk: sum(PM.seconds_for(blk, st, sec) for st in ("flames5", "lstai", "mindglide"))  # noqa: E731
    hd = PM.seconds_for
    # nn: A on nn-a (with its HD-BET), B (+ C2) on nn-b (with its HD-BET); C1 split to balance the two.
    fixed = [len(a_ids) * (hd("A", "hdbet", sec) + nn_s("A")) / 3600.0,
             len(b_ids) * (2 * hd("B1", "hdbet", sec) + nn_s("B1")) / 3600.0 + len(c2) * nn_s("C2") / 3600.0]
    (c1_a, c1_b), nn_load = split_balanced([(i, nn_s("C1")) for i in c1], fixed, sec)
    plans = {
        "mimics-nn-a": {"prep": [{"kind": "hdbet", "block": "A", "cohort": "wmh2017", "ids": a_ids, "finalize": a_ids}],
                        "steps": [{"tools": TOOLS_NN, "inputs": a_ids}, {"tools": TOOLS_NN, "inputs": c1_a, "wait_blocks": ["C1"]}]},
        "mimics-nn-b": {"prep": [{"kind": "hdbet", "block": "B", "cohort": "dlbs", "ids": b_ids, "finalize": b_ids}],
                        "steps": [{"tools": TOOLS_NN, "inputs": b_ids}]
                        + ([{"tools": TOOLS_NN, "inputs": c2, "wait_blocks": ["C2"]}] if c2 else [])
                        + [{"tools": TOOLS_NN, "inputs": c1_b, "wait_blocks": ["C1"]}]},
    }
    # fs: WMH-SynthSeg on fs-a (C2, C1, A test, B); SAMSEG split so that fs-a and fs-b end together.
    wmh = [(c2, "C2"), (c1, "C1"), (a_test, "A"), (b_ids, "B")]
    wmh_h = sum(len(ids) * hd({"A": "A", "B": "B1"}.get(b, b), "wmhsynthseg", sec) for ids, b in wmh) / 3600.0
    sam_seq = [(i, "C2") for i in c2] + [(i, "C1") for i in sam_c1] + [(i, "A") for i in a_ids] + [(i, "B") for i in b_ids]
    sam_s = lambda b: hd({"A": "A", "B": "B1"}.get(b, b), "samseg", sec)  # noqa: E731
    total = wmh_h + sum(sam_s(b) for _, b in sam_seq) / 3600.0
    fsa_sam, acc = [], wmh_h
    for iid, b in reversed(sam_seq):                     # fs-a takes SAMSEG from the end (A, B) up to balance
        if acc + sam_s(b) / 3600.0 > total / 2:
            break
        fsa_sam.append((iid, b))
        acc += sam_s(b) / 3600.0
    fsa_set = {i for i, _ in fsa_sam}
    fsb_sam = [(i, b) for i, b in sam_seq if i not in fsa_set]

    def steps(tool, seq):
        out = []
        for blk in ("C2", "C1", "A", "B"):
            ids = [i for i, b in seq if b == blk]
            if ids:
                out.append({"tools": [tool], "inputs": ids, "wait_blocks": [blk]})
        return out
    plans["mimics-fs-a"] = {"prep": [], "steps": [{"tools": ["wmhsynthseg"], "inputs": ids, "wait_blocks": [b]}
                                                  for ids, b in wmh if ids] + steps("samseg", list(reversed(fsa_sam)))}
    plans["mimics-fs-b"] = {"prep": [], "steps": steps("samseg", fsb_sam)}
    for p in plans.values():
        p["idle_wait_h"] = 8
    hours = {"mimics-nn-a": nn_load[0], "mimics-nn-b": nn_load[1], "mimics-fs-a": acc, "mimics-fs-b": total - acc}
    return plans, hours


def upload_code():
    for p in CODE:
        if not os.path.exists(p):
            raise SystemExit(f"missing {p}")
    files = " ".join(f'"{p}"' for p in CODE)
    gs(f"cp {files} {BK}/mimics/code/ --quiet")
    return {os.path.basename(p): hashlib.sha256(open(p, "rb").read()).hexdigest() for p in CODE}


def upload_plan(name, plan):
    d = tempfile.mkdtemp()
    p = os.path.join(d, f"{name}.json")
    json.dump(plan, open(p, "w"), indent=1)
    gs(f'cp "{p}" {BK}/mimics/plans/{name}.json --quiet')
    return f"mimics/plans/{name}.json"


def launch(name, plan_path, max_hours, purpose, dry):
    mtype, disk, swap, needs, rate = VM[name]
    sd = os.path.join(tempfile.mkdtemp(), "shutdown.sh")
    open(sd, "w", newline="\n").write(SHUTDOWN)
    cmd = [sys.executable, os.path.join(ROOT, "research", "cloud", "launch_vm.py"), "--name", name, "--machine-type", mtype,
           "--disk-gb", str(disk), "--spot", "--startup", os.path.join(ROOT, "research", "cloud", "vm_mimics.sh"),
           "--paper", "1", "--max-hours", str(max_hours), "--purpose", purpose,
           "--meta", f"plan={plan_path}", f"needs={needs}", f"swap-gb={swap}", f"shutdown-script={SHUTDOWN}"]
    print(" ".join(cmd[:14]), "...", flush=True)
    if dry:
        return
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    print(r.stdout.strip(), r.stderr.strip()[-1500:], flush=True)
    if r.returncode != 0:
        raise SystemExit(f"launch of {name} failed")


def cmd_pilot(a):
    s = sets()
    plan = pilot_plan(s)
    if a.dry_run:
        print(json.dumps({k: (v if k != "prep" else [{x: (y if x not in ("cases", "finalize", "one_mm") else len(y))
                                                       for x, y in i.items()} for i in v]) for k, v in plan.items()}, indent=1))
        return
    print(json.dumps(upload_code(), indent=1))
    launch("mimics-pilot", upload_plan("mimics-pilot", plan), 4,
           "Paper 1 addendum pilot (Spot): all C inputs simulated; HD-BET + every tool on wmh_utrecht_1, DLBS sub-178, "
           "mslesseg_P10_T1 at 7 mm, SibBMS sub-001 at 7 mm", a.dry_run)


def cmd_full(a):
    s = sets()
    sec = dict(PM.LEDGER_SECONDS)
    if a.pilot_json:
        sec.update({k: float(v) for k, v in json.load(open(a.pilot_json)).items()})
    rule = PM.apply_rule(sec, a.spent_usd)
    if not rule.get("selected"):
        raise SystemExit(f"budget rule: no launch ({rule['reason']})")
    g = PM.guards(rule["kwargs"], sec, a.spent_usd)
    if not g:
        raise SystemExit("no guard setting keeps the worst case under the cap: no launch")
    plans, hours = full_plans(s, rule["kwargs"], sec)
    print(json.dumps({"variant": rule["selected"], "projection": rule["projection"], "guards": g,
                      "projected_hours": {k: round(v, 1) for k, v in hours.items()},
                      "inputs_per_vm": {k: sum(len(st["inputs"]) for st in p["steps"]) for k, p in plans.items()}}, indent=1))
    if a.dry_run:
        return
    upload_code()
    guard_of = {"mimics-nn-a": "nn-a", "mimics-nn-b": "nn-b", "mimics-fs-a": "fs-a", "mimics-fs-b": "fs-b"}
    for name, plan in plans.items():
        launch(name, upload_plan(name, plan), g["max_hours"][guard_of[name]],
               f"Paper 1 addendum full run ({rule['selected']}): {name.split('-', 1)[1]} - "
               f"{', '.join(sorted({t for st in plan['steps'] for t in st['tools']}))}", False)


def cmd_status(a):
    print(sh(f"gcloud compute instances list --project={PROJECT} --filter=name~^mimics- --format=\"table(name,status,machineType.basename(),zone.basename())\"", check=False))
    for pre in ("flames/cohort", "lstai/cohort", "toolbench/cohort", "interruptions", "inputs"):
        out = sh(f"gcloud storage ls {BK}/mimics/{pre}/ --project={PROJECT}", check=False)
        names = [x.rsplit('/', 1)[-1] for x in out.split() if x.strip()]
        print(f"{pre}: {len(names)} files" + (f" {names}" if pre == "interruptions" else ""))


def cmd_check(a):
    """G3 structural check of the outputs of the given inputs (downloads them to a scratch folder; PASS/FAIL only)."""
    import nibabel as nib
    import numpy as np
    sys.path.insert(0, os.path.join(ROOT, "research", "cloud"))
    import job_common as jc
    d = a.scratch
    os.makedirs(d, exist_ok=True)
    recs = {}
    for name in gs(f"ls {BK}/mimics/manifests/").split():
        if "/prep-" in name:
            recs.update(json.loads(gs(f"cat {name}")).get("records", {}))
    tbm = {}
    for name in gs(f"ls {BK}/mimics/toolbench/manifests/").split():
        for c in json.loads(gs(f"cat {name}")).get("cases", []):
            tbm[(c["case"], c["tool"])] = c
    bad = 0
    for iid in a.inputs:
        r = recs[iid]
        files = [f"flames/cohort/{iid}_f{k}_prob.nii.gz" for k in range(5)] + [f"lstai/cohort/{iid}_lstai_prob.nii.gz"] + \
                [f"toolbench/cohort/{iid}_{t}_seg.nii.gz" for t in a.tools]
        for f in files:
            loc = os.path.join(d, os.path.basename(f))
            why = []
            if not os.path.exists(loc):
                subprocess.run(f'gcloud storage cp {BK}/mimics/{f} "{loc}" --project={PROJECT} --quiet', shell=True,
                               capture_output=True)
            if not os.path.exists(loc):
                why.append("missing")
            else:
                img = nib.load(loc)
                if list(img.shape[:3]) != r["shape"] or not np.allclose(img.affine, np.asarray(r["affine"]), atol=1e-3):
                    why.append("not on the input grid")
                if "_seg" in f:
                    tool = f.rsplit("_", 2)[-2]
                    data = np.asarray(img.dataobj)
                    if img.get_data_dtype() != np.uint8 or not set(np.unique(data).tolist()) <= {0, 1}:
                        why.append("not binary uint8")
                    m = tbm.get((iid, tool))
                    if m is None or m.get("seg_sha256") != jc.sha256(loc):
                        why.append("SHA-256 differs from the manifest")
            bad += bool(why)
            print(f"{'PASS' if not why else 'FAIL'} {f}" + ("" if not why else ": " + "; ".join(why)), flush=True)
    print(f"G3: {'PASS' if not bad else f'{bad} FAIL'}")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pilot")
    p.add_argument("--dry-run", action="store_true")
    f = sub.add_parser("full")
    f.add_argument("--pilot-json")
    f.add_argument("--spent-usd", type=float, default=0.0)
    f.add_argument("--dry-run", action="store_true")
    sub.add_parser("status")
    c = sub.add_parser("check")
    c.add_argument("scratch")
    c.add_argument("--inputs", nargs="+", required=True)
    c.add_argument("--tools", nargs="+", default=["wmhsynthseg", "mindglide", "samseg"])
    a = ap.parse_args()
    sys.exit({"pilot": cmd_pilot, "full": cmd_full, "status": cmd_status, "check": cmd_check}[a.cmd](a) or 0)


if __name__ == "__main__":
    main()
