"""Push / watch / fetch the FLAMeS-thick Kaggle sessions (local tool; research, not the medical device).

Every session is its own PRIVATE Kaggle script kernel "MSTool research FLAMeS-thick <session>" that
mounts the two private input datasets and, from the second session of a chain on, the previous
session's kernel output (its training "store"), from which it resumes. The kernel source is
kernel_main.py with CONFIG and a code bundle filled in: `git archive` of research/flames_thick at the
committed HEAD (uncommitted changes are refused), fixed tar/gzip metadata, SHA-256 recorded.

    python research/flames_thick/kaggle_run/push.py push smoke-s1 [--dry-run]
    python research/flames_thick/kaggle_run/push.py push smoke-s2 --previous smoke-s1
    python research/flames_thick/kaggle_run/push.py wait smoke-s1        # until complete / error
    python research/flames_thick/kaggle_run/push.py fetch smoke-s1 <dir> [--pattern REGEX]
    python research/flames_thick/kaggle_run/push.py quota
Uses the owner's Kaggle API token from ~/.kaggle (never printed or copied).
"""
import argparse
import base64
import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
OWNER = "nicolasbonilna"
DATASETS = [f"{OWNER}/mstool-research-flames-fold0", f"{OWNER}/mstool-research-mslesseg-train"]
PILOT_CASES = "mslesseg_P1_T1 mslesseg_P2_T1"


def slug(session):
    return f"mstool-research-flames-thick-{session}"


def session_config(session, epochs=None):
    """Runs and limits per session kind (smoke = CPU plumbing, pilot = GPU timing + resume, full = the study)."""
    kind, _, part = session.partition("-")
    first = part in ("s1", "")
    base = {"session": session, "prefix": "flames-thick", "python": "3.10.12", "uv_spec": ">=0.8,<1",
            "max_cumulative_hours": 60, "session_reserve_s": 600, "progress_every_s": 300}
    if kind == "smoke":
        env = {"FT_DEVICE": "cpu", "FT_LOCAL_TEST_PATCH": "64,64,64", "FT_CASE_IDS": PILOT_CASES, "FT_EPOCHS": 3,
               "FT_ITERS": 2, "FT_VAL_ITERS": 1, "FT_SAVE_EVERY": 1, "FT_WARMUP_EPOCHS": 1, "nnUNet_n_proc_DA": 0}
        if first:
            env.update({"FT_KILL_TEST_AFTER_EPOCH": 0, "FT_PAUSE_AFTER_EPOCH": 1})
        return {**base, "accelerator": None, "soft_hours": 2.0, "hard_hours": 2.5, "nproc": 2,
                "purpose": "FLAMeS-thick Kaggle plumbing test on CPU (2 MSLesSeg-train scans, 64^3 patch)",
                "runs": [{"run_id": "kaggle-smoke-thick", "arm": "thick", "gpu": "", "gpu_label": "none (CPU)",
                          "env": env}]}
    if kind == "pilot":
        common = {"FT_CASE_IDS": PILOT_CASES, "FT_EPOCHS": 6, "FT_ITERS": 60, "FT_VAL_ITERS": 10,
                  "FT_SAVE_EVERY": 1, "FT_WARMUP_EPOCHS": 1}
        if first:
            common["FT_PAUSE_AFTER_EPOCH"] = 1
        thick = dict(common, **({"FT_KILL_TEST_AFTER_EPOCH": 0} if first else {}))
        return {**base, "accelerator": "NvidiaTeslaT4", "soft_hours": 1.0, "hard_hours": 1.25, "nproc": 2,
                "purpose": "FLAMeS-thick Kaggle pilot: 2 MSLesSeg-train scans, short epochs, kill + session "
                           "hand-over resume, timing of both arms side by side on the 2 T4",
                "runs": [{"run_id": "kaggle-pilot-thick", "arm": "thick", "gpu": 0, "gpu_label": "NVIDIA Tesla T4 (GPU 0 of 2)",
                          "env": thick},
                         {"run_id": "kaggle-pilot-ft", "arm": "ft", "gpu": 1, "gpu_label": "NVIDIA Tesla T4 (GPU 1 of 2)",
                          "env": common}]}
    if kind == "full":
        if not epochs:
            raise SystemExit("full sessions need --epochs (PROTOCOL §5.2 / §14)")
        env = {"FT_EPOCHS": int(epochs)}
        return {**base, "accelerator": "NvidiaTeslaT4", "soft_hours": 11.0, "hard_hours": 11.6, "nproc": 2,
                "purpose": f"FLAMeS-thick full run, both arms side by side ({epochs} epochs each, PROTOCOL §5)",
                "runs": [{"run_id": "flames-thick-a", "arm": "thick", "gpu": 0, "gpu_label": "NVIDIA Tesla T4 (GPU 0 of 2)",
                          "purpose": f"FLAMeS-thick arm A: fold-0 init, MSLesSeg-train, thick-slice augmentation, {epochs} epochs",
                          "env": env},
                         {"run_id": "flames-thick-b", "arm": "ft", "gpu": 1, "gpu_label": "NVIDIA Tesla T4 (GPU 1 of 2)",
                          "purpose": f"FLAMeS-thick arm B (control): same fine-tuning without thick-slice augmentation, {epochs} epochs",
                          "env": env}]}
    raise SystemExit(f"unknown session kind {kind!r}")


