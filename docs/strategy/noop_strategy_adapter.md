---
title: noop_strategy_adapter
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# No-Op Strategy Adapter

The no-op adapter verifies interface wiring. It requires an approved contract
and a matching prepared adjusted-OHLC input, then emits one `NO_SIGNAL` intent
per input row with reason `noop_adapter_interface_only`.

It contains no entry/exit strategy logic and computes no fills, trades, PnL,
equity, returns, or performance metrics. Its output is not a strategy result,
recommendation, Backtrader run, or investment advice.
