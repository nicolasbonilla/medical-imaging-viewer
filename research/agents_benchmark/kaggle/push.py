"""Gemma 4 E4B-it on Kaggle's free GPU (PREREG section 4): prepare inputs, push, wait, fetch, ingest.

    python -m research.agents_benchmark.kaggle.push prepare     # private dataset with A0 prompts + records
    python -m research.agents_benchmark.kaggle.push push [--soft-hours 11]
    python -m research.agents_benchmark.kaggle.push wait
    python -m research.agents_benchmark.kaggle.push fetch
    python -m research.agents_benchmark.kaggle.push ingest      # -> runs/gemma-<subset>/results.jsonl

Uses the owner's Kaggle API token from ~/.kaggle (never printed or copied). Private dataset and kernel only.
"""
import argparse
import base64
import gzip
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import time
from pathlib import Path

from .. import config

OWNER = "nicolasbonilna"
DATASET = f"{OWNER}/mstool-agents-bench-inputs"
KERNEL = f"{OWNER}/mstool-agents-bench-gemma"
MODEL_SOURCE = "google/gemma-4/transformers/gemma-4-e4b-it/1"
WORK = Path(config.WORK_DIR) / "kaggle"


def api():
    from kaggle.api.kaggle_api_extended import KaggleApi
    a = KaggleApi()
    a.authenticate()
    return a


def git(*args):
    return subprocess.run(["git", "-C", str(config.REPO), *args], capture_output=True, check=True).stdout


def code_bundle():
    dirty = git("status", "--porcelain", "--", "research/agents_benchmark").decode().strip()
    dirty = "\n".join(l for l in dirty.splitlines() if l.strip().endswith(".py"))
    if dirty:
        raise SystemExit(f"commit research/agents_benchmark first (the bundle is the committed HEAD):\n{dirty}")
    tbuf = io.BytesIO()
    with tarfile.open(fileobj=tbuf, mode="w", format=tarfile.USTAR_FORMAT) as t:
        for path in sorted(git("ls-tree", "-r", "--name-only", "HEAD", "research/agents_benchmark").decode().split("\n")):
            if not path.endswith(".py") or "/tests/" in path or "/kaggle/" in path:
                continue
            data = git("show", f"HEAD:{path}")
            info = tarfile.TarInfo(path)
            info.size, info.mtime, info.mode = len(data), 0, 0o644
            t.addfile(info, io.BytesIO(data))
        info = tarfile.TarInfo("research/__init__.py")
        info.size, info.mtime, info.mode = 0, 0, 0o644
        t.addfile(info, io.BytesIO(b""))
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(tbuf.getvalue())
    blob = buf.getvalue()
    return blob, hashlib.sha256(blob).hexdigest(), git("rev-parse", "HEAD").decode().strip()


def cmd_prepare(a):
    from ..arms import A0
    from ..records import load_record
    from ..runner import planned_jobs
    d = WORK / "dataset"
    d.mkdir(parents=True, exist_ok=True)
    a0_lines, a3_lines, need = [], [], set()
    for subset in config.PLAN["gemma"]["subsets"]:
        for rid_, arm, lang, payload in planned_jobs("gemma", subset):
            rec = load_record(rid_)
            need.add(rid_)
            if arm == "A0":
                j = A0(rec, lang=lang, payload=payload)
                a0_lines.append({"key": j.key, "subset": subset, "record_id": rid_, "lang": lang, "payload": payload,
                                 "system": j.system, "user": j.user})
            else:
                a3_lines.append({"subset": subset, "record_id": rid_, "lang": lang, "payload": payload})
    with open(d / "a0_requests.jsonl", "w", encoding="utf-8") as fh:
        for x in a0_lines:
            fh.write(json.dumps(x, ensure_ascii=False) + "\n")
    with open(d / "a3_jobs.jsonl", "w", encoding="utf-8") as fh:
        for x in a3_lines:
            fh.write(json.dumps(x) + "\n")
    with open(d / "views.jsonl", "w", encoding="utf-8") as fh:
        for rid_ in sorted(need):
            fh.write(json.dumps({"record_id": rid_, "view": load_record(rid_)["view"]}, ensure_ascii=False) + "\n")
    json.dump({"title": "MSTool agents benchmark inputs", "id": DATASET, "licenses": [{"name": "other"}]},
              open(d / "dataset-metadata.json", "w"), indent=1)
    print(json.dumps({"a0": len(a0_lines), "a3": len(a3_lines), "records": len(need), "folder": str(d)}))
    if a.dry_run:
        return 0
    k = api()
    try:
        r = k.dataset_create_new(str(d), public=False, quiet=True, dir_mode="skip")
    except Exception as e:  # noqa: BLE001 - exists already: new version
        print("create failed, trying a new version:", repr(e)[:200])
        r = k.dataset_create_version(str(d), version_notes=f"inputs {time.strftime('%Y-%m-%d %H:%M')}", quiet=True,
                                     dir_mode="skip")
    print({x: getattr(r, x, None) for x in ("ref", "url", "status", "error")})
    return 0


