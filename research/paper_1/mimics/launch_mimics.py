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
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
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
# Global quota CPUS_ALL_REGIONS = 12 vCPUs -> three 4-vCPU machines at a time. Disk per VM from the pilot (docker disk
# use: FreeSurfer 41.2 GB, LST-AI 30.2 GB, MindGlide 13.3 GB): 65 + 95 + 75 = 235 GB <= the 250 GB regional SSD quota.
VM = {  # name: (machine type, disk GB, swap GB, needs, rate key)
    "mimics-pilot": ("c2d-highmem-4", 130, 16, "hdbet flames lstai mindglide fs cdata", "pilot"),
    "mimics-v1": ("c2d-standard-4", 65, 8, "hdbet flames lstai", "v1"),
    "mimics-v2": ("c2d-highmem-4", 95, 16, "hdbet flames mindglide fs", "v2"),
    "mimics-v3": ("c2d-standard-4", 75, 8, "hdbet flames fs", "v3"),
}
RATE_VM = {"v1": 0.0921, "v2": 0.1252, "v3": 0.0935, "pilot": 0.13002}      # Spot list price incl. boot disk
FULL_VMS = ("mimics-v1", "mimics-v2", "mimics-v3")


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
    """Three Spot VMs. Fixed: HD-BET of A and LST-AI on v1 (LST-AI image), WMH-SynthSeg and MindGlide on v2 (FreeSurfer +
    MindGlide images, 32 GB), HD-BET of B on v3 (FreeSurfer image). Flexible: SAMSEG (v2, v3) then FLAMeS (v1, v2, v3),
    each input to the least-loaded allowed VM. One step per (block, tool); blocks a VM does not prepare itself come after
    the ones it can do at once (A is prepared by v1, B by v3; C1 and C2 by the pilot)."""
    thick = tuple(kw.get("c1_thick", (3, 5, 7)))
    with_c2 = kw.get("with_c2", True)
    b_ids = s["B1_sample"]["reduced_75"]["ids"] if kw.get("dlbs_n") == 75 else s["B1_sample"]["ids"]
    a_ids = sorted(s["A_wmh2017"])
    a_test = [i for i in a_ids if s["A_wmh2017"][i]["split"] == "test"]
    c1, sam_c1, c2 = c_ids(s, thick, with_c2)
    blk = {"A": "A", "B": "B1", "C1": "C1", "C2": "C2"}
    sec_of = lambda b, step: PM.seconds_for(blk[b], step, sec)  # noqa: E731
    load = {v: 0.0 for v in FULL_VMS}
    work = {v: [] for v in FULL_VMS}                             # (block, tool, input)

    def put(v, b, tool, ids, step):
        for i in ids:
            work[v].append((b, tool, i))
            load[v] += sec_of(b, step) / 3600.0
    load["mimics-v1"] += len(a_ids) * sec_of("A", "hdbet") / 3600.0
    load["mimics-v3"] += 2 * len(b_ids) * sec_of("B", "hdbet") / 3600.0
    for b, ids in (("A", a_ids), ("B", b_ids), ("C2", c2), ("C1", c1)):
        put("mimics-v1", b, "lstai", [i for i in ids if not i.startswith("mslesseg_P49_T2")], "lstai")
        put("mimics-v2", b, "mindglide", ids, "mindglide")
    for b, ids in (("A", a_test), ("B", b_ids), ("C2", c2), ("C1", c1)):
        put("mimics-v2", b, "wmhsynthseg", ids, "wmhsynthseg")
    flex = [(b, "samseg", i, ("mimics-v2", "mimics-v3")) for b, ids in (("C2", c2), ("C1", sam_c1), ("A", a_ids), ("B", b_ids))
            for i in ids]
    flex += [(b, "flames", i, FULL_VMS) for b, ids in (("C2", c2), ("C1", c1), ("A", a_ids), ("B", b_ids)) for i in ids]
    for b, tool, i, allowed in flex:
        v = min(allowed, key=lambda x: (load[x], FULL_VMS.index(x)))
        put(v, b, tool, [i], "flames5" if tool == "flames" else tool)
    order = {"mimics-v1": ("A", "C2", "C1", "B"), "mimics-v2": ("C2", "C1", "A", "B"), "mimics-v3": ("B", "C2", "C1", "A")}
    own = {"mimics-v1": "A", "mimics-v3": "B"}
    plans = {}
    for v in FULL_VMS:
        steps = []
        for b in order[v]:
            for tool in ("flames", "lstai", "wmhsynthseg", "mindglide", "samseg"):
                ids = [i for bb, t, i in work[v] if bb == b and t == tool]
                if ids:
                    steps.append({"tools": [tool], "inputs": ids, **({} if own.get(v) == b else {"wait_blocks": [b]})})
        prep = []
        if v == "mimics-v1":
            prep = [{"kind": "hdbet", "block": "A", "cohort": "wmh2017", "ids": a_ids, "finalize": a_ids}]
        if v == "mimics-v3":
            prep = [{"kind": "hdbet", "block": "B", "cohort": "dlbs", "ids": b_ids, "finalize": b_ids}]
        plans[v] = {"prep": prep, "steps": steps, "idle_wait_h": 12}
    return plans, dict(load)


