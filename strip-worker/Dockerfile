# Skull-removal worker: CPU only, kept small on purpose (the registry is free up to 0.5 GB).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu && \
    pip install nipreps-synthstrip==0.0.1 nibabel==5.4.2 numpy==2.4.6 scipy==1.17.1 fastapi==0.162.0 "uvicorn[standard]==0.30.6"

# SynthStrip weights, with the fluid (MIT or CC BY 4.0 as the FreeSurfer page states), pinned by hash.
ADD https://surfer.nmr.mgh.harvard.edu/docs/synthstrip/requirements/synthstrip.1.pt /models/synthstrip.1.pt
RUN echo "37417f802196186441aae3e7f385d94f8a98c64a88acaeaa2723af995c653e33  /models/synthstrip.1.pt" | sha256sum -c -

WORKDIR /app
COPY server.py .
CMD exec uvicorn server:app --host 0.0.0.0 --port ${PORT:-8080}
