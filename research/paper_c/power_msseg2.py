"""Paper C — power of the pre-registered MSSEG-2 study, simulated from the PILOT distributions.

Research code, not the medical device. Written 2026-10-31, before any MSSEG-2 data were requested
or seen. Uses only the public pilot candidate cache (arm A4 = open_ms longitudinal with expert change
masks, arm A2 = MSLesSeg first pairs; app rule on FLAMeS 5-fold mean; NEW-lesion candidates only;
score S_sub = the app's subtraction_signal).

Generative model of one MSSEG-2-like patient (assumptions stated in PREREGISTRATION_C.md §8):
  * stable patient (no new lesion): every candidate is false; it carries >= 1 candidate with
    probability q_any (pilot, Jeffreys-smoothed) and then its largest score is drawn from the pilot's
    per-patient LARGEST FALSE new-candidate score (tail scenario: A4, A2 or a 50/50 mixture);
  * active patient: K new lesions, P(K = 1) = 17/64 and K - 2 ~ geometric with mean 8.04 otherwise
    (MSSEG-2 final ground truth, Masson et al. 2026: 17 of 64 active patients have 1 new lesion,
    mean 4.89 new lesions over 100 patients). Each lesion yields a true candidate with probability
    p_det (pilot A4 lesion-level recall of the new-candidate set, or a pessimistic 0.6 x p_det);
    true scores are drawn from the pilot's true new-candidate scores (optionally shifted down by
    0.25 SD); its largest FALSE score is drawn like a stable patient's.
Procedures (as pre-registered): stable-conditional CF-M (PRIMARY; calibration on stable patients
only) and CF-M pooled over all patients (secondary; statistic = largest false score), both
leave-one-patient-out, alpha 0.1 and 0.2. Hypotheses H2-H4 with Holm at 0.05, power reported with
each procedure as the one tested; H1 is a falsification check (CP lower bound > alpha).
H3 (app rule) power is also given analytically for a range of true false-activity rates.

    python research/paper_c/power_msseg2.py --cache <research/paper_c/.cache/candidates.json> [--sims 4000]
"""
import argparse
import datetime
import hashlib
import json
import math
import os
import sys

import numpy as np
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import conformal as K  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
RECORDS = os.path.join(ROOT, "docs", "research", "records")
SEED = 20261031
SCENARIO_N = {"S1_training_only": (11, 29), "S2_training_plus_test": (36, 64)}
P_K1 = 17 / 64
MEAN_K_GE2 = (4.89 * 100 - 17) / 47          # E[K | K >= 2] among active patients (= 10.04)


def dev_distributions(d):
    out = {}
    for arm, units in (("A4", d["open_ms"]), ("A2", d["mslesseg"])):
        mf, tr, any_false, hit, les = [], [], 0, 0, 0
        for u in units:
            if not u.get("first_pair", True):
                continue
            c = [x for x in u["dseg"] if x["kind"] == "new" and np.isfinite(x["score_sub"])]
            f = [x["score_sub"] for x in c if not x["true"]]
            if f:
                mf.append(max(f))
                any_false += 1
            tr += [x["score_sub"] for x in c if x["true"]]
            h = set()
            for x in c:
                if x["true"]:
                    h.update(x.get("hits", []))
            hit += len(h)
            les += u["n_truth_lesions"]
        n = sum(1 for u in units if u.get("first_pair", True))
        out[arm] = {"max_false": np.array(mf), "true_scores": np.array(tr),
                    "q_any": (any_false + 0.5) / (n + 1.0), "n_patients": n,
                    "p_det": hit / les if les else float("nan")}
    return out


def draw_max_false(rng, dev, tail, size):
    if tail == "mixed":
        pick = rng.random(size) < 0.5
        a = rng.choice(dev["A4"]["max_false"], size)
        b = rng.choice(dev["A2"]["max_false"], size)
        return np.where(pick, a, b), (dev["A4"]["q_any"] + dev["A2"]["q_any"]) / 2
    return rng.choice(dev[tail]["max_false"], size), dev[tail]["q_any"]


def simulate_once(rng, dev, n_stable, n_active, tail, p_det, shift, stable_tail=None):
    """Return per-patient (is_stable, max_false, best_true, n_true_lesions, lesion_true_scores)."""
    stable_tail = stable_tail or tail
    mfs, q_s = draw_max_false(rng, dev, stable_tail, n_stable)
    has_s = rng.random(n_stable) < q_s
    mfs = np.where(has_s, mfs, -np.inf)
    mfa, q_a = draw_max_false(rng, dev, tail, n_active)
    has_a = rng.random(n_active) < q_a
    mfa = np.where(has_a, mfa, -np.inf)
    k = np.where(rng.random(n_active) < P_K1, 1, 2 + rng.geometric(1.0 / (MEAN_K_GE2 - 1.0), n_active) - 1)
    true_scores = []
    for i in range(n_active):
        det = rng.random(k[i]) < p_det
        true_scores.append(rng.choice(dev["A4"]["true_scores"], det.sum()) - shift)
    return mfs, mfa, k, true_scores


