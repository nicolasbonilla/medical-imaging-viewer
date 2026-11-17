"""Literal example sentences for the manuscript (post hoc; PREREG §12, 2026-11-17), drawn with a fixed seed so that no
example is hand-picked. People without MS, FLAMeS ensemble records. For each category, one report is drawn uniformly
from the eligible reports, and the decisive sentences are quoted as the frozen classifier found them.

Categories:
  d1_unq    primary model, D1, an MS-suggestive statement without a caveat in its sentence
  d1_qual   primary model, D1, MS-suggestive and every statement qualified in its sentence
  d2_unq    primary model, D2, an unqualified statement that cites the second segmentation
  d1c_clin  any model, D1c, an MS-suggestive report that names another cause of the lesions (if any exists)

    python -m research.paper_2.select_examples   -> runs/analysis/examples.json
"""
import json
import random
import re

from research.paper_2 import classifier as C
from research.paper_2 import designs as D
from research.paper_2 import review_analyses as RA
from research.paper_2 import runner as RN

SEED = 20261117
SECOND = re.compile(r"second|lst-ai|wmh-synthseg|independent|both", re.I)


def provenance_sentence(text):
    for s in re.split(r"(?<=[.!?])\s+|\n+", RA.model_body(text)):
        if RA.PROVENANCE.search(C.L.fold(s)) and len(s.strip()) > 20:
            return s.strip()[:240]
    return None


def clinical_sentence(text):
    for s in re.split(r"(?<=[.!?])\s+|\n+", RA.model_body(text)):
        if RA.CLINICAL.search(C.L.fold(s)) and len(s.strip()) > 20:
            return s.strip()[:300]
    return None


def eligible_from_rows(model, design, pred):
    rows = [r for r in RA.rows_of(model) if r["arm"] == "flames_ens" and r["set"] in RN.SETTING_P
            and r["design"] == design]
    texts = RA.texts_of(model)
    out = []
    for r in rows:
        t = (texts.get(r["key"]) or {}).get("result", {}).get("delivered") or ""
        c = C.classify(t, code_texts=[], boilerplate=D.BOILERPLATE)
        if pred(c, t):
            out.append((r["key"], t, c))
    return sorted(out, key=lambda x: x[0])


def draw(items, rng):
    return rng.choice(items) if items else None


def main():
    rng = random.Random(SEED)
    ex = {}
    unq = eligible_from_rows("gemini", "D1", lambda c, t: c["unqualified"])
    k, t, c = draw(unq, rng)
    ex["d1_unq"] = {"model": "gemini", "design": "D1", "eligible": len(unq),
                    "unqualified_sentence": next(h["text"] for h in c["hits"] if not h["qualified"] and h.get("text")),
                    "provenance_elsewhere": provenance_sentence(t)}
    qual = eligible_from_rows("gemini", "D1", lambda c, t: c["ms_suggestive"] and not c["unqualified"])
    k, t, c = draw(qual, rng)
    ex["d1_qual"] = {"model": "gemini", "design": "D1", "eligible": len(qual),
                     "qualified_sentence": next((h["text"] for h in c["hits"] if h.get("text")), None)}
    sec = eligible_from_rows("gemini", "D2", lambda c, t: any(not h["qualified"] and h.get("text")
                                                              and SECOND.search(h["text"]) for h in c["hits"]))
    k, t, c = draw(sec, rng)
    ex["d2_unq"] = {"model": "gemini", "design": "D2", "eligible": len(sec),
                    "unqualified_sentence": next(h["text"] for h in c["hits"] if not h["qualified"] and h.get("text")
                                                 and SECOND.search(h["text"]))}
    clin = []
    by_rid = {rec["views"][v]["record_id"]: rec for rec in RN.load_records() if rec["arm"] == "flames_ens"
              for v in rec["views"]}
    for m in ("gemini", "sonnet", "deepseek", "gptoss"):
        p = RN.RUNS / f"posthoc-{m}-D1c" / "results.jsonl"
        if not p.exists():
            continue
        last = {}
        for x in p.read_text(encoding="utf-8").splitlines():
            if x.strip():
                r = json.loads(x)
                if (r.get("result") or {}).get("status") == "ok":
                    last[r["key"]] = r
        for key in sorted(last):
            r = last[key]
            if by_rid[r["record_id"]]["set"] not in RN.SETTING_P:
                continue
            t = r["result"].get("delivered") or ""
            c = C.classify(t, code_texts=[], boilerplate=D.BOILERPLATE)
            s = clinical_sentence(t)
            if c["ms_suggestive"] and s:
                clin.append((m, key, s))
    pick = draw(clin, rng)
    ex["d1c_clin"] = {"eligible": len(clin), "model": pick[0] if pick else None,
                      "clinical_sentence": pick[2] if pick else None}
    p = RN.RUNS / "analysis" / "examples.json"
    p.write_text(json.dumps(ex, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(ex, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
