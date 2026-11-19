"""Post-hoc experiments E3 and E4 after the independent review of 2026-11-18 (PREREG §12, 2026-11-19). Exploratory;
registered in the log, with this file, its analysis and its tests committed, before any of their reports existed. The
frozen files (runner.FROZEN) are not touched: the designs below subclass D1 and D2 and change only the record they read.
Prompts, tools and their descriptions are those of D1 and D2, unchanged.

E3, D2p (review A3, "provenance-labelled second tool"): D2, except that the output of get_second_segmentation carries
    the provenance fields of the primary record (basis "automatic, unreviewed AI marking (no radiologist confirmation)",
    confirmed false, and the regions given as an unconfirmed block, as the primary record's regions). Question: is D2's
    increase an artefact of a second-tool output without provenance?
E4, D1f and D2f (review A2, "the record fixed"): (i) the DIS block's label "criteria": "McDonald 2024 (...)" is replaced
    by "rule": RULE; (ii) a field "interpretation": INTERPRETATION is added to the DIS block; (iii) the person's age in
    years, "person_age_years", is added to the DIS block only where the data provider releases it per person
    (`build_ages`; DLBS, MSLesSeg and Ljubljana yes, WMH 2017 no). D2f = D2 on that record, with the second tool labelled
    as in D2p and carrying the same interpretation field. Question: does a record that states what the rule is (and is
    not) reduce the unqualified relay, and what does it cost in MS?

Records: FLAMeS ensemble, setting P (DLBS, WMH 2017) and the MS examinations, pilot records excluded (393), as E1/E2.
Pilot: the FLAMeS-ens records of the registered pilot set (PREREG §8; never analysed), within the model's registered sets.

    python -m research.paper_2.posthoc2 ages                         -> runs/age_sources/ages.json
    python -m research.paper_2.posthoc2 pilot   --model gemini --design D2p
    python -m research.paper_2.posthoc2 project                       (pilots -> projected plan, reductions applied)
    python -m research.paper_2.posthoc2 campaign                      (the projected plan; one lane per provider)
    python -m research.paper_2.posthoc2 analyse                       -> runs/analysis/posthoc2.json
"""
import argparse
import copy
import csv
import hashlib
import json
import math
import os
import random
import threading
import time
from collections import defaultdict
from pathlib import Path

from research.paper_2 import designs as D
from research.paper_2 import runner as RN

# ------------------------------------------------------------------------------------------------ record changes
BASIS = "automatic, unreviewed AI marking (no radiologist confirmation)"
REGION_SOURCE = "automatic, unreviewed (computed on the AI marking)"
RULE = ("automated location-only rule modeled on the brain dissemination-in-space criterion; not the McDonald "
        "criteria")
INTERPRETATION = ("Automated location-only count. It does not apply the 2024 McDonald criteria: periventricular caps, "
                  "lesions atypical of multiple sclerosis, age and vascular risk are not taken into account. Location "
                  "rules of this kind are also met in most adults over 50 years of age and in most people with "
                  "vascular white matter hyperintensities. It is not evidence of multiple sclerosis without a "
                  "radiologist's review of the lesions and of the clinical context.")
AGE_FIELD = "person_age_years"


def labelled_second(sec, interpretation=False):
    """get_second_segmentation's output with the primary record's provenance fields (D2p); with the interpretation
    field on its DIS block as well (D2f). An unavailable second tool stays as it is."""
    if not sec or sec.get("available") is False:
        return copy.deepcopy(sec)
    out = {"tool": sec.get("tool"), "basis": BASIS, "confirmed": False}
    for k, v in sec.items():
        if k == "tool":
            continue
        if k == "regions" and isinstance(v, dict) and "lesion_counts" not in v:
            out["regions"] = {"confirmed": False, "source": REGION_SOURCE, "lesion_counts": copy.deepcopy(v)}
        elif k == "dis" and isinstance(v, dict):
            d = {"status": v.get("status"), "basis": BASIS}
            d.update({kk: copy.deepcopy(vv) for kk, vv in v.items() if kk not in ("status", "basis")})
            if interpretation and v.get("status") == "evaluated":
                d["interpretation"] = INTERPRETATION
            out["dis"] = d
        else:
            out[k] = copy.deepcopy(v)
    return out


def fixed_dis(dis, age=None):
    """The DIS block of E4: the 'criteria' label replaced in place by 'rule', then 'interpretation' and, where released,
    the person's age in whole years."""
    out = {}
    for k, v in dis.items():
        if k == "criteria":
            out["rule"] = RULE
            continue
        out[k] = copy.deepcopy(v)
    if dis.get("status") == "evaluated":
        out.setdefault("rule", RULE)
        out["interpretation"] = INTERPRETATION
    if age is not None:
        out[AGE_FIELD] = int(age)
    return out


VIEW = {"D2p": "d2", "D1f": "base", "D2f": "d2"}


