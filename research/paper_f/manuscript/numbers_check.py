"""Paper F manuscript - automatic number check. OFFLINE; reads only committed files (and local git objects).

For every number written in manuscript.md this script
  1. re-derives the value from its source file and field,
  2. formats it exactly as the text does and asserts equality,
  3. asserts that the sentence or table row carrying it occurs in manuscript.md,
then writes NUMBERS_CHECK.md (number -> file -> field -> stored value -> PASS) and a coverage scan of numeric
tokens in the main text that no entry covers. Exit code 1 if any check fails.

    python research/paper_f/manuscript/numbers_check.py
"""
import csv
import hashlib
import io
import json
import math
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
PF = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(PF))
RES = os.path.join(PF, "results")
DATA = os.path.join(HERE, "data")
MS = open(os.path.join(HERE, "manuscript.md"), encoding="utf-8").read()


def norm(t):
    return re.sub(r"\s+", " ", t.replace("−", "-")).strip()


MSN = norm(MS)
J = lambda *p: json.load(open(os.path.join(*p), encoding="utf-8"))  # noqa: E731
COMP = J(RES, "comparisons.json")
SUMM = J(RES, "summary.json")
VER = J(RES, "verify_runs.json")
RUNI = J(RES, "run_info.json")
EXTRA = J(DATA, "extra_numbers.json")
SPLIT = J(DATA, "flames_ljubljana_split_87e998d.json")
ACT = J(DATA, "github_push_activity_paper_f_branch.json")
LEDGER = list(csv.DictReader(open(os.path.join(DATA, "compute_ledger_c8b4239.csv"), encoding="utf-8")))
sys.path.insert(0, PF)
import metrics as M  # noqa: E402
import evaluate as EV  # noqa: E402


def text(path):
    return open(os.path.join(ROOT, path), encoding="utf-8").read()


def git(*a):
    return subprocess.run(["git", "-C", ROOT, *a], capture_output=True, check=True).stdout


# ----------------------------------------------------------------------------- accessors
def comp(fam, tool, outcome, band=None, vs="flames", contrast=False):
    for r in COMP[fam]:
        if r["tool"] == tool and r.get("vs") == vs and r["outcome"] == outcome:
            if contrast and "contrast" in r:
                return r
            if not contrast and r.get("band") == band:
                return r
    raise KeyError((fam, tool, outcome, band, vs))


def pband(band, tool):
    return [r for r in SUMM["per_band"] if r["band"] == band and r["tool"] == tool][0]


def pcoh(cohort, tool):
    return [r for r in SUMM["per_cohort"] if r["cohort"] == cohort and r["tool"] == tool][0]


def sbin(band, tool, b):
    return [r for r in SUMM["size_bins"] if r["band"] == band and r["tool"] == tool and r["bin"] == b][0]


def sens(analysis, tool, outcome):
    return [r for r in COMP["sensitivity"] if r["analysis"] == analysis and r["tool"] == tool and r["outcome"] == outcome][0]


def expl_auc(tool, band):
    return [r for r in COMP["exploratory"] if r.get("auroc") is not None and r["tool"] == tool and r["band"] == band][0]


def expl_conf(tool, band):
    return [r for r in COMP["exploratory"] if "f1" in r and r["tool"] == tool and r["band"] == band][0]


def e1post(tool):
    return [r for r in EXTRA["e1_posthoc"] if r["tool"] == tool][0]


def run(rid):
    return [r for r in VER["runs"] if r["run_id"] == rid][0]


def led(rid):
    return [r for r in LEDGER if r["run_id"] == rid][0]


# ----------------------------------------------------------------------------- formatting (as written in the text)
def d(v, n=3):
    return f"{v:.{n}f}".replace("-", "−")


def sd(v, n=3):
    return f"{v:+.{n}f}".replace("-", "−")


def ad(v, n=3):
    return f"{abs(v):.{n}f}"


def pc(v):
    return f"{round(100 * v):.0f}%"


def pholm(p, m):
    if p == 0.0:
        return "< 0.002" if m <= 6 else "< 0.003"
    return f"{p:.2g}" if p < 0.995 else "1.0"      # two significant figures (Monte Carlo SE ~0.008)


def i(v):
    return f"{int(round(v)):,}"


ENTRIES = []   # (number as written, context that must occur in the manuscript, source, field, stored value)
FAIL = []


def E(written, context, source, field, value, fmt):
    got = fmt(value)
    ok_fmt = norm(got) == norm(written)
    ok_ctx = norm(written) in norm(context) and norm(context) in MSN
    ENTRIES.append((written, context, source, field, value, ok_fmt and ok_ctx))
    if not (ok_fmt and ok_ctx):
        FAIL.append(f"{written!r}: formatted {got!r} (fmt ok {ok_fmt}); context found {ok_ctx}: {context[:90]!r}")


def lit(written, context, source, field, value=None):
    """Literal values (constants, identifiers) checked against the source text or file."""
    E(written, context, source, field, written if value is None else value, lambda v: str(v))


C = "results/comparisons.json"
S = "results/summary.json"
X = "manuscript/data/extra_numbers.json"
V = "results/verify_runs.json"
L = "manuscript/data/compute_ledger_c8b4239.csv"

# ============================================================================= abstract, highlights, introduction
E("324", "324 public MS scans", X, "n_scans_total", EXTRA["n_scans_total"], i)
E("3.9", "179 with 3.9–8.3 mm FLAIR slices", X, "cohorts.pedims.slice_mm_min", EXTRA["cohorts"]["pedims"]["slice_mm_min"], lambda v: f"{v:.1f}")
E("8.3", "179 with 3.9–8.3 mm FLAIR slices", X, "cohorts.muslim.slice_mm_max", EXTRA["cohorts"]["muslim"]["slice_mm_max"], lambda v: f"{v:.1f}")
E("179", "179 thick-slice scans (3.9–8.3 mm; 160 patients)", X, "bands.thick.scans", EXTRA["bands"]["thick"]["scans"], i)
E("160", "179 thick-slice scans (3.9–8.3 mm; 160 patients)", X, "bands.thick.patients", EXTRA["bands"]["thick"]["patients"], i)
E("145", "145 scans on a 1 mm grid (105 patients)", X, "bands.iso.scans", EXTRA["bands"]["iso"]["scans"], i)
E("105", "145 scans on a 1 mm grid (105 patients)", X, "bands.iso.patients", EXTRA["bands"]["iso"]["patients"], i)
E("12.55", "Incremental compute cost: 12.55 USD", X, "compute.usd_list", EXTRA["compute"]["usd_list"], lambda v: f"{v:.2f}")
E("0.724", "FLAMeS had a higher lesion-wise F1 (0.724) than every tool", S, "per_band[thick, flames].f1.estimate", pband("thick", "flames")["f1"]["estimate"], d)
for tool, ctx in (("mindglide", "ΔF1 −0.170 (95% CI −0.206 to −0.136) for MindGlide"),
                  ("samseg", "−0.237 (−0.304 to −0.173) for SAMSEG (129 scans)"),
                  ("wmhsynthseg", "−0.384 (−0.424 to −0.344) for WMH-SynthSeg (all p~Holm~ < 0.002)")):
    r = comp("primary", tool, "f1", "thick")
    E(d(r["estimate"]), ctx, C, f"primary[{tool}, f1, thick].estimate", r["estimate"], d)
    E(d(r["ci95"][0]), ctx, C, f"primary[{tool}, f1, thick].ci95[0]", r["ci95"][0], d)
    E(d(r["ci95"][1]), ctx, C, f"primary[{tool}, f1, thick].ci95[1]", r["ci95"][1], d)
E("129", "for SAMSEG (129 scans)", C, "primary[samseg, f1, thick].n_scans", comp("primary", "samseg", "f1", "thick")["n_scans"], i)
E("< 0.002", "(all p~Holm~ < 0.002)", C, "primary[*, f1].p_holm_registered_family (all 0.0; m = 6)", 0.0, lambda v: pholm(v, 6))
E("5.15", "had 5.15 and 3.88 fewer false lesions", C, "primary[samseg, false_lesions].estimate", comp("primary", "samseg", "false_lesions", "thick")["estimate"], lambda v: ad(v, 2))
E("3.88", "had 5.15 and 3.88 fewer false lesions", C, "primary[wmhsynthseg, false_lesions].estimate", comp("primary", "wmhsynthseg", "false_lesions", "thick")["estimate"], lambda v: ad(v, 2))
E("6%", "detected only 6% and 5% of expert lesions of 14–50 mm³ (FLAMeS 49%)", S, "size_bins[thick, samseg, 14-50].estimate", sbin("thick", "samseg", "14-50")["estimate"], pc)
E("5%", "detected only 6% and 5% of expert lesions of 14–50 mm³ (FLAMeS 49%)", S, "size_bins[thick, wmhsynthseg, 14-50].estimate", sbin("thick", "wmhsynthseg", "14-50")["estimate"], pc)
E("49%", "detected only 6% and 5% of expert lesions of 14–50 mm³ (FLAMeS 49%)", S, "size_bins[thick, flames, 14-50].estimate", sbin("thick", "flames", "14-50")["estimate"], pc)
r = comp("primary", "mindglide", "false_lesions", "thick")
for w, v, f in (("+0.57", r["estimate"], "estimate"), ("−0.89", r["ci95"][0], "ci95[0]"), ("+2.21", r["ci95"][1], "ci95[1]")):
    E(w, "MindGlide's false-lesion difference was not significant (+0.57, −0.89 to +2.21)", C, f"primary[mindglide, false_lesions].{f}", v, lambda x: sd(x, 2))
r = comp("secondary", "lstai", "f1", "iso")
for w, v, f in (("−0.180", r["estimate"], "estimate"), ("−0.212", r["ci95"][0], "ci95[0]"), ("−0.150", r["ci95"][1], "ci95[1]")):
    E(w, "also led (LST-AI −0.180, −0.212 to −0.150)", C, f"secondary[lstai, f1, iso].{f}", v, d)
E("0.102", "MindGlide's deficit relative to FLAMeS was 0.102 smaller in the thick cohorts", C, "secondary[mindglide, degradation].estimate", comp("secondary", "mindglide", "f1", contrast=True)["estimate"], d)
E("0.78", "with an AUROC of 0.78 (exploratory; post hoc 95% interval about 0.60 to 0.93)", C, "exploratory[mindglide, thick].auroc", expl_auc("mindglide", "thick")["auroc"], lambda v: f"{v:.2f}")
E("14", "Both analyses rest on 14 poor scans, 10 of them from one cohort", C, "exploratory[mindglide, thick].n_poor", expl_auc("mindglide", "thick")["n_poor"], i)
E("1–9 mm", "synthetic scans with resolutions of 1–9 mm", "docs/research/paper-f/PROTOCOL.md", "section 3, MindGlide training data", "1–9 mm", str)
E("179", "against the FLAMeS 5-fold ensemble on 179 real thick-slice FLAIR scans from three public cohorts, with LST-AI", X, "bands.thick.scans", EXTRA["bands"]["thick"]["scans"], i)

# ============================================================================= 2.1 registration
h65 = git("rev-parse", "65a95e3").decode().strip()
lit(h65, "were recorded in commit `65a95e310168071703398aab3a53ba9fc0086e1a`", "git", "rev-parse 65a95e3")
ts = git("show", "-s", "--format=%cI", h65).decode().strip()        # 2026-10-21T22:45:32+02:00
E("20:45", "(2026-10-21 20:45 UTC)", "git", f"committer date of 65a95e3 = {ts}", ts, lambda v: "20:45" if v.startswith("2026-10-21T22:45") and v.endswith("+02:00") else v)
bc = [a for a in ACT if a["activity_type"] == "branch_creation"][0]
E("20:58", "pushed to the public GitHub repository `nicolasbonilla/medical-imaging-viewer` at 2026-10-21 20:58 UTC",
  "manuscript/data/github_push_activity_paper_f_branch.json", "branch_creation.timestamp", bc["timestamp"], lambda v: v[11:16])
