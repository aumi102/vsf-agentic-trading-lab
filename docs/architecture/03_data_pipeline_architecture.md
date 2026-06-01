---
title: 03_data_pipeline_architecture
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Data Pipeline Architecture

### Key Terms
<details open>
<summary>The pipeline vocabulary used for crawl, clean, feature engineering, and backtest.</summary>
---
#### Data pipeline terms

| Term | Meaning |
|---|---|
| `raw` | The exact file or response collected from the source. |
| `bronze` | Raw data stored with source metadata and minimal parsing. |
| `silver` | Cleaned and normalized data with consistent schema. |
| `gold` | Feature-ready or analytics-ready data used by tools. |
| `lineage` | The chain that shows where a row came from and how it changed. |
| `schema` | The field definitions, types, units, keys, and constraints. |
| `feature` | A computed value used by a strategy, such as return, MA, volatility, or RSI. |
| `point-in-time` | Data as it was known at a specific time, before later revisions. |

---
#### Frequency terms

| Term | Meaning |
|---|---|
| `daily` | One row per trading day. |
| `intraday` | Many rows inside one trading day, such as minute bars. |
| `quarterly` | One row per reporting quarter, usually for financial statements. |
| `monthly` | One row per month, common for macro series. |
| `event-based` | Rows appear only when an event happens, such as dividend or split. |

---
</details>

### Pipeline Levels
<details open>
<summary>The pipeline should preserve raw evidence and create clean tables for tools.</summary>
---
#### Cast

- `FPT_daily_ohlcv` = the market data example.
- `source_file` = a daily price CSV or scraped table from a market data source.
- `trading_calendar` = the list of official trading days used to detect missing bars.
- `ma20_ma50_strategy` = the downstream strategy that needs clean daily close prices.

---
#### Level: raw capture

- **input** = CSV, HTML table, API JSON, PDF, or manually downloaded file.
- **stored fields** = source name, source URL, crawl time, file hash, raw payload path, and parser version.
- **meaning** = raw capture gives the team a replayable source if a cleaned value looks suspicious.

---
#### Level: bronze parsing

- **input** = raw file or response.
- **job** = parse rows without changing financial meaning.
- **stored fields** = original symbol, original date, original price strings, original volume strings, and parse status.
- **meaning** = bronze separates parsing errors from financial cleaning decisions.

---
#### Level: silver normalization

- **input** = bronze rows.
- **job** = convert dates, numeric types, symbol codes, units, and exchange identifiers.
- **stored fields** = `symbol`, `exchange`, `date`, `open`, `high`, `low`, `close`, `volume`, `value`, `source_id`.
- **meaning** = silver is the first layer that tools can query safely.

---
#### Level: gold features

- **input** = silver OHLCV.
- **job** = compute features with point-in-time rules.
- **stored fields** = return, MA, RSI, volatility, gap, volume ratio, and feature timestamp.
- **meaning** = gold prevents each strategy tool from recomputing features differently.

---
</details>

### Worked Example
<details open>
<summary>A single bad date can break a backtest if the pipeline does not catch it.</summary>
---
#### Input sample

- `FPT` has `250` expected trading days in a year.
- The crawler finds `249` rows.
- The missing date is `2024-09-02`.
- The trading calendar says `2024-09-02` was a holiday.
- The quality tool should mark this as `pass`, because the missing row is not a trading day.

---
#### Quality rules

| Rule | Check | Result |
|---|---|---|
| trading calendar | expected trading days match actual rows | `pass` |
| duplicate key | no duplicate `symbol + date` | `pass` |
| OHLC rule | `high >= max(open, close)` and `low <= min(open, close)` | `pass` |
| unit rule | volume unit is known | `warn` if source reports lots instead of shares. |
| adjusted price rule | adjusted and unadjusted fields are not mixed | `fail` if unclear. |

---
#### Read

- If holiday-aware missing-day check is absent, the system may falsely reject clean data.
- If unit check is absent, volume features may be wrong by `100x` when one source reports lots and another reports shares.
- If adjusted price is unclear, return and backtest metrics may be distorted around dividends or splits.

---
</details>

### Failure Modes
<details open>
<summary>The pipeline must stop bad data before the agent reaches a trading conclusion.</summary>
---
#### Data failures

- **schema drift** = a source changes column names, so the parser maps the wrong field.
- **timestamp mismatch** = macro data is monthly while market data is daily, so the join leaks future data.
- **duplicate symbol** = the same ticker exists across exchanges or time periods without a stable security ID.
- **corporate-action gap** = price is unadjusted but the strategy assumes adjusted returns.
- **revision gap** = a financial report was revised, but the database does not store the old version.

---
#### Required pipeline outputs

- `dataset_id` for each cleaned table.
- `source_id` for every row.
- `quality_status` as `pass`, `warn`, or `fail`.
- `quality_reasons` as machine-readable codes.
- `as_of_timestamp` for point-in-time safety.
- `parser_version` and `schema_version` for reproducibility.

---
#### Questions to ask mentor

- Which layer should be mandatory in the MVP: raw, bronze, silver, and gold, or only raw plus silver?
- Should adjusted OHLCV be required before backtesting VN stocks?
- What is the maximum allowed missing-data rate before a backtest becomes `unanswered`?
- Should feature tables be stored permanently or computed on demand first?

---
</details>
