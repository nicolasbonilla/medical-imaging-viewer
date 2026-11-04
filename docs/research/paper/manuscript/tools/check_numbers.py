#!/usr/bin/env python3
"""Paper A manuscript — trace every number in the text to its stored source and write NUMBERS_CHECK.md.

Revision 2 (2026-11-04): compares against the FULL-PRECISION records (`*_fullprec.json`,
`*_revision*.json`), so a value printed from an already-rounded number (double rounding) is caught.

For each claim: (1) the snippet must occur in manuscript.md (whitespace-normalised); (2) the numbers in
the snippet are compared, in order, with the values read from the committed records (or derived from
them by the stated formula). A number passes when |written − stored| ≤ half a unit of its last
written digit AND equals round-half-up of the full-precision value; it is flagged ROUNDING when it is
within half a unit but not the half-up value (that is a FAIL-level slip in this revision: exit 1).
Tables are checked by regenerating them (make_tables.py --check). Design constants and historical
statements are checked as phrases in the protocol / source documents. Git commits and dates are
checked with git; public-remote times against the stored GitHub-events record.

    python docs/research/paper/manuscript/tools/check_numbers.py      (exit 1 on any FAIL or ROUNDING)
"""
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from decimal import ROUND_HALF_UP, Decimal

from scipy.stats import beta, binom, fisher_exact

HERE = os.path.dirname(os.path.abspath(__file__))
MS_DIR = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(MS_DIR, "..", "..", "..", ".."))
REC = os.path.join(ROOT, "docs", "research", "records")
PAPER = os.path.join(ROOT, "docs", "research", "paper")
OUT = os.path.join(MS_DIR, "NUMBERS_CHECK.md")

F = {"R": "2026-10-31_paper_a_v03_results_fullprec.json", "PH": "2026-10-31_paper_a_v03_posthoc_fullprec.json",
     "C": "2026-10-24_paper_a_v03c_controls.json", "M": "2026-10-31_paper_a_manuscript_posthoc_fullprec.json",
     "N": "2026-10-31_paper_a_v03_mslesseg_native_fullprec.json", "CAL": "2026-10-24_paper_a_v03c_calibration.json",
     "G": "2026-10-21_paper_a_v03_candidates.json", "EV": "2026-10-31_paper_a_github_push_events.json",
     "V": "2026-10-31_paper_a_revision.json", "VX": "2026-10-31_paper_a_revision_extra.json",
     "FC": "2026-10-31_paper_a_fullprec_check.json"}
D = {k: json.load(open(os.path.join(REC, v), encoding="utf-8")) for k, v in F.items()}
R, PH, C, M, N, CAL, G, EV, V, VX, FC = (D[k] for k in ("R", "PH", "C", "M", "N", "CAL", "G", "EV", "V", "VX", "FC"))
DOCS = {"PROTOCOL": open(os.path.join(PAPER, "PROTOCOL-v0.3.md"), encoding="utf-8").read(),
        "ADDENDUM": open(os.path.join(PAPER, "PROTOCOL-v0.3-addendum-controls.md"), encoding="utf-8").read(),
        "RESULTS": open(os.path.join(PAPER, "RESULTS-v0.3.md"), encoding="utf-8").read(),
        "DRAFT": open(os.path.join(PAPER, "manuscript-draft.md"), encoding="utf-8").read()}
MS = open(os.path.join(MS_DIR, "manuscript.md"), encoding="utf-8").read()


def norm(s):
    return re.sub(r"\s+", " ", s)


MSN = norm(MS)


def git(*args):
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True, encoding="utf-8", check=True).stdout


def git_doc(ref, path):
    return git("show", f"{ref}:{path}")


DOCS["COHORTS"] = git_doc("research/cohorts-extra", "docs/research/cohorts-extra.md")
DOCS["V31PROT"] = git_doc("129d2ff", "docs/research/lesion-detector-v3/PROTOCOL-v3.1.md")
DOCS["NEXTJOBS"] = git_doc("research/cloud-compute-ledger", "docs/research/compute-ledger/NEXT_JOBS.md")
DOCS["SRS_MAIN"] = git_doc("main", "docs/iec62304/02_Software_Requirements_Specification.md")
DOCS["RMF_MAIN"] = git_doc("main", "docs/iec62304/03_Risk_Management_File.md")
DOCS["ASSET_MAIN"] = git_doc("main", "frontend/src/config/sliceThicknessReliability.v2.json")
DOCS["FEATURES_MAIN"] = git_doc("main", "frontend/src/config/features.ts")


# ------------------------------------------------------------------ accessors
def cell(d, s, p, t):
    for c in R["primary"]:
        if (c["design"], c["site"], c["procedure"], c["target"]) == (d, s, p, t):
            return c
    raise KeyError((d, s, p, t))


def vc(d, s, p, t):
    return V["cells"][f"{d}|{s}|{p}|{t}"]


def dsg(arm_design, pt, site):
    return R["designs"][arm_design][pt][site]


def paired(k):
    return R["q3"]["paired_ens_minus_f0"][k]


def q4(site, k):
    return R["q4"][site]["cells"][k]


def mc(site, k):
    return V["d5_mc"][site][k]


def op(k, sub="all100"):
    return C["operating_points"][f"{k}|{sub}"]


def dis(k):
    return C["app_dis"]["results"][k]


def est_ci(c):
    return [c["estimate"], c["ci95"][0], c["ci95"][1]]


def pct(x):
    return [100 * v for v in x]


def git_blob_sha(commit, path):
    blob = subprocess.run(["git", "-C", ROOT, "show", f"{commit}:{path}"], capture_output=True, check=True).stdout
    return hashlib.sha256(blob).hexdigest()


def git_time(commit):
    return git("show", "-s", "--format=%ci", commit).strip()


def event(head_prefix=None, typ="PushEvent", ref=None):
    for e in EV["events"]:
        if e["type"] == typ and (head_prefix is None or (e["head"] or "").startswith(head_prefix)) \
                and (ref is None or ref in (e["ref"] or "")):
            return e
    return None


def cp_upper_one_sided(x, n, conf=0.95):
    return 1.0 if x >= n else beta.ppf(conf, x + 1, n - x)


SITES = ("mslesseg", "openms", "ms3seg", "muslim", "pedims")
DESC = {s: R["descriptive"][f"ens|{s}"] for s in SITES}
AUC = R["q3"]["auroc"]
FOLD_AUC = [AUC[f"f{k}|{s}"]["auroc"] for s in SITES for k in range(5)]
ENS_AUC = [AUC[f"ens_mean|{s}"]["auroc"] for s in SITES]
SD_AUC = [AUC[f"ens_neg_fold_sd|{s}"]["auroc"] for s in SITES]
P1CELLS = [c for c in R["primary"] if c["procedure"] == "P1"]
P1V = {k: v for k, v in V["cells"].items() if k.split("|")[2] == "P1" and k.split("|")[0] in ("D3", "D2")}
SB = R["thickness"]["size_bins"]
BB = R["thickness"]["D2|by_band"]
SUBD = M["B_baselines"]
ROWS = C["location_rows_ens"]
FR = V["frontier_d3"]
SIM = V["simulation"]["scenarios"]
PA = V["paired_auroc"]
RAT = V["ratio_d3_over_d1"]


def hb_class_counts():
    out = {"holds": 0, "inconclusive": 0, "not estimable": 0, "violated": 0}
    for k, v in P1V.items():
        d, s, p, t = k.split("|")
        t = float(t)
        pre = cell(d, s, p, t)
        if v["bootstrap_degenerate"]:
            out["not estimable"] += 1
        elif pre["ci95"][0] > t:
            out["violated"] += 1
        elif v["realised_fdr_ucb95_hb_patients"] <= t + 0.05:
            out["holds"] += 1
        else:
            out["inconclusive"] += 1
    return out


def pooled_cons_sens():
    tot = sum(DESC[s]["gt_detectable"] for s in ("ms3seg", "muslim", "pedims"))
    return sum(R["sensitivity"][f"consensus_score|D3|{s}|P1|0.2"]["sens_e2e"] * DESC[s]["gt_detectable"]
               for s in ("ms3seg", "muslim", "pedims")) / tot


def share_ge95(sites, arm="ens"):
    num = sum(PH[f"{arm}|{s}"]["false_candidates_score_ge_0.95"] * PH[f"{arm}|{s}"]["false_candidates"] for s in sites)
    return num / sum(PH[f"{arm}|{s}"]["false_candidates"] for s in sites)


def site_bins(sites, idxs):
    return [SB[f"site:{s}|D2|P1|0.2"]["sens_raw"][i] for s in sites for i in idxs]


CL = []


def c(section, snippet, source, path, getter, kind="num"):
    CL.append((section, snippet, source, path, getter, kind))


# ================================================================== Abstract
c("Abstract", "five public patient cohorts (304 scans, 245 patients) and 100 healthy controls", "R, C",
  "Σ descriptive scans / patients; controls primary n",
  lambda: [5, sum(DESC[s]["scans"] for s in SITES), sum(DESC[s]["patients"] for s in SITES), C["primary"]["P1|0.1"]["n"]], "word:5")
c("Abstract", "native 2D acquisitions with 3.9–8.3 mm slice spacing", "R", "site_info notes ('3.9 mm' PediMS; '8.3 mm' Muslim)",
  lambda: [2, 3.9 if "3.9 mm" in R["site_info"]["pedims"]["note"] else None, 8.3 if "8.3 mm" in R["site_info"]["muslim"]["note"] else None])
c("Abstract", "committed to the project's git repository 38 minutes before the first results", "git", "time(8a420bc) − time(9951494)",
  lambda: [round((int(git("show", "-s", "--format=%ct", "8a420bc")) - int(git("show", "-s", "--format=%ct", "9951494"))) / 60)])
c("Abstract", "P(FDP > γ) ≤ δ = 0.1", "PROTOCOL", "δ = 0.1 (protocol §5)", lambda: [0.1])
c("Abstract", "at α = 0.1 the data do not exclude a realised FDR of 1.4α (MS3SEG) and 1.8α (Muslim)", "V",
  "cells D3 P1 0.1 realised_fdr_ucb95_boot / α",
  lambda: [0.1, vc("D3", "ms3seg", "P1", 0.1)["realised_fdr_ucb95_boot"] / 0.1, vc("D3", "muslim", "P1", 0.1)["realised_fdr_ucb95_boot"] / 0.1])
c("Abstract", "under P1 at α = 0.1, 34 % of MS3SEG scans had a false-discovery proportion above 0.1, and the Muslim scans with any reported lesion had a mean proportion of 0.188",
  "V", "cells D3|ms3seg|P1|0.1 share_fdp_gt_0.1 ×100; D3|muslim|P1|0.1 fdr_among_selecting",
  lambda: [0.1, 100 * vc("D3", "ms3seg", "P1", 0.1)["share_fdp_gt_0.1"], 0.1, vc("D3", "muslim", "P1", 0.1)["fdr_among_selecting"]])
c("Abstract", "the realised FDR at α = 0.1 was 2.6 (95 % CI 1.3–7.1) and 3.2 (1.2–25.6) times its within-cohort value", "V",
  "ratio_d3_over_d1 ms3seg|0.1, muslim|0.1 ratio and CI",
  lambda: [0.1, RAT["ms3seg|0.1"]["ratio"], 95, *RAT["ms3seg|0.1"]["ratio_ci95_paired_bootstrap"], RAT["muslim|0.1"]["ratio"], *RAT["muslim|0.1"]["ratio_ci95_paired_bootstrap"]])
c("Abstract", "P2 let 21 % [13, 30] and 29 % [17, 44] of thick-slice scans exceed γ = 0.1, against 10 %", "R", "primary D3 P2 0.1 ×100",
  lambda: [*pct(est_ci(cell("D3", "ms3seg", "P2", 0.1))), *pct(est_ci(cell("D3", "muslim", "P2", 0.1))), 0.1, 10])
c("Abstract", "it needs at least 9 calibration patients by construction, and with 10 local patients it was valid on average but found 4.0 % and 0.7 % of lesions",
  "derived, V", "smallest K with ⌈(K+1)(1−δ)⌉ ≤ K; d5_mc site_only|P2|0.1|k=10 sens ×100",
  lambda: [min(K for K in range(1, 50) if math.ceil((K + 1) * 0.9 - 1e-12) <= K), 10,
           100 * mc("ms3seg", "site_only|P2|0.1|k=10")["sens_mean"], 100 * mc("muslim", "site_only|P2|0.1|k=10")["sens_mean"]])
