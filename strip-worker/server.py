"""Skull-removal worker (REQ-FUNC-115, RC-101): the FLAIR comes in, the brain goes out, on the same grid.

CPU only, scale-to-zero, private: only the main service may call it. It keeps nothing: the image lives in a temporary folder for the
length of the request, and the worker has no access to any bucket. SynthStrip's weights are MIT or CC BY 4.0 (FreeSurfer page). Its own
output fills the background with the image minimum, so the mask is applied here: the app needs an exact zero outside the brain.

    POST /strip   body: a .nii.gz      answer: the skull-stripped .nii.gz
    GET  /health
"""
import os
import subprocess
import tempfile
from pathlib import Path

import nibabel as nib
import numpy as np
from fastapi import FastAPI, HTTPException, Request, Response

MODEL = os.environ.get("SYNTHSTRIP_MODEL", "/models/synthstrip.1.pt")
MAX_BYTES = 30 * 1024 * 1024
TIMEOUT_SECONDS = 150

app = FastAPI(title="MSTool skull-strip worker")


@app.get("/health")
def health():
    return {"status": "ok", "model": Path(MODEL).name}


def strip_file(source: Path, folder: Path) -> Path:
    mask_path, target = folder / "mask.nii.gz", folder / "brain.nii.gz"
    subprocess.run(["nipreps-synthstrip", "-i", str(source), "-o", str(folder / "filled.nii.gz"), "-m", str(mask_path), "--model", MODEL],
                   check=True, capture_output=True, timeout=TIMEOUT_SECONDS)
    image = nib.load(source)
    mask = np.asarray(nib.load(mask_path).dataobj) > 0
    if mask.shape != image.shape[:3] or not mask.any():
        raise ValueError("the brain mask does not fit the image")
    brain = image.get_fdata(dtype=np.float32) * mask
    out = nib.Nifti1Image(brain, image.affine, image.header)
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
        return Response(content=target.read_bytes(), media_type="application/gzip")
