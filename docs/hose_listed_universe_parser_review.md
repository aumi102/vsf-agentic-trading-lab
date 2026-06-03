---
title: hose_listed_universe_parser_review
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# HOSE Listed Universe Parser Review

## Purpose

This note records the HOSE listed-stock universe dry-run parser behavior and validation result.

The parser is limited to the saved page-1 raw sample from the HOSE listed-stock universe API. It does not fetch all pages, parse quote reports, parse OHLCV, write to a database, run migrations, or implement backtesting.

## Input Raw Sample

<details open>
<summary>The dry run uses the latest verified local HOSE listed-stock universe probe payload.</summary>

---

#### Raw files

- Raw payload: `data/raw/source_probe/source=hose/run_id=20260603T042853Z/hose_listed_stock_universe/payload.json`
- Metadata: `data/raw/source_probe/source=hose/run_id=20260603T042853Z/hose_listed_stock_universe/metadata.json`
- Source: `hose`
- Dataset: `hose_listed_stock_universe`
- Raw content hash: `99c8a1bf65cccbb4f5cd95a29a16077fe9cb90a48b3a331b7f75353086d3da47`

#### Observed payload shape

- Top-level fields: `data`, `success`, `message`.
- Row container: `data.list`.
- Pagination container: `data.paging`.
- Saved sample: page 1 only.
- Pagination says `pageSize=30`, `totalCount=403`, `totalPages=14`.

---

</details>

## Output Files

<details open>
<summary>The parser writes three dry-run canonical CSV outputs and validation artifacts.</summary>

---

Latest dry-run output:

`data/processed/dry_run/hose_listed_universe/20260603T073031Z/`

| File | Purpose |
|---|---|
| `securities_master.csv` | Security-level identifiers, company names, ISIN/Bloomberg id, capital, ownership ratios, and outstanding volumes. |
| `exchange_listings.csv` | HOSE listing-specific fields, security type code, listing status, dates, listed volume, and listed value. |
| `symbol_universe.csv` | Lightweight HOSE symbol universe row for downstream symbol selection. |
| `validation_report.md` | Human-readable dry-run quality report. |
| `validation_summary.json` | Machine-readable dry-run quality summary. |

---

</details>

## Field Mapping

<details open>
<summary>HOSE listed-stock rows map into security, exchange listing, and universe views.</summary>

---

#### `securities_master`

| Raw field | Canonical field | Rule |
|---|---|---|
| `id` | `source_security_id` | Parse as integer. |
| `code` | `symbol` | Strip and uppercase. |
| Source identity | `exchange` | Constant `HOSE`. |
| `code` | `security_id` | `hose:<symbol>`. |
| `name` | `company_name` | Preserve UTF-8 text. |
| `brief` | `short_name` | Trim string. |
| `isin` | `isin` | Preserve and validate format when present. |
| `bloomberg` | `bloomberg_id` | Preserve as Bloomberg id; do not assume FIGI yet. |
| `capital` | `charter_capital_vnd` | Parse numeric. |
| `parValue` | `par_value_vnd` | Parse numeric. |
| `outStanding` | `outstanding_volume` | Parse comma-separated numeric string. |
| `adjOutStanding` | `adjusted_outstanding_volume` | Parse comma-separated numeric string. |
| `treasuryVol` | `treasury_volume` | Parse comma-separated numeric string. |
| `foreignOwnedRatio` | `foreign_owned_ratio_pct` | Parse numeric percent. |
| `stateOwnedRatio` | `state_owned_ratio_pct` | Parse numeric percent. |

#### `exchange_listings`

