---
title: vnstock_prototype_status
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Vnstock Prototype Status

### Summary

<details open>
<summary>The existing vnstock implementation is useful, but it is not the canonical source path.</summary>

---

The `vnstock` prototype proved that the local raw/silver/report pipeline can run end to end. After mentor feedback, it should be treated as prototype/fallback/reference only. The canonical MVP direction is direct source/vendor/provider crawling and fetching.

---

</details>

### What Worked

<details open>
<summary>The prototype validated pipeline mechanics.</summary>

---

The prototype successfully demonstrated:

- package structure under `src/trading_agent`.
- source wrapper isolation in `src/trading_agent/data_sources/vnstock_client.py`.
- raw output under `data/raw/vnstock/...`.
- silver Parquet outputs under `data/silver/...`.
- canonical tables for `securities`, `daily_prices`, and `corporate_events`.
- quality checks for schema, duplicates, OHLC consistency, source IDs, and adjusted-price warnings.
- data inventory and quality reports under `reports/`.
- tests for normalization and quality checks.

The live prototype produced:

- `data/silver/securities.parquet`
- `data/silver/daily_prices.parquet`
- `data/silver/corporate_events.parquet`
- `reports/data_inventory.md`
- `reports/data_quality_report.md`

---

</details>

### Why It Is Not Canonical

<details open>
<summary>Wrapper-library output hides too much source-level detail for the main MVP path.</summary>

---

`vnstock` should not be canonical because:

- It is a wrapper library, not the source/vendor/provider itself.
- It may rename, reshape, filter, or join fields before the project sees raw source evidence.
- It does not by itself teach provider access handling, auth, rate limits, source terms, or source schema drift.
- Canonical DB and schema design need provider-level IDs, timestamps, adjustment fields, and provenance.
- The mentor explicitly wants direct data infrastructure work around providers such as HSX/HOSE, SSI, Vietcap, and other source surfaces.

---

</details>

### Reusable Parts

<details open>
<summary>Keep the infrastructure lessons, not the wrapper as the primary source.</summary>

---

The following should be reused:

- canonical table contracts for `securities`, `daily_prices`, and `corporate_events`.
- quality checks for required columns, duplicates, OHLC consistency, source IDs, and adjusted-price limitations.
- raw/silver/gold folder convention.
- data inventory and data quality report shape.
- parser/adapter isolation pattern.
- tests pattern using synthetic DataFrames without network access.
- fallback behavior that reports unavailable optional datasets without crashing the whole run.

---

</details>

### Do Not Reuse As-Is

<details open>
<summary>The vnstock adapter should not become the primary data provider.</summary>

---

Do not reuse these as canonical MVP behavior:

- treating `vnstock` datasets as P0 canonical source data.
- relying on wrapper-specific field names as the final schema basis.
- silently substituting `vnstock` when a source/vendor/provider probe fails.
- assuming wrapper output satisfies source terms, provider provenance, or point-in-time requirements.

---

</details>

### Current Position

<details open>
<summary>How vnstock should be used after the roadmap correction.</summary>

---

`vnstock` can remain:

- a prototype/fallback adapter.
- a reference for expected field shapes.
- a quick local demo path.
- a regression-test fixture source when direct source access is unavailable.

`vnstock` must not be:

- the canonical MVP market-data source.
- the only source behind `daily_prices`.
- the basis for claiming provider-level ingestion is complete.

---

</details>
