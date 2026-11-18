#!/usr/bin/env python3
"""Paper 1 addendum 2 — evaluation of the three analyses (docs/research/paper-1/PREREG-addendum-2026-11-age-faithful-
deterministic.md). Committed before it is run on any new output; run ONCE, on the evaluation VM
(research/cloud/vm_mimics_eval_x.sh), with no cloud credentials. The first addendum's evaluation code
(evaluate_mimics.py) is imported and NOT changed; the app's region / DIS code is reached only through it (hc_core.AppDIS).

Subcommands (in the order the VM runs them; run 3 itself = the unchanged `evaluate_mimics.py register/check/run`):
  dg              gate DG: the two independent deterministic registration runs, transform by transform
  young-register  B2 (Dallas 21-49): GR with the run-a transforms (evaluate_mimics.cmd_register, unchanged)
  young-check     B2: G3 structural check of the six configurations' outputs (evaluate_mimics.cmd_check)
  young-run       B2: evaluate_mimics.one_unit for every participant (as block B) -> records_b2.json
  xb-register / xb-run   only if DG's primary criterion fails: A, B and B2 again with the run-b transforms
  gs              gate GS(ii): SynthSeg label maps present and structurally valid; QC flags (before any outcome)
  faithful        analysis 3: the clinically faithful rule in each person's own space -> records_faithful.json
  summarise       every endpoint of the three analyses -> summary_addendum2.json, SUMMARY.md, csv files
"""
import argparse
import csv
import glob
import hashlib
import json
import math
import os
import sys
import time
from multiprocessing import Pool
from types import SimpleNamespace

import nibabel as nib
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import evaluate_mimics as EM            # noqa: E402  (first addendum, unchanged)
import faithful_rule as FR              # noqa: E402
import hc_core as H                     # noqa: E402

SETS2 = os.path.join(HERE, "analysis_sets_addendum2.json")
SEED2, N_BOOT = 20261118, 10000
ARMS = EM.ARMS
CONFIGS = ("experts",) + ARMS
QC_MIN = 0.65
SAFEGUARD = {"flames_ens": ("0.65", "25.000"), "flames_f0": ("0.50", "50.000")}   # part D selections of run 1
DECADES = (20, 30, 40, 50, 60, 70, 80)
COHORTS = ("ms_1mm", "wmh", "dlbs_20_49", "dlbs_50_89", "dlbs_20_89", "sibbms")
NON_MS = ("wmh", "dlbs_20_49", "dlbs_50_89", "dlbs_20_89", "sibbms")


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def rnd(x, k=4):
    return EM.rnd(x, k)


def dump(obj, path):
    json.dump(obj, open(path, "w"), indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))


# ====================================================================== sets and folders
def load_sets():
    return json.load(open(EM.SETS)), json.load(open(SETS2))


def sets_b2(sets, x2, extra_b=()):
    """A sets dict for which evaluate_mimics.units() yields only block-B units (B2, optionally plus B1 / A)."""
    return {"A_wmh2017": {}, "B1_sample": {"ids": list(extra_b) + x2["B2_sample"]["ids"]}, "B_dlbs": sets["B_dlbs"],
            "C1_ms_iso": {}, "C1_samseg_subset": {"ids": []}, "C2_sibbms": []}


def dirs(a):
    d = EM.dirs(SimpleNamespace(pf=a.pf, mimics=a.mimics, wmh=a.wmh, work=a.work, manifests=a.manifests, atlas_t1=a.atlas_t1))
    d["ss"] = a.synthseg
    return d


def sub_dirs(d, work):
    return dict(d, out=work, reg=os.path.join(work, "registration"), atlas_t1=os.path.join(work, "atlas_t1_brain.nii.gz"))


# ====================================================================== gate DG
def read_mat(p):
    return np.array([[float(v) for v in line.split()] for line in open(p) if line.strip()])


def cmd_dg(a):
    ids = sorted(os.path.basename(p)[:-4] for p in glob.glob(os.path.join(a.run_a, "*.mat")))
    idb = sorted(os.path.basename(p)[:-4] for p in glob.glob(os.path.join(a.run_b, "*.mat")))
    sets, x2 = load_sets()
    want = sorted(list(sets["A_wmh2017"]) + sets["B1_sample"]["ids"] + x2["B2_sample"]["ids"])
    rec, maxd = {}, 0.0
    for i in want:
        pa, pb = os.path.join(a.run_a, f"{i}.mat"), os.path.join(a.run_b, f"{i}.mat")
        if not (os.path.exists(pa) and os.path.exists(pb)):
            rec[i] = {"present": False}
            continue
        sa, sb = sha256(pa), sha256(pb)
        dd = float(np.abs(read_mat(pa) - read_mat(pb)).max())
        maxd = max(maxd, dd)
        rec[i] = {"present": True, "sha256_a": sa, "identical": sa == sb, "max_abs_diff": dd}
    fixed = {}
    for run, dd_ in (("a", a.run_a), ("b", a.run_b)):
        for m in glob.glob(os.path.join(os.path.dirname(dd_.rstrip("/")), "manifest-*.json")):
            fixed[f"{run}:{os.path.basename(m)}"] = json.load(open(m)).get("fixed", {}).get("sha256")
    n = len(want)
    present = sum(r["present"] for r in rec.values())
    ident = sum(r.get("identical", False) for r in rec.values())
    out = {"n_expected": n, "present_both": present, "byte_identical": ident, "max_abs_matrix_diff": maxd,
           "fixed_image_sha256": fixed, "fixed_images_identical": len(set(fixed.values())) == 1,
           "primary_pass": present == n and ident == n,
           "fallback_matrix_pass": present == n and maxd <= 1e-6,
           "ids_a": len(ids), "ids_b": len(idb), "records": rec}
    dump(out, a.out)
    print(f"DG: {ident}/{n} byte-identical; max |diff| {maxd:.3g}; primary {'PASS' if out['primary_pass'] else 'FAIL'}; "
          f"fixed image identical: {out['fixed_images_identical']}", flush=True)
    return 0


# ====================================================================== B2 (and the run-b check)
def _ns(threads=1):
    return SimpleNamespace(threads=threads)


