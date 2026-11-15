"""Analysis (PREREG sections 5 and 7). Offline, deterministic; reads every run under config.RUNS_DIR.

    python -m research.agents_benchmark.analysis [--out docs/research/agents-benchmark/results]

Writes summary.json, per_report.csv (no measurements, no text) and tables.md.
"""
import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import beta, binom

from . import config
from . import verifier as V
from . import verifier_frozen_v2 as V2
from .arms import view_for
from .records import load_manifest, load_record
from .runner import read_results

ALIASES = ("haiku", "sonnet", "gemini", "gemma")
FAMILY = [("haiku", "A0", "A3"), ("haiku", "A1", "A3"), ("haiku", "A2", "A3"), ("haiku", "A1", "A2"),
          ("gemini", "A0", "A3"), ("gemini", "A1", "A3"), ("gemini", "A2", "A3"), ("gemini", "A1", "A2"),
          ("sonnet", "A0", "A3"), ("gemma", "A0", "A3")]
N_BOOT = 10000


def clopper_pearson(x, n, conf=0.95):
    if n == 0:
        return [None, None]
    a = 1 - conf
    lo = 0.0 if x == 0 else float(beta.ppf(a / 2, x, n - x + 1))
    hi = 1.0 if x == n else float(beta.ppf(1 - a / 2, x + 1, n - x))
    return [lo, hi]


def mcnemar_exact(a, b):
    a, b = np.asarray(a, bool), np.asarray(b, bool)
    n10, n01 = int((a & ~b).sum()), int((~a & b).sum())
    k = n10 + n01
    p = 1.0 if k == 0 else min(1.0, 2 * binom.cdf(min(n10, n01), k, 0.5))
    return {"first_only": n10, "second_only": n01, "p_two_sided": float(p)}


def holm(pvals):
    p = np.array([1.0 if v is None else float(v) for v in pvals])
    order = np.argsort(p, kind="stable")
    m, run, adj = p.size, 0.0, np.empty(p.size)
    for r, i in enumerate(order):
        run = max(run, min(1.0, (m - r) * p[i]))
        adj[i] = run
    return adj.tolist()


def cluster_boot(values_by_cluster, n_boot=N_BOOT, seed=config.SEED):
    """Percentile CI of a pooled proportion (or mean) resampling clusters (patients)."""
    keys = sorted(values_by_cluster)
    if not keys:
        return [None, None]
    sums = np.array([np.sum(values_by_cluster[k]) for k in keys], float)
    ns = np.array([len(values_by_cluster[k]) for k in keys], float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(keys), size=(n_boot, len(keys)))
    est = sums[idx].sum(1) / np.maximum(ns[idx].sum(1), 1)
    return [float(np.percentile(est, 2.5)), float(np.percentile(est, 97.5))]


def evaluate_all():
    man = load_manifest()
    meta = {r["record_id"]: r for r in man["records"]}
    pilot = set(man["subsets"]["pilot"])
    out = []
    for alias in ALIASES:
        for subset in ("main", "injection", "multilingual"):
            for r in read_results(alias, subset):
                if r["record_id"] in pilot or r["result"].get("status") != "ok":
                    out.append(_row(r, alias, subset, meta, None, None))
                    continue
                rec = load_record(r["record_id"])
                view = view_for(rec, r["lang"], r["payload"])
                res = V.verify(r["result"].get("authored") or "", r["result"].get("delivered"), view)
                first = None
                if r["arm"] == "A3" and r["result"].get("attempts"):
                    first = _a3_first(r, view)
                raw = None
                if r["arm"] == "A0" and r["result"].get("authored_raw") is not None:
                    raw = V.verify(r["result"]["authored_raw"], None, view)
                v2 = V2.verify(r["result"].get("authored") or "", r["result"].get("delivered"), view)
                out.append(_row(r, alias, subset, meta, res, {"first": first, "raw": raw, "v2": v2}))
    return out, man


def _a3_first(r, view):
    from .arms import A3
    job = A3.__new__(A3)
    job.view, job.lang = view, r["lang"]
    assembled, fails = A3.check(job, r["result"]["attempts"][0]["text"])
    if assembled is None:
        return {"primary": None, "format_failure": True}
    res = V.verify(assembled, None, view)
    return {"primary": res["primary"], "format_failure": False, "by_class": res["by_class"]}


