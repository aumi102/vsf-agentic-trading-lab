---
title: strategy_validation_gates
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Strategy Validation Gates

- [ ] Contract exists, validates, and has mentor status `approved`.
- [ ] Full adjusted OHLC input and provenance are ready.
- [ ] Raw OHLC is not used as strategy or execution price.
- [ ] Every requested symbol survives date and row filters.
- [ ] Features use no future data and execution has no lookahead.
- [ ] Transaction cost and slippage are explicit and non-negative.
- [ ] Slippage is within HOSE/HSX 700-bps or UPCOM 1500-bps band.
- [ ] Entry, exit, rebalance, execution, sizing, and risk rules are frozen.
- [ ] Outputs include assumptions, data limitations, universe caveats, and
  `not_financial_advice=true`.
- [ ] Results are called research results, never production readiness or advice.

Any failed gate blocks the first real adjusted-basis run.