first = min(r["started_utc"] for r in VER["runs"])
E("21:39", "40 minutes before the first tool container started (21:39 UTC", V, "min(runs[].started_utc)", first, lambda v: v[11:16])
import datetime as _dt  # noqa: E402
gap = (_dt.datetime.fromisoformat(first.replace("Z", "+00:00")) - _dt.datetime.fromisoformat(bc["timestamp"].replace("Z", "+00:00"))).total_seconds() / 60
E("40", "40 minutes before the first tool container started", "derived", "21:39:06Z - 20:58:43Z (minutes, floor)", gap, lambda v: str(int(v)))
proto_sha = hashlib.sha256(git("show", "65a95e3:docs/research/paper-f/PROTOCOL.md")).hexdigest()
lit(proto_sha, "`587ba9ffc1f07d559a0008728e97ec9e1e9455eaf0037e37bbcc52b8f5f284e2`", "git show 65a95e3:docs/research/paper-f/PROTOCOL.md | sha256", "SHA-256")
lit(RUNI["code_commit"], "commit `7a9a24e8fa92c83ded210854fd8614f7be4dcd50`", "results/run_info.json", "code_commit")
E("00:11", "(2026-10-29 00:11 UTC; pushed 00:01 UTC)", "results/run_info.json", "created_utc", RUNI["created_utc"], lambda v: v[11:16])
p7 = [a for a in ACT if a["after"].startswith("7a9a24e")][0]
E("00:01", "(2026-10-29 00:11 UTC; pushed 00:01 UTC)", "manuscript/data/github_push_activity_paper_f_branch.json", "push after=7a9a24e .timestamp", p7["timestamp"], lambda v: v[11:16])
E("3,059", "records the SHA-256 of all 3,059 input files read", "results/run_info.json", "n_input_files", RUNI["n_input_files"], i)

# ============================================================================= 2.2 cohorts
E("265", "324 scans of 265 patients", X, "n_patients_total", EXTRA["n_patients_total"], i)
for c, sc, pt, ctx in (("mslesseg", "115", "75", "provides 115 longitudinal scans of 75 patients"),
                       ("openms", "30", None, "Ljubljana [@lesjak2018ljubljana] provides 30 patients"),
                       ("ms3seg", "100", None, "[@bawil2026ms3seg; @bawil2026ms3segdata]: 100 patients"),
                       ("pedims", "28", "9", "28 longitudinal scans of 9 children")):
    E(sc, ctx, X, f"cohorts.{c}.scans", EXTRA["cohorts"][c]["scans"], i)
    if pt:
        E(pt, ctx, X, f"cohorts.{c}.patients", EXTRA["cohorts"][c]["patients"], i)
E("51", "51 axial scans (of 60; 9 coronal or sagittal scans were excluded", X, "cohorts.muslim.scans", EXTRA["cohorts"]["muslim"]["scans"], i)
lit("60", "51 axial scans (of 60; 9 coronal or sagittal scans were excluded", "docs/research/cohorts-extra.md", "3.2: 'Patient-1 … Patient-60'; 51 axial, 6 coronal, 3 sagittal")
E("6.0", "6.0–8.1 mm slice spacing (median 7.2 mm)", X, "cohorts.ms3seg.slice_mm_min", EXTRA["cohorts"]["ms3seg"]["slice_mm_min"], lambda v: f"{v:.1f}")
E("8.1", "6.0–8.1 mm slice spacing (median 7.2 mm)", X, "cohorts.ms3seg.slice_mm_max", EXTRA["cohorts"]["ms3seg"]["slice_mm_max"], lambda v: f"{v:.1f}")
E("7.2", "6.0–8.1 mm slice spacing (median 7.2 mm)", X, "cohorts.ms3seg.slice_mm_median", EXTRA["cohorts"]["ms3seg"]["slice_mm_median"], lambda v: f"{v:.1f}")
E("4.86", "4.86–8.3 mm slice spacing (median 6.0 mm)", X, "cohorts.muslim.slice_mm_min", EXTRA["cohorts"]["muslim"]["slice_mm_min"], lambda v: f"{v:.2f}")
E("8.3", "4.86–8.3 mm slice spacing (median 6.0 mm)", X, "cohorts.muslim.slice_mm_max", EXTRA["cohorts"]["muslim"]["slice_mm_max"], lambda v: f"{v:.1f}")
E("6.0", "4.86–8.3 mm slice spacing (median 6.0 mm)", X, "cohorts.muslim.slice_mm_median", EXTRA["cohorts"]["muslim"]["slice_mm_median"], lambda v: f"{v:.1f}")
E("3.9", "0.75 × 0.75 × 3.9 mm; one child", X, "cohorts.pedims.slice_mm_max", EXTRA["cohorts"]["pedims"]["slice_mm_max"], lambda v: f"{v:.1f}")
for w, ctx in (("0.898", "0.898 × 0.898 mm in plane"), ("0.41–0.97", "in-plane pixel size (0.41–0.97 mm)"),
               ("±5%", "(expected error about ±5% per axis)"), ("20", "1.5 T, about 20 centres"),
               ("2.0.1", "HD-BET 2.0.1 on CPU without test-time augmentation"), ("0.75", "0.75 × 0.75 × 3.9 mm")):
    lit(w, ctx, "docs/research/cohorts-extra.md (and PROTOCOL.md section 2)", "sections 1, 3.2, 3.3")
for w in ("1.5", "3", "5.5"):
    lit(w, "iso ≤ 1.5 mm and thick > 3 mm, with exploratory sub-bands 3–5.5 mm", "research/paper_f/metrics.py", "ISO_MAX_MM, THICK_MIN_MM, THICK_SPLIT_MM")
E("24", "3–5.5 mm (PediMS and 24 Muslim scans)", S, "per_band[thick_3-5.5, flames].n − PediMS 28", pband("thick_3-5.5", "flames")["n"] - 28, i)
E("27", "> 5.5 mm (MS3SEG and 27 Muslim scans)", S, "per_band[thick_>5.5, flames].n − MS3SEG 100", pband("thick_>5.5", "flames")["n"] - 100, i)
B = EXTRA["bands"]
E("3,463", "the FLAMeS comparison set contained 3,463 expert lesions, 1,209 (34.9%)", X, "bands.iso.expert_lesions_flames_set", B["iso"]["expert_lesions_flames_set"], i)
E("1,209", "3,463 expert lesions, 1,209 (34.9%) of them", X, "bands.iso.expert_lesions_14_50", B["iso"]["expert_lesions_14_50"], i)
E("34.9%", "1,209 (34.9%) of them", X, "bands.iso.share_14_50", B["iso"]["share_14_50"], lambda v: f"{100 * v:.1f}%")
E("5,993", "in the thick band 5,993 expert lesions, 1,248 (20.8%)", X, "bands.thick.expert_lesions_flames_set", B["thick"]["expert_lesions_flames_set"], i)
E("1,248", "5,993 expert lesions, 1,248 (20.8%)", X, "bands.thick.expert_lesions_14_50", B["thick"]["expert_lesions_14_50"], i)
E("20.8%", "1,248 (20.8%) of them 14–50 mm³", X, "bands.thick.share_14_50", B["thick"]["share_14_50"], lambda v: f"{100 * v:.1f}%")
E("No scan", "No scan had an empty reference", X, "bands.*.scans_with_empty_reference (sum)", B["iso"]["scans_with_empty_reference"] + B["thick"]["scans_with_empty_reference"], lambda v: "No scan" if v == 0 else str(v))

# ============================================================================= 2.3 tools
lit("17955359", "(Zenodo 17955359, version 2.0, CC BY 4.0)", "references.bib (larosa2025flameszenodo, verified on Zenodo)", "doi 10.5281/zenodo.17955359")
torch_v = json.loads(git("show", "origin/research/cloud-compute-ledger:docs/research/compute-ledger/records/flames-full-a.json"))["manifest_summary"]
E("2.14.1", "PyTorch 2.14.1 CPU build", "branch research/cloud-compute-ledger: records/flames-full-a.json", "manifest_summary.versions.torch", torch_v["versions"]["torch"], lambda v: v.split("+")[0])
E("switched off", "Test-time mirroring, nnU-Net's default, was switched off to save CPU time", "records/flames-full-a.json", "manifest_summary.tta", torch_v["tta"], lambda v: "switched off" if v is False else "?")
lit("0.5", "tile step 0.5 with Gaussian weighting", "research/cloud/flames_ensemble_driver.py", "nnUNetPredictor(tile_step_size=0.5, use_gaussian=True)")
E("144", "had been run on the 1 mm cohorts only (144 scans", S, "status_counts.lstai.ok", SUMM["status_counts"]["lstai"]["ok"], i)
for w in ("18", "77", "99"):
    lit(w, "(lesion = label 18)" if w == "18" else "(labels 77 and 99)", "docs/research/paper-f/PROTOCOL.md", "section 4.2 lesion labels")
for w, ctx in (("668", "668 FLAIR scans of 575 people with MS from seven sites"), ("575", "668 FLAIR scans of 575 people with MS"),
               ("20", "including ISBI-2015 (20 scans), MSSEG-2016 (53) and Ljubljana (20)"), ("53", "MSSEG-2016 (53)"),
               ("51", "the FLAMeS developers used 51 MSLesSeg cases as an external test set")):
    lit(w, ctx, "Dereskewicz et al. 2025, J Neuroimaging (PMC12426979), Table 1 and Methods", "verified 2026-10-31 (references.bib notes)")
for w, ctx in (("491", "491 in-house 3D FLAIR + T1 scans"), ("4,247", "4,247 real scans"), ("4,303", "4,303 synthetic scans"),
               ("2.5–8.5", "random slice spacing 2.5–8.5 mm"), ("20", "atlas from 20 subjects"), ("212", "lesion shape model from 212 MS subjects")):
    lit(w, ctx, "docs/research/paper-f/PROTOCOL.md", "section 3 (training data, with sources)")
E("Twenty", "Twenty consecutive entries matched the bounding box", "manuscript/data/flames_ljubljana_split_87e998d.json", "n_exact_matches", SPLIT["n_exact_matches"], lambda v: "Twenty" if v == 20 else str(v))
E("zero", "with zero voxels of difference", "manuscript/data/flames_ljubljana_split_87e998d.json", "max(assignment[exact].l1_voxels)", max(a["l1_voxels"] for a in SPLIT["assignment"] if a.get("exact")), lambda v: "zero" if v == 0 else str(v))
E("01–15 and 21–25", "(patients 01–15 and 21–25)", "manuscript/data/flames_ljubljana_split_87e998d.json", "matched_trained", SPLIT["matched_trained"],
  lambda v: "01–15 and 21–25" if v == [f"patient{k:02d}" for k in list(range(1, 16)) + list(range(21, 26))] else "?")
E("16–20 and 26–30", "leaving patients 16–20 and 26–30 never seen", "manuscript/data/flames_ljubljana_split_87e998d.json", "held_out", SPLIT["held_out"],
  lambda v: "16–20 and 26–30" if v == [f"patient{k:02d}" for k in list(range(16, 21)) + list(range(26, 31))] else "?")

