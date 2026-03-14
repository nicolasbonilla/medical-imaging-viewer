FROM python:3.11-slim

# Install system dependencies for nibabel/numpy
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    flask==3.1.0 \
    nibabel>=5.0.0 \
    numpy>=1.24.0 \
    torch>=2.0.0 --index-url https://download.pytorch.org/whl/cpu

# Install SynthSeg (FreeSurfer standalone)
# Note: For production, use the FreeSurfer-bundled version or pip install
RUN pip install --no-cache-dir synthseg || echo "SynthSeg pip install may require manual setup"

COPY server.py /app/server.py

EXPOSE 5001

CMD ["python", "/app/server.py"]
