---
title: vietcap_iq_fa_publicdate_pit_validation
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Vietcap IQ FA publicDate PIT Validation

## Purpose

Check whether Vietcap IQ FA `publicDate` can be treated as a point-in-time
availability/publication field. This package adds a machine-readable sample and
an offline validator. It does not unblock DB writes or backtests.

## Artifacts

- Sample CSV: `docs/data_sources/vietcap_iq_fa_publicdate_validation_samples.csv`
- Validator: `scripts/validate_vietcap_iq_fa_publicdate_samples.py`
- Tests: `tests/test_validate_vietcap_iq_fa_publicdate_samples.py`

The validator reads the CSV, parses dates, verifies `date_delta_days`, normalizes
blank statuses, preserves unresolved statuses, counts confidence levels, and
emits one of: `pit_red_flags_found`, `pit_inconclusive`, or
`pit_supported_small_sample`. It never emits `pit_confirmed_full`.

Optional flag `--check-payload-paths` verifies that each `payload_path` in the
CSV resolves to an existing file under the repo root.

## Sample Selection

The 8-row sample uses saved local FA payloads only. It covers FPT and VCI,
BALANCE_SHEET / INCOME_STATEMENT / CASH_FLOW, annual and Q1 periods.

Saved payload sources:

- FPT BALANCE_SHEET: `20260609T075857Z`
- FPT CASH_FLOW: `20260610T025440Z`
- VCI BALANCE_SHEET: `20260609T035318Z`
- VCI INCOME_STATEMENT: `20260609T075846Z`
- VCI CASH_FLOW: `20260610T025429Z`

A third HOSE issuer (HPG) was considered but blocked: the saved HPG payload
(`20260611T083445Z`) is a metrics-code mapping probe with no financial statement
`publicDate` values.

## Validation Method

For each sample row, compare Vietcap `publicDate` to the best official or
authoritative disclosure evidence found in a targeted manual lookup.

FPT official IR disclosures were accessible at
`https://fpt.com/en/ir/information-disclosures` (company IR — confidence
`medium`).

For VCI, the official Vietcap IR page returned a login portal (inaccessible) and
the HOSE disclosure page returned no VCI records. Two Vietstock.vn secondary
source articles were found and verified:

- 2025 annual: https://vietstock.vn/2026/02/vci-bao-cao-tai-chinh-rieng-le-nam-2025-737-1403936.htm
  Published 2026-02-13 14:42 with standalone BCTC 2025 PDF attached.
- Q1 2026: https://vietstock.vn/2026/04/vci-bctc-quy-1-nam-2026-737-1430835.htm
  Published 2026-04-20 with Q1 2026 BCTC PDF attached.

Vietstock is a reputable Vietnamese financial news aggregator but is not the
official HOSE disclosure channel. VCI rows are therefore marked confidence `low`.

Normalized `match_status` values: `exact_match`, `near_match_1_3_days`,
`vietcap_after_official`, `vietcap_before_official`, `official_not_found`,
`ambiguous_basis`, and `not_comparable`.

## Sample Results

| Symbol | Section | Period | Vietcap date | Official date | Delta | Status | Confidence |
|---|---|---:|---|---|---:|---|---|
| FPT | BALANCE_SHEET | 2025 annual | 2026-03-20 | 2026-03-19 | +1 | `near_match_1_3_days` | medium |
| FPT | CASH_FLOW | 2025 annual | 2026-03-20 | 2026-03-19 | +1 | `near_match_1_3_days` | medium |
| FPT | BALANCE_SHEET | 2026 Q1 | 2026-04-28 | 2026-04-24 | +4 | `vietcap_after_official` | medium |
| FPT | CASH_FLOW | 2026 Q1 | 2026-04-28 | 2026-04-24 | +4 | `vietcap_after_official` | medium |
| VCI | BALANCE_SHEET | 2025 annual | 2026-02-13 | 2026-02-13 | 0 | `exact_match` | low |
| VCI | INCOME_STATEMENT | 2025 annual | 2026-02-13 | 2026-02-13 | 0 | `exact_match` | low |
| VCI | BALANCE_SHEET | 2026 Q1 | 2026-04-21 | 2026-04-20 | +1 | `near_match_1_3_days` | low |
| VCI | CASH_FLOW | 2026 Q1 | 2026-04-21 | 2026-04-20 | +1 | `near_match_1_3_days` | low |

Validator counts:

- `exact_match`: 2
- `near_match_1_3_days`: 4
- `vietcap_after_official`: 2
- `vietcap_before_official`: 0 — no red flags
- `official_not_found`: 0 (down from 4 in PR #12)
- `ambiguous_basis`, `not_comparable`: 0
- Confidence: medium=4, low=4, high=0, none=0

## Findings

Final PIT sample status: `pit_inconclusive`.

All 8 rows now have comparison evidence. No `vietcap_before_official` red flag
was found in either issuer. Vietcap `publicDate` values are at or after the
disclosure date for every row.

The status remains `pit_inconclusive` because the validator threshold for
`pit_supported_small_sample` requires credible-comparable ratio ≥ 0.70, and
credible-comparable is defined as match_status in a comparable set AND confidence
`high` or `medium`. The 4 VCI rows are confidence `low` (secondary source) and
are therefore excluded from the credible count, giving a ratio of 4/8 = 0.50.

To upgrade to `pit_supported_small_sample`, official HOSE disclosure records or
accessible company IR dates for VCI (or a different second issuer) are needed.

`publicDate` remains unconfirmed and must not be used for PIT backtests.

## Gate Status

- `publicDate` PIT semantics: **Unconfirmed** — status `pit_inconclusive`.
- Mapping coverage gate remains below 95%: BS 89.7%, IS 94.5%, CF 87.6%.
- DB write remains blocked.
- Backtest remains blocked.
- QuestDB schema not designed.
- Full-history FA fetch not implemented.

## Next Action

Obtain official HOSE exchange disclosure dates for VCI (or another HOSE issuer
with a saved FA financial statement payload) at confidence `high` or `medium`.
Four more credible-comparable rows would move the ratio above 0.70 and upgrade
the status to `pit_supported_small_sample`.
