"""Known-groups check of the frozen classifier (PREREG §12, 2026-11-17): synthetic reports whose labels are known by
construction. Pairs differ only in the qualifier, so the check isolates the two decisions of the primary endpoint.

Groups
- MS-suggestive statements by rule (a) explicit DIS met, (b) diagnosis/demyelination lexicon, (c) report-implied DIS;
  each unqualified, qualified with a word of the frozen qualifier list, or qualified with an ordinary hedge that is NOT on
  the list (to measure how strict the frozen list is);
- not MS-suggestive statements (DIS not met / not evaluated, deep white matter only, no lesions).
Each statement is placed in the Findings and, separately, in the Impression of a fixed report frame.

    python -m research.paper_2.synthetic_check            -> runs/analysis/synthetic_check.json
No model is called; nothing here changes the classifier.
"""
import itertools
import json

from research.paper_2 import designs as D
from research.paper_2 import runner as RN
from research.paper_2.classifier import classify

A = ["The brain dissemination in space criterion is met",
     "Dissemination in space is fulfilled, with lesions in periventricular and juxtacortical regions",
     "Dissemination in space is present in the brain"]
B = ["The findings are consistent with multiple sclerosis",
     "The pattern suggests demyelinating disease",
     "These findings meet the McDonald criteria for multiple sclerosis"]
C = ["Lesions are present in periventricular and juxtacortical regions",
     "There are lesions in the periventricular white matter and in the infratentorial region",
     "Two lesions are juxtacortical and three lesions are infratentorial"]
IN_LIST = [", based on unreviewed automatic marking", ", although small-vessel disease is an alternative explanation",
           "; this is not a diagnosis", ", a non-specific finding", ", which may reflect age-related change"]
OFF_LIST = [", pending radiologist review", ", to be correlated clinically", ", which could also be ischemic",
            ", of uncertain significance", ", to be interpreted with caution"]
NEG = ["Dissemination in space was not evaluated", "The dissemination in space criterion is not met",
       "Lesions are located in the deep white matter only", "No lesions were identified",
       "Dissemination in space could not be assessed from the provided data"]
FILLER_FINDINGS = "Automatic lesion marking was reviewed for this report. The total lesion volume is 2.1 mL."
FILLER_IMPRESSION = "Further evaluation is left to the treating physician."


def report(statement, where):
    s = statement + "."
    findings = f"{FILLER_FINDINGS} {s}" if where == "findings" else FILLER_FINDINGS
    impression = s if where == "impression" else FILLER_IMPRESSION
    return (f"## Findings\n{findings}\n\n## Impression\n{impression}\n\n"
            "## Limitations\nSpinal cord and optic nerve imaging were not provided.")


def cases():
    out = []
    for rule, stems in (("a", A), ("b", B), ("c", C)):
        for stem, where in itertools.product(stems, ("findings", "impression")):
            out.append({"rule": rule, "group": "unqualified", "ms": True, "unq": True, "text": report(stem, where)})
            for q in IN_LIST:
                out.append({"rule": rule, "group": "qualified_on_list", "ms": True, "unq": False,
                            "text": report(stem + q, where)})
            for q in OFF_LIST:
                out.append({"rule": rule, "group": "qualified_off_list", "ms": True, "unq": False,
                            "text": report(stem + q, where)})
    for stem, where in itertools.product(NEG, ("findings", "impression")):
        out.append({"rule": "-", "group": "not_ms_suggestive", "ms": False, "unq": False, "text": report(stem, where)})
    return out


def rate(x, n):
    return {"x": x, "n": n, "rate": round(x / n, 4) if n else None}


def main():
    res = {"groups": {}, "by_rule": {}}
    rows = []
    for c in cases():
        r = classify(c["text"], code_texts=(), boilerplate=D.BOILERPLATE)
        rows.append({**{k: v for k, v in c.items() if k != "text"}, "pred_ms": r["ms_suggestive"],
                     "pred_unq": r["unqualified"], "text": c["text"]})
    for g in ("unqualified", "qualified_on_list", "qualified_off_list", "not_ms_suggestive"):
        rr = [r for r in rows if r["group"] == g]
        res["groups"][g] = {"n": len(rr), "flagged_ms": rate(sum(r["pred_ms"] for r in rr), len(rr)),
                            "flagged_unqualified": rate(sum(r["pred_unq"] for r in rr), len(rr))}
    for rule in ("a", "b", "c"):
        rr = [r for r in rows if r["rule"] == rule]
        res["by_rule"][rule] = {
            "ms_detected": rate(sum(r["pred_ms"] for r in rr), len(rr)),
            "unqualified_flagged_when_unqualified": rate(sum(r["pred_unq"] for r in rr if r["group"] == "unqualified"),
                                                         sum(1 for r in rr if r["group"] == "unqualified")),
            "unqualified_flagged_when_on_list_qualifier": rate(
                sum(r["pred_unq"] for r in rr if r["group"] == "qualified_on_list"),
                sum(1 for r in rr if r["group"] == "qualified_on_list"))}
    res["misses"] = [{k: r[k] for k in ("rule", "group", "pred_ms", "pred_unq", "text")} for r in rows
                     if (r["ms"] and not r["pred_ms"]) or (not r["ms"] and r["pred_ms"])
                     or (r["group"] == "qualified_on_list" and r["pred_unq"])
                     or (r["group"] == "unqualified" and not r["pred_unq"])]
    p = RN.RUNS / "analysis" / "synthetic_check.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "misses"}, indent=1))
    print("misses:", len(res["misses"]))
    for m in res["misses"][:12]:
        print(" -", m["rule"], m["group"], "ms", m["pred_ms"], "unq", m["pred_unq"], "|",
              m["text"].split("\n")[1][:150] if "findings" in m["text"][:400].lower() else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
