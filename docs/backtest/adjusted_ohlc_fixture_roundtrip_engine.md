---
title: adjusted_ohlc_fixture_roundtrip_engine
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Adjusted OHLC Fixture Round-Trip Engine

## Purpose

This layer is a tiny deterministic, adjusted-basis **fixture round-trip engine**
dry-run. It consumes the PR #49 prepared input, the PR #50 fixture signal, and
the PR #51 fixture diagnostic report, and produces a deterministic, auditable,
non-advice round-trip report. Its only goal is to prove the engine/reporting
plumbing can consume adjusted-basis fixture inputs. It is **not** strategy
performance, not profitability evaluation, and not a backtest. It does not
implement Backtrader, optimize parameters, run full VN100, call any production
engine, fetch live data, or mutate a database.

## Preconditions

- PR #49 preparation `status=ok` (`backtest_input_status=ready_for_research_dry_run`);
- PR #50 fixture signal `status=ok`;
- PR #51 fixture metrics `status=ok` with `forbidden_performance_metrics_present=false`;
- all three inputs use `price_basis=adjusted_ohlc` and `not_financial_advice=true`;
- explicit small symbol set (for example `FPT,VNM,VCB`);
- explicit cost/slippage assumptions echoed from the preparation.

## Allowed Fixture Actions

- `NO_POSITION`;
- `FIXTURE_ENTER`;
- `FIXTURE_EXIT`.

These are synthetic fixture states. They are **not** buy/sell/hold and carry no
trading meaning.

## Allowed Diagnostics

- `input_row_count`;
- `signal_row_count`;
- `processed_row_count`;
- `action_counts`;
- `state_transition_counts` (`fixture_enter_count`, `fixture_exit_count`,
  `duplicate_enter_count`, `unmatched_exit_count`, `open_fixture_state_count`);
- `first_date` / `last_date`;
- cost/slippage `assumptions` echoed;
- `input_price_basis` echoed.

## Forbidden

This engine never computes and never emits:

- Sharpe;
- Sortino;
- Profit Factor;
- Max Drawdown;
- PnL;
- equity curve;
- win rate;
- alpha;
- return %;
- a real trade list;
- any recommendation language.

A real action (`BUY`/`SELL`/`HOLD`), a non-null `performance_metrics`, or any
PnL/equity/return/Sharpe/drawdown field on a row blocks the run.

## State Machine

Per-symbol state starts at `OUT`:

- `NO_POSITION`: no state change;
- `FIXTURE_ENTER`: `OUT → IN_FIXTURE` and `fixture_enter_count++`; if already
  `IN_FIXTURE`, `duplicate_enter_count++`;
- `FIXTURE_EXIT`: `IN_FIXTURE → OUT` and `fixture_exit_count++`; if already
  `OUT`, `unmatched_exit_count++`.

At the end, symbols still `IN_FIXTURE` are counted as `open_fixture_state_count`.
No PnL, returns, or trade list are produced.

## Output

```json
{
  "status": "ok",
  "engine_stage": "fixture_roundtrip_engine",
  "price_basis": "adjusted_ohlc",
  "symbols": ["FPT", "VNM", "VCB"],
  "roundtrip_diagnostics": {
    "input_row_count": 3,
    "signal_row_count": 3,
    "processed_row_count": 3,
    "action_counts": {"NO_POSITION": 3},
    "state_transition_counts": {
      "fixture_enter_count": 0,
      "fixture_exit_count": 0,
      "duplicate_enter_count": 0,
      "unmatched_exit_count": 0,
      "open_fixture_state_count": 0
    },
    "first_date": "2026-01-02",
    "last_date": "2026-01-02"
  },
  "forbidden_performance_metrics_present": false,
  "not_financial_advice": true,
  "reasons": [],
  "caveats": ["Fixture round-trip diagnostics only; not strategy performance."]
}
```

A Markdown report can also be rendered for review.

## Command

```bash
python scripts/run_adjusted_ohlc_fixture_roundtrip_engine.py --preparation-json reports/reviewed_evidence/backtest_input_preview.json --fixture-signal-json reports/reviewed_evidence/fixture_signal_preview.json --fixture-metrics-json reports/reviewed_evidence/fixture_metrics.json --symbols FPT,VNM,VCB --output-json reports/reviewed_evidence/fixture_roundtrip.json --output-md reports/reviewed_evidence/fixture_roundtrip.md
```

## Boundaries

- no Backtrader;
- no optimizer;
- no full VN100;
- no DB mutation;
- no live data fetch;
- no profitability or risk-performance metrics;
- no investment advice;
- no production-readiness claim.

## Next Safe Step

PR #53 adds fixture cost/slippage bps-units diagnostics over these transition
counts. It is not PnL, returns, strategy performance, Backtrader, an optimizer,
full VN100, or investment advice, and intentionally avoids price multiplication
and trade lists. After PR #53, mentor review is required before any real
adjusted-basis engine integration.
