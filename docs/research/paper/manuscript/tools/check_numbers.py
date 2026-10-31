#!/usr/bin/env python3
"""Paper A manuscript — trace every number in the text to its stored source and write NUMBERS_CHECK.md.

For each claim: (1) the snippet must occur in manuscript.md (whitespace-normalised); (2) the numbers
in the snippet are compared, in order, with the values read from the committed records (or derived
from them by the stated formula). A number passes when |written − stored| ≤ half a unit of its last
written digit; it is flagged ROUNDING when it passes but differs from round-half-up of the stored
value. Tables are checked by regenerating them (make_tables.py --check). Design constants and
historical statements are checked as phrases in the protocol / source documents. Git commits and
dates are checked with git; public-remote times against the stored GitHub-events record.

    python docs/research/paper/manuscript/tools/check_numbers.py      (exit 1 on any FAIL)
"""
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

F = {"R": "2026-10-21_paper_a_v03_results.json", "PH": "2026-10-21_paper_a_v03_posthoc.json",
     "C": "2026-10-24_paper_a_v03c_controls.json", "M": "2026-10-31_paper_a_manuscript_posthoc.json",
     "N": "2026-10-21_paper_a_v03_mslesseg_native.json", "CAL": "2026-10-24_paper_a_v03c_calibration.json",
     "G": "2026-10-21_paper_a_v03_candidates.json", "EV": "2026-10-31_paper_a_github_push_events.json"}
D = {k: json.load(open(os.path.join(REC, v), encoding="utf-8")) for k, v in F.items()}
R, PH, C, M, N, CAL, G, EV = (D[k] for k in ("R", "PH", "C", "M", "N", "CAL", "G", "EV"))
DOCS = {"PROTOCOL": open(os.path.join(PAPER, "PROTOCOL-v0.3.md"), encoding="utf-8").read(),
        "ADDENDUM": open(os.path.join(PAPER, "PROTOCOL-v0.3-addendum-controls.md"), encoding="utf-8").read(),
        "RESULTS": open(os.path.join(PAPER, "RESULTS-v0.3.md"), encoding="utf-8").read(),
        "DRAFT": open(os.path.join(PAPER, "manuscript-draft.md"), encoding="utf-8").read()}
MS = open(os.path.join(MS_DIR, "manuscript.md"), encoding="utf-8").read()


def norm(s):
    return re.sub(r"\s+", " ", s)


MSN = norm(MS)


# ------------------------------------------------------------------ accessors
def cell(d, s, p, t):
    for c in R["primary"]:
        if (c["design"], c["site"], c["procedure"], c["target"]) == (d, s, p, t):
            return c
    raise KeyError((d, s, p, t))


def dsg(arm_design, pt, site):
    return R["designs"][arm_design][pt][site]


def paired(k):
    return R["q3"]["paired_ens_minus_f0"][k]


def q4(site, k):
    return R["q4"][site]["cells"][k]


def op(k, sub="all100"):
    return C["operating_points"][f"{k}|{sub}"]


def dis(k):
    return C["app_dis"]["results"][k]


def tl(site, design="D2", p="P1|0.2"):
    return R["thickness"][f"{design}|by_site_band"][p] if False else None


def est_ci(c):
    return [c["estimate"], c["ci95"][0], c["ci95"][1]]


def pct(x):
    return [100 * v for v in x]


def git(*args):
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True, encoding="utf-8", check=True).stdout


def git_blob_sha(commit, path):
    blob = subprocess.run(["git", "-C", ROOT, "show", f"{commit}:{path}"], capture_output=True, check=True).stdout
    import hashlib
    return hashlib.sha256(blob).hexdigest()


def git_time(commit):
    return git("show", "-s", "--format=%ci", commit).strip()        # 'YYYY-MM-DD HH:MM:SS +0200'


def event(head_prefix=None, typ="PushEvent", ref=None):
    for e in EV["events"]:
        if e["type"] == typ and (head_prefix is None or (e["head"] or "").startswith(head_prefix)) \
                and (ref is None or ref in (e["ref"] or "")):
            return e
    return None


def cp_upper_one_sided(x, n, conf=0.95):
    return 1.0 if x >= n else beta.ppf(conf, x + 1, n - x)


DESC = {s: R["descriptive"][f"ens|{s}"] for s in ("mslesseg", "openms", "ms3seg", "muslim", "pedims")}
AUC = R["q3"]["auroc"]
SITES = ("mslesseg", "openms", "ms3seg", "muslim", "pedims")
FOLD_AUC = [AUC[f"f{k}|{s}"]["auroc"] for s in SITES for k in range(5)]
ENS_AUC = [AUC[f"ens_mean|{s}"]["auroc"] for s in SITES]
SD_AUC = [AUC[f"ens_neg_fold_sd|{s}"]["auroc"] for s in SITES]
P1CELLS = [c for c in R["primary"] if c["procedure"] == "P1"]
SB = R["thickness"]["size_bins"]
BB = R["thickness"]["D2|by_band"]


def thick_bins(idx):
    return [SB[f"{b}|D2|P1|0.2"]["sens_raw"][idx] for b in ("B3", "B4")]


def pooled_cons_sens():
    tot = sum(DESC[s]["gt_detectable"] for s in ("ms3seg", "muslim", "pedims"))
    return sum(R["sensitivity"][f"consensus_score|D3|{s}|P1|0.2"]["sens_e2e"] * DESC[s]["gt_detectable"]
               for s in ("ms3seg", "muslim", "pedims")) / tot


def share_ge95(sites, arm="ens"):
    num = sum(PH[f"{arm}|{s}"]["false_candidates_score_ge_0.95"] * PH[f"{arm}|{s}"]["false_candidates"] for s in sites)
    den = sum(PH[f"{arm}|{s}"]["false_candidates"] for s in sites)
    return num / den


ROWS = C["location_rows_ens"]
SUBD = M["B_baselines"]

# ------------------------------------------------------------------ claims
# (section, snippet as written, source, path / derivation, getter -> list of stored values [, kind])
CL = []


def c(section, snippet, source, path, getter, kind="num"):
    CL.append((section, snippet, source, path, getter, kind))


# ---- Abstract
c("Abstract", "(304 scans, 245 patients)", "R", "Σ descriptive['ens|site'].scans / .patients",
  lambda: [sum(DESC[s]["scans"] for s in SITES), sum(DESC[s]["patients"] for s in SITES)])
c("Abstract", "and 100 healthy controls", "C", "primary['P1|0.1'].n", lambda: [C["primary"]["P1|0.1"]["n"]])
c("Abstract", "10 scans are natively thin, 110 are", "R, N", "descriptive['ens|openms'].scans; Σ N.native_group_counts (2–2.3, 3, 4–5 mm)",
  lambda: [DESC["openms"]["scans"], sum(v for k, v in N["native_group_counts"].items() if k != "unknown")])
c("Abstract", "and 5 have unknown native thickness", "N", "native_group_counts.unknown", lambda: [N["native_group_counts"]["unknown"]])
c("Abstract", "with 3.9–8.3 mm slices", "R", "site_info.pedims.note ('3.9 mm'), site_info.muslim.note ('8.3 mm')",
  lambda: [3.9 if "3.9 mm" in R["site_info"]["pedims"]["note"] else None, 8.3 if "8.3 mm" in R["site_info"]["muslim"]["note"] else None])
c("Abstract", "16 pre-registered held-out-site comparisons (14 on sites FLAMeS never trained on)", "R",
  "count primary P1 cells; minus the 2 Ljubljana (openms) cells", lambda: [len(P1CELLS), len([x for x in P1CELLS if x["site"] != "openms"])])
c("Abstract", "(Muslim: realised FDR 0.122 [95 % CI 0.062, 0.197])", "R", "primary D3|muslim|P1|0.1 estimate, ci95",
  lambda: [cell("D3", "muslim", "P1", 0.1)["estimate"], 95, *cell("D3", "muslim", "P1", 0.1)["ci95"]])
c("Abstract", "Three comparisons passed only because almost nothing was selected", "R",
  "count P1 primary cells with uninformative_abstention", lambda: [sum(x["uninformative_abstention"] for x in P1CELLS)], "word:3")
c("Abstract", "was 2.6–3.2 times its within-site value", "R",
  "D3 P1 0.1 estimate / designs['ens|D1']['P1|0.1'] mean_fdp (MS3SEG, Muslim)",
  lambda: [cell("D3", "ms3seg", "P1", 0.1)["estimate"] / dsg("ens|D1", "P1|0.1", "ms3seg")["mean_fdp"],
           cell("D3", "muslim", "P1", 0.1)["estimate"] / dsg("ens|D1", "P1|0.1", "muslim")["mean_fdp"]])
c("Abstract", "it was 0.196 [0.120, 0.282]", "PH", "pi0_subset|ms3seg+muslim|P1|0.1|pi0>=0.4 .D3_1mm_calibrated",
  lambda: [PH["pi0_subset|ms3seg+muslim|P1|0.1|pi0>=0.4"]["D3_1mm_calibrated"]["realised_fdr"], *PH["pi0_subset|ms3seg+muslim|P1|0.1|pi0>=0.4"]["D3_1mm_calibrated"]["ci95"]])
c("Abstract", "21 % [13, 30] (MS3SEG) and 29 % [17, 44] (Muslim)", "R", "primary D3 P2 0.1 estimate, ci95 (×100)",
  lambda: pct(est_ci(cell("D3", "ms3seg", "P2", 0.1)) + est_ci(cell("D3", "muslim", "P2", 0.1))))
c("Abstract", "Only 10 or more local calibration patients restored it", "R", "q4[site].k_star['site_only|P2|0.1'] (MS3SEG = Muslim)",
  lambda: [R["q4"]["ms3seg"]["k_star"]["site_only|P2|0.1"]["k_star"]] if R["q4"]["ms3seg"]["k_star"]["site_only|P2|0.1"]["k_star"] == R["q4"]["muslim"]["k_star"]["site_only|P2|0.1"]["k_star"] else [None])
