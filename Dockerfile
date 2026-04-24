# ── Build stage ──────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Install deps into an isolated prefix so we can copy only what's needed
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Non-root user created before any file copies
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Copy installed packages from build stage
COPY --from=builder /install /usr/local

# Copy only application source — not .env, __pycache__, tests, etc.
COPY --chown=appuser:appuser src/ ./src/

USER appuser

EXPOSE 8001


CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "2"]
