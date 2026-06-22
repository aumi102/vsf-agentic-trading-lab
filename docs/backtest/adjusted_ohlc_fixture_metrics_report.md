---
title: adjusted_ohlc_fixture_metrics_report
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Adjusted OHLC Fixture Diagnostic Metrics Report

## Purpose

This layer consumes a PR #50 fixture signal preview JSON and produces
deterministic, clearly fixture-labeled **diagnostics**. Its only goal is to prove
the reporting/metrics plumbing can read adjusted-basis fixture inputs. It is
**not** strategy performance, not a profitability claim, and not a backtest. It
does not implement Backtrader, optimize parameters, run full VN100, call any
engine, fetch live data, mutate a database, or give investment advice.

## Preconditions

- PR #49 preparation `status=ok`;
- PR #50 fixture signal `status=ok`;
- fixture signal `dry_run_stage=fixture_signal_preview`;
- fixture signal `price_basis=adjusted_ohlc`;
- fixture signal `not_financial_advice=true` and `performance_metrics=null`;
- explicit small symbol set (for example `FPT,VNM,VCB`);
- explicit cost/slippage assumptions were already validated upstream in PR #49.

## Allowed Diagnostic Metrics

- `row_count`;
- `symbol_count`;
- `signal_action_counts`;
- `first_date` / `last_date`;
- `fixture_no_position_ratio`;
- `input_price_basis`.

## Forbidden Metrics

This report intentionally never computes:

- Sharpe;
- Sortino;
- Profit Factor;
- Max Drawdown;
- equity curve;
- PnL;
- win rate;
- alpha;
- any profitability claim.

If the input fixture signal carries a real action (`BUY`/`SELL`/`HOLD`), a
non-null `performance_metrics`, or any performance field on a row, the report
blocks and sets `forbidden_performance_metrics_present=true`.

## Validation

The report blocks unless all of the following hold:

- fixture signal file exists and is a JSON object;
- fixture signal `status=ok`;
- fixture signal `dry_run_stage=fixture_signal_preview`;
- fixture signal `price_basis=adjusted_ohlc`;
- fixture signal `not_financial_advice=true`;
- fixture signal `performance_metrics is null`;
- every requested symbol is covered;
- signal rows exist;
- no row uses a forbidden action (`BUY`/`SELL`/`HOLD`);
- no row carries a PnL/equity/performance field.

Representative block reasons: `fixture_signal_missing:<path>`,
`fixture_signal_invalid_json`, `fixture_signal_must_be_object`,
`fixture_signal_status_not_ok:<value>`,
`fixture_signal_stage_invalid:<value>`,
`fixture_price_basis_not_adjusted_ohlc:<value>`,
`fixture_not_financial_advice_missing`,
`fixture_performance_metrics_must_be_null`,
`requested_symbol_missing:<SYMBOL>`, `signal_rows_missing`,
`forbidden_action_present:<ACTION>`, `forbidden_row_field_present:<field>`.

## Output

```json
{
  "status": "ok",
  "report_stage": "fixture_diagnostic_metrics",
  "price_basis": "adjusted_ohlc",
  "symbols": ["FPT", "VNM", "VCB"],
  "diagnostic_metrics": {
    "row_count": 3,
    "symbol_count": 3,
    "signal_action_counts": {
      "NO_POSITION": 3
    },
    "first_date": "2026-01-02",
    "last_date": "2026-01-02",
    "fixture_no_position_ratio": 1.0,
    "input_price_basis": "adjusted_ohlc"
  },
  "forbidden_performance_metrics_present": false,
  "not_financial_advice": true,
  "reasons": [],
  "caveats": [
    "Fixture diagnostics only; not strategy performance."
  ]
}
```

A Markdown report can also be rendered for review.

## Command

```bash
python scripts/report_adjusted_ohlc_fixture_metrics.py --fixture-signal-json reports/reviewed_evidence/fixture_signal_preview.json --symbols FPT,VNM,VCB --output-json reports/reviewed_evidence/fixture_metrics.json --output-md reports/reviewed_evidence/fixture_metrics.md
```

## Boundaries

- no Backtrader;
- no optimizer;
- no engine call;
- no full VN100;
- no DB mutation;
- no live data fetch;
- no profitability or risk-performance metrics;
- no investment advice;
- no production-readiness claim.

## Next Safe Step

The next step is `docs/backtest/adjusted_ohlc_fixture_roundtrip_engine.md`, a
deterministic adjusted-basis fixture round-trip engine dry-run that consumes the
PR #49 preparation, PR #50 fixture signal, and this fixture metrics report, and
emits round-trip state-transition diagnostics only (enter/exit/duplicate/unmatched/
open counts). It is fixture diagnostics only: not strategy performance, not
Backtrader, not an optimizer, not full VN100, and it intentionally avoids all
profitability/performance metrics. After that, a mentor review of these
boundaries is required before any real adjusted-basis engine integration.
Backtrader research work stays blocked until that review passes.
