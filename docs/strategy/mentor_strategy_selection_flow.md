---
title: mentor_strategy_selection_flow
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Mentor Strategy Selection Flow

The flow from candidate families to a real signal-intent adapter, kept gated at
every step.

1. **Mentor selects a family** from the registry (`moving_average`, `momentum`,
   `breakout`, `mean_reversion`, or `noop`).
2. **Fill the strategy contract** with explicit decisions, replacing every
   pending/placeholder value.
3. **Validate the contract** and require `status=ok`.
4. **Enable exactly one candidate adapter** in a later PR by flipping its
   registry status; all other families stay disabled.
5. **Run the no-op / interface preview first** against the prepared adjusted-OHLC
   input to confirm wiring.
6. **Implement the real signal-intent adapter** only after mentor approval.
7. **Backtrader remains later and separately gated** — it is not part of family
   selection or the first real adapter.

No optimizer, no full VN100, no live fetch, no broker execution, no performance
claim, and no investment advice at any step.
