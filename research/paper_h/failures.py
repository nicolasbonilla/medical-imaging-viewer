"""RQ2 — verification-failure episodes (PROTOCOL.md §5, metrics 6-8).

    python research/paper_h/failures.py            # prints the RQ2 block as JSON

The coding sheet ``data/failure_coding.json`` is manual. This module (1) checks that every
quoted passage occurs verbatim (whitespace-normalised) in the cited file at the cited ref, or
in the cited commit message, and that every cited commit exists; (2) derives dates, trailer
status and time to detection from git, never from the sheet.
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from collections import Counter
from datetime import date
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.paper_h import config, gitlog  # noqa: E402

CLASSES = ("P", "N", "S", "I", "M", "R", "C")
CHANNELS = ("AR", "BP", "SA", "CI", "IM", "EX", "OW", "SC")
POST_HOC_CHANNELS = ("SC",)


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def load_coding(path: Path | None = None) -> dict:
    path = path or (config.DATA_DIR / "failure_coding.json")
    return json.loads(Path(path).read_text(encoding="utf-8"))


def resolve_ref(ref: str) -> str:
    return config.REFS.get(ref, ref)


class QuoteChecker:
    """Caches file and commit-message text so each is read from git once."""

    def __init__(self, repo):
        self.repo = repo
        self._files: dict[tuple[str, str], str] = {}
        self._msgs: dict[str, str] = {}

    def text(self, ev: dict) -> str:
        ref = resolve_ref(ev["ref"])
        if ev.get("commit_message"):
            if ref not in self._msgs:
                self._msgs[ref] = gitlog.git(self.repo, "show", "-s", "--format=%B", ref)
            return self._msgs[ref]
        key = (ref, ev["path"])
        if key not in self._files:
            self._files[key] = gitlog.show_file(self.repo, ref, ev["path"])
        return self._files[key]

    def check(self, ev: dict) -> bool:
        return normalise(ev["quote"]) in normalise(self.text(ev))


def schema_problems(coding: dict) -> list[str]:
    problems = []
    ids = [e["id"] for e in coding["episodes"]]
    if len(ids) != len(set(ids)):
        problems.append("duplicate episode ids")
    for e in coding["episodes"]:
        if e["class"] not in CLASSES:
            problems.append(f"{e['id']}: unknown class {e['class']}")
        for c in e.get("secondary_classes", []):
            if c not in CLASSES:
                problems.append(f"{e['id']}: unknown secondary class {c}")
        if e["channel"] not in CHANNELS:
            problems.append(f"{e['id']}: unknown channel {e['channel']}")
        if not e.get("evidence"):
            problems.append(f"{e['id']}: no evidence")
        if not e.get("detected") or not e["detected"].get("commit"):
            problems.append(f"{e['id']}: no detecting commit")
        for o in e.get("overlaps", []):
            if o not in ids:
                problems.append(f"{e['id']}: overlaps unknown episode {o}")
    return problems


def verify(coding: dict, repo=None) -> list[str]:
    """Every problem found; an empty list means the sheet is fully traceable."""
    repo = repo or config.repo_root()
    problems = schema_problems(coding)
    qc = QuoteChecker(repo)
    evidences = []
    for e in coding["episodes"]:
        evidences += [(e["id"], ev) for ev in e["evidence"]]
        for side in ("introduced", "detected"):
            sha = (e.get(side) or {}).get("commit")
            if sha and not gitlog.commit_exists(repo, sha):
                problems.append(f"{e['id']}: {side} commit {sha} not found")
    for c in coding.get("verified_then_ineffective", {}).get("controls", []):
        evidences.append((c["rc"], c["evidence"]))
    for c in coding.get("capas", []):
        evidences.append((c["id"], c["evidence"]))
        if not gitlog.commit_exists(repo, c["opened_commit"]):
            problems.append(f"{c['id']}: opened commit {c['opened_commit']} not found")
    for owner, ev in evidences:
        try:
            if not qc.check(ev):
                problems.append(f"{owner}: quote not found in {ev.get('path') or 'commit message'} "
                                f"@ {ev['ref']}: {ev['quote'][:70]!r}")
        except RuntimeError as exc:
            problems.append(f"{owner}: cannot read {ev.get('path')} @ {ev['ref']}: {exc}")
    return problems


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def is_ancestor(repo, a: str, b: str) -> bool:
    import subprocess
    out = subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", a, b],
                         capture_output=True, text=True)
    return out.returncode == 0


def first_parent_landing(repo, sha: str, ref: str) -> str | None:
    """The first commit on ``ref``'s first-parent line that contains ``sha`` (its landing)."""
    line = gitlog.git(repo, "rev-list", "--first-parent", "--reverse", ref).split()
    lo, hi = 0, len(line) - 1
    if not line or not is_ancestor(repo, sha, line[-1]):
        return None
    while lo < hi:                      # contains(sha) is monotone along the first-parent line
        mid = (lo + hi) // 2
        if is_ancestor(repo, sha, line[mid]):
            hi = mid
        else:
            lo = mid + 1
    return line[lo]


