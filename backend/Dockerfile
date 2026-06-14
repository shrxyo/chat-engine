# ---------------------------------------------------------------------------
# Stage 1 — installer: sync dependencies into an isolated virtualenv
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS installer

WORKDIR /app

# Bring in uv without an extra pip install
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
# --no-dev keeps the runtime image lean; --frozen ensures the lockfile is respected
RUN uv sync --frozen --no-dev

# ---------------------------------------------------------------------------
# Stage 2 — runtime: minimal image with only what is needed to run
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

WORKDIR /app

# curl is needed for the compose healthcheck
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN useradd --system --no-create-home appuser

# Virtualenv from the installer stage
COPY --from=installer /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="src"

# Application source
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY src/ ./src/

COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh && chown -R appuser /app

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
