---
title: progress_report
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Progress Report - Autonomous Trading Agent

## Executive Summary

- **Current focus:** source discovery, OHLCV safety planning, và chuẩn hóa architecture direction sau mentor feedback.
- **Completed:** Vietcap IQ broad universe, listed-market fetch candidate `1598` symbols, index universe separation, gap-chart `FPT/VNM/VCB`, parser dry-run, controlled fetcher plan-only, tiny controlled execute.
- **Blocked:** full-universe fetch, DB ingestion, backtest, financial statement ingestion, and production agent tools.
- **Next:** review Vietcap IQ FA endpoint access after FPT-only non-secret probes returned `403`, review architecture with mentor, define first tool contracts.

Kiến trúc chi tiết nằm ở `docs/architecture/02_trading_agent_architecture_overview.md`.

---

## TL;DR cho mentor

- Product nên được hiểu là **agent/tool product**, không phải chỉ là backtest pipeline.
- Architecture canonical doc: `docs/architecture/02_trading_agent_architecture_overview.md`.
- Backtest là một module/tool, không phải toàn bộ product.
- Progress hiện tại là data discovery + parser dry-run + safe fetch planning, chưa phải DB/backtest.
- Vietcap IQ universe: `2080` rows, `2078` unique symbols, `1598` listed-market fetch candidates, `34` index candidates.
- Gap-chart `countBack=5000`: `FPT=4,852`, `VNM=5,000`, `VCB=4,227` bars.
- Parser dry-run: `14,079` rows, `2,781` pass, `11,290` warn, `8` fail quarantined.
- Controlled fetcher plan-only passed: `network_requests_made=False`, `planned_request_count=3`.
- Tiny execute passed for `FPT,VNM,VCB`: `network_requests_made=True`, `planned_request_count=3`, `failed_symbols=0`.
- FA endpoint discovery is in FPT-only probe stage; five non-secret FA candidates returned `403/auth_required`, so row-level FA JSON is still not captured.
- One-endpoint short-financial header-context diagnostic also returned `403/auth_required`; no Cookie/Auth was used and no raw FA JSON was saved.
- `httpx` session diagnostic loaded the VCI financial page with `200`, but the FA API still returned `403/auth_required`; metadata only, no raw FA JSON.
- `httpx` browser-session warm-up diagnostic (run `20260609T024007Z`): `trading.*` public warm-ups returned `200`; all `iq.*` warm-up + FA API endpoints returned `403/auth_required`; warm-up session state (trading subdomain cookies or `sec-ch-ua*` headers) was a likely contributing factor in the earlier `403` responses.
- `httpx` search-bar parity diagnostic (run `20260609T032924Z`): fresh `httpx.Client`, 8-header profile (no `sec-ch-ua*`, no `Cookie`, no `Authorization`), `trading-company-page` referer style — returned `200 JSON`, `data_length=2083`; shows `iq.*` is accessible with a clean request profile.
- `httpx` FA direct clean-profile diagnostic (run `20260609T035318Z`): same clean 8-header profile, `VCI/financial-statement?section=BALANCE_SHEET` — returned `200 JSON`, `data_keys=quarters,years`, `byte_size=354443`; FA endpoint accessible with clean profile.
- FA BALANCE_SHEET payload-shape review added (`docs/data_sources/vietcap_iq_fa_payload_shape_review.md`): wide-format, 33 quarters + 8 years, 331 opaque metric codes, `publicDate` present as candidate availability field (PIT semantics unconfirmed); no parser implemented yet.
- FA shape cross-check added (`docs/data_sources/vietcap_iq_fa_shape_cross_check.md`): VCI INCOME_STATEMENT (run `20260609T075846Z`) and FPT BALANCE_SHEET (run `20260609T075857Z`) both returned HTTP 200; initial section/symbol cross-check passed (three tested cases); `nos*` columns are null for FPT (not applicable for non-securities firms); parser dry-run design can start; no parser or DB write yet.
- FA parser dry-run implemented (`scripts/parse_vietcap_iq_fa_payloads_dry_run.py`): wide-to-long pivot on all three saved payloads; `34,563` total fact rows (`8,695` present, `23,885` zero, `1,983` missing/null); no DB write, no backtest; `line_item_name` empty (no mapping); `publicDate` PIT semantics unconfirmed; see `docs/data_sources/vietcap_iq_fa_parser_dry_run.md`.
- Main blocker: safe fetch policy, price adjustment semantics, corporate actions, FA metric name mapping, `publicDate` PIT validation, parser hardening for production, full-history FA fetch policy, and tool contracts.

