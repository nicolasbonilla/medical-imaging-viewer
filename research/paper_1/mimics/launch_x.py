"""Paper 1 addendum 2 (PREREG-addendum-2026-11-age-faithful-deterministic.md section 7): pilot, budget rule, full runs,
status, relaunch after a pre-emption, the single evaluation and the download of its results.
Project mstool-research only: every gcloud call carries --project=mstool-research and the isolated configuration
CLOUDSDK_CONFIG=C:/Users/Nicolas/.gcloud-mstool (launch_vm.py sets it too). Spot VMs named mimics-x*, self-deleting.
Hard cap 25 USD for the whole addendum 2 (audit-log spend of the mimics-x* VMs, list prices).

    python research/paper_1/mimics/launch_x.py pilot [--dry-run]
    python research/paper_1/mimics/launch_x.py timings --out <scratch>/xpilot.json
    python research/paper_1/mimics/launch_x.py full --pilot-json <scratch>/xpilot.json [--dry-run]
    python research/paper_1/mimics/launch_x.py tick        # idempotent: relaunch pre-empted VMs, then evaluate, then fetch
    python research/paper_1/mimics/launch_x.py status | complete | spent | evaluate | fetch | relaunch mimics-x2
Code is always taken from the committed HEAD (git archive), never from the working tree.
"""
import argparse
import datetime
import json
import math
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
os.environ["CLOUDSDK_CONFIG"] = r"C:\Users\Nicolas\.gcloud-mstool"
PROJECT = "mstool-research"
BK = "gs://mstool-research-data"
CAP_USD = 25.0
EVAL_RESERVE_USD = 1.5                # the evaluation VM (c2d-standard-8 Spot, <= 10 h guard) and its possible rerun
SAFETY, SETUP_H = 1.25, 1.0       # set-up per VM: the pilot measured 55 min (envs, 84 GB of images, archives)
SETS = json.load(open(os.path.join(HERE, "analysis_sets.json")))
X2 = json.load(open(os.path.join(HERE, "analysis_sets_addendum2.json")))
TOOLS = ["flames", "lstai", "mindglide", "wmhsynthseg", "samseg"]
CODE_FILES = ["research/paper_1/mimics/" + f for f in ("mimics_vm.py", "mimics_prep.py", "simulate_thick.py", "thick_slice.py",
                                                         "analysis_sets.json", "analysis_sets_addendum2.json", "x_jobs.py",
                                                         "faithful_rule.py", "evaluate_mimics.py")] + \
             ["research/paper_1/hc_core.py", "research/paper_f/metrics.py", "research/paper_f/flames_inputs.json",
              "research/paper_1/controls_inputs.json", "backend/data/msmask/sub-mni152_space-mni_msmask.nii.gz"] + \
             ["research/cloud/" + f for f in ("flames_ensemble_driver.py", "lstai_driver.py", "toolbench_driver.py", "job_common.py")]
SHUTDOWN = ('#!/bin/bash\nMD=http://metadata/computeMetadata/v1/instance\n'
            'P=$(curl -sf -H "Metadata-Flavor: Google" $MD/preempted)\nN=$(curl -sf -H "Metadata-Flavor: Google" $MD/name)\n'
            'echo "$N preempted=$P $(date -u +%Y-%m-%dT%H:%M:%SZ)" | '
            'gcloud storage cp - gs://mstool-research-data/mimics/interruptions/$N-$(date -u +%s).txt --quiet\n')
# name: (machine type, disk GB, swap GB, needs, Spot list USD/h incl. disk - used only before runs/<vm>/plan.json exists)
# Global quota 12 vCPUs (three 4-vCPU VMs); regional SSD quota 250 GB: 70 + 90 + 85 = 245 GB.
VM = {"mimics-xp": ("c2d-highmem-4", 130, 16, "hdbet flames lstai mindglide fs cdata greedy", 0.1300),
      "mimics-xt": ("c2d-standard-2", 30, 2, "greedy", 0.0500),   # amendment 1: Linux re-check of the seeded registration
      "mimics-x1": ("c2d-standard-4", 70, 8, "hdbet flames lstai greedy", 0.0928),
      "mimics-x2": ("c2d-highmem-4", 90, 16, "hdbet flames mindglide fs", 0.1245),
      "mimics-x3": ("c2d-standard-4", 85, 8, "hdbet flames fs cdata greedy", 0.0950)}
