"""Container entry point of the FLAMeS-thick training job (Vertex AI CustomJob, Spot GPU, mstool-research).

    python -m flames_thick.vertex_entry            # supervisor (container command)
    python -m flames_thick.vertex_entry worker     # training process started by the supervisor

Supervisor: registers this attempt (Spot restarts create new attempts), checks the cumulative cost
guard, self-tests the GPU, fetches the mirrored inputs (FLAMeS weights, MSLesSeg) with SHA-256
checks, builds the MSLesSeg-TRAIN-only nnU-Net dataset with FLAMeS's plans, runs the worker
(restarting it once on a crash; in the pilot it SIGKILLs it after a checkpoint and checks that a
fresh worker resumes from the bucket), exports the model and writes manifest / runinfo / cost
records for research/cloud/build_ledger.py.

Worker: builds the trainer, resumes from the bucket's checkpoint (final > latest) or loads FLAMeS
fold 0 strictly, uploads every checkpoint at once, stops cleanly when the cost guard says so
(exit 3), then runs nnU-Net's validation on the internal split.

Configuration (environment; written by research/cloud/launch_vertex.py):
  FT_RUN_ID, FT_ARM (thick|ft), FT_RATE_USD_PER_H, FT_MAX_COST_USD, FT_MAX_HOURS   required
  FT_STORE (gs://mstool-research-data | local:<dir>), FT_PREFIX (flames-thick), FT_SAFETY (1.15),
  FT_ATTEMPT_OVERHEAD_S (300), FT_RESERVE_S (1800), FT_CASE_IDS (pilot subset), FT_KILL_TEST_AFTER_EPOCH,
  FT_DEVICE (cuda), FT_WORKDIR (/w), FT_NPROC (8), FT_MACHINE_TYPE, FT_GPU, FT_IMAGE, FT_GIT_COMMIT,
  FT_PURPOSE, FT_EPOCHS/FT_ITERS/FT_VAL_ITERS/FT_SAVE_EVERY/FT_INITIAL_LR/FT_WARMUP_EPOCHS (trainer).
Exit codes: 0 completed (or budget stop recorded), 1 failure, 143 terminated (Spot preemption).
"""
import json
import os
import platform
import shutil
import signal
import socket
import statistics
import subprocess
import sys
import tarfile
import threading
import time
import zipfile

from flames_thick import budget, data_prep as dp
from flames_thick.store import open_store

TRAINERS = {"thick": "nnUNetTrainerFLAMeSThick", "ft": "nnUNetTrainerFLAMeSFT"}
FLAMES_MEMBERS = ("plans.json", "dataset.json", "dataset_fingerprint.json", "fold_0/checkpoint_final.pth")
NOTICE = ("Fine-tuned from FLAMeS fold 0 (Dereskewicz et al., J Neuroimaging 2025; F. La Rosa, Zenodo "
          "10.5281/zenodo.17955359, CC BY 4.0) on MSLesSeg-train (Guarnera et al., Sci Data 2025; Figshare "
          "10.6084/m9.figshare.27919209.v1, CC BY 4.0). Changes by MSTool-AI research: fine-tuning {arm}; "
          "see docs/research/flames-thick/PROTOCOL.md. Research use; not a medical device.\n")


