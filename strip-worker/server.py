"""Skull-removal worker (REQ-FUNC-115, RC-101): the FLAIR comes in, the brain goes out, on the same grid.

CPU only, scale-to-zero, private: only the main service may call it. It keeps nothing: the image lives in a temporary folder for the
length of the request, and the worker has no access to any bucket. SynthStrip's weights are MIT or CC BY 4.0 (FreeSurfer page). Its own
output fills the background with the image minimum, so the mask is applied here: the app needs an exact zero outside the brain.

    POST /strip   body: a .nii.gz      answer: the skull-stripped .nii.gz
    GET  /health
"""
import hashlib
import os
import subprocess
import tempfile
from pathlib import Path

import nibabel as nib
import numpy as np
from fastapi import FastAPI, HTTPException, Request, Response

# The model WITH the fluid: the FLAIR contrast gate measures the bright fluid inside the brain region to refuse T2 and PD (review B1).
MODEL = os.environ.get("SYNTHSTRIP_MODEL", "/models/synthstrip.1.pt")
MAX_BYTES = 30 * 1024 * 1024
TIMEOUT_SECONDS = 150

app = FastAPI(title="MSTool skull-strip worker")


def model_hash() -> str:
    try:
        return hashlib.sha256(Path(MODEL).read_bytes()).hexdigest()[:12]
    except OSError:
        return "unknown"


@app.get("/health")
def health():
    return {"status": "ok", "model": Path(MODEL).name, "sha256": model_hash()}


def strip_file(source: Path, folder: Path) -> Path:
    mask_path, target = folder / "mask.nii.gz", folder / "brain.nii.gz"
    subprocess.run(["nipreps-synthstrip", "-i", str(source), "-o", str(folder / "filled.nii.gz"), "-m", str(mask_path), "--model", MODEL],
                   check=True, capture_output=True, timeout=TIMEOUT_SECONDS)
    image = nib.load(source)
    data = image.get_fdata(dtype=np.float32)
    if data.ndim == 4 and data.shape[3] == 1:          # a valid 3D image stored with one volume
        data = data[..., 0]
    if data.ndim != 3:
        raise ValueError("only a 3D image can be stripped")
    mask = np.squeeze(np.asarray(nib.load(mask_path).dataobj)) > 0
    if mask.shape != data.shape or not mask.any():
        raise ValueError("the brain mask does not fit the image")
    brain = np.where(mask, data, np.float32(0))        # exact zero outside, also where the input had NaN
    header = image.header.copy()
    header.set_data_shape(brain.shape)
    out = nib.Nifti1Image(brain, image.affine, header)
    out.set_data_dtype(np.float32)
    out.header.set_slope_inter(1, 0)
    nib.save(out, target)
    return target


@app.post("/strip")
async def strip(request: Request):
    body = await request.body()
    if not body or len(body) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Image missing or too large")
    with tempfile.TemporaryDirectory() as name:
        folder = Path(name)
        source = folder / "flair.nii.gz"
        source.write_bytes(body)
        try:
            target = strip_file(source, folder)
        except (subprocess.SubprocessError, ValueError, OSError, nib.filebasedimages.ImageFileError) as error:
            raise HTTPException(status_code=422, detail=f"The skull could not be removed ({type(error).__name__})")
        return Response(content=target.read_bytes(), media_type="application/gzip", headers={"X-Strip-Model": model_hash()})
