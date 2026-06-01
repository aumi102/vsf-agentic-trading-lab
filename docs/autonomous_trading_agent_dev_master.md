# Autonomous Trading Agent - Dev Master Doc

## 1. Purpose

This is the single source of truth for implementation and coding agents working on the Autonomous Trading Agent MVP.

Use this document to implement data ingestion, canonical data contracts, feature generation, signal generation, backtesting, validation gates, trace storage, and answer composition. Do not treat this as a research summary. Domain notes and paper notes remain supporting material, not coding instructions.

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
| `docs/data_sources/01_vietcap_iq.md` | optional later report/evidence source contract. |
| `docs/data_sources/02_hsx_hose.md` | VN market-data schema ideas that map to vnstock OHLCV and symbol data. |
| `docs/data_sources/03_vbma.md` | optional later local bond/rates context. |
| `docs/data_sources/04_fred_api.md` | optional later global macro context and point-in-time macro caution. |

Excluded from consolidation:

- `docs/domain_knowledge/*` = reference material only.
- `docs/research_notes/*` = paper and research notes only.
- Paper notes are not copied here unless they directly affect implementation contracts.

## 3. MVP Boundary

In scope:

- vnstock daily OHLCV ingestion.
- vnstock symbol master ingestion.
- Data quality validation.
- Feature generation from daily OHLCV.
- Buy/sell/hold or position signals.
- Backtest with cost and slippage assumptions.
- Validation gates for data quality, cost, drawdown, benchmark, sample size, and leakage.
- Trace records for tool inputs, outputs, warnings, failures, and final decisions.

Optional later:

- FRED macro series.
- VBMA bond/rates context.
- Vietcap reports.
- Company news.
- Macro/evidence retrieval.
- Vector search over reports/news.

Out of scope:

- Live trading.
- Broker execution.
- High-frequency order book strategy.
- RL-based trading.
- Real-money buy/sell advice.

## 4. Target Implementation Pipeline

```text
raw -> bronze -> silver -> gold -> signal -> backtest -> validation -> agent answer
```

| Layer | Coding meaning | Required output |
|---|---|---|
| `raw` | exact vnstock response, export, or serialized payload before interpretation. | raw file path, crawl metadata, source ID, content hash. |
| `bronze` | minimally parsed source-shaped rows; preserve original names where useful. | parse status, parser version, schema version, raw path. |
| `silver` | canonical normalized tables with stable IDs, types, units, and quality status. | Parquet tables such as `securities`, `daily_prices`, `corporate_events`. |
| `gold` | feature-ready tables derived from silver with point-in-time rules. | returns, moving averages, volatility, volume ratios, feature timestamps. |
| `signal` | rule output from features. | signal rows with date, security, action, score, reason code. |
| `backtest` | historical simulation using signal, price, cost, and slippage assumptions. | trades, metrics, equity curve, assumptions, status. |
| `validation` | gates that decide reject/revise/promote/unanswered. | gate results, failed gates, warnings, decision proposal. |
| `agent answer` | final user-facing summary based only on tool outputs. | observed facts, interpretation, decision, limitations, next steps. |

## 5. Module Map

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

### `backtest_tool`

- **responsibility:** simulate strategy using prices, signals, cost, slippage, and execution timing.
- **input:** `daily_prices`, signal table, initial capital, cost config, slippage config, execution rule.
- **output:** trades, equity curve, metrics, assumptions, status.
- **failure modes:** missing cost config, missing prices after signal, invalid execution date, too few trades.
- **must not do:** ignore costs by default, execute at the same close used to generate a close-based signal, invent benchmark data.

### `validation_gate_tool`

- **responsibility:** convert tool outputs into gate statuses and a decision proposal.
- **input:** data quality report, backtest metrics, trade count, benchmark metrics, cost sensitivity, warnings.
- **output:** gate table, failed gates, decision proposal: `reject`, `revise`, `promote_to_backtest`, `promote_to_paper_test`, or `unanswered`.
- **failure modes:** missing metrics, missing benchmark, missing assumptions, tool failure upstream.
- **must not do:** promote a strategy when a required gate is absent.