def cmd_young(a, what):
    sets, x2 = load_sets()
    d = dirs(a)
    if what.startswith("xb"):
        s2 = sets_b2(sets, x2, extra_b=sets["B1_sample"]["ids"])
        s2["A_wmh2017"] = sets["A_wmh2017"]
        dd = sub_dirs(d, a.work_xb)
        recs_name = "records_xb.json"
    else:
        s2 = sets_b2(sets, x2)
        dd = sub_dirs(d, a.work_b2)
        recs_name = "records_b2.json"
    os.makedirs(dd["out"], exist_ok=True)
    if what.endswith("register"):
        return EM.cmd_register(_ns(1), dd, s2)
    if what.endswith("check"):
        return EM.cmd_check(_ns(1), dd, s2)
    us = EM.units(s2, dd)
    with Pool(a.workers) as pool:
        recs = pool.map(EM.one_unit, [(u, dd) for u in us], chunksize=1)
    for r in recs:
        if r["block"] == "B" and r["base"] in set(x2["B2_sample"]["ids"]):
            r["sample"] = "B2"
    dump(recs, os.path.join(dd["out"], recs_name))
    print(f"{what}: {len(recs)} units -> {recs_name}", flush=True)
    return 0


# ====================================================================== gate GS and analysis 3
def faithful_units(sets, x2, d):
    us = []
    keys = x2["synthseg_keys"]
    for u in EM.units(sets, d):
        if u["block"] == "A":
            us.append(dict(u, cohort="wmh", key=keys["A"][u["base"]]))
        elif u["block"] == "B":
            us.append(dict(u, cohort="dlbs_50_89", key=keys["B"][u["base"]]))
        elif u["block"] == "C1" and u["T"] == 1.0:
            us.append(dict(u, cohort="ms_1mm", key=keys["C1"][u["base"]]))
        elif u["block"] == "C2" and u["T"] == 1.0:
            us.append(dict(u, cohort="sibbms", key=keys["C2"][u["base"]]))
    for u in EM.units(sets_b2(sets, x2), sub_dirs(d, d["out"] + "_b2_units")):
        us.append(dict(u, cohort="dlbs_20_49", key=keys["B2"][u["base"]], sample="B2"))
    return us


def parse_qc(path):
    if not os.path.exists(path):
        return None
    rows = [r for r in csv.reader(open(path)) if r]
    vals = {}
    if len(rows) >= 2:
        for k, v in zip(rows[0], rows[1]):
            try:
                vals[k.strip()] = float(v)
            except ValueError:
                pass
    return vals


def cmd_gs(a):
    sets, x2 = load_sets()
    d = dirs(a)
    need = {"lateral ventricles": FR.VENTRICLES, "cortex": FR.CORTEX, "brainstem": (16,)}
    out, bad = {}, 0
    keys = [(u["cohort"], u["key"]) for u in faithful_units(sets, x2, d)] + [("atlas", x2["synthseg_keys"]["atlas"])]
    for coh, key in keys:
        p = os.path.join(d["ss"], f"{key}_synthseg.nii.gz")
        why = []
        if not os.path.exists(p):
            why.append("missing")
        else:
            img = nib.load(p)
            lab = np.rint(np.asarray(img.dataobj)).astype(int)
            present = set(np.unique(lab).tolist())
            for name, ls in need.items():
                if not present & set(ls):
                    why.append(f"no {name} label")
        qc = parse_qc(os.path.join(d["ss"], f"{key}_qc.csv"))
        qmin = min(qc.values()) if qc else None
        out[key] = {"cohort": coh, "pass": not why, "why": why, "qc_min": qmin, "qc_flag": qmin is None or qmin < QC_MIN}
        if why:
            bad += 1
            print(f"FAIL {key}: {'; '.join(why)}", flush=True)
    by = {}
    for k, v in out.items():
        b = by.setdefault(v["cohort"], {"n": 0, "pass": 0, "qc_flagged": 0})
        b["n"] += 1
        b["pass"] += v["pass"]
        b["qc_flagged"] += v["qc_flag"]
    for b in by.values():
        b["qc_flag_over_10pct"] = b["qc_flagged"] > 0.10 * b["n"]
    dump({"qc_min_threshold": QC_MIN, "by_cohort": by, "records": out}, os.path.join(a.work, "gs.json"))
    print(f"GS: {len(out) - bad} PASS, {bad} FAIL; by cohort {json.dumps(by)}", flush=True)
    return 0


def faithful_unit(args):
    u, d = args
    t0 = time.time()
    img = EM.ref_image(u, d)
    rec = {k: u.get(k) for k in ("id", "block", "base", "T", "site", "split", "age", "cohort", "clean", "key", "sample")}
    rec["configs"] = {}
    p = os.path.join(d["ss"], f"{u['key']}_synthseg.nii.gz")
    if not os.path.exists(p):
        rec["anat"] = False
        return rec
    seg = nib.load(p)
    anat = FR.labels_on_grid(np.asarray(seg.dataobj), seg.affine, img.shape[:3], img.affine)
    rec["anat"] = True
    masks = {}
    if u["block"] == "A":
        lab = np.rint(np.asarray(nib.load(os.path.join(d["wmh"], u["wmh"])).dataobj)).astype(np.int16)
        masks["experts"] = lab == 1
    elif u["block"] == "C1":
        masks["experts"] = np.asarray(img.get_fdata(dtype=np.float32)) > 0.5
    for arm in u["arms"]:
        m = EM.arm_map(u, arm, d, img)
        masks[arm] = None if m is None else (m >= 0.5)
    for cfg, mk in masks.items():
        rec["configs"][cfg] = {"available": False} if mk is None else {"available": True,
                                                                         **FR.evaluate_mask(mk, img.affine, anat)}
    if u["block"] == "C2":                                         # atlas-derived labels (sensitivity)
        ap = os.path.join(d["ss"], f"{d['atlas_key']}_synthseg.nii.gz")
        if os.path.exists(ap):
            at = nib.load(ap)
            anat_a = FR.labels_on_grid(np.asarray(at.dataobj), at.affine, img.shape[:3], img.affine)
            rec["configs_atlas"] = {cfg: ({"available": False} if mk is None else
                                          {"available": True, **FR.evaluate_mask(mk, img.affine, anat_a)})
                                    for cfg, mk in masks.items()}
    rec["seconds"] = round(time.time() - t0, 1)
    return rec