# ============================================================================= 2.4 - 2.9 methods constants
lit("4", "on 4 vCPUs, inside containers pinned by digest", "manuscript/data/compute_ledger_c8b4239.csv", "vcpus = 4 for every toolbench run")
assert all(r["vcpus"] == "4" for r in LEDGER if r["run_id"].startswith("toolbench"))
E("179", "fraction was ≥ 0.5 (179 scans)", V, "tools.wmhsynthseg.transform_kinds.footprint-mean", VER["tools"]["wmhsynthseg"]["transform_kinds"]["footprint-mean"], i)
E("145", "1 mm outputs were mapped trilinearly (145 scans)", V, "tools.wmhsynthseg.transform_kinds.trilinear", VER["tools"]["wmhsynthseg"]["transform_kinds"]["trilinear"], i)
E("45", "exceeded 45 minutes was to be scored as an empty prediction", V, "runs[].timeout_min", run("toolbench-wmh")["timeout_min"], lambda v: str(int(v)))
E("14.137", "Components smaller than 14.137 mm³ (a sphere of 3 mm diameter)", "research/paper_f/metrics.py", "SPHERE_3MM_MM3", M.SPHERE_3MM_MM3, lambda v: f"{v:.3f}")
E("10,000", "within each cohort, 10,000 replicates, seed 20261021", "research/paper_f/metrics.py", "BOOT_N", M.BOOT_N, i)
E("20261021", "10,000 replicates, seed 20261021", "research/paper_f/metrics.py", "BOOT_SEED", M.BOOT_SEED, str)
E("±0.05", "inside ±0.05 F1 or ±1 false lesion per scan", "research/paper_f/metrics.py", "EQUIV_MARGIN_F1", M.EQUIV_MARGIN_F1, lambda v: f"±{v:.2f}")
E("±1", "inside ±0.05 F1 or ±1 false lesion per scan", "research/paper_f/metrics.py", "EQUIV_MARGIN_FP", M.EQUIV_MARGIN_FP, lambda v: f"±{v:.0f}")
E("6", "**Primary family (6 tests", "research/paper_f/evaluate.py", "REGISTERED_FAMILY['primary']", EV.REGISTERED_FAMILY["primary"], str)
E("11", "**Secondary family (11 tests", "research/paper_f/evaluate.py", "REGISTERED_FAMILY['secondary']", EV.REGISTERED_FAMILY["secondary"], str)
E("4", "**Raw-input arm (4 tests", "research/paper_f/evaluate.py", "REGISTERED_FAMILY['secondary_raw_arm']", EV.REGISTERED_FAMILY["secondary_raw_arm"], str)
lit("< 0.5", "identifying scans with FLAMeS lesion-wise F1 < 0.5", "research/paper_f/evaluate.py", "prestated(): poor = f1 < 0.5")
lit("0.15", "With a per-scan SD of 0.15 for ΔF1", "docs/research/paper-f/PROTOCOL.md", "section 8")
lit("±0.04", "half-width of about ±0.04 F1", "docs/research/paper-f/PROTOCOL.md", "section 8")
E("3.11.4", "Software: Python 3.11.4 and NumPy 1.26.4", "results/run_info.json", "python", RUNI["python"], str)
E("1.26.4", "Python 3.11.4 and NumPy 1.26.4", "results/run_info.json", "numpy", RUNI["numpy"], str)
lit("15", "so that the projected total spend stayed ≤ 15 USD", "docs/research/paper-f/PROTOCOL.md", "section 4.4")
lit("13.76", "the rule selected tier C (projected total 13.76 USD)", "docs/research/paper-f/PROTOCOL.md", "section 12, row 2026-10-28")
tierc = open(os.path.join(RES, "samseg_tier_c_ids.txt")).read().split()
E("129", "tier C a fixed thick subsample of 129 scans", "results/samseg_tier_c_ids.txt", "number of ids", len(tierc), i)
E("50", "the 50 odd-numbered MS3SEG scans", "results/samseg_tier_c_ids.txt", "ms3seg ids", sum(t.startswith("ms3seg") for t in tierc), i)
E("110", "paired on 129 thick scans of 110 patients", C, "primary[samseg].n_clusters", comp("primary", "samseg", "f1", "thick")["n_clusters"], i)
E("14", "The study's own runs used 14 virtual machines, 61.90 machine-hours and 12.55 USD", X, "compute.runs", EXTRA["compute"]["runs"], i)
E("61.90", "14 virtual machines, 61.90 machine-hours", X, "compute.vm_hours", EXTRA["compute"]["vm_hours"], lambda v: f"{v:.2f}")
E("12.55", "61.90 machine-hours and 12.55 USD", X, "compute.usd_list", EXTRA["compute"]["usd_list"], lambda v: f"{v:.2f}")
lit("32", "n2d-highmem-4 with 32 GB for WMH-SynthSeg", L, "memory_gb of toolbench-wmh = 32.0")
assert led("toolbench-wmh")["memory_gb"] == "32.0"

# ============================================================================= 3.1 completeness
for tool, w in (("wmhsynthseg", "324/324"), ("mindglide", "324/324"), ("mindglide-raw", "179/179")):
    t = VER["tools"][tool]
    E(w, "WMH-SynthSeg 324/324, MindGlide 324/324, MindGlide on raw input 179/179 and SAMSEG 129/129", V, f"tools.{tool}.ok/planned", (t["ok"], t["planned"]), lambda v: f"{v[0]}/{v[1]}")
st = VER["tools"]["samseg"]
E("129/129", "and SAMSEG 129/129", V, "tools.samseg (ok + ms3seg_001 without record)/planned", (st["planned"], st["planned"]), lambda v: f"{v[0]}/{v[1]}")
lit("1,129", "verified by its lesion-voxel count (1,129)", "results/RESULTS.md / PROTOCOL.md section 12", "integrity note 2026-10-29")
E("3", "SAMSEG predicted no lesion after the size filter in 3 of 129 scans", X, "zero_prediction_scans_posthoc['samseg|thick'].no_predicted_lesion", EXTRA["zero_prediction_scans_posthoc"]["samseg|thick"]["no_predicted_lesion"], i)

# ============================================================================= 3.2 primary
fb = pband("thick", "flames")
E("0.724", "lesion-wise F1 of 0.724 (95% CI 0.702–0.745) and 6.9 false lesions", S, "per_band[thick, flames].f1.estimate", fb["f1"]["estimate"], d)
E("0.702", "(95% CI 0.702–0.745)", S, "per_band[thick, flames].f1.ci95[0]", fb["f1"]["ci95"][0], d)
E("0.745", "(95% CI 0.702–0.745)", S, "per_band[thick, flames].f1.ci95[1]", fb["f1"]["ci95"][1], d)
E("6.9", "0.702–0.745) and 6.9 false lesions per scan on the 179 thick scans", S, "per_band[thick, flames].false_lesions.estimate", fb["false_lesions"]["estimate"], lambda v: f"{v:.1f}")
for tool, ctx in (("mindglide", "MindGlide by 0.170 (95% CI 0.136–0.206)"), ("samseg", "SAMSEG by 0.237 (0.173–0.304)"),
                  ("wmhsynthseg", "WMH-SynthSeg by 0.384 (0.344–0.424)")):
    r = comp("primary", tool, "f1", "thick")
    E(ad(r["estimate"]), ctx, C, f"primary[{tool}, f1].estimate (magnitude)", r["estimate"], ad)
    E(ad(r["ci95"][1]), ctx, C, f"primary[{tool}, f1].ci95[1] (magnitude)", r["ci95"][1], ad)
    E(ad(r["ci95"][0]), ctx, C, f"primary[{tool}, f1].ci95[0] (magnitude)", r["ci95"][0], ad)
for tool, ctx in (("samseg", "SAMSEG had 5.15 fewer false lesions per scan (95% CI 3.91–6.30)"), ("wmhsynthseg", "WMH-SynthSeg 3.88 fewer (2.27–5.21)")):
    r = comp("primary", tool, "false_lesions", "thick")
    E(ad(r["estimate"], 2), ctx, C, f"primary[{tool}, false_lesions].estimate (magnitude)", r["estimate"], lambda v: ad(v, 2))
    E(ad(r["ci95"][1], 2), ctx, C, f"primary[{tool}, false_lesions].ci95[1] (magnitude)", r["ci95"][1], lambda v: ad(v, 2))
    E(ad(r["ci95"][0], 2), ctx, C, f"primary[{tool}, false_lesions].ci95[0] (magnitude)", r["ci95"][0], lambda v: ad(v, 2))
r = comp("primary", "mindglide", "false_lesions", "thick")
E("0.45", "(−0.89 to +2.21; p~Holm~ = 0.45)", C, "primary[mindglide, false_lesions].p_holm_registered_family", r["p_holm_registered_family"], lambda v: f"{v:.2f}")
tc = EXTRA["tier_c"]
E("0.729", "FLAMeS had F1 0.729 and 6.97 false lesions per scan", X, "tier_c.flames_f1.estimate", tc["flames_f1"]["estimate"], d)
E("6.97", "FLAMeS had F1 0.729 and 6.97 false lesions per scan", X, "tier_c.flames_false_lesions.estimate", tc["flames_false_lesions"]["estimate"], lambda v: f"{v:.2f}")
E("0.492", "against 0.492 and 1.82 for SAMSEG", X, "tier_c.samseg_f1.estimate", tc["samseg_f1"]["estimate"], d)
E("1.82", "against 0.492 and 1.82 for SAMSEG", X, "tier_c.samseg_false_lesions.estimate", tc["samseg_false_lesions"]["estimate"], lambda v: f"{v:.2f}")


# ---------------------------------------------------------------- Table 3, rebuilt from comparisons.json and matched row by row
def ci_txt(r, n, signed=True):
    f = (lambda v: sd(v, n)) if signed else (lambda v: d(v, n))
    return f"{f(r['estimate'])} ({f(r['ci95'][0])} to {f(r['ci95'][1])})"


def row3(fam_label, label, band, fam, tool, vs="flames", m=6):
    a = comp(fam, tool, "f1", band, vs)
    b = comp(fam, tool, "false_lesions", band, vs)
    f1 = ci_txt(a, 3).replace("+", "") if a["estimate"] < 0 else ci_txt(a, 3)
    return (f"| {fam_label} | {label} | {band} | {a['n_scans']} / {a['n_clusters']} | {f1} | "
            f"{pholm(a['p_holm_registered_family'], m)} | {ci_txt(b, 2)} | {pholm(b['p_holm_registered_family'], m)} |"), (a, b)


T3 = [("Primary (6)", "MindGlide − FLAMeS", "thick", "primary", "mindglide", "flames", 6),
      ("Primary (6)", "WMH-SynthSeg − FLAMeS", "thick", "primary", "wmhsynthseg", "flames", 6),
      ("Primary (6)", "SAMSEG − FLAMeS", "thick", "primary", "samseg", "flames", 6),
      ("Secondary (11)", "MindGlide − FLAMeS", "iso", "secondary", "mindglide", "flames", 11),
      ("Secondary (11)", "WMH-SynthSeg − FLAMeS", "iso", "secondary", "wmhsynthseg", "flames", 11),
      ("Secondary (11)", "LST-AI − FLAMeS", "iso", "secondary", "lstai", "flames", 11),
      ("Raw arm (4)", "MindGlide raw − FLAMeS", "thick", "secondary_raw_arm", "mindglide-raw", "flames", 4),
      ("Raw arm (4)", "MindGlide raw − MindGlide", "thick", "secondary_raw_arm", "mindglide-raw", "mindglide", 4)]
for fl, lab, band, fam, tool, vs, m in T3:
    rowtxt, (a, b) = row3(fl, lab, band, fam, tool, vs, m)
    rowtxt = rowtxt.replace("(+", "(+").replace(" (−", " (−")
    # the text writes negative F1 differences without a plus on the CI bounds that are negative; positives keep +
    E(norm(rowtxt), rowtxt, C, f"{fam}[{tool} vs {vs}, {band}]: n_scans, n_clusters, f1/false_lesions estimate, ci95, p_holm_registered_family",
      norm(rowtxt), lambda v: v)
for tool, lab in (("mindglide", "Between-band contrast^c^, MindGlide"), ("wmhsynthseg", "Between-band contrast^c^, WMH-SynthSeg")):
    r = comp("secondary", tool, "f1", contrast=True)
    rowtxt = (f"| Secondary (11) | {lab} | thick − iso | {r['n_scans']} / {r['n_clusters']} | {ci_txt(r, 3)} | "
              f"{pholm(r['p_holm_registered_family'], 11)} | — | — |")
    E(norm(rowtxt), rowtxt, C, f"secondary[{tool}, degradation contrast]: estimate, ci95, p_holm_registered_family", norm(rowtxt), lambda v: v)

# ---------------------------------------------------------------- Table 4, rebuilt
P = EXTRA["precision_by_band_descriptive"]
R = EXTRA["recall_by_band_descriptive"]
for band, tool, label in (("iso", "flames", "FLAMeS"), ("iso", "lstai", "LST-AI"), ("iso", "mindglide", "MindGlide"),
                          ("iso", "wmhsynthseg", "WMH-SynthSeg"), ("thick", "flames", "FLAMeS"), ("thick", "mindglide", "MindGlide"),
                          ("thick", "mindglide-raw", "MindGlide, raw input"), ("thick", "wmhsynthseg", "WMH-SynthSeg"),
                          ("thick", "samseg", "SAMSEG (tier C)")):
    pb = pband(band, tool)
    f1 = f"{d(pb['f1']['estimate'])} ({d(pb['f1']['ci95'][0])}–{d(pb['f1']['ci95'][1])})"
    fp = f"{pb['false_lesions']['estimate']:.1f} ({pb['false_lesions']['ci95'][0]:.1f}–{pb['false_lesions']['ci95'][1]:.1f})"
    pr = d(P[f"{tool}|{band}"]["estimate"]) + ("^a^" if tool == "samseg" else "")
    rowtxt = (f"| {band} | {label} | {pb['n']} | {f1} | {fp} | {pr} | {d(R[f'{tool}|{band}']['estimate'])} | "
              f"{d(pb['dice']['estimate'])} |")
    E(norm(rowtxt), rowtxt, f"{S} + {X}", f"per_band[{band},{tool}].n, f1, false_lesions, dice; precision/recall_by_band_descriptive['{tool}|{band}']", norm(rowtxt), lambda v: v)
E("126", "^a^ 126 scans; precision is undefined", X, "precision_by_band_descriptive['samseg|thick'].n_scans", P["samseg|thick"]["n_scans"], i)

