---
title: fred_observations_parser_review
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# FRED Observations Parser Review

## Purpose

This note records the FRED observations dry-run parser behavior and validation result.

The parser is limited to macro observation parsing from an already captured source-probe payload. It does not implement full ingestion, database writes, stock OHLCV, HOSE, Vietcap IQ, backtesting, or new sources.

## Input Raw Sample

<details open>
<summary>The dry run uses the latest verified local FRED probe payload.</summary>

---

#### Raw files

- Raw payload: `data/raw/source_probe/source=fred/run_id=20260602T072716Z/fred_observations/payload.json`
- Metadata: `data/raw/source_probe/source=fred/run_id=20260602T072716Z/fred_observations/metadata.json`
- Source: `fred`
- Dataset: `fred_observations`
- Series: `DGS10`
- Raw content hash: `bb06f040e8cb2bb238623483fc751d4b12e3b94d5d7be16e57b4dc04654edaa4`

#### Observed payload shape

- Top-level metadata fields: `realtime_start`, `realtime_end`, `observation_start`, `observation_end`, `units`, `count`, `offset`, `limit`.
- Nested rows: `observations[]`.
- Observation fields: `date`, `value`, `realtime_start`, `realtime_end`.

---

</details>

## Output Files

<details open>
<summary>The parser writes dry-run canonical CSV outputs and validation artifacts.</summary>

---

Latest dry-run output:

`data/processed/dry_run/fred_observations/20260603T025403Z/`

| File | Purpose |
|---|---|
| `macro_series.csv` | One row of series-level metadata for `DGS10`. |
| `macro_observations.csv` | One row per FRED observation. |
| `validation_report.md` | Human-readable dry-run quality report. |
| `validation_summary.json` | Machine-readable dry-run quality summary. |

---

</details>

## Field Mapping

<details open>
<summary>FRED observations map to macro series and macro observation tables.</summary>

---

#### Series mapping

| Raw field or metadata source | Canonical field | Rule |
|---|---|---|
| Metadata request params or endpoint query `series_id` | `series_id` | Preserve source series id; current sample resolves to `DGS10`. |
| Top-level `units` | `units` | Preserve source units value. |
| Top-level `observation_start` | `observation_start` | Parse as ISO date string. |
| Top-level `observation_end` | `observation_end` | Parse as ISO date string. |
| Top-level `count` | `count` | Parse as integer. |
| Top-level `limit` | `limit` | Parse as integer. |
| Raw payload hash | `raw_content_hash` | Preserve for lineage. |
| Hash-derived payload id | `source_payload_id` | `fred:<first 16 chars of raw hash>`. |

#### Observation mapping

| Raw field | Canonical field | Rule |
|---|---|---|
| Recovered series id | `series_id` | Repeat on every observation row. |
| `observations[].date` | `observation_date` | Parse as ISO date string. |
| `observations[].value` | `observation_value` | Numeric string to float; `.` becomes null with warning. |
| `observations[].realtime_start` | `realtime_start` | Parse as ISO date string. |
| `observations[].realtime_end` | `realtime_end` | Parse as ISO date string. |
| Row position | `raw_row_index` | Preserve local row lineage. |
| Parser/schema constants | `parser_version`, `schema_version` | Current values: `fred_observation_parser_v1`, `fred_observations_dry_run_v1`. |

---

</details>

## Validation Rules

<details open>
<summary>Validation preserves row-level pass, warn, and fail status.</summary>

---

#### Required fields

- `series_id`
- `observation_date`
- `realtime_start`
- `realtime_end`

#### Value rules

- `value == "."` becomes null and adds `warning_missing_observation_value`.
- Empty or missing value also becomes null with `warning_missing_observation_value`.
- Numeric strings become floats.
- Numeric parse failures fail the row with `invalid_numeric_observation_value`.

#### Date rules

- Dates must parse as strict `YYYY-MM-DD`.
- Invalid required dates fail the row through missing parsed canonical fields.

#### Duplicate rules

- Exact duplicate macro observation identity fails with `exact_duplicate_macro_observation_identity`.
- Exact duplicate identity uses `series_id`, `observation_date`, `realtime_start`, `realtime_end`, and `observation_value`.

#### Row count rule

- Parsed macro observation row count must match the number of rows in `observations[]`.

---

</details>

## Point-In-Time Considerations

<details open>
<summary>FRED realtime fields are preserved because macro values can be revised.</summary>

---

- `realtime_start` and `realtime_end` are preserved on every observation row.
- Future backtests must not use revised macro values unless the revision was available as of the simulated date.
- `observation_date` is not the same as data availability date.
- The first dry run uses a tiny configured probe and should not be treated as a full macro history ingestion.

---

</details>

## Dry-Run Result Summary

<details open>
<summary>The latest FRED dry run parsed the verified DGS10 sample without warnings or failures.</summary>

---

| Metric | Count |
|---|---:|
| JSON observations | 5 |
| Macro series rows | 1 |
| Macro observation rows | 5 |
| Quality pass rows | 5 |
| Quality warn rows | 0 |
| Quality fail rows | 0 |
| Exact duplicate macro observation rows | 0 |

Quality reasons:

- none

---

</details>

## Limitations

<details open>
<summary>The parser is ready for review, but this is not full FRED ingestion.</summary>

---

- The current sample is limited to `DGS10` and `limit=5`.
- No FRED series catalog parser is implemented yet.
- No database migration or database write is implemented.
- No macro feature engineering is implemented.
- FRED is macro context only and must not be treated as stock OHLCV.

---

</details>
