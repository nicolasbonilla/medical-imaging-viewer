"""FLAMeS 5-fold ensemble driver — runs on a research VM (project mstool-research only).

For each requested fold, the nnU-Net predictor is loaded ONCE; then every case that is not
already in the bucket is predicted, converted to a compact uint8 NIfTI (prob = value * slope,
read back with nibabel get_fdata, max error ~0.002) and uploaded IMMEDIATELY. A crash or a
restart therefore loses at most one case, and a relaunch skips everything already uploaded.

A run manifest (JSON) records software versions, model/data checksums, per-case timings and
outcomes, so any result can be traced and reproduced.

Usage (on the VM, inside the job venv):
    python flames_ensemble_driver.py --cases /w/cases.json --folds 0 1 2 3 4 \
        --bucket mstool-research-data --prefix flames-ensemble --run-id <vm-name>
cases.json: {"<case_id>": {"flair": "/abs/flair.nii.gz", "gt": "/abs/gt.nii.gz"}, ...}

Other trained models (FLAMeS-thick evaluation, docs/research/flames-thick/PROTOCOL.md §7): repeat
`--model TAG=FOLDER` (an nnU-Net trained-model folder with fold_k/checkpoint_final.pth); outputs are
then named {case}_{TAG}_f{k}_prob.nii.gz and each manifest entry records its model. Without --model
the behaviour is unchanged (the single FLAMeS folder under $nnUNet_results, no tag).
"""
import argparse
import glob
import hashlib
import json
import os
import platform
import subprocess
import sys
import time

import nibabel as nib
import numpy as np
import torch
from google.cloud import storage


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def model_folder():
    root = os.environ["nnUNet_results"]
    hits = glob.glob(os.path.join(root, "**", "*3d_fullres*"), recursive=True)
    hits = [h for h in hits if os.path.isdir(h) and glob.glob(os.path.join(h, "fold_*"))]
    if len(hits) != 1:
        raise SystemExit(f"expected exactly one FLAMeS 3d_fullres model folder, found {hits}")
    return hits[0]


def parse_models(items):
    """['ftA=/w/models/a/...'] -> [('ftA', '/w/models/a/...')]; tags are short [A-Za-z0-9]+ words."""
    out = []
    for it in items:
        tag, _, folder = it.partition("=")
        if not tag.isalnum() or not folder:
            raise SystemExit(f"--model expects TAG=FOLDER with an alphanumeric tag, got {it!r}")
        if not glob.glob(os.path.join(folder, "fold_*", "checkpoint_final.pth")):
            raise SystemExit(f"--model {tag}: no fold_*/checkpoint_final.pth under {folder}")
        out.append((tag, folder))
    if len({t for t, _ in out}) != len(out):
        raise SystemExit("--model tags must be unique")
    return out


def out_name(cid, fold, tag=None):
    return f"{cid}_{tag}_f{fold}_prob.nii.gz" if tag else f"{cid}_f{fold}_prob.nii.gz"


def existing(bucket, prefix):
    return {os.path.basename(b.name) for b in bucket.list_blobs(prefix=f"{prefix}/cohort/")}


