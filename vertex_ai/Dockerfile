# Vertex AI training container for LightGBM model
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Install system dependencies required for LightGBM, scientific Python, and uv
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    curl \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Copy project files for uv
COPY pyproject.toml uv.lock ./
COPY src/ src/
COPY train_model.py train_model.py

# Install Python dependencies with uv (faster than pip)
# Uses ml and vertex extras for training environment
RUN uv pip install --system ".[ml,vertex]"

# Default environment configuration (can be overridden in the job spec)
ENV GCS_ENABLED=true \
    GCP_REGION=europe-north1

# The entrypoint runs the training script; pass additional args via Vertex AI job spec
ENTRYPOINT ["python", "train_model.py"]
CMD ["--data-source", "bigquery", "--use-features"]