def plan_cost(hours, spent):
    """Projected list-price spend of a plan: central (measured seconds) and high (x1.25), + set-up and fixed costs."""
    fixed = sum(PM.FIXED_USD.values()) + spent
    rate = {v: RATE_VM[VM[v][4]] for v in hours}
    central = sum((h + PM.SETUP_H) * rate[v] for v, h in hours.items()) + fixed
    high = sum((PM.SAFETY * h + PM.SETUP_H) * rate[v] for v, h in hours.items()) + fixed
    return {"usd_central": round(central, 2), "usd_high": round(high, 2),
            "wall_clock_h_central": round(max(hours.values()) + PM.SETUP_H, 1),
            "wall_clock_h_high": round(PM.SAFETY * max(hours.values()) + PM.SETUP_H, 1)}


def vm_guards(hours, spent):
    """max-hours per VM (projected hours x factor + set-up) so that every VM running to its guard keeps the total
    spend <= the cap; the largest factor in 1.0-1.6 that fits."""
    import math
    left = PM.CAP_USD - spent - sum(PM.FIXED_USD.values())
    for f in (1.6, 1.5, 1.4, 1.3, 1.25, 1.2, 1.1, 1.0):
        g = {k: math.ceil(h * f + PM.SETUP_H) for k, h in hours.items()}
        worst = sum(g[k] * RATE_VM[VM[k][4]] for k in g)
        if worst <= left:
            return {"factor": f, "max_hours": g, "worst_case_usd": round(worst + spent + sum(PM.FIXED_USD.values()), 2)}
    return None


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
    print(r.stdout.strip(), flush=True)
    if r.returncode != 0:
        print("STDERR:", "\n".join(x for x in r.stderr.splitlines() if "FutureWarning" not in x)[-3000:], flush=True)
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
    """Budget rule (PREREG 15.3) on the real three-VM plan: the first variant (full, then the registered reductions in
    order) whose HIGH projection is <= the cap; guards so that every VM running to its guard stays under the cap."""
    s = sets()
    sec = dict(PM.LEDGER_SECONDS)
    if a.pilot_json:
        sec.update({k: float(v) for k, v in json.load(open(a.pilot_json)).items()})
    chosen = None
    considered = []
    for label, kw in PM.VARIANTS:
        plans, hours = full_plans(s, kw, sec)
        c = plan_cost(hours, a.spent_usd)
        considered.append({"variant": label, **c})
        if c["usd_high"] <= PM.CAP_USD:
            chosen = (label, kw, plans, hours, c)
            break
    if not chosen:
        raise SystemExit(f"budget rule: nothing fits the cap: {json.dumps(considered)}")
    label, kw, plans, hours, c = chosen
    g = vm_guards(hours, a.spent_usd)
    if not g:
        raise SystemExit("no guard setting keeps the worst case under the cap: no launch")
    print(json.dumps({"variant": label, "projection": c, "considered": considered, "guards": g,
                      "projected_hours": {k: round(v, 1) for k, v in hours.items()},
                      "inputs_per_vm": {k: sum(len(st["inputs"]) for st in p["steps"]) for k, p in plans.items()}}, indent=1))
    if a.dry_run:
        return
    upload_code()
    d = tempfile.mkdtemp()
    json.dump({**kw, "variant": label, "vms": list(FULL_VMS), "seconds": sec, "spent_before_usd": a.spent_usd,
               "guards": g, "projection": c, "projected_hours": hours}, open(os.path.join(d, "variant.json"), "w"), indent=1)
    gs(f'cp "{os.path.join(d, "variant.json")}" {BK}/mimics/plans/variant.json --quiet')
    for name, plan in plans.items():
        launch(name, upload_plan(name, plan), g["max_hours"][name],
               f"Paper 1 addendum full run ({label}): {name} - "
               f"{', '.join(sorted({t for st in plan['steps'] for t in st['tools']}))}", False)


