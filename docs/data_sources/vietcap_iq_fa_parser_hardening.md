---
title: vietcap_iq_fa_parser_hardening
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Vietcap IQ FA Parser Hardening

## Purpose

This document records the validation checks added to
`scripts/parse_vietcap_iq_fa_payloads_dry_run.py` after the initial dry-run parser was
implemented. The goal is to make structural and data-quality issues explicit rather than
silent, without adding any DB write, backtest, or live network dependency.

---

## Validation Checks Added

All checks are implemented in `validate_parse_result(all_facts, all_stats)` and its helper
functions. Each check returns one or more findings with a `check`, `severity`, and `detail`
field. Severity levels:

| Severity | Meaning |
|---|---|
| `error` | Structural issue that indicates corrupt or unexpected data; blocks `--strict` mode |
| `warning` | Data pattern worth investigating but not necessarily wrong |
| `info` | Expected condition, recorded for audit completeness |

### a. Required metadata fields / metric columns detected

Each payload stats dict carries `metric_column_count` (the number of non-metadata columns
in the first period row). If `metric_column_count == 0`, the payload is metadata-only or
malformed — `severity=error`.

### b. Detected period columns

Validated inside `melt_period_rows` (pre-existing): if a row has no `yearReport` or
`lengthReport`, it is skipped and recorded as a structural error. The `validate_parse_result`
function additionally checks that at least one fact row was produced across all payloads
(`facts_produced` check).

### c. Duplicate long-format keys

`_check_duplicate_keys(facts)` checks uniqueness of
`(source_run_id, symbol, section, source_period_label, line_item_code)` across all
long-format fact rows. Duplicate keys indicate either two payloads returning identical
data for the same symbol/section/period, or a parser bug that mints the same row twice.
Result is `severity=error` if any duplicates are found.

### d. Null / zero / missing counts

Already tracked per-payload in `stats["q_publicdate_nonnull"]` and per-fact via
`value_status`. The report table shows `present` / `zero` / `missing` totals across all
parsed payloads. The `_check_value_status_validity` check verifies that every fact has
exactly one of the three valid `value_status` values (`severity=error` otherwise).

### e. Invalid or unexpected date / period labels

`_check_publicdate_format(facts)` checks that every non-empty `public_date` value starts
with `YYYY-MM-DD` (ISO date format). Values like `25/04/2024` or `Apr 25 2024` produce
`severity=warning`. The format check uses `re.compile(r"^\d{4}-\d{2}-\d{2}")`.

Structural `lengthReport` range validation is handled in `melt_period_rows`:
`lengthReport ∉ {1,2,3,4}` for quarterly rows → `unexpected_lengthReport_for_quarter`
error; `lengthReport ≠ 5` for annual rows → `unexpected_lengthReport_for_year` error.

### f. Empty mapping coverage

`_check_mapping_coverage(facts)` explicitly reports the fraction of fact rows with a
non-empty `line_item_name`. Expected: 0.0%. The check always produces an `info` finding
that states the exact count and links to the mapping discovery doc. This makes the
unmapped state visible rather than silently zero.

### g. nos* columns null for non-securities firms

`_check_nos_pattern(facts)` groups fact rows by symbol and examines rows where
`line_item_code` starts with `nos`. Three cases:

| Pattern | Severity | Interpretation |
|---|---|---|
| 100% `missing` | `info` | Expected for non-securities firm (FPT-type) |
| 0% `missing` | `info` | Expected for securities firm (VCI-type) |
| Mixed | `warning` | Unexpected — review company type classification |

---

## Guard: No Invented Metric Names

`_check_no_invented_names(facts)` asserts that `line_item_name` is empty for all fact
rows. If any row has a non-empty name, severity is `error`. This prevents the parser from
ever silently inserting unverified human-readable names.

The guard complements `WARNING_NO_NAME` (a per-row `parser_warning` flag emitted by
`melt_period_rows`) with a post-parse aggregate check.

---

## Deterministic Output Order

`_sort_facts(facts)` sorts the long-format output before writing, keyed by:
`(symbol, section, source_period_label, line_item_code, source_run_id)`.

This ensures that repeated runs of the parser on the same saved payloads produce
byte-for-byte identical CSV/JSONL output.

---

## CLI Flag: --strict

`--strict` causes the script to exit with code 1 if any validation finding has
`severity=error`. Without `--strict`, errors are printed to stderr but the output files
are still written. This allows soft enforcement in development while enabling hard
enforcement in CI when desired.

---

## What Remains Blocked

| Item | Status |
|---|---|
| `line_item_name` population | **Blocked** — no verified mapping available |
| `publicDate` PIT semantics confirmation | **Unconfirmed** — not validated against exchange filings |
| Full-universe FA fetch | **Not implemented** |
| DB write / canonical schema | **Not implemented** |
| Backtest | **Not implemented** |
| Production parser | **Not implemented** |

---

## Test Coverage

New tests added to `tests/test_vietcap_iq_fa_payload_parser_dry_run.py`:

| Test | What it verifies |
|---|---|
| `test_sort_facts_is_deterministic` | Same facts in different orders → same sorted output |
| `test_check_duplicate_keys_*` (3 tests) | Detects exact dupes; no-dupe info; different run_ids not flagged |
| `test_check_publicdate_format_*` (4 tests) | Valid ISO, empty, slash format, `YYYY/MM/DD` |
| `test_check_mapping_coverage_*` (3 tests) | 0%, unique code count, empty facts |
| `test_check_no_invented_names_*` (2 tests) | All empty passes; non-empty is error |
| `test_check_value_status_validity_*` (2 tests) | Valid values pass; bad value is error |
| `test_check_nos_pattern_*` (5 tests) | All-null, 0%-null, mixed, no-nos-cols, non-nos excluded |
| `test_validate_*` (8 tests) | Composite: clean input, zero cols, empty facts, dupe key, invented name, mapping coverage always present, null-vs-zero preserved, no fake names from melt |
| `test_generate_report_*` (2 new tests) | Validation section present/absent based on `findings` arg |

Total tests: 235 (full suite) / 77 (this file).

---

## Related Documents

- `docs/data_sources/vietcap_iq_fa_parser_dry_run.md` — parser command, output schema, key findings
- `docs/data_sources/vietcap_iq_fa_metric_mapping_discovery.md` — local audit + live probe result
- `docs/data_sources/vietcap_iq_fa_shape_cross_check.md` — section/symbol cross-check results
