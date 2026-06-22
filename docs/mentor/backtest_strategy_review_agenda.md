---
title: backtest_strategy_review_agenda
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Backtest and Strategy Review Agenda

## 1. Data and Readiness

Review small-symbol coverage, reviewed evidence, adjusted OHLC readiness,
blocked states, and whether the demo inputs are sufficient for a first research
run.

## 2. Adjusted OHLC and Provenance

Confirm full OHLC adjustment, factor provenance, corporate-action handling,
and the rule that raw OHLC cannot drive adjusted-basis signals or fills.

## 3. Backtest Assumptions

Decide transaction-cost bps, slippage bps, exchange band (HOSE/HSX ≤700;
UPCOM ≤1500), date range, initial symbol universe, and missing-data policy.

## 4. Strategy Design With Mentor

Compare simple baseline options: momentum, moving-average, breakout, mean
reversion, or another rule-based baseline. Freeze entry/exit rules, signal and
rebalance frequency, execution-price assumption, risk stop, position sizing,
and maximum holding period before implementation.

## 5. Remaining Blocks

No real Backtrader integration, optimizer, full VN100, production scheduler,
broker execution, live trading, or profitability claim is authorized yet.

## 6. Decisions Needed

Complete the strategy decision template and readiness checklist. Record rejected
options and unresolved assumptions, not only the selected option.

## 7. Candidate Next PRs

1. mentor-approved small-symbol strategy contract;
2. gated Backtrader research scaffold over adjusted OHLC;
3. deterministic baseline tests and execution-convention tests;
4. only later, separately reviewed universe expansion or optimization.
