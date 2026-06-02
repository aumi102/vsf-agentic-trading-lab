---
title: autonomous_trading_agent_dev_master
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Autonomous Trading Agent - Dev Master Doc

## 1. Purpose

This is the single source of truth for implementation and coding agents working on the Autonomous Trading Agent MVP.

Use this document to implement source/vendor/provider ingestion, raw evidence capture, canonical schemas, data quality checks, feature generation, signal generation, backtesting, validation gates, trace storage, and answer composition. Do not treat this as a research summary. Domain notes and paper notes remain supporting material, not coding instructions.

The project direction is now source-first. `vnstock` is prototype/fallback/reference only and must not be treated as the canonical MVP data source.

## 2. Consolidated Sources

| Source doc | Contribution |
|---|---|
| `docs/architecture/02_trading_agent_architecture_overview.md` | module map, decision states, MVP boundary, end-to-end flow. |
| `docs/architecture/03_data_pipeline_architecture.md` | raw -> bronze -> silver -> gold pipeline, data quality outputs, lineage fields. |
| `docs/architecture/04_db_infrastructure_options.md` | MVP storage direction: keep moving parts small, use files/Parquet first, defer heavier infra. |
| `docs/architecture/05_schema_design_principles.md` | entity boundaries, stable IDs, point-in-time rules, validation gates. |
| `docs/plans/01_data_crawling_plan.md` | crawl scope, source priority, raw capture contract, failure handling. |
| `docs/plans/02_database_schema_plan.md` | entity plan, schema implementation order, reproducibility invariants. |
| `docs/plans/03_mvp_6_week_plan.md` | MVP scope, demo scenarios, acceptance signals. |
| `docs/plans/04_agent_architecture_plan.md` | agent roles, tool contract shape, answer policy, unanswered behavior. |
| `docs/plans/05_sample_user_questions.md` | later evaluation questions for market, strategy, evidence, and safety paths. |
| `docs/plans/06_risk_register.md` | data, backtest, LLM, and product risks that become validation gates. |
| `docs/data_sources/01_vietcap_iq.md` | reports/evidence source ideas; not primary OHLCV. |
| `docs/data_sources/02_hsx_hose.md` | official market-data source direction and schema ideas. |
| `docs/data_sources/03_vbma.md` | optional later local bond/rates context. |
| `docs/data_sources/04_fred_api.md` | optional later global macro context and point-in-time macro caution. |

Excluded from consolidation:

- `docs/domain_knowledge/*` = TA/FA/reference material only.
- `docs/research_notes/*` = paper and research notes only.
- Paper notes are not copied here unless they directly affect implementation contracts.

## 3. MVP Boundary

In scope:

- Direct source/vendor/provider probing before full ingestion.
- Official or vendor-level daily OHLCV and symbol master ingestion where access is verified.
- Raw evidence preservation for every source response, export, or page payload.
- Canonical `securities`, `daily_prices`, and `corporate_events` tables.
- Data quality validation.
- Feature generation from canonical daily OHLCV.
- Deterministic buy/sell/hold or position signals.
- Backtest with cost and slippage assumptions.
- Validation gates for data quality, cost, drawdown, benchmark, sample size, leakage, and source limitations.
- Trace records for tool inputs, outputs, warnings, failures, source IDs, and final decisions.

Prototype/fallback only:

- `vnstock` can be used to compare fields, test normalizers, and keep a fallback demo path.
- `vnstock` must not be the canonical source for MVP market data after mentor feedback.

Optional later:

- FRED macro series.
- VBMA bond/rates context.
- Vietcap reports and research evidence.
- Company news.
- Macro/evidence retrieval.
- Vector search over reports/news.

Out of scope:

- Live trading.
- Broker execution.
- High-frequency order book strategy.
- RL-based trading.
- Real-money buy/sell advice.

## 4. Source-First Ingestion Strategy

### Why Source First

<details open>
<summary>Source-level crawling is the main learning and implementation path.</summary>

---

#### Rationale

- Source/vendor/provider data exposes the real fields, timestamps, adjustment flags, identifiers, and access constraints that shape schema and DB design.
- Wrapper libraries hide field provenance and may rename, drop, join, or transform values before the project can audit them.
- The trading agent must be able to explain where a price, event, report, or macro value came from.
- Provider-level adapters make data quality, legal/access constraints, point-in-time rules, and failure handling explicit.
- `vnstock` is useful as a prototype reference, but relying on it as canonical would skip the intended data infrastructure work.

