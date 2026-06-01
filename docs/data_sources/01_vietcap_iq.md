---
title: 01_vietcap_iq
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Source Review

### Snapshot
<details open>
<summary>Vietcap IQ is mainly a FA and report-retrieval source for Vietnamese equities.</summary>
---
#### Source role

- **source** = Vietcap IQ and Vietcap Research reports.
- **purpose** = collect company reports, industry reports, market commentary, macro notes, strategy notes, and technical notes.
- **agent usage** = FA Agent, Evidence Agent, Strategy Agent, and Answer Composer.
- **official fact** = Vietcap describes Vietcap IQ as a financial analysis platform for investors that helps follow changes in the Vietnamese stock market.
- **MVP stance** = treat Vietcap as a document and evidence source first, not as the primary OHLCV database.

---
#### Access surface

- **Access:** web platform and public report URLs when available.
- **Build it:** crawler or manual download first; API only if official access exists.
- **Your own code:** parser code in Python can extract metadata, text, ticker mentions, tables, and report dates.

---
</details>

### Data Categories
<details open>
<summary>The useful data is mostly unstructured reports plus structured metadata.</summary>
---
#### Categories

| Category | Example | Agent use |
|---|---|---|
| company report | `FPT` update report | FA thesis and valuation context. |
| industry report | banking, real estate, technology | sector regime and peer comparison. |
| market report | VN-Index daily or monthly wrap | market context and breadth narrative. |
| macro report | rates, FX, liquidity, policy | macro regime input. |
| technical report | index or stock technical view | TA reference, not direct signal unless rule is formalized. |
| recommendation fields | target price, rating, upside | evidence input, not automatic trade decision. |

---
#### Important fields

- `report_id` = stable internal ID.
- `source_name` = `vietcap`.
- `title` = report title.
- `category` = company, industry, market, macro, strategy, or technical.
- `tickers` = extracted ticker list.
- `published_at` = report publication date.
- `analyst` = author or team when available.
- `recommendation` = buy, hold, sell, outperform, or other source label when available.
- `target_price` = value and currency when available.
- `raw_pdf_path` = object-storage path.
- `text_hash` = hash for deduplication.

---
</details>

### Proposed Schema
<details open>
<summary>The schema should separate report metadata from retrievable chunks.</summary>
---
#### Tables

| Table | Fields | Notes |
|---|---|---|
| `reports` | `report_id`, `source_id`, `title`, `category`, `published_at`, `url`, `raw_path`, `text_hash` | one row per report. |
| `report_tickers` | `report_id`, `security_id`, `mention_type` | connects reports to securities. |
| `report_chunks` | `chunk_id`, `report_id`, `chunk_text`, `page`, `section`, `embedding_id` | supports semantic retrieval. |
| `report_metrics` | `report_id`, `metric_name`, `metric_value`, `unit`, `period` | optional structured extraction. |

---
#### Worked example

- **document** = an `FPT` company update report.
- **metadata** = `category=company`, `ticker=FPT`, `published_at=2025-03-15`.
- **chunk** = page text around revenue growth and target price.
- **usage** = FA Agent retrieves the chunk, but Strategy Agent must still check price data and risk before any trade decision.
- **read** = a positive report can support a thesis; it is not by itself a buy signal.

---
</details>

### Quality And Usage
<details open>
<summary>The main risk is treating analyst text as hard evidence without timestamp and source checks.</summary>
---
#### Data quality issues

- **login risk** = some content may require account access.
- **PDF parsing risk** = tables and Vietnamese text may parse incorrectly.
- **timestamp risk** = report date must be extracted reliably for point-in-time use.
- **ticker extraction risk** = company names can appear without explicit tickers.
- **recommendation drift** = old target prices may be stale after earnings or market moves.

---
#### Agent rules

- FA Agent can use report content to form a thesis.
- Evidence Agent must show report date, source, and exact supporting chunk.
- Backtest Agent must not use a report before its `published_at` date.
- Answer Composer must use cautious wording if the evidence is analyst opinion, not observed market data.

---
#### Cons and references

- **main con** = public access and document structure may be inconsistent across reports.
- **net** = use Vietcap as high-value evidence, but keep raw files and timestamps for audit.
- `REF_VIETCAP_IQ`: Vietcap IQ official user guide.
- `REF_VIETCAP_RESEARCH`: Vietcap public research reports and disclosures.

---
</details>
