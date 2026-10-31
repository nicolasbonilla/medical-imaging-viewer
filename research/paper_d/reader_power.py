"""Paper D reader study — power of R1 (READER_STUDY_PROTOCOL.md §3), Monte Carlo.

Research code, not the device. Written 2026-10-31 before any reader was invited. Uses only the case
manifest (strata and expert lesion counts of the 84 selected scans).

R1a: one-sided exact Fisher test, reader non-unanimity in 48 non-unanimous vs 36 control scans.
R1b: logistic regression of reader non-unanimity on stratum + standardised log expert lesion count,
     one-sided likelihood-ratio test of the stratum term (reject if LR > 2.706 and coefficient > 0).

    python research/paper_d/reader_power.py \
        --manifest <data>/experiments/paper-d/reader-study/case_manifest.json \
        --out docs/research/paper-d/records/reader_power_record.json
The manifest is git-ignored (it holds the strata; the repository is public and readers must not see
it); the record written here holds only aggregate numbers.
"""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit
from scipy.stats import fisher_exact

SEED = 20261031


def nll(beta, X, y):
    p = np.clip(expit(X @ beta), 1e-9, 1 - 1e-9)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p)).sum()


def fit(X, y):
    r = minimize(nll, np.zeros(X.shape[1]), args=(X, y), method="BFGS")
    return r.x, r.fun


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sims-fisher", type=int, default=4000)
    ap.add_argument("--sims-adjusted", type=int, default=1500)
    args = ap.parse_args()
    m = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    nu = np.array([c["stratum"] == "non-unanimous" for c in m["cases"]], float)
    n1, n0 = int(nu.sum()), int((1 - nu).sum())
    logl = np.log(np.array([c["expert_lesions"] for c in m["cases"]], float))
    z = (logl - logl.mean()) / logl.std()
    X = np.column_stack([np.ones_like(z), nu, z])
    rng = np.random.default_rng(SEED)
    out = {"date": str(datetime.date.today()), "seed": SEED, "n_nonunanimous": n1, "n_controls": n0,
           "mean_z_nonunanimous": float(z[nu == 1].mean()), "mean_z_controls": float(z[nu == 0].mean()),
           "R1a_fisher": [], "R1b_adjusted": []}
    for p1, p0 in [(0.20, 0.05), (0.25, 0.05), (0.30, 0.08), (0.35, 0.10)]:
        rej = 0
        for _ in range(args.sims_fisher):
            x1, x0 = rng.binomial(n1, p1), rng.binomial(n0, p0)
            rej += fisher_exact([[x1, n1 - x1], [x0, n0 - x0]], alternative="greater")[1] < 0.05
        out["R1a_fisher"].append({"p_nonunanimous": p1, "p_controls": p0, "power": rej / args.sims_fisher})
    a = np.log(0.06 / 0.94)
    for or_nu in (3, 4, 6):
        for or_burden in (1.0, 0.6):
            b, c = np.log(or_nu), np.log(or_burden)
            rej = rejf = 0
            rates = []
            for _ in range(args.sims_adjusted):
                y = (rng.random(len(z)) < expit(a + b * nu + c * z)).astype(float)
                rates.append((y[nu == 1].mean(), y[nu == 0].mean()))
                x1, x0 = y[nu == 1].sum(), y[nu == 0].sum()
                rejf += fisher_exact([[x1, n1 - x1], [x0, n0 - x0]], alternative="greater")[1] < 0.05
                if y.sum() < 2:
                    continue
                bf, ll1 = fit(X, y)
                _, ll0 = fit(X[:, [0, 2]], y)
                rej += (2 * (ll0 - ll1) > 2.706) and bf[1] > 0
            r = np.mean(rates, axis=0)
            out["R1b_adjusted"].append({"odds_ratio_stratum": or_nu, "odds_ratio_per_sd_log_lesions": or_burden,
                                        "mean_rate_nonunanimous": float(r[0]), "mean_rate_controls": float(r[1]),
                                        "power_adjusted": rej / args.sims_adjusted, "power_fisher": rejf / args.sims_adjusted})
    rec = Path(args.out)
    rec.parent.mkdir(parents=True, exist_ok=True)
    rec.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
