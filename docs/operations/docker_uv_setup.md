# Docker with uv

Mentor feedback #4: Docker should use `uv` so setup, API and environment are
reproducible. The image is built from `pyproject.toml` + `uv.lock`, so a container
gets the exact same pinned dependencies as a local `uv sync`.

## What the image runs

The container serves the **read-only FastAPI demo console** at port 8010:

- `GET /health`, `GET /demo`, all `GET /api/demo/*`, the legacy `/v1/*` and
  `/market|/backtest|/events` routes.

It is lean by default — only the core dependency group (`fastapi`, `uvicorn`,
`psycopg[binary]`, `psycopg-pool`, `httpx`). DeepAgents is **not** installed unless
you opt in (the guarded demo routes don't need it).

## Build

```bat
docker compose config                         :: validate (no secrets in output)
docker build -t vsf-agent-backend:demo .
```

Optional DeepAgents (LLM) mode in the image:

```bat
docker build -t vsf-agent-backend:demo-deep --build-arg INSTALL_DEEPAGENTS=true .
```

### How the Dockerfile uses uv

- The pinned uv binary is copied from `ghcr.io/astral-sh/uv:0.11.24`.
- Dependencies install first from the lockfile (`uv sync --frozen --no-install-project`)
  as a cached layer; the source copies and project install come after, so code edits
  don't re-resolve dependencies.
- `UV_COMPILE_BYTECODE=1` and a build cache mount keep rebuilds fast.
- `CMD` runs `uv run --no-sync python scripts/run_fastapi_demo_app.py` on `0.0.0.0:8010`.

## Run

Full stack (QuestDB + backend on one network):

```bat
docker compose up --build -d
:: QuestDB Web Console: http://localhost:9000   Demo console: http://localhost:8010/demo
docker compose down
```

Backend-only against a QuestDB already running on the host (started by `run.cmd`):

```bat
docker compose -f docker-compose.backend-local.yml up --build -d
curl.exe -s http://127.0.0.1:8010/health
curl.exe -s http://127.0.0.1:8010/demo
curl.exe -s http://127.0.0.1:8010/api/demo/backtest/FPT
docker compose -f docker-compose.backend-local.yml down
```

The backend-local compose reaches the host QuestDB via `host.docker.internal:9000`
(`extra_hosts: host.docker.internal:host-gateway` makes that work on Linux engines
too). The in-container `QUESTDB_URL` uses a real hostname (`questdb` or
`host.docker.internal`), so the `localhost`→`127.0.0.1` normalization does not touch
it.

## Secrets

- `.env` is loaded with `required: false` and is git-ignored / docker-ignored — it is
  never baked into the image.
- `docker compose config` output contains **no** `sk-…` keys (verified). API keys, if
  any, are injected only at runtime via `.env` / environment.
- `.dockerignore` keeps `data/`, `logs/`, `*.csv`, `.venv`, `.env`, keys and caches out
  of the build context.

## Notes

- `requirements-backend.txt` / `requirements-deepagents.txt` remain for the older
  pip-based path and are no longer used by this Dockerfile.
- The previous image ran the stdlib `http.server` backend; the image now runs the
  FastAPI console. The stdlib backend is still available locally via
  `scripts/run_questdb_agent_backend.py` if needed.