def cmd_faithful(a):
    sets, x2 = load_sets()
    d = dirs(a)
    d["atlas_key"] = x2["synthseg_keys"]["atlas"]
    us = faithful_units(sets, x2, d)
    with Pool(a.workers) as pool:
        recs = pool.map(faithful_unit, [(u, d) for u in us], chunksize=1)
    dump(recs, os.path.join(a.work, "records_faithful.json"))
    print(f"faithful: {len(recs)} units", flush=True)
    return 0


# ====================================================================== statistics
def cp(x, n):
    return EM.binom(x, n)


def patient(base):
    parts = base.split("_")
    return "_".join(parts[:2]) if base.startswith("mslesseg_") else base


def icc_binary(groups):
    """ANOVA estimator of the intraclass correlation of a 0/1 outcome (the manuscript's make_rule_stats.py)."""
    k = len(groups)
    n = sum(len(g) for g in groups)
    if k < 2 or n <= k:
        return 0.0
    grand = sum(sum(g) for g in groups) / n
    ssb = sum(len(g) * (sum(g) / len(g) - grand) ** 2 for g in groups)
    ssw = sum(sum((v - sum(g) / len(g)) ** 2 for v in g) for g in groups)
    msb, msw = ssb / (k - 1), ssw / (n - k)
    n0 = (n - sum(len(g) ** 2 for g in groups) / n) / (k - 1)
    den = msb + (n0 - 1) * msw
    return max(0.0, (msb - msw) / den) if den > 0 else 0.0


def cluster_exact(units):
    """units: [(patient, 0/1)] -> exact CI on the effective sample size n / DEFF (DEFF = 1 + (m - 1) ICC)."""
    from scipy.stats import beta
    by = {}
    for p, v in units:
        by.setdefault(p, []).append(v)
    groups = list(by.values())
    x, n = sum(v for _, v in units), len(units)
    if n == 0:
        return {"x": 0, "n": 0}
    icc = icc_binary(groups)
    deff = max(1.0, 1 + (n / len(groups) - 1) * icc)
    ne, xe = n / deff, x / deff
    lo = 0.0 if xe <= 0 else float(beta.ppf(0.025, xe, ne - xe + 1))
    hi = 1.0 if xe >= ne else float(beta.ppf(0.975, xe + 1, ne - xe))
    return {"x": x, "n": n, "patients": len(groups), "rate": rnd(x / n), "icc": rnd(icc, 3), "deff": rnd(deff, 3),
            "ci95_cluster_exact": [rnd(lo), rnd(hi)], "ci95_exact_scan": cp(x, n)["ci95_exact"]}


def lr_plus(ms_units, other):
    """LR+ = P(rule | MS) / P(rule | non-MS) with a percentile bootstrap that resamples MS patients and non-MS people
    independently (RandomState(20261118) per estimate, 10,000 replicates); inf when the denominator is 0."""
    if not ms_units or not other:
        return None
    by = {}
    for p, v in ms_units:
        by.setdefault(p, []).append(v)
    pats = sorted(by)
    s_ = np.array([sum(by[p]) for p in pats], float)
    c_ = np.array([len(by[p]) for p in pats], float)
    y = np.asarray(other, float)
    sens, fpr = s_.sum() / c_.sum(), y.mean()
    rng = np.random.RandomState(SEED2)
    i1 = rng.randint(0, len(pats), size=(N_BOOT, len(pats)))
    i2 = rng.randint(0, len(y), size=(N_BOOT, len(y)))
    se = s_[i1].sum(1) / c_[i1].sum(1)
    f = y[i2].mean(1)
    with np.errstate(divide="ignore", invalid="ignore"):
        reps = np.where(f > 0, se / np.where(f > 0, f, 1), np.inf)
    reps.sort()
    lo, hi = float(reps[int(0.025 * N_BOOT)]), float(reps[int(0.975 * N_BOOT) - 1])
    fmt = lambda v: None if math.isinf(v) else rnd(v, 3)  # noqa: E731
    return {"lr_plus": fmt(sens / fpr) if fpr > 0 else None, "lr_plus_infinite": fpr == 0, "ci95_boot": [fmt(lo), fmt(hi)],
            "sens": rnd(sens), "prop_non_ms": rnd(fpr), "n_ms": int(c_.sum()), "n_non_ms": len(y)}


def logit_trend(age, y):
    """Logistic regression of y on age per 10 years (IRLS); Wald CI and p. Not estimable when y is constant, when
    IRLS does not converge in 100 iterations, or when |beta| > 10 per decade (separation)."""
    from scipy.stats import norm
    y = np.asarray(y, float)
    out = {"n": int(len(y)), "events": int(y.sum())}
    if len(y) == 0 or y.min() == y.max():
        return {**out, "estimable": False, "reason": "outcome constant", "p_wald": None}
    X = np.column_stack([np.ones(len(age)), (np.asarray(age, float) - 55.0) / 10.0])
    b = np.zeros(2)
    conv = False
    for _ in range(100):
        p = 1 / (1 + np.exp(-X @ b))
        W = p * (1 - p)
        hess = X.T @ (X * W[:, None])
        try:
            step = np.linalg.solve(hess, X.T @ (y - p))
        except np.linalg.LinAlgError:
            break
        b += step
        if np.abs(step).max() < 1e-10:
            conv = True
            break
    if not conv or abs(b[1]) > 10:
        return {**out, "estimable": False, "reason": "no convergence or separation", "p_wald": None}
    se = math.sqrt(np.linalg.inv(hess)[1, 1])
    z = b[1] / se
    return {**out, "estimable": True, "or_per_decade": rnd(math.exp(b[1])),
            "ci95_wald": [rnd(math.exp(b[1] - 1.959964 * se)), rnd(math.exp(b[1] + 1.959964 * se))],
            "p_wald": float(2 * norm.sf(abs(z)))}


