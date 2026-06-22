---
title: backtest_readiness_checklist
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Backtest Readiness Checklist

- [ ] Machine-readable strategy contract exists, validates, and is mentor-approved.
- [ ] Adjusted OHLC readiness passes for every requested symbol and row.
- [ ] Raw OHLC is retained as evidence and not used as trading price.
- [ ] Adjustment factor/source/raw-path/method provenance is present.
- [ ] Every requested symbol is represented after date and row limits.
- [ ] Date range is explicit and valid.
- [ ] Transaction-cost bps is explicit and non-negative.
- [ ] Slippage bps is explicit, non-negative, and within the exchange band.
- [ ] Strategy entry, exit, rebalance, execution, sizing, and risk rules are frozen before the run.
- [ ] Signal and execution timing prevent lookahead.
- [ ] Universe policy is defined; no survivorship claim is made otherwise.
- [ ] No performance claim is made without validated metrics and assumptions.
- [ ] Outputs include data, execution, universe, and research caveats.
- [ ] Scope remains small-symbol; full VN100 and optimization require later approval.
- [ ] Output is labeled research-only and not investment advice.

Any unchecked gate blocks the real adjusted-basis backtest.
After approval, implement one strategy adapter only; optimizer and full VN100
remain outside scope.
