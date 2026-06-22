---
title: live_system_demo_runbook
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Live System Demo Runbook

## Prerequisites

- clean `main` or the reviewed demo branch;
- Python dependencies and website dependencies installed;
- no network fetch enabled;
- optional local reviewed-evidence inputs under ignored paths;
- FPT/VNM/VCB only for the adjusted-basis fixture flow.

Confirm state:

```bash
git status --short
git log --oneline -5
python scripts/list_mentor_demo_package.py
```

## Baseline Validation

```bash
python -m pytest
cd website
cmd.exe /c npm run build
cd ..
python scripts/run_mentor_demo_suite.py
```

## Adjusted-Basis Demo Flow

The following commands are templates unless their local DB/audit/JSON inputs
exist. Missing inputs should produce or be explained as explicit blocked states;
never substitute raw OHLC as adjusted trading prices.

For the call, prefer showing blocked states honestly over fabricating demo
inputs. Every command below that depends on ignored/local inputs is template-only.

```bash
python scripts/preview_adjusted_ohlc_backtest_feed.py --db-path path/to/local.sqlite --symbols FPT,VNM,VCB --start-date 2026-01-01 --end-date 2026-12-31 --audit-report reports/reviewed_evidence/adjusted_ohlc_audit.json --output-json reports/reviewed_evidence/feed_preview.json
python scripts/prepare_adjusted_ohlc_backtest_dry_run.py --feed-preview reports/reviewed_evidence/feed_preview.json --symbols FPT,VNM,VCB --start-date 2026-01-01 --end-date 2026-12-31 --transaction-cost-bps 15 --slippage-bps 10 --exchange HOSE --output-json reports/reviewed_evidence/backtest_input_preview.json
python scripts/run_adjusted_ohlc_fixture_signal_dry_run.py --preparation-json reports/reviewed_evidence/backtest_input_preview.json --symbols FPT,VNM,VCB --signal-mode all_cash --output-json reports/reviewed_evidence/fixture_signal_preview.json --output-md reports/reviewed_evidence/fixture_signal_preview.md
python scripts/report_adjusted_ohlc_fixture_metrics.py --fixture-signal-json reports/reviewed_evidence/fixture_signal_preview.json --symbols FPT,VNM,VCB --output-json reports/reviewed_evidence/fixture_metrics.json --output-md reports/reviewed_evidence/fixture_metrics.md
python scripts/run_adjusted_ohlc_fixture_roundtrip_engine.py --preparation-json reports/reviewed_evidence/backtest_input_preview.json --fixture-signal-json reports/reviewed_evidence/fixture_signal_preview.json --fixture-metrics-json reports/reviewed_evidence/fixture_metrics.json --symbols FPT,VNM,VCB --output-json reports/reviewed_evidence/fixture_roundtrip.json --output-md reports/reviewed_evidence/fixture_roundtrip.md
python scripts/report_adjusted_ohlc_fixture_cost_diagnostics.py --preparation-json reports/reviewed_evidence/backtest_input_preview.json --roundtrip-json reports/reviewed_evidence/fixture_roundtrip.json --symbols FPT,VNM,VCB --output-json reports/reviewed_evidence/fixture_cost_diagnostics.json --output-md reports/reviewed_evidence/fixture_cost_diagnostics.md
```

## What Mentor Should See

- full adjusted OHLC is mandatory and provenance-gated;
- raw OHLC remains evidence, never an adjusted trading price;
- assumptions and exchange bands are explicit;
- failures are visible blocked states;
- fixture outputs make no PnL, return, equity, or performance claim;
- strategy rules remain pending joint review.
