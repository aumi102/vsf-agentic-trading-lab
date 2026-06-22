---
title: live_demo_index
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Mentor Live Demo Index

## Purpose

This is the single entry point for the mentor call. The product is an
agent/tool system; backtesting is one gated module. The call should review the
live system and jointly decide the first real adjusted-basis strategy contract.

## Current Status

Implemented: cached-data agent demo, adjusted-price evidence gates, adjusted
OHLC feed contract, dry-run preparation, fixture signal/metrics, fixture
round-trip diagnostics, and fixture cost/slippage bps-units diagnostics.
PR #55 adds a machine-readable strategy contract validator and mentor decision
materials. The template remains pending and blocks real backtesting.

Intentionally blocked: real Backtrader execution, strategy optimization, full
VN100, production scheduling, broker execution, live trading, and investment
advice.

## Live Demo Route

1. Review [current status](./current_system_status_for_call.md).
2. Follow the [live runbook](./live_system_demo_runbook.md).
3. Review the [backtest/strategy agenda](./backtest_strategy_review_agenda.md).
4. Record decisions in the [strategy template](./strategy_decision_template.md).
5. Confirm the [readiness checklist](./backtest_readiness_checklist.md).
6. Close the open [mentor questions](./mentor_questions.md).
7. Fill and validate `docs/strategy/examples/strategy_contract_template.json`.

## Docs and Reports

Repository documentation is under `docs/`; committed reports are under
`docs/reports/`. Use the [Vin upload manifest](./vin_folder_upload_manifest.md)
and `python scripts/list_mentor_demo_package.py` to list the package.

## Latest PR Chain

- adjusted evidence/readiness: PRs #37–#47;
- adjusted feed contract: PR #48;
- dry-run preparation: PR #49;
- fixture signal: PR #50;
- fixture metrics: PR #51;
- fixture round-trip engine: PR #52;
- fixture cost/slippage diagnostics: PR #53.

## Decision Required

The next implementation depends on mentor agreement about baseline strategy,
universe, execution timing, costs, rebalance frequency, and risk rules. No
strategy logic is finalized by this package.
After approval, the next PR may implement one strategy adapter over adjusted
OHLC; optimizer and full VN100 remain blocked.
