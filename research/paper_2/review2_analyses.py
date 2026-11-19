"""A4 and A5 on the delivered reports (PREREG §12, 2026-11-19), post hoc, 0 USD. No end point, classifier or rule of the
registration changes; every number here is labelled post hoc.

A4, statement level. Setting P (FLAMeS ensemble, DLBS and WMH 2017), every model and model-written design that exists
    (D1, D2, D2i; post hoc D1c, D2n; and D2p, D1f, D2f once their runs are analysed). A statement is a distinct sentence
    with a rule (a) or (b) hit of the frozen classifier, plus the report's rule (c) statement; it is qualified as the
    frozen classifier qualifies it. Per cell: statements per report, the share qualified, and the count distribution.
    Within each model: logistic GEE (exchangeable) of "statement qualified" on design (reference D1), clustered by
    report, and by person as a check. Each increase of the sentence-level end point from D1 to another design of the
    same model is split into "more statements" and "less qualification per statement": with q the per-statement
    qualification share and N a report's statement count, P(unqualified report) = 1 - q^N; the counterfactual applies
    D1's q to the other design's counts; both orders are averaged (Shapley), and an empirical version (D1's observed
    rate per count stratum, 1, 2, 3, >= 4) is the check. 95 % CIs from a bootstrap over people (paired).
A5, classifier robustness on the delivered reports. Every model and model-written design, setting P and SibBMS: the
    frozen classifier's MS-suggestive and unqualified rates next to the sensitivity classifier's (`classifier_sens.py`),
    the explicit-DIS-met-only end point (rule (a) without a qualifier, `unq_dis_met`), and a check that needs no ground
    truth: reports MS-suggestive by rule (c) alone on records with at most one lesion, where (c) is impossible.

    python -m research.paper_2.review2_analyses a4      -> runs/analysis/statement_level.json
    python -m research.paper_2.review2_analyses a5      -> runs/analysis/classifier_sensitivity.json
"""
import argparse
import json
from collections import Counter, defaultdict

import numpy as np

from research.paper_2 import analysis as AN
from research.paper_2 import classifier as C
from research.paper_2 import classifier_sens as CS
from research.paper_2 import designs as D
from research.paper_2 import review_analyses as RA
from research.paper_2 import runner as RN

POSTHOC = {"D1c": "posthoc-{a}-D1c", "D2n": "posthoc-{a}-D2n", "D2p": "posthoc-{a}-D2p", "D1f": "posthoc-{a}-D1f",
           "D2f": "posthoc-{a}-D2f"}
REGISTERED = ("D1", "D2", "D2i")
ORDER = ("D1", "D2", "D2i", "D1c", "D2n", "D2p", "D1f", "D2f")
NB = 2000


def runs_of(alias):
    """(design, run folder) for every model-written design of this model that has a results file."""
    out = []
    reg = RN.RUNS / RA.RUN_OF[alias]
    if (reg / "results.jsonl").exists():
        out += [(d, reg) for d in REGISTERED]
    for d, pat in POSTHOC.items():
        rd = RN.RUNS / pat.format(a=alias)
        if (rd / "results.jsonl").exists():
            out.append((d, rd))
    return out


def reports(alias, sets):
    """{design: {scan: text}} for FLAMeS-ens, non-pilot records of the given sets; the last 'ok' line per key."""
    recs = RN.load_records()
    pilot = RN.pilot_set(recs)
    by_rid = {v["record_id"]: r for r in recs if r["arm"] == "flames_ens" and (r["scan"], r["arm"]) not in pilot
              for v in r["views"].values()}
    cache = {}
    out = defaultdict(dict)
    for d, rd in runs_of(alias):
        if rd not in cache:
            cache[rd] = AN.latest(rd)[0]
        for line in cache[rd].values():
            rec = by_rid.get(line["record_id"])
            if line["arm"] != d or rec is None or rec["set"] not in sets:
                continue
            out[d][rec["scan"]] = {"text": line["result"].get("delivered") or "", "set": rec["set"],
                                   "lesions": rec["views"]["base"]["lesions"]["total_count"]}
    return out


def statements(text):
    c = C.classify(text, code_texts=[], boilerplate=D.BOILERPLATE)
    sent = {}
    for h in c["hits"]:
        if h["rule"] in ("a", "b"):
            sent[h["text"]] = sent.get(h["text"], True) and h["qualified"]
    st = list(sent.values()) + [h["qualified"] for h in c["hits"] if h["rule"] == "c"]
    assert (any(not q for q in st)) == c["unqualified"]
    return st, c


