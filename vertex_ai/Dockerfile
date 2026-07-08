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

# Runtime reference data and feature-selection config the trainer reads from the
# working directory (/app). Without these, market features fall back to zeros and
# market-index normalization fails with "At least one positive market index".
COPY config/ config/
COPY data/reference/ data/reference/

# Install exact locked versions from uv.lock.
RUN uv export --frozen --no-dev --no-hashes --extra ml --extra monitoring --extra vertex --extra geo --no-emit-project \
        --format requirements-txt -o /tmp/requirements.txt \
    && uv pip install --system -r /tmp/requirements.txt \
    && uv pip install --system --no-deps .

# Default environment configuration (can be overridden in the job spec)
ENV GCS_ENABLED=true \
    GCP_REGION=europe-north1

# The entrypoint runs the same production trainer used for local training.
ENTRYPOINT ["python", "-m", "estate_value_index.cli", "train-production-models"]
CMD ["--data-source", "bigquery"]