def loo_thresholds(values, alpha):
    """CF-M threshold for each leave-one-out calibration set (same as K.threshold on np.delete)."""
    v = np.asarray(values, float)
    n = len(v)
    kk = K.k_marginal(n - 1, alpha)
    if kk > n - 1:
        return np.full(n, np.inf)
    order = np.argsort(v, kind="stable")
    srt = v[order]
    rank = np.empty(n, int)
    rank[order] = np.arange(n)
    # removing the element at sorted position r: the kk-th smallest of the rest
    return np.where(rank >= kk, srt[kk - 1], srt[kk])


def evaluate(mfs, mfa, k, true_scores, alpha):
    """Pooled CF-M and stable-conditional CF-M, both leave-one-patient-out."""
    allmax = np.concatenate([mfs, mfa])
    n_s, n_a = len(mfs), len(mfa)
    res = {}
    # pooled CF-M
    lams = loo_thresholds(allmax, alpha)
    fa_s = int(np.sum(mfs > lams[:n_s]))
    det = hit = 0
    fw_a = int(np.sum(mfa > lams[n_s:]))
    for i in range(n_a):
        sel = true_scores[i][true_scores[i] > lams[n_s + i]]
        det += len(sel) > 0
        hit += len(sel)
    res["pooled"] = {"false_activity_stable": int(fa_s), "fwer_all": int(fa_s + fw_a),
                     "true_flag_active": int(det), "lesions_hit": int(hit), "lesions": int(k.sum())}
    # stable-conditional CF-M
    fa_s = int(np.sum(mfs > loo_thresholds(mfs, alpha)))
    lam_a = K.threshold(mfs.tolist(), alpha)
    det = hit = 0
    for i in range(n_a):
        sel = true_scores[i][true_scores[i] > lam_a]
        det += len(sel) > 0
        hit += len(sel)
    res["stable_conditional"] = {"false_activity_stable": int(fa_s), "true_flag_active": int(det),
                                 "lesions_hit": int(hit), "lesions": int(k.sum()),
                                 "abstains": bool(not np.isfinite(lam_a))}
    return res


def holm(pvals, level=0.05):
    order = np.argsort(pvals)
    rej = np.zeros(len(pvals), bool)
    for r, i in enumerate(order):
        if pvals[i] <= level / (len(pvals) - r):
            rej[i] = True
        else:
            break
    return rej


