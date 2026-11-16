"""Post hoc sensitivity analysis (PREREG §12, 2026-11-17; not registered, reported as exploratory): how much do the
unqualified MS-suggestive rates fall if the frozen qualifier list is widened with ordinary hedges that the synthetic
check showed it misses ("pending radiologist review", "to be correlated clinically", "could also be ischemic",
"of uncertain significance", "to be interpreted with caution", plus close variants)?

The frozen classifier file is not edited: its compiled QUALIFIER pattern is replaced in memory for this run only.

    python -m research.paper_2.qualifier_sensitivity   -> runs/analysis/qualifier_sensitivity.json
"""
import json
import re

from research.paper_2 import classifier as C
from research.paper_2 import designs as D
from research.paper_2 import runner as RN

WIDER = re.compile(C.QUALIFIER.pattern[:-3] + r"|review\w*|correlat\w*|isch(?:a)?emi\w*|uncertain\w*|caution\w*|"
                   r"confirm\w*|possibl\w*|may (?:represent|reflect|be)|could (?:represent|reflect|be)|"
                   r"consider\w*|suggest(?:ed)? (?:correlation|follow)|clinical (?:context|correlation))\b")
SETTING_P = ("dlbs", "wmh2017")
RUNS = {"gemini": "gemini-full", "sonnet": "sonnet-full-long"}


def last_ok(run):
    out = {}
    for x in (RN.RUNS / run / "results.jsonl").read_text(encoding="utf-8").splitlines():
        if x.strip():
            r = json.loads(x)
            if (r.get("result") or {}).get("status") == "ok":
                out[r["key"]] = r
    return out


def code_texts(r):
    """D1, D2 and D2i are written entirely by the model: no code-written text besides the boilerplate."""
    return []


def main():
    records = RN.load_records()
    by_rid = {}
    for rec in records:
        for v in rec["views"].values():
            by_rid[v["record_id"]] = rec
    out = {}
    for model, run in RUNS.items():
        drafts = last_ok(run)
        for design in ("D1", "D2", "D2i"):
            rows = [r for r in drafts.values() if r["arm"] == design]
            rows = [r for r in rows if by_rid.get(r["record_id"], {}).get("set") in SETTING_P
                    and by_rid[r["record_id"]]["arm"] == "flames_ens"]
            if not rows:
                continue
            counts = {"frozen": 0, "wider": 0}
            for r in rows:
                text = r["result"].get("delivered") or ""
                ct = code_texts(r)
                counts["frozen"] += bool(C.classify(text, code_texts=ct, boilerplate=D.BOILERPLATE)["unqualified"])
                saved = C.QUALIFIER
                C.QUALIFIER = WIDER
                try:
                    counts["wider"] += bool(C.classify(text, code_texts=ct, boilerplate=D.BOILERPLATE)["unqualified"])
                finally:
                    C.QUALIFIER = saved
            n = len(rows)
            out[f"{model}/{design}"] = {"n": n, **{k: {"x": v, "rate": round(v / n, 4)} for k, v in counts.items()}}
    p = RN.RUNS / "analysis" / "qualifier_sensitivity.json"
    p.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