def git(*args):
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True, check=True).stdout


def code_bundle(allow_dirty=False):
    dirty = git("status", "--porcelain", "--", "research/flames_thick").decode().strip()
    if dirty and not allow_dirty:
        raise SystemExit(f"commit research/flames_thick first (the bundle is the committed HEAD):\n{dirty}")
    # the committed blobs (not the working tree), with fixed metadata: same commit -> same bytes
    tbuf = io.BytesIO()
    with tarfile.open(fileobj=tbuf, mode="w", format=tarfile.USTAR_FORMAT) as t:
        for path in sorted(git("ls-tree", "-r", "--name-only", "HEAD", "research/flames_thick").decode().split("\n")):
            if not path or "__pycache__" in path:
                continue
            data = git("show", f"HEAD:{path}")
            info = tarfile.TarInfo(path[len("research/"):])
            info.size, info.mtime, info.mode, info.uid, info.gid = len(data), 0, 0o644, 0, 0
            t.addfile(info, io.BytesIO(data))
    tar = tbuf.getvalue()
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(tar)
    blob = buf.getvalue()
    return blob, hashlib.sha256(blob).hexdigest(), git("rev-parse", "HEAD").decode().strip()


def api():
    from kaggle.api.kaggle_api_extended import KaggleApi
    a = KaggleApi()
    a.authenticate()
    return a


def build(session, previous, epochs, allow_dirty, folder):
    cfg = session_config(session, epochs)
    blob, sha, commit = code_bundle(allow_dirty)
    cfg.update({"kernel": f"{OWNER}/{slug(session)}", "previous_kernel": f"{OWNER}/{slug(previous)}" if previous else None,
                "git_commit": commit, "code_sha256": sha, "code_bytes": len(blob)})
    src = open(os.path.join(HERE, "kernel_main.py"), encoding="utf-8").read()
    src = src.replace("__CONFIG_JSON__", json.dumps(cfg, indent=1)).replace("__CODE_B64__", base64.b64encode(blob).decode())
    os.makedirs(folder, exist_ok=True)
    open(os.path.join(folder, "kernel_main.py"), "w", encoding="utf-8", newline="\n").write(src)
    meta = {"id": f"{OWNER}/{slug(session)}", "title": f"MSTool research FLAMeS-thick {session}",
            "code_file": "kernel_main.py", "language": "python", "kernel_type": "script", "is_private": True,
            "enable_gpu": bool(cfg["accelerator"]), "enable_tpu": False, "enable_internet": True,
            "dataset_sources": DATASETS, "competition_sources": [],
            "kernel_sources": [cfg["previous_kernel"]] if previous else [], "model_sources": []}
    if cfg["accelerator"]:
        meta["machine_shape"] = cfg["accelerator"]
    json.dump(meta, open(os.path.join(folder, "kernel-metadata.json"), "w"), indent=1)
    return cfg, meta


