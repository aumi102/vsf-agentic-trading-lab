---
title: 01_vietcap_iq
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Vietcap IQ

**Role:** Primary candidate for full-market Vietnamese symbol/instrument universe.
Secondary: company profiles, FA statements, financial ratios, reports.
Probe stage only — not promoted to canonical storage.

---

## Current Status

| Area | Status |
|---|---|
| Universe | Confirmed — 2,080 rows, 1,598 listed-market candidates (HOSE/HNX/UPCOM, `isIndex=false`) |
| OHLCV gap-chart | HTTP 200 for FPT/VNM/VCB; parser dry-run: 14,079 rows; full-universe fetch not approved |
| Controlled fetcher | Tiny execute passed for FPT/VNM/VCB; checkpoint/resume design in place |
| FA endpoint | HTTP 200 (clean 8-header profile); BS/IS/CF confirmed for VCI and FPT |
| FA parser | Dry-run complete; 7 validation checks; `--strict` mode; 583 tests pass |
| FA mapping integration | Option C resolver wired; Mode B active; 7 output columns; 71 integration tests; 53,013 rows; 0 errors |
| DB write | **Blocked** — all §17 gates not met |
| Backtest | **Blocked** — DB write not implemented |
| PIT semantics | **Unconfirmed** — sample status `pit_inconclusive`; FPT canonical evidence supportive; VCI official evidence unresolved |
| Mapping coverage | Below 95% gate — union: BS 89.7% / IS 94.5% / CF 87.6%; 99 conflicts |

---

## Key Constraints

- `line_item_name` (legacy) is always empty — never populated by mapping resolver.
- `publicDate` PIT semantics unconfirmed — sample status `pit_inconclusive`; FPT canonical evidence supportive; VCI official evidence unresolved; do not use for PIT backtest yet.
- DB write blocked until all gates in `vietcap_iq_fa_ingestion_v2_readiness.md` §17 are met.
- No full-history FA fetch until mapping, PIT, and schema gates are cleared.
- Fetch universe (1,598 symbols) is not the final tradable asset list — liquidity and
  data-completeness filters apply during the strategy phase.

---

## Open Blockers

- Mapping coverage below 95% per section; 99 name conflicts remain.
- `publicDate` PIT semantics unconfirmed — official HOSE/HNX/company IR disclosure dates for VCI needed; Vietstock secondary leads non-canonical.
- Full-history FA fetch not implemented.
- DB write not implemented (QuestDB schema not designed).
- Backtest not implemented.

---

## FA Docs Map

| Doc | Purpose |
|---|---|
| `vietcap_iq_fa_ingestion_v2_readiness.md` | Master gate table — confirmed facts, open gates, all policies |
| `vietcap_iq_fa_mapping_integration_strategy.md` | Option C design record — options A/B/C, lookup contract |
| `vietcap_iq_fa_parser_mapping_integration.md` | Parser integration block note (876 words) |
| `vietcap_iq_fa_publicdate_pit_validation.md` | `publicDate` PIT sample validator |
| `vietcap_iq_fa_mapping_resolver_tests.md` | Resolver implementation and test coverage (74 tests) |
| `vietcap_iq_fa_firm_type_determination.md` | Firm-type determination design (Approach D) |
| `vietcap_iq_fa_mapping_coverage_bank_probe.md` | Bank/insurance union coverage analysis |
| `vietcap_iq_fa_mapping_cashflow_probe.md` | VCI mapping baseline and CASH_FLOW probe |
| `vietcap_iq_fa_metric_mapping_discovery.md` | VCI-only coverage tables |
| `notes/archive/vietcap_iq_legacy_notes.md` (outside docs) | Historical probe logs, URL inventory, field semantics — non-canonical |

---

## Documentation Policy

- New or touched docs: target 1500 words or fewer.
- Compact overview first; detailed historical probes belong in archival files.
- Future work: update existing block notes — do not create new long reports.
- Core current status lives in this file and the block notes under `docs/data_sources/`.
- Historical raw notes are in `notes/archive/vietcap_iq_legacy_notes.md` — outside canonical docs, non-navigable.
