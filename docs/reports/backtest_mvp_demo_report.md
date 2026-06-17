---
title: backtest_mvp_demo_report
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Backtest MVP Demo Report

This report summarizes the exploratory Backtest MVP commands now included in the mentor demo package. It uses the cached local SQLite store only. It is not production-ready and not financial advice.

Build the local store first:

```bash
python scripts/build_mvp_db.py --symbols FPT,VNM,VCB
```

No network fetch, broker execution, live trading, LLM reasoning, QuestDB, shorting, or portfolio optimization is used.

---

## Expected Results

| Command | Exit | Status | Key result |
|---|---:|---|---|
| `run_backtest_demo.py --symbols FPT,VNM,VCB` | 0 | ok | metrics present; validation gates pass/warn |
| `run_backtest_demo.py --symbols FPT,HPG` | 0 | ok | FPT runs; HPG in `symbols_missing` |
| `run_backtest_demo.py --symbols FPT --start-date 2030-01-01 --end-date 2030-12-31` | 1 | not_found | no usable rows; no traceback |
| `run_backtest_demo.py --symbols HPG` | 1 | not_found | all symbols missing; no traceback |
| `run_backtest_demo.py --symbols FPT --initial-capital 0` | 2 | invalid_assumptions | no traceback |

---

## What To Inspect

- `status`, `symbols_found`, and `symbols_missing` in the JSON summary.
- Validation gates: `store_exists`, `symbols_exist`, `usable_rows_exist`, `daily_prices_have_source_id_raw_path`, `fail_ohlc_rows_excluded`, `enough_lookback`, adjustment warning, and same-day close caveat.
- Metrics table for total return, annualized return, Sharpe, Sortino, profit factor, max drawdown, win rate, trade count, and exposure.
- Caveats confirming cached data only, unknown adjustment/corporate-action status, same-day close execution convention, and not financial advice.

---

## Current Limitations

- Same-day close is an MVP convention; production should use a stricter next-bar execution convention.
- Corporate-action adjustment is not implemented.
- Cost and slippage are flat assumptions.
- Results are over saved local payloads only and should not be interpreted as investment advice.
- Production hardening remains blocked until mentor confirms execution convention, assumptions, symbol universe, and store path.
