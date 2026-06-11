---
title: autonomous_trading_agent_dev_master
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Autonomous Trading Agent - Dev Master Doc

## 1. Purpose

Single source of truth for implementation and coding agents working on the Autonomous Trading Agent MVP.

Use this document to implement source/vendor/provider ingestion, raw evidence capture, canonical schemas, data quality checks, feature generation, signal generation, backtesting, validation gates, trace storage, and answer composition. Domain notes and paper notes are supporting material, not coding instructions.

Active source scope: HSX/HOSE, Vietcap IQ, VBMA, and FRED/fredapi.

## 2. Consolidated Sources

| Source doc | Contribution |
|---|---|
| `docs/architecture/02_trading_agent_architecture_overview.md` | Module map, decision states, MVP boundary, end-to-end flow. |
| `docs/architecture/03_data_pipeline_architecture.md` | raw → bronze → silver → gold pipeline, data quality outputs, lineage fields. |
| `docs/architecture/04_db_infrastructure_options.md` | MVP storage direction: keep moving parts small, use files/Parquet first, defer heavier infra. |
| `docs/architecture/05_schema_design_principles.md` | Entity boundaries, stable IDs, point-in-time rules, validation gates. |
| `docs/plans/01_data_crawling_plan.md` | Crawl scope, source priority, raw capture contract, failure handling. |
| `docs/plans/02_database_schema_plan.md` | Entity plan, schema implementation order, reproducibility invariants. |
| `docs/plans/03_mvp_6_week_plan.md` | MVP scope, demo scenarios, acceptance signals. |
| `docs/plans/04_agent_architecture_plan.md` | Agent roles, tool contract shape, answer policy, unanswered behavior. |
| `docs/plans/05_sample_user_questions.md` | Evaluation questions for market, strategy, evidence, and safety paths. |
| `docs/plans/06_risk_register.md` | Data, backtest, LLM, and product risks that become validation gates. |
| `docs/data_sources/01_vietcap_iq.md` | Reports/evidence source ideas; not primary OHLCV. |
| `docs/data_sources/02_hsx_hose.md` | Official market-data source direction and schema ideas. |
| `docs/data_sources/03_vbma.md` | Optional later local bond/rates context. |
| `docs/data_sources/04_fred_api.md` | Optional later global macro context and point-in-time macro caution. |

Excluded: `docs/domain_knowledge/*` (TA/FA reference only), `docs/research_notes/*` (paper notes only).

## 3. MVP Boundary

In scope: source/vendor probing; official daily OHLCV and symbol master ingestion; raw evidence preservation; canonical `securities`, `daily_prices`, `corporate_events` tables; data quality validation; feature generation; deterministic buy/sell/hold signals; backtest with cost/slippage; validation gates.

Optional later: FRED macro, VBMA bond context, Vietcap IQ reports, company news, vector search.

Out of scope: live trading, broker execution, HFT, RL-based trading, real-money advice.

## 4. Source-First Ingestion Strategy

Source-level adapters expose the real fields, timestamps, adjustment flags, identifiers, and access constraints that shape schema and DB design. Wrapper libraries hide field provenance; the agent must be able to explain where each value came from.

Required raw evidence per response: raw body or file, request URL or endpoint name, request params/headers/auth mode (no secrets), crawl timestamp, HTTP status, content type, row count, original columns, parser version, content hash, raw path, error payload.

## 5. Target Implementation Pipeline

```text
source -> raw capture -> bronze parser -> silver canonical table -> gold features -> signal -> backtest -> validation -> agent answer
```

| Layer | Coding meaning | Required output |
|---|---|---|
| `source` | Verified HSX/HOSE, Vietcap IQ, VBMA, or FRED surface. | Source probe result and access notes. |
| `raw` | Exact response, export, or serialized object before interpretation. | Raw file path, crawl metadata, source ID, content hash. |
| `bronze` | Minimally parsed source-shaped rows; preserve original names. | Parse status, parser version, schema version, raw path. |
| `silver` | Canonical normalized tables with stable IDs, types, units, quality status. | Parquet tables: `securities`, `daily_prices`, `corporate_events`. |
| `gold` | Feature-ready tables derived from silver with point-in-time rules. | Returns, moving averages, volatility, volume ratios, feature timestamps. |
| `signal` | Rule output from features. | Signal rows with date, security, action, score, reason code, intended execution. |
| `backtest` | Historical simulation using signal, price, cost, and slippage assumptions. | Trades, metrics, equity curve, assumptions, status. |
| `validation` | Gates that decide reject/revise/promote/unanswered. | Gate results, failed gates, warnings, decision proposal. |
| `agent answer` | Final user-facing summary based only on tool outputs. | Observed facts, interpretation, decision, limitations, next steps. |

## 6. Module Map