def run(dev, sims, rng):
    out = {}
    p4 = dev["A4"]["p_det"]
    settings = [("consistent (A4 tail)", "A4", p4, 0.0, None),
                ("consistent, pessimistic detection", "A4", 0.6 * p4, 0.25, None),
                ("heterogeneous (A2 tail)", "A2", p4, 0.0, None),
                ("mixed tail", "mixed", p4, 0.0, None),
                ("mixed tail, pessimistic detection", "mixed", 0.6 * p4, 0.25, None),
                ("A-dom violated (stable from A2 tail, active from A4)", "A4", p4, 0.0, "A2")]
    for scen, (n_s, n_a) in SCENARIO_N.items():
        for name, tail, pdet, shift, st_tail in settings:
            key = f"{scen} | {name}"
            agg = {}
            for alpha in (0.1, 0.2):
                acc = {m: {"fa": [], "det": [], "sens": [], "h1_viol": 0} for m in ("pooled", "stable_conditional")}
                pw = {m: {"H2": 0, "H3": 0, "H4": 0} for m in ("pooled", "stable_conditional")}
                for _ in range(sims):
                    mfs, mfa, k, ts = simulate_once(rng, dev, n_s, n_a, tail, pdet, shift, st_tail)
                    r = evaluate(mfs, mfa, k, ts, alpha)
                    for m in acc:
                        acc[m]["fa"].append(r[m]["false_activity_stable"] / n_s)
                        acc[m]["det"].append(r[m]["true_flag_active"] / n_a)
                        acc[m]["sens"].append(r[m]["lesions_hit"] / max(1, r[m]["lesions"]))
                        lo = K.clopper_pearson(r[m]["false_activity_stable"], n_s)[0]
                        acc[m]["h1_viol"] += lo > alpha
                    # H3: app rule false activity in stable = stable patients with >= 1 candidate
                    x_app = int(np.isfinite(mfs).sum())
                    p3 = stats.binomtest(x_app, n_s, 0.2, alternative="greater").pvalue
                    for m in pw:     # H2-H4 family evaluated with each procedure as the primary one
                        p2 = stats.binomtest(r[m]["true_flag_active"], n_a, 0.25, alternative="greater").pvalue
                        b = x_app - r[m]["false_activity_stable"]   # CF-M flag implies an app flag
                        p4_ = 0.5 ** b if b > 0 else 1.0           # exact one-sided McNemar
                        rej = holm(np.array([p2, p3, p4_]))
                        pw[m]["H2"] += rej[0]
                        pw[m]["H3"] += rej[1]
                        pw[m]["H4"] += rej[2]
                agg[f"a{alpha}"] = {
                    m: {"false_activity_stable_mean": float(np.mean(v["fa"])),
                        "true_flag_active_mean": float(np.mean(v["det"])),
                        "true_flag_active_p10_p90": [float(np.percentile(v["det"], 10)), float(np.percentile(v["det"], 90))],
                        "lesion_sensitivity_mean": float(np.mean(v["sens"])),
                        "P(H1 violation flagged)": v["h1_viol"] / sims,
                        "power_holm": {"H2_detection_gt_0.25": pw[m]["H2"] / sims,
                                       "H3_app_rule_overcalls": pw[m]["H3"] / sims,
                                       "H4_cfm_below_app_rule": pw[m]["H4"] / sims}} for m, v in acc.items()}
            out[key] = agg
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--sims", type=int, default=4000)
    args = ap.parse_args()
    raw = open(args.cache, "rb").read()
    dev = dev_distributions(json.loads(raw))
    rng = np.random.default_rng(SEED)
    # self-check: the fast leave-one-out thresholds equal the pilot's own threshold function
    chk = np.random.default_rng(1)
    for n in (5, 11, 12, 40, 100):
        for alpha in (0.1, 0.2):
            v = np.round(chk.normal(size=n), 1)
            v[chk.random(n) < 0.1] = -np.inf
            ref = [K.threshold(np.delete(v, i).tolist(), alpha) for i in range(n)]
            assert np.array_equal(loo_thresholds(v, alpha), np.array(ref)), (n, alpha)
    res = run(dev, args.sims, rng)
    h3 = {}
    for n_s in (11, 36):
        for q in (0.4, 0.5, 0.6, 0.75, 0.9):
            # reject when the one-sided exact binomial p (H0: rate <= 0.2) <= 0.05/3 (Holm, worst case)
            xs = [x for x in range(n_s + 1) if stats.binomtest(x, n_s, 0.2, alternative="greater").pvalue <= 0.05 / 3]
            h3[f"n_stable={n_s}, true rate={q}"] = float(stats.binom.sf(min(xs) - 1, n_s, q)) if xs else 0.0
    rec = {"script": "research/paper_c/power_msseg2.py", "H3_power_analytic_holm_worst_case": h3, "date": str(datetime.date.today()), "seed": SEED,
           "sims": args.sims, "candidate_cache_sha256": hashlib.sha256(raw).hexdigest(),
           "development_inputs": {a: {"n_patients": v["n_patients"], "q_any_false": v["q_any"], "p_det_new": v["p_det"],
                                      "max_false_quantiles_0_25_50_75_90_100": [float(x) for x in np.quantile(v["max_false"], [0, .25, .5, .75, .9, 1])],
                                      "n_true_scores": int(len(v["true_scores"])),
                                      "true_score_quartiles": [float(x) for x in np.quantile(v["true_scores"], [.25, .5, .75])]}
                                  for a, v in dev.items()},
           "msseg2_assumptions": {"P(K=1 | active)": P_K1, "E[K | K>=2]": MEAN_K_GE2,
                                  "sample_sizes": {k: {"stable": v[0], "active": v[1]} for k, v in SCENARIO_N.items()}},
           "results": res}
    os.makedirs(RECORDS, exist_ok=True)
    stem = os.path.join(RECORDS, "2026-10-31_paper_c_power_msseg2")
    with open(stem + ".json", "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1)
    lines = [f"Paper C power simulation (pilot-based) {rec['date']} seed {SEED} sims {args.sims}",
             "dev: " + json.dumps(rec["development_inputs"]),
             "H3 analytic power (Holm worst case): " + json.dumps({k: round(v, 3) for k, v in h3.items()})]
    for key, agg in res.items():
        for a in ("a0.1", "a0.2"):
            g = agg[a]
            for m in ("stable_conditional", "pooled"):
                v = g[m]
                pw = v["power_holm"]
                lines.append(f"{key} | {a} | {m}: false-activity(stable) {v['false_activity_stable_mean']:.3f} "
                             f"true-flag(active) {v['true_flag_active_mean']:.2f} [{v['true_flag_active_p10_p90'][0]:.2f},{v['true_flag_active_p10_p90'][1]:.2f}] "
                             f"lesion-sens {v['lesion_sensitivity_mean']:.3f} P(H1 viol) {v['P(H1 violation flagged)']:.3f} | "
                             f"power(Holm) H2 {pw['H2_detection_gt_0.25']:.3f} H3 {pw['H3_app_rule_overcalls']:.3f} H4 {pw['H4_cfm_below_app_rule']:.3f}")
    txt = "\n".join(lines)
    with open(stem + "_output.txt", "w", encoding="utf-8") as f:
        f.write(txt + "\n")
    print(txt)


if __name__ == "__main__":
    main()
