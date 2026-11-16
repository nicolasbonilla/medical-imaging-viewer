#!/usr/bin/env python3
"""Paper 2, design D5 (PREREG §3): two-tool consensus on paper 1's frozen masks, with paper 1's frozen functions.

It runs on a research VM next to paper 1's evaluation code: same environment, same inputs, and paper 1's atlas
transforms. It covers each paper-2 scan whose FLAMeS-ens output exists (A; B; C1 FLAMeS-clean at 1 mm; C2 at 1 mm).

**Variants:**
- `d5_primary`: the FLAMeS-ens components that LST-AI also marks (18-connected, at least 1 voxel of overlap), on the
  native FLAIR grid (`consensus.split`, k = 2).
- `d5_k2`, `d5_k3`: components marked by at least k - 1 of {LST-AI, WMH-SynthSeg, MindGlide, SAMSEG}. Run only on
  scans where all five arms exist (PREREG §3, sensitivity rules).

**The DIS path:** each kept mask follows paper 1's path exactly: warp to the atlas (A, B; linear, value >= 0.5), then
the lesion rule (18-connected components >= 3 mm^3), then the app's DIS rule (`hc_core.AppDIS`, app code, read-only).

**Single-tool candidates:** the primary's other components go through the same warp and lesion rule. Only their count
is kept, for D5's code-written line.

**Gate GD5 (identity):** FLAMeS-ens agreed with itself must reproduce, on every scan, paper 1's DIS, its lesion count,
its region flags and its lesion list (`per_unit.csv`, `lesions.csv`) — those of the paper-1 run whose transforms it
uses, i.e. the reproduction run (PREREG §12, 2026-11-16). A failure stops the job, and nothing is written as a result.

**Lesion-level supplement (PREREG §5.2 item 6):** each variant's kept lesions matched as paper 1 matches an arm
(`evaluate_mimics.one_unit`): the FLAMeS-ens map > 0.5, restricted to the kept components, on the native grid,
`metrics.lesion_metrics` (26-connected, >= 14.137 mm^3) against WMH 2017 label 1 with label 2 left out of the
prediction (A) or the expert mask (C1). B (no MS, no lesion reference) and C2 (no reference in paper 1) get the
lesion count only. **Gate GD5-acc:** the identity variant must equal paper 1's FLAMeS-ens n_ref, false_lesions and F1
on every A and C1 scan.

**Outputs** (in --out): `consensus_per_unit.csv` and `consensus_lesions.csv` (paper 1's columns, plus `n_single`),
`consensus_accuracy.csv` (the supplement, identity included as FLAMeS-ens) and `consensus_gate.json`.

    python research/paper_2/consensus_eval.py --p1-results <paper 1 results> --pf ... --mimics ... --wmh ... \
        --manifests ... --atlas-t1 ... --work <paper 1 work dir with registration/> --out <dir> --workers 8
"""
import argparse
import csv
import importlib.util
import json
import os
import sys
import time
from collections import defaultdict
from multiprocessing import Pool

import nibabel as nib
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
PARTNERS = ("lstai", "wmhsynthseg", "mindglide", "samseg")
VARIANTS = ("d5_primary", "d5_k2", "d5_k3")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


EM = C = None       # paper 1's evaluation module and the consensus rule, loaded by init() (the tests need neither)


def init():
    global EM, C
    EM = _load("evaluate_mimics", os.path.join(ROOT, "research", "paper_1", "mimics", "evaluate_mimics.py"))
    C = _load("paper2_consensus", os.path.join(HERE, "consensus.py"))


def rnd(x, k=1):
    return "" if x is None else round(float(x), k)


def paper2_units(sets, d):
    """Paper 1's units of the four paper-2 sets: native resolution only, C1 FLAMeS-clean, FLAMeS-ens registered."""
    out = []
    for u in EM.units(sets, d):
        if u["block"] in ("C1", "C2") and "_th" in u["id"]:
            continue
        if u["block"] == "C1" and not u.get("clean"):
            continue
        if "flames_ens" in u["arms"]:
            out.append(u)
    return out


def _warp(mask, u, img, d, tag):
    m = mask.astype(np.float32)
    if u["warp"]:
        m = (EM.warp_float(m, img, u["base"], d, tag) >= 0.5).astype(np.float32)
    return m


ACC_KEYS = ("n_ref", "n_pred", "tp_ref", "tp_pred", "false_lesions", "f1")


def reference(u, d, img):
    """Paper 1's accuracy reference (`evaluate_mimics.one_unit`): (reference mask, mask left out of the prediction)."""
    if u["block"] == "A":
        lab = np.rint(np.asarray(nib.load(os.path.join(d["wmh"], u["wmh"])).dataobj)).astype(np.int16)
        return lab == 1, lab == 2
    if u["block"] == "C1":
        return np.asarray(img.get_fdata(dtype=np.float32)) > 0.5, None
    return None, None