def cmd_push(a):
    blob, sha, commit = code_bundle()
    cfg = {"kernel": KERNEL, "git_commit": commit, "code_sha256": sha, "soft_hours": a.soft_hours,
           "subsets": config.PLAN["gemma"]["subsets"], "model": MODEL_SOURCE, "max_tokens": config.MAX_TOKENS}
    src = (config.HERE / "kaggle" / "gemma_kernel.py").read_text(encoding="utf-8")
    src = src.replace("__CONFIG_JSON__", json.dumps(cfg)).replace("__CODE_B64__", base64.b64encode(blob).decode())
    d = WORK / "kernel"
    d.mkdir(parents=True, exist_ok=True)
    (d / "gemma_kernel.py").write_text(src, encoding="utf-8", newline="\n")
    meta = {"id": KERNEL, "title": "MSTool agents bench gemma", "code_file": "gemma_kernel.py", "language": "python",
            "kernel_type": "script", "is_private": True, "enable_gpu": True, "enable_tpu": False,
            "enable_internet": True, "dataset_sources": [DATASET], "competition_sources": [], "kernel_sources": [],
            "model_sources": [MODEL_SOURCE], "machine_shape": "NvidiaTeslaT4"}
    json.dump(meta, open(d / "kernel-metadata.json", "w"), indent=1)
    print(json.dumps({"kernel": KERNEL, "git_commit": commit, "code_sha256": sha, "soft_hours": a.soft_hours}))
    if a.dry_run:
        return 0
    r = api().kernels_push(str(d))
    out = {k: getattr(r, k, None) for k in ("ref", "url", "version_number", "error", "invalid_dataset_sources",
                                            "invalid_model_sources")}
    print(json.dumps(out, default=str))
    (WORK / "push_log.jsonl").open("a").write(json.dumps({"ts": time.time(), **cfg, **{k: str(v) for k, v in out.items()}})
                                              + "\n")
    return 1 if out.get("error") else 0


def cmd_wait(a):
    k, last = api(), None
    while True:
        try:
            s = k.kernels_status(KERNEL)
            st = getattr(getattr(s, "status", s), "name", str(getattr(s, "status", s))).lower()
            msg = getattr(s, "failure_message", None)
        except Exception as e:  # noqa: BLE001
            st, msg = "api_error", repr(e)[:200]
        if st != last:
            print(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), st, msg or "", flush=True)
            last = st
        if st != "api_error" and any(x in st for x in ("complete", "error", "cancel")):
            return 0 if "complete" in st else 1
        if a.once:
            return 0
        time.sleep(a.poll)


def cmd_fetch(a):
    dest = WORK / "output"
    dest.mkdir(parents=True, exist_ok=True)
    files, _ = api().kernels_output(KERNEL, str(dest), force=True)
    for f in files:
        print(f)
    return 0


def cmd_ingest(a):
    """Gemma outputs -> runs/gemma-<subset>/results.jsonl in the same form as the other models."""
    from ..arms import A0
    from ..records import load_record
    from ..runner import run_dir
    src = WORK / "output"
    model = config.MODELS["gemma"]
    info = json.loads((src / "session_info.json").read_text()) if (src / "session_info.json").exists() else {}
    counts = {}
    a0 = [json.loads(x) for x in (src / "gemma_a0.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()] \
        if (src / "gemma_a0.jsonl").exists() else []
    a3 = [json.loads(x) for x in (src / "gemma_a3.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()] \
        if (src / "gemma_a3.jsonl").exists() else []
    by_subset = {}
    for line in a0:
        rid_, arm, lang, payload = line["key"].split("|")
        job = A0(load_record(rid_), lang=lang, payload=None if payload == "-" else payload)
        meta = line.get("meta") or {}
        job.consume({"text": line["text"], "usage": meta,
                     "stop_reason": "max_tokens" if meta.get("stopped_at_max") else "end_turn"})
        by_subset.setdefault(line["subset"], []).append(_line(job.key, rid_, "A0", lang, job.payload, model, job.result,
                                                               job.calls))
    for line in a3:
        by_subset.setdefault(line["subset"], []).append(_line(line["key"], line["record_id"], "A3", line["lang"],
                                                               line["payload"], model, line["result"], line["calls"]))
    for subset, rows in by_subset.items():
        p = run_dir("gemma", subset) / "results.jsonl"
        with open(p, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        counts[subset] = len(rows)
        (run_dir("gemma", subset) / "session_info.json").write_text(json.dumps(info, indent=1))
    print(json.dumps(counts))
    return 0


def _line(key, rid_, arm, lang, payload, model, result, calls):
    return {"key": key, "record_id": rid_, "arm": arm, "lang": lang, "payload": payload, "model": model,
            "max_tokens": config.MAX_TOKENS, "result": result, "calls": calls, "n_calls": len(calls), "usd": 0.0,
            "ts": time.time()}


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_prepare)
    p = sub.add_parser("push")
    p.add_argument("--soft-hours", type=float, default=11.0)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_push)
    p = sub.add_parser("wait")
    p.add_argument("--poll", type=int, default=120)
    p.add_argument("--once", action="store_true")
    p.set_defaults(fn=cmd_wait)
    sub.add_parser("fetch").set_defaults(fn=cmd_fetch)
    sub.add_parser("ingest").set_defaults(fn=cmd_ingest)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
