"""Numbers pack for the manuscript after the independent review of 2026-11-18 (PREREG §12, 2026-11-19). It assembles
existing outputs only: no model is called and no end point is changed. Every block names its source.

    python -m research.paper_2.numbers_pack          -> runs/analysis/numbers_pack.json
"""
import csv
import json
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path

from research.paper_2 import analysis as AN
from research.paper_2 import posthoc2 as P2
from research.paper_2 import review_analyses as RA
from research.paper_2 import runner as RN

A = RN.RUNS / "analysis"
MODEL_NAME = {"gemini": "Gemini 3.1 Flash-Lite (primary)", "sonnet": "Claude Sonnet 5.5", "gemini4argon": "Gemini 4 Argon",
              "gptoss": "gpt-oss-120b", "deepseek": "DeepSeek V4.1 Flash", "mistral3": "Mistral Large 3",
              "gemma": "Gemma 4 E4B"}
SITE = (("wmh_utrecht", "Utrecht"), ("wmh_singapore", "Singapore"), ("wmh_ams", "Amsterdam"))


def _json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _records():
    recs = RN.load_records()
    pilot = RN.pilot_set(recs)
    return [r for r in recs if r["arm"] == "flames_ens" and (r["scan"], r["arm"]) not in pilot]


def site_of(rec):
    if rec["set"] == "dlbs":
        return "DLBS (Dallas)"
    if rec["set"] == "wmh2017":
        return next(name for pre, name in SITE if rec["scan"].startswith(pre))
    if rec["set"] == "ms":
        return "MSLesSeg" if rec["scan"].startswith("mslesseg_") else "Ljubljana"
    return rec["set"]


def load_bin(n):
    return "0-9" if n < 10 else ("10-19" if n < 20 else ">=20")


def _texts_flags(alias):
    """Per (design, scan) flags of the registered D1/D2 drafts with the amendment's code (posthoc2.flags)."""
    texts = RA.texts_of(alias)
    recs = {v["record_id"]: r for r in _records() for v in r["views"].values()}
    out = {}
    for line in texts.values():
        if line["arm"] not in ("D1", "D2"):
            continue
        rec = recs.get(line["record_id"])
        if rec is None:
            continue
        res = line["result"]
        out[(line["arm"], rec["scan"])] = P2.flags(res.get("delivered"), res.get("authored"),
                                                   rec["views"][RN.VIEW_OF[line["arm"]]], res.get("tool_calls"))
    return out


