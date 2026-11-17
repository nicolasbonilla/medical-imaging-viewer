"""Post-hoc analyses requested by an internal review before submission (PREREG §12, 2026-11-17). Exploratory; they
change no registered end point, and every number they print is labelled post hoc in the manuscript.

Reads the frozen classifier's per-draft rows (`runs/analysis/<model>_rows.jsonl`), the delivered texts and the judges'
labels. Writes `runs/analysis/review_analyses.json`.

    python -m research.paper_2.review_analyses

1. text_level: per model and design (setting P, FLAMeS ensemble), the registered sentence-level end point next to
   report-level readings: a provenance caveat anywhere in the model's text; a clinical caveat (another cause of the
   lesions) anywhere; the sentence rule with "automat*" in place of "automatic*"; statement-level qualification.
2. paired: D1 vs D2 per model on the 270 people (exact McNemar, paired difference with a bootstrap CI over people).
3. ms_coverage: the criterion conveyed in MS examinations whose experts' masks met it, with a CI from a bootstrap
   that resamples patients (PREREG §5.2: clustered by patient).
4. kappa_by_type: classifier vs judges on model-written (D1, D2, D2i) and code-written (D3-D5) reports separately,
   and judge vs judge on the unqualified label.
5. h1: the registered gatekeeper per model.
6. gptoss_without_failed: gpt-oss rates without the 11 replies that held no report.
7. gemini_d2_tools: tool use and disagreement mentions of the primary model's agent on setting P, FLAMeS ensemble.
8. other_arms and sibbms: the primary model on the five other segmentation arms; every model on the SibBMS controls.
9. consensus_rule: how often D5's consensus rule was met in setting P.
"""
import json
import random
import re
from collections import defaultdict

import numpy as np
from scipy.stats import binomtest

from research.paper_2 import analysis as A
from research.paper_2 import classifier as C
from research.paper_2 import designs as D
from research.paper_2 import judges as J
from research.paper_2 import runner as RN

RUN_OF = {"gemini": "gemini-full", "sonnet": "sonnet-full-long", "gemini4argon": "gemini4argon-full-long",
          "gptoss": "gptoss-full-long", "deepseek": "deepseek-full-long", "mistral3": "mistral3-full-long",
          "gemma": "gemma-full"}
SETTING_P = ("dlbs", "wmh2017")
MODEL_WRITTEN = ("D1", "D2", "D2i")

# Post-hoc lexicons, fixed in this file before any count was printed from them (the review had read some reports).
PROVENANCE = re.compile(r"\b(?:unreviewed|unconfirmed|not (?:yet )?(?:been )?(?:reviewed|confirmed)|automat\w*|"
                        r"not (?:a )?diagnos\w*)\b")
CLINICAL = re.compile(r"\b(?:vascular|microvascular|small[- ]vessel|age[- ]related|non-?specific|mimic\w*|"
                      r"alternative (?:cause|explanation|diagnos\w*)|differential|isch(?:a)?emi\w*|microangiopath\w*|"
                      r"migraine|gliosis)\b")
AUTOMAT = re.compile(C.QUALIFIER.pattern.replace(r"automatic\w*", r"automat\w*"))


def rows_of(model):
    out = []
    for x in (RN.RUNS / "analysis" / f"{model}_rows.jsonl").read_text(encoding="utf-8").splitlines():
        if x.strip():
            out.append(json.loads(x))
    return out


def texts_of(model):
    """The delivered text of the last 'ok' line of each key, as the analysis reads it."""
    last = {}
    for x in (RN.RUNS / RUN_OF[model] / "results.jsonl").read_text(encoding="utf-8").splitlines():
        if x.strip():
            r = json.loads(x)
            if (r.get("result") or {}).get("status") == "ok":
                last[r["key"]] = r
    return last


def model_body(delivered):
    t = delivered or ""
    for b in D.BOILERPLATE:
        t = t.replace(b, "")
    return t


def classify_with(pattern, text):
    saved = C.QUALIFIER
    C.QUALIFIER = pattern
    try:
        return C.classify(text, code_texts=[], boilerplate=D.BOILERPLATE)
    finally:
        C.QUALIFIER = saved


def prop(x, n):
    return A.cp(x, n)


