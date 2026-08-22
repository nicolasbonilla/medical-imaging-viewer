#!/usr/bin/env python3
"""Download the OPEN public MS datasets; document the GATED ones.

Design goals (all satisfiable without credentials on a CPU-only box):

* **Idempotent** — a completed file/repo is detected and skipped; re-running is a
  no-op. Checksums (when the source advertises them) gate "completed".
* **Resumable** — HTTP downloads use a ``.part`` file + a ``Range`` request so an
  interrupted transfer continues instead of restarting.
* **Checksummed** — Zenodo and Figshare expose per-file md5 via their APIs; we
  verify against it automatically. For direct/http and Mendeley entries we verify
  an optional ``sha256`` from ``datasets.yaml`` when present.
* **Honest about gated data** — a ``manual`` dataset is never silently skipped: we
  print its exact registration/DUA steps and create a ``<dest>/<dir>/`` with a
  ``HOW_TO_OBTAIN.txt`` stub so ``preprocess.py`` has a well-known drop location.

Nothing here downloads by import; ``main()`` is the only entry that touches the
network. Every resolver is a small, testable function.

Usage
-----
    python -m research.data_pipeline.download --list
    python -m research.data_pipeline.download --all-open --dest ./raw
    python -m research.data_pipeline.download --dataset msmri_baghdad --dest ./raw
    python -m research.data_pipeline.download --dataset msseg2 --dest ./raw   # prints steps
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Optional

# Support both `python -m research.data_pipeline.download` and direct execution.
try:
    from .common import load_manifest, iter_datasets
except ImportError:  # pragma: no cover - direct-script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from common import load_manifest, iter_datasets  # type: ignore

_UA = {"User-Agent": "mstool-ai-calm-ms-datapipeline/1.0"}
_CHUNK = 1 << 20  # 1 MiB


# ---------------------------------------------------------------------------
# low-level helpers
# ---------------------------------------------------------------------------
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _http_json(url: str, timeout: int = 60) -> dict:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (trusted API host)
        return json.loads(r.read().decode("utf-8"))


def download_file(url: str, dest: Path, expected_md5: Optional[str] = None,
                  expected_sha256: Optional[str] = None, timeout: int = 120) -> Path:
    """Resumable, idempotent single-file download with optional checksum gate.

    If ``dest`` already exists and matches the expected checksum (or no checksum
    was given), returns immediately. Otherwise streams to ``dest.part`` with an
    HTTP ``Range`` resume, then atomically renames on success.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        if _checksum_ok(dest, expected_md5, expected_sha256):
            print(f"    [skip] {dest.name} already present + verified")
            return dest
        if expected_md5 is None and expected_sha256 is None:
            print(f"    [skip] {dest.name} already present (no checksum to verify)")
            return dest
        print(f"    [redo] {dest.name} present but checksum mismatch — refetching")
        dest.unlink()

    part = dest.with_suffix(dest.suffix + ".part")
    have = part.stat().st_size if part.exists() else 0
    req = urllib.request.Request(url, headers=dict(_UA))
    if have:
        req.add_header("Range", f"bytes={have}-")
        print(f"    [resume] {dest.name} from byte {have:,}")
    else:
        print(f"    [get] {url}")

    mode = "ab" if have else "wb"
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        with open(part, mode) as out:
            while True:
                chunk = r.read(_CHUNK)
                if not chunk:
                    break
                out.write(chunk)

    if expected_md5 or expected_sha256:
        if not _checksum_ok(part, expected_md5, expected_sha256):
            raise ValueError(f"checksum mismatch after download: {dest.name}")
    part.replace(dest)
    print(f"    [done] {dest.name} ({dest.stat().st_size:,} bytes)")
    return dest


def _checksum_ok(path: Path, md5: Optional[str], sha256: Optional[str]) -> bool:
    if sha256:
        return _sha256(path).lower() == sha256.lower()
    if md5:
        return _md5(path).lower() == md5.lower()
    return False


# ---------------------------------------------------------------------------
# per-method resolvers  (each returns the dest dir it wrote into)
# ---------------------------------------------------------------------------
def fetch_git(entry: dict, out: Path) -> Path:
    """`git clone` (or `pull` if already present) a data-bearing repo."""
    url = entry["download"]["url"]
    out.mkdir(parents=True, exist_ok=True)
    if (out / ".git").exists():
        print(f"    [pull] {out}")
        subprocess.run(["git", "-C", str(out), "pull", "--ff-only"], check=False)
    else:
        print(f"    [clone] {url} -> {out}")
        subprocess.run(["git", "clone", "--depth", "1", url, str(out)], check=True)
    return out


def fetch_zenodo(entry: dict, out: Path) -> Path:
    """Resolve a Zenodo record's files via its API and download each (md5-checked)."""
    rec = entry["download"]["record_id"]
    meta = _http_json(f"https://zenodo.org/api/records/{rec}")
    files = meta.get("files", [])
    if not files:
        raise RuntimeError(f"Zenodo record {rec} lists no files")
    out.mkdir(parents=True, exist_ok=True)
    for f in files:
        # Zenodo checksum is like "md5:abcd..."
        algo, _, digest = (f.get("checksum") or "md5:").partition(":")
        link = f["links"]["self"]
        name = f.get("key") or link.rsplit("/", 1)[-1]
        download_file(link, out / name,
                      expected_md5=digest if algo == "md5" else None)
    return out


