"""Release step for the in-browser FLAMeS model (configuration management, CMP-001 §6).

Verifies an ONNX file against the pin compiled into the app (frontend/src/services/flames/plan.ts:
FLAMES_FOLD0_MODEL.sha256 / .bytes) and against the committed export manifest
(docs/research/flames-in-browser/evidence/export-fold0-manifest.json), then copies it to its
content-addressed hosting path (frontend/public/models/flames/flames-fold0-<sha8>.onnx, git-ignored).

    python -I research/flames_in_browser/stage_model.py <path to flames-fold0.onnx> [--repo .] [--check-only]

Exit code 0 only when size and SHA-256 equal the pin. Makes no network or cloud call; fetching the archived
copy (gs://mstool-research-data/models/flames/v2.0/..., see CMP-001 §6) is a separate, manual step.
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path


def pin_from_plan(repo: Path) -> tuple[str, int, str]:
    text = (repo / "frontend/src/services/flames/plan.ts").read_text(encoding="utf-8")
    block = text[text.index("export const FLAMES_FOLD0_MODEL"):]
    sha = re.search(r"sha256:\s*'([0-9a-f]{64})'", block).group(1)
    size = int(re.search(r"bytes:\s*(\d+)", block).group(1))
    url = re.search(r"url:\s*'([^']+)'", block).group(1)
    return sha, size, url


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("onnx", type=Path)
    ap.add_argument("--repo", type=Path, default=Path("."))
    ap.add_argument("--check-only", action="store_true")
    a = ap.parse_args()
    sha, size, url = pin_from_plan(a.repo)
    manifest = json.loads((a.repo / "docs/research/flames-in-browser/evidence/export-fold0-manifest.json").read_text())
    if manifest["sha256"] != sha or manifest["bytes"] != size:
        print(f"FAIL: committed manifest ({manifest['sha256'][:12]}, {manifest['bytes']} B) != plan.ts pin ({sha[:12]}, {size} B)")
        return 2
    data = a.onnx.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if len(data) != size or digest != sha:
        print(f"FAIL: {a.onnx} is {len(data)} B sha256 {digest[:12]}..., pinned {size} B {sha[:12]}...; NOT staged")
        return 1
    print(f"OK: {a.onnx} matches the pin ({size} B, sha256 {sha})")
    if not a.check_only:
        dest = a.repo / "frontend/public" / url.lstrip("/")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(a.onnx, dest)
        if hashlib.sha256(dest.read_bytes()).hexdigest() != sha:
            print("FAIL: copy does not match the pin")
            return 1
        print(f"staged -> {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