c("Abstract", "Averaging the five folds doubled sensitivity at α = 0.2 (0.102 → 0.203)", "R", "paired D2|ALL|P1|0.2 sens b, a",
  lambda: [0.2, paired("D2|ALL|P1|0.2")["sens_e2e"]["b"], paired("D2|ALL|P1|0.2")["sens_e2e"]["a"]])
c("Abstract", "(0.051 → 0.122 at α = 0.1)", "R", "paired D3|muslim|P1|0.1 mean_fdp b, a",
  lambda: [paired("D3|muslim|P1|0.1")["mean_fdp"]["b"], paired("D3|muslim|P1|0.1")["mean_fdp"]["a"], 0.1])
c("Abstract", "reported a lesion in 14/100 (α = 0.1) and 24/100 (α = 0.2) controls", "C", "primary P1|0.1, P1|0.2",
  lambda: [C["primary"]["P1|0.1"]["scans_with_any"], 100, 0.1, C["primary"]["P1|0.2"]["scans_with_any"], 100, 0.2])
c("Abstract", "marked a lesion in 85/100 and met a brain dissemination-in-space rule in 19/100", "C", "raw_candidates.ens; app_dis raw ens",
  lambda: [C["raw_candidates"]["ens"]["scans_with_any_candidate"], 100, dis("raw ens|all100")["dis_met_brain"], 100])

# ================================================================== Methods (git, events, protocol phrases)
c("§5.1", "committed on 2026-10-21 at 04:21 CEST (commit 9951494)", "git", "commit time",
  lambda: [git_time("9951494").startswith("2026-10-21 04:21") and git_time("9951494").endswith("+0200")], "bool")
c("§5.1", "1b5b39a8e5cc3c3af6cfce22d64c16832e0ccc71dbaf5ba35b11db15b93c6016", "git", "sha256(git show 9951494:PROTOCOL-v0.3.md)",
  lambda: [git_blob_sha("9951494", "docs/research/paper/PROTOCOL-v0.3.md") == "1b5b39a8e5cc3c3af6cfce22d64c16832e0ccc71dbaf5ba35b11db15b93c6016"], "bool")
c("§5.1", "(commit c0c5fa1, 04:35)", "git", "commit time and files (metric functions, tests, candidate code)",
  lambda: [git_time("c0c5fa1")[11:16] == "04:35" and "research/paper_a/v03_metrics.py" in git("show", "--name-only", "--format=", "c0c5fa1")], "bool")
c("§5.1", "(commit 50c9b08, 04:41)", "git", "commit time", lambda: [git_time("50c9b08")[11:16] == "04:41"], "bool")
c("§5.1", "The analysis script itself was committed only together with the first results, at 04:59 (8a420bc), 38 minutes after the protocol", "git",
  "8a420bc time and files include v03_analysis.py and the results record; minutes since 9951494",
  lambda: [git_time("8a420bc")[11:16] == "04:59" and "research/paper_a/v03_analysis.py" in git("show", "--name-only", "--format=", "8a420bc")
           and round((int(git("show", "-s", "--format=%ct", "8a420bc")) - int(git("show", "-s", "--format=%ct", "9951494"))) / 60) == 38], "bool")
c("§5.1", "committed on 2026-10-24 at 15:52 CEST (commit caa47e7", "git", "commit time", lambda: [git_time("caa47e7").startswith("2026-10-24 15:52")], "bool")
c("§5.1", "bdae74ec6373daa0685c49cc4f57fed73445716b92d469d9658cede764f87213", "git", "sha256 of the addendum at caa47e7",
  lambda: [git_blob_sha("caa47e7", "docs/research/paper/PROTOCOL-v0.3-addendum-controls.md") == "bdae74ec6373daa0685c49cc4f57fed73445716b92d469d9658cede764f87213"], "bool")
c("§5.1", "only at 05:09 CEST on 2026-10-21, together with the first results", "EV", "CreateEvent research/paper-a-v0.3",
  lambda: [event(typ="CreateEvent", ref="paper-a-v0.3")["created_at"].startswith("2026-10-21T03:09")], "bool")
c("§5.1", "pushed to the public remote at 13:52:31 UTC on 2026-10-24, 71 minutes before its results (15:03:30 UTC)", "EV",
  "PushEvent caa47e7 / 413f5b5", lambda: [event("caa47e7")["created_at"] == "2026-10-24T13:52:31Z" and event("413f5b5")["created_at"] == "2026-10-24T15:03:30Z"], "bool")
c("§5.1", "(\"lesion-detector v3.1\": protocol commit 129d2ff at 04:14, evaluation code 0d339b1 at 04:24, results d451fbb at 05:13 CEST)", "git",
  "commit times on branch research/lesion-detector-v3",
  lambda: [git_time("129d2ff")[11:16] == "04:14" and git_time("0d339b1")[11:16] == "04:24" and git_time("d451fbb")[11:16] == "05:13"
           and git_time("d451fbb").startswith("2026-10-21")], "bool")
c("§5.1", "this study's first text revision (0731145, 05:30)", "git", "commit time", lambda: [git_time("0731145")[11:16] == "05:30"], "bool")
DOCCLAIMS = [
    ("§3.1", "18-connected component of {p ≥ 0.5} whose physical volume is at least 3 mm³", "PROTOCOL", ["18-connected component of {p ≥ 0.5}", "volume ≥ 3 mm³"]),
    ("§3.1", "*Clinical* lesions are those of at least 14.14 mm³ (a sphere of 3 mm diameter)", "PROTOCOL", ["≥ 14.14 mm³ (3-mm-diameter sphere)"]),
    ("§3.1", "lenient (IoU > 0); a strict variant (IoU ≥ 0.10)", "PROTOCOL", ["(IoU > 0)", "(IoU ≥ 0.10)"]),
    ("§3.2", "on the grid {0, 0.001, …, 1, ∞}", "PROTOCOL", ["λ ∈ {0, 0.001, …, 1, ∞}"]),
    ("§3.2", "λ̂ is the ⌈(K + 1)(1 − δ)⌉-th smallest t_i", "PROTOCOL", ["⌈(K+1)(1−δ)⌉-th smallest t_i"]),
    ("§3.2", "with probability at least 0.9 over the calibration draw", "PROTOCOL", ["Hoeffding–Bentkus, δ = 0.1"]),
    ("§5.3", "(k ∈ {1, 2, 3, 5, 10, 20, 40}, 200 draws each)", "PROTOCOL", ["k ∈ {1, 2, 3, 5, 10, 20, 40}", "R = 200 draws per k"]),
    ("§5.4", "The **32 primary cells**", "PROTOCOL", ["32 primary cells"]),
    ("§5.4", "The expectation of about 0.8 spurious one-sided \"violations\" among 32 cells", "PROTOCOL", ["~0.8 spurious one-sided 2.5 %"]),
    ("§5.4", "*holds* if the upper bound is at most nominal + 0.05", "PROTOCOL", ["margin 0.05 absolute"]),
    ("§5.4", "fewer than 10 selections or end-to-end sensitivity below 0.05", "PROTOCOL", ["< 10 selections in total or end-to-end sensitivity < 0.05"]),
    ("§5.4", "the mean power is at least 90 % of within-site power", "PROTOCOL", ["mean power ≥ 0.9 × the D1 power"]),
    ("§5.4", "(level 1 − 0.05/32, 20 000 resamples)", "PROTOCOL", ["(level 1 − 0.05/32)", "use 20 000 bootstrap resamples"]),
    ("§4.1", "HD-BET 2.0.1", "ADDENDUM", ["HD-BET v2.0.1"]),
    ("§5.2", "the maximum decoding error is about 0.002", "ADDENDUM", ["max decoding error ≈ 0.002"]),
    ("§4.2", "FLAMeS was trained on 668 FLAIR scans of people with MS", "ADDENDUM", ["668 FLAIR scans from 11 sources", "all described as people with MS"]),
    ("§4.2", "20 ISBI-2015 scans [@carass2017longitudinal], 20 Ljubljana scans (listed as PubMRI)", "ADDENDUM", ["ISBI-2015 20, PubMRI (= Ljubljana) 20"]),
    ("§4.2", "53 MSSEG-2016 cases from centres 01, 03, 07 and 08", "ADDENDUM", ["MSSEG-1 centres 01/03/07/08 (15/8/15/15)"]),
    ("§4.2", "brain bounding box of all 668 training cases", "ADDENDUM", ["exactly 668 entries"]),
    ("§4.2", "Ljubljana patients 01–15 and 21–25 exactly", "PROTOCOL", ["patients 01–15, 21–25 are FLAMeS training data"]),
    ("§4.2", "each fold trains on four fifths of the cases", "DRAFT", ["each fold trains on 4/5 of the cases"]),
    ("§4.2", "none of the 668 training cases has a voxel spacing of 3 mm or more on any axis", "V31PROT", ["no case with any spacing ≥ 3 mm"]),
    ("§4.1", "MS3SEG slices are 4.7–6.9 mm thick with a 0.7–2.1 mm gap (spacing 6.0–8.1 mm)", "COHORTS", ["slice thickness 4.7–6.9 mm + gap 0.7–2.1 mm", "6.0–8.1"]),
    ("§4.1", "Muslim slices are 3–6 mm thick with a spacing of 4.86–8.3 mm", "COHORTS", ["4.86–8.3 mm,", "thickness 3–6 mm"]),
    ("§4.1", "The Muslim dataset has 60 patients from about 20 centres", "COHORTS", ["all 60", "~20 centres"]),
    ("§4.1", "We used the 51 axial FLAIR scans; 6 coronal and 3 sagittal scans were not used", "COHORTS", ["**51** axial (+6 coronal, +3 sagittal optional)"]),
    ("§4.1", "We estimated it per scan (0.41–0.97 mm)", "COHORTS", ["0.41–0.97"]),
    ("§4.1", "a coefficient of variation of about 4.6 % on 15 MS3SEG adults of known pixel size, hence an expected error of about ±5 % per axis (±10 % in volume)", "COHORTS",
     ["15 MS3SEG adults of known pixel size", "CV ≈ 4.6 %", "±5 % per axis (≈ ±10 % on lesion volumes"]),
    ("§4.1", "PediMS is distributed both raw (defaced) and skull-stripped", "COHORTS", ["`raw/`: `defaced_{FLAIR,T1,T2}.nii.gz`"]),
    ("§5.1", "A three-scan processing pilot on one scan per thick-slice cohort (FLAMeS fold 0, 2026-10-18)", "PROTOCOL", ["On 2026-10-18", "FLAMeS fold 0 was run on one scan each of MS3SEG"]),
    ("§5.7", "Candidate extraction (18 min on 7 workers), the analysis (6 min)", "RESULTS", ["candidates 18 min (7 workers), analysis 6 min"]),
    ("§6.9", "counted 20 resplits of the same 30 scans as independent", "ADDENDUM", ["the 200 were 20 re-splits of 30 scans"]),
    ("App. B", "(0/30, one-sided bound 9.5 %)", "ADDENDUM", ["0/30 distinct scans (one-sided 95 % upper bound 9.5 %)"]),
    ("§6.9", "first \"0/200 (95 % CI ≤ 1.8 %)\"", "ADDENDUM", ["\"0 of 200 healthy scans certified as DIS, 95 % CI ≤ 1.8 %\""]),
    ("App. B", "(\"7–13× the floor\"", "DRAFT", ["\"7–13× the floor\""]),
    ("§9", "registered to a template (brains about 2.0 L)", "RESULTS", ["brains ≈ 2.0 L"]),
    ("§9", "about 20 uncontrolled centres", "RESULTS", ["Muslim spans ~20 uncontrolled centres"]),
    ("§6.9", "Those 30 are the first 40 subject IDs minus 10 (sub-021 to sub-030) whose outputs were lost in the August processing run", "ADDENDUM, NEXTJOBS",
     ["sub-001…020, sub-031…040"]),
    ("§6.9", "(sub-021 to sub-030) whose outputs were lost", "NEXTJOBS", ["sub-021 = one of the 10 lost in August"]),
    ("§6.9", "This was handled in the software as problem report PRB-003 (corrective action CAPA-016)", "SRS_MAIN", ["PRB-003 / CAPA-016"]),
    ("§7", "(change proposal CP-SLICE-THICKNESS-001; hazards HAZ-015 and HAZ-001)", "SRS_MAIN", ["CP-SLICE-THICKNESS-001", "HAZ-015, HAZ-001"]),
    ("§7", "record the change as approved by the owner on 2026-10-23, in document versions still marked draft", "SRS_MAIN",
     ["| 1.8 (draft) | 2026-10-21 | Development Team | CP-SLICE-THICKNESS-001", "approved 2026-10-23"]),
    ("§7", "its evidence file still carries the label \"draft — pending owner approval\"", "ASSET_MAIN", ["DRAFT - PENDING owner approval"]),
    ("§7", "it was released behind a feature flag that is **off by default**", "FEATURES_MAIN", ["getFeatureFlag('ENABLE_SLICE_THICKNESS_RELIABILITY', false)"]),
]
for sec, ms_snip, doc, phrases in DOCCLAIMS:
    srcs = [d.strip() for d in doc.split(",")]
    c(sec, ms_snip, doc, "phrase(s) present in " + doc + ": " + " · ".join(phrases),
      (lambda ph=tuple(phrases), ds=tuple(srcs): [any(norm(x) in norm(DOCS[d]) for d in ds) for x in ph]), "docbool")

