---
title: adjusted_price_evidence_pipeline
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Adjusted Price Evidence Pipeline

## Purpose

This pipeline is the first local technical path from confirmed adjusted-price
policy to small-symbol adjusted OHLC population. It verifies local adjusted
price evidence for explicit symbols, derives factor records, optionally applies
them to a local SQLite DB, and runs the adjusted OHLC readiness gate.

It is controlled and local-first. It does not fetch live data, crawl a universe,
run Backtrader, or schedule ETL.

## Inputs

`configs/ingestion/adjusted_price_small_symbol_mvp.json` defines the default
small set: `FPT`, `VNM`, and `VCB`, with `max_symbols = 3` and
`allow_network_default = false`.

The local payload must provide:

- `symbol`;
- `trade_date`;
- `close`;
- `adjusted_close`.

The run must also provide `source_id` and `raw_path` for factor provenance.

## Behavior

The pipeline derives:

```text
factor = adjusted_close / close
```

It rejects missing or non-positive `close`, missing or non-positive
`adjusted_close`, missing provenance, and requests with more than three symbols.
It never creates a `factor=1` fallback and never treats raw close as adjusted
close.

## Commands

Dry-run local verification:

```bash
python scripts/run_adjusted_price_evidence_pipeline.py --payload tests/fixtures/adjustment_factors/adjusted_close_payload.json --source-id fixture:adjusted_close --raw-path tests/fixtures/adjustment_factors/adjusted_close_payload.json --symbols FPT --factor-output .pytest_tmp/factors.json --dry-run
```

Execute mode requires an explicit local DB path:

```bash
python scripts/run_adjusted_price_evidence_pipeline.py --payload path/to/payload.json --source-id source:adjusted_price --raw-path path/to/payload.json --symbols FPT,VNM,VCB --factor-output path/to/factors.json --db-path data/demo/mvp_trading_agent.sqlite --execute
```

## Outputs

The JSON summary reports status, symbols, total/usable/invalid records, factor
output path, DB mutation flag, readiness status, and backtest gate. Execute mode
uses the existing local factor application path and then calls the adjusted OHLC
readiness gate. Execute mode returns top-level `status=ok` only when readiness
returns `status=ok` and `backtest_gate=pass`; partial DB adjustment with blocked
readiness returns `status=not_ready`.

## Smoke Runbook

Use `docs/data_platform/adjusted_price_evidence_smoke_runbook.md` for the
synthetic local FPT/VNM/VCB smoke. It creates temporary payload and SQLite
artifacts by default, runs dry-run and execute modes, and checks readiness
without live fetch, full-universe mutation, or Backtrader.

## Boundaries

- No uncontrolled live fetch.
- No full-universe crawl.
- No production adjusted OHLC population.
- No Backtrader/VN100 run until readiness passes.
- No Docker/scheduler.
- No production-readiness or investment-advice claim.
