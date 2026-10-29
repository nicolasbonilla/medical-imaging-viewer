"""Paper F — LOCAL completeness and integrity check of the toolbench runs (no cloud calls).

Reads the run manifests, logs, cost files and run records downloaded read-only from the bucket, plus
the per-case outputs, and answers, per tool: was every planned (scan, tool) cell produced? do the
downloaded files have the SHA-256 the VM recorded? which cells failed, and how? It never reads an
accuracy number.

Planned cells (PROTOCOL.md 4.4 and 7.6):
  wmhsynthseg, mindglide   all 324 scans of flames_inputs.json
  mindglide-raw            the 179 thick-band scans (secondary arm 7.6)
  samseg                   tier C = plan_budget.tier_c_ids() (129 scans); any other SAMSEG output (the
                           isotropic pilot scan) is listed as "outside the tier"

    python -I research/paper_f/verify_runs.py --dl <download dir> --out <json>
<download dir> has manifests/ logs/ cost/ runs/<run>/{plan,runinfo,vm}.json and cohort/ (the outputs).
"""
import argparse
import glob
import hashlib
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import plan_budget  # noqa: E402

FS_DIGEST = "sha256:5648104ca75a24f6ee5a8786146f99b405c2bda1da12bff723a15056da8ddf6b"
MG_DIGEST = "sha256:14e88f61d6cba18322d03774b168682e255383387aaab55e6a5aa33a2dbdd971"
MG_WEIGHTS = "881e30efd9444a25ee70c01d795dd9fb21ac750a48f1ba8070fcd79fb75e76ca"
LESION_LABEL = {"samseg": 99, "wmhsynthseg": 77, "mindglide": 18}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def planned(expected):
    thick = sorted(c for c, v in expected.items() if v["band"] == "thick")
    return {"wmhsynthseg": sorted(expected), "mindglide": sorted(expected), "mindglide-raw": thick,
            "samseg": plan_budget.tier_c_ids(expected)}


def log_flags(path):
    if not os.path.exists(path):
        return {"present": False}
    txt = open(path, encoding="utf-8", errors="replace").read()
    after = [ln.split("TOOLS AFTER CHECKS", 1)[1].strip(" :") for ln in txt.splitlines() if "TOOLS AFTER CHECKS" in ln]
    done = [ln.strip() for ln in txt.splitlines() if "TOOLBENCH DONE" in ln]
    return {"present": True, "toolbench_done": done[-1] if done else None,
            "tool_dropped_lines": [ln.strip()[:200] for ln in txt.splitlines() if "TOOL DROPPED" in ln],
            "tools_after_checks": after[-1] if after else None,
            "wall_clock_guard_hit": "WALL-CLOCK GUARD HIT" in txt,
            "oom_or_killed_lines": [ln.strip()[:200] for ln in txt.splitlines()
                                    if "exit 137" in ln or "Killed" in ln or "MemoryError" in ln][:10]}