---

#### Raw evidence that must be preserved

- Raw response body, downloaded file, page snapshot, or serialized payload.
- Request URL or endpoint name when allowed.
- Request parameters, symbol, date range, headers/auth mode without secrets.
- Crawl timestamp and source-provided timestamp if present.
- HTTP status, provider status, content type, row count, original columns, parser version.
- Content hash and local raw path.
- Error payload or failure reason.

---

#### Why source fields matter

- Schema design depends on provider identifiers, exchange codes, timestamp names, corporate-action flags, adjusted-price fields, and security type fields.
- DB design needs stable source IDs, crawl run IDs, source-specific row keys, and provenance fields.
- Backtest correctness depends on adjusted/unadjusted price flags, corporate-action fields, release timestamps, and next-bar execution assumptions.
- Agent answers must distinguish observed source facts from inferred interpretation.

---

#### Adapter mapping rule

Each source-specific adapter maps raw source fields into canonical tables, but must keep raw fields available through `raw_path`, `source`, `source_id`, `schema_version`, and parser metadata.

---

</details>

## 5. Target Implementation Pipeline

```text
source -> raw capture -> bronze parser -> silver canonical table -> gold features -> signal -> backtest -> validation -> agent answer
```

| Layer | Coding meaning | Required output |
|---|---|---|
| `source` | verified official/vendor/provider surface, including public pages, APIs, downloads, or paid feeds. | source probe result and access notes. |
| `raw` | exact response, export, page payload, or serialized object before interpretation. | raw file path, crawl metadata, source ID, content hash. |
| `bronze` | minimally parsed source-shaped rows; preserve original names where useful. | parse status, parser version, schema version, raw path. |
| `silver` | canonical normalized tables with stable IDs, types, units, and quality status. | Parquet tables such as `securities`, `daily_prices`, `corporate_events`. |
| `gold` | feature-ready tables derived from silver with point-in-time rules. | returns, moving averages, volatility, volume ratios, feature timestamps. |
| `signal` | rule output from features. | signal rows with date, security, action, score, reason code, intended execution. |
| `backtest` | historical simulation using signal, price, cost, and slippage assumptions. | trades, metrics, equity curve, assumptions, status. |
| `validation` | gates that decide reject/revise/promote/unanswered. | gate results, failed gates, warnings, decision proposal. |
| `agent answer` | final user-facing summary based only on tool outputs. | observed facts, interpretation, decision, limitations, next steps. |

## 6. Module Map

### `source_probe_tool`

- **responsibility:** verify what each source exposes before building a full crawler.
- **input:** source name, endpoint/page/download candidate, sample symbols, date range.
- **output:** probe status, access/auth status, available fields, sample raw path, legal/terms notes.
- **failure modes:** inaccessible source, auth required, blocked request, unknown schema, manual-only access.
- **must not do:** claim a source is usable without a probe result.

### `source_adapter`

- **responsibility:** fetch source-level payloads and expose a common interface for raw capture.
- **input:** source config, symbols, dates, credentials from environment when needed.
- **output:** `FetchResult` with raw payload metadata and source-specific fields.
- **failure modes:** auth failure, rate limit, network failure, schema drift, empty response.
- **must not do:** hide source errors, store secrets, or silently transform fields without raw evidence.

### `market_data_tool`

- **responsibility:** load canonical market data for requested symbols and date range.
- **input:** symbols, exchange filter, start date, end date, dataset version, adjusted-price preference.
- **output:** `daily_prices` rows plus dataset metadata.
- **failure modes:** symbol not found, date range unavailable, source file missing, schema mismatch.
- **must not do:** silently fill large gaps, invent adjusted prices, return rows without `source_id`.

### `data_quality_tool`

- **responsibility:** validate schema, duplicates, OHLC consistency, date order, missing dates, units, source linkage.
- **input:** canonical table name, rows or dataset path, expected schema, quality thresholds.
- **output:** `quality_status`, `quality_reasons`, failed rows if available, warnings.
- **failure modes:** missing required column, duplicate key, unparseable date, invalid OHLC, missing source metadata.
- **must not do:** downgrade blocking errors to warnings without an explicit diagnostic mode.

