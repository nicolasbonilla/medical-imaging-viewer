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

AMENDMENT v2 (2026-09-27, made BEFORE any Layer-2 real-data output was observed; the v1 run was
stopped unread). Reason: the adversarial validity review showed (a) A1 (candidate-level
exchangeability) is rejected at every site by exact permutation tests, so Layer 1 is reported as
EMPIRICAL only; (b) calibrating Layer 2 on the selected set's FDP covers only that selection, NOT
the simultaneous curve or the region certificates -> Layer 2 is now calibrated on the
SIMULTANEOUS event (V_k <= B*_k for all k), which covers selection + certified DIS; (c) the
Layer-2 pool need not come from the target site (validity needs only the K labelled and the test
subjects to be exchangeable GIVEN the pool), which makes Layer 2 feasible everywhere:
    openms   : pool = all MSLesSeg false scores;                  K=20 / test=10 openms subjects
    mslesseg : pool = 35 random MSLesSeg subjects;                K=29 / test=11 subjects
    controls : pool = all patient false scores (openms+MSLesSeg); K=20 / test=10 controls
  one random scan per subject in K and test; 20 random splits per site (seed 20260927 + site).
  Layer 2 is the ONLY guarantee claimed on real data. Also added: exact permutation test of A1
  (Kruskal-Wallis of false scores across scans, counts fixed, 2000 permutations).

AMENDMENT v2.1 (2026-09-28, before any real-data output was observed; the first v2 run was
stopped unread to add this): from the final adversarially-revised spec (CALM-FDX v1.1), a PAC
(training-conditional) Layer-2 quantile for DEVICE claims, delta_L = 0.05: theta_PAC = the
(K - j*)-th smallest safe value, j* = max{j : BinomCDF(j; K, delta) <= delta_L}. Feasible only
for K >= 29 (MSLesSeg); reported alongside the marginal Layer-2 result on the SAME splits.

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
                   bh_sel=0, bh_fp=0, bhm_sel=0, bhm_fp=0, lb={a: 0 for a in AREAS}, m0_hat=0,
                   curve_fail=False)
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
    V = np.cumsum(np.bincount(k[isf], minlength=n + 2))[1:n + 2]
    out["curve_fail"] = bool(np.any(V > Bstar))
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
         "curve_fail": {"scans": sum(r["curve_fail"] for r in rows),
                        "ci95": _clopper(sum(r["curve_fail"] for r in rows), N) if N else None},
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
          f" abstain {f['abstain_rate']} curve-fail {s['curve_fail']['scans']}/{N} | BH@g {s['bh_gamma']['scans_fdp_gt_gamma']}/{N} pw {s['bh_gamma']['power']}"
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


def layer2(cases, site, template, pool, pool_from=None, n_pool_subj=0, K=20, T=10, splits=20):
    """Layer 2 (scan-level, SIMULTANEOUS event). Subjects of `site` are split into K labelled and
    T test (one random scan each). The pool is either the false scores of `pool_from` sites
    (another source) or, if pool_from is None, of `n_pool_subj` random subjects of the same site."""
    rng = np.random.RandomState(SEED + {"openms": 1, "mslesseg": 2, "sibbms": 3}[site])
    tgt = [c for c in cases if c["site"] == site]
    subj = sorted({c["subject"] for c in tgt})
    ext_pool = (np.concatenate([c["scores"][_isf(c)] for c in cases if c["site"] in pool_from])
                if pool_from else None)
    per_split, allrows, pacrows = [], [], []
    for _ in range(splits):
        perm = list(rng.permutation(subj))
        P = set(perm[:n_pool_subj]); rest = perm[n_pool_subj:]
        Ks, Ts = rest[:K], rest[K:K + T]
        pick = {}
        for sj in Ks + Ts:
            cs = [c for c in tgt if c["subject"] == sj]
            pick[sj] = cs[rng.randint(len(cs))]
        calib = ext_pool if ext_pool is not None else np.concatenate(
            [c["scores"][_isf(c)] for c in tgt if c["subject"] in P])
        fam = cf.EnvelopeFamily(DELTA, template)
        safe = []
        for sj in Ks:
            c = pick[sj]
            if c["scores"].size == 0:
                safe.append(0)
                continue
            k, n = cf.conformal_ranks(c["scores"], calib)
            safe.append(cf.scan_safe_inflation_simultaneous(k, n, _isf(c), fam))
        theta = cf.scan_level_theta(safe, DELTA)
        infl = 10 ** 6 if theta is None else theta
        rows = pool.map(eval_scan, [(pick[sj], calib, template, infl) for sj in Ts])
        allrows += rows
        theta_pac = cf.scan_level_theta_pac(safe, DELTA, 0.05)
        if theta_pac is not None:
            rows_pac = pool.map(eval_scan, [(pick[sj], calib, template, theta_pac) for sj in Ts])
            pacrows += rows_pac
        per_split.append({"theta_hat": theta, "theta_pac": theta_pac, "n_pool": int(calib.size),
                          "safe_values": [int(x) for x in safe],
                          "test_curve_fail": int(sum(r["curve_fail"] for r in rows)),
                          "test_fdx": int(sum(r["sel"] > 0 and r["fdp"] > GAMMA for r in rows))})
    return allrows, per_split, pacrows


