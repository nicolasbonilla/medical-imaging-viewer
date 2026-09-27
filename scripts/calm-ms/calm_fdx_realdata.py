#!/usr/bin/env python3
"""CALM-FDX on real MS data: per-scan FDX control + CERTIFIED dissemination in space (DIS).

PRE-REGISTERED (fixed before this script was first run; do not tune on its output):
  gamma = 0.2, delta = 0.1; labels = one-to-one Hungarian, lenient (IoU > 0);
  PRIMARY template = "hc" (chosen by the design stage on synthetic data only);
  SECONDARY template = "hybrid" (proposed after an agent had seen real LOSO outcomes ->
  reported as exploratory, never as the headline);
  DIS areas (brain-only McDonald): PV=1, JC=2, IT=3; DIS = >=1 lesion in >=2 areas.
  Layer 2 (scan-level): MSLesSeg only; 20 random subject splits (seed 20260927) into
  pool 35 / labelled K=29 / test 11 subjects, one random scan per subject in K and test.
  openms (30 subjects) cannot host pool + K>=9 + test at a useful n -> Layer 1 only, and its
  numbers are EMPIRICAL (the Polya gate fails there).

Reports per site: scans with FDP > gamma (Clopper-Pearson 95% CI), power (selection recall),
abstention rate; baselines per-scan BH at gamma (marginal FDR) and at gamma*delta (Markov-
valid FDX); DIS: certified-DIS rate on GT-DIS scans, FALSE certified DIS (a certified area with
no true candidate), and the same for raw-segmentation DIS and BH-selection DIS — including on
HEALTHY CONTROLS, where every DIS call is false.

    python scripts/calm-ms/calm_fdx_realdata.py
"""
import json
import os
import sys
from multiprocessing import Pool

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(_HERE, "..", "..")
for p in (os.path.join(_ROOT, "research", "conformal_fdx"), os.path.join(_ROOT, "backend")):
    if p not in sys.path:
        sys.path.insert(0, p)
import calm_fdx as cf                                                    # noqa: E402
from app.services.conformal_lesion_fdr import benjamini_hochberg        # noqa: E402

GAMMA, DELTA = 0.2, 0.1
AREAS = (1, 2, 3)
SEED = 20260927
CACHE = os.path.join(_HERE, ".region_cache.npz")
OUT = os.path.join(_ROOT, "backend", "app", "services", "assets", "calm_fdx_realdata_record.json")


def _clopper(x, n, a=0.05):
    from scipy.stats import beta
    lo = 0.0 if x == 0 else beta.ppf(a / 2, x, n - x + 1)
    hi = 1.0 if x == n else beta.ppf(1 - a / 2, x + 1, n - x)
    return [round(float(lo), 3), round(float(hi), 3)]


def _isf(c):
    return c["mg0"] == 0


def _gt_dis(c):
    return sum(int(np.any(c["gt_region"] == a)) for a in AREAS) >= 2


def _dis_from_selection(c, sel):
    """Naive DIS from a selected candidate set (every selected candidate taken as a lesion)."""
    return sum(int(np.any(c["region"][sel] == a)) for a in AREAS) >= 2


def _true_areas(c):
    """Areas that truly contain at least one TRUE candidate (one-to-one matched to GT)."""
    isf = _isf(c)
    return {a for a in AREAS if np.any((c["region"] == a) & ~isf)}


def _false_dis(c, claimed_areas):
    """A DIS CONCLUSION is false iff it was claimed (>=2 areas) but fewer than 2 areas truly
    contain a true candidate."""
    return len(claimed_areas) >= 2 and len(_true_areas(c)) < 2


def _area_wrong(c, claimed_areas):
    """Stronger event: some area counted towards the claim has no true candidate."""
    return any(a not in _true_areas(c) for a in claimed_areas)


def _bh(k, n, level):
    if k.size == 0:
        return np.zeros(0, bool)
    return benjamini_hochberg(k / (n + 1.0), alpha=level)


