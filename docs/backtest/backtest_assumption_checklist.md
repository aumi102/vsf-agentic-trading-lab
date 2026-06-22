---
title: backtest_assumption_checklist
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Backtest Assumption Checklist

Use this checklist to record and review the explicit assumptions behind any
adjusted OHLC backtest dry-run before a Backtrader research scaffold is built.
It is a review aid only. It is not production readiness and not investment
advice.

## Required Assumptions

- [ ] **Adjusted OHLC source:** feed preview uses `source_price_basis=adjusted_ohlc`
  and `feed_contract_version=adjusted_ohlc_feed_v1` from PR #48.
- [ ] **Transaction cost (bps):** explicit, non-negative, and researched.
- [ ] **Slippage (bps):** explicit and non-negative.
- [ ] **Exchange band:** slippage within the exchange daily price band
  - HOSE/HSX: `<= 700 bps` (+/-7%);
  - UPCoM: `<= 1500 bps` (+/-15%).
- [ ] **Symbol universe:** explicit small symbol set (for example `FPT,VNM,VCB`);
  full VN100 remains blocked.
- [ ] **Date range:** explicit ISO `YYYY-MM-DD` with `start_date <= end_date`.

## Caveats To Disclose

- [ ] **Liquidity:** thin symbols may not fill at assumed slippage.
- [ ] **Corporate actions:** unresolved adjustment status distorts returns.
- [ ] **Survivorship:** current VN100 membership introduces survivorship bias.
- [ ] **No look-ahead:** signals must not use future bars.

## Boundaries

- No live trading.
- No broker execution.
- No investment advice.
- No production readiness claim.