| Raw field | Canonical field | Rule |
|---|---|---|
| `code` | `symbol` | Strip and uppercase. |
| Source identity | `exchange` | Constant `HOSE`. |
| `securitiesType` | `security_type_code` | Parse integer; lookup semantics still need confirmation. |
| `listingStatusId` | `listing_status_id` | Parse integer; lookup semantics still need confirmation. |
| `regDate` | `registration_date` | Positive Unix epoch seconds to ISO date; negative sentinel becomes null with warning. |
| `ftdate` | `first_trading_date` | Positive Unix epoch seconds to ISO date; negative sentinel becomes null with warning. |
| `acceptDate` | `acceptance_date` | Positive Unix epoch seconds to ISO date; negative sentinel becomes null with warning. |
| `listDate` | `listing_date` | Positive Unix epoch seconds to ISO date; negative sentinel becomes null with warning. |
| `listingVolume` | `listed_volume` | Parse comma-separated numeric string. |
| `listingValue` | `listed_value_vnd` | Parse comma-separated numeric string. |

#### `symbol_universe`

| Raw field | Canonical field | Rule |
|---|---|---|
| `code` | `symbol` | Strip and uppercase. |
| Source identity | `exchange` | Constant `HOSE`. |
| `displayText` | `display_text` | Preserve source UI label. |
| `name` | `company_name` | Preserve UTF-8 text. |
| `securitiesType` | `security_type_code` | Parse integer. |
| `listingStatusId` | `listing_status_id` | Parse integer. |
| `listingStatusId` | `is_active_candidate` | `true` when status id is `11`; final status lookup still needs confirmation. |

---

</details>

## Validation Rules

<details open>
<summary>Validation produces row-level pass, warn, or fail status.</summary>

---

#### Required fields

- `symbol` is required.
- `company_name` is expected but treated as a warning if missing, because a symbol row can still be useful for universe construction.

#### Failure checks

- Duplicate `symbol` within the saved page sample fails the affected rows.
- Negative numeric values in volume/value/capital fields fail when present.
- Impossible non-sentinel date values fail.

#### Warning checks

- Missing `company_name` warns with `warning_missing_company_name`.
- Invalid present ISIN warns with `warning_invalid_isin`.
- Negative sentinel dates such as `-62135596800` become null and warn with `warning_sentinel_date_<rawField>`.
- `listed_volume < outstanding_volume` warns, because listed volume is not guaranteed to dominate outstanding volume in every source case.

#### Pagination checks

- `data.paging` must exist.
- Summary records `pageIndex`, `pageSize`, `totalCount`, and `totalPages`.
- This parser does not fetch additional pages.

---

</details>

## Dry-Run Result Summary

<details open>
<summary>The latest dry run parsed page 1 into 30 rows per output with warnings only for sentinel dates.</summary>

---

Latest dry run:

`data/processed/dry_run/hose_listed_universe/20260603T073031Z/`

| Metric | Count |
|---|---:|
| Page rows parsed | 30 |
| Securities master rows | 30 |
| Exchange listing rows | 30 |
| Symbol universe rows | 30 |
| Quality pass rows | 21 |
| Quality warn rows | 9 |
| Quality fail rows | 0 |
| Duplicate symbol rows | 0 |

Pagination:

| Field | Value |
|---|---:|
| `pageIndex` | 1 |
| `pageSize` | 30 |
| `totalCount` | 403 |
| `totalPages` | 14 |

Quality reasons:

| Reason | Count |
|---|---:|
| `warning_sentinel_date_acceptDate` | 9 |
| `warning_sentinel_date_listDate` | 9 |

---

</details>

## Limitations

<details open>
<summary>The dry run is parser proof for page 1 only, not market data ingestion.</summary>

---

- This parser processes only the saved page-1 raw sample, so it covers 30 of 403 listed-stock rows.
- It does not fetch pages 2 through 14.
- It does not parse OHLCV.
- It does not parse quote-report data.
- The latest quote-report samples are HTML request-rejection pages and remain out of scope.
- `securitiesType` and `listingStatusId` require source lookup confirmation before production use.
- Date fields are epoch-like seconds, and sentinel negative values are normalized to null with warnings.

---

</details>

## Review Decision

The HOSE listed-universe parser dry run is ready for review.

The next parser task should either expand the universe dry run to all pages, still without database writes, or re-probe quote-report until a usable row-level JSON sample is captured.
