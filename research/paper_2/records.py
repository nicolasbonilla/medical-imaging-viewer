"""Paper 2 record builder (PREREG §2): measurement records from paper 1's frozen outputs, with no new tool run.

**Inputs:**
- paper 1's `per_unit.csv` and `lesions.csv` (the addendum's frozen evaluation; blocks A, B, C1, C2);
- `analysis_sets.json` (the FLAMeS-clean flag of C1);
- optionally, a geometry function: input id → the app's acquisition block, read from header-only images.

**Sets** (PREREG §2):
- A = WMH 2017 (T 3.0);
- B = DLBS (T 2.5);
- C2 = SibBMS (T 1.0, native, no `_th`);
- C1 = MS 1 mm, FLAMeS-clean, native (T 1.0, no `_th`).

**One record per (scan, arm)** with an available output. The honest view follows v1's measurement record:
- regions and DIS as computed on the tool's unreviewed mask, marked "automatic, unreviewed";
- DIS = paper 1's app DIS for the unit (gate G1);
- region counts from paper 1's per-lesion regions.

**Variants of the view:**
- `d4`: regions withheld and DIS not evaluated (the app's confirmation gate);
- `second_segmentation`: the paired arm's summary, used by D2 and D2i.

The view names no cohort, dataset or status, and carries no age. Those go in `meta` only.

Implementation rules, logged in PREREG §12 before any draft:
- **Recount mismatch.** When paper 1's per-lesion recount disagrees with the app's DIS for a unit, DIS still follows
  the app, as G1 requires, and `brain_regions_with_lesions` follows the app's verdict: 2 if met; otherwise 1 if any DIS
  region holds a lesion, else 0. The record is flagged `recount_mismatch` and counted.
- **GR failure** (block A/B): DIS is "not evaluated" and regions are not given, as the app would do without a valid
  atlas registration. The record is kept and counted.
- **Thick-slice context.** v1's fixed sentence is added when the app's effective slice thickness exceeds its thin
  limit (1.5 mm).
"""
import csv
import hashlib
import json
from collections import OrderedDict, defaultdict
from typing import Any, Callable, Dict, List, Optional

VERSION = "paper2-v1"
ARMS = ("flames_ens", "flames_f0", "lstai", "mindglide", "wmhsynthseg", "samseg")
TOOL_LABEL = {"flames_ens": "FLAMeS, mean of 5 models", "flames_f0": "FLAMeS, fold 0", "lstai": "LST-AI",
              "wmhsynthseg": "WMH-SynthSeg", "mindglide": "MindGlide", "samseg": "SAMSEG"}
RNAME = {"PV": "Periventricular", "JC": "Juxtacortical", "IT": "Infratentorial", "DWM": "Deep White Matter"}
DIS_CODES = ("PV", "JC", "IT")
SET_OF_BLOCK = {"A": "wmh2017", "B": "dlbs", "C1": "ms", "C2": "sibbms"}
NOT_AVAILABLE = ["clinical indication", "contrast-enhanced imaging", "T1-weighted imaging", "spinal cord imaging",
                 "optic nerve imaging", "brain volumetry"]                       # = v1 config.NOT_AVAILABLE
THIN_LIMIT_MM = 1.5                                                              # = app acquisition_geometry
THICK_CONTEXT = ("The original acquisition has slices at least {x} mm thick (read from the stored image grid). "
                 "Automatic lesion marking is less sensitive on thick slices: small lesions may be missed and volumes "
                 "are less precise.")                                            # = v1 config.THICK_CONTEXT


def rid(scan: str, arm: str, variant: str) -> str:
    return hashlib.sha256(f"{VERSION}|{scan}|{arm}|{variant}".encode()).hexdigest()[:12]


def count_category(n: int) -> str:                                             # = v1 records.count_category
    if n < 20:
        return "exact"
    if n <= 50:
        return "20-50"
    if n <= 100:
        return "50-100"
    return ">100"


def size_category(v: float) -> str:
    return "small" if v < 100 else ("medium" if v <= 1000 else "large")


def _f(x):
    return float(x) if x not in ("", None) else None