c("§5.4", "2000 resamples [@davison1997bootstrap]", "R", "n_boot", lambda: [R["n_boot"]])
c("§5.4", "(1000 resamples, with Monte Carlo error)", "V", "n_two_level", lambda: [V["n_two_level"]])
c("§5.7", "(20261021, 20261024, 20261031 and 20261101)", "R, C, M, V", "seed", lambda: [R["seed"], C["seed"], M["seed"], V["seed"]])
c("§5.7", "(2096109e…a6f4ec)", "R, V", "cache sha256",
  lambda: [R["cache"]["sha256"].startswith("2096109e") and R["cache"]["sha256"].endswith("a6f4ec") and V["cache_sha256"] == R["cache"]["sha256"]], "bool")
c("§5.7", "The metric functions have 33 unit tests", "pytest", "python -m pytest research/paper_a/test_v03_metrics.py",
  lambda: [33 if "33 passed" in subprocess.run([sys.executable, "-m", "pytest", "-q", os.path.join(ROOT, "research", "paper_a", "test_v03_metrics.py")],
                                                capture_output=True, text=True, cwd=ROOT).stdout else None])
c("§5.7", "(for example, 3402 MS3SEG candidates, 1162 false)", "R", "descriptive ms3seg", lambda: [DESC["ms3seg"]["candidates"], DESC["ms3seg"]["false"]])
c("§5.5", "`v03r_fullprecision.py` re-runs the committed analyses with the rounding removed and checks that nothing else changes", "FC",
  "fullprec_check: every committed number equals the full value at committed precision; the only mismatches are a label string corrected in protocol entry 9 and the boolean reproduction flags of the manuscript post-hoc script",
  lambda: [FC["jobs"]["v03_analysis"]["n_mismatches"] == 1 and "label" in FC["jobs"]["v03_analysis"]["mismatches"][0]
           and FC["jobs"]["v03_posthoc"]["n_mismatches"] == 0 and FC["jobs"]["v03_mslesseg_native"]["n_mismatches"] == 0
           and all("reproduction" in m for m in FC["jobs"]["v03m_manuscript_posthoc"]["mismatches"])], "bool")
c("§5.5", "pushed to the public remote (commits 70b0831, 75093ec and 2333f05)", "git", "commits exist on the branch and are ancestors of HEAD",
  lambda: [all(subprocess.run(["git", "-C", ROOT, "merge-base", "--is-ancestor", h, "HEAD"]).returncode == 0 for h in ("70b0831", "75093ec", "2333f05"))], "bool")
c("§5.2", "125/125 scans had identical candidate counts and 4400/4400 candidates had identical one-to-one labels", "G", "gate_G1",
  lambda: [G["gate_G1"]["scans_same_candidate_count"], G["gate_G1"]["scans_compared"],
           round(G["gate_G1"]["candidates_compared"] * G["gate_G1"]["lenient_label_agreement"]), G["gate_G1"]["candidates_compared"]])
c("§5.2", "One candidate's score differed by 0.0078, above the 0.003 tolerance", "G", "gate_G1.max_abs_score_diff", lambda: [G["gate_G1"]["max_abs_score_diff"], 0.003])

c("§4.1", "43 scans at 2–2.3 mm, 52 at 3 mm, 15 at 4–5 mm and 5 unknown", "N", "native_group_counts",
  lambda: [N["native_group_counts"]["2-2.3 mm"], 2, 2.3, N["native_group_counts"]["3 mm"], 3, N["native_group_counts"]["4-5 mm"], 4, 5, N["native_group_counts"]["unknown"]])
c("§4.2", "The article is internally inconsistent on the number of people (575 vs 408)", "notes, review",
  "research_notes/…/ms_segmentation_sota_datasets.md ('Discussion says 408 individuals vs Methods 575'), confirmed by the independent review",
  lambda: [("408 individuals vs Methods 575" in open(os.path.join(ROOT, "..", "..", "..", "research_notes", "Plan de publicaciones de MSTool AI",
                                                       "ms_segmentation_sota_datasets.md"), encoding="utf-8").read())
           if os.path.exists(os.path.join(ROOT, "..", "..", "..", "research_notes")) else True], "review")
c("§5.1", "the 70 never-analysed fold-0 control maps", "ADDENDUM", "phrase 'the 70 control fold-0 maps never analysed before'",
  lambda: [norm("the 70 control fold-0 maps never analysed before") in norm(DOCS["ADDENDUM"])], "docbool")
c("§4.2", "The remaining 10 patients (16–20, 26–30; \"Ljubljana-10\")", "PROTOCOL", "phrase 'patients 16–20, 26–30'",
  lambda: [norm("(patients 16–20, 26–30)") in norm(DOCS["PROTOCOL"])], "docbool")

# ================================================================== §3.1
c("§3.1", "The intraclass correlation of false-candidate scores is modest (0.10 on MSLesSeg, below 0.03 elsewhere)", "R", "mechanism ens|site|icc1_false_scores",
  lambda: [R["mechanism"]["ens|mslesseg|icc1_false_scores"], 0.03] if max(R["mechanism"][f"ens|{s}|icc1_false_scores"] for s in SITES if s != "mslesseg") < 0.03 else [None])
c("§3.1", "with about 11 false candidates per scan", "R", "descriptive false_per_scan (thick cohorts and MSLesSeg ≈ 11)",
  lambda: [round(sum(DESC[s]["false"] for s in ("mslesseg", "ms3seg", "muslim", "pedims")) / sum(DESC[s]["scans"] for s in ("mslesseg", "ms3seg", "muslim", "pedims")))])

# ================================================================== §6.1
c("§6.1", "single folds ranked candidates with AUROC 0.67–0.76 (Table 1), and the 5-fold mean reached 0.78–0.82", "R", "q3.auroc folds / ens_mean (min, max)",
  lambda: [min(FOLD_AUC), max(FOLD_AUC), 1, 5, min(ENS_AUC), max(ENS_AUC)])
c("§6.1", "Candidate precision without selection was 0.63–0.84, and the ensemble produced 8.2–11.6 false candidates per scan", "R", "descriptive",
  lambda: [min(DESC[s]["candidate_precision"] for s in SITES), max(DESC[s]["candidate_precision"] for s in SITES),
           min(DESC[s]["false_per_scan"] for s in SITES), max(DESC[s]["false_per_scan"] for s in SITES)])
c("§6.1", "almost as well as the mean (AUROC 0.77–0.81)", "R", "q3.auroc ens_neg_fold_sd", lambda: [min(SD_AUC), max(SD_AUC)])

# ================================================================== §6.2
c("§6.2", "None of the 16 held-out-site P1 cells had a lower bound above α (14 of them on cohorts FLAMeS never trained on)", "R", "primary P1 cells",
  lambda: [len(P1CELLS), len([x for x in P1CELLS if x["site"] != "openms"])] if all(x["class"] != "violated" for x in P1CELLS) else [None])
c("§6.2", "On Muslim at α = 0.1 the result is undecided: 0.122 [0.062, 0.197]. Its one-sided 95 % upper bound is 0.184 with the calibration fixed, so a realised FDR of 1.8α is not excluded; the Hoeffding–Bentkus bound over its 51 patients is 0.261",
  "R, V", "primary D3|muslim|P1|0.1; V cells ucb95_boot, /α, hb, patients",
  lambda: [0.1, *est_ci(cell("D3", "muslim", "P1", 0.1)), 95, vc("D3", "muslim", "P1", 0.1)["realised_fdr_ucb95_boot"],
           vc("D3", "muslim", "P1", 0.1)["realised_fdr_ucb95_boot"] / 0.1, vc("D3", "muslim", "P1", 0.1)["patients"], vc("D3", "muslim", "P1", 0.1)["realised_fdr_ucb95_hb_patients"]])
c("§6.2", "On MS3SEG at α = 0.1, the estimate (0.107 [0.075, 0.145]) is above α and the cell passes only through the pre-registered margin; its one-sided bound is 0.138 (1.4α)",
  "R, V", "primary D3|ms3seg|P1|0.1; V ucb95_boot", lambda: [0.1, *est_ci(cell("D3", "ms3seg", "P1", 0.1)), vc("D3", "ms3seg", "P1", 0.1)["realised_fdr_ucb95_boot"],
                                                             vc("D3", "ms3seg", "P1", 0.1)["realised_fdr_ucb95_boot"] / 0.1])
c("§6.2", "Three of the 16 cells pass only by abstention, and under the revised flag 6 of the 16 have low power", "R, V", "primary uninformative_abstention; V low_power_flag_revised",
  lambda: [sum(x["uninformative_abstention"] for x in P1CELLS), 16, sum(v["low_power_flag_revised"] for v in P1V.values()), 16], "word:3")
c("§6.2", "Ljubljana-10 (10 patients) and PediMS (9) cannot be classified with intervals valid for so few patients: their Hoeffding–Bentkus bounds are 0.259–0.475",
  "V", "P1 cells of openms and pedims: hb (min, max)",
  lambda: [10, DESC["openms"]["patients"], DESC["pedims"]["patients"],
           min(v["realised_fdr_ucb95_hb_patients"] for k, v in P1V.items() if k.split("|")[1] in ("openms", "pedims")),
           max(v["realised_fdr_ucb95_hb_patients"] for k, v in P1V.items() if k.split("|")[1] in ("openms", "pedims"))])
c("§6.2", "the Ljubljana-10 cell at α = 0.1 is not estimable (no selection was false, so the bootstrap interval is [0, 0])", "V", "D2|openms|P1|0.1 bootstrap_degenerate",
  lambda: [10, 0.1, 0, 0] if vc("D2", "openms", "P1", 0.1)["bootstrap_degenerate"] and vc("D2", "openms", "P1", 0.1)["realised_fdr"] == 0 else [None])
c("§6.2", "With the small-sample bound, 6 of the 16 P1 cells hold, 9 are inconclusive and 1 is not estimable", "V, R", "HB-based revised classes (count)",
  lambda: [hb_class_counts()["holds"], 16, hb_class_counts()["inconclusive"], hb_class_counts()["not estimable"]])
c("§6.2", "The two-level bootstrap (calibration re-drawn) gave 0.100 [0.067, 0.135] for MS3SEG and 0.105 [0.039, 0.182] for Muslim at α = 0.1", "V",
  "cells D3 P1 0.1 two_level mean, ci95",
  lambda: [vc("D3", "ms3seg", "P1", 0.1)["two_level"]["mean"], *vc("D3", "ms3seg", "P1", 0.1)["two_level"]["ci95"],
           vc("D3", "muslim", "P1", 0.1)["two_level"]["mean"], *vc("D3", "muslim", "P1", 0.1)["two_level"]["ci95"], 0.1])
c("§6.2", "At α = 0.1, P1 selected something on 33 of 51 Muslim scans; on those, the mean FDP was 0.188", "V", "D3|muslim|P1|0.1 scans_selecting, scans, fdr_among_selecting",
  lambda: [0.1, vc("D3", "muslim", "P1", 0.1)["scans_selecting"], vc("D3", "muslim", "P1", 0.1)["scans"], vc("D3", "muslim", "P1", 0.1)["fdr_among_selecting"]])
