---
title: real_adjusted_price_local_execute_readiness
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Real Adjusted Price Local Execute Readiness

## Purpose

This workflow applies a reviewed adjusted-price evidence package only to an
explicit temporary/local SQLite DB, runs adjusted OHLC readiness, and writes a
Markdown execution-readiness report.

It is not production DB population and not Backtrader.

## Preconditions

- Dry-run report passed.
- If `--require-dry-run-report` is used, the runner validates the Markdown
  report content, not only that the file exists.
- Reviewed package validation passed.
- Explicit local SQLite DB is prepared.
- Output paths are explicit.
- Real evidence files remain under ignored local paths.

## Command

```bash
python scripts/run_reviewed_adjusted_price_local_execute_readiness.py --package-dir data/reviewed_evidence/adjusted_price/FPT_VNM_VCB --symbols FPT,VNM,VCB --db-path path/to/local.sqlite --factor-output reports/reviewed_evidence/factors_execute.json --validation-output reports/reviewed_evidence/execute_validation.json --readiness-output reports/reviewed_evidence/readiness.json --report-md reports/reviewed_evidence/execute_readiness_report.md --require-dry-run-report reports/reviewed_evidence/package_qa_report.md
```

## Pass Criteria

- Validation status is `ok`.
- Execute mode reports `db_mutation_made=true`.
- Adjusted readiness status is `ok`.
- `backtest_gate=pass`.
- Markdown report is written.
- The Markdown report decision is `READY_FOR_LOCAL_REVIEW_ONLY`.

## Failure Cases

- Missing explicit DB path.
- Demo DB path is used without explicit override.
- Required dry-run report is missing, stale, not `ok`, or lacks the Backtrader
  block warning.
- Package validation fails.
- If validation fails before DB mutation, readiness is skipped and the readiness
  JSON records `status=skipped`.
- Reviewed package does not cover all requested DB rows.
- Adjusted readiness is not `ok`.

## Boundaries

- No live fetch.
- No full VN100.
- No production/demo DB by default.
- No Backtrader.
- No Docker/scheduler.

After this passes for a small explicit local DB, the next step is an adjusted
OHLC execution audit/inspection report, not full VN100 or Backtrader execution.