def text_level(model, rows, texts):
    out = {}
    for des in sorted({r["design"] for r in rows if r["design"] in MODEL_WRITTEN}):
        sel = [r for r in rows if r["design"] == des and r["arm"] == "flames_ens" and r["set"] in SETTING_P]
        if not sel:
            continue
        n = len(sel)
        ms = unq = unq_automat = rep_unq = prov = clin = 0
        stmts = stmts_q = dis_sent = 0
        for r in sel:
            t = (texts.get(r["key"]) or {}).get("result", {}).get("delivered") or ""
            c = C.classify(t, code_texts=[], boilerplate=D.BOILERPLATE)
            assert c["ms_suggestive"] == r["ms"] and c["unqualified"] == r["unq"], (model, r["key"])
            dis_sent += sum(h["rule"] == "a" for h in c["hits"])
            if not c["ms_suggestive"]:
                continue
            body = C.L.fold(model_body(t))
            ms += 1
            unq += c["unqualified"]
            unq_automat += classify_with(AUTOMAT, t)["unqualified"]
            rep_unq += not C.QUALIFIER.search(body)
            prov += bool(PROVENANCE.search(body))
            clin += bool(CLINICAL.search(body))
            for h in c["hits"]:
                if h["rule"] in ("a", "b"):
                    stmts += 1
                    stmts_q += h["qualified"]
        out[des] = {"n": n, "ms_suggestive": prop(ms, n), "unqualified_registered": prop(unq, n),
                    "unqualified_automat": prop(unq_automat, n), "unqualified_report_level": prop(rep_unq, n),
                    "provenance_caveat_among_ms": prop(prov, ms), "clinical_caveat_among_ms": prop(clin, ms),
                    "statements_qualified": prop(stmts_q, stmts), "dis_met_sentences_per_report": round(dis_sent / n, 3)}
    return out


def paired(rows, seed=A.BOOT_SEED):
    by = defaultdict(dict)
    for r in rows:
        if r["arm"] == "flames_ens" and r["set"] in SETTING_P and r["design"] in ("D1", "D2"):
            by[r["scan"]][r["design"]] = bool(r["unq"])
    pairs = [(v["D1"], v["D2"]) for v in by.values() if "D1" in v and "D2" in v]
    if not pairs:
        return None
    b = sum(x and not y for x, y in pairs)
    c = sum(y and not x for x, y in pairs)
    p = binomtest(min(b, c), b + c, 0.5).pvalue if b + c else 1.0
    diffs = np.array([int(y) - int(x) for x, y in pairs])
    rng = np.random.default_rng(seed)
    boots = [diffs[rng.integers(0, len(diffs), len(diffs))].mean() for _ in range(A.BOOT)]
    return {"n": len(pairs), "d1_only": b, "d2_only": c, "p_exact_two_sided": float(p),
            "difference_d2_minus_d1": round(float(diffs.mean()), 4),
            "ci95": [round(float(np.percentile(boots, 2.5)), 4), round(float(np.percentile(boots, 97.5)), 4)]}


def clustered_rate(units, seed=A.BOOT_SEED):
    """units: [(patient, 0/1)]; bootstrap over patients."""
    by = defaultdict(list)
    for p, v in units:
        by[p].append(v)
    pats = sorted(by)
    x, n = sum(v for _, v in units), len(units)
    rng = random.Random(seed)
    boots = []
    for _ in range(A.BOOT):
        s = [rng.choice(pats) for _ in pats]
        xs = sum(sum(by[p]) for p in s)
        ns = sum(len(by[p]) for p in s)
        boots.append(xs / ns)
    boots.sort()
    return {"x": x, "n": n, "patients": len(pats), "rate": round(x / n, 4) if n else None,
            "ci95_patient_bootstrap": [round(boots[int(0.025 * A.BOOT)], 4), round(boots[int(0.975 * A.BOOT) - 1], 4)]}


def ms_coverage(rows):
    out = {}
    for des in sorted({r["design"] for r in rows}):
        sel = [r for r in rows if r["design"] == des and r["arm"] == "flames_ens" and r["set"] == "ms"
               and str(r.get("expert_dis")) == "1"]
        if sel:
            out[des] = clustered_rate([(r["patient"], int(bool(r["dis_conveyed"]))) for r in sel])
    return out


def kappa_by_type():
    rows = {r["key"]: r for r in rows_of("gemini")}
    sample = J.load_sample()
    lab = {j: J.labels_of(j) for j in J.JUDGES}
    res = {}
    for group, designs in (("model_written", MODEL_WRITTEN), ("code_written", ("D3", "D4", "D5"))):
        keys = [k for k in sample if rows[k]["design"] in designs]
        g = {"n": len(keys)}
        for field in ("ms", "unq"):
            cls = [bool(rows[k][field]) for k in keys]
            for j in J.JUDGES:
                jl = [None if k not in lab[j] else (lab[j][k]["ms_suggestive"] if field == "ms" else
                                                    bool(lab[j][k]["ms_suggestive"] and lab[j][k]["unqualified"]))
                      for k in keys]
                g[f"{field}_classifier_vs_{j}"] = J.kappa(cls, jl)
        res[group] = g
    js = [k for k in sample if all(k in lab[j] for j in J.JUDGES)]
    res["judges_unqualified_sonnet_vs_gptoss"] = J.kappa(
        [bool(lab["sonnet"][k]["ms_suggestive"] and lab["sonnet"][k]["unqualified"]) for k in js],
        [bool(lab["gptoss"][k]["ms_suggestive"] and lab["gptoss"][k]["unqualified"]) for k in js])
    res["judges_missing"] = {j: len(sample) - len(lab[j]) for j in J.JUDGES}
    return res