FULL = ("mimics-x1", "mimics-x2", "mimics-x3")
EVAL_MACHINE, EVAL_DISK, EVAL_H, EVAL_RATE = "c2d-standard-8", 80, 10, 0.19


def sh(cmd, check=True, timeout=600):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise SystemExit(f"FAILED: {cmd}\n{r.stderr[-1500:]}")
    return r.stdout


def gs(args, check=True):
    return sh(f"gcloud storage {args} --project={PROJECT}", check=check)


def ls(prefix):
    out = sh(f'gcloud storage ls "{BK}/{prefix}" --project={PROJECT}', check=False)
    return {x.split(f"{BK}/", 1)[1] for x in out.split() if x.startswith(BK)}


def head_commit():
    if sh("git status --porcelain --untracked-files=no -- research backend/data/msmask", check=True).strip():
        raise SystemExit("tracked research code has uncommitted changes: commit (and push) first")
    return sh("git rev-parse HEAD").strip()


# ---------------------------------------------------------------------------------------------- ids and keys
def b2_ids():
    return list(X2["B2_sample"]["ids"])


def all_reg_ids():
    return sorted(SETS["A_wmh2017"]) + list(SETS["B1_sample"]["ids"]) + b2_ids()


def ss_keys(block):
    k = X2["synthseg_keys"][block]
    return [k] if block == "atlas" else list(k.values())


# ---------------------------------------------------------------------------------------------- plans
def pilot_plan():
    p = X2["pilot"]
    keys = X2["synthseg_keys"]
    pre = [keys[b][i] for b in ("A", "B", "C1", "C2") for i in p["synthseg"][b]] + [keys["atlas"]]
    post = [keys["B2"][i] for i in p["synthseg"]["B2"]]
    return {"prep": [{"kind": "hdbet", "block": "B2", "cohort": "dlbs", "ids": p["B2_tools"]}],
            "steps": [{"tools": TOOLS, "inputs": p["B2_tools"]}],
            "synthseg": {"pre": pre, "post": post}, "regtest": {"ids": p["regtest"]},
            "overlays": {"keys": pre + post}, "idle_wait_h": 1}


def sec_of(sec, step):
    return float(sec[step])


