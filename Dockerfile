# syntax=docker/dockerfile:1
# uv-based image for the read-only QuestDB agent + FastAPI demo console.
# Lean by default: only core deps (fastapi, uvicorn, psycopg, httpx). Optional
# DeepAgents extra is opt-in via --build-arg INSTALL_DEEPAGENTS=true.
FROM python:3.11-slim

# Copy the uv binary from the official image (pinned for reproducibility).
COPY --from=ghcr.io/astral-sh/uv:0.11.24 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH=/app/.venv/bin:$PATH \
    QUESTDB_URL=http://questdb:9000 \
    VSF_DEEPAGENTS_MODEL=gpt-4.1-mini

WORKDIR /app
ARG INSTALL_DEEPAGENTS=false

# 1) Install dependencies from the lockfile first (cached layer; no project yet).
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev \
    && if [ "$INSTALL_DEEPAGENTS" = "true" ]; then \
         uv sync --frozen --no-install-project --no-dev --extra deepagents; \
       fi

# 2) Copy the source and install the project itself.
COPY src src
COPY scripts scripts
COPY docs docs
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev \
    $( [ "$INSTALL_DEEPAGENTS" = "true" ] && echo "--extra deepagents" )

EXPOSE 8010

# Serve the FastAPI demo console (read-only). QUESTDB_URL/PORT are overridable.
CMD ["sh", "-c", "uv run --no-sync python scripts/run_fastapi_demo_app.py --host 0.0.0.0 --port ${PORT:-8010} --questdb-url ${QUESTDB_URL:-http://questdb:9000}"]