def gptoss_without_failed(rows, texts):
    out = {}
    for des in ("D1", "D2"):
        sel = [r for r in rows if r["design"] == des and r["arm"] == "flames_ens" and r["set"] in SETTING_P]
        ok = [r for r in sel if not RN.failed_delivery(dict(texts.get(r["key"]) or {}, arm=des))]
        out[des] = {"failed": len(sel) - len(ok), "unqualified": prop(sum(r["unq"] for r in ok), len(ok)),
                    "ms_suggestive": prop(sum(r["ms"] for r in ok), len(ok))}
    return out


def gemini_d2_tools(rows):
    sel = [r for r in rows if r["design"] == "D2" and r["arm"] == "flames_ens" and r["set"] in SETTING_P]
    dis = [r for r in sel if r.get("disagree")]
    return {"n": len(sel), "called_second": prop(sum(bool(r["called_second"]) for r in sel), len(sel)),
            "mentions_disagreement": prop(sum(bool(r["mentions_disagreement"]) for r in sel), len(sel)),
            "disagreement_records": len(dis),
            "correct_on_disagreement": prop(sum(bool(r["mentions_disagreement"]) and not r.get("unq_dis_met")
                                                for r in dis), len(dis))}


def other_arms(rows):
    out = {}
    for arm in sorted({r["arm"] for r in rows}):
        for des in ("D1", "D2"):
            sel = [r for r in rows if r["arm"] == arm and r["design"] == des and r["set"] in SETTING_P]
            if sel:
                out[f"{arm}/{des}"] = {"auto_dis_met": prop(sum(bool(r["auto_dis"]) for r in sel), len(sel)),
                                       "ms_suggestive": prop(sum(r["ms"] for r in sel), len(sel)),
                                       "unqualified": prop(sum(r["unq"] for r in sel), len(sel))}
    return out


def sibbms(rows):
    out = {}
    for des in ("D1", "D2"):
        sel = [r for r in rows if r["arm"] == "flames_ens" and r["design"] == des and r["set"] == "sibbms"]
        if sel:
            out[des] = {"auto_dis_met": prop(sum(bool(r["auto_dis"]) for r in sel), len(sel)),
                        "ms_suggestive": prop(sum(r["ms"] for r in sel), len(sel)),
                        "unqualified": prop(sum(r["unq"] for r in sel), len(sel))}
    return out


def consensus_rule():
    recs = RN.load_records()
    sel = [r for r in recs if r["arm"] == "flames_ens" and r["set"] in SETTING_P and "d5" in r["views"]]
    met = sum(bool(r["meta"].get("d5_dis_met")) for r in sel)
    by_expert = defaultdict(lambda: [0, 0])
    for r in sel:
        if r["set"] == "wmh2017":
            k = str(r["meta"].get("expert_dis"))
            by_expert[k][0] += bool(r["meta"].get("d5_dis_met"))
            by_expert[k][1] += 1
    return {"n": len(sel), "consensus_rule_met": prop(met, len(sel)),
            "wmh2017_by_expert_dis": {k: {"met": v[0], "n": v[1]} for k, v in by_expert.items()}}


def main():
    res = {"note": "post hoc (PREREG §12, 2026-11-17); exploratory", "text_level": {}, "paired": {}, "ms_coverage": {},
           "h1": {}, "sibbms": {}}
    for model in RUN_OF:
        rows, texts = rows_of(model), texts_of(model)
        res["text_level"][model] = text_level(model, rows, texts)
        res["paired"][model] = paired(rows)
        res["ms_coverage"][model] = ms_coverage(rows)
        res["h1"][model] = json.loads((RN.RUNS / "analysis" / f"{model}.json").read_text(encoding="utf-8"))["primary"]["H1"]
        res["sibbms"][model] = sibbms(rows)
        if model == "gptoss":
            res["gptoss_without_failed"] = gptoss_without_failed(rows, texts)
        if model == "gemini":
            res["gemini_d2_tools"] = gemini_d2_tools(rows)
            res["other_arms"] = other_arms(rows)
        print(f"[review] {model} done", flush=True)
    res["kappa_by_type"] = kappa_by_type()
    res["consensus_rule"] = consensus_rule()
    p = RN.RUNS / "analysis" / "review_analyses.json"
    p.write_text(json.dumps(res, indent=1))
    print(f"[review] -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