def accuracy(kept, strict, ref, other, zooms, pf):
    """One variant's lesion-level counts, matched as paper 1 matches an arm: `kept` (the variant's components) within
    `strict` (the FLAMeS-ens map > 0.5), label 2 left out (A), `pf.lesion_metrics` against the reference."""
    pred = np.asarray(kept, bool) & np.asarray(strict, bool)
    if other is not None:
        pred = pred & ~other
    if ref is None:
        return {"n_pred": int(pf.components(pred, zooms)[1])}
    lm = pf.lesion_metrics(pred, ref, zooms)
    return {k: lm[k] for k in ACC_KEYS}


def one(args):
    u, d = args
    t0 = time.time()
    img = EM.ref_image(u, d)
    if u["warp"]:
        reg = json.load(open(os.path.join(d["out"], "registration.json")))["records"][u["base"]]
        gr, dis_img = bool(reg["pass"]), nib.load(d["msmask"])
    else:
        gr, dis_img = True, img
    app = EM.app_for(dis_img)
    bins, strict = {}, None
    for a in ("flames_ens",) + PARTNERS:
        if a in u["arms"]:
            m = EM.arm_map(u, a, d, img)
            if m is not None:
                bins[a] = m >= 0.5
                if a == "flames_ens":
                    strict = m > 0.5                  # paper 1's accuracy threshold
    zooms = img.header.get_zooms()[:3]
    ref, other = reference(u, d, img)
    rec = {"id": u["id"], "block": u["block"], "base": u["base"], "T": u["T"], "gr_pass": gr, "rows": {}}
    if "flames_ens" not in bins:
        rec["flames_missing"] = True
        return rec
    fl = bins["flames_ens"]
    plan = {"identity": ([fl], 2)}
    if "lstai" in bins:
        plan["d5_primary"] = ([bins["lstai"]], 2)
    if all(p in bins for p in PARTNERS):
        plan["d5_k2"] = ([bins[p] for p in PARTNERS], 2)
        plan["d5_k3"] = ([bins[p] for p in PARTNERS], 3)
    for name, (partners, k) in plan.items():
        agreed, single, n_a, n_s = C.split(fl, partners, k)
        row = {"available": True, "n_native_agreed": n_a, "n_native_single": n_s,
               "acc": accuracy(agreed, strict, ref, other, zooms, EM.PF)}
        if gr:
            blk, les = EM.dis_block(_warp(agreed, u, img, d, name), dis_img, app)
            row.update(blk)
            row["lesions"] = [[round(v, 3), g] for v, g in les]
            if name != "identity":
                row["n_single"] = len(EM.lesion_set(_warp(single, u, img, d, name + "s"), dis_img)[0])
        rec["rows"][name] = row
    rec["seconds"] = round(time.time() - t0, 1)
    return rec


def paper1_reference(results):
    pu, les = {}, defaultdict(list)
    with open(os.path.join(results, "per_unit.csv"), newline="") as fh:
        for r in csv.DictReader(fh):
            if r["arm"] == "flames_ens":
                pu[r["id"]] = r
    with open(os.path.join(results, "lesions.csv"), newline="") as fh:
        for r in csv.DictReader(fh):
            if r["arm"] == "flames_ens":
                les[r["id"]].append([round(float(r["vol_mm3"]), 3), r["region"]])
    return pu, les


def gate_identity(recs, pu, les):
    """GD5: FLAMeS-ens agreed with itself equals paper 1's FLAMeS-ens unit on every scan."""
    bad, n = [], 0
    for r in recs:
        row = r["rows"].get("identity")
        if row is None or not r["gr_pass"]:
            continue
        n += 1
        ref = pu.get(r["id"])
        mine = {"n_lesions": str(row["n"]), "dis": str(int(row["dis"])), "dis_pv3": str(int(row["dis_pv3"])),
                "any_dis_region": str(int(row["any_dis_region"]))}
        theirs = {k: (ref or {}).get(k) for k in mine}
        same_les = sorted(map(tuple, row["lesions"])) == sorted(map(tuple, les.get(r["id"], [])))
        if mine != theirs or not same_les:
            bad.append({"id": r["id"], "mine": mine, "paper1": theirs, "lesions_equal": same_les})
    return {"compared": n, "equal": n - len(bad), "passed": not bad and n > 0, "mismatches": bad[:20]}