def load(per_unit_csv: str, lesions_csv: str, sets: Dict[str, Any]):
    """Paper 1 units of the four paper-2 sets, at native resolution, with their lesions."""
    clean = {c for c, v in sets["C1_ms_iso"].items() if not v["flames_contaminated"]}
    keep = {}
    with open(per_unit_csv, newline="") as fh:
        for r in csv.DictReader(fh):
            b, uid = r["block"], r["id"]
            if b not in SET_OF_BLOCK or "_th" in uid:
                continue
            if b == "C1" and uid not in clean:
                continue
            if r["available"] != "1":
                continue
            keep[(uid, r["arm"])] = r
    les = defaultdict(list)
    with open(lesions_csv, newline="") as fh:
        for r in csv.DictReader(fh):
            if (r["id"], r["arm"]) in keep:
                les[(r["id"], r["arm"])].append((float(r["vol_mm3"]), r["region"]))
    return keep, les


def _lesions_view(les):
    rows = [[j, round(v, 1), round(v / 1000.0, 4), size_category(v), RNAME.get(g, "none")]
            for j, (v, g) in enumerate(les, 1)]
    tot = sum(v for v, _ in les)
    sd = {"small": 0, "medium": 0, "large": 0}
    for v, _ in les:
        sd[size_category(v)] += 1
    return {"total_count": len(les), "count_category": count_category(len(les)),
            "total_volume_mm3": round(tot, 1), "total_volume_ml": round(tot / 1000.0, 4), "size_distribution": sd,
            "size_classes_mm3": {"small": "<100", "medium": "100-1000", "large": ">1000"},
            "lesion_table_columns": ["id", "volume_mm3", "volume_ml", "size_category", "region (automatic)"],
            "lesion_table": rows}


def _region_counts(les):
    c = {RNAME[k]: 0 for k in RNAME}
    vol = {RNAME[k]: 0.0 for k in RNAME}
    for v, g in les:
        if g in RNAME:
            c[RNAME[g]] += 1
            vol[RNAME[g]] += v / 1000.0
    return c, {k: round(x, 4) for k, x in vol.items()}


def recount_dis(les, min_vol=3.0) -> bool:                                      # = paper 1 dis_from_lesions
    present = {g for v, g in les if v >= min_vol - 1e-9 and g in DIS_CODES}
    return len(present) >= 2


def _dis_and_regions(unit, les):
    """(regions block, dis block, recount_mismatch) of the honest view."""
    gr_ok = unit.get("gr_pass", "1") in ("1", "")
    if not gr_ok:
        return ({"confirmed": False, "note": "Regions could not be computed: the image could not be registered to the "
                                             "atlas."},
                {"status": "not evaluated", "reason": "The image could not be registered to the atlas; dissemination "
                                                      "in space could not be computed."}, False)
    counts, vols = _region_counts(les)
    met = unit["dis"] == "1"
    present = {RNAME[g]: any(gg == g and v >= 3.0 - 1e-9 for v, gg in les) for g in DIS_CODES}   # the rule's min size
    k = sum(present.values())
    mismatch = recount_dis(les) != met
    if mismatch:                                   # the app's verdict rules (G1); k follows it
        k = 2 if met else (1 if unit.get("any_dis_region") == "1" else 0)
    regions = {"confirmed": False, "source": "automatic, unreviewed (computed on the AI marking)",
               "lesion_counts": counts, "volumes_ml": vols}
    dis = {"status": "evaluated", "basis": "automatic, unreviewed AI marking (no radiologist confirmation)",
           "dis_met_brain": met, "brain_regions_with_lesions": k, "brain_regions_evaluable": 3,
           "total_topographies": 5, "region_presence": present, "spinal_cord": "not assessed",
           "optic_nerve": "not assessed", "criteria": "McDonald 2024 (Montalban et al., Lancet Neurology 2025)"}
    return regions, dis, mismatch


def pair_of(arm: str, available: List[str]) -> Optional[str]:
    """PREREG §3: FLAMeS-ens and FLAMeS-f0 pair with LST-AI, else WMH-SynthSeg; every other arm pairs with FLAMeS-ens."""
    if arm in ("flames_ens", "flames_f0"):
        for p in ("lstai", "wmhsynthseg"):
            if p in available:
                return p
        return None
    return "flames_ens" if "flames_ens" in available else None