### `feature_tool`

- **responsibility:** compute point-in-time features from clean silver data.
- **input:** `daily_prices`, feature config, lookback windows, date range.
- **output:** feature table with `security_id`, `trade_date`, feature names, values, and `feature_timestamp`.
- **failure modes:** insufficient lookback history, missing close/volume, non-trading date alignment issue.
- **must not do:** use future rows, mix adjusted and unadjusted prices without a warning, recompute with hidden defaults.

### `signal_tool`

- **responsibility:** convert features into deterministic signal rows.
- **input:** feature table, strategy config, signal rules, allowed positions.
- **output:** signal table with action, score, reason code, and rule version.
- **failure modes:** undefined strategy rule, missing feature, ambiguous signal conflict.
- **must not do:** create discretionary LLM signals or change strategy rules after seeing backtest results.

## 7. Source And Provider Priority

| Priority | Source/provider | Role | Blocking for MVP? |
|---|---|---|---|
| P0 | HSX/HOSE official data surfaces | official exchange reference for symbol, market, and trading data where accessible. | yes, if accessible fields cover daily OHLCV. |
| P0/P1 | SSI FastConnect Data | candidate vendor API for securities, daily OHLC, intraday OHLC, daily index, daily stock price, and streaming. | yes only after access/auth is verified. |
| P1 | FiinGroup Datafeed | candidate vendor feed for EOD price, adjusted price, foreign trading, and market-depth-style fields. | yes only after access/auth is verified. |
| P2 | Vietcap IQ / Vietcap Research | reports, research, company context, and evidence retrieval; not primary OHLCV. | no for first market-data MVP. |
| P2 | VBMA | Vietnam bond/rates context. | no for first market-data MVP. |
| P2/P3 | FRED API | global macro context and release-timestamp caution. | no for first market-data MVP. |
| prototype | `vnstock` | fallback/reference adapter for existing prototype and field comparison. | no. |

See `docs/source_provider_matrix.md` for the current provider matrix. Do not claim a provider is production-usable until access, terms, response fields, and sample raw capture are verified.

## 8. Canonical Data Contracts

Canonical tables are source-agnostic. A source-specific adapter may produce these rows from HSX/HOSE, SSI, FiinGroup, or another verified source. `vnstock` can produce the same tables only as prototype/fallback output.

### 8.1 `securities`

| Field | Contract |
|---|---|
| source dataset | official/vendor symbol master, listing page, securities API, or equivalent source-level payload. |
| target canonical table | `securities`. |
| MVP priority | P0. |
| role in pipeline | symbol master, exchange mapping, stable ID for all downstream tables. |
| primary key | `security_id`. |
| output path | `data/silver/securities.parquet`. |

Required fields:

- `security_id: string`
- `symbol: string`
- `exchange: string`
- `company_name: string | null`
- `security_type: string | null`
- `industry: string | null`
- `market_cap: float | null`
- `foreign_room: float | null`
- `source: string`
- `source_id: string`
- `raw_path: string | null`
- `crawled_at: datetime`
- `schema_version: string`

MVP `security_id` rule:

- If exchange exists: `{source_family}:{exchange}:{symbol}` or `vn:{exchange}:{symbol}` after a canonical VN namespace is chosen.
- If exchange is missing: `{source_family}:UNKNOWN:{symbol}`.
- If one symbol appears on multiple known exchanges, keep separate `security_id` values.

### 8.2 `daily_prices`

| Field | Contract |
|---|---|
| source dataset | source/vendor daily OHLCV endpoint, file, page, or official feed. |
| target canonical table | `daily_prices`. |
| MVP priority | P0. |
| role in pipeline | source for features, signals, backtests, validation, and basic risk metrics. |
| primary key | `security_id + trade_date + source_id`. |
| output path | `data/silver/daily_prices.parquet`. |

Required fields:

- `security_id: string`
- `symbol: string`
- `exchange: string`
- `trade_date: date`
- `open: float`
- `high: float`
- `low: float`
- `close: float`
- `volume: float`
- `value: float | null`
- `adjusted_close: float | null`
- `adjustment_status: string | null`
- `source: string`
- `source_id: string`
- `raw_path: string`
- `crawled_at: datetime`
- `schema_version: string`
- `quality_status: string`
- `quality_reasons: list[string]`

