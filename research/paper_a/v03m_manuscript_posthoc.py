#!/usr/bin/env python3
"""Paper A manuscript (2026-10-31) — POST-HOC analyses requested at the manuscript stage.

NOT pre-registered. Written after every v0.3 result had been seen (PROTOCOL-v0.3 §13 entry 10).
Nothing here changes a pre-registered number; every output is labelled post hoc in the manuscript.
Local CPU only; reads the frozen v0.3 candidate cache (SHA-256 2096109e...) and nothing else.

  A. Site-seen sensitivity. Ljubljana (open_ms_data) is a FLAMeS training SITE: 20 of its 30
     patients are FLAMeS training data. The 10 patients that no fold trained on were used in v0.3
     as calibration (1-mm pool) and as a held-out site. Here the primary cells are recomputed with
     Ljubljana removed from EVERY calibration pool:
       D3-noLj  calibrate on MSLesSeg only, test MS3SEG / Muslim / PediMS;
       D2-noLj  leave-one-site-out over MSLesSeg, MS3SEG, Muslim, PediMS (Ljubljana nowhere).
  B. Scan-aware baselines not carried into v0.3 (PROTOCOL-v0.3 §5 "not carried over"), on the
     pre-registered D3 and D2 calibration pools, ensemble arm, primary score:
       SUB      one false candidate drawn per calibration patient (first scan), conformal p-values
                against that subsampled null, BH within each test scan (Dunn-Wasserman-Ramdas-style
                subsampling); randomised -> R = 200 draws; per-patient FDP sums are averaged over
                draws before the patient-cluster bootstrap, so the interval is for the
                randomisation-averaged realised FDR.
       LR-hier  Lee & Ren (arXiv 2501.02514) hierarchical conformal e-values + e-BH over the whole
                batch of test scans of the held-out site (batch-FDR guarantee under group
                exchangeability and observation-independent group sizes); deterministic.
     The Learn-then-Test baseline with the per-scan FDP as loss is the pre-registered B3 and is
     taken from the v0.3 record (not recomputed). P1 is recomputed here only as a reproduction
     check of the harness against the v0.3 record.

    python research/paper_a/v03m_manuscript_posthoc.py
"""
import json
import os
import pickle
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import baselines as BL                                      # noqa: E402  (v0.2 implementations)
import v03_analysis as A                                    # noqa: E402
import v03_metrics as M                                     # noqa: E402
from v03_candidates import CACHE, sha256                    # noqa: E402
from v03_data import RECORDS, SITES, THICK_SITES            # noqa: E402

OUT = os.path.join(RECORDS, "2026-10-31_paper_a_manuscript_posthoc.json")
V03 = os.path.join(RECORDS, "2026-10-21_paper_a_v03_results.json")
SEED_M = 20261031
R_SUB = 200
EXPECTED_CACHE = "2096109e4da247aeaf03db43f4f5be02a14f95a450f711bb349e4942b9a6f4ec"
PRIMARY_PROCS = (("P1", 0.1), ("P1", 0.2), ("P2", 0.1), ("P2", 0.2))


def cell_from_sum(test, sum_fdp_avg, hits_avg, nsel_avg, target, label):
    """Classify a randomisation-averaged realised FDR (per-patient FDP sums averaged over draws)."""
    pats, T = A.patient_table(test, {t["case"]: np.zeros(t["scores"].size, bool) for t in test})
    W = A.weights(pats)
    n = T["n_scans"].sum()
    est = float(sum_fdp_avg.sum() / n)
    ci = A.rnd(M.ratio_ci(sum_fdp_avg, T["n_scans"], W))
    sens = float(hits_avg.sum() / T["n_gt"].sum()) if T["n_gt"].sum() else None
    cls = M.classify(ci, target, A.MARGIN)
    nsel = float(nsel_avg.sum())
    uninf = nsel < 10 or (sens is not None and sens < 0.05)
    return {"cell": label, "target": target, "estimate": A.rnd(est), "ci95": ci, "class": cls,
            "uninformative_abstention": bool(uninf and cls != "violated"),
            "sens_e2e": A.rnd(sens), "n_sel_mean": A.rnd(nsel, 1), "scans": int(n), "patients": len(pats)}