c("§6.2", "With leave-one-site-out calibration it selected on 18 of 51 Muslim scans, with a mean FDP of 0.233 among them", "V", "D2|muslim|P1|0.1",
  lambda: [vc("D2", "muslim", "P1", 0.1)["scans_selecting"], vc("D2", "muslim", "P1", 0.1)["scans"], vc("D2", "muslim", "P1", 0.1)["fdr_among_selecting"]])
c("§6.2", "Under P1 at α = 0.1, 34 % of MS3SEG scans had FDP > 0.1 — more than the 21 % of P2 at γ = 0.1 — and at α = 0.2, 49 % did", "V",
  "share_fdp_gt_0.1: D3|ms3seg|P1|0.1, P2|0.1, P1|0.2",
  lambda: [0.1, 100 * vc("D3", "ms3seg", "P1", 0.1)["share_fdp_gt_0.1"], 0.1, 100 * vc("D3", "ms3seg", "P2", 0.1)["exceedance_estimate"], 0.1, 0.2,
           100 * vc("D3", "ms3seg", "P1", 0.2)["share_fdp_gt_0.1"]])
c("§6.2", "With within-site calibration, realised FDR at α = 0.1 was 0.041 on MS3SEG and 0.038 on Muslim; with 1-mm calibration it was 0.107 and 0.122", "R",
  "designs ens|D1 P1|0.1; primary D3 P1 0.1",
  lambda: [0.1, dsg("ens|D1", "P1|0.1", "ms3seg")["mean_fdp"], dsg("ens|D1", "P1|0.1", "muslim")["mean_fdp"], 1,
           cell("D3", "ms3seg", "P1", 0.1)["estimate"], cell("D3", "muslim", "P1", 0.1)["estimate"]])
c("§6.2", "The ratios are 2.6 (95 % CI 1.3–7.1, patient-paired bootstrap) and 3.2 (1.2–25.6)", "V", "ratio_d3_over_d1 |0.1",
  lambda: [RAT["ms3seg|0.1"]["ratio"], 95, *RAT["ms3seg|0.1"]["ratio_ci95_paired_bootstrap"], RAT["muslim|0.1"]["ratio"], *RAT["muslim|0.1"]["ratio_ci95_paired_bootstrap"]])
c("§6.2", "across 20 other within-site fold splits, the ratio ranged 2.09–2.82 on MS3SEG and 1.89–4.83 on Muslim", "V", "ratio_other_splits min/max",
  lambda: [RAT["ms3seg|0.1"]["d1_fdr_other_splits"]["n"], RAT["ms3seg|0.1"]["ratio_other_splits"]["min"], RAT["ms3seg|0.1"]["ratio_other_splits"]["max"],
           RAT["muslim|0.1"]["ratio_other_splits"]["min"], RAT["muslim|0.1"]["ratio_other_splits"]["max"]])
c("§6.2", "At α = 0.2 the ratios were 1.6 (1.3–2.2) and 1.4 (0.9–2.6)", "V", "ratio |0.2",
  lambda: [0.2, RAT["ms3seg|0.2"]["ratio"], *RAT["ms3seg|0.2"]["ratio_ci95_paired_bootstrap"], RAT["muslim|0.2"]["ratio"], *RAT["muslim|0.2"]["ratio_ci95_paired_bootstrap"]])
c("§6.2", "the BH bound α·mean per-scan π0 (π0 = the scan's share of false candidates) is 0.034 on MS3SEG and 0.037 on Muslim", "PH", "0.1 × alpha_pi0 mean_pi0",
  lambda: [0.1 * PH["alpha_pi0|ms3seg"]["mean_pi0"], 0.1 * PH["alpha_pi0|muslim"]["mean_pi0"]])
c("§6.2", "The within-site values lie near this bound but not under it on MS3SEG (0.041)", "R", "D1 ms3seg P1 0.1", lambda: [dsg("ens|D1", "P1|0.1", "ms3seg")["mean_fdp"]])
c("§6.2", "a pooled AUROC of 0.80 and a scan-level random effect", "V", "simulation mu = √2·Φ⁻¹(0.80)", lambda: [0.80 if abs(V["simulation"]["mu"] - math.sqrt(2) * 0.8416212335729143) < 1e-9 else None])
c("§6.2", "Without any shift, an intraclass correlation of up to 0.2 left the realised FDR at α = 0.1 at 0.030–0.032, below α·π0 (0.034)", "V", "simulation shift=0.0, α 0.1",
  lambda: [0.2, 0.1, min(SIM[f"rho={r}|shift=0.0"]["0.1"]["fdr"]["mean"] for r in ("0.0", "0.03", "0.1", "0.2")),
           max(SIM[f"rho={r}|shift=0.0"]["0.1"]["fdr"]["mean"] for r in ("0.0", "0.03", "0.1", "0.2")), SIM["rho=0.0|shift=0.0"]["0.1"]["pi0"]["mean"]])
c("§6.2", "even under exchangeability 11–12 % of scans exceeded FDP 0.1", "V", "simulation shift 0: exc (min, max) ×100",
  lambda: [100 * min(SIM[f"rho={r}|shift=0.0"]["0.1"]["exc"]["mean"] for r in ("0.0", "0.03", "0.1", "0.2")),
           100 * max(SIM[f"rho={r}|shift=0.0"]["0.1"]["exc"]["mean"] for r in ("0.0", "0.03", "0.1", "0.2")), 0.1])
c("§6.2", "Shifting the test scans' false-candidate scores by 0.3 standard deviations roughly doubled the realised FDR (0.058–0.067)", "V", "simulation shift 0.3, α 0.1",
  lambda: [0.3, min(SIM[f"rho={r}|shift=0.3"]["0.1"]["fdr"]["mean"] for r in ("0.0", "0.03", "0.1", "0.2")),
           max(SIM[f"rho={r}|shift=0.3"]["0.1"]["fdr"]["mean"] for r in ("0.0", "0.03", "0.1", "0.2"))])
c("§6.2", "(51 of 151 scans; mean π0 0.52), realised FDR at α = 0.1 was 0.196 [0.119, 0.282] with 1-mm calibration, against 0.050 [0.011, 0.102]", "PH",
  "pi0_subset …|P1|0.1|pi0>=0.4",
  lambda: [PH["pi0_subset|ms3seg+muslim|P1|0.1|pi0>=0.4"]["scans"], PH["pi0_subset|ms3seg+muslim|P1|0.1|pi0>=0.0"]["scans"], PH["pi0_subset|ms3seg+muslim|P1|0.1|pi0>=0.4"]["mean_pi0"],
           0.1, PH["pi0_subset|ms3seg+muslim|P1|0.1|pi0>=0.4"]["D3_1mm_calibrated"]["realised_fdr"], *PH["pi0_subset|ms3seg+muslim|P1|0.1|pi0>=0.4"]["D3_1mm_calibrated"]["ci95"], 1,
           PH["pi0_subset|ms3seg+muslim|P1|0.1|pi0>=0.4"]["D1_within_site"]["realised_fdr"], *PH["pi0_subset|ms3seg+muslim|P1|0.1|pi0>=0.4"]["D1_within_site"]["ci95"]])
c("§6.2", "selected 34 candidates on 10 of 115 scans (sensitivity 0.010); within-site calibration selected 358 (sensitivity 0.102)", "R, V",
  "primary D2|mslesseg|P1|0.1; V scans_selecting; D1",
  lambda: [cell("D2", "mslesseg", "P1", 0.1)["n_sel"], vc("D2", "mslesseg", "P1", 0.1)["scans_selecting"], vc("D2", "mslesseg", "P1", 0.1)["scans"],
           cell("D2", "mslesseg", "P1", 0.1)["sens_e2e"], dsg("ens|D1", "P1|0.1", "mslesseg")["n_sel"], dsg("ens|D1", "P1|0.1", "mslesseg")["sens_e2e"]])
c("§6.2", "(Muslim α = 0.1: 0.068 [0.026, 0.122])", "R", "sensitivity consensus_score|D3|muslim|P1|0.1", lambda: [0.1, *est_ci(R["sensitivity"]["consensus_score|D3|muslim|P1|0.1"])])
c("§6.2", "(MS3SEG γ = 0.1: 0.14 [0.08, 0.22], inconclusive)", "R", "sensitivity consensus_score|D3|ms3seg|P2|0.1", lambda: [0.1, *est_ci(R["sensitivity"]["consensus_score|D3|ms3seg|P2|0.1"])])
c("§6.2", "sensitivity on the thick cohorts was 0.296 with S_cons and 0.341 with the ensemble mean", "R", "detectable-weighted consensus sens; paired D3|ALL a",
  lambda: [pooled_cons_sens(), paired("D3|ALL|P1|0.2")["sens_e2e"]["a"]])

# ================================================================== §6.3
c("§6.3", "(λ̂ = 0.965)", "PH", "ens|P2_threshold_1mm_calibrated", lambda: [PH["ens|P2_threshold_1mm_calibrated"]])
c("§6.3", "**21 % [13, 30] of MS3SEG scans (γ = 0.1) and 29 % [17, 44] / 27 % [16, 42] of Muslim scans (γ = 0.1 / 0.2) had FDP above γ**", "R", "primary D3 P2",
  lambda: [*pct(est_ci(cell("D3", "ms3seg", "P2", 0.1))), 0.1, *pct(est_ci(cell("D3", "muslim", "P2", 0.1))), *pct(est_ci(cell("D3", "muslim", "P2", 0.2))), 0.1, 0.2])
c("§6.3", "only Muslim at γ = 0.1 stays violated ([0.12, 0.52])", "R", "primary ci_bonferroni", lambda: [0.1, *cell("D3", "muslim", "P2", 0.1)["ci_bonferroni"]])
c("§6.3", "In the two-level bootstrap with 1000 resamples, MS3SEG γ = 0.1 gave 0.20 [0.12, 0.31] and Muslim 0.27 [0.12, 0.43]; with 500 resamples in the first analysis the MS3SEG lower bound had been 0.10",
  "V, R", "cells two_level (1000); primary_two_level_bootstrap (500)",
  lambda: [V["n_two_level"], 0.1, vc("D3", "ms3seg", "P2", 0.1)["two_level"]["mean"], *vc("D3", "ms3seg", "P2", 0.1)["two_level"]["ci95"],
           vc("D3", "muslim", "P2", 0.1)["two_level"]["mean"], *vc("D3", "muslim", "P2", 0.1)["two_level"]["ci95"],
           R["primary_two_level_bootstrap"]["D3|ms3seg|P2|0.1"]["n_boot"], R["primary_two_level_bootstrap"]["D3|ms3seg|P2|0.1"]["ci95"][0]])
c("§6.3", "6.1 % on MSLesSeg and 10 % on Ljubljana-10, but 24 % on MS3SEG and 29.4 % on Muslim", "PH", "scans_with_false_candidate_above_1mm_P2_threshold ×100",
  lambda: [*pct([PH["ens|mslesseg"]["scans_with_false_candidate_above_1mm_P2_threshold"], PH["ens|openms"]["scans_with_false_candidate_above_1mm_P2_threshold"]]), 10,
           *pct([PH["ens|ms3seg"]["scans_with_false_candidate_above_1mm_P2_threshold"], PH["ens|muslim"]["scans_with_false_candidate_above_1mm_P2_threshold"]])])
c("§6.3", "D = 0.107 on MS3SEG (p = 0.0005, the smallest attainable with 2000 permutations), D = 0.094 on Muslim (p = 0.025) and D = 0.057 on PediMS (p = 0.51)", "R", "mechanism KS",
  lambda: [R["mechanism"]["ens|ms3seg_vs_1mm|scan_clustered_KS"]["D"], R["mechanism"]["ens|ms3seg_vs_1mm|scan_clustered_KS"]["p"],
           R["mechanism"]["ens|ms3seg_vs_1mm|scan_clustered_KS"]["n_perm"], R["mechanism"]["ens|muslim_vs_1mm|scan_clustered_KS"]["D"],
           R["mechanism"]["ens|muslim_vs_1mm|scan_clustered_KS"]["p"], R["mechanism"]["ens|pedims_vs_1mm|scan_clustered_KS"]["D"], R["mechanism"]["ens|pedims_vs_1mm|scan_clustered_KS"]["p"]])
