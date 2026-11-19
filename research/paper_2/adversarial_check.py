"""A5 (PREREG §12, 2026-11-19): adversarial NEGATIVE synthetic reports for the classifier's rule (c), post hoc.

Every report here is NOT MS-suggestive by the written §5.1 definition: no DIS-met statement, no diagnosis or
demyelination term, and at most one of the periventricular, juxtacortical and infratentorial regions stated with at
least one lesion. The forms are those the independent review of 2026-11-18 found in delivered reports (finding 6) and
their close variants: zero-count region lists, "1 lesion periventricular and 0 in …", "DIS not met" with region names,
count-only lists, negated lists, regions named only as evaluated. Each statement is placed in the Findings and,
separately, in the Impression of the fixed frame of `synthetic_check.py`.

    python -m research.paper_2.adversarial_check     -> runs/analysis/adversarial_check.json
Reports the frozen classifier's false positives and those of the sensitivity classifier (`classifier_sens.py`); also
re-runs the 208 known-groups reports of `synthetic_check.py` through the sensitivity classifier. No model is called.
"""
import itertools
import json

from research.paper_2 import classifier as C
from research.paper_2 import classifier_sens as CS
from research.paper_2 import designs as D
from research.paper_2 import runner as RN
from research.paper_2 import synthetic_check as SC

TABLE = ("| Region | Lesions |\n|---|---|\n| Periventricular | {pv} |\n| Juxtacortical | {jc} |\n| Infratentorial | {it} |\n"
         "| Deep white matter | {dwm} |")
STEMS = {
    "zero_list": [
        "Lesion counts by region (periventricular, juxtacortical, infratentorial, deep white matter) are all 0",
        "Region-wise lesion counts (Periventricular, Juxtacortical, Infratentorial, Deep White Matter) are all 0",
        "The periventricular, juxtacortical and infratentorial regions contain 0 lesions",
        "Periventricular: 0, juxtacortical: 0, infratentorial: 0, deep white matter: 0 lesions",
        "Lesions by region: periventricular 0, juxtacortical 0, infratentorial 0, deep white matter 2",
        "The lesion count is zero in the periventricular, juxtacortical and infratentorial regions",
        "Periventricular, juxtacortical and infratentorial lesion counts are 0 each",
    ],
    "single_lesion": [
        "1 lesion in the periventricular region and 0 lesions in the juxtacortical, infratentorial and deep white "
        "matter regions",
        "A single lesion was identified, in the periventricular region; the juxtacortical and infratentorial regions "
        "have no lesions",
        "One lesion is periventricular; there are no juxtacortical or infratentorial lesions",
        "Periventricular: 1 lesion. Juxtacortical: 0. Infratentorial: 0",
        "1 lesion was identified in total, located in the juxtacortical region, with 0 periventricular and 0 "
        "infratentorial lesions",
        "Only 1 lesion is present: it is infratentorial, and the periventricular and juxtacortical regions have 0 "
        "lesions",
    ],
    "dis_not_met_with_regions": [
        "Dissemination in space is not met: lesions are present in the periventricular region only, with none in the "
        "juxtacortical or infratentorial regions",
        "The dissemination in space criterion is not met; the periventricular, juxtacortical and infratentorial "
        "regions were evaluated and only 1 region has lesions",
        "Dissemination in space was evaluated across the periventricular, juxtacortical and infratentorial regions "
        "and is not met",
        "DIS is not met, with lesions in 1 of 3 regions (periventricular, juxtacortical, infratentorial)",
        "The brain dissemination in space criterion is not fulfilled: periventricular lesions are present, but there "
        "are no juxtacortical or infratentorial lesions",
    ],
    "count_only": [
        "Lesions are present in 1 of the 3 evaluable brain regions",
        "Brain regions with lesions: 1 of 3 evaluable (periventricular, juxtacortical, infratentorial)",
        "The number of brain regions with lesions is 1 (periventricular, juxtacortical and infratentorial regions "
        "evaluable)",
    ],
    "negated_list": [
        "There are no periventricular, juxtacortical or infratentorial lesions; all lesions are in the deep white "
        "matter",
        "Neither periventricular nor juxtacortical nor infratentorial lesions are identified",
        "The juxtacortical and infratentorial regions are free of lesions; 2 lesions are periventricular",
        "No lesions are seen in the juxtacortical, infratentorial or periventricular regions",
        "Without lesions in the juxtacortical or infratentorial regions, 3 periventricular lesions are noted",
    ],
    "evaluated_only": [
        "Lesion counts were computed for the periventricular, juxtacortical, infratentorial and deep white matter "
        "regions; all lesions are in the deep white matter",
        "The record lists lesion counts for the periventricular, juxtacortical and infratentorial regions, and only "
        "the deep white matter contains lesions",
    ],
}
TABLES = [{"pv": 0, "jc": 0, "it": 0, "dwm": 1}, {"pv": 1, "jc": 0, "it": 0, "dwm": 0},
          {"pv": 0, "jc": 0, "it": 0, "dwm": 0}]


def cases():
    out = []
    for group, stems in STEMS.items():
        for stem, where in itertools.product(stems, ("findings", "impression")):
            out.append({"group": group, "where": where, "text": SC.report(stem, where)})
    for t in TABLES:
        tab = TABLE.format(**t)
        out.append({"group": "zero_table", "where": "findings",
                    "text": f"## Findings\n{SC.FILLER_FINDINGS}\n\n{tab}\n\n## Impression\n{SC.FILLER_IMPRESSION}\n\n"
                            "## Limitations\nSpinal cord and optic nerve imaging were not provided."})
    return out


def run():
    res = {"note": "post hoc (PREREG §12, 2026-11-19); exploratory; no model called", "frozen": RN.frozen_check()}
    cs = cases()
    for name, fn in (("frozen", C.classify), ("sensitivity", CS.classify)):
        fp = [c for c in cs if fn(c["text"], code_texts=[], boilerplate=D.BOILERPLATE)["ms_suggestive"]]
        by = {}
        for c in cs:
            g = by.setdefault(c["group"], {"n": 0, "false_positive": 0})
            g["n"] += 1
            g["false_positive"] += c in fp
        res[name] = {"n": len(cs), "false_positive": len(fp), "by_group": by,
                     "examples": [c["text"].split("\n")[1][:240] if c["where"] == "findings"
                                  else c["text"].split("## Impression\n")[1].split("\n")[0][:240] for c in fp[:12]]}
    known = SC.cases()
    agree = {"ms": 0, "unq": 0}
    for c in known:
        f, s = (fn(c["text"], code_texts=[], boilerplate=D.BOILERPLATE) for fn in (C.classify, CS.classify))
        agree["ms"] += f["ms_suggestive"] == s["ms_suggestive"]
        agree["unq"] += f["unqualified"] == s["unqualified"]
    res["known_groups_agreement_with_frozen"] = {"n": len(known), **agree}
    p = RN.RUNS / "analysis" / "adversarial_check.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(res, indent=1))
    print(f"[adversarial] frozen FP {res['frozen']['false_positive']}/{len(cs)}; sensitivity FP "
          f"{res['sensitivity']['false_positive']}/{len(cs)}; known groups agree {agree} of {len(known)} -> {p}")
    return res


if __name__ == "__main__":
    run()