def per_patient(test, sel):
    pats, T = A.patient_table(test, sel)
    return pats, T["sum_fdp"], T["hits"], T["ns"]


def splits_custom(by, design, sites):
    if design == "D3-noLj":
        cal = by["mslesseg"]
        for site in THICK_SITES:
            yield site, cal, by[site]
    elif design == "D2-noLj":
        for site in sites:
            yield site, [s for x in sites if x != site for s in by[x]], by[site]
    else:
        raise ValueError(design)


def main():
    t0 = time.time()
    h = sha256(CACHE)
    assert h == EXPECTED_CACHE, h
    cache = pickle.load(open(CACHE, "rb"))
    v03 = json.load(open(V03))
    rec_prim = {c["cell"] + "|" + c["procedure"] + "|" + str(c["target"]): c for c in v03["primary"]}
    ens = A.build(cache, "ens")
    by = {}
    for s in ens:
        by.setdefault(s["site"], []).append(s)
    out = {"status": "POST-HOC (manuscript stage, 2026-10-31), not pre-registered; PROTOCOL-v0.3 §13 entry 10",
           "cache_sha256": h, "seed": SEED_M, "draws_subsampled": R_SUB, "arm": "ens (5-fold mean), primary score",
           "A_site_seen_sensitivity": {}, "B_baselines": {}, "reproduction_check": {}}

    # ---------------------------------------------------------------- A. Ljubljana out of every pool
    sites4 = ("mslesseg", "ms3seg", "muslim", "pedims")
    for design in ("D3-noLj", "D2-noLj"):
        for site, cal, test in splits_custom(by, design, sites4):
            for proc, tgt in PRIMARY_PROCS:
                sel, lam = A.select(cal, test, proc, tgt)
                c = A.primary_cell(test, sel, proc, tgt, f"{design}|{site}")
                c["threshold"] = None if lam is None or not np.isfinite(lam) else A.rnd(lam)
                c["calibration_patients"] = len({s["patient"] for s in cal})
                c["null_size"] = int(sum(int(s["isf"].sum()) for s in cal)) if proc == "P1" else None
                ref = rec_prim.get(f"{design.split('-')[0]}|{site}|{proc}|{tgt}")
                if ref is not None:
                    c["preregistered_with_Ljubljana"] = {"estimate": ref["estimate"], "ci95": ref["ci95"],
                                                         "class": ref["class"], "sens_e2e": ref["sens_e2e"]}
                out["A_site_seen_sensitivity"][f"{design}|{site}|{proc}|{tgt}"] = c
                print(f"A {design:8s} {site:9s} {proc} {tgt}: {c['estimate']} {c['ci95']} {c['class']}"
                      f"{' [abst]' if c['uninformative_abstention'] else ''} sens {c['sens_e2e']}"
                      f" | prereg {ref['estimate'] if ref else '-'} {ref['class'] if ref else ''}", flush=True)
    print(f"A done ({time.time() - t0:.0f} s)", flush=True)

    # ---------------------------------------------------------------- B. baselines, pre-registered pools
    for design in ("D3", "D2"):
        for site, cal, test in A.splits(ens, design):
            fs = A.first_scans(cal)
            # reproduction check: P1 through the same harness
            for tgt in (0.1, 0.2):
                sel, _ = A.select(cal, test, "P1", tgt)
                est = A.summarize(test, sel)["mean_fdp"]
                ref = rec_prim[f"{design}|{site}|P1|{tgt}"]["estimate"]
                out["reproduction_check"][f"{design}|{site}|P1|{tgt}"] = {"recomputed": est, "v03_record": ref,
                                                                          "equal": abs(est - ref) < 1e-9}
            for tgt in (0.1, 0.2):
                # SUB: one false candidate per calibration patient, R draws
                rng = np.random.RandomState(SEED_M + 13 * SITES.index(site) + int(100 * tgt) + (0 if design == "D3" else 7))
                acc_s = acc_h = acc_n = None
                draws_fdr, draws_sens, nulls = [], [], []
                for _ in range(R_SUB):
                    sels = BL.subsampled_bh(fs, test, tgt, rng)
                    sel = {t["case"]: s for t, s in zip(test, sels)}
                    pats, sf, hh, nn = per_patient(test, sel)
                    acc_s = sf if acc_s is None else acc_s + sf
                    acc_h = hh if acc_h is None else acc_h + hh
                    acc_n = nn if acc_n is None else acc_n + nn
                    n_sc = sum(1 for _ in test)
                    draws_fdr.append(float(sf.sum() / n_sc))
                    n_gt = sum(t["gt_ids"].size for t in test)
                    draws_sens.append(float(hh.sum() / n_gt) if n_gt else 0.0)
                    nulls.append(sum(1 for c in fs if c["isf"].any()))
                c = cell_from_sum(test, acc_s / R_SUB, acc_h / R_SUB, acc_n / R_SUB, tgt, f"{design}|{site}")
                c.update({"draws": R_SUB, "null_size": int(np.median(nulls)),
                          "realised_fdr_draws_q025_q975": A.rnd(np.quantile(draws_fdr, [0.025, 0.975]).tolist()),
                          "share_draws_above_alpha": A.rnd(float(np.mean(np.array(draws_fdr) > tgt + 1e-12))),
                          "sens_draws_q025_q975": A.rnd(np.quantile(draws_sens, [0.025, 0.975]).tolist())})
                out["B_baselines"][f"SUB|{design}|{site}|{tgt}"] = c
                # LR-hier: hierarchical conformal e-values + e-BH over the test batch
                sels = BL.leeren(fs, test, tgt, variant="hier")
                sel = {t["case"]: s for t, s in zip(test, sels)}
                s = A.summarize(test, sel)
                pats, T = A.patient_table(test, sel)
                cls = M.classify(s["mean_fdp_ci"], tgt, A.MARGIN)
                uninf = s["n_sel"] < 10 or (s["sens_e2e"] is not None and s["sens_e2e"] < 0.05)
                out["B_baselines"][f"LRhier|{design}|{site}|{tgt}"] = {
                    "cell": f"{design}|{site}", "target": tgt, "estimate": s["mean_fdp"], "ci95": s["mean_fdp_ci"],
                    "class": cls, "uninformative_abstention": bool(uninf and cls != "violated"),
                    "batch_fdp": s["micro_fdr"], "batch_fdp_ci95": s["micro_fdr_ci"], "n_sel": s["n_sel"],
                    "sens_e2e": s["sens_e2e"], "scans_selecting": s["scans_selecting"],
                    "calibration_groups": len(fs)}
                b3 = v03["designs"][f"ens|{design}"][f"B3|{tgt}"][site]
                out["B_baselines"][f"B3_LTT_from_v03|{design}|{site}|{tgt}"] = {
                    "estimate": b3["mean_fdp"], "ci95": b3["mean_fdp_ci"], "sens_e2e": b3["sens_e2e"],
                    "n_sel": b3["n_sel"], "class": M.classify(b3["mean_fdp_ci"], tgt, A.MARGIN)}
                lr = out["B_baselines"][f"LRhier|{design}|{site}|{tgt}"]
                print(f"B {design} {site:9s} a={tgt}: SUB {c['estimate']} {c['ci95']} {c['class']} sens {c['sens_e2e']}"
                      f" | LRhier {lr['estimate']} batch {lr['batch_fdp']} n_sel {lr['n_sel']} sens {lr['sens_e2e']} {lr['class']}"
                      f" | B3 {b3['mean_fdp']} sens {b3['sens_e2e']}", flush=True)
    out["reproduction_all_equal"] = all(v["equal"] for v in out["reproduction_check"].values())
    print("reproduction of v0.3 P1 cells:", out["reproduction_all_equal"], flush=True)
    out["runtime_s"] = round(time.time() - t0, 1)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print("wrote", OUT, f"in {out['runtime_s']} s")


if __name__ == "__main__":
    main()
