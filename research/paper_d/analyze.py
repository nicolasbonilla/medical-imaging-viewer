"""Paper D analysis: every pre-specified outcome of docs/research/paper-d/PROTOCOL.md §6 and the
success criteria of §9, from the grid rows written by run_grid.py (research code, not the device).

    python research/paper_d/analyze.py --data-root <main checkout>/data \
        --out docs/research/paper-d/records/results_v1.json

Every interval is a patient-clustered percentile bootstrap (B = 2,000, seed 20261021).
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from research.paper_d.common import cache_dir, data_root, experiments_dir  # noqa: E402
from research.paper_d.run_grid import COLUMNS, PRIMARY_SOURCES, THRESHOLDS  # noqa: E402

PRIMARY_RULES = ("APP", "APP-LV", "LSTAI", "LSTAI-LV")
PRIMARY_G = ("G0", "G1")
M_LEVELS = ("none", "v3", "v14", "la3")
FACTORS = ("source", "t", "M", "R", "G")
REF = ("E", -1.0, "v3", "APP", "G0")
DEFAULT = ("F0", 0.5, "v3", "APP", "G0")
LSTAI_SHIPPED = ("LENS", 0.5, "none", "LSTAI", "G1")
B, SEED = 2000, 20261021
REGIONS = ("n_pv", "n_jc", "n_it", "n_dwm")


# ----------------------------------------------------------------------------- loading
def load(out: Path):
    rows, lesions = [], {}
    for f in sorted((out / "scans").glob("*.json.gz")):
        d = json.load(gzip.open(f, "rt"))
        rows += d["rows"]
        lesions[d["case"]] = d["lesions"]
    df = pd.DataFrame(rows, columns=COLUMNS)
    df["t"] = df["t"].fillna(-1.0).astype(float)
    record = json.loads((out / "run_record.json").read_text())
    return df, lesions, record


def matrix(df, cases, col="dis", sources=PRIMARY_SOURCES, ts=THRESHOLDS, Ms=M_LEVELS, Rs=PRIMARY_RULES,
           Gs=PRIMARY_G):
    sub = df[df.source.isin(sources) & df.t.isin(ts) & df.M.isin(Ms) & df.R.isin(Rs) & df.G.isin(Gs)]
    piv = sub.pivot_table(index="case", columns=list(FACTORS), values=col, aggfunc="first")
    piv = piv.reindex(cases)
    expected = len(sources) * len(ts) * len(Ms) * len(Rs) * len(Gs)
    if piv.shape[1] != expected or piv.isna().any().any():
        raise ValueError(f"grid incomplete: {piv.shape[1]} of {expected} pipelines, NaN={int(piv.isna().sum().sum())}")
    return piv


def cell(df, cases, key, col="dis"):
    s, t, M, R, G = key
    sub = df[(df.source == s) & (df.t == t) & (df.M == M) & (df.R == R) & (df.G == G)].set_index("case")[col]
    sub = sub.reindex(cases)
    if sub.isna().any():
        raise ValueError(f"missing cell {key}")
    return sub.to_numpy()


# ----------------------------------------------------------------------------- bootstrap
class Boot:
    """Patient-clustered bootstrap: multinomial patient weights reused for every statistic, so
    differences between statistics are paired."""

    def __init__(self, patients, b=B, seed=SEED):
        self.patients = np.asarray(patients)
        self.ids, self.inv = np.unique(self.patients, return_inverse=True)
        rng = np.random.default_rng(seed)
        n = len(self.ids)
        self.W = rng.multinomial(n, np.full(n, 1.0 / n), size=b).astype(float)   # (B, nP)

    def _sum(self, v):
        v = np.asarray(v, dtype=float)
        S = np.zeros((len(self.ids),) + v.shape[1:])
        np.add.at(S, self.inv, v)
        return S

    def ratio(self, num, den=None):
        num = np.asarray(num, float)
        den = np.ones(len(num)) if den is None else np.asarray(den, float)
        Sn, Sd = self._sum(num), self._sum(den)
        est = Sn.sum(0) / Sd.sum(0)
        bs = (self.W @ Sn) / (self.W @ Sd)[..., None] if Sn.ndim > 1 else (self.W @ Sn) / (self.W @ Sd)
        return est, bs

    def mean(self, v):
        est, bs = self.ratio(v)
        return summarise(est, bs)


def summarise(est, bs):
    lo, hi = np.nanpercentile(bs, [2.5, 97.5], axis=0)
    if np.ndim(est) == 0:
        return {"est": round(float(est), 4), "lo": round(float(lo), 4), "hi": round(float(hi), 4)}
    return [{"est": round(float(e), 4), "lo": round(float(a), 4), "hi": round(float(b), 4)} for e, a, b in zip(est, lo, hi)]


def index_boot(boot: Boot, fn, seed=SEED):
    """Generic patient bootstrap by index resampling (for non-ratio statistics such as ICC)."""
    rng = np.random.default_rng(seed + 1)
    groups = [np.flatnonzero(boot.inv == i) for i in range(len(boot.ids))]
    est = fn(np.arange(len(boot.inv)))
    out = []
    for _ in range(B):
        pick = rng.integers(0, len(groups), len(groups))
        idx = np.concatenate([groups[i] for i in pick])
        out.append(fn(idx))
    return summarise(est, np.array(out))


# ----------------------------------------------------------------------------- outcome helpers
def instability(D):
    p = D.mean(1)
    n = D.shape[1]
    return {"p_dis": p, "not_unanimous": ((p > 0) & (p < 1)).astype(float),
            "contested": ((p >= 0.1) & (p <= 0.9)).astype(float),
            "pairwise": 2 * p * (1 - p) * n / (n - 1)}


def factor_disagreement(piv, factor, levels):
    """Per-scan disagreement between pipelines that differ only in `factor` (restricted to
    `levels`), averaged over every combination of the other factors and every pair of levels."""
    cols = [c for c in piv.columns if c[FACTORS.index(factor)] in levels]
    sub = piv[cols]
    others = [i for i, f in enumerate(FACTORS) if f != factor]
    groups = {}
    for j, c in enumerate(cols):
        groups.setdefault(tuple(c[i] for i in others), []).append(j)
    X = sub.to_numpy()
    vals = []
    for idx in groups.values():
        k = len(idx)
        if k < 2:
            continue
        n1 = X[:, idx].sum(1)
        vals.append(n1 * (k - n1) / (k * (k - 1) / 2))
    return np.mean(vals, axis=0), len(groups)


def icc_a1(x, y):
    """ICC(A,1): two-way random effects, absolute agreement, single measurement (McGraw & Wong)."""
    Y = np.stack([x, y], 1).astype(float)
    n, k = Y.shape
    gm = Y.mean()
    msr = k * ((Y.mean(1) - gm) ** 2).sum() / (n - 1)
    msc = n * ((Y.mean(0) - gm) ** 2).sum() / (k - 1)
    sse = ((Y - Y.mean(1, keepdims=True) - Y.mean(0, keepdims=True) + gm) ** 2).sum()
    mse = sse / ((n - 1) * (k - 1))
    den = msr + (k - 1) * mse + k * (msc - mse) / n
    return float((msr - mse) / den) if den > 0 else float("nan")


def flag_metrics(boot, flag, outcome):
    flag, outcome = flag.astype(float), outcome.astype(float)
    res = {"flagged": boot.mean(flag)}
    res["p_outcome_if_flagged"] = summarise(*boot.ratio(flag * outcome, flag)) if flag.sum() else None
    res["p_outcome_if_not_flagged"] = summarise(*boot.ratio((1 - flag) * outcome, 1 - flag)) if (1 - flag).sum() else None
    if flag.sum() and (1 - flag).sum():
        e1, b1 = boot.ratio(flag * outcome, flag)
        e0, b0 = boot.ratio((1 - flag) * outcome, 1 - flag)
        res["risk_difference"] = summarise(e1 - e0, b1 - b0)
    res["sensitivity"] = summarise(*boot.ratio(flag * outcome, outcome)) if outcome.sum() else None
    res["specificity"] = summarise(*boot.ratio((1 - flag) * (1 - outcome), 1 - outcome)) if (1 - outcome).sum() else None
    res["counts"] = {"flag_and_outcome": int((flag * outcome).sum()), "flag_only": int((flag * (1 - outcome)).sum()),
                     "outcome_only": int(((1 - flag) * outcome).sum()), "neither": int(((1 - flag) * (1 - outcome)).sum())}
    return res


# ----------------------------------------------------------------------------- main analyses
def core(df, cases, patients, col="dis"):
    """P1 + P2 for one scan set and one DIS column."""
    boot = Boot(patients)
    D = matrix(df, cases, col)
    E = matrix(df, cases, col, sources=("E",), ts=(-1.0,))
    ref = E[REF].to_numpy()
    flips = (D.to_numpy() != ref[:, None]).astype(float)
    per_pipe = flips.mean(0)
    order = np.argsort(per_pipe)
    out = {
        "n_scans": len(cases), "n_patients": int(len(np.unique(patients))),
        "reference_dis_met": boot.mean(ref),
        "P1": {
            "device_default_flip": boot.mean(D[DEFAULT].to_numpy() != ref),
            "device_default_direction": {
                "ref_met_pipeline_not": int(((ref == 1) & (D[DEFAULT].to_numpy() == 0)).sum()),
                "ref_not_pipeline_met": int(((ref == 0) & (D[DEFAULT].to_numpy() == 1)).sum())},
            "lstai_as_shipped_flip": boot.mean(D[LSTAI_SHIPPED].to_numpy() != ref),
            "grid_mean_flip": boot.mean(flips.mean(1)),
            "per_pipeline_flip": {"min": round(float(per_pipe.min()), 4), "median": round(float(np.median(per_pipe)), 4),
                                  "max": round(float(per_pipe.max()), 4),
                                  "share_pipelines_le_5pct": round(float((per_pipe <= 0.05).mean()), 4),
                                  "best": [list(map(str, D.columns[i])) + [round(float(per_pipe[i]), 4)] for i in order[:5]],
                                  "worst": [list(map(str, D.columns[i])) + [round(float(per_pipe[i]), 4)] for i in order[-5:]]},
            "any_flip": boot.mean(flips.any(1)),
            "flip_direction_grid": {"ref_met_mean_share_not": round(float(flips[ref == 1].mean()), 4) if (ref == 1).any() else None,
                                    "ref_not_mean_share_met": round(float(flips[ref == 0].mean()), 4) if (ref == 0).any() else None},
        },
        "P2_automated": {k: boot.mean(v) for k, v in instability(D.to_numpy()).items() if k != "p_dis"},
        "P2_expert": {k: boot.mean(v) for k, v in instability(E.to_numpy()).items() if k != "p_dis"},
        "expert_grid_flip_vs_ref_mean": boot.mean((E.to_numpy() != ref[:, None]).mean(1)),
        "n_pipelines": {"automated": D.shape[1], "expert": E.shape[1]},
    }
    return out, D, E, ref, boot


def drivers(D, E, ref, boot, df, cases):
    fam = {"segmenter_family": ("source", ("F0", "FENS", "LENS")), "flames_fold": ("source", ("F0", "F1", "F2", "F3", "F4")),
           "threshold": ("t", THRESHOLDS), "min_size": ("M", M_LEVELS), "region_rule": ("R", PRIMARY_RULES),
           "registration": ("G", PRIMARY_G)}
    per = {}
    res = {}
    for name, (f, lv) in fam.items():
        v, ng = factor_disagreement(D, f, lv)
        per[name] = v
        res[name] = {"disagreement": boot.mean(v), "n_groups": ng}
    ranked = sorted(per, key=lambda k: -per[k].mean())
    top, second = ranked[0], ranked[1]
    est, bs = boot.ratio(per[top] - per[second])
    res["_ranking"] = ranked
    res["_top_minus_second"] = {"top": top, "second": second, **summarise(est, bs)}
    # expert grid: rule, size, registration only
    exp = {}
    for name, (f, lv) in (("min_size", ("M", M_LEVELS)), ("region_rule", ("R", PRIMARY_RULES)), ("registration", ("G", PRIMARY_G))):
        v, ng = factor_disagreement(E, f, lv)
        exp[name] = {"disagreement": boot.mean(v), "n_groups": ng}
    res["_expert_grid"] = exp
    # one factor at a time from the device default (primary and secondary levels)
    dflt = cell(df, cases, DEFAULT)
    ofat = {}
    changes = [("source", s) for s in ("F1", "F2", "F3", "F4", "FENS", "LENS", "L1", "L2", "L3")] + \
              [("t", t) for t in (0.3, 0.4, 0.6, 0.7)] + [("M", m) for m in ("none", "v14", "la3")] + \
              [("R", r) for r in ("APP-LV", "LSTAI", "LSTAI-LV", "APP-3MM", "APP-MAJ", "LSTAI-ORD2")] + \
              [("G", g) for g in ("G1", "G2")]
    for f, lv in changes:
        key = list(DEFAULT)
        key[FACTORS.index(f)] = lv
        try:
            v = cell(df, cases, tuple(key))
        except ValueError:
            continue
        ofat[f"{f}={lv}"] = {"flip_vs_default": boot.mean(v != dflt), "flip_vs_reference": boot.mean(v != ref)}
    # one factor at a time from the reference (expert mask)
    ofat_ref = {}
    for f, lv in [("M", m) for m in ("none", "v14", "la3")] + \
                 [("R", r) for r in ("APP-LV", "LSTAI", "LSTAI-LV", "APP-3MM", "APP-MAJ", "LSTAI-ORD2")] + \
                 [("G", g) for g in ("G1", "G2")]:
        key = list(REF)
        key[FACTORS.index(f)] = lv
        try:
            v = cell(df, cases, tuple(key))
        except ValueError:
            continue
        ofat_ref[f"{f}={lv}"] = boot.mean(v != ref)
    res["_ofat_from_default"] = ofat
    res["_ofat_from_reference"] = ofat_ref
    return res


def regions(df, cases, D, ref, boot):
    out = {}
    refc = {r: cell(df, cases, REF, r) for r in REGIONS}
    dfl = {r: cell(df, cases, DEFAULT, r) for r in REGIONS}
    for r in REGIONS:
        C = matrix(df, cases, r).to_numpy()
        pres_flip = ((C >= 1) != (refc[r] >= 1)[:, None]).mean(1)
        x, y = dfl[r].astype(float), refc[r].astype(float)
        diff = x - y
        q75, q25 = np.percentile(C, [75, 25], axis=1)
        out[r] = {
            "presence_flip_grid_mean": boot.mean(pres_flip),
            "presence_flip_default": boot.mean((dfl[r] >= 1) != (refc[r] >= 1)),
            "icc_a1_default_vs_ref": index_boot(boot, lambda idx: icc_a1(x[idx], y[idx])),
            "bland_altman_default_minus_ref": {"bias": boot.mean(diff), "sd": round(float(diff.std(ddof=1)), 3),
                                               "loa": [round(float(diff.mean() - 1.96 * diff.std(ddof=1)), 2),
                                                       round(float(diff.mean() + 1.96 * diff.std(ddof=1)), 2)]},
            "ref_median_iqr": [float(np.median(y)), float(np.percentile(y, 25)), float(np.percentile(y, 75))],
            "within_scan_iqr_median": float(np.median(q75 - q25)),
            "within_scan_range_median": float(np.median(C.max(1) - C.min(1))),
        }
    return out


def strata(df, cases, D, E, ref, patients):
    refc = np.stack([cell(df, cases, REF, r) for r in ("n_pv", "n_jc", "n_it")], 1)
    margin = (refc >= 1).sum(1)
    ntot = cell(df, cases, REF, "n_total")
    t1, t2 = np.percentile(ntot, [100 / 3, 200 / 3])
    tert = np.where(ntot <= t1, "T1", np.where(ntot <= t2, "T2", "T3"))
    flips = (D.to_numpy() != ref[:, None])
    inst = instability(D.to_numpy())
    inst_e = instability(E.to_numpy())
    dflt = D[DEFAULT].to_numpy() != ref
    out = {"lesion_count_tertile_cuts": [float(t1), float(t2)]}
    for name, lab in (("reference_regions", np.where(margin <= 1, "<=1", margin.astype(str))), ("lesion_tertile", tert)):
        out[name] = {}
        for g in sorted(set(lab)):
            m = lab == g
            b = Boot(np.asarray(patients)[m])
            out[name][g] = {"n_scans": int(m.sum()), "n_patients": int(len(np.unique(np.asarray(patients)[m]))),
                            "reference_dis_met": round(float(ref[m].mean()), 4),
                            "device_default_flip": b.mean(dflt[m]), "grid_mean_flip": b.mean(flips[m].mean(1)),
                            "not_unanimous": b.mean(inst["not_unanimous"][m]), "contested": b.mean(inst["contested"][m]),
                            "expert_grid_not_unanimous": b.mean(inst_e["not_unanimous"][m]),
                            "ref_lesions_median": float(np.median(ntot[m]))}
    return out, margin, ntot


def ventricle_audit(df, lesions, cases, boot):
    """S4: expert lesions (>= 3 mm^3) — third ventricle, LST-AI priority, outside-zone lesions."""
    out = {}
    for G in ("G0", "G1"):
        L18 = [dict(case=c, **x) for c in cases for x in lesions[c]["E"] if x["G"] == G and x["conn"] == 18 and x["volume_mm3"] >= 3.0]
        L26 = [dict(case=c, **x) for c in cases for x in lesions[c]["E"] if x["G"] == G and x["conn"] == 26 and x["volume_mm3"] >= 3.0]
        d18, d26 = pd.DataFrame(L18), pd.DataFrame(L26)
        ch_app = d18["APP"] != d18["APP-LV"]
        ch_lst = d26["LSTAI"] != d26["LSTAI-LV"]
        only3 = d18["touch_third"] & ~d18["touch_lateral"]
        trans = (d18[ch_app].groupby(["APP", "APP-LV"]).size()).to_dict()
        no_zone = d18["zone_vox"].apply(lambda z: sum(z[1:]) == 0)
        pv_it = d26["hit4"] & d26["hit5"]
        jc_it = d26["hit2"] & d26["hit5"] & ~d26["hit4"]
        per_scan_changed = d18.assign(ch=ch_app).groupby("case")["ch"].any().reindex(cases).fillna(False).to_numpy()
        out[G] = {
            "expert_lesions": int(len(d18)), "expert_lesions_26conn": int(len(d26)),
            "app_to_app_lv_changed": int(ch_app.sum()), "app_to_app_lv_changed_pct": round(100 * float(ch_app.mean()), 2),
            "app_to_app_lv_transitions": {f"{k[0]}->{k[1]}": int(v) for k, v in trans.items()},
            "lstai_to_lstai_lv_changed": int(ch_lst.sum()), "lstai_to_lstai_lv_changed_pct": round(100 * float(ch_lst.mean()), 2),
            "touch_only_third_ventricle": int(only3.sum()),
            "touch_only_third_ventricle_app_regions": {str(k): int(v) for k, v in d18[only3]["APP"].value_counts().items()},
            "touch_only_third_ventricle_app_lv_regions": {str(k): int(v) for k, v in d18[only3]["APP-LV"].value_counts().items()},
            "touch_ventricle_and_infratentorial_26conn": int(pv_it.sum()),
            "of_which_only_third_ventricle": int((pv_it & d26["touch_third"] & ~d26["touch_lateral"]).sum()),
            "touch_cortex_and_infratentorial_not_ventricle_26conn": int(jc_it.sum()),
            "outside_every_zone_dwm_by_default": int(no_zone.sum()),
            "outside_every_zone_pct": round(100 * float(no_zone.mean()), 2),
            "outside_every_zone_volume_median": float(d18[no_zone]["volume_mm3"].median()) if no_zone.any() else None,
            "scans_with_a_changed_lesion": boot.mean(per_scan_changed),
        }
        # scan-level DIS changes on the expert mask
        dis = {R: cell(df, cases, ("E", -1.0, "v3", R, G)) for R in ("APP", "APP-LV", "LSTAI", "LSTAI-LV", "LSTAI-ORD2")}
        pvs = {R: cell(df, cases, ("E", -1.0, "v3", R, G), "n_pv") for R in ("APP", "APP-LV", "LSTAI", "LSTAI-LV")}
        out[G]["dis_changes"] = {
            f"{a}_vs_{b}": {"n_scans": int((dis[a] != dis[b]).sum()), "scans": [cases[i] for i in np.flatnonzero(dis[a] != dis[b])]}
            for a, b in (("APP", "APP-LV"), ("LSTAI", "LSTAI-LV"), ("LSTAI", "LSTAI-ORD2"), ("APP", "LSTAI"))}
        out[G]["pv_lesions_total"] = {R: int(v.sum()) for R, v in pvs.items()}
    return out


def indicator(df, cases, D, ref, boot):
    variants = [("F0", t, M, R, "G0") for t in (0.4, 0.5, 0.6) for M in ("v3", "v14") for R in ("APP", "APP-LV")]
    V = np.stack([cell(df, cases, k) for k in variants], 1)
    fragile = ((V.mean(1) > 0) & (V.mean(1) < 1))
    c = np.stack([cell(df, cases, DEFAULT, r) for r in ("n_pv", "n_jc", "n_it")], 1)
    present = c >= 1
    dflt = cell(df, cases, DEFAULT)
    two = present.sum(1) == 2
    min_present = np.where(present, c, 10 ** 6).min(1)
    pivotal = (dflt == 1) & two & (min_present == 1)
    union = fragile | pivotal
    A = (dflt != ref)
    Bn = instability(D.to_numpy())["not_unanimous"].astype(bool)
    out = {"n_variants": len(variants)}
    for name, flag in (("internal_variants", fragile), ("pivotal_lesion", pivotal), ("union", union)):
        out[name] = {"vs_default_differs_from_reference": flag_metrics(boot, flag, A),
                     "vs_not_unanimous_in_primary_grid": flag_metrics(boot, flag, Bn)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    root = data_root(args.data_root)
    out_dir = experiments_dir(root)
    df, lesions, record = load(out_dir)
    meta = record["scan_meta"]
    done = sorted(set(df.case) & set(record["scans"]))   # a scan file may land before its record
    df = df[df.case.isin(done)]
    checks = [v for c in done for v in record["scans"][c]["device_checks"].values()]
    clean = [c for c in done if not meta[c]["flames_in_sample"]]
    result = {"protocol": "docs/research/paper-d/PROTOCOL.md v1.0",
              "device_agreement": {"masks_checked": len(checks), "all_equal": all(v["equal"] for v in checks),
                                   "zone_map_equal_on_every_scan": all(record["scans"][c]["zone_map_equals_device"] for c in done)},
              "scans_available": len(done), "clean_set": len(clean)}

    # primary (clean set)
    pats = [meta[c]["patient"] for c in clean]
    core_res, D, E, ref, boot = core(df, clean, pats)
    result["primary"] = core_res
    result["S1_drivers"] = drivers(D, E, ref, boot, df, clean)
    result["S2_regions"] = regions(df, clean, D, ref, boot)
    result["S3_strata"], margin, ntot = strata(df, clean, D, E, ref, pats)
    result["S4_ventricles"] = ventricle_audit(df, lesions, clean, boot)
    result["S5_indicator"] = indicator(df, clean, D, ref, boot)

    # S6 sensitivity analyses
    s6 = {}
    full = done
    s6["a_with_flames_in_sample"] = core(df, full, [meta[c]["patient"] for c in full])[0]
    insample = [c for c in done if meta[c]["flames_in_sample"]]
    if insample:
        s6["a_flames_in_sample_only"] = core(df, insample, [meta[c]["patient"] for c in insample])[0]
    s6["c_pv_at_least_3"] = core(df, clean, pats, col="dis_pv3")[0]
    for ds in ("mslesseg", "ljubljana"):
        cs = [c for c in clean if meta[c]["dataset"] == ds]
        if cs:
            s6[f"d_{ds}_only"] = core(df, cs, [meta[c]["patient"] for c in cs])[0]
    reg = json.loads((cache_dir(root) / "warped" / "registration_record.json").read_text())
    qc = reg.get("qc", {})
    bad = [c for c in clean if qc.get(c, {}).get("dice_brain_warped_vs_t1", 1.0) < 0.70]
    dq = [qc[c]["dice_brain_warped_vs_t1"] for c in clean if c in qc]
    s6["e_g1_qc"] = {"n_with_qc": len(dq),
                     "dice_brain_warped_vs_t1": ({"median": float(np.median(dq)), "min": float(np.min(dq))} if dq else None),
                     "dice_brain_g0_vs_t1_median": (float(np.median([qc[c]["dice_brain_g0_vs_t1"] for c in clean if c in qc])) if dq else None),
                     "dice_ventricles_warped_vs_g0_median": (float(np.median([qc[c]["dice_ventricles_warped_vs_g0"] for c in clean if c in qc])) if dq else None),
                     "below_0_70": bad}
    if bad:
        keep = [c for c in clean if c not in bad]
        s6["e_g1_qc"]["restricted"] = core(df, keep, [meta[c]["patient"] for c in keep])[0]
    result["S6_sensitivity"] = s6

    # success criteria (protocol §9)
    p2 = result["primary"]["P2_automated"]["not_unanimous"]
    p2e = result["primary"]["P2_expert"]["not_unanimous"]
    tm = result["S1_drivers"]["_top_minus_second"]
    s4 = result["S4_ventricles"]["G0"]
    result["criteria"] = {
        "C1_fragile": {"rule": "lower bound of P2 (not unanimous, automated) >= 0.10", "lower": p2["lo"], "met": p2["lo"] >= 0.10},
        "C2_fragile_with_expert_mask": {"rule": "lower bound of P2 expert >= 0.02", "lower": p2e["lo"], "met": p2e["lo"] >= 0.02},
        "C3_single_biggest_driver": {"rule": "top-minus-second CI excludes 0", "top": tm["top"], "second": tm["second"],
                                     "diff": [tm["est"], tm["lo"], tm["hi"]], "met": tm["lo"] > 0},
        "C5_ventricle_definition_material": {"rule": ">= 1 % of expert lesions change region (APP->APP-LV, G0)",
                                             "pct": s4["app_to_app_lv_changed_pct"], "met": s4["app_to_app_lv_changed_pct"] >= 1.0},
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    print(json.dumps(result["criteria"], indent=1))


if __name__ == "__main__":
    main()
