---
title: first_backtest_strategy_scope
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# First Backtest Strategy Scope

## Included After Mentor Approval

- one selected deterministic strategy;
- explicit FPT/VNM/VCB or another approved small symbol set;
- adjusted OHLC only with readiness and provenance gates;
- one frozen parameter set and execution convention;
- research report output with assumptions and caveats.

## Excluded

- full VN100;
- optimizer, grid search, or parameter sweep;
- live data fetch, broker connection, or live trading;
- production-readiness or profitability claim;
- investment advice.

PR #55 only prepares the contract foundation. A later PR may implement one
mentor-approved strategy adapter over the adjusted OHLC feed.

The no-op adapter preview is interface-only and does not satisfy this strategy
implementation step. It emits no real signal logic or performance result.