class Cfg:
    def __init__(self):
        e = os.environ.get
        self.run_id = e("FT_RUN_ID") or sys.exit("FT_RUN_ID is required")
        self.arm = e("FT_ARM", "thick")
        if self.arm not in TRAINERS:
            sys.exit(f"FT_ARM must be one of {sorted(TRAINERS)}")
        self.trainer = TRAINERS[self.arm]
        self.prefix = e("FT_PREFIX", "flames-thick")
        self.rate = float(e("FT_RATE_USD_PER_H") or sys.exit("FT_RATE_USD_PER_H is required"))
        self.max_cost = float(e("FT_MAX_COST_USD") or sys.exit("FT_MAX_COST_USD is required"))
        self.max_hours = float(e("FT_MAX_HOURS") or sys.exit("FT_MAX_HOURS is required"))
        self.safety = float(e("FT_SAFETY", "1.15"))
        self.overhead_s = float(e("FT_ATTEMPT_OVERHEAD_S", "300"))
        # reserve for nnU-Net's final validation (mirroring TTA on ~19 scans: 10-20 min on a T4) + export
        self.reserve_s = float(e("FT_RESERVE_S", "1800"))
        self.case_ids = [c for c in e("FT_CASE_IDS", "").replace(",", " ").split() if c]
        k = e("FT_KILL_TEST_AFTER_EPOCH", "").strip()
        self.kill_after = int(k) if k else None
        self.device = e("FT_DEVICE", "cuda")
        self.work = e("FT_WORKDIR", "/w")
        self.nproc = int(e("FT_NPROC", "8"))
        self.machine = e("FT_MACHINE_TYPE", "")
        self.gpu = e("FT_GPU", "")
        self.image = e("FT_IMAGE", "")
        self.git = e("FT_GIT_COMMIT", "")
        self.purpose = e("FT_PURPOSE", "")
        self.root = f"{self.prefix}/train/{self.run_id}"
        self.remote_fold = f"{self.root}/fold_0"
        self.state = os.path.join(self.work, "state")
        for k, v in {"nnUNet_raw": "nnunet_raw", "nnUNet_preprocessed": "nnunet_preprocessed",
                     "nnUNet_results": "nnunet_results"}.items():
            os.environ.setdefault(k, os.path.join(self.work, v))

    @property
    def output_folder(self):
        return os.path.join(os.environ["nnUNet_results"], dp.DATASET_NAME,
                            f"{self.trainer}__nnUNetPlans__3d_fullres", "fold_0")


def now_s():
    return budget.to_s(budget.utcnow())


def jdump(obj):
    return json.dumps(obj, indent=1, default=str)


def read_state(cfg, name, default=None):
    p = os.path.join(cfg.state, name)
    if not os.path.isfile(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def write_state(cfg, name, obj):
    os.makedirs(cfg.state, exist_ok=True)
    tmp = os.path.join(cfg.state, name + ".part")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(jdump(obj))
    os.replace(tmp, os.path.join(cfg.state, name))


def fetch_verified(store, name, path):
    """Download a mirrored input and check it against its .sha256 sidecar object."""
    store.download(name, path)
    want = store.read_text(name + ".sha256").split()[0].strip() if store.exists(name + ".sha256") else None
    got = dp.sha256_file(path)
    if want and want != got:
        raise RuntimeError(f"{name}: SHA-256 {got} != mirrored {want}")
    return got, bool(want)


def hardware(cfg):
    def sh(cmd):
        try:
            return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=20).stdout.strip()
        except Exception:
            return ""
    def md(path):
        try:
            import urllib.request
            req = urllib.request.Request(f"http://metadata.google.internal/computeMetadata/v1/{path}",
                                         headers={"Metadata-Flavor": "Google"})
            return urllib.request.urlopen(req, timeout=2).read().decode()
        except Exception:
            return ""
    mem = ""
    if os.path.exists("/proc/meminfo"):
        mem = str(round(int(open("/proc/meminfo").readline().split()[1]) / 1048576, 1))
    return {"host": socket.gethostname(), "machine_type": cfg.machine, "gpu_requested": cfg.gpu,
            "gpu": sh("nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader"),
            "cpu_model": sh("lscpu | sed -n 's/^Model name:[[:space:]]*//p' | head -1") or platform.processor(),
            "vcpus": os.cpu_count(), "memory_gb": mem, "zone": md("instance/zone").rsplit("/", 1)[-1],
            "cpu_platform": md("instance/cpu-platform"), "provisioning": "SPOT (Vertex AI)",
            "os": platform.platform()}


