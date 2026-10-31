"""Check every number of the manuscript against the re-derived data; write NUMBERS_CHECK.md.

    python research/paper_h/numbers_check.py          # exit 1 if any number differs or is missing from the text

Reads research/paper_h/out/manuscript_data.json (manuscript_data.py), research/paper_h/out/results.json
(run_all.py) and docs/research/paper-h/manuscript/manuscript.md. For each claim: the text as written in
the manuscript, the value re-derived from the data, the data key, and whether (a) they agree and (b) the
text occurs verbatim in the manuscript.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.paper_h import config  # noqa: E402

MS_DIR = config.repo_root() / "docs" / "research" / "paper-h" / "manuscript"


def pct(x: float) -> str:
    return f"{x * 100:.1f} %"


def n(x: int) -> str:
    return f"{x:,}"


def git_count_scripts(ref: str) -> int:
    out = subprocess.run(["git", "-C", str(config.repo_root()), "ls-tree", "--name-only", ref, "scripts/safety/"],
                         capture_output=True, text=True, check=True).stdout.split()
    return sum(p.endswith("_negative_controls.py") for p in out)


def git_subject(sha: str) -> str:
    return subprocess.run(["git", "-C", str(config.repo_root()), "show", "-s", "--format=%s", sha],
                          capture_output=True, text=True, check=True).stdout.strip()


def claims(md: dict, rs: dict) -> list[tuple[str, str, str, str, str]]:
    """(section, claim, text as written, re-derived text, source key)."""
    c = md["contribution"]
    cc = c["commits"]
    li = c["lines"]
    g = md["github"]
    rec = md["records"]["summary"]
    ms = md["manifest_series"]
    tw = {p["sha"]: p for p in md["tests_weekly"]}
    nc = md["negative_controls"]
    ap = md["approvals"]
    subs = {s["sha"]: s for s in ap["signoff_substitutions"]["commits"]}
    rv = md["reviews"]
    ch = md["record_channels"]["by_channel"]
    s2 = rs["rq2_failures"]["summary"]
    rcv = rs["rq3_verification"]["rcv_headline"]["rows"]
    stale = sum(r["status_still_says_not_merged"] for r in md["records"]["rows"])
    models = c["models"]
    opus55 = sum(v for k, v in models.items() if k.startswith("Claude Opus 5.5"))
    non_ph = sum(v for k, v in ap["signoff_substitutions"]["totals_by_kind"].items() if k != "approval placeholder")
    replaced = sum(s["occurrences_replaced"] for s in subs.values())
    ci = md["ci"]
    cls = rs["rq2_failures"]["by_class"] if "by_class" in rs["rq2_failures"] else None
    out = [
        ("Abstract, §5.1", "commits on main", "595 commits", f"{cc['all']['total']} commits", "contribution.commits.all.total"),
        ("Abstract, §5.1", "agent-trailered commits", "525 of 595 commits (88.2 %", f"{cc['all']['agent']} of {cc['all']['total']} commits ({pct(cc['all']['share'])}", "contribution.commits.all"),
        ("§5.1", "non-merge commits, agent", "of 546\nnon-merge commits, 513 (94.0 %)", f"of {cc['non_merge']['total']}\nnon-merge commits, {cc['non_merge']['agent']} ({pct(cc['non_merge']['share'])})", "contribution.commits.non_merge"),
        ("§5.1", "lines added by agent-trailered commits", "357,958", n(li["including_initial_commit"]["agent"]["added"]), "contribution.lines.including_initial_commit.agent.added"),
        ("§5.1", "lines added by other commits", "2,100 (agent share 99.4 %", f"{n(li['including_initial_commit']['other']['added'])} (agent share {pct(li['including_initial_commit']['agent_share_of_added'])}", "contribution.lines"),
        ("§5.1", "agent share without initial import", "99.3 % without", f"{pct(li['excluding_initial_commit']['agent_share_of_added'])} without", "contribution.lines.excluding_initial_commit"),
        ("§5.1", "initial import lines", "69,839 lines", f"{n(li['initial_commit']['added'])} lines", "contribution.lines.initial_commit.added"),
        ("Abstract, §5.1", "Class C module commits, all agent", "All\n38 non-merge commits", f"All\n{c['class_c_modules_any']['agent']} non-merge commits" if c['class_c_modules_any']['agent'] == c['class_c_modules_any']['commits'] else "MISMATCH", "contribution.class_c_modules_any"),
        ("§5.1", "controlled-document commits", "Of 163\nnon-merge commits that touched a controlled document, 159", f"Of {c['controlled_documents']['commits']}\nnon-merge commits that touched a controlled document, {c['controlled_documents']['agent']}", "contribution.controlled_documents"),
        ("§5.1", "PR descriptions with the Claude Code footer", "Every one of the 75 pull-request descriptions", f"Every one of the {g['agent_footer_in_body']} pull-request descriptions" if g['agent_footer_in_body'] == g['pull_requests'] else "MISMATCH", "github.agent_footer_in_body"),
        ("§5.1", "untrailered non-merge commits", "The 33 untrailered non-merge commits", f"The {cc['non_merge']['total'] - cc['non_merge']['agent']} untrailered non-merge commits", "contribution.commits.non_merge"),
        ("§5.1", "Opus 5.5 commits", "wrote 223 commits, all after 27 September 2026", f"wrote {opus55} commits, all after {int(c['model_spans']['Claude Opus 5.5 (1M context)']['first'][8:])} September 2026", "contribution.models, model_spans"),
        ("§5.1", "merged PRs with owner's account as merger", "64 of 64 merged PRs", f"{g['merged_by'].get('nicolasbonilla', 0)} of {g['by_state']['MERGED']} merged PRs", "github.merged_by"),
        ("Table 4", "PRs at 31 Oct", "| 75 (64 / 9 / 2) |", f"| {g['pull_requests']} ({g['by_state']['MERGED']} / {g['by_state']['OPEN']} / {g['by_state']['CLOSED']}) |", "github.by_state"),
        ("Table 4, §5.4", "formal GitHub reviews", "(0 on 75)", f"({g['formal_reviews_total']} on {g['pull_requests']})", "github.formal_reviews_total"),
        ("§5.4", "PR comments", "there were three PR comments", "there were three PR comments" if g["comments_total"] == 3 else "MISMATCH", "github.comments_total"),
        ("Table 4", "CAPA records 31 Oct", "| 16 (15) |", f"| {rec['CAPA']['count']} ({rec['CAPA']['severity'].get('Critical')}) |", "records.summary.CAPA"),
        ("Table 4", "PRB records", "| 22 (6 Critical, 11 Major, 5 Minor) |", f"| {rec['PRB']['count']} ({rec['PRB']['severity']['Critical']} Critical, {rec['PRB']['severity']['Major']} Major, {rec['PRB']['severity']['Minor']} Minor) |", "records.summary.PRB"),
        ("§5.0", "days opened -> main, CAPA", "median 6 days from opening for CAPAs (range 0–19)", f"median {rec['CAPA']['median_days_opened_to_main']:g} days from opening for CAPAs (range {rec['CAPA']['range_days_opened_to_main'][0]}–{rec['CAPA']['range_days_opened_to_main'][1]})", "records.summary.CAPA"),
        ("§5.0", "days opened -> main, PRB", "2 days for problem\nreports (0–6)", f"{rec['PRB']['median_days_opened_to_main']:g} days for problem\nreports ({rec['PRB']['range_days_opened_to_main'][0]}–{rec['PRB']['range_days_opened_to_main'][1]})", "records.summary.PRB"),
        ("§5.0, §7", "records whose status still says branch / not merged", "25 of the 38 records", f"{stale} of the {len(md['records']['rows'])} records", "records.rows[*].status_still_says_not_merged"),
        ("Table 4", "manifest at 31 Oct", "| 35 (18) | 88 (68) |", f"| {next(p for p in ms if p['sha'] == '6209131')['controls']} ({next(p for p in ms if p['sha'] == '6209131')['implemented']}) | {ms[-1]['controls']} ({ms[-1]['implemented']}) |", "manifest_series"),
        ("Table 4", "declared tests", "| 1,056 / 116 | 1,502 / 584 |", f"| {n(tw['6209131']['backend_test_functions'])} / {tw['6209131']['frontend_test_cases']} | {n(tw['8805882']['backend_test_functions'])} / {tw['8805882']['frontend_test_cases']} |", "tests_weekly"),
        ("Table 4", "negative-control / tests-on-base scripts", "| 4 / 0ᵇ | 16 / 6 |", f"| {git_count_scripts('6209131')} / 0ᵇ | {len(nc['scripts']['negative_control_scripts'])} / {len(nc['scripts']['tests_on_base_scripts'])} |", "negative_controls.scripts; git ls-tree 6209131 scripts/safety"),
        ("Table 4", "CI runs", "| 291 (218) |", f"| {ci['workflow_runs']} ({ci['by_conclusion']['success']}) |", "ci.by_conclusion"),
        ("§5.0", "PR heads green on all jobs", "the last head of each of\n71 pull requests with checks was green on all seven jobs", f"the last head of each of\n{ci['prs_all_checks_green_on_last_head']} pull requests with checks was green on all {len(ci['jobs_in_ci_yml']) and 'seven'} jobs", "ci.prs_all_checks_green_on_last_head"),
        ("§5.0", "commits since draft", "207 commits reached `main` (198 agent-trailered)", f"{c['since_draft']['commits']} commits reached `main` ({c['since_draft']['agent']} agent-trailered)", "contribution.since_draft"),
        ("§5.0", "PRs since draft", "19 pull requests were\nopened (#57–#75), 13 of them merged", f"{len(g['since_draft_snapshot']['numbers'])} pull requests were\nopened (#57–#75), {g['since_draft_snapshot']['merged']} of them merged", "github.since_draft_snapshot"),
        ("§5.2.1", "verified before / after", "found 4 verified, 6 partial and 12", f"found {rcv['Verified']['reverified_2026_07_18']} verified, {rcv['Partial']['reverified_2026_07_18']} partial and {rcv['Overstated / not implemented']['reverified_2026_07_18']}", "results.rq3_verification.rcv_headline"),
        ("§5.2.1", "verified in April record", "\"Verified 21 (95.5\n%)", "\"Verified 21 (95.5\n%)" if rcv["Verified"]["recorded_2026_04_12"] == 21 else "MISMATCH", "results.rq3_verification.rcv_headline"),
        ("§5.2.2", "episodes", "33 verification-failure episodes (53 items)", f"{s2['episodes']} verification-failure episodes (53 items)", "results.rq2_failures.summary.episodes"),
        ("§5.2.2", "episodes by primary class (I, S, N)", "**I**, environments that could not observe the failure (10 episodes as primary code)", f"**I**, environments that could not observe the failure ({s2['by_class']['I']} episodes as primary code)", "results.rq2_failures.summary.by_class"),
        ("§5.2.2", "episodes S and N", "**S**, the wrong locus (5)", f"**S**, the wrong locus ({s2['by_class']['S']})", "results.rq2_failures.summary.by_class"),
        ("§5.2.2", "episodes N", "**N** (3)", f"**N** ({s2['by_class']['N']})", "results.rq2_failures.summary.by_class"),
        ("§5.2.2", "episodes C, R, M", "**C** (4)", f"**C** ({s2['by_class']['C']})", "results.rq2_failures.summary.by_class"),
        ("§5.2.2", "episodes R", "**R** (4)", f"**R** ({s2['by_class']['R']})", "results.rq2_failures.summary.by_class"),
        ("§5.2.2", "episodes M", "**M** (6)", f"**M** ({s2['by_class']['M']})", "results.rq2_failures.summary.by_class"),
        ("§5.2.2", "detection channels", "adversarial review by\nseparate agent sessions 15, behaviour probes 6, self-check 4, incidental discovery 3, CI 2, external\nresearch 2, route sweep 1, owner 0", "adversarial review by\nseparate agent sessions {AR}, behaviour probes {BP}, self-check {SC}, incidental discovery {IM}, CI {CI}, external\nresearch {EX}, route sweep {SA}, owner {OW}".format(**s2['by_channel']), "results.rq2_failures.summary.by_channel"),
        ("§5.2.2", "introduced by agent", "All 28 episodes with an introducing commit were introduced by agent-trailered commits", f"All {s2['with_introducing_commit']} episodes with an introducing commit were introduced by agent-trailered commits" if s2['introduced_by_agent_trailer'] == s2['with_introducing_commit'] else "MISMATCH", "results.rq2_failures.summary.introduced_by_agent_trailer"),
        ("§5.2.3", "escaped persistence", "median of 91 days (range 27–223)", f"median of {s2['days_to_detection_by_stage']['escaped']['median']} days (range {s2['days_to_detection_by_stage']['escaped']['min']}–{s2['days_to_detection_by_stage']['escaped']['max']})", "results.rq2_failures.summary.days_to_detection_by_stage"),
        ("§5.2.3", "contained dated", "The nine contained episodes", "The nine contained episodes" if s2["days_to_detection_by_stage"]["contained"]["n"] == 9 else "MISMATCH", "results.rq2_failures.summary.days_to_detection_by_stage.contained.n"),
        ("§5.3.1", "release 2026-10-25", "11 records ran 602 mutations (597 detected, 5 declared equivalent)", "{} records ran {} mutations ({} detected, {} declared equivalent)".format(nc['release_2026_10_25_at_final']['records'], *[nc['release_2026_10_25_at_final']['totals'][k] for k in ('mutations', 'detected', 'declared_equivalent')]), "negative_controls.release_2026_10_25_at_final"),
        ("Abstract, §5.3.1", "release 2026-10-30 first run", "14 scripts and 772 mutations (767 detected, 5\ndeclared equivalent)", "{} scripts and {} mutations ({} detected, {}\ndeclared equivalent)".format(nc['release_2026_10_30_first_run']['records'], *[nc['release_2026_10_30_first_run']['totals'][k] for k in ('mutations', 'detected', 'declared_equivalent')]), "negative_controls.release_2026_10_30_first_run"),
        ("Abstract, §5.3.1", "release 2026-10-30 final", "873 mutations across 15 scripts: 868 detected, 5 declared\nequivalent, 0 unexpected survivors", "{} mutations across {} scripts: {} detected, {} declared\nequivalent, {} unexpected survivors".format(nc['release_2026_10_30_final']['totals']['mutations'], nc['release_2026_10_30_final']['records'], nc['release_2026_10_30_final']['totals']['detected'], nc['release_2026_10_30_final']['totals']['declared_equivalent'], nc['release_2026_10_30_final']['totals']['unexpected_undetected']), "negative_controls.release_2026_10_30_final"),
        ("§5.3.1", "history of committed records", "100 recorded runs and 5,925 mutation\nexecutions", f"{nc['history']['distinct_recorded_runs']} recorded runs and {n(nc['history']['mutation_executions'])} mutation\nexecutions", "negative_controls.history"),
        ("Abstract, §5.3.3", "committed versions with unexpected survivor", "Of the 100 committed record versions, **none**", f"Of the {nc['history']['distinct_recorded_runs']} committed record versions, **none**" if not nc['history']['runs_with_unexpected_survivor'] else "MISMATCH", "negative_controls.history.runs_with_unexpected_survivor"),
        ("Abstract, Table 2", "negative-control record files", "47 negative-control record files (21 per-change, 26 per-release)", f"{nc['risk_verification_at_final']['records'] + nc['release_2026_10_25_at_final']['records'] + nc['release_2026_10_30_final']['records']} negative-control record files ({nc['risk_verification_at_final']['records']} per-change, {nc['release_2026_10_25_at_final']['records'] + nc['release_2026_10_30_final']['records']} per-release)", "negative_controls.*.records"),
        ("§5.3.2", "implemented controls", "(68 of 88 controls on 31 October are\n\"implemented\")", f"({ms[-1]['implemented']} of {ms[-1]['controls']} controls on 31 October are\n\"implemented\")", "manifest_series[-1]"),
        ("§5.3.2", "PRB-028..031 tests on base", "32 of 37 backend and 42 of 49 frontend", "32 of 37 backend and 42 of 49 frontend" if "backend 32 of 37 and frontend 42 of 49 fail" in git_subject("d494367") else "MISMATCH", "commit d494367 subject"),
        ("§5.3.3", "pooled detection rate", "99.4 % (868/873)", f"{pct(nc['release_2026_10_30_final']['totals']['detected'] / nc['release_2026_10_30_final']['totals']['mutations'])} ({nc['release_2026_10_30_final']['totals']['detected']}/{nc['release_2026_10_30_final']['totals']['mutations']})", "negative_controls.release_2026_10_30_final.totals"),
        ("Abstract, §5.4.1", "review rounds and findings", "29 review rounds on nine PRs and 189 findings", f"{rv['rounds']} review rounds on nine PRs and {rv['total_findings']} findings" if len(rv['per_pr']) == 9 else "MISMATCH", "reviews.rounds, total_findings, per_pr"),
        ("§5.4.1", "severity totals", "2 blockers, 23\nmajor, 73 minor, 3 nits and 88", f"{rv['total']['blocker']} blockers, {rv['total']['major']}\nmajor, {rv['total']['minor']} minor, {rv['total']['nit']} nits and {rv['total']['unlabelled']}", "reviews.total"),
        ("§5.4.1", "PR #69", "six rounds and 46 findings", "six rounds and {} findings".format(sum(rv['per_pr']['69'].values())) if rv['rounds_by_pr']['69'] == 6 else "MISMATCH", "reviews.per_pr.69"),
        ("§5.4.1", "PR #67", "five rounds and\n29 findings", "five rounds and\n{} findings".format(sum(rv['per_pr']['67'].values())) if rv['rounds_by_pr']['67'] == 5 else "MISMATCH", "reviews.per_pr.67"),
        ("§5.4.1", "findings by channel", "independent agent sessions reported 162 findings,\nbrowser capture sessions 25, and a coordinating session 2", "independent agent sessions reported {} findings,\nbrowser capture sessions {}, and a coordinating session {}".format(*[sum(rv['by_channel'][k].values()) for k in ('independent agent session', 'browser walk-through / capture', 'coordinating agent session')]), "reviews.by_channel"),
        ("§5.4.1", "PR #74 minor", "found ten minor items", "found ten minor items" if rv['per_pr']['74'] == {'minor': 10} else "MISMATCH", "reviews.per_pr.74"),
        ("§7", "review quotes checked", "208 in the review coding", f"{rv['quotes_checked']} in the review coding", "reviews.quotes_checked"),
        ("§5.5.1", "approval lines at draft", "31 lines in 19 controlled documents", f"{ap['lines_at_draft']['lines']} lines in {ap['lines_at_draft']['documents']} controlled documents", "approvals.lines_at_draft"),
        ("§5.5.3", "8832dae", "replaced the placeholder in 17 files (197 occurrences)", f"replaced the placeholder in {subs['8832dae']['files_with_marker_removed']} files ({subs['8832dae']['occurrences_replaced']} occurrences)", "approvals.signoff_substitutions"),
        ("§5.5.3", "5561999", "(PR #70, 64 occurrences in 16\nfiles)", f"(PR #70, {subs['5561999']['occurrences_replaced']} occurrences in {subs['5561999']['files_with_marker_removed']}\nfiles)", "approvals.signoff_substitutions"),
        ("§5.5.3", "c1d0e04", "(PR #72, 239 occurrences in 25 files)", f"(PR #72, {subs['c1d0e04']['occurrences_replaced']} occurrences in {subs['c1d0e04']['files_with_marker_removed']} files)", "approvals.signoff_substitutions"),
        ("§5.5.3", "042d50b", "(PR #74, 28 occurrences in 8\nfiles)", f"(PR #74, {subs['042d50b']['occurrences_replaced']} occurrences in {subs['042d50b']['files_with_marker_removed']}\nfiles)", "approvals.signoff_substitutions"),
        ("§5.5.3", "verified sign-offs", "GitHub reports all three as verified", "GitHub reports all three as verified" if all(v["verified"] for v in ap["commit_verification"] if v["sha"][:7] in ("5561999", "c1d0e04", "042d50b")) else "MISMATCH", "approvals.commit_verification"),
        ("Abstract, §5.5.3", "approval lines at final", "489 lines in 59 controlled documents record the owner's approval: 279", f"{ap['lines_at_final']['lines']} lines in {ap['lines_at_final']['documents']} controlled documents record the owner's approval: {ap['lines_at_final']['by_writer']['owner sign-off in GitHub web editor (verified)']}", "approvals.lines_at_final"),
        ("§5.5.3", "unsigned local / agent lines at final", "179 by the unsigned local commit and 31", f"{ap['lines_at_final']['by_writer']['local commit without agent trailer']} by the unsigned local commit and {ap['lines_at_final']['by_writer']['agent-trailered commit']}", "approvals.lines_at_final.by_writer"),
        ("§5.5.3", "placeholders remaining", "No placeholder remains.", "No placeholder remains." if ap["marker_occurrences_at_final"] == 0 else "MISMATCH", "approvals.marker_occurrences_at_final"),
        ("§5.5.4", "non-placeholder replacements", "Of 528 occurrences\nreplaced by the four approval commits, at least 15 (2.8 %", f"Of {replaced} occurrences\nreplaced by the four approval commits, at least {non_ph} ({pct(non_ph / replaced)}", "approvals.signoff_substitutions.totals_by_kind"),
        ("§5.5.4", "files outside scope of PR #70 sign-off", "four documents of another change", "four documents of another change" if len(subs['5561999']['files_outside_controlled_documents']) == 4 else "MISMATCH", "approvals.signoff_substitutions.commits[5561999].files_outside_controlled_documents"),
        ("§5.6", "browser capture records", "browser capture of a release build (14 records", f"browser capture of a release build ({ch['BC']} records", "record_channels.by_channel.BC"),
        ("§5.6", "other channels", "independent or adversarial review opened 10; the owner's research studies on the same\ncode base — papers A, C, D and this study — opened 5", f"independent or adversarial review opened {ch['AR']}; the owner's research studies on the same\ncode base — papers A, C, D and this study — opened {ch['RS']}", "record_channels.by_channel"),
        ("§5.6", "incidental / probe / code reading / external", "incidental discovery\nwhile implementing opened 4; behaviour probes 2; code reading in an orchestrating session 2;\nexternal literature research 1", f"incidental discovery\nwhile implementing opened {ch['IM']}; behaviour probes {ch['BP']}; code reading in an orchestrating session {ch['CR']};\nexternal literature research {ch['EX']}", "record_channels.by_channel"),
        ("§7", "quoted statements checked", "and 33 statements quoted from records and pull requests", f"and {len(md['stated']['rows'])} statements quoted from records and pull requests", "stated.rows"),
        ("§6.2", "records from capture + research", "Their\nyield (19 of 38 records)", f"Their\nyield ({ch['BC'] + ch['RS']} of {sum(ch.values())} records)", "record_channels.by_channel"),
    ]
    return out


def main() -> int:
    md = json.loads((config.OUT_DIR / "manuscript_data.json").read_text(encoding="utf-8"))
    rs = json.loads((config.OUT_DIR / "results.json").read_text(encoding="utf-8"))
    text = (MS_DIR / "manuscript.md").read_text(encoding="utf-8")
    flat = " ".join(text.split())
    rows, bad = [], 0
    for sec, claim, written, derived, key in claims(md, rs):
        agree = " ".join(written.split()) == " ".join(derived.split())
        present = " ".join(written.split()) in flat
        ok = agree and present
        bad += not ok
        rows.append(f"| {sec} | {claim} | {' '.join(written.split())} | {' '.join(derived.split())} | `{key}` | "
                    f"{'OK' if ok else ('NOT IN TEXT' if agree else 'DIFFERS')} |")
    stated = md["stated"]["rows"]
    srows = [f"| `{r['id']}` | {r['source']} | {'found' if r['found'] else 'NOT FOUND'} |" for r in stated]
    bad += sum(not r["found"] for r in stated)
    doc = f"""# NUMBERS_CHECK — paper H manuscript

