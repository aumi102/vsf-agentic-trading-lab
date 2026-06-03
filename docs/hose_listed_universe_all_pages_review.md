---
title: hose_listed_universe_all_pages_review
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# HOSE Listed Universe All-Pages Review

## Purpose

This note records the HOSE listed-stock universe all-pages dry-run workflow and validation result.

The workflow extends the page-1 parser proof by fetching all pages advertised by the HOSE listed-stock universe pagination metadata. It still performs no database migration, no database write, no quote-report parsing, no OHLCV parsing, and no backtest work.

## How This Differs From The Page-1 Parser

<details open>
<summary>The all-pages script wraps the existing parser instead of replacing it.</summary>

---

The existing parser remains:

`src/trading_agent/ingestion/parsers/hose_listed_universe_parser.py`

The all-pages workflow adds:

- Page discovery from the saved page-1 metadata and payload.
- Fetching pages `1..totalPages`.
- Raw page preservation under the dry-run output.
- Combined parsing across all fetched pages.
- Cross-page duplicate symbol detection.
- Run-level checks for missing pages and expected row count.

The parser logic for row normalization and row quality remains the page-1 parser logic.

---

</details>

## Endpoint And Pagination Behavior

<details open>
<summary>The source advertises 14 pages and 403 listed-stock rows.</summary>

---

Page-1 source metadata:

`data/raw/source_probe/source=hose/run_id=20260603T042853Z/hose_listed_stock_universe/metadata.json`

Endpoint:

`https://api.hsx.vn/l/api/v1/1/securities/stock?pageIndex=1&pageSize=30&alphabet=&sectorId=`

Pagination from the page-1 payload:

| Field | Value |
|---|---:|
| `pageIndex` | 1 |
| `pageSize` | 30 |
| `totalCount` | 403 |
| `totalPages` | 14 |

The all-pages dry-run script derives page URLs by changing `pageIndex` and preserving `pageSize`.

---

</details>

## Output Files

<details open>
<summary>The run writes combined canonical CSVs plus local raw page copies.</summary>

---

Latest dry-run output:

`data/processed/dry_run/hose_listed_universe_all_pages/20260603T075046Z/`

| File | Purpose |
|---|---|
| `securities_master.csv` | Combined security-level rows across all fetched pages. |
| `exchange_listings.csv` | Combined HOSE listing rows across all fetched pages. |
| `symbol_universe.csv` | Combined symbol-universe rows across all fetched pages. |
| `validation_report.md` | Human-readable all-pages validation report. |
| `validation_summary.json` | Machine-readable all-pages validation summary. |
| `raw_pages/page_001.json ... page_014.json` | Local raw page payload copies. |
| `raw_pages/page_manifest.json` | Fetch manifest with page status and raw paths. |

Each combined output includes lineage fields such as source payload id, page index, raw row index, global row index, parser version, and schema version.

---

</details>

## Validation Rules

<details open>
<summary>The all-pages workflow adds run-level validation to the existing row-level parser checks.</summary>

---

#### Row-level checks reused from page parser

- Required `symbol`.
- Missing `company_name` warns.
- Duplicate symbol within parsed data fails affected rows.
- Numeric volume/value/capital fields must be non-negative when present.
- `listed_volume < outstanding_volume` warns.
- Sentinel negative dates become null and warn.
- Invalid ISIN warns.

#### All-pages checks

- `requested_page_count` is taken from `totalPages`.
- `fetched_page_count` must match requested pages for a clean run.
- Missing pages are recorded in `missing_pages`.
- `parsed_total_rows` is compared with `totalCount`.
- If parsed rows do not equal `totalCount`, the run is warning-level, not failure-level.
- Duplicate symbols across pages fail affected rows.
- Raw page payloads and page metadata are preserved under `raw_pages/`.

---

</details>

## Dry-Run Result Summary

<details open>
<summary>The latest all-pages dry run fetched all 14 pages and parsed all 403 expected rows.</summary>

---

Latest dry run:

`data/processed/dry_run/hose_listed_universe_all_pages/20260603T075046Z/`

| Metric | Count |
|---|---:|
| Requested pages | 14 |
| Fetched pages | 14 |
| Missing pages | 0 |
| Expected total rows | 403 |
| Parsed total rows | 403 |
| Securities master rows | 403 |
| Exchange listing rows | 403 |
| Symbol universe rows | 403 |
| Duplicate symbol rows | 0 |
| Quality pass rows | 178 |
| Quality warn rows | 225 |
| Quality fail rows | 0 |

Run quality:

- `pass`

Quality reasons:

| Reason | Count |
|---|---:|
| `warning_sentinel_date_acceptDate` | 220 |
| `warning_sentinel_date_listDate` | 220 |
| `warning_listed_volume_less_than_outstanding_volume` | 11 |

The row count matches the source pagination total count.

---

</details>

## Limitations

<details open>
<summary>This is still listed-universe metadata only.</summary>

---

- This workflow does not parse quote-report data.
- This workflow does not parse OHLCV.
- This workflow does not write to a database.
- This workflow does not implement backtest logic.
- `securitiesType` and `listingStatusId` still need source lookup confirmation.
- Sentinel date warnings are expected because many rows contain negative placeholder dates from the source.
- Quote-report samples remain out of scope because the saved bodies are HTML request-rejection pages, not quote JSON.

---

</details>

## Review Decision

The HOSE listed-universe all-pages dry run is ready for review.

The next safe implementation step is to decide whether this all-pages listed universe output should remain a dry-run CSV artifact, be promoted into a formal local ingestion stage, or wait until quote-report/OHLCV endpoint capture is successful.