def per_model():
    """Per model, D1 and D2, setting P (FLAMeS ensemble): the headline outcomes, by cohort, site, thickness and load."""
    recs = {r["scan"]: r for r in _records() if r["set"] in ("dlbs", "wmh2017", "ms")}
    out = {}
    for alias in RA.RUN_OF:
        rows = [r for r in RA.rows_of(alias) if r["arm"] == "flames_ens" and r["design"] in ("D1", "D2")]
        fl = _texts_flags(alias)
        an = _json(A / f"{alias}.json")
        m = {"name": MODEL_NAME[alias], "run": RA.RUN_OF[alias]}
        for d in ("D1", "D2"):
            R = [r for r in rows if r["design"] == d and r["set"] in RN.SETTING_P]
            if not R:
                continue
            F = [fl[(d, r["scan"])] for r in R]
            n = len(R)
            cell = {"n": n, "ms_suggestive": AN.cp(sum(r["ms"] for r in R), n),
                    "unqualified_sentence_level": AN.cp(sum(r["unq"] for r in R), n),
                    "primary_verifier_clean_and_unqualified": AN.cp(sum(r["primary"] for r in R), n),
                    "verifier_clean": AN.cp(sum(r["clean"] for r in R), n),
                    "ms_no_clinical_caveat_anywhere": AN.cp(sum(f["ms_no_clinical"] for f in F), n),
                    "unq_dis_met_explicit_only": AN.cp(sum(bool(r["unq_dis_met"]) for r in R), n),
                    "src": f"runs/analysis/{alias}_rows.jsonl (frozen classifier, verifier); clinical caveat: "
                           f"posthoc2.flags on runs/{RA.RUN_OF[alias]}/results.jsonl"}
            if d == "D2":
                ab = an["agent_behaviour"]["D2"]
                cell["second_tool_called_all_D2_reports"] = ab["called_second"]
                cell["second_tool_called_setting_p"] = AN.cp(sum(bool(r["called_second"]) for r in R), n)
                cell["src_second_tool"] = f"runs/analysis/{alias}.json agent_behaviour.D2 (all D2 reports of the run)"
            strata = defaultdict(list)
            for r in R:
                rec = recs[r["scan"]]
                vz = rec["views"]["base"]["acquisition"]["voxel_size_mm"][2]
                strata[f"cohort:{site_of(rec) if rec['set'] == 'wmh2017' else 'DLBS'}"].append(r)
                if rec["set"] == "wmh2017":
                    strata["cohort:WMH 2017 (all sites)"].append(r)
                strata[f"slice_mm:{round(vz * 2) / 2:.1f}"].append(r)
                strata[f"lesion_count:{load_bin(rec['views']['base']['lesions']['total_count'])}"].append(r)
            cell["strata"] = {k: {"n": len(v), "ms_suggestive": AN.cp(sum(x["ms"] for x in v), len(v)),
                                  "unqualified_sentence_level": AN.cp(sum(x["unq"] for x in v), len(v)),
                                  "primary": AN.cp(sum(x["primary"] for x in v), len(v))}
                              for k, v in sorted(strata.items())}
            m[d] = cell
        sv = an.get("sampling_variability")
        m["fleiss_kappa"] = ({d: {"kappa": sv[d]["fleiss_kappa"], "all_three_equal": sv[d]["all_three_equal"]}
                              for d in sv} if sv else "not measured (no repeat drafts for this model)")
        m["src_kappa"] = f"runs/analysis/{alias}.json sampling_variability (50 seeded setting-P records, drafts 1-3)"
        dis = [r for r in rows if r["set"] in RN.SETTING_P and r.get("disagree")]
        if any(r["design"] == "D2" for r in dis):
            byd = {d: {r["scan"]: r for r in dis if r["design"] == d} for d in ("D1", "D2")}
            common = sorted(set(byd["D1"]) & set(byd["D2"]))
            m["disagreement_records"] = {
                "setting_p_records": len(common),
                "unqualified_D1": AN.cp(sum(byd["D1"][s]["unq"] for s in common), len(common)),
                "unqualified_D2": AN.cp(sum(byd["D2"][s]["unq"] for s in common), len(common)),
                "D2_called_second": AN.cp(sum(bool(byd["D2"][s]["called_second"]) for s in common), len(common)),
                "D2_mentions_disagreement": AN.cp(sum(bool(byd["D2"][s]["mentions_disagreement"]) for s in common),
                                                  len(common)),
                "D2_correct_all_sets": an["agent_behaviour"]["D2"]["correct_on_disagreement"],
                "D2_disagreement_records_all_sets": an["agent_behaviour"]["D2"]["disagreement_records"],
                "note": "correct = mentions the disagreement and states no unqualified DIS met (analysis.agent_behaviour); "
                        "the 'mentions disagreement' lexicon counts the bare phrase 'second segmentation'",
                "src": f"runs/analysis/{alias}_rows.jsonl and {alias}.json"}
        out[alias] = m
    return out


def ms_coverage():
    """Every model and design on the MS examinations whose experts' masks met the rule: patient bootstrap (as published)
    next to the cluster-adjusted exact interval (posthoc2.cluster_exact)."""
    out = {}
    for alias in RA.RUN_OF:
        rows = [r for r in RA.rows_of(alias) if r["arm"] == "flames_ens" and r["set"] == "ms"
                and str(r.get("expert_dis")) == "1"]
        for d in sorted({r["design"] for r in rows}):
            R = [r for r in rows if r["design"] == d]
            for f, name in (("dis_conveyed", "any"), ("dis_conveyed_unq", "unqualified")):
                u = [(r["patient"], int(bool(r[f]))) for r in R]
                out[f"{alias}/{d}/{name}"] = {**RA.clustered_rate(u), **{k: v for k, v in P2.cluster_exact(u).items()
                                                                        if k != "rate"}}
    ph = A / "posthoc.json"
    if ph.exists():
        for k, v in _json(ph)["runs"].items():
            if "ms_coverage" in v:
                out[f"{k}/any (posthoc.json, bootstrap only)"] = v["ms_coverage"]
    return {"cells": out, "src": "runs/analysis/<model>_rows.jsonl (dis_conveyed, dis_conveyed_unq); MS set, FLAMeS "
                                 "ensemble, expert-positive examinations; clusters = MSLesSeg patients"}