def full_plans(sec, have):
    """Three Spot VMs. Fixed: LST-AI and registration run a on x1; WMH-SynthSeg and MindGlide on x2 (32 GB);
    SynthSeg of C1 (needs the MS archives) and registration run b on x3. Flexible, least-loaded first: HD-BET of B2
    (every VM), SAMSEG and the other SynthSeg items (x2, x3), FLAMeS (every VM). Items already in the bucket are left out."""
    ids = b2_ids()
    load = {v: 0.0 for v in FULL}
    work = {v: {"prep": [], "tools": {t: [] for t in TOOLS}, "ss_pre": [], "ss_post": [], "register": None} for v in FULL}
    reg_h = len(all_reg_ids()) * sec_of(sec, "greedy1") / 4 / 3600 + 0.2
    work["mimics-x1"]["register"], load["mimics-x1"] = "detreg-a", load["mimics-x1"] + reg_h
    work["mimics-x3"]["register"], load["mimics-x3"] = "detreg-b", load["mimics-x3"] + reg_h

    def done_tool(t, i):
        if t == "flames":
            return all(f"mimics/flames/cohort/{i}_f{k}_prob.nii.gz" in have for k in range(5))
        if t == "lstai":
            return f"mimics/lstai/cohort/{i}_lstai_prob.nii.gz" in have
        return f"mimics/toolbench/cohort/{i}_{t}_seg.nii.gz" in have

    def put(v, kind, item, hours, tool=None):
        if tool:
            work[v]["tools"][tool].append(item)
        else:
            work[v][kind].append(item)
        load[v] += hours
    for i in ids:
        if not done_tool("lstai", i):
            put("mimics-x1", "tools", i, sec_of(sec, "lstai") / 3600, "lstai")
        for t in ("wmhsynthseg", "mindglide"):
            if not done_tool(t, i):
                put("mimics-x2", "tools", i, sec_of(sec, t) / 3600, t)
    ss_done = {x.rsplit("/", 1)[1][:-len("_synthseg.nii.gz")] for x in have if x.endswith("_synthseg.nii.gz")}
    for k in ss_keys("C1"):
        if k not in ss_done:
            put("mimics-x3", "ss_pre", k, sec_of(sec, "synthseg") / 3600)
    prep_done = {i for i in ids if f"mimics/inputs/{i}_T1brainmask.nii.gz" in have}
    least = lambda allowed: min(allowed, key=lambda v: (load[v], FULL.index(v)))  # noqa: E731
    for i in ids:
        if i not in prep_done:
            put(least(FULL), "prep", i, sec_of(sec, "hdbet_b2") / 3600)
    for i in ids:
        if not done_tool("samseg", i):
            put(least(("mimics-x2", "mimics-x3")), "tools", i, sec_of(sec, "samseg") / 3600, "samseg")
    for b in ("A", "B", "C2", "atlas"):
        for k in ss_keys(b):
            if k not in ss_done:
                put(least(("mimics-x2", "mimics-x3")), "ss_pre", k, sec_of(sec, "synthseg") / 3600)
    for k in ss_keys("B2"):
        if k not in ss_done:
            put(least(("mimics-x2", "mimics-x3")), "ss_post", k, sec_of(sec, "synthseg") / 3600)
    for i in ids:
        if not done_tool("flames", i):
            put(least(FULL), "tools", i, sec_of(sec, "flames5") / 3600, "flames")
    plans = {}
    for v in FULL:
        w = work[v]
        plans[v] = {"prep": [{"kind": "hdbet", "block": "B2", "cohort": "dlbs", "ids": w["prep"], "finalize": ids}],
                    "steps": [{"tools": [t], "inputs": w["tools"][t], "wait_blocks": ["B2"]} for t in TOOLS if w["tools"][t]],
                    "synthseg": {"pre": w["ss_pre"], "post": w["ss_post"], "post_wait_blocks": ["B2"]},
                    "idle_wait_h": 30}
        if w["register"]:
            plans[v]["register"] = {"run": w["register"], "ids": all_reg_ids(), "workers": 4, "wait_blocks": ["B2"],
                                    "idle_wait_h": 30}
    return plans, load


def projection(load, spent, rates):
    central = sum((h + SETUP_H) * rates[v] for v, h in load.items()) + spent + EVAL_RESERVE_USD
    high = sum((SAFETY * h + SETUP_H) * rates[v] for v, h in load.items()) + spent + EVAL_RESERVE_USD
    return {"usd_central": round(central, 2), "usd_high": round(high, 2),
            "wall_clock_h_central": round(max(load.values()) + SETUP_H, 1),
            "wall_clock_h_high": round(SAFETY * max(load.values()) + SETUP_H, 1)}


def guards(load, spent, rates):
    left = CAP_USD - spent - EVAL_RESERVE_USD
    for f in (1.8, 1.6, 1.5, 1.4, 1.3, 1.25, 1.2):
        g = {v: math.ceil(h * f + SETUP_H + 1) for v, h in load.items()}
        worst = sum(g[v] * rates[v] for v in g)
        if worst <= left:
            return {"factor": f, "max_hours": g, "worst_case_usd": round(worst + spent + EVAL_RESERVE_USD, 2)}
    return None


# ---------------------------------------------------------------------------------------------- cloud actions
def upload_code(commit):
    """The committed files (git archive of HEAD), flat, to mimics/xcode/<commit>/."""
    d = tempfile.mkdtemp()
    tar = os.path.join(d, "code.tar")
    sh(f'git archive --format=tar -o "{tar}" {commit} ' + " ".join(CODE_FILES))
    flat = os.path.join(d, "flat")
    os.makedirs(flat)
    with tarfile.open(tar) as t:
        for m in t.getmembers():
            if m.isfile():
                with t.extractfile(m) as src, open(os.path.join(flat, os.path.basename(m.name)), "wb") as dst:
                    shutil.copyfileobj(src, dst)
    gs(f'cp "{flat}/*" {BK}/mimics/xcode/{commit[:12]}/ --quiet')
    return f"mimics/xcode/{commit[:12]}"


