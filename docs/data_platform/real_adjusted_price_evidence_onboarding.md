---
title: real_adjusted_price_evidence_onboarding
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Real Adjusted Price Evidence Onboarding

## Purpose

This workflow lets the user place manually obtained reviewed adjusted-price
evidence for `FPT,VNM,VCB` in an ignored local directory, generate a SHA-256
manifest, validate the package, and save a QA report without committing real
market data.

It does not fetch live data, scrape sources, crawl VN100, mutate a production
DB, or run Backtrader.

## Local Directory Convention

Use ignored local paths:

```text
data/reviewed_evidence/adjusted_price/FPT_VNM_VCB/
  payload.json or payload.csv
  manifest.json
reports/reviewed_evidence/
  validation_report.json
  package_qa_report.json
```

Do not commit files under `data/reviewed_evidence/` or
`reports/reviewed_evidence/`.

## Manifest Generation

Create a manifest from a local reviewed payload:

```bash
python scripts/create_reviewed_adjusted_price_manifest.py --payload data/reviewed_evidence/adjusted_price/FPT_VNM_VCB/payload.json --source-id vendor:reviewed_adjusted_price --reviewer your_name --reviewed-at 2026-06-19 --evidence-basis adjusted_price_vendor_export --raw-path payload.json --output data/reviewed_evidence/adjusted_price/FPT_VNM_VCB/manifest.json
```

For development-only fixtures, use `manual_curated_for_dev_only` with
`--not-real-market-data`.

## Package Validation

Run dry-run validation and save reports only when explicitly requested:

```bash
python scripts/validate_reviewed_adjusted_price_package.py --package-dir data/reviewed_evidence/adjusted_price/FPT_VNM_VCB --symbols FPT,VNM,VCB --validation-output reports/reviewed_evidence/validation_report.json --factor-output reports/reviewed_evidence/factors.json
```

Execute mode is optional and must use an explicit local DB path:

```bash
python scripts/validate_reviewed_adjusted_price_package.py --package-dir data/reviewed_evidence/adjusted_price/FPT_VNM_VCB --symbols FPT,VNM,VCB --validation-output reports/reviewed_evidence/validation_report.json --factor-output reports/reviewed_evidence/factors.json --db-path path/to/local.sqlite --execute
```

## Gates

- Payload hash must match `manifest.payload_sha256`.
- Manifest must include source, raw path, reviewer, review date, evidence
  basis, and SHA-256.
- Raw close must never be treated as adjusted close.
- No `factor=1` fallback is created.
- Backtrader/VN100 remains blocked until reviewed evidence passes and adjusted
  readiness passes.

## Next Step

Run real FPT/VNM/VCB evidence through dry-run validation and inspect the report
before any execute-mode population or Backtrader work.
