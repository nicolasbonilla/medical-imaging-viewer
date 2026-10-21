"""Kaggle pilot pass/fail + full-run projection (local, read-only; RUNBOOK §10).

    python research/flames_thick/kaggle_run/push.py fetch pilot-s1 <d1> --pattern "sessions/|manifests/|status.json"
    python research/flames_thick/kaggle_run/push.py fetch pilot-s2 <d2> --pattern "sessions/|manifests/|status.json|validation_summary"
    python research/flames_thick/kaggle_run/pilot_check.py <d1> <d2> --quota-left-h 29.2

Session 1 (per arm): status "paused" by the forced pause after epoch 1; thick arm: kill test ok (SIGKILL
after epoch 0, fresh worker resumed at epoch 1). Session 2 (per arm): pilot_report.checks (completed,
no errors, FLAMeS SHA-256, MSLesSeg-train only, axial axis, model exported, GPU self-test), resumed from
the previous kernel's output at epoch 2, epochs 0..E-1 contiguous, two attempts (one per session).

Projection (Kaggle rule, PROTOCOL §14): both arms train side by side, one T4 each, so a session advances
both at the SLOWER arm's pace. epoch_s = 250 x train_s/iter + 50 x val_s/iter (median over pilot epochs
that are not the first epoch of a worker), per arm. Quota hours for E epochs = E x epoch_s + n_sessions x
(setup + hand-over) + final validation, with n_sessions = ceil(E / epochs per 11-h session). E = 300 if
that fits the GPU quota left this week minus a 1-h margin, else the largest E that fits, never below 150;
the same E for both arms.
"""
import argparse
import datetime as dt
import glob
import json
import math
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import pilot_report  # noqa: E402

FULL_ITERS, FULL_VAL_ITERS, EPOCHS, MIN_EPOCHS = 250, 50, 300, 150
F = "%Y-%m-%dT%H:%M:%SZ"


def load_all(folder, kind):
    return [json.load(open(p)) for p in sorted(glob.glob(os.path.join(folder, "**", kind, "*.json"), recursive=True))]


def steady(man, worker_starts):
    return [e for e in man.get("epochs", []) if e.get("train_seconds") and e["epoch"] not in worker_starts]


def arm_projection(man, worker_starts):
    eps = steady(man, worker_starts)
    if not eps:
        raise SystemExit(f"{man.get('run_id')}: no steady epoch")
    t_it = statistics.median(e["train_seconds"] / e["iters"] for e in eps)
    t_val = statistics.median(e["val_seconds"] / e["val_iters"] for e in eps)
    return {"steady_epochs": [e["epoch"] for e in eps], "train_s_per_iter": round(t_it, 3),
            "val_s_per_iter": round(t_val, 3), "epoch_s_projected": round(FULL_ITERS * t_it + FULL_VAL_ITERS * t_val, 1),
            "measured_epoch_seconds": [e.get("seconds") for e in man["epochs"]]}


def plan(epoch_s, setup_s, quota_left_h, soft_h=11.0, handover_s=600, final_val_s=1800, margin_h=1.0):
    per_session = math.floor((soft_h * 3600 - setup_s - handover_s) / epoch_s)

    def need(e):
        n = math.ceil(e / per_session)
        return (e * epoch_s + n * (setup_s + handover_s) + final_val_s) / 3600, n

    budget = quota_left_h - margin_h
    e = EPOCHS
    while e > MIN_EPOCHS and need(e)[0] > budget:
        e -= 1
    h, n = need(e)
    return {"epochs": e, "quota_hours_needed": round(h, 2), "sessions": n, "epochs_per_session": per_session,
            "fits_this_week": h <= budget, "quota_left_h": quota_left_h, "margin_h": margin_h,
            "quota_hours_for_300": round(need(EPOCHS)[0], 2)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("s1")
    ap.add_argument("s2")
    ap.add_argument("--quota-left-h", type=float, required=True)
    ap.add_argument("--preprocess-s", type=float, default=300.0,
                    help="extra set-up for 93 scans instead of the pilot's 2 (nnU-Net preprocessing)")
    a = ap.parse_args(argv)
    m1 = {m["run_id"]: m for m in load_all(a.s1, "manifests")}
    m2 = {m["run_id"]: m for m in load_all(a.s2, "manifests")}
    res = {"arms": {}, "sessions": []}
    for rid, m in m2.items():
        first = m1.get(rid, {})
        c = pilot_report.checks(m)
        kt = first.get("kill_test")
        c["s1_paused"] = first.get("status") == "paused" and "forced pause" in str((first.get("pause") or {}).get("reason"))
        c["s1_kill_test_ok"] = (kt is None and m["arm"] != "thick") or bool(kt and kt.get("ok"))
        pause_epoch = (first.get("pause") or {}).get("epoch")
        c["s2_resumed_after_pause"] = (m.get("init_source") or {}) == {"kind": "checkpoint", "resumed_at_epoch": pause_epoch}
        c["epochs_contiguous"] = [e["epoch"] for e in m["epochs"]] == list(range(len(m["epochs"])))
        c["two_attempts"] = len(m.get("attempts", [])) == 2
        starts = {0, pause_epoch} | ({kt["resumed_at_epoch"]} if kt else set())
        res["arms"][rid] = {"arm": m["arm"], "checks": c, "projection": arm_projection(m, starts),
                            "gpu": (m.get("hardware") or {}).get("selftest", {}).get("device_name"),
                            "kill_test": kt, "pause_s1": first.get("pause"), "init_s2": m.get("init_source")}
    setup = []
    for folder in (a.s1, a.s2):
        for s in load_all(folder, "sessions"):
            st = s.get("stages", {})
            if s["session_id"] in [x["session_id"] for x in res["sessions"]]:
                continue
            res["sessions"].append({"session_id": s["session_id"], "wall_s": s.get("wall_seconds"),
                                    "gpu_hours": s.get("gpu_hours"), "stages": st, "gpus": (s.get("machine") or {}).get("gpus"),
                                    "driver_cuda": (s.get("machine") or {}).get("driver_cuda"),
                                    "vcpus": (s.get("machine") or {}).get("vcpus"), "errors": s.get("errors"),
                                    "torch": s.get("torch"), "venv_python": s.get("venv_python"),
                                    "lock_mismatches": s.get("lock_mismatches")})
            if st.get("train") and st.get("machine"):
                setup.append((dt.datetime.strptime(st["train"], F) - dt.datetime.strptime(st["machine"], F)).total_seconds())
    setup_s = (max(setup) if setup else 300.0) + a.preprocess_s
    slow = max(v["projection"]["epoch_s_projected"] for v in res["arms"].values())
    res.update({"setup_s_assumed": setup_s, "side_by_side_epoch_s": slow, "plan": plan(slow, setup_s, a.quota_left_h)})
    res["pass"] = all(all(v for k, v in arm["checks"].items() if k != "resumed_kind") for arm in res["arms"].values())
    print(json.dumps(res, indent=1, default=str))
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