def _row(r, alias, subset, meta, res, extra):
    m = meta[r["record_id"]]
    row = {"model": alias, "subset": subset, "record_id": r["record_id"], "arm": r["arm"], "lang": r["lang"],
           "payload": r["payload"], "stratum": m["stratum"], "condition": m["condition"], "patient": m["patient"],
           "status": r["result"].get("status"), "usd": r.get("usd", 0.0), "n_calls": r.get("n_calls"),
           "truncated": any(c.get("stop_reason") == "max_tokens" for c in r.get("calls") or []),
           "latency_s": sum((c.get("latency_s") or 0) for c in r.get("calls") or []),
           "a3_outcome": r["result"].get("a3_outcome"), "tool_steps": r["result"].get("tool_steps"),
           "dis_replaced": r["result"].get("dis_statements_replaced"),
           "injection_reachable": r["result"].get("injection_reachable")}
    if res is None:
        row["evaluable"] = False
        return row
    row.update({"evaluable": True, "primary": res["primary"], "n_elements": res["n_elements"],
                **{f"n_{k}": v for k, v in res["by_class"].items()},
                "extended": res["extended_any"], "primary_or_extended": res["primary"] or res["extended_any"],
                "omission_any": res["omission_any"],
                **{f"om_{k}": bool(v) for k, v in res["omissions"].items()},
                "hc_unsafe": bool(res["hc_unsafe"]),
                "injection_success": bool(res["injection"].get(r["payload"])) if r["payload"] else None,
                "inj_detect": dict(res["injection"]),
                "elements": res["elements"]})
    if extra and extra.get("first"):
        row["a3_first_primary"] = extra["first"].get("primary")
    if extra and extra.get("raw"):
        row["a0_raw_primary"] = extra["raw"]["primary"]
    if extra and extra.get("v2"):
        row["primary_frozen_v2"] = extra["v2"]["primary"]   # PREREG deviation 5: sensitivity with the frozen verifier
    return row


def rate(rows, key):
    vals = [bool(r[key]) for r in rows if r.get("evaluable") and r.get(key) is not None]
    by_pat = defaultdict(list)
    for r in rows:
        if r.get("evaluable") and r.get(key) is not None:
            by_pat[r["patient"]].append(bool(r[key]))
    x, n = sum(vals), len(vals)
    return {"x": x, "n": n, "rate": (x / n) if n else None, "ci_cp": clopper_pearson(x, n),
            "ci_cluster": cluster_boot(by_pat), "rule_of_three_upper": (3 / n) if (n and x == 0) else None}


def paired(rows, alias, a1, a2, key="primary"):
    by = defaultdict(dict)
    for r in rows:
        if r["model"] == alias and r["subset"] == "main" and r.get("evaluable"):
            by[r["record_id"]][r["arm"]] = r
    common = [k for k, v in by.items() if a1 in v and a2 in v]
    x1 = [bool(by[k][a1][key]) for k in common]
    x2 = [bool(by[k][a2][key]) for k in common]
    mc = mcnemar_exact(x1, x2)
    diff_by_pat = defaultdict(list)
    for k in common:
        diff_by_pat[by[k][a1]["patient"]].append(float(by[k][a1][key]) - float(by[k][a2][key]))
    ci = cluster_boot(diff_by_pat)
    d = (sum(x1) - sum(x2)) / len(common) if common else None
    return {"model": alias, "first": a1, "second": a2, "n_pairs": len(common), "rate_first": (sum(x1) / len(common))
            if common else None, "rate_second": (sum(x2) / len(common)) if common else None, "difference": d,
            "difference_ci_cluster": ci, **mc}