### `trace_store`

- **responsibility:** persist run, tool input, tool output, status, warning, failure reason, and final decision.
- **input:** run ID, user request, module calls, configs, outputs, error records.
- **output:** reproducible trace record and trace IDs linked to tables/reports.
- **failure modes:** trace write failure, missing run ID, unserializable payload.
- **must not do:** store only natural-language summaries; raw structured payloads are required for audit.

### `answer_composer`

- **responsibility:** produce cautious final answer from structured outputs.
- **input:** user request, trace summary, metrics, gate results, limitations.
- **output:** observed facts, interpretation, decision, failed gates, limitations, next steps.
- **failure modes:** missing tool output, conflicting gates, unanswered decision.
- **must not do:** invent metrics, causal explanations, or buy/sell advice.

## 6. vnstock Data Source Priority

| Priority | Dataset | Why |
|---|---|---|
| P0 | `listing_all_symbols` | baseline symbol universe and company names. |
| P0 | `listing_symbols_by_exchange` | exchange/security-type mapping for stable `security_id`. |
| P0 | `ohlcv` | required for daily features, signals, and first backtest. |
| P1 | `price_board` | realtime quote snapshot experiments and bid/ask structure, not first backtest. |
| P1 | `company_events` | corporate actions and event limitations for price/backtest warnings. |
| P1 | `company_overview` | metadata enrichment for securities and company profiles. |
| P2 | `fin_balance`, `fin_income`, `fin_cashflow` | later FA/fundamental features. |
| P2 | `fin_ratio` | later factor/fundamental features. |
| P2 | `company_news` | later Evidence Agent input with timestamp alignment. |
| P2 | `company_shareholders`, `company_officers` | later governance/ownership context. |
| P2 | `company_trading_stats` | metadata and liquidity/trading-profile enrichment. |
| P3 | FRED API | global macro context; non-blocking for first ingestion/backtest prototype. |
| P3 | VBMA | local rates/bond context; non-blocking for first ingestion/backtest prototype. |
| P3 | Vietcap reports | report/evidence retrieval; non-blocking for first ingestion/backtest prototype. |

FRED and VBMA provide macro/rates context. They should not block the first vnstock ingestion and daily backtest prototype because the first prototype must prove market-data ingestion, data quality, feature generation, signal generation, backtest, validation, and trace.

## 7. vnstock Canonical Data Contracts

### 7.1 `securities`

| Field | Contract |
|---|---|
| source dataset | `listing_all_symbols`, `listing_symbols_by_exchange`, `company_overview`. |
| target canonical table | `securities`. |
| MVP priority | P0. |
| role in pipeline | symbol master, exchange mapping, stable ID for all downstream tables. |
| primary key | `security_id`. |
| output path | `data/silver/securities.parquet`. |

Required fields:

- `security_id: string`
- `symbol: string`
- `exchange: string`
- `company_name: string`
- `security_type: string`
- `industry: string | null`
- `market_cap: float | null`
- `foreign_room: float | null`
- `source: string`
- `source_id: string`
- `crawled_at: datetime`
- `schema_version: string`

Optional fields:

- `short_name: string | null`
- `organ_name: string | null`
- `listed_date: date | null`
- `is_active: bool | null`

MVP `security_id` rule:

- If exchange exists: `vnstock:{exchange}:{symbol}`.
- If exchange is missing: `vnstock:UNKNOWN:{symbol}`.

Quality checks:

- `symbol` not null.
- no duplicate `security_id`.
- exchange normalized to known values where possible: `HOSE`, `HNX`, `UPCOM`, or `UNKNOWN`.
- company name present for listed symbols where source provides it.
- `source_id`, `crawled_at`, `schema_version` not null.

Notes/limitations:

