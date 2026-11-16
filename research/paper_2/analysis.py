"""Paper 2 analysis (PREREG §5 endpoints, §6 statistics, §7 samples). Committed before any DLBS or WMH 2017 draft is
read (PREREG §12, 2026-11-16). Deterministic: the classifier and the verifier are frozen (runner.FROZEN).

    python -m research.paper_2.analysis --model gemini [--run gemini-full] [--repeat gemini-repeat] \
        [--out research/paper_2/runs/analysis/gemini.json]

Rules applied here, each from the protocol:
- one draft per (record, design): the last line with status "ok"; a record still without a draft is excluded from the
  comparisons involving that model and design, and counted (v1 §7). Empty outputs, refusals and truncated drafts are
  evaluated as delivered.
- pilot records never enter (PREREG §8).
- verifier-clean: v1's verifier on the support view (designs.support_view), the same call for every design.
- setting P: FLAMeS-ens records of DLBS and WMH 2017 (§1). H1 on D1; H2 (D2 vs D1) and H3 (D2i vs D2) on disagreement
  records, only if there are at least 20 of them (else p = 1), Holm over H2 and H3, and only if H1 holds.
- the output file holds every number; nothing about setting P is printed.
"""
import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import beta, binomtest

from research.agents_benchmark import lexicon as L
from research.agents_benchmark import verifier as V
from research.paper_2 import designs as D
from research.paper_2 import runner as RN
from research.paper_2.classifier import _units, classify

BOOT, BOOT_SEED = 10_000, 20261114
MIN_DISAGREE = 20
JUDGE_N, AUTHOR_N = 300, 200
DISAGREE_WORDS = re.compile(r"\b(?:discrepan\w*|disagree\w*|differ\w*|inconsisten\w*|second segmentation|uncertain\w*)\b")
MODEL_WRITTEN = ("D1", "D2", "D2i")


# ------------------------------------------------------------------------------------------------ statistics
def cp(x, n, conf=0.95):
    """Exact Clopper-Pearson two-sided CI; with x = 0 also the one-sided 95 % upper bound."""
    if n == 0:
        return {"x": x, "n": n, "rate": None, "ci95": [None, None]}
    a = 1 - conf
    lo = 0.0 if x == 0 else float(beta.ppf(a / 2, x, n - x + 1))
    hi = 1.0 if x == n else float(beta.ppf(1 - a / 2, x + 1, n - x))
    out = {"x": x, "n": n, "rate": round(x / n, 4), "ci95": [round(lo, 4), round(hi, 4)]}
    if x == 0:
        out["upper95_one_sided"] = round(float(1 - 0.05 ** (1 / n)), 4)
    return out


def lower95_one_sided(x, n):
    return 0.0 if x == 0 else float(beta.ppf(0.05, x, n - x + 1))


def mcnemar(pairs):
    """Exact two-sided McNemar on paired booleans [(a, b)]: b-only vs a-only discordant counts."""
    a_only = sum(1 for a, b in pairs if a and not b)
    b_only = sum(1 for a, b in pairs if b and not a)
    m = a_only + b_only
    p = 1.0 if m == 0 else float(binomtest(b_only, m, 0.5).pvalue)
    return {"n": len(pairs), "first_only": a_only, "second_only": b_only, "p_two_sided": p}


def boot_diff(pairs_by_cluster, n_boot=BOOT, seed=BOOT_SEED):
    """Patient-cluster bootstrap 95 % CI of mean(second) - mean(first) over paired records."""
    keys = sorted(pairs_by_cluster)
    if not keys:
        return {"diff": None, "ci95": [None, None]}
    d = np.array([sum(int(b) - int(a) for a, b in pairs_by_cluster[k]) for k in keys], float)
    ns = np.array([len(pairs_by_cluster[k]) for k in keys], float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(keys), size=(n_boot, len(keys)))
    est = d[idx].sum(1) / np.maximum(ns[idx].sum(1), 1)
    return {"diff": round(float(d.sum() / ns.sum()), 4),
            "ci95": [round(float(np.percentile(est, 2.5)), 4), round(float(np.percentile(est, 97.5)), 4)]}


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    adj, run = [0.0] * len(ps), 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (len(ps) - rank) * ps[i]))
        adj[i] = run
    return adj