def fetch_figshare(entry: dict, out: Path) -> Path:
    """Resolve a Figshare article's files via its API and download each (md5-checked)."""
    art = entry["download"].get("article_id")
    if not art:
        raise RuntimeError(
            "figshare article_id is null in datasets.yaml — set it from the live "
            "record first (see the entry's `verify:` note).")
    meta = _http_json(f"https://api.figshare.com/v2/articles/{art}")
    files = meta.get("files", [])
    if not files:
        raise RuntimeError(f"Figshare article {art} lists no files")
    out.mkdir(parents=True, exist_ok=True)
    for f in files:
        download_file(f["download_url"], out / f["name"],
                      expected_md5=f.get("computed_md5") or f.get("supplied_md5"))
    return out


def fetch_mendeley(entry: dict, out: Path) -> Path:
    """Download the Mendeley Data whole-dataset zip from its S3 cache URL."""
    dl = entry["download"]
    out.mkdir(parents=True, exist_ok=True)
    name = f"{dl['dataset_id']}-{dl.get('version', 1)}.zip"
    download_file(dl["zip_url"], out / name, expected_sha256=dl.get("sha256"))
    return out


def fetch_http(entry: dict, out: Path) -> Path:
    """Download explicit direct URL(s) with optional sha256 verification."""
    out.mkdir(parents=True, exist_ok=True)
    for spec in entry["download"]["urls"]:
        url = spec["url"]
        name = url.rsplit("/", 1)[-1] or "download.bin"
        download_file(url, out / name, expected_sha256=spec.get("sha256"))
    return out


def document_manual(name: str, entry: dict, out: Path) -> Path:
    """Print the exact obtain-steps for a gated dataset + write a drop-dir stub."""
    dl = entry["download"]
    dropdir = out / dl.get("dropdir", name)
    dropdir.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# HOW TO OBTAIN — {entry.get('title', name)}",
        f"# access: GATED ({entry.get('license', 'restricted')})",
        f"# landing: {entry.get('landing', '')}",
        "",
        "Steps:",
    ]
    lines += [f"  {i}. {s}" for i, s in enumerate(dl.get("steps", []), 1)]
    lines += ["", f"Drop the unzipped files into this directory: {dropdir}",
              "Then run preprocess.py pointing --raw at the dataset's dropdir."]
    text = "\n".join(lines) + "\n"
    (dropdir / "HOW_TO_OBTAIN.txt").write_text(text, encoding="utf-8")
    print("\n".join(lines))
    print(f"\n    [stub] wrote {dropdir / 'HOW_TO_OBTAIN.txt'}")
    return dropdir


_RESOLVERS = {
    "git": fetch_git,
    "zenodo": fetch_zenodo,
    "figshare": fetch_figshare,
    "mendeley": fetch_mendeley,
    "http": fetch_http,
}


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------
def fetch_dataset(name: str, entry: dict, dest: Path) -> Path:
    """Fetch one dataset by its manifest entry. Gated -> print steps + stub."""
    method = (entry.get("download") or {}).get("method")
    print(f"\n=== {name}  [{entry.get('access')}]  ({method}) ===")
    if entry.get("access") == "gated" or method == "manual":
        return document_manual(name, entry, dest)
    resolver = _RESOLVERS.get(method)
    if resolver is None:
        raise ValueError(f"[{name}] unknown download.method={method!r}")
    target = dest / name
    return resolver(entry, target)


def _print_list(manifest: dict) -> None:
    print(f"{'dataset':22s} {'access':6s} {'method':9s} {'use'}")
    print("-" * 72)
    for name, e in iter_datasets(manifest):
        method = (e.get("download") or {}).get("method", "-")
        use = ",".join(e.get("target_use", []))
        print(f"{name:22s} {e.get('access',''):6s} {method:9s} {use}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", default="./raw", help="download root (default ./raw)")
    ap.add_argument("--dataset", help="fetch a single dataset by manifest key")
    ap.add_argument("--all-open", action="store_true", help="fetch every OPEN dataset")
    ap.add_argument("--all", action="store_true",
                    help="process every dataset (gated ones print steps only)")
    ap.add_argument("--list", action="store_true", help="list datasets and exit")
    args = ap.parse_args(argv)

    manifest = load_manifest()
    if args.list:
        _print_list(manifest)
        return 0

    dest = Path(args.dest).resolve()
    datasets = dict(iter_datasets(manifest))

    if args.dataset:
        if args.dataset not in datasets:
            ap.error(f"unknown dataset {args.dataset!r}; try --list")
        selected = [args.dataset]
    elif args.all_open:
        selected = [n for n, e in datasets.items() if e.get("access") == "open"]
    elif args.all:
        selected = list(datasets)
    else:
        ap.error("choose one of --list / --dataset / --all-open / --all")
        return 2

    failures = []
    for name in selected:
        try:
            fetch_dataset(name, datasets[name], dest)
        except Exception as e:  # keep going; report at the end
            print(f"    [error] {name}: {e}")
            failures.append((name, str(e)))

    print(f"\nProcessed {len(selected)} dataset(s); {len(failures)} failure(s).")
    for name, err in failures:
        print(f"  FAILED {name}: {err}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
