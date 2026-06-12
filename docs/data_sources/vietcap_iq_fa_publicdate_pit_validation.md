---
title: vietcap_iq_fa_publicdate_pit_validation
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Vietcap IQ FA publicDate PIT Validation

## Purpose

Check whether Vietcap IQ FA `publicDate` can be treated as a point-in-time
availability/publication field. This package provides a machine-readable sample
CSV and offline validator. It does not unblock DB writes or backtests.

## Artifacts

- Sample CSV: `docs/data_sources/vietcap_iq_fa_publicdate_validation_samples.csv`
- Validator: `scripts/validate_vietcap_iq_fa_publicdate_samples.py`
- Tests: `tests/test_validate_vietcap_iq_fa_publicdate_samples.py`

The validator parses dates, verifies `date_delta_days`, preserves unresolved
statuses, groups duplicate statement sections by official evidence event, and
emits only `pit_red_flags_found`, `pit_inconclusive`, or
`pit_supported_small_sample`. It never emits `pit_confirmed_full`.

## Evidence Policy

Canonical PIT evidence must come from an official source: HOSE, HNX, company IR,
or official report/PDF metadata clearly tied to publication date. Secondary
aggregators such as Vietstock are non-canonical and do not populate
`official_disclosure_date` or contribute to the PIT gate.

## Sample

The 8-row sample uses saved FA payloads for FPT and VCI across annual and Q1
periods. Rows are statement-section observations; unique evidence events are
deduplicated by symbol, period label, normalized official URL, official
disclosure date, and official document title.

| Symbol | Section | Period | Vietcap date | Official date | Delta | Status | Confidence |
|---|---|---:|---|---|---:|---|---|
| FPT | BALANCE_SHEET | 2025 annual | 2026-03-20 | 2026-03-19 | +1 | `near_match_1_3_days` | medium |
| FPT | CASH_FLOW | 2025 annual | 2026-03-20 | 2026-03-19 | +1 | `near_match_1_3_days` | medium |
| FPT | BALANCE_SHEET | 2026 Q1 | 2026-04-28 | 2026-04-24 | +4 | `vietcap_after_official` | medium |
| FPT | CASH_FLOW | 2026 Q1 | 2026-04-28 | 2026-04-24 | +4 | `vietcap_after_official` | medium |
| VCI | BALANCE_SHEET | 2025 annual | 2026-02-13 | 2026-02-13 | 0 | `exact_match` | high |
| VCI | INCOME_STATEMENT | 2025 annual | 2026-02-13 | 2026-02-13 | 0 | `exact_match` | high |
| VCI | BALANCE_SHEET | 2026 Q1 | 2026-04-21 | 2026-04-20 | +1 | `near_match_1_3_days` | high |
| VCI | CASH_FLOW | 2026 Q1 | 2026-04-21 | 2026-04-20 | +1 | `near_match_1_3_days` | high |

## Results

- Statement rows credible: 8/8.
- Unique official disclosure events credible: 4/4.
- Unique issuers: 2.
- Red flags: 0.
- Final status: `pit_supported_small_sample`.

VCI official IR evidence is live-verified on `www.vietcap.com.vn`: FY2025
financial statements dated `2026-02-13`, and Q1 2026 financial statements dated
`2026-04-20`. FPT official IR evidence provides FY2025 financial statements
dated `2026-03-19` and Q1 2026 financial statements dated `2026-04-24`.

This is not full PIT confirmation. The evidence is date-level, not
timestamp-level. Broader issuer and exchange validation is still required before
`publicDate` can be used for PIT backtests.

## Gate Status

- `publicDate` PIT semantics: supported small sample, `pit_supported_small_sample`.
- Mapping coverage remains below 95%: BS 89.7%, IS 94.5%, CF 87.6%.
- DB write remains blocked.
- Backtest remains blocked.
- QuestDB schema not implemented.
- Full-history FA fetch not implemented.

## Next Action

Broaden official PIT validation beyond this 2-issuer, 4-event sample. Keep DB
write and backtest blocked until mapping coverage, PIT breadth, QuestDB schema,
and full-history fetch gates are resolved.