def summarise(rows, man):
    s = {"n_rows": len(rows), "models": {}, "family": [], "secondary": {}}
    main = [r for r in rows if r["subset"] == "main"]
    for alias in ALIASES:
        for arm in ("A0", "A1", "A2", "A3"):
            rr = [r for r in main if r["model"] == alias and r["arm"] == arm]
            if not rr:
                continue
            ev = [r for r in rr if r.get("evaluable")]
            cell = {"n_drafts": len(rr), "n_evaluable": len(ev), "primary": rate(ev, "primary"),
                    "by_class": {c: rate(ev, f"n_{c}") for c in ("E1", "E2", "E3", "E4")},
                    "omission_any": rate(ev, "omission_any"),
                    "omission_items": {k: rate(ev, f"om_{k}") for k in ("count", "dis", "regions", "longitudinal")},
                    "extended": rate(ev, "extended"), "S1_primary_or_extended": rate(ev, "primary_or_extended"),
                    "S2_primary_frozen_v2": rate(ev, "primary_frozen_v2"),
                    "truncated": sum(r["truncated"] for r in rr) / len(rr),
                    "usd_total": sum(r["usd"] for r in rr), "usd_per_report": sum(r["usd"] for r in rr) / len(rr),
                    "calls_per_report": sum(r["n_calls"] or 0 for r in rr) / len(rr),
                    "latency_s_per_report": sum(r["latency_s"] for r in rr) / len(rr),
                    "by_stratum": {st: rate([r for r in ev if r["stratum"] == st], "primary")
                                   for st in ("i_thick", "i_thin", "ii", "iii", "v")},
                    "hc_unsafe": rate([r for r in ev if r["stratum"] == "v"], "hc_unsafe")}
            if arm == "A3":
                cell["a3_outcomes"] = dict(Counter(r["a3_outcome"] for r in rr))
                cell["a3_blocked"] = rate([{**r, "b": r["a3_outcome"] == "blocked"} for r in ev], "b")
                cell["a3_first_draft_primary"] = rate([r for r in ev if r.get("a3_first_primary") is not None],
                                                      "a3_first_primary")
            if arm == "A0":
                cell["a0_raw_primary"] = rate([r for r in ev if r.get("a0_raw_primary") is not None], "a0_raw_primary")
            if arm == "A2":
                cell["tool_steps_mean"] = float(np.mean([r["tool_steps"] or 0 for r in rr]))
            s["models"].setdefault(alias, {})[arm] = cell
    fam = [paired(rows, *f) for f in FAMILY]
    fam = [f for f in fam if f["n_pairs"]]
    for f, p in zip(fam, holm([f["p_two_sided"] for f in fam])):
        f["p_holm"] = p
    s["family"] = fam
    inj = [r for r in rows if r["subset"] == "injection"]
    # baseline: the same detector on the drafts of the SAME records without any injected text (main subset)
    main_by = {(r["model"], r["arm"], r["record_id"]): r for r in rows if r["subset"] == "main" and r.get("evaluable")}
    for r in inj:
        b = main_by.get((r["model"], r["arm"], r["record_id"]))
        r["injection_baseline"] = (bool(b["inj_detect"].get(r["payload"])) if b and r.get("evaluable") else None)
    s["secondary"]["injection"] = {f"{a}/{arm}": {**rate([r for r in inj if r["model"] == a and r["arm"] == arm],
                                                       "injection_success"),
                                                  "baseline_same_records": rate([r for r in inj if r["model"] == a
                                                                                 and r["arm"] == arm], "injection_baseline"),
                                                  "reachable_A0": sum(1 for r in inj if r["model"] == a and r["arm"] == arm
                                                                      and r.get("injection_reachable"))}
                                   for a in ALIASES for arm in ("A0", "A1", "A2", "A3")
                                   if any(r["model"] == a and r["arm"] == arm for r in inj)}
    ml = [r for r in rows if r["subset"] == "multilingual"]
    s["secondary"]["multilingual"] = {f"{a}/{arm}/{lang}": rate([r for r in ml if r["model"] == a and r["arm"] == arm
                                                                 and r["lang"] == lang], "primary")
                                      for a in ALIASES for arm in ("A0", "A1", "A2", "A3") for lang in ("es", "de")
                                      if any(r["model"] == a and r["arm"] == arm and r["lang"] == lang for r in ml)}
    kinds = defaultdict(Counter)
    for r in main:
        for e in r.get("elements") or []:
            kinds[f"{r['model']}/{r['arm']}"][f"{e['cls']}:{e['kind'].split('+')[0]}"] += 1
    s["secondary"]["element_kinds"] = {k: dict(v.most_common(12)) for k, v in kinds.items()}
    s["n_analysis_records"] = len([r for r in man["records"] if r["record_id"] not in set(man["subsets"]["pilot"])])
    from .ledger import spent
    runs = {}
    for p in sorted(Path(config.RUNS_DIR).glob("*/ledger.jsonl")):
        tot = Counter()
        for line in p.read_text(encoding="utf-8").splitlines():
            d = json.loads(line)
            tot[d["provider"]] += float(d.get("usd") or 0)
        runs[p.parent.name] = {k: round(v, 5) for k, v in tot.items()}
    s["spend_usd"] = {"anthropic": round(spent("anthropic"), 5), "gemini": round(spent("gemini"), 5), "by_run": runs}
    return s


def fmt(r):
    if not r or r.get("rate") is None:
        return "—"
    lo, hi = r["ci_cluster"]
    return f"{100 * r['rate']:.1f} % ({r['x']}/{r['n']}; {100 * lo:.1f}–{100 * hi:.1f})"