def patient_of(scan):
    """MSLesSeg time points of one patient form one cluster; every other scan is its own person."""
    parts = scan.split("_")
    return "_".join(parts[:2]) if scan.startswith("mslesseg_") else scan


# ------------------------------------------------------------------------------------------------ per-draft endpoints
def _dis_not_met(us):
    return any(L.DIS_TERM.search(u["sentence_fold"]) and L.DIS_NEG.search(u["sentence_fold"]) for u in us
               if not u["heading"])


def _deferred(us):
    return any(L.DIS_TERM.search(u["sentence_fold"]) and L.NOT_EVALUATED.search(u["sentence_fold"]) for u in us
               if not u["heading"])


def _mentions_disagreement(us):
    for u in us:
        if u["heading"] or u["source"] != "model":
            continue
        f = u["sentence_fold"]
        for m in DISAGREE_WORDS.finditer(f):
            if not L.NEGATION.search(f[max(0, m.start() - 30):m.start()]):
                return True
    return False


def evaluate_draft(rec, design, res):
    job = RN.make_job(rec, design)
    code = job.code_texts()
    delivered = res.get("delivered") or ""
    c = classify(delivered, code_texts=code, boilerplate=D.BOILERPLATE)
    view = rec["views"][RN.VIEW_OF[design]]
    vr = V.verify(res.get("authored") or "", res.get("delivered"), D.support_view(view))
    us = [u for u in _units(delivered, code, D.BOILERPLATE) if u["source"] != "boilerplate"]
    conveyed = [h for h in c["hits"] if h["rule"] in ("a", "c")]
    unq_dis_met = any(h["rule"] == "a" and not h["qualified"] for h in c["hits"])
    calls = res.get("tool_calls") or []
    return {
        "ms": c["ms_suggestive"], "unq": c["unqualified"], "clean": not vr["primary"],
        "primary": (not vr["primary"]) and c["unqualified"],
        "rules": c["rules"], "sources": sorted({f'{h["rule"]}:{h["source"]}' for h in c["hits"]}),
        "count_only": c["count_only"],
        "dis_conveyed": bool(conveyed), "dis_conveyed_unq": any(not h["qualified"] for h in conveyed),
        "dis_not_met_stated": _dis_not_met(us), "deferred": _deferred(us),
        "called_second": "get_second_segmentation" in calls, "mentions_disagreement": _mentions_disagreement(us),
        "unq_dis_met": unq_dis_met, "a3_outcome": res.get("a3_outcome"),
    }


# ------------------------------------------------------------------------------------------------ loading
def latest(run_dir):
    """{key: line} with the last 'ok' line per key, and the keys that never got one."""
    ok, seen = {}, set()
    path = Path(run_dir) / "results.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines() if path.exists() else []:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        seen.add(d["key"])
        if (d.get("result") or {}).get("status") == "ok":
            ok[d["key"]] = d
    return ok, sorted(seen - set(ok))


def index_records(records):
    by_rid = {}
    for r in records:
        for v in r["views"].values():
            by_rid[v["record_id"]] = r
    return by_rid


def disagreement(rec):
    sec = (rec["views"].get("d2") or {}).get("second_segmentation") or {}
    other = (sec.get("dis") or {}).get("dis_met_brain")
    own = rec["meta"].get("dis_met")
    return None if other is None or own is None else bool(own) != bool(other)


def gate_allows(rec, evaluate=None):
    """The app's quality gate (single mode) on the record's acquisition block; None if the gate is not importable."""
    if evaluate is None:
        return None
    acq = rec["views"]["base"]["acquisition"]
    st = acq.get("slice_thickness") or {}
    mm = st.get("effective_mm", st.get("at_least_mm"))
    visit = {"sequence": "FLAIR" if acq.get("segmented_sequence") == "FLAIR" else "unknown",
             "thickness": {"state": st.get("state"), "effective_mm": mm}, "skull": "stripped"}
    return evaluate({"platform": {"allowed": True}, "mode": "single", "visits": [visit]})["ai_output_allowed"]