def eval_scan(args):
    """Layer-1 evaluation of one test scan against a given calibration false-score array."""
    c, calib, template, inflate = args
    fam = cf.EnvelopeFamily(DELTA, template)
    isf = _isf(c)
    m = c["scores"].size
    out = {"site": c["site"], "case": c["case"], "m": int(m), "n_true": int((~isf).sum()),
           "gt_dis": bool(_gt_dis(c))}
    if m == 0:
        out.update(sel=0, fp=0, fdp=0.0, tp=0, dis_cert=False, dis_cert_false=False, cert_area_wrong=False,
                   dis_raw=False, dis_raw_false=False, dis_bh=False, dis_bh_false=False,
                   bh_sel=0, bh_fp=0, bhm_sel=0, bhm_fp=0, lb={a: 0 for a in AREAS}, m0_hat=0)
        return out
    k, n = cf.conformal_ranks(c["scores"], calib)
    sel, info = cf.select_fdx(k, n, GAMMA, fam, inflate=inflate)
    Bstar = info["Bstar"]
    dis, lb = cf.certify_dis(c["region"], k, Bstar, AREAS)
    cert_areas = [a for a in AREAS if lb[a] >= 1]
    bh = _bh(k, n, GAMMA)
    bhm = _bh(k, n, GAMMA * DELTA)
    raw_areas = [a for a in AREAS if np.any(c["region"] == a)]
    bh_areas = [a for a in AREAS if np.any(c["region"][bh] == a)]
    ns = int(sel.sum()); nf = int((sel & isf).sum())
    out.update(sel=ns, fp=nf, fdp=(nf / ns) if ns else 0.0, tp=int((sel & ~isf).sum()),
               m0_hat=int(info["m0_hat"]), lb={int(a): int(v) for a, v in lb.items()},
               dis_cert=bool(dis), dis_cert_false=bool(_false_dis(c, cert_areas)),
               cert_area_wrong=bool(_area_wrong(c, cert_areas)),
               dis_raw=bool(len(raw_areas) >= 2), dis_raw_false=bool(_false_dis(c, raw_areas)),
               dis_bh=bool(len(bh_areas) >= 2), dis_bh_false=bool(_false_dis(c, bh_areas)),
               bh_sel=int(bh.sum()), bh_fp=int((bh & isf).sum()),
               bhm_sel=int(bhm.sum()), bhm_fp=int((bhm & isf).sum()))
    return out


def summarize(rows, label):
    N = len(rows)
    ex = sum(r["sel"] > 0 and r["fdp"] > GAMMA for r in rows)
    bh_ex = sum(r["bh_sel"] > 0 and r["bh_fp"] / r["bh_sel"] > GAMMA for r in rows)
    bhm_ex = sum(r["bhm_sel"] > 0 and r["bhm_fp"] / r["bhm_sel"] > GAMMA for r in rows)
    ntrue = sum(r["n_true"] for r in rows)
    pw = sum(r["tp"] for r in rows) / ntrue if ntrue else None
    bh_pw = (sum(r["bh_sel"] - r["bh_fp"] for r in rows) / ntrue) if ntrue else None
    bhm_pw = (sum(r["bhm_sel"] - r["bhm_fp"] for r in rows) / ntrue) if ntrue else None
    gd = [r for r in rows if r["gt_dis"]]
    s = {"scans": N,
         "calm_fdx": {"scans_fdp_gt_gamma": ex, "rate": round(ex / N, 3) if N else None,
                      "ci95": _clopper(ex, N) if N else None,
                      "power": round(pw, 4) if pw is not None else None,
                      "abstain_rate": round(sum(r["sel"] == 0 for r in rows) / N, 3) if N else None},
         "bh_gamma": {"scans_fdp_gt_gamma": bh_ex, "rate": round(bh_ex / N, 3) if N else None,
                      "power": round(bh_pw, 4) if bh_pw is not None else None},
         "bh_gamma_delta": {"scans_fdp_gt_gamma": bhm_ex, "rate": round(bhm_ex / N, 3) if N else None,
                            "power": round(bhm_pw, 4) if bhm_pw is not None else None},
         "dis": {"gt_dis_scans": len(gd),
                 "certified_on_gt_dis": sum(r["dis_cert"] for r in gd),
                 "certified_false": sum(r["dis_cert_false"] for r in rows),
                 "certified_false_rate": round(sum(r["dis_cert_false"] for r in rows) / N, 3) if N else None,
                 "certified_false_ci95": _clopper(sum(r["dis_cert_false"] for r in rows), N) if N else None,
                 "certified_area_wrong": sum(r["cert_area_wrong"] for r in rows),
                 "raw_dis_false": sum(r["dis_raw_false"] for r in rows),
                 "raw_dis_false_rate": round(sum(r["dis_raw_false"] for r in rows) / N, 3) if N else None,
                 "bh_dis_false": sum(r["dis_bh_false"] for r in rows),
                 "bh_dis_false_rate": round(sum(r["dis_bh_false"] for r in rows) / N, 3) if N else None}}
    d = s["dis"]; f = s["calm_fdx"]
    print(f"  {label:34s} N={N:3d} | FDX {f['scans_fdp_gt_gamma']:2d}/{N} {f['ci95']} power {f['power']}"
          f" abstain {f['abstain_rate']} | BH@g {s['bh_gamma']['scans_fdp_gt_gamma']}/{N} pw {s['bh_gamma']['power']}"
          f" | BH@gd {s['bh_gamma_delta']['scans_fdp_gt_gamma']}/{N} pw {s['bh_gamma_delta']['power']}")
    print(f"  {'':34s} DIS: certified {d['certified_on_gt_dis']}/{d['gt_dis_scans']} GT-DIS scans | "
          f"FALSE certified {d['certified_false']}/{N} {d['certified_false_ci95']} (area-wrong {d['certified_area_wrong']}) | "
          f"raw-seg false DIS {d['raw_dis_false']}/{N} | BH false DIS {d['bh_dis_false']}/{N}")
    return s