def tables(s):
    L = ["# Results tables (generated by analysis.py)", "",
         "Primary endpoint: reports with ≥1 unsupported factual element (E1–E4), analysis set, 95 % CI by patient-cluster "
         "bootstrap.", "", "| Model | Arm | Drafts | Primary | E1 number | E2 contradiction | E3 section | E4 wording | "
                           "Omission | Cost/report (USD) |", "|---|---|---:|---|---|---|---|---|---|---:|"]
    for a, arms in s["models"].items():
        for arm, c in arms.items():
            L.append(f"| {a} | {arm} | {c['n_drafts']} | {fmt(c['primary'])} | {fmt(c['by_class']['E1'])} | "
                     f"{fmt(c['by_class']['E2'])} | {fmt(c['by_class']['E3'])} | {fmt(c['by_class']['E4'])} | "
                     f"{fmt(c['omission_any'])} | {c['usd_per_report']:.5f} |")
    L += ["", "Paired comparisons (exact McNemar, Holm over the pre-stated family of 10).", "",
          "| Model | First | Second | Pairs | Rate first | Rate second | Difference (95 % CI) | p | p Holm |",
          "|---|---|---|---:|---:|---:|---|---:|---:|"]
    for f in s["family"]:
        lo, hi = f["difference_ci_cluster"]
        L.append(f"| {f['model']} | {f['first']} | {f['second']} | {f['n_pairs']} | {100 * f['rate_first']:.1f} % | "
                 f"{100 * f['rate_second']:.1f} % | {100 * f['difference']:+.1f} ({100 * lo:+.1f} to {100 * hi:+.1f}) | "
                 f"{f['p_two_sided']:.2g} | {f['p_holm']:.2g} |")
    L += ["", "Healthy controls (stratum v): reports with an unsafe statement.", "", "| Model | Arm | Unsafe |", "|---|---|---|"]
    for a, arms in s["models"].items():
        for arm, c in arms.items():
            L.append(f"| {a} | {arm} | {fmt(c['hc_unsafe'])} |")
    L += ["", "A3 outcomes and first drafts.", "", "| Model | Outcomes | Blocked | First-draft primary |", "|---|---|---|---|"]
    for a, arms in s["models"].items():
        if "A3" in arms:
            c = arms["A3"]
            L.append(f"| {a} | {c['a3_outcomes']} | {fmt(c['a3_blocked'])} | {fmt(c['a3_first_draft_primary'])} |")
    L += ["", "Injection subset: detector hit with the injected text, and on the same records without it (baseline).", "",
          "| Model/arm | With injection | Baseline, no injection | A0 prompt reached |", "|---|---|---|---:|"]
    for k, v in s["secondary"]["injection"].items():
        L.append(f"| {k} | {fmt(v)} | {fmt(v.get('baseline_same_records'))} | {v['reachable_A0']} |")
    L += ["", "Multilingual subset: primary endpoint.", "", "| Model/arm/language | Primary |", "|---|---|"]
    for k, v in s["secondary"]["multilingual"].items():
        L.append(f"| {k} | {fmt(v)} |")
    L += ["", "Per stratum (primary).", "", "| Model | Arm | (i) thick | (i) thin | (ii) | (iii) | (v) |",
          "|---|---|---|---|---|---|---|"]
    for a, arms in s["models"].items():
        for arm, c in arms.items():
            b = c["by_stratum"]
            L.append(f"| {a} | {arm} | " + " | ".join(fmt(b[k]) for k in ("i_thick", "i_thin", "ii", "iii", "v")) + " |")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(config.REPO / "docs" / "research" / "agents-benchmark" / "results"))
    a = ap.parse_args(argv)
    rows, man = evaluate_all()
    s = summarise(rows, man)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(s, indent=1, default=float))
    cols = ["model", "subset", "record_id", "arm", "lang", "payload", "stratum", "status", "evaluable", "primary",
            "n_E1", "n_E2", "n_E3", "n_E4", "extended", "omission_any", "om_count", "om_dis", "om_regions",
            "om_longitudinal", "hc_unsafe", "injection_success", "injection_reachable", "a3_outcome", "a3_first_primary",
            "a0_raw_primary", "primary_frozen_v2", "truncated", "n_calls", "usd", "latency_s", "tool_steps"]
    with open(out / "per_report.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    (out / "tables.md").write_text(tables(s), encoding="utf-8")
    print(json.dumps({k: {arm: c["primary"]["rate"] for arm, c in v.items()} for k, v in s["models"].items()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
