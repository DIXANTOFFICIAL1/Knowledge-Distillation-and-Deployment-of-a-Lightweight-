# Multi-stage optimized Dockerfile for Command Parsing Inference Microservice
# Uses CPU-only PyTorch to ensure image size is strictly below 2 GB.
FROM python:3.10-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install PyTorch CPU first to prevent pulling heavy CUDA wheels
RUN pip install --no-cache-dir torch==2.2.2+cpu --extra-index-url https://download.pytorch.org/whl/cpu

# Copy requirements and install pinned dependencies
COPY service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code and schema (NO MODEL WEIGHTS INCLUDED)
COPY service/app.py /app/app.py
COPY data/schema.json /app/data/schema.json

# Create non-root user for security best practices
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/model && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Default environment variables
ENV MODEL_URI="models/v1" \
    MODEL_VERSION="v1" \
    S3_ENDPOINT="http://seaweedfs-s3.data.svc.cluster.local:8333" \
    MAX_NEW_TOKENS="64" \
    FAULT_INJECT="0"

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