# ------------------------------------------------------------------------------------------------------------ A4
def _components(n1, u1, n2, u2):
    """n: statement counts per report; u: unqualified statements per report (same people, same order)."""
    q1 = 1 - u1.sum() / n1.sum() if n1.sum() else 1.0
    q2 = 1 - u2.sum() / n2.sum() if n2.sum() else 1.0
    f = lambda n, q: float(np.mean(np.where(n > 0, 1 - q ** n, 0.0)))               # noqa: E731
    r1, r2 = f(n1, q1), f(n2, q2)
    cf12, cf21 = f(n2, q1), f(n1, q2)                 # D2's counts with D1's q; D1's counts with D2's q
    more = ((cf12 - r1) + (r2 - cf21)) / 2
    less = ((r2 - cf12) + (cf21 - r1)) / 2
    return {"q_first": q1, "q_second": q2, "model_first": r1, "model_second": r2, "more_statements": more,
            "less_qualification": less, "cf_second_counts_first_q": cf12}


def _empirical(n1, unq1, n2):
    k1, k2 = np.minimum(n1, 4), np.minimum(n2, 4)
    p = {k: (unq1[k1 == k].mean() if (k1 == k).any() else None) for k in range(5)}
    for k in range(1, 5):                              # an empty stratum borrows the nearest lower one
        if p[k] is None:
            p[k] = p[k - 1] if p[k - 1] is not None else 0.0
    return float(np.mean([p[k] for k in k2]))


def a4():
    import statsmodels.api as sm
    res = {"note": "post hoc (PREREG §12, 2026-11-19); exploratory; setting P, FLAMeS ensemble", "cells": {}, "gee": {},
           "decomposition": {}}
    for alias in RA.RUN_OF:
        reps = reports(alias, RN.SETTING_P)
        per = {}
        for d in [x for x in ORDER if x in reps]:
            rows = {}
            for scan, r in reps[d].items():
                st, c = statements(r["text"])
                rows[scan] = {"n": len(st), "u": sum(not q for q in st), "q": st, "unq": c["unqualified"]}
            per[d] = rows
            ns = [v["n"] for v in rows.values()]
            nst = sum(ns)
            res["cells"][f"{alias}/{d}"] = {
                "reports": len(rows), "statements": nst,
                "statements_per_report": round(nst / len(rows), 3) if rows else None,
                "statements_per_ms_report": round(nst / max(1, sum(n > 0 for n in ns)), 3),
                "share_qualified": AN.cp(sum(sum(v["q"]) for v in rows.values()), nst),
                "count_distribution": dict(sorted(Counter(min(n, 6) for n in ns).items())),
                "unqualified_reports": AN.cp(sum(v["unq"] for v in rows.values()), len(rows))}
        designs = [d for d in ORDER if d in per]
        if len(designs) > 1 and "D1" in designs:
            y, X, g_rep, g_person = [], [], [], []
            for d in designs:
                for scan, v in per[d].items():
                    for q in v["q"]:
                        y.append(int(q))
                        X.append([1.0] + [float(d == e) for e in designs[1:]])
                        g_rep.append(f"{d}|{scan}")
                        g_person.append(scan)
            y, X = np.array(y), np.array(X)
            out = {"statements": int(len(y)), "reference": "D1"}
            for name, groups in (("by_report", g_rep), ("by_person", g_person)):
                codes = {k: i for i, k in enumerate(sorted(set(groups)))}
                try:
                    fit = sm.GEE(y, X, groups=np.array([codes[k] for k in groups]), family=sm.families.Binomial(),
                                 cov_struct=sm.cov_struct.Exchangeable()).fit()
                    ci = fit.conf_int()
                    out[name] = {d: {"odds_ratio": round(float(np.exp(fit.params[i + 1])), 3),
                                     "ci95": [round(float(np.exp(ci[i + 1][0])), 3), round(float(np.exp(ci[i + 1][1])), 3)]}
                                 for i, d in enumerate(designs[1:])}
                except Exception as e:  # noqa: BLE001 - e.g. no variation in a design; reported
                    out[name] = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
            res["gee"][alias] = out
        for d in designs:
            if d == "D1":
                continue
            common = sorted(set(per["D1"]) & set(per[d])) if "D1" in per else []
            if not common:
                continue
            n1 = np.array([per["D1"][s]["n"] for s in common])
            u1 = np.array([per["D1"][s]["u"] for s in common])
            n2 = np.array([per[d][s]["n"] for s in common])
            u2 = np.array([per[d][s]["u"] for s in common])
            o1 = np.array([per["D1"][s]["unq"] for s in common], float)
            o2 = np.array([per[d][s]["unq"] for s in common], float)
            comp = _components(n1, u1, n2, u2)
            emp = _empirical(n1, o1, n2)
            rng = np.random.default_rng(AN.BOOT_SEED)
            bs = defaultdict(list)
            for _ in range(NB):
                i = rng.integers(0, len(common), len(common))
                b = _components(n1[i], u1[i], n2[i], u2[i])
                for k in ("more_statements", "less_qualification"):
                    bs[k].append(b[k])
                bs["observed_increase"].append(o2[i].mean() - o1[i].mean())
                bs["statements_per_report_difference"].append(n2[i].mean() - n1[i].mean())
            ci = {k: [round(float(np.percentile(v, 2.5)), 4), round(float(np.percentile(v, 97.5)), 4)]
                  for k, v in bs.items()}
            tot = comp["model_second"] - comp["model_first"]
            res["decomposition"][f"{alias}: D1 -> {d}"] = {
                "n_people": len(common), "observed_first": round(float(o1.mean()), 4),
                "observed_second": round(float(o2.mean()), 4),
                "observed_increase": round(float(o2.mean() - o1.mean()), 4),
                "model_implied_first": round(comp["model_first"], 4), "model_implied_second": round(comp["model_second"], 4),
                "q_per_statement_first": round(comp["q_first"], 4), "q_per_statement_second": round(comp["q_second"], 4),
                "statements_per_report_first": round(float(n1.mean()), 3),
                "statements_per_report_second": round(float(n2.mean()), 3),
                "more_statements": round(comp["more_statements"], 4),
                "less_qualification": round(comp["less_qualification"], 4),
                "share_from_more_statements": round(comp["more_statements"] / tot, 3) if abs(tot) > 1e-9 else None,
                "empirical_cf_second_counts_first_rates": round(emp, 4),
                "empirical_more_statements": round(emp - float(o1.mean()), 4),
                "empirical_less_qualification": round(float(o2.mean()) - emp, 4),
                "ci95_people_bootstrap": ci}
        print(f"[a4] {alias} done", flush=True)
    p = RN.RUNS / "analysis" / "statement_level.json"
    p.write_text(json.dumps(res, indent=1))
    print(f"[a4] -> {p}")
    return res