- Use `listing_symbols_by_exchange` to resolve exchange when `company_overview` omits it.
- If one symbol appears on multiple exchanges, keep distinct `security_id` values.

### 7.2 `daily_prices`

| Field | Contract |
|---|---|
| source dataset | `ohlcv`: `1,266` rows, daily historical price, date range roughly `2023-11-10` to `2026-06-01`. |
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
- `source: string`
- `source_id: string`
- `raw_path: string`
- `crawled_at: datetime`
- `schema_version: string`
- `quality_status: string`
- `quality_reasons: list[string]`

Optional fields:

- `timeframe: string`
- `currency: string`
- `adjustment_status: string`

Quality checks:

- no duplicate `security_id + trade_date`.
- `trade_date` parseable.
- price fields numeric.
- `high >= max(open, close)`.
- `low <= min(open, close)`.
- `volume >= 0`.
- `source_id` not null.
- dates sorted per symbol.
- warn if `adjusted_close` is missing or unclear.

Notes/limitations:

- If adjusted price/corporate-action handling is unclear, backtest output must include the limitation: `prices may be unadjusted around corporate events`.
- Do not use same-day close for both signal generation and execution unless the strategy explicitly models next-bar execution.

### 7.3 `realtime_quote_snapshots`

| Field | Contract |
|---|---|
| source dataset | `price_board`: `3` rows, realtime board for `2` symbols, matched price, bid/ask depth, listing information. |
| target canonical table | `realtime_quote_snapshots`. |
| MVP priority | P1. |
| role in pipeline | realtime snapshot experiments, liquidity inspection, later execution realism. |
| primary key | `security_id + snapshot_at + source_id`. |
| output path | `data/silver/realtime_quote_snapshots.parquet`. |

Required fields:

- `security_id: string`
- `symbol: string`
- `exchange: string`
- `snapshot_at: datetime`
- `last_price: float | null`
- `last_volume: float | null`
- `total_volume: float | null`
- `total_value: float | null`
- `reference_price: float | null`
- `ceiling_price: float | null`
- `floor_price: float | null`
- `open: float | null`
- `high: float | null`
- `low: float | null`
- `change: float | null`
- `pct_change: float | null`
- `bid_price_1: float | null`
- `bid_volume_1: float | null`
- `ask_price_1: float | null`
- `ask_volume_1: float | null`
- `bid_price_2: float | null`
- `bid_volume_2: float | null`
- `ask_price_2: float | null`
- `ask_volume_2: float | null`
- `bid_price_3: float | null`
- `bid_volume_3: float | null`
- `ask_price_3: float | null`
- `ask_volume_3: float | null`
- `trading_status: string | null`
- `source: string`
- `source_id: string`
- `raw_path: string`
- `crawled_at: datetime`
- `schema_version: string`
- `quality_status: string`
- `quality_reasons: list[string]`

Optional fields:

- `listed_share: float | null`
- `security_type: string | null`
- `exchange_name: string | null`

Quality checks:

- `snapshot_at` not null.
- no duplicate `security_id + snapshot_at + source_id`.
- bid/ask prices numeric when present.
- bid volumes and ask volumes non-negative when present.
- `ceiling_price >= floor_price` when both present.
- warn if snapshot timestamp is crawl time rather than exchange-provided time.

MVP note:

- This is for realtime snapshot experiments only.
- Do not use this for the first daily backtest.

### 7.4 `corporate_events`

| Field | Contract |
|---|---|
| source dataset | `company_events`: `100` rows, corporate actions/events such as dividends, issuance, ex-right date. |
| target canonical table | `corporate_events`. |
| MVP priority | P1. |
| role in pipeline | corporate-action awareness, price-adjustment warning, point-in-time event context. |
| primary key | `event_id`. |
| output path | `data/silver/corporate_events.parquet`. |

Required fields:

- `event_id: string`
- `security_id: string`
- `symbol: string`
- `event_type: string`
- `title: string`
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

Optional fields:

- `event_url: string | null`
- `exchange: string | null`
- `currency: string | null`

Quality checks:

- `event_id` not null and unique.
- `security_id` and `symbol` not null.
- at least one event date present.
- event dates parseable when present.
- dividend and ratio fields non-negative when present.
- warn if `event_type` cannot be normalized.

MVP note:

- If adjusted price/corporate action handling is not implemented, backtest output must include limitation: `prices may be unadjusted around corporate events`.

### 7.5 `company_profiles`

| Field | Contract |
|---|---|
| source dataset | `company_overview`: `2` rows; `company_trading_stats`: `10` rows. |
| target canonical table | `company_profiles`. |
| MVP priority | P1/P2. |
| role in pipeline | metadata enrichment for symbols, company context, market cap, foreign room, target price. |
| primary key | `security_id + source_id`. |
| output path | `data/silver/company_profiles.parquet`. |

Required fields:

- `security_id: string`
- `symbol: string`
- `company_name: string | null`
- `industry: string | null`
- `market_cap: float | null`
- `foreign_room: float | null`
- `target_price: float | null`
- `profile: string | null`
- `source: string`
- `source_id: string`
- `crawled_at: datetime`
- `schema_version: string`

Optional fields:

- `exchange: string | null`
- `outstanding_shares: float | null`
- `free_float: float | null`
- `beta: float | null`
- `avg_volume: float | null`

Quality checks:

- `security_id` resolvable from `securities`.
- numeric fields parseable when present.
- market cap and foreign room non-negative when present.
- warn if company profile lacks crawl timestamp or source metadata.

MVP status:

- P1/P2 metadata enrichment.

### 7.6 `financial_statement_items`

| Field | Contract |
|---|---|
| source dataset | `fin_balance`: `208` rows; `fin_income`: `51` rows; `fin_cashflow`: `93` rows. Columns are years `2018-2025`. |
| target canonical table | `financial_statement_items`. |
| MVP priority | P2. |
| role in pipeline | later FA and fundamental feature extraction. |
| primary key | `security_id + statement_type + fiscal_year + fiscal_period + item_name + source_id`. |
| output path | `data/silver/financial_statement_items.parquet`. |

Normalize from wide format to long format.

Required fields:

- `security_id: string`
- `symbol: string`
- `statement_type: string`
- `fiscal_year: int`
- `fiscal_period: string | null`
- `item_name: string`
- `item_value: float | null`
- `unit: string | null`
- `currency: string | null`
- `source: string`
- `source_id: string`
- `raw_path: string`
- `crawled_at: datetime`
- `schema_version: string`

Optional fields:

- `announcement_date: date | null`
- `report_type: string | null`
- `is_audited: bool | null`

Quality checks:

- wide year columns must become long `fiscal_year` rows.
- `statement_type` must be one of `balance`, `income`, `cashflow`.
- fiscal year parseable.
- duplicate item keys flagged.
- warn if announcement date is missing because point-in-time joins are unsafe.

MVP status:

- P2, not required for first data ingestion prototype.

### 7.7 `financial_ratios`

| Field | Contract |
|---|---|
| source dataset | `fin_ratio`: `108` rows, financial ratios such as ROE, P/E, EPS. |
| target canonical table | `financial_ratios`. |
| MVP priority | P2. |
| role in pipeline | later factor/fundamental features. |
| primary key | `security_id + ratio_name + fiscal_year + fiscal_period + source_id`. |
| output path | `data/silver/financial_ratios.parquet`. |

Required fields:

- `security_id: string`
- `symbol: string`
- `ratio_name: string`
- `fiscal_year: int | null`
- `fiscal_period: string | null`
- `ratio_value: float | null`
- `unit: string | null`
- `source: string`
- `source_id: string`
- `crawled_at: datetime`
- `schema_version: string`

Optional fields:

- `announcement_date: date | null`
- `calculation_method: string | null`

Quality checks:

- ratio name not null.
- ratio value numeric when present.
- duplicate ratio keys flagged.
- warn if period or announcement date is missing.

MVP status:

- P2, later for factor/fundamental features.

### 7.8 `company_news`

| Field | Contract |
|---|---|
| source dataset | `company_news`: `100` rows, news with full content. |
| target canonical table | `company_news`. |
| MVP priority | P2/P3. |
| role in pipeline | later Evidence Agent input and timestamp-aligned explanation. |
| primary key | `news_id`. |
| output path | `data/silver/company_news.parquet`. |

Required fields:

- `news_id: string`
- `security_id: string`
- `symbol: string`
- `title: string`
- `summary: string | null`
- `content: string | null`
- `published_at: datetime | null`
- `url: string | null`
- `source: string`
- `source_id: string`
- `raw_path: string`
- `content_hash: string`
- `crawled_at: datetime`
- `schema_version: string`

Optional fields:

- `language: string | null`
- `author: string | null`
- `tags: list[string] | null`
- `chunk_count: int | null`
- `embedding_status: string | null`

Quality checks:

- title or content present.
- content hash not null for deduplication.
- published date parseable when present.
- warn if published date is missing because causal alignment is unsafe.
- duplicate `content_hash` flagged.

MVP status:

- P2/P3 for Evidence Agent.
- Do not use for causal explanation without timestamp alignment.

## 8. Data Quality Gates

| Gate | Applies to | Blocking rule |
|---|---|---|
| schema validation | all canonical tables | required fields missing or wrong type -> fail. |
| duplicate checks | all primary keys | duplicate primary key -> fail or quarantine. |
| OHLC consistency | `daily_prices`, realtime snapshots when fields exist | `high < max(open, close)` or `low > min(open, close)` -> fail. |
| missing data | `daily_prices` | missing trading days above threshold -> unanswered for backtest. |
| unit checks | prices, volume, value, financials | unknown unit -> warn; conflicting unit -> fail if used for metrics. |
| adjusted/unadjusted warning | `daily_prices`, `corporate_events` | missing adjusted price/corporate-action handling -> warn in backtest output. |
| source ID requirement | all canonical tables | missing `source_id` -> fail. |
| point-in-time checks | reports, macro, financial statements, news | missing publication/release/announcement date -> do not use for historical causal claims. |
| tool failure propagation | all tools | required upstream tool failure -> downstream tools stop unless diagnostic mode. |

Canonical quality statuses:

- `pass`: usable for MVP pipeline.
- `warn`: usable with limitation in trace and answer.
- `fail`: not usable for downstream conclusion.

## 9. First Implementation Target After This Doc

Next coding target: vnstock ingestion prototype only.

Inputs:

- symbols.
- start date.
- end date.

Required outputs:

- `data/raw/vnstock/...`
- `data/silver/securities.parquet`
- `data/silver/daily_prices.parquet`
- `data/silver/corporate_events.parquet`
- `reports/data_inventory.md`
- `reports/data_quality_report.md`

Prototype behavior:

- Crawl or load P0 datasets first: `listing_all_symbols`, `listing_symbols_by_exchange`, `ohlcv`.
- Add P1 `company_events` if available in the same run.
- Preserve raw payloads before normalization.
- Generate `security_id` using the MVP rule.
- Write silver Parquet outputs.
- Write a data inventory report with row counts, date ranges, symbols, and source IDs.
- Write a quality report with pass/warn/fail gates and limitations.

Do not implement features, signals, backtest, agent orchestration, vector search, FRED, VBMA, or Vietcap in the first ingestion prototype unless explicitly requested later.

## 10. Acceptance Criteria

This document is acceptable if:

- one file can guide a coding agent.
- data contracts are concrete.
- P0/P1/P2/P3 priority is clear.
- first ingestion target is unambiguous.
- FRED and VBMA are clearly non-blocking macro/rates context.
- no `domain_knowledge` or long paper notes are copied.
- no implementation code is written.