c("Abstract", "(3.85 % and 0.65 % of lesions found)", "R", "q4[ms3seg|muslim].cells['site_only|P2|0.1|k=10'].sens_e2e_mean ×100",
  lambda: pct([q4("ms3seg", "site_only|P2|0.1|k=10")["sens_e2e_mean"], q4("muslim", "site_only|P2|0.1|k=10")["sens_e2e_mean"]]))
c("Abstract", "candidate AUROC from 0.67–0.76 to 0.78–0.82", "R", "q3.auroc f0..f4 (min, max); ens_mean (min, max)",
  lambda: [min(FOLD_AUC), max(FOLD_AUC), min(ENS_AUC), max(ENS_AUC)])
c("Abstract", "(0.102 → 0.203, leave-one-site-out)", "R", "q3.paired_ens_minus_f0['D2|ALL|P1|0.2'].sens_e2e b, a",
  lambda: [paired("D2|ALL|P1|0.2")["sens_e2e"]["b"], paired("D2|ALL|P1|0.2")["sens_e2e"]["a"]])
c("Abstract", "(0.052 → 0.122)", "R", "q3.paired_ens_minus_f0['D3|muslim|P1|0.1'].mean_fdp b, a",
  lambda: [paired("D3|muslim|P1|0.1")["mean_fdp"]["b"], paired("D3|muslim|P1|0.1")["mean_fdp"]["a"]])
c("Abstract", "flagged 14/100 (α = 0.1) and 24/100 (α = 0.2) controls", "C", "primary P1|0.1, P1|0.2 scans_with_any / n",
  lambda: [C["primary"]["P1|0.1"]["scans_with_any"], 100, 0.1, C["primary"]["P1|0.2"]["scans_with_any"], 100, 0.2])
c("Abstract", "marked a lesion in 85/100 healthy brains", "C", "raw_candidates.ens.scans_with_any_candidate",
  lambda: [C["raw_candidates"]["ens"]["scans_with_any_candidate"], 100])
c("Abstract", "met a brain dissemination-in-space rule in 19/100 [11.8, 28.1 %]", "C", "app_dis.results['raw ens|all100']",
  lambda: [dis("raw ens|all100")["dis_met_brain"], 100, *pct(dis("raw ens|all100")["ci95_exact"])])

# ---- Methods: pre-registration (git and GitHub events)
c("§5.1", "committed on 2026-10-21 at 04:21 CEST (commit 9951494)", "git", "git show -s --format=%ci 9951494",
  lambda: [git_time("9951494").startswith("2026-10-21 04:21") and git_time("9951494").endswith("+0200")], "bool")
c("§5.1", "1b5b39a8e5cc3c3af6cfce22d64c16832e0ccc71dbaf5ba35b11db15b93c6016", "git",
  "sha256(git show 9951494:docs/research/paper/PROTOCOL-v0.3.md)",
  lambda: [git_blob_sha("9951494", "docs/research/paper/PROTOCOL-v0.3.md") == "1b5b39a8e5cc3c3af6cfce22d64c16832e0ccc71dbaf5ba35b11db15b93c6016"], "bool")
c("§5.1", "(commit c0c5fa1, 04:35)", "git", "commit time", lambda: [git_time("c0c5fa1")[11:16] == "04:35"], "bool")
c("§5.1", "(commit 50c9b08, 04:41)", "git", "commit time", lambda: [git_time("50c9b08")[11:16] == "04:41"], "bool")
c("§5.1", "committed at 04:59 (8a420bc)", "git", "commit time", lambda: [git_time("8a420bc")[11:16] == "04:59"], "bool")
c("§5.1", "committed on 2026-10-24 at 15:52 CEST (commit caa47e7", "git", "commit time",
  lambda: [git_time("caa47e7").startswith("2026-10-24 15:52")], "bool")
c("§5.1", "bdae74ec6373daa0685c49cc4f57fed73445716b92d469d9658cede764f87213", "git",
  "sha256(git show caa47e7:docs/research/paper/PROTOCOL-v0.3-addendum-controls.md)",
  lambda: [git_blob_sha("caa47e7", "docs/research/paper/PROTOCOL-v0.3-addendum-controls.md") == "bdae74ec6373daa0685c49cc4f57fed73445716b92d469d9658cede764f87213"], "bool")
c("§5.1", "only at 05:09 CEST on 2026-10-21, together with the first results", "EV",
  "CreateEvent research/paper-a-v0.3 created_at (UTC+2)",
  lambda: [event(typ="CreateEvent", ref="paper-a-v0.3")["created_at"].startswith("2026-10-21T03:09")], "bool")
c("§5.1", "pushed to the public remote at 13:52:31 UTC on 2026-10-24, 71 minutes before its results (15:03:30 UTC)", "EV",
  "PushEvent heads caa47e7 / 413f5b5 created_at; difference in minutes",
  lambda: [event("caa47e7")["created_at"] == "2026-10-24T13:52:31Z" and event("413f5b5")["created_at"] == "2026-10-24T15:03:30Z"
           and round((15 * 60 + 3.5) - (13 * 60 + 52.5)) == 71], "bool")

# ---- Methods: protocol constants (phrases that must be in the protocol / addendum)
DOCCLAIMS = [
    ("§3.1", "18-connected component of {p ≥ 0.5} whose physical volume is at least 3 mm³", "PROTOCOL", ["18-connected component of {p ≥ 0.5}", "volume ≥ 3 mm³"]),
    ("§3.1", "*Clinical* lesions are those of at least 14.14 mm³ (a sphere of 3 mm diameter)", "PROTOCOL", ["≥ 14.14 mm³ (3-mm-diameter sphere)"]),
    ("§3.1", "lenient (IoU > 0); a strict variant (IoU ≥ 0.10)", "PROTOCOL", ["(IoU > 0)", "(IoU ≥ 0.10)"]),
    ("§3.2", "on the grid {0, 0.001, …, 1, ∞}", "PROTOCOL", ["λ ∈ {0, 0.001, …, 1, ∞}"]),
    ("§3.2", "λ̂ is the ⌈(K + 1)(1 − δ)⌉-th smallest t_i", "PROTOCOL", ["⌈(K+1)(1−δ)⌉-th smallest t_i"]),
    ("§3.2", "with probability at least 0.9 over the calibration draw", "PROTOCOL", ["Hoeffding–Bentkus, δ = 0.1"]),
    ("§5.3", "(k ∈ {1, 2, 3, 5, 10, 20, 40}, 200 draws each)", "PROTOCOL", ["k ∈ {1, 2, 3, 5, 10, 20, 40}", "R = 200 draws per k"]),
    ("§5.4", "The **32 primary cells**", "PROTOCOL", ["32 primary cells"]),
    ("§5.4", 'about 0.8 spurious one-sided "violations" among 32 cells', "PROTOCOL", ["~0.8 spurious one-sided 2.5 %"]),
    ("§5.4", "*holds* if the upper bound is at most nominal + 0.05", "PROTOCOL", ["margin 0.05 absolute"]),
    ("§5.4", "fewer than 10 selections or end-to-end sensitivity below 0.05", "PROTOCOL", ["< 10 selections in total or end-to-end sensitivity < 0.05"]),
    ("§5.4", "the mean power is at least 90 % of within-site power", "PROTOCOL", ["mean power ≥ 0.9 × the D1 power"]),
    ("§5.4", "(level 1 − 0.05/32, 20 000 resamples)", "PROTOCOL", ["(level 1 − 0.05/32)", "use 20 000 bootstrap resamples"]),
    ("§4.1", "HD-BET 2.0.1", "ADDENDUM", ["HD-BET v2.0.1"]),
    ("§5.2", "the maximum decoding error is about 0.002", "ADDENDUM", ["max decoding error ≈ 0.002"]),
    ("§4.2", "FLAMeS was trained on 668 FLAIR scans from 11 sources", "ADDENDUM", ["668 FLAIR scans from 11 sources"]),
    ("§4.2", "20 ISBI-2015 scans [@carass2017longitudinal] and 20 Ljubljana scans", "ADDENDUM", ["ISBI-2015 20, PubMRI (= Ljubljana) 20"]),
    ("§4.2", "MSSEG-2016 scans (centres 01, 03, 07 and 08)", "ADDENDUM", ["MSSEG-1 centres 01/03/07/08"]),
    ("§4.2", "brain bounding box of all 668 training cases", "ADDENDUM", ["exactly 668 entries"]),
    ("§4.2", "Ljubljana patients 01–15 and 21–25 exactly", "PROTOCOL", ["patients 01–15, 21–25 are FLAMeS training data"]),
    ("§4.2", "each fold trains on four fifths of the cases", "DRAFT", ["each fold trains on 4/5 of the cases"]),
    ("§4.1", "was estimated (±5 % per axis)", "RESULTS", ["(±5 % per axis)"]),
    ("§5.1", "A three-scan processing pilot on one scan per thick-slice cohort (FLAMeS fold 0, 2026-10-18)", "PROTOCOL",
     ["On 2026-10-18", "FLAMeS fold 0 was run on one scan each of MS3SEG"]),
    ("§5.7", "Candidate extraction (18 min on 7 workers), the analysis (6 min)", "RESULTS", ["candidates 18 min (7 workers), analysis 6 min"]),
    ("§6.9", "counted 20 resplits of the same 30 scans as independent", "ADDENDUM", ["the 200 were 20 re-splits of 30 scans"]),
    ("App. B", "(0/30, one-sided bound 9.5 %)", "ADDENDUM", ["0/30 distinct scans (one-sided 95 % upper bound 9.5 %)"]),
    ("§6.9", 'first "0/200 (95 % CI ≤ 1.8 %)"', "ADDENDUM", ['"0 of 200 healthy scans certified as DIS, 95 % CI ≤ 1.8 %"']),
    ("App. B", '("7–13× the floor"', "DRAFT", ['"7–13× the floor"']),
    ("§9", "(brains about 2.0 L)", "RESULTS", ["brains ≈ 2.0 L"]),
    ("§9", "about 20 uncontrolled centres", "RESULTS", ["Muslim spans ~20 uncontrolled centres"]),
]
for sec, ms_snip, doc, phrases in DOCCLAIMS:
    c(sec, ms_snip, doc, "phrase(s) present in " + doc + ": " + " · ".join(phrases),
      (lambda ph=tuple(phrases), dd=doc: [norm(x) in norm(DOCS[dd]) for x in ph]), "docbool")