def a1_permutation_test(cases, site, perms=2000):
    """Exact test of candidate-level exchangeability: Kruskal-Wallis H of false scores across
    scans vs its distribution when false scores are permuted across scans (counts fixed)."""
    from scipy.stats import kruskal
    groups = [c["scores"][_isf(c)] for c in cases if c["site"] == site]
    groups = [g for g in groups if g.size >= 1]
    sizes = [g.size for g in groups]
    allv = np.concatenate(groups)
    obs = kruskal(*groups).statistic
    rng = np.random.RandomState(SEED)
    ge = 0
    for _ in range(perms):
        p = rng.permutation(allv)
        i = 0
        gs = []
        for z in sizes:
            gs.append(p[i:i + z])
            i += z
        ge += kruskal(*gs).statistic >= obs
    return {"H": round(float(obs), 2), "perm_p": (ge + 1) / (perms + 1), "scans": len(groups)}


def main():
    d = np.load(CACHE, allow_pickle=True)
    cases = list(d["cases"])
    rec = {"preregistration": {"gamma": GAMMA, "delta": DELTA, "primary_template": "hc",
                               "secondary_template": "hybrid (exploratory)", "labels": "one-to-one lenient",
                               "dis_areas": "PV,JC,IT (>=2)",
                               "layer2": "simultaneous; openms pool=mslesseg K20/T10; mslesseg 35/29/11; controls pool=patients K20/T10; 20 splits",
                               "pac": "delta_L=0.05, K>=29 only"},
           "results": {}}
    rec["a1_permutation_test"] = {site: a1_permutation_test(cases, site) for site in ("openms", "mslesseg")}
    print("A1 (candidate-level exchangeability) exact permutation test:", rec["a1_permutation_test"])
    with Pool(max(1, (os.cpu_count() or 2) - 2)) as pool:
        for template in ("hc", "hybrid"):
            tag = "PRIMARY" if template == "hc" else "SECONDARY(exploratory)"
            print("  (Layer 1 = EMPIRICAL only: A1 rejected; Layer 2 = the claimed guarantee)")
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
            for site, kw in [("openms", dict(pool_from=["mslesseg"], K=20, T=10)),
                             ("mslesseg", dict(n_pool_subj=35, K=29, T=11)),
                             ("sibbms", dict(pool_from=["openms", "mslesseg"], K=20, T=10))]:
                rows, splits, pacrows = layer2(cases, site, template, pool, **kw)
                key = f"layer2_simultaneous|{site}"
                R[key] = summarize(rows, f"L2 simultaneous {site} (20 splits)")
                R[key]["splits"] = splits
                if pacrows:
                    R[f"layer2_PAC|{site}"] = summarize(pacrows, f"L2 PAC (device) {site}")
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=2)
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
