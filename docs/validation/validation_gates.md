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
| `agent_guardrail_gate` | agent answer | Runs readiness checks for market/FA/backtest/event routing. |
| `docker_packaging_gate` | deployment packaging | Validates Docker files, compose config, and image build when Docker is available. |

## Expected warnings in the current demo

These warnings are known and should be stated to the mentor:

- adjusted OHLC source remains unverified;
- FA metric mapping is `metric_mapping_unverified`;
- broader-universe exchange metadata may remain partial unless source-backed;
- `slippage_bps=0` is explicit and within the demo symbols' HOSE price band, but still a simple assumption;
- event/news ingestion is not implemented, and event/news queries remain unsupported by guardrail.

For the current mentor demo, FPT/VNM/HPG exchange metadata is filled as `HOSE`
from captured Vietcap IQ universe and HOSE listed-universe dry-run evidence.
That allows `exchange_metadata_gate` and the persisted backtest
`price_band_status` checks to pass for the demo scope without claiming full
universe exchange coverage.
