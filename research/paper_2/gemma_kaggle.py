"""Gemma 4 E4B-it, design D1, on Kaggle's free GPU (PREREG §4: "D1, FLAMeS-ens records of all four sets, as v1 §4").

The D1 prompts are built here, with the same job class as every other model (designs.D1), and uploaded as a private
Kaggle dataset; the kernel only generates text (greedy, thinking off, 700 output tokens, as v1 §4); the texts come back
through the same job class, so the result lines have the same form as the other models'.

    python -m research.paper_2.gemma_kaggle prepare [--dry-run]   # private dataset with the D1 prompts
    python -m research.paper_2.gemma_kaggle push [--dry-run]      # private GPU kernel
    python -m research.paper_2.gemma_kaggle wait | fetch | ingest # -> runs/gemma-full/results.jsonl
    python -m research.paper_2.gemma_kaggle cleanup               # deletes the private dataset (derived records)

Uses the owner's Kaggle token from ~/.kaggle (never printed). Needs the `kaggle` package (agents-benchmark venv).
"""
import argparse
import json
import sys
import time
from pathlib import Path

from research.paper_2 import runner as RN

OWNER = "nicolasbonilna"
DATASET = f"{OWNER}/mstool-paper2-gemma-inputs"
KERNEL = f"{OWNER}/mstool-paper2-gemma"
MODEL_SOURCE = "google/gemma-4/transformers/gemma-4-e4b-it/1"
MAX_TOKENS = 700                                   # PREREG §4 "All calls": max_tokens 700 (v1 §4)
WORK = RN.RUNS / "gemma-kaggle"
OUT_DIR = RN.RUNS / "gemma-full"


def api():
    from kaggle.api.kaggle_api_extended import KaggleApi
    a = KaggleApi()
    a.authenticate()
    return a


def jobs():
    recs = RN.load_records()
    return [j for j in (RN.make_job(r, d) for r, d in RN.planned(recs, "gemma")) if j is not None]


def cmd_prepare(a):
    d = WORK / "dataset"
    d.mkdir(parents=True, exist_ok=True)
    js = jobs()
    with open(d / "d1_requests.jsonl", "w", encoding="utf-8", newline="\n") as fh:
        for j in js:
            req = j.next_request()
            fh.write(json.dumps({"key": j.key, "system": req["system"], "messages": req["messages"]},
                                ensure_ascii=False) + "\n")
    json.dump({"title": "MSTool paper 2 gemma inputs", "id": DATASET, "licenses": [{"name": "other"}]},
              open(d / "dataset-metadata.json", "w"), indent=1)
    print(json.dumps({"jobs": len(js), "designs": sorted({j.arm for j in js}), "folder": str(d)}))
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
    src = (Path(__file__).parent / "gemma_kernel_p2.py").read_text(encoding="utf-8")
    src = src.replace("__MAX_TOKENS__", str(MAX_TOKENS)).replace("__SOFT_HOURS__", str(a.soft_hours))
    d = WORK / "kernel"
    d.mkdir(parents=True, exist_ok=True)
    (d / "gemma_kernel_p2.py").write_text(src, encoding="utf-8", newline="\n")
    meta = {"id": KERNEL, "title": "MSTool paper2 gemma", "code_file": "gemma_kernel_p2.py", "language": "python",
            "kernel_type": "script", "is_private": True, "enable_gpu": True, "enable_tpu": False,
            "enable_internet": True, "dataset_sources": [DATASET], "competition_sources": [], "kernel_sources": [],
            "model_sources": [MODEL_SOURCE], "machine_shape": "NvidiaTeslaT4"}
    json.dump(meta, open(d / "kernel-metadata.json", "w"), indent=1)
    if a.dry_run:
        print(json.dumps({"kernel": KERNEL, "folder": str(d)}))
        return 0
    r = api().kernels_push(str(d))
    out = {k: str(getattr(r, k, None)) for k in ("ref", "url", "version_number", "error", "invalid_dataset_sources",
                                                 "invalid_model_sources")}
    print(json.dumps(out))
    return 1 if out.get("error") not in ("None", "") else 0


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
    print(len(files), "files")
    return 0


def cmd_ingest(a):
    """The kernel's texts through the same D1 job class -> runs/gemma-full/results.jsonl (job_line form)."""
    from research.agents_benchmark.runner import job_line
    src = WORK / "output" / "gemma_d1.jsonl"
    got = {}
    for x in src.read_text(encoding="utf-8").splitlines():
        if x.strip():
            d = json.loads(x)
            got[d["key"]] = d
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(OUT_DIR / "results.jsonl", "w", encoding="utf-8") as fh:
        for j in jobs():
            line = got.get(j.key)
            if line is None:
                continue
            j.next_request()
            meta = line.get("meta") or {}
            j.consume({"text": line["text"], "usage": meta,
                       "stop_reason": "max_tokens" if meta.get("stopped_at_max") else "end_turn"})
            fh.write(json.dumps(job_line(j, RN.MODELS["gemma"]), ensure_ascii=False) + "\n")
            n += 1
    info = WORK / "output" / "session_info.json"
    if info.exists():
        (OUT_DIR / "session_info.json").write_text(info.read_text(encoding="utf-8"), encoding="utf-8")
    print(json.dumps({"ingested": n, "planned": len(jobs())}))
    return 0


def cmd_cleanup(a):
    k = api()
    try:
        k.dataset_delete(OWNER, DATASET.split("/")[1], no_confirm=True)
        print("dataset deleted")
    except Exception as e:  # noqa: BLE001
        print("delete failed:", repr(e)[:300])
        return 1
    return 0


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
    for name, fn in (("fetch", cmd_fetch), ("ingest", cmd_ingest), ("cleanup", cmd_cleanup)):
        sub.add_parser(name).set_defaults(fn=fn)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