def cmd_push(a):
    folder = a.folder or tempfile.mkdtemp(prefix=f"kaggle-{a.session}-")
    cfg, meta = build(a.session, a.previous, a.epochs, a.allow_dirty, folder)
    print(json.dumps({"folder": folder, "kernel": meta["id"], "gpu": meta["enable_gpu"],
                      "machine_shape": meta.get("machine_shape"), "sources": meta["dataset_sources"] + meta["kernel_sources"],
                      "git_commit": cfg["git_commit"], "code_sha256": cfg["code_sha256"],
                      "runs": [(r["run_id"], r["arm"], r["gpu"], r["env"]) for r in cfg["runs"]]}, indent=1))
    if a.dry_run:
        return 0
    r = api().kernels_push(folder, timeout=a.timeout)
    out = {k: getattr(r, k, None) for k in ("ref", "url", "version_number", "error", "invalid_dataset_sources",
                                            "invalid_kernel_sources", "invalid_tags")}
    print(json.dumps(out, indent=1, default=str))
    return 1 if out.get("error") or out.get("invalid_kernel_sources") or out.get("invalid_dataset_sources") else 0


def status(k, session):
    s = k.kernels_status(f"{OWNER}/{slug(session)}")
    st = getattr(s, "status", s)
    name = getattr(st, "name", str(st)).lower()
    return name, getattr(s, "failure_message", None)


def cmd_wait(a):
    k, last, t0 = api(), None, time.time()
    while True:
        try:
            st, msg = status(k, a.session)
        except Exception as exc:                      # transient API errors must not end the watch
            st, msg = "api_error", repr(exc)[:200]
        if st != last:
            print(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), a.session, st, msg or "", flush=True)
            last = st
        if any(x in st for x in ("complete", "error", "cancel")):
            return 0 if "complete" in st else 1
        if a.max_hours and time.time() - t0 > a.max_hours * 3600:
            print("wait: max hours reached, still", st, flush=True)
            return 2
        time.sleep(a.poll)


def cmd_fetch(a):
    files, _ = api().kernels_output(f"{OWNER}/{slug(a.session)}", a.dest, file_pattern=a.pattern, force=True)
    for f in files:
        print(f, os.path.getsize(f) if os.path.isfile(f) else "")
    return 0


def cmd_quota(a):
    r = api().quota_view()
    g = r.gpu_quota
    print(json.dumps({"gpu_used_h": round(g.time_used.total_seconds() / 3600, 3),
                      "gpu_total_h": round(g.total_time_allowed.total_seconds() / 3600, 3),
                      "refresh_utc": r.quota_refresh_time.isoformat() if r.quota_refresh_time else None}))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("push")
    p.add_argument("session")
    p.add_argument("--previous")
    p.add_argument("--epochs", type=int)
    p.add_argument("--folder")
    p.add_argument("--timeout", help="session timeout in seconds (Kaggle's own maximum applies)")
    p.add_argument("--allow-dirty", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_push)
    p = sub.add_parser("wait")
    p.add_argument("session")
    p.add_argument("--poll", type=int, default=120)
    p.add_argument("--max-hours", type=float, default=0)
    p.set_defaults(fn=cmd_wait)
    p = sub.add_parser("fetch")
    p.add_argument("session")
    p.add_argument("dest")
    p.add_argument("--pattern")
    p.set_defaults(fn=cmd_fetch)
    p = sub.add_parser("quota")
    p.set_defaults(fn=cmd_quota)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