def icc_a1(x, y):
    """ICC(A,1): two-way, absolute agreement, single measure (McGraw & Wong 1996), two 'raters' = two runs."""
    M = np.column_stack([np.asarray(x, float), np.asarray(y, float)])
    n, k = M.shape
    if n < 2:
        return None
    gm = M.mean()
    msr = k * ((M.mean(1) - gm) ** 2).sum() / (n - 1)
    msc = n * ((M.mean(0) - gm) ** 2).sum() / (k - 1)
    sse = ((M - M.mean(1, keepdims=True) - M.mean(0, keepdims=True) + gm) ** 2).sum()
    mse = sse / ((n - 1) * (k - 1))
    den = msr + (k - 1) * mse + k * (msc - mse) / n
    return rnd((msr - mse) / den, 5) if den > 0 else None


# ====================================================================== summarise
def read_csv(p):
    return list(csv.DictReader(open(p, encoding="utf-8")))


def agreement(new_rows, old_rows):
    """Run 3 vs an earlier run on blocks A and B: decisions, component counts, experts' decisions."""
    old = {(r["id"], r["arm"]): r for r in old_rows if r["block"] in ("A", "B")}
    out = {}
    for blk in ("A", "B"):
        out[blk] = {}
        for arm in ARMS:
            ks = [(r, old[(r["id"], r["arm"])]) for r in new_rows if r["block"] == blk and r["arm"] == arm
                  and r["available"] == "1" and (r["id"], r["arm"]) in old and old[(r["id"], r["arm"])]["available"] == "1"
                  and r["n_lesions"] != "" and old[(r["id"], r["arm"])]["n_lesions"] != ""]
            if not ks:
                continue
            n_new = [int(a["n_lesions"]) for a, _ in ks]
            n_old = [int(b["n_lesions"]) for _, b in ks]
            e = {"n": len(ks)}
            for f in ("dis", "dis_pv3", "any_dis_region"):
                e[f"{f}_differ"] = sum(a[f] != b[f] for a, b in ks)
            e["count_exact_agreement"] = rnd(np.mean([x == y for x, y in zip(n_new, n_old)]))
            e["count_max_abs_diff"] = int(max(abs(x - y) for x, y in zip(n_new, n_old)))
            e["count_icc_a1"] = icc_a1(n_new, n_old)
            out[blk][arm] = e
        ex_new = {r["id"]: r["expert_dis"] for r in new_rows if r["block"] == blk and r["expert_dis"] != ""}
        ex_old = {r["id"]: r["expert_dis"] for r in old_rows if r["block"] == blk and r["expert_dis"] != ""}
        if ex_new:
            out[blk]["experts"] = {"n": len(ex_new), "dis_differ": sum(ex_new[k] != ex_old.get(k) for k in ex_new)}
    return out


def decisions_changed(s_new, s_old):
    out = []
    for fam, es in s_new["families"].items():
        old = {e["arm"]: e for e in s_old["families"].get(fam, [])}
        for e in es:
            o = old.get(e["arm"], {})
            ch = (e.get("established_holm_lt_0.05") != o.get("established_holm_lt_0.05") or
                  (e.get("p_holm_all_40", 1) < 0.05) != (o.get("p_holm_all_40", 1) < 0.05))
            if ch:
                out.append({"family": fam, "arm": e["arm"], "new_p": e.get("p_two_sided"), "old_p": o.get("p_two_sided")})
    return out


def rows_of(path, blocks, key_cols):
    return sorted(tuple(r[c] for c in key_cols) for r in read_csv(path) if r["block"] in blocks)


def gate_dc(res_new, res_run1):
    """Gate DC: C1 and C2 rows of run 3 must equal run 1's exactly (they do not pass through the registration)."""
    pu = rows_of(os.path.join(res_new, "per_unit.csv"), ("C1", "C2"), list(read_csv(os.path.join(res_run1, "per_unit.csv"))[0]))
    pu1 = rows_of(os.path.join(res_run1, "per_unit.csv"), ("C1", "C2"), list(read_csv(os.path.join(res_run1, "per_unit.csv"))[0]))
    cols = ["id", "block", "arm", "lesion", "vol_mm3", "region"]
    le = rows_of(os.path.join(res_new, "lesions.csv"), ("C1", "C2"), cols)
    le1 = rows_of(os.path.join(res_run1, "lesions.csv"), ("C1", "C2"), cols)
    return {"per_unit_rows": len(pu), "lesion_rows": len(le), "passed": pu == pu1 and le == le1}


def age_endpoints(r, arm):
    """E1-E4 and (a) for one participant and configuration (None when unavailable or the GR gate failed)."""
    a = r["arms"].get(arm, {})
    if not a.get("available") or "dis" not in a:
        return None
    les = [(v, g) for v, g in a.get("lesions", [])]
    e = {"any_lesion": a["n_native"] > 0, "E1_rule": bool(a["dis"]), "E2_pv3": bool(a["dis_pv3"]),
         "E3_min14": bool(EM.dis_from_lesions(les, EM.PF.SPHERE_3MM_MM3))}
    if arm in SAFEGUARD and a.get("grid"):
        t, m = SAFEGUARD[arm]
        e["E4_safeguard"] = bool(a["grid"][t]["dis"][m])
    return e


def analysis2(recs3, recs_b2, recs3_c2):
    young = [r for r in recs_b2 if r["block"] == "B"]
    old = [r for r in recs3 if r["block"] == "B"]
    allp = young + old
    out = {"n_20_49": len(young), "n_50_89": len(old), "arms": {}}
    fam = []
    for arm in ARMS:
        e = {"by_decade": {}, "trend": {}}
        vals = [(r["age"], age_endpoints(r, arm)) for r in allp]
        vals = [(age, v) for age, v in vals if v is not None]
        keys = sorted({k for _, v in vals for k in v})
        for k in keys:
            e["by_decade"][k] = {str(dec): cp(sum(v[k] for age, v in vals if dec <= age < dec + 10 and k in v),
                                              sum(1 for age, v in vals if dec <= age < dec + 10 and k in v)) for dec in DECADES}
            e["trend"][k] = logit_trend([age for age, v in vals if k in v], [v[k] for _, v in vals if k in v])
            yv = [v[k] for age, v in vals if age < 50 and k in v]
            ov = [v[k] for age, v in vals if age >= 50 and k in v]
            if yv and ov:
                e.setdefault("young_minus_old", {})[k] = EM.newcombe(sum(yv), len(yv), sum(ov), len(ov))
        sib = [bool(r["arms"][arm]["dis"]) for r in recs3_c2 if r["arms"].get(arm, {}).get("available") and "dis" in r["arms"][arm]]
        yv = [v["E1_rule"] for age, v in vals if age < 50]
        if sib and yv:
            e["young_minus_sibbms_E1"] = EM.newcombe(sum(yv), len(yv), sum(sib), len(sib))
            e["young_E1"] = cp(sum(yv), len(yv))
        e["lesions_per_scan_by_decade"] = {str(dec): EM.dist([r["arms"][arm]["n"] for r in allp if dec <= r["age"] < dec + 10
                                                               and r["arms"].get(arm, {}).get("available") and "n" in r["arms"][arm]])
                                           for dec in DECADES}
        out["arms"][arm] = e
        t = e["trend"].get("E1_rule", {})
        fam.append({"arm": arm, "run": bool(t.get("estimable")), "p_two_sided": t.get("p_wald")})
    out["family_G1"] = EM.family(fam)
    gr = [r.get("gr_pass") for r in young]
    out["gr_b2"] = {"pass": int(sum(bool(x) for x in gr)), "n": len(gr), "dice": EM.dist([r.get("gr_dice") for r in young
                                                                                            if r.get("gr_dice") is not None])}
    return out


