---
title: adjusted_ohlc_fixture_signal_dry_run
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Adjusted OHLC Fixture Signal Dry-Run

## Purpose

This layer turns a PR #49 backtest input preparation JSON into a tiny,
deterministic **fixture signal** preview for a research dry-run. It is not a
real strategy and not a backtest. It does not implement Backtrader, optimize
parameters, run full VN100, call any engine, fetch live data, mutate a
database, report performance metrics, or produce investment advice.

## Preconditions

- PR #49 preparation `status=ok`;
- preparation `backtest_input_status=ready_for_research_dry_run`;
- preparation `price_basis=adjusted_ohlc`;
- explicit small symbol set (for example `FPT,VNM,VCB`);
- explicit transaction-cost and slippage assumptions present in the preparation.

## Fixture Signal Options

- `all_cash` (default): every row is `NO_POSITION`
  (`reason=research_fixture_all_cash`). The fixture always stays out of the
  market.
- `alternating_fixture_signal` (optional): a purely synthetic on/off flag that
  alternates `FIXTURE_ENTER` and `FIXTURE_EXIT` by row index. It is a plumbing
  fixture only, not a trade rule.

Neither mode uses buy/sell/hold wording. Neither mode is a recommendation.

## Validation

The dry-run blocks unless all of the following hold:

- preparation file exists and is a JSON object;
- preparation `status=ok`;
- preparation `backtest_input_status=ready_for_research_dry_run`;
- preparation `price_basis=adjusted_ohlc`;
- every requested symbol is represented in the preparation;
- cost/slippage assumptions are present;
- `signal_mode` is one of `all_cash`, `alternating_fixture_signal`;
- `max_rows > 0`.

Representative block reasons: `preparation_missing:<path>`,
`preparation_invalid_json`, `preparation_must_be_object`,
`preparation_status_not_ok:<value>`,
`preparation_input_status_not_ready:<value>`,
`preparation_price_basis_not_adjusted_ohlc:<value>`,
`requested_symbol_missing_from_preparation:<SYMBOL>`,
`preparation_assumptions_missing`, `unknown_signal_mode:<value>`,
`max_rows_must_be_positive`.

## Output

```json
{
  "status": "ok",
  "dry_run_stage": "fixture_signal_preview",
  "price_basis": "adjusted_ohlc",
  "signal_mode": "all_cash",
  "symbols": ["FPT", "VNM", "VCB"],
  "row_count": 3,
  "signal_rows": [
    {
      "symbol": "FPT",
      "datetime": "2026-01-02",
      "fixture_signal_action": "NO_POSITION",
      "reason": "research_fixture_all_cash"
    }
  ],
  "performance_metrics": null,
  "not_financial_advice": true,
  "reasons": [],
  "caveats": []
}
```

`performance_metrics` is always `null`. No performance claim is made unless an
actual adjusted-basis fixture engine is added later and tests verify it; this
layer does not do that. A Markdown report can also be rendered for review.

## Command

```bash
python scripts/run_adjusted_ohlc_fixture_signal_dry_run.py --preparation-json reports/reviewed_evidence/backtest_input_preview.json --symbols FPT,VNM,VCB --signal-mode all_cash --output-json reports/reviewed_evidence/fixture_signal_preview.json --output-md reports/reviewed_evidence/fixture_signal_preview.md
```

## Boundaries

- no Backtrader;
- no optimizer;
- no engine call;
- no full VN100;
- no DB mutation;
- no live data fetch;
- no performance metrics by default;
- no live trading;
- no broker execution;
- no investment advice;
- no real trading recommendation.

## Next Safe Step

The next step is `docs/backtest/adjusted_ohlc_fixture_metrics_report.md`, which
consumes this fixture signal output and produces deterministic, clearly
fixture-labeled diagnostic metrics (counts, dates, no-position ratio). It is
fixture diagnostics only: not strategy performance, and it intentionally avoids
Sharpe/Sortino/Profit Factor/Max Drawdown/PnL/equity curve. After that, a mentor
review of the assumption, signal, and diagnostic boundaries is required before
any actual backtest engine integration. Backtrader research work stays blocked
until that review passes.
