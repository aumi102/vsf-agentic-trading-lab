---
title: 01_data_crawling_plan
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Data Crawling Plan

### Goal And Scope
<details open>
<summary>The crawling plan should collect high-value data without breaking schema discipline.</summary>
---
#### Goal

- Build a repeatable data intake path for market data, reports, macro data, and bond context.
- Preserve raw files before normalization.
- Attach every cleaned row to source metadata.
- Avoid coding a wide crawler before schema and quality gates are clear.

---
#### MVP scope

- **market data** = daily OHLCV for a small VN equity universe or one easier crypto asset if approved.
- **reports** = Vietcap or similar public reports for company and market context.
- **macro** = curated FRED series plus local bond context from VBMA.
- **out of scope** = live trading, high-frequency order book, and broad multi-source crawling.

---
</details>

### Source Priority
<details open>
<summary>Crawl sources in the order that supports architecture proof first.</summary>
---
#### Priority table

| Priority | Source | Why first or later |
|---|---|---|
| P0 | market OHLCV | required for TA, features, and backtest. |
| P1 | trading calendar and symbol master | required for missing-date checks and stable IDs. |
| P2 | corporate actions | required before trusting VN equity return backtests. |
| P3 | Vietcap reports | useful for FA and evidence retrieval. |
| P4 | FRED macro series | useful for regime context with clean API access. |
| P5 | VBMA bond data | useful for local rates context. |
| P6 | intraday/order book | execution realism; later unless mentor requires. |

---
#### Worked example

- Start with `10` stocks and `5` years of daily prices.
- Expected rows are about `10 × 250 × 5 = 12,500`.
- This size is small enough for Parquet and DuckDB.
- Use it to prove source capture, schema validation, feature generation, and backtest trace.

---
</details>

### Crawl Contract
<details open>
<summary>Every crawler should output raw data, parsed data, metadata, and failure reason.</summary>
---
#### Required output

| Output | Meaning |
|---|---|
| `raw_path` | Where the original file or response is stored. |
| `source_url` | Where the data came from. |
| `crawled_at` | When the crawler fetched it. |
| `content_hash` | Deduplication and audit. |
| `parser_version` | Which parser generated the rows. |
| `schema_version` | Which schema the rows follow. |
| `parse_status` | pass, warn, or fail. |
| `failure_reason` | machine-readable error if failed. |

---
#### Failure handling

- If access fails, store an error trace with HTTP status or file error.
- If parsing fails, keep raw file and mark the batch `parse_fail`.
- If schema validation fails, quarantine the batch and do not update silver tables.
- If data quality fails, do not let backtest tools consume the dataset.

---
</details>

### Questions To Mentor
<details open>
<summary>The plan needs mentor decisions before implementation starts.</summary>
---
#### Questions

- Which source should be used for canonical daily OHLCV?
- Are we allowed to crawl Vietcap IQ, or should we use manually downloaded reports first?
- Should corporate actions be mandatory before any VN stock backtest?
- Should FRED be included in MVP or kept for macro reference only?
- What is the first asset universe for demo?
- Should raw files be committed to repo, stored locally, or stored in object storage?

---
</details>