# ============================================================================= 3.3
th = ("ms3seg", "muslim", "pedims")
rng = lambda vals, n=1: f"{min(vals):.{n}f}–{max(vals):.{n}f}"  # noqa: E731
E("4.2–5.2", "was 4.2–5.2 mL for WMH-SynthSeg", S, "per_cohort[thick cohorts, wmhsynthseg].vol_pred_ml.estimate (min–max)", [pcoh(c, "wmhsynthseg")["vol_pred_ml"]["estimate"] for c in th], rng)
E("6.8–9.7", "6.8–9.7 mL for SAMSEG", S, "per_cohort[thick cohorts, samseg].vol_pred_ml.estimate (min–max)", [pcoh(c, "samseg")["vol_pred_ml"]["estimate"] for c in th], rng)
E("12.6–19.8", "expert volumes of 12.6–19.8 mL", S, "per_cohort[thick cohorts, all tools].vol_ref_ml.estimate (min–max)",
  [r["vol_ref_ml"]["estimate"] for r in SUMM["per_cohort"] if r["cohort"] in th], rng)
E("13.1–18.4", "FLAMeS volumes of 13.1–18.4 mL", S, "per_cohort[thick cohorts, flames].vol_pred_ml.estimate (min–max)", [pcoh(c, "flames")["vol_pred_ml"]["estimate"] for c in th], rng)
for w, key in (("0.837", "samseg|thick"), ("0.707", "wmhsynthseg|thick"), ("0.738", "flames|thick")):
        E(w, "(SAMSEG 0.837 against 0.743 for FLAMeS on the same 129 scans; WMH-SynthSeg 0.707 against 0.738)", X, f"precision_by_band_descriptive['{key}'].estimate", P[key]["estimate"], d)
for w, key in (("0.397", "samseg|thick"), ("0.248", "wmhsynthseg|thick"), ("0.758", "flames|thick")):
    E(w, "(0.397 and 0.248 vs 0.758)", X, f"recall_by_band_descriptive['{key}'].estimate", R[key]["estimate"], d)
E("1,248", "of the 1,248 expert lesions of 14–50 mm³ on thick scans", S, "size_bins[thick, flames, 14-50].n_ref", sbin("thick", "flames", "14-50")["n_ref"], i)
for tool, ctx in (("flames", "FLAMeS detected 0.49 (95% CI 0.44–0.54)"), ("mindglide", "MindGlide 0.22 (0.18–0.27)"),
                  ("samseg", "SAMSEG 0.06 (0.04–0.09; 935 lesions in its scans)"), ("wmhsynthseg", "WMH-SynthSeg 0.05 (0.03–0.07)")):
    r = sbin("thick", tool, "14-50")
    for f, v in (("estimate", r["estimate"]), ("ci95[0]", r["ci95"][0]), ("ci95[1]", r["ci95"][1])):
        E(f"{v:.2f}", ctx, S, f"size_bins[thick, {tool}, 14-50].{f}", v, lambda x: f"{x:.2f}")
E("935", "935 lesions in its scans", S, "size_bins[thick, samseg, 14-50].n_ref", sbin("thick", "samseg", "14-50")["n_ref"], i)
for tool, w in (("flames", "0.97"), ("mindglide", "0.97"), ("samseg", "0.89"), ("wmhsynthseg", "0.83")):
    E(w, "FLAMeS and MindGlide both detected 0.97, SAMSEG 0.89 and WMH-SynthSeg 0.83", S, f"size_bins[thick, {tool}, >=1000].estimate", sbin("thick", tool, ">=1000")["estimate"], lambda x: f"{x:.2f}")

# ============================================================================= 3.4 sensitivity
TH = ("S1_no_size_filter", "S2_min_3mm3", "S3_inplane_8conn", "S4_complete_case", "S6_thick_without_muslim", "S7_scan_weighted")
for tool, ctx in (("mindglide", "range −0.153 to −0.194 for MindGlide"), ("samseg", "−0.212 to −0.244 for SAMSEG"),
                  ("wmhsynthseg", "−0.373 to −0.436 for WMH-SynthSeg")):
    vals = [sens(a, tool, "f1")["estimate"] for a in TH]
    assert all(sens(a, tool, "f1")["ci95"][1] < 0 for a in TH)
    E(d(max(vals)), ctx, C, f"sensitivity[S1-S4,S6,S7; {tool}; f1].estimate (max)", max(vals), d)
    E(d(min(vals)), ctx, C, f"sensitivity[S1-S4,S6,S7; {tool}; f1].estimate (min)", min(vals), d)
for tool, ctx in (("wmhsynthseg", "WMH-SynthSeg (−3.66 to −4.87)"), ("samseg", "SAMSEG (−5.00 to −8.25)")):
    vals = [sens(a, tool, "false_lesions")["estimate"] for a in TH]
    assert all(sens(a, tool, "false_lesions")["ci95"][1] < 0 for a in TH)
    E(d(max(vals), 2), ctx, C, f"sensitivity[...; {tool}; false_lesions].estimate (max)", max(vals), lambda v: d(v, 2))
    E(d(min(vals), 2), ctx, C, f"sensitivity[...; {tool}; false_lesions].estimate (min)", min(vals), lambda v: d(v, 2))
for a, ctx in (("S1_no_size_filter", "(S1, +2.42, 95% CI +0.10 to +5.06)"), ("S3_inplane_8conn", "(S3, +8.09, +4.51 to +12.35)"),
               ("S7_scan_weighted", "S7, scan-weighted, +0.85, −0.34 to +2.01")):
    r = sens(a, "mindglide", "false_lesions")
    for f, v in (("estimate", r["estimate"]), ("ci95[0]", r["ci95"][0]), ("ci95[1]", r["ci95"][1])):
        E(sd(v, 2), ctx, C, f"sensitivity[{a}, mindglide, false_lesions].{f}", v, lambda x: sd(x, 2))

# ============================================================================= 3.5 secondary
fi = pband("iso", "flames")
E("0.765", "On the 1 mm-grid scans FLAMeS had F1 0.765 (0.727–0.798)", S, "per_band[iso, flames].f1.estimate", fi["f1"]["estimate"], d)
E("0.727", "On the 1 mm-grid scans FLAMeS had F1 0.765 (0.727–0.798)", S, "per_band[iso, flames].f1.ci95[0]", fi["f1"]["ci95"][0], d)
E("0.798", "On the 1 mm-grid scans FLAMeS had F1 0.765 (0.727–0.798)", S, "per_band[iso, flames].f1.ci95[1]", fi["f1"]["ci95"][1], d)
for tool, w in (("mindglide", "−0.272"), ("wmhsynthseg", "−0.363"), ("lstai", "−0.180")):
    E(w, "MindGlide (ΔF1 −0.272), WMH-SynthSeg (−0.363) and LST-AI (−0.180), all p~Holm~ < 0.003", C, f"secondary[{tool}, f1, iso].estimate", comp("secondary", tool, "f1", "iso")["estimate"], d)
for tool, w in (("mindglide", "+3.07"), ("lstai", "+3.79")):
    E(w, "MindGlide (+3.07) and LST-AI (+3.79) produced more false lesions", C, f"secondary[{tool}, false_lesions, iso].estimate", comp("secondary", tool, "false_lesions", "iso")["estimate"], lambda v: sd(v, 2))
r = comp("secondary", "wmhsynthseg", "false_lesions", "iso")
E("1.32", "WMH-SynthSeg produced 1.32 fewer (95% CI 0.23–2.58)", C, "secondary[wmhsynthseg, false_lesions, iso].estimate (magnitude)", r["estimate"], lambda v: ad(v, 2))
E("0.23", "WMH-SynthSeg produced 1.32 fewer (95% CI 0.23–2.58)", C, "… .ci95[1] (magnitude)", r["ci95"][1], lambda v: ad(v, 2))
E("2.58", "WMH-SynthSeg produced 1.32 fewer (95% CI 0.23–2.58)", C, "… .ci95[0] (magnitude)", r["ci95"][0], lambda v: ad(v, 2))
E("0.086", "registered family (p~Holm~ = 0.086)", C, "secondary[wmhsynthseg, false_lesions, iso].p_holm_registered_family", r["p_holm_registered_family"], lambda v: f"{v:.3f}")
E("0.034", "Holm over only the eight tests performed would have given 0.034", C, "secondary[wmhsynthseg, false_lesions, iso].p_holm", r["p_holm"], lambda v: f"{v:.3f}")
for tool, w in (("mindglide", "−0.258"), ("wmhsynthseg", "−0.389"), ("lstai", "−0.156")):
    E(w, "(ΔF1 −0.258, −0.389 and −0.156 for MindGlide, WMH-SynthSeg and LST-AI)", C, f"sensitivity[S5, {tool}, f1].estimate", sens("S5_iso_with_flames_training_cases", tool, "f1")["estimate"], d)
E("0.765", "FLAMeS F1 was 0.765 in the iso band and 0.724 in the thick band", S, "per_band[iso, flames].f1.estimate", fi["f1"]["estimate"], d)
E("0.724", "FLAMeS F1 was 0.765 in the iso band and 0.724 in the thick band", S, "per_band[thick, flames].f1.estimate", fb["f1"]["estimate"], d)
E("0.518", "0.554, against 0.518 on all 145 iso scans and 0.492 on the 125 iso scans paired", S, "per_band[iso, mindglide].f1.estimate", pband("iso", "mindglide")["f1"]["estimate"], d)
E("0.554", "0.554, against 0.518 on all 145 iso scans and 0.492 on the 125 iso scans paired", S, "per_band[thick, mindglide].f1.estimate", pband("thick", "mindglide")["f1"]["estimate"], d)
r = comp("secondary", "mindglide", "f1", contrast=True)
for w, v, f in (("0.102", r["estimate"], "estimate"), ("0.047", r["ci95"][0], "ci95[0]"), ("0.160", r["ci95"][1], "ci95[1]")):
    E(w, "0.102 smaller in the thick cohorts than in the iso cohorts (95% CI 0.047–0.160; p~Holm~ < 0.003)", C, f"secondary[mindglide, degradation].{f}", v, d)
r = comp("secondary", "wmhsynthseg", "f1", contrast=True)
for w, v, f in (("−0.021", r["estimate"], "estimate"), ("−0.098", r["ci95"][0], "ci95[0]"), ("+0.056", r["ci95"][1], "ci95[1]")):
    E(w, "(−0.021, −0.098 to +0.056; p~Holm~ = 1.0)", C, f"secondary[wmhsynthseg, degradation].{f}", v, (lambda x: sd(x)) if w.startswith("+") else d)

# ============================================================================= 3.6 raw arm (prose)
r = comp("secondary_raw_arm", "mindglide-raw", "f1", "thick")
for w, v, f in (("−0.186", r["estimate"], "estimate"), ("−0.222", r["ci95"][0], "ci95[0]"), ("−0.150", r["ci95"][1], "ci95[1]")):
    E(w, "raw-input MindGlide had ΔF1 −0.186 (−0.222 to −0.150; p~Holm~ < 0.002)", C, f"secondary_raw_arm[mindglide-raw vs flames, f1].{f}", v, d)
r = comp("secondary_raw_arm", "mindglide-raw", "false_lesions", "thick")
for w, v, f in (("+0.38", r["estimate"], "estimate"), ("−0.94", r["ci95"][0], "ci95[0]"), ("+1.88", r["ci95"][1], "ci95[1]")):
    E(w, "+0.38 false lesions per scan (−0.94 to +1.88; p~Holm~ = 0.99)", C, f"secondary_raw_arm[mindglide-raw vs flames, false_lesions].{f}", v, lambda x: sd(x, 2))
E("0.99", "(−0.94 to +1.88; p~Holm~ = 0.99)", C, "secondary_raw_arm[… false_lesions].p_holm_registered_family (2 s.f.)", r["p_holm_registered_family"], lambda v: f"{v:.2g}")
r = comp("secondary_raw_arm", "mindglide-raw", "f1", "thick", vs="mindglide")
for w, v, f in (("−0.016", r["estimate"], "estimate"), ("−0.028", r["ci95"][0], "ci95[0]"), ("−0.004", r["ci95"][1], "ci95[1]")):
    E(w, "ΔF1 −0.016 (−0.028 to −0.004; p~Holm~ = 0.037)", C, f"secondary_raw_arm[mindglide-raw vs mindglide, f1].{f}", v, d)
E("0.037", "(−0.028 to −0.004; p~Holm~ = 0.037)", C, "… .p_holm_registered_family", r["p_holm_registered_family"], lambda v: f"{v:.3f}")
assert r["equivalent_within_margin"] and comp("secondary_raw_arm", "mindglide-raw", "false_lesions", "thick", vs="mindglide")["equivalent_within_margin"]
r = comp("secondary_raw_arm", "mindglide-raw", "false_lesions", "thick", vs="mindglide")
for w, v, f in (("−0.19", r["estimate"], "estimate"), ("−0.75", r["ci95"][0], "ci95[0]"), ("+0.32", r["ci95"][1], "ci95[1]")):
    E(w, "and −0.19 false lesions (−0.75 to +0.32)", C, f"secondary_raw_arm[mindglide-raw vs mindglide, false_lesions].{f}", v, lambda x: sd(x, 2))