c("§5.4", "2000 resamples", "R", "n_boot", lambda: [R["n_boot"]])
c("§5.4", "Bonferroni intervals (level 1 − 0.05/32", "R", "level from the number of primary cells; n_boot_bonferroni = 20000",
  lambda: [1, 0.05, len(R["primary"])] if R["n_boot_bonferroni"] == 20000 else [None])
c("§5.4", "(500 resamples)", "R", "n_boot_two_level", lambda: [R["n_boot_two_level"]])
c("§5.7", "(20261021, 20261024 and 20261031)", "R, C, M", "seed", lambda: [R["seed"], C["seed"], M["seed"]])
c("§5.7", "(2096109e…a6f4ec)", "R, M", "cache.sha256",
  lambda: [R["cache"]["sha256"].startswith("2096109e") and R["cache"]["sha256"].endswith("a6f4ec") and M["cache_sha256"] == R["cache"]["sha256"]], "bool")
c("§5.7", "The metric functions have 33 unit tests", "pytest", "python -m pytest research/paper_a/test_v03_metrics.py (33 passed, run 2026-10-31)",
  lambda: [33 if "33 passed" in subprocess.run([sys.executable, "-m", "pytest", "-q", os.path.join(ROOT, "research", "paper_a", "test_v03_metrics.py")],
                                                capture_output=True, text=True, cwd=ROOT).stdout else None])
c("§5.7", "(for example, 3402 MS3SEG candidates, 1162 false)", "R", "descriptive['ens|ms3seg'].candidates, .false",
  lambda: [DESC["ms3seg"]["candidates"], DESC["ms3seg"]["false"]])
c("§5.2", "125/125 scans had identical candidate counts and 4400/4400 candidates had identical one-to-one labels", "G",
  "gate_G1 scans_same_candidate_count/scans_compared; candidates_compared × lenient_label_agreement",
  lambda: [G["gate_G1"]["scans_same_candidate_count"], G["gate_G1"]["scans_compared"],
           round(G["gate_G1"]["candidates_compared"] * G["gate_G1"]["lenient_label_agreement"]), G["gate_G1"]["candidates_compared"]])
c("§5.2", "One candidate's score differed by 0.0078, above the 0.003 tolerance", "G", "gate_G1.max_abs_score_diff; tolerance (protocol §12)",
  lambda: [G["gate_G1"]["max_abs_score_diff"], 0.003])

# ---- 6.1
c("§6.1", "Every single fold ranked candidates with AUROC 0.67–0.76", "R", "q3.auroc f0..f4 all sites (min, max)", lambda: [min(FOLD_AUC), max(FOLD_AUC)])
c("§6.1", "The 5-fold mean reached 0.78–0.82 at every site", "R", "q3.auroc ens_mean (min, max)", lambda: [5, min(ENS_AUC), max(ENS_AUC)])
c("§6.1", "Candidate precision without selection was 0.63–0.84", "R", "descriptive candidate_precision (min, max)",
  lambda: [min(DESC[s]["candidate_precision"] for s in SITES), max(DESC[s]["candidate_precision"] for s in SITES)])
c("§6.1", "8.2–11.6 false candidates per scan", "R", "descriptive false_per_scan (min, max)",
  lambda: [min(DESC[s]["false_per_scan"] for s in SITES), max(DESC[s]["false_per_scan"] for s in SITES)])
c("§6.1", "almost as well as the mean (AUROC 0.77–0.81)", "R", "q3.auroc ens_neg_fold_sd (min, max)", lambda: [min(SD_AUC), max(SD_AUC)])

# ---- 6.2
c("§6.2", "On Muslim at α = 0.1 the result is undecided: 0.122 [0.062, 0.197]", "R", "primary D3|muslim|P1|0.1",
  lambda: [0.1, *est_ci(cell("D3", "muslim", "P1", 0.1))])
c("§6.2", "Ljubljana-10 (10 patients) and PediMS (9) are small", "R", "descriptive patients",
  lambda: [10, DESC["openms"]["patients"], DESC["pedims"]["patients"]])
c("§6.2", "On MS3SEG at α = 0.1, the estimate (0.107 [0.075, 0.145]) is above α", "R", "primary D3|ms3seg|P1|0.1",
  lambda: [0.1, *est_ci(cell("D3", "ms3seg", "P1", 0.1))])
c("§6.2", "The two-level bootstrap gave 0.101 [0.070, 0.136] (MS3SEG) and 0.104 [0.042, 0.182] (Muslim) at α = 0.1", "R",
  "primary_two_level_bootstrap D3|ms3seg|P1|0.1, D3|muslim|P1|0.1",
  lambda: [R["primary_two_level_bootstrap"]["D3|ms3seg|P1|0.1"]["mean"], *R["primary_two_level_bootstrap"]["D3|ms3seg|P1|0.1"]["ci95"],
           R["primary_two_level_bootstrap"]["D3|muslim|P1|0.1"]["mean"], *R["primary_two_level_bootstrap"]["D3|muslim|P1|0.1"]["ci95"], 0.1])
c("§6.2", "was 0.041 on MS3SEG and 0.038 on Muslim", "R", "designs['ens|D1']['P1|0.1'][site].mean_fdp",
  lambda: [dsg("ens|D1", "P1|0.1", "ms3seg")["mean_fdp"], dsg("ens|D1", "P1|0.1", "muslim")["mean_fdp"]])
c("§6.2", "α·π0 = 0.034 and 0.037", "PH", "0.1 × alpha_pi0|site.mean_pi0",
  lambda: [0.1 * PH["alpha_pi0|ms3seg"]["mean_pi0"], 0.1 * PH["alpha_pi0|muslim"]["mean_pi0"]])
c("§6.2", "realised FDR was 0.107 and 0.122, that is 2.6–3.2 times higher", "R", "primary D3 P1 0.1 estimates; ratios to D1",
  lambda: [cell("D3", "ms3seg", "P1", 0.1)["estimate"], cell("D3", "muslim", "P1", 0.1)["estimate"],
           cell("D3", "ms3seg", "P1", 0.1)["estimate"] / dsg("ens|D1", "P1|0.1", "ms3seg")["mean_fdp"],
           cell("D3", "muslim", "P1", 0.1)["estimate"] / dsg("ens|D1", "P1|0.1", "muslim")["mean_fdp"]])
c("§6.2", "(51 of 151 scans; mean π0 0.52)", "PH", "pi0_subset …pi0>=0.4 .scans, pi0>=0.0 .scans, mean_pi0",
  lambda: [PH["pi0_subset|ms3seg+muslim|P1|0.1|pi0>=0.4"]["scans"], PH["pi0_subset|ms3seg+muslim|P1|0.1|pi0>=0.0"]["scans"],
           PH["pi0_subset|ms3seg+muslim|P1|0.1|pi0>=0.4"]["mean_pi0"]])
c("§6.2", "realised FDR at α = 0.1 was **0.196 [0.120, 0.282]** with 1-mm calibration, against 0.050 [0.011, 0.103]", "PH",
  "pi0_subset …|P1|0.1|pi0>=0.4 D3_1mm_calibrated / D1_within_site",
  lambda: [0.1, PH["pi0_subset|ms3seg+muslim|P1|0.1|pi0>=0.4"]["D3_1mm_calibrated"]["realised_fdr"], *PH["pi0_subset|ms3seg+muslim|P1|0.1|pi0>=0.4"]["D3_1mm_calibrated"]["ci95"],
           1, PH["pi0_subset|ms3seg+muslim|P1|0.1|pi0>=0.4"]["D1_within_site"]["realised_fdr"], *PH["pi0_subset|ms3seg+muslim|P1|0.1|pi0>=0.4"]["D1_within_site"]["ci95"]])
c("§6.2", "(24 scans) it was 0.225 [0.101, 0.366]", "PH", "pi0_subset …|P1|0.1|pi0>=0.5",
  lambda: [PH["pi0_subset|ms3seg+muslim|P1|0.1|pi0>=0.5"]["scans"], PH["pi0_subset|ms3seg+muslim|P1|0.1|pi0>=0.5"]["D3_1mm_calibrated"]["realised_fdr"],
           *PH["pi0_subset|ms3seg+muslim|P1|0.1|pi0>=0.5"]["D3_1mm_calibrated"]["ci95"]])
c("§6.2", "selected 34 candidates (sensitivity 0.010); within-site calibration selected 358 (sensitivity 0.102)", "R",
  "primary D2|mslesseg|P1|0.1 n_sel, sens; designs ens|D1 P1|0.1 mslesseg",
  lambda: [cell("D2", "mslesseg", "P1", 0.1)["n_sel"], cell("D2", "mslesseg", "P1", 0.1)["sens_e2e"],
           dsg("ens|D1", "P1|0.1", "mslesseg")["n_sel"], dsg("ens|D1", "P1|0.1", "mslesseg")["sens_e2e"]])
c("§6.2", "(Muslim α = 0.1: 0.068 [0.026, 0.122])", "R", "sensitivity['consensus_score|D3|muslim|P1|0.1']",
  lambda: [0.1, *est_ci(R["sensitivity"]["consensus_score|D3|muslim|P1|0.1"])])