Generated by `python research/paper_h/numbers_check.py` from `research/paper_h/out/manuscript_data.json`
(main @ `{md['refs']['final'][:7]}`, GitHub snapshot {md['github']['retrieved_utc']}) and
`research/paper_h/out/results.json` (October analysis, main @ `{md['refs']['draft'][:7]}`).
Do not edit by hand: change the manuscript or the data, then re-run.

**Result: {len(rows) - sum('| OK |' not in r for r in rows)} of {len(rows)} numeric claims agree with the data and occur
verbatim in `manuscript.md`; {sum(r['found'] for r in stated)} of {len(stated)} quoted statements from the records and PR
descriptions are found verbatim at their source.**

## 1. Numbers in the manuscript, re-derived

"Text as written" must occur verbatim (whitespace-normalised) in `manuscript.md`; "re-derived" is built
from the data key. Status: OK, DIFFERS (data and text disagree) or NOT IN TEXT (the text changed).

| Section | Claim | Text as written | Re-derived | Data key | Status |
|---|---|---|---|---|---|
""" + "\n".join(rows) + f"""

## 2. Statements quoted from the records and PR descriptions

Each is a verbatim substring check at `main` @ `{md['refs']['final'][:7]}` (records) or in the committed GitHub
snapshot (PR descriptions); defined in `research/paper_h/manuscript_data.py` (`STATED`, `STATED_PR`).

