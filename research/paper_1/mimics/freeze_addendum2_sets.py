"""Paper 1 addendum 2 (docs/research/paper-1/PREREG-addendum-2026-11-age-faithful-deterministic.md): freeze the new
analysis sets BEFORE any tool output exists for them. Writes research/paper_1/mimics/analysis_sets_addendum2.json
(analysis_sets.json, the frozen file of the first addendum, is NOT changed):

  B2_sample    75 DLBS participants aged 21-49 (pool: the 105 participants of set "B2" in analysis_sets.json
               B_dlbs = wave 1, the same 64-slice 2.5-mm FLAIR protocol and last-run rule as B1), 25 per decade
               (21-29, 30-39, 40-49): within each decade the ids are sorted by participant number and drawn with ONE
               numpy.random.RandomState(20261118) stream, decades in ascending order (rng.permutation(n)[:25]).
  pilot        the pilot inputs (protocol section 7.2), fixed by rule:
               B2: the lowest participant number among the drawn 20s and among the drawn 40s;
               SynthSeg: two scans per data type (A wmh_utrecht_1 + the lowest-numbered Singapore id; B sub-178 + the
               lowest-numbered drawn 80s id of B1; C1 mslesseg_P10_T1 + openms_patient16; C2 sub-001 + sub-002;
               the two B2 pilot participants) and the atlas T1;
               registration determinism pre-check: wmh_utrecht_1, the Singapore pilot id and sub-178.
  synthseg_keys  the SynthSeg item key of every scan of analysis 3 (A, B1 sample, B2 sample, C1 at 1 mm, C2) and the atlas.

    python -I research/paper_1/mimics/freeze_addendum2_sets.py
"""
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SETS = os.path.join(HERE, "analysis_sets.json")
OUT = os.path.join(HERE, "analysis_sets_addendum2.json")
SEED = 20261118
PER_DECADE = 25
DECADES = (20, 30, 40)
ATLAS_KEY = "atlas_mni152_2009c_t1"


def num(pid):
    return int(pid.split("-")[1])


def synthseg_key(block, iid):
    """One flat namespace for the SynthSeg outputs (DLBS and SibBMS ids are both sub-NNN)."""
    if block in ("B", "B2"):
        return f"dlbs_{iid}"
    if block == "C2":
        return f"sibbms_{iid}"
    return iid                                             # wmh_..., mslesseg_..., openms_...


def young_sample(dlbs):
    rng = np.random.RandomState(SEED)
    out, rank = [], {}
    for dec in DECADES:
        ids = sorted((s for s, v in dlbs.items() if v["set"] == "B2" and dec <= v["age_mri_w1"] < dec + 10), key=num)
        order = rng.permutation(len(ids))[:PER_DECADE]
        for r, i in enumerate(order, 1):
            out.append(ids[i])
            rank[ids[i]] = {"decade": dec, "draw_rank": r, "decade_pool": len(ids)}
    return sorted(out, key=num), rank


def main():
    s = json.load(open(SETS))
    ids, rank = young_sample(s["B_dlbs"])
    assert len(ids) == 75 and all(sum(1 for i in ids if rank[i]["decade"] == d) == 25 for d in DECADES)
    p20 = min((i for i in ids if rank[i]["decade"] == 20), key=num)
    p40 = min((i for i in ids if rank[i]["decade"] == 40), key=num)
    sing = min((i for i in s["A_wmh2017"] if i.startswith("wmh_singapore_")), key=lambda x: int(x.rsplit("_", 1)[1]))
    b80 = min((i for i in s["B1_sample"]["ids"] if s["B1_sample"]["draw"][i]["decade"] == 80), key=num)
    keys = {"A": {i: synthseg_key("A", i) for i in sorted(s["A_wmh2017"])},
            "B": {i: synthseg_key("B", i) for i in s["B1_sample"]["ids"]},
            "B2": {i: synthseg_key("B2", i) for i in ids},
            "C1": {c: synthseg_key("C1", c) for c in sorted(s["C1_ms_iso"])},
            "C2": {c: synthseg_key("C2", c) for c in s["C2_sibbms"]},
            "atlas": ATLAS_KEY}
    out = {"_doc": "Paper 1 addendum 2 analysis sets, frozen before any tool output exists for them "
                   "(PREREG-addendum-2026-11-age-faithful-deterministic.md). Written by freeze_addendum2_sets.py.",
           "B2_sample": {"rule": f"25 per decade (21-29, 30-39, 40-49) from the 105 B2 participants; RandomState({SEED})"
                                 ".permutation per decade in ascending order over ids sorted by participant number",
                         "seed": SEED, "ids": ids, "draw": rank,
                         "pool_per_decade": {d: sum(1 for v in s["B_dlbs"].values() if v["set"] == "B2"
                                                    and d <= v["age_mri_w1"] < d + 10) for d in DECADES}},
           "pilot": {"B2_tools": [p20, p40],
                     "synthseg": {"A": ["wmh_utrecht_1", sing], "B": ["sub-178", b80],
                                  "C1": ["mslesseg_P10_T1", "openms_patient16"], "C2": ["sub-001", "sub-002"],
                                  "B2": [p20, p40], "atlas": [ATLAS_KEY]},
                     "regtest": ["wmh_utrecht_1", sing, "sub-178"],
                     "note": "fixed by rule; pilot outputs stay in the analysis"},
           "synthseg_keys": keys}
    json.dump(out, open(OUT, "w", newline="\n"), indent=1)
    print(json.dumps({"B2_sample": len(ids), "per_decade": {d: sum(1 for i in ids if rank[i]["decade"] == d) for d in DECADES},
                      "pool": out["B2_sample"]["pool_per_decade"], "pilot": out["pilot"],
                      "synthseg_items": sum(len(v) for k, v in keys.items() if k != "atlas") + 1}, indent=1))


if __name__ == "__main__":
    main()
