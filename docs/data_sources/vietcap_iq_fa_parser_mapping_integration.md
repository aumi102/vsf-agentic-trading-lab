# Vietcap IQ FA Parser Mapping Integration

**Status:** Dry-run complete. Resolver wired. New output columns verified against real payloads.
DB writes: blocked. Backtests: blocked. PIT semantics: not confirmed. Mapping gate: not complete.

---

## What changed

`scripts/parse_vietcap_iq_fa_payloads_dry_run.py` now accepts optional mapping CSV inputs and
enriches every long-format fact row with 7 new columns. No existing columns were removed.

When no mapping inputs are provided (original behavior), all 7 new columns are empty strings
and `mapping_status=""` (not one of the 6 resolver statuses). Existing tests pass unchanged.

---

## New output columns (appended after `line_item_name`)

| Column | Description |
|---|---|
| `line_item_name_en` | English name from primary or consensus_fallback mapping; empty otherwise |
| `line_item_name_vi` | Vietnamese name from primary mapping only; empty for consensus_fallback |
| `mapping_status` | One of 6 resolver statuses, or `""` when mapping not loaded (see below) |
| `mapping_source_symbol` | `"VCI"` (primary hit), `"union"` (consensus), or `""` |
| `mapping_source_run_id` | Run ID of primary mapping probe; `""` for union or no-mapping |
| `mapping_conflict` | `"true"` / `"false"` from union CSV; `""` for primary or no-mapping |
| `mapping_group` | Firm type group from firm-type plan (e.g. `securities`, `general`); `""` if unknown |

**Legacy column `line_item_name`:** always empty — never populated. Do not remove.

---

## Mapping status values

| Status | Meaning |
|---|---|
| `primary` | Code found in primary symbol's mapping CSV, section matched |
| `consensus_fallback` | Not in primary; found in union CSV with `conflict=false`, section matched |
| `conflict_skipped` | In union CSV but `conflict=true`; name suppressed |
| `not_covered` | Code not found in primary or union |
| `no_mapping_available` | Non-general firm without a matching primary CSV (symbol has no probe data yet) |
| `section_mismatch` | Code found in mapping but under a different section |
| `""` | Mapping not loaded — no mapping CLI args were provided |

---

## CLI inputs (all optional)

```
python scripts/parse_vietcap_iq_fa_payloads_dry_run.py \
  --run-id 20260609T035318Z \
  --firm-type-plan-csv data/processed/vietcap_iq/fa_firm_type_plan.csv \
  --primary-mapping-csv data/processed/vietcap_iq/fa_metric_mapping_VCI_20260610T025420Z.csv \
  --primary-source-symbol VCI \
  --primary-source-run-id 20260610T025420Z \
  --union-mapping-csv data/processed/vietcap_iq/fa_metric_mapping_union.csv \
  --mapping-summary-output data/processed/vietcap_iq/fa_parser_mapping_integration_summary.csv
```

Omitting all mapping flags restores original behavior: all 7 new columns are empty.

---

## No-mapping-input behavior

When mapping flags are not provided:
- All 7 new columns are empty (`""`)
- `mapping_status=""` (clearly distinct from all 6 resolver statuses)
- `line_item_name` remains empty (legacy — unchanged)
- All existing validation checks still run and pass

---

## Per-symbol resolver dispatch

The parser builds one `MappingResolver` per unique symbol, governed by the firm-type plan:

| Firm type | `has_primary` | Resolution path |
|---|---|---|
| `securities` (e.g. VCI) | `True` | Primary → consensus_fallback → conflict_skipped / not_covered / section_mismatch |
| `general` (e.g. FPT) | `False` | Union only → consensus_fallback / conflict_skipped / not_covered / section_mismatch |
| Unknown symbol | `False` (default) | Union only |
| Non-general without matching primary CSV | `True`, no rows | All codes → `no_mapping_available` |

---

## Mapping summary output

When `--mapping-summary-output` is provided, a CSV is written with one row per
`(symbol, section, mapping_group)` combination:

```
symbol, section, mapping_group, primary_source_symbol,
total_rows, primary_count, consensus_fallback_count,
conflict_skipped_count, not_covered_count, no_mapping_available_count,
section_mismatch_count, no_status_count, named_count, unnamed_count
```

---

## Real payload validation (2026-06-10)

Run on 5 saved FA-direct payloads. No live network. No DB write.

| Symbol | Section | Total rows | named | primary | consensus | conflict_skip | not_covered | no_map | mismatch |
|---|---|---|---|---|---|---|---|---|---|
| VCI | BALANCE_SHEET | 13,571 | 11,849 | 8,241 | 3,608 | 0 | 1,435 | 0 | 287 |
| VCI | INCOME_STATEMENT | 7,421 | 6,683 | 3,239 | 3,444 | 164 | 574 | 0 | 0 |
| VCI | CASH_FLOW | 9,225 | 7,995 | 6,068 | 1,927 | 0 | 1,230 | 0 | 0 |
| FPT | BALANCE_SHEET | 13,571 | 9,471 | 0 | 9,471 | 2,378 | 1,435 | 0 | 287 |
| FPT | CASH_FLOW | 9,225 | 7,216 | 0 | 7,216 | 779 | 1,230 | 0 | 0 |

Total: 53,013 fact rows. Errors: 0.

**Generated files:**
- `data/processed/vietcap_iq/financial_statement_facts.csv` — 53,013 rows, 32 columns
- `data/processed/vietcap_iq/fa_parser_mapping_integration_summary.csv` — 5 rows
- `data/processed/vietcap_iq/fa_metric_mapping_VCI_20260610T025420Z.csv` — 1,078 primary codes
- `data/processed/vietcap_iq/fa_firm_type_plan.csv` — 5 symbols (VCI, FPT, VCB, BVH, SSI)

---

## Tests added

File: `tests/test_parse_vietcap_iq_fa_payload_mapping_integration.py`

65 tests across 14 groups:

1. No mapping inputs — backward compatibility (9 tests)
2. Primary lookup hit (7 tests)
3. Primary miss / consensus fallback (4 tests)
4. Conflict skipped (5 tests)
5. Not covered (3 tests)
6. Section mismatch (2 tests)
7. No primary mapping available (3 tests)
8. Deterministic output (3 tests)
9. No invented names guard (8 tests)
10. Summary output (5 tests)
11. No DB / no backtest / no network (4 tests)
12. Mapping status consistency check (5 tests)
13. Load firm-type plan CSV (3 tests)
14. Build symbol resolver (4 tests)

Full suite: **552 tests passed** (0 failures, 0 regressions).

---

## Hard constraints

- Parser is dry-run only. No DB writes.
- No backtests.
- No live network requests.
- `line_item_name` (legacy) is always empty.
- Existing parser columns unchanged.
- PIT semantics not confirmed — `public_date_semantics` warnings unchanged.
- Mapping gate not marked complete — cross-symbol consistency not yet validated.