def upload_plan(name, plan):
    d = tempfile.mkdtemp()
    p = os.path.join(d, f"{name}.json")
    json.dump(plan, open(p, "w"), indent=1)
    gs(f'cp "{p}" {BK}/mimics/plans/{name}.json --quiet')
    return f"mimics/plans/{name}.json"


def launch(name, spec, plan_path, code, max_hours, purpose, startup="vm_mimics_x.sh", meta=(), dry=False):
    mtype, disk, swap, needs, _ = spec
    cmd = [sys.executable, os.path.join(ROOT, "research", "cloud", "launch_vm.py"), "--name", name, "--machine-type", mtype,
           "--disk-gb", str(disk), "--spot", "--startup", os.path.join(ROOT, "research", "cloud", startup),
           "--paper", "1", "--max-hours", str(max_hours), "--purpose", purpose,
           "--meta", f"shutdown-script={SHUTDOWN}", *meta]
    if plan_path:
        cmd += [f"plan={plan_path}", f"code={code}", f"needs={needs}", f"swap-gb={swap}"]
    print(f"launch {name} ({mtype}, {disk} GB, max {max_hours} h)", flush=True)
    if dry:
        return
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    print(r.stdout.strip()[-1500:], flush=True)
    if r.returncode != 0:
        print("STDERR:", "\n".join(x for x in r.stderr.splitlines() if "FutureWarning" not in x)[-3000:], flush=True)
        raise SystemExit(f"launch of {name} failed")


def running():
    out = sh(f"gcloud compute instances list --project={PROJECT} --filter=name~^mimics-x --format=value(name)")
    return [x for x in out.split() if x]


def rate_of(vm, cache={}):
    if vm not in cache:
        try:
            cache[vm] = float(json.loads(gs(f"cat {BK}/runs/{vm}/plan.json"))["list_price"]["usd_per_hour"])
        except (SystemExit, KeyError, ValueError):
            base = vm.split("-r")[0]
            cache[vm] = VM.get(base, ("", 0, 0, "", EVAL_RATE))[4]
    return cache[vm]