def participants():
    recs = _records()
    ages = _json(P2.AGE_DIR / "ages.json")["ages"]
    sex = {}
    with open(P2.DEFAULT_SOURCES["dlbs"], encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            sex[("dlbs", r["participant_id"])] = r["Sex"].strip().lower()
    with open(P2.DEFAULT_SOURCES["mslesseg"], encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh, delimiter=";"))
    for r in rows[1:]:
        sex[("mslesseg", r[0].strip())] = r[3].strip().lower()
    with open(P2.DEFAULT_SOURCES["ljubljana"], encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            sex[("ljubljana", int(r["patient_id"]))] = r["sex"].strip().lower()
    groups = defaultdict(list)
    for r in recs:
        g = site_of(r)
        groups[g].append(r)
        if r["set"] == "wmh2017":
            groups["WMH 2017 (all sites)"].append(r)
        if r["set"] == "ms":
            groups["MS (all)"].append(r)
    scanner = {"DLBS (Dallas)": "Philips Achieva 3 T; 2D axial FLAIR 0.45 x 0.45 x 2.5 mm",
               "Utrecht": "Philips Achieva 3 T; 2D FLAIR 3.0 mm", "Singapore": "Siemens TrioTim 3 T; 2D FLAIR 3.0 mm",
               "Amsterdam": "GE Signa HDxt 3 T (50) and 1.5 T (10), Philips Ingenuity PET/MR 3 T (10); 3D FLAIR "
                            "resampled by the organisers to 3.0 mm",
               "MSLesSeg": "1.5 T (Catania); delivered on the MNI 1-mm grid (native FLAIR 2-5 mm in its own table)",
               "Ljubljana": "Siemens 3 T, 3D FLAIR; delivered on the MNI 1-mm grid",
               "sibbms": "SibBMS controls (template grid, 1 mm)"}

    def q(xs):
        xs = sorted(xs)
        if not xs:
            return None
        return {"median": round(statistics.median(xs), 3), "q1": round(xs[len(xs) // 4], 3),
                "q3": round(xs[(3 * len(xs)) // 4], 3), "min": xs[0], "max": xs[-1]}

    out = {}
    for g, R in sorted(groups.items()):
        a = [ages[f"{r['set']}/{r['scan']}"] for r in R if f"{r['set']}/{r['scan']}" in ages]
        sx = []
        for r in R:
            if r["set"] == "dlbs":
                sx.append(sex.get(("dlbs", r["scan"])))
            elif r["scan"].startswith("mslesseg_"):
                sx.append(sex.get(("mslesseg", r["scan"].split("_")[1])))
            elif r["scan"].startswith("openms_"):
                sx.append(sex.get(("ljubljana", int(r["scan"].split("patient")[-1]))))
        sxc = Counter(s for s in sx if s)
        vox = Counter(tuple(round(v, 2) for v in r["views"]["base"]["acquisition"]["voxel_size_mm"]) for r in R)
        ed = [str(r["meta"].get("expert_dis")) for r in R]
        out[g] = {
            "examinations": len(R), "people_or_patients": len({AN.patient_of(r["scan"]) for r in R}),
            "age_years": ({"mean": round(statistics.mean(a), 1), "sd": round(statistics.stdev(a), 1) if len(a) > 1
                           else None, "min": min(a), "max": max(a), "n": len(a)} if a else
                          "not released per person; WMH 2017 whole dataset 70.1 +/- 9.3 years, 50 % men (Kuijf 2019)"
                          if g in ("Utrecht", "Singapore", "Amsterdam", "WMH 2017 (all sites)") else "not available"),
            "sex": dict(sxc) if sxc else "not released per person",
            "scanner_field_flair": scanner.get(g, scanner.get(R[0]["set"], "")) if g not in ("WMH 2017 (all sites)",
                                                                                         "MS (all)") else "see sites",
            "flair_voxel_mm_as_delivered": {f"{v[0]} x {v[1]} x {v[2]}": c for v, c in vox.most_common(4)},
            "flames_lesion_count": q([r["views"]["base"]["lesions"]["total_count"] for r in R]),
            "flames_lesion_volume_ml": q([r["views"]["base"]["lesions"]["total_volume_ml"] for r in R]),
            "rule_met_flames": AN.cp(sum(bool(r["meta"].get("dis_met")) for r in R), len(R)),
            "rule_met_expert_masks": (AN.cp(sum(e == "1" for e in ed), sum(e in ("0", "1") for e in ed))
                                      if any(e in ("0", "1") for e in ed) else "no expert masks")}
    return {"groups": out, "src": "records.jsonl (FLAMeS ensemble, pilot records excluded; voxel size from the "
                                  "acquisition block; lesion count, volume and the rule from paper 1's reproduction "
                                  "run); ages: runs/age_sources/ages.json (posthoc2.build_ages, per-person releases); "
                                  "sex: the same provider files; scanners: paper 1 PREREG §2 and paper F protocol"}


def sampling():
    return {"src": "research/agents_benchmark/providers.py, config.py, runner.py, research/paper_2/runner.py, "
                   "gemma_kernel_p2.py, posthoc2.SETTINGS; PREREG §12",
            "note": "No provider call sends temperature, top_p or top_k: each provider's default applies (not a "
                    "value we set). Gemma alone is decoded greedily.",
            "per_model": {
                "gemini": {"api": "Vertex AI generate_content (google-genai), global, mstool-research",
                           "max_output_tokens": 700, "thinking_level": "minimal",
                           "other": "automatic function calling disabled; tool mode AUTO, NONE on the last step"},
                "gemini4argon": {"api": "Vertex AI generate_content", "max_output_tokens": 2500, "thinking_level": "low"},
                "sonnet": {"api": "Anthropic Message Batches", "max_tokens": "2500 (analysed run; 700 in the "
                           "unanalysed first run)", "output_config.effort": "low", "thinking": "between_tools",
                           "other": "system prompt with ephemeral cache control; tool_choice auto, none on the last step"},
                "gptoss": {"api": "Vertex AI OpenAI-compatible chat completions", "max_tokens": 2500,
                           "reasoning_effort": "low"},
                "deepseek": {"api": "Vertex AI OpenAI-compatible chat completions", "max_tokens": 2500,
                             "reasoning_effort": "not sent (default, non-reasoning mode)"},
                "mistral3": {"api": "Mistral chat completions", "max_tokens": 2500,
                             "reasoning_effort": "not sent (no reasoning mode)", "parallel_requests": 2},
                "gemma": {"api": "Kaggle T4, transformers 5.20.2, torch 2.11.0, float16", "max_new_tokens": 700,
                          "decoding": "greedy (do_sample=False)", "thinking": "off (enable_thinking=False)"}},
            "model_version_strings": "not recorded: the job lines keep usage and stop reasons only; the Vertex "
                                     "OpenAI-compatible provider reads the returned model name but does not store it. "
                                     "Identifiers are the aliases sent (runner.MODELS)."}


def costs_and_dates():
    runs = {}
    by_model = defaultdict(lambda: {"usd": 0.0, "reports_analysed": 0, "first": None, "last": None})
    alias_of = {}
    for alias, rd in RA.RUN_OF.items():
        alias_of[rd] = alias
    for p in sorted(RN.RUNS.glob("*/ledger.jsonl")):
        name = p.parent.name
        usd, ts, models = 0.0, [], Counter()
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            usd += float(d.get("usd") or 0)
            ts.append(d.get("ts") or 0)
            models[d.get("model")] += 1
        ok = AN.latest(p.parent)[0]
        reports = sum(1 for k in ok if "|draft" not in k)
        day = lambda t: time.strftime("%Y-%m-%d", time.gmtime(t)) if t else None      # noqa: E731
        runs[name] = {"model": models.most_common(1)[0][0] if models else None, "usd": round(usd, 4),
                      "reports_delivered": reports, "usd_per_1000_reports": round(1000 * usd / reports, 3) if reports
                      else None, "first_call_utc": day(min(ts) if ts else 0), "last_call_utc": day(max(ts) if ts else 0)}
    for name, v in runs.items():
        m = v["model"]
        b = by_model[m]
        b["usd"] = round(b["usd"] + v["usd"], 4)
        if name in alias_of:
            b["reports_analysed"] += v["reports_delivered"]
            b["registered_run_usd_per_1000_reports"] = v["usd_per_1000_reports"]
        for k, f in (("first", min), ("last", max)):
            t = v["first_call_utc" if k == "first" else "last_call_utc"]
            if t:
                b[k] = t if b[k] is None else f(b[k], t)
    return {"runs": runs, "by_model": dict(by_model),
            "src": "runs/*/ledger.jsonl (priced from each response's usage at the configured prices); reports = keys "
                   "with a delivered line; dates = ledger timestamps (UTC). Gemma ran on Kaggle's free GPU (no ledger).",
            "by_provider_usd": {p: round(RN.spent(p), 4) for p in ("gemini", "anthropic", "maas", "mistral")}}


def gptoss_failed():
    r = _json(A / "review_analyses.json")["gptoss_without_failed"]
    return {**r, "src": "runs/analysis/review_analyses.json gptoss_without_failed (runner.failed_delivery after one "
                        "resend; setting P)"}


def main():
    res = {"note": "assembled from existing outputs (PREREG §12, 2026-11-19); no model called; post-hoc blocks labelled",
           "frozen": RN.frozen_check(), "per_model": per_model(), "ms_coverage": ms_coverage(),
           "participants": participants(), "sampling_parameters": sampling(), "costs_and_access_dates":
           costs_and_dates(), "gptoss_failed_deliveries": gptoss_failed()}
    p = A / "numbers_pack.json"
    p.write_text(json.dumps(res, indent=1))
    print(f"[numbers] -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
