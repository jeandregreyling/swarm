# Dockerfile — SWARM production image
# ═══════════════════════════════════════════════════════════════════════════════
# Build:  docker build -t swarm:latest .
# Run:    docker run -p 5050:5050 -v swarm-data:/app/data swarm:latest
# ═══════════════════════════════════════════════════════════════════════════════
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV SWARM_ROOT=/app
ENV SWARM_ENV=prod
ENV PORT=5050
ENV SWARM_DB_PATH=/app/data/swarm_memory.db
ENV SWARM_MEMORY_DB=/app/data/swarm_memory.db

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    sqlite3 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer caching)
COPY requirements.txt requirements-lock.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements-lock.txt 2>/dev/null || \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Ensure scripts are executable
RUN chmod +x bootstrap.sh killswitch.sh

# Create non-root user
RUN mkdir -p /app/data && useradd -m -u 1000 swarm && chown -R swarm:swarm /app

USER swarm

EXPOSE 5050

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:5050/api/health || exit 1

CMD ["python", "frontend/terminal.py"]