def analysis3(recs_f, app_by_id, gs):
    def units(cohort, cfg, key="rule", qc_ok=False, src="configs"):
        out = []
        for r in recs_f:
            if not (r["cohort"] == cohort or (cohort == "dlbs_20_89" and r["cohort"] in ("dlbs_20_49", "dlbs_50_89"))):
                continue
            if qc_ok and gs.get(r["key"], {}).get("qc_flag", True):
                continue
            c = (r.get(src) or {}).get(cfg, {})
            if c.get("available"):
                out.append((patient(r["base"]) if r["cohort"] == "ms_1mm" else r["id"], int(c[key]), r))
        return out
    res = {"proportions": {}, "lr_plus": {}, "vs_app_rule": {}, "regions": {}, "by_decade": {}, "sensitivity": {}}
    for key in ("rule", "rule_pv3", "rule_corner"):
        res["proportions"][key] = {}
        for cfg in CONFIGS:
            res["proportions"][key][cfg] = {}
            for coh in COHORTS:
                u = units(coh, cfg, key)
                if not u:
                    continue
                if coh == "ms_1mm":
                    res["proportions"][key][cfg][coh] = cluster_exact([(p, v) for p, v, _ in u])
                else:
                    res["proportions"][key][cfg][coh] = cp(sum(v for _, v, _ in u), len(u))
        res["lr_plus"][key] = {}
        for cfg in CONFIGS:
            ms = [(p, v) for p, v, _ in units("ms_1mm", cfg, key)]
            res["lr_plus"][key][cfg] = {coh: lr_plus(ms, [v for _, v, _ in units(coh, cfg, key)])
                                        for coh in NON_MS if units(coh, cfg, key)}
    # sensitivity: QC-flagged scans excluded; SibBMS with the atlas-derived labels
    res["sensitivity"]["qc_excluded"] = {}
    for cfg in CONFIGS:
        ms = [(p, v) for p, v, _ in units("ms_1mm", cfg, qc_ok=True)]
        res["sensitivity"]["qc_excluded"][cfg] = {
            coh: {"prop": (cluster_exact([(p, v) for p, v, _ in units(coh, cfg, qc_ok=True)]) if coh == "ms_1mm" else
                           cp(sum(v for _, v, _ in units(coh, cfg, qc_ok=True)), len(units(coh, cfg, qc_ok=True)))),
                  **({"lr_plus": lr_plus(ms, [v for _, v, _ in units(coh, cfg, qc_ok=True)])} if coh != "ms_1mm" else {})}
            for coh in COHORTS if units(coh, cfg, qc_ok=True)}
    res["sensitivity"]["sibbms_atlas_labels"] = {}
    for cfg in ARMS:
        u = units("sibbms", cfg, src="configs_atlas")
        if u:
            ms = [(p, v) for p, v, _ in units("ms_1mm", cfg)]
            res["sensitivity"]["sibbms_atlas_labels"][cfg] = {"prop": cp(sum(v for _, v, _ in u), len(u)),
                                                              "lr_plus": lr_plus(ms, [v for _, v, _ in u])}
    # faithful vs the app rule, paired (exploratory): b = faithful only, c = app only
    for cfg in CONFIGS:
        res["vs_app_rule"][cfg] = {}
        for coh in COHORTS:
            pairs = [(v, app_by_id.get((r["block"], r["id"], cfg))) for _, v, r in units(coh, cfg)]
            pairs = [(f, ap) for f, ap in pairs if ap is not None]
            if pairs:
                f_ = np.array([p[0] for p in pairs], bool)
                a_ = np.array([p[1] for p in pairs], bool)
                res["vs_app_rule"][cfg][coh] = {"n": len(pairs), "faithful": int(f_.sum()), "app": int(a_.sum()),
                                                **H.mcnemar_exact(f_, a_)}
    # lesions per region (qualifying lesions), per cohort and configuration
    for cfg in CONFIGS:
        res["regions"][cfg] = {}
        for coh in COHORTS:
            rows = [r["configs"][cfg] for r in recs_f if (r["cohort"] == coh) and r["configs"].get(cfg, {}).get("available")]
            if rows:
                res["regions"][cfg][coh] = {g: EM.dist([x["regions"][g] for x in rows]) for g in ("PV", "JC", "IT", "other")}
                res["regions"][cfg][coh]["n_components"] = EM.dist([x["n_components"] for x in rows])
                res["regions"][cfg][coh]["n_lesions"] = EM.dist([x["n_lesions"] for x in rows])
    # Dallas by decade
    for cfg in ARMS:
        res["by_decade"][cfg] = {}
        for key in ("rule", "rule_pv3"):
            u = units("dlbs_20_89", cfg, key)
            res["by_decade"][cfg][key] = {str(dec): cp(sum(v for _, v, r in u if dec <= r["age"] < dec + 10),
                                                       sum(1 for _, v, r in u if dec <= r["age"] < dec + 10)) for dec in DECADES}
            res["by_decade"][cfg][key + "_trend"] = logit_trend([r["age"] for _, _, r in u], [v for _, v, _ in u])
    return res


