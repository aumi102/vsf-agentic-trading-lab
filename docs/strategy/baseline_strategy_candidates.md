---
title: baseline_strategy_candidates
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Baseline Strategy Candidates

These are candidates for mentor review, not selected strategies. Every candidate
requires adjusted OHLC and rules frozen before implementation.

| Candidate | Idea / adjusted inputs | Lookback and rule placeholders | Caveats / leakage risk |
|---|---|---|---|
| Moving-average crossover | Trend comparison using adjusted close; adjusted OHLC for later fills | fast/slow lookbacks; entry/exit pending mentor approval | Lag/whipsaw; indicators must exclude execution bar when required. |
| Momentum lookback | Rank or threshold trailing adjusted returns | lookback, threshold, entry/exit pending | Reversal risk; future close must not leak into signal. |
| Breakout | Compare adjusted high/close with prior range | range lookback and exit pending | False breakouts; current-bar range cannot become prior information. |
| Mean reversion | Compare adjusted close with trailing mean/bands | lookback, deviation, exits pending | Can fail in trends; bands must use available history only. |
| All-cash control | No position transitions | no feature lookback; no entry | Control only, not evidence of profitability. |

Mentor approval is needed to choose the family, exact lookbacks, rules,
execution convention, and risk behavior. This document intentionally selects
none of them.
