# Multi-stage build for Medical Imaging Viewer Backend
# Optimized for Google Cloud Run deployment

# Stage 1: Builder
FROM python:3.11-slim as builder

# Install system dependencies required for medical imaging libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    libgomp1 \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Pre-download nilearn atlas data at build time (avoids runtime download)
ENV PATH=/root/.local/bin:$PATH
RUN mkdir -p /app/data/nilearn_data && \
    python -c "\
from nilearn import datasets; \
d = '/app/data/nilearn_data'; \
datasets.fetch_atlas_harvard_oxford('sub-maxprob-thr25-1mm', data_dir=d); \
datasets.fetch_atlas_harvard_oxford('cort-maxprob-thr25-1mm', data_dir=d); \
print('Atlas data pre-downloaded successfully')"

# Stage 2: Runtime
FROM python:3.11-slim

# Install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security (ISO 27001 A.9.2.3)
RUN useradd -m -u 1000 appuser

# Set working directory
WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy application code
COPY . .

# Copy pre-downloaded atlas data from builder (AFTER COPY . . to avoid overwrite)
COPY --from=builder /app/data/nilearn_data /app/data/nilearn_data

# Create necessary directories including data for SecureUserStorage
RUN mkdir -p logs storage data && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Add local bin to PATH
ENV PATH=/home/appuser/.local/bin:$PATH

# Set Python to run unbuffered (good for logging in Cloud Run)
ENV PYTHONUNBUFFERED=1

# Expose port (Cloud Run uses PORT environment variable)
ENV PORT=8080
EXPOSE 8080

# Run the application using optimized startup script
# This reduces container startup time by deferring heavy library imports
# Cloud Run will inject PORT environment variable
CMD ["python", "startup.py"]
