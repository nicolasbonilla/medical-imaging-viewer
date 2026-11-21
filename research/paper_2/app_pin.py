"""E5 (PREREG §12, 2026-11-21): the application's code is used unchanged, pinned to main e559929. Every file E5
imports, and the MSMask atlas, is checked by its git blob SHA-1 (`git rev-parse e559929:<path>`) before use, locally
and on the research VM. No other import; this module is shared by the local driver and the VM job.
"""
import hashlib
from pathlib import Path

APP_COMMIT = "e559929aaf5a19160e20ffdb64d5790eff70c4d6"
APP_BLOBS = {
    "backend/app/services/verified_report.py": "df169af659d86aebbb57e5c50bbb1d34de19f6ba",
    "backend/app/services/report_payload_guard.py": "687675f72dc472fcc09e6d6dd68e7f1d51a59257",
    "backend/app/services/dis_review_gate.py": "48808937666bb2126b29b34fce9d5aec1c67bb3a",
    "backend/app/services/lesion_analysis_service.py": "8109cbe7c0079c4d5f4e95984e57f63b5608ee57",
    "backend/app/services/brain_report_service.py": "994e3492e3e2d8deb3c2bf62f0b5dff4867feb4f",
    "backend/app/services/acquisition_geometry.py": "fb87b179ad0d62dec2c4a9d6c1a051cd9f9c99d2",
    "backend/app/services/quality_gate.py": "ced65da9769c5b7c31c214698b0e9dd3b0bd8ef5",
    "backend/app/services/ms_region_classifier.py": "e0776a878a1386f05168d55d50c4ec2533ab4f81",
    "backend/app/services/report_claim_strict.py": "2cbe39549e1aa322b0ba02c0239e351f49e7cf01",
    "backend/app/services/report_claim_verifier.py": "245fcd428b82b4db2087a56eafdc25878f2b5e74",
    "backend/app/services/report_claim_lexicon.py": "fa5a1f3c1491b9d52f25e911295957514202ee80",
    "backend/app/services/lesion_metrics.py": "ab8c7dc4d5e88ffc460edb641ac8c6fdeb62682b",
    "backend/app/core/config.py": "480a84a3bcba2ffdf35f5f780aeef93038ddc8ca",
    "backend/app/utils/nifti_utils.py": "bd6acc73c2fd8fb9c61ab13376f5770308efad62",
    "backend/data/msmask/sub-mni152_space-mni_msmask.nii.gz": "fb768b4f039c5626d26fac1b3e1f477a396a341b",
}


def blob_sha1(path) -> str:
    """git's blob SHA-1 of the file; a text file with CRLF line ends (a `git archive` on Windows) is hashed with LF,
    as git stores it (the same rule as runner.frozen_check)."""
    data = Path(path).read_bytes()
    if str(path).endswith(".py"):
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def check(root) -> dict:
    """root: the folder that holds `backend/` (a copy of the application at APP_COMMIT)."""
    root = Path(root)
    bad = sorted(p for p, h in APP_BLOBS.items() if not (root / p).exists() or blob_sha1(root / p) != h)
    return {"app_commit": APP_COMMIT, "files": len(APP_BLOBS), "differ_or_missing": bad, "passed": not bad}