---

## Progress Tracker

### Data source discovery

- [x] Vietcap IQ identified as full-market universe candidate.
- [x] HOSE/HSX kept as HOSE-specific source, not full-market source.
- [x] Some macro/bond context dry-run proofs exist.
- [x] Vietcap IQ financial statement endpoint candidates manually discovered for FPT.
- [ ] Vietcap IQ financial statement endpoint access/row-level JSON not verified yet.
- [ ] Vietcap IQ report/document endpoints not discovered yet.

### Vietcap IQ universe

- [x] `company/search-bar?language=1` verified as row-level universe JSON.
- [x] Saved payload parsed into local dry-run tables.
- [x] `index_universe.csv` separated.
- [x] Listed-market fetch candidate set created with `1598` symbols.
- [x] Excluded rows preserved for audit.
- [ ] Mentor/source confirmation needed for `floor`, `comTypeCode`, `isIndex`, `bank`, `index`, `icbLv*`.

### Vietcap IQ OHLCV / gap-chart

- [x] `gap-chart` verified for `FPT`, `VNM`, `VCB`.
- [x] `countBack=5000` tested for `FPT/VNM/VCB`.
- [x] `FPT/VNM/VCB` controlled raw outputs parsed locally: 14,079 rows, 2,781 pass, 11,290 warn, 8 OHLC fail rows quarantined.
- [x] `REE/SAM countBack=10000` tiny execute reached `2000-07-28` to `2026-06-05`; countBack remains a fallback, not true from/to.
- [x] `REE/SAM countBack=10000` controlled raw outputs parsed locally: 12,580 rows, 1,854 pass, 10,721 warn, 5 OHLC fail rows quarantined.
- [x] Saved-payload parser dry-run completed.
- [x] `8` source OHLC inconsistency rows quarantined.
- [ ] Adjusted/unadjusted semantics not confirmed.
- [ ] Corporate action/dividend/split handling not confirmed.

### Controlled fetcher

- [x] Skeleton exists.
- [x] Plan-only mode passed.
- [x] Checkpoint/resume and controlled batch design exists.
- [x] Random sleep design exists.
- [x] Tiny execute for `FPT/VNM/VCB` passed.
- [ ] Full `1598` symbol fetch not approved.

### Data preprocessing pipeline

- [x] Raw payload preservation pattern exists.
- [x] Parser dry-run pattern exists.
- [x] Quality split `pass/warn/fail` exists.
- [x] Fail rows are quarantined, not silently dropped.
- [ ] Canonical DB tables not implemented.
- [ ] Feature store not implemented.
- [ ] Dynamic universe layer not implemented.

### Product architecture

- [x] Mentor clarified backtest is not the whole product.
- [x] Canonical architecture doc created/updated at `docs/architecture/02_trading_agent_architecture_overview.md`.
- [ ] Mentor confirmation needed for agent/tool architecture and module boundaries.

### Agent/tool architecture

- [x] Direction: agent calls data, feature, strategy, risk, report tools directly.
- [x] First-draft tool contracts documented in architecture overview.
- [ ] Implementation-ready schemas still needed.

### Backtest/research module