# ============================================================================= 3.7 exploratory
mg = e1post("mindglide")
E("14", "FLAMeS had a lesion-wise F1 below 0.5 in 14 of 179 scans", X, "e1_posthoc[mindglide].n_poor", mg["n_poor"], i)
E("10", "(10 Muslim, 4 MS3SEG, 0 PediMS)", X, "e1_posthoc[mindglide].poor_by_cohort.muslim", mg["poor_by_cohort"]["muslim"], i)
E("4", "(10 Muslim, 4 MS3SEG, 0 PediMS)", X, "e1_posthoc[mindglide].poor_by_cohort.ms3seg", mg["poor_by_cohort"]["ms3seg"], i)
E("0", "(10 Muslim, 4 MS3SEG, 0 PediMS)", X, "e1_posthoc[mindglide].poor_by_cohort.pedims", mg["poor_by_cohort"]["pedims"], i)
E("0.779", "identified these scans with an AUROC of 0.779", C, "exploratory[mindglide, thick].auroc", expl_auc("mindglide", "thick")["auroc"], d)
E("0.597", "its 95% bootstrap interval was 0.597–0.925", X, "e1_posthoc[mindglide].auroc_ci95_posthoc[0]", mg["auroc_ci95_posthoc"][0], d)
E("0.925", "its 95% bootstrap interval was 0.597–0.925", X, "e1_posthoc[mindglide].auroc_ci95_posthoc[1]", mg["auroc_ci95_posthoc"][1], d)
E("0.819", "the cohort-stratified AUROC was 0.819", X, "e1_posthoc[mindglide].auroc_cohort_stratified_posthoc", mg["auroc_cohort_stratified_posthoc"], d)
w = e1post("wmhsynthseg")
E("0.593", "Disagreement with WMH-SynthSeg (0.593; post hoc CI 0.385–0.787)", C, "exploratory[wmhsynthseg, thick].auroc", expl_auc("wmhsynthseg", "thick")["auroc"], d)
E("0.385", "(0.593; post hoc CI 0.385–0.787)", X, "e1_posthoc[wmhsynthseg].auroc_ci95_posthoc[0]", w["auroc_ci95_posthoc"][0], d)
E("0.787", "(0.593; post hoc CI 0.385–0.787)", X, "e1_posthoc[wmhsynthseg].auroc_ci95_posthoc[1]", w["auroc_ci95_posthoc"][1], d)
E("0.488", "or SAMSEG (0.488; 11 poor scans of 129)", C, "exploratory[samseg, thick].auroc", expl_auc("samseg", "thick")["auroc"], d)
E("11", "or SAMSEG (0.488; 11 poor scans of 129)", C, "exploratory[samseg, thick].n_poor", expl_auc("samseg", "thick")["n_poor"], i)
E("2", "On the 1 mm grid only 2 scans were poor", C, "exploratory[mindglide, iso].n_poor", expl_auc("mindglide", "iso")["n_poor"], i)
for tool, wv in (("mindglide", "0.813"), ("lstai", "0.803"), ("wmhsynthseg", "0.520")):
    E(wv, "(MindGlide 0.813, LST-AI 0.803, WMH-SynthSeg 0.520)", C, f"exploratory[{tool}, iso].auroc", expl_auc(tool, "iso")["auroc"], d)
cf = expl_conf("mindglide", "thick")
for wv, v, f in (("−3.8", cf["false_lesions"]["estimate"], "false_lesions.estimate"), ("−4.7", cf["false_lesions"]["ci95"][0], "false_lesions.ci95[0]"),
                 ("−2.8", cf["false_lesions"]["ci95"][1], "false_lesions.ci95[1]")):
    E(wv, "−3.8 false lesions per scan (95% CI −4.7 to −2.8)", C, f"exploratory[confirmed, mindglide, thick].{f}", v, lambda x: d(x, 1))
for wv, v, f in (("−0.074", cf["f1"]["estimate"], "f1.estimate"), ("−0.111", cf["f1"]["ci95"][0], "f1.ci95[0]"), ("−0.040", cf["f1"]["ci95"][1], "f1.ci95[1]")):
    E(wv, "ΔF1 −0.074 (−0.111 to −0.040)", C, f"exploratory[confirmed, mindglide, thick].{f}", v, d)

# ============================================================================= 3.8 runtime, Table 5
mgr = [run("toolbench-mindglide-a")["seconds_per_case"]["median"], run("toolbench-mindglide-b")["seconds_per_case"]["median"]]
E("77–84", "were 77–84 s for MindGlide", V, "runs[toolbench-mindglide-a/b].seconds_per_case.median", mgr, lambda v: f"{min(v):.0f}–{max(v):.0f}")
E("5.91", "peak memory ≤ 5.91 GB", V, "max runs[toolbench-mindglide-*].peak_mem_gb_max", max(run(x)["peak_mem_gb_max"] for x in ("toolbench-mindglide-a", "toolbench-mindglide-b", "toolbench-pilot-mindglide-3")), lambda v: f"{v:.2f}")
E("216", "216 s for WMH-SynthSeg (n2d-highmem-4; peak 31.3 GB plus up to 14.4 GB of swap)", V, "runs[toolbench-wmh].seconds_per_case.median", run("toolbench-wmh")["seconds_per_case"]["median"], lambda v: f"{v:.0f}")
E("31.3", "peak 31.3 GB plus up to 14.4 GB of swap", V, "runs[toolbench-wmh].peak_mem_gb_max", run("toolbench-wmh")["peak_mem_gb_max"], lambda v: f"{v:.1f}")
E("14.4", "peak 31.3 GB plus up to 14.4 GB of swap", V, "runs[toolbench-wmh].peak_swap_gb_max", run("toolbench-wmh")["peak_swap_gb_max"], lambda v: f"{v:.1f}")
sm = [run(x)["seconds_per_case"]["median"] for x in ("toolbench-samseg-a", "toolbench-samseg-b", "toolbench-samseg-c")]
E("470–524", "470–524 s per run for SAMSEG on thick scans", V, "runs[toolbench-samseg-a/b/c].seconds_per_case.median", sm, lambda v: f"{min(v):.0f}–{max(v):.0f}")
E("7.1", "peak ≤ 7.1 GB, pilot included", V, "max runs[toolbench-pilot-fs-2, samseg-*].peak_mem_gb_max",
  max(run(x)["peak_mem_gb_max"] for x in ("toolbench-pilot-fs-2", "toolbench-samseg-a", "toolbench-samseg-b", "toolbench-samseg-c")), lambda v: f"{v:.1f}")
lit("15", "the pre-stated CPU rule of ≤ 15 minutes per scan", "docs/research/paper-f/PROTOCOL.md", "section 3, CPU feasibility rule")
fl = [float(led(x)["median_seconds_per_item"]) for x in ("flames-full-a", "flames-full-b", "flames-full-c", "flames-extra-a", "flames-extra-b")]
E("67.5–69.1", "FLAMeS took 67.5–69.1 s per fold and scan", L, "median_seconds_per_item of flames-full-a/b/c, flames-extra-a/b", fl, lambda v: f"{min(v):.1f}–{max(v):.1f}")
E("5.7", "(about 5.7 minutes for the five folds without test-time mirroring)", L, "5 × median of the five run medians / 60", 5 * sorted(fl)[2] / 60, lambda v: f"{v:.1f}")
E("5.7", "ran in about 5.7 minutes per scan on 4 vCPUs here", L, "5 × median of the five run medians / 60", 5 * sorted(fl)[2] / 60, lambda v: f"{v:.1f}")
G = EXTRA["compute"]["by_group"]
for key, label in (("pilots", "Pilots (MindGlide, FreeSurfer tools)"), ("mindglide_primary", "MindGlide, primary arm (324 scans)"),
                   ("mindglide_raw_arm", "MindGlide, raw-input arm (179 scans)"), ("wmhsynthseg", "WMH-SynthSeg (324 scans, incl. one `--crop` re-run)"),
                   ("samseg_tier_c", "SAMSEG, tier C (127 scans + 2 from pilots)")):
    g = G[key]
    rowtxt = f"| {label} | {g['runs']} | {g['vm_hours']:.2f} | {g['usd_list']:.2f} |"
    E(norm(rowtxt), rowtxt, X, f"compute.by_group.{key}: runs, vm_hours, usd_list", norm(rowtxt), lambda v: v)
c = EXTRA["compute"]
rowtxt = f"| **Total, this study** | **{c['runs']}** | **{c['vm_hours']:.2f}** | **{c['usd_list']:.2f}** |"
E(norm(rowtxt), rowtxt, X, "compute: runs, vm_hours, usd_list", norm(rowtxt), lambda v: v)
U = c["upstream_not_paper_f"]
for key, label in (("flames_iso_maps", "Earlier runs reused: FLAMeS maps, 1 mm cohorts"), ("flames_thick_maps_incl_hdbet", "Earlier runs reused: HD-BET + FLAMeS maps, thick cohorts"),
                   ("lstai_maps", "Earlier runs reused: LST-AI maps")):
    g = U[key]
    rowtxt = f"| {label} | {g['runs']} | {g['vm_hours']:.2f} | {g['usd_list']:.2f} |"
    E(norm(rowtxt), rowtxt, X, f"compute.upstream_not_paper_f.{key}", norm(rowtxt), lambda v: v)
E("127", "SAMSEG, tier C (127 scans + 2 from pilots)", V, "sum runs[toolbench-samseg-a/b/c].n_ok", sum(run(x)["n_ok"] for x in ("toolbench-samseg-a", "toolbench-samseg-b", "toolbench-samseg-c")), i)
for w in ("13.9", "17.8"):
    lit(w, "(about 13.9 USD in total) but tier A would not (about 17.8 USD)", "results/RESULTS.md", "section 5")

# ============================================================================= discussion, limitations, conclusion
pr = [abs(comp("primary", t, "f1", "thick")["estimate"]) for t in ("mindglide", "wmhsynthseg", "samseg")]
E("0.17–0.38", "The F1 deficits (0.17–0.38 F1)", C, "primary[*, f1].estimate magnitudes (min–max)", pr, lambda v: f"{min(v):.2f}–{max(v):.2f}")
E("5–6%", "detect only 5–6% of small expert lesions", S, "size_bins[thick, wmhsynthseg/samseg, 14-50].estimate", [sbin("thick", "wmhsynthseg", "14-50")["estimate"], sbin("thick", "samseg", "14-50")["estimate"]],
  lambda v: f"{round(100 * min(v))}–{round(100 * max(v))}%")
E("200", "miss most lesions below 200 mm³", S, "size_bins[thick, wmhsynthseg/samseg, 50-200].estimate < 0.5", max(sbin("thick", t, "50-200")["estimate"] for t in ("wmhsynthseg", "samseg")), lambda v: "200" if v < 0.5 else "?")
lit("15%", "failed on 15% of visually assessed contrasts, particularly with slices thicker than 5 mm", "Goebl et al. 2025 (PMC11976987), quoted in references.bib notes", "65 of 433 contrasts")
E("28.4", "(28.4 mL predicted vs 11.8 mL expert", S, "per_cohort[mslesseg, mindglide].vol_pred_ml.estimate", pcoh("mslesseg", "mindglide")["vol_pred_ml"]["estimate"], lambda v: f"{v:.1f}")
E("11.8", "(28.4 mL predicted vs 11.8 mL expert", S, "per_cohort[mslesseg, mindglide].vol_ref_ml.estimate", pcoh("mslesseg", "mindglide")["vol_ref_ml"]["estimate"], lambda v: f"{v:.1f}")
E("0.78", "with an AUROC of 0.78 (exploratory; post hoc 95% interval about 0.60 to 0.93). A score", C, "exploratory[mindglide, thick].auroc", expl_auc("mindglide", "thick")["auroc"], lambda v: f"{v:.2f}")
E("0.60", "post hoc 95% interval about 0.60 to 0.93", X, "e1_posthoc[mindglide].auroc_ci95_posthoc[0]", mg["auroc_ci95_posthoc"][0], lambda v: f"{v:.2f}")
E("0.93", "post hoc 95% interval about 0.60 to 0.93", X, "e1_posthoc[mindglide].auroc_ci95_posthoc[1]", mg["auroc_ci95_posthoc"][1], lambda v: f"{v:.2f}")

E("129", "SAMSEG covers 129 of the 179 thick scans", C, "primary[samseg].n_scans", comp("primary", "samseg", "f1", "thick")["n_scans"], i)