def audit():
    """(start, stop, preempted) per mimics-x* VM from the project's audit log."""
    q = ('resource.type="gce_instance" AND protoPayload.resourceName:"instances/mimics-x" AND '
         '(protoPayload.methodName:"insert" OR protoPayload.methodName:"preempted" OR protoPayload.methodName:"delete")')
    exe = shutil.which("gcloud") or shutil.which("gcloud.cmd") or "gcloud"
    r = subprocess.run([exe, "logging", "read", q, f"--project={PROJECT}", "--freshness=30d", "--limit=2000",
                        "--format=value(timestamp,protoPayload.methodName,protoPayload.resourceName)"],
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise SystemExit(f"audit log unreadable: {r.stderr[-300:]} (a failed read never counts as zero spend)")
    start, stop, pre = {}, {}, set()
    for line in r.stdout.splitlines():
        p = line.strip().split("\t")
        if len(p) < 3:
            continue
        t = datetime.datetime.fromisoformat(p[0].replace("Z", "+00:00")).timestamp()
        vm = p[2].rsplit("/", 1)[-1]
        if "insert" in p[1]:
            start[vm] = min(start.get(vm, t), t)
        else:
            stop[vm] = min(stop.get(vm, t), t)
            if "preempted" in p[1]:
                pre.add(vm)
    return start, stop, pre


def spent_usd():
    """List-price spend of addendum 2 from the project's audit log: every mimics-x* VM from its insert to its first
    pre-emption or deletion (a VM still running counts to now)."""
    start, stop, _ = audit()
    live = set(running())
    now = datetime.datetime.now(datetime.timezone.utc).timestamp()
    total, per = 0.0, {}
    for vm, t0 in start.items():
        t1 = stop.get(vm) or (now if vm in live else t0)
        per[vm] = round(max(0.0, t1 - t0) / 3600.0 * rate_of(vm), 3)
        total += per[vm]
    return round(total, 2), per


def expected(plan):
    out = set()
    for p in plan.get("prep", []):
        for i in p["ids"]:
            out |= {f"mimics/inputs/{i}_{s}.nii.gz" for s in ("FLAIR", "T1", "brainmask", "T1brainmask")}
    for st in plan.get("steps", []):
        for i in st["inputs"]:
            for t in st["tools"]:
                if t == "flames":
                    out |= {f"mimics/flames/cohort/{i}_f{k}_prob.nii.gz" for k in range(5)}
                elif t == "lstai":
                    out.add(f"mimics/lstai/cohort/{i}_lstai_prob.nii.gz")
                else:
                    out.add(f"mimics/toolbench/cohort/{i}_{t}_seg.nii.gz")
    ss = plan.get("synthseg") or {}
    out |= {f"mimics/anat/synthseg/{k}_synthseg.nii.gz" for k in ss.get("pre", []) + ss.get("post", [])}
    if plan.get("register"):
        out |= {f"mimics/registration/{plan['register']['run']}/registration/{i}.mat" for i in plan["register"]["ids"]}
    return out


def listing():
    have = set()
    for pre in ("mimics/flames/cohort/", "mimics/lstai/cohort/", "mimics/toolbench/cohort/", "mimics/inputs/",
                "mimics/anat/synthseg/", "mimics/registration/detreg-a/registration/", "mimics/registration/detreg-b/registration/"):
        have |= ls(pre)
    return have


def plans_in_bucket():
    out = {}
    for v in FULL:
        try:
            out[v] = json.loads(gs(f"cat {BK}/mimics/plans/{v}.json"))
        except SystemExit:
            pass
    return out


def missing_by_vm(have=None):
    have = listing() if have is None else have
    return {v: sorted(expected(p) - have) for v, p in plans_in_bucket().items()}


# ---------------------------------------------------------------------------------------------- commands
def cmd_pilot(a):
    plan = pilot_plan()
    if a.dry_run:
        print(json.dumps(plan, indent=1))
        return
    commit = head_commit()
    code = upload_code(commit)
    launch("mimics-xp", VM["mimics-xp"], upload_plan("mimics-xp", plan), code, 6,
           "Paper 1 addendum 2 pilot (Spot): HD-BET + six tools on 2 Dallas 21-49 participants; SynthSeg on 2 scans per "
           "data type + atlas; single-thread registration twice on 3 subjects; SynthSeg overlays", dry=False)


def cmd_regtest(a):
    """Amendment 1: the registration pre-check again, on Linux, with the fixed seed (no other work)."""
    commit = head_commit()
    code = upload_code(commit)
    launch("mimics-xt", VM["mimics-xt"], upload_plan("mimics-xt", {"prep": [], "steps": [],
                                                                  "regtest": {"ids": X2["pilot"]["regtest"]}}), code, 2,
           "Paper 1 addendum 2, amendment 1: single-thread seeded registration twice on 3 subjects (pre-check)")


def cmd_timings(a):
    acc = {}

    def add(k, v):
        if v is not None:
            acc.setdefault(k, []).append(float(v))
    prep = json.loads(gs(f"cat {BK}/mimics/manifests/prep-{a.run}.json"))
    for i, r in prep["records"].items():
        if r.get("seconds_hdbet_flair") is not None:
            add("hdbet_b2", float(r["seconds_hdbet_flair"]) + float(r.get("seconds_hdbet_t1") or 0))
    fl = json.loads(gs(f"cat {BK}/mimics/flames/manifests/{a.run}-t-s0.json"))
    per = {}
    for c in fl["cases"]:
        per[c["case"]] = per.get(c["case"], 0.0) + c["seconds"]
    for v in per.values():
        add("flames5", v)
    for c in json.loads(gs(f"cat {BK}/mimics/lstai/manifests/{a.run}-t-s0.json"))["cases"]:
        add("lstai", c["seconds"])
    peaks = {}
    tb = json.loads(gs(f"cat {BK}/mimics/toolbench/manifests/{a.run}-t-s0.json"))
    for c in tb["cases"]:
        add(c["tool"], c["seconds"])
        peaks[c["tool"]] = max(peaks.get(c["tool"], 0), c.get("peak_mem_used_gb") or 0)
    errors = {"toolbench": tb.get("errors"), "prep": prep.get("errors")}
    for ph in ("pre", "post"):
        m = json.loads(gs(f"cat {BK}/mimics/anat/manifests/{a.run}-{ph}.json"))
        for it in m["items"]:
            add("synthseg", it["seconds"])
            add(f"synthseg_{it['block']}", it["seconds"])
            peaks["synthseg"] = max(peaks.get("synthseg", 0), it.get("peak_mem_used_gb") or 0)
        errors[f"synthseg_{ph}"] = m.get("errors")
    rt = json.loads(gs(f"cat {BK}/mimics/registration/pilot-regtest/result-{a.run}.json"))
    for r in rt["records"].values():
        add("greedy1", r["rep1"]["seconds"])
        add("greedy1", r["rep2"]["seconds"])
    out = {k: round(sum(v) / len(v), 1) for k, v in acc.items()}
    print(json.dumps({"seconds": out, "peak_mem_gb": peaks, "errors": errors,
                      "regtest_identical": {k: v["identical"] for k, v in rt["records"].items()}}, indent=1))
    if a.out:
        json.dump(out, open(a.out, "w"), indent=1)


def cmd_full(a):
    sec = json.load(open(a.pilot_json))
    spent, _ = spent_usd()
    have = listing()
    plans, load = full_plans(sec, have)
    rates = {v: VM[v][4] for v in FULL}
    proj = projection(load, spent, rates)
    g = guards(load, spent, rates)
    print(json.dumps({"spent_usd": spent, "projected_hours": {k: round(v, 1) for k, v in load.items()}, "projection": proj,
                      "guards": g, "items": {v: {"prep": len(p["prep"][0]["ids"]), "steps": {s["tools"][0]: len(s["inputs"])
                                                                                            for s in p["steps"]},
                                                 "synthseg": len(p["synthseg"]["pre"]) + len(p["synthseg"]["post"]),
                                                 "register": (p.get("register") or {}).get("run")}
                                             for v, p in plans.items()}}, indent=1))
    if proj["usd_high"] > CAP_USD or not g:
        raise SystemExit(f"budget rule: the projection ({proj['usd_high']} USD high) or the guards do not fit the "
                         f"{CAP_USD} USD cap: no launch (owner decision)")
    if a.dry_run:
        return
    if running():
        raise SystemExit(f"mimics-x VMs still running: {running()}")
    commit = head_commit()
    code = upload_code(commit)
    d = tempfile.mkdtemp()
    json.dump({"commit": commit, "seconds": sec, "spent_before_usd": spent, "projection": proj, "guards": g,
               "projected_hours": load}, open(os.path.join(d, "xvariant.json"), "w"), indent=1)
    gs(f'cp "{os.path.join(d, "xvariant.json")}" {BK}/mimics/plans/xvariant.json --quiet')
    for v in FULL:
        launch(v, VM[v], upload_plan(v, plans[v]), code, g["max_hours"][v],
               f"Paper 1 addendum 2 full run: {v}")


def cmd_status(a):
    print(sh(f"gcloud compute instances list --project={PROJECT} --filter=name~^mimics-x "
             f"--format=\"table(name,status,machineType.basename(),zone.basename())\"", check=False))
    have = listing()
    ids = b2_ids()
    print(json.dumps({"b2_prepared": sum(f"mimics/inputs/{i}_T1brainmask.nii.gz" in have for i in ids),
                      "b2_done_marker": bool(ls("mimics/inputs/_done_B2.json")),
                      "b2_tools": {t: sum((f"mimics/flames/cohort/{i}_f4_prob.nii.gz" if t == "flames" else
                                           f"mimics/lstai/cohort/{i}_lstai_prob.nii.gz" if t == "lstai" else
                                           f"mimics/toolbench/cohort/{i}_{t}_seg.nii.gz") in have for i in ids) for t in TOOLS},
                      "synthseg": sum(x.endswith("_synthseg.nii.gz") for x in have),
                      "detreg_a": sum(x.startswith("mimics/registration/detreg-a/") for x in have),
                      "detreg_b": sum(x.startswith("mimics/registration/detreg-b/") for x in have),
                      "interruptions": sorted(x.rsplit("/", 1)[1] for x in ls("mimics/interruptions/") if "mimics-x" in x)},
                     indent=1))


def cmd_spent(a):
    total, per = spent_usd()
    print(json.dumps({"spent_usd": total, "cap_usd": CAP_USD, "per_vm": per}, indent=1))


def cmd_complete(a):
    miss = missing_by_vm()
    run = running()
    print(json.dumps({"running": run, "missing_by_vm": {k: len(v) for k, v in miss.items()},
                      "examples": {k: v[:3] for k, v in miss.items() if v}}, indent=1))
    return 0 if not any(miss.values()) and not [r for r in run if not r.startswith("mimics-xe")] else 1


def relaunch(vm, spent, run, dry=False):
    if any(r == vm or r.startswith(vm + "-r") for r in run):
        print(f"{vm}: still running, not relaunched")
        return 0.0
    plan = plans_in_bucket()[vm]
    rate = VM[vm][4]
    left = CAP_USD - spent - EVAL_RESERVE_USD
    hours = int(min(72, left / rate))
    if hours < 2:
        raise SystemExit(f"cap reached (spent {spent} USD): no relaunch")
    k = 1 + sum(1 for x in ls("runs/") if x.rstrip("/").rsplit("/", 1)[-1].startswith(vm + "-r"))
    xv = json.loads(gs(f"cat {BK}/mimics/plans/xvariant.json"))
    code = f"mimics/xcode/{xv['commit'][:12]}"
    hours = min(hours, int(xv["guards"]["max_hours"][vm]))
    if not plan:
        raise SystemExit(f"no plan for {vm} in the bucket")
    launch(f"{vm}-r{k}", VM[vm], f"mimics/plans/{vm}.json", code, hours,
           f"Paper 1 addendum 2: relaunch {k} of {vm} after a pre-emption (same plan; finished outputs are skipped)", dry=dry)
    return hours * rate


def cmd_relaunch(a):
    spent, _ = spent_usd()
    run = running()
    for vm in a.vms:
        spent += relaunch(vm, spent, run, a.dry_run)


def eval_name(commit):
    return f"mimics-xe-{commit[:7]}"


def xeval():
    """The evaluation record (mimics/plans/xeval.json): which commit is evaluated, under which VM name, how often it
    was launched. The evaluation is tied to this record, never to whatever HEAD is later."""
    try:
        return json.loads(gs(f"cat {BK}/mimics/plans/xeval.json"))
    except SystemExit:
        return None


def cmd_evaluate(a):
    if cmd_complete(a) != 0:
        raise SystemExit("not complete: see above")
    rec = xeval()
    if rec:
        name, commit = rec["name"], rec["commit"]
        if ls(f"mimics/results/{name}/DONE"):
            raise SystemExit(f"{name} already finished: run fetch (the evaluation runs once)")
        if name in running():
            raise SystemExit(f"{name} is running")
        if rec["launches"] >= 2:
            raise SystemExit(f"{name} was launched {rec['launches']} times without results: read mimics/logs/{name}.log "
                             "(stop and report; a code fix is a logged deviation)")
    else:
        commit = head_commit()
        name = eval_name(commit)
        d = tempfile.mkdtemp()
        tar = os.path.join(d, f"{commit}.tar.gz")
        sh(f'git archive --format=tar.gz -o "{tar}" {commit} backend/app backend/data/msmask research/paper_1 research/paper_f')
        gs(f'cp "{tar}" {BK}/mimics/evalcode/{commit}.tar.gz --quiet')
        rec = {"name": name, "commit": commit, "launches": 0}
    spent, _ = spent_usd()
    if spent + EVAL_H * EVAL_RATE > CAP_USD:
        raise SystemExit(f"cap: spent {spent} USD + evaluation guard {EVAL_H * EVAL_RATE:.2f} > {CAP_USD}")
    rec["launches"] += 1
    d = tempfile.mkdtemp()
    json.dump(rec, open(os.path.join(d, "xeval.json"), "w"), indent=1)
    gs(f'cp "{os.path.join(d, "xeval.json")}" {BK}/mimics/plans/xeval.json --quiet')
    launch(name, (EVAL_MACHINE, EVAL_DISK, 0, "", EVAL_RATE), None, None, EVAL_H,
           "Paper 1 addendum 2: the single evaluation (DG, run 3, Dallas 21-49, GS, faithful rule, summary)",
           startup="vm_mimics_eval_x.sh", meta=(f"evalcode=mimics/evalcode/{commit}.tar.gz", f"commit={commit}", "workers=8"))
    print(f"results will appear in {BK}/mimics/results/{name}/ ; then: python research/paper_1/mimics/launch_x.py fetch")


def cmd_fetch(a):
    rec = xeval()
    if not rec or not ls(f"mimics/results/{rec['name']}/DONE"):
        raise SystemExit(f"no results yet ({rec and rec['name']})")
    out = os.path.join(HERE, "results_addendum")
    os.makedirs(out, exist_ok=True)
    gs(f'cp -r "{BK}/mimics/results/{rec["name"]}/*" "{out}" --quiet')
    print(open(os.path.join(out, "SUMMARY.md"), encoding="utf-8").read()[:3000])
    print(f"results of {rec['name']} (code {rec['commit'][:7]}) in {out}")


def cmd_tick(a):
    """One idempotent step: relaunch work VMs whose last instance was PRE-EMPTED (within the cap), evaluate when
    everything is in the bucket, fetch when the evaluation is done. A VM that ended without a pre-emption and left
    work missing is reported, never relaunched automatically (a failing item would loop)."""
    run = running()
    rec = xeval()
    if rec and ls(f"mimics/results/{rec['name']}/DONE"):
        return cmd_fetch(a)
    if rec and rec["name"] in run:
        print(f"evaluation {rec['name']} running")
        return
    miss = missing_by_vm()
    spent, _ = spent_usd()
    start, _, pre = audit()
    print(json.dumps({"running": run, "spent_usd": spent, "missing": {k: len(v) for k, v in miss.items()}}, indent=1))
    for vm, m in miss.items():
        if not m or any(r == vm or r.startswith(vm + "-r") for r in run):
            continue
        tries = [x for x in start if x == vm or x.startswith(vm + "-r")]
        last = max(tries, key=lambda x: start[x]) if tries else None
        if last in pre:
            spent += relaunch(vm, spent, run)
        else:
            print(f"{vm}: {len(m)} outputs missing and its last instance {last} was not pre-empted: read "
                  f"mimics/logs/{last}.log; one re-run of a failed item is allowed: launch_x.py relaunch {vm}")
    if not any(miss.values()) and not run:
        cmd_evaluate(a)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pilot")
    p.add_argument("--dry-run", action="store_true")
    t = sub.add_parser("timings")
    t.add_argument("--run", default="mimics-xp")
    t.add_argument("--out")
    f = sub.add_parser("full")
    f.add_argument("--pilot-json", required=True)
    f.add_argument("--dry-run", action="store_true")
    for c in ("status", "spent", "complete", "evaluate", "tick", "regtest"):
        sub.add_parser(c)
    sub.add_parser("fetch")
    r = sub.add_parser("relaunch")
    r.add_argument("vms", nargs="+")
    r.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sys.exit({"pilot": cmd_pilot, "timings": cmd_timings, "full": cmd_full, "status": cmd_status, "spent": cmd_spent,
              "complete": cmd_complete, "relaunch": cmd_relaunch, "evaluate": cmd_evaluate, "fetch": cmd_fetch,
              "tick": cmd_tick, "regtest": cmd_regtest}[a.cmd](a) or 0)


if __name__ == "__main__":
    main()