def stage_problems(coding: dict, repo=None) -> list[str]:
    """Check each episode's coded stage against git ancestry.

    escaped   — the defective evidence landed on main before the failure was recorded;
    contained — it never landed on main, or the detecting commit landed with it (same PR).
    """
    repo = repo or config.repo_root()
    main = config.REFS["main"]
    problems = []
    for e in coding["episodes"]:
        stage, intro = e.get("stage"), (e.get("introduced") or {}).get("commit")
        det = e["detected"]["commit"]
        if stage not in ("escaped", "contained"):
            problems.append(f"{e['id']}: stage must be 'escaped' or 'contained'")
            continue
        landing = first_parent_landing(repo, intro, main) if intro else None
        if stage == "escaped":
            if landing is None:
                problems.append(f"{e['id']}: coded escaped but {intro} is not on main")
            elif is_ancestor(repo, det, landing):
                problems.append(f"{e['id']}: coded escaped but detection {det} landed with {intro}")
        else:
            if landing is not None and not is_ancestor(repo, det, landing):
                problems.append(f"{e['id']}: coded contained but {intro} landed on main before {det}")
    return problems


def episode_table(coding: dict, repo=None) -> list[dict]:
    repo = repo or config.repo_root()
    rows = []
    for e in coding["episodes"]:
        intro = e.get("introduced") or {}
        det = gitlog.show_commit(repo, e["detected"]["commit"])
        ic = gitlog.show_commit(repo, intro["commit"]) if intro.get("commit") else None
        rows.append({
            "id": e["id"], "title": e["title"], "capa": e["capa"],
            "class": e["class"], "secondary_classes": e.get("secondary_classes", []),
            "channel": e["channel"], "stage": e.get("stage"),
            "items": e.get("items", 1), "overlaps": e.get("overlaps", []),
            "introduced_commit": ic.sha[:7] if ic else None,
            "introduced_date": ic.date if ic else None,
            "introduced_by_agent_trailer": ic.is_agent if ic else None,
            "introduced_model": gitlog.model_label(ic.agent_trailer) if ic and ic.is_agent else None,
            "detected_commit": det.sha[:7], "detected_date": det.date,
            "detected_by_agent_trailer": det.is_agent,
            "detected_model": gitlog.model_label(det.agent_trailer) if det.is_agent else None,
            "days_to_detection": _days(ic.date, det.date) if ic else None,
        })
    return rows


def _latency(values: list[int]) -> dict:
    lat = sorted(values)
    return {
        "n": len(lat),
        "median": statistics.median(lat) if lat else None,
        "min": lat[0] if lat else None,
        "max": lat[-1] if lat else None,
        "values": lat,
    }


