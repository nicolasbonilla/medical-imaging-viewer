# Skull-removal worker: CPU only, kept small on purpose (the registry is free up to 0.5 GB).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install nipreps-synthstrip nibabel numpy scipy fastapi "uvicorn[standard]"

# SynthStrip weights (MIT or CC BY 4.0), pinned by hash.
ADD https://surfer.nmr.mgh.harvard.edu/docs/synthstrip/requirements/synthstrip.1.pt /models/synthstrip.1.pt
RUN echo "37417f802196186441aae3e7f385d94f8a98c64a88acaeaa2723af995c653e33  /models/synthstrip.1.pt" | sha256sum -c -

WORKDIR /app
COPY server.py .
CMD exec uvicorn server:app --host 0.0.0.0 --port ${PORT:-8080}