def save_prob(prob_zyx, flair_path, out_path):
    """Lesion probability (z,y,x as returned by nnU-Net) -> uint8-scaled NIfTI in FLAIR geometry."""
    fl = nib.load(flair_path)
    arr = np.transpose(prob_zyx.astype(np.float32), (2, 1, 0))   # (x,y,z); validated Aug 2026
    if arr.shape != fl.shape[:3]:
        raise ValueError(f"shape mismatch {arr.shape} vs {fl.shape}")
    img = nib.Nifti1Image(np.clip(arr, 0.0, 1.0), fl.affine, fl.header.copy())
    img.set_data_dtype(np.uint8)
    nib.save(img, out_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--folds", nargs="+", type=int, default=[0, 1, 2, 3, 4])
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--prefix", default="flames-ensemble")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--threads", type=int, default=os.cpu_count())
    ap.add_argument("--tta", action="store_true", help="test-time mirroring (8x slower on CPU)")
    ap.add_argument("--model", action="append", default=[], metavar="TAG=FOLDER",
                    help="extra trained-model folder(s); outputs {case}_{TAG}_f{k}_prob.nii.gz")
    args = ap.parse_args()

    torch.set_num_threads(args.threads)
    from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor
    from nnunetv2.imageio.simpleitk_reader_writer import SimpleITKIO
    import nnunetv2

    cases = json.load(open(args.cases))
    client = storage.Client()
    bucket = client.bucket(args.bucket)
    done = existing(bucket, args.prefix)
    models = parse_models(args.model) if args.model else [(None, model_folder())]
    mdir = models[0][1]
    tmp = "/w/tmp_out"
    os.makedirs(tmp, exist_ok=True)

    manifest = {
        "run_id": args.run_id, "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": platform.node(), "cpu_count": os.cpu_count(), "threads": args.threads, "tta": args.tta,
        "versions": {"python": sys.version.split()[0], "torch": torch.__version__,
                     "nnunetv2": getattr(nnunetv2, "__version__", "unknown"), "nibabel": nib.__version__,
                     "numpy": np.__version__},
        "pip_freeze": subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True).stdout.splitlines(),
        "model_folder": mdir,
        "checkpoints_sha256": {os.path.relpath(p, mdir): sha256(p)
                               for p in sorted(glob.glob(os.path.join(mdir, "fold_*", "checkpoint_final.pth")))},
        "models": {(tag or "flames"): {"folder": d, "checkpoints_sha256": {
            os.path.relpath(p, d): sha256(p) for p in sorted(glob.glob(os.path.join(d, "fold_*", "checkpoint_final.pth")))}}
            for tag, d in models},
        "inputs_sha256": {cid: sha256(c["flair"]) for cid, c in cases.items()},
        "folds": args.folds, "cases": [], "errors": [],
    }

    def flush_manifest():
        p = f"/w/manifest_{args.run_id}.json"
        json.dump(manifest, open(p, "w"), indent=1)
        bucket.blob(f"{args.prefix}/manifests/{args.run_id}.json").upload_from_filename(p)

    flush_manifest()
    reader = SimpleITKIO()
    for tag, mdir in models:
        for k in args.folds:
            todo = [cid for cid in sorted(cases) if out_name(cid, k, tag) not in done]
            print(f"[{tag or 'flames'} fold {k}] {len(todo)} cases to run, {len(cases) - len(todo)} already in the bucket",
                  flush=True)
            if not todo:
                continue
            predictor = nnUNetPredictor(tile_step_size=0.5, use_gaussian=True, use_mirroring=args.tta,
                                        perform_everything_on_device=False, device=torch.device("cpu"),
                                        verbose=False, verbose_preprocessing=False, allow_tqdm=False)
            predictor.initialize_from_trained_model_folder(mdir, use_folds=(k,), checkpoint_name="checkpoint_final.pth")
            for cid in todo:
                t0 = time.time()
                name = out_name(cid, k, tag)
                try:
                    img, props = reader.read_images([cases[cid]["flair"]])
                    _seg, prob = predictor.predict_single_npy_array(img, props, None, None, True)
                    out = os.path.join(tmp, name)
                    save_prob(prob[1], cases[cid]["flair"], out)
                    bucket.blob(f"{args.prefix}/cohort/{name}").upload_from_filename(out)
                    os.remove(out)
                    manifest["cases"].append({"case": cid, "fold": k, "model": tag or "flames",
                                              "seconds": round(time.time() - t0, 1), "ok": True})
                    print(f"[{tag or 'flames'} fold {k}] {cid} done in {time.time() - t0:.0f}s", flush=True)
                except Exception as exc:                         # record and continue; never silent
                    manifest["errors"].append({"case": cid, "fold": k, "model": tag or "flames", "error": repr(exc)[:500]})
                    print(f"[{tag or 'flames'} fold {k}] {cid} FAILED: {exc!r}", flush=True)
                if len(manifest["cases"]) % 10 == 0:
                    flush_manifest()
            flush_manifest()
    manifest["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    flush_manifest()
    print("DRIVER DONE", len(manifest["cases"]), "ok,", len(manifest["errors"]), "errors", flush=True)


if __name__ == "__main__":
    main()