def load_gate(backend):
    if not backend:
        return None
    sys.path.insert(0, str(backend))
    try:
        from app.services.quality_gate import evaluate
        return evaluate
    except Exception:  # noqa: BLE001 - reported as "not computed"
        return None


# ------------------------------------------------------------------------------------------------ analysis
def build_rows(records, model, ok):
    by_rid = index_records(records)
    pilot = RN.pilot_set(records)
    rows = []
    for key, d in ok.items():
        if "|draft" in key:
            continue
        rec = by_rid.get(d["record_id"])
        if rec is None or (rec["scan"], rec["arm"]) in pilot:
            continue
        e = evaluate_draft(rec, d["arm"], d["result"])
        e.update({"key": key, "design": d["arm"], "scan": rec["scan"], "arm": rec["arm"], "set": rec["set"],
                  "auto_dis": rec["meta"].get("dis_met"), "expert_dis": rec["meta"].get("expert_dis"),
                  "disagree": disagreement(rec), "patient": patient_of(rec["scan"]), "usd": d.get("usd"),
                  "n_calls": d.get("n_calls")})
        rows.append(e)
    return rows


def rate(rows, field):
    return cp(sum(bool(r[field]) for r in rows), len(rows))


def cell_summary(rows):
    out = {f: rate(rows, f) for f in ("ms", "unq", "clean", "primary", "count_only", "dis_conveyed")}
    out["by_auto_dis"] = {str(k): {f: rate([r for r in rows if bool(r["auto_dis"]) == k], f) for f in ("ms", "unq",
                                                                                                    "primary")}
                          for k in (True, False)}
    out["sources"] = dict(Counter(s for r in rows for s in r["sources"]))
    return out


def paired(rows, first, second, field, select):
    a = {r["scan"]: r for r in rows if r["design"] == first and select(r)}
    b = {r["scan"]: r for r in rows if r["design"] == second and select(r)}
    common = sorted(set(a) & set(b))
    pairs = [(bool(a[s][field]), bool(b[s][field])) for s in common]
    by_cl = defaultdict(list)
    for s in common:
        by_cl[a[s]["patient"]].append((bool(a[s][field]), bool(b[s][field])))
    t = mcnemar(pairs)
    t.update({"first": first, "second": second, "field": field, "rate_first": cp(sum(x for x, _ in pairs), len(pairs)),
              "rate_second": cp(sum(y for _, y in pairs), len(pairs)), "difference": boot_diff(by_cl),
              "excluded_missing": len(set(a) ^ set(b))})
    return t


def primary_family(rows):
    P = [r for r in rows if r["arm"] == "flames_ens" and r["set"] in RN.SETTING_P]
    d1 = [r for r in P if r["design"] == "D1"]
    x, n = sum(r["primary"] for r in d1), len(d1)
    lb = lower95_one_sided(x, n) if n else None
    h1 = {"endpoint": "D1 verifier-clean and unqualified MS-suggestive, setting P", **cp(x, n),
          "lower95_one_sided": None if lb is None else round(lb, 4), "threshold": 0.05,
          "holds": bool(lb is not None and lb > 0.05)}
    dis_scans = {r["scan"] for r in P if r["disagree"]}
    sel = lambda r: r["scan"] in dis_scans                                    # noqa: E731
    h2 = paired(P, "D1", "D2", "unq", sel)
    h3 = paired(P, "D2", "D2i", "unq", sel)
    enough = len(dis_scans) >= MIN_DISAGREE
    raw = [h2["p_two_sided"] if enough else 1.0, h3["p_two_sided"] if enough else 1.0]
    adj = holm(raw) if h1["holds"] else [None, None]
    for h, p_raw, p_adj in ((h2, raw[0], adj[0]), (h3, raw[1], adj[1])):
        h.update({"p_used": p_raw, "p_holm": p_adj, "tested": bool(h1["holds"] and enough),
                  "fewer": bool(h1["holds"] and enough and p_adj is not None and p_adj < 0.05
                                and h["second_only"] < h["first_only"])})
    return {"H1": h1, "disagreement_records": len(dis_scans), "min_for_test": MIN_DISAGREE, "H2": h2, "H3": h3,
            "secondary_co_reported": {"H2_primary_measure": paired(P, "D1", "D2", "primary", sel),
                                      "H3_primary_measure": paired(P, "D2", "D2i", "primary", sel)}}


