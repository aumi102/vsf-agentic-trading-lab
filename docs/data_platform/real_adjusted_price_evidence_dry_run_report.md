---
title: real_adjusted_price_evidence_dry_run_report
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Real Adjusted Price Evidence Dry-Run Report

## Purpose

PR #44 added local onboarding for manually obtained reviewed FPT/VNM/VCB
adjusted-price evidence. This workflow turns the dry-run validation JSON into a
human-readable Markdown report before any execute-mode DB population.

It does not fetch live data, commit real evidence, mutate production/demo DBs,
or run Backtrader.

## Commands

1. Create the manifest:

```bash
python scripts/create_reviewed_adjusted_price_manifest.py --payload data/reviewed_evidence/adjusted_price/FPT_VNM_VCB/payload.json --source-id vendor:reviewed_adjusted_price --reviewer your_name --reviewed-at 2026-06-21 --evidence-basis adjusted_price_vendor_export --raw-path payload.json --output data/reviewed_evidence/adjusted_price/FPT_VNM_VCB/manifest.json
```

2. Validate the package in dry-run mode:

```bash
python scripts/validate_reviewed_adjusted_price_package.py --package-dir data/reviewed_evidence/adjusted_price/FPT_VNM_VCB --symbols FPT,VNM,VCB --validation-output reports/reviewed_evidence/validation_report.json --factor-output reports/reviewed_evidence/factors.json
```

3. Summarize the validation report:

```bash
python scripts/summarize_reviewed_adjusted_price_validation_report.py --validation-report reports/reviewed_evidence/validation_report.json --output-md reports/reviewed_evidence/package_qa_report.md --expected-symbols FPT,VNM,VCB --min-usable-records 3
```

4. Inspect `reports/reviewed_evidence/package_qa_report.md`.

## Pass Criteria

- Validation status is `ok`.
- Manifest integrity has `payload_sha256_match=true`.
- Expected symbols are present.
- Usable records meet the configured minimum.
- No invalid or missing records are reported.

## Fail Criteria

- Missing or invalid manifest.
- Payload SHA-256 mismatch.
- Missing expected symbols.
- Any raw-close-as-adjusted-close or `factor=1` fallback issue.
- Validation status other than `ok`.

## What To Send Back

Share the Markdown summary and the high-level source/reviewer/date metadata.
Do not send or commit real payload files unless explicitly requested through a
separate reviewed data process.

## Do Not

- Do not commit data under `data/reviewed_evidence/`.
- Do not commit generated reports under `reports/reviewed_evidence/`.
- Do not execute into production/demo DB.
- Do not run Backtrader until reviewed evidence and adjusted readiness pass.
