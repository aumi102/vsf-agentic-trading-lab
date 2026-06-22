---
title: noop_strategy_adapter
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# No-Op Strategy Adapter

The no-op adapter verifies interface wiring. It requires an approved contract
whose `strategy_family` is enabled in the registry (only `noop` today) and a
matching prepared adjusted-OHLC input, then emits one `NO_SIGNAL` intent per
input row with reason `noop_adapter_interface_only`. A contract naming any other
family blocks at the
[enablement gate](./strategy_family_enablement_gate.md) with
`strategy_family_not_enabled:<family>`.

It contains no entry/exit strategy logic and computes no fills, trades, PnL,
equity, returns, or performance metrics. Its output is not a strategy result,
recommendation, Backtrader run, or investment advice.
