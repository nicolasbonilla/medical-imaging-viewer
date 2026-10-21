"""Stage the extra public cohorts (MS3SEG, Muslim 2022, PediMS) for the FLAMeS cloud job (v2).

build-raw  Fetch every case of the requested cohorts ONCE (streaming range reads, cohorts_extra.py)
           into OUT and write OUT/cases_extra.json with paths RELATIVE to OUT, so the folder is cached
           as a single tarball in gs://mstool-research-data/inputs/ and never fetched again.
strip      Skull-strip (HD-BET v2, CPU, no TTA) only the SELECTED cases that still have a skull.
           Brains already in gs://.../inputs/extra_stripped/ are reused; each new brain is uploaded
           there as soon as HD-BET finishes, so HD-BET runs once per case across all runs.
           Writes a {case: {"flair": brain_or_original, "gt": mask}} JSON for the case list.

    python extra_cohorts_stage.py build-raw --out /w/extra_raw --cohorts ms3seg muslim pedims
    python extra_cohorts_stage.py strip --raw /w/extra_raw --cases ms3seg_001 ... \
        --bucket-prefix gs://mstool-research-data/inputs/extra_stripped --out /w/extra_brain \
        --result /w/extra_selected.json
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cohorts_extra as cx  # noqa: E402


def build_raw(out, cohorts):
    cases = {}
    for name in cohorts:
        try:
            got = cx.FETCHERS[name](os.path.join(out, name))
        except Exception as exc:                 # one unreachable source must not kill the others
            print("FETCH FAILED", name, repr(exc), flush=True)
            continue
        print("FETCHED", name, len(got), flush=True)
        for cid, fl, gt, needs_strip in got:
            cases[cid] = {"cohort": name, "flair": os.path.relpath(fl, out), "gt": os.path.relpath(gt, out),
                          "strip": bool(needs_strip)}
    json.dump(cases, open(os.path.join(out, "cases_extra.json"), "w"), indent=1)
    print("RAW CASES", len(cases), flush=True)
    return 0 if cases else 1


def pedims_raw(out):
    """PediMS raw (defaced, not skull-stripped) FLAIR for the paper F raw-input arm, cached as one
    tarball: OUT/pedims_raw/*.nii.gz + OUT/cases_pedims_raw.json ({case: path relative to OUT})."""
    got = cx.fetch_pedims_raw(out)
    json.dump({c: os.path.relpath(p, out).replace(os.sep, "/") for c, p in got.items()},
              open(os.path.join(out, "cases_pedims_raw.json"), "w"), indent=1)
    print("PEDIMS RAW", len(got), flush=True)
    return 0 if got else 1


def gs_cp(src, dst):
    return subprocess.run(["gcloud", "storage", "cp", src, dst, "--quiet"], capture_output=True).returncode == 0


def strip(raw, selected, bucket_prefix, out, result):
    cases = json.load(open(os.path.join(raw, "cases_extra.json")))
    os.makedirs(out, exist_ok=True)
    final, todo = {}, {}
    for c in selected:
        flair, gt = os.path.join(raw, cases[c]["flair"]), os.path.join(raw, cases[c]["gt"])
        if not cases[c]["strip"]:
            final[c] = {"flair": flair, "gt": gt, "brain_source": "provided by the dataset"}
            continue
        brain = os.path.join(out, f"{c}_flair_brain.nii.gz")
        if gs_cp(f"{bucket_prefix}/{c}_flair_brain.nii.gz", brain):
            final[c] = {"flair": brain, "gt": gt, "brain_source": "HD-BET (reused from bucket)"}
        else:
            todo[c] = (flair, gt)
    if todo:
        print(f"HD-BET on {len(todo)} cases ({len(final)} reused or not needed)", flush=True)
        # One case per HD-BET call: each brain is uploaded immediately (a crash loses at most one case).
        for c, (flair, gt) in sorted(todo.items()):
            got = cx.hdbet_strip({c: flair}, os.path.join(out, "_hdbet", c), gts={c: gt}, device="cpu", tta=False)
            qc = os.path.join(out, "_hdbet", c, "hdbet_qc.json")
            if os.path.exists(qc):
                gs_cp(qc, f"{bucket_prefix}/qc/{c}_hdbet_qc.json")
            if c not in got:
                print("HD-BET FAILED -> dropped", c, flush=True)
                continue
            brain = os.path.join(out, f"{c}_flair_brain.nii.gz")
            os.replace(got[c], brain)
            gs_cp(brain, f"{bucket_prefix}/{c}_flair_brain.nii.gz")
            final[c] = {"flair": brain, "gt": gt, "brain_source": "HD-BET 2.0.1 (CPU, no TTA)"}
    json.dump(final, open(result, "w"), indent=1)
    print("EXTRA SELECTED", len(final), "of", len(selected), flush=True)
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build-raw")
    b.add_argument("--out", required=True)
    b.add_argument("--cohorts", nargs="+", default=["ms3seg", "muslim", "pedims"])
    s = sub.add_parser("strip")
    s.add_argument("--raw", required=True)
    s.add_argument("--cases", nargs="*", default=[])
    s.add_argument("--bucket-prefix", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--result", required=True)
    r = sub.add_parser("pedims-raw")
    r.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "build-raw":
        return build_raw(a.out, a.cohorts)
    if a.cmd == "pedims-raw":
        return pedims_raw(a.out)
    return strip(a.raw, a.cases, a.bucket_prefix, a.out, a.result)


if __name__ == "__main__":
    sys.exit(main())
