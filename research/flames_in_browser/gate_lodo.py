"""Leave-one-dataset-out (LODO) evaluation of the FLAIR content rule on features recorded by the shipped
TypeScript gate (gateValidation.flames.test.ts output).

    python -I research/flames_in_browser/gate_lodo.py <results.json> [<results.json> ...] [--out lodo.json]

Content rule (refuse = "not a FLAIR"):  deepOverCortex > a  OR  frac45to80 > b  OR  fracAbove1p6 > c,
or a band with < 500 voxels. Fitting on the training datasets: maximise the share of skull-stripped FLAIRs
accepted SUBJECT TO 100 % of the training T1 / T1-post / T2 volumes refused (specificity first), then report
on the held-out dataset. Datasets: mslesseg (train+test), openms (MNI + native), isbi2015.
The full gate adds the fixed skull clues (rim > 1 %, dark > 20 %) and the border/volume refusals recorded by
the harness.
"""
import argparse
import json
import math

import numpy as np


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (round((c - r) / d, 3), round((c + r) / d, 3))


def group(ds):
    return "mslesseg" if ds.startswith("mslesseg") else "openms" if ds.startswith("openms") else ds


def load(paths):
    rows = []
    for p in paths:
        data = json.load(open(p, encoding="utf-8"))
        rows += data["rows"] if isinstance(data, dict) else data
    out = []
    for r in rows:
        f = r.get("features") or {}
        g = lambda k: float("nan") if f.get(k) is None else float(f[k])
        why = r.get("reason") or ""
        out.append(dict(
            id=r["id"], group=group(r["dataset"]), contrast=r["contrast"], variant=r["variant"],
            flair=r["contrast"] == "FLAIR" and r["variant"] == "stripped",
            skullimg=r["variant"].startswith("skull"),
            a=g("locDeepOverNearP75"), b=g("frac45to80"), c=g("fracAbove1p6"),
            rim=g("rimBrightFraction"), dark=g("darkFraction"),
            bands=min(g("nearVoxels"), g("deepVoxels")),
            border=("image border is nonzero" in why or "nonzero region measures" in why),
        ))
    return out


def content_refuses(r, a, b, c):
    if not (r["bands"] >= 500) or any(math.isnan(r[k]) for k in ("a", "b", "c")):
        return True
    return r["a"] > a or r["b"] > b or r["c"] > c


def full_refuses(r, a, b, c):
    return r["border"] or r["rim"] > 0.01 or r["dark"] > 0.2 or content_refuses(r, a, b, c)


A = np.round(np.arange(0.88, 1.10, 0.005), 3)
B = np.round(np.arange(0.15, 0.60, 0.01), 3)
C = np.round(np.arange(0.01, 0.12, 0.005), 3)


def fit(train, objective="content"):
    fn = content_refuses if objective == "content" else full_refuses
    flair = [r for r in train if r["flair"]]
    neg = [r for r in train if not r["flair"] and not r["skullimg"]]
    best = None
    for a in A:
        for b in B:
            for c in C:
                if any(not fn(r, a, b, c) for r in neg):
                    continue
                acc = sum(not fn(r, a, b, c) for r in flair)
                key = (acc, a + b + c)
                if best is None or key > best[0]:
                    best = (key, (float(a), float(b), float(c)))
    return best[1] if best else None


def report(rows, params, label):
    a, b, c = params
    flair = [r for r in rows if r["flair"]]
    neg = [r for r in rows if not r["flair"] and not r["skullimg"]]
    skull = [r for r in rows if r["skullimg"]]
    res = {"thresholds": {"deepOverCortex_max": a, "frac45to80_max": b, "fracAbove1p6_max": c}}
    for name, fn in (("content_only", content_refuses), ("full_gate", full_refuses)):
        tp = sum(not fn(r, a, b, c) for r in flair)
        tn = sum(fn(r, a, b, c) for r in neg)
        res[name] = {
            "flair_accepted": f"{tp}/{len(flair)}", "sensitivity": round(tp / len(flair), 3) if flair else None,
            "sensitivity_ci95": wilson(tp, len(flair)),
            "non_flair_refused": f"{tn}/{len(neg)}", "specificity": round(tn / len(neg), 3) if neg else None,
            "specificity_ci95": wilson(tn, len(neg)),
            "false_accepts": [r["id"] for r in neg if not fn(r, a, b, c)],
        }
        if skull:
            res[name]["with_skull_refused"] = f"{sum(fn(r, a, b, c) for r in skull)}/{len(skull)}"
    print(label, json.dumps(res))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results", nargs="+")
    ap.add_argument("--out")
    ap.add_argument("--objective", choices=["content", "full"], default="content",
                    help="fit with 100 %% training specificity of the content rule alone, or of the full gate")
    args = ap.parse_args()
    rows = load(args.results)
    groups = sorted({r["group"] for r in rows})
    out = {"groups": groups, "objective": args.objective, "lodo": {}, "all": {}}
    for held in groups:
        params = fit([r for r in rows if r["group"] != held], args.objective)
        if params is None:
            out["lodo"][held] = "no thresholds give 100 % training specificity"
            continue
        out["lodo"][held] = report([r for r in rows if r["group"] == held], params, f"HELD-OUT {held}:")
    params = fit(rows, args.objective)
    out["all"]["fit_on_all"] = report(rows, params, "FIT ON ALL (apparent):")
    for g in groups:
        out["all"][g] = report([r for r in rows if r["group"] == g], params, f"  apparent {g}:")
    if args.out:
        json.dump(out, open(args.out, "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    main()
