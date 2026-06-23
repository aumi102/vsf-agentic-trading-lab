# Vietcap IQ financial report ingestion

This pipeline loads Vietcap IQ financial statements into QuestDB without touching OHLCV ingestion or `daily_prices`.

## Tables

Financial report facts use long/narrow tables:

- `fa_balance_sheet`
- `fa_income_statement`
- `fa_cash_flow`
- `fa_notes`

Each fact row is one symbol, one reporting period, and one metric. Core columns:

- `public_date`
- `security_id`
- `symbol`
- `statement_type`
- `period_type`
- `fiscal_year`
- `fiscal_quarter`
- `period_end_date`
- `metric_code`
- `metric_name`
- `metric_value`
- `metric_value_raw`
- `currency`
- `unit`
- `source`
- `run_id`
- `raw_payload_ref`
- `quality_status`

Supporting tables:

- `fa_raw_payloads`: raw payload evidence metadata and cache references.
- `fa_ingest_runs`: one or more rows per ingest run for started/final run state.

## Run tracking

`fa_ingest_runs` records:

- `run_id`
- scope (`explicit_symbols` or `limit_symbols`)
- symbol and statement scope
- replace mode
- final status (`complete`, `partial`, or `failed`)
- per-table row counts
- raw payload count
- failure count and JSON failure details

The financial report query tools prefer the latest `status='complete'` run. If the run table is unavailable or no complete run exists, tools fall back to querying all rows and return a caveat that duplicate append rows may be included.

## Replace modes

`scripts/ingest_vietcap_financial_reports_to_questdb.py` supports:

- `--replace-mode run` (default): append a new `run_id`. Query tools scope reads to the latest complete run, reducing duplicate-answer risk without deleting older evidence.
- `--replace-mode append`: append rows without any query-side de-duplication guarantee. This is retained for debugging and prints a duplicate-risk warning.
- `--replace-mode table --allow-table-replace`: drop and recreate only FA tables:
  - `fa_balance_sheet`
  - `fa_income_statement`
  - `fa_cash_flow`
  - `fa_notes`
  - `fa_raw_payloads`
  - `fa_ingest_runs`

`daily_prices`, derived market tables, and OHLCV ingestion state are never touched by this script.

## Smoke command

```bat
python scripts\ingest_vietcap_financial_reports_to_questdb.py --symbols FPT,VNM,VCB --statements balance_sheet,income_statement,cash_flow,notes --replace-mode table --allow-table-replace
python scripts\questdb_fa_status.py
python scripts\demo_agent_backend_cli.py "financial report FPT"
```

## Tiny scale check

```bat
python scripts\ingest_vietcap_financial_reports_to_questdb.py --limit-symbols 5 --statements balance_sheet,income_statement,cash_flow,notes --replace-mode table --allow-table-replace
python scripts\questdb_fa_status.py
```

Do not run full-universe FA ingestion until the small-scope behavior is accepted.

## Caveats

- Metric mapping is currently marked `metric_mapping_unverified`.
- `fa_notes` metric semantics can be opaque and should be treated as raw metric-code evidence until mapping is hardened.
- Vietcap `publicDate` point-in-time semantics remain a data-quality caveat.
- Full-universe financial report ingestion has not been run yet.