lit("31.32", "the pilot peak (31.32 GB) exceeded the pre-stated 30 GB trigger", "results/verify_runs.json + PROTOCOL.md 4.2", "runs[toolbench-pilot-fs].peak_mem_gb_max = 31.32; trigger 30 GB")
assert run("toolbench-pilot-fs")["peak_mem_gb_max"] == 31.32
lit("80", "boot disk 80 GB instead of 150 GB", "docs/research/paper-f/PROTOCOL.md", "section 12, row 2026-10-28")
E("6,906", "(`research/paper_f/results/per_scan.csv.gz`, 6,906 rows)", X, "_provenance.per_scan_rows", EXTRA["_provenance"]["per_scan_rows"], i)
n_commits = len(git("log", "--format=%h", "65a95e3^..1d3be48", "--", "research/paper_f", "docs/research/paper-f", "research/cloud").split())
E("13", "All 13 commits of the study branch", "git", "git log 65a95e3^..1d3be48 -- research/paper_f docs/research/paper-f research/cloud | wc -l", n_commits, i)
tr = git("log", "--format=%(trailers:key=Co-Authored-By,valueonly)", "65a95e3^..1d3be48", "--", "research/paper_f", "docs/research/paper-f", "research/cloud").decode()
assert tr.count("Claude") == n_commits
E("790,531,383", "790,531,383 bytes", V, "runs[toolbench-wmh].wmh_model.bytes", run("toolbench-wmh")["wmh_model"]["bytes"], i)
lit(run("toolbench-wmh")["wmh_model"]["sha256"], "SHA-256 `0ece39dd651357aa95222fc4d45fa32d00f11e763d2583cae3f869989ce35988`", V, "runs[toolbench-wmh].wmh_model.sha256")
lit(run("toolbench-wmh")["fs_build"], "(build `freesurfer-linux-rocky8_x86_64-8.2.0-20260314-d932c45`)", V, "runs[toolbench-wmh].fs_build")
lit(RUNI["inputs_digest_sha256"], "input-list digest `d50d356bcd6676b38fb10545f1f0a659a49582ba4d83ad8c5567bdcc9dd0b43b`", "results/run_info.json", "inputs_digest_sha256")
for dig, src in (("sha256:14e88f61d6cba18322d03774b168682e255383387aaab55e6a5aa33a2dbdd971", "docs/research/paper-f/RUNBOOK.md"),
                 ("881e30efd9444a25ee70c01d795dd9fb21ac750a48f1ba8070fcd79fb75e76ca", "docs/research/paper-f/RUNBOOK.md"),
                 ("sha256:5648104ca75a24f6ee5a8786146f99b405c2bda1da12bff723a15056da8ddf6b", "docs/research/paper-f/RUNBOOK.md"),
                 ("sha256:2b2a0d6454e6efff60a350df3c650ae9584f1926338dec7842f9e71912cc6c85", "research/cloud/lstai_driver.py")):
    assert dig in text(src), dig
    lit(dig, dig, src, "pinned identifier")
for f, short in (("docs/research/paper-f/PROTOCOL.md", "587ba9ff"), ("research/paper_f/metrics.py", "8aae0587"),
                 ("research/paper_f/evaluate.py", "93512380"), ("research/paper_f/flames_inputs.json", "4847df6d")):
    h = hashlib.sha256(git("show", f"65a95e3:{f}")).hexdigest()
    E(short, f"`{short}", "git show 65a95e3:" + f, "SHA-256 (first 8 hex)", h, lambda v: v[:8])
for tool, cells in (("wmhsynthseg", "| WMH-SynthSeg | 324 | 324 | 0 | 1 (out of memory → `--crop`) |"),
                    ("mindglide", "| MindGlide, primary | 324 | 324 | 0 | 3 (pilot setup error) |"),
                    ("mindglide-raw", "| MindGlide, raw input | 179 | 179 | 0 | 3 (10 h time guard) |")):
    t = VER["tools"][tool]
    vals = (t["planned"], t["ok"], len(t["failed_never_recovered"]), len(t["failed_then_recovered"]))
    E(cells, cells, V, f"tools.{tool}: planned, ok, failed_never_recovered, failed_then_recovered", vals,
      lambda v, c=cells: c if [str(x) for x in v] == re.findall(r"\| (\d+)", c)[:4] else str(v))
t = VER["tools"]["samseg"]
row_s = "| SAMSEG, tier C | 129 | 128 + 1 verified by voxel count | 0 | 0 |"
E(row_s, row_s, V, "tools.samseg: planned, ok (+1 without manifest record), failed_never_recovered, failed_then_recovered",
  (t["planned"], t["ok"], len(t["failed_never_recovered"]), len(t["failed_then_recovered"])),
  lambda v: row_s if v == (129, 128, 0, 0) else str(v))


# ============================================================================= versions, constants and identifiers in prose
for w, ctx, src, fld in (
    ("1.0", "The protocol (version 1.0, 2026-10-21)", "docs/research/paper-f/PROTOCOL.md", "title: version 1.0"),
    ("2.0", "(Zenodo 17955359, version 2.0, CC BY 4.0)", "references.bib larosa2025flameszenodo (Zenodo API)", "version 2.0"),
    ("1.2.0", "**LST-AI** 1.2.0 (three U-Nets, FLAIR + T1)", "docs/research/paper-f/PROTOCOL.md", "section 3: LST-AI v1.2.0"),
    ("1.3.0", "**MindGlide** 1.3.0", "docs/research/paper-f/PROTOCOL.md / RUNBOOK.md", "MindGlide 1.3.0 digest"),
    ("8.2.0", "FreeSurfer 8.2.0 [@fischl2012freesurfer] (labels 77 and 99)", "results/verify_runs.json", "runs[].fs_build contains 8.2.0"),
    ("231110", "FreeSurfer 8.2.0; model v10 (231110)", "results/verify_runs.json / RUNBOOK.md", "model file WMH-SynthSeg_v10_231110.pth"),
    ("12345", "--random-seed 12345", "results/verify_runs.json", "runs[].samseg_seed = 12345"),
    ("1000", "50–200, 200–1000 and ≥ 1000 mm³)", "research/paper_f/metrics.py", "SIZE_BINS_MM3"),
    ("0.0001", "rather than the \"< 0.0001\" printed by the analysis tables", "research/paper_f/summarize.py", "pfmt(): '< 0.0001' if p < 1e-4"),
    ("90", "Equivalence was declared when the 90% interval lay inside", "research/paper_f/metrics.py", "summarize(): ci90 = percentiles 5, 95"),
        ("0.1", "flags a Dice below 0.1 as a probable label or orientation error", "research/paper_f/evaluate.py", "check_case(): WARN if Dice < 0.1"),
    ("4", "on 4 vCPUs", "manuscript/data/compute_ledger_c8b4239.csv", "vcpus"),
        ("7.6", "Secondary arm 7.6 registered: MindGlide on the raw FLAIR", "docs/research/paper-f/PROTOCOL.md", "section 7.6 (protocol section number)"),
    ("10.5281", "Zenodo 10.5281/zenodo.17955359, version 2.0", "references.bib", "larosa2025flameszenodo.doi"),
):
    lit(w, ctx, src, fld)
assert run("toolbench-wmh")["samseg_seed"] == 12345 and "8.2.0" in run("toolbench-wmh")["fs_build"]
assert M.SIZE_BINS_MM3[3] == 1000.0
for ctx in ("lesions were 3D components ≥ 14.1 mm³ matched by any overlap", "expert lesions counted after the 14.1 mm³ size filter",
            "(3D components ≥ 14.1 mm³)"):
    if norm(ctx) in MSN:
        E("14.1", ctx, "research/paper_f/metrics.py", "SPHERE_3MM_MM3", M.SPHERE_3MM_MM3, lambda v: f"{v:.1f}")
E("22", "and LST-AI was run on 2026-10-22", "docs/research/paper-f/RESULTS-interim.md", "title date 2026-10-22", "22", str)

ratios = [pcoh(c, "wmhsynthseg")["vol_pred_ml"]["estimate"] / pcoh(c, "wmhsynthseg")["vol_ref_ml"]["estimate"] for c in th]
E("about a quarter to a third", "marked only about a quarter to a third of the expert lesion volume in every cohort", S,
  "per_cohort[thick cohorts, wmhsynthseg].vol_pred_ml / vol_ref_ml (0.265–0.335)", ratios,
  lambda v: "about a quarter to a third" if 0.24 <= min(v) and max(v) <= 0.34 else str(v))


# ============================================================================= REVISION (2026-10-31) - new numbers
RV = EXTRA["revision"]
FP_CHECK = J(DATA, "flames_fingerprint_check.json")
MSL_CHECK = J(DATA, "mslesseg_flames_overlap_check_87e998d.json")
WMH = J(DATA, "wmh_resampling_posthoc.json")
FPX = "manuscript/data/flames_fingerprint_check.json"
WX = "manuscript/data/wmh_resampling_posthoc.json"
for ctx in ("- FLAMeS, trained only on voxels of 1.25 mm or less, led on 3.9–8.3 mm FLAIR.",
            "every voxel dimension in the released fingerprint ≤ 1.25 mm",
            "None of the 668 training entries has a voxel dimension above 1.25 mm",
            "The fingerprint also shows that FLAMeS never saw a voxel dimension larger than 1.25 mm in training.",
            "contained no voxel dimension larger than 1.25 mm",
                        "yet no FLAMeS training case has a voxel dimension above 1.25 mm (Section 2.3)",
            "and no FLAMeS training case has a voxel dimension above 1.25 mm, so no thick-slice scan was a training case"):
    E("1.25", ctx, FPX, "max_largest_voxel_dimension_mm (n entries > 3 mm = 0)", FP_CHECK["max_largest_voxel_dimension_mm"], lambda v: f"{v:.2f}")
assert FP_CHECK["n_entries_with_slice_spacing_above_3mm"] == 0
E("668", "None of the 668 training entries has a voxel dimension above 1.25 mm", FPX, "n_training_entries", FP_CHECK["n_training_entries"], i)
E("319", "bounding box of any of the 319 training entries with 1 mm spacing", "manuscript/data/mslesseg_flames_overlap_check_87e998d.json", "n_1mm_training_entries", MSL_CHECK["n_1mm_training_entries"], i)
E("115", "None of the 115 MSLesSeg scans matches the", "manuscript/data/mslesseg_flames_overlap_check_87e998d.json", "n_checked (n_exact_hits = 0)", MSL_CHECK["n_checked"], i)
assert MSL_CHECK["n_exact_hits"] == 0
first_vm = min(r["start_utc"] for r in LEDGER if r["run_id"].startswith("toolbench"))
E("21:31", "first virtual machine had been created at 21:31 UTC", L, "min(start_utc) of toolbench runs", first_vm, lambda v: v[11:16])
for w, ctx in (("2.61", "the data paper reports a mean slice thickness of 2.61 mm (SD 0.62)"),
               ("0.62", "the data paper reports a mean slice thickness of 2.61 mm (SD 0.62)"),
               ("2.6", "acquired with slices of about 2.6 mm")):
    lit(w, ctx, "Guarnera et al. 2025, Sci Data 12:920, Table 2 (PMC12126551; references.bib revision notes)", "FLAIR slice thickness mean (SD)")
pix = sorted({tuple(v["flair_pixdim_nifti"]) for v in SPLIT["patients"].values()})
E("0.47", "near-isotropic 3D FLAIR at 3 T (0.47 × 0.47 × 0.8–0.9 mm voxels)", "manuscript/data/flames_ljubljana_split_87e998d.json", "patients[*].flair_pixdim_nifti (in-plane)", pix[0][1], lambda v: f"{v:.2f}")
E("0.8–0.9", "near-isotropic 3D FLAIR at 3 T (0.47 × 0.47 × 0.8–0.9 mm voxels)", "manuscript/data/flames_ljubljana_split_87e998d.json", "patients[*].flair_pixdim_nifti (slice)", [p[0] for p in pix], lambda v: f"{min(v):.1f}–{max(v):.1f}")
iso_by = RV["iso_flames_scans_by_cohort"]
for ctx in ("115 of its 125 FLAMeS comparison scans were acquired with slices of about 2.6 mm",
            "115 of its 125 FLAMeS comparison scans come from MSLesSeg",
            "115 of its 125 FLAMeS comparison scans were acquired with slices of"):
    if norm(ctx) in MSN:
        E("115 of its 125", ctx, X, "revision.iso_flames_scans_by_cohort (mslesseg, total)", (iso_by["mslesseg"], sum(iso_by.values())), lambda v: f"{v[0]} of its {v[1]}")
