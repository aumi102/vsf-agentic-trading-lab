# Validation gates

The validation gate suite is a read-only preflight layer for the current architecture:

```text
source -> raw capture -> bronze parser -> silver canonical table -> gold features -> signal -> backtest -> validation -> agent answer
```

The gates make the demo state explicit before the agent answers. They do not run ingestion, do not rebuild QuestDB tables, and do not run live Backtrader from the agent.

## Run commands

```bat
python scripts\run_validation_gates.py
python scripts\run_validation_gates.py --json
python scripts\run_validation_gates.py --write-report docs\demo\validation_gate_latest.md
```

## Status model

Each gate returns:

- `gate_name`
- `status`: `PASS`, `WARN`, or `FAIL`
- `evidence`
- `caveats`
- `recommended_fix`
- `blocking`

Overall status:

- any blocking `FAIL` -> `OVERALL_STATUS=FAIL`;
- no blocking `FAIL`, but at least one `WARN` -> `OVERALL_STATUS=WARN`;
- all gates `PASS` -> `OVERALL_STATUS=PASS`.

## Gate coverage

| Gate | Architecture layer | Purpose |
|---|---|---|
| `market_table_coverage` | silver canonical table | Confirms `daily_prices` exists, has rows/symbols, and has a latest date. |
| `feature_signal_parity` | gold features / signal | Confirms `feature_snapshots` and `signals` remain close to `daily_prices` coverage. |
| `adjusted_ohlc_gate` | silver canonical price quality | Checks adjusted OHLC column presence and warns when adjusted prices are source-unverified. |
| `exchange_metadata_gate` | security master | Checks `securities.exchange`, especially source-backed FPT/VNM/HPG metadata for price-band guard readiness. |
| `fa_tables_gate` | raw/bronze/silver FA | Confirms FA tables and latest complete FA run exist. |
| `fa_mapping_gate` | bronze parser / silver FA | Warns when Vietcap metric mapping is still opaque. |
| `backtest_tables_gate` | backtest | Confirms persisted runs, metrics, equity, and trade rows exist. |
| `backtest_execution_assumptions_gate` | backtest validation | Checks commission, slippage, and price-band status. |
| `event_news_gate` | source probe / raw capture / agent answer | Confirms the official-disclosure event layer exists when available and verifies event/news prompts do not use OHLCV as a proxy. |
| `agent_guardrail_gate` | agent answer | Runs readiness checks for market/FA/backtest/event routing. |
| `docker_packaging_gate` | deployment packaging | Validates Docker files, compose config, and image build when Docker is available. |

## Expected warnings in the current demo

These warnings are known and should be stated to the mentor:

- adjusted OHLC source remains unverified;
- adjusted OHLC source remains unverified and current adjusted values are raw-equivalent;
- FA metric mapping is partial: `fa_metric_mapping` exists, but consensus coverage is below the threshold for a full PASS;
- `slippage_bps=0` remains the default demo comparison, while 5/10/15 bps scenario rows are persisted separately;
- event/news uses a minimal official-disclosure layer for FPT only; this is not broad market news.

Current exchange metadata is source-backed from captured Vietcap IQ universe and
HOSE listed-universe dry-run evidence for all 1,556 current `securities` rows.
That allows `exchange_metadata_gate` and the persisted backtest
`price_band_status` checks to pass for the current database scope. New symbols
still require source-backed exchange evidence before the guard should be treated
as complete.
