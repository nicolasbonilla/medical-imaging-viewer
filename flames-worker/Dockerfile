# FLAMeS MS-lesion segmentation worker — Cloud Run GPU (NVIDIA L4) sidecar.
# nnU-Net v2 (Dataset004_WML, FLAMeS weights, CC-BY-4.0) + SynthStrip skull-strip,
# behind a small FastAPI service. Weights are BAKED so cold starts don't pull 2.4 GB.

# --- SynthStrip binary + model from the official FreeSurfer image (multi-stage) ---
FROM freesurfer/synthstrip:latest AS synthstrip

# --- Runtime: CUDA + PyTorch ---
FROM pytorch/pytorch:2.4.1-cuda12.1-cudnn9-runtime

ENV DEBIAN_FRONTEND=noninteractive \
    nnUNet_results=/weights \
    nnUNet_raw=/tmp/nnraw \
    nnUNet_preprocessed=/tmp/nnprep \
    FLAMES_DEVICE=cuda \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl unzip ca-certificates python3-pip && \
    rm -rf /var/lib/apt/lists/*

# nnU-Net v2 + inference/serving deps (torch already in the base image)
RUN pip install --no-cache-dir \
        nnunetv2==2.5.1 nibabel==5.2.1 SimpleITK \
        fastapi==0.115.0 "uvicorn[standard]==0.30.6" pydantic==2.9.2 \
        google-cloud-storage==2.18.2 surfa

# SynthStrip: bring in the mri_synthstrip entrypoint + its baked model weights.
COPY --from=synthstrip /freesurfer /freesurfer
ENV FREESURFER_HOME=/freesurfer PATH="/freesurfer:${PATH}"

# --- Bake the FLAMeS weights (Zenodo record 17955359 -> $nnUNet_results/Dataset004_WML) ---
RUN mkdir -p /weights && cd /tmp && \
    ZIP_URL=$(curl -sSL "https://zenodo.org/api/records/17955359" \
      | python3 -c "import sys,json;\
d=json.load(sys.stdin);\
c=[f for f in d.get('files',[]) if str(f.get('key','')).endswith('.zip')];\
print((c[0] if c else d['files'][0])['links']['self'])") && \
    echo "downloading FLAMeS weights: $ZIP_URL" && \
    curl -sSL -o w.zip "$ZIP_URL" && unzip -q w.zip -d /weights && rm w.zip && \
    ls -la /weights

WORKDIR /app
COPY server.py /app/server.py

# Cloud Run provides $PORT (default 8080).
ENV PORT=8080
CMD exec uvicorn server:app --host 0.0.0.0 --port ${PORT} --workers 1 --timeout-keep-alive 600