def view_for(rec, design, ages=None):
    v = copy.deepcopy(rec["views"][VIEW[design]])
    if design in ("D1f", "D2f"):
        v["dis"] = fixed_dis(v["dis"], (ages or {}).get(f'{rec["set"]}/{rec["scan"]}'))
    if design in ("D2p", "D2f") and v.get("second_segmentation"):
        v["second_segmentation"] = labelled_second(v["second_segmentation"], interpretation=design == "D2f")
    return v


class D2p(D.D2):
    arm = "D2p"


class D2f(D.D2):
    arm = "D2f"


class D1f(D.D1):
    arm = "D1f"


CLASSES = {"D2p": D2p, "D1f": D1f, "D2f": D2f}
PLAN = {"D2p": ("gemini", "sonnet", "mistral3"), "D1f": ("gemini", "gptoss", "sonnet"),
        "D2f": ("gemini", "gptoss", "sonnet")}
SETS = ("dlbs", "wmh2017", "ms")
# the logged settings of each model (PREREG §12): Gemini 3.1 Flash-Lite its registered ones (700 tokens, thinking
# minimal); the secondary models 2,500 tokens at their lowest reasoning (Sonnet effort low with thinking between tools,
# set by the provider; gpt-oss reasoning effort low; Mistral Large 3 has no reasoning mode, 2 parallel requests)
SETTINGS = {"gemini": {"max_tokens": None, "workers": 8, "reasoning": "thinking level minimal",
                       "env": {"AB_GEMINI_ATTEMPTS": "8", "AB_GEMINI_THINKING_LEVEL": None}},
            "sonnet": {"max_tokens": 2500, "workers": None, "reasoning": "effort low, thinking between_tools",
                       "env": {"AB_ANTHROPIC_KEY_FROM_ENV": "1"}},
            "gptoss": {"max_tokens": 2500, "workers": 8, "reasoning": "reasoning_effort low", "env": {}},
            "mistral3": {"max_tokens": 2500, "workers": 2, "reasoning": "none (no reasoning mode)", "env": {}}}
BATCH_CHUNK = 50          # Claude: jobs per batch, so that the worst-case check before each batch stays meaningful
MS_HALF_SEED = f"{RN.SEED}-posthoc2-ms-half"
# the amendment's caps (PREREG §12, 2026-11-19): hard stops of runner.CAP unchanged; projection limits
AMENDMENT_ANTHROPIC_LIMIT = 7.0
PROJECTION_LIMIT = {"gemini": RN.PROJECTION_LIMIT["gemini"], "maas": RN.PROJECTION_LIMIT["maas"],
                    "mistral": RN.PROJECTION_LIMIT["mistral"]}
REFERENCE_RUN = {("gemini", "D1"): "gemini-full", ("gemini", "D2"): "gemini-full",
                 ("sonnet", "D1"): "sonnet-full-long", ("sonnet", "D2"): "sonnet-full-long",
                 ("gptoss", "D1"): "gptoss-full-long", ("gptoss", "D2"): "gptoss-full-long",
                 ("mistral3", "D1"): "mistral3-full-long", ("mistral3", "D2"): "mistral3-full-long"}


# ------------------------------------------------------------------------------------------------ ages
AGE_DIR = RN.RUNS / "age_sources"
DEFAULT_SOURCES = {
    "dlbs": AGE_DIR / "dlbs" / "participants.tsv",
    "mslesseg": AGE_DIR / "mslesseg" / "clinical_data.csv",
    "ljubljana": AGE_DIR / "ljubljana" / "patient_info.csv",
}


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _mslesseg_key(scan):
    parts = scan.split("_")                     # mslesseg_P10_T1, or mslesseg_P55 (test patients: one time point, T1)
    return parts[1], (parts[2] if len(parts) > 2 else "T1")


