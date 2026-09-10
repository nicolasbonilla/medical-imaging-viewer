#!/usr/bin/env python3
"""CALM-MS — multi-site characterization of conformal lesion-FDR under REAL MS shift.

HONEST FRAMING (rewritten after a 3-agent adversarial review that refuted an earlier
"conformal breaks across every site shift" headline — the clean axis actually HOLDS).

What the numbers here support, precisely:
  1. ROBUSTNESS (the surprising part): distribution-free conformal lesion-FDR control
     (Jin & Candès selection + Benjamini-Hochberg) TRANSPORTS across same-segmenter
     acquisition/population shift between two real MS patient cohorts — realized micro-FDR
     stays <= alpha at alpha in {0.2, 0.3} (one marginal breach at alpha=0.10) — DESPITE the
     FP-score law being formally non-exchangeable by KS. The guarantee is more robust than
     its own assumption. We also report per-SCAN FDP (the quantity BH actually bounds), not
     only the pooled micro-FDR, and subject-level bootstrap CIs.
  2. SPECIFICITY degrades under population/prevalence shift: on HEALTHY controls (zero
     prevalence) a patient-derived null produces ~100-230 false detections / 100 scans vs
     ~10-30 under the controls' OWN null (the exchangeable floor). Realized FDR is 1.0 by
     construction on controls (no true lesions), so we report the false-discovery RATE and
     its ratio to the own-null floor, not FDR.
  3. POWER (not FDR) collapses under a SEGMENTER change: a FLAMeS-calibrated null applied to
     LST-AI-segmented data selects almost nothing (FDR-safe, zero sensitivity). The ISBI
     cohort is TRIPLE-confounded (segmenter + acquisition + population) and its patient
     identity is not recoverable from the flat case naming, so it is used ONLY as a
     test-only transfer-stress probe and is EXCLUDED from the Mondrian few-shot section
     (its case001..019 are timepoints of ~5 ISBI-2015 patients -> few-shot on them would
     leak within-patient). Do not read its numbers as "algorithm shift" in isolation.
  4. The few-shot Mondrian REMEDY restores/keeps FDR control on FLAMeS patient sites but at
     RECALL 0.05-0.30 across alpha — control partly by abstention; not yet a deployable
     operating point. Power is printed beside every FDR.

A naive precision-matched global threshold is included as a BASELINE.

Cohorts (data/cohorts/*):
  openms   = open_ms_data     FLAMeS  patients  30 scans / 30 subj   (single-TP)
  mslesseg = MSLesSeg         FLAMeS  patients 115 scans / 75 subj   (P<n> groups TPs)
  sibbms   = sib/BMS controls FLAMeS  controls 30 acquired           (0 true lesions)
  isbi     = ISBI-2015        LST-AI  patients 19 scans              (test-only probe)

    python scripts/calm-ms/multisite_conformal_fdr.py
"""
import os, sys, glob, json, re

