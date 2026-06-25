# QuestDB connection modes (REST vs PGWire) and the `run.cmd` question

Mentor feedback #5 and #7. This clarifies how the app talks to QuestDB, the two
ports involved, and what `run.cmd` does (and does not) do.

## The two query paths

| Path | Address | Used for | Client |
|---|---|---|---|
| REST `/exec` + Web Console | `http://127.0.0.1:9000` | SQL queries (JSON), the Web Console UI | `httpx` (`questdb_client`, `questdb_read`) |
| REST `/imp` | `http://127.0.0.1:9000/imp` | bulk CSV ingestion (append, DEDUP) | `httpx` (`questdb_client.imp_csv`) |
| PGWire (PostgreSQL wire) | `127.0.0.1:8812` | low-latency repeated read queries | `psycopg` (`questdb_pgwire_client`) |

Default PGWire credentials (local QuestDB): `user=admin password=quest dbname=qdb`.
All are overridable — see environment variables below.

### When to use each

- **REST `/exec`** — the default for all app reads (`QUESTDB_QUERY_MODE=rest`).
  Simple, no driver, returns JSON, supports `timings=true` for server-side execute
  timing.
- **PGWire** — opt-in for low-latency repeated reads (`QUESTDB_QUERY_MODE=pgwire`).
  Skips REST JSON, reuses a warm connection (~20–30% lower p50 in our benchmark).
- **REST `/imp`** — CSV ingestion only. Not used by the read-only demo. Keep REST
  here even if reads move to PGWire.

## `run.cmd` only starts the server — the app never shells out to it

- `run.cmd` (QuestDB's launcher) **starts the QuestDB server** locally if it is not
  already running. It is a one-time/bootstrap action.
- Once QuestDB is running, the app **connects directly** to:
  - REST `http://127.0.0.1:9000`
  - PGWire `127.0.0.1:8812`
- **No app endpoint shells out to `run.cmd` per query.** Queries go straight over
  HTTP/PGWire to the already-running server. The FastAPI demo, the rule agent, the
  benchmark and the backtest engine all do this.
- Under Docker, the `questdb` service starts the server automatically (see
  `docker-compose.yml`), so `run.cmd` is not needed there at all.

## Use `127.0.0.1`, not `localhost`, on Windows

On Windows, `localhost` resolves to IPv6 `::1` first. QuestDB binds IPv4, so a fresh
connection to `localhost` pays a **~2 second** `::1` connect-timeout fallback before
retrying `127.0.0.1`. Measured: `localhost` p50 ≈ 2049 ms vs `127.0.0.1` p50 ≈ 18 ms
per fresh connection (`python scripts\benchmark_questdb_query_paths.py --compare-hosts`).

The app normalizes a literal `localhost` host to `127.0.0.1` at the REST and PGWire
chokepoints (`trading_agent.storage.questdb_client.to_ipv4_localhost`). You can still
pass `http://localhost:9000`; it is rewritten for the connection only. Real/remote
hostnames are never rewritten.

## Environment variables

REST:

- `QUESTDB_URL` — e.g. `http://127.0.0.1:9000` (default `http://localhost:9000`,
  auto-normalized to IPv4).
- `QUESTDB_QUERY_MODE` — `rest` (default) or `pgwire`.

PGWire (`questdb_pgwire_client`):

- `QUESTDB_PGWIRE_DSN` — full DSN, overrides the parts below.
- `QUESTDB_PGWIRE_HOST` (default `127.0.0.1`)
- `QUESTDB_PGWIRE_PORT` (default `8812`)
- `QUESTDB_PGWIRE_USER` (default `admin`)
- `QUESTDB_PGWIRE_PASSWORD` (default `quest`)
- `QUESTDB_PGWIRE_DB` (default `qdb`)

## Quick checks

```bat
:: REST is up
curl.exe -s "http://127.0.0.1:9000/exec?query=SELECT%201&timings=true"

:: PGWire is up (psycopg)
python -c "import sys; sys.path.insert(0,'src'); from trading_agent.storage import questdb_pgwire_client as p; print(p.ping())"

:: Compare paths
python scripts\benchmark_questdb_query_paths.py --repeats 50
```
