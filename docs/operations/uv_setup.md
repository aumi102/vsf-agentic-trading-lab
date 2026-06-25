# uv setup (preferred) — conda remains the fallback

Mentor feedback #4: use `uv` to make environment/setup reproducible. This repo now
ships `pyproject.toml`, `uv.lock`, and `.python-version` so the demo environment can
be reproduced with two commands. The existing conda workflow still works and remains
the documented fallback.

## Install uv

uv is a single binary. Any of:

```bat
:: pip (installs into the active interpreter/env — what this repo used)
python -m pip install uv

:: official standalone installer (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Verify:

```bat
uv --version          ::  e.g. uv 0.11.24
python -m uv --version
```

## Reproduce the environment

```bat
uv sync                       :: core/runtime deps + the project (creates .venv)
uv run python -m compileall -q src scripts
uv run python scripts\run_fastapi_demo_app.py --host 127.0.0.1 --port 8010
```

Open http://127.0.0.1:8010/demo .

`uv sync` was verified here against CPython 3.11.15: it resolved 100 packages and
installed the core deps plus `vsf-trading-agent` itself. `uv run` then imports the
FastAPI app (27 routes) and PGWire client successfully.

## Dependency groups

Defined in `pyproject.toml`:

| Group | Install | Contents |
|---|---|---|
| core (default) | `uv sync` | `httpx`, `fastapi`, `uvicorn`, `psycopg[binary]`, `psycopg-pool` |
| `research` | `uv sync --extra research` | `pandas`, `numpy`, `pyarrow`, `backtrader`, `openpyxl`, `vnstock` |
| `deepagents` | `uv sync --extra deepagents` | `deepagents`, `langchain`, `langchain-openai` (needs `OPENAI_API_KEY`) |
| `dev` | `uv sync --extra dev` | `pytest` |

The **core** group is all the FastAPI demo console, the read-only agent + tools, the
anti-blackbox trace, the SimpleEngine, and the REST/PGWire paths need. Backtrader and
pandas are only required for the persisted-backtest research path, so they live in
`research`.

Examples:

```bat
uv sync --extra research --extra dev        :: backtest comparison + tests
uv run pytest -q
uv run python scripts\benchmark_questdb_query_paths.py --repeats 50
```

## Files

- `pyproject.toml` — project metadata, core deps, optional extras, hatchling build of
  the `src/trading_agent` package (includes `demo_console.html`).
- `uv.lock` — fully pinned, committed for reproducibility.
- `.python-version` — pins Python 3.11 for uv.
- `.venv/` — created by `uv sync`; git-ignored (never committed).

## Conda fallback (still supported)

```bat
conda activate vsf-trading
python scripts\run_fastapi_demo_app.py --host 127.0.0.1 --port 8010
```

`requirements*.txt` remain for the conda/pip path. uv is the preferred new setup;
conda is the fallback and is not removed.
