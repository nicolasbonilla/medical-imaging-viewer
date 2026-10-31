"""Registration level G1 for paper D: LST-AI's own atlas registration, reproduced.

LST-AI v1.2.0 (annotate.py) registers its atlas T1 to the patient T1 with greedy and warps the
MSMask with label interpolation:

    greedy -d 3 -m WNCC 2x2x2 -sv -n 100x50x10 -i <t1> <atlas_t1> -o <warp> -threads N
    greedy -d 3 -rf <t1> -ri LABEL 0.2vox -rm <msmask> <msmask_warped> -r <warp> -threads N

We run exactly these two commands (picsl_greedy 1.4.0.3, the Python build of greedy) for every
scan, and additionally warp the third-ventricle-split atlas (atlas.split_third_ventricle) so the
lateral-ventricle variants exist at G1 too. The warp field is deleted afterwards; only the warped
label maps (~0.3 MB each) and a QC/timing record are kept in data/cache/paper-d/warped/.

Research tool only: greedy is not part of the device. Run with the backend venv; greedy itself runs
in a separate venv given by --greedy-python (pip install picsl_greedy==1.4.0.3 nibabel).

    python research/paper_d/register_atlas_greedy.py --data-root <main checkout>/data \
        --greedy-python <venv>/Scripts/python.exe --workers 3 --threads 5
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import nibabel as nib  # noqa: E402
import numpy as np  # noqa: E402

from research.paper_d import atlas as A  # noqa: E402
from research.paper_d.common import (ATLAS_T1_SHA256, DEVICE_MSMASK, MSMASK_SHA256, cache_dir,  # noqa: E402
                                     data_root, enumerate_scans, sha256)

GREEDY_DEFORMABLE = "-d 3 -m WNCC 2x2x2 -sv -n 100x50x10 -i t1.nii.gz {atlas_t1} -o warp.nii.gz -threads {threads}"
GREEDY_RESLICE = "-d 3 -rf t1.nii.gz -ri LABEL 0.2vox -rm {mask} {out} -r warp.nii.gz -threads {threads}"


def prepare_atlas(cache: Path) -> dict:
    adir = cache / "atlas"
    t1 = adir / "sub-mni152_space-mni_t1.nii.gz"
    if sha256(DEVICE_MSMASK) != MSMASK_SHA256:
        raise RuntimeError("device MSMask hash differs from the LST-AI release")
    if not t1.exists() or sha256(t1) != ATLAS_T1_SHA256:
        raise RuntimeError(f"{t1} missing or hash differs (extract atlas/ from LST-AI v1.1.0 lst_data.zip)")
    shutil.copyfile(DEVICE_MSMASK, adir / "msmask.nii.gz")
    labels, aff = A.load_labels(DEVICE_MSMASK)
    split, info = A.split_third_ventricle(labels, aff)
    nib.save(nib.Nifti1Image(split.astype(np.uint8), aff), str(adir / "msmask_split3v.nii.gz"))
    return info


def run_case(scan, cache: Path, greedy_python: str, threads: int) -> dict:
    out_dir = cache / "warped"
    out_dir.mkdir(exist_ok=True)
    o1 = out_dir / f"{scan.case}_msmask.nii.gz"
    o2 = out_dir / f"{scan.case}_msmask_split3v.nii.gz"
    if o1.exists() and o2.exists():
        return {"case": scan.case, "skipped": "exists"}
    tmp = cache / "tmp" / scan.case
    tmp.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(scan.t1, tmp / "t1.nii.gz")      # greedy's parser cannot take paths with spaces
    code = (
        "from picsl_greedy import Greedy3D\n"
        "g = Greedy3D()\n"
        f"g.execute({GREEDY_DEFORMABLE.format(atlas_t1='../../atlas/sub-mni152_space-mni_t1.nii.gz', threads=threads)!r})\n"
        f"g.execute({GREEDY_RESLICE.format(mask='../../atlas/msmask.nii.gz', out='w_msmask.nii.gz', threads=threads)!r})\n"
        f"g.execute({GREEDY_RESLICE.format(mask='../../atlas/msmask_split3v.nii.gz', out='w_split.nii.gz', threads=threads)!r})\n"
    )
    t0 = time.time()
    with open(tmp / "greedy.log", "w") as log:
        r = subprocess.run([greedy_python, "-c", code], cwd=tmp, stdout=log, stderr=subprocess.STDOUT)
    secs = time.time() - t0
    if r.returncode != 0 or not (tmp / "w_msmask.nii.gz").exists():
        return {"case": scan.case, "error": f"greedy exit {r.returncode}", "log": str(tmp / 'greedy.log')}
    t1 = nib.load(str(tmp / "t1.nii.gz"))
    for src, dst in (("w_msmask.nii.gz", o1), ("w_split.nii.gz", o2)):
        w = np.asarray(nib.load(str(tmp / src)).dataobj).astype(np.uint8)
        nib.save(nib.Nifti1Image(w, t1.affine), str(dst))
    shutil.rmtree(tmp, ignore_errors=True)
    return {"case": scan.case, "seconds": round(secs, 1)}


def qc_case(scan, cache: Path) -> dict:
    """Warped atlas brain vs the scan's brain (T1 > 0) and vs the world-coordinate (G0) atlas."""
    w = np.asarray(nib.load(str(cache / "warped" / f"{scan.case}_msmask.nii.gz")).dataobj).astype(np.int16)
    ws = np.asarray(nib.load(str(cache / "warped" / f"{scan.case}_msmask_split3v.nii.gz")).dataobj).astype(np.int16)
    t1 = nib.load(scan.t1)
    labels, aff = A.load_labels(DEVICE_MSMASK)
    g0 = A.resample_nearest(labels, aff, t1.shape, t1.affine)
    brain = np.asarray(t1.dataobj) > 0

    def dice(a, b):
        return float(2 * (a & b).sum() / max(a.sum() + b.sum(), 1))
    return {
        "dice_brain_warped_vs_t1": dice(w > 0, brain),
        "dice_brain_g0_vs_t1": dice(g0 > 0, brain),
        "dice_ventricles_warped_vs_g0": dice(w == 4, g0 == 4),
        "ventricle_ml_warped": float((w == 4).sum() / 1000.0),
        "ventricle_ml_g0": float((g0 == 4).sum() / 1000.0),
        "split_union_equals_original": float(np.mean(((ws == 4) | (ws == 6)) == (w == 4))),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root")
    ap.add_argument("--greedy-python", required=True)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--threads", type=int, default=5)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    root = data_root(args.data_root)
    cache = cache_dir(root)
    info = prepare_atlas(cache)
    scans = enumerate_scans(root, include_contaminated=True)
    if args.limit:
        scans = scans[: args.limit]
    ver = subprocess.run([args.greedy_python, "-c", "import importlib.metadata as m; print(m.version('picsl_greedy'))"],
                         capture_output=True, text=True).stdout.strip()
    record = {"tool": f"picsl_greedy {ver}", "deformable": GREEDY_DEFORMABLE, "reslice": GREEDY_RESLICE,
              "atlas_t1_sha256": ATLAS_T1_SHA256, "msmask_sha256": MSMASK_SHA256,
              "third_ventricle_split": info, "workers": args.workers, "threads": args.threads}
    rec_path = cache / "warped" / "registration_record.json"
    (cache / "warped").mkdir(exist_ok=True)
    timing = {}
    if rec_path.exists():
        timing = json.loads(rec_path.read_text()).get("timing", {})
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(run_case, s, cache, args.greedy_python, args.threads): s for s in scans}
        for i, f in enumerate(as_completed(futs), 1):
            res = f.result()
            if "seconds" in res:
                timing[res["case"]] = res["seconds"]
            print(f"[{i}/{len(scans)}] {json.dumps(res)}", flush=True)
            record["timing"] = timing
            rec_path.write_text(json.dumps(record, indent=1))
    record["qc"] = {s.case: qc_case(s, cache) for s in scans
                    if (cache / "warped" / f"{s.case}_msmask_split3v.nii.gz").exists()}
    record["missing"] = [s.case for s in scans if s.case not in record["qc"]]
    rec_path.write_text(json.dumps(record, indent=1))
    print(f"done: {len(record['qc'])} registered; missing {record['missing']}", flush=True)


if __name__ == "__main__":
    main()