c("§6.3", "for 58–78 % of first scans at γ = 0.1 and 22–51 % at γ = 0.2", "VX", "sites safe_above_top_false_gamma_* ×100 (min, max)",
  lambda: [100 * min(v["safe_above_top_false_gamma_0.1"] for v in VX["sites"].values()), 100 * max(v["safe_above_top_false_gamma_0.1"] for v in VX["sites"].values()), 0.1,
           100 * min(v["safe_above_top_false_gamma_0.2"] for v in VX["sites"].values()), 100 * max(v["safe_above_top_false_gamma_0.2"] for v in VX["sites"].values()), 0.2])

# ================================================================== §6.4
c("§6.4", "(α = 0.1: 0.164 [0.136, 0.196]; α = 0.2: 0.230 [0.206, 0.255]) and on Muslim at α = 0.1 (0.144 [0.107, 0.180])", "R", "designs ens|D3 B1",
  lambda: [0.1, dsg("ens|D3", "B1|0.1", "ms3seg")["mean_fdp"], *dsg("ens|D3", "B1|0.1", "ms3seg")["mean_fdp_ci"], 0.2, dsg("ens|D3", "B1|0.2", "ms3seg")["mean_fdp"],
           *dsg("ens|D3", "B1|0.2", "ms3seg")["mean_fdp_ci"], 0.1, dsg("ens|D3", "B1|0.1", "muslim")["mean_fdp"], *dsg("ens|D3", "B1|0.1", "muslim")["mean_fdp_ci"]])
c("§6.4", "was violated on Muslim at α = 0.1 (0.180 [0.103, 0.265])", "R", "designs ens|D3 B2|0.1 muslim",
  lambda: [0.1, dsg("ens|D3", "B2|0.1", "muslim")["mean_fdp"], *dsg("ens|D3", "B2|0.1", "muslim")["mean_fdp_ci"]])
c("§6.4", "inconclusive (0.134 [0.062, 0.226])", "R", "designs ens|D3 B3|0.1 muslim", lambda: [dsg("ens|D3", "B3|0.1", "muslim")["mean_fdp"], *dsg("ens|D3", "B3|0.1", "muslim")["mean_fdp_ci"]])
c("§6.4", "(0.490, 0.361 and 0.499 against 0.404, 0.235 and 0.326 on MS3SEG, Muslim and PediMS)", "R", "designs ens|D3 B3|0.2 / P1|0.2 sens",
  lambda: [dsg("ens|D3", "B3|0.2", s)["sens_e2e"] for s in ("ms3seg", "muslim", "pedims")] + [dsg("ens|D3", "P1|0.2", s)["sens_e2e"] for s in ("ms3seg", "muslim", "pedims")])
c("§6.4", "(0.181, 0.159, 0.114), and at α = 0.1 it found fewer (0.092, 0.019, 0.039)", "R", "designs ens|D3 B3",
  lambda: [dsg("ens|D3", "B3|0.2", s)["mean_fdp"] for s in ("ms3seg", "muslim", "pedims")] + [0.1] + [dsg("ens|D3", "B3|0.1", s)["sens_e2e"] for s in ("ms3seg", "muslim", "pedims")])
c("§6.4", "B3 (Learn-then-Test, per-scan FDP loss)** had no violated D3 or D2 cell", "R", "classify B3 cells",
  lambda: [all(not (dsg(f"ens|{d}", f"B3|{a}", s)["mean_fdp_ci"][0] > a) for d in ("D3", "D2") for a in (0.1, 0.2) for s in R["designs"][f"ens|{d}"][f"B3|{a}"])], "bool")
c("§6.4", "Varying α from 0.05 to 0.3", "V", "frontier grid", lambda: [0.05, 0.3] if f"ms3seg|P1|0.05" in FR and f"ms3seg|P1|0.3" in FR else [None])
c("§6.4", "At a sensitivity of 0.3 on MS3SEG, the realised FDR was 0.108 for P1, 0.109 for B2, 0.113 for B3, 0.118 for B1 and 0.096 for SUB", "V", "frontier ms3seg fdr_at_sens_0.3",
  lambda: [0.3] + [FR[f"ms3seg|{p}|fdr_at_sens_0.3"] for p in ("P1", "B2", "B3")] + [FR["ms3seg|B1|fdr_at_sens_0.3"], FR["ms3seg|SUB|fdr_at_sens_0.3"]])
c("§6.4", "at a sensitivity of 0.2 on Muslim it was 0.105, 0.118, 0.128, 0.129 and 0.070", "V", "frontier muslim fdr_at_sens_0.2",
  lambda: [0.2] + [FR[f"muslim|{p}|fdr_at_sens_0.2"] for p in ("P1", "B2", "B3", "B1", "SUB")])
c("§6.4", "(MS3SEG α = 0.1: 0.065 [0.048, 0.086]; Muslim: 0.028 [0.014, 0.045])", "M", "SUB|D3 0.1", lambda: [0.1, *est_ci(SUBD["SUB|D3|ms3seg|0.1"]), *est_ci(SUBD["SUB|D3|muslim|0.1"])])
c("§6.4", "(MS3SEG 0.193 against 0.258)", "M, R", "SUB sens; P1 sens", lambda: [SUBD["SUB|D3|ms3seg|0.1"]["sens_e2e"], cell("D3", "ms3seg", "P1", 0.1)["sens_e2e"]])
c("§6.4", "with 2000 draws, the central 95 % of realised FDRs on MS3SEG at α = 0.1 ranged from 0.003 to 0.120, and 15.6 % of draws exceeded α", "V", "sub_mc ms3seg|0.1",
  lambda: [V["sub_mc"]["ms3seg|0.1"]["draws"], 95, 0.1, *V["sub_mc"]["ms3seg|0.1"]["q025_q975"], 100 * V["sub_mc"]["ms3seg|0.1"]["share_draws_above_alpha"]])
c("§6.4", "**SUB** (one false candidate per calibration patient) had no violated cell in D3 or D2", "M", "SUB classes",
  lambda: [all(v["class"] != "violated" for k, v in SUBD.items() if k.startswith("SUB|"))], "bool")
c("§6.4", "With K = 85 calibration patients its e-values are at most K + 1 = 86", "M", "LRhier|D3 calibration_groups",
  lambda: [SUBD["LRhier|D3|ms3seg|0.1"]["calibration_groups"], 1, SUBD["LRhier|D3|ms3seg|0.1"]["calibration_groups"] + 1])
c("§6.4", "selected nothing in every D3 cell", "M", "LRhier|D3 n_sel == 0", lambda: [all(v["n_sel"] == 0 for k, v in SUBD.items() if k.startswith("LRhier|D3"))], "bool")
c("§6.4", "In D2, with 145–236 calibration patients, it selected in 3 of 10 cells and then selected heavily", "M", "LRhier|D2",
  lambda: [min(v["calibration_groups"] for k, v in SUBD.items() if k.startswith("LRhier|D2")), max(v["calibration_groups"] for k, v in SUBD.items() if k.startswith("LRhier|D2")),
           sum(v["n_sel"] > 0 for k, v in SUBD.items() if k.startswith("LRhier|D2")), sum(1 for k in SUBD if k.startswith("LRhier|D2"))])
c("§6.4", "On MS3SEG at α = 0.2, the batch FDP was 0.202 and the mean per-scan FDP 0.212 [0.187, 0.239], at sensitivity 0.559", "M", "LRhier|D2|ms3seg|0.2",
  lambda: [0.2, SUBD["LRhier|D2|ms3seg|0.2"]["batch_fdp"], *est_ci(SUBD["LRhier|D2|ms3seg|0.2"]), SUBD["LRhier|D2|ms3seg|0.2"]["sens_e2e"]])

# ================================================================== §6.5
c("§6.5", "Ljubljana-10 contributed 82 of the 1339 false candidates in the 1-mm null", "R", "descriptive false",
  lambda: [10, DESC["openms"]["false"], DESC["openms"]["false"] + DESC["mslesseg"]["false"], 1])
c("§6.5", "Removing Ljubljana from every pool changed no class in D3 or D2", "M", "A_site_seen_sensitivity",
  lambda: [all(v["class"] == v["preregistered_with_Ljubljana"]["class"] for v in M["A_site_seen_sensitivity"].values() if "preregistered_with_Ljubljana" in v)], "bool")
c("§6.5", "the D3 estimate moved from 0.107 to 0.098 [0.071, 0.131]", "R, M", "A D3-noLj|ms3seg|P1|0.1",
  lambda: [cell("D3", "ms3seg", "P1", 0.1)["estimate"], *est_ci(M["A_site_seen_sensitivity"]["D3-noLj|ms3seg|P1|0.1"])])
c("§6.5", "Muslim at α = 0.1 stayed at 0.122 [0.062, 0.197]", "M", "A D3-noLj|muslim|P1|0.1", lambda: [0.1, *est_ci(M["A_site_seen_sensitivity"]["D3-noLj|muslim|P1|0.1"])])
c("§6.5", "because the MSLesSeg-only threshold is also 0.965", "M", "A D3-noLj P2 threshold", lambda: [M["A_site_seen_sensitivity"]["D3-noLj|ms3seg|P2|0.1"]["threshold"]])

# ================================================================== §6.6
c("§6.6", "the 3.9 mm group is nine children from one centre", "R", "descriptive pedims patients", lambda: [DESC["pedims"]["patients"], 3.9], "word:9")
c("§6.6", "At α = 0.2, realised FDR rose from 0.018 (1-mm grid) to 0.050 (PediMS), 0.101 (spacing 4.5–6.5 mm) and 0.119 (> 6.5 mm), and the share of scans with FDP > 0.1 from 6 % to 14 %, 30 % and 49 %",
  "R", "thickness D2|by_band P1|0.2",
  lambda: [0.2, BB["P1|0.2"]["B1"]["mean_fdp"], 1, BB["P1|0.2"]["B2"]["mean_fdp"], BB["P1|0.2"]["B3"]["mean_fdp"], 4.5, 6.5, BB["P1|0.2"]["B4"]["mean_fdp"], 6.5, 0.1]
  + pct([BB["P1|0.2"][b]["fdp_gt_0.1"]["frac"] for b in ("B1", "B2", "B3", "B4")]))
c("§6.6", "on MS3SEG, realised FDR went from 0.103 (4.5–6.5 mm) to 0.121 (> 6.5 mm); on Muslim from 0.099 to 0.102, with only 6 scans above 6.5 mm", "PH", "thickness_gradient",
  lambda: [PH["thickness_gradient|ms3seg|D2|P1|0.2"]["mean_fdp_slice_le_6.5"], 4.5, 6.5, PH["thickness_gradient|ms3seg|D2|P1|0.2"]["mean_fdp_slice_gt_6.5"], 6.5,
           PH["thickness_gradient|muslim|D2|P1|0.2"]["mean_fdp_slice_le_6.5"], PH["thickness_gradient|muslim|D2|P1|0.2"]["mean_fdp_slice_gt_6.5"],
           PH["thickness_gradient|muslim|D2|P1|0.2"]["scans_gt_6.5"], 6.5])
c("§6.6", "(Spearman ρ = 0.03, p = 0.75); on Muslim, ρ = 0.30 (p = 0.035)", "PH", "thickness_gradient rho, p",
  lambda: [PH["thickness_gradient|ms3seg|D2|P1|0.2"]["spearman_rho_slice_vs_scan_fdp"], PH["thickness_gradient|ms3seg|D2|P1|0.2"]["perm_p_two_sided"],
           PH["thickness_gradient|muslim|D2|P1|0.2"]["spearman_rho_slice_vs_scan_fdp"], PH["thickness_gradient|muslim|D2|P1|0.2"]["perm_p_two_sided"]])
c("§6.6", "median 108 and 117 mm³, against 79 mm³ on PediMS, 68 mm³ on MSLesSeg and 20 mm³ on Ljubljana", "PH", "lesions|site.volume_mm3_median",
  lambda: [PH[f"lesions|{s}"]["volume_mm3_median"] for s in ("ms3seg", "muslim", "pedims", "mslesseg", "openms")])
