"""Offline re-scoring of the benchmark's existing arm-A3 drafts with the product's stricter claim check.

Second independent review of PR #78 (items A and B; RC-103; DRAFT, PENDING owner approval). No model is called: every
answer the models gave in the pre-registered benchmark (branch `research/agents-benchmark`, results at f3c1976) is
read from the run folders and checked again —

  v2       the benchmark's own A3 check (format rules + frozen verifier v2), recomputed from its code at f3c1976 and
           compared with the failures recorded in the run (they must agree);
  product  v2 + the stricter rules of `backend/app/services/report_claim_strict.py` on the two comments (diagnostic
           and activity statements in either polarity, treatment phrases no negation governs, heading lines).

For every delivered draft (outcome passed_k), the answer that passed v2 is re-checked: if the product check flags it,
the draft "would now be flagged". With k = 2 (the last allowed answer) the draft would now be blocked for certain;
with k < 2 the loop would ask again, and the new answer cannot be known offline (lower and upper bounds are given).

Usage (reads in place, writes one JSON record):
  python -I scripts/safety/rescore_benchmark_a3_strict.py --bench-root <dir holding research/agents_benchmark at
      f3c1976> --work <AB_WORK_DIR: records/ and runs/> --out <record.json>
"""
import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve()
BACKEND = HERE.parents[2] / "backend"
CONDITION = {"i": "automatic marking, single study", "ii": "radiologist-confirmed mask (DIS evaluated)",
             "iii": "visit pair (longitudinal)", "v": "healthy control"}