import numpy as np
import nibabel as nib

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(_HERE, "..", "..", "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.services.calm_ms_inference import extract_lesion_candidates, label_candidates_tp  # noqa: E402
from app.services.conformal_lesion_fdr import conformal_pvalues, benjamini_hochberg          # noqa: E402

THRESHOLD, MIN_VOL, SCORE, SPACING = 0.5, 3.0, "mean", (1.0, 1.0, 1.0)
MIN_OVERLAP_MAIN = 0.0          # any-voxel TP (lenient); a stricter 0.10 robustness pass runs too
ALPHAS = (0.30, 0.20, 0.10)
K_SHOTS = (2, 5, 10, 20)
N_REPEAT = 50
N_BOOT = 2000
SEED = 20260823
_CACHE = os.path.join(_HERE, ".multisite_cache_v2.npz")
_OUT = os.path.join(_BACKEND, "app", "services", "assets", "multisite_conformal_record.json")

SITES = {
    "openms":   dict(sub="openms-flames",         seg="FLAMeS", kind="patients", null_source=True,  mondrian=True),
    "mslesseg": dict(sub="mslesseg-flames",        seg="FLAMeS", kind="patients", null_source=True,  mondrian=True),
    "sibbms":   dict(sub="sibbms-controls-flames", seg="FLAMeS", kind="controls", null_source=True,  mondrian=False),
    "isbi":     dict(sub="isbi19-lstai",           seg="LST-AI", kind="patients", null_source=False, mondrian=False),
}
FLAMES_PAT = [s for s, m in SITES.items() if m["seg"] == "FLAMeS" and m["kind"] == "patients"]


def _acquired_scan_count(site):
    """ALL acquired scans with a GT (denominator for the control specificity rate) — counts
    even scans that produced zero candidates (a perfect-specificity control scan)."""
    d = os.path.join("data", "cohorts", SITES[site]["sub"])
    probs = glob.glob(os.path.join(d, "*_prob.nii.gz"))
    return sum(1 for p in probs
               if os.path.exists(p[:-len("_prob.nii.gz")] + "_gt.nii.gz"))


def _subject_of(site, case):
    if site == "mslesseg":
        m = re.match(r"mslesseg_(P\d+)(?:_|$)", case)
        if not m:
            raise ValueError(f"cannot parse MSLesSeg subject from {case!r}")
        return "mslesseg_" + m.group(1)
    return f"{site}:{case}"


def _extract_all():
    if os.path.exists(_CACHE):
        d = np.load(_CACHE, allow_pickle=True)
        return list(d["cases"]), {k: int(v) for k, v in d["acq"].item().items()}
    cases = []
    for site, meta in SITES.items():
        for prob_path in sorted(glob.glob(os.path.join("data", "cohorts", meta["sub"], "*_prob.nii.gz"))):
            case = os.path.basename(prob_path)[:-len("_prob.nii.gz")]
            gt_path = os.path.join(os.path.dirname(prob_path), case + "_gt.nii.gz")
            if not os.path.exists(gt_path):
                continue
            prob = np.asarray(nib.load(prob_path).get_fdata(), dtype=np.float32)
            gt = (np.asarray(nib.load(gt_path).get_fdata()) > 0).astype(np.uint8)
            labeled, cands = extract_lesion_candidates(prob, THRESHOLD, SPACING,
                                                       min_volume_mm3=MIN_VOL, score=SCORE)
            if not cands:
                continue
            scores = np.array([c.score for c in cands], dtype=float)
            false0 = np.array([not v for v in label_candidates_tp(labeled, cands, gt, min_overlap=0.0).values()], bool)
            false1 = np.array([not v for v in label_candidates_tp(labeled, cands, gt, min_overlap=0.10).values()], bool)
            cases.append({"site": site, "case": case, "subject": _subject_of(site, case),
                          "scores": scores, "is_false0": false0, "is_false1": false1})
            print(f"  [{site}] {case}: {len(cands)} cand, {int(false0.sum())} false", end="\r")
    print()
    acq = {s: _acquired_scan_count(s) for s in SITES}
    np.savez_compressed(_CACHE, cases=np.array(cases, dtype=object), acq=np.array(acq, dtype=object))
    return cases, acq


# ---- selection + realized metrics -----------------------------------------------------
def _select(test_scores, null_scores, alpha):
    if null_scores.size < 3:
        return np.zeros(test_scores.size, bool)
    return benjamini_hochberg(conformal_pvalues(test_scores, null_scores), alpha=alpha)


def _false_scores(cases, site, key, exclude_subject=None, exclude_site=None):
    arrs = [c["scores"][c[key]] for c in cases
            if c["site"] == site and c["subject"] != exclude_subject]
    return np.concatenate(arrs) if arrs else np.array([])


def _pooled_null(cases, key, exclude_site):
    """FLAMeS-patient FP scores, leave-one-SITE-out (fixes the in-sample POOLED leak)."""
    arrs = [c["scores"][c[key]] for c in cases
            if SITES[c["site"]]["kind"] == "patients" and SITES[c["site"]]["seg"] == "FLAMeS"
            and c["site"] != exclude_site]
    return np.concatenate(arrs) if arrs else np.array([])


def _perscan(test_cases, null_fn, alpha, key):
    """Per-scan (n_sel, n_false_sel, n_true_sel, n_true, subject). null_fn(tc)->null array."""
    rows = []
    for tc in test_cases:
        sel = _select(tc["scores"], null_fn(tc), alpha)
        isf = tc[key]
        rows.append((int(sel.sum()), int((sel & isf).sum()),
                     int((sel & ~isf).sum()), int((~isf).sum()), tc["subject"]))
    return rows


def _agg(rows, alpha=None):
    ns = sum(r[0] for r in rows); nf = sum(r[1] for r in rows)
    nts = sum(r[2] for r in rows); nt = sum(r[3] for r in rows)
    micro = (nf / ns) if ns else 0.0
    power = (nts / nt) if nt else float("nan")
    fdps = [r[1] / r[0] for r in rows if r[0] > 0]
    mean_fdp = float(np.mean(fdps)) if fdps else 0.0
    frac_exceed = (float(np.mean([f > alpha for f in fdps])) if (fdps and alpha is not None) else 0.0)
    return micro, power, ns, mean_fdp, frac_exceed


def _boot_ci(rows, n_boot, rng, subj_level=True):
    """Bootstrap CI of micro-FDR, resampling SUBJECTS (cluster) with replacement."""
    if not rows:
        return (None, None)
    by_subj = {}
    for r in rows:
        by_subj.setdefault(r[4], []).append(r)
    keys = list(by_subj)
    vals = []
    for _ in range(n_boot):
        pick = rng.choice(len(keys), size=len(keys), replace=True)
        ns = nf = 0
        for i in pick:
            for r in by_subj[keys[i]]:
                ns += r[0]; nf += r[1]
        if ns:
            vals.append(nf / ns)
    if not vals:
        return (None, None)
    return (round(float(np.percentile(vals, 2.5)), 3), round(float(np.percentile(vals, 97.5)), 3))


def main():
    print("Extracting candidates + TP/FP labels (any-voxel & >=0.10 overlap), cached ...")
    cases, acq = _extract_all()
    by_site = {s: [c for c in cases if c["site"] == s] for s in SITES}
    rng = np.random.RandomState(SEED)
    rec = {"config": {"threshold": THRESHOLD, "min_vol_mm3": MIN_VOL, "alphas": list(ALPHAS),
                      "tp_rule": "any-voxel (main) + >=0.10 overlap (robustness)",
                      "n_boot": N_BOOT, "n_repeat": N_REPEAT},
           "sites": {}, "ks": {}, "realized_fdr": {}, "naive_threshold": {},
           "control_specificity": {}, "mondrian_kshot": {}, "robustness_overlap": {}}

    print("\nSite summary:")
    for s, meta in SITES.items():
        cs = by_site[s]
        fp = np.concatenate([c["scores"][c["is_false0"]] for c in cs]) if cs else np.array([])
        tp = np.concatenate([c["scores"][~c["is_false0"]] for c in cs]) if cs else np.array([])
        nsub = len({c["subject"] for c in cs})
        rec["sites"][s] = {"seg": meta["seg"], "kind": meta["kind"], "acquired_scans": acq[s],
                           "scans_with_cand": len(cs), "subjects": nsub,
                           "n_false": int(fp.size), "n_true": int(tp.size),
                           "fp_mean": round(float(fp.mean()), 4) if fp.size else None,
                           "tp_mean": round(float(tp.mean()), 4) if tp.size else None}
        print(f"  {s:9s}[{meta['seg']:6s} {meta['kind']:8s}] acq={acq[s]:3d} cand-scans={len(cs):3d}"
              f" subj={nsub:3d} | FP n={fp.size} m={rec['sites'][s]['fp_mean']}"
              f" | TP n={tp.size} m={rec['sites'][s]['tp_mean']}")

    # Exchangeability diagnostic — report effect size D; significance is uninformative at
    # this n with intra-scan clustering, so we gate 'meaningful' on D, not p.
    from scipy.stats import ks_2samp
    print("\nFP-score two-sample KS (effect size D; p is anti-conservative under clustering):")
    ks_keys = list(SITES)
    for i in range(len(ks_keys)):
        for j in range(i + 1, len(ks_keys)):
            a, b = ks_keys[i], ks_keys[j]
            fa = np.concatenate([c["scores"][c["is_false0"]] for c in by_site[a]])
            fb = np.concatenate([c["scores"][c["is_false0"]] for c in by_site[b]])
            if fa.size < 3 or fb.size < 3:
                continue
            ks = ks_2samp(fa, fb)
            meaningful = ks.statistic > 0.20
            rec["ks"][f"{a}|{b}"] = {"D": round(float(ks.statistic), 3), "p": float(ks.pvalue),
                                     "meaningful_D_gt_0.2": bool(meaningful)}
            print(f"  {a:9s} vs {b:9s}: D={ks.statistic:.3f} (p={ks.pvalue:.1e})"
                  f"  {'MEANINGFUL' if meaningful else 'small'}")

    # ---- Realized FDR on PATIENT test sites (fdr/power, CI, per-scan FDP) --------------
    patient_test = [s for s in SITES if SITES[s]["kind"] == "patients"]
    null_srcs = [s for s in SITES if SITES[s]["null_source"]]
    print("\nRealized FDR on PATIENT test sites  [micro-FDR / power | meanFDP | %scans>alpha]")
    print("  diagonal = leave-one-SUBJECT-out ; POOLED = leave-one-SITE-out ; '·' = nothing selected")
    for alpha in ALPHAS:
        print(f"\n  alpha={alpha:.2f}")
        for nsrc in null_srcs + ["POOLED"]:
            for tsite in patient_test:
                if nsrc == "POOLED":
                    null_fn = (lambda t, xs=tsite: _pooled_null(cases, "is_false0", exclude_site=xs))
                elif nsrc == tsite:
                    null_fn = (lambda t: _false_scores(cases, t["site"], "is_false0", exclude_subject=t["subject"]))
                else:
                    nl = _false_scores(cases, nsrc, "is_false0")
                    null_fn = (lambda t, nn=nl: nn)
                rows = _perscan(by_site[tsite], null_fn, alpha, "is_false0")
                micro, power, nsel, mfdp, fexc = _agg(rows, alpha)
                ci = _boot_ci(rows, N_BOOT, rng) if nsel else (None, None)
                rec["realized_fdr"][f"{alpha}|{nsrc}|{tsite}"] = {
                    "micro_fdr": round(micro, 4), "ci95": ci,
                    "power": (round(power, 4) if power == power else None),
                    "n_sel": nsel, "mean_perscan_fdp": round(mfdp, 4), "frac_scans_exceed_alpha": round(fexc, 3)}
                mark = "·" if nsel == 0 else f"{micro:.2f}/{power:.2f} [{ci[0]},{ci[1]}] fdp{mfdp:.2f} x{fexc:.2f}"
                print(f"    {nsrc:9s} -> {tsite:9s}: {mark}")

    # ---- Naive precision-matched threshold BASELINE -----------------------------------
    # Calibrate tau on the null site so its own FP-fraction among selected <= alpha, apply
    # cross-site. Shows whether a fixed threshold transports as well as conformal.
    print("\nNaive precision-matched threshold baseline (calib on null site -> apply cross-site):")
    def _tau_for(site_cases, alpha, key):
        sc = np.concatenate([c["scores"] for c in site_cases])
        isf = np.concatenate([c[key] for c in site_cases])
        order = np.argsort(-sc)
        sc_o, isf_o = sc[order], isf[order]
        cum_false = np.cumsum(isf_o); n = np.arange(1, len(sc_o) + 1)
        ok = (cum_false / n) <= alpha
        if not ok.any():
            return np.inf
        k = np.max(np.where(ok)[0])
        return sc_o[k]
    for alpha in ALPHAS:
        for nsrc in FLAMES_PAT:
            tau = _tau_for(by_site[nsrc], alpha, "is_false0")
            for tsite in FLAMES_PAT:
                if tsite == nsrc:
                    continue
                sc = np.concatenate([c["scores"] for c in by_site[tsite]])
                isf = np.concatenate([c["is_false0"] for c in by_site[tsite]])
                sel = sc >= tau
                fdr = float((sel & isf).sum() / max(sel.sum(), 1))
                power = float((sel & ~isf).sum() / max((~isf).sum(), 1))
                rec["naive_threshold"][f"{alpha}|{nsrc}|{tsite}"] = {
                    "tau": round(float(tau), 4), "fdr": round(fdr, 4), "power": round(power, 4),
                    "n_sel": int(sel.sum())}
                print(f"  a={alpha} tau({nsrc})={tau:.3f} -> {tsite}: FDR={fdr:.3f} power={power:.3f}")

    # ---- Healthy-control specificity: false discoveries / 100 ACQUIRED scans ----------
    print("\nHealthy-control false discoveries per 100 ACQUIRED scans (denominator = all acquired):")
    print("  own-null = the exchangeable FLOOR; a valid conformal null still fires ~nominally")
    for csite in [s for s in SITES if SITES[s]["kind"] == "controls"]:
        denom = acq[csite]
        print(f"  control {csite} (acquired={denom}):")
        for alpha in ALPHAS:
            line = f"    a={alpha}: "
            for nsrc in null_srcs + ["POOLED"]:
                if nsrc == "POOLED":
                    null_fn = (lambda t: _pooled_null(cases, "is_false0", exclude_site=None))
                elif nsrc == csite:
                    null_fn = (lambda t: _false_scores(cases, t["site"], "is_false0", exclude_subject=t["subject"]))
                else:
                    nl = _false_scores(cases, nsrc, "is_false0")
                    null_fn = (lambda t, nn=nl: nn)
                fd = sum(int(_select(tc["scores"], null_fn(tc), alpha).sum()) for tc in by_site[csite])
                per100 = round(100.0 * fd / max(denom, 1), 1)
                rec["control_specificity"][f"{alpha}|{nsrc}|{csite}"] = {"false_disc": fd, "per_100": per100}
                line += f"{nsrc}={per100}  "
            print(line)

    # ---- Mondrian few-shot remedy (FLAMeS patient sites only; isbi excluded: leak) -----
    print("\nMondrian few-shot (k labelled SUBJECTS -> null; FLAMeS patient sites only):")
    for tsite in [s for s in SITES if SITES[s].get("mondrian")]:
        subs = sorted({c["subject"] for c in by_site[tsite]})
        print(f"  {tsite} ({len(subs)} subjects):")
        ks = {}
        for k in K_SHOTS:
            if k >= len(subs):
                continue
            per = {a: {"fdr": [], "power": []} for a in ALPHAS}
            for _ in range(N_REPEAT):
                sl = set(rng.choice(subs, size=k, replace=False).tolist())
                slc = [c for c in by_site[tsite] if c["subject"] in sl]
                evc = [c for c in by_site[tsite] if c["subject"] not in sl]
                nk = np.concatenate([c["scores"][c["is_false0"]] for c in slc]) if slc else np.array([])
                if nk.size < 3:
                    continue
                for a in ALPHAS:
                    rows = _perscan(evc, (lambda t, nn=nk: nn), a, "is_false0")
                    micro, power, _, _, _ = _agg(rows)
                    per[a]["fdr"].append(micro)
                    if power == power:
                        per[a]["power"].append(power)
            ks[f"k={k}"] = {f"a={a}": {
                "fdr_mean": round(float(np.mean(per[a]["fdr"])), 3) if per[a]["fdr"] else None,
                "fdr_resample_sd": round(float(np.std(per[a]["fdr"])), 3) if per[a]["fdr"] else None,
                "power_mean": round(float(np.mean(per[a]["power"])), 3) if per[a]["power"] else None}
                for a in ALPHAS}
            cells = " | ".join(f"a{a}:{ks[f'k={k}'][f'a={a}']['fdr_mean']}"
                               f"/{ks[f'k={k}'][f'a={a}']['power_mean']}" for a in ALPHAS)
            print(f"     k={k:2d} (fdr/power): {cells}")
        rec["mondrian_kshot"][tsite] = ks

    # ---- Robustness: does the cross-site conclusion survive a STRICTER TP rule? --------
    print("\nRobustness — same cells under >=0.10-overlap TP rule (a=0.20):")
    for nsrc in FLAMES_PAT:
        for tsite in FLAMES_PAT:
            if tsite == nsrc:
                continue
            nl = _false_scores(cases, nsrc, "is_false1")
            rows = _perscan(by_site[tsite], (lambda t, nn=nl: nn), 0.20, "is_false1")
            micro, power, nsel, mfdp, _ = _agg(rows)
            rec["robustness_overlap"][f"0.2|{nsrc}|{tsite}"] = {
                "micro_fdr": round(micro, 4), "power": (round(power, 4) if power == power else None), "n_sel": nsel}
            print(f"  {nsrc} -> {tsite}: FDR={micro:.3f} power={power:.3f} (n_sel={nsel})")

    with open(_OUT, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=2)
    print(f"\nWrote {_OUT}")


if __name__ == "__main__":
    main()
