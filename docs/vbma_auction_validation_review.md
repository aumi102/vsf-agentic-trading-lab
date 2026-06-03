---
title: vbma_auction_validation_review
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# VBMA Auction Validation Review

## Purpose

This note records the validation review for the VBMA government bond auction dry-run parser after the first successful parse produced many row-level failures.

The review is limited to parser and validator behavior. It does not introduce database migrations, production ingestion, backtesting, or any non-VBMA source work.

## Before Fix

Latest reviewed dry-run:

`data/processed/dry_run/vbma_auction/20260603T021243Z/`

| Metric | Count |
|---|---:|
| Input rows | 3,268 |
| Quality pass rows | 2,834 |
| Quality warn rows | 0 |
| Quality fail rows | 434 |

| Fail reason | Count |
|---|---:|
| `bid_yield_min_greater_than_max` | 428 |
| `duplicate_bond_code_auction_or_issue_date` | 6 |

## Root Cause Analysis

### Bid Yield Min Greater Than Max

The 428 rows were inspected against the original spreadsheet payload:

`data/raw/source_probe/source=vbma/run_id=20260602T085214Z/vbma_primary_market_auction_results/payload.txt`

The raw payload columns include:

- `Mã trái phiếu`
- `Tổ chức phát hành`
- `Kỳ hạn (năm)`
- `Ngày TCPH`
- `Giá trị gọi thầu (tỷ đồng)`
- `Giá trị đặt thầu (tỷ đồng)`
- `Giá trị trúng thầu (tỷ đồng)`
- `Lãi suất trúng thầu (%/y)`
- `Lãi suất đấu thầu max`
- `Lãi suất đấu thầu min`

At least 20 failing examples were checked. The raw spreadsheet itself contains cases where the value under `Lãi suất đấu thầu max` is lower than the value under `Lãi suất đấu thầu min`, for example:

| Raw row | Bond code | Raw max | Raw min | Winning yield |
|---:|---|---:|---:|---:|
| 672 | TD2333119 | 2.95 | 3.60 | 2.95 |
| 673 | TD2328099 | 2.40 | 2.60 | 2.40 |
| 674 | TD2338134 | 3.05 | 3.40 | 3.05 |
| 817 | BVBS22262 | 4.00 | 4.60 | 4.00 |

The parser is not swapping the columns during normalization. Numeric parsing is also not the root cause for these examples because the raw spreadsheet values already parse as numeric decimal values.

Decision: the source semantics are ambiguous. The labels may not mean strict mathematical minimum and maximum, or the source may contain label/field inconsistencies. These rows should not be hard failures until VBMA semantics are confirmed manually.

Validator change: `bid_yield_min_greater_than_max` was downgraded to `warning_bid_yield_min_greater_than_max`.

Negative yield values remain failures.

### Duplicate Bond Date Rows

The six duplicate `bond_code + auction_or_issue_date` rows were inspected. They are duplicate bond/date pairs, but the amount and yield fields differ. Examples include:

- `BVBS18171` on `2018-10-01`
- `BVBS18203` on `2018-10-01`
- `BVBS18228` on `2018-10-01`

These are not exact duplicate auction result records under the current canonical row identity.

Decision: duplicate `bond_code + auction_or_issue_date` is a warning unless the full canonical auction result identity is duplicated.

Exact duplicate identity now uses:

- `bond_code`
- `auction_or_issue_date`
- `offered_amount_billion_vnd`
- `bid_amount_billion_vnd`
- `winning_amount_billion_vnd`
- `winning_yield_pct`
- `bid_yield_max_pct`
- `bid_yield_min_pct`

Validator change: non-exact duplicate bond/date rows are marked with `warning_duplicate_bond_code_auction_or_issue_date`. Exact duplicate canonical rows remain failures with `exact_duplicate_bond_auction_result_identity`.

## Numeric Parsing Decision

Numeric parsing was tightened so that:

- Existing numeric Excel cells are preserved without string over-transformation.
- `"-"` and empty strings become null.
- Decimal comma values such as `"3,60"` parse to `3.60`.
- Amount-style thousands separators such as `"1,500"` parse to `1500`.
- Mixed separators such as `"1.500,25"` parse to `1500.25`.
- Amount fields are treated as billion VND unless later source evidence proves otherwise.

This keeps yield decimals and amount separators distinct enough for the current VBMA dry run.

## Date Parsing Decision

VBMA date values are parsed with day-first behavior.

Decision: ambiguous dates such as `03/04/2020` are interpreted as `2020-04-03`.

Reason: the VBMA source is Vietnamese, and date strings are expected to follow `dd/mm/yyyy` when they are not already typed Excel dates.

## Validator Changes Made

The parser now produces three row-level quality states:

- `pass`
- `warn`
- `fail`

Warnings are included in `quality_reasons` but no longer block the row from being considered a parsed auction result.

The validation summary now includes:

- `quality_warn_count`
- `exact_duplicate_canonical_row_count`
- `quality_warning_reason_counts`
- `quality_failure_reason_counts`

## After Fix

Latest rerun:

`data/processed/dry_run/vbma_auction/20260603T023438Z/`

| Metric | Count |
|---|---:|
| Input rows | 3,268 |
| Quality pass rows | 2,834 |
| Quality warn rows | 434 |
| Quality fail rows | 0 |

| Warning reason | Count |
|---|---:|
| `warning_bid_yield_min_greater_than_max` | 428 |
| `warning_duplicate_bond_code_auction_or_issue_date` | 6 |

| Failure reason | Count |
|---|---:|
| None | 0 |

## Review Decision

The VBMA auction parser is ready for code review as a dry-run parser.

The remaining warning rows should be reviewed with source semantics before promoting this parser into production ingestion or database writes. In particular, the business meaning of `Lãi suất đấu thầu max` and `Lãi suất đấu thầu min` should be confirmed before using those fields in downstream analytics.