- [x] Backtest reframed as one module/tool.
- [ ] Backtest engine not implemented.
- [ ] Backtest result schema not implemented.
- [ ] Strategy research loop not implemented.

### Financial statements / FA data

- [x] Vietcap IQ identified as candidate for profiles, statements, ratios, reports.
- [x] FA discovery plan added after controlled OHLCV proof.
- [x] FPT-only FA endpoint candidates added to local source-probe config.
- [ ] FPT-only non-secret FA probe returned `403/auth_required`; no raw JSON saved.
- [ ] FPT-only short-financial header-context diagnostic returned `403/auth_required`; parser planning remains blocked.
- [ ] VCI `httpx` session diagnostic returned page `200` but FA API `403/auth_required`; no raw FA JSON saved.
- [ ] VCI `httpx` browser-session warm-up diagnostic (run `20260609T024007Z`): `trading.*` public warm-ups `200`; all `iq.*` endpoints `403/auth_required`; warm-up session state (cookies or `sec-ch-ua*`) was a likely contributing factor; no raw FA JSON saved.
- [x] Search-bar parity diagnostic (run `20260609T032924Z`): fresh `httpx.Client`, 8-header profile — `iq.*` search-bar returned `200 JSON`, `data_length=2083`; `iq.*` accessible with clean request profile.
- [x] FA direct clean-profile diagnostic (run `20260609T035318Z`): same clean 8-header profile, `VCI/financial-statement?section=BALANCE_SHEET` — returned `200 JSON`, `data_keys=quarters,years`, `byte_size=354443`; FA endpoint accessible; raw payload captured.
- [x] FA BALANCE_SHEET payload-shape review written: wide-format, 33 quarters + 8 years, 331 opaque metric codes, `publicDate` present as candidate availability field (PIT semantics unconfirmed); no parser implemented; see `docs/data_sources/vietcap_iq_fa_payload_shape_review.md`.
- [x] FA shape cross-check: VCI INCOME_STATEMENT and FPT BALANCE_SHEET both HTTP 200; initial section/symbol cross-check passed (three tested cases); `nos*` null for non-securities firms; parser dry-run design can start; see `docs/data_sources/vietcap_iq_fa_shape_cross_check.md`.
- [x] FA dry-run parser implemented: `scripts/parse_vietcap_iq_fa_payloads_dry_run.py`; `34,563` fact rows from 3 saved payloads; no DB write, no backtest; `publicDate` PIT semantics unconfirmed; see `docs/data_sources/vietcap_iq_fa_parser_dry_run.md`.
- [ ] Full-history FA fetch not implemented.
- [ ] PIT availability and statement/ratio schema not finalized.

### RAG / text data future module

- [x] Reports/news identified as future evidence layer.
- [ ] Report-list endpoint not discovered.
- [ ] Document download/chunking not implemented.
- [ ] Vector DB/RAG pipeline not implemented.
- [ ] Citation and timestamp safety not implemented.

---

## Minimal Architecture Summary

- Detailed architecture is in `docs/architecture/02_trading_agent_architecture_overview.md`.
- `Trading Agent Orchestrator` is the product center.
- Agent should call data/feature/strategy/risk/report/RAG/backtest tools as needed.
- Backtest is only required when the user or research flow asks for simulation.
- Online questions like `HPG hôm nay thế nào?` should usually read cache/store through tools, not trigger heavy fetch/backtest.
- Current status is pre-DB, pre-backtest, pre-production agent tools.

---

## Current Technical Evidence

### Universe evidence

| Metric | Value |
|---|---:|
| Vietcap IQ search-bar JSON rows | `2080` |
| Vietcap IQ unique symbols | `2078` |
| Listed-market fetch candidate rows | `1598` |
| Listed-market fetch candidate unique symbols | `1598` |
| Index universe rows | `34` |
| HOSE overlap | `403/403` |

### Gap-chart `countBack=5000` evidence