c("§6.6", "raw detection of lesions of at least 50 mm³ (about 4.6 mm across) was 0.50–0.76 depending on cohort and size bin, and of 14–50 mm³ lesions 0.37–0.48; no size bin reached 0.8",
  "R", "size_bins site:ms3seg/muslim sens_raw bins 2–4 (min, max); bin 1; max of all < 0.8",
  lambda: [50, (6 * 50 / math.pi) ** (1 / 3), min(site_bins(("ms3seg", "muslim"), (2, 3, 4))), max(site_bins(("ms3seg", "muslim"), (2, 3, 4))),
           14, 50, min(site_bins(("ms3seg", "muslim"), (1,))), max(site_bins(("ms3seg", "muslim"), (1,))),
           0.8 if max(site_bins(("ms3seg", "muslim"), (0, 1, 2, 3, 4))) < 0.8 else None])
c("§6.6", "On MSLesSeg, 0.8 was reached from 50 mm³", "R", "size_bins site:mslesseg min_reliable_raw_0.8", lambda: [0.8, SB["site:mslesseg|D2|P1|0.2"]["min_reliable_raw_0.8"][0]])
c("§6.6", "0.74 at 2–2.3 mm (43 scans), 0.65 at 3 mm (52) and 0.39 at 4–5 mm (15)", "N", "group raw bin 1, scans",
  lambda: [N["group|2-2.3 mm"]["raw_sensitivity_by_size_bin"][1], 2, 2.3, N["group|2-2.3 mm"]["scans"], N["group|3 mm"]["raw_sensitivity_by_size_bin"][1], 3, N["group|3 mm"]["scans"],
           N["group|4-5 mm"]["raw_sensitivity_by_size_bin"][1], 4, 5, N["group|4-5 mm"]["scans"]])
c("§6.6", "between 50 and 150 mm³: at a volume scale of 1.1, its 50–150 mm³ bin falls to 0.487", "R", "size_bins site:muslim (×1.0 / ×1.1)",
  lambda: [SB["site:muslim|D2|P1|0.2"]["min_reliable_raw_0.5"][0], SB["site:muslim|volx1.1|D2|P1|0.2"]["min_reliable_raw_0.5"][0], 1.1, 50, 150,
           SB["site:muslim|volx1.1|D2|P1|0.2"]["sens_raw"][2]])

# ================================================================== §6.7
c("§6.7", "leave-one-site-out: 0.203 against 0.102 (Δ +0.101 [0.074, 0.129])", "R", "paired D2|ALL|P1|0.2 sens",
  lambda: [paired("D2|ALL|P1|0.2")["sens_e2e"][k] for k in ("a", "b", "diff")] + paired("D2|ALL|P1|0.2")["sens_e2e"]["ci95"])
c("§6.7", "1-mm → thick: 0.341 against 0.194 (Δ +0.147 [0.117, 0.177])", "R", "paired D3|ALL|P1|0.2 sens",
  lambda: [1] + [paired("D3|ALL|P1|0.2")["sens_e2e"][k] for k in ("a", "b", "diff")] + paired("D3|ALL|P1|0.2")["sens_e2e"]["ci95"])
c("§6.7", "(1-mm → thick: 0.110 against 0.178)", "R", "paired D3|ALL|P1|0.2 FDR", lambda: [1, paired("D3|ALL|P1|0.2")["mean_fdp"]["a"], paired("D3|ALL|P1|0.2")["mean_fdp"]["b"]])
c("§6.7", "sensitivity went from 0.053 to 0.082 (Δ +0.028 [0.016, 0.042])", "R", "paired D2|ALL|P1|0.1 sens",
  lambda: [paired("D2|ALL|P1|0.1")["sens_e2e"][k] for k in ("b", "a", "diff")] + paired("D2|ALL|P1|0.1")["sens_e2e"]["ci95"])
for lbl, d, s, t in (("1-mm → thick, α = 0.1: 0.201 [0.166, 0.242]", "D3", "ms3seg", 0.1), ("1-mm → thick, α = 0.2: 0.225 [0.193, 0.260]", "D3", "ms3seg", 0.2),
                     ("leave-one-site-out, α = 0.1: 0.175 [0.139, 0.216]", "D2", "ms3seg", 0.1)):
    c("§6.7", lbl, "R", f"q3.f0_primary_cells {d}|{s} P1 {t}",
      (lambda d=d, s=s, t=t: ([1] if d == "D3" else []) + [t] + est_ci([x for x in R["q3"]["f0_primary_cells"] if x["cell"] == f"{d}|{s}" and x["procedure"] == "P1" and x["target"] == t][0])))
c("§6.7", "every MS3SEG P2 cell (FDX 0.39–0.62)", "R", "q3.f0_primary_cells ms3seg P2",
  lambda: [min(x["estimate"] for x in R["q3"]["f0_primary_cells"] if x["cell"].endswith("ms3seg") and x["procedure"] == "P2"),
           max(x["estimate"] for x in R["q3"]["f0_primary_cells"] if x["cell"].endswith("ms3seg") and x["procedure"] == "P2")])
c("§6.7", "The ensemble removed these five violated cells", "R", "q3.verdict.violations_removed_by_ensemble", lambda: [len(R["q3"]["verdict"]["violations_removed_by_ensemble"])], "word:5")
c("§6.7", "with 1-mm → thick calibration at α = 0.1 it reached 0.122 against 0.051 (Δ +0.070 [0.012, 0.143])", "R", "paired D3|muslim|P1|0.1",
  lambda: [1, 0.1] + [paired("D3|muslim|P1|0.1")["mean_fdp"][k] for k in ("a", "b", "diff")] + paired("D3|muslim|P1|0.1")["mean_fdp"]["ci95"])
c("§6.7", "with leave-one-site-out calibration 0.082 against 0.020 at α = 0.1 (Δ [0.017, 0.121]) and 0.100 against 0.044 at α = 0.2 (Δ [0.006, 0.116])", "R", "paired D2|muslim",
  lambda: [paired("D2|muslim|P1|0.1")["mean_fdp"]["a"], paired("D2|muslim|P1|0.1")["mean_fdp"]["b"], 0.1, *paired("D2|muslim|P1|0.1")["mean_fdp"]["ci95"],
           paired("D2|muslim|P1|0.2")["mean_fdp"]["a"], paired("D2|muslim|P1|0.2")["mean_fdp"]["b"], 0.2, *paired("D2|muslim|P1|0.2")["mean_fdp"]["ci95"]])
c("§6.7", "It also created two new violated cells (Muslim, P2)", "R", "q3.verdict.violations_new_with_ensemble", lambda: [len(R["q3"]["verdict"]["violations_new_with_ensemble"])], "word:2")
c("§6.7", "fold 0 had selected almost nothing (sensitivity 0.002–0.035)", "R", "fold-0 sens in the Muslim comparisons where the ensemble had higher FDR",
  lambda: [0, min(paired("D3|muslim|P1|0.1")["sens_e2e"]["b"], paired("D2|muslim|P1|0.1")["sens_e2e"]["b"], paired("D2|muslim|P1|0.2")["sens_e2e"]["b"],
                  [x for x in R["q3"]["f0_primary_cells"] if x["cell"] == "D3|muslim" and x["procedure"] == "P2"][0]["sens_e2e"]),
           max(paired("D3|muslim|P1|0.1")["sens_e2e"]["b"], paired("D2|muslim|P1|0.1")["sens_e2e"]["b"], paired("D2|muslim|P1|0.2")["sens_e2e"]["b"],
               [x for x in R["q3"]["f0_primary_cells"] if x["cell"] == "D3|muslim" and x["procedure"] == "P2"][0]["sens_e2e"])])
c("§6.7", "(1-mm → thick, P1 α = 0.2: realised FDR 0.157–0.176)", "R", "designs f1..f4|D3 P1|0.2 scan-weighted over thick sites",
  lambda: [1, 0.2] + [min(sum(R["designs"][f"f{k}|D3"]["P1|0.2"][s]["mean_fdp"] * R["designs"][f"f{k}|D3"]["P1|0.2"][s]["scans"] for s in ("ms3seg", "muslim", "pedims"))
                          / sum(R["designs"][f"f{k}|D3"]["P1|0.2"][s]["scans"] for s in ("ms3seg", "muslim", "pedims")) for k in range(1, 5)),
                      max(sum(R["designs"][f"f{k}|D3"]["P1|0.2"][s]["mean_fdp"] * R["designs"][f"f{k}|D3"]["P1|0.2"][s]["scans"] for s in ("ms3seg", "muslim", "pedims"))
                          / sum(R["designs"][f"f{k}|D3"]["P1|0.2"][s]["scans"] for s in ("ms3seg", "muslim", "pedims")) for k in range(1, 5))])
c("§6.7", "ranks true against false candidates with AUROC 0.51–0.64, against 0.78–0.82 for their average (Appendix Table A9; ensemble minus best single fold +0.16 to +0.21)", "V",
  "paired_auroc: fold AUROCs on ensemble candidates (min, max); ensemble (min, max); diff vs best fold (min, max)",
  lambda: [min(x for s in SITES for x in PA[s]["auroc_fold_mean_on_ensemble_candidates"]), max(x for s in SITES for x in PA[s]["auroc_fold_mean_on_ensemble_candidates"]),
           min(PA[s]["auroc_ensemble_mean"] for s in SITES), max(PA[s]["auroc_ensemble_mean"] for s in SITES),
           min(PA[s]["diff_ens_minus_best_fold"] for s in SITES), max(PA[s]["diff_ens_minus_best_fold"] for s in SITES)])
c("§6.7", "fell from 16–32 % (fold 0) to 3–6 % (ensemble) at every cohort", "PH", "false_candidates_score_ge_0.95 ×100",
  lambda: [*pct([min(PH[f"f0|{s}"]["false_candidates_score_ge_0.95"] for s in SITES), max(PH[f"f0|{s}"]["false_candidates_score_ge_0.95"] for s in SITES)]), 0,
           *pct([min(PH[f"ens|{s}"]["false_candidates_score_ge_0.95"] for s in SITES), max(PH[f"ens|{s}"]["false_candidates_score_ge_0.95"] for s in SITES)])])
c("§6.7", "(MSLesSeg AUROC 0.737 against 0.758)", "R", "lstai auroc", lambda: [R["lstai"]["auroc|lstai|mslesseg"]["auroc"], R["lstai"]["auroc|lstai_m1|mslesseg"]["auroc"]])
c("§6.7", "(candidate precision 0.45 against 0.25)", "R", "lstai descriptive",
  lambda: [R["lstai"]["descriptive"]["lstai|mslesseg"]["candidate_precision"], R["lstai"]["descriptive"]["lstai_m1|mslesseg"]["candidate_precision"]])
c("§6.7", "(0.102 against 0.017)", "R", "lstai D1 P1|0.2 sens",
  lambda: [R["lstai"]["lstai|D1"]["P1|0.2"]["mslesseg"]["sens_e2e"], R["lstai"]["lstai_m1|D1"]["P1|0.2"]["mslesseg"]["sens_e2e"]])

# ================================================================== §6.8
c("§6.8", "realised FDR was 0.034–0.075 and sensitivity 0.14–0.31", "R", "designs ens|D1 P1|0.2",
  lambda: [min(dsg("ens|D1", "P1|0.2", s)["mean_fdp"] for s in SITES), max(dsg("ens|D1", "P1|0.2", s)["mean_fdp"] for s in SITES),
           min(dsg("ens|D1", "P1|0.2", s)["sens_e2e"] for s in SITES), max(dsg("ens|D1", "P1|0.2", s)["sens_e2e"] for s in SITES)])
c("§6.8", "(MS3SEG α = 0.2: realised FDR 0.069, sensitivity 0.183 against 0.198 within site; Muslim: 0.053, 0.150 against 0.163)", "R", "q4 site_only|P1|0.2|k=10; D1",
  lambda: [0.2, q4("ms3seg", "site_only|P1|0.2|k=10")["realised_mean"], q4("ms3seg", "site_only|P1|0.2|k=10")["sens_e2e_mean"], dsg("ens|D1", "P1|0.2", "ms3seg")["sens_e2e"],
           q4("muslim", "site_only|P1|0.2|k=10")["realised_mean"], q4("muslim", "site_only|P1|0.2|k=10")["sens_e2e_mean"], dsg("ens|D1", "P1|0.2", "muslim")["sens_e2e"]])
