#!/usr/bin/env python3
"""Paper A v0.2 — check that the committed v0.1 records are reproduced by the committed v0.1 scripts.

Procedure followed on 2026-10-17 (worktree of commit 5518705):
  1. copy the three cached candidate files into scripts/calm-ms/ (they are git-ignored) and create
     empty data/cohorts/{openms-flames,mslesseg-flames,sibbms-controls-flames,isbi19-lstai}/ so
     the registry finds the four built-in cohorts (the legacy cache is then used, no image read);
  2. run scripts/calm-ms/multisite_conformal_fdr.py, multisite_conformal_advanced.py and
     calm_fdx_realdata.py — each overwrites its record under backend/app/services/assets/;
  3. this script compares each regenerated record with the committed blob (git HEAD) by SHA-256.

    python research/paper_a/verify_v01_records.py
"""
import hashlib
import os
import subprocess

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
RECS = ["backend/app/services/assets/multisite_conformal_record.json",
        "backend/app/services/assets/multisite_conformal_advanced_record.json",
        "backend/app/services/assets/calm_fdx_realdata_record.json"]


def main():
    # json.dump in text mode writes CRLF on Windows; git stores LF (core.autocrlf), so compare the
    # content with line endings normalised to LF.
    for rel in RECS:
        norm = lambda b: b.replace(b"\r\n", b"\n")                      # noqa: E731
        disk = hashlib.sha256(norm(open(os.path.join(ROOT, rel), "rb").read())).hexdigest()
        head = hashlib.sha256(norm(subprocess.run(["git", "-C", ROOT, "show", f"HEAD:{rel}"],
                                                  capture_output=True, check=True).stdout)).hexdigest()
        print(f"{rel}: regenerated {disk[:16]} | committed {head[:16]} | "
              f"{'IDENTICAL' if disk == head else 'DIFFERENT'}")


if __name__ == "__main__":
    main()
