"""Two post-hoc experiments prompted by an internal review before submission (PREREG §12, 2026-11-17). Exploratory;
registered in the log, with this file and its analysis committed, before any of their reports existed. The frozen
files (runner.FROZEN) are not touched: the designs below subclass them.

E1, D1c ("clinical caveat permitted"): D1 with ONE added sentence after rule 6, which forbids any diagnosis. Question:
    do models add another cause of the lesions when they are allowed to, and does that change the registered end
    point and the cost in MS?
E2, D2n ("agent without the second tool"): v1's agent A2 on the same view as D2, without get_second_segmentation.
    Question: is D2's increase due to the second segmentation or to the agent format?

Records: FLAMeS ensemble, setting P (DLBS, WMH 2017) and the MS examinations, pilot records excluded, as every arm.
Models: E1 on Gemini 3.1 Flash-Lite (primary, its registered settings), Claude Sonnet 5.5, DeepSeek V4.1 Flash and
gpt-oss-120b (their logged secondary settings: 2,500 output tokens, lowest reasoning); E2 on Gemini 3.1 Flash-Lite and
Claude Sonnet 5.5. One report per record. Same caps as runner.CAP.

    python -m research.paper_2.posthoc run --model gemini --design D1c [--max-tokens 2500]
    python -m research.paper_2.posthoc analyse
"""
import argparse
import json
import time

from research.agents_benchmark import arms as A
from research.paper_2 import designs as D
from research.paper_2 import runner as RN

RULE6_END = "and give no treatment or follow-up advice."
PERMIT = ("You may describe the limitations of the measurements and of the dissemination-in-space result, including "
          "other causes of white matter lesions that a radiologist would consider.")


class D1c(D.D1):
    arm = "D1c"

    def next_request(self):
        req = super().next_request()
        if req is not None:
            assert req["system"].count(RULE6_END) == 1
            req["system"] = req["system"].replace(RULE6_END, RULE6_END + " " + PERMIT)
        return req


class D2n(A.A2):
    arm = "D2n"

    def code_texts(self):
        return []


POSTHOC = {"D1c": (D1c, "base"), "D2n": (D2n, "d2")}
PLAN = {"D1c": ("gemini", "sonnet", "deepseek", "gptoss"), "D2n": ("gemini", "sonnet")}
SETS = ("dlbs", "wmh2017", "ms")


def jobs_for(records, design):
    cls, view_name = POSTHOC[design]
    pilot = RN.pilot_set(records)
    out = []
    for rec in records:
        if rec["arm"] != "flames_ens" or rec["set"] not in SETS or (rec["scan"], rec["arm"]) in pilot:
            continue
        view = rec["views"][view_name]
        out.append(cls({"record_id": view["record_id"], "view": view,
                        "meta": {"scan": rec["scan"], "arm": rec["arm"], "set": rec["set"]}, "a0": None}))
    return out


def run(alias, design, max_tokens=None):
    if alias not in PLAN[design]:
        raise SystemExit(f"{alias} is not planned for {design}")
    model = RN.MODELS[alias]
    rd = RN.RUNS / f"posthoc-{alias}-{design}"
    rd.mkdir(parents=True, exist_ok=True)
    out = rd / "results.jsonl"
    finished = RN.done_keys(out)
    jobs = [j for j in jobs_for(RN.load_records(), design) if j.key not in finished]
    from research.agents_benchmark.providers import provider_for
    provider = provider_for(model, rd)
    info = {"model": model, "design": design, "max_tokens_override": max_tokens, "jobs": len(jobs),
            "already_done": len(finished), "started": time.time(), "frozen": RN.frozen_check()}
    print(f"[posthoc] {alias}/{design}: {len(jobs)} jobs ({len(finished)} already done)", flush=True)
    if getattr(provider, "batch", False):
        info = RN.run_batch(provider, model, jobs, out, info, max_tokens)
    else:
        info = RN.run_online(provider, model, jobs, out, info, None, max_tokens)
    (rd / f"run_info_{int(info['started'])}.json").write_text(json.dumps(info, indent=1))
    print(f"[posthoc] done {info['done']}/{info['jobs']}; stopped: {info['stopped']}", flush=True)
    return info