c("§6.2", "(MS3SEG γ = 0.1: 0.14 [0.08, 0.22], inconclusive)", "R", "sensitivity['consensus_score|D3|ms3seg|P2|0.1']",
  lambda: [0.1, *est_ci(R["sensitivity"]["consensus_score|D3|ms3seg|P2|0.1"])])
c("§6.2", "sensitivity on the thick sites was 0.296 with S_cons and 0.341 with the ensemble mean", "R",
  "Σ_site sens(consensus D3 P1 0.2) × detectable / Σ detectable; q3 paired D3|ALL|P1|0.2 sens a",
  lambda: [pooled_cons_sens(), paired("D3|ALL|P1|0.2")["sens_e2e"]["a"]])

# ---- 6.3
c("§6.3", "(λ̂ = 0.965)", "PH, CAL", "ens|P2_threshold_1mm_calibrated", lambda: [PH["ens|P2_threshold_1mm_calibrated"]])
c("§6.3", "**21 % [13, 30] of MS3SEG scans (γ = 0.1) and 29 % [17, 44] / 27 % [16, 42] of Muslim scans (γ = 0.1 / 0.2)", "R",
  "primary D3 P2 cells ×100",
  lambda: [*pct(est_ci(cell("D3", "ms3seg", "P2", 0.1))), 0.1, *pct(est_ci(cell("D3", "muslim", "P2", 0.1))),
           *pct(est_ci(cell("D3", "muslim", "P2", 0.2))), 0.1, 0.2])
c("§6.3", "only Muslim at γ = 0.1 stays violated ([0.12, 0.52])", "R", "primary D3|muslim|P2|0.1 ci_bonferroni",
  lambda: [0.1, *cell("D3", "muslim", "P2", 0.1)["ci_bonferroni"]])
c("§6.3", "(0.20 [0.10, 0.30])", "R", "primary_two_level_bootstrap D3|ms3seg|P2|0.1",
  lambda: [R["primary_two_level_bootstrap"]["D3|ms3seg|P2|0.1"]["mean"], *R["primary_two_level_bootstrap"]["D3|ms3seg|P2|0.1"]["ci95"]])
c("§6.3", "(0.27 [0.12, 0.41] and 0.25 [0.12, 0.37])", "R", "primary_two_level_bootstrap D3|muslim|P2|0.1, 0.2",
  lambda: [R["primary_two_level_bootstrap"]["D3|muslim|P2|0.1"]["mean"], *R["primary_two_level_bootstrap"]["D3|muslim|P2|0.1"]["ci95"],
           R["primary_two_level_bootstrap"]["D3|muslim|P2|0.2"]["mean"], *R["primary_two_level_bootstrap"]["D3|muslim|P2|0.2"]["ci95"]])
c("§6.3", "6.1 % on MSLesSeg and 10 % on Ljubljana-10, but 24 % on MS3SEG and 29.4 % on Muslim", "PH",
  "ens|site.scans_with_false_candidate_above_1mm_P2_threshold ×100",
  lambda: [*pct([PH["ens|mslesseg"]["scans_with_false_candidate_above_1mm_P2_threshold"], PH["ens|openms"]["scans_with_false_candidate_above_1mm_P2_threshold"]]), 10,
                 *pct([PH["ens|ms3seg"]["scans_with_false_candidate_above_1mm_P2_threshold"], PH["ens|muslim"]["scans_with_false_candidate_above_1mm_P2_threshold"]])])
c("§6.3", "D = 0.107 on MS3SEG (p = 0.0005, the smallest attainable with 2000 permutations), D = 0.094 on Muslim (p = 0.025) and D = 0.057 on PediMS (p = 0.51)",
  "R", "mechanism ens|site_vs_1mm|scan_clustered_KS (D, p, n_perm); 1/(n_perm+1)",
  lambda: [R["mechanism"]["ens|ms3seg_vs_1mm|scan_clustered_KS"]["D"], R["mechanism"]["ens|ms3seg_vs_1mm|scan_clustered_KS"]["p"],
           R["mechanism"]["ens|ms3seg_vs_1mm|scan_clustered_KS"]["n_perm"],
           R["mechanism"]["ens|muslim_vs_1mm|scan_clustered_KS"]["D"], R["mechanism"]["ens|muslim_vs_1mm|scan_clustered_KS"]["p"],
           R["mechanism"]["ens|pedims_vs_1mm|scan_clustered_KS"]["D"], R["mechanism"]["ens|pedims_vs_1mm|scan_clustered_KS"]["p"]])
c("§6.3", "for 22–51 % of calibration scans", "PH", "ens|site.safe_threshold_above_top_false_candidate_gamma_0.2 (min, max) ×100",
  lambda: pct([min(PH[f"ens|{s}"]["safe_threshold_above_top_false_candidate_gamma_0.2"] for s in SITES),
               max(PH[f"ens|{s}"]["safe_threshold_above_top_false_candidate_gamma_0.2"] for s in SITES)]))

# ---- 6.4
for s, a, txt in [("ms3seg", 0.1, "(α = 0.1: 0.164 [0.136, 0.196]"), ("ms3seg", 0.2, "α = 0.2: 0.230 [0.206, 0.255])"),
                  ("muslim", 0.1, "(0.144 [0.107, 0.180])")]:
    c("§6.4", txt, "R", f"designs['ens|D3']['B1|{a}'][{s}] mean_fdp, ci",
      (lambda s=s, a=a, txt=txt: ([a] if txt.startswith("(α") or txt.startswith("α") else []) +
       [dsg("ens|D3", f"B1|{a}", s)["mean_fdp"], *dsg("ens|D3", f"B1|{a}", s)["mean_fdp_ci"]]))
c("§6.4", "violated on Muslim at α = 0.1 (0.180 [0.103, 0.265])", "R", "designs['ens|D3']['B2|0.1'].muslim",
  lambda: [0.1, dsg("ens|D3", "B2|0.1", "muslim")["mean_fdp"], *dsg("ens|D3", "B2|0.1", "muslim")["mean_fdp_ci"]])
c("§6.4", "with Muslim at α = 0.1 inconclusive (0.134 [0.062, 0.226])", "R", "designs['ens|D3']['B3|0.1'].muslim",
  lambda: [0.1, dsg("ens|D3", "B3|0.1", "muslim")["mean_fdp"], *dsg("ens|D3", "B3|0.1", "muslim")["mean_fdp_ci"]])
c("§6.4", "(0.490, 0.361 and 0.499 against 0.404, 0.235 and 0.326 on MS3SEG, Muslim and PediMS)", "R",
  "designs['ens|D3']['B3|0.2'] / ['P1|0.2'] sens_e2e",
  lambda: [dsg("ens|D3", "B3|0.2", s)["sens_e2e"] for s in ("ms3seg", "muslim", "pedims")] + [dsg("ens|D3", "P1|0.2", s)["sens_e2e"] for s in ("ms3seg", "muslim", "pedims")])
c("§6.4", "with realised FDR closer to α (0.181, 0.159, 0.114)", "R", "designs['ens|D3']['B3|0.2'] mean_fdp",
  lambda: [dsg("ens|D3", "B3|0.2", s)["mean_fdp"] for s in ("ms3seg", "muslim", "pedims")])
c("§6.4", "it found fewer (0.092, 0.019, 0.039)", "R", "designs['ens|D3']['B3|0.1'] sens_e2e",
  lambda: [dsg("ens|D3", "B3|0.1", s)["sens_e2e"] for s in ("ms3seg", "muslim", "pedims")])
c("§6.4", "B3 (Learn-then-Test, per-scan FDP loss)** had no violated D3 or D2 cell", "R", "classify(designs ens|D3, ens|D2 B3 cells)",
  lambda: [all(not (dsg(f"ens|{d}", f"B3|{a}", s)["mean_fdp_ci"][0] > a) for d in ("D3", "D2") for a in (0.1, 0.2)
               for s in R["designs"][f"ens|{d}"][f"B3|{a}"])], "bool")
c("§6.4", "(MS3SEG α = 0.1: 0.065 [0.048, 0.086]; Muslim: 0.028 [0.014, 0.045])", "M", "B_baselines SUB|D3|site|0.1",
  lambda: [0.1, *est_ci(SUBD["SUB|D3|ms3seg|0.1"]), *est_ci(SUBD["SUB|D3|muslim|0.1"])])
c("§6.4", "(MS3SEG 0.193 against 0.258)", "M, R", "SUB|D3|ms3seg|0.1 sens; primary D3|ms3seg|P1|0.1 sens",
  lambda: [SUBD["SUB|D3|ms3seg|0.1"]["sens_e2e"], cell("D3", "ms3seg", "P1", 0.1)["sens_e2e"]])
c("§6.4", "ranged from 0.004 to 0.115, and 14.5 % of draws exceeded α", "M", "SUB|D3|ms3seg|0.1 realised_fdr_draws_q025_q975; share_draws_above_alpha ×100",
  lambda: [*SUBD["SUB|D3|ms3seg|0.1"]["realised_fdr_draws_q025_q975"], 100 * SUBD["SUB|D3|ms3seg|0.1"]["share_draws_above_alpha"]])
c("§6.4", "**SUB** (one false candidate per calibration patient) had no violated cell in D3 or D2", "M", "B_baselines SUB|* class",
  lambda: [all(v["class"] != "violated" for k, v in SUBD.items() if k.startswith("SUB|"))], "bool")
c("§6.4", "With K = 85 calibration patients its e-values are at most K + 1 = 86", "M", "LRhier|D3|*.calibration_groups",
  lambda: [SUBD["LRhier|D3|ms3seg|0.1"]["calibration_groups"], 1, SUBD["LRhier|D3|ms3seg|0.1"]["calibration_groups"] + 1])
c("§6.4", "selected nothing in every D3 cell", "M", "LRhier|D3|* n_sel == 0",
  lambda: [all(v["n_sel"] == 0 for k, v in SUBD.items() if k.startswith("LRhier|D3"))], "bool")
