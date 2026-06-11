---
title: progress_report
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Progress Report — Autonomous Trading Agent

**Phase:** Source discovery, parser dry-run, safe fetch planning.
No DB write, no backtest, no production agent tools yet.

---

## Current Status

| Area | Status |
|---|---|
| Vietcap IQ universe | 2,080 rows; 1,598 listed-market candidates (HOSE/HNX/UPCOM) |
| OHLCV gap-chart | FPT/VNM/VCB confirmed HTTP 200; parser dry-run: 14,079 rows |
| Controlled fetcher | Tiny execute passed for FPT/VNM/VCB; full-universe fetch not approved |
| FA endpoint | HTTP 200 (clean 8-header profile); BS/IS/CF confirmed for VCI and FPT |
| FA parser | Dry-run complete; 7 validation checks; `--strict` mode; deterministic sort |
| FA mapping integration | Option C resolver wired; 7 output columns; 53,013 rows validated; 0 errors |
| Test suite | **552 tests pass** (65 integration + 74 resolver + 46 firm-type + others) |
| DB write | **Blocked** |
| Backtest | **Blocked** |

---

## Main Blockers

- **Mapping coverage:** Below 95% per section — BS 89.4% / IS 92.3% / CF 86.7%; 88 name conflicts in union mapping.
- **PIT semantics:** `publicDate` unconfirmed — cross-check vs HOSE/HNX filing records required before any backtest.
- **DB write:** Blocked until all §17 gates met (see `vietcap_iq_fa_ingestion_v2_readiness.md`).
- **Full-history FA fetch:** Not implemented — blocked on mapping, PIT, and schema gates.
- **Backtest:** Blocked on DB write.

---

## Key Validation Numbers

| Metric | Value |
|---|---|
| Universe symbols | 2,080 total / 1,598 listed-market candidates |
| OHLCV gap-chart bars (FPT) | 4,852 (2006–2026) |
| FA parser fact rows (5 payloads) | 53,013 |
| FA parser errors | 0 |
| FA mapping named rows | 43,214 / 53,013 (81.5% at row level) |
| Mapping coverage gate (95%) | Not met — union peak 92.3% (IS only) |
| FA tests | 65 integration + 74 resolver + 46 firm-type |
| Total tests passing | 552 |

---

## Architecture

- Product: **agent/tool product** — not just a backtest pipeline.
- Full doc: `docs/architecture/02_trading_agent_architecture_overview.md`.
- Backtest is one module/tool; current state is pre-DB, pre-backtest, pre-production.
- Online questions (e.g. "HPG hôm nay thế nào?") should read cache/store, not trigger heavy fetches.

---

## Next Steps

1. Close mapping coverage gap (probe additional firm types; target ≥95% per section).
2. Validate `publicDate` PIT semantics — cross-check 5–10 sample rows vs HOSE/HNX filing dates.
3. Design canonical QuestDB schema and dedup/upsert policy.
4. Build full-history FA fetcher (after gates above are met).
5. Merge core docs compaction PR #9 after review, then iterate on coverage gap and PIT validation.

---

## Docs Policy

All docs under `docs/` target ≤1500 words. All files comply as of PR #9 (2026-06-11).

| File | Words | Status |
|---|---|---|
| `docs/architecture/02_trading_agent_architecture_overview.md` | 1497 | Compliant |
| `docs/data_sources/hose_pipeline.md` | 1151 | Compliant |
| `docs/autonomous_trading_agent_dev_master.md` | 1496 | Compliant |
| `docs/data_sources/vietcap_iq_fa_ingestion_v2_readiness.md` | 846 | Compliant |
| `docs/data_sources/vietcap_iq_fa_mapping_integration_strategy.md` | 1159 | Compliant |
| `docs/data_sources/vietcap_iq_fa_firm_type_determination.md` | 1110 | Compliant |
| `docs/data_sources/vietcap_iq_fa_mapping_coverage_bank_probe.md` | 892 | Compliant |
| `docs/data_sources/vietcap_iq_fa_mapping_cashflow_probe.md` | 887 | Compliant |
| `docs/ingestion_v2_schema_plan.md` | 1473 | Compliant |
| `docs/data_sources/vietcap_iq_fa_parser_mapping_integration.md` | 876 | Compliant |
| All other `docs/` files (stubs + minor docs) | below 500 | Compliant |

Archived historical detail (probe notes, paper notes, writing guide, legacy sections) lives in `notes/archive/` (outside Docusaurus tree).
