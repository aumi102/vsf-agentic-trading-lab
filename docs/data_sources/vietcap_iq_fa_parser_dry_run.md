---
title: vietcap_iq_fa_parser_dry_run
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Vietcap IQ FA Parser Dry-Run

## Scope

| Field | Value |
|---|---|
| Review date | 2026-06-09 |
| Script | `scripts/parse_vietcap_iq_fa_payloads_dry_run.py` |
| Input | Saved `fa-direct` payloads under `data/raw/httpx_diagnostic/source=vietcap_iq/` |
| Output | `data/processed/fa_dry_run/` (local CSV + report only) |
| Guardrails | No DB write, no backtest, no live network, no full-universe fetch |

---

## Input Payloads

Three saved payloads from previous `fa-direct` diagnostics were parsed:

| run_id | symbol | section | Q rows | Y rows | metric cols |
|---|---|---|---:|---:|---:|
| `20260609T035318Z` | `VCI` | `BALANCE_SHEET` | 33 | 8 | 331 |
| `20260609T075846Z` | `VCI` | `INCOME_STATEMENT` | 33 | 8 | 181 |
| `20260609T075857Z` | `FPT` | `BALANCE_SHEET` | 33 | 8 | 331 |

---

## Parser Command

```
python scripts/parse_vietcap_iq_fa_payloads_dry_run.py \
  --run-id 20260609T035318Z \
  --run-id 20260609T075846Z \
  --run-id 20260609T075857Z
```

---

## Output Summary

| Metric | Count |
|---|---:|
| Total fact rows | 34,563 |
| `value_status=present` | 8,695 |
| `value_status=zero` | 23,885 |
| `value_status=missing` (null) | 1,983 |
| Parse errors | 0 |

Output files:
- `data/processed/fa_dry_run/financial_statement_facts.csv`
- `data/processed/fa_dry_run/financial_statement_parse_report.md`

---

## Long-Format Schema

Each output row represents one `(period, metric_code)` cell from the source wide-format payload.

Key columns:

| Column | Description |
|---|---|
| `source_name` | `vietcap_iq` |
| `symbol` | Stock ticker |
| `organ_code` | Source `organCode` field |
| `statement_type` / `section` | FA section (e.g. `BALANCE_SHEET`) |
| `period_type` | `quarter` or `year` |
| `fiscal_year` | `yearReport` integer |
| `fiscal_quarter` | 1–4 for quarters; empty for annual |
| `length_report` | Raw `lengthReport` value |
| `source_period_label` | e.g. `2025Q4`, `2025Y` |
| `public_date` | Copied from `publicDate` row field |
| `public_date_semantics` | `candidate_availability_publication_date_unconfirmed` |
| `line_item_code` | Opaque metric code (e.g. `bsa1`, `isa25`) |
| `line_item_name` | Empty — no name mapping available |
| `value` | Numeric value, or empty for null |
| `value_status` | `present`, `zero`, or `missing` |
| `availability_status` | `unknown_until_publicDate_validated` |
| `parser_warning` | Pipe-separated warning codes |

---

## publicDate Coverage

`publicDate` is present and non-null for all 41 rows (33 quarterly + 8 annual) in all three payloads.

| run_id | Q publicDate non-null | Y publicDate non-null |
|---|---:|---:|
| `20260609T035318Z` (VCI BS) | 33/33 | 8/8 |
| `20260609T075846Z` (VCI IS) | 33/33 | 8/8 |
| `20260609T075857Z` (FPT BS) | 33/33 | 8/8 |

---

## Key Findings

### null vs zero distinction preserved

- `value_status=missing` (1,983 rows): metric cell is null in the source — indicates the line item does not apply for this company type (e.g., `nos*` columns for FPT)
- `value_status=zero` (23,885 rows): metric cell is numeric zero — line item exists for this company type but had zero value this period
- `value_status=present` (8,695 rows): non-zero numeric value

The `nos*` group (off-balance-sheet securities notes) is the primary source of `missing` rows for FPT. This is expected — see `docs/data_sources/vietcap_iq_fa_shape_cross_check.md`.

### Line item names

Metric codes (`bsa1`, `isa25`, etc.) are opaque in the payload. The `line_item_name` column is empty for all rows. A separate mapping table or endpoint is needed before the output can be used for analysis.

### organCode vs ticker

`organCode` differs from `ticker` for VCI (`organCode=VCSC`, `ticker=VCI`). The `organCode_ticker_differ` warning is emitted for all VCI rows. `organCode=FPT`, `ticker=FPT` for FPT — no warning.

---

## Parser Warnings (per fact row)

| Warning code | Meaning |
|---|---|
| `line_item_name_unknown_no_mapping` | Metric code has no human-readable name in the payload |
| `publicDate_semantics_unconfirmed` | `publicDate` is present but exact semantics unconfirmed |
| `organCode_ticker_differ` | `organCode` ≠ `ticker` for this row |

---

## What Is Not Done

| Item | Status |
|---|---|
| DB write | **Not implemented** |
| Full-universe fetch | **Not implemented** |
| Backtest | **Not implemented** |
| Line item name mapping | **Not available** |
| `publicDate` PIT validation | **Not done** |
| Multi-section schema (CASH_FLOW etc.) | **Not probed** |

---

## PIT / Backtest Warning

> **`publicDate`** is present and non-null for all rows. It is a **candidate availability/publication field** only. Its exact semantics — whether it represents the exchange filing date, the auditor sign-off date, or the date Vietcap entered the data — have not been confirmed against authoritative filing records. Do not use this data for historical point-in-time backtest until `publicDate` semantics are confirmed.

---

## Next Steps

1. **Locate a line-item name mapping.** Check for a `/field-metadata` or `/template` endpoint. Without it, the long-format output contains only opaque codes.
2. **Confirm `publicDate` semantics.** Cross-reference one or two known VCI/FPT filing dates against exchange records before enabling PIT-aware use.
3. **Probe additional sections** (e.g., `CASH_FLOW`) using the same clean 8-header profile.
4. **No full-universe fetch, no DB write, no backtest** until name mapping and `publicDate` semantics are reviewed.
