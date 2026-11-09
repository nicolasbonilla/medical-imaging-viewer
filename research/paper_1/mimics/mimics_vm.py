"""Paper 1 addendum: the job a Spot VM runs (research/cloud/vm_mimics.sh), project mstool-research only.

Reads a plan (mimics/plans/<vm>.json, written by launch_mimics.py):
  {"prep":  [{"kind": "hdbet", "block": "A", "cohort": "wmh2017", "ids": [...], "finalize": [all ids of A]},
             {"kind": "simulate", "block": "C1", "cases": [...], "thicknesses": [3, 5, 7], "one_mm": [...],
              "finalize": [...]}, ...],
   "steps": [{"tools": ["flames", "lstai", "mindglide"], "inputs": [...], "wait_blocks": ["A"]}, ...],
   "idle_wait_h": 6}
Prep runs first (mimics_prep.py). Each step waits for the completion markers of its blocks (polling every 5 min,
at most idle_wait_h hours, then the step is skipped and logged), stages its inputs from the bucket into one flat
folder ({id}_FLAIR.nii.gz, and {id}_T1.nii.gz when LST-AI runs), checks every SHA-256 against the merged prep
records, and calls the unchanged drivers with outputs under mimics/:
  flames    flames_ensemble_driver.py  -> mimics/flames/cohort/{id}_f{0..4}_prob.nii.gz
  lstai     lstai_driver.py (flat)     -> mimics/lstai/cohort/{id}_lstai_prob.nii.gz
  mindglide / wmhsynthseg / samseg  toolbench_driver.py (flat, --log-outcomes 0) -> mimics/toolbench/cohort/{id}_{tool}_seg.nii.gz
Every driver is resumable; nothing is recomputed. No outcome is printed (PREREG section 15.5).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mimics_prep as MP  # noqa: E402

TB_TOOLS = ("wmhsynthseg", "mindglide", "samseg")


def wait_for(bucket, blocks, idle_h, poll_s=300):
    t0 = time.time()
    while True:
        missing = [b for b in blocks if not bucket.blob(f"{MP.INPUTS}/_done_{b}.json").exists()]
        if not missing:
            return True
        if time.time() - t0 > idle_h * 3600:
            print(f"WAIT LIMIT: blocks {missing} not complete after {idle_h} h; step skipped", flush=True)
            return False
        print(f"waiting for blocks {missing} ({(time.time() - t0) / 60:.0f} min)", flush=True)
        time.sleep(poll_s)


def stage(bucket, recs, ids, flat, with_t1, jc):
    """Download each input (and its T1 if needed) into the flat folder; SHA-256 must equal the prep record."""
    ok, problems = [], []
    for iid in ids:
        r = recs.get(iid)
        if r is None:
            problems.append({"input": iid, "reason": "no prep record"})
            continue
        fl = os.path.join(flat, f"{iid}_FLAIR.nii.gz")
        try:
            if not os.path.exists(fl) or jc.sha256(fl) != r["flair_sha256"]:
                bucket.blob(r["flair"]).download_to_filename(fl)
            if jc.sha256(fl) != r["flair_sha256"]:
                raise ValueError("FLAIR SHA-256 differs from the prep record")
            if with_t1 and r.get("t1"):
                t1 = os.path.join(flat, f"{iid}_T1.nii.gz")
                if not os.path.exists(t1):
                    bucket.blob(r["t1"]).download_to_filename(t1)
                if r.get("t1_sha256") and jc.sha256(t1) != r["t1_sha256"]:
                    raise ValueError("T1 SHA-256 differs from the prep record")
            ok.append(iid)
        except Exception as exc:
            problems.append({"input": iid, "reason": repr(exc)[:300]})
    return ok, problems


def run(cmd):
    print("RUN", " ".join(cmd)[:600], flush=True)
    r = subprocess.run(cmd)
    print(f"EXIT {r.returncode}", flush=True)
    return r.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--work", default="/w")
    ap.add_argument("--code", default="/w/code")
    ap.add_argument("--sets", required=True, help="analysis_sets.json")
    ap.add_argument("--data", default="/w/data", help="extracted paper F archives (simulate only)")
    ap.add_argument("--flames-inputs", default="")
    ap.add_argument("--controls-inputs", default="")
    ap.add_argument("--lstai-image-ref", default="")
    ap.add_argument("--mg-image-ref", default="")
    ap.add_argument("--fs-image-ref", default="")
    ap.add_argument("--fs-license", default="")
    ap.add_argument("--wmh-model", default="")
    a = ap.parse_args()

    from google.cloud import storage
    sys.path.insert(0, a.code)
    import job_common as jc
    bucket = storage.Client().bucket(a.bucket)
    plan = json.load(open(a.plan))
    sets = json.load(open(a.sets))
    prep = MP.Prep(bucket, a.run_id, os.path.join(a.work, "prep"), sets)

    # ------------------------------------------------------------------ preparation
    for p in plan.get("prep", []):
        if p["kind"] == "hdbet":
            prep.prep_native(p["block"], p["cohort"], p["ids"])
        elif p["kind"] == "simulate":
            sources, t1s, t1refs = {}, {}, {}
            if p["block"] == "C1":
                import lstai_driver as LD
                import toolbench_driver as TD
                exp = json.load(open(a.flames_inputs))
                roots = {"mslesseg": os.path.join(a.data, "mslesseg"),
                         "openms": os.path.join(a.data, "open_ms_data", "cross_sectional", "MNI")}
                cands = TD.enumerate_cases(roots, ["mslesseg", "openms"])
                lcands = LD.enumerate_candidates(roots, ["mslesseg", "openms"])
                for c in p["cases"]:
                    if c not in cands or jc.sha256(cands[c]["flair"]) != exp[c]["flair_sha256"]:
                        prep.errors.append({"input": c, "block": "C1", "error": "1-mm FLAIR missing or not the FLAMeS input"})
                        continue
                    sources[c] = cands[c]["flair"]
                    t1s[c] = (lcands.get(c) or {}).get("t1")
            else:
                exp = json.load(open(a.controls_inputs))
                src = os.path.join(a.work, "c2src")
                os.makedirs(src, exist_ok=True)
                for c in p["cases"]:
                    f = os.path.join(src, f"{c}_FLAIR.nii.gz")
                    bucket.blob(f"controls/sibbms/{c}_FLAIR.nii.gz").download_to_filename(f)
                    if jc.sha256(f) != exp[c]["flair_sha256"]:
                        prep.errors.append({"input": c, "block": "C2", "error": "FLAIR differs from the healthy-arm input"})
                        continue
                    sources[c] = f
                    t1b = bucket.blob(f"controls/sibbms/{c}_T1.nii.gz")
                    t1l = os.path.join(src, f"{c}_T1.nii.gz")
                    t1b.download_to_filename(t1l)
                    t1refs[c] = (f"controls/sibbms/{c}_T1.nii.gz", jc.sha256(t1l))
                    os.remove(t1l)
            prep.simulate(p["block"], sources, p["thicknesses"], p.get("one_mm", []), t1s, t1refs)
        if p.get("finalize"):
            MP.finalize(bucket, p["block"], p["finalize"], prep.work)
    prep.done()
    print(f"PREP DONE {len(prep.records)} records, {len(prep.errors)} errors", flush=True)

    # ------------------------------------------------------------------ tools
    flat = os.path.join(a.work, "flat")
    os.makedirs(flat, exist_ok=True)
    for k, step in enumerate(plan.get("steps", [])):
        if step.get("wait_blocks") and not wait_for(bucket, step["wait_blocks"], plan.get("idle_wait_h", 6)):
            continue
        recs = MP.merged_records(bucket)
        tools = step["tools"]
        ids, problems = stage(bucket, recs, step["inputs"], flat, "lstai" in tools, jc)
        print(f"[step {k}] tools {tools}: {len(ids)} inputs staged, {len(problems)} problems {problems[:5]}", flush=True)
        if not ids:
            continue
        exp_path = os.path.join(a.work, f"expected_s{k}.json")
        json.dump({i: {"flair_sha256": recs[i]["flair_sha256"], "shape": recs[i]["shape"], "affine": recs[i]["affine"]}
                   for i in ids}, open(exp_path, "w"), indent=1)
        rid = f"{a.run_id}-s{k}"
        py = sys.executable
        if "flames" in tools:
            cj = os.path.join(a.work, f"cases_s{k}.json")
            json.dump({i: {"flair": os.path.join(flat, f"{i}_FLAIR.nii.gz")} for i in ids}, open(cj, "w"), indent=1)
            run([py, os.path.join(a.code, "flames_ensemble_driver.py"), "--cases", cj, "--folds", "0", "1", "2", "3", "4",
                 "--bucket", a.bucket, "--prefix", f"{MP.PREFIX}/flames", "--run-id", rid])
        if "lstai" in tools:
            run([py, os.path.join(a.code, "lstai_driver.py"), "--bucket", a.bucket, "--prefix", f"{MP.PREFIX}/lstai",
                 "--run-id", rid, "--datasets", "flat", "--roots", f"flat={flat}", "--cases", " ".join(ids),
                 "--image", "lstai:v1.2.0", "--image-ref", a.lstai_image_ref, "--segment-only", "1",
                 "--work", os.path.join(a.work, "run_lstai")])
        tb = [t for t in TB_TOOLS if t in tools]
        if tb:
            cmd = [py, os.path.join(a.code, "toolbench_driver.py"), "--bucket", a.bucket, "--prefix", f"{MP.PREFIX}/toolbench",
                   "--run-id", rid, "--tools", *tb, "--datasets", "flat", "--roots", f"flat={flat}", "--expected", exp_path,
                   "--cases", " ".join(ids), "--images", "mindglide=mindglide:bench", "fs=freesurfer:bench",
                   "--image-refs", f"mindglide={a.mg_image_ref}", f"fs={a.fs_image_ref}", "--log-outcomes", "0",
                   "--work", os.path.join(a.work, "run_tb")]
            if a.fs_license:
                cmd += ["--fs-license", a.fs_license]
            if a.wmh_model:
                cmd += ["--wmh-model", a.wmh_model]
            run(cmd)
        for i in ids:                                   # keep the disk small: inputs of finished steps go
            for suf in ("_FLAIR.nii.gz", "_T1.nii.gz"):
                p = os.path.join(flat, i + suf)
                if os.path.exists(p) and not any(i in s["inputs"] for s in plan["steps"][k + 1:]):
                    os.remove(p)
    print("MIMICS JOB DONE", flush=True)


if __name__ == "__main__":
    main()
