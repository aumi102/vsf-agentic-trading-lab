---
title: adjusted_ohlc_execution_audit
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Adjusted OHLC Execution Audit

## Purpose

Run this after reviewed adjusted-price local execute readiness. It inspects the
explicit local SQLite DB and confirms adjusted OHLC rows, provenance, factor
consistency, and readiness report status before any backtest integration
planning.

The audit is read-only. It does not fetch data, mutate the DB, run Backtrader,
or approve full VN100 execution.

## Command

```bash
python scripts/audit_adjusted_ohlc_execution.py --db-path path/to/local.sqlite --symbols FPT,VNM,VCB --factor-records reports/reviewed_evidence/factors_execute.json --validation-report reports/reviewed_evidence/execute_validation.json --readiness-report reports/reviewed_evidence/readiness.json --output-json reports/reviewed_evidence/adjusted_ohlc_audit.json --output-md reports/reviewed_evidence/adjusted_ohlc_audit.md
```

## Pass Criteria

- DB exists and an explicit symbol set is provided.
- Requested symbols have daily price rows.
- Adjusted open, high, low, and close are populated.
- Adjustment source, raw path, and method provenance are present.
- Adjusted OHLC is internally consistent.
- If factor records are provided, adjusted OHLC equals raw OHLC multiplied by
  the reviewed factor within tolerance.
- Validation report is `ok` and shows `db_mutation_made=true`.
- Readiness report is `ok` and `backtest_gate=pass`.

## Failure Cases

- Missing DB or missing explicit symbols.
- Demo DB path without explicit override.
- Missing adjusted OHLC or provenance.
- Factor mismatch or missing factor record.
- Validation or readiness report is missing, failed, or stale.

## Boundaries

- No DB mutation.
- No live fetch.
- No production/demo DB by default.
- No full VN100.
- No Backtrader.
- No Docker/scheduler.

If this audit passes for FPT/VNM/VCB, the next step is small-symbol adjusted
OHLC backtest integration planning, not full VN100 execution.