c("§6.4", "In D2, with 145–236 calibration patients, it selected in 3 of 10 cells", "M", "LRhier|D2|* calibration_groups (min, max); count n_sel>0; cells",
  lambda: [min(v["calibration_groups"] for k, v in SUBD.items() if k.startswith("LRhier|D2")),
           max(v["calibration_groups"] for k, v in SUBD.items() if k.startswith("LRhier|D2")),
           sum(v["n_sel"] > 0 for k, v in SUBD.items() if k.startswith("LRhier|D2")),
           sum(1 for k in SUBD if k.startswith("LRhier|D2"))])
c("§6.4", "On MS3SEG at α = 0.2, the batch FDP was 0.202 and the mean per-scan FDP 0.212 [0.188, 0.239], at sensitivity 0.559", "M",
  "LRhier|D2|ms3seg|0.2 batch_fdp, estimate, ci95, sens_e2e",
  lambda: [0.2, SUBD["LRhier|D2|ms3seg|0.2"]["batch_fdp"], *est_ci(SUBD["LRhier|D2|ms3seg|0.2"]), SUBD["LRhier|D2|ms3seg|0.2"]["sens_e2e"]])

# ---- 6.5
c("§6.5", "Ljubljana-10 contributed 82 of the 1339 false candidates in the 1-mm null", "R, CAL",
  "descriptive['ens|openms'].false; descriptive false (MSLesSeg + Ljubljana)",
  lambda: [10, DESC["openms"]["false"], DESC["openms"]["false"] + DESC["mslesseg"]["false"], 1])
c("§6.5", "Removing Ljubljana from every pool changed no class in D3 or D2", "M", "A_site_seen_sensitivity class == preregistered class",
  lambda: [all(v["class"] == v["preregistered_with_Ljubljana"]["class"] for v in M["A_site_seen_sensitivity"].values() if "preregistered_with_Ljubljana" in v)], "bool")
c("§6.5", "the D3 estimate moved from 0.107 to 0.098 [0.071, 0.131]", "M", "A D3-noLj|ms3seg|P1|0.1",
  lambda: [cell("D3", "ms3seg", "P1", 0.1)["estimate"], *est_ci(M["A_site_seen_sensitivity"]["D3-noLj|ms3seg|P1|0.1"])])
c("§6.5", "Muslim at α = 0.1 stayed at 0.122 [0.062, 0.197]", "M", "A D3-noLj|muslim|P1|0.1",
  lambda: [0.1, *est_ci(M["A_site_seen_sensitivity"]["D3-noLj|muslim|P1|0.1"])])
c("§6.5", "because the MSLesSeg-only threshold is also 0.965", "M, CAL", "A D3-noLj|*|P2 threshold; CAL",
  lambda: [M["A_site_seen_sensitivity"]["D3-noLj|ms3seg|P2|0.1"]["threshold"]])

# ---- 6.6
c("§6.6", "realised FDR rose from 0.018 (≤ 1.5 mm grid) to 0.050 (3.9 mm), 0.101 (4.5–6.5 mm) and 0.120 (> 6.5 mm)", "R",
  "thickness['D2|by_band']['P1|0.2'][B1..B4].mean_fdp (band labels fixed in the protocol)",
  lambda: [BB["P1|0.2"]["B1"]["mean_fdp"], 1.5, BB["P1|0.2"]["B2"]["mean_fdp"], 3.9, BB["P1|0.2"]["B3"]["mean_fdp"], 4.5, 6.5,
           BB["P1|0.2"]["B4"]["mean_fdp"], 6.5])
c("§6.6", "The share of scans with FDP > 0.1 rose from 6 % to 14 %, 30 % and 49 %", "R", "thickness['D2|by_band']['P1|0.2'][band]['fdp_gt_0.1'].frac ×100",
  lambda: [0.1] + pct([BB["P1|0.2"][b]["fdp_gt_0.1"]["frac"] for b in ("B1", "B2", "B3", "B4")]))
c("§6.6", "On MS3SEG, realised FDR went from 0.103 (4.5–6.5 mm) to 0.121 (> 6.5 mm)", "PH", "thickness_gradient|ms3seg|D2|P1|0.2 mean_fdp_slice_le/gt_6.5",
  lambda: [PH["thickness_gradient|ms3seg|D2|P1|0.2"]["mean_fdp_slice_le_6.5"], 4.5, 6.5, PH["thickness_gradient|ms3seg|D2|P1|0.2"]["mean_fdp_slice_gt_6.5"], 6.5])
c("§6.6", "On Muslim it went from 0.100 to 0.102, with only 6 scans above 6.5 mm", "PH", "thickness_gradient|muslim|D2|P1|0.2",
  lambda: [PH["thickness_gradient|muslim|D2|P1|0.2"]["mean_fdp_slice_le_6.5"], PH["thickness_gradient|muslim|D2|P1|0.2"]["mean_fdp_slice_gt_6.5"],
           PH["thickness_gradient|muslim|D2|P1|0.2"]["scans_gt_6.5"], 6.5])
c("§6.6", "(Spearman ρ = 0.03, p = 0.75); on Muslim, ρ = 0.30 (p = 0.035)", "PH", "thickness_gradient|site spearman_rho, perm_p",
  lambda: [PH["thickness_gradient|ms3seg|D2|P1|0.2"]["spearman_rho_slice_vs_scan_fdp"], PH["thickness_gradient|ms3seg|D2|P1|0.2"]["perm_p_two_sided"],
           PH["thickness_gradient|muslim|D2|P1|0.2"]["spearman_rho_slice_vs_scan_fdp"], PH["thickness_gradient|muslim|D2|P1|0.2"]["perm_p_two_sided"]])
c("§6.6", "median 108–117 mm³, against 68 mm³ on MSLesSeg and 20 mm³ on Ljubljana", "PH", "lesions|site.volume_mm3_median",
  lambda: [PH["lesions|ms3seg"]["volume_mm3_median"], PH["lesions|muslim"]["volume_mm3_median"], PH["lesions|mslesseg"]["volume_mm3_median"], PH["lesions|openms"]["volume_mm3_median"]])
c("§6.6", "lesions of at least 50 mm³ (about 4.6 mm across) were found 59–76 % of the time", "R",
  "size_bins B3, B4 sens_raw bins 50–150, 150–500, ≥ 500 (min, max) ×100; sphere diameter of 50 mm³",
  lambda: [50, (6 * 50 / math.pi) ** (1 / 3), 100 * min(thick_bins(2) + thick_bins(3) + thick_bins(4)), 100 * max(thick_bins(2) + thick_bins(3) + thick_bins(4))])
c("§6.6", "lesions of 14–50 mm³ were found 43–45 % of the time", "R", "size_bins B3, B4 sens_raw[1] ×100",
  lambda: [14, 50, 100 * min(thick_bins(1)), 100 * max(thick_bins(1))])
c("§6.6", "lesions under 14 mm³ were found 13–21 % of the time", "R", "size_bins B3, B4 sens_raw[0] ×100",
  lambda: [14, 100 * min(thick_bins(0)), 100 * max(thick_bins(0))])
c("§6.6", "On the 1-mm grid, 80 % was reached from 50 mm³", "R", "size_bins['B1|D2|P1|0.2'].min_reliable_raw_0.8",
  lambda: [1, 80, SB["B1|D2|P1|0.2"]["min_reliable_raw_0.8"][0]])
c("§6.6", "only for lesions of at least 500 mm³ on slices thicker than 6.5 mm", "R", "size_bins B4 sens_selected (first ≥ 0.5 bin edge)",
  lambda: [SB["B4|D2|P1|0.2"]["bins_mm3"][min(i for i, v in enumerate(SB["B4|D2|P1|0.2"]["sens_selected"]) if v > 0.5)], 6.5])
c("§6.6", "The PediMS band missed 0.8 by a small margin on 93 lesions (≥ 500 mm³: 0.796)", "R", "size_bins['B2|D2|P1|0.2'] n_lesions[4], sens_raw[4]",
  lambda: [0.8, SB["B2|D2|P1|0.2"]["n_lesions"][4], 500, SB["B2|D2|P1|0.2"]["sens_raw"][4]])
c("§6.6", "0.74 at 2–2.3 mm (43 scans), 0.65 at 3 mm (52) and 0.39 at 4–5 mm (15)", "N", "group|… raw_sensitivity_by_size_bin[1], scans",
  lambda: [N["group|2-2.3 mm"]["raw_sensitivity_by_size_bin"][1], 2, 2.3, N["group|2-2.3 mm"]["scans"],
           N["group|3 mm"]["raw_sensitivity_by_size_bin"][1], 3, N["group|3 mm"]["scans"],
           N["group|4-5 mm"]["raw_sensitivity_by_size_bin"][1], 4, 5, N["group|4-5 mm"]["scans"]])
c("§6.6", "between 50 and 150 mm³: at a volume scale of 1.1, its 50–150 mm³ bin falls to 0.487", "R",
  "size_bins['site:muslim|volx1.1|D2|P1|0.2'] sens_raw[2]; min_reliable_raw_0.5 at ×0.9/×1.0/×1.1",
  lambda: [SB["site:muslim|D2|P1|0.2"]["min_reliable_raw_0.5"][0], SB["site:muslim|volx1.1|D2|P1|0.2"]["min_reliable_raw_0.5"][0], 1.1, 50, 150,
           SB["site:muslim|volx1.1|D2|P1|0.2"]["sens_raw"][2]])

# ---- 6.7
c("§6.7", "leave-one-site-out: 0.203 against 0.102 (Δ +0.101 [0.074, 0.129])", "R", "paired D2|ALL|P1|0.2 sens_e2e",
  lambda: [paired("D2|ALL|P1|0.2")["sens_e2e"][k] for k in ("a", "b", "diff")] + paired("D2|ALL|P1|0.2")["sens_e2e"]["ci95"])
