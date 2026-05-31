# Multi-stage Dockerfile for Estate Value Index
# Combines Next.js frontend + FastAPI backend in a single container
# Optimized for Cloud Run deployment with minimal cost

# ============================================================================
# Stage 1: Build Next.js frontend
# ============================================================================
FROM node:20-slim AS web-builder

WORKDIR /app/web

# Copy package files
COPY web/package*.json ./

# Install dependencies (including devDependencies needed for build)
RUN npm ci

# Copy web source
COPY web/ ./

# Build Next.js app
RUN npm run build

# ============================================================================
# Stage 2: Python dependencies
# ============================================================================
FROM python:3.11-slim AS python-deps

WORKDIR /app

# Install system dependencies (including libgomp for LightGBM) and uv
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libgomp1 \
    curl \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.local/bin:$PATH"

# Copy project files for uv
COPY pyproject.toml uv.lock ./
COPY src/ src/

# Install Python packages with uv to system Python (faster than pip)
# [ml] extras include lightgbm, xgboost, optuna — required for model loading at runtime
RUN uv pip install --system ".[ml]"

# ============================================================================
# Stage 3: Final production image
# ============================================================================
FROM python:3.11-slim

WORKDIR /app

# Install Node.js, gsutil, and runtime dependencies (including libgomp for LightGBM)
# IMPORTANT: libgomp1 is required for LightGBM model loading
# IMPORTANT: gsutil is required for downloading models from GCS at startup
RUN apt-get update && apt-get install -y \
    curl \
    supervisor \
    libgomp1 \
    apt-transport-https \
    ca-certificates \
    gnupg \
    && curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list \
    && apt-get update && apt-get install -y google-cloud-cli \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies from stage 2
COPY --from=python-deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=python-deps /usr/local/bin /usr/local/bin

# Copy web build from stage 1
COPY --from=web-builder /app/web/.next /app/web/.next
COPY --from=web-builder /app/web/node_modules /app/web/node_modules
COPY --from=web-builder /app/web/public /app/web/public
COPY --from=web-builder /app/web/package.json /app/web/

# Copy Python application code (new package structure)
COPY src/ /app/src/
COPY api_server.py /app/
COPY pyproject.toml /app/
# Note: Package is already installed in python-deps stage via uv

# Copy startup script
COPY scripts/startup.sh /app/startup.sh
RUN chmod +x /app/startup.sh

# Copy web source for API routes
COPY web/src/ /app/web/src/
COPY web/next.config.ts /app/web/
COPY web/tsconfig.json /app/web/
COPY web/tailwind.config.ts /app/web/
COPY web/postcss.config.mjs /app/web/

# Create directories for models and data (data loaded from GCS at runtime)
RUN mkdir -p /app/web/models /app/data/enrichment

# Create supervisor configuration
RUN mkdir -p /var/log/supervisor && \
    echo '[supervisord]' > /etc/supervisor/conf.d/supervisord.conf && \
    echo 'nodaemon=true' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'logfile=/var/log/supervisor/supervisord.log' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'pidfile=/var/run/supervisord.pid' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo '' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo '[program:nextjs]' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'command=npm start' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'directory=/app/web' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'autostart=true' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'autorestart=true' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'stdout_logfile=/dev/stdout' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'stdout_logfile_maxbytes=0' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'stderr_logfile=/dev/stderr' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'stderr_logfile_maxbytes=0' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'environment=PORT=8080,NODE_ENV=production,PREDICTION_API_URL=http://127.0.0.1:8000' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo '' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo '[program:fastapi]' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'command=uvicorn api_server:app --host 0.0.0.0 --port 8000 --workers 1' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'directory=/app' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'autostart=true' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'autorestart=true' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'stdout_logfile=/dev/stdout' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'stdout_logfile_maxbytes=0' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'stderr_logfile=/dev/stderr' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'stderr_logfile_maxbytes=0' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'environment=PYTHONPATH=/app' >> /etc/supervisor/conf.d/supervisord.conf

# Environment variables
ENV PORT=8080
ENV NODE_ENV=production
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Expose port 8080 (Cloud Run expects this port)
EXPOSE 8080

# Health check - uses composite endpoint that verifies both Next.js and FastAPI
# Increased start-period to 240s to allow supervisor to start both services
HEALTHCHECK --interval=30s --timeout=10s --start-period=240s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

# Start with startup script (downloads models from GCS, then starts supervisor)
CMD ["/app/startup.sh"]
