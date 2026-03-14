FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# mindGlide requires MONAI + PyTorch + nibabel
RUN pip install --no-cache-dir \
    flask==3.1.0 \
    nibabel>=5.0.0 \
    numpy>=1.24.0 \
    torch>=2.0.0 --index-url https://download.pytorch.org/whl/cpu

# Install MONAI (required by mindGlide DynUNet)
RUN pip install --no-cache-dir monai>=1.3.0

# Install mindGlide (MS-PINPOINT, Nature Communications 2025)
# Note: For production, pin to a specific release tag
RUN pip install --no-cache-dir mindglide || echo "mindGlide pip install may require manual setup from GitHub"

COPY server.py /app/server.py

EXPOSE 5002

CMD ["python", "/app/server.py"]