def cmd_status(a):
    print(sh(f"gcloud compute instances list --project={PROJECT} --filter=name~^mimics- --format=\"table(name,status,machineType.basename(),zone.basename())\"", check=False))
    for pre in ("flames/cohort", "lstai/cohort", "toolbench/cohort", "interruptions", "inputs"):
        out = sh(f"gcloud storage ls {BK}/mimics/{pre}/ --project={PROJECT}", check=False)
        names = [x.rsplit('/', 1)[-1] for x in out.split() if x.strip()]
        print(f"{pre}: {len(names)} files" + (f" {names}" if pre == "interruptions" else ""))


def expected_outputs(plan):
    """Bucket names every step of a plan must leave (LST-AI skips a blank T1: mslesseg_P49_T2)."""
    out = set()
    for st in plan["steps"]:
        for i in st["inputs"]:
            for t in st["tools"]:
                if t == "flames":
                    out |= {f"flames/cohort/{i}_f{k}_prob.nii.gz" for k in range(5)}
                elif t == "lstai":
                    if not i.startswith("mslesseg_P49_T2"):
                        out.add(f"lstai/cohort/{i}_lstai_prob.nii.gz")
                else:
                    out.add(f"toolbench/cohort/{i}_{t}_seg.nii.gz")
    return out


def listing():
    have = set()
    for pre in ("flames/cohort", "lstai/cohort", "toolbench/cohort"):
        out = sh(f"gcloud storage ls {BK}/mimics/{pre}/ --project={PROJECT}", check=False)
        have |= {x.split("/mimics/", 1)[1] for x in out.split() if "/mimics/" in x}
    return have


def running():
    out = sh(f"gcloud compute instances list --project={PROJECT} --filter=name~^mimics- --format=value(name)", check=False)
    return [x for x in out.split() if x]


def plans_in_bucket():
    vms = json.loads(gs(f"cat {BK}/mimics/plans/variant.json")).get("vms", [])
    out = {}
    for name in gs(f"ls {BK}/mimics/plans/").split():
        b = name.rsplit("/", 1)[-1][:-5]
        if any(b == v or b.startswith(v + "-r") for v in vms):
            out[b] = json.loads(gs(f"cat {name}"))
    return out


