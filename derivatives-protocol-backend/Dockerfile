FROM python:3.11-slim

# ======================
# System setup
# ======================
WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# ======================
# Install uv
# ======================
RUN pip install --no-cache-dir uv

# ======================
# Copy dependency files
# ======================
COPY pyproject.toml uv.lock ./

# ======================
# Install dependencies
# ======================
RUN uv sync --frozen --no-dev

# ======================
# Copy application code
# ======================
COPY app ./app

# ======================
# Runtime setup
# ======================
RUN mkdir -p logs

EXPOSE 8000

# ======================
# Healthcheck
# ======================
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/ping || exit 1

# ======================
# Run application
# ======================

# Run application
CMD ["uv", "run", "-m", "app.main"]