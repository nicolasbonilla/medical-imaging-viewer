"""Recompute every number in docs/research/paper-h/RESULTS.md.

    python research/paper_h/run_all.py            # writes research/paper_h/out/results.json
    python research/paper_h/run_all.py --check    # also fails (exit 1) if the coding sheet has a problem

Read-only: git log/show/blame/grep on pinned SHAs, plus the committed GitHub snapshot.
Refresh the snapshot separately with ``python research/paper_h/snapshot_github.py``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.paper_h import config, contribution, failures, governance, verification  # noqa: E402


def compute(repo=None) -> dict:
    repo = repo or config.repo_root()
    return {
        "refs": config.REFS,
        "rq1_contribution": contribution.compute(repo),
        "rq2_failures": failures.compute(repo),
        "rq3_verification": verification.compute(repo),
        "rq4_governance": governance.compute(repo),
    }


def headline(r: dict) -> dict:
    c = r["rq1_contribution"]["commits"]
    s = r["rq2_failures"]["summary"]
    nc = r["rq3_verification"]["negative_controls_pooled"]
    g = r["rq4_governance"]
    return {
        "commits_agent_of_all": f'{c["all"]["agent"]}/{c["all"]["total"]}',
        "episodes": s["episodes"],
        "episodes_escaped_contained": f'{s["by_stage"]["escaped"]}/{s["by_stage"]["contained"]}',
        "median_days_escaped": s["days_to_detection_by_stage"]["escaped"]["median"],
        "median_days_contained": s["days_to_detection_by_stage"]["contained"]["median"],
        "detected_by_owner": s["detected_by_owner"],
        "rcv_verified_before_after": "{}/{} -> {}/{}".format(
            r["rq3_verification"]["rcv_headline"]["rows"]["Verified"]["recorded_2026_04_12"],
            r["rq3_verification"]["rcv_headline"]["controls"],
            r["rq3_verification"]["rcv_headline"]["rows"]["Verified"]["reverified_2026_07_18"],
            r["rq3_verification"]["rcv_headline"]["controls"]),
        "mutations_detected": f'{nc["detected"]}/{nc["mutations"]}',
        "formal_github_reviews": g["github"]["formal_reviews_total"],
        "approval_lines_agent_written": "{}/{}".format(
            g["approval_lines_in_controlled_documents_main"]["written_by_agent_trailered_commits"],
            g["approval_lines_in_controlled_documents_main"]["lines"]),
        "coding_problems": len(r["rq2_failures"]["coding_problems"]),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    results = compute()
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = config.OUT_DIR / "results.json"
    out.write_text(json.dumps(results, indent=1, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8")
    print(json.dumps(headline(results), indent=1, ensure_ascii=False))
    print(f"wrote {out}")
    problems = results["rq2_failures"]["coding_problems"]
    for p in problems:
        print("CODING PROBLEM:", p, file=sys.stderr)
    return 1 if (args.check and problems) else 0


if __name__ == "__main__":
    sys.exit(main())
