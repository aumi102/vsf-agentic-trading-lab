---
title: candidate_adapter_contracts
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Candidate Adapter Contracts

These are planning notes for mentor review. No final strategy is chosen here.
Every candidate requires a mentor-approved contract over adjusted OHLC, with
rules frozen before implementation. Entry/exit rules below are placeholders.

## `moving_average`

- Contract fields: lookbacks (fast/slow), entry/exit cross rule, execution price.
- Feature inputs: adjusted close history; adjusted OHLC for later fills.
- Entry/exit placeholders: prior close crosses prior MA(fast) vs MA(slow).
- Lookahead risk: indicators must exclude the execution bar when required.
- Mentor questions: which lookbacks, long-only vs long/flat, rebalance cadence?

## `momentum`

- Contract fields: lookback window, threshold or rank rule.
- Feature inputs: trailing adjusted returns.
- Entry/exit placeholders: enter on positive trailing return above threshold.
- Lookahead risk: future close must not leak into the signal.
- Mentor questions: lookback length, threshold vs cross-sectional rank?

## `breakout`

- Contract fields: range lookback, breakout level, exit rule.
- Feature inputs: adjusted high/low/close over prior range.
- Entry/exit placeholders: enter when adjusted close exceeds prior range high.
- Lookahead risk: the current-bar range cannot be treated as prior information.
- Mentor questions: range length, confirmation rule, stop placement?

## `mean_reversion`

- Contract fields: mean lookback, deviation band, exit rule.
- Feature inputs: trailing adjusted mean and bands.
- Entry/exit placeholders: enter when adjusted close is below the lower band.
- Lookahead risk: bands must use available history only.
- Mentor questions: lookback, band width, trend filter to avoid trends?

## `noop`

- Contract fields: existing approved-contract schema.
- Behaviour: emits `NO_SIGNAL` intents only; interface preview, not a strategy.