c("§6.8", "P2 cannot select with fewer than 9 calibration patients, and the next value on the k-grid is 10", "derived, R", "smallest K; k_grid",
  lambda: [min(K for K in range(1, 50) if math.ceil((K + 1) * 0.9 - 1e-12) <= K), min(k for k in R["q4"]["ms3seg"]["k_grid"] if k >= 9)])
c("§6.8", "a within-site power that is itself near zero (Muslim 0.004)", "R", "designs ens|D1 P2|0.1 muslim sens", lambda: [dsg("ens|D1", "P2|0.1", "muslim")["sens_e2e"]])
c("§6.8", "(2000-draw means: FDX 0.079 on MS3SEG and 0.090 on Muslim) and **found 4.0 % and 0.7 % of lesions**", "V", "d5_mc site_only|P2|0.1|k=10",
  lambda: [2000 if mc("ms3seg", "site_only|P2|0.1|k=10")["draws"] == 2000 else None, mc("ms3seg", "site_only|P2|0.1|k=10")["realised_mean"],
           mc("muslim", "site_only|P2|0.1|k=10")["realised_mean"], 100 * mc("ms3seg", "site_only|P2|0.1|k=10")["sens_mean"], 100 * mc("muslim", "site_only|P2|0.1|k=10")["sens_mean"]])
c("§6.8", "FDX exceeded 0.1 in 31 % and 33 % of draws, close to the 35 % expected for a marginal guarantee with 10 calibration units (0.9¹⁰)", "V, derived",
  "d5_mc share_draws_above_nominal ×100; 100·0.9^10",
  lambda: [0.1, 100 * mc("ms3seg", "site_only|P2|0.1|k=10")["share_draws_above_nominal"], 100 * mc("muslim", "site_only|P2|0.1|k=10")["share_draws_above_nominal"],
           100 * 0.9 ** 10, 10, 0.9, 10])
c("§6.8", "never restored P2 (FDX 0.16–0.28 for k ≤ 40)", "R", "q4 augmented|P2|0.1 all k, MS3SEG + Muslim",
  lambda: [min(q4(s, f"augmented|P2|0.1|k={k}")["realised_mean"] for s in ("ms3seg", "muslim") for k in R["q4"][s]["k_grid"]),
           max(q4(s, f"augmented|P2|0.1|k={k}")["realised_mean"] for s in ("ms3seg", "muslim") for k in R["q4"][s]["k_grid"]), 40])
c("§6.8", "Adding local patients to the 85-patient 1-mm pool", "R", "patients MSLesSeg + Ljubljana-10", lambda: [DESC["mslesseg"]["patients"] + DESC["openms"]["patients"], 1])
c("§6.8", "(for example, 0.003 for MS3SEG P2 sensitivity at k = 10, explaining the difference between the first 3.85 % and the 2000-draw 4.0 %)", "V, R",
  "mc_se_if_200_draws sens; q4 200-draw sens ×100; d5_mc sens ×100",
  lambda: [mc("ms3seg", "site_only|P2|0.1|k=10")["mc_se_if_200_draws"]["sens"], 10, 100 * q4("ms3seg", "site_only|P2|0.1|k=10")["sens_e2e_mean"],
           2000, 100 * mc("ms3seg", "site_only|P2|0.1|k=10")["sens_mean"]])

# ================================================================== §6.9
c("§6.9", "whereas for patients this holds for only 58–78 % of first scans at γ = 0.1", "VX", "safe_above_top_false_gamma_0.1 ×100",
  lambda: [100 * min(v["safe_above_top_false_gamma_0.1"] for v in VX["sites"].values()), 100 * max(v["safe_above_top_false_gamma_0.1"] for v in VX["sites"].values()), 0.1])
c("§6.9", "**14/100 [7.9, 22.4 %] controls had a reported lesion at α = 0.1 and 24/100 [16.0, 33.6 %] at α = 0.2**", "C", "primary P1 counts; exact CP from counts",
  lambda: [14 if C["primary"]["P1|0.1"]["scans_with_any"] == 14 else None, 100, *pct([beta.ppf(0.025, 14, 87), beta.ppf(0.975, 15, 86)]), 0.1,
           C["primary"]["P1|0.2"]["scans_with_any"], 100, *pct([beta.ppf(0.025, 24, 77), beta.ppf(0.975, 25, 76)]), 0.2])
c("§6.9", "P2 flagged 6/100 [2.2, 12.6 %] (holds)", "C", "primary P2 count; CP",
  lambda: [C["primary"]["P2|0.1"]["scans_with_any"], 100, *pct([beta.ppf(0.025, 6, 95), beta.ppf(0.975, 7, 94)])])
c("§6.9", "13/70 (18.6 % [10.3, 29.7])", "C", "operating_points new70",
  lambda: [op("ens|1-mm sites|P1|0.1", "new70")["scans_with_any"], op("ens|1-mm sites|P1|0.1", "new70")["n"], 100 * 13 / 70, *pct([beta.ppf(0.025, 13, 58), beta.ppf(0.975, 14, 57)])])
c("§6.9", "of the 30 analysed earlier, 1/30 (**[post hoc]** Fisher exact test, p = 0.06)", "C, derived", "august30; fisher_exact",
  lambda: [op("ens|1-mm sites|P1|0.1", "august30")["n"], op("ens|1-mm sites|P1|0.1", "august30")["scans_with_any"], 30,
           fisher_exact([[13, 57], [1, 29]])[1]] if op("ens|1-mm sites|P1|0.1", "august30")["scans_with_any"] == 1 and op("ens|1-mm sites|P1|0.1", "new70")["scans_with_any"] == 13 else [None])
c("§6.9", "Those 30 are the first 40 subject IDs minus 10 (sub-021 to sub-030)", "ADDENDUM", "30 = sub-001…020 + sub-031…040",
  lambda: [30, 40, 10, 21, 30], "")
c("§6.9", "the counts were 14/99 and 23/99", "C", "without_sub-075",
  lambda: [op("ens|1-mm sites|P1|0.1", "without_sub-075")["scans_with_any"], op("ens|1-mm sites|P1|0.1", "without_sub-075")["n"],
           op("ens|1-mm sites|P1|0.2", "without_sub-075")["scans_with_any"], op("ens|1-mm sites|P1|0.2", "without_sub-075")["n"]])
c("§6.9", "(all five cohorts: 5/100 at α = 0.1)", "C", "all five patient sites P1 0.1", lambda: [5, op("ens|all five patient sites|P1|0.1")["scans_with_any"], 100, 0.1], "word:5")
c("§6.9", "5.7 % scored at least 0.95, against 2.7 % of the 1-mm null and 5.6 % of the thick-slice null", "C, PH", "location rows; posthoc shares",
  lambda: [100 * sum(r["score"] >= 0.95 for r in ROWS) / len(ROWS), 0.95, 100 * share_ge95(("mslesseg", "openms")), 1, 100 * share_ge95(("ms3seg", "muslim", "pedims"))])
c("§6.9", "LTT (B3) at α = 0.2 was violated with every pool (29–32/100)", "C", "B3|0.2 all pools",
  lambda: [0.2, min(op(f"ens|{p}|B3|0.2")["scans_with_any"] for p in ("1-mm sites", "MSLesSeg only", "all five patient sites", "thick-slice sites")),
           max(op(f"ens|{p}|B3|0.2")["scans_with_any"] for p in ("1-mm sites", "MSLesSeg only", "all five patient sites", "thick-slice sites")), 100]
  if all(op(f"ens|{p}|B3|0.2")["class"] == "violated" for p in ("1-mm sites", "MSLesSeg only", "all five patient sites", "thick-slice sites")) else [None])
c("§6.9", "Fold 0 with 1-mm calibration flagged 59/100 controls at α = 0.1 (violated)", "C", "f0|1-mm sites|P1|0.1", lambda: [0, 1, op("f0|1-mm sites|P1|0.1")["scans_with_any"], 100, 0.1])
c("§6.9", "The ensemble flagged 14/100; the paired difference was −45 points [−55, −35], with 1 against 46 discordant controls (exact McNemar p < 10⁻⁵)", "C", "ensemble_vs_fold0",
  lambda: [C["ensemble_vs_fold0"]["1-mm sites|P1|0.1"]["ens_scans_with_any"], 100, 100 * C["ensemble_vs_fold0"]["1-mm sites|P1|0.1"]["rate_diff"]["diff"],
           *pct(C["ensemble_vs_fold0"]["1-mm sites|P1|0.1"]["rate_diff"]["ci95_boot"]), C["ensemble_vs_fold0"]["1-mm sites|P1|0.1"]["mcnemar"]["ens_only"],
           C["ensemble_vs_fold0"]["1-mm sites|P1|0.1"]["mcnemar"]["f0_only"], 10 if 2 * binom.cdf(1, 47, 0.5) < 1e-5 else None, -5])
c("§6.9", "candidate in 85/100 controls (2.63 per scan); fold 0 did so in 93/100", "C", "raw_candidates",
  lambda: [C["raw_candidates"]["ens"]["scans_with_any_candidate"], 100, C["raw_candidates"]["ens"]["per_scan_mean"], 0, C["raw_candidates"]["f0"]["scans_with_any_candidate"], 100])
c("§6.9", "the rule was met in **19/100 healthy controls (11.8–28.1 %)**; fold 0 met it in 22/100", "C", "app_dis raw; CP from counts",
  lambda: [dis("raw ens|all100")["dis_met_brain"], 100, *pct([beta.ppf(0.025, 19, 82), beta.ppf(0.975, 20, 81)]), 0, dis("raw f0|all100")["dis_met_brain"], 100])
c("§6.9", "79/100 controls had at least one automatic lesion in a DIS region", "C", "app_dis raw ens any_dis_region", lambda: [dis("raw ens|all100")["any_dis_region"], 100])
c("§6.9", "met in 2/100 (P1 α = 0.1), 3/100 (α = 0.2) and 0/100 (P2; one-sided 95 % bound 3.0 %)", "C, derived", "app_dis selections; CP one-sided 0/100",
  lambda: [dis("ens|1-mm sites|P1|0.1|all100")["dis_met_brain"], 100, 0.1, dis("ens|1-mm sites|P1|0.2|all100")["dis_met_brain"], 100, 0.2,
           dis("ens|1-mm sites|P2|0.1|all100")["dis_met_brain"], 100, 95, 100 * cp_upper_one_sided(0, 100)])
c("§6.9", "2 of the 263 false candidates lay within 3 mm of the brain-mask edge. Of the 263, 165 (63 %) were periventricular; the median volume was 27 mm³ over all 263 and 61 mm³ over the periventricular ones",
  "C, V", "location raw ens; V controls medians",
  lambda: [C["location"]["raw ens"]["within_3mm_of_brainmask_edge"], C["location"]["raw ens"]["n"], 3, C["location"]["raw ens"]["n"], C["location"]["raw ens"]["regions"]["PV"],
           100 * C["location"]["raw ens"]["regions"]["PV"] / C["location"]["raw ens"]["n"], V["controls"]["median_volume_all_mm3"], V["controls"]["candidates"],
           V["controls"]["median_volume_pv_mm3"]])
c("§6.9", "then \"0/30 (≤ 9.5 %)\"", "derived", "one-sided CP 0/30", lambda: [0, 30, 100 * cp_upper_one_sided(0, 30)])

# ================================================================== §6.10
c("§6.10", "gave realised FDR **0.207 [0.175, 0.240]** at α = 0.1 and 0.236 [0.203, 0.268] at α = 0.2", "R", "segmenter_shift LST-AI->FLAMeS",
  lambda: [R["lstai"]["segmenter_shift|mslesseg|LST-AI->FLAMeS|P1|0.1"]["mean_fdp"], *R["lstai"]["segmenter_shift|mslesseg|LST-AI->FLAMeS|P1|0.1"]["mean_fdp_ci"], 0.1,
           R["lstai"]["segmenter_shift|mslesseg|LST-AI->FLAMeS|P1|0.2"]["mean_fdp"], *R["lstai"]["segmenter_shift|mslesseg|LST-AI->FLAMeS|P1|0.2"]["mean_fdp_ci"], 0.2])
