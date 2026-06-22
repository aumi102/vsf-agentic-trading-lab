---
title: vin_folder_upload_manifest
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Vin Folder Upload Manifest

## Repository Docs

| File | Status |
|---|---|
| `docs/architecture/02_trading_agent_architecture_overview.md` | `ready_to_upload` |
| `docs/demo/vsf_mentor_db_ingestion_backtest_handoff.md` | `ready_to_upload` |
| `docs/backtest/adjusted_ohlc_backtest_requirement.md` | `ready_to_upload` |
| `docs/backtest/adjusted_ohlc_backtest_feed_contract.md` | `ready_to_upload` |
| `docs/backtest/adjusted_ohlc_feed_to_backtest_dry_run.md` | `ready_to_upload` |
| `docs/backtest/adjusted_ohlc_fixture_signal_dry_run.md` | `ready_to_upload` |
| `docs/backtest/adjusted_ohlc_fixture_metrics_report.md` | `ready_to_upload` |
| `docs/backtest/adjusted_ohlc_fixture_roundtrip_engine.md` | `ready_to_upload` |
| `docs/backtest/adjusted_ohlc_fixture_cost_diagnostics.md` | `ready_to_upload` |
| `docs/reports/progress_report.md` | `ready_to_upload` |

## Reports

| File or class | Status | Note |
|---|---|---|
| `docs/reports/progress_report.md` | `ready_to_upload` | Current source of truth. |
| `docs/reports/mentor_demo_report.md` | `ready_to_upload` | Demo/handoff report. |
| `docs/reports/backtest_mvp_demo_report.md` | `ready_to_upload` | Exploratory only; retain caveats. |
| reviewed evidence reports, if locally present | `external_only` | Ignored/generated; do not commit. |
| generated fixture JSON/Markdown reports | `external_only` | Upload only when intentionally generated for the call. |
| real raw market data | `blocked` | Do not upload unless explicitly allowed. |

Run `python scripts/list_mentor_demo_package.py` before upload. Do not upload
credentials, tokens, private paths, secrets, or unapproved raw data. Keep
generated reports outside Git. This package does not claim production readiness
or investment advice.
