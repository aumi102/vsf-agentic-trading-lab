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
| FA mapping integration | Option C resolver wired; Mode B active for general symbols; 53,013 rows validated; 0 errors |
| FA mapping coverage gap probe | 3 general/fund symbols probed; union: 7 payloads, all known groups sampled; BS 89.7% / IS 94.5% / CF 87.6%; gap appears structural |
| FA `publicDate` PIT spot-check | 8-row CSV validator returns `pit_supported_small_sample`; 8/8 credible; FPT and VCI official IR live-verified; Vietstock non-canonical |
| Official Disclosure Foundation v1 | Hardened+VCI: FPT IR 20 records (pass); VCI FY2025 `2026-02-13` (pass); VCI Q1 2026 `2026-04-20` (pass); HOSE=js_app_shell; HNX=timeout. Honest UA; TLS always verified; no pseudo rows. |
| Test suite | **692 tests pass** (71 integration + 74 resolver + 54 firm-type + 19 PIT validator + 107 disclosure + others) |
| DB write | **Blocked** |
| Backtest | **Blocked** |

---

## Main Blockers

- **Mapping coverage:** Below 95% per section — BS 89.7% / IS 94.5% / CF 87.6% (7 payloads, all known groups sampled). Gap appears structural for `/metrics` endpoint: residual codes (`bsi*`, `bss*`, `bsb*`, `cfs*`, `cfi*`) absent from all probed mapping payloads.
- **PIT semantics:** `pit_supported_small_sample` (8/8 credible, 0 red flags); FPT and VCI official IR live-verified; Vietstock non-canonical; do not claim full PIT confirmation; do not use for PIT backtest yet.
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
| FA mapping named rows | 46,412 / 53,013 (87.5% combined validation view) |
| FPT BS+CF Mode B code-row naming | 485 / 556 named (87%); primary=163; consensus=322; conflict_skipped=2; not_covered=62 |
| FA `publicDate` PIT sample | 8 rows; 2 exact_match, 4 near_match, 2 vietcap_after_official; 0 red flags; credible ratio 8/8 = 1.00 |
| Mapping coverage gate (95%) | Not met — union peak 94.5% (IS); gap structural; all known groups sampled |
| FA tests | 71 integration + 74 resolver + 54 firm-type |
| Disclosure foundation tests | 107 (+ VCI parser, security hardening, URL/date validation, category semantics) |
| Total tests passing | 692 |

---

## Architecture

- Product: **agent/tool product** — not just a backtest pipeline.
- Full doc: `docs/architecture/02_trading_agent_architecture_overview.md`.
- Backtest is one module/tool; current state is pre-DB, pre-backtest, pre-production.
- Online questions (e.g. "HPG hôm nay thế nào?") should read cache/store, not trigger heavy fetches.

---

## Next Steps

1. ~~Close mapping coverage gap (probe additional firm types)~~ — gap appears structural; all known groups sampled.
2. ~~Activate FPT primary mapping for general symbols~~ — Mode B implemented; legacy `line_item_name` remains empty.
3. Decide on coverage gate response: lower threshold, or supplement mapping from a secondary source.
4. ~~Build official disclosure source discovery/crawler POC for HOSE/HNX/company IR~~ — Foundation v1 hardened+VCI: FPT IR (20 records), VCI FY2025+Q1 2026 (2 records, exact/near match). Honest UA, TLS enforced, no pseudo rows. PIT gate: `pit_supported_small_sample`.
5. Design canonical QuestDB schema and dedup/upsert policy.
6. Build full-history FA fetcher (after gates above are met).

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
| `docs/data_sources/vietcap_iq_fa_mapping_coverage_gap_probe.md` | ~1050 | Compliant |
| `docs/ingestion_v2_schema_plan.md` | 1473 | Compliant |
| `docs/data_sources/vietcap_iq_fa_parser_mapping_integration.md` | 876 | Compliant |
| All other `docs/` files (stubs + minor docs) | below 500 | Compliant |

Archived historical detail (probe notes, paper notes, writing guide, legacy sections) lives in `notes/archive/` (outside Docusaurus tree).
