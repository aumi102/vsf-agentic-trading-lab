# FastAPI demo console

Mentor feedback #1: the demo must not require the operator to run many terminal
commands. The FastAPI console replaces the command sequence with a single browser
page of buttons; each button shows the result **and** the anti-blackbox trace and the
next recommended action.

## Run it

```bat
uv run python scripts\run_fastapi_demo_app.py --host 127.0.0.1 --port 8010
:: or, without uv:
python scripts\run_fastapi_demo_app.py --host 127.0.0.1 --port 8010
```

Open **http://127.0.0.1:8010/demo** .

Read-only: it serves persisted QuestDB data and safe in-process diagnostics. It never
runs live Backtrader and never mutates a table. The stdlib backend
(`scripts/run_questdb_agent_backend.py`) still exists and is unaffected.

## The browser console (`/demo`)

A single self-contained page (no build step). Left: a grouped menu + an "Ask the
agent" box. Right: for each action it renders status, query timing, the answer, the
result table, and the full pipeline trace (pipeline position, RouterAgent, the domain
agent, decisions/reasons, allowed vs rejected tools, tool calls, caveats, next
action). A query-mode selector switches REST ↔ PGWire.

## JSON endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/demo/menu` | menu items + defaults (query mode, pgwire availability) |
| `GET /api/demo/status` | QuestDB health, FA latest run, backtest coverage, pipeline counts |
| `GET /api/demo/validation` | fast read-only **data** gates (docker/subprocess gates excluded) |
| `GET /api/demo/readiness` | in-process routing readiness for the demo queries |
| `GET /api/demo/market/{symbol}` | latest OHLCV + features + deterministic signal + trace |
| `GET /api/demo/fa/{symbol}` | persisted Vietcap FA facts + trace |
| `GET /api/demo/backtest/{symbol}` | persisted Backtrader strategy comparison + trace |
| `GET /api/demo/backtest/{symbol}/slippage` | persisted 0/5/10/15 bps scenarios + trace |
| `GET /api/demo/backtest/{symbol}/simple-engine` | transparent SimpleEngine vs persisted Backtrader + trace |
| `GET /api/demo/backtest/{symbol}/simple-engine/logic` | exact, mentor-readable logic / assumptions block (data source, signal, execution, sizing, cost, metrics, divergences vs Backtrader) |
| `GET /api/demo/backtest/{symbol}/simple-engine/variants` | deterministic strategy logic lab: 9 variants (raw vs adjusted, next-open vs same-close, 95% vs 100%, 0/5/10/15 bps slippage, volume filter, RSI(14) mean-reversion) with per-row narrative |
| `GET /api/demo/events/{symbol}` | official disclosure records (FPT) / guardrail (VNM) |
| `POST /api/demo/ask` | free-text query → answer + trace (`{"query": "..."}` or `{"message": "..."}`; `mode: rule|deep`) |
| `GET /api/demo/trace/examples` | full traces for each domain |
| `GET /api/demo/benchmark/questdb` | REST vs PGWire timing + recommendation |
| `GET /api/demo/next-actions` | prioritized next steps from current state |

Every demo envelope carries: `status`, `domain`, `answer_markdown`/`rows`,
`tool_calls`, `trace`, `caveats`, `next_action`, and a `timing` block
(`query_mode`, `execute_ms`, `total_ms`) plus handler `elapsed_ms`.

Add `?mode=pgwire` to a demo GET to route its timing probe through PGWire.

## Preserved legacy endpoints

`GET /health`, `GET /questdb/health`, `GET /v1/models`, `POST /v1/chat/completions`,
`GET /market/summary/{symbol}`, `GET /backtest/comparison/{symbol}`,
`GET /backtest/slippage-scenarios/{symbol}`, `GET /events/latest/{symbol}` — same
behavior as the stdlib backend, so existing clients keep working.

## Robustness

- **JSON errors, never raw 500 text.** An app-wide exception handler returns
  `{status, error_type, message, path, caveats, next_action}` (HTTP 500) for any
  unhandled error, with OpenAI-style key fragments redacted. The browser console
  renders it as an error card instead of failing to parse.
- **Domain is derived from the tools that actually ran** (then intent, then keywords),
  so the trace stays correct even in deep mode where the intent is nested — e.g.
  `summary CTG` is `market_summary`/`MarketDataAgent`, not `SYSTEM`.
- **Pandas-free import path.** `trading_agent.backtest` exposes `run_backtest` lazily,
  so the validation gates / slippage guard / SimpleEngine import under the core
  (no-pandas) `uv` environment; `/api/demo/validation` no longer 500s there.
- **PGWire pool self-heals** QuestDB's idle-close (connection check on borrow); the
  harmless "discarding closed connection" warning is quieted in the demo.

## Performance notes (Task H)

- Uses `127.0.0.1` (not `localhost`) to avoid the ~2s Windows IPv6 connect penalty.
- Short-TTL caching (10–30s) on non-mutating views (status, menu, benchmark,
  next-actions); mutating results are never cached (there are none — all read-only).
- Blocking QuestDB calls run in a worker thread (`asyncio.to_thread`) so the event
  loop stays responsive.

## Verified endpoints

All GET endpoints (15) + `POST /api/demo/ask` + `POST /v1/chat/completions` return
`200` with valid JSON; `/demo` returns HTML. The event/news VNM route returns
`status=unsupported` (no OHLCV proxy), and the backtest route's trace shows
`RouterAgent → BacktestAgent` with live-Backtrader tools rejected. The
`/simple-engine/logic` endpoint returns the explicit assumption dict;
`/simple-engine/variants` returns the variant lab with the baseline row
highlighted and per-row narratives.
