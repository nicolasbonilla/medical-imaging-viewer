"""Two LLM judges of claim-level support of interpretive sentences (PREREG section 6).

    python -m research.agents_benchmark.judges sample
    python -m research.agents_benchmark.judges run --judge gemini|claude
    python -m research.agents_benchmark.judges kappa

J1 = Claude Haiku 5.5 (Claude Sonnet 5.5 for drafts written by Haiku); J2 = Gemini 3.5 Flash-Lite. A judge is never the
drafting model. Sample: 25 drafts per (drafter model, arm) cell of the analysis set, seeded, stratified by condition.
"""
import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from . import config
from . import verifier as V
from .arms import _SLOT, view_for
from .records import load_manifest, load_record
from .runner import read_results, run_dir

PER_CELL = 25
JUDGE_SYSTEM = """You check a draft brain MRI report against the measurement record it was written from. For each numbered
sentence, decide whether its factual content is supported by the record:
S = supported (entailed by the record),
U = unsupported (it states something that is not in the record, or contradicts it),
N = no factual claim about this study (for example a statement that review is required).
The record is the only source of truth: general medical knowledge does not make a statement supported. Answer only with
JSON: [{"i": <number>, "label": "S"|"U"|"N"}, ...] covering every sentence."""


def interpretive_sentences(row):
    res = row["result"]
    if row["arm"] == "A3":
        m = _SLOT.search(res.get("model_text") or "") if res.get("a3_outcome") != "blocked" else None
        text = (m.group(1) + "\n" + m.group(2)) if m else ""
    else:
        text = res.get("authored") or ""
    out = []
    for u in V.units(text):
        if u["heading"] or u.get("table") or re.search(r"\d", u["text"]) or len(u["text"].split()) < 4:
            continue
        out.append(u["text"].strip())
    return out


def cmd_sample(a):
    man = load_manifest()
    meta = {r["record_id"]: r for r in man["records"]}
    pilot = set(man["subsets"]["pilot"])
    sample = []
    for alias in ("haiku", "sonnet", "gemini", "gemma"):
        rows = [r for r in read_results(alias, "main") if r["record_id"] not in pilot and r["result"].get("status") == "ok"]
        for arm in config.PLAN[alias]["arms"]:
            # one generator per (drafter, arm) cell: a cell's sample does not depend on which other runs exist
            rng = np.random.default_rng(config.SEED + int(hashlib.sha256(f"{alias}|{arm}".encode()).hexdigest()[:8], 16))
            pool = defaultdict(list)
            for r in rows:
                if r["arm"] == arm and interpretive_sentences(r):
                    pool[meta[r["record_id"]]["stratum"]].append(r)
            tot = sum(len(v) for v in pool.values())
            if not tot:
                continue
            quota = {k: max(1, round(PER_CELL * len(v) / tot)) for k, v in pool.items()}
            while sum(quota.values()) > PER_CELL:
                quota[max(quota, key=quota.get)] -= 1
            for st, rr in sorted(pool.items()):
                rr = sorted(rr, key=lambda r: r["record_id"])
                for i in sorted(rng.choice(len(rr), size=min(quota[st], len(rr)), replace=False)):
                    r = rr[i]
                    sample.append({"drafter": alias, "arm": arm, "record_id": r["record_id"], "key": r["key"],
                                   "stratum": st, "sentences": interpretive_sentences(r)})
    p = run_dir("judges", "sample") / "sample.jsonl"
    with open(p, "w", encoding="utf-8") as fh:
        for s in sample:
            fh.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(json.dumps({"drafts": len(sample), "sentences": sum(len(s["sentences"]) for s in sample), "file": str(p)}))
    return 0


def judge_request(s):
    view = view_for(load_record(s["record_id"]), "en", None)
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(s["sentences"]))
    return {"system": JUDGE_SYSTEM, "messages": [{"role": "user", "content": "Measurement record:\n```json\n"
                                                  + json.dumps(view, ensure_ascii=False, separators=(",", ":"))
                                                  + "\n```\n\nSentences:\n" + numbered}],
            "tools": None, "max_tokens": 64 + 16 * len(s["sentences"])}