def read_results(run_dir: Path):
    """The benchmark's own rule (runner.read_results): one row per job, the last successful result."""
    best = {}
    p = run_dir / "results.jsonl"
    if not p.exists():
        return []
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            prev = best.get(d["key"])
            if prev is None or d["result"].get("status") == "ok" or prev["result"].get("status") != "ok":
                best[d["key"]] = d
    return list(best.values())


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench-root", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    work = Path(a.work)
    os.environ["AB_WORK_DIR"] = str(work)
    sys.path[:0] = [str(Path(a.bench_root)), str(BACKEND)]
    from research.agents_benchmark import arms as A          # noqa: E402  (benchmark code at f3c1976)
    from app.services import report_claim_strict as S         # noqa: E402  (the product's stricter rules)
    from app.services import verified_report as VR            # noqa: E402  (its format rules, fourth review)

    man = json.loads((work / "records" / "manifest.json").read_text(encoding="utf-8"))
    pilot = set(man["subsets"]["pilot"])
    meta = {r["record_id"]: r for r in man["records"]}
    max_k = A.config.A3_MAX_REGENERATIONS

    groups = defaultdict(Counter)
    kinds_new = defaultdict(Counter)
    unflagged_examples = []               # sixth review, W3: delivered drafts with a count word the rule lets pass
    number_words = defaultdict(Counter)   # fifth review, V1: which words flag a delivered draft (model-language)
    examples = defaultdict(list)
    totals = Counter()
    mismatch = 0
    superset_violations = 0
    for alias in ("gemini", "gemma", "haiku", "sonnet"):
        for subset in ("main", "multilingual", "injection"):
            for r in read_results(work / "runs" / f"{alias}-{subset}"):
                if r.get("arm") != "A3":
                    continue
                if r["record_id"] in pilot or r["result"].get("status") != "ok":
                    totals["excluded_pilot_or_failed_job"] += 1
                    continue
                rec = json.loads((work / "records" / f"{r['record_id']}.json").read_text(encoding="utf-8"))
                view = A.view_for(rec, r["lang"], r["payload"])
                job = A.A3.__new__(A.A3)
                job.view, job.lang = view, r["lang"]
                vals = A.placeholder_values(view, r["lang"])
                attempt_new = []
                slips_seen = []     # sixth review, W3: per attempt, the count words the rule lets pass (for review)
                for att in r["result"]["attempts"]:
                    _assembled, v2 = A.A3.check(job, att["text"])
                    recorded = list(att.get("failures") or [])
                    if bool(v2) != bool(recorded):
                        mismatch += 1                       # a different verdict (pass / fail)
                    elif set(v2) != set(recorded):
                        totals["recomputed_v2_other_failure_set"] += 1
                    elif list(v2) != recorded:
                        totals["recomputed_v2_same_failures_other_order"] += 1
                    m = A._SLOT.search(att["text"] or "")
                    strict = []
                    slips_seen.append([])
                    if m:
                        # (fourth review of PR #78: the comments read with the shared format-character rule, Q6; the
                        # empty-comment and raw-template-token rules, Q1 and Q2)
                        fc = VR.without_format_characters(m.group(1)).strip()
                        ic = VR.without_format_characters(m.group(2)).strip()
                        if not (VR._HAS_A_LETTER.search(fc) and VR._HAS_A_LETTER.search(ic)):
                            strict.append({"kind": "empty_comment", "unit": (fc or ic or "")[:80]})
                        # (fifth review of PR #78, V1: a number written in words, before the placeholders are filled;
                        # sixth review, W3: only when it counts a clinical noun, in the report's language)
                        words = VR.number_words(fc + "\n" + ic, r["lang"])
                        fold = VR.L_fold(fc + "\n" + ic)
                        word_re = VR._COUNT_WORD_OF[r["lang"]]
                        unflagged = [m for m in re.finditer(r"\w+", fold) if word_re.fullmatch(m.group(0))]
                        if len(unflagged) > len(words):     # a count word that counts no listed clinical noun
                            slips_seen[-1] = [fold[max(0, u.start() - 60):u.end() + 60].replace("\n", " ")
                                              for u in unflagged]
                        if words:
                            strict.append({"kind": "number_words", "words": sorted(set(words)),
                                           "unit": f"{sorted(set(words))[:4]} in: {(fc + ' | ' + ic)[:150]}"})
                        for k, v in vals.items():
                            fc, ic = fc.replace("{" + k + "}", v), ic.replace("{" + k + "}", v)
                        if VR._TEMPLATE_TOKEN.search(fc + "\n" + ic):
                            strict.append({"kind": "template_token", "unit": (fc + " | " + ic)[:180]})
                        if S.heading_lines(fc) or S.heading_lines(ic):
                            strict.append({"kind": "heading", "unit": (S.heading_lines(fc) + S.heading_lines(ic))[0]})
                        strict += S.comment_elements(fc, view) + S.comment_elements(ic, view)   # A, B and K (the record's DIS state)
                    product_fails = bool(v2) or bool(strict)
                    if bool(v2) and not product_fails:
                        superset_violations += 1
                    attempt_new.append((bool(v2), strict))
                outcome = r["result"]["a3_outcome"]
                cond = meta[r["record_id"]]["condition"]
                key = (alias, r["lang"], subset)
                g = groups[key]
                g["drafts"] += 1
                g["attempts"] += len(attempt_new)
                g["attempts_newly_flagged"] += sum(1 for v2f, st in attempt_new if not v2f and st)
                g[f"cond_{cond}_drafts"] += 1
                if outcome == "blocked":
                    g["blocked_before"] += 1
                    continue
                k = int(outcome.split("_")[1])
                g["delivered_before"] += 1
                v2f, st = attempt_new[k]
                assert not v2f, (r["key"], "a delivered answer must have passed v2")
                if slips_seen[k] and not st:
                    g["delivered_with_unflagged_count_words"] += 1
                    unflagged_examples.append({"model": alias, "lang": r["lang"], "record": r["record_id"],
                                               "snippets": slips_seen[k][:3]})
                if st:
                    g["now_flagged"] += 1
                    g[f"cond_{cond}_now_flagged"] += 1
                    g["now_blocked_certain" if k == max_k else "now_need_regeneration"] += 1
                    for e in st:
                        kinds_new[alias][e["kind"]] += 1
                        number_words[f"{alias}-{r['lang']}"].update(e.get("words") or [])
                        ex = examples[e["kind"]]
                        if len(ex) < 3:
                            ex.append({"model": alias, "lang": r["lang"], "condition": CONDITION.get(cond, cond),
                                       "sentence": e["unit"][:180]})
    rows = []
    for (alias, lang, subset), g in sorted(groups.items()):
        rows.append({"model": alias, "language": lang, "subset": subset, **dict(sorted(g.items()))})
    per_model_lang = defaultdict(Counter)
    for (alias, lang, _subset), g in groups.items():
        per_model_lang[(alias, lang)].update(g)
    summary = []
    for (alias, lang), g in sorted(per_model_lang.items()):
        d, nf = g["delivered_before"], g["now_flagged"]
        summary.append({
            "model": alias, "language": lang, "drafts": g["drafts"], "blocked_before": g["blocked_before"],
            "delivered_before": d, "now_flagged": nf, "now_flagged_pct_of_delivered": round(100 * nf / d, 1) if d else None,
            "now_blocked_certain": g["now_blocked_certain"], "now_need_regeneration": g["now_need_regeneration"],
            "blocked_after_lower_bound": g["blocked_before"] + g["now_blocked_certain"],
            "blocked_after_upper_bound": g["blocked_before"] + nf,
            "healthy_control_drafts": g["cond_v_drafts"], "healthy_control_now_flagged": g["cond_v_now_flagged"],
            "delivered_with_unflagged_count_words": g["delivered_with_unflagged_count_words"]})
    record = {
        "executed": "2026-11-11",
        "purpose": "second independent review of PR #78 (items A, B): offline re-scoring of the benchmark's existing "
                   "A3 drafts with the product's stricter claim check (no model called); re-run for the fourth review "
                   "(Q1, Q2, Q6), the fifth review (V1: numbers written in words) and the sixth review (W3: a "
                   "number word fails only when it counts a clinical noun, en / es / de)",
        "benchmark_code": "research/agents_benchmark at f3c1976 (A3.check with the frozen verifier v2)",
        "product_rules": "backend/app/services/report_claim_strict.py",
        "product_rules_sha256": hashlib.sha256((BACKEND / "app" / "services" / "report_claim_strict.py")
                                               .read_bytes()).hexdigest(),
        "runs": "data/cohorts/agents-benchmark/runs (local copy of gs://mstool-research-data/agents-benchmark/runs), "
                "read in place; selection = the benchmark's own rule (last successful result per job; pilot records "
                "and failed jobs excluded)",
        "models_with_drafts": sorted({r["model"] for r in rows}),
        "models_without_drafts": "haiku and sonnet: the Claude arms of the benchmark were never run (no research key)",
        "recorded_vs_recomputed_v2_verdict_mismatches": mismatch,
        "recorded_vs_recomputed_v2_note": "verdicts (pass / fail) agree for every answer; where the lists differ they "
                                          "hold the same failures in another order (the benchmark's placeholder check iterates a set, so the order of its messages varies between runs; see 'recomputation_counts')",
        "superset_violations": superset_violations,
        "recomputation_counts": dict(totals),
        "reading": "now_flagged = a delivered draft whose passing answer the product check flags; with the last "
                   "allowed answer (passed_2) it would now be blocked for certain, otherwise the loop would ask again "
                   "and the new answer is unknown offline: blocked after the change lies between the lower and the "
                   "upper bound.",
        "summary_per_model_and_language": summary,
        "per_model_language_subset": rows,
        "new_flags_by_rule_and_model": {m: dict(c) for m, c in sorted(kinds_new.items())},
        "examples_of_new_flags": dict(examples),
        "delivered_drafts_with_count_words_not_flagged": unflagged_examples,
        "number_words_in_flagged_delivered_drafts": {k: dict(c.most_common(12)) for k, c in sorted(number_words.items())},
        "conditions": CONDITION,
    }
    Path(a.out).write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for s in summary:
        print(s)
    print("mismatches", mismatch, "superset_violations", superset_violations, dict(kinds_new))
    return 0


if __name__ == "__main__":
    sys.exit(main())