def app_decisions(recs3, recs_b2):
    """(block, unit id, configuration) -> the app rule decision of the same scan (run 3; B2 from records_b2)."""
    out = {}
    for r in list(recs3) + list(recs_b2):
        if r["block"] in ("C1", "C2") and r["T"] != 1.0:
            continue
        if r["block"] in ("A", "C1") and "expert" in r:
            out[(r["block"], r["id"], "experts")] = bool(r["expert"]["dis"])
        for arm, a in r["arms"].items():
            if a.get("available") and "dis" in a:
                out[(r["block"], r["id"], arm)] = bool(a["dis"])
    return out


def fmt(c):
    if not c or not c.get("n"):
        return "—"
    lo, hi = c.get("ci95_cluster_exact") or c["ci95_exact"]
    return f"{c['x']}/{c['n']} ({100 * c['x'] / c['n']:.0f} %; {100 * lo:.0f}–{100 * hi:.0f})"


def fmt_lr(e):
    if not e:
        return "—"
    lo, hi = e["ci95_boot"]
    est = "∞" if e["lr_plus_infinite"] else f"{e['lr_plus']:.2f}"
    return f"{est} ({'∞' if lo is None else f'{lo:.2f}'}–{'∞' if hi is None else f'{hi:.2f}'})"


NAMES = {"experts": "Experts' masks", "flames_ens": "FLAMeS ensemble", "flames_f0": "FLAMeS fold 0", "lstai": "LST-AI",
         "mindglide": "MindGlide", "wmhsynthseg": "WMH-SynthSeg", "samseg": "SAMSEG"}
COH_NAMES = {"ms_1mm": "MS 1 mm", "wmh": "WMH 2017", "dlbs_20_49": "Dallas 20–49", "dlbs_50_89": "Dallas 50–89",
             "dlbs_20_89": "Dallas 20–89", "sibbms": "SibBMS (template space)"}