def summarise(rows: list[dict]) -> dict:
    by_class = Counter(r["class"] for r in rows)
    by_channel = Counter(r["channel"] for r in rows)
    with_intro = [r for r in rows if r["introduced_commit"]]
    lat = sorted(r["days_to_detection"] for r in with_intro)
    reached_main_or_branch = len(with_intro)
    stages = ("escaped", "contained")
    return {
        "by_stage": {s: sum(1 for r in rows if r["stage"] == s) for s in stages},
        "by_stage_and_channel": {
            s: dict(Counter(r["channel"] for r in rows if r["stage"] == s)) for s in stages},
        "by_stage_and_class": {
            s: dict(Counter(r["class"] for r in rows if r["stage"] == s)) for s in stages},
        "days_to_detection_by_stage": {
            s: _latency([r["days_to_detection"] for r in with_intro if r["stage"] == s]) for s in stages},
        "introduced_date_range_by_stage": {
            s: [min((r["introduced_date"] for r in with_intro if r["stage"] == s), default=None),
                max((r["introduced_date"] for r in with_intro if r["stage"] == s), default=None)]
            for s in stages},
        "distinct_detection_dates_by_stage": {
            s: dict(sorted(Counter(r["detected_date"] for r in rows if r["stage"] == s).items()))
            for s in stages},
        "detected_date_range_by_stage": {
            s: [min((r["detected_date"] for r in rows if r["stage"] == s), default=None),
                max((r["detected_date"] for r in rows if r["stage"] == s), default=None)]
            for s in stages},
        "episodes": len(rows),
        "episodes_without_overlap": sum(1 for r in rows if not r["overlaps"]),
        "items_including_multi_item_episodes": sum(r["items"] for r in rows),
        "by_class": {c: by_class.get(c, 0) for c in CLASSES},
        "by_class_including_secondary": {
            c: sum(1 for r in rows if r["class"] == c or c in r["secondary_classes"]) for c in CLASSES},
        "by_channel": {c: by_channel.get(c, 0) for c in CHANNELS},
        "post_hoc_channels": list(POST_HOC_CHANNELS),
        "detected_by_owner": by_channel.get("OW", 0),
        "with_introducing_commit": reached_main_or_branch,
        "introduced_by_agent_trailer": sum(bool(r["introduced_by_agent_trailer"]) for r in with_intro),
        "detected_by_agent_trailer": sum(bool(r["detected_by_agent_trailer"]) for r in rows),
        "days_to_detection": {
            "n": len(lat),
            "median": statistics.median(lat) if lat else None,
            "min": lat[0] if lat else None,
            "max": lat[-1] if lat else None,
            "q1": statistics.quantiles(lat, n=4)[0] if len(lat) >= 4 else None,
            "q3": statistics.quantiles(lat, n=4)[2] if len(lat) >= 4 else None,
            "over_30_days": sum(1 for d in lat if d > 30),
            "same_or_next_day": sum(1 for d in lat if d <= 1),
        },
        "days_to_detection_by_class": {
            c: sorted(r["days_to_detection"] for r in with_intro if r["class"] == c) for c in CLASSES},
    }


def capa_table(coding: dict, repo=None) -> list[dict]:
    repo = repo or config.repo_root()
    out = []
    for c in coding["capas"]:
        oc = gitlog.show_commit(repo, c["opened_commit"])
        out.append({"id": c["id"], "severity": c["severity"], "channel": c["channel"],
                    "opened_commit": oc.sha[:7], "opened_date": oc.date,
                    "opened_by_agent_trailer": oc.is_agent})
    return out


def compute(repo=None) -> dict:
    repo = repo or config.repo_root()
    coding = load_coding()
    problems = verify(coding, repo) + stage_problems(coding, repo)
    rows = episode_table(coding, repo)
    capas = capa_table(coding, repo)
    vti = coding["verified_then_ineffective"]["controls"]
    return {
        "coding_problems": problems,
        "episodes": rows,
        "summary": summarise(rows),
        "capas": capas,
        "capas_summary": {
            "n": len(capas),
            "by_severity": dict(Counter(c["severity"] for c in capas)),
            "by_channel": dict(Counter(c["channel"] for c in capas)),
            "opened_by_agent_trailer": sum(c["opened_by_agent_trailer"] for c in capas),
        },
        "verified_then_ineffective": {
            "erratum_in_manifest": [c["rc"] for c in vti if c["source"] == "erratum"],
            "post_hoc": [c["rc"] for c in vti if c["source"] != "erratum"],
        },
    }


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2, ensure_ascii=False))