def run_summary(m, dl):
    rid = m["run_id"]
    imgs = m.get("images", {})
    rec = {"run_id": rid, "tools": m.get("tools"), "output_tags": m.get("output_tags"),
           "input_variant": m.get("input_variant"), "started_utc": m.get("started_utc"),
           "finished_utc": m.get("finished_utc"), "n_ok": sum(1 for c in m.get("cases", []) if c.get("ok")),
           "n_errors": len(m.get("errors", [])), "input_problems": m.get("input_problems", []),
           "fs_license_present": m.get("fs_license_present"), "code_sha256": m.get("code_sha256"),
           "samseg_seed": m.get("samseg_seed"), "timeout_min": m.get("timeout_min"),
           "selection_explicit": len((m.get("selection") or {}).get("explicit") or []),
           "commands": m.get("commands")}
    if "fs" in imgs:
        fs = imgs["fs"]
        rec["fs_digest_ok"] = FS_DIGEST in (fs.get("image_id", "") + " ".join(fs.get("repo_digests", [])))
        rec["fs_build"] = str(fs.get("fs_build", ""))[:200]
    if "mindglide" in imgs:
        mg = imgs["mindglide"]
        rec["mindglide_digest_ok"] = MG_DIGEST in (mg.get("image_id", "") + " ".join(mg.get("repo_digests", [])))
        rec["mindglide_weights_ok"] = MG_WEIGHTS in json.dumps(mg)
    if m.get("wmh_model"):
        rec["wmh_model"] = {k: m["wmh_model"].get(k) for k in ("bytes", "sha256")}
    secs = [c["seconds"] for c in m.get("cases", []) if c.get("ok") and c.get("seconds")]
    if secs:
        rec["seconds_per_case"] = {"median": statistics.median(secs), "min": min(secs), "max": max(secs)}
    peaks = [c.get("peak_mem_used_gb") or 0 for c in m.get("cases", []) if c.get("ok")]
    swaps = [c.get("peak_swap_used_gb") or 0 for c in m.get("cases", []) if c.get("ok")]
    if peaks:
        rec["peak_mem_gb_max"], rec["peak_swap_gb_max"] = max(peaks), max(swaps)
    rec["log"] = log_flags(os.path.join(dl, "logs", f"{rid}.log"))
    cost = os.path.join(dl, "cost", f"{rid}.txt")
    rec["cost_record"] = open(cost).read().strip() if os.path.exists(cost) else None
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dl", required=True)
    ap.add_argument("--expected", default=os.path.join(HERE, "flames_inputs.json"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    expected = json.load(open(a.expected))
    plan = planned(expected)
    manifests = [json.load(open(p)) for p in sorted(glob.glob(os.path.join(a.dl, "manifests", "*.json")))]
    manifests.sort(key=lambda m: m.get("started_utc") or "")
    cohort = os.path.join(a.dl, "cohort")
    files = set(os.listdir(cohort)) if os.path.isdir(cohort) else set()

    ok, errs, input_sha_bad, label_bad = {}, {}, [], []
    for m in manifests:
        for c in m.get("cases", []):
            if not c.get("ok"):
                continue
            key = (c["case"], c["tool"])
            ok.setdefault(key, []).append({"run": m["run_id"], "seg_sha256": c.get("seg_sha256"),
                                           "prob_sha256": c.get("prob_sha256"), "seconds": c.get("seconds"),
                                           "kind": (c.get("seg_transform") or {}).get("kind"),
                                           "lesion_voxels": c.get("lesion_voxels")})
            exp = expected.get(c["case"], {}).get("flair_sha256")
            if c.get("input_variant", "flames") == "flames" and exp and c.get("flair_sha256") != exp:
                input_sha_bad.append({"case": c["case"], "tool": c["tool"], "run": m["run_id"]})
            base = c.get("base_tool", c["tool"])
            labs = (c.get("native_seg") or {}).get("labels_found") or []
            if base in LESION_LABEL and labs and LESION_LABEL[base] not in labs and c.get("lesion_voxels", 0) > 0:
                label_bad.append({"case": c["case"], "tool": c["tool"], "run": m["run_id"]})
        for e in m.get("errors", []):
            errs.setdefault((e.get("case"), e.get("tool")), []).append(
                {"run": m["run_id"], "error": (e.get("error") or "")[:300], "seconds": e.get("seconds")})

    report = {"planned_counts": {t: len(v) for t, v in plan.items()}, "tools": {}, "runs": [],
              "input_sha256_mismatches": input_sha_bad, "lesion_label_missing": label_bad}
    for m in manifests:
        report["runs"].append(run_summary(m, a.dl))
    for tool, ids in plan.items():
        t = {"planned": len(ids), "ok": 0, "missing_output": [], "failed_never_recovered": [],
             "failed_then_recovered": [], "sha256_seg_mismatch": [], "sha256_prob_mismatch": [],
             "outputs_outside_plan": [], "ok_in_runs": {}, "transform_kinds": {}}
        for cid in ids:
            recs = ok.get((cid, tool), [])
            seg_f, prob_f = f"{cid}_{tool}_seg.nii.gz", f"{cid}_{tool}_prob.nii.gz"
            if not recs:
                (t["failed_never_recovered"] if (cid, tool) in errs else t["missing_output"]).append(
                    {"case": cid, "errors": errs.get((cid, tool), [])})
                continue
            if (cid, tool) in errs:
                t["failed_then_recovered"].append({"case": cid, "errors": errs[(cid, tool)],
                                                   "ok_runs": [r["run"] for r in recs]})
            if seg_f not in files:
                t["missing_output"].append({"case": cid, "note": "manifest ok but file not downloaded"})
                continue
            got = sha256(os.path.join(cohort, seg_f))
            match = [r for r in recs if r["seg_sha256"] == got]
            if not match:
                t["sha256_seg_mismatch"].append({"case": cid, "file": got, "manifest": [r["seg_sha256"] for r in recs]})
                continue
            r = match[-1]
            if r.get("prob_sha256"):
                gp = sha256(os.path.join(cohort, prob_f)) if prob_f in files else None
                if gp != r["prob_sha256"]:
                    t["sha256_prob_mismatch"].append({"case": cid, "file": gp, "manifest": r["prob_sha256"]})
            t["ok"] += 1
            t["ok_in_runs"][r["run"]] = t["ok_in_runs"].get(r["run"], 0) + 1
            t["transform_kinds"][r["kind"]] = t["transform_kinds"].get(r["kind"], 0) + 1
        suffix = f"_{tool}_seg.nii.gz"
        on_disk = {f[:-len(suffix)] for f in files if f.endswith(suffix)
                   and not (tool == "mindglide" and f.endswith("_mindglide-raw_seg.nii.gz"))}
        t["outputs_outside_plan"] = sorted(on_disk - set(ids))
        t["complete"] = (t["ok"] == len(ids) and not t["sha256_seg_mismatch"] and not t["sha256_prob_mismatch"])
        report["tools"][tool] = t
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(report, open(a.out, "w"), indent=1)
    for tool, t in report["tools"].items():
        print(f"{tool:14s} planned {t['planned']:3d}  ok+sha {t['ok']:3d}  missing {len(t['missing_output'])}  "
              f"failed {len(t['failed_never_recovered'])}  recovered {len(t['failed_then_recovered'])}  "
              f"sha-mismatch {len(t['sha256_seg_mismatch']) + len(t['sha256_prob_mismatch'])}  "
              f"outside-plan {t['outputs_outside_plan']}  runs {t['ok_in_runs']}")
    print("input sha256 mismatches:", len(input_sha_bad), " lesion label missing:", len(label_bad))
    for r in report["runs"]:
        lg = r["log"]
        print(f"  {r['run_id']:28s} ok {r['n_ok']:3d} err {r['n_errors']}  input_problems {len(r['input_problems'])}  "
              f"done={bool(lg.get('toolbench_done'))} dropped={len(lg.get('tool_dropped_lines', []))} "
              f"guard={lg.get('wall_clock_guard_hit')} fs_digest={r.get('fs_digest_ok')} mg_digest={r.get('mindglide_digest_ok')} "
              f"licence={r.get('fs_license_present')}")


if __name__ == "__main__":
    main()