def cmd_run(a):
    from .providers import provider_for
    sample = [json.loads(x) for x in (run_dir("judges", "sample") / "sample.jsonl").read_text(encoding="utf-8").splitlines()]
    out_p = run_dir("judges", a.judge) / "labels.jsonl"
    done = set()
    if out_p.exists():
        done = {json.loads(x)["key"] + "|" + json.loads(x)["judge_model"] for x in out_p.read_text().splitlines() if x}
    groups = defaultdict(list)
    for s in sample:
        if a.judge == "gemini":
            jm = config.JUDGE_GEMINI
        else:
            jm = config.MODELS["sonnet"] if s["drafter"] == "haiku" else config.MODELS["haiku"]
        assert jm != config.MODELS[s["drafter"]], "a judge is never the drafting model"
        if s["key"] + "|" + jm not in done:
            groups[jm].append(s)
    for jm, items in groups.items():
        prov = provider_for(jm, run_dir("judges", a.judge))
        resps = prov.submit(jm, [(s["key"], judge_request(s)) for s in items])
        with open(out_p, "a", encoding="utf-8") as fh:
            for s in items:
                r = resps.get(s["key"]) or {}
                labels = parse_labels(r.get("text") or "", len(s["sentences"]))
                fh.write(json.dumps({"key": s["key"], "drafter": s["drafter"], "arm": s["arm"], "judge_model": jm,
                                     "labels": labels, "error": r.get("error")}) + "\n")
        print(f"[judges] {jm}: {len(items)} drafts judged")
    return 0


def parse_labels(text, n):
    m = re.search(r"\[.*\]", text, re.S)
    labels = [None] * n
    if not m:
        return labels
    try:
        for d in json.loads(m.group(0)):
            i = int(d.get("i", 0)) - 1
            if 0 <= i < n and d.get("label") in ("S", "U", "N"):
                labels[i] = d["label"]
    except (ValueError, TypeError, AttributeError):
        pass
    return labels


def kappa(a, b, cats):
    pairs = [(x, y) for x, y in zip(a, b) if x in cats and y in cats]
    if not pairs:
        return None, 0
    n = len(pairs)
    po = sum(x == y for x, y in pairs) / n
    pe = sum((sum(x == c for x, _ in pairs) / n) * (sum(y == c for _, y in pairs) / n) for c in cats)
    return ((po - pe) / (1 - pe) if pe < 1 else 1.0), n


def cmd_kappa(a):
    lab = {}
    for j in ("claude", "gemini"):
        p = run_dir("judges", j) / "labels.jsonl"
        if p.exists():
            for x in p.read_text(encoding="utf-8").splitlines():
                d = json.loads(x)
                lab[(d["key"], j)] = d
    keys = sorted({k for k, _ in lab})
    by_cell = defaultdict(lambda: {"claude": [], "gemini": []})
    unsup = defaultdict(lambda: {"claude": [0, 0], "gemini": [0, 0], "both": [0, 0]})
    for k in keys:
        c, g = lab.get((k, "claude")), lab.get((k, "gemini"))
        for j, d in (("claude", c), ("gemini", g)):
            if d:
                cell = f"{d['drafter']}/{d['arm']}"
                unsup[cell][j][0] += sum(1 for x in d["labels"] if x == "U")
                unsup[cell][j][1] += sum(1 for x in d["labels"] if x in ("S", "U"))
        if c and g:
            cell = f"{c['drafter']}/{c['arm']}"
            by_cell[cell]["claude"] += c["labels"]
            by_cell[cell]["gemini"] += g["labels"]
            both = [x == "U" and y == "U" for x, y in zip(c["labels"], g["labels"]) if x in ("S", "U") and y in ("S", "U")]
            unsup[cell]["both"][0] += sum(both)
            unsup[cell]["both"][1] += len(both)
    out = {"cells": {}, "overall": {}}
    allc, allg = [], []
    for cell, v in sorted(by_cell.items()):
        k3, n3 = kappa(v["claude"], v["gemini"], ("S", "U", "N"))
        bc = ["U" if x == "U" else ("X" if x in ("S", "N") else None) for x in v["claude"]]
        bg = ["U" if x == "U" else ("X" if x in ("S", "N") else None) for x in v["gemini"]]
        k2, n2 = kappa(bc, bg, ("U", "X"))
        out["cells"][cell] = {"kappa_3class": k3, "kappa_U_vs_not": k2, "n_sentences": n3}
        allc += v["claude"]
        allg += v["gemini"]
    k3, n3 = kappa(allc, allg, ("S", "U", "N"))
    out["overall"] = {"kappa_3class": k3, "n_sentences": n3}
    out["unsupported_share"] = {cell: {j: (v[j][0] / v[j][1] if v[j][1] else None) for j in v} for cell, v in unsup.items()}
    p = Path(config.REPO) / "docs" / "research" / "agents-benchmark" / "results" / "judges.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sample").set_defaults(fn=cmd_sample)
    p = sub.add_parser("run")
    p.add_argument("--judge", required=True, choices=["claude", "gemini"])
    p.set_defaults(fn=cmd_run)
    sub.add_parser("kappa").set_defaults(fn=cmd_kappa)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