| Module | Responsibility | Must not do |
|---|---|---|
| `source_probe_tool` | Verify what each source exposes before building a full crawler. | Claim a source is usable without a probe result. |
| `source_adapter` | Fetch source-level payloads and expose a common interface for raw capture. | Hide source errors, store secrets, or silently transform fields without raw evidence. |
| `market_data_tool` | Load canonical market data for requested symbols and date range. | Silently fill large gaps, invent adjusted prices, or return rows without `source_id`. |
| `data_quality_tool` | Validate schema, duplicates, OHLC consistency, date order, missing dates, units, source linkage. | Downgrade blocking errors to warnings without an explicit diagnostic mode. |
| `feature_tool` | Compute point-in-time features from clean silver data. | Use future rows, mix adjusted and unadjusted prices without a warning. |
| `signal_tool` | Convert features into deterministic signal rows. | Create discretionary LLM signals or change strategy rules after seeing backtest results. |

## 7. Focused Source Priority

| Priority | Source | Role | Blocking for MVP? |
|---|---|---|---|
| P0 | HSX/HOSE | Canonical stock-market target: universe, OHLCV, corporate actions, indexes, trading calendar. | Yes, once verified. |
| P1/P2 | Vietcap IQ | Company profiles, financial statements, ratios, reports, evidence. | No for primary OHLCV. |
| P2 | VBMA | Vietnam bonds, auctions, yields, rates, local macro context. | No for primary stock OHLCV. |
| P2/P3 | FRED/fredapi | Global macro series, observations, rates, inflation, regime context. | No for primary stock OHLCV. |

Do not add other sources unless the mentor explicitly asks. Do not claim a source is production-usable until access, terms, response fields, and sample raw capture are verified.

## 8. Canonical Data Contracts

### 8.1 `securities`

| Field | Contract |
|---|---|
| source dataset | Official/vendor symbol master, listing page, or securities API. |
| target canonical table | `securities` |
| MVP priority | P0 |
| role in pipeline | Symbol master, exchange mapping, stable ID for all downstream tables. |
| primary key | `security_id` |
| output path | `data/silver/securities.parquet` |

MVP `security_id` rule: `{source_family}:{exchange}:{symbol}` or `{source_family}:UNKNOWN:{symbol}` if exchange is missing. Keep separate IDs for the same symbol on multiple exchanges.

### 8.2 `daily_prices`

| Field | Contract |
|---|---|
| source dataset | Source/vendor daily OHLCV endpoint, file, page, or official feed. |
| target canonical table | `daily_prices` |
| MVP priority | P0 |
| role in pipeline | Source for features, signals, backtests, validation, and basic risk metrics. |
| primary key | `security_id + trade_date + source_id` |
| output path | `data/silver/daily_prices.parquet` |

Quality checks: no duplicate `security_id + trade_date`; price fields numeric; `high >= max(open, close)`; `low <= min(open, close)`; `volume >= 0`; `source_id` and `raw_path` not null; dates sorted per symbol; warn if `adjusted_close` missing.

### 8.3 `corporate_events`

| Field | Contract |
|---|---|
| source dataset | Source/vendor corporate action endpoint, page, event file, or issuer disclosure. |
| target canonical table | `corporate_events` |
| MVP priority | P1 |
| role in pipeline | Corporate-action awareness, price-adjustment warning, point-in-time event context. |
| primary key | `event_id` |
| output path | `data/silver/corporate_events.parquet` |


## 9. Data Quality Gates

| Gate | Applies to | Blocking rule |
|---|---|---|
| source probe | All new sources | Source cannot be used as canonical until access, fields, and terms are recorded. |
| schema validation | All canonical tables | Required fields missing or wrong type → fail. |
| duplicate checks | All primary keys | Duplicate primary key → fail or quarantine. |
| OHLC consistency | `daily_prices`, realtime snapshots | `high < max(open, close)` or `low > min(open, close)` → fail. |
| missing data | `daily_prices` | Missing trading days above threshold → unanswered for backtest. |
| unit checks | Prices, volume, value, financials | Unknown unit → warn; conflicting unit → fail if used for metrics. |
| adjusted/unadjusted warning | `daily_prices`, `corporate_events` | Missing adjusted price or corporate-action handling → warn in backtest. |
| source ID requirement | All canonical tables | Missing `source_id` or `raw_path` → fail. |
| point-in-time checks | Reports, macro, FA, news | Missing publication/release date → do not use for historical causal claims. |

Quality statuses: `pass` (usable), `warn` (usable with limitation), `fail` (not usable downstream).

## 10. First Implementation Target

Next coding target: source-level probing, not full ingestion.

Outputs: `scripts/probe_sources.py`; source adapter skeletons; raw sample files under `data/raw/source_probe/...`; probe metadata JSON per source.

Probe behavior: record access status (`verified`, `auth_required`, `manual_only`, `blocked`, `not_configured`, `unknown`); preserve raw evidence; do not build full ingestion until at least one canonical OHLCV-capable source is verified.

## 11. Acceptance Criteria

- Source-first ingestion is the canonical path; active scope is limited to HSX/HOSE, Vietcap IQ, VBMA, and FRED/fredapi.
- Data contracts are source-agnostic and concrete; the first coding target is unambiguous.
- Raw evidence, source IDs, parser metadata, and source terms are required before canonical ingestion.
- FRED and VBMA are non-blocking macro/rates context; Vietcap IQ is company/FA evidence context, not primary OHLCV.