| Symbol | Bars | Coverage |
|---|---:|---|
| `FPT` | `4,852` | `2006-12-13` to `2026-06-05` |
| `VNM` | `5,000` | `2006-05-18` to `2026-06-05` |
| `VCB` | `4,227` | `2009-06-30` to `2026-06-05` |

### Parser and fetcher evidence

| Metric | Value |
|---|---|
| Parser total rows | `14,079` |
| Parser pass | `2,781` |
| Parser warn | `11,290` |
| Parser fail quarantined | `8` |
| Controlled fetcher mode | `plan_only` |
| Network requests made | `False` |
| Planned request count | `3` |
| Tiny execute | Passed for `FPT,VNM,VCB`; `failed_symbols=0` |

---

## Current Risks / Blockers

- **Full `1598`-symbol fetch safety:** needs checkpoint/resume, controlled batches, random sleep, no aggressive async.
- **Rate-limit behavior:** unknown until tiny controlled execute.
- **Adjusted vs unadjusted semantics:** not confirmed.
- **Corporate action / dividend / split handling:** not defined.
- **`accumulatedValue` missing before `2022-09-15`:** trading value completeness caveat.
- **`8` OHLC failed rows quarantined:** source inconsistency, should not be auto-fixed.
- **QuestDB schema/migration:** not implemented.
- **Backtest:** not implemented.
- **Financial statement endpoints:** not discovered.
- **Agent tool interface:** first draft exists in architecture doc, but implementation schemas not finalized.
- **Online freshness policy:** cache/store vs controlled live calls not decided.
- **Point-in-time availability:** needed for statements, reports, macro, adjusted data, and backtest.

---

## Next Steps

### Immediate next steps

- [x] Refactor architecture content into canonical architecture doc.
- [ ] Review architecture with mentor.
- [x] Run tiny controlled execute for `FPT/VNM/VCB`.
- [x] Parse controlled raw outputs from tiny execute.
- [x] Start Vietcap IQ financial statement endpoint discovery.
- [ ] Resolve FPT-only FA endpoint access before parser planning.

### Short-term next steps

- [ ] Finalize safe fetcher execution policy.
- [ ] Expand controlled batch only after tiny execute review.
- [ ] Design dynamic universe/filter rules.
- [ ] Design feature engineering and feature store contract.
- [ ] Finalize first market data tool contract.

### Later steps

- [ ] QuestDB ingestion and dedup/upsert implementation.
- [ ] Backtest engine and result store.
- [ ] Strategy tools exposed to agent.
- [ ] RAG for reports/news.
- [ ] User-facing report generation.

---

## Mentor Confirmation Questions

- Kiến trúc agent/tool trong `docs/architecture/02_trading_agent_architecture_overview.md` đã đúng hướng chưa?
- Data tool cho agent nên expose function nào trước?
- Với OHLCV, nên ưu tiên full-history theo `countBack` lớn hay tìm API theo `from/to` date?
- Vietcap IQ financial statements nên ưu tiên income statement, balance sheet, cash flow, hay ratios trước?
- Tiny execute `FPT/VNM/VCB` đã đủ để bắt đầu mở rộng controlled batch chưa?
- Dynamic tradable universe nên filter theo tiêu chí nào trước?
- Backtest tool nên là research-only, user-callable, hay internal-only ở MVP?
- Online agent nên chỉ đọc cache/store hay có quyền gọi controlled live data tool?
- Với `accumulatedValue` thiếu trước `2022-09-15`, có cho phép features không cần trading value chạy trước không?
- Có cần bắt buộc lưu cả adjusted và unadjusted OHLCV ngay từ MVP nếu source chưa expose rõ không?

---

## Report Pointers

- Architecture: `docs/architecture/02_trading_agent_architecture_overview.md`.
- Source details: `docs/data_sources/01_vietcap_iq.md`, `docs/data_sources/hose_pipeline.md`.
- Ingestion plan: `docs/ingestion_v2_schema_plan.md`.