def build(units, les, geometry: Optional[Callable[[str], Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    by_scan = defaultdict(list)
    for (uid, arm) in units:
        by_scan[uid].append(arm)
    summaries, out = {}, []
    for (uid, arm), u in sorted(units.items()):
        regions, dis, mismatch = _dis_and_regions(u, les[(uid, arm)])
        summaries[(uid, arm)] = {"tool": TOOL_LABEL[arm], "lesion_count": len(les[(uid, arm)]),
                                 "regions": regions.get("lesion_counts"), "dis": {k: dis[k] for k in dis
                                                                                 if k in ("status", "dis_met_brain",
                                                                                          "brain_regions_with_lesions")}}
    for (uid, arm), u in sorted(units.items()):
        L = les[(uid, arm)]
        regions, dis, mismatch = _dis_and_regions(u, L)
        acq = (geometry(uid) if geometry else None) or {"segmented_sequence": "FLAIR", "series_description": "FLAIR"}
        eff = ((acq.get("slice_thickness") or {}).get("at_least_mm"))
        if eff is not None and eff > THIN_LIMIT_MM:
            acq = dict(acq, thick_slice_context=THICK_CONTEXT.format(x=f"{float(eff):g}"))
        base = OrderedDict()
        base["record_id"] = rid(uid, arm, "base")
        base["report_language"] = "en"
        base["segmentation"] = {"source": f"automatic AI lesion marking ({TOOL_LABEL[arm]}), not reviewed",
                                "tool": TOOL_LABEL[arm], "confirmed_by_radiologist": False,
                                "segmentation_source": "automatic, unreviewed"}
        base["acquisition"] = acq
        base["lesions"] = _lesions_view(L)
        base["regions"] = regions
        base["dis"] = dis
        base["longitudinal"] = None
        base["not_available"] = list(NOT_AVAILABLE)
        pair = pair_of(arm, by_scan[uid])
        d2 = copy_view(base, rid(uid, arm, "d2"))
        d2["second_segmentation"] = (summaries[(uid, pair)] if pair else
                                     {"available": False, "note": "No second segmentation exists for this scan."})
        d4 = copy_view(base, rid(uid, arm, "d4"))
        d4["regions"] = {"confirmed": False, "note": "Regions not confirmed by a radiologist; not given."}
        d4["dis"] = {"status": "not evaluated", "reason": "No radiologist has confirmed the lesions and their MAGNIMS "
                                                          "regions; dissemination in space was not assessed."}
        out.append({"scan": uid, "arm": arm, "set": SET_OF_BLOCK[u["block"]],
                    "views": {"base": base, "d2": d2, "d4": d4},
                    "meta": {"expert_dis": u.get("expert_dis", ""), "gr_pass": u.get("gr_pass", ""),
                             "recount_mismatch": mismatch, "pair_arm": pair, "dis_met": dis.get("dis_met_brain")}})
    return out


def copy_view(view, new_id):
    v = json.loads(json.dumps(view), object_pairs_hook=OrderedDict)
    v["record_id"] = new_id
    return v


def gate_g1(records, units) -> Dict[str, Any]:
    """G1: per (set, arm), the share of records whose automatic DIS is met equals paper 1's arm DIS (GR-passing units)."""
    mine, ref = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for r in records:
        if r["meta"]["gr_pass"] in ("1", ""):
            k = (r["set"], r["arm"])
            mine[k][0] += int(bool(r["meta"]["dis_met"]))
            mine[k][1] += 1
    for (uid, arm), u in units.items():
        if u.get("gr_pass", "1") in ("1", ""):
            k = (SET_OF_BLOCK[u["block"]], arm)
            ref[k][0] += int(u["dis"] == "1")
            ref[k][1] += 1
    bad = {f"{k[0]}/{k[1]}": (mine[k], ref[k]) for k in set(mine) | set(ref) if mine[k] != ref[k]}
    return {"passed": not bad, "mismatches": bad, "cells": len(set(mine) | set(ref))}
