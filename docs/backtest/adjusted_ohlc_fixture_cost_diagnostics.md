---
title: adjusted_ohlc_fixture_cost_diagnostics
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Adjusted OHLC Fixture Cost/Slippage Diagnostics

## Purpose

This fixture-only layer attaches validated transaction-cost and slippage
assumptions to PR #52 state-transition counts. It produces auditable bps-units
diagnostics, not money, PnL, returns, strategy performance, or a production
backtest.

## Preconditions

- PR #49 preparation has `status=ok` and
  `backtest_input_status=ready_for_research_dry_run`;
- PR #52 round-trip output has `status=ok`;
- both inputs use `price_basis=adjusted_ohlc`;
- `transaction_cost_bps` and `slippage_bps` are explicit and non-negative;
- `exchange` and its already-validated `slippage_band_bps` are explicit;
- requested small-symbol coverage is complete.

## Allowed Diagnostics

- fixture enter and exit transition counts as event-count inputs;
- estimated cost event count and estimated slippage event count;
- transaction-cost bps, slippage bps, exchange, and exchange-band echoes;
- `total_transaction_cost_bps_units = event_count * transaction_cost_bps`;
- `total_slippage_bps_units = event_count * slippage_bps`;
- total friction bps-units as the sum of those two diagnostics.

Bps-units are dimensionless assumption diagnostics only. They are not currency,
loss, PnL, or return.

## Forbidden

This layer never multiplies an assumption by price. It never computes or emits
PnL, equity, return, alpha, Sharpe, Sortino, Profit Factor, Max Drawdown,
currency loss, a real trade list, or recommendation language.

## Output

```json
{
  "status": "ok",
  "diagnostic_stage": "fixture_cost_slippage_diagnostics",
  "price_basis": "adjusted_ohlc",
  "symbols": ["FPT", "VNM", "VCB"],
  "cost_diagnostics": {
    "estimated_cost_event_count": 0,
    "estimated_slippage_event_count": 0,
    "transaction_cost_bps": 15,
    "slippage_bps": 10,
    "exchange": "HOSE",
    "slippage_band_bps": 700,
    "total_transaction_cost_bps_units": 0,
    "total_slippage_bps_units": 0,
    "total_friction_bps_units": 0
  },
  "not_financial_advice": true,
  "forbidden_performance_metrics_present": false,
  "reasons": [],
  "caveats": ["Fixture cost/slippage diagnostics only; not PnL or returns."]
}
```

## Command

```bash
python scripts/report_adjusted_ohlc_fixture_cost_diagnostics.py --preparation-json reports/reviewed_evidence/backtest_input_preview.json --roundtrip-json reports/reviewed_evidence/fixture_roundtrip.json --symbols FPT,VNM,VCB --output-json reports/reviewed_evidence/fixture_cost_diagnostics.json --output-md reports/reviewed_evidence/fixture_cost_diagnostics.md
```

## Boundaries

- no Backtrader;
- no optimizer;
- no full VN100;
- no price multiplication or trade list;
- no production backtest, broker execution, or live trading;
- no strategy-performance or production-readiness claim;
- no investment advice.

## Next Safe Step

After PR #53, mentor review is required before any real adjusted-basis engine
integration.