def write_summary(S, out):
    L = ["# Paper 1 addendum 2 — results (deterministic registration, Dallas age curve, faithful rule)", "",
         "Protocol: `docs/research/paper-1/PREREG-addendum-2026-11-age-faithful-deterministic.md`. Generated by "
         "`research/paper_1/mimics/evaluate_addendum2.py` on the evaluation VM; aggregate numbers only (no per-person "
         "data of WMH 2017 or SibBMS). Proportions: x/n (%; exact 95 % CI; MS: cluster-adjusted exact CI).", "",
         "## Gates", ""]
    g = S["gates"]
    L += [f"- DG (deterministic registration): {g['DG']['byte_identical']}/{g['DG']['n_expected']} transforms byte-identical "
          f"between the two independent runs; max |matrix difference| {g['DG']['max_abs_matrix_diff']:.3g}; "
          f"primary criterion **{'PASS' if g['DG']['primary_pass'] else 'FAIL'}**"
          + ("" if g["DG"]["primary_pass"] else f"; fallback: {g.get('DG_fallback')}"),
          f"- DC (C1/C2 of run 3 identical to run 1): **{'PASS' if g['DC']['passed'] else 'FAIL'}** "
          f"({g['DC']['per_unit_rows']} per-unit rows, {g['DC']['lesion_rows']} lesion rows)",
          f"- GR: run 3 {json.dumps(g['GR_run3'])}; Dallas 20–49 {g['GR_b2']['pass']}/{g['GR_b2']['n']}",
          f"- G1 (run 3): {'PASS' if g['G1_run3'] else 'FAIL'}; G2 run 3: {g.get('G2_run3')}; G2 Dallas 20–49: {g.get('G2_b2')}",
          f"- GS (SynthSeg): {json.dumps(g['GS'])}", ""]
    A1 = S["analysis1"]
    L += ["## Analysis 1 — deterministic registration (run 3) vs runs 1 and 2", "",
          "| Block | Configuration | n | DIS differs vs run 1 | vs run 2 | PV≥3 differs vs run 1 | count exact agreement vs run 1 | "
          "max |Δ count| vs run 1 | ICC(A,1) vs run 1 | ICC vs run 2 |", "|---|---|---|---|---|---|---|---|---|---|"]
    for blk in ("A", "B"):
        for arm in ARMS + ("experts",):
            e1, e2 = A1["vs_run1"][blk].get(arm), A1["vs_run2"][blk].get(arm)
            if not e1:
                continue
            if arm == "experts":
                L.append(f"| {blk} | {NAMES[arm]} | {e1['n']} | {e1['dis_differ']} | {e2['dis_differ']} | | | | | |")
                continue
            L.append(f"| {blk} | {NAMES[arm]} | {e1['n']} | {e1['dis_differ']} | {e2['dis_differ']} | {e1['dis_pv3_differ']} | "
                     f"{e1['count_exact_agreement']} | {e1['count_max_abs_diff']} | {e1['count_icc_a1']} | {e2['count_icc_a1']} |")
    L += ["", f"Test decisions that change vs run 1 (within-family Holm or Holm over all 40): {len(A1['test_decisions_vs_run1'])} "
          f"{json.dumps(A1['test_decisions_vs_run1'])}. GR brain Dice, max |Δ| vs run 1: {A1['gr_dice_max_diff_vs_run1']}; "
          f"vs run 2: {A1['gr_dice_max_diff_vs_run2']}.", "",
          "Run 3 headline (blocks A and B; the reported run from now on):", "",
          "| Configuration | WMH 2017 DIS | Dallas 50–89 DIS |", "|---|---|---|"]
    for arm in ARMS:
        L.append(f"| {NAMES[arm]} | {fmt(A1['run3']['A'][arm])} | {fmt(A1['run3']['B'][arm])} |")
    L.append(f"| {NAMES['experts']} | {fmt(A1['run3']['A_experts'])} | |")
    A2 = S["analysis2"]
    L += ["", "## Analysis 2 — the automated rule by decade, Dallas 20–89", "",
          f"Dallas 20–49: n = {A2['n_20_49']} (GR {A2['gr_b2']['pass']}/{A2['gr_b2']['n']}); Dallas 50–89 (run 3): n = {A2['n_50_89']}.", ""]
    for k, title in (("E1_rule", "E1 primary automated rule"), ("E2_pv3", "E2 ≥ 3 periventricular"),
                     ("E3_min14", "E3 lesions ≥ 14.1 mm³ only"), ("E4_safeguard", "E4 safeguard (ens 0.65/25 mm³; fold 0 0.50/50 mm³)"),
                     ("any_lesion", "≥ 1 lesion called")):
        L += [f"### {title}", "", "| Configuration | " + " | ".join(f"{d}s" for d in DECADES) + " | OR per decade (95 % CI) | p (Wald) |",
              "|---" * (len(DECADES) + 3) + "|"]
        for arm in ARMS:
            e = A2["arms"][arm]
            if k not in e["by_decade"]:
                continue
            cells = [(lambda c: f"{c['x']}/{c['n']}" if c.get("n") else "—")(e["by_decade"][k][str(dd)]) for dd in DECADES]
            t = e["trend"][k]
            tr = f"{t['or_per_decade']} ({t['ci95_wald'][0]}–{t['ci95_wald'][1]})" if t.get("estimable") else f"not estimable ({t.get('reason')})"
            pp = "—" if t.get("p_wald") is None else f"{t['p_wald']:.3g}"
            L.append(f"| {NAMES[arm]} | " + " | ".join(cells) + f" | {tr} | {pp} |")
        L.append("")
    L += ["Family G-1 (age slope of E1, Holm within family):", "", "| Configuration | p | Holm | established |", "|---|---|---|---|"]
    for e in A2["family_G1"]:
        L.append(f"| {NAMES[e['arm']]} | {e.get('p_two_sided')} | {e.get('p_holm_family')} | {e.get('established_holm_lt_0.05')} |")
    L += ["", "Dallas 20–49 vs the SibBMS healthy controls (E1; Newcombe 95 % CI):", "", "| Configuration | Dallas 20–49 | difference vs SibBMS |", "|---|---|---|"]
    for arm in ARMS:
        e = A2["arms"][arm]
        if "young_E1" in e:
            dd = e["young_minus_sibbms_E1"]
            L.append(f"| {NAMES[arm]} | {fmt(e['young_E1'])} | {dd['diff']} ({dd['ci95'][0]}, {dd['ci95'][1]}) |")
    A3 = S["analysis3"]
    for key, title in (("rule", "primary (F ≥ 3 mm between voxel centres)"), ("rule_pv3", "≥ 3 periventricular variant"),
                       ("rule_corner", "sensitivity: F over voxel corners")):
        L += ["", f"## Analysis 3 — clinically faithful rule in each person's own space: {title}", "",
              "| Configuration | " + " | ".join(COH_NAMES[c] for c in COHORTS) + " |", "|---" * (len(COHORTS) + 1) + "|"]
        for cfg in CONFIGS:
            row = A3["proportions"][key].get(cfg, {})
            if row:
                L.append(f"| {NAMES[cfg]} | " + " | ".join(fmt(row.get(c)) for c in COHORTS) + " |")
        L += ["", "Positive likelihood ratio (MS 1 mm ÷ non-MS cohort; 95 % bootstrap CI):", "",
              "| Configuration | " + " | ".join(COH_NAMES[c] for c in NON_MS) + " |", "|---" * (len(NON_MS) + 1) + "|"]
        for cfg in CONFIGS:
            row = A3["lr_plus"][key].get(cfg, {})
            if row:
                L.append(f"| {NAMES[cfg]} | " + " | ".join(fmt_lr(row.get(c)) for c in NON_MS) + " |")
    L += ["", "### Faithful rule vs the app's rule on the same scans (exploratory, exact McNemar)", "",
          "| Configuration | Cohort | n | faithful met | app rule met | faithful only | app only | p |", "|---|---|---|---|---|---|---|---|"]
    for cfg in CONFIGS:
        for coh, e in A3["vs_app_rule"].get(cfg, {}).items():
            L.append(f"| {NAMES[cfg]} | {COH_NAMES[coh]} | {e['n']} | {e['faithful']} | {e['app']} | {e['arm_only']} | "
                     f"{e['reference_only']} | {e['p_two_sided']:.3g} |")
    L += ["", "### Sensitivity: SibBMS with atlas-derived labels; QC-flagged scans excluded", "",
          "| Configuration | SibBMS atlas labels | LR+ vs SibBMS (atlas) |", "|---|---|---|"]
    for cfg, e in A3["sensitivity"]["sibbms_atlas_labels"].items():
        L.append(f"| {NAMES[cfg]} | {fmt(e['prop'])} | {fmt_lr(e['lr_plus'])} |")
    L += ["", "| Configuration | " + " | ".join(COH_NAMES[c] for c in COHORTS) + " |", "|---" * (len(COHORTS) + 1) + "|"]
    for cfg in CONFIGS:
        row = A3["sensitivity"]["qc_excluded"].get(cfg, {})
        if row:
            L.append(f"| {NAMES[cfg]} | " + " | ".join(fmt(row.get(c, {}).get("prop")) for c in COHORTS) + " |")
    open(os.path.join(out, "SUMMARY.md"), "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")


def write_faithful_csv(recs_f, out):
    with open(os.path.join(out, "per_unit_faithful.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "cohort", "config", "labels", "available", "rule", "rule_pv3", "rule_corner", "n_components",
                    "n_lesions", "PV", "JC", "IT", "other"])
        for r in recs_f:
            for src, tag in (("configs", "subject"), ("configs_atlas", "atlas")):
                for cfg, c in (r.get(src) or {}).items():
                    w.writerow([r["id"], r["cohort"], cfg, tag, int(c.get("available", False))] +
                               ([int(c["rule"]), int(c["rule_pv3"]), int(c["rule_corner"]), c["n_components"], c["n_lesions"]]
                                + [c["regions"][g] for g in ("PV", "JC", "IT", "other")] if c.get("available") else [""] * 9))