# ------------------------------------------------------------------------------------------------------------ A5
def a5():
    res = {"note": "post hoc (PREREG §12, 2026-11-19); exploratory; FLAMeS ensemble", "frozen_check": RN.frozen_check(),
           "cells": {}}
    for alias in RA.RUN_OF:
        reps = reports(alias, RN.SETTING_P + ("sibbms",))
        for d in [x for x in ORDER if x in reps]:
            for group, sets in (("setting_p", RN.SETTING_P), ("sibbms", ("sibbms",))):
                sel = [r for r in reps[d].values() if r["set"] in sets]
                if not sel:
                    continue
                n = len(sel)
                cnt = Counter()
                for r in sel:
                    f = C.classify(r["text"], code_texts=[], boilerplate=D.BOILERPLATE)
                    s = CS.classify(r["text"], code_texts=[], boilerplate=D.BOILERPLATE)
                    cnt["ms"] += f["ms_suggestive"]
                    cnt["unq"] += f["unqualified"]
                    cnt["ms_sens"] += s["ms_suggestive"]
                    cnt["unq_sens"] += s["unqualified"]
                    cnt["ms_dis_met"] += any(h["rule"] == "a" for h in f["hits"])
                    cnt["unq_dis_met"] += any(h["rule"] == "a" and not h["qualified"] for h in f["hits"])
                    cnt["c_only"] += f["rules"] == ["c"]
                    cnt["c_only_sens"] += s["rules"] == ["c"]
                    impossible = r["lesions"] <= 1
                    cnt["c_only_impossible"] += impossible and f["rules"] == ["c"]
                    cnt["c_only_impossible_sens"] += impossible and s["rules"] == ["c"]
                    cnt["ms_to_not_ms"] += f["ms_suggestive"] and not s["ms_suggestive"]
                    cnt["not_ms_to_ms"] += s["ms_suggestive"] and not f["ms_suggestive"]
                    cnt["unq_to_not_unq"] += f["unqualified"] and not s["unqualified"]
                    cnt["records_at_most_1_lesion"] += impossible
                res["cells"][f"{alias}/{d}/{group}"] = {
                    "n": n, "ms_frozen": AN.cp(cnt["ms"], n), "ms_sensitivity": AN.cp(cnt["ms_sens"], n),
                    "unqualified_frozen": AN.cp(cnt["unq"], n), "unqualified_sensitivity": AN.cp(cnt["unq_sens"], n),
                    "ms_explicit_dis_met": AN.cp(cnt["ms_dis_met"], n), "unq_dis_met": AN.cp(cnt["unq_dis_met"], n),
                    "rule_c_only_frozen": cnt["c_only"], "rule_c_only_sensitivity": cnt["c_only_sens"],
                    "records_at_most_1_lesion": cnt["records_at_most_1_lesion"],
                    "rule_c_only_on_at_most_1_lesion_frozen": cnt["c_only_impossible"],
                    "rule_c_only_on_at_most_1_lesion_sensitivity": cnt["c_only_impossible_sens"],
                    "changed": {"ms_to_not_ms": cnt["ms_to_not_ms"], "not_ms_to_ms": cnt["not_ms_to_ms"],
                                "unq_to_not_unq": cnt["unq_to_not_unq"]}}
        print(f"[a5] {alias} done", flush=True)
    p = RN.RUNS / "analysis" / "classifier_sensitivity.json"
    p.write_text(json.dumps(res, indent=1))
    print(f"[a5] -> {p}")
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["a4", "a5"])
    a = ap.parse_args(argv)
    (a4 if a.cmd == "a4" else a5)()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
