"""RQ3 — risk-control verification evidence (PROTOCOL.md §5, metrics 9-12).

    python research/paper_h/verification.py        # prints the RQ3 block as JSON

Two record schemas exist:
  * schema A (RC-032, RC-029, CAPA-008/009/010/011): ``mutations`` is a dict
    ``{id: {failed, passed, errors?, applied, ...}}`` with optional ``expected_undetected``;
  * schema B (CP-FLAMES-BROWSER-001): ``results`` is a list ``[{id, detected, ...}]``, where
    ids starting with ``BEFORE`` run the NEW tests against the reviewed (pre-fix) code and ids
    ending in ``-old`` run a mutation against the PRE-FIX tests.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.paper_h import config, gitlog  # noqa: E402


# --------------------------------------------------------------------------- RCV headline

_ROW = re.compile(r"^\|\s*(?P<label>[^|]+?)\s*\|\s*(?P<before>[^|]+?)\s*\|\s*(?P<after>[^|]+?)\s*\|\s*$")


def _first_int(cell: str) -> int:
    m = re.search(r"\d+", cell.replace("*", ""))
    if not m:
        raise ValueError(f"no integer in {cell!r}")
    return int(m.group())


def parse_rcv_headline(text: str) -> dict:
    """Parse the §1 headline table of RCV-SUMMARY_2026-07-18.md."""
    section = text.split("## 1. Headline", 1)[1].split("\n## ", 1)[0]
    rows = {}
    for line in section.splitlines():
        m = _ROW.match(line.strip())
        if not m or set(m.group("label")) <= {"-", " "} or m.group("label") == "":
            continue
        label = m.group("label").strip()
        if label.startswith("---") or "record" in m.group("before"):
            continue
        rows[label] = {"recorded_2026_04_12": _first_int(m.group("before")),
                       "reverified_2026_07_18": _first_int(m.group("after"))}
    total = re.search(r"(\d+)\s*/\s*(\d+)", section)
    return {"rows": rows, "controls": int(total.group(2)) if total else None}


# --------------------------------------------------------------------------- manifest

def manifest_summary(manifest: dict) -> dict:
    controls = manifest["controls"]
    status = Counter(v.get("status") for v in controls.values())
    implemented = sorted(k for k, v in controls.items() if v.get("status") == "implemented")
    errata = sorted(k for k, v in controls.items()
                    if v.get("status") == "implemented" and "ERRATUM" in (v.get("note") or ""))
    with_nc = sorted(k for k, v in controls.items()
                     if v.get("status") == "implemented" and v.get("negative_control"))
    return {
        "controls": len(controls),
        "status": dict(sorted(status.items())),
        "implemented": implemented,
        "implemented_with_negative_control": len(with_nc),
        "implemented_with_erratum": errata,
    }


# --------------------------------------------------------------------------- negative controls

def _restored_green(restored) -> bool | None:
    if not isinstance(restored, dict):
        return None
    if "failed" in restored:
        return restored.get("failed", 0) == 0 and restored.get("errors", 0) == 0
    # RC-032: one entry per test file
    return all(isinstance(v, dict) and v.get("failed", 0) == 0 and v.get("errors", 0) == 0
               for v in restored.values())


def normalise_record(record: dict) -> dict:
    """Reduce a negative-control record to comparable counts."""
    if "mutations" in record:                                   # schema A
        muts = record["mutations"]
        expected = set((record.get("expected_undetected") or {}).keys())
        not_applied = sorted(k for k, v in muts.items() if not v.get("applied", False))
        detected = sorted(k for k, v in muts.items()
                          if v.get("applied", False) and (v.get("failed", 0) > 0 or v.get("errors", 0) > 0))
        undetected = sorted(k for k in muts if k not in detected and k not in not_applied)
        return {
            "schema": "A",
            "mutations": len(muts),
            "detected": len(detected),
            "not_applied": not_applied,
            "undetected": undetected,
            "expected_undetected": sorted(expected & set(undetected)),
            "unexpected_undetected": sorted(set(undetected) - expected),
            "restored_green": _restored_green(record.get("restored")),
            "executed": record.get("executed"),
        }
    if "results" in record:                                     # schema B
        res = record["results"]
        muts = [r for r in res if not r["id"].startswith("BEFORE") and not r["id"].endswith("-old")]
        before = [r for r in res if r["id"].startswith("BEFORE")]
        old = [r for r in res if r["id"].endswith("-old")]
        explained = set(((record.get("summary") or {}).get("not_detected_explained") or {}).keys())
        undetected = sorted(r["id"] for r in muts if not r.get("detected"))
        return {
            "schema": "B",
            "mutations": len(muts),
            "detected": sum(bool(r.get("detected")) for r in muts),
            "not_applied": [],
            "undetected": undetected,
            "expected_undetected": sorted(explained & set(undetected)),
            "unexpected_undetected": sorted(set(undetected) - explained),
            "restored_green": record.get("restored_ok"),
            "executed": record.get("dates"),
            "new_tests_vs_reviewed_code": {"runs": len(before),
                                           "failing": sum(bool(r.get("detected")) for r in before)},
            "mutations_vs_pre_fix_tests": {"runs": len(old),
                                           "detected": sum(bool(r.get("detected")) for r in old)},
        }
    raise ValueError("unknown negative-control record schema")


def pooled(rows: list[dict]) -> dict:
    m = sum(r["mutations"] for r in rows)
    d = sum(r["detected"] for r in rows)
    e = sum(len(r["expected_undetected"]) for r in rows)
    u = sum(len(r["unexpected_undetected"]) for r in rows)
    return {
        "records": len(rows),
        "mutations": m,
        "detected": d,
        "declared_equivalent_or_redundant": e,
        "unexpected_undetected": u,
        "detected_share_of_all": round(d / m, 4) if m else None,
        "detected_share_excluding_declared": round(d / (m - e), 4) if m - e else None,
        "restored_green_all": all(r["restored_green"] for r in rows),
    }


def lf_sha256(text: str) -> str:
    """The records' hash basis: SHA-256 of the UTF-8 text with LF line endings."""
    import hashlib
    return hashlib.sha256(text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")).hexdigest()


def evidence_freshness(repo, record: dict, ref: str) -> dict:
    """Post hoc: do the source files a negative-control record hashed still match at ``ref``?

    A mismatch means the code changed after the mutations were run, so the record no longer
    describes the code at ``ref`` (it is stale evidence, not necessarily wrong evidence).
    """
    hashes = record.get("source_sha256") or {}
    match, differ, missing = [], [], []
    for path, recorded in sorted(hashes.items()):
        try:
            current = lf_sha256(gitlog.show_file(repo, ref, path))
        except RuntimeError:
            missing.append(path)
            continue
        (match if current == recorded else differ).append(path)
    return {"hashed_files": len(hashes), "match": len(match), "differ": differ, "missing": missing}


def tests_on_pre_fix_code(record: dict) -> dict:
    return {"total": record["total"], "failed": record["failed"], "passed": record["passed"],
            "expected_to_pass": len(record.get("expected_to_pass_on_main", []))}


def compute(repo=None) -> dict:
    repo = repo or config.repo_root()
    refs = config.REFS
    rcv = parse_rcv_headline(gitlog.show_file(repo, refs["main"], config.RCV_2026_07_18))
    manifests = {k: manifest_summary(json.loads(gitlog.show_file(repo, refs[k], config.MANIFEST_PATH)))
                 for k in ("main", "capa010", "capa011", "flames")}
    nc_rows, freshness = [], []
    for label, ref_key, path in config.NEGATIVE_CONTROL_RECORDS:
        raw = json.loads(gitlog.show_file(repo, refs[ref_key], path))
        nc_rows.append({"record": label, "ref": refs[ref_key][:7], "path": path, **normalise_record(raw)})
        if raw.get("source_sha256"):
            freshness.append({"record": label, "ref": refs[ref_key][:7],
                              "at_own_ref": evidence_freshness(repo, raw, refs[ref_key])})
    capa010_main = tests_on_pre_fix_code(json.loads(
        gitlog.show_file(repo, refs["capa010"], config.CAPA010_TESTS_ON_MAIN)))
    return {
        "rcv_headline": rcv,
        "manifest": manifests,
        "negative_controls": nc_rows,
        "negative_controls_pooled": pooled(nc_rows),
        "negative_controls_pooled_on_main_only": pooled([r for r in nc_rows if r["ref"] == refs["main"][:7]]),
        "capa010_new_tests_on_main_sources": capa010_main,
        "evidence_freshness_post_hoc": freshness,
    }


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2, ensure_ascii=False))