def cmd_summarise(a):
    W = a.work
    recs3 = json.load(open(os.path.join(W, "records.json")))
    recs_b2 = json.load(open(os.path.join(a.work_b2, "records_b2.json")))
    recs_f = json.load(open(os.path.join(W, "records_faithful.json")))
    gs = json.load(open(os.path.join(W, "gs.json")))
    dg = json.load(open(os.path.join(W, "dg.json")))
    s3 = json.load(open(os.path.join(a.results, "summary.json")))
    s1 = json.load(open(os.path.join(a.prev1, "summary.json")))
    pu3 = read_csv(os.path.join(a.results, "per_unit.csv"))
    S = {"gates": {}, "analysis1": {}, "run_info": {}}
    S["gates"]["DG"] = {k: v for k, v in dg.items() if k != "records"}
    if not dg["primary_pass"]:
        xb = os.path.join(a.work_xb, "records_xb.json")
        if os.path.exists(xb):
            ra = {r["id"]: r for r in recs3 + recs_b2 if r["block"] in ("A", "B")}
            diffs = 0
            for r in json.load(open(xb)):
                o = ra.get(r["id"])
                for arm, x in r["arms"].items():
                    y = (o or {}).get("arms", {}).get(arm, {})
                    for f in ("dis", "dis_pv3", "any_dis_region", "n"):
                        diffs += x.get(f) != y.get(f)
                    diffs += (x.get("grid") or {}) != (y.get("grid") or {})
                if "expert" in r:
                    diffs += r["expert"]["dis"] != (o or {}).get("expert", {}).get("dis")
            S["gates"]["DG_fallback"] = {"matrix_within_1e-6": dg["fallback_matrix_pass"], "decision_differences": diffs,
                                         "passed": dg["fallback_matrix_pass"] and diffs == 0}
        else:
            S["gates"]["DG_fallback"] = {"passed": False, "reason": "run-b evaluation missing"}
    S["gates"]["DC"] = gate_dc(a.results, a.prev1)
    S["gates"]["evaluate_mimics_unchanged"] = (s3["run_info"]["code_sha256"]["evaluate_mimics.py"] ==
                                               s1["run_info"]["code_sha256"]["evaluate_mimics.py"])
    S["gates"]["GR_run3"] = s3["gate_GR"]["by_block"]
    S["gates"]["G1_run3"] = s3["gate_G1"]["passed"]
    for k, f in (("G2_run3", os.path.join(a.results, "independent_check.json")),
                 ("G2_b2", os.path.join(a.results, "b2", "independent_check.json"))):
        S["gates"][k] = json.load(open(f)).get("passed") if os.path.exists(f) else None
    S["gates"]["GS"] = gs["by_cohort"]
    # ---- analysis 1
    A1 = S["analysis1"]
    A1["vs_run1"] = agreement(pu3, read_csv(os.path.join(a.prev1, "per_unit.csv")))
    A1["vs_run2"] = agreement(pu3, read_csv(os.path.join(a.prev2, "per_unit.csv")))
    A1["test_decisions_vs_run1"] = decisions_changed(s3, s1)
    A1["test_decisions_vs_run2"] = decisions_changed(s3, json.load(open(os.path.join(a.prev2, "summary.json"))))
    r3 = json.load(open(os.path.join(W, "registration.json")))["records"]
    for tag, p in (("run1", a.prev1), ("run2", a.prev2)):
        rp = json.load(open(os.path.join(p, "registration.json")))["records"]
        A1[f"gr_dice_max_diff_vs_{tag}"] = rnd(max(abs(r3[k]["dice_brain"] - rp[k]["dice_brain"]) for k in r3 if k in rp), 5)
    A1["run3"] = {"A": {arm: s3["A"]["arms"][arm]["dis"] for arm in ARMS}, "B": {arm: s3["B"]["arms"][arm]["b_dis"] for arm in ARMS},
                  "A_experts": s3["A"]["A0_expert_dis"], "D_selected": {k: s3["D"][k]["selected"] for k in s3["D"]},
                  "D_validation_dlbs": {k: s3["D"][k].get("validation_selected", {}).get("dlbs") for k in s3["D"]}}
    sel = {k: (f"{v['t']:.2f}", f"{v['m']:.3f}") for k, v in A1["run3"]["D_selected"].items() if v}
    A1["safeguard_points_equal_run1"] = sel == SAFEGUARD
    # ---- analysis 2 and 3
    c2 = [r for r in recs3 if r["block"] == "C2" and r["T"] == 1.0]
    S["analysis2"] = analysis2(recs3, recs_b2, c2)
    S["gates"]["GR_b2"] = S["analysis2"]["gr_b2"]
    S["analysis3"] = analysis3(recs_f, app_decisions(recs3, recs_b2), gs["records"])
    S["run_info"] = {"created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "code_commit": os.environ.get("MIMICS_CODE_COMMIT"),
                     "code_sha256": {f: sha256(os.path.join(HERE, f)) for f in ("evaluate_addendum2.py", "faithful_rule.py",
                                                                                 "evaluate_mimics.py", "analysis_sets_addendum2.json")},
                     "seed": SEED2, "n_boot": N_BOOT, "qc_min": QC_MIN}
    os.makedirs(a.out, exist_ok=True)
    dump(S, os.path.join(a.out, "summary_addendum2.json"))
    write_summary(S, a.out)
    write_faithful_csv(recs_f, a.out)
    print(f"wrote {a.out}", flush=True)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("dg", "young-register", "young-check", "young-run", "xb-register", "xb-run", "gs",
                                    "faithful", "summarise"))
    ap.add_argument("--pf", default="")
    ap.add_argument("--mimics", default="")
    ap.add_argument("--wmh", default="")
    ap.add_argument("--manifests", default="")
    ap.add_argument("--atlas-t1", default="")
    ap.add_argument("--work", default="")
    ap.add_argument("--work-b2", default="")
    ap.add_argument("--work-xb", default="")
    ap.add_argument("--synthseg", default="")
    ap.add_argument("--results", default="", help="run 3 results folder (summary.json, per_unit.csv, lesions.csv)")
    ap.add_argument("--prev1", default="", help="run 1 results folder")
    ap.add_argument("--prev2", default="", help="run 2 results folder")
    ap.add_argument("--run-a", default="")
    ap.add_argument("--run-b", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    if a.cmd == "dg":
        sys.exit(cmd_dg(a))
    if a.cmd in ("young-register", "young-check", "young-run", "xb-register", "xb-run"):
        sys.exit(cmd_young(a, a.cmd))
    sys.exit({"gs": cmd_gs, "faithful": cmd_faithful, "summarise": cmd_summarise}[a.cmd](a))


if __name__ == "__main__":
    main()