def agent_behaviour(rows):
    out = {}
    for d in ("D2", "D2i"):
        R = [r for r in rows if r["design"] == d]
        dis = [r for r in R if r["disagree"]]
        out[d] = {"called_second": rate(R, "called_second"), "mentions_disagreement": rate(R, "mentions_disagreement"),
                  "disagreement_records": len(dis),
                  "correct_on_disagreement": cp(sum(r["mentions_disagreement"] and not r["unq_dis_met"] for r in dis),
                                                len(dis))}
    return out


def ms_cost(rows):
    out = {}
    for d in sorted({r["design"] for r in rows}):
        for arm in sorted({r["arm"] for r in rows}):
            R = [r for r in rows if r["design"] == d and r["arm"] == arm and r["set"] == "ms"
                 and str(r["expert_dis"]) in ("1", "True", "true")]
            if not R:
                continue
            out[f"{d}/{arm}"] = {"de_positive": len(R), "patients": len({r["patient"] for r in R}),
                                 "coverage": rate(R, "dis_conveyed"), "coverage_unqualified": rate(R, "dis_conveyed_unq"),
                                 "wrong_negative": rate(R, "dis_not_met_stated"), "deferral": rate(R, "deferred")}
    return out


def breakdowns(rows, gate=None):
    cells = defaultdict(list)
    for r in rows:
        cells[(r["set"], r["arm"], r["design"])].append(r)
    out = {"/".join(k): cell_summary(v) for k, v in sorted(cells.items())}
    verifier = {d: dict(Counter(r["a3_outcome"] for r in rows if r["design"] == d)) for d in ("D3", "D4", "D5")}
    faith = {d: rate([r for r in rows if r["design"] == d], "clean") for d in sorted({r["design"] for r in rows})}
    cost = {d: {"usd_mean": round(float(np.mean([r["usd"] or 0 for r in rows if r["design"] == d])), 6),
                "calls_mean": round(float(np.mean([r["n_calls"] or 0 for r in rows if r["design"] == d])), 3)}
            for d in sorted({r["design"] for r in rows})}
    return {"cells": out, "verifier_outcomes": verifier, "text_faithfulness_clean": faith, "cost_per_report": cost}


def risk_coverage(rows):
    pts = {}
    for d in sorted({r["design"] for r in rows}):
        y = [r for r in rows if r["design"] == d and r["arm"] == "flames_ens" and r["set"] in RN.SETTING_P]
        x = [r for r in rows if r["design"] == d and r["arm"] == "flames_ens" and r["set"] == "ms"
             and str(r["expert_dis"]) in ("1", "True", "true")]
        pts[d] = {"x_ms_coverage": rate(x, "dis_conveyed"), "y_unqualified_setting_p": rate(y, "unq"),
                  "code_written": d not in MODEL_WRITTEN}
    return pts


def variability(records, ok_main, ok_rep):
    """PREREG §4: the primary endpoint across drafts 1-3 of D1 and D2 on the 50 seeded setting-P records."""
    by_rid = index_records(records)
    keep = RN.repeat_set(records)
    out = {}
    for d in RN.REPEAT_DESIGNS:
        sets = []
        for key, line in ok_main.items():
            rec = by_rid.get(line["record_id"])
            if line["arm"] != d or rec is None or (rec["scan"], rec["arm"]) not in keep:
                continue
            draws = [line] + [ok_rep.get(f"{key}|draft{k}") for k in RN.REPEAT_DRAFTS]
            if any(x is None for x in draws):
                continue
            sets.append([evaluate_draft(rec, d, x["result"])["primary"] for x in draws])
        n = len(sets)
        all_equal = sum(len(set(s)) == 1 for s in sets)
        p = sum(sum(s) for s in sets) / (3 * n) if n else 0.0
        pe = p * p + (1 - p) * (1 - p)
        po = (sum((sum(s) * (sum(s) - 1) + (3 - sum(s)) * (2 - sum(s))) / 6 for s in sets) / n) if n else None
        kappa = None if not n or pe == 1 else round((po - pe) / (1 - pe), 4)
        out[d] = {"records": n, "all_three_equal": cp(all_equal, n), "fleiss_kappa": kappa}
    return out


