---
title: 01_vietcap_iq
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Vietcap IQ

**Role:** primary candidate for Vietnamese symbol/instrument universe and FA
statements. Probe stage only; not promoted to canonical storage.

## Current Status

| Area | Status |
|---|---|
| Universe | Confirmed: 2,080 rows, 1,598 listed-market candidates |
| OHLCV gap-chart | HTTP 200 for FPT/VNM/VCB; parser dry-run 14,079 rows; full-universe fetch not approved |
| Controlled fetcher | Tiny execute passed; checkpoint/resume design in place |
| FA endpoint | HTTP 200 clean profile; BS/IS/CF confirmed for VCI and FPT |
| FA parser | Dry-run complete; 7 validation checks; strict mode |
| FA mapping | Option C resolver wired; Mode B active; 53,013 rows; 0 errors |
| PIT semantics | Supported small sample: 8/8 statement rows credible, 4/4 unique official disclosure events credible, 2 issuers, zero red flags, `pit_supported_small_sample` |
| Mapping coverage | Below 95% gate: BS 89.7% / IS 94.5% / CF 87.6%; 99 conflicts |
| DB write | Blocked |
| Backtest | Blocked |

## Key Constraints

- `line_item_name` legacy field stays empty.
- `publicDate` PIT evidence is date-level, not timestamp-level.
- `pit_supported_small_sample` is not full PIT confirmation.
- Broader issuer/exchange validation is required before PIT backtests.
- DB write remains blocked until mapping, PIT breadth, QuestDB schema, and
  full-history gates are resolved.
- Full-history FA fetch is not implemented.
- QuestDB schema is not implemented.

## Official Evidence

- FPT official IR: FY2025 financial statements `2026-03-19`; Q1 2026 financial
  statements `2026-04-24`.
- VCI official IR: FY2025 financial statements `2026-02-13`; Q1 2026 financial
  statements `2026-04-20`.
- Secondary aggregators are non-canonical.

## Open Blockers

- Mapping coverage below 95% per section.
- PIT validation is only a 2-issuer, 4-event small sample.
- HOSE structured disclosure endpoint unresolved.
- HNX structured source unresolved.
- Full-history FA fetch not implemented.
- DB write not implemented.
- Backtest not implemented.

## FA Docs Map

| Doc | Purpose |
|---|---|
| `vietcap_iq_fa_ingestion_v2_readiness.md` | Master gate table |
| `vietcap_iq_fa_publicdate_pit_validation.md` | PIT sample validator |
| `official_disclosure_ingestion_foundation.md` | Official disclosure adapter and CLI |
| `official_disclosure_source_discovery.md` | Official source matrix |
| `vietcap_iq_fa_parser_mapping_integration.md` | Parser integration note |
| `vietcap_iq_fa_mapping_coverage_gap_probe.md` | Mapping coverage gap |

## Documentation Policy

New or touched docs must remain 1500 words or fewer. Historical raw notes live
outside the Docusaurus docs tree in `notes/archive/`.
