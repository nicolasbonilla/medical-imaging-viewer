"""FLAMeS MS-lesion segmentation worker (Cloud Run GPU sidecar).

The vanguard, externally-validated SOTA automatic MS-lesion segmenter: FLAMeS
(nnU-Net v2, Dataset004_WML, trainer nnUNetTrainer_8000epochs; medRxiv 2025.05.19,
J. Neuroimaging 2025 — Dice 0.74 / F1 0.78, beats SAMSEG / LST-LPA / LST-AI; weights
CC-BY-4.0, Zenodo 17955359). Single FLAIR input — the modality essentially always
acquired in MS — so it degrades gracefully where a T1 is missing.

This runs OUT of the main API service (which is cpu=1/1Gi and cannot host a 2.4 GB
nnU-Net): the main service POSTs `{input_gcs_uri, output_gcs_uri}` here, this downloads
the FLAIR from GCS, optionally skull-strips (SynthStrip), runs nnU-Net, post-processes
the lesion-probability channel to a binary mask, uploads the NIfTI to `output_gcs_uri`,
and returns. Deploy as a scale-to-zero Cloud Run GPU (L4) service.

CLASS C / INVESTIGATIONAL: this is a research-grade auto-segmenter. Its output is a
DRAFT to be reviewed, never an autonomous diagnosis; the app surfaces it as such.

Endpoints:
  GET  /health   -> readiness (weights present, device)
  POST /segment  -> {input_gcs_uri, output_gcs_uri, skull_strip?, threshold?}
"""
import os
import subprocess
import tempfile
import shutil
import logging

import numpy as np
import nibabel as nib
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from google.cloud import storage

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("flames-worker")

# nnU-Net expects these; the Dockerfile bakes the weights under /weights.
os.environ.setdefault("nnUNet_results", "/weights")
os.environ.setdefault("nnUNet_raw", "/tmp/nnraw")
os.environ.setdefault("nnUNet_preprocessed", "/tmp/nnprep")

DATASET = os.environ.get("FLAMES_DATASET", "004")
TRAINER = os.environ.get("FLAMES_TRAINER", "nnUNetTrainer_8000epochs")
CONFIG = os.environ.get("FLAMES_CONFIG", "3d_fullres")
DEVICE = os.environ.get("FLAMES_DEVICE", "cuda")   # 'cuda' on the GPU service, 'cpu' fallback
LESION_CHANNEL = 1                                  # channel 1 of the softmax = lesion prob
# (z,y,x) SimpleITK order from nnU-Net -> (x,y,z) nibabel; empirically validated in the
# research pipeline (vm-flames.sh, Dice 0.56 vs GT without this transpose).
_PROB_TRANSPOSE = (2, 1, 0)

app = FastAPI(title="FLAMeS worker", version="1.0.0")
_gcs = storage.Client()


class SegmentRequest(BaseModel):
    input_gcs_uri: str            # gs://bucket/path/flair.nii.gz
    output_gcs_uri: str           # gs://bucket/segmentations/{id}/masks.nii.gz
    skull_strip: bool = True      # run SynthStrip on raw clinical FLAIR
    threshold: float = 0.5        # binarize the lesion-probability map


def _parse_gs(uri: str):
    if not uri.startswith("gs://"):
        raise HTTPException(400, f"expected a gs:// URI, got {uri!r}")
    bucket, _, obj = uri[len("gs://"):].partition("/")
    if not bucket or not obj:
        raise HTTPException(400, f"malformed gs:// URI: {uri!r}")
    return bucket, obj


def _download(uri: str, dest: str):
    b, o = _parse_gs(uri)
    _gcs.bucket(b).blob(o).download_to_filename(dest)


def _upload(path: str, uri: str, content_type="application/gzip"):
    b, o = _parse_gs(uri)
    _gcs.bucket(b).blob(o).upload_from_filename(path, content_type=content_type)


def _run(cmd: list, what: str):
    log.info("running %s: %s", what, " ".join(cmd))
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        log.error("%s failed (%d): %s", what, p.returncode, p.stderr[-2000:])
        raise HTTPException(500, f"{what} failed: {p.stderr[-400:]}")


@app.get("/health")
def health():
    weights_ok = os.path.isdir(os.path.join(os.environ["nnUNet_results"],
                                             f"Dataset{DATASET}_WML")) or \
        any(d.startswith(f"Dataset{DATASET}") for d in
            (os.listdir(os.environ["nnUNet_results"]) if os.path.isdir(os.environ["nnUNet_results"]) else []))
    return {
        "status": "ok" if weights_ok else "degraded",
        "model": "FLAMeS",
        "dataset": DATASET, "trainer": TRAINER, "config": CONFIG,
        "device": DEVICE, "weights_present": bool(weights_ok),
    }


@app.post("/segment")
def segment(req: SegmentRequest):
    work = tempfile.mkdtemp(prefix="flames_")
    in_dir = os.path.join(work, "in"); out_dir = os.path.join(work, "out")
    os.makedirs(in_dir); os.makedirs(out_dir)
    try:
        raw = os.path.join(work, "flair.nii.gz")
        _download(req.input_gcs_uri, raw)

        # nnU-Net single-channel input naming: {case}_0000.nii.gz
        flair = os.path.join(in_dir, "case_0000.nii.gz")
        if req.skull_strip:
            # SynthStrip (FreeSurfer) — robust, contrast-agnostic brain extraction, the
            # preprocessing FLAMeS expects on raw clinical FLAIR.
            _run(["mri_synthstrip", "-i", raw, "-o", flair, "--no-csf"], "synthstrip")
        else:
            shutil.copyfile(raw, flair)

        _run([
            "nnUNetv2_predict", "-i", in_dir, "-o", out_dir,
            "-d", DATASET, "-c", CONFIG, "-tr", TRAINER,
            "-device", DEVICE, "-f", "0", "--disable_tta", "--save_probabilities",
        ], "nnUNetv2_predict")

        # Post-process: lesion-probability channel -> transpose to nibabel order ->
        # binarize. nnU-Net writes case.npz (probabilities) + case.nii.gz (argmax).
        npz = os.path.join(out_dir, "case.npz")
        if os.path.exists(npz):
            probs = np.load(npz)["probabilities"]          # (C, z, y, x)
            lesion = probs[LESION_CHANNEL].transpose(*_PROB_TRANSPOSE)
            mask = (lesion >= req.threshold).astype(np.uint8)
        else:
            seg = nib.load(os.path.join(out_dir, "case.nii.gz"))
            mask = (np.asarray(seg.get_fdata()) > 0).astype(np.uint8)

        # write NIfTI in the FLAIR's space (affine from the skull-stripped input)
        ref = nib.load(flair)
        out_img = nib.Nifti1Image(mask, ref.affine)
        out_img.header.set_data_dtype(np.uint8)
        out_path = os.path.join(work, "mask.nii.gz")
        nib.save(out_img, out_path)
        _upload(out_path, req.output_gcs_uri)

        n_vox = int(mask.sum())
        log.info("FLAMeS done: %d lesion voxels -> %s", n_vox, req.output_gcs_uri)
        return {"status": "completed", "output_gcs_uri": req.output_gcs_uri,
                "lesion_voxels": n_vox, "model": "FLAMeS", "threshold": req.threshold}
    finally:
        shutil.rmtree(work, ignore_errors=True)