c("§6.7", "1-mm → thick: 0.341 against 0.194 (Δ +0.147 [0.117, 0.177])", "R", "paired D3|ALL|P1|0.2 sens_e2e",
  lambda: [1] + [paired("D3|ALL|P1|0.2")["sens_e2e"][k] for k in ("a", "b", "diff")] + paired("D3|ALL|P1|0.2")["sens_e2e"]["ci95"])
c("§6.7", "(1-mm → thick: 0.110 against 0.178)", "R", "paired D3|ALL|P1|0.2 mean_fdp a, b",
  lambda: [1, paired("D3|ALL|P1|0.2")["mean_fdp"]["a"], paired("D3|ALL|P1|0.2")["mean_fdp"]["b"]])
c("§6.7", "sensitivity went from 0.054 to 0.082 (Δ +0.028 [0.016, 0.042])", "R", "paired D2|ALL|P1|0.1 sens_e2e b, a, diff, ci",
  lambda: [paired("D2|ALL|P1|0.1")["sens_e2e"][k] for k in ("b", "a", "diff")] + paired("D2|ALL|P1|0.1")["sens_e2e"]["ci95"])
c("§6.7", "1-mm → thick, α = 0.1: 0.201 [0.166, 0.242]", "R", "q3.f0_primary_cells D3|ms3seg P1 0.1",
  lambda: [1, 0.1] + est_ci([x for x in R["q3"]["f0_primary_cells"] if x["cell"] == "D3|ms3seg" and x["procedure"] == "P1" and x["target"] == 0.1][0]))
c("§6.7", "1-mm → thick, α = 0.2: 0.225 [0.193, 0.260]", "R", "q3.f0_primary_cells D3|ms3seg P1 0.2",
  lambda: [1, 0.2] + est_ci([x for x in R["q3"]["f0_primary_cells"] if x["cell"] == "D3|ms3seg" and x["procedure"] == "P1" and x["target"] == 0.2][0]))
c("§6.7", "leave-one-site-out, α = 0.1: 0.176 [0.139, 0.216]", "R", "q3.f0_primary_cells D2|ms3seg P1 0.1",
  lambda: [0.1] + est_ci([x for x in R["q3"]["f0_primary_cells"] if x["cell"] == "D2|ms3seg" and x["procedure"] == "P1" and x["target"] == 0.1][0]))
c("§6.7", "every MS3SEG P2 cell (FDX 0.39–0.62)", "R", "q3.f0_primary_cells *|ms3seg P2 estimates (min, max)",
  lambda: [min(x["estimate"] for x in R["q3"]["f0_primary_cells"] if x["cell"].endswith("ms3seg") and x["procedure"] == "P2"),
           max(x["estimate"] for x in R["q3"]["f0_primary_cells"] if x["cell"].endswith("ms3seg") and x["procedure"] == "P2")])
c("§6.7", "The ensemble removed these five violated cells", "R", "q3.verdict.violations_removed_by_ensemble (count)",
  lambda: [len(R["q3"]["verdict"]["violations_removed_by_ensemble"])], "word:5")
c("§6.7", "it reached 0.122 against 0.052 (Δ +0.070 [0.012, 0.143])", "R", "paired D3|muslim|P1|0.1 mean_fdp",
  lambda: [paired("D3|muslim|P1|0.1")["mean_fdp"][k] for k in ("a", "b", "diff")] + paired("D3|muslim|P1|0.1")["mean_fdp"]["ci95"])
c("§6.7", "It also created two new violated cells (Muslim, P2)", "R", "q3.verdict.violations_new_with_ensemble (count)",
  lambda: [len(R["q3"]["verdict"]["violations_new_with_ensemble"])], "word:2")
c("§6.7", "fold 0 had selected almost nothing (sensitivity 0.002–0.035)", "R",
  "fold-0 sensitivity in the Muslim comparisons where the ensemble had higher FDR: paired D3/D2 P1 0.1, D2 P1 0.2 (b); f0_primary_cells D3|muslim P2 (min, max)",
  lambda: [0, min(paired("D3|muslim|P1|0.1")["sens_e2e"]["b"], paired("D2|muslim|P1|0.1")["sens_e2e"]["b"], paired("D2|muslim|P1|0.2")["sens_e2e"]["b"],
                  [x for x in R["q3"]["f0_primary_cells"] if x["cell"] == "D3|muslim" and x["procedure"] == "P2"][0]["sens_e2e"]),
           max(paired("D3|muslim|P1|0.1")["sens_e2e"]["b"], paired("D2|muslim|P1|0.1")["sens_e2e"]["b"], paired("D2|muslim|P1|0.2")["sens_e2e"]["b"],
               [x for x in R["q3"]["f0_primary_cells"] if x["cell"] == "D3|muslim" and x["procedure"] == "P2"][0]["sens_e2e"])])
c("§6.7", "it reached 0.082 against 0.020 at α = 0.1 (Δ [0.017, 0.121]) and 0.100 against 0.044 at α = 0.2 (Δ [0.006, 0.116])", "R",
  "paired D2|muslim|P1|0.1 / 0.2 mean_fdp a, b, ci95",
  lambda: [paired("D2|muslim|P1|0.1")["mean_fdp"]["a"], paired("D2|muslim|P1|0.1")["mean_fdp"]["b"], 0.1, *paired("D2|muslim|P1|0.1")["mean_fdp"]["ci95"],
           paired("D2|muslim|P1|0.2")["mean_fdp"]["a"], paired("D2|muslim|P1|0.2")["mean_fdp"]["b"], 0.2, *paired("D2|muslim|P1|0.2")["mean_fdp"]["ci95"]])
c("§6.7", "(1-mm → thick, P1 α = 0.2: realised FDR 0.157–0.176)", "R", "designs f1..f4|D3 P1|0.2 pooled over thick sites (scan-weighted mean FDP)",
  lambda: [1, 0.2] + [min(sum(R["designs"][f"f{k}|D3"]["P1|0.2"][s]["mean_fdp"] * R["designs"][f"f{k}|D3"]["P1|0.2"][s]["scans"] for s in ("ms3seg", "muslim", "pedims"))
                              / sum(R["designs"][f"f{k}|D3"]["P1|0.2"][s]["scans"] for s in ("ms3seg", "muslim", "pedims")) for k in range(1, 5)),
                          max(sum(R["designs"][f"f{k}|D3"]["P1|0.2"][s]["mean_fdp"] * R["designs"][f"f{k}|D3"]["P1|0.2"][s]["scans"] for s in ("ms3seg", "muslim", "pedims"))
                              / sum(R["designs"][f"f{k}|D3"]["P1|0.2"][s]["scans"] for s in ("ms3seg", "muslim", "pedims")) for k in range(1, 5))])
c("§6.7", "fell from 16–32 % (fold 0) to 3–6 % (ensemble) at every site", "PH", "arm|site.false_candidates_score_ge_0.95 ×100 (min, max)",
  lambda: [*pct([min(PH[f"f0|{s}"]["false_candidates_score_ge_0.95"] for s in SITES), max(PH[f"f0|{s}"]["false_candidates_score_ge_0.95"] for s in SITES)]), 0,
           *pct([min(PH[f"ens|{s}"]["false_candidates_score_ge_0.95"] for s in SITES), max(PH[f"ens|{s}"]["false_candidates_score_ge_0.95"] for s in SITES)])])
c("§6.7", "(MSLesSeg AUROC 0.737 against 0.758)", "R", "lstai['auroc|lstai|mslesseg'], ['auroc|lstai_m1|mslesseg']",
  lambda: [R["lstai"]["auroc|lstai|mslesseg"]["auroc"], R["lstai"]["auroc|lstai_m1|mslesseg"]["auroc"]])
c("§6.7", "(candidate precision 0.45 against 0.25)", "R", "lstai.descriptive lstai|mslesseg / lstai_m1|mslesseg candidate_precision",
  lambda: [R["lstai"]["descriptive"]["lstai|mslesseg"]["candidate_precision"], R["lstai"]["descriptive"]["lstai_m1|mslesseg"]["candidate_precision"]])
c("§6.7", "(0.102 against 0.017)", "R", "lstai['lstai|D1'] / ['lstai_m1|D1'] P1|0.2 mslesseg sens_e2e",
  lambda: [R["lstai"]["lstai|D1"]["P1|0.2"]["mslesseg"]["sens_e2e"], R["lstai"]["lstai_m1|D1"]["P1|0.2"]["mslesseg"]["sens_e2e"]])

# ---- 6.8
c("§6.8", "realised FDR was 0.034–0.075 and sensitivity 0.14–0.31", "R", "designs ens|D1 P1|0.2 mean_fdp, sens_e2e (min, max)",
  lambda: [min(dsg("ens|D1", "P1|0.2", s)["mean_fdp"] for s in SITES), max(dsg("ens|D1", "P1|0.2", s)["mean_fdp"] for s in SITES),
           min(dsg("ens|D1", "P1|0.2", s)["sens_e2e"] for s in SITES), max(dsg("ens|D1", "P1|0.2", s)["sens_e2e"] for s in SITES)])
c("§6.8", "(MS3SEG α = 0.2: realised FDR 0.069, sensitivity 0.183 against 0.198 within site; Muslim: 0.053, 0.150 against 0.163)", "R",
  "q4 site_only|P1|0.2|k=10 realised_mean, sens_e2e_mean; designs ens|D1 P1|0.2 sens",
  lambda: [0.2, q4("ms3seg", "site_only|P1|0.2|k=10")["realised_mean"], q4("ms3seg", "site_only|P1|0.2|k=10")["sens_e2e_mean"], dsg("ens|D1", "P1|0.2", "ms3seg")["sens_e2e"],
           q4("muslim", "site_only|P1|0.2|k=10")["realised_mean"], q4("muslim", "site_only|P1|0.2|k=10")["sens_e2e_mean"], dsg("ens|D1", "P1|0.2", "muslim")["sens_e2e"]])