def gpu_selftest(device):
    import torch
    info = {"torch": torch.__version__, "cuda_build": torch.version.cuda}
    if device == "cpu":
        info["device"] = "cpu"
        return info
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA not available in the container")
    cap = torch.cuda.get_device_capability()
    arch = torch.cuda.get_arch_list()
    info.update({"device_name": torch.cuda.get_device_name(), "capability": list(cap), "arch_list": arch,
                 "cudnn": torch.backends.cudnn.version()})
    if f"sm_{cap[0]}{cap[1]}" not in arch and not any(a.startswith("compute_") for a in arch):
        raise RuntimeError(f"this torch build has no kernels for sm_{cap[0]}{cap[1]}: {arch}")
    x = torch.randn(2, 4, 32, 32, 32, device="cuda", requires_grad=True)
    conv = torch.nn.Conv3d(4, 8, 3).cuda()
    with torch.autocast("cuda", dtype=torch.float16):
        y = conv(x).float().mean()
    y.backward()
    torch.cuda.synchronize()
    return info


# ====================================================================== worker
def worker():
    cfg = Cfg()
    store = open_store()
    import torch
    from batchgenerators.utilities.file_and_folder_operations import load_json
    from flames_thick.trainer import BudgetStop, nnUNetTrainerFLAMeSFT, nnUNetTrainerFLAMeSThick
    cls = nnUNetTrainerFLAMeSThick if cfg.arm == "thick" else nnUNetTrainerFLAMeSFT
    pre = os.path.join(os.environ["nnUNet_preprocessed"], dp.DATASET_NAME)
    plans, dataset_json = load_json(os.path.join(pre, "nnUNetPlans.json")), load_json(os.path.join(pre, "dataset.json"))
    has_final = store.exists(f"{cfg.remote_fold}/checkpoint_final.pth")
    has_latest = store.exists(f"{cfg.remote_fold}/checkpoint_latest.pth")
    plans["continue_training"] = has_final or has_latest
    if cfg.device == "cuda":
        torch.backends.cudnn.benchmark = True
    tr = cls(plans, "3d_fullres", 0, dataset_json, device=torch.device(cfg.device))
    out = tr.output_folder
    os.makedirs(out, exist_ok=True)
    trained = False
    if has_final:
        store.download(f"{cfg.remote_fold}/checkpoint_final.pth", os.path.join(out, "checkpoint_final.pth"))
        tr.load_checkpoint(os.path.join(out, "checkpoint_final.pth"))
        trained = True
    elif has_latest:
        store.download(f"{cfg.remote_fold}/checkpoint_latest.pth", os.path.join(out, "checkpoint_latest.pth"))
        tr.load_checkpoint(os.path.join(out, "checkpoint_latest.pth"))
    else:
        tr.initialize()
        tr.load_flames_init(os.path.join(cfg.work, "flames", "fold_0", "checkpoint_final.pth"), dp.FLAMES_FOLD0_SHA256)
    write_state(cfg, "init_source.json", tr.init_source)
    prev_records = read_state(cfg, "epochs.json", []) or []
    if not prev_records and store.exists(f"{cfg.remote_fold}/epochs.json"):
        prev_records = json.loads(store.read_text(f"{cfg.remote_fold}/epochs.json"))

    def side_files():
        logs = sorted(f for f in os.listdir(out) if f.startswith("training_log"))
        for f in ([logs[-1]] if logs else []) + ["progress.png"]:
            if os.path.isfile(os.path.join(out, f)):
                store.upload(os.path.join(out, f), f"{cfg.remote_fold}/{'training_log.txt' if f.startswith('training_log') else f}")

    def on_checkpoint(path):
        name = os.path.basename(path)
        if name not in ("checkpoint_latest.pth", "checkpoint_final.pth"):
            return
        t0 = time.time()
        store.upload(path, f"{cfg.remote_fold}/{name}")
        records = [r for r in prev_records if r["epoch"] < (tr.epoch_records[0]["epoch"] if tr.epoch_records else 10**9)]
        records += tr.epoch_records
        store.write_text(f"{cfg.remote_fold}/epochs.json", jdump(records))
        write_state(cfg, "epochs.json", records)
        if tr.thick_info and read_state(cfg, "thick_info.json") is None:
            write_state(cfg, "thick_info.json", tr.thick_info)
            store.write_text(f"{cfg.remote_fold}/thick_augmentation.json", jdump(tr.thick_info))
        try:
            side_files()
        except Exception as exc:
            print("side-file upload failed (not fatal):", repr(exc), flush=True)
        write_state(cfg, "last_uploaded.json", {"name": name, "epoch": int(tr.current_epoch),
                                                "seconds": round(time.time() - t0, 1), "utc": now_s()})
        print(f"[worker] uploaded {name} (epoch {tr.current_epoch}) in {time.time() - t0:.0f}s", flush=True)
        if (cfg.kill_after is not None and name == "checkpoint_latest.pth" and tr.current_epoch >= cfg.kill_after
                and read_state(cfg, "kill_test.json") is None):
            # Pilot only: die abruptly right after a checkpoint is safely in the bucket, like a Spot
            # preemption (no clean-up, data-augmentation workers included); the supervisor must then
            # start a fresh worker that resumes from the bucket at epoch + 1.
            write_state(cfg, "kill_test.json", {"killed_after_epoch": int(tr.current_epoch), "utc": now_s()})
            print(f"[worker] KILL TEST: SIGKILL after the epoch-{tr.current_epoch} checkpoint upload", flush=True)
            kill_self()

    prev_attempts = read_state(cfg, "prev_attempts.json", []) or []
    this_attempt = read_state(cfg, "this_attempt.json")

    def guard(trainer, finished_epoch):
        secs = [r["seconds"] for r in trainer.epoch_records if "seconds" in r][-10:]
        return budget.decide(prev_attempts + [dict(this_attempt, live=True)], budget.utcnow(), cfg.rate,
                             cfg.max_cost, cfg.max_hours, statistics.median(secs) if secs else 0.0,
                             cfg.reserve_s, cfg.overhead_s, cfg.safety)

    tr.checkpoint_callbacks.append(on_checkpoint)
    if this_attempt:
        tr.epoch_end_callbacks.append(guard)
    if not trained:
        try:
            tr.run_training()
        except BudgetStop as stop:
            write_state(cfg, "stop.json", {"reason": str(stop), "epoch": int(tr.current_epoch)})
            for dl in (tr.dataloader_train, tr.dataloader_val):
                try:
                    dl._finish()
                except Exception:
                    pass
            sys.stdout.flush()
            os._exit(3)
    if tr.thick_info:
        write_state(cfg, "thick_info.json", tr.thick_info)
    elif read_state(cfg, "thick_info.json") is None and store.exists(f"{cfg.remote_fold}/thick_augmentation.json"):
        write_state(cfg, "thick_info.json", json.loads(store.read_text(f"{cfg.remote_fold}/thick_augmentation.json")))
    tr.perform_actual_validation(False)
    summ = os.path.join(out, "validation", "summary.json")
    if os.path.isfile(summ):
        store.upload(summ, f"{cfg.remote_fold}/validation_summary.json")
    side_files()
    print("[worker] training and internal validation done", flush=True)