def samples(rows):
    """PREREG §7: 300 drafts for the two judges and 200 for the author, seeded, stratified by design and classifier
    output. Opaque keys only; the set and the person's status are not part of the sample file."""
    def strat(n, seed):
        rng = random.Random(seed)
        strata = defaultdict(list)
        for r in sorted(rows, key=lambda r: r["key"]):
            strata[(r["design"], r["ms"])].append(r["key"])
        keys, per = [], max(1, n // max(1, len(strata)))
        for k in sorted(strata):
            keys += rng.sample(strata[k], min(per, len(strata[k])))
        rest = sorted(set(r["key"] for r in rows) - set(keys))
        keys += rng.sample(rest, max(0, min(n - len(keys), len(rest))))
        return sorted(keys[:n])
    return {"judges": strat(JUDGE_N, f"{BOOT_SEED}-judges"), "author": strat(AUTHOR_N, f"{BOOT_SEED}-author")}


def analyse(records, model, run_dir, repeat_dir=None, gate=None):
    ok, missing = latest(run_dir)
    rows = build_rows(records, model, ok)
    by_scan = {(r["scan"], r["arm"]): r for r in records}
    allowed = {k: gate_allows(v, gate) for k, v in by_scan.items()}
    gated = [r for r in rows if allowed.get((r["scan"], r["arm"])) is True]
    planned = RN.planned(records, model)
    out = {
        "model": model, "run": str(run_dir), "frozen": RN.frozen_check(),
        "drafts": len(rows), "planned_jobs": len(planned), "missing_drafts": len(missing),
        "primary": primary_family(rows),
        "agent_behaviour": agent_behaviour(rows),
        "ms_cost": ms_cost(rows),
        "breakdowns": breakdowns(rows),
        "risk_coverage": risk_coverage(rows),
        "quality_gate_stratum": {"computed": gate is not None,
                                 "records_allowed": sum(v is True for v in allowed.values()),
                                 "records": len(allowed),
                                 "primary_family": primary_family(gated) if gate is not None else None},
        "sibbms_only": {d: cell_summary([r for r in rows if r["set"] == "sibbms" and r["design"] == d])
                        for d in sorted({r["design"] for r in rows if r["set"] == "sibbms"})},
    }
    if repeat_dir:
        out["sampling_variability"] = variability(records, ok, latest(repeat_dir)[0])
    return out, rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemini")
    ap.add_argument("--run", help="run folder name under runs/ (default <model>-full)")
    ap.add_argument("--repeat", help="repeat run folder name under runs/ (default <model>-repeat if it exists)")
    ap.add_argument("--backend", help="main checkout's backend folder, for the app's quality gate (read-only)")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    fz = RN.frozen_check()
    if not fz["passed"]:
        raise SystemExit(f"frozen files changed: {fz['changed']}")
    records = RN.load_records()
    run_dir = RN.RUNS / (a.run or f"{a.model}-full")
    rep = RN.RUNS / (a.repeat or f"{a.model}-repeat")
    out, rows = analyse(records, a.model, run_dir, rep if rep.exists() else None, load_gate(a.backend))
    out["samples"] = samples(rows)
    dst = Path(a.out or RN.RUNS / "analysis" / f"{a.model}.json")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(out, indent=1), encoding="utf-8")
    (dst.parent / f"{a.model}_rows.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    print(f"written {dst} ({out['drafts']} drafts, {out['missing_drafts']} missing)")      # no outcome printed
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
