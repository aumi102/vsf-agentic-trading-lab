---
title: vietcap_iq_fa_publicdate_pit_validation
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Vietcap IQ FA publicDate PIT Validation

## Purpose

Check whether Vietcap IQ FA `publicDate` can be treated as a point-in-time
availability/publication field. This PR adds a machine-readable sample and an
offline validator. It does not unblock DB writes or backtests.

## Artifacts

- Sample CSV: `docs/data_sources/vietcap_iq_fa_publicdate_validation_samples.csv`
- Validator: `scripts/validate_vietcap_iq_fa_publicdate_samples.py`
- Tests: `tests/test_validate_vietcap_iq_fa_publicdate_samples.py`

The validator reads the CSV, parses dates, verifies `date_delta_days`, normalizes
blank statuses, preserves unresolved statuses, counts confidence levels, and
emits one of: `pit_red_flags_found`, `pit_inconclusive`, or
`pit_supported_small_sample`. It never emits `pit_confirmed_full`.

## Sample Selection

The 8-row sample uses saved local FA payloads only. It covers FPT and VCI,
BALANCE_SHEET / INCOME_STATEMENT / CASH_FLOW, annual and Q1 periods, and recent
periods likely to have accessible disclosure pages.

Saved payload sources:

- FPT BALANCE_SHEET: `20260609T075857Z`
- FPT CASH_FLOW: `20260610T025440Z`
- VCI BALANCE_SHEET: `20260609T035318Z`
- VCI INCOME_STATEMENT: `20260609T075846Z`
- VCI CASH_FLOW: `20260610T025429Z`

## Validation Method

For each sample row, compare Vietcap `publicDate` to the best official or
authoritative disclosure evidence found in a tiny manual lookup. FPT official IR
disclosures were accessible at `https://fpt.com/en/ir/information-disclosures`.
Vietcap official disclosure pages returned 403 from this environment, and no
HOSE disclosure date was recovered for VCI in this pass.

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
| VCI | BALANCE_SHEET | 2025 annual | 2026-02-13 |  |  | `official_not_found` | none |
| VCI | INCOME_STATEMENT | 2025 annual | 2026-02-13 |  |  | `official_not_found` | none |
| VCI | BALANCE_SHEET | 2026 Q1 | 2026-04-21 |  |  | `official_not_found` | none |
| VCI | CASH_FLOW | 2026 Q1 | 2026-04-21 |  |  | `official_not_found` | none |

Validator counts:

- `near_match_1_3_days`: 2
- `vietcap_after_official`: 2
- `official_not_found`: 4
- `exact_match`, `vietcap_before_official`, `ambiguous_basis`, `not_comparable`: 0
- Confidence: medium=4, none=4

## Findings

Final PIT sample status: `pit_inconclusive`.

FPT rows are supportive: none are earlier than official company IR disclosure
dates, and the Q1 rows are conservative by 4 days. No credible
`vietcap_before_official` red flag was observed.

The sample is still inconclusive because 4/8 rows lack official evidence and
only one issuer has comparable official evidence. `publicDate` remains
unconfirmed and must not be used for PIT backtests yet.

## Gate Status

- Mapping coverage gate remains below 95%: BS 89.7%, IS 94.5%, CF 87.6%.
- DB write remains blocked.
- Backtest remains blocked.
- QuestDB schema not designed.
- Full-history FA fetch not implemented.

## Next Action

Broaden the PIT check to exchange records for VCI plus at least one more HOSE
issuer. Require no credible `vietcap_before_official` rows before treating
`publicDate` as a PIT availability field.