def build_ages(records, sources):
    """Age in whole years per record of E4's sets, only where the provider releases it per person:
    - DLBS (OpenNeuro ds004856 1.3.0, participants.tsv, CC0): AgeMRI_W1, the age at the wave-1 MRI (whole years);
    - MSLesSeg (Figshare 52771814, info_dataset/clinical_data.csv, CC BY 4.0): Age per patient and time point, decimal
      years with a decimal comma -> completed years (floor);
    - Ljubljana (open_ms_data, cross_sectional/patient_info.csv, CC BY): age per patient (whole years);
    - WMH 2017: not released per person (Kuijf 2019 gives the whole dataset's mean only) -> no field.
    Returns {"ages": {"<set>/<scan>": years}, "availability": ..., "sources": {name: sha256}}."""
    dl = {}
    with open(sources["dlbs"], encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            v = (r.get("AgeMRI_W1") or "").strip()
            if v and v.lower() != "n/a":
                dl[r["participant_id"]] = int(math.floor(float(v)))
    ml = {}
    with open(sources["mslesseg"], encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh, delimiter=";"))
    head = [h.strip() for h in rows[0]]
    ip, it, ia = head.index("Patient"), head.index("Timepoint"), head.index("Age")
    for r in rows[1:]:
        if len(r) > ia and r[ia].strip():
            ml[(r[ip].strip(), r[it].strip())] = int(math.floor(float(r[ia].strip().replace(",", "."))))
    lj = {}
    with open(sources["ljubljana"], encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            v = (r.get("age") or "").strip()
            if v and v.upper() != "N/A":
                lj[int(r["patient_id"])] = int(math.floor(float(v)))
    ages, avail = {}, defaultdict(lambda: {"records": 0, "with_age": 0})
    for rec in records:
        if rec["arm"] != "flames_ens" or rec["set"] not in SETS:
            continue
        s, scan = rec["set"], rec["scan"]
        src = ("dlbs" if s == "dlbs" else "wmh2017" if s == "wmh2017" else
               "mslesseg" if scan.startswith("mslesseg_") else "ljubljana" if scan.startswith("openms_") else "other")
        age = None
        if src == "dlbs":
            age = dl.get(scan)
        elif src == "mslesseg":
            age = ml.get(_mslesseg_key(scan))
        elif src == "ljubljana":
            age = lj.get(int(scan.split("patient")[-1]))
        avail[src]["records"] += 1
        if age is not None:
            avail[src]["with_age"] += 1
            ages[f"{s}/{scan}"] = age
    return {"ages": ages, "availability": dict(avail),
            "sources": {k: {"file": str(v), "sha256": _sha(v)} for k, v in sources.items()}}


def load_ages():
    p = AGE_DIR / "ages.json"
    return json.loads(p.read_text(encoding="utf-8"))["ages"] if p.exists() else None


# ------------------------------------------------------------------------------------------------ jobs and runs
def ms_half(records):
    pilot = RN.pilot_set(records)
    scans = sorted(r["scan"] for r in records if r["arm"] == "flames_ens" and r["set"] == "ms"
                   and (r["scan"], r["arm"]) not in pilot)
    return set(random.Random(MS_HALF_SEED).sample(scans, len(scans) // 2))


def jobs_for(records, design, alias, phase="full", ages=None, sets=SETS, ms_subset=None):
    if design in ("D1f", "D2f") and ages is None:
        raise SystemExit("ages.json is missing: run `posthoc2 ages` first (E4 records carry the released ages)")
    pilot = RN.pilot_set(records)
    plan_sets = RN.PLAN[alias].get("sets")
    out = []
    for rec in records:
        if rec["arm"] != "flames_ens":
            continue
        in_pilot = (rec["scan"], rec["arm"]) in pilot
        if phase == "pilot":
            if not in_pilot or (plan_sets and rec["set"] not in plan_sets):
                continue
        else:
            if in_pilot or rec["set"] not in sets:
                continue
            if ms_subset is not None and rec["set"] == "ms" and rec["scan"] not in ms_subset:
                continue
        view = view_for(rec, design, ages)
        out.append(CLASSES[design]({"record_id": view["record_id"], "view": view,
                                    "meta": {"scan": rec["scan"], "arm": rec["arm"], "set": rec["set"]}, "a0": None}))
    return out


def run_name(alias, design, phase):
    return f"posthoc-{alias}-{design}" + ("-pilot" if phase == "pilot" else "")


_ENV_LOCK = threading.Lock()


def _apply_env(alias):
    """Per-model settings through the providers' environment switches (no key is ever printed or written). The
    Anthropic key of this computer's environment lacks its first character (PREREG §12, 2026-11-16); it is completed in
    this process only."""
    with _ENV_LOCK:
        for k, v in SETTINGS[alias]["env"].items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        if alias == "sonnet":
            k = os.environ.get("ANTHROPIC_API_KEY", "")
            if k.startswith("k-ant-"):
                os.environ["ANTHROPIC_API_KEY"] = "s" + k


def _env_record(alias):
    return {k: v for k, v in SETTINGS[alias]["env"].items() if k != "AB_ANTHROPIC_KEY_FROM_ENV"}


def provider_for_alias(alias, run_dir):
    """The providers of the logged arms. The reasoning setting of the two OpenAI-compatible models is fixed per provider
    instance (not through the shared environment switch), so that the lanes, which run in parallel, cannot mix them."""
    from research.agents_benchmark import providers as PV
    if alias == "gptoss":
        class GptOssLow(PV.VertexOpenAI):
            @classmethod
            def body(cls, model, req):
                b = super().body(model, req)
                b["reasoning_effort"] = "low"
                return b
        return GptOssLow(run_dir, workers=SETTINGS[alias]["workers"])
    if alias == "mistral3":
        class Mistral3(PV.MistralAPI):
            @classmethod
            def body(cls, model, req):
                b = super().body(model, req)
                b.pop("reasoning_effort", None)
                return b
        return Mistral3(run_dir, workers=SETTINGS[alias]["workers"])
    return PV.provider_for(RN.MODELS[alias], run_dir)


def run_batch_chunked(provider, model, jobs, out, max_tokens, chunk=BATCH_CHUNK):
    agg = {"calls": 0, "rounds": 0, "done": 0, "unfinished": 0, "stopped": None, "chunks": 0}
    for i in range(0, len(jobs), chunk):
        part = jobs[i:i + chunk]
        sub = RN.run_batch(provider, model, part, out, {}, max_tokens)
        agg["chunks"] += 1
        for k in ("calls", "rounds", "done", "unfinished"):
            agg[k] += sub.get(k) or 0
        if sub.get("stopped"):
            agg["stopped"] = sub["stopped"]
            agg["unfinished"] += len(jobs) - i - len(part)
            break
    return agg


def failed_or_missing(path, jobs):
    done = RN.done_keys(path)
    return [j for j in jobs if j.key not in done]


def run(alias, design, phase="full", ms_subset=None, sets=SETS, provider=None, passes=2):
    """One run, then one resend of the keys without a report (network errors and failed deliveries), then stop.
    Every pass builds fresh jobs (a finished job object sends nothing again). `passes=1` sends only the keys still
    without a report: the resend of a run whose first process ended (PREREG §12, 2026-11-19)."""
    if alias not in PLAN[design]:
        raise SystemExit(f"{alias} is not planned for {design}")
    if phase == "full":
        fz = RN.frozen_check()
        if not fz["passed"]:
            raise SystemExit(f"frozen files changed: {fz['changed']} (PREREG §8): log a deviation first")
    model = RN.MODELS[alias]
    st = SETTINGS[alias]
    _apply_env(alias)
    rd = RN.RUNS / run_name(alias, design, phase)
    rd.mkdir(parents=True, exist_ok=True)
    out = rd / "results.jsonl"
    records, ages = RN.load_records(), load_ages()
    all_jobs = jobs_for(records, design, alias, phase, ages, sets, ms_subset)
    if provider is None:
        provider = provider_for_alias(alias, rd)
    info = {"model": model, "design": design, "phase": phase, "max_tokens_override": st["max_tokens"],
            "reasoning": st["reasoning"], "settings_env": _env_record(alias), "workers": st["workers"],
            "planned": len(all_jobs),
            "ms_subset": None if ms_subset is None else len(ms_subset), "sets": list(sets),
            "started": time.time(), "frozen": RN.frozen_check(), "passes": []}
    for attempt in range(1, passes + 1):        # the first pass and at most one resend (PREREG §12, 2026-11-17)
        jobs = failed_or_missing(out, jobs_for(records, design, alias, phase, ages, sets, ms_subset))
        if not jobs:
            break
        print(f"[posthoc2] {alias}/{design}/{phase} pass {attempt}: {len(jobs)} jobs", flush=True)
        if getattr(provider, "batch", False):
            p = run_batch_chunked(provider, model, jobs, out, st["max_tokens"])
        else:
            p = RN.run_online(provider, model, jobs, out, {}, st["workers"], st["max_tokens"])
        info["passes"].append({k: p.get(k) for k in ("calls", "done", "unfinished", "stopped", "chunks", "rounds")})
        if p.get("stopped"):
            break
    info["without_report"] = len(failed_or_missing(out, all_jobs))
    info["ended"] = time.time()
    (rd / f"run_info_{int(info['started'])}.json").write_text(json.dumps(info, indent=1))
    print(f"[posthoc2] {alias}/{design}/{phase}: {len(all_jobs) - info['without_report']}/{len(all_jobs)} with a "
          f"report", flush=True)
    return info


def last_ok(run_dir):
    last = {}
    p = Path(run_dir) / "results.jsonl"
    for x in (p.read_text(encoding="utf-8").splitlines() if p.exists() else []):
        if x.strip():
            r = json.loads(x)
            if (r.get("result") or {}).get("status") == "ok":
                last[r["key"]] = r
    return last


def qa_of(alias, design, phase):
    rows = list(last_ok(RN.RUNS / run_name(alias, design, phase)).values())
    q = RN.qa(rows)
    q["failed_deliveries"] = sum(RN.failed_delivery(r) for r in rows)
    return q


def gate_failed_runs():
    """Full runs of the amendment that failed `runner.qa`: by the amendment's rule they stop and are not analysed
    (PREREG §12, 2026-11-19; gpt-oss-120b D2f). Computed, not listed, so that every analysis applies the same gate."""
    return {(a, d) for d, aliases in PLAN.items() for a in aliases
            if (RN.RUNS / run_name(a, d, "full") / "results.jsonl").exists() and not qa_of(a, d, "full")["passed"]}


# ------------------------------------------------------------------------------------------------ projection
def _ledger_usd(run_dir):
    p = Path(run_dir) / "ledger.jsonl"
    tot = 0.0
    for line in (p.read_text(encoding="utf-8").splitlines() if p.exists() else []):
        try:
            tot += float(json.loads(line).get("usd") or 0)
        except ValueError:
            continue
    return tot


def reference_per_job(alias, design, records):
    """Mean cost per report of the same model's registered design on the E3/E4 records (conservative floor)."""
    base = "D1" if design == "D1f" else "D2"
    rd = RN.RUNS / REFERENCE_RUN[(alias, base)]
    by_rid = {v["record_id"]: r for r in records for v in r["views"].values()}
    us = [r.get("usd") or 0 for r in last_ok(rd).values()
          if r["arm"] == base and (by_rid.get(r["record_id"]) or {}).get("set") in SETS
          and (by_rid.get(r["record_id"]) or {}).get("arm") == "flames_ens"]
    return sum(us) / len(us) if us else None


def plan_runs(costs, spent, n_full, n_ms, n_ms_half, mistral_n_p):
    """Apply the amendment's caps and reduction order to per-job cost estimates.
    costs: {(alias, design): usd per job}; spent: {provider: usd already spent, the amendment's pilots included};
    returns the list of runs [(alias, design, scope)] and the projection per provider.
    Reduction order (PREREG §12, 2026-11-19): Anthropic (1) drop Sonnet D1f; (2) Sonnet on setting P plus a seeded half
    of the MS records. Mistral: setting P only if the full set does not fit. Google and open models: no reduction (a
    run that does not fit is not started)."""
    from research.agents_benchmark.ledger import provider_of
    runs = [(a, d, "full") for d, aliases in PLAN.items() for a in aliases]
    prov_of = {a: provider_of(RN.MODELS[a]) for a in SETTINGS}

    def proj(rs):
        out = defaultdict(float)
        for a, d, scope in rs:
            n = n_full - n_ms + n_ms_half if scope == "ms_half" else (mistral_n_p if scope == "setting_p" else n_full)
            out[prov_of[a]] += costs[(a, d)] * n
        return out

    def fits(rs):
        p = proj(rs)
        ok = {"anthropic": spent.get("anthropic_amendment", 0) + p["anthropic"] <= AMENDMENT_ANTHROPIC_LIMIT
              and spent.get("anthropic", 0) + p["anthropic"] <= RN.CAP["anthropic"]}
        for prov in ("gemini", "maas", "mistral"):
            ok[prov] = spent.get(prov, 0) + p[prov] <= PROJECTION_LIMIT[prov]
        return ok

    steps = []
    if not fits(runs)["anthropic"]:
        runs = [r for r in runs if r[:2] != ("sonnet", "D1f")]
        steps.append("anthropic (1): Sonnet D1f dropped")
    if not fits(runs)["anthropic"]:
        runs = [(a, d, "ms_half" if a == "sonnet" else s) for a, d, s in runs]
        steps.append("anthropic (2): Sonnet on setting P plus a seeded half of the MS records")
    if not fits(runs)["mistral"]:
        runs = [(a, d, "setting_p" if a == "mistral3" else s) for a, d, s in runs]
        steps.append("mistral: setting P only")
    ok = fits(runs)
    final = [r for r in runs if ok[prov_of[r[0]]]]
    dropped = [r for r in runs if not ok[prov_of[r[0]]]]
    return {"runs": final, "not_started": dropped, "reductions": steps, "projected_usd": dict(proj(final)),
            "fits": ok}


def project():
    from research.agents_benchmark.ledger import provider_of
    records = RN.load_records()
    costs, detail = {}, {}
    for d, aliases in PLAN.items():
        for a in aliases:
            rd = RN.RUNS / run_name(a, d, "pilot")
            rows = list(last_ok(rd).values())
            pilot_mean = sum(r.get("usd") or 0 for r in rows) / len(rows) if rows else None
            ref = reference_per_job(a, d, records)
            est = max(x for x in (pilot_mean, ref) if x is not None)
            costs[(a, d)] = est
            detail[f"{a}/{d}"] = {"pilot_reports": len(rows), "pilot_mean_usd": pilot_mean, "reference_mean_usd": ref,
                                  "estimate_per_report_usd": est, "pilot_qa": qa_of(a, d, "pilot")}
    pilots_anthropic = sum(_ledger_usd(RN.RUNS / run_name("sonnet", d, "pilot")) for d in PLAN if "sonnet" in PLAN[d])
    spent = {p: RN.spent(p) for p in ("anthropic", "gemini", "maas", "mistral")}
    spent["anthropic_amendment"] = pilots_anthropic
    n_full = len(jobs_for(records, "D2p", "gemini", "full", None))
    n_ms = sum(1 for r in records if r["arm"] == "flames_ens" and r["set"] == "ms"
               and (r["scan"], r["arm"]) not in RN.pilot_set(records))
    plan = plan_runs(costs, spent, n_full, n_ms, len(ms_half(records)), n_full - n_ms)
    gate_failed = [k for k, v in detail.items() if not v["pilot_qa"]["passed"]]
    plan["runs"] = [r for r in plan["runs"] if f"{r[0]}/{r[1]}" not in gate_failed]
    out = {"per_run": detail, "spent_before_full": spent, "n_full": n_full, "n_ms": n_ms, "pilot_gate_failed": gate_failed,
           **plan, "providers": {a: provider_of(RN.MODELS[a]) for a in SETTINGS}}
    p = RN.RUNS / "posthoc2_projection.json"
    p.write_text(json.dumps(out, indent=1, default=list))
    print(json.dumps({k: out[k] for k in ("runs", "not_started", "reductions", "projected_usd", "fits",
                                          "pilot_gate_failed")}, indent=1, default=list))
    return out


def campaign():
    """The projected plan (runs/posthoc2_projection.json), one lane per provider, lanes in parallel; each lane runs its
    models' runs one after another. Written to run unattended (a one-off scheduled task)."""
    proj = json.loads((RN.RUNS / "posthoc2_projection.json").read_text(encoding="utf-8"))
    records = RN.load_records()
    half = ms_half(records)
    lanes = defaultdict(list)
    for a, d, scope in proj["runs"]:
        lanes[proj["providers"][a]].append((a, d, scope))
    log = RN.RUNS / "posthoc2_campaign.jsonl"

    def lane(items):
        for a, d, scope in items:
            t0 = time.time()
            try:
                info = run(a, d, "full", ms_subset=half if scope == "ms_half" else None,
                           sets=("dlbs", "wmh2017") if scope == "setting_p" else SETS)
                q = qa_of(a, d, "full")
                line = {"run": f"{a}/{d}", "scope": scope, "without_report": info["without_report"], "qa": q,
                        "usd": _ledger_usd(RN.RUNS / run_name(a, d, "full")), "seconds": round(time.time() - t0)}
            except Exception as e:  # noqa: BLE001 - logged; the other lanes go on
                line = {"run": f"{a}/{d}", "scope": scope, "error": f"{type(e).__name__}: {str(e)[:300]}"}
            with _ENV_LOCK, open(log, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(line) + "\n")

    ts = [threading.Thread(target=lane, args=(items,)) for items in lanes.values()]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    (RN.RUNS / "posthoc2_campaign.done").write_text(time.strftime("%Y-%m-%d %H:%M:%S"))
    return 0


# ------------------------------------------------------------------------------------------------ analysis
def cluster_exact(units, conf=0.95):
    """Cluster-adjusted exact interval: Clopper-Pearson on the design-effect-adjusted n (Kish), n_eff = n / deff and
    x_eff = p * n_eff, with non-integer beta quantiles. deff = the ratio-estimator variance over patients divided by the
    binomial variance, floored at 1, when 0 < p < 1; when p is 0 or 1 the within-patient correlation cannot be estimated
    and deff = the mean number of examinations per patient (ICC = 1, so n_eff = the number of patients). The interval
    therefore never has zero width."""
    from scipy.stats import beta
    by = defaultdict(lambda: [0, 0])
    for p, v in units:
        by[p][0] += int(v)
        by[p][1] += 1
    k = len(by)
    x = sum(v[0] for v in by.values())
    n = sum(v[1] for v in by.values())
    if n == 0:
        return {"x": 0, "n": 0, "rate": None, "ci95_cluster_exact": [None, None]}
    p = x / n
    if 0 < p < 1 and k > 1:
        var = k / (k - 1) * sum((xi - p * mi) ** 2 for xi, mi in by.values()) / n ** 2
        deff = max(1.0, var / (p * (1 - p) / n))
    else:
        deff = n / k
    n_eff = n / deff
    x_eff = p * n_eff
    a = 1 - conf
    lo = 0.0 if x_eff <= 0 else float(beta.ppf(a / 2, x_eff, n_eff - x_eff + 1))
    hi = 1.0 if x_eff >= n_eff else float(beta.ppf(1 - a / 2, x_eff + 1, n_eff - x_eff))
    return {"x": x, "n": n, "patients": k, "rate": round(p, 4), "design_effect": round(deff, 3),
            "n_effective": round(n_eff, 2), "ci95_cluster_exact": [round(lo, 4), round(hi, 4)]}


def flags(delivered, authored=None, view=None, tool_calls=None):
    """Every per-report outcome of the amendment, with the same code for the new runs and their comparators."""
    from research.agents_benchmark import lexicon as L
    from research.agents_benchmark import verifier as V
    from research.paper_2 import review_analyses as RA
    from research.paper_2.classifier import classify
    t = delivered or ""
    c = classify(t, code_texts=[], boilerplate=D.BOILERPLATE)
    body = L.fold(RA.model_body(t))
    conveyed = [h for h in c["hits"] if h["rule"] in ("a", "c")]
    out = {"ms": c["ms_suggestive"], "unq": c["unqualified"],
           "unq_automat": RA.classify_with(RA.AUTOMAT, t)["unqualified"],
           "clinical_any": bool(RA.CLINICAL.search(body)), "provenance_any": bool(RA.PROVENANCE.search(body)),
           "dis_met_sentences": sum(h["rule"] == "a" for h in c["hits"]),
           "dis_conveyed": bool(conveyed), "dis_conveyed_unq": any(not h["qualified"] for h in conveyed),
           "unq_dis_met": any(h["rule"] == "a" and not h["qualified"] for h in c["hits"]),
           "called_second": "get_second_segmentation" in (tool_calls or [])}
    out["ms_no_clinical"] = out["ms"] and not out["clinical_any"]
    if view is not None:
        out["clean"] = not V.verify(authored or "", t, D.support_view(view))["primary"]
    return out


PAIRED_FIELDS = ("unq", "ms", "ms_no_clinical", "unq_automat")


def paired(a, b, field, seed=None):
    """a, b: {scan: flags}; exact McNemar and a bootstrap CI over people of mean(b) - mean(a)."""
    import numpy as np
    from scipy.stats import binomtest

    from research.paper_2 import analysis as AN
    common = sorted(set(a) & set(b))
    pairs = [(bool(a[s][field]), bool(b[s][field])) for s in common]
    if not pairs:
        return None
    x_only = sum(x and not y for x, y in pairs)
    y_only = sum(y and not x for x, y in pairs)
    dd = np.array([int(y) - int(x) for x, y in pairs])
    rng = np.random.default_rng(AN.BOOT_SEED if seed is None else seed)
    bs = dd[rng.integers(0, len(dd), size=(AN.BOOT, len(dd)))].mean(1)
    return {"n": len(pairs), "first": AN.cp(sum(x for x, _ in pairs), len(pairs)),
            "second": AN.cp(sum(y for _, y in pairs), len(pairs)), "first_only": x_only, "second_only": y_only,
            "difference": round(float(dd.mean()), 4),
            "ci95_people_bootstrap": [round(float(np.percentile(bs, 2.5)), 4), round(float(np.percentile(bs, 97.5)), 4)],
            "p_exact_mcnemar": float(binomtest(min(x_only, y_only), x_only + y_only, 0.5).pvalue) if x_only + y_only
            else 1.0}


def summarise(per):
    """per: {scan: flags + set, patient, expert_dis}."""
    from research.paper_2 import analysis as AN
    from research.paper_2 import review_analyses as RA
    P = [v for v in per.values() if v["set"] in RN.SETTING_P]
    n = len(P)
    ms_n = sum(v["ms"] for v in P)
    out = {"n_setting_p": n, "n_ms_set": sum(v["set"] == "ms" for v in per.values()),
           "unqualified": AN.cp(sum(v["unq"] for v in P), n),
           "unqualified_automat": AN.cp(sum(v["unq_automat"] for v in P), n),
           "ms_suggestive": AN.cp(ms_n, n),
           "ms_no_clinical_caveat_anywhere": AN.cp(sum(v["ms_no_clinical"] for v in P), n),
           "clinical_caveat_any_report": AN.cp(sum(v["clinical_any"] for v in P), n),
           "clinical_caveat_among_ms": AN.cp(sum(v["ms"] and v["clinical_any"] for v in P), ms_n),
           "provenance_caveat_any_report": AN.cp(sum(v["provenance_any"] for v in P), n),
           "provenance_caveat_among_ms": AN.cp(sum(v["ms"] and v["provenance_any"] for v in P), ms_n),
           "unq_dis_met": AN.cp(sum(v["unq_dis_met"] for v in P), n),
           "dis_met_sentences_per_report": round(sum(v["dis_met_sentences"] for v in P) / n, 3) if n else None,
           "second_tool_called_setting_p": AN.cp(sum(v["called_second"] for v in P), n),
           "second_tool_called_all": AN.cp(sum(v["called_second"] for v in per.values()), len(per))}
    if all("clean" in v for v in P):
        out["verifier_clean"] = AN.cp(sum(v["clean"] for v in P), n)
        out["verifier_clean_and_unqualified"] = AN.cp(sum(v["clean"] and v["unq"] for v in P), n)
    ms = [v for v in per.values() if v["set"] == "ms" and str(v.get("expert_dis")) == "1"]
    if ms:
        for f, name in (("dis_conveyed", "ms_coverage"), ("dis_conveyed_unq", "ms_coverage_unqualified")):
            u = [(v["patient"], int(bool(v[f]))) for v in ms]
            out[name] = {**RA.clustered_rate(u), **{k: v for k, v in cluster_exact(u).items()
                                                    if k in ("design_effect", "n_effective", "ci95_cluster_exact")}}
    return out


def _per_from(lines, by_rid, view_of):
    from research.paper_2 import analysis as AN
    per = {}
    for r in lines.values():
        rec = by_rid.get(r["record_id"])
        if rec is None or rec["arm"] != "flames_ens" or rec["set"] not in SETS:
            continue
        res = r["result"]
        f = flags(res.get("delivered"), res.get("authored"), view_of(rec, r["arm"]), res.get("tool_calls"))
        f.update({"set": rec["set"], "patient": AN.patient_of(rec["scan"]), "expert_dis": rec["meta"].get("expert_dis"),
                  "failed_delivery": RN.failed_delivery(r)})
        per[rec["scan"]] = f
    return per


def analyse():
    from research.paper_2 import analysis as AN
    from research.paper_2 import review_analyses as RA
    records = RN.load_records()
    pilot = RN.pilot_set(records)
    by_rid = {v["record_id"]: r for r in records if (r["scan"], r["arm"]) not in pilot for v in r["views"].values()}
    ages = load_ages()
    res = {"note": "post hoc (PREREG §12, 2026-11-19); exploratory; never pooled with the registered arms",
           "frozen": RN.frozen_check(), "runs": {}, "comparators": {}, "paired": {}}
    stopped = gate_failed_runs()
    res["stopped_at_quality_gate"] = {f"{a}/{d}": qa_of(a, d, "full") for a, d in sorted(stopped)}
    new = {}
    for design, aliases in PLAN.items():
        for alias in aliases:
            rd = RN.RUNS / run_name(alias, design, "full")
            if not (rd / "results.jsonl").exists() or (alias, design) in stopped:
                continue
            lines = last_ok(rd)
            per = _per_from(lines, by_rid, lambda rec, arm: view_for(rec, arm, ages))
            s = summarise(per)
            s.update({"qa": qa_of(alias, design, "full"), "failed_deliveries": sum(v["failed_delivery"]
                                                                                  for v in per.values()),
                      "usd": round(_ledger_usd(rd), 4)})
            res["runs"][f"{alias}/{design}"] = s
            new[(alias, design)] = per
    comps = {}
    for alias in sorted({a for a, _ in new}):
        texts = RA.texts_of(alias)
        rows = {r["key"]: r for r in RA.rows_of(alias)}
        for base in ("D1", "D2"):
            sel = {k: v for k, v in texts.items() if v["arm"] == base}
            per = _per_from(sel, by_rid, lambda rec, arm: rec["views"][RN.VIEW_OF[arm]])
            for k, v in sel.items():               # the same classifier and verifier as the registered analysis
                rec = by_rid.get(v["record_id"])
                if rec is not None and rec["scan"] in per and k in rows:
                    assert per[rec["scan"]]["unq"] == rows[k]["unq"] and per[rec["scan"]]["ms"] == rows[k]["ms"], k
                    assert per[rec["scan"]]["clean"] == rows[k]["clean"], k
            comps[(alias, base)] = per
            res["comparators"][f"{alias}/{base}"] = summarise(per)
    allp = {**comps, **new}
    pairs = []
    for (alias, design) in new:
        refs = {"D2p": ("D2", "D1"), "D1f": ("D1",), "D2f": ("D2", "D2p", "D1f", "D1")}[design]
        pairs += [((alias, r), (alias, design)) for r in refs if (alias, r) in allp]
    for first, second in pairs:
        P1 = {s: v for s, v in allp[first].items() if v["set"] in RN.SETTING_P}
        P2 = {s: v for s, v in allp[second].items() if v["set"] in RN.SETTING_P}
        res["paired"][f"{second[0]}: {second[1]} vs {first[1]}"] = {f: paired(P1, P2, f) for f in PAIRED_FIELDS}
    p = RN.RUNS / "analysis" / "posthoc2.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(res, indent=1))
    rows_out = [dict(v, scan=s, model=a, design=d) for (a, d), per in new.items() for s, v in per.items()]
    (p.parent / "posthoc2_rows.jsonl").write_text("\n".join(json.dumps(r) for r in rows_out) + "\n", encoding="utf-8")
    print(f"[posthoc2] -> {p} ({len(new)} runs)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("ages")
    for k in DEFAULT_SOURCES:
        g.add_argument(f"--{k}", default=str(DEFAULT_SOURCES[k]))
    for name in ("pilot", "qa", "resend"):
        s = sub.add_parser(name)
        s.add_argument("--model", required=True, choices=sorted(SETTINGS))
        s.add_argument("--design", required=True, choices=sorted(CLASSES))
        if name == "qa":
            s.add_argument("--phase", default="pilot", choices=["pilot", "full"])
    sub.add_parser("project")
    sub.add_parser("campaign")
    sub.add_parser("analyse")
    a = ap.parse_args(argv)
    if a.cmd == "ages":
        out = build_ages(RN.load_records(), {k: getattr(a, k) for k in DEFAULT_SOURCES})
        AGE_DIR.mkdir(parents=True, exist_ok=True)
        (AGE_DIR / "ages.json").write_text(json.dumps(out, indent=1))
        print(json.dumps({"availability": out["availability"], "sources": out["sources"]}, indent=1))
        return 0
    if a.cmd == "pilot":
        run(a.model, a.design, "pilot")
        print(json.dumps(qa_of(a.model, a.design, "pilot"), indent=1))
        return 0
    if a.cmd == "resend":                       # the one resend of the keys still without a report
        info = run(a.model, a.design, "full", passes=1)
        print(json.dumps({"without_report": info["without_report"], "qa": qa_of(a.model, a.design, "full")}, indent=1))
        return 0
    if a.cmd == "qa":
        q = qa_of(a.model, a.design, a.phase)
        print(json.dumps(q, indent=1))
        return 0 if q["passed"] else 1
    if a.cmd == "project":
        project()
        return 0
    if a.cmd == "campaign":
        return campaign()
    return analyse()


if __name__ == "__main__":
    raise SystemExit(main())
