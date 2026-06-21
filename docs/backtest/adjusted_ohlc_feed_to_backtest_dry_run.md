---
title: adjusted_ohlc_feed_to_backtest_dry_run
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Adjusted OHLC Feed To Backtest Dry-Run Preparation

## Purpose

This layer converts a PR #48 adjusted OHLC feed preview into a backtest-ready
input contract for a research dry-run. It is preparation only. It does not
implement Backtrader, run a strategy, optimize parameters, run full VN100, fetch
live data, mutate a database, or produce investment advice.

## Preconditions

- PR #48 feed readiness returned `status=ok`.
- Adjusted OHLC strict execution audit passed (`backtest_planning_gate=pass`).
- An explicit, small symbol set is provided (for example `FPT,VNM,VCB`).
- An explicit date range is provided when filtering.

## Required Input

- feed preview JSON produced by PR #48
  (`scripts/preview_adjusted_ohlc_backtest_feed.py --output-json ...`);
- `transaction_cost_bps`;
- `slippage_bps`;
- `exchange`;
- optional fixture signal source (`--fixture-signal-mode`), research-only.

## Assumptions

- `price_basis=adjusted_ohlc`;
- transaction cost is explicit;
- slippage is explicit;
- slippage is bounded by the exchange daily price band:
  - HOSE/HSX: `<= 700 bps` (+/-7%);
  - UPCoM: `<= 1500 bps` (+/-15%).

## Validation

The preparation layer blocks unless all of the following hold:

- feed preview file exists and is a JSON object;
- feed preview `status=ok`;
- feed preview `feed_contract_version=adjusted_ohlc_feed_v1`;
- feed preview `source_price_basis=adjusted_ohlc`;
- every requested symbol is present in the feed preview;
- date range is valid ISO `YYYY-MM-DD` and `start_date <= end_date`;
- `max_rows > 0`;
- each row has `open/high/low/close/volume`;
- no raw OHLC field is used as a trading price;
- no signal, trade, or performance field is present in the input;
- `transaction_cost_bps >= 0` and `slippage_bps >= 0`;
- `exchange` is one of `HOSE`, `HSX`, `UPCOM`, `UPCoM`;
- `slippage_bps` is within the exchange band.

## Output

```json
{
  "status": "ok",
  "dry_run_stage": "backtest_input_preparation",
  "backtest_input_status": "ready_for_research_dry_run",
  "price_basis": "adjusted_ohlc",
  "symbols": ["FPT", "VNM", "VCB"],
  "row_count": 3,
  "assumptions": {
    "transaction_cost_bps": 15,
    "slippage_bps": 10,
    "exchange": "HOSE",
    "slippage_band_bps": 700
  },
  "rows_preview": [],
  "reasons": [],
  "caveats": [
    "Preparation only; no Backtrader execution.",
    "No investment advice.",
    "No live trading."
  ]
}
```

The output reports dry-run status, input rows, symbols, date range assumptions,
and blocked reasons. It makes no performance claim. A performance claim would
require an actual backtest engine to be safely called and clearly marked as
fixture/research only; this layer does not do that.

## Fixture Signal Mode

`--fixture-signal-mode` adds a deterministic, research-only fixture labelled
`research_fixture_signal`. It is an all-cash placeholder. It does not execute an
engine, produce trades, make a performance claim, or recommend buy/sell/hold.

## Command

```bash
python scripts/prepare_adjusted_ohlc_backtest_dry_run.py --feed-preview reports/reviewed_evidence/feed_preview.json --symbols FPT,VNM,VCB --start-date 2026-01-01 --end-date 2026-12-31 --transaction-cost-bps 15 --slippage-bps 10 --exchange HOSE --output-json reports/reviewed_evidence/backtest_input_preview.json
```

## Boundaries

- no Backtrader;
- no full VN100;
- no optimizer;
- no live trading;
- no broker execution;
- no investment advice;
- no production readiness claim.
