# FLAMeS-thick GPU training image (research, not the medical device).
# Build context = the folder written by research/flames_thick/make_build_context.py (only this
# package + the lock; nothing else from the repository). Proposed Artifact Registry repository:
#   us-central1-docker.pkg.dev/mstool-research/mstool-research-images/flames-thick:<git-sha>
# Ubuntu 22.04 gives Python 3.10.12, the interpreter of the v2 FLAMeS CPU jobs whose lock is reused.
# torch 2.14.1+cu126 brings its own CUDA 12.6 / cuDNN libraries (nvidia-*-cu12 wheels); the host
# only needs an NVIDIA driver >= 525 (Vertex AI GPU nodes). cu126 builds cover sm_70 (V100),
# sm_75 (T4) and sm_80 (A100); the job self-tests the GPU before any work.
FROM ubuntu:22.04@sha256:0a9887931b0e38af2e3487ed39e29436b0535c4f3f52e57745baaf79d1898956

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    NVIDIA_VISIBLE_DEVICES=all NVIDIA_DRIVER_CAPABILITIES=compute,utility
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3.10 python3.10-venv python3-pip ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements-gpu.lock /opt/requirements-gpu.lock
RUN python3.10 -m venv /opt/venv \
 && /opt/venv/bin/pip install "pip==25.2" \
 && /opt/venv/bin/pip install -r /opt/requirements-gpu.lock --extra-index-url https://download.pytorch.org/whl/cu126 \
 && /opt/venv/bin/pip freeze > /opt/pip-freeze.txt \
 && /opt/venv/bin/pip install "pytest==8.4.2" \
 && /opt/venv/bin/python -c "import torch, nnunetv2, batchgeneratorsv2, google.cloud.storage; \
print('torch', torch.__version__, 'cuda', torch.version.cuda, 'arch', torch.cuda.get_arch_list())"

COPY flames_thick /opt/mstool/flames_thick
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/opt/mstool \
    nnUNet_extTrainer=/opt/mstool/flames_thick/nnunet_ext \
    nnUNet_compile=f \
    FT_WORKDIR=/w
RUN mkdir -p /w && python -c "from nnunetv2.utilities.find_objects import recursive_find_trainer_class_by_name as f; \
assert f('nnUNetTrainerFLAMeSThick').THICK and not f('nnUNetTrainerFLAMeSFT').THICK; print('trainers ok')" \
 && python -m pytest -q -p no:cacheprovider /opt/mstool/flames_thick/tests/test_thick_slice.py \
      /opt/mstool/flames_thick/tests/test_data_budget.py /opt/mstool/flames_thick/tests/test_trainer.py

WORKDIR /w
ENTRYPOINT ["python", "-m", "flames_thick.vertex_entry"]