def spent_usd():
    """List-price spend of the addendum so far: cost records, plus VMs that left none (pre-empted or running),
    estimated from their plan creation time to their last interruption marker (or now) at their list rate."""
    import datetime
    total, notes = 0.0093, []                                     # the mirror job
    costs = {}
    for name in sh(f"gcloud storage ls {BK}/mimics/cost/ --project={PROJECT}", check=False).split():
        txt = gs(f"cat {name}")
        kv = dict(x.split("=", 1) for x in txt.strip().split(",")[1:] if "=" in x)
        costs[kv.get("run_id")] = float(kv.get("cost_usd_compute_estimate", 0) or 0)
    inter = {}
    for name in sh(f"gcloud storage ls {BK}/mimics/interruptions/ --project={PROJECT}", check=False).split():
        b = name.rsplit("/", 1)[-1]
        vm, ts = b.rsplit("-", 1)
        inter[vm] = max(inter.get(vm, 0), int(ts.split(".")[0]))
    for name in sh(f"gcloud storage ls {BK}/runs/ --project={PROJECT}", check=False).split():
        vm = name.rstrip("/").rsplit("/", 1)[-1]
        if not vm.startswith("mimics-"):
            continue
        if vm in costs:
            total += costs[vm]
            continue
        try:
            plan = json.loads(gs(f"cat {BK}/runs/{vm}/plan.json"))
        except SystemExit:
            continue
        t0 = datetime.datetime.strptime(plan["created_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc).timestamp()
        t1 = inter.get(vm) or datetime.datetime.now(datetime.timezone.utc).timestamp()
        est = max(0.0, (t1 - t0) / 3600.0) * float(plan["list_price"]["usd_per_hour"])
        total += est
        notes.append(f"{vm}: no cost record, estimated {est:.2f} USD")
    return round(total, 2), notes


def cmd_complete(a):
    have, run = listing(), running()
    missing = {}
    for vm, plan in plans_in_bucket().items():
        base = vm.rsplit("-r", 1)[0] if vm.rsplit("-", 1)[-1].startswith("r") else vm
        miss = sorted(expected_outputs(plan) - have)
        if miss:
            missing.setdefault(base, set()).update(miss)
    spent, notes = spent_usd()
    print(json.dumps({"running": run, "spent_usd_estimate": spent, "notes": notes,
                      "missing_by_vm": {k: len(v) for k, v in missing.items()}}, indent=1))
    if missing and not run:
        print("incomplete and nothing running: relaunch with  python research/paper_1/mimics/launch_mimics.py relaunch "
              + " ".join(sorted(missing)) + f"   (only within the {PM.CAP_USD} USD cap)")
    return 0 if not missing and not run else 1


def cmd_relaunch(a):
    """Relaunch pre-empted VMs with their identical plan (drivers skip finished outputs), only within the cap."""
    spent, notes = spent_usd()
    plans = plans_in_bucket()
    run = running()
    for vm in a.vms:
        if any(r == vm or r.startswith(vm + "-r") for r in run):
            print(f"{vm}: still running, not relaunched")
            continue
        rk = VM[vm][4]
        rate = RATE_VM[rk]
        left = PM.CAP_USD - spent - sum(PM.FIXED_USD.values())
        hours = int(min(a.max_hours, left / rate))
        if hours < 1:
            raise SystemExit(f"cap reached (spent {spent} USD): no relaunch")
        k = 1 + sum(1 for p in plans if p.startswith(vm + "-r"))
        name = f"{vm}-r{k}"
        VM[name] = VM[vm]
        launch(name, upload_plan(name, plans[vm]), hours, f"Paper 1 addendum: relaunch {k} of {vm} after a pre-emption "
               f"(same plan; finished outputs are skipped)", a.dry_run)
        spent += hours * rate


def cmd_evaluate(a):
    """Final evaluation: refuses while any mimics VM runs or outputs are missing; then one Spot VM runs GR, G3, the
    frozen evaluation and G2; results are downloaded into research/paper_1/mimics/results/."""
    import time
    if cmd_complete(a) != 0 and not a.allow_incomplete:
        raise SystemExit("not complete: see above")
    commit = sh("git rev-parse HEAD").strip()
    if sh("git status --porcelain --untracked-files=no -- research/paper_1 research/paper_f backend/app").strip():
        raise SystemExit("tracked evaluation code has uncommitted changes: commit first")
    d = tempfile.mkdtemp()
    tar = os.path.join(d, f"{commit}.tar.gz")
    sh(f'git archive --format=tar.gz -o "{tar}" {commit} backend/app backend/data/msmask research/paper_1 research/paper_f')
    gs(f'cp "{tar}" {BK}/mimics/evalcode/{commit}.tar.gz --quiet')
    name = f"mimics-eval-{commit[:7]}"
    cmd = [sys.executable, os.path.join(ROOT, "research", "cloud", "launch_vm.py"), "--name", name, "--machine-type",
           "c2d-standard-8", "--disk-gb", "60", "--spot", "--startup", os.path.join(ROOT, "research", "cloud", "vm_mimics_eval.sh"),
           "--paper", "1", "--max-hours", "8", "--purpose", "Paper 1 addendum: frozen final evaluation (GR, G3, run once, G2)",
           "--meta", f"evalcode=mimics/evalcode/{commit}.tar.gz", f"commit={commit}", "workers=8", f"shutdown-script={SHUTDOWN}"]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    print(r.stdout[-2000:])
    if r.returncode != 0:
        print("\n".join(x for x in r.stderr.splitlines() if "FutureWarning" not in x)[-3000:])
        raise SystemExit("evaluation VM launch failed")
    print(f"waiting for {BK}/mimics/results/{name}/DONE (polls every 5 min) ...", flush=True)
    done = False
    while True:
        time.sleep(300)
        done = subprocess.run(f"gcloud storage ls {BK}/mimics/results/{name}/DONE --project={PROJECT}", shell=True,
                              capture_output=True, text=True).returncode == 0
        if done or name not in running():
            break
    if not done:
        raise SystemExit(f"{name} ended without results (pre-empted?): run this command again")
    out = os.path.join(HERE, "results")
    os.makedirs(out, exist_ok=True)
    gs(f'cp -r "{BK}/mimics/results/{name}/*" "{out}" --quiet')
    for f in ("gr_registration.txt", "g3_structural_check.txt"):
        p = os.path.join(out, f)
        if os.path.exists(p):
            print(open(p).read().strip().splitlines()[-1])
    s_ = json.load(open(os.path.join(out, "summary.json")))
    print("G1:", json.dumps(s_["gate_G1"]))
    print("G2 passed:", json.load(open(os.path.join(out, "independent_check.json"))).get("passed"))
    print(f"results in {out} (tables.md, summary.json, per_unit.csv, lesions.csv)")
    return 0


def cmd_timings(a):
    """Pilot seconds per step (and per data type) for the budget rule, from the pilot manifests (timings only)."""
    kind = lambda i: "_wmh" if i.startswith("wmh_") else ("_dlbs" if i.startswith("sub-") and "_th" not in i else "")  # noqa: E731
    acc = {}

    def add(key, v):
        if v is not None:
            acc.setdefault(key, []).append(float(v))
    prep = json.loads(gs(f"cat {BK}/mimics/manifests/prep-{a.run}.json"))
    for i, r in prep["records"].items():
        if r.get("seconds_hdbet_flair") is not None:
            add("hdbet" + kind(i), r["seconds_hdbet_flair"])
            add("hdbet" + kind(i), r.get("seconds_hdbet_t1"))
    fl = json.loads(gs(f"cat {BK}/mimics/flames/manifests/{a.run}-s0.json"))
    per = {}
    for c in fl["cases"]:
        per[c["case"]] = per.get(c["case"], 0.0) + c["seconds"]
    for i, v in per.items():
        add("flames5" + kind(i), v)
    ls = json.loads(gs(f"cat {BK}/mimics/lstai/manifests/{a.run}-s0.json"))
    for c in ls["cases"]:
        add("lstai" + kind(c["case"]), c["seconds"])
    tb = json.loads(gs(f"cat {BK}/mimics/toolbench/manifests/{a.run}-s0.json"))
    peaks = {}
    for c in tb["cases"]:
        add(c["tool"] + kind(c["case"]), c["seconds"])
        peaks[f"{c['tool']}{kind(c['case'])}"] = max(peaks.get(f"{c['tool']}{kind(c['case'])}", 0), c.get("peak_mem_used_gb") or 0)
    out = {k: round(sum(v) / len(v), 1) for k, v in acc.items()}
    errors = {"flames": fl.get("errors"), "lstai": ls.get("errors"), "toolbench": tb.get("errors"), "prep": prep.get("errors")}
    print(json.dumps({"seconds": out, "peak_mem_gb": peaks, "errors": errors}, indent=1))
    if a.out:
        json.dump(out, open(a.out, "w"), indent=1)
    return 0


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
    sub.add_parser("complete")
    tm = sub.add_parser("timings")
    tm.add_argument("--run", default="mimics-pilot")
    tm.add_argument("--out")
    rl = sub.add_parser("relaunch")
    rl.add_argument("vms", nargs="+")
    rl.add_argument("--max-hours", type=int, default=72)
    rl.add_argument("--dry-run", action="store_true")
    ev = sub.add_parser("evaluate")
    ev.add_argument("--allow-incomplete", action="store_true")
    c = sub.add_parser("check")
    c.add_argument("scratch")
    c.add_argument("--inputs", nargs="+", required=True)
    c.add_argument("--tools", nargs="+", default=["wmhsynthseg", "mindglide", "samseg"])
    a = ap.parse_args()
    sys.exit({"pilot": cmd_pilot, "full": cmd_full, "status": cmd_status, "check": cmd_check, "complete": cmd_complete,
              "relaunch": cmd_relaunch, "evaluate": cmd_evaluate, "timings": cmd_timings}[a.cmd](a) or 0)


if __name__ == "__main__":
    main()