n151 = EXTRA["cohorts"]["ms3seg"]["scans"] + EXTRA["cohorts"]["muslim"]["scans"]
for ctx in ("MS3SEG and Muslim (151 of the 179 thick scans) were stripped with",
            "used to skull-strip 151 of the 179 thick scans (MS3SEG, Muslim et al.)"):
    E("151", ctx, X, "cohorts.ms3seg.scans + cohorts.muslim.scans", n151, i)
lit("14445620", "Zenodo record 14445620, downloaded by HD-BET 2.x", "Zenodo API (records/14445620; references.bib hdbet2024params)", "record id; licence cc-by-nc-4.0")
p_mg = comp("primary", "mindglide", "false_lesions", "thick")["p_two_sided"]
E("0.45", "standard error of a bootstrap p near 0.45 is about 0.008", C, "primary[mindglide, false_lesions].p_two_sided", p_mg, lambda v: f"{v:.2f}")
E("0.008", "standard error of a bootstrap p near 0.45 is about 0.008", X, "revision.mc_se_of_p_at_mindglide_fp.se", RV["mc_se_of_p_at_mindglide_fp"]["se"], lambda v: f"{v:.3f}")
E("6.9%", "for scale, 0.05 is 6.9% of FLAMeS's thick-band F1", S, "0.05 / per_band[thick, flames].f1.estimate", 0.05 / fb["f1"]["estimate"], lambda v: f"{100 * v:.1f}%")
E("14%", "one false lesion is 14% of its 6.9 false lesions per scan", S, "1 / per_band[thick, flames].false_lesions.estimate", 1 / fb["false_lesions"]["estimate"], lambda v: f"{100 * v:.0f}%")
E("6.9", "one false lesion is 14% of its 6.9 false lesions per scan", S, "per_band[thick, flames].false_lesions.estimate", fb["false_lesions"]["estimate"], lambda v: f"{v:.1f}")
cst = EXTRA["compute"]
for ctx in ("the total is 101.97 machine-hours and 19.84 USD at list price",):
    E("101.97", ctx, X, "compute.vm_hours_including_reused_runs", cst["vm_hours_including_reused_runs"], lambda v: f"{v:.2f}")
    E("19.84", ctx, X, "compute.usd_list_including_reused_runs", cst["usd_list_including_reused_runs"], lambda v: f"{v:.2f}")
rowtxt = f"| **Total including reused runs** | **{cst['runs'] + sum(g['runs'] for g in cst['upstream_not_paper_f'].values())}** | **{cst['vm_hours_including_reused_runs']:.2f}** | **{cst['usd_list_including_reused_runs']:.2f}** |"
E(norm(rowtxt), rowtxt, X, "compute: runs + upstream runs, vm_hours_including_reused_runs, usd_list_including_reused_runs", norm(rowtxt), lambda v: v)
lit("00:01:59", "it was run on 2026-10-29 at 00:01:59 UTC, 21 s after the decisions of that date",
    "agent session log (outside the repository; owner TODO to archive)", "timestamp of the `evaluate.py check` command")
E("21", "00:01:59 UTC, 21 s after the decisions of that date were pushed (00:01:38 UTC)", "derived", "00:01:59 − push of 7a9a24e", p7["timestamp"],
  lambda v: str(int((_dt.datetime.fromisoformat("2026-10-29T00:01:59+00:00") - _dt.datetime.fromisoformat(v.replace("Z", "+00:00"))).total_seconds())))