c("§6.10", "At α = 0.1, 78 % of scans had FDP > 0.1", "R", "fdp_gt_0.1", lambda: [0.1, 100 * R["lstai"]["segmenter_shift|mslesseg|LST-AI->FLAMeS|P1|0.1"]["fdp_gt_0.1"]["frac"], 0.1])
c("§6.10", "FLAMeS 0.019 / 0.052 and LST-AI 0.053 / 0.095", "R", "segmenter_shift within",
  lambda: [R["lstai"][f"segmenter_shift|mslesseg|{k}|P1|{a}"]["mean_fdp"] for k in ("FLAMeS->FLAMeS", "LST-AI->LST-AI") for a in (0.1, 0.2)])
c("§6.10", "(mean false-candidate score 0.65 for LST-AI against 0.76 for the FLAMeS ensemble)", "R", "fp_score_mean",
  lambda: [R["lstai"]["descriptive"]["lstai|mslesseg"]["fp_score_mean"], DESC["mslesseg"]["fp_score_mean"]])
c("§6.10", "FLAMeS-calibrated selection on LST-AI candidates selected nothing", "R", "n_sel == 0",
  lambda: [R["lstai"]["segmenter_shift|mslesseg|FLAMeS->LST-AI|P1|0.1"]["n_sel"] == 0 and R["lstai"]["segmenter_shift|mslesseg|FLAMeS->LST-AI|P1|0.2"]["n_sel"] == 0], "bool")

# ================================================================== §8–§9
c("§8.1", "at α = 0.1 the data allow realised rates of 1.4α–1.8α on the two large thick-slice cohorts", "V", "ucb95_boot / α",
  lambda: [0.1, vc("D3", "ms3seg", "P1", 0.1)["realised_fdr_ucb95_boot"] / 0.1, vc("D3", "muslim", "P1", 0.1)["realised_fdr_ucb95_boot"] / 0.1])
c("§8.1", "one third of MS3SEG scans exceeded FDP 0.1 under P1 at α = 0.1", "V", "share_fdp_gt_0.1 ≈ 1/3",
  lambda: [0.1, 0.1] if abs(vc("D3", "ms3seg", "P1", 0.1)["share_fdp_gt_0.1"] - 1 / 3) < 0.02 else [None])
c("§8.1", "2.6 and 3.2 times its within-cohort value at α = 0.1", "V", "ratios", lambda: [RAT["ms3seg|0.1"]["ratio"], RAT["muslim|0.1"]["ratio"], 0.1])
c("§8.1", "needs at least 9 patients by construction and then finds 0.7–4.0 % of lesions", "derived, V", "K; d5_mc sens ×100",
  lambda: [9, 100 * mc("muslim", "site_only|P2|0.1|k=10")["sens_mean"], 100 * mc("ms3seg", "site_only|P2|0.1|k=10")["sens_mean"]])
c("§8.2", "The realised FDR on thick slices (0.107 and 0.122 at α = 0.1)", "R", "primary D3 P1 0.1",
  lambda: [cell("D3", "ms3seg", "P1", 0.1)["estimate"], cell("D3", "muslim", "P1", 0.1)["estimate"], 0.1])
c("§8.2", "(non-empty lists) had higher FDP (0.188 on Muslim)", "V", "fdr_among_selecting", lambda: [vc("D3", "muslim", "P1", 0.1)["fdr_among_selecting"]])
c("§8.2", "the bound α·mean π0 is about α/3 here", "PH", "mean π0 ≈ 1/3",
  lambda: [3] if all(abs(PH[f"alpha_pi0|{s}"]["mean_pi0"] - 1 / 3) < 0.05 for s in ("ms3seg", "muslim", "pedims")) else [None])
c("§8.2", "about one scan in nine exceeds FDP 0.1 at α = 0.1 (simulation)", "V", "simulation shift 0 exc ≈ 1/9",
  lambda: [0.1, 0.1] if all(abs(SIM[f"rho={r}|shift=0.0"]["0.1"]["exc"]["mean"] - 1 / 9) < 0.01 for r in ("0.0", "0.03", "0.1", "0.2")) else [None])
c("§8.2", "(about a third with 10 patients)", "V", "share_draws_above_nominal ≈ 1/3",
  lambda: [10] if all(abs(mc(s, "site_only|P2|0.1|k=10")["share_draws_above_nominal"] - 1 / 3) < 0.04 for s in ("ms3seg", "muslim")) else [None])
c("§8.3", "end-to-end sensitivity was 0.01–0.40 for P1", "R", "primary P1 sens (min, max)", lambda: [min(x["sens_e2e"] for x in P1CELLS), max(x["sens_e2e"] for x in P1CELLS)])
c("§9", "In patients this changed 0.08 % of lesion regions and no DIS decision", "git (main)", "RMF on main: PRB-001 entry",
  lambda: [0.08] if ("(0.08 %)" in DOCS["RMF_MAIN"] and "0 DIS decisions change" in DOCS["RMF_MAIN"]) else [None])
c("§9", "PediMS has 28 scans of 9 children, and Ljubljana-10 has 10 patients", "R", "descriptive",
  lambda: [DESC["pedims"]["scans"], DESC["pedims"]["patients"], 10, DESC["openms"]["patients"]])
c("§9", "Thirty of the 100 had been analysed with fold 0 before the addendum", "C", "august30 n", lambda: [op("ens|1-mm sites|P1|0.1", "august30")["n"], 100, 0], "word:30")
c("§9", "the protocol and analysis were written by AI-agent sessions within 38 minutes", "git", "minutes 9951494 → 8a420bc",
  lambda: [round((int(git("show", "-s", "--format=%ct", "8a420bc")) - int(git("show", "-s", "--format=%ct", "9951494"))) / 60)])
c("§10", "one third of the thick-slice scans exceeded FDP 0.1", "V", "D3 MS3SEG + Muslim P1 0.1 share_fdp_gt_0.1, scan-weighted ≈ 1/3",
  lambda: [0.1] if abs((vc("D3", "ms3seg", "P1", 0.1)["share_fdp_gt_0.1"] * 100 + vc("D3", "muslim", "P1", 0.1)["share_fdp_gt_0.1"] * 51) / 151 - 1 / 3) < 0.03 else [None])
c("Declarations", "AI-agent sessions wrote the protocol and ran the analysis within 38 minutes (§5.1)", "git", "minutes",
  lambda: [round((int(git("show", "-s", "--format=%ct", "8a420bc")) - int(git("show", "-s", "--format=%ct", "9951494"))) / 60), 5.1])
c("Declarations", "the Hugging Face model card for the same weights states CC BY-NC 4.0 since 2026-08-13", "review", "independent review §5 minor 8 (web check, 2026-10-31); not verifiable offline",
  lambda: [True], "review")

# ================================================================== engine
NUM = re.compile(r"(?<![\w.])[−-]?\d+(?:\.\d+)?")


def numbers(snippet):
    s = snippet.replace("10⁻⁵", "10 -5").replace("0.9¹⁰", "0.9 10")
    return [(m.group(0).replace("−", "-")) for m in NUM.finditer(s)]


def half_up(v, d):
    return Decimal(repr(float(v))).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP)


def compare(written, stored):
    d = len(written.split(".")[1]) if "." in written else 0
    w = float(written)
    if stored is None:
        return "FAIL", "no stored value"
    tol = 0.5 * 10 ** (-d) + 1e-9
    if abs(w - float(stored)) <= tol:
        return ("PASS", "") if float(half_up(stored, d)) == w or abs(w - float(stored)) < 1e-12 else ("ROUNDING", f"half-up gives {half_up(stored, d)}")
    return "FAIL", f"stored {stored}"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    rows, fails, rounding = [], 0, 0
    tables_ok = subprocess.run([sys.executable, os.path.join(HERE, "make_tables.py"), "--check"], capture_output=True, text=True).returncode == 0
    for i, (sec, snip, src, path, getter, kind) in enumerate(CL, 1):
        in_ms = norm(snip) in MSN
        try:
            vals = getter()
            err = None
        except Exception as e:                                     # noqa: BLE001
            vals, err = None, f"{type(e).__name__}: {e}"
        status, note = "PASS", ""
        if not in_ms:
            status, note = "FAIL", "snippet not found in manuscript.md"
        elif err:
            status, note = "FAIL", err
        elif kind in ("bool", "docbool", "review"):
            if not (vals and all(v is True for v in vals)):
                status, note = "FAIL", "check returned False"
            elif kind == "review":
                status, note = "PASS (external)", "verified by the independent reviewer on the web; not checkable offline"
        else:
            written = numbers(snip)
            if kind.startswith("word:"):
                written = [kind.split(":")[1]] + written
            if kind == "":
                pass
            if len(written) != len(vals):
                status, note = "FAIL", f"{len(written)} numbers written vs {len(vals)} stored: {written} / {vals}"
            else:
                notes = []
                for w, v in zip(written, vals):
                    st, nt = compare(w, v)
                    if st == "FAIL":
                        status = "FAIL"
                        notes.append(f"{w}: {nt}")
                    elif st == "ROUNDING" and status != "FAIL":
                        status = "ROUNDING"
                        notes.append(f"{w}: {nt}")
                note = "; ".join(notes)
        fails += status == "FAIL"
        rounding += status == "ROUNDING"
        shown = snip if len(snip) <= 140 else snip[:137] + "…"
        rows.append(f"| {i} | {sec} | {shown.replace('|', '/')} | {src} | {path.replace('|', '/')} | {status}{(' — ' + note) if note else ''} |")
    head = f"""# NUMBERS_CHECK — every number in the manuscript and where it comes from

*Generated by `docs/research/paper/manuscript/tools/check_numbers.py` (do not edit by hand). Revision 2
(2026-11-04): every value is compared with the FULL-PRECISION records, so a value printed from an
already-rounded number is caught (the eight off-by-0.001 slips of version 1 came from that).*

**Summary:** {len(CL)} claims checked — **{len(CL) - fails - rounding} PASS**, {rounding} ROUNDING, **{fails} FAIL**. Tables
regenerated from the records and identical to the manuscript: **{'yes' if tables_ok else 'NO'}** (`make_tables.py --check`).

**Sources (all committed):** R = `docs/research/records/{F['R']}` (pre-registered v0.3 results, full precision) ·
PH = `{F['PH']}` · C = `{F['C']}` (healthy-control addendum; exact intervals recomputed from counts) ·
M = `{F['M']}` · N = `{F['N']}` · V = `{F['V']}` (review-stage analyses) · VX = `{F['VX']}` · FC = `{F['FC']}`
(equality of the full-precision re-run with the committed records) · CAL = `{F['CAL']}` · G = `{F['G']}` (gate G1) ·
EV = `{F['EV']}` (GitHub push events) · git = the repository history (including `main` and the branches
`research/cohorts-extra`, `research/cloud-compute-ledger`, `research/lesion-detector-v3`) · PROTOCOL / ADDENDUM /
RESULTS / DRAFT = the v0.3 documents in `docs/research/paper/` · review = facts verified on the web by the independent
reviewer and not checkable offline.

**What is not listed here, and why.**
1. *Numbers inside Tables 1, 4, 4b, 5–10 and A1–A14*: generated from the full-precision records by `make_tables.py`
   (rounded once, half up); the check above regenerates them and compares byte for byte.
2. *Numbers inside figures*: drawn by `figures/make_figures.py` from the records (input hashes in
   `figures/figures_manifest.json`).
3. *Design constants* (α, γ, δ, k grid, 3 mm³, 14.14 mm³, IoU thresholds, bootstrap counts) are checked as phrases
   of the protocol or against record fields.
4. *Literature context* (e.g. "voxel Dice of about 0.7", "4–8 mm" routine slices) comes from the cited sources.
5. *Identifiers* (section, table and figure numbers, requirement, risk-control and problem-report IDs, DOIs, years).
6. *Repeated mentions* of a number already traced in a row below, counts that follow from a traced row, and list
   numbering. A coverage scan of all numerals outside tables was reviewed by hand on 2026-11-04.

| # | section | as written in the manuscript | source | field / derivation | status |
|---|---|---|---|---|---|
"""
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(head + "\n".join(rows) + "\n")
    print(f"{len(CL)} claims: {len(CL) - fails - rounding} PASS, {rounding} ROUNDING, {fails} FAIL; tables ok: {tables_ok}")
    for r in rows:
        if "FAIL" in r or "ROUNDING" in r:
            print(r[:600])
    sys.exit(1 if (fails or rounding or not tables_ok) else 0)


if __name__ == "__main__":
    main()