c("§6.8", "with fewer than 9 calibration patients (δ = 0.1)", "derived", "smallest K with ⌈(K+1)(1−δ)⌉ ≤ K at δ = 0.1",
  lambda: [min(K for K in range(1, 50) if math.ceil((K + 1) * 0.9 - 1e-12) <= K), 0.1])
c("§6.8", "(MS3SEG 0.075, Muslim 0.092)", "R", "q4 site_only|P2|0.1|k=10 realised_mean",
  lambda: [q4("ms3seg", "site_only|P2|0.1|k=10")["realised_mean"], q4("muslim", "site_only|P2|0.1|k=10")["realised_mean"]])
c("§6.8", "**it found 3.85 % (MS3SEG) and 0.65 % (Muslim) of lesions**", "R", "q4 site_only|P2|0.1|k=10 sens_e2e_mean ×100",
  lambda: pct([q4("ms3seg", "site_only|P2|0.1|k=10")["sens_e2e_mean"], q4("muslim", "site_only|P2|0.1|k=10")["sens_e2e_mean"]]))
c("§6.8", "in 30 % and 36 % of draws, FDX exceeded 0.1", "R", "q4 site_only|P2|0.1|k=10 share_draws_above_nominal ×100",
  lambda: pct([q4("ms3seg", "site_only|P2|0.1|k=10")["share_draws_above_nominal"], q4("muslim", "site_only|P2|0.1|k=10")["share_draws_above_nominal"]]) + [0.1])
c("§6.8", "never restored P2 (FDX 0.16–0.28 for k ≤ 40)", "R", "q4 augmented|P2|0.1|k=* realised_mean, MS3SEG + Muslim (min, max)",
  lambda: [min(q4(s, f"augmented|P2|0.1|k={k}")["realised_mean"] for s in ("ms3seg", "muslim") for k in R["q4"][s]["k_grid"]),
           max(q4(s, f"augmented|P2|0.1|k={k}")["realised_mean"] for s in ("ms3seg", "muslim") for k in R["q4"][s]["k_grid"]), 40])
c("§6.8", "Adding local patients to the 85-patient 1-mm pool", "R", "descriptive patients MSLesSeg + Ljubljana-10",
  lambda: [1 if False else DESC["mslesseg"]["patients"] + DESC["openms"]["patients"], 1])

# ---- 6.9
c("§6.9", "**14/100 [7.9, 22.4 %] controls had a reported lesion at α = 0.1 and 24/100 [16.0, 33.6 %] at α = 0.2**", "C", "primary P1|0.1, P1|0.2",
  lambda: [14 if C["primary"]["P1|0.1"]["scans_with_any"] == 14 else None, 100, *pct(C["primary"]["P1|0.1"]["ci95_exact"]), 0.1,
           C["primary"]["P1|0.2"]["scans_with_any"], 100, *pct(C["primary"]["P1|0.2"]["ci95_exact"]), 0.2])
c("§6.9", "P2 flagged 6/100 [2.2, 12.6 %] (holds)", "C", "primary P2|0.1",
  lambda: [C["primary"]["P2|0.1"]["scans_with_any"], 100, *pct(C["primary"]["P2|0.1"]["ci95_exact"])])
c("§6.9", "13/70 (18.6 % [10.3, 29.7])", "C", "operating_points ens|1-mm sites|P1|0.1|new70",
  lambda: [op("ens|1-mm sites|P1|0.1", "new70")["scans_with_any"], op("ens|1-mm sites|P1|0.1", "new70")["n"],
           100 * op("ens|1-mm sites|P1|0.1", "new70")["rate"], *pct(op("ens|1-mm sites|P1|0.1", "new70")["ci95_exact"])])
c("§6.9", "Of the 30 analysed earlier, 1/30 was flagged (**[post hoc]** Fisher exact test, p = 0.06)", "C, derived",
  "operating_points …|august30; scipy fisher_exact([[13, 57], [1, 29]]) two-sided",
  lambda: [op("ens|1-mm sites|P1|0.1", "august30")["n"], op("ens|1-mm sites|P1|0.1", "august30")["scans_with_any"], op("ens|1-mm sites|P1|0.1", "august30")["n"],
           fisher_exact([[op("ens|1-mm sites|P1|0.1", "new70")["scans_with_any"], 70 - op("ens|1-mm sites|P1|0.1", "new70")["scans_with_any"]],
                         [op("ens|1-mm sites|P1|0.1", "august30")["scans_with_any"], 30 - op("ens|1-mm sites|P1|0.1", "august30")["scans_with_any"]]])[1]])
c("§6.9", "the counts were 14/99 and 23/99", "C", "operating_points …|without_sub-075",
  lambda: [op("ens|1-mm sites|P1|0.1", "without_sub-075")["scans_with_any"], op("ens|1-mm sites|P1|0.1", "without_sub-075")["n"],
           op("ens|1-mm sites|P1|0.2", "without_sub-075")["scans_with_any"], op("ens|1-mm sites|P1|0.2", "without_sub-075")["n"]])
c("§6.9", "(all five sites: 5/100 at α = 0.1)", "C", "operating_points ens|all five patient sites|P1|0.1",
  lambda: [op("ens|all five patient sites|P1|0.1")["scans_with_any"], 100, 0.1])
c("§6.9", "5.7 % scored at least 0.95, against 2.7 % of the 1-mm null and 5.6 % of the thick-slice null", "C, PH",
  "share of location_rows_ens scores ≥ 0.95; candidate-weighted share ≥ 0.95 of 1-mm and thick-slice false candidates (posthoc)",
  lambda: [100 * sum(r["score"] >= 0.95 for r in ROWS) / len(ROWS), 0.95, 100 * share_ge95(("mslesseg", "openms")), 1, 100 * share_ge95(("ms3seg", "muslim", "pedims"))])
c("§6.9", "LTT (B3) at α = 0.2 was violated with every pool (29–32/100)", "C", "operating_points ens|*|B3|0.2 (min, max) and classes",
  lambda: [0.2] + [min(op(f"ens|{p}|B3|0.2")["scans_with_any"] for p in ("1-mm sites", "MSLesSeg only", "all five patient sites", "thick-slice sites")),
                   max(op(f"ens|{p}|B3|0.2")["scans_with_any"] for p in ("1-mm sites", "MSLesSeg only", "all five patient sites", "thick-slice sites")), 100]
  if all(op(f"ens|{p}|B3|0.2")["class"] == "violated" for p in ("1-mm sites", "MSLesSeg only", "all five patient sites", "thick-slice sites")) else [None])
c("§6.9", "flagged 59/100 controls at α = 0.1 (violated)", "C", "operating_points f0|1-mm sites|P1|0.1",
  lambda: [op("f0|1-mm sites|P1|0.1")["scans_with_any"], 100, 0.1])
c("§6.9", "The ensemble flagged 14/100; the paired difference was −45 points [−55, −35], with 1 against 46 discordant controls (exact McNemar p < 10⁻⁵)",
  "C", "ensemble_vs_fold0['1-mm sites|P1|0.1'] rate_diff ×100, mcnemar; exact two-sided binomial p computed",
  lambda: [C["ensemble_vs_fold0"]["1-mm sites|P1|0.1"]["ens_scans_with_any"], 100, 100 * C["ensemble_vs_fold0"]["1-mm sites|P1|0.1"]["rate_diff"]["diff"],
           *pct(C["ensemble_vs_fold0"]["1-mm sites|P1|0.1"]["rate_diff"]["ci95_boot"]),
           C["ensemble_vs_fold0"]["1-mm sites|P1|0.1"]["mcnemar"]["ens_only"], C["ensemble_vs_fold0"]["1-mm sites|P1|0.1"]["mcnemar"]["f0_only"],
           10 if 2 * binom.cdf(1, 47, 0.5) < 1e-5 else None, -5])
c("§6.9", "candidate in 85/100 controls (2.63 per scan); fold 0 did so in 93/100", "C", "raw_candidates ens / f0",
  lambda: [C["raw_candidates"]["ens"]["scans_with_any_candidate"], 100, C["raw_candidates"]["ens"]["per_scan_mean"], 0,
           C["raw_candidates"]["f0"]["scans_with_any_candidate"], 100])
c("§6.9", "the rule was met in **19/100 healthy controls (11.8–28.1 %)**; fold 0 met it in 22/100", "C", "app_dis raw ens, raw f0",
  lambda: [dis("raw ens|all100")["dis_met_brain"], 100, *pct(dis("raw ens|all100")["ci95_exact"]), 0, dis("raw f0|all100")["dis_met_brain"], 100])
c("§6.9", "79/100 controls had at least one automatic lesion in a DIS region", "C", "app_dis raw ens any_dis_region",
  lambda: [dis("raw ens|all100")["any_dis_region"], 100])
c("§6.9", "met in 2/100 (P1 α = 0.1), 3/100 (α = 0.2) and 0/100 (P2; one-sided 95 % bound 3.0 %)", "C, derived",
  "app_dis ens|1-mm sites|P1|0.1/0.2/P2|0.1; one-sided Clopper–Pearson 95 % upper bound for 0/100",
  lambda: [dis("ens|1-mm sites|P1|0.1|all100")["dis_met_brain"], 100, 0.1, dis("ens|1-mm sites|P1|0.2|all100")["dis_met_brain"], 100, 0.2,
           dis("ens|1-mm sites|P2|0.1|all100")["dis_met_brain"], 100, 95, 100 * cp_upper_one_sided(0, 100)])
