#!/usr/bin/env python3
"""Extract every number the negative-results manuscript uses from the committed result records.

Reads the records with ``git show <commit>:<path>`` at PINNED commits (no working-tree files, no
network), records the SHA-256 of every source blob, and writes one compact JSON file
(``../data/extracted_results.json``) that ``make_figures.py`` and ``check_numbers.py`` read.

Nothing is recomputed from images or models here: values are copied from the records. The only
arithmetic is (a) sums of compute-ledger rows and (b) differences of recorded candidate counts,
both labelled ``derived`` in the output.

Run from anywhere inside the repository (any worktree). The pinned commits must be present locally:
    git fetch origin research/flames-thick research/lesion-detector-v3 research/cloud-compute-ledger
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "data" / "extracted_results.json"

# ---------------------------------------------------------------- pinned sources
FT_COMMIT = "b19293c48302b93bc6934230ad5ab97627df5362"      # research/flames-thick: results commit
DET_COMMIT = "90797a93611fcc8e2c8275b738bbf5f1b44921bc"     # research/lesion-detector-v3: v3.2 results
LEDGER_COMMIT = "c8b4239b6b5d3b28c089b717f911d34dd36c9c8d"  # research/cloud-compute-ledger

SOURCES = {
    "flames_thick": (FT_COMMIT, "docs/research/records/2026-10-23_flames_thick_results.json"),
    "ft_models": (FT_COMMIT, "docs/research/flames-thick/kaggle/models.json"),
    "v3": (DET_COMMIT, "docs/research/records/2026-10-17_lesion_detector_v3_evaluation.json"),
    "v3_posthoc": (DET_COMMIT, "docs/research/records/2026-10-17_lesion_detector_v3_posthoc_checks.json"),
    "v31": (DET_COMMIT, "docs/research/records/2026-10-21_lesion_detector_v31_evaluation.json"),
    "v31_posthoc": (DET_COMMIT, "docs/research/records/2026-10-21_lesion_detector_v31_posthoc_checks.json"),
    "v32": (DET_COMMIT, "docs/research/records/2026-10-24_lesion_detector_v32_evaluation.json"),
    "v32_independent": (DET_COMMIT, "docs/research/records/2026-10-24_lesion_detector_v32_independent_check.json"),
    "v32_posthoc": (DET_COMMIT, "docs/research/records/2026-10-24_lesion_detector_v32_posthoc_checks.json"),
    "ledger_csv": (LEDGER_COMMIT, "docs/research/compute-ledger/compute_ledger.csv"),
    "kaggle_csv": (LEDGER_COMMIT, "docs/research/compute-ledger/kaggle_runs.csv"),
}

# Pre-registration commits: the protocol file as first committed, before any run or result.
PREREG = {
    "flames_thick": ("5b286f2a105e5f548b80a6ac7766cb47dcc05a13", "docs/research/flames-thick/PROTOCOL.md"),
    "detector_v3": ("59cc7969cac57d44342bad96cd0e16425d2e3c9e", "docs/research/lesion-detector-v3/PROTOCOL.md"),
    "detector_v31": ("129d2ff6efb70d606b3bc899e5d19a9ac41ade0f", "docs/research/lesion-detector-v3/PROTOCOL-v3.1.md"),
    "detector_v32": ("3c2497747f722d64838484c51c92082a2a3a11bc", "docs/research/lesion-detector-v3/PROTOCOL-v3.2.md"),
}
# Commits that first contain the corresponding results.
RESULTS_COMMITS = {
    "flames_thick": "b19293c48302b93bc6934230ad5ab97627df5362",
    "detector_v3": "a5b63081d86c3ba637b3728b0e4660ef9c570e6c",
    "detector_v31": "d451fbb00cf88a89197790846bb967bea2d09e6c",
    "detector_v32": "90797a93611fcc8e2c8275b738bbf5f1b44921bc",
}
# Other commits named in the manuscript (amendments, evaluation code).
OTHER_COMMITS = {
    "ft_kaggle_port": "1539e16198a239c6c36c644db76e5abf194d024c",
    "ft_amendment_kaggle_pilot": "73e9651466a85447c36f3c6d1bffb48f0eed7615",
    "ft_amendment_early_look": "aba9a54e98ea90c85fe062c40b75640417053337",
    "ft_training_done": "c4fd2e588db88efede0b353cd3af73265901fcf2",
    "v3_eval_code": "6840ef390c08082e4ed6ab714f37bbb06a89b71e",
    "v3_deviations_d1_d2": "ed3c858cb6f27645d993b39aaf408cab2b0c50bc",
    "v3_deviations_d3_d4": "b87f2672bd44ab230f639fdfe1c32873043b2f7d",
    "v31_eval_code": "0d339b1ea4c4a5747658a2546199661dd82236e2",
    "v32_eval_code_d1": "6606cc6ef44bfbe7adc68b68645c7ab3ca7695a3",
}

# Evidence of when commits first became public on GitHub. Not derivable offline from git objects,
# so recorded here with its source. The raw API responses are archived in
# ../data/github_timing_evidence_2026-10-31.json (the events endpoint keeps only ~90 days).
# Queried 2026-10-31 (GitHub REST API: pull-request metadata and repository events) and
# cross-checked against the local reflog of refs/remotes/origin/* ("update by push" entries).
# Entries marked author_side come only from the local reflog (no GitHub event was returned).
PUBLIC_PUSH_EVIDENCE = [
    {"event": "PR #55 opened (branch research/lesion-detector-v3 first public; contains the v3 and v3.1 "
              "protocols AND their results, commits up to d451fbb)", "utc": "2026-10-21T03:14:13Z",
     "source": "GitHub API pulls/55 createdAt; local reflog push of d451fbb at 2026-10-21T03:13:56Z"},
    {"event": "PR #56 opened (branch research/flames-thick first public; contains protocol 5b286f2)",
     "utc": "2026-10-21T05:08:35Z", "source": "GitHub API pulls/56 createdAt; local reflog push of 76adbcc "
                                               "at 2026-10-21T05:08:18Z"},
    {"event": "push 73e9651 (FLAMeS-thick amendments: Kaggle platform, epoch rule, pilot criterion)",
     "utc": "2026-10-21T17:19:42Z", "source": "GitHub API events (PushEvent)"},
    {"event": "push aba9a54 (FLAMeS-thick early look passed, E = 300 kept)", "utc": "2026-10-21T18:40:54Z",
     "source": "GitHub API events (PushEvent)"},
    {"event": "push c4fd2e5 (FLAMeS-thick training finished; model hashes)", "utc": "2026-10-22T23:34:09Z",
     "source": "local reflog of refs/remotes/origin/research/flames-thick", "author_side": True},
    {"event": "push b19293c (FLAMeS-thick results)", "utc": "2026-10-23T10:10:02Z",
     "source": "local reflog of refs/remotes/origin/research/flames-thick", "author_side": True},
    {"event": "push 3c24977 (detector v3.2 protocol)", "utc": "2026-10-24T16:26:06Z",
     "source": "GitHub API events (PushEvent); local reflog 16:26:05Z"},
    {"event": "push 6606cc6 (detector v3.2 evaluation code + deviation D1)", "utc": "2026-10-24T16:38:27Z",
     "source": "GitHub API events (PushEvent)"},
    {"event": "push 90797a9 (detector v3.2 results)", "utc": "2026-10-24T17:03:01Z",
     "source": "GitHub API events (PushEvent)"},
]

# Compute-ledger rows whose maps the two studies consumed but that also served other studies.
SHARED_UPSTREAM_RUNS = ["flames-full-a", "flames-full-b", "flames-full-c", "flames-extra-pilot",
                        "flames-extra-a", "flames-extra-b", "lstai-full-a", "lstai-ctl",
                        "sibbms-ctl-pilot", "sibbms-ctl-a", "sibbms-ctl-b", "sibbms-ctl-c"]
FT_EVAL_RUNS = ["flames-thick-eval-pilot", "flames-thick-eval-1", "flames-thick-eval-2"]
FT_KAGGLE_STUDY = ["kaggle-full-s1", "kaggle-full-s2", "kaggle-full-s3"]
FT_KAGGLE_ALL = ["kaggle-smoke-s1", "kaggle-smoke-s2", "kaggle-pilot-s1", "kaggle-pilot-s2"] + FT_KAGGLE_STUDY


def repo_root() -> Path:
    out = subprocess.run(["git", "-C", str(HERE), "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True, encoding="utf-8", check=True)
    return Path(out.stdout.strip())


ROOT = repo_root()


def git_blob(commit: str, path: str) -> bytes:
    res = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{path}"], capture_output=True)
    if res.returncode != 0:
        sys.exit(f"cannot read {commit[:7]}:{path} - fetch the research branches first\n"
                 f"{res.stderr.decode(errors='replace')}")
    return res.stdout


def git_commit_info(commit: str) -> dict:
    fmt = "%H%n%cI%n%aI%n%s"
    res = subprocess.run(["git", "-C", str(ROOT), "log", "-1", f"--format={fmt}", commit],
                         capture_output=True, text=True, encoding="utf-8", check=True)
    full, committed, authored, subject = res.stdout.strip().split("\n", 3)
    return {"commit": full, "committer_date": committed, "author_date": authored, "subject": subject}


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def pick(d: dict, keys):
    return {k: d[k] for k in keys if k in d}


def main() -> None:
    provenance, raw = {}, {}
    for name, (commit, path) in SOURCES.items():
        blob = git_blob(commit, path)
        provenance[name] = {"commit": commit, "path": path, "sha256": sha256(blob), "bytes": len(blob)}
        raw[name] = blob

    ft = json.loads(raw["flames_thick"])
    models = json.loads(raw["ft_models"])
    v3 = json.loads(raw["v3"])
    v3p = json.loads(raw["v3_posthoc"])
    v31 = json.loads(raw["v31"])
    v31p = json.loads(raw["v31_posthoc"])
    v32 = json.loads(raw["v32"])
    v32i = json.loads(raw["v32_independent"])
    v32p = json.loads(raw["v32_posthoc"])

    out: dict = {"_about": __doc__.strip().splitlines()[0], "provenance": provenance}

    # ------------------------------------------------------------ study 1: FLAMeS-thick
    ft_keys = ["H1", "H1_by_site", "H2", "S6_strict", "S6_without_pedims_P9", "S3_A_vs_B",
               "S4_A_vs_E", "B_vs_R_thick", "S1_size", "S2_by_site", "S5_mslesseg_by_native_thickness",
               "counts", "n_scans"]
    out["flames_thick"] = pick(ft, ft_keys)
    per_scan = []
    for s in ft["per_scan"]:
        row = {"case": s["case"], "site": s["site"], "patient": s["patient"], "band": s["band"],
               "slice_mm": s["slice_mm"]}
        for arm, m in s["arms"].items():
            row[arm] = {k: m[k] for k in ("f1", "dice", "fp", "tp", "fn", "sens", "prec") if k in m}
        per_scan.append(row)
    out["flames_thick"]["per_scan"] = per_scan
    out["flames_thick_models"] = {
        arm: {"sha256_model_tar_gz": m["model_tar_gz"]["sha256"], "bytes": m["model_tar_gz"]["bytes"],
              "epochs": m["epochs"], "median_s_per_epoch": m.get("median_s_per_epoch"),
              "internal_validation_dice": m.get("internal_validation_final", {}).get("dice_mean_15_scans"),
              "pseudo_dice_first_last": m.get("pseudo_dice_first_last"),
              "flames_fold0_sha256": m.get("flames_fold0_sha256"),
              "sessions": m.get("sessions")}
        for arm, m in models["models"].items()}

    # ------------------------------------------------------------ study 2: detector v3 / v3.1 / v3.2
    out["v3"] = {
        "reproduction_gate": v3["reproduction_gate"], "base_rates": v3["base_rates"],
        "primary_pooled_loco": v3["primary_pooled_loco"], "primary_criterion": v3["primary_criterion"],
        "S2_loco_per_direction": v3["S2_loco_per_direction"], "S1_within_cohort": v3["S1_within_cohort"],
        "S5_controls_auroc": v3["S5_controls"]["auroc_L10true_vs_control"],
        "A1_shuffle_null": v3["A1_shuffle_null"], "A3_site_identity_auroc": v3["A3_site_identity_auroc"],
        "A5_small_n": v3["A5_small_n"], "A4_label_definitions": v3["A4_label_definitions"],
        "runtime_s": v3.get("runtime_s"), "feature_sets_sizes": {k: len(v) for k, v in v3["feature_sets"].items()},
        "posthoc_P1_same_model": v3p["P1_v3_minus_v2_same_model"],
        "posthoc_P2_direction_A_refits": v3p["P2_direction_A_refit_variance"],
    }
    out["v31"] = {
        "gate_and_descriptives": v31["gate_and_descriptives"],
        "primary_pooled_external": v31["primary_pooled_external"], "criteria": v31["criteria"],
        "S_per_site_external": v31["S_per_site_external"],
        "H4_site_signature_M_vs_L10": v31["H4_site_signature_M_vs_L10"],
        "H4b_site_signature_M_vs_new_sites": v31["H4b_site_signature_M_vs_new_sites"],
        "B1_shuffle_null": v31["B1_shuffle_null_external"], "B6_contamination": v31["B6_contamination"],
        "S_M_L10_not_confirmatory": v31["S_M_L10_not_confirmatory"], "B5_refit_variance_external": v31["B5_refit_variance_external"],
        "runtime_s": v31.get("runtime_s"),
        "posthoc_P1_mean5": v31p["P1_mean5_candidates"],
        "posthoc_P2_counts": v31p["P2_candidates_fold0_vs_mean5"],
        "posthoc_runtime_s": v31p.get("runtime_s"),
    }
    # derived: what the ensemble's candidate generation alone removes at the external sites
    p2 = v31p["P2_candidates_fold0_vs_mean5"]
    ext = ["ms3seg", "muslim", "pedims"]
    f0_false = sum(p2[s]["fold0"]["false"] for s in ext)
    m5_false = sum(p2[s]["mean5"]["false"] for s in ext)
    f0_true = sum(p2[s]["fold0"]["true"] for s in ext)
    m5_true = sum(p2[s]["mean5"]["true"] for s in ext)
    out["v31"]["derived_external_candidate_counts"] = {
        "fold0_false": f0_false, "mean5_false": m5_false, "fold0_true": f0_true, "mean5_true": m5_true,
        "false_removed": f0_false - m5_false, "true_removed": f0_true - m5_true,
        "false_removed_share": round((f0_false - m5_false) / f0_false, 4),
        "true_removed_share": round((f0_true - m5_true) / f0_true, 4),
        "note": "derived: sums/differences of the recorded P2 counts (v3.1 post-hoc record)"}

    hk = v32["K2_cohort_identity_probe"]
    out["v32"] = {
        "descriptives": v32["descriptives"], "gate_V1": v32["gate_V1"],
        "H1": v32["H1_primary_ms_true_vs_controls"],
        "H3": v32["H3_false_per_control_at_90pct_sensitivity"],
        "H4_external_pooled": v32["H4_external_pooled"],
        "H4_external_deployable_operating_point": v32["H4_external_deployable_operating_point"],
        "S2_1mm": v32["S2_1mm"], "S_CAL": v32["S_CAL_healthy_calibrated_threshold"],
        "K2": {k: {"pooled": {f: v for f, v in hk[k].items() if not f.startswith("_")},
                   "foldwise": hk[k].get("_foldwise_D1"), "n": hk[k].get("_n")} for k in hk},
        "K3": v32["K3_transfer"], "K10": v32["K10_H1_foldwise_D1"], "K5": v32["K5_shuffle_null"],
        "K7": v32["K7_bootstrap_seeds"], "K9": v32["K9_without_sub075"], "K8": v32["K8_blindness_split"],
        "criteria": v32["criteria"], "decisions": v32["decisions"], "runtime_s": v32.get("runtime_s"),
        "K6_independent_check": v32i, "posthoc": v32p,
    }

    # ------------------------------------------------------------ compute ledger
    rows = list(csv.DictReader(io.StringIO(raw["ledger_csv"].decode("utf-8"))))
    by_id = {r["run_id"]: r for r in rows}
    krows = list(csv.DictReader(io.StringIO(raw["kaggle_csv"].decode("utf-8"))))
    kby = {r["run_id"]: r for r in krows}

    def ledger_rows(ids):
        sel = []
        for i in ids:
            r = by_id[i]
            sel.append({"run_id": i, "date_utc": r["date_utc"], "machine_type": r["machine_type"],
                        "provisioning": r["provisioning"], "start_utc": r["start_utc"], "end_utc": r["end_utc"],
                        "vm_hours": float(r["vm_hours"]), "cost_usd_list": float(r["cost_usd_list"]),
                        "items_ok": r["items_ok"], "items_failed": r["items_failed"],
                        "price_basis": r["price_basis"], "purpose": r["purpose"]})
        return sel

    ft_eval = ledger_rows(FT_EVAL_RUNS)
    shared = ledger_rows(SHARED_UPSTREAM_RUNS)
    kag = [{"run_id": i, "start_utc": kby[i]["start_utc"], "end_utc": kby[i]["end_utc"],
            "quota_hours": float(kby[i]["gpu_hours"]), "gpu": kby[i]["gpu"], "epochs": kby[i]["epochs"],
            "median_s_per_epoch": kby[i]["median_seconds_per_epoch"]} for i in FT_KAGGLE_ALL]
    project_rows = [r for r in rows if r["project"] == "mstool-research" and r["cost_usd_list"]]
    out["compute"] = {
        "ledger_commit": LEDGER_COMMIT,
        "flames_thick_eval_runs": ft_eval,
        "flames_thick_eval_cost_usd_list": round(sum(r["cost_usd_list"] for r in ft_eval), 4),
        "flames_thick_eval_vm_hours": round(sum(r["vm_hours"] for r in ft_eval), 4),
        "kaggle_sessions": kag,
        "kaggle_quota_hours_all": round(sum(r["quota_hours"] for r in kag), 3),
        "kaggle_quota_hours_study": round(sum(r["quota_hours"] for r in kag if r["run_id"] in FT_KAGGLE_STUDY), 3),
        "kaggle_cost_usd": 0.0,
        "shared_upstream_runs": shared,
        "shared_upstream_cost_usd_list": round(sum(r["cost_usd_list"] for r in shared), 4),
        "shared_upstream_vm_hours": round(sum(r["vm_hours"] for r in shared), 4),
        "research_project_total_cost_usd_list": round(sum(float(r["cost_usd_list"]) for r in project_rows), 4),
        "research_project_total_vm_hours": round(sum(float(r["vm_hours"]) for r in project_rows if r["vm_hours"]), 2),
        "note": "derived: sums of ledger rows (list price, cores + RAM + boot disk; storage/network excluded)",
    }

    # ------------------------------------------------------------ pre-registration evidence
    prereg = {}
    for name, (commit, path) in PREREG.items():
        blob = git_blob(commit, path)
        info = git_commit_info(commit)
        res = git_commit_info(RESULTS_COMMITS[name])
        anc = subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", commit,
                              RESULTS_COMMITS[name]]).returncode == 0
        prereg[name] = {"protocol_path": path, "protocol_sha256_at_preregistration": sha256(blob),
                        "preregistration": info, "results": res, "protocol_is_ancestor_of_results": anc}
    out["preregistration"] = prereg
    out["other_commits"] = {k: git_commit_info(c) for k, c in OTHER_COMMITS.items()}
    out["public_push_evidence"] = PUBLIC_PUSH_EVIDENCE

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size} bytes)")
    for name, p in provenance.items():
        print(f"  {name:16s} {p['commit'][:7]}:{p['path']}  sha256 {p['sha256'][:16]}...")


if __name__ == "__main__":
    main()