def gate_accuracy(recs, pu):
    """GD5-acc: the identity variant's lesion-level counts equal paper 1's FLAMeS-ens accuracy on every A and C1 scan."""
    bad, n = [], 0
    for r in recs:
        acc = (r["rows"].get("identity") or {}).get("acc") or {}
        if "n_ref" not in acc:
            continue
        n += 1
        ref = pu.get(r["id"]) or {}
        mine = {"n_ref": str(acc["n_ref"]), "false_lesions": str(acc["false_lesions"]), "f1": str(rnd(acc["f1"], 4))}
        theirs = {k: ref.get(k) for k in mine}
        if mine != theirs:
            bad.append({"id": r["id"], "mine": mine, "paper1": theirs})
    return {"compared": n, "equal": n - len(bad), "passed": not bad and n > 0, "mismatches": bad[:20]}


def write_accuracy(recs, out):
    with open(os.path.join(out, "consensus_accuracy.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "block", "arm"] + list(ACC_KEYS))
        for r in recs:
            for v in ("identity",) + VARIANTS:
                acc = (r["rows"].get(v) or {}).get("acc")
                if acc is not None:
                    w.writerow([r["id"], r["block"], "flames_ens" if v == "identity" else v]
                               + [rnd(acc[k], 4) if k == "f1" else acc.get(k, "") for k in ACC_KEYS])


def write(recs, out):
    with open(os.path.join(out, "consensus_per_unit.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "block", "base", "T", "arm", "available", "gr_pass", "n_lesions", "dis", "dis_pv3",
                    "any_dis_region", "vol_mm3", "n_single", "n_native_agreed", "n_native_single"])
        for r in recs:
            for v in VARIANTS:
                a = r["rows"].get(v)
                if a is None:
                    w.writerow([r["id"], r["block"], r["base"], r["T"], v, 0, int(r["gr_pass"])] + [""] * 8)
                    continue
                w.writerow([r["id"], r["block"], r["base"], r["T"], v, 1, int(r["gr_pass"]), a.get("n", ""),
                            int(a["dis"]) if "dis" in a else "", int(a["dis_pv3"]) if "dis_pv3" in a else "",
                            int(a["any_dis_region"]) if "any_dis_region" in a else "", rnd(a.get("vol_mm3"), 1),
                            a.get("n_single", ""), a["n_native_agreed"], a["n_native_single"]])
    with open(os.path.join(out, "consensus_lesions.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "block", "arm", "lesion", "vol_mm3", "region"])
        for r in recs:
            for v in VARIANTS:
                for j, (vol, g) in enumerate((r["rows"].get(v) or {}).get("lesions", []), 1):
                    w.writerow([r["id"], r["block"], v, j, vol, g])


def main(argv=None):
    ap = argparse.ArgumentParser()
    for k in ("--pf", "--mimics", "--wmh", "--manifests", "--atlas-t1", "--work", "--out", "--p1-results"):
        ap.add_argument(k, required=True)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(argv)
    init()                                            # before the pool: the forked workers inherit the modules
    d = EM.dirs(a)
    if not os.path.exists(os.path.join(d["out"], "registration.json")) or not os.path.exists(d["atlas_t1"]):
        raise SystemExit("paper 1's registration step must run first (evaluate_mimics.py register with the kept transforms)")
    sets = json.load(open(EM.SETS))
    us = paper2_units(sets, d)
    t0 = time.time()
    with Pool(a.workers) as pool:
        recs = pool.map(one, [(u, d) for u in us], chunksize=1)
    pu, les = paper1_reference(a.p1_results)
    gate = gate_identity(recs, pu, les)
    gate["accuracy"] = gate_accuracy(recs, pu)
    gate["passed"] = gate["passed"] and gate["accuracy"]["passed"]
    gate.update({"scans": len(recs), "flames_missing": sum(1 for r in recs if r.get("flames_missing")),
                 "excluded_no_lstai": sum(1 for r in recs if r["rows"] and "d5_primary" not in r["rows"]),
                 "five_arm_scans": sum(1 for r in recs if "d5_k2" in r["rows"]),
                 "by_set": {b: sum(1 for r in recs if r["block"] == b) for b in ("A", "B", "C1", "C2")},
                 "runtime_s": round(time.time() - t0, 1)})
    os.makedirs(a.out, exist_ok=True)
    json.dump(gate, open(os.path.join(a.out, "consensus_gate.json"), "w"), indent=1)
    print("GD5:", json.dumps({k: gate[k] for k in ("compared", "equal", "passed")}), flush=True)
    print("GD5-acc:", json.dumps({k: gate["accuracy"][k] for k in ("compared", "equal", "passed")}), flush=True)
    if not gate["passed"]:
        print(json.dumps(gate["mismatches"][:5] + gate["accuracy"]["mismatches"][:5], indent=1), flush=True)
        return 1
    write(recs, a.out)
    write_accuracy(recs, a.out)
    print(json.dumps({k: v for k, v in gate.items() if k != "mismatches"}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
