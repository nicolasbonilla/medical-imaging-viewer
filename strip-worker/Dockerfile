# Skull-removal worker: CPU only, kept small on purpose (the registry is free up to 0.5 GB).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install nipreps-synthstrip nibabel numpy scipy fastapi "uvicorn[standard]"

# SynthStrip weights without cerebrospinal fluid (MIT or CC BY 4.0), pinned by hash.
ADD https://surfer.nmr.mgh.harvard.edu/docs/synthstrip/requirements/synthstrip.nocsf.1.pt /models/synthstrip.nocsf.1.pt
RUN echo "62bf01137c45b5f0cc04d59dbaed5b9ac138b3f25b766c062a7c1a0d696ecb28  /models/synthstrip.nocsf.1.pt" | sha256sum -c -

WORKDIR /app
COPY server.py .
CMD exec uvicorn server:app --host 0.0.0.0 --port ${PORT:-8080}
