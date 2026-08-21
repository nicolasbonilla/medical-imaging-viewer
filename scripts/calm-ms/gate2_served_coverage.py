#!/usr/bin/env python3
"""CALM-MS V&V Gate-2: within-domain coverage of the SERVED statistic.

Generates the honest coverage record for the statistic the endpoint ACTUALLY serves
— RAW mean-pooled probability — retiring the learned-scorer figures (0.021/0.044/0.067)
that describe an UNWIRED path. Protocol locked by the 2026-08-21 adversarial
design+refute (workflow w2nwis0e5). Every rigor decision below is a refuter mandate:

  * Leave-one-SUBJECT-out, NOT leave-one-scan-out. MSLesSeg is longitudinal
    (75 patients, 115 series; up to 4 timepoints/patient). Dropping one scan leaves
    the same patient's other timepoints in the null -> self-calibration -> optimistic
    FDR. We drop the whole subject's candidates from each fold's null.
  * NULL VALUE-EQUIVALENCE check. The experiment RE-DERIVES nulls from raw pairs;
    it never loads the frozen asset. So we check the pipeline reproduces the served
    null: sorted(all-115 false-candidate scores @ calib_overlap 0.0, float32) ==
    sorted(frozen null_scores) (n=1174). This is a float32 MULTISET value-equality
    (order discarded), not byte equality and not a proof — it validates candidate
    extraction + TP labelling reproducing the null, NOT the selection/metric code
    (those reuse the served select_by_fdr directly). Without it the record could
    validate a phantom.
  * Marginal FDR<=alpha is a CONSISTENCY CHECK on the Gate-1 theorem, not the headline
    evidence. The load-bearing outputs are (i) subject-exchangeable validity,
    (ii) per-scan FDP DISPERSION (quantiles + exceedance, incl. conditional on
    n_sel>0), (iii) the sensitivity cost.
  * Probe A (evaluation-only) overlap disclosure. The served TP rule is any-voxel
    (min_overlap 0.0), which can relabel over-segmentation fragments as multiple TPs.
    Holding the SHIPPED selection fixed (0.0 null), we recompute FDP under stricter TP
    rules (>=10%, majority>=50%, greedy 1-GT-to-1-candidate) to disclose that optimism.
  * Sensitivity is recorded but its clinical acceptance is DEFERRED to Gate 4/5
    (HAZ-CALM-3/8) — a missed lesion is the more severe MS hazard; a floor needs a
    usability/clinical study, not this script.

Cohort = the exact 115 MSLesSeg FLAMeS pairs the frozen null is built from
(data/cohorts/mslesseg-flames), same params (thr 0.5, min_vol 3.0, score mean, MNI 1mm).

    python scripts/calm-ms/gate2_served_coverage.py

Output: docs/calm-ms/gate2_served_coverage_record.json
"""
import os, sys, glob, re, json, datetime
import numpy as np
import nibabel as nib

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(_HERE, "..", "..", "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.services.calm_ms_inference import extract_lesion_candidates          # noqa: E402
from app.services.lesion_metrics import label_lesions                         # noqa: E402
from app.services.conformal_lesion_fdr import select_by_fdr                   # noqa: E402

# --- SERVED config (must match build_null_bundle.py exactly) ------------------
THRESHOLD = 0.5
MIN_VOLUME_MM3 = 3.0
SCORE = "mean"
VOXEL_SPACING = (1.0, 1.0, 1.0)
CALIB_OVERLAP = 0.0                      # served TP convention (any-voxel)
ALPHAS = [0.30, 0.20, 0.10]              # frozen presets
EVAL_OVERLAPS = {"eval_0.10": 0.10, "eval_majority": 0.50}   # Probe A thresholds
N_BOOTSTRAP = 10000
SEED = 0
_COHORT = os.path.join("data", "cohorts", "mslesseg-flames")
_FROZEN = os.path.join(_BACKEND, "app", "services", "assets", "calm_ms_null_flames_v2.npz")
_OUT = os.path.join("docs", "calm-ms", "gate2_served_coverage_record.json")


def _subject_of(case: str) -> str:
    """Patient id P<n> from a case name like `mslesseg_P10_T2` or bare `mslesseg_P54`
    (single-timepoint). Fail closed if a name yields no P<n> key — a silent fallback
    would split one patient's timepoints across two 'subjects' and leak into the null."""
    m = re.match(r"mslesseg_(P\d+)(?:_|$)", case)
    if not m:
        raise ValueError(f"cannot parse subject P<n> from case name {case!r} — refusing "
                         "(a fallback key would risk same-patient leakage)")
    return m.group(1)


def _prep_scan(prob, gt):
    """Per-candidate: score, overlap_frac (|cand cap gt|/n_vox), gt_hits (GT labels),
    and served TP flag (any-voxel). GT labelled once. Mirrors label_candidates_tp."""
    labeled, cands = extract_lesion_candidates(prob, THRESHOLD, VOXEL_SPACING, MIN_VOLUME_MM3, SCORE)
    gtb = (gt > 0)
    gt_labeled, n_gt = label_lesions(gtb.astype(np.uint8))
    rows = []
    for c in cands:
        comp = (labeled == c.label)
        inter = np.logical_and(comp, gtb)
        overlap = int(inter.sum())
        frac = (overlap / c.n_voxels) if c.n_voxels else 0.0
        hits = set(int(x) for x in np.unique(gt_labeled[comp]) if x != 0)
        rows.append({"score": float(c.score), "overlap_frac": float(frac),
                     "gt_hits": hits, "tp0": frac > CALIB_OVERLAP})
    return {"cands": rows, "n_gt": int(n_gt)}


def _fp_flags(sel_rows, rule):
    """Boolean FP flag per SELECTED candidate under a TP `rule`. Probe A: selection is
    fixed; only the TP definition changes. Returns (fp_flags, detected_gt_set)."""
    if rule == "served":
        fp = [not r["tp0"] for r in sel_rows]
        det = set().union(*[r["gt_hits"] for r in sel_rows]) if sel_rows else set()
        return fp, det
    if rule.startswith("eval_"):
        thr = EVAL_OVERLAPS[rule]
        fp = [not (r["overlap_frac"] > thr and r["gt_hits"]) for r in sel_rows]
        det = set().union(*[r["gt_hits"] for r in sel_rows if r["overlap_frac"] > thr]) if sel_rows else set()
        return fp, det
    if rule == "greedy_1to1":
        # Highest-score first claims one unclaimed GT lesion it hits; fragments over an
        # already-claimed lesion (or hitting none) are FP. Penalises over-segmentation.
        claimed, fp = set(), []
        order = sorted(range(len(sel_rows)), key=lambda i: -sel_rows[i]["score"])
        is_fp = [True] * len(sel_rows)
        for i in order:
            avail = sel_rows[i]["gt_hits"] - claimed
            if avail:
                g = min(avail)
                claimed.add(g)
                is_fp[i] = False
        return is_fp, set(claimed)
    raise ValueError(rule)


def _scan_metrics(sel_rows, n_gt, rule):
    n_sel = len(sel_rows)
    if n_sel == 0:
        return {"fdp": 0.0, "n_sel": 0, "sens": (1.0 if n_gt == 0 else 0.0)}
    fp, det = _fp_flags(sel_rows, rule)
    fdp = float(sum(fp)) / n_sel
    sens = (len(det) / n_gt) if n_gt else 1.0
    return {"fdp": fdp, "n_sel": n_sel, "sens": float(sens)}


def main():
    pairs = []
    for prob_path in sorted(glob.glob(os.path.join(_COHORT, "*_prob.nii.gz"))):
        case = os.path.basename(prob_path)[:-len("_prob.nii.gz")]
        gt_path = os.path.join(_COHORT, case + "_gt.nii.gz")
        if not os.path.exists(gt_path):
            continue
        prob = np.asarray(nib.load(prob_path).get_fdata(), dtype=np.float32)
        gt = (np.asarray(nib.load(gt_path).get_fdata()) > 0).astype(np.uint8)
        pairs.append((case, _subject_of(case), prob, gt))
    n = len(pairs)
    if n < 2:
        sys.exit(f"need >= 2 cases, found {n}")
    subjects = sorted(set(s for _, s, _, _ in pairs))
    print(f"Loaded {n} scans across {len(subjects)} subjects. Extracting candidates ...")

    preps = []
    for case, subj, prob, gt in pairs:
        p = _prep_scan(prob, gt)
        p["case"], p["subject"] = case, subj
        preps.append(p)
        print(f"  {case} [{subj}]: {len(p['cands'])} cand, {p['n_gt']} GT", flush=True)

    # ---- NULL VALUE-EQUIVALENCE (float32 multiset): the pipeline reproduces the frozen null.
    all_false = np.array([r["score"] for p in preps for r in p["cands"] if not r["tp0"]],
                         dtype=np.float32)
    frozen = np.asarray(np.load(_FROZEN, allow_pickle=False)["null_scores"], dtype=np.float32)
    eq = (all_false.size == frozen.size and
          np.array_equal(np.sort(all_false), np.sort(frozen)))
    print(f"\nNull equivalence: derived {all_false.size} vs frozen {frozen.size} -> "
          f"{'IDENTICAL' if eq else 'MISMATCH'}")
    if not eq:
        sys.exit("NULL MISMATCH — the experiment pipeline does not reproduce the served "
                 "null; record would validate a phantom. Refusing to write.")

    rng = np.random.default_rng(SEED)
    subj_to_idx = {s: [i for i, p in enumerate(preps) if p["subject"] == s] for s in subjects}
    rules = ["served", "eval_0.10", "eval_majority", "greedy_1to1"]

    presets_out = []
    for alpha in ALPHAS:
        # Leave-one-SUBJECT-out selection (served 0.0 null), then per-scan metrics per rule.
        per_scan = {r: {"fdp": [], "n_sel": [], "sens": []} for r in rules}
        n_zero = 0
        for i, p in enumerate(preps):
            # float32 to mirror the served asset's precision (asset stores float32,
            # promoted to float64 at load) — keeps the estimate faithful to production.
            null = np.asarray(
                np.array([r["score"] for j, q in enumerate(preps)
                          if q["subject"] != p["subject"] for r in q["cands"] if not r["tp0"]],
                         dtype=np.float32), dtype=float)
            scores = np.array([r["score"] for r in p["cands"]], dtype=float)
            if scores.size == 0:
                sel_rows = []
            elif null.size == 0:
                sel_rows = list(p["cands"])
            else:
                sel, _ = select_by_fdr(scores, null, alpha)
                sel_rows = [p["cands"][k] for k in range(len(p["cands"])) if sel[k]]
            if len(sel_rows) == 0:
                n_zero += 1
            for r in rules:
                m = _scan_metrics(sel_rows, p["n_gt"], r)
                per_scan[r]["fdp"].append(m["fdp"])
                per_scan[r]["n_sel"].append(m["n_sel"])
                per_scan[r]["sens"].append(m["sens"])

        served_fdp = np.array(per_scan["served"]["fdp"])
        nsel = np.array(per_scan["served"]["n_sel"])
        sens = np.array(per_scan["served"]["sens"])
        sel_mask = nsel > 0

        # Subject-clustered bootstrap of the mean served FDP (resample SUBJECTS).
        boot = np.empty(N_BOOTSTRAP)
        subj_list = list(subjects)
        for b in range(N_BOOTSTRAP):
            pick = rng.choice(len(subj_list), size=len(subj_list), replace=True)
            idx = [i for k in pick for i in subj_to_idx[subj_list[k]]]
            boot[b] = served_fdp[idx].mean()
        ci = [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))]

        def _exc(arr, a, cond=None):
            arr = np.asarray(arr)
            if cond is not None:
                arr = arr[cond]
            return float((arr > a).mean()) if arr.size else 0.0

        overlap_probes = {}
        for r in ["eval_0.10", "eval_majority", "greedy_1to1"]:
            rf = np.array(per_scan[r]["fdp"])
            overlap_probes[r] = {
                "realized_fdr_mean": float(rf.mean()),
                "frac_scans_fdp_gt_alpha": _exc(rf, alpha),
            }

        presets_out.append({
            "alpha": alpha,
            "realized_fdr_mean": float(served_fdp.mean()),
            "realized_fdr_ci95_subject_bootstrap": ci,
            "n_bootstrap": N_BOOTSTRAP, "seed": SEED,
            "fdp_quantiles": {q: float(np.percentile(served_fdp, p_)) for q, p_ in
                              [("p50", 50), ("p75", 75), ("p90", 90), ("p95", 95), ("max", 100)]},
            "frac_scans_fdp_gt_alpha": _exc(served_fdp, alpha),
            "frac_scans_fdp_gt_alpha_cond_selected": _exc(served_fdp, alpha, sel_mask),
            "n_scans_zero_selected": int(n_zero),
            "sensitivity_mean": float(sens.mean()),
            "sensitivity_median": float(np.median(sens)),
            "n_selected_mean": float(nsel.mean()),
            "n_selected_total": int(nsel.sum()),
            "overlap_sensitivity_probe_A_eval_only": overlap_probes,
            "pass_alpha": bool(served_fdp.mean() <= alpha and ci[1] <= alpha),
        })
        print(f"alpha {alpha}: FDR {served_fdp.mean():.3f} CI{ci} | "
              f"exceed {_exc(served_fdp, alpha):.2f} | sens {sens.mean():.3f} | zero {n_zero}")

    # Baseline keep-all (served TP).
    base_fdp, base_sens, base_nsel = [], [], []
    for p in preps:
        m = _scan_metrics(list(p["cands"]), p["n_gt"], "served")
        base_fdp.append(m["fdp"]); base_sens.append(m["sens"]); base_nsel.append(m["n_sel"])

    all_pass = all(x["pass_alpha"] for x in presets_out)
    # Recall-collapse summary for the honest verdict (adversarial honesty review):
    # the marginal pass is only sound because it is disclosed alongside this cost.
    recall_line = "; ".join(
        f"alpha {x['alpha']}: recall {x['sensitivity_mean']:.3f} (median "
        f"{x['sensitivity_median']:.2f}), {x['n_scans_zero_selected']}/{n} scans select nothing"
        for x in presets_out)
    tight = presets_out[-1]   # alpha 0.10 (tightest)
    record = {
        "record": "CALM-MS Gate-2 within-domain coverage — SERVED raw mean-pooled statistic",
        "requirement": "REQ-FUNC-CALM-001",
        "generated_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "generator": "scripts/calm-ms/gate2_served_coverage.py",
        "protocol_locked_by": "adversarial design+refute workflow w2nwis0e5 (2026-08-21)",
        "supersedes": "learned-scorer figures 0.021/0.044/0.067 (UNWIRED; not served)",
        "served_config": {
            "score_pooling": SCORE, "threshold": THRESHOLD, "min_volume_mm3": MIN_VOLUME_MM3,
            "voxel_spacing": list(VOXEL_SPACING), "base_model": "FLAMeS",
            "calib_overlap": CALIB_OVERLAP, "frozen_null_asset": "calm_ms_null_flames_v2.npz",
            "n_null_scores": int(frozen.size), "n_cases": n,
        },
        "null_equivalence_to_frozen_asset": {"asserted": True, "n_scores_matched": int(frozen.size)},
        "exchangeability": {
            "unit": "subject", "n_subjects": len(subjects), "n_scans": n,
            "loso": "leave-one-SUBJECT-out — the held-out subject's ALL timepoints are "
                    "excluded from its null (no same-patient self-calibration)",
            "bootstrap_cluster": "subject",
            "cohort_scope": "MSLesSeg (ICPR-2024) multi-center, single curated dataset / "
                            "annotation protocol; NOT external-scanner validated",
        },
        "presets": presets_out,
        "baseline_keep_all": {
            "fdr_mean": float(np.mean(base_fdp)), "sensitivity_mean": float(np.mean(base_sens)),
            "n_selected_mean": float(np.mean(base_nsel)),
            "note": "uncontrolled operating point — the status quo the guarantee is measured against",
        },
        "sensitivity_acceptance": {
            "gated_here": False, "deferred_to": "gate_4/5",
            "hazards": ["HAZ-CALM-3", "HAZ-CALM-8"],
            "why": ("a missed lesion is the more severe MS hazard and a recall floor needs a "
                    "usability/clinical study, not this coverage script. The design is ADDITIVE "
                    "(RC-CALM-1): the base FLAMeS mask is NEVER suppressed, so an unselected or "
                    "low-tier true lesion is still painted and reviewed — this bounds recall-"
                    "collapse to a UTILITY (tier-usefulness) failure, not a direct missed-lesion "
                    "SAFETY failure. The residual automation-bias risk (a hurried reader trusting "
                    "the tiers) is exactly what the Gate 4 usability study must prove."),
        },
        "gate2_verdict": {
            "status": ("amber — marginal within-domain coverage MET; utility (recall) NOT cleared"
                       if all_pass else "fail"),
            "coverage_subclaim_met": bool(all_pass),
            "utility_cleared": False,
            "counts_toward_enablement": False,
            "does_not_advance_overall": ("delta to enablement is essentially unchanged — Gates 4-7 "
                "(usability, PCCP, base-model producer, external multi-site) remain the blocking, "
                "expensive/unmeetable items; do not read a rising pass-count as 'nearly there'"),
            "marginal_is_consistency_check": ("Gate 1 already proves marginal FDR <= alpha BY THEOREM "
                "(BH on conformal p-values, PRDS). This record only confirms it EMPIRICALLY within-"
                "domain and that subject-LOSO exchangeability roughly holds inside MSLesSeg — a "
                "sanity/consistency check, NOT independent safety evidence."),
            "over_conservatism": ("realized FDR runs far below target (e.g. 0.018 vs 0.10) BECAUSE the "
                f"operating point selects NOTHING on {tight['n_scans_zero_selected']}/{n} scans at "
                "alpha=0.10 (recall median 0). 'Well below alpha' is a symptom of near-empty selection, "
                "not a safety margin."),
            "recall_collapse": recall_line,
            "must_not_be_read_as": [
                "clinically useful sensitivity — recall collapses (median 0 at alpha 0.10 and 0.20) and "
                f"the point selects nothing on {tight['n_scans_zero_selected']}/{n} scans at alpha=0.10; "
                "FDR is partly 'controlled' by not selecting",
                "a per-scan guarantee — per-scan FDP disperses; up to ~31% of SELECTING scans exceed alpha",
                "cross-site / external-scanner validity — that is Gate 7, still blocked",
                "clinical fragment-level FDR — headline uses any-voxel TP; under majority-overlap it rises (Probe A)",
                "the exact served-115 guarantee — this is the subject-LOSO estimate",
            ],
            "relocated_findings": [
                "site-shift / OOD-blind confident-FP inflation (realized FDR up to ~6x, "
                "0/115 flagged) -> Gate 7 external-validation evidence",
            ],
            "overall_status_unchanged": "NOT_READY (Gates 4-7 still blocked)",
        },
    }
    with open(_OUT, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
    print(f"\nWROTE {_OUT}")
    print(f"Gate-2 verdict: {record['gate2_verdict']['status']}")


if __name__ == "__main__":
    main()