| Claim id | Source | Status |
|---|---|---|
""" + "\n".join(srows) + f"""

## 3. Coded data checked by script

- Review findings (`research/paper_h/data/review_findings_coding.json`): {md['reviews']['quotes_checked']} verbatim quotations
  checked; per-PR totals recomputed and equal to the stored totals; problems: {len(md['reviews']['problems'])}.
- Detection channel of records (`research/paper_h/data/record_channels_coding.json`): {md['record_channels']['records']} records,
  each quotation found at its source; problems: {len(md['record_channels']['problems'])}.
- October episode coding (`research/paper_h/data/failure_coding.json`): 81 quotations, checked by
  `python research/paper_h/run_all.py --check` (coding problems: {len(rs['rq2_failures']['coding_problems'])}).

## 4. Numbers that are NOT re-derived here (and why)

| Number | Where | Status |
|---|---|---|
| 2,309 backend unit tests / 621 frontend tests passing | §5.0 | Agent-reported in RELEASE-2026-10-30 notes §7 (quote checked: `release_1030_backend_unit_final`, `release_1030_frontend_final`); not re-run for this paper |
| 62 test accounts, 112 writes (PRB-002) | §5.6 | From local application logs, summarised in PRB-002 (quote checked); logs not re-read |
| 19 tests and 19 mutations of the PRB-002 guard | §5.6 | Record `RELEASE-2026-10-30_PRB-002_negative_controls.json` (19 mutations, counted by the script) and PRB-002 §4 (19 tests, agent-reported) |
| CAPA-010: 25 of 27 new tests failed on `main` | §5.3.2 | October analysis, `results.json` key `rq3_verification.capa010_new_tests_on_main_sources` |
| Two harness refusals (17–21 Oct) | §5.5.2 | Owner's notes (D8), cited by CAPA-012 Finding 4; not reproducible from the repository |
| 15 administrator-password locations, rotation requested | §5.6 | Commit message of `fd2aa2e` (agent-trailered); count not re-derived (the literal is not printed) |
"""
    (MS_DIR / "NUMBERS_CHECK.md").write_text(doc, encoding="utf-8")
    print(f"wrote {MS_DIR / 'NUMBERS_CHECK.md'}; problems: {bad}")
    for r in rows:
        if "| OK |" not in r:
            print(r)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
