"""Exploratory (PREREG §12, 2026-11-17; not a registered test): where the false MS suggestion comes from.

In the vascular cohort (WMH 2017) the experts' masks exist, so each person can be placed in one of two strata:
- the experts' own mask meets the brain DIS rule: the lesions are real and the rule is met on them, so a suggestion is
  the criterion applied outside its population (a perfect segmentation would not prevent it);
- the experts' mask does not meet it: the rule is met only through the tool's errors.
DLBS has no expert masks, so its suggestions cannot be split. Reads the drafts and the frozen classifier only; writes
runs/analysis/harm_sources.json. Usage: python -m research.paper_2.harm_sources <alias>=<run folder> ..."""
import json
import sys

from research.paper_2 import analysis as A
from research.paper_2 import runner as RN


def main(pairs):
    recs = RN.load_records()
    by_rid = A.index_records(recs)
    out = {}
    for pair in pairs:
        alias, run = pair.split("=")
        ok, _ = A.latest(RN.RUNS / run)
        cell = {}
        for line in ok.values():
            rec = by_rid.get(line["record_id"])
            if rec is None or rec["set"] != "wmh2017" or rec["arm"] != "flames_ens" or line["arm"] not in ("D1", "D2"):
                continue
            ev = A.evaluate_draft(rec, line["arm"], line["result"])
            k = f'{line["arm"]}|expert_dis={rec["meta"].get("expert_dis")}|auto_dis={rec["meta"].get("dis_met")}'
            c = cell.setdefault(k, {"n": 0, "ms": 0, "unq": 0})
            c["n"] += 1
            c["ms"] += int(ev["ms"])
            c["unq"] += int(ev["unq"])
        out[alias] = dict(sorted(cell.items()))
    dst = RN.RUNS / "analysis" / "harm_sources.json"
    dst.write_text(json.dumps(out, indent=1), encoding="utf-8")
    for alias, cell in out.items():
        print(alias)
        for k, c in cell.items():
            print(f"  {k}: n={c['n']} ms={c['ms']} unq={c['unq']}")


if __name__ == "__main__":
    main(sys.argv[1:])
