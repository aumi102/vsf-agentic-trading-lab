---
title: apply_adjustment_factors_plan
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Apply Adjustment Factors Plan

## Purpose

This module is the first local ETL foundation for turning verified adjustment
factor records into adjusted OHLC columns. It is intentionally limited to local
SQLite demo stores and explicit symbol lists.

The flow is:

```text
verified factor records -> apply factor to raw OHLC -> write adjusted OHLC columns -> run readiness gate
```

## Input

The factor input is a local JSON list. Each usable record must have:

- `symbol`;
- `trade_date`;
- `factor > 0`;
- `source_id`;
- `method`;
- `raw_path`;
- `status=ok`;
- empty `reasons`.

No `factor=1` fallback is created. A row without a matching usable factor stays
unadjusted and is reported.

Factor provenance is separate from raw OHLC provenance. `daily_prices.source_id`
and `daily_prices.raw_path` continue to identify the raw OHLC source, while
`adjustment_source_id`, `adjustment_raw_path`, and `adjustment_method` identify
the adjustment factor source.

## Commands

```bash
python scripts/apply_adjustment_factors.py --db-path data/demo/mvp_trading_agent.sqlite --factors path/to/factors.json --symbols FPT --dry-run
python scripts/apply_adjustment_factors.py --db-path data/demo/mvp_trading_agent.sqlite --factors path/to/factors.json --symbols FPT --execute
```

Dry-run is the default. `--execute` is required before any DB mutation.

## Write Policy

Execute mode updates only:

- `adjustment_factor`;
- `adjusted_open`;
- `adjusted_high`;
- `adjusted_low`;
- `adjusted_close`;
- `adjustment_source_id`;
- `adjustment_raw_path`;
- `adjustment_method`;
- `adjustment_status`.

Raw OHLCV columns are never modified.

## Guardrails

- Explicit symbols are required.
- Rows with adjusted OHLC but missing factor provenance fail readiness.
- No network request.
- No full-universe mutation.
- No factor discovery.
- No Backtrader run.
- No Docker/scheduler behavior.
- Expected file/input errors return JSON instead of tracebacks.

## Validation

After execute mode, run:

```bash
python scripts/check_adjusted_ohlc_readiness.py --symbols FPT
```

The readiness gate should pass only when all selected rows have populated and
valid adjusted OHLC fields.

## Limitations

This is a local factor-application foundation only. It does not verify a live
source, does not derive corporate-action factors, and does not make the project
production-ready or provide investment advice.
