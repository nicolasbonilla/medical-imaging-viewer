"""Paper H manuscript (2026-10-31): every new number, re-derived from git and committed snapshots.

    python research/paper_h/manuscript_data.py            # writes research/paper_h/out/manuscript_data.json
    python research/paper_h/manuscript_data.py --check    # exit 1 if any quote, total or stated number fails

Extends the October analysis (``run_all.py``, pinned at ``main`` @ 6209131) to ``main`` @ 8805882
(merge of PR #75, 2026-10-31). Read-only and offline: ``git log/show/ls-tree/grep/blame/rev-list``
on pinned SHAs, plus two committed files:

* ``data/github_prs_full_2026-10-31.json`` — PR descriptions, merges, reviews, CI runs and PR-head
  checks (``snapshot_github_full.py``; redacted, public repository);
* ``data/review_findings_coding.json`` — findings of the review rounds of PRs #64-#75, coded with
  verbatim quotes (single coder: the AI agent; every quote is re-checked here).

No cloud service, no production system and no patient data are touched.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter, OrderedDict, defaultdict
from datetime import date
from pathlib import Path, PurePosixPath

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.paper_h import config, contribution, gitlog  # noqa: E402

#: Pinned references for the manuscript update.
REF_FINAL = "880588205468c91687b0693995e586ee029de801"      # main @ merge of PR #75, 2026-10-31
REF_DRAFT = config.REFS["main"]                               # main @ 6209131, 2026-10-17 (October draft)
REF_RELEASE_1030_FIRST = "64eca24095d0e25394bd1319ff397b79d57d418e"   # records of the first 10-30 run (14 scripts)

SNAPSHOT = config.DATA_DIR / "github_prs_full_2026-10-31.json"
REVIEW_CODING = config.DATA_DIR / "review_findings_coding.json"
CHANNEL_CODING = config.DATA_DIR / "record_channels_coding.json"

RECORDS = "docs/iec62304/records/"
CAPA_DIR = RECORDS + "capa/"
PRB_DIR = RECORDS + "problem_reports/"
MANIFEST = RECORDS + "risk_verification/rc_test_manifest.json"
SIGNOFF_SUBJECT = re.compile(r"^Owner sign-off of PR #(\d+)")
MARKER = "PENDING owner approval"
OWNER_APPROVAL = re.compile(r"Bonilla Vargas.{0,80}approv|approv.{0,80}Bonilla Vargas", re.I)

#: Numbers that the agent-written records state, checked verbatim at REF_FINAL (claim id, path, quote).
STATED = (
    ("release_1030_first_run_total", RECORDS + "releases/RELEASE-2026-10-30_integration_notes.md",
     "| **Total (14 scripts)** | **772** | **767 detected, 5 declared equivalent**"),
    ("release_1030_final_total", RECORDS + "releases/RELEASE-2026-10-30_integration_notes.md",
     "| **All 15 scripts on the final tree** | **873** | **868 detected, 5 declared equivalent**"),
    ("release_1030_capa009_o2", RECORDS + "releases/RELEASE-2026-10-30_integration_notes.md",
     "the first run, on `04fd105`, left O2 undetected: the re-anchor after #71 kept the reference image's authorization"),
    ("release_1030_backend_unit_final", RECORDS + "releases/RELEASE-2026-10-30_integration_notes.md",
     "| Backend unit | **2309 passed, 0 failed** (2139 + #70's + 2 merge tests) |"),
    ("release_1030_frontend_final", RECORDS + "releases/RELEASE-2026-10-30_integration_notes.md",
     "| Frontend vitest | **621 passed, 3 skipped** (83 files passed)"),
    ("release_1025_total", RECORDS + "releases/RELEASE-2026-10-25_integration_notes.md",
     "| **Total** | **602** | **597 detected, 5 declared equivalent**"),
    ("release_1025_first_review_no_blocker", RECORDS + "releases/RELEASE-2026-10-25_integration_notes.md",
     "The review found that nothing reviewed was lost in the integration and no blocker or major issue."),
    ("release_1030_label_interaction", RECORDS + "releases/RELEASE-2026-10-30_integration_notes.md",
     "every segmentation classified before #71 would have been refused (drawn orange, stored red)"),
    ("release_1030_audit_interaction", RECORDS + "releases/RELEASE-2026-10-30_integration_notes.md",
     "Merged, the privileged creation would have read as an access grant"),
    ("release_1025_fixture_failures", RECORDS + "releases/RELEASE-2026-10-25_integration_notes.md",
     "Before reconciliation the\nunit suite had 151 failures"),
    ("prb002_accounts", PRB_DIR + "PRB-002_Local_Test_Runs_Wrote_To_Production_User_Store.md",
     "62 distinct test accounts"),
    ("prb002_writes", PRB_DIR + "PRB-002_Local_Test_Runs_Wrote_To_Production_User_Store.md",
     "| **Total** | | **112** | |"),
    ("prb002_ci_blind", PRB_DIR + "PRB-002_Local_Test_Runs_Wrote_To_Production_User_Store.md",
     "The CI pipeline has no cloud credentials, so CI never showed the problem"),
    ("prb002_five_layers", PRB_DIR + "PRB-002_Local_Test_Runs_Wrote_To_Production_User_Store.md",
     "`backend/tests/conftest.py` sets five\nindependent layers before any application import"),
    ("prb020_capture", PRB_DIR + "PRB-020_Open_Self_Registration.md",
     "browser capture of the release candidate"),
    ("prb020_marketing", PRB_DIR + "PRB-020_Open_Self_Registration.md",
     "a marketing study that named it the largest EU MDR\nrisk"),
    ("prb020_unknown_exposure", PRB_DIR + "PRB-020_Open_Self_Registration.md",
     "**Whether patient\n  data were read by self-registered accounts in production is unknown**"),
    ("prb021_found_while_reproducing", PRB_DIR + "PRB-021_Patient_Registry_Visible_To_Every_User.md",
     "found by the AI coding agent while reproducing PRB-020 (F21) on `main`"),
    ("prb020_password_logged", PRB_DIR + "PRB-020_Open_Self_Registration.md",
     "every\n  validation error, the typed password included, was written to the log with its `input`"),
    ("prb020_r4_more_leaks", PRB_DIR + "PRB-020_Open_Self_Registration.md",
     "**R4 — two more password leaks were closed by the first review's handler fix**"),
    ("capa012_31_lines", CAPA_DIR + "CAPA-012_Approval_And_Review_Records.md",
     "**31 lines in 19 controlled documents** record the owner's approval"),
    ("capa012_no_protection", CAPA_DIR + "CAPA-012_Approval_And_Review_Records.md",
     "returns HTTP 404 \"Branch not protected\""),
    ("capa012_codeowner_is_author", CAPA_DIR + "CAPA-012_Approval_And_Review_Records.md",
     "**The code owner is the pull-request author.**"),
    ("capa012_harness_refusal", CAPA_DIR + "CAPA-012_Approval_And_Review_Records.md",
     "on two occasions between 2026-10-17 and 2026-10-21 the agent harness's permission classifier refused"),
    ("capa012_not_relied_on", CAPA_DIR + "CAPA-012_Approval_And_Review_Records.md",
     "This is a behaviour of the tool, not a control of the quality system"),
    ("sdp_agent_writes_approval_line", "docs/iec62304/01_Software_Development_Plan.md",
     "value, a signature or a sign-off date; where an approval is pending it writes\n"
     "`approved by N. G. Bonilla Vargas 2026-10-23 (PR #52/#51/#53/#59/#49/#62/#63)`."),
    ("flames_doc_not_approved_but_approved", "docs/research/flames-in-browser/CHANGE-PROPOSAL.md",
     "**Draft records written, NOT approved.** SRS 1.7, RMF 1.9, TM 1.6, SOUP 1.2, CMP 1.1 carry the entries below "
     "with every approval field \"N. G. Bonilla Vargas — approved 2026-10-30 (PR #70)\""),
    ("prb020_and_code_review", PRB_DIR + "PRB-020_Open_Self_Registration.md",
     "No Class C module changed. **N. G. Bonilla Vargas — approved 2026-10-30 (PR #70) and code review.**"),
)

#: Statements in PR descriptions of the snapshot (claim id, PR, quote).
STATED_PR = (
    ("pr44_wrong_project", 44, "a bare `gcloud builds submit` ran while the machine's default gcloud project belonged to an unrelated product"),
    ("pr44_removed_same_day", 44, "Both were removed the same day"),
    ("pr75_signoff", 75, "Brings the owner's own sign-off commit 042d50b (GitHub-verified, made by the owner in github.dev) to `main`."),
    ("pr64_no_review_when_written", 64, "**#59 and #62 had no independent review when written**"),
    ("pr64_marker_sentences", 64, "Some #62 occurrences in SDP-001 §4.4/§7.4 and in CAPA-012 are sentences of the proposed procedure that name the marker, not blocks to sign."),
)


# --------------------------------------------------------------------------------------- helpers

def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b[:10]) - date.fromisoformat(a[:10])).days


def _median(xs):
    return None if not xs else statistics.median(xs)


def first_parent_chain(repo, ref: str) -> list[dict]:
    """Chronological first-parent history of ``ref``: sha, author date, committer date, subject."""
    out = gitlog.git(repo, "log", "--first-parent", "--reverse", "--date=short",
                     "--format=%H\x1f%ad\x1f%cd\x1f%s", ref)
    rows = []
    for line in out.splitlines():
        sha, ad, cd, subject = line.split("\x1f", 3)
        rows.append({"sha": sha, "date": ad, "cdate": cd, "subject": subject})
    return rows


def tree_paths(repo, sha: str, prefix: str) -> set[str]:
    return set(gitlog.git(repo, "ls-tree", "-r", "--name-only", sha, "--", prefix).splitlines())


def show_or_none(repo, ref: str, path: str) -> str | None:
    try:
        return gitlog.show_file(repo, ref, path)
    except RuntimeError:
        return None


# --------------------------------------------------------------------------------- RQ1 extension

def weekly_commits(commits: list[gitlog.Commit]) -> list[dict]:
    """Commits per ISO week (Monday date), agent-trailered or not."""
    weeks = defaultdict(Counter)
    for c in commits:
        d = date.fromisoformat(c.date)
        monday = date.fromordinal(d.toordinal() - d.weekday()).isoformat()
        weeks[monday]["agent" if c.is_agent else "other"] += 1
    return [{"week": w, "agent": v.get("agent", 0), "other": v.get("other", 0)} for w, v in sorted(weeks.items())]


def contribution_final(repo) -> dict:
    commits = gitlog.log(repo, REF_FINAL)
    stats = gitlog.numstat(repo, REF_FINAL)
    since = [c for c in commits if c.sha not in {x.sha for x in gitlog.log(repo, REF_DRAFT)}]
    nonmerge = [c for c in commits if not c.is_merge]
    owner_web = [c for c in nonmerge if c.committer == "GitHub" and not c.is_agent]
    untrailered_local_since = [c for c in since if not c.is_merge and not c.is_agent and c.committer == "local"]
    return {
        "ref": REF_FINAL,
        "commits": contribution.commit_counts(commits),
        "monthly": contribution.monthly(commits),
        "models": contribution.models(commits),
        "model_spans": contribution.model_first_last(commits),
        "lines": contribution.lines(commits, stats),
        "controlled_documents": contribution.touching(commits, stats, config.CONTROLLED_DOC_PREFIXES),
        "class_c_modules_any": contribution.touching(commits, stats, config.CLASS_C_MODULES),
        "weekly": weekly_commits(commits),
        "since_draft": {
            "commits": len(since),
            "agent": sum(c.is_agent for c in since),
            "merges": sum(c.is_merge for c in since),
            "non_merge": sum(not c.is_merge for c in since),
            "non_merge_agent": sum(c.is_agent for c in since if not c.is_merge),
            "first": min(c.date for c in since) if since else None,
            "last": max(c.date for c in since) if since else None,
        },
        "owner_web_commits": [{"sha": c.sha[:7], "date": c.date, "subject": c.subject} for c in
                              sorted(owner_web, key=lambda c: c.date)],
        "untrailered_local_non_merge_since_draft": [{"sha": c.sha[:7], "date": c.date, "subject": c.subject}
                                                    for c in sorted(untrailered_local_since, key=lambda c: c.date)],
    }


# ------------------------------------------------------------------------- records: CAPA / PRB

_FIELD = r"^\*\*{name}\*\*:\s*(.+)$"


def _field(text: str, name: str) -> str | None:
    m = re.search(_FIELD.format(name=re.escape(name)), text, re.M)
    return m.group(1).strip() if m else None


def _severity(text: str) -> str | None:
    v = _field(text, "Severity")
    if not v:
        return None
    m = re.search(r"\b(Critical|Major|Minor|CRITICAL|MAJOR|MINOR)\b", v)
    return m.group(1).capitalize() if m else None


def _record_id(path: str) -> str:
    return re.match(r"((?:CAPA|PRB)-\d{3})", PurePosixPath(path).name).group(1)


def records_timeline(repo, chain: list[dict], prs_by_merge: dict[str, int]) -> dict:
    final_paths = sorted(p for p in tree_paths(repo, REF_FINAL, CAPA_DIR) | tree_paths(repo, REF_FINAL, PRB_DIR)
                         if p.endswith(".md"))
    # first first-parent commit whose tree contains each path
    on_main: dict[str, dict] = {}
    for row in chain:
        present = tree_paths(repo, row["sha"], CAPA_DIR) | tree_paths(repo, row["sha"], PRB_DIR)
        for p in present:
            if p in final_paths and p not in on_main:
                on_main[p] = row
    rows = []
    for p in final_paths:
        text = gitlog.show_file(repo, REF_FINAL, p)
        added = gitlog.git(repo, "log", REF_FINAL, "--diff-filter=A", "--date=short", "--format=%h\x1f%ad", "--", p)
        first_add = added.strip().splitlines()[-1].split("\x1f") if added.strip() else [None, None]
        opened_field = _field(text, "Date Opened") or _field(text, "Date")
        opened = re.search(r"\d{4}-\d{2}-\d{2}", opened_field or "")
        opened = opened.group(0) if opened else first_add[1]
        m = on_main.get(p)
        pr = None
        if m:
            pr = prs_by_merge.get(m["sha"])
            if pr is None:
                mm = re.search(r"#(\d+)", m["subject"])
                pr = int(mm.group(1)) if mm else None
        status = _field(text, "Status") or ""
        rows.append({
            "id": _record_id(p),
            "kind": _record_id(p)[:4].rstrip("-"),
            "path": p,
            "title": text.splitlines()[0].lstrip("# ").strip(),
            "severity": _severity(text),
            "opened": opened,
            "first_commit": first_add[0],
            "first_commit_date": first_add[1],
            "on_main_commit": m["sha"][:7] if m else None,
            "on_main_date": m["cdate"] if m else None,
            "via_pr": pr,
            "days_opened_to_main": _days(opened, m["cdate"]) if m else None,
            "status_field": status[:200],
            "status_still_says_not_merged": bool(re.search(r"not merged|draft PR|on branch", status, re.I)),
        })
    by_kind = defaultdict(list)
    for r in rows:
        by_kind[r["kind"]].append(r)
    summary = {}
    for k, rs in by_kind.items():
        d = [r["days_opened_to_main"] for r in rs if r["days_opened_to_main"] is not None]
        summary[k] = {
            "count": len(rs),
            "severity": dict(Counter(r["severity"] for r in rs)),
            "opened_range": [min(r["opened"] for r in rs), max(r["opened"] for r in rs)],
            "median_days_opened_to_main": _median(d),
            "range_days_opened_to_main": [min(d), max(d)] if d else None,
            "status_still_says_not_merged": sum(r["status_still_says_not_merged"] for r in rs),
            "opened_since_draft": sum(r["opened"] > "2026-10-17" for r in rs),
        }
    return {"rows": rows, "summary": summary}


# -------------------------------------------------------------------- risk-control manifest series

def manifest_series(repo, chain: list[dict]) -> list[dict]:
    series, last = [], None
    for row in chain:
        text = show_or_none(repo, row["sha"], MANIFEST)
        if text is None:
            continue
        try:
            d = json.loads(text)
        except json.JSONDecodeError:
            continue
        controls = d.get("controls") or {}
        items = list(controls.values()) if isinstance(controls, dict) else list(controls)
        st = Counter(i.get("status") for i in items)
        point = {"date": row["cdate"], "sha": row["sha"][:7], "controls": len(items),
                 "implemented": st.get("implemented", 0), "not_implemented": st.get("not_implemented", 0),
                 "unverified": st.get("unverified", 0)}
        key = (point["controls"], point["implemented"], point["not_implemented"], point["unverified"])
        if key != last:
            series.append(point)
            last = key
    return series


# ------------------------------------------------------------------------ negative-control records

def parse_nc_record(d) -> dict:
    """Mutations, detected, declared-equivalent and unexpected survivors of one record (all formats)."""
    if isinstance(d, dict) and "results" in d and "summary" in d and "mutations_detected" in d["summary"]:
        det, tot = (int(x) for x in d["summary"]["mutations_detected"].split("/"))
        nd = d["summary"].get("not_detected") or []
        expl = d["summary"].get("not_detected_explained") or {}
        return {"mutations": tot, "detected": det, "declared_equivalent": sum(k in expl for k in nd),
                "unexpected_undetected": [k for k in nd if k not in expl], "executed": (d.get("dates") or [None])[0]
                if isinstance(d.get("dates"), list) else d.get("dates")}
    muts = d.get("mutations")
    n = len(muts) if muts is not None else d["summary"]["mutations"]
    und = d.get("undetected")
    if und is None:
        und = (d.get("summary") or {}).get("undetected", [])
    if isinstance(und, int):
        und = ["?"] * und
    if isinstance(und, dict):
        und = list(und)
    expected = d.get("expected_undetected") or {}
    expected_keys = set(expected) if isinstance(expected, (dict, list)) else set()
    unexpected = d.get("unexpected_undetected")
    if unexpected is None:
        unexpected = [u for u in und if u not in expected_keys]
    if isinstance(muts, list) and muts and isinstance(muts[0], dict) and "detected" in muts[0]:
        und = [m.get("name") for m in muts if not m.get("detected")]
        unexpected = [u for u in und if u not in expected_keys]
    return {"mutations": n, "detected": n - len(und), "declared_equivalent": len([u for u in und if u in expected_keys]),
            "unexpected_undetected": list(unexpected),
            "executed": d.get("executed") or d.get("generated")}


def nc_set(repo, ref: str, prefix: str, folder: str = RECORDS + "releases/") -> dict:
    paths = sorted(p for p in tree_paths(repo, ref, folder) if PurePosixPath(p).name.startswith(prefix)
                   and "negative_controls" in PurePosixPath(p).name and p.endswith(".json"))
    rows = []
    for p in paths:
        r = parse_nc_record(json.loads(gitlog.show_file(repo, ref, p)))
        r["record"] = PurePosixPath(p).name
        rows.append(r)
    tot = {k: sum(r[k] for r in rows) for k in ("mutations", "detected", "declared_equivalent")}
    tot["unexpected_undetected"] = sum(len(r["unexpected_undetected"]) for r in rows)
    return {"ref": ref[:7], "prefix": prefix, "records": len(rows), "totals": tot, "rows": rows}


def nc_history(repo) -> dict:
    """Every distinct version of every negative-control record reachable from REF_FINAL (one per run)."""
    out = gitlog.git(repo, "log", REF_FINAL, "--date=short", "--format=\x1e%H\x1f%ad", "--name-only",
                     "--diff-filter=AM", "--", "*negative_controls*.json")
    seen, runs = set(), []
    for chunk in out.split("\x1e"):
        lines = [ln for ln in chunk.splitlines() if ln.strip()]
        if not lines:
            continue
        sha, d8 = lines[0].split("\x1f")
        for p in lines[1:]:
            if "negative_controls" not in p or not p.endswith(".json"):
                continue
            text = show_or_none(repo, sha, p)
            if text is None:
                continue
            try:
                r = parse_nc_record(json.loads(text))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
            key = (PurePosixPath(p).name, str(r["executed"]), r["mutations"], r["detected"])
            if key in seen:
                continue
            seen.add(key)
            runs.append({"record": PurePosixPath(p).name, "commit": sha[:7], "commit_date": d8,
                         "executed": str(r["executed"])[:19], "mutations": r["mutations"],
                         "detected": r["detected"], "declared_equivalent": r["declared_equivalent"],
                         "unexpected_undetected": len(r["unexpected_undetected"])})
    runs.sort(key=lambda r: (r["commit_date"], r["record"]))
    return {
        "distinct_recorded_runs": len(runs),
        "mutation_executions": sum(r["mutations"] for r in runs),
        "runs_with_unexpected_survivor": [r for r in runs if r["unexpected_undetected"]],
        "first": runs[0]["commit_date"] if runs else None,
        "last": runs[-1]["commit_date"] if runs else None,
        "runs": runs,
    }


def safety_scripts(repo) -> dict:
    paths = sorted(p for p in tree_paths(repo, REF_FINAL, "scripts/safety/"))
    return {"negative_control_scripts": [p for p in paths if p.endswith("_negative_controls.py")],
            "tests_on_base_scripts": [p for p in paths if p.endswith("_tests_on_base.py")],
            "all": paths}


# ----------------------------------------------------------------------- approval provenance

def _classify_writer(c: gitlog.Commit) -> str:
    if c.is_agent:
        return "agent-trailered commit"
    if c.committer == "GitHub" and not c.is_merge and SIGNOFF_SUBJECT.match(c.subject):
        return "owner sign-off in GitHub web editor (verified)"
    if c.committer == "GitHub":
        return "other GitHub web commit"
    return "local commit without agent trailer"


def approval_lines(repo, ref: str) -> dict:
    out = gitlog.git(repo, "grep", "-n", "-i", "-E", OWNER_APPROVAL.pattern, ref, "--",
                     *config.CONTROLLED_DOC_PREFIXES)
    rows, cache = [], {}
    for line in out.splitlines():
        _, path, lineno, _text = line.split(":", 3)
        blame = gitlog.git(repo, "blame", "--porcelain", "-L", f"{lineno},{lineno}", ref, "--", path)
        sha = blame.split()[0]
        if sha not in cache:
            cache[sha] = gitlog.show_commit(repo, sha)
        c = cache[sha]
        rows.append({"path": path, "line": int(lineno), "written_by": c.sha[:7], "date": c.date,
                     "writer": _classify_writer(c), "subject": c.subject})
    by_writer = Counter(r["writer"] for r in rows)
    by_commit = Counter((r["written_by"], r["date"], r["writer"]) for r in rows)
    return {
        "ref": ref[:7],
        "lines": len(rows),
        "documents": len({r["path"] for r in rows}),
        "by_writer": dict(by_writer),
        "by_commit": [{"sha": s, "date": d, "writer": w, "lines": n} for (s, d, w), n in
                      sorted(by_commit.items(), key=lambda kv: kv[0][1])],
        "rows": rows,
    }


def marker_count(repo, ref: str) -> int:
    out = subprocess_grep_count(repo, ref, MARKER)
    return out


def subprocess_grep_count(repo, ref: str, needle: str) -> int:
    try:
        out = gitlog.git(repo, "grep", "-c", "-F", needle, ref, "--", *config.CONTROLLED_DOC_PREFIXES)
    except RuntimeError:
        return 0
    return sum(int(line.rsplit(":", 1)[1]) for line in out.splitlines() if line.strip())


def _replacement_kind(old_line: str, pos: int) -> str:
    before, after = old_line[:pos], old_line[pos + len(MARKER):]
    if before.endswith(("`", "\"", "'", "“")) or before.endswith("**") and before[:-2].endswith(("`", "\"")):
        return "name of the marker (procedure text or quotation)"
    if re.match(r"\**\s*and (code|independent|a code) review", after):
        return "conjoined with a review (\"... and code review\")"
    if re.search(r"still reads|none was changed|every approval field", old_line, re.I):
        return "statement about the pre-sign-off state"
    return "approval placeholder"


def signoff_substitutions(repo) -> dict:
    """What each sign-off commit replaced: every removed occurrence of the marker, classified."""
    commits = [gitlog.show_commit(repo, s) for s in
               ("8832dae0861c4f72c76a028b005352af8e25877f", "55619994eed5d8e03dd959f3d152eaaaf331166b",
                "c1d0e0435745a6cd6401d3a31be098f7e509f42e", "042d50bf7e1b356edfa6b0574aba8698fb826681")]
    result = []
    for c in commits:
        diff = gitlog.git(repo, "show", "--format=", "--unified=0", c.sha)
        kinds, files, removed_lines, examples = Counter(), set(), 0, []
        cur = None
        for ln in diff.splitlines():
            if ln.startswith("+++ b/"):
                cur = ln[6:]
            elif ln.startswith("-") and not ln.startswith("---") and MARKER in ln:
                removed_lines += 1
                files.add(cur)
                text = ln[1:]
                for m in re.finditer(re.escape(MARKER), text):
                    kind = _replacement_kind(text, m.start())
                    kinds[kind] += 1
                    if kind != "approval placeholder":
                        examples.append({"file": cur, "kind": kind,
                                         "old_text": text[max(0, m.start() - 160): m.end() + 80].strip()})
        added = gitlog.git(repo, "show", "--format=", "--numstat", c.sha)
        names = gitlog.git(repo, "show", "--format=", "--name-only", c.sha).split()
        outside = sorted(n for n in names if not n.startswith(config.CONTROLLED_DOC_PREFIXES))
        result.append({
            "sha": c.sha[:7], "date": c.date, "subject": c.subject, "committer": c.committer,
            "agent_trailer": c.is_agent, "files_with_marker_removed": len(files),
            "lines_with_marker_removed": removed_lines, "occurrences_replaced": sum(kinds.values()),
            "by_kind": dict(kinds),
            "non_placeholder_examples": examples,
            "files_changed": len([x for x in added.splitlines() if x.strip()]),
            "files_outside_controlled_documents": outside,
        })
    return {"commits": result,
            "totals_by_kind": dict(sum((Counter(r["by_kind"]) for r in result), Counter()))}


# --------------------------------------------------------------------------- GitHub snapshot

def prs(snapshot: dict) -> dict:
    ps = snapshot["pull_requests"]
    merged = [p for p in ps if p["state"] == "MERGED"]
    lead = [(_days(p["created"], p["merged"]), p["number"]) for p in merged]
    by_month = defaultdict(Counter)
    for p in ps:
        by_month[p["created"][:7]]["created"] += 1
        if p["merged"]:
            by_month[p["merged"][:7]]["merged"] += 1
    since = [p for p in ps if p["number"] > 56]
    return {
        "retrieved_utc": snapshot["retrieved_utc"],
        "pull_requests": len(ps),
        "by_state": dict(Counter(p["state"] for p in ps)),
        "open_drafts": sum(p["state"] == "OPEN" and p["is_draft"] for p in ps),
        "formal_reviews_total": sum(len(p["formal_reviews"]) for p in ps),
        "comments_total": sum(len(p["comments"]) for p in ps),
        "merged_by": dict(Counter(p["merged_by"] for p in merged)),
        "agent_footer_in_body": sum("Generated with [Claude Code]" in p["body"] for p in ps),
        "median_days_created_to_merged": _median([d for d, _ in lead]),
        "max_days_created_to_merged": max(lead) if lead else None,
        "by_month": {k: dict(v) for k, v in sorted(by_month.items())},
        "since_draft_snapshot": {"numbers": [p["number"] for p in since],
                                 "merged": sum(p["state"] == "MERGED" for p in since),
                                 "closed": sum(p["state"] == "CLOSED" for p in since),
                                 "open": sum(p["state"] == "OPEN" for p in since)},
        "integration_prs": [p["number"] for p in ps if re.search(r"release", p["title"], re.I)
                            and re.search(r"sign-off|release", p["head"], re.I)],
        "body_chars": {str(p["number"]): len(p["body"]) for p in ps if p["number"] >= 64},
    }


def ci(snapshot: dict, repo) -> dict:
    runs = snapshot["ci"]["runs"]
    by_month = defaultdict(Counter)
    for r in runs:
        by_month[r["createdAt"][:7]][r["conclusion"] or r["status"]] += 1
    checks = snapshot["ci"]["pr_head_checks"]
    with_checks = [c for c in checks if c["checks"]]
    all_green = [c["number"] for c in with_checks if all(x["conclusion"] == "SUCCESS" for x in c["checks"])]
    wf = gitlog.show_file(repo, REF_FINAL, ".github/workflows/ci.yml")
    jobs = re.findall(r"^  ([a-z0-9_-]+):\n    name: (.+)$", wf, re.M)
    merged = {p["number"] for p in snapshot["pull_requests"] if p["state"] == "MERGED"}
    return {
        "workflow_runs": len(runs),
        "first_run": min(r["createdAt"] for r in runs)[:10],
        "last_run": max(r["createdAt"] for r in runs)[:10],
        "by_conclusion": dict(Counter(r["conclusion"] or r["status"] for r in runs)),
        "by_event_conclusion": {f"{k[0]}/{k[1]}": v for k, v in
                                Counter((r["event"], r["conclusion"]) for r in runs).items()},
        "by_month": {k: dict(v) for k, v in sorted(by_month.items())},
        "jobs_in_ci_yml": [{"id": j, "name": n.strip()} for j, n in jobs],
        "prs_with_checks_on_last_head": len(with_checks),
        "prs_all_checks_green_on_last_head": len(all_green),
        "merged_prs_without_checks_on_last_head": sorted(merged - {c["number"] for c in with_checks}),
        "branch_protection": "not protected (CAPA-012 Finding 3, gh api 2026-10-22: HTTP 404); not re-queried",
    }


# ----------------------------------------------------------------------------------- tests

def test_counts(repo, chain: list[dict]) -> list[dict]:
    """Test functions in the tree at the last first-parent commit of each ISO week (a size proxy)."""
    by_week = OrderedDict()
    for row in chain:
        y, w, _ = date.fromisoformat(row["cdate"]).isocalendar()
        by_week[(y, w)] = row
    pts = []
    for (_y, _w), row in by_week.items():
        def count(pattern: str, *paths: str) -> int:
            try:
                out = gitlog.git(repo, "grep", "-c", "-E", pattern, row["sha"], "--", *paths)
            except RuntimeError:
                return 0
            return sum(int(line.rsplit(":", 1)[1]) for line in out.splitlines() if line.strip())
        be = count(r"^\s*(async\s+)?def test_", "backend/tests")
        fe = count(r"^\s*(it|test)(\.each\([^)]*\))?\(", "frontend/src/**/*.test.ts", "frontend/src/**/*.test.tsx",
                   "frontend/src/*.test.ts", "frontend/src/*.test.tsx")
        pts.append({"date": row["cdate"], "sha": row["sha"][:7], "backend_test_functions": be,
                    "frontend_test_cases": fe})
    return pts


# --------------------------------------------------------------------------- review findings

def review_findings(repo, snapshot: dict) -> dict:
    coding = json.loads(REVIEW_CODING.read_text(encoding="utf-8"))
    bodies = {p["number"]: p["body"] for p in snapshot["pull_requests"]}
    files: dict[str, str] = {}
    problems, checked = [], 0
    totals = defaultdict(Counter)
    by_channel = defaultdict(Counter)
    rounds_by_pr = Counter()

    def source_text(src: dict) -> str | None:
        if src.get("kind") == "pr_body":
            return bodies.get(src.get("pr"))
        path = src.get("path")
        if path not in files:
            files[path] = show_or_none(repo, REF_FINAL, path) or ""
        return files[path]

    for rnd in coding["rounds"]:
        text = source_text(rnd["source"]) or ""
        rounds_by_pr[rnd["pr"]] += 1
        ch = ("browser walk-through / capture" if "capture" in rnd["reviewer"] or "browser" in rnd["reviewer"]
              else "coordinating agent session" if "coordinat" in rnd["reviewer"]
              else "independent agent session" if "independent" in rnd["reviewer"] else rnd["reviewer"])
        if rnd.get("verdict_quote"):
            checked += 1
            if rnd["verdict_quote"] not in text:
                problems.append(f"verdict quote not found: {rnd['round_id']}")
        for f in rnd["findings"]:
            checked += 1
            src_text = text
            if f.get("source"):
                src_text = source_text(f["source"]) or ""
            if f["quote"] not in src_text:
                problems.append(f"finding quote not found: {rnd['round_id']} {f['id']}")
            totals[rnd["pr"]][f["severity"]] += 1
            by_channel[ch][f["severity"]] += 1
    stored = coding["per_pr_totals"]
    for pr, c in totals.items():
        s = stored.get(str(pr), {})
        for sev in ("blocker", "major", "minor", "nit", "unlabelled"):
            if s.get(sev, 0) != c.get(sev, 0):
                problems.append(f"stored total differs: PR {pr} {sev} {s.get(sev)} != {c.get(sev, 0)}")
    grand = sum((Counter(v) for v in totals.values()), Counter())
    return {
        "coded_by": coding["coded_by"],
        "rounds": len(coding["rounds"]),
        "rounds_by_pr": {str(k): v for k, v in sorted(rounds_by_pr.items())},
        "per_pr": {str(k): dict(v) for k, v in sorted(totals.items())},
        "by_channel": {k: dict(v) for k, v in by_channel.items()},
        "total": dict(grand),
        "total_findings": sum(grand.values()),
        "quotes_checked": checked,
        "problems": problems,
        "f08_provenance": coding.get("f08_provenance"),
    }


# ------------------------------------------------------------------ detection channel of records

def record_channels(repo) -> dict:
    coding = json.loads(CHANNEL_CODING.read_text(encoding="utf-8"))
    problems, cache = [], {}
    for r in coding["records"]:
        if r["path"] not in cache:
            cache[r["path"]] = show_or_none(repo, REF_FINAL, r["path"]) or ""
        if r["quote"] not in cache[r["path"]]:
            problems.append(f"channel quote not found: {r['id']}")
    by = Counter(r["channel"] for r in coding["records"])
    by_kind = defaultdict(Counter)
    for r in coding["records"]:
        by_kind[r["id"][:3] if r["id"].startswith("PRB") else "CAPA"][r["channel"]] += 1
    return {"records": len(coding["records"]), "by_channel": dict(by.most_common()),
            "by_kind": {k: dict(v) for k, v in by_kind.items()}, "channels": coding["channels"],
            "codes": {r["id"]: r["channel"] for r in coding["records"]}, "problems": problems}


# ---------------------------------------------------------------------------- stated numbers

def stated_numbers(repo, snapshot: dict) -> dict:
    rows, problems = [], []
    for cid, path, quote in STATED:
        text = show_or_none(repo, REF_FINAL, path) or ""
        ok = quote in text
        rows.append({"id": cid, "source": f"{path} @ {REF_FINAL[:7]}", "found": ok})
        if not ok:
            problems.append(cid)
    bodies = {p["number"]: p["body"] for p in snapshot["pull_requests"]}
    for cid, pr, quote in STATED_PR:
        ok = quote in bodies.get(pr, "")
        rows.append({"id": cid, "source": f"PR #{pr} description (snapshot {snapshot['retrieved_utc']})", "found": ok})
        if not ok:
            problems.append(cid)
    return {"rows": rows, "problems": problems}


# ------------------------------------------------------------------------------------- main

def compute(repo=None) -> dict:
    repo = repo or config.repo_root()
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    chain = first_parent_chain(repo, REF_FINAL)
    prs_by_merge = {p["merge_commit"]: p["number"] for p in snapshot["pull_requests"] if p.get("merge_commit")}
    nc_final = nc_set(repo, REF_FINAL, "RELEASE-2026-10-30_")
    nc_first = nc_set(repo, REF_RELEASE_1030_FIRST, "RELEASE-2026-10-30_")
    nc_1025 = nc_set(repo, REF_FINAL, "RELEASE-2026-10-25_")
    data = {
        "refs": {"final": REF_FINAL, "draft": REF_DRAFT, "release_1030_first_run": REF_RELEASE_1030_FIRST},
        "contribution": contribution_final(repo),
        "records": records_timeline(repo, chain, prs_by_merge),
        "manifest_series": manifest_series(repo, chain),
        "negative_controls": {
            "release_2026_10_25_at_final": nc_1025,
            "release_2026_10_30_first_run": nc_first,
            "release_2026_10_30_final": nc_final,
            "risk_verification_at_final": nc_set(repo, REF_FINAL, "", RECORDS + "risk_verification/"),
            "history": nc_history(repo),
            "scripts": safety_scripts(repo),
        },
        "approvals": {
            "lines_at_draft": approval_lines(repo, REF_DRAFT),
            "lines_at_final": approval_lines(repo, REF_FINAL),
            "marker_occurrences_at_final": subprocess_grep_count(repo, REF_FINAL, MARKER),
            "signoff_substitutions": signoff_substitutions(repo),
            "commit_verification": snapshot["commit_verification"],
        },
        "github": prs(snapshot),
        "ci": ci(snapshot, repo),
        "tests_weekly": test_counts(repo, chain),
        "reviews": review_findings(repo, snapshot),
        "stated": stated_numbers(repo, snapshot),
        "record_channels": record_channels(repo),
    }
    data["problems"] = (data["reviews"]["problems"] + [f"stated: {x}" for x in data["stated"]["problems"]]
                        + data["record_channels"]["problems"])
    # cross-check the release totals against the totals the records state
    if (nc_first["totals"]["mutations"], nc_final["totals"]["mutations"]) != (772, 873):
        data["problems"].append(f"release totals {nc_first['totals']['mutations']}/{nc_final['totals']['mutations']} != 772/873")
    return data


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    data = compute()
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = config.OUT_DIR / "manuscript_data.json"
    out.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    for p in data["problems"]:
        print("PROBLEM:", p, file=sys.stderr)
    return 1 if (args.check and data["problems"]) else 0


if __name__ == "__main__":
    sys.exit(main())
