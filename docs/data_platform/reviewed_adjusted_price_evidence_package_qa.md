---
title: reviewed_adjusted_price_evidence_package_qa
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Reviewed Adjusted Price Evidence Package QA

## Purpose

PR #42 added reviewed adjusted-price evidence intake. This package QA proves a
complete reviewed evidence package shape with synthetic development-only files:
`manifest.json`, `payload.json`, `payload.csv`, and `README.md`.

It does not fetch live data, crawl VN100, mutate production adjusted OHLC, run
Backtrader, or schedule ETL.

## Fixture Package

Default package:

```text
tests/fixtures/adjustment_factors/reviewed_evidence_package/
```

The package is marked `manual_curated_for_dev_only` and
`not_real_market_data=true`. `manifest.json` carries the SHA-256 for
`payload.json`; `raw_path` is package-relative so the fixture can be copied and
validated as a self-contained package. The QA script computes the CSV payload
hash and creates a temporary CSV manifest for parity validation.

## Command

```bash
python scripts/smoke_reviewed_adjusted_price_evidence_package.py
```

Expected status:

- JSON dry-run: `ok`;
- CSV dry-run: `ok`;
- JSON execute against temporary SQLite DB: `ok`;
- adjusted readiness: `status=ok`, `backtest_gate=pass`.

To test another local package:

```bash
python scripts/smoke_reviewed_adjusted_price_evidence_package.py --package-dir path/to/package
```

## Boundaries

- Synthetic/dev-only package.
- No live fetch.
- No full VN100.
- No production DB mutation.
- No Backtrader.
- No Docker/scheduler.

Next, use `docs/data_platform/real_adjusted_price_evidence_onboarding.md` to
place real reviewed FPT/VNM/VCB evidence under ignored local paths, generate the
SHA-256 manifest, and save a QA report without committing real data. Backtrader
remains blocked until reviewed real evidence and adjusted readiness pass.
