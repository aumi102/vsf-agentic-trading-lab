---
title: mentor_call_brief_2026_06_22
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Mentor Call Brief — 2026-06-22

A short brief for the live call. The product is an agent/tool system; backtesting
is one gated module. Nothing here is investment advice.

## Current Status

- Adjusted-OHLC safety gates, evidence intake, and readiness checks are in place.
- The adjusted-OHLC backtest **feed contract** maps validated full OHLC only.
- Research **dry-run preparation** validates cost/slippage assumptions.
- Fixture diagnostics (signal, metrics, round-trip, cost) are deterministic and
  emit no performance numbers.
- A machine-readable **strategy contract validator** gates strategy work.
- A read-only **strategy adapter registry** lists candidate families.
- The **family enablement gate** allows only `noop` today and blocks real
  families until mentor approval.

## Ready to Demo

- local mentor dashboard: `python scripts/run_mentor_demo_ui.py`;
- live demo package and call documents;
- adjusted OHLC safety gates;
- adjusted OHLC feed contract;
- research dry-run preparation;
- fixture diagnostics;
- strategy contract template and validator;
- strategy adapter registry;
- noop adapter gate and blocked behavior for real families.

## Intentionally Blocked

- real Backtrader integration;
- full VN100 run;
- strategy optimizer / grid search;
- live trading or broker execution;
- any performance / profitability claim.

## Suggested Live Demo Route

1. Start the [local mentor demo UI](./mentor_demo_ui_runbook.md).
2. Use this brief as the call outline.
3. Open `docs/reports/progress_report.md` only if more detail is needed.
4. Validate the pending strategy contract template in the dashboard.
5. Show the registry, noop preview, and blocked real-family behavior.
6. Ask the mentor to choose the first strategy family and contract assumptions.

## Decisions Needed From Mentor

- select the first strategy **family**;
- decide the **universe** (small-symbol research first);
- decide the **execution price** convention;
- decide **transaction cost** and **slippage** assumptions
  (HOSE/HSX ≤ 700 bps, UPCoM ≤ 1500 bps);
- decide **rebalance** cadence and **risk** rules.

After selection, a later PR enables exactly one family and a contract is filled
and validated before any real adapter is implemented.

## Files to Upload to the Vin Folder

- **Primary:** `docs/mentor/mentor_call_brief_2026_06_22.md` (this file).
- **Optional second file:** `docs/reports/progress_report.md`.

Detailed docs stay in the repository and can be opened live during the call. Do
**not** upload raw data, secrets, credentials, database files, or build/temp
artifacts.