# ====================================================================== supervisor
class Supervisor:
    def __init__(self):
        self.cfg = Cfg()
        self.store = open_store()
        self.start = budget.utcnow()
        self.attempt_id = f"{budget.to_s(self.start).replace(':', '').replace('-', '')}-{socket.gethostname()}"
        self.attempt = {"attempt_id": self.attempt_id, "start_utc": budget.to_s(self.start), "heartbeat_utc": None,
                        "end_utc": None, "image": self.cfg.image, "git_commit": self.cfg.git}
        self.stages = {"boot": budget.to_s(self.start)}
        self.errors, self.kill_test, self.inputs, self.cases = [], None, {}, {}
        self.log_path = os.path.join(self.cfg.work, "logs", f"{self.attempt_id}.log")
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        self._log = open(self.log_path, "a", encoding="utf-8")
        self._stop = threading.Event()
        self.hw = {}
        self.prev = []

    # ---------------------------------------------------------------- logging / records
    def log(self, *msg):
        line = f"{now_s()} " + " ".join(str(m) for m in msg)
        print(line, flush=True)
        self._log.write(line + "\n")
        self._log.flush()

    def stage(self, name):
        self.stages[name] = now_s()
        self.log(f"=== stage {name}")

    def put_attempt(self):
        self.store.write_text(f"{self.cfg.root}/attempts/{self.attempt_id}.json", jdump(self.attempt))

    def all_attempts(self, live=True):
        return self.prev + [dict(self.attempt, live=live)]

    def records(self, status):
        cfg, now = self.cfg, budget.utcnow()
        b = budget.summary(self.all_attempts(), now, cfg.rate, cfg.overhead_s, cfg.safety)
        measured = sum(budget.attempt_seconds(a, now) for a in self.all_attempts())
        epochs = read_state(cfg, "epochs.json", []) or []
        runinfo = {"run_id": cfg.run_id, "platform": "vertex-ai-customjob", "wall_seconds": int(measured),
                   "billed_seconds_estimate": b["billed_seconds_estimate"],
                   "rate_usd_per_h_metadata": cfg.rate, "cost_usd_estimate_metadata": b["cost_usd_list_estimate"],
                   "hardware": self.hw, "stages_utc": self.stages, "attempts": self.all_attempts(live=False),
                   "status": status}
        manifest = {"run_id": cfg.run_id, "kind": "training", "arm": cfg.arm, "trainer": cfg.trainer,
                    "purpose": cfg.purpose, "status": status, "started_utc": self.attempt["start_utc"],
                    "updated_utc": budget.to_s(now), "image": cfg.image, "git_commit": cfg.git, "hardware": self.hw,
                    "versions": self.versions(), "inputs": self.inputs, "training_cases": self.cases,
                    "split": read_state(cfg, "split.json"), "schedule": self.schedule(),
                    "thick_augmentation": read_state(cfg, "thick_info.json"),
                    "init_source": read_state(cfg, "init_source.json"), "stop": read_state(cfg, "stop.json"),
                    "kill_test": self.kill_test, "budget": b, "attempts": self.all_attempts(live=False),
                    "cases": [{"case": f"epoch_{r['epoch']:04d}", "seconds": r.get("seconds"), "ok": True}
                              for r in epochs if r.get("seconds") is not None],
                    "epochs": epochs, "errors": self.errors}
        cost = (f"COST_RECORD,run_id={cfg.run_id},machine={cfg.machine}+{cfg.gpu} spot (Vertex AI),"
                f"seconds={int(b['billed_seconds_estimate'])},rate_usd_per_h={cfg.rate},"
                f"cost_usd_compute_estimate={b['cost_usd_list_estimate']}\n")
        return runinfo, manifest, cost

    def flush_records(self, status):
        runinfo, manifest, cost = self.records(status)
        self.store.write_text(f"runs/{self.cfg.run_id}/runinfo.json", jdump(runinfo))
        self.store.write_text(f"{self.cfg.prefix}/manifests/{self.cfg.run_id}.json", jdump(manifest))
        self.store.write_text(f"{self.cfg.prefix}/cost/{self.cfg.run_id}.txt", cost)
        self.store.upload(self.log_path, f"{self.cfg.prefix}/logs/{self.cfg.run_id}/{self.attempt_id}.log")

    def versions(self):
        if not hasattr(self, "_versions"):
            from importlib import metadata
            v = {"python": sys.version.split()[0]}
            for n in ("torch", "nnunetv2", "batchgeneratorsv2", "numpy", "nibabel", "SimpleITK", "blosc2"):
                try:
                    v[n] = metadata.version(n)
                except metadata.PackageNotFoundError:
                    v[n] = None
            v["pip_freeze"] = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True,
                                             text=True).stdout.splitlines()
            self._versions = v
        return self._versions

    @staticmethod
    def schedule():
        from flames_thick.trainer import PREREGISTERED_SCHEDULE
        return {k: os.environ.get(k) or v for k, v in PREREGISTERED_SCHEDULE.items()} | {
            "nnUNet_n_proc_DA": os.environ.get("nnUNet_n_proc_DA"), "nnUNet_compile": os.environ.get("nnUNet_compile"),
            "FT_LOCAL_TEST_PATCH": os.environ.get("FT_LOCAL_TEST_PATCH"), "FT_CASE_IDS": os.environ.get("FT_CASE_IDS"),
            "FT_KILL_TEST_AFTER_EPOCH": os.environ.get("FT_KILL_TEST_AFTER_EPOCH")}

    def set_status(self, state, **extra):
        self.store.write_text(f"{self.cfg.root}/status.json",
                              jdump({"state": state, "utc": now_s(), "attempt": self.attempt_id, **extra}))

    def heartbeat(self):
        n = 0
        while not self._stop.wait(60):
            n += 1
            try:
                self.attempt["heartbeat_utc"] = now_s()
                self.put_attempt()
                if n % 10 == 0:
                    self.flush_records("running")
            except Exception as exc:
                print("heartbeat failed (not fatal):", repr(exc), flush=True)

    def on_sigterm(self, signum, frame):
        self.log(f"SIGTERM ({signum}): Spot preemption or job cancel — recording the attempt end")
        try:
            self.attempt["end_utc"] = now_s()
            self.attempt["ended_by"] = "SIGTERM"
            self.put_attempt()
            self.store.upload(self.log_path, f"{self.cfg.prefix}/logs/{self.cfg.run_id}/{self.attempt_id}.log")
        finally:
            os._exit(143)

    # ---------------------------------------------------------------- stages
    def fetch_inputs(self):
        w = self.cfg.work
        self.stage("weights_start")
        z = os.path.join(w, "cache", "flames_weights.zip")
        sha, mirrored = fetch_verified(self.store, "inputs/flames_weights.zip", z)
        self.inputs["flames_weights_zip"] = {"object": "inputs/flames_weights.zip", "sha256": sha, "sidecar_checked": mirrored}
        with zipfile.ZipFile(z) as zf:
            names = zf.namelist()
            for m in FLAMES_MEMBERS:
                src = [n for n in names if n.endswith(f"{dp.FLAMES_MODEL}/{m}")]
                if len(src) != 1:
                    raise RuntimeError(f"FLAMeS zip: expected one member for {m}, found {src}")
                dst = os.path.join(w, "flames", *m.split("/"))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with zf.open(src[0]) as s, open(dst, "wb") as d:
                    shutil.copyfileobj(s, d, 1 << 22)
        os.remove(z)
        got = dp.sha256_file(os.path.join(w, "flames", "fold_0", "checkpoint_final.pth"))
        if got != dp.FLAMES_FOLD0_SHA256:
            raise RuntimeError(f"FLAMeS fold-0 checkpoint SHA-256 {got} != {dp.FLAMES_FOLD0_SHA256}")
        self.inputs["flames_fold0_checkpoint_sha256"] = got
        self.stage("datasets_start")
        z = os.path.join(w, "cache", "mslesseg_52771814.zip")
        sha, mirrored = fetch_verified(self.store, "inputs/mslesseg_52771814.zip", z)
        self.inputs["mslesseg_zip"] = {"object": "inputs/mslesseg_52771814.zip", "sha256": sha,
                                       "sidecar_checked": mirrored, "bytes": os.path.getsize(z),
                                       "matches_figshare_size": os.path.getsize(z) == dp.MSLESSEG_ZIP_BYTES}
        return z

    def prepare(self, zip_path):
        self.stage("cases_start")
        cfg = self.cfg
        self.cases = dp.build_raw_dataset(zip_path, os.environ["nnUNet_raw"], cfg.case_ids or None)
        os.remove(zip_path)
        self.log(f"training dataset: {len(self.cases)} MSLesSeg-train scans")
        splits = dp.prepare_nnunet(os.path.join(cfg.work, "flames"), sorted(self.cases), cfg.nproc, self.log)
        write_state(cfg, "split.json", {"fold": 0, "train": splits[0]["train"], "val": splits[0]["val"],
                                        "seed": dp.SPLIT_SEED, "n_splits": len(splits)})
        self.log(f"fold 0: {len(splits[0]['train'])} train / {len(splits[0]['val'])} val scans")

    def run_worker(self):
        cfg = self.cfg
        restarts, n = 0, 0
        while True:
            n += 1
            write_state(cfg, "this_attempt.json", self.attempt)
            write_state(cfg, "prev_attempts.json", self.prev)
            self.log(f"starting worker #{n}")
            p = subprocess.Popen([sys.executable, "-m", "flames_thick.vertex_entry", "worker"],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                                 env=dict(os.environ, PYTHONUNBUFFERED="1", PYTHONFAULTHANDLER="1"),
                                 start_new_session=(os.name == "posix"))
            reader = threading.Thread(target=self._pump, args=(p,), daemon=True)
            reader.start()
            rc = p.wait()
            reader.join(timeout=30)
            kt = read_state(cfg, "kill_test.json")
            if kt is not None and self.kill_test is None:
                self.kill_test = dict(kt, worker_returncode=rc)
                self.log(f"KILL TEST: worker died ({rc}) after epoch {kt['killed_after_epoch']}; wiping local "
                         f"training state, a fresh worker must resume from the bucket")
                shutil.rmtree(os.path.dirname(cfg.output_folder), ignore_errors=True)
                for f in ("last_uploaded.json", "init_source.json", "epochs.json"):
                    if os.path.isfile(os.path.join(cfg.state, f)):
                        os.remove(os.path.join(cfg.state, f))
                continue
            if self.kill_test is not None and "resumed_at_epoch" not in self.kill_test:
                init = read_state(cfg, "init_source.json") or {}
                self.kill_test["resumed_at_epoch"] = init.get("resumed_at_epoch")
                self.kill_test["ok"] = (init.get("kind") == "checkpoint"
                                        and init.get("resumed_at_epoch") == self.kill_test["killed_after_epoch"] + 1)
            if rc == 0:
                return "completed"
            if rc == 3:
                return "budget_stop"
            restarts += 1
            self.errors.append({"worker": n, "returncode": rc, "utc": now_s()})
            if restarts > 1:
                return "failed"
            self.log(f"worker exited with {rc}; restarting once (resume from the bucket)")

    def _pump(self, p):
        for line in p.stdout:
            sys.stdout.write(line)
            self._log.write(line)
        self._log.flush()

    def export(self):
        cfg = self.cfg
        base = os.path.dirname(cfg.output_folder)
        if not os.path.isfile(os.path.join(cfg.output_folder, "checkpoint_final.pth")):
            self.store.download(f"{cfg.remote_fold}/checkpoint_final.pth",
                                os.path.join(cfg.output_folder, "checkpoint_final.pth"))
        with open(os.path.join(base, "NOTICE.txt"), "w") as f:
            f.write(NOTICE.format(arm="with thick-slice augmentation (arm A)" if cfg.arm == "thick"
                                  else "without thick-slice augmentation (control arm B)"))
        for name, obj in (("thick_augmentation.json", read_state(cfg, "thick_info.json")),
                          ("split.json", read_state(cfg, "split.json"))):
            with open(os.path.join(base, name), "w") as f:
                f.write(jdump(obj))
        tar = os.path.join(cfg.work, "model.tar.gz")
        top = os.path.relpath(base, os.environ["nnUNet_results"])
        keep = ["plans.json", "dataset.json", "dataset_fingerprint.json", "NOTICE.txt", "thick_augmentation.json",
                "split.json", "fold_0/checkpoint_final.pth", "fold_0/progress.png", "fold_0/debug.json",
                "fold_0/validation/summary.json"]
        keep += [f"fold_0/{f}" for f in os.listdir(cfg.output_folder) if f.startswith("training_log")]
        with tarfile.open(tar, "w:gz") as t:
            for rel in sorted(keep):
                p = os.path.join(base, *rel.split("/"))
                if os.path.isfile(p):
                    t.add(p, arcname=f"{top}/{rel}".replace(os.sep, "/"))
        sha = dp.sha256_file(tar)
        self.store.upload(tar, f"{cfg.root}/model.tar.gz")
        self.store.write_text(f"{cfg.root}/model.tar.gz.sha256", sha + "\n")
        self.inputs["model_export"] = {"object": f"{cfg.root}/model.tar.gz", "sha256": sha,
                                       "bytes": os.path.getsize(tar), "top_folder": top.replace(os.sep, "/")}
        self.log(f"model exported: {cfg.root}/model.tar.gz sha256 {sha}")

    # ---------------------------------------------------------------- main
    def run(self):
        cfg = self.cfg
        signal.signal(signal.SIGTERM, self.on_sigterm)
        st = json.loads(self.store.read_text(f"{cfg.root}/status.json")) if self.store.exists(f"{cfg.root}/status.json") else {}
        if st.get("state") in ("completed", "budget_stop"):
            self.log(f"run {cfg.run_id} already {st['state']} — nothing to do")
            return 0
        for name in self.store.list(f"{cfg.root}/attempts/"):
            a = json.loads(self.store.read_text(name))
            if a.get("attempt_id") != self.attempt_id:
                self.prev.append(a)
        self.put_attempt()
        hb = threading.Thread(target=self.heartbeat, daemon=True)
        hb.start()
        reason = budget.decide(self.all_attempts(), budget.utcnow(), cfg.rate, cfg.max_cost, cfg.max_hours,
                               0.0, cfg.reserve_s, cfg.overhead_s, cfg.safety)
        status = "failed"
        try:
            if reason:
                self.log("cost guard before start:", reason)
                status = "budget_stop"
                self.set_status(status, reason=reason)
                return 0
            self.set_status("running")
            self.stage("env_start")
            self.hw = hardware(cfg)
            self.hw["selftest"] = gpu_selftest(cfg.device)
            self.log("hardware:", jdump(self.hw))
            zip_path = self.fetch_inputs()
            self.prepare(zip_path)
            self.stage("train_start")
            status = self.run_worker()
            self.stage("train_end")
            if status == "completed":
                self.export()
            if self.kill_test is not None and not self.kill_test.get("ok"):
                self.errors.append({"kill_test": "worker did not resume from the uploaded checkpoint"})
                status = "failed"
            extra = {"stop": read_state(cfg, "stop.json")} if status == "budget_stop" else {}
            self.set_status(status, **extra)
            return 0 if status in ("completed", "budget_stop") else 1
        except Exception as exc:
            import traceback
            self.errors.append({"error": repr(exc)[:2000], "trace": traceback.format_exc()[-4000:]})
            self.log("FAILED:", repr(exc))
            self.set_status("failed", error=repr(exc)[:500])
            return 1
        finally:
            self._stop.set()
            self.stage("end")
            self.attempt["end_utc"] = now_s()
            self.attempt["heartbeat_utc"] = self.attempt["end_utc"]
            self.put_attempt()
            self.flush_records(status)


def kill_self():
    """SIGKILL this worker and its whole process group (it runs in its own session)."""
    sys.stdout.flush()
    if os.name == "posix":
        os.killpg(os.getpgid(0), signal.SIGKILL)
    os.kill(os.getpid(), signal.SIGTERM)          # Windows (local tests): TerminateProcess
    time.sleep(60)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        worker()
        return 0
    return Supervisor().run()


if __name__ == "__main__":
    sys.exit(main())