# ------------------------------------------------------------------------------------------------------- analysis
def analyse():
    """Per model: D1c vs that model's D1 and D2n vs its D1 and D2 (exact McNemar on the registered end point, people in
    setting P), the clinical and provenance caveats (review_analyses lexicons), and the cost in MS (patient bootstrap)."""
    from scipy.stats import binomtest

    from research.paper_2 import analysis as AN
    from research.paper_2 import review_analyses as RA
    from research.paper_2.classifier import classify

    by_rid = {rec["views"][v]["record_id"]: rec for rec in RN.load_records() if rec["arm"] == "flames_ens"
              for v in rec["views"]}
    res = {"note": "post hoc (PREREG §12, 2026-11-17); exploratory", "runs": {}}
    for design, models in PLAN.items():
        for alias in models:
            rd = RN.RUNS / f"posthoc-{alias}-{design}"
            if not (rd / "results.jsonl").exists():
                continue
            last = {}
            for x in (rd / "results.jsonl").read_text(encoding="utf-8").splitlines():
                if x.strip():
                    r = json.loads(x)
                    if (r.get("result") or {}).get("status") == "ok":
                        last[r["key"]] = r
            qa = RN.qa(list(last.values()))
            base_rows = [r for r in RA.rows_of(alias) if r["arm"] == "flames_ens"]
            per = {}
            for r in last.values():
                rec = by_rid[r["record_id"]]
                scan = rec["scan"]
                t = r["result"].get("delivered") or ""
                c = classify(t, code_texts=[], boilerplate=D.BOILERPLATE)
                body = RA.C.L.fold(RA.model_body(t))
                per[scan] = {"set": rec["set"], "ms": c["ms_suggestive"], "unq": c["unqualified"],
                             "clinical": c["ms_suggestive"] and bool(RA.CLINICAL.search(body)),
                             "clinical_any": bool(RA.CLINICAL.search(body)),
                             "provenance": c["ms_suggestive"] and bool(RA.PROVENANCE.search(body)),
                             "dis_conveyed": any(h["rule"] in ("a", "c") for h in c["hits"]),
                             "patient": AN.patient_of(scan), "expert_dis": str(rec["meta"].get("expert_dis")),
                             "tool_calls": r["result"].get("tool_calls")}
            P = [s for s, v in per.items() if v["set"] in RN.SETTING_P]
            out = {"qa": qa, "n_setting_p": len(P),
                   "ms_suggestive": AN.cp(sum(per[s]["ms"] for s in P), len(P)),
                   "unqualified": AN.cp(sum(per[s]["unq"] for s in P), len(P)),
                   "clinical_caveat_among_ms": AN.cp(sum(per[s]["clinical"] for s in P), sum(per[s]["ms"] for s in P)),
                   "clinical_caveat_any_report": AN.cp(sum(per[s]["clinical_any"] for s in P), len(P)),
                   "provenance_caveat_among_ms": AN.cp(sum(per[s]["provenance"] for s in P),
                                                       sum(per[s]["ms"] for s in P))}
            ms_units = [(v["patient"], int(v["dis_conveyed"])) for s, v in per.items()
                        if v["set"] == "ms" and v["expert_dis"] == "1"]
            if ms_units:
                out["ms_coverage"] = RA.clustered_rate(ms_units)
            for ref in ("D1", "D2"):
                ref_unq = {r["scan"]: bool(r["unq"]) for r in base_rows
                           if r["design"] == ref and r["set"] in RN.SETTING_P}
                pairs = [(ref_unq[s], bool(per[s]["unq"])) for s in P if s in ref_unq]
                if not pairs:
                    continue
                b = sum(x and not y for x, y in pairs)
                c = sum(y and not x for x, y in pairs)
                import numpy as np
                dd = np.array([int(y) - int(x) for x, y in pairs])
                rng = np.random.default_rng(AN.BOOT_SEED)
                bs = [dd[rng.integers(0, len(dd), len(dd))].mean() for _ in range(AN.BOOT)]
                out[f"vs_{ref}"] = {"n": len(pairs), f"{ref}_only": b, f"{design}_only": c,
                                    "difference": round(float(dd.mean()), 4),
                                    "ci95": [round(float(np.percentile(bs, 2.5)), 4),
                                             round(float(np.percentile(bs, 97.5)), 4)],
                                    "p_exact_two_sided": float(binomtest(min(b, c), b + c, 0.5).pvalue) if b + c else 1.0}
            res["runs"][f"{alias}/{design}"] = out
            print(f"[posthoc] {alias}/{design}: unq {out['unqualified']['x']}/{len(P)}, clinical caveat "
                  f"{out['clinical_caveat_among_ms']['x']}/{out['clinical_caveat_among_ms']['n']}", flush=True)
    p = RN.RUNS / "analysis" / "posthoc.json"
    p.write_text(json.dumps(res, indent=1))
    print(f"[posthoc] -> {p}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--model", required=True)
    r.add_argument("--design", required=True, choices=sorted(POSTHOC))
    r.add_argument("--max-tokens", type=int)
    sub.add_parser("analyse")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        run(a.model, a.design, a.max_tokens)
        return 0
    return analyse()


if __name__ == "__main__":
    raise SystemExit(main())