def loso_jobs(cases, site, template, calib_from=None):
    """Layer 1, leave-one-SUBJECT-out: each test scan vs false scores of the OTHER subjects
    (of `calib_from` sites; default its own site)."""
    src = [c for c in cases if c["site"] in (calib_from or [site])]
    jobs = []
    for c in [x for x in cases if x["site"] == site]:
        calib = np.concatenate([x["scores"][_isf(x)] for x in src if x["subject"] != c["subject"]])
        jobs.append((c, calib, template, 0))
    return jobs


def layer2_mslesseg(cases, template, pool):
    rng = np.random.RandomState(SEED)
    ms = [c for c in cases if c["site"] == "mslesseg"]
    subj = sorted({c["subject"] for c in ms})
    per_split, allrows = [], []
    for split in range(20):
        perm = rng.permutation(subj)
        P, Ks, T = set(perm[:35]), list(perm[35:64]), list(perm[64:])
        one = {s: [c for c in ms if c["subject"] == s] for s in Ks + T}
        pick = {s: one[s][rng.randint(len(one[s]))] for s in Ks + T}
        calib = np.concatenate([c["scores"][_isf(c)] for c in ms if c["subject"] in P])
        fam = cf.EnvelopeFamily(DELTA, template)
        safe = []
        for s in Ks:
            c = pick[s]
            if c["scores"].size == 0:
                safe.append(0); continue
            k, n = cf.conformal_ranks(c["scores"], calib)
            safe.append(cf.scan_safe_inflation(k, n, _isf(c), GAMMA, fam))
        theta = cf.scan_level_theta(safe, DELTA)
        infl = 10 ** 6 if theta is None else theta
        rows = pool.map(eval_scan, [(pick[s], calib, template, infl) for s in T])
        allrows += rows
        per_split.append({"theta_hat": theta, "n_pool": int(calib.size),
                          "test_exceed": int(sum(r["sel"] > 0 and r["fdp"] > GAMMA for r in rows))})
    return allrows, per_split


def main():
    d = np.load(CACHE, allow_pickle=True)
    cases = list(d["cases"])
    rec = {"preregistration": {"gamma": GAMMA, "delta": DELTA, "primary_template": "hc",
                               "secondary_template": "hybrid (exploratory)", "labels": "one-to-one lenient",
                               "dis_areas": "PV,JC,IT (>=2)", "layer2": "mslesseg 20 splits 35/29/11"},
           "results": {}}
    with Pool(max(1, (os.cpu_count() or 2) - 2)) as pool:
        for template in ("hc", "hybrid"):
            tag = "PRIMARY" if template == "hc" else "SECONDARY(exploratory)"
            print(f"\n===== template={template} [{tag}] =====")
            R = rec["results"].setdefault(template, {})
            for site in ("openms", "mslesseg"):
                rows = pool.map(eval_scan, loso_jobs(cases, site, template))
                R[f"layer1_loso|{site}"] = summarize(rows, f"L1 LOSO {site}")
            # healthy controls: own LOSO null (exchangeable floor) vs patient null (population shift)
            rows = pool.map(eval_scan, loso_jobs(cases, "sibbms", template))
            R["layer1_loso|sibbms(own null)"] = summarize(rows, "L1 controls, own LOSO null")
            rows = pool.map(eval_scan, loso_jobs(cases, "sibbms", template, calib_from=["openms", "mslesseg"]))
            R["layer1|sibbms(patient null)"] = summarize(rows, "L1 controls, PATIENT null")
            rows, splits = layer2_mslesseg(cases, template, pool)
            R["layer2|mslesseg"] = summarize(rows, "L2 scan-level mslesseg (20 splits)")
            R["layer2|mslesseg"]["splits"] = splits
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=2)
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