c("§6.9", "2 of 263 lay within 3 mm of the brain-mask edge. Of the 263, 165 (63 %) were periventricular; their median volume was 27 mm³", "C",
  "location['raw ens'] within_3mm, n, regions.PV, vol_mm3_quantiles_50_90[0]",
  lambda: [C["location"]["raw ens"]["within_3mm_of_brainmask_edge"], C["location"]["raw ens"]["n"], 3, C["location"]["raw ens"]["n"],
           C["location"]["raw ens"]["regions"]["PV"], 100 * C["location"]["raw ens"]["regions"]["PV"] / C["location"]["raw ens"]["n"],
           C["location"]["raw ens"]["vol_mm3_quantiles_50_90"][0]])
c("§6.9", "then \"0/30 (≤ 9.5 %)\"", "derived", "one-sided Clopper–Pearson 95 % upper bound for 0/30",
  lambda: [0, 30, 100 * cp_upper_one_sided(0, 30)])

# ---- 6.10
c("§6.10", "gave realised FDR **0.207 [0.175, 0.240]** at α = 0.1 and 0.236 [0.203, 0.268] at α = 0.2", "R",
  "lstai['segmenter_shift|mslesseg|LST-AI->FLAMeS|P1|0.1/0.2'] mean_fdp, ci",
  lambda: [R["lstai"]["segmenter_shift|mslesseg|LST-AI->FLAMeS|P1|0.1"]["mean_fdp"], *R["lstai"]["segmenter_shift|mslesseg|LST-AI->FLAMeS|P1|0.1"]["mean_fdp_ci"], 0.1,
           R["lstai"]["segmenter_shift|mslesseg|LST-AI->FLAMeS|P1|0.2"]["mean_fdp"], *R["lstai"]["segmenter_shift|mslesseg|LST-AI->FLAMeS|P1|0.2"]["mean_fdp_ci"], 0.2])
c("§6.10", "At α = 0.1, 78 % of scans had FDP > 0.1", "R", "segmenter_shift …LST-AI->FLAMeS|P1|0.1 fdp_gt_0.1.frac ×100",
  lambda: [0.1, 100 * R["lstai"]["segmenter_shift|mslesseg|LST-AI->FLAMeS|P1|0.1"]["fdp_gt_0.1"]["frac"], 0.1])
c("§6.10", "FLAMeS 0.019 / 0.052 and LST-AI 0.053 / 0.095", "R", "segmenter_shift FLAMeS->FLAMeS, LST-AI->LST-AI P1 0.1/0.2 mean_fdp",
  lambda: [R["lstai"][f"segmenter_shift|mslesseg|{k}|P1|{a}"]["mean_fdp"] for k in ("FLAMeS->FLAMeS", "LST-AI->LST-AI") for a in (0.1, 0.2)])
c("§6.10", "(mean false-candidate score 0.65 for LST-AI against 0.76 for the FLAMeS ensemble)", "R", "lstai.descriptive lstai|mslesseg fp_score_mean; descriptive ens|mslesseg fp_score_mean",
  lambda: [R["lstai"]["descriptive"]["lstai|mslesseg"]["fp_score_mean"], DESC["mslesseg"]["fp_score_mean"]])
c("§6.10", "FLAMeS-calibrated selection on LST-AI candidates selected nothing", "R", "segmenter_shift FLAMeS->LST-AI P1 n_sel == 0",
  lambda: [R["lstai"]["segmenter_shift|mslesseg|FLAMeS->LST-AI|P1|0.1"]["n_sel"] == 0 and R["lstai"]["segmenter_shift|mslesseg|FLAMeS->LST-AI|P1|0.2"]["n_sel"] == 0], "bool")

# ---- 8 Discussion
c("§8.1", "at which point it found 0.65–3.85 % of lesions", "R", "q4 site_only|P2|0.1|k=10 sens ×100 (Muslim, MS3SEG)",
  lambda: pct([q4("muslim", "site_only|P2|0.1|k=10")["sens_e2e_mean"], q4("ms3seg", "site_only|P2|0.1|k=10")["sens_e2e_mean"]]))
c("§8.2", "The realised FDR on thick slices (0.107 and 0.122 at α = 0.1)", "R", "primary D3 P1 0.1",
  lambda: [cell("D3", "ms3seg", "P1", 0.1)["estimate"], cell("D3", "muslim", "P1", 0.1)["estimate"], 0.1])
c("§8.2", "(30–36 % with 10 patients)", "R", "q4 site_only|P2|0.1|k=10 share_draws_above_nominal ×100",
  lambda: pct([q4("ms3seg", "site_only|P2|0.1|k=10")["share_draws_above_nominal"], q4("muslim", "site_only|P2|0.1|k=10")["share_draws_above_nominal"]]) + [10])
c("§8.2", "was 0.10 on MSLesSeg with the ensemble and below 0.03 elsewhere", "R", "mechanism ens|site|icc1_false_scores",
  lambda: [R["mechanism"]["ens|mslesseg|icc1_false_scores"], 0.03] if max(R["mechanism"][f"ens|{s}|icc1_false_scores"] for s in SITES if s != "mslesseg") < 0.03 else [None])
c("§8.2", "Under exchangeability, conformal BH attains α·π0, about α/3 here", "PH", "alpha_pi0 mean_pi0 (MS3SEG, Muslim, PediMS) ≈ 1/3",
  lambda: [3] if all(abs(PH[f"alpha_pi0|{s}"]["mean_pi0"] - 1 / 3) < 0.05 for s in ("ms3seg", "muslim", "pedims")) else [None])
c("§8.3", "End-to-end sensitivity was 0.01–0.40 for P1", "R", "primary P1 cells sens_e2e (min, max)",
  lambda: [min(x["sens_e2e"] for x in P1CELLS), max(x["sens_e2e"] for x in P1CELLS)])

# ---- 9 Limitations
c("§9", "In patients this changed 0.08 % of lesion regions and no DIS decision", "git (main)",
  "docs/iec62304/03_Risk_Management_File.md on branch main: PRB-001 entry '3 lesions (0.08 %) … 0 DIS decisions change'",
  lambda: [0.08] if ("(0.08 %)" in git("show", "main:docs/iec62304/03_Risk_Management_File.md")
                      and "0 DIS decisions change" in git("show", "main:docs/iec62304/03_Risk_Management_File.md")) else [None])
c("§9", "PediMS has 28 scans of 9 children, and Ljubljana-10 has 10 patients", "R", "descriptive pedims scans/patients; openms patients",
  lambda: [DESC["pedims"]["scans"], DESC["pedims"]["patients"], 10, DESC["openms"]["patients"]])
c("§9", "Thirty of the 100 controls had been analysed with fold 0 before the addendum", "C", "operating_points …|august30 n",
  lambda: [op("ens|1-mm sites|P1|0.1", "august30")["n"], 100, 0], "word:30")


# ------------------------------------------------------------------ engine
NUM = re.compile(r"(?<![\w.])[−-]?\d+(?:\.\d+)?")


def numbers(snippet):
    s = snippet.replace("10⁻⁵", "10 -5")
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
        elif kind in ("bool", "docbool"):
            if not (vals and all(v is True for v in vals)):
                status, note = "FAIL", "check returned False"
        else:
            written = numbers(snip)
            if kind.startswith("word:"):
                written = [kind.split(":")[1]] + written
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

*Generated by `docs/research/paper/manuscript/tools/check_numbers.py` (do not edit by hand). Run it
again after any change to the manuscript or the records.*

**Summary:** {len(CL)} claims checked — **{len(CL) - fails - rounding} PASS**, {rounding} ROUNDING (within half a unit of the last written
digit but not the round-half-up value), **{fails} FAIL**. Tables regenerated from the records and identical
to the manuscript: **{'yes' if tables_ok else 'NO'}** (`make_tables.py --check`).

**Sources (all committed; SHA-256 of the committed blob in parentheses is in the records themselves):**
R = `docs/research/records/{F['R']}` (pre-registered v0.3 results) · PH = `{F['PH']}` (post hoc) ·
C = `{F['C']}` (healthy-control addendum) · M = `{F['M']}` (manuscript-stage post hoc) ·
N = `{F['N']}` (MSLesSeg native thickness, post hoc) · CAL = `{F['CAL']}` · G = `{F['G']}` (gate G1) ·
EV = `{F['EV']}` (GitHub push events) · git = the repository history · PROTOCOL / ADDENDUM / RESULTS / DRAFT =
the v0.3 protocol, addendum, results and earlier draft in `docs/research/paper/`.

**What is not listed here, and why.**
1. *Numbers inside Tables 1, 4–10 and A1–A3*: generated from the records by `make_tables.py`; the check
   above regenerates them and compares byte for byte.
2. *Numbers inside figures*: drawn by `figures/make_figures.py` from the same records (input hashes in
   `figures/figures_manifest.json`).
3. *Design constants* (α, γ, δ, k grid, 3 mm³, 14.14 mm³, IoU thresholds, bootstrap counts) are checked as
   phrases of the protocol (rows marked PROTOCOL / ADDENDUM) or against the record fields.
4. *Literature context* (e.g. "voxel Dice of about 0.7", "4–8 mm" routine slices, FLAMeS's 668 training scans)
   comes from the cited sources, not from our data; the FLAMeS training-set facts are checked against the
   addendum's verified summary.
5. *Identifiers* (section, table and figure numbers, requirement and risk-control IDs, DOIs, years).
6. *Repeated mentions* of a number already traced in a row below (e.g. the same value restated in the
   abstract, the discussion or Appendix B), counts that follow from a traced row (e.g. "19 %" for 19/100),
   and list numbering. A coverage scan (all numerals outside tables) was reviewed by hand on 2026-10-31.

| # | section | as written in the manuscript | source | field / derivation | status |
|---|---|---|---|---|---|
"""
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(head + "\n".join(rows) + "\n")
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"{len(CL)} claims: {len(CL) - fails - rounding} PASS, {rounding} ROUNDING, {fails} FAIL; tables ok: {tables_ok}")
    for r in rows:
        if "FAIL" in r or "ROUNDING" in r:
            print(r)
    sys.exit(1 if (fails or not tables_ok) else 0)


if __name__ == "__main__":
    main()
