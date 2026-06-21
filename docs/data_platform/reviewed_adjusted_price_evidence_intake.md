---
title: reviewed_adjusted_price_evidence_intake
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Reviewed Adjusted Price Evidence Intake

## Purpose

This intake layer is the controlled step after the synthetic smoke. It accepts
reviewed local adjusted-price evidence for the explicit `FPT,VNM,VCB` set,
validates reviewer/provenance metadata, derives factor records, optionally
applies them to a local SQLite DB, and reports adjusted OHLC readiness.

It does not fetch live data, crawl VN100, run Backtrader, or mutate production
adjusted OHLC.

## Manifest Contract

`configs/ingestion/reviewed_adjusted_price_evidence_mvp.json` defines the MVP
contract: max 3 symbols, JSON/CSV local inputs, required price fields, and
required metadata.

Each reviewed manifest must include:

- `source_id`;
- `raw_path`;
- `reviewer`;
- `reviewed_at`;
- `evidence_basis`;
- `payload_sha256`.

Accepted evidence basis values are `adjusted_price_vendor_export`,
`corporate_action_derived`, and `manual_curated_for_dev_only`.
`reviewed_at` must be ISO date `YYYY-MM-DD`. If `evidence_basis` is
`manual_curated_for_dev_only`, the manifest must also include
`not_real_market_data=true`.

## Payload Rules

Payload rows must include `symbol`, `trade_date`, `close`, and
`adjusted_close`. The intake supports JSON list/object-with-`data` and CSV with
headers.

The intake computes SHA-256 from the exact local payload bytes and compares it
with `manifest.payload_sha256` before factor generation. Hash mismatches fail
cleanly and do not write factor output or mutate a DB.

The intake rejects missing/non-positive prices, missing reviewed metadata,
invalid payload hashes, more than three symbols, unsupported evidence basis, and
raw-close-as-adjusted-close rows. It does not create a `factor=1` fallback.

## Command

```bash
python scripts/run_reviewed_adjusted_price_evidence_intake.py --manifest tests/fixtures/adjustment_factors/reviewed_adjusted_price_manifest.json --payload path/to/reviewed_payload.json --symbols FPT,VNM,VCB --validation-output .pytest_tmp/reviewed_validation.json --factor-output .pytest_tmp/reviewed_factors.json --dry-run
```

Execute mode requires an explicit local DB path:

```bash
python scripts/run_reviewed_adjusted_price_evidence_intake.py --manifest path/to/manifest.json --payload path/to/reviewed_payload.csv --symbols FPT,VNM,VCB --validation-output .pytest_tmp/reviewed_validation.json --factor-output .pytest_tmp/reviewed_factors.json --db-path .pytest_tmp/reviewed.sqlite --execute
```

Execute mode is successful only when adjusted readiness returns `status=ok` and
`backtest_gate=pass`.

The validation report includes a `manifest_integrity` object with source ID,
raw path, reviewer, review date, evidence basis, expected/computed payload
SHA-256, hash-match status, and `not_real_market_data` when present.

## Package QA

`docs/data_platform/reviewed_adjusted_price_evidence_package_qa.md` documents
the package-level smoke that runs JSON dry-run, CSV dry-run, temporary-DB
execute, and readiness against a synthetic reviewed evidence package.

## Real Evidence Onboarding

`docs/data_platform/real_adjusted_price_evidence_onboarding.md` documents the
local-only workflow for manually obtained FPT/VNM/VCB evidence. It keeps real
payloads and generated reports under ignored paths, creates a manifest with the
payload SHA-256, and runs dry-run validation before any execute-mode population.

## Boundaries

- Reviewed local evidence only.
- No live fetch.
- No full VN100.
- No Backtrader.
- No Docker/scheduler.
- No production-readiness or investment-advice claim.
