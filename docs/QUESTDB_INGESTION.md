# QuestDB OHLCV ingestion + agent demo — operational note

Implementation-first pipeline: full Vietcap universe -> daily OHLCV -> QuestDB,
plus a read-only tool layer, a simple strategy/backtest, and a rule-based agent CLI.

## Prereqs
- QuestDB running at `http://localhost:9000` (verify: `curl "http://localhost:9000/exec?query=SELECT%201"`).
- Python: `C:\Users\NguyenDucHoangPhuc\.conda\envs\vsf-trading\python.exe` (or set `PY_INTERP`).

## Verified sources (reused, not invented)
- Universe : `GET https://iq.vietcap.com.vn/api/iq-insight-service/v2/company/search-bar?language=1`
  -> 2083 rows -> **1597 tradable** (HOSE/HNX/UPCOM, excl. index/OTC/OTHER/STOP).
- OHLCV    : `POST https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart`
  body `{"symbols":[SYM],"timeFrame":"ONE_DAY","countBack":N,"to":epoch}`.

## QuestDB schema (`daily_prices`)
Designated `trade_date TIMESTAMP`, `PARTITION BY YEAR`, WAL,
`DEDUP UPSERT KEYS(trade_date, security_id, source_id)`. Raw OHLC + adjusted OHLC,
`adjustment_factor`, `adjustment_status`, `quality_status`, `source_id`, `raw_path`, `ingested_at`.
`security_id`/`symbol` are `SYMBOL CAPACITY 4096`. **Why PARTITION BY YEAR:** daily bars over
25+ years = a few thousand rows/symbol; YEAR keeps partitions large and few (fast range scans),
whereas `PARTITION BY DAY` would create ~9000 tiny partitions and slow queries.

### Adjustment honesty
The gap-chart returns a single OHLC series that already appears back-adjusted but exposes **no
separate raw-vs-adjusted field**. Per the no-fabrication rule we set `adjustment_factor=1.0`,
`adjustment_status=adjusted_price_missing_warn`, and store the same source series in both the raw
and adjusted columns. The adjustment helper already implements the `adjusted_close/close` branch,
so a future source that exposes an adjusted close needs no code change.

## Run the full ingest (overnight)
```bat
scripts\run_full_vietcap_questdb_ingest.bat
```
Sequential, batches of 10 (fetch 10 -> one CSV -> `/imp` -> `gc.collect()`). Rate-limited tickers
get an in-loop cooldown, then a retry queue drained at the end (`final_failed.jsonl` for the rest).
`--resume` skips checkpointed tickers, so it is crash-safe and **re-runnable until coverage is full**.
Vietcap throttles hard after a burst, so the full 1597-symbol / ~3M-row load is paced and may take
multiple resumed passes; re-run the same command — DEDUP makes it idempotent.

Smoke test (fast):
```bat
scripts\run_full_vietcap_questdb_ingest.bat --limit-symbols 30
python scripts\batch_ingest_vietcap_ohlcv_to_questdb.py --symbols FPT,VNM,VCB --batch-size 10 --resume
```

## Daily refresh
Re-run the same full command daily. DEDUP upserts on `(trade_date, security_id, source_id)` so the
full history is recomputed and current without duplicating rows.

## Demo to mentor
```bat
python scripts\demo_deep_agent_questdb_cli.py "how many rows are in QuestDB"
python scripts\demo_deep_agent_questdb_cli.py "show latest FPT data"
python scripts\demo_deep_agent_questdb_cli.py "backtest MA strategy for FPT from 2020 to 2025"
python scripts\demo_questdb_strategy_backtest.py --symbol FPT --start-date 2020-01-01 --end-date 2025-12-31 --show-trades 5
```
Tool layer: `src/trading_agent/tools/questdb_market_data_tool.py`
(`query_questdb`, `get_universe`, `get_latest_ohlcv`, `get_ohlcv_window`, `get_table_health`).
Strategy/backtest: `src/trading_agent/strategies/simple_ma_cross.py` (MA20/MA50, long-only,
0.15% cost, next-day-close execution, leak-free).