Quality checks:

- no duplicate `security_id + trade_date`.
- `trade_date` parseable.
- price fields numeric.
- `high >= max(open, close)`.
- `low <= min(open, close)`.
- `volume >= 0`.
- `source_id` and `raw_path` not null.
- dates sorted per symbol.
- warn if `adjusted_close` is missing or unclear.

### 8.3 `corporate_events`

| Field | Contract |
|---|---|
| source dataset | source/vendor corporate action endpoint, page, event file, or issuer disclosure source. |
| target canonical table | `corporate_events`. |
| MVP priority | P1. |
| role in pipeline | corporate-action awareness, price-adjustment warning, point-in-time event context. |
| primary key | `event_id`. |
| output path | `data/silver/corporate_events.parquet`. |

Required fields:

- `event_id: string`
- `security_id: string`
- `symbol: string`
- `event_type: string | null`
- `title: string | null`
- `description: string | null`
- `announcement_date: date | null`
- `ex_date: date | null`
- `record_date: date | null`
- `payment_date: date | null`
- `effective_date: date | null`
- `cash_dividend: float | null`
- `stock_dividend_ratio: float | null`
- `issue_ratio: float | null`
- `source: string`
- `source_id: string`
- `raw_path: string`
- `crawled_at: datetime`
- `schema_version: string`
- `quality_status: string`
- `quality_reasons: list[string]`

## 9. Data Quality Gates

| Gate | Applies to | Blocking rule |
|---|---|---|
| source probe | all new sources | source cannot be used as canonical until access, fields, and terms are recorded. |
| schema validation | all canonical tables | required fields missing or wrong type -> fail. |
| duplicate checks | all primary keys | duplicate primary key -> fail or quarantine. |
| OHLC consistency | `daily_prices`, realtime snapshots when fields exist | `high < max(open, close)` or `low > min(open, close)` -> fail. |
| missing data | `daily_prices` | missing trading days above threshold -> unanswered for backtest. |
| unit checks | prices, volume, value, financials | unknown unit -> warn; conflicting unit -> fail if used for metrics. |
| adjusted/unadjusted warning | `daily_prices`, `corporate_events` | missing adjusted price/corporate-action handling -> warn in backtest output. |
| source ID requirement | all canonical tables | missing `source_id` or `raw_path` -> fail. |
| point-in-time checks | reports, macro, financial statements, news | missing publication/release/announcement date -> do not use for historical causal claims. |
| tool failure propagation | all tools | required upstream tool failure -> downstream tools stop unless diagnostic mode. |

Canonical quality statuses:

- `pass`: usable for MVP pipeline.
- `warn`: usable with limitation in trace and answer.
- `fail`: not usable for downstream conclusion.

## 10. First Implementation Target After This Doc

Next coding target: source-level probing, not full ingestion.

Required outputs:

- `scripts/probe_sources.py`
- source adapter skeletons for source-level probing.
- raw sample files under `data/raw/source_probe/...`.
- probe metadata JSON per source.
- `reports/source_probe_report.md`.

Prototype behavior:

- Probe HSX/HOSE, SSI FastConnect candidate endpoints if credentials/config exist, FiinGroup if credentials/config exist, Vietcap public/research surfaces if available, VBMA/FRED as non-blocking context, and `vnstock` as fallback/reference only.
- Record access status as `verified`, `auth_required`, `manual_only`, `blocked`, `not_configured`, or `unknown`.
- Preserve raw evidence for every successful probe.
- Do not build full ingestion until at least one canonical OHLCV-capable source is verified.

Do not implement backtest, agent orchestration, vector search, FRED/VBMA/Vietcap ingestion, or production DB infrastructure in the source probe task.

## 11. Acceptance Criteria

This document is acceptable if:

- source/vendor/provider ingestion is the canonical path.
- `vnstock` is clearly prototype/fallback/reference only.
- data contracts are source-agnostic and concrete.
- the first source-first coding target is unambiguous.
- raw evidence, source IDs, parser metadata, and source terms are required before canonical ingestion.
- FRED and VBMA are clearly non-blocking macro/rates context.
- Vietcap is clearly reports/evidence context, not primary OHLCV.
- no `domain_knowledge` or long paper notes are copied.