E("00:01:38", "were pushed (00:01:38 UTC)", "manuscript/data/github_push_activity_paper_f_branch.json", "push after=7a9a24e .timestamp", p7["timestamp"], lambda v: v[11:19])
E("nine", "and nine minutes before the final analysis (00:11 UTC)", "results/run_info.json", "created_utc − 00:01:59 (minutes, floor)", RUNI["created_utc"],
  lambda v: {9: "nine"}.get(int((_dt.datetime.fromisoformat(v.replace("Z", "+00:00")) - _dt.datetime.fromisoformat("2026-10-29T00:01:59+00:00")).total_seconds() // 60), "?"))
mgstart = sorted(led(x)["start_utc"] for x in ("toolbench-mindglide-a", "toolbench-mindglide-b"))
E("about ten minutes earlier", "the MindGlide full-run machines had started about ten minutes earlier", L, "start_utc of toolbench-mindglide-a/b vs push 22:43:47", mgstart,
  lambda v: "about ten minutes earlier" if 8 <= (_dt.datetime.fromisoformat("2026-10-21T22:43:47+00:00") - _dt.datetime.fromisoformat(v[-1].replace("Z", "+00:00"))).total_seconds() / 60 <= 12 else "?")
E("22:32–22:34", "The MindGlide full-run machines had started at 22:32–22:34 and were computing", L, "start_utc of toolbench-mindglide-a/b", mgstart, lambda v: f"{v[0][11:16]}–{v[1][11:16]}")
# per-cohort ranges (thick) and iso per-cohort values
PCD = RV["per_cohort_paired_differences"]
for tool, ctx in (("mindglide", "per-cohort ΔF1 ranged from −0.123 to −0.226 for MindGlide"), ("samseg", "from −0.226 to −0.255 for SAMSEG"),
                  ("wmhsynthseg", "from −0.279 to −0.467 for WMH-SynthSeg, every 95% interval excluding zero")):
    vals = [PCD[f"{tool}|{c}"]["f1"]["estimate"] for c in th]
    assert all(PCD[f"{tool}|{c}"]["f1"]["ci95"][1] < 0 for c in th)
    E(d(max(vals)), ctx, X, f"revision.per_cohort_paired_differences[{tool}|thick cohorts].f1.estimate (max)", max(vals), d)
    E(d(min(vals)), ctx, X, f"revision.per_cohort_paired_differences[{tool}|thick cohorts].f1.estimate (min)", min(vals), d)
for tool, c, w in (("wmhsynthseg", "mslesseg", "−0.286"), ("wmhsynthseg", "openms", "−0.440"), ("mindglide", "mslesseg", "−0.227"), ("mindglide", "openms", "−0.318")):
    E(w, "WMH-SynthSeg's ΔF1 was −0.286 on MSLesSeg (115 scans) and −0.440 on Ljubljana (10 scans), and MindGlide's −0.227 and −0.318",
      X, f"revision.per_cohort_paired_differences[{tool}|{c}].f1.estimate", PCD[f"{tool}|{c}"]["f1"]["estimate"], d)
# Table A3 rows
CN = {"ms3seg": "MS3SEG", "muslim": "Muslim et al.", "pedims": "PediMS", "mslesseg": "MSLesSeg", "openms": "Ljubljana"}
TN = {"mindglide": "MindGlide", "wmhsynthseg": "WMH-SynthSeg", "samseg": "SAMSEG", "lstai": "LST-AI"}
for tool, cohorts in (("mindglide", ("ms3seg", "muslim", "pedims", "mslesseg", "openms")), ("wmhsynthseg", ("ms3seg", "muslim", "pedims", "mslesseg", "openms")),
                      ("samseg", ("ms3seg", "muslim", "pedims")), ("lstai", ("mslesseg", "openms"))):
    for c in cohorts:
        r = PCD[f"{tool}|{c}"]
        cname = "MS3SEG (odd ids)" if (tool == "samseg" and c == "ms3seg") else CN[c]
        rowtxt = (f"| {TN[tool]} | {cname} | {r['n_scans']} | {d(r['f1']['estimate'])} ({d(r['f1']['ci95'][0])} to {d(r['f1']['ci95'][1])}) | "
                  f"{sd(r['false_lesions']['estimate'], 2)} |")
        E(norm(rowtxt), rowtxt, X, f"revision.per_cohort_paired_differences[{tool}|{c}]: n_scans, f1 estimate/ci95, false_lesions estimate", norm(rowtxt), lambda v: v)
# paired-set absolute F1 (between-band contrast)
PS = RV["paired_set_absolute_f1"]
E("0.492", "and 0.492 on the 125 iso scans paired with FLAMeS", X, "revision.paired_set_absolute_f1['mindglide|iso'].tool_f1.estimate (n 125)", PS["mindglide|iso"]["tool_f1"]["estimate"], d)
assert PS["mindglide|iso"]["n_scans"] == 125
E("0.743", "against 0.743 for FLAMeS on the same 129 scans", X, "revision.tier_c_precision.flames_all_129.estimate", RV["tier_c_precision"]["flames_all_129"]["estimate"], d)
E("0.743", "On the same tier-C scans FLAMeS's precision was 0.743", X, "revision.tier_c_precision.flames_all_129.estimate", RV["tier_c_precision"]["flames_all_129"]["estimate"], d)
E("2.4-fold", "its 2.4-fold over-segmentation of lesion volume on MSLesSeg", S, "per_cohort[mslesseg, mindglide].vol_pred_ml / vol_ref_ml",
  pcoh("mslesseg", "mindglide")["vol_pred_ml"]["estimate"] / pcoh("mslesseg", "mindglide")["vol_ref_ml"]["estimate"], lambda v: f"{v:.1f}-fold")
# micro F1
MF = RV["micro_f1_posthoc"]
for key, ctx in (("mindglide|thick", "tool minus FLAMeS −0.173 (95% CI −0.202 to −0.148) for MindGlide"), ("samseg|thick", "−0.285 (−0.352 to −0.216) for SAMSEG"),
                 ("wmhsynthseg|thick", "−0.429 (−0.465 to −0.391) for WMH-SynthSeg on the thick band")):
    r = MF[key]
    for f, v in (("difference", r["difference"]), ("ci95[0]", r["ci95"][0]), ("ci95[1]", r["ci95"][1])):
        E(d(v), ctx, X, f"revision.micro_f1_posthoc['{key}'].{f}", v, d)
E("4", "(4 thick scans have fewer than 5 reference lesions, 3 of them 2 or fewer)", X, "revision.thick_scans_with_fewer_than_5_ref_lesions", RV["thick_scans_with_fewer_than_5_ref_lesions"], i)
E("3", "(4 thick scans have fewer than 5 reference lesions, 3 of them 2 or fewer)", X, "revision.thick_scans_with_at_most_2_ref_lesions", RV["thick_scans_with_at_most_2_ref_lesions"], i)
lit("5", "(4 thick scans have fewer than 5 reference lesions, 3 of them 2 or fewer)", "compute_extra_numbers.py", "threshold of the count (n_ref < 5)")
# WMH resampling (text + Table A4)
WV = WMH["variants"]
for key, w in (("hard_majority", "0.341"), ("prob_mean_ge_0.50", "0.315"), ("prob_mean_ge_0.25", "0.413"), ("prob_mean_ge_0.10", "0.469")):
    E(w, "changed its F1 on the thick band from 0.341 (pre-registered mask) to 0.315, 0.413 and 0.469", WX, f"variants.{key}.absolute.f1.estimate", WV[key]["absolute"]["f1"]["estimate"], d)
for w in ("0.50", "0.25", "0.10"):
    lit(w, "at probability thresholds of 0.50, 0.25 and 0.10", "manuscript/wmh_resampling_posthoc.py", "THRESH (fixed before computing)")
E("4.55", "Its predicted volume rose from 4.55 to 13.48 mL", WX, "variants.hard_majority.absolute.vol_pred_ml.estimate", WV["hard_majority"]["absolute"]["vol_pred_ml"]["estimate"], lambda v: f"{v:.2f}")
E("13.48", "Its predicted volume rose from 4.55 to 13.48 mL", WX, "variants.prob_mean_ge_0.10.absolute.vol_pred_ml.estimate", WV["prob_mean_ge_0.10"]["absolute"]["vol_pred_ml"]["estimate"], lambda v: f"{v:.2f}")
E("0.050", "its detection of 14–50 mm³ lesions from 0.050 to 0.104", WX, "variants.hard_majority.small_14_50_detected_pooled.proportion", WV["hard_majority"]["small_14_50_detected_pooled"]["proportion"], d)
E("0.104", "its detection of 14–50 mm³ lesions from 0.050 to 0.104", WX, "variants.prob_mean_ge_0.10.small_14_50_detected_pooled.proportion", WV["prob_mean_ge_0.10"]["small_14_50_detected_pooled"]["proportion"], d)
v10 = WV["prob_mean_ge_0.10"]["vs_flames"]
for w, v, f in (("−0.256", v10["f1"]["estimate"], "estimate"), ("−0.309", v10["f1"]["ci95"][0], "ci95[0]"), ("−0.208", v10["f1"]["ci95"][1], "ci95[1]")):
    E(w, "(ΔF1 −0.256, 95% CI −0.309 to −0.208)", WX, f"variants.prob_mean_ge_0.10.vs_flames.f1.{f}", v, d)
E("−5.69", "still had fewer false lesions (−5.69 per scan)", WX, "variants.prob_mean_ge_0.10.vs_flames.false_lesions.estimate", v10["false_lesions"]["estimate"], lambda v: d(v, 2))
assert WMH["_provenance"]["hard_majority_reproduces_per_scan_csv"]
for key, label in (("hard_majority", "Pre-registered: footprint majority of the hard label"), ("prob_mean_ge_0.50", "Probability ≥ 0.50"),
                   ("prob_mean_ge_0.25", "Probability ≥ 0.25"), ("prob_mean_ge_0.10", "Probability ≥ 0.10")):
    a, vf = WV[key]["absolute"], WV[key]["vs_flames"]
    rowtxt = (f"| {label} | {d(a['f1']['estimate'])} | {d(vf['f1']['estimate'])} ({d(vf['f1']['ci95'][0])} to {d(vf['f1']['ci95'][1])}) | "
              f"{d(vf['false_lesions']['estimate'], 2)} | {d(a['recall']['estimate'])} | {a['vol_pred_ml']['estimate']:.2f} | "
              f"{WV[key]['small_14_50_detected_pooled']['proportion']:.3f} |")
    E(norm(rowtxt), rowtxt, WX, f"variants.{key}: absolute f1/recall/vol, vs_flames f1/false_lesions, small_14_50", norm(rowtxt), lambda v: v)
# E1 baselines
EB = RV["e1_baselines_posthoc"]
fl_ = EB["fewer_flames_lesions"]
E("0.932", "identified the poor scans with an AUROC of 0.932", X, "revision.e1_baselines_posthoc.fewer_flames_lesions.auroc", fl_["auroc"], d)
E("0.861", "(95% CI 0.861–0.987; cohort-stratified 0.956)", X, "… .fewer_flames_lesions.auroc_ci95[0]", fl_["auroc_ci95"][0], d)
E("0.987", "(95% CI 0.861–0.987; cohort-stratified 0.956)", X, "… .fewer_flames_lesions.auroc_ci95[1]", fl_["auroc_ci95"][1], d)
E("0.956", "(95% CI 0.861–0.987; cohort-stratified 0.956)", X, "… .fewer_flames_lesions.auroc_cohort_stratified", fl_["auroc_cohort_stratified"], d)
E("0.840", "ranking by smaller FLAMeS lesion volume gave 0.840", X, "… .smaller_flames_volume.auroc", EB["smaller_flames_volume"]["auroc"], d)
E("0.884", "(sum of ranks) gave 0.884, lower than the count alone", X, "… .rank_sum_fewer_lesions_and_disagreement.auroc", EB["rank_sum_fewer_lesions_and_disagreement"]["auroc"], d)
E("0.733", "(Muslim et al. or not) gave 0.733", X, "… .cohort_is_muslim.auroc", EB["cohort_is_muslim"]["auroc"], d)
E("0.93", "gave an AUROC of 0.93 (post hoc)", X, "… .fewer_flames_lesions.auroc", fl_["auroc"], lambda v: f"{v:.2f}")
assert abs(EB["mindglide_disagreement"]["auroc"] - expl_auc("mindglide", "thick")["auroc"]) < 1e-12
ms3_poor = [p for p in RV["poor_scans"] if p["cohort"] == "ms3seg"]
E("three of the four", "three of the four poor MS3SEG scans had only 1–4 reference lesions", X, "revision.ms3seg_poor_scans_with_at_most_4_ref_lesions / ms3seg poor scans",
  (RV["ms3seg_poor_scans_with_at_most_4_ref_lesions"], len(ms3_poor)), lambda v: "three of the four" if v == (3, 4) else str(v))
E("1–4", "three of the four poor MS3SEG scans had only 1–4 reference lesions", X, "revision.poor_scans[ms3seg, n_ref ≤ 4].n_ref (min–max)",
  [p["n_ref"] for p in ms3_poor if p["n_ref"] <= 4], lambda v: f"{min(v)}–{max(v)}")
E("10", "Both analyses rest on 14 poor scans, 10 of them from one cohort", X, "e1_posthoc[mindglide].poor_by_cohort.muslim", mg["poor_by_cohort"]["muslim"], i)
# runtime of the raw arm
rr = [run("toolbench-mgraw")["seconds_per_case"]["median"], run("toolbench-mgraw-2")["seconds_per_case"]["median"]]
E("253–286", "253–286 s for MindGlide on raw input (e2-standard-4", V, "runs[toolbench-mgraw, -2].seconds_per_case.median", rr, lambda v: f"{min(v):.0f}–{max(v):.0f}")
E("13.3", "peak 13.3 GB), 216 s for WMH-SynthSeg", V, "max runs[toolbench-mgraw, -2].peak_mem_gb_max", max(run(x)["peak_mem_gb_max"] for x in ("toolbench-mgraw", "toolbench-mgraw-2")), lambda v: f"{v:.1f}")
assert led("toolbench-mgraw")["machine_type"] == "e2-standard-4"
# Table 6 times (UTC)
def ctime(c):
    return _dt.datetime.fromisoformat(git("show", "-s", "--format=%cI", c).decode().strip()).astimezone(_dt.timezone.utc).strftime("%H:%M")
E("20:55", "| 2026-10-21 20:55 (commit; first push 20:58) |", "git", "committer date of 595a94f in UTC", ctime("595a94f"), str)
E("22:43", "| 2026-10-21 22:43 (commit and push) |", "git + github activity", "committer date of 8315278 in UTC (push 22:43:47)", ctime("8315278"), str)
pushes = {a["after"][:7]: a["timestamp"] for a in ACT}
E("20:08", "| 2026-10-22 20:08 (push of 6d507c4) |", "manuscript/data/github_push_activity_paper_f_branch.json", "push after=6d507c4", pushes["6d507c4"], lambda v: v[11:16])
E("19:37", "| 2026-10-24 19:37 (push) |", "manuscript/data/github_push_activity_paper_f_branch.json", "push after=759084c", pushes["759084c"], lambda v: v[11:16])
E("14:54", "| 2026-10-24 19:37 and 2026-10-28 14:54 (pushes) |", "manuscript/data/github_push_activity_paper_f_branch.json", "push after=3cffc01", pushes["3cffc01"], lambda v: v[11:16])
E("00:01", "| 2026-10-29 00:01 (push of 7a9a24e) |", "manuscript/data/github_push_activity_paper_f_branch.json", "push after=7a9a24e", pushes["7a9a24e"], lambda v: v[11:16])
E("9", "(run 21 s after the push above and 9 min before the final analysis at 00:11)", "results/run_info.json", "created_utc − 00:01:59 (minutes, floor)", RUNI["created_utc"],
  lambda v: str(int((_dt.datetime.fromisoformat(v.replace("Z", "+00:00")) - _dt.datetime.fromisoformat("2026-10-29T00:01:59+00:00")).total_seconds() // 60)))
E("00:11", "(run 21 s after the push above and 9 min before the final analysis at 00:11)", "results/run_info.json", "created_utc", RUNI["created_utc"], lambda v: v[11:16])
lit("30", "exceeded the pre-stated 30 GB trigger", "docs/research/paper-f/PROTOCOL.md", "section 4.2: --crop if > 30 GB peak")
lit("150", "boot disk 80 GB instead of 150 GB", "docs/research/paper-f/RUNBOOK.md", "section 2: 150 GB disk for highmem/SAMSEG machines")
lit("0.78", "including the exploratory E1 AUROC of 0.78, which the product-planning note then read", "results/comparisons.json", "exploratory[mindglide, thick].auroc = 0.779")
lit("0.78", "The interim included the exploratory E1 AUROC of 0.78", "results/comparisons.json", "exploratory[mindglide, thick].auroc = 0.779")

# ============================================================================= coverage scan of the main text
main = MS.split("# 1. Introduction")[1].split("# Pre-registration deviations")[0]
abstract = MS.split("## Highlights")[1].split("# 1. Introduction")[0]
TOK = r"\d(?:[\d,.]*\d)?"
covered = {norm(e[0]) for e in ENTRIES} | {tok for e in ENTRIES for tok in re.findall(TOK, norm(e[1]))}
IGNORE = re.compile(r"^(19\d\d|20\d\d|2026-10-\d\d|\d)$")       # years, dates, one-digit section/list numbers
unmapped = []
back = MS.split("# Pre-registration deviations")[1]
for blk_name, blk in (("abstract/highlights", abstract), ("main text", main), ("deviations, declarations, appendix", back)):
    for line in blk.splitlines():
        if line.startswith("#"):
            continue                                   # headings: section numbers only
        clean = re.sub(r"\[@[^\]]*\]|`[^`]*`|Sections? \d[.\d]*|Table [A]?\d|Figure \d[A-B]?|S\d|E\d|\d{4}-\d\d-\d\d", "", norm(line))
        for tok in re.findall(r"(?<![\w@`#.])" + TOK, clean):
            if IGNORE.match(tok) or tok in covered:
                continue
            unmapped.append((blk_name, tok, norm(line)[:110]))

# ============================================================================= write NUMBERS_CHECK.md
out = ["# NUMBERS_CHECK — Paper F manuscript",
       "",
       "Generated by `numbers_check.py` (offline). Every row re-derives the number from its source and asserts that the",
       "formatted value equals the text **and** that the sentence or table row carrying it occurs in `manuscript.md`.",
       "Paths are relative to `research/paper_f/` unless they start with `docs/` or `research/`.",
       "",
       f"**Result: {sum(e[5] for e in ENTRIES)} of {len(ENTRIES)} checks PASS; {len(FAIL)} FAIL.**",
       "",
       "Conventions: \"−\" in the text is the Unicode minus. Bootstrap p-values stored as `0.0` (no replicate crossed zero)",
       "are written \"< 0.002\" (families of 4 or 6 tests) or \"< 0.003\" (family of 11): 10,000 replicates give a two-sided",
       "resolution of 2/10,000, multiplied by the Holm factor. `results/tables.md` prints the same values as \"< 0.0001\".",
       "Whole table rows (Tables 3, 4, 5, A2) are rebuilt from the JSON and compared with the manuscript row as a unit.",
       "Post hoc numbers (labelled as such in the text) come from `manuscript/data/extra_numbers.json`, written by",
       "`compute_extra_numbers.py` from `results/per_scan.csv.gz` with the pre-registered bootstrap code.",
       "",
       "**Correction found while checking:** `results/RESULTS.md` section 3.1 gives the SAMSEG predicted lesion volume on",
       "thick scans as 6.8–9.8 mL. The stored MS3SEG value is 9.748 mL (printed 9.75 in `tables.md`), which rounds to 9.7;",
       "the 9.8 came from rounding the already rounded 9.75. The manuscript uses 6.8–9.7 mL.",
       "",
       "| # | Number as written | Where (context in manuscript) | Source file | Field | Stored value | Check |",
       "|---|---|---|---|---|---|---|"]
for k, (w, ctx, src, field, val, ok) in enumerate(ENTRIES, 1):
    if isinstance(val, float):
        sval = repr(round(val, 6))
    elif isinstance(val, (list, tuple)):
        sval = "[" + ", ".join(repr(round(x, 4)) if isinstance(x, float) else str(x) for x in val) + "]" if len(str(val)) < 200 else str(val)[:200] + "…"
    else:
        sval = str(val)
    if len(sval) > 160:
        sval = sval[:160] + "…"
    w_show = w if len(w) < 60 else "(table row)"
    out.append(f"| {k} | {w_show} | {norm(ctx)[:120].replace('|', '¦')} | `{src}` | {field.replace('|', '¦')} | {sval.replace('|', '¦')} | {'PASS' if ok else '**FAIL**'} |")
out += ["", "## Numbers in the text that no automatic entry covers", "",
        "These are tokens found by a scan of the abstract, highlights and main text (after removing citations, code spans,",
        "section/table/figure labels, years and one-digit list numbers). Each is explained below.", ""]
if unmapped:
    out.append("| Block | Token | Line (start) |")
    out.append("|---|---|---|")
    for b, tok, line in unmapped:
        out.append(f"| {b} | {tok} | {line.replace('|', '¦')} |")
else:
    out.append("None.")
open(os.path.join(HERE, "NUMBERS_CHECK.md"), "w", encoding="utf-8").write("\n".join(out) + "\n")
print(f"{sum(e[5] for e in ENTRIES)}/{len(ENTRIES)} PASS; {len(FAIL)} FAIL; {len(unmapped)} unmapped tokens")
for f in FAIL:
    print("FAIL", f)
for b, tok, line in unmapped:
    print("UNMAPPED", b, tok, "|", line[:100])
sys.exit(1 if FAIL else 0)
